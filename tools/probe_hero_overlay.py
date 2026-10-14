#!/usr/bin/env python3
"""py65 probe: find HERO's ball/missile overlay writes (asymmetric tiles).

Hypothesis under test (2026-10-04): the asymmetric middle-band tile seen in
screenshots (x240-271 = 8clks, color tracks COLUPF, y8-167) is the BALL
(ENABL/RESBL/HMBL), possibly + missile1 — not per-line PF writes.

Model per docs/hero_asymmetric_rooms.md: flat 8K, ROM[0:4096]=$D000-$DFFF,
ROM[4096:8192]=$F000-$FFFF, reset vector $FFFC-> $F000. Virtual clock:
WSYNC aligns to 76, TIM64T/INTIM emulated, frame = VSYNC bit2 rising edge.

Usage: probe_hero_overlay.py [frames]   (default 400)
"""
import sys
from pathlib import Path

from py65.devices.mpu6502 import MPU

ROM_PATH = Path(__file__).resolve().parents[1] / "src" / "hero" / "hero.bin"

# TIA write registers we care about (addr -> name)
WATCH = {
    0x0D: "PF0", 0x0E: "PF1", 0x0F: "PF2",
    0x08: "COLUPF", 0x07: "COLUP1", 0x0A: "CTRLPF",
    0x1F: "ENABL", 0x14: "RESBL", 0x24: "HMBL",
    0x1E: "ENAM1", 0x13: "RESM1", 0x23: "HMM1",
    0x1D: "ENAM0", 0x12: "RESM0", 0x22: "HMM0",
    0x1B: "GRP0", 0x1C: "GRP1",
    0x10: "RESP0", 0x11: "RESP1",
}

# cave band scanlines (relative to VSYNC) from hero_asymmetric_rooms.md
CAVE_LO, CAVE_HI = 44, 175


