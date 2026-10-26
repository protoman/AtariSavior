#!/usr/bin/env python3
"""A bomb must not open a side wall that has no room behind it (user 2026-10-26).

"When a thin wall (sync or async) is placed on the left or right side of the screen
that has NO exit to that side, the bomb blast should NOT work on that wall. We
should have no openings when there is no connected rooms."

Per-room flags (bank2 SetRoomExits, run by EnterRoomB2): RoomExits ($DB) b1 = NO room
to the WEST, b0 = NO room to the EAST (0 = both sides connected, so every older test
that never stages it is unchanged). The rules, in bank1:
  * symmetric (PF) thin wall in the cell next to the screen border (k = 1: the wall
    in front of the edge column) - the PF is MIRRORED, so breaking it opens BOTH
    sides: it needs both neighbours (any missing side keeps it intact);
  * the dead-side PLUG strips (the generator paints the edge cell on a side with no
    room: left M1 strip at dcol 0, right ball strip at right_col 9) are
    unbreakable; an INTERIOR strip is a designed block (the start room's bomb
    lesson has no side neighbour at all) and stays bombable;
  * every other thin wall (k >= 2) and the border cell behave as before.

Drives the real frozen routines. Run: /home/iuri/python3/bin/python3 tools/test_bomb_side_walls.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import test_cell_map as CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"
L0 = parse_labels(FROZEN / "bank0.lst", {"BombX", "LineCount", "EnemyDeadMask",
                                         "CollisionX", "BombPacked", "PF0Buf",
                                         "PF1Buf", "PF2Buf"})
L1 = parse_labels(FROZEN / "bank1.lst", {"BombMarkWalls"})
for lab, names in ((L0, ("BombX", "LineCount", "EnemyDeadMask", "PF0Buf",
                         "PF1Buf", "PF2Buf")), (L1, ("BombMarkWalls",))):
    miss = [n for n in names if n not in lab]
    if miss:
        sys.exit(f"frozen labels missing: {miss}")
ROOMEXITS = 0xDB - 0x80
ROOMPF0 = 0x99 - 0x80                    # RoomMetaA / RoomMetaB ($99/$9A)


def bmw(bomb_x, exits, *, pf=None, meta=(0, 0), line_count=0):
    """Run BombMarkWalls with RoomExits = exits; returns (count, ram)."""
    mem = CM.Mem()
    r = mem.ram
    r[ROOMEXITS] = exits
    r[ROOMPF0], r[ROOMPF0 + 1] = meta
    r[L0["BombX"] - 0x80] = bomb_x
    r[L0["LineCount"] - 0x80] = line_count
    r[L0["EnemyDeadMask"] - 0x80] = 0
    for addr, val in (pf or {}).items():
        r[addr - 0x80] = val
    mem.bank = 1
    mpu = MPU(memory=mem)
    mpu.pc = L1["BombMarkWalls"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(8000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return mpu.a, r
    sys.exit(f"BombMarkWalls never returned (pc=${mpu.pc:04X})")


PF0 = L0["PF0Buf"]
PF1 = L0["PF1Buf"]

# --- 1. sync thin wall next to the border: cell 1 = display cols 2-3 -------------
# PF0Buf row 0 bits for cols 2,3 = $40|$80; its neighbours (cols 0-1, 4-5) are empty.
EDGE_WALL = {PF0: 0xC0}
for exits in (0, 1, 2, 3):
    n, r = bmw(19, exits, pf=EDGE_WALL)          # BombX 19 -> screen col 3
    broken = n == 1 and r[PF0 - 0x80] == 0
    if exits == 0:
        assert broken, f"both rooms present: the edge wall must break (count={n})"
    else:
        assert n == 0 and r[PF0 - 0x80] == 0xC0, (
            f"RoomExits=${exits:02X} (a side has no room): the edge wall must stay "
            f"intact, count={n} PF0=${r[PF0 - 0x80]:02X}")

# a thin wall away from the border (cell 3 = cols 6-7, PF1Buf row 0 bits $20|$10)
INNER_WALL = {PF1: 0x30}
n, r = bmw(35, 3, pf=INNER_WALL)                 # BombX 35 -> screen col 7
assert n == 1 and r[PF1 - 0x80] == 0, (
    f"an inner thin wall must still break whatever RoomExits says (count={n})")

# --- 2. the right (ball) strip: the EDGE plug (right_col 9) needs the EAST room ---
EDGE_PACKED = (9 + 1) << 4 | 0x07                 # strip at right_col 9 (pL 38)
for exits, want in ((0, 1), (2, 1), (1, 0), (3, 0)):
    n, r = bmw(159, exits, line_count=EDGE_PACKED)    # BombX 159 -> screen col 38
    got = bool(r[L0["EnemyDeadMask"] - 0x80] & 0x08)
    assert got == bool(want) and n == want, (
        f"edge ball strip, RoomExits=${exits:02X}: broken={got} count={n}, want "
        f"{bool(want)} (east room {'absent' if exits & 1 else 'present'})")
# an INTERIOR ball strip (right_col 2) is a designed block: bombable whatever the flags
PACKED = (2 + 1) << 4 | 0x07
for exits in (0, 1, 3):
    n, r = bmw(107, exits, line_count=PACKED)
    assert n == 1 and r[L0["EnemyDeadMask"] - 0x80] & 0x08, (
        f"interior ball strip must stay bombable (RoomExits=${exits:02X}, count={n})")

# --- 3. the left (M1) strip: the EDGE plug (dcol 0) needs the WEST room -----------
for exits, want in ((0, 1), (1, 1), (2, 0), (3, 0)):
    n, r = bmw(11, exits, meta=(0x10, 0))         # m1_col+1 = 1 -> strip at dcol 0
    got = bool(r[L0["EnemyDeadMask"] - 0x80] & 0x10)
    assert got == bool(want) and n == want, (
        f"edge M1 strip, RoomExits=${exits:02X}: broken={got} count={n}, want "
        f"{bool(want)} (west room {'absent' if exits & 2 else 'present'})")
for exits in (0, 2, 3):                           # interior M1 strip (dcol 16)
    n, r = bmw(71, exits, meta=(0x90, 0))
    assert n == 1 and r[L0["EnemyDeadMask"] - 0x80] & 0x10, (
        f"interior M1 strip must stay bombable (RoomExits=${exits:02X}, count={n})")

# --- 4. SetRoomExits (bank2): the flags come from the room grid -------------------
L2 = parse_labels(FROZEN / "bank2.lst", {"SetRoomExits"})
assert "SetRoomExits" in L2, "frozen bank2.lst lacks SetRoomExits"
bank2 = bytearray(CM.BANK2)
BASE = 0xFFC0 - 0xF000                           # fabricated level block base
N = 4
positions = [0x00, 0x10, 0x20, 0x01]             # (x,y) nibbles: (0,0)(1,0)(2,0)(0,1)
bank2[BASE + N:BASE + N + N] = bytes(positions)
CM.BANK2 = bytes(bank2)
for room, want in ((0, 0b10), (1, 0b00), (2, 0b01), (3, 0b11)):
    mem = CM.Mem()
    r = mem.ram
    r[0x9F - 0x80] = (0xF000 + BASE) & 0xFF      # LevelPFDataLo/Hi
    r[0xA0 - 0x80] = (0xF000 + BASE) >> 8
    r[0xA1 - 0x80] = N                           # LevelRoomN
    r[0x98 - 0x80] = room                        # RoomNo
    r[ROOMEXITS] = 0xFF
    mem.bank = 2
    mpu = MPU(memory=mem)
    mpu.pc = L2["SetRoomExits"]
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(3000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            break
    else:
        sys.exit("SetRoomExits never returned")
    assert r[ROOMEXITS] & 3 == want, (
        f"room {room} (pos ${positions[room]:02X}): RoomExits=${r[ROOMEXITS]:02X}, "
        f"want b1=no west b0=no east = {want:02b}")

print("test_bomb_side_walls: OK (edge wall needs both rooms, strips need their own side)")
