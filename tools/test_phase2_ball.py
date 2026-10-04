#!/usr/bin/env python3
"""Phase 2 CHECK 2 probe (py65): cave-frame invariants + symmetric
bit-identity against the Phase 1 baseline ROM.

Assertions (gameplay frames >= 2 where the cave kernel runs):
  * last CTRLPF ($0A) write before cave entry (.Row) == $35 on the new
    ROM, == $05 on the baseline ROM, constant across frames;
  * last ENABL ($1F) write at .Row == 0; no bank0 ENABL write != 0
    anywhere (bank1 HUD bar writes are excluded via the log's bank tag);
  * zero bank0 RESBL ($14) / HMBL ($24) writes — symmetric models must
    never position the ball (bank1 HUD bar ball writes are expected and
    excluded);
  * bit-identical: the new ROM's TIA write sequence (frame >= 2) equals
    the baseline ROM's with every CTRLPF ($0A) write dropped. CTRLPF is
    the only intended Phase 2 delta; with the ball disabled $35 vs $05
    is invisible.

Baseline: P2_BASELINE env var, default /tmp/opencode/savior_phase1.bin.
If missing, the bit-identical leg is skipped (invariants still run).

Run: /home/iuri/python3/bin/python3 tools/test_phase2_ball.py
"""
import os
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

LABELS = {}
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$", _l)
    if _m:
        LABELS.setdefault(_m.group(2), int(_m.group(1), 16))
for _need in ("StartFrame", ".Row", "Overscan"):
    if _need not in LABELS:
        sys.exit(f"label {_need} not found in bank0.lst")
PC_START = LABELS["StartFrame"]
PC_ROW = LABELS[".Row"]
PC_OVER = LABELS["Overscan"]

FRAMES = 60
CTRLPF, ENABL, RESBL, HMBL = 0x0A, 0x1F, 0x14, 0x24


class Mem:
    def __init__(self, banks):
        self.banks = banks
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF              # neutral stick
        self.swchb = 0xFF
        self.inpt4 = 0xFF              # fire released
        self.wsync_seen = False
        self.wall = 0
        self.deadline = {}
        self.log = []                  # (frame, bank, addr, val)
        self.frame = -1
        self.last = {}                 # addr -> last written value

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.banks[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            dl = self.deadline.get(0x296, 0)
            if self.wall >= dl:
                return 0
            return min(0xFF, max(1, (dl - self.wall + 63) // 64))
        if a == 0x000C:
            return self.inpt4
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF6 <= a <= 0x1FF9:
            self.bank = a - 0x1FF6
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            mult = {0x294: 1024, 0x296: 64, 0x297: 8}[a]
            self.deadline[a] = self.wall + v * mult
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            if (a & 0x3F) == 2:
                self.wsync_seen = True
            self.tia[a & 0x3F] = v
            self.log.append((self.frame, self.bank, a & 0x3F, v))
            self.last[a & 0x3F] = v


def run(rom: Path) -> dict:
    import py65.devices.mpu6502 as m
    blob = rom.read_bytes()
    assert len(blob) == 16384, f"{rom} is {len(blob)} bytes, want 16K"
    banks = [blob[4096 * i:4096 * (i + 1)] for i in range(4)]
    mem = Mem(banks)
    mpu = m.MPU(memory=mem)
    prev = 0

    def step():
        nonlocal prev
        mpu.step()
        c = mpu.processorCycles - prev
        prev = mpu.processorCycles
        mem.wall += c
        if mem.wsync_seen:
            w = mem.wall
            mem.wall = (w // 76 + 1) * 76 if w % 76 else w
            mem.wsync_seen = False

    frame = -1
    ctrlpf_at_row = []
    enabl_at_row = []
    cave_rows = 0
    steps = 0
    while frame < FRAMES:
        step()
        steps += 1
        if steps > 6_000_000:
            sys.exit(f"{rom.name}: runaway (frame {frame})")
        pc, bk = mpu.pc, mem.bank
        if bk == 0 and pc == PC_START:
            frame += 1
            mem.frame = frame
            # console RESET pulse: title -> game start (same as sim)
            mem.swchb = 0xFE if frame in (1, 2) else 0xFF
        if bk == 0 and pc == PC_ROW and frame >= 0:
            cave_rows += 1
            ctrlpf_at_row.append((frame, mem.last.get(CTRLPF)))
            enabl_at_row.append((frame, mem.last.get(ENABL)))
    return dict(
        ctrlpf=[v for f, v in ctrlpf_at_row if f >= 2],
        enabl_at_row=[v for f, v in enabl_at_row if f >= 2],
        cave_rows=cave_rows,
        log=mem.log,
    )


def check(r: dict, want_ctrlpf: int) -> list[str]:
    fails = []
    rows = r["ctrlpf"]
    if not rows:
        fails.append("cave kernel (.Row) never reached")
        return fails
    bad = sorted({v for v in rows if v != want_ctrlpf})
    if bad:
        fails.append(f"CTRLPF at cave entry = "
                     + ", ".join(f"${v:02X}" for v in bad)
                     + f", want ${want_ctrlpf:02X}")
    if len(set(rows)) != 1:
        fails.append(f"CTRLPF not constant: {sorted(set(rows))}")
    ea = [v for v in r["enabl_at_row"] if v != 0]
    if ea:
        fails.append(f"ENABL at cave entry != 0: {sorted(set(ea))}")
    bank0 = [(f, a, v) for f, b, a, v in r["log"] if f >= 2 and b == 0]
    for f, a, v in bank0:
        if a == ENABL and v != 0:
            fails.append(f"bank0 ENABL write ${v:02X} at frame {f} (want only 0)")
            break
    ball = [(f, a, v) for f, a, v in bank0 if a in (RESBL, HMBL)]
    if ball:
        fails.append(f"bank0 ball-reg writes in symmetric run: {ball[:6]} "
                     f"(count {len(ball)})")
    return fails


def main() -> int:
    new = SRC / "savior.bin"
    r = run(new)
    fails = check(r, 0x35)

    base_path = Path(os.environ.get(
        "P2_BASELINE", "/tmp/opencode/savior_phase1.bin"))
    trace = [(a, v) for f, b, a, v in r["log"] if f >= 2]
    stripped = [(a, v) for a, v in trace if a != CTRLPF]
    if base_path.exists():
        b = run(base_path)
        fails += check(b, 0x05)
        b_stripped = [(a, v) for f, bb, a, v in b["log"]
                      if f >= 2 and a != CTRLPF]
        if stripped != b_stripped:
            n = min(len(stripped), len(b_stripped))
            i = next((k for k in range(n) if stripped[k] != b_stripped[k]), n)
            fails.append(
                f"TIA write trace differs from baseline at index {i} "
                f"(new {stripped[i] if i < len(stripped) else '-'} vs base "
                f"{b_stripped[i] if i < len(b_stripped) else '-'}; "
                f"len {len(stripped)} vs {len(b_stripped)})")
        else:
            print(f"bit-identical vs baseline: {len(stripped)} TIA writes "
                  f"(CTRLPF dropped) match over {FRAMES} frames")
    else:
        print(f"NOTE: baseline {base_path} missing — bit-identical leg skipped")

    if fails:
        for f in fails:
            print(f"FAIL: {f}")
        return 1
    print(f"test_phase2_ball: OK (CTRLPF $35 x{len(r['ctrlpf'])} cave "
          f"entries, ENABL 0, no bank0 ball writes, {FRAMES} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
