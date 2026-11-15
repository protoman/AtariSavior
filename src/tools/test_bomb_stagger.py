#!/usr/bin/env python3
"""The bomb's wall punch is spread over frames (2026-11).

One blast frame in a wall-heavy room (level 20 room 18) measured 285.8 lines: BombMarkWalls scanned
every cell of the +-2 col blast window in the single overscan that also carried the room's normal
work. BombTick now calls BombMarkWalls at BombTimer 60 (the edge: first cell + the strips), 58 and
57 (one cell each); BombTimer 59 stays the enemy/player/sound frame. Any other BombTimer keeps the
old all-cells call (the other bomb tests rely on it).

Checks, driving the real frozen routine: thin walls in window cells 3 and 5 (bomb col 9 -> cells
3..5): timer 60 breaks cell 3 only, 58 (cell 4) nothing, 57 breaks cell 5; the legacy call breaks both;
a slice runs fewer cycles than the whole; past-the-window slices do nothing.

Run: /home/iuri/python3/bin/python3 tools/test_bomb_stagger.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import test_cell_map as CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"
L0 = parse_labels(FROZEN / "bank0.lst", {"BombX", "BombTimer", "LineCount", "EnemyDeadMask", "PF1Buf"})
L1 = parse_labels(FROZEN / "bank3.lst", {"BombMarkWalls"})
for lab, names in ((L0, ("BombX", "BombTimer", "PF1Buf")), (L1, ("BombMarkWalls",))):
    miss = [n for n in names if n not in lab]
    if miss:
        sys.exit(f"frozen labels missing: {miss}")


def bmw(timer, pf1, bomb_x=39):
    """BombX 39 -> screen col 8..9 -> blast cols 7..11 -> cells 3..5. Returns (count, pf1, cycles)."""
    mem = CM.Mem()
    r = mem.ram
    r[L0["BombX"] - 0x80] = bomb_x
    r[L0["BombTimer"] - 0x80] = timer
    r[L0["LineCount"] - 0x80] = 0
    r[L0["EnemyDeadMask"] - 0x80] = 0
    r[0xDB - 0x80] = 0                       # RoomExits: both sides connected
    r[L0["PF1Buf"] - 0x80] = pf1
    mem.bank = 3
    mpu = MPU(memory=mem)
    mpu.pc = L1["BombMarkWalls"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    c0 = mpu.processorCycles
    for _ in range(8000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return mpu.a, r[L0["PF1Buf"] - 0x80], mpu.processorCycles - c0
    sys.exit(f"BombMarkWalls never returned (timer {timer}, pc=${mpu.pc:04X})")


WALLS = 0x30 | 0x03              # PF1 row 0: cell 3 (cols 6-7) and cell 5 (cols 10-11); cell 4 empty

n, pf, c_all = bmw(0, WALLS)
assert n == 2 and pf == 0, f"legacy call must break both walls (count {n}, PF1 ${pf:02X})"

n60, pf60, c60 = bmw(60, WALLS)
assert n60 == 1 and pf60 == 0x03, f"timer 60 = cell 3 only (count {n60}, PF1 ${pf60:02X})"
n58, pf58, c58 = bmw(58, pf60)
assert n58 == 0 and pf58 == 0x03, f"timer 58 = cell 4 (empty): count {n58}, PF1 ${pf58:02X}"
n57, pf57, c57 = bmw(57, pf58)
assert n57 == 1 and pf57 == 0, f"timer 57 = cell 5: count {n57}, PF1 ${pf57:02X}"
for c, tag in ((c60, "60"), (c58, "58"), (c57, "57")):
    assert c < c_all, f"slice {tag} ({c}c) is not cheaper than the whole blast ({c_all}c)"

# a bomb whose window only spans two cells (col 2 -> cols 0..4 -> cells 1..2): slice 57 is past it
n, pf, c = bmw(57, WALLS, bomb_x=11)
assert n == 0 and pf == WALLS, f"slice past the window must do nothing (count {n}, PF1 ${pf:02X})"

print(f"test_bomb_stagger: OK (legacy {c_all}c = 2 walls; slices 60/58/57 = {c60}/{c58}/{c57}c, "
      "walls 1/0/1, past-window slice inert)")
