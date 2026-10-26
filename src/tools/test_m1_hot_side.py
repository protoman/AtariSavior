#!/usr/bin/env python3
"""M1 hot-band kill must be one-SIDED, like the strip it comes from.

User report 2026-10-24 (screenshot stuck_003_die_open.png): "when I move to the
right here, most of the times, I just die — probably he is hitting some
hot-wall even if there is none in that part".

Root cause: the playfield is REFLECTED, so the cell walk works in MIRROR space
(display col 39 - c). The M1 strip, however, is an OBJECT drawn on ONE side
only. `HotOverlapBody`'s M1 cell test compared the mirror-space box against the
strip's cell, so a player at display 37-38 matched a strip drawn at display 2-3
(~80 px away) and died on it. The fix gates the kill on the PHYSICAL half
(`RoomX` vs 80) matching MetaA b0 (the strip's side).

Cases: real touch on the left half kills / its mirror does NOT kill / the same
pair on the right half. Frozen banks + labels only (src/tests/frozen/).

Run: /home/iuri/python3/bin/python3 tools/test_m1_hot_side.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

import os
# M1_HOT_FROZEN lets the red-proof run point at a patched copy of the banks
# (the gate bytes NOPed) and watch the two ghost cases FAIL, i.e. the test
# really does pin the fix instead of agreeing with itself.
FROZEN = Path(os.environ.get("M1_HOT_FROZEN")
              or (ROOT / "tests" / "frozen"))

NEED = {"HotOverlapBody", "PF0Buf", "RoomMetaA", "RoomMetaB", "RoomM1Hot",
        "EnemyDeadMask", "RoomX", "Temp", "CollisionCellY", "CollisionEndY",
        "CollisionCellX", "CollisionEndX", "RoomRectsLo", "RoomRectsHi"}
L3 = parse_labels(FROZEN / "bank3.lst", NEED)
missing = NEED - L3.keys()
if missing:
    sys.exit(f"frozen bank3 labels missing: {sorted(missing)}")
Z = {k: v & 0x7F for k, v in L3.items() if 0x80 <= v <= 0xFF}

HOT_FLAG = 0x80


def hot(meta_a, m1_cell, roomx, min_col, max_col):
    """Run the REAL HotOverlapBody once; True when it flags a hot death."""
    mem = Mem()
    r = mem.ram
    for i in range(12):                 # every PF cell AIR: the row-1 sweep
        r[(Z["PF0Buf"] + i) & 0x7F] = 0  # must not kill on its own
    r[Z["RoomMetaA"]] = meta_a
    r[Z["RoomMetaB"]] = 0x40            # b6 = hot room
    r[Z["RoomM1Hot"]] = m1_cell         # m1_col+1 (the strip's mirror cell)
    r[Z["RoomX"]] = roomx               # PHYSICAL sprite X (px)
    r[Z["Temp"]] = 0
    r[Z["EnemyDeadMask"]] = 0
    r[Z["CollisionCellY"]] = 1          # box touches the hot band (row 1)
    r[Z["CollisionEndY"]] = 1
    r[Z["CollisionEndX"]] = min_col     # mirror-space box columns
    r[Z["CollisionCellX"]] = max_col
    r[Z["RoomRectsLo"]] = 0x00
    r[Z["RoomRectsHi"]] = 0x01          # no feature stream ($0100 holds 0)

    mpu = MPU(memory=mem)
    mpu.pc = L3["HotOverlapBody"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    mem.bank = 3
    for _ in range(900):
        mpu.step()
        if mem.bank == 0 or mpu.pc == RTS_SENTINEL:   # reached ReturnPad
            return bool(r[Z["Temp"]] & HOT_FLAG)
    sys.exit(f"HotOverlapBody never returned (pc=${mpu.pc:04X})")


fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}: hot={got} want {want}")


# MetaA: high nibble = m1_col+1 (col 1 -> cell 2), b0 = strip on the RIGHT half.
META_L = 0x20
META_R = 0x21

# The strip's mirror cell is 2 (display 2-3 left / 36-37 right), so the box
# columns 2..3 are the real contact in BOTH halves — only RoomX says which.
check("left strip, touched on its half (RoomX 15)",  hot(META_L, 2, 15, 2, 3), True)
check("left strip, MIRROR of a right-side player",   hot(META_L, 2, 140, 1, 2), False)
check("right strip, touched on its half (RoomX 150)", hot(META_R, 2, 150, 2, 3), True)
check("right strip, MIRROR of a left-side player",   hot(META_R, 2, 15, 2, 3), False)

if fails:
    print(f"test_m1_hot_side: FAIL ({fails})")
    sys.exit(1)
print("test_m1_hot_side: OK (the hot M1 cell kills only on the strip's own side)")