class Probe:
    def __init__(self, rom: bytes):
        self.mpu = MPU()
        mem = bytearray(0x10000)
        mem[0xD000:0xE000] = rom[0:4096]
        mem[0xF000:0x10000] = rom[4096:8192]
        self.mem = mem
        self.v = 0                 # virtual cycle clock
        self.tim_dead = None
        self.frame = 0
        self.line0 = 0             # v at frame start (VSYNC rise)
        self.vsync_prev = 0
        self.events = []           # (frame, scanline, phase, name, value)
        self.instr_at = {}         # pc -> count (for landmarks)
        mpu = self.mpu
        mpu.memory = self          # intercept via our __getitem__/__setitem__

    # --- memory interface ------------------------------------------------
    def __getitem__(self, addr):
        addr &= 0xFFFF
        if addr == 0x0284:  # INTIM
            if self.tim_dead is None:
                return 0
            return max(0, (self.tim_dead - self.v) // 64) & 0xFF
        return self.mem[addr]

    def __setitem__(self, addr, val):
        addr &= 0xFFFF
        val &= 0xFF
        self.mem[addr] = val
        if addr == 0x0002:  # WSYNC -> align to next 76-cycle boundary
            self._align = True
        elif addr == 0x0294:  # TIM1024T
            self.tim_dead = self.v + 1024 * val
        elif addr == 0x0295:  # TIM16T
            self.tim_dead = self.v + 16 * val
        elif addr == 0x0296:  # TIM64T
            self.tim_dead = self.v + 64 * val
        elif addr == 0x0297:  # TIM1T
            self.tim_dead = self.v + val
        elif addr == 0x0000 and (val & 2) and not (self.vsync_prev & 2):
            # VSYNC rising edge (D1, value seen $82) = frame boundary
            if self.line0:
                self.frame += 1
            self.line0 = self.v
            self.vsync_prev = val
        elif addr == 0x0000:
            self.vsync_prev = val
        if addr in WATCH:
            line = (self.v - self.line0) // 76
            self.events.append(
                (self.frame, line, self.v % 76, WATCH[addr], val,
                 getattr(self, "_pc0", -1))
            )

    # --- execution -------------------------------------------------------
    def step(self):
        pc = self.mpu.pc
        self.instr_at[pc] = self.instr_at.get(pc, 0) + 1
        self._pc0 = pc
        c0 = self.mpu.processorCycles
        self.mpu.step()
        cyc = self.mpu.processorCycles - c0
        self.v += cyc
        if getattr(self, "_align", False):
            self.v = -(-self.v // 76) * 76
            self._align = False

    def run(self, nframes, input_fn=None):
        guard = 0
        limit = nframes * 40000
        while self.frame < nframes:
            guard += 1
            if guard > limit:
                raise RuntimeError(
                    f"frame stalled at {self.frame} after {guard} steps "
                    "(no VSYNC?)"
                )
            if input_fn:
                input_fn(self)
            self.step()


def default_input(p):
    """Title -> game: RESET pulse f40; then wander with fire bursts."""
    f = p.frame
    swchb = 0xFD if 40 <= f < 42 else 0xFF  # RESET low = pressed
    p.mem[0x0282] = swchb
    # joystick: rotate direction every 16 frames from f60
    dirs = (0xFF, 0x7F, 0xDF, 0xBF, 0xEF)  # neutral, right, down, left, up
    p.mem[0x0280] = dirs[(f // 16) % 5]
    # fire bursts every 40 frames
    p.mem[0x00C0] = 0x00 if (f % 40) < 6 and f >= 60 else 0x80


def analyze(p):
    """Per-(frame,line) final state of ENABL/ENAM0/ENAM1 + late PF writes."""
    final = {}   # (f, ln) -> {name: (phase, val)}
    late_pf = {}  # (f, ln) -> count of PF writes with phase >= 50
    for (f, ln, ph, nm, val, _pc) in p.events:
        if nm in ("ENABL", "ENAM0", "ENAM1"):
            final.setdefault((f, ln), {})[nm] = (ph, val)
        if nm in ("PF0", "PF1", "PF2") and ph >= 50:
            late_pf[(f, ln)] = late_pf.get((f, ln), 0) + 1

    def runs_of(pred, lo, hi):
        byf = {}
        for (f, ln), d in final.items():
            if lo <= ln <= hi and pred(d):
                byf.setdefault(f, []).append(ln)
        out = []
        for f, lns in byf.items():
            lns = sorted(set(lns))
            s = pr = lns[0]
            for ln in lns[1:]:
                if ln - pr > 2:
                    out.append((f, s, pr))
                    s = ln
                pr = ln
            out.append((f, s, pr))
        return out

    # value histograms: hero's bar ball is known-visible -> its ENABL value
    # in HUD lines reveals the enable bit
    from collections import Counter
    hist = {"ENABL": Counter(), "ENAM0": Counter(), "ENAM1": Counter()}
    for (f, ln, ph, nm, val, _pc) in p.events:
        if nm in hist:
            region = "cave" if CAVE_LO <= ln <= CAVE_HI else ("hud" if ln > CAVE_HI else "pre")
            hist[nm][(region, val)] += 1
    for nm, c in hist.items():
        print(f"{nm} (region,val) top:", c.most_common(12))

    en_on = lambda d: "ENABL" in d and (d["ENABL"][1] & 0x03)
    m0_on = lambda d: "ENAM0" in d and (d["ENAM0"][1] & 0x03)
    m1_on = lambda d: "ENAM1" in d and (d["ENAM1"][1] & 0x03)

    for name, pred in (("ENABL", en_on), ("ENAM0", m0_on), ("ENAM1", m1_on)):
        rs = [r for r in runs_of(pred, CAVE_LO, CAVE_HI) if r[2] - r[1] >= 8]
        print(f"{name} >=8-line enabled runs in cave: {len(rs)}")
        for r in sorted(rs)[:10]:
            f, a, b = r
            # positions set this frame for that object
            pos = [
                (nm, ln, ph) for (ff, ln, ph, nm, v, _pc) in p.events
                if ff == f and nm in ("RESBL", "RESM0", "RESM1")
            ]
            print(f"  f{f} lines {a}-{b} ({b-a+1}) pos={pos[:6]}")

    lf = sorted(late_pf.items())
    print(f"lines with phase>=50 PF writes: {len(lf)}")
    byf = {}
    for (f, ln), n in lf:
        byf.setdefault(f, []).append(ln)
    for f in sorted(byf)[:6]:
        print(f"  f{f}: late-PF lines {sorted(byf[f])[:30]}")


def main():
    nframes = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    rom = ROM_PATH.read_bytes()
    assert len(rom) == 8192, f"expected 8192B, got {len(rom)}"
    p = Probe(rom)
    p.run(nframes, input_fn=default_input)

    ev = p.events
    print(f"frames={p.frame} events={len(ev)}")
    analyze(p)

    # RESBL positions (ball coarse) summary
    resbl = [(f, ln, ph) for (f, ln, ph, nm, v, _pc) in ev if nm == "RESBL"]
    cave_res = [x for x in resbl if CAVE_LO <= x[1] <= CAVE_HI]
    print(f"RESBL total={len(resbl)} cave={len(cave_res)}")
    for f, ln, ph in cave_res[:12]:
        print(f"  RESBL f{f} line={ln} phase={ph} -> clk~{3*ph}")

    print("CTRLPF values:", sorted({hex(v) for (_, _, _, nm, v, _pc) in ev if nm == "CTRLPF"}))
    print("HMBL values:", sorted({hex(v) for (_, _, _, nm, v, _pc) in ev if nm == "HMBL"}))
    print("HMM1 values:", sorted({hex(v) for (_, _, _, nm, v, _pc) in ev if nm == "HMM1"})[:12])
    top = sorted(p.instr_at.items(), key=lambda kv: -kv[1])[:12]
    print("hottest PCs:", [(hex(pc), n) for pc, n in top])


if __name__ == "__main__":
    main()
