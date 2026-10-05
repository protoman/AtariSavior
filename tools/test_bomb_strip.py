#!/usr/bin/env python3
"""Bomb-vs-strip blast (user 2026-10-04: 'blasting the strip must work').

Two halves of the fix, driven against the real routines:

1. bank1 BombMarkWalls: with LineCount packed (strip at right_col 2 ->
   pL=24), a bomb whose ±2-col blast covers the strip sets
   EnemyDeadMask b3 and returns count+1 (+75 via the caller). Frames:
   BMW computes blast cols in LEFT-half space (bomb col mirrored), the
   strip pL is RIGHT-half space — StripBlastCheck mirrors the window
   in-body (39-x). Controls: sym run, non-overlapping bomb, no double
   count on a second blast.

2. bank2 StageBandTab: with b3 set, BandTab stages 0/0/0 (cave renders
   no strip; pack emits mask 0 → PHM/LWC/moth overlays transparent);
   without b3 the model's bands stage unchanged ($ff/$ff/$00).

Both deaths are room-scoped: EnterRoom zeroes EnemyDeadMask.

Run: /home/iuri/python3/bin/python3 tools/test_bomb_strip.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

from test_cell_map import Mem as Mem02, RTS_SENTINEL, parse_labels  # noqa: E402

BANKS = [bytearray(open(SRC / f"bank{i}.bin", "rb").read()) for i in range(4)]


class Mem1:
    """Bank-aware RAM for the bank1 BMW drive (hotspots $1FF6-$1FF9)."""

    def __init__(self):
        self.ram = bytearray(128)
        self.bank = 1

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0284:
            return 0
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return 0
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


def parse_equ(path: Path, names: set) -> dict:
    """bank2.lst EQU lines: `addr  bytes  Name = $vv` (no U prefix)."""
    out = {}
    rx = re.compile(r"^\s*\d+\s+U?[0-9a-f]{4}\s+(?:[0-9a-f]{2}\s+)+"
                    r"([A-Za-z_][A-Za-z0-9_]*)\s+=\s+\$([0-9a-fA-F]+)")
    for line in path.read_text(errors="replace").splitlines():
        m = rx.match(line)
        if m and m.group(1) in names and m.group(1) not in out:
            out[m.group(1)] = int(m.group(2), 16)
    return out


L1 = parse_labels(SRC / "bank1.lst", {"BombMarkWalls"})
L0 = parse_labels(SRC / "bank0.lst", {"BombX", "LineCount", "RcBase",
                                "EnemyDeadMask", "CollisionX"})
L2 = parse_labels(SRC / "bank2.lst", {"StageBandTab", "M0TilePF0"})
L2.update(parse_equ(SRC / "bank2.lst",
                    {"BandTab", "CollisionEndY", "RoomPF0Lo"}))
need = ({"BombMarkWalls"} - L1.keys()) | \
       ({"BombX", "LineCount", "RcBase", "EnemyDeadMask", "CollisionX"}
        - L0.keys()) | \
       ({"StageBandTab", "M0TilePF0", "BandTab", "CollisionEndY",
         "RoomPF0Lo"} - L2.keys())
if need:
    sys.exit(f"labels missing: {sorted(need)}")


def run_bmw(mem: Mem1, bomb_x: int, line_count: int) -> int:
    """Drive BombMarkWalls; return the count A (walls newly broken)."""
    r = mem.ram
    r[L0["BombX"] - 0x80] = bomb_x
    r[L0["LineCount"] - 0x80] = line_count
    r[L0["RcBase"] - 0x80] = 0           # no rects: strip check only
    r[L0["EnemyDeadMask"] - 0x80] = 0
    mem.bank = 1
    mpu = MPU(memory=mem)
    mpu.pc = L1["BombMarkWalls"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return mpu.a
    sys.exit(f"BMW(bombX={bomb_x}) never returned "
             f"(pc=${mpu.pc:04X}, bank={mem.bank})")


def stage(deadmask: int) -> tuple[int, int, int]:
    """Drive StageBandTab; return (BandTab0..2, packed_mask)."""
    mem = Mem02()
    r = mem.ram
    r[L2["RoomPF0Lo"] - 0x80] = L2["M0TilePF0"] & 0xFF
    r[(L2["RoomPF0Lo"] + 1) - 0x80] = L2["M0TilePF0"] >> 8
    r[L0["EnemyDeadMask"] - 0x80] = deadmask
    mem.bank = 2
    mpu = MPU(memory=mem)
    mpu.pc = L2["StageBandTab"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            bands = (r[L2["BandTab"] - 0x80], r[L2["BandTab"] + 1 - 0x80],
                     r[L2["BandTab"] + 2 - 0x80])
            packed = r[L2["CollisionEndY"] - 0x80]
            return bands, packed & 7
    sys.exit("StageBandTab never returned")


def main() -> int:
    # packed: right_col 2 -> n=3 -> pL=24; all bands active (mask 7)
    packed = (2 + 1) << 4 | 0x07

    # 1. bomb at display col 25 (BombX=107 -> vl=100 -> col25 -> mirrored
    #    left-col 14 -> blast [12,16] covers the strip's mirror {14,15})
    mem = Mem1()
    got = run_bmw(mem, 107, packed)
    mask = mem.ram[L0["EnemyDeadMask"] - 0x80]
    assert got == 1 and mask & 0x08, (
        f"strip blast must break (count={got}, deadmask=${mask:02X})")

    # 2. no double count: bit already set
    def rerun_preserve(bomb_x, line_count, deadmask_pre):
        r = mem.ram
        r[L0["EnemyDeadMask"] - 0x80] = deadmask_pre
        r[L0["BombX"] - 0x80] = bomb_x
        r[L0["LineCount"] - 0x80] = line_count
        r[L0["RcBase"] - 0x80] = 0
        mem.bank = 1
        mpu = MPU(memory=mem)
        mpu.pc = L1["BombMarkWalls"]
        mpu.a = mpu.x = mpu.y = 0
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(5000):
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                return mpu.a
        sys.exit("BMW rerun never returned")

    got2 = rerun_preserve(107, packed, 0x08)
    assert got2 == 0, f"second blast must not count (got {got2})"

    # 3. symmetric room: no strip, no count
    mems = Mem1()
    got3 = run_bmw(mems, 107, 0)
    assert got3 == 0 and not mems.ram[L0["EnemyDeadMask"] - 0x80], (
        f"sym run must not break the strip (count={got3})")

    # 4. bomb far from the strip (col 10 -> blast [8,12]; strip mirror
    #    {14,15} untouched)
    memf = Mem1()
    got4 = run_bmw(memf, 40, packed)
    assert got4 == 0 and not memf.ram[L0["EnemyDeadMask"] - 0x80], (
        f"far bomb must not break the strip (count={got4})")

    # 5. staging: b3 set -> bands blanked + packed mask 0 (overlays off)
    bands, mask_bits = stage(0x08)
    assert bands == (0, 0, 0) and mask_bits == 0, (
        f"dead strip must stage blank (bands={bands}, mask={mask_bits})")

    # 6. staging: alive -> model 0's bands + mask (bands 0/1 painted -> 3)
    bands, mask_bits = stage(0x00)
    assert bands == (0xFF, 0xFF, 0x00) and mask_bits == 0x03, (
        f"live strip must stage normally (bands={bands}, mask={mask_bits})")

    print("test_bomb_strip: OK (blast hit/controls, no double count, "
          "staging alive+dead)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
