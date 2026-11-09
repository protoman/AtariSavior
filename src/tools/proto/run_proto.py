#!/usr/bin/env python3
"""Build the HERO-style kernel prototype and measure it in the TIA model.

  run_proto.py [--keep DIR]

Checks (all on the simulated 4K ROM, tools/tia_render.py beam model):
  * frame length (262 lines) and the cycle at which every kernel line's WSYNC lands
  * every player (P0) and object (P1) art row shows on exactly its own scanline, for every
    top line from -25 to 150 (across all four band boundaries), both frames/designs
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from py65.devices.mpu6502 import MPU  # noqa: E402

import tia_render as T  # noqa: E402

H0, H1 = 22, 16
DOOR = None


def build(outdir, overscan):
    subprocess.check_call([sys.executable, str(HERE.parent / "cave_kernel_gen.py"), str(outdir)])
    (outdir / "main.asm").write_text((HERE / "main.asm").read_text())
    r = subprocess.run(["dasm", "main.asm", "-f3", "-oproto.bin", "-lproto.lst",
                        "-sproto.sym", f"-DOVERSCAN={overscan}"], cwd=outdir,
                       capture_output=True, text=True)
    if r.returncode or "error" in r.stdout.lower():
        print(r.stdout, r.stderr)
        sys.exit("dasm failed")
    sym = {}
    for line in (outdir / "proto.sym").read_text().splitlines()[1:]:
        p = line.split()
        if len(p) >= 2:
            try:
                sym[p[0]] = int(p[1], 16)
            except ValueError:
                pass
    return (outdir / "proto.bin").read_bytes(), sym


class Base:
    def __init__(self, rom):
        self.rom = rom
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 0
        self.swcha = 0xFF
        self.inpt4 = 0x80
        self.frames = 0
        self.mpu = MPU(memory=self)

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.rom[a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v & 0xFF
        # everything else (TIA/RIOT) is handled by TiaConsole


class Proto(T.TiaConsole, Base):
    pass


def make(rom, sym):
    con = Proto(rom)
    con.sym = sym
    con.pc_frame = sym["StartFrame"]
    con.mpu.pc = 0xF000
    con.tia_init()
    return con


def poke(con, name, v):
    con.ram[con.sym[name] & 0x7F] = v & 0xFF


def frame_info(con, log):
    by = {}
    for t, reg, v in log:
        by.setdefault(t // T.LINE, []).append((t % T.LINE, reg, v))
    first, last = min(by), max(by)
    k0 = [ln for ln, ev in by.items() if any(r == T.VBLANK and v == 0 for _, r, v in ev)]
    return by, first, last, (max(k0) + 1 if k0 else None)


def shown(con, by, first, last, k0):
    beam = con.beam
    orig = T.Beam.pixel
    seen0, seen1 = {}, {}
    cur = [0]

    def px(self, x):
        if not self.r[T.VBLANK] & 2:
            if x == self.pos["p0"] % 160:
                g = self.old0 if self.r[T.VDELP0] & 1 else self.new0
                if g & 0x80:
                    seen0[cur[0]] = (g >> 6 & 1, g & 31)
            if x == self.pos["p1"] % 160:
                g = self.old1 if self.r[T.VDELP1] & 1 else self.new1
                if g & 0x80:
                    seen1[cur[0]] = (g >> 6 & 1, g & 31)
        return orig(self, x)
    T.Beam.pixel = px
    try:
        for line in range(first, last + 1):
            cur[0] = line - k0
            ev = sorted(by.get(line, ()), key=lambda e: e[0])
            ei = 0
            for clk in range(228):
                while ei < len(ev) and 3 * ev[ei][0] + 3 <= clk:
                    beam.write(ev[ei][1], ev[ei][2], ev[ei][0])
                    ei += 1
                if clk >= 68:
                    beam.pixel(clk - 68)
            while ei < len(ev):
                beam.write(ev[ei][1], ev[ei][2], ev[ei][0])
                ei += 1
    finally:
        T.Beam.pixel = orig
    return seen0, seen1


def colours(by, k0, n_lines=144):
    """{line: (COLUP0 write, COLUP1 write)} of the last write on each kernel line."""
    out = {}
    for n in range(n_lines):
        c0 = [v for t, r, v in by.get(k0 + n, []) if r == T.COLUP0]
        c1 = [v for t, r, v in by.get(k0 + n, []) if r == T.COLUP1]
        out[n] = (c0[-1] if c0 else None, c1[-1] if c1 else None)
    return out


def pf_phases(by, k0):
    """cycles of the playfield stores on every band's first two lines"""
    bad = []
    lim = {T.PF0: (29, 70), T.PF1: (39, 59), T.COLUPF: (49, 60)}
    for b in range(4):
        for t, r, v in by.get(k0 + 36 * b, []):
            if r in lim and not lim[r][0] <= t <= lim[r][1]:
                bad.append((b, r, t))
        pf2 = [t for t, r, v in by.get(k0 + 36 * b + 1, []) if r == T.PF2]
        if not pf2 or not pf2[0] <= 38:
            bad.append((b, "PF2", pf2))
    return bad


def expect(top, h, frame, n_lines=144):
    return {n: (frame, n - top) for n in range(n_lines) if 0 <= n - top < h}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep")
    ap.add_argument("--step", type=int, default=1)
    a = ap.parse_args()
    out = Path(a.keep) if a.keep else Path(tempfile.mkdtemp())
    overscan = 77
    rom, sym = build(out, overscan)
    con = make(rom, sym)
    con.tia_frame()                          # the reset code clears the zero page: poke after it
    for n, v in (("PF0B", 0xF0), ("PF1B", 0xAA), ("PF2B", 0x55), ("CPFB", 0x4A)):
        for k in range(4):
            con.ram[(sym[n] + k) & 0x7F] = [0xF0, 0x0F, 0xFF, 0x00][k] if n == "PF0B" else \
                [0xAA, 0xFF, 0x00, 0x33][k] if n == "PF1B" else \
                [0x55, 0x00, 0xFF, 0x0F][k] if n == "PF2B" else [0x44, 0x66, 0x88, 0xAA][k]
    poke(con, "P0X", 40)
    poke(con, "P1X", 90)
    poke(con, "LaserState", 0)
    poke(con, "WaterCol", 0x96)
    poke(con, "WaterOff", 0)
    poke(con, "TideOff", 0)
    poke(con, "DoorAnd", 0xFF)
    poke(con, "DoorOr", 0)
    for k in range(4):
        con.ram[(sym["BandTab"] + k) & 0x7F] = 0
    for _ in range(3):
        con.tia_frame()
    import cave_kernel_gen as G0_
    for n, v in (("P0Top", 30), ("P1Top", 60), ("P0GHi", 0xFA), ("P0CHi", 0xFB), ("P1GHi", 0xFC),
                 ("P1CHi", 0xFE), ("P0Kb", G0_.PAD + G0_.H0), ("P1Kb", G0_.PAD + G0_.H1)):
        poke(con, n, v)
    con.tia_frame()
    # frame length
    log = con.tia_frame()
    by, first, last, k0 = frame_info(con, log)
    print(f"frame lines {last - first + 1} (want 262), kernel line 0 at {k0 - first}")
    ws = {}
    for ln in range(k0, k0 + 144):
        c = [t for t, r, v in by.get(ln, []) if r == T.WSYNC]
        ws[ln - k0] = c[0] if c else None
    vals = [v for v in ws.values() if v is not None]
    print("WSYNC write cycle on kernel lines: min", min(vals), "max", max(vals),
          "lines without WSYNC:", [n for n, v in ws.items() if v is None][:5])
    bad = []
    tops = list(range(-25, 151, a.step))
    combos = [("A", "D0"), ("B", "D1"), ("A", "D2")]
    import cave_kernel_gen as G
    P0 = {"A": (0xFA, 0xFB, G.PAD + G.H0 + G.BASE_P0["A"]),
          "B": (0xFA, 0xFB, G.PAD + G.H0 + G.BASE_P0["B"])}
    P1 = {"D0": (0xFC, 0xFE, G.PAD + G.H1 + G.BASE_P1["D0"]),
          "D1": (0xFC, 0xFE, G.PAD + G.H1 + G.BASE_P1["D1"]),
          "D2": (0xFD, 0xFF, G.PAD + G.H1 + G.BASE_P1["D2"])}
    for i, t0 in enumerate(tops):
        for f0, f1 in combos:
            t1 = ((t0 * 3 + 7) % 170) - 20
            tide = (i + t0) % 4
            poke(con, "TideOff", tide)
            poke(con, "P0Top", t0)
            poke(con, "P1Top", t1)
            poke(con, "P0GHi", P0[f0][0])
            poke(con, "P0CHi", P0[f0][1])
            poke(con, "P0Kb", P0[f0][2])
            poke(con, "P1GHi", P1[f1][0])
            poke(con, "P1CHi", P1[f1][1])
            poke(con, "P1Kb", P1[f1][2])
            con.tia_frame()
            log = con.tia_frame()
            by, first, last, k0 = frame_info(con, log)
            s0, s1 = shown(con, by, first, last, k0)
            col = colours(by, k0)
            for n, (c0, c1) in col.items():
                r0 = n - t0
                want0 = 0x40 + 2 * r0 if 0 <= r0 < H0 else None
                if want0 is not None and c0 != want0:
                    bad.append(("COLUP0", t0, f0, (n, c0, want0)))
            for n in range(143):                 # line 143 feeds the HUD, not a cave row
                # COLUP1 written on line n belongs to the row shown on line n+1 (like GRP1);
                # BandCol (latched on the last line of a band) otherwise
                nxt = s1.get(n + 1)
                band = min(3, (n + 1) // 36) if n % 36 == 35 else n // 36
                bc = [0x44, 0x66, 0x88, 0xAA][band] if DOOR is None else DOOR
                want = (0x20 + 2 * nxt[1]) if nxt is not None else bc
                if col[n][1] != want:
                    bad.append(("COLUP1", t1, f1, (n, col[n][1], want)))
            wl = [(n, v) for n in range(144) for t_, r, v in by.get(k0 + n, []) if r == 9]
            if wl != [(132 + tide, 0x96)]:
                bad.append(("water", tide, f0, wl[:3]))
            if last - first + 1 != 262:
                bad.append(("frame length", tide, f0, last - first + 1))
            ph = pf_phases(by, k0)
            if ph:
                bad.append(("PF phase", t0, f0, ph[:3]))
            e0 = expect(t0, H0, 1 if f0 == "B" else 0)
            e1 = expect(t1, H1, 1 if f1 == "D1" else 0)
            for name, s, e in (("P0", s0, e0), ("P1", s1, e1)):
                s = {n: v for n, v in s.items() if 0 <= n < 144}
                if s != e:
                    diff = sorted(set(s.items()) ^ set(e.items()))
                    bad.append((name, t0 if name == "P0" else t1, f0 + f1, diff[:6]))
    print(f"{len(tops) * 3} frames, sprite pictures that differ from the art: {len(bad)}")
    for b in bad[:12]:
        print(" ", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
