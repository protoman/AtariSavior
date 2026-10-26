#!/usr/bin/env python3
"""M1 door overlay guard: a locked door must BLOCK, whichever half it is on.

Calls the REAL `OvM1Block` (bank0) in py65 with a hand-staged room: the strip's
PF cell open (the wall-hide envelope guarantees open == patched), a cold room
(MetaB b6 = 0) so the block path is the simple `sec` in `DoorLocked`.

Why it exists (bug 2026-10-23, user report + Stella trace): the right-half cell
mirror was `eor #%00011111` = 31 - l, not 39 - l (the project's reflect mapping,
see test_cell_map.visible_range). For the live level-4 room 3 door (MetaA $39 =
right half, col 2, M1X 103) the code looked up cell 6 instead of cell 14, read
a WALL, and returned clc — the player walked through the door. The trace proved
it: 268 overlaps, every one of them exited through `.OvM1no`, and the register
dump at `$FAA6` had X = 6 (want 14).

Cases: right door blocks (RED before the fix) / left door still blocks /
a solid cell is still passable / key held unlocks on touch / a destroyed strip
is transparent.

Frozen banks + labels (src/tests/frozen/) only — never the live build.
Run: /home/iuri/python3/bin/python3 tools/test_m1_door.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels, BANK0  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"
C_FLAG = 0x01

NEED = {"OvM1Block", "PF0Buf", "RoomPF0Lo", "RoomPF0Hi",
        "EnemyDeadMask", "LevelStartRoom", "CollisionX", "CollisionCellY",
        "CollisionEndY", "RectCount"}
L0 = parse_labels(FROZEN / "bank0.lst", NEED)
missing = NEED - L0.keys()
if missing:
    sys.exit(f"frozen labels missing: {sorted(missing)}")

# kernel.asm ColOff/ColMask (20 PF cells: 4 PF0, 8 PF1, 8 PF2). The lst has no
# symbol line for data labels, so locate the 40-byte pair by its signature and
# assert it — the walk's own tables, not a hand-typed copy.
_SIG = bytes([0, 0, 0, 0] + [4] * 8 + [8] * 8
             + [0x10, 0x20, 0x40, 0x80, 0x80, 0x40, 0x20, 0x10,
                0x08, 0x04, 0x02, 0x01, 0x01, 0x02, 0x04, 0x08,
                0x10, 0x20, 0x40, 0x80])
_at = BANK0.find(_SIG)
assert _at >= 0, "ColOff/ColMask pair not found in the frozen bank0"
COLOFF = list(BANK0[_at:_at + 20])
COLMASK = list(BANK0[_at + 20:_at + 40])
Z = {k: v & 0x7F for k, v in L0.items() if 0x80 <= v <= 0xFF}


def wall(pf, cell, row):
    pf[row + COLOFF[cell]] |= COLMASK[cell]


def call_ovm1(meta_a, open_cells, meta_b=0x00, dead=0x00, key=False,
              vl=100, cell_y=1, end_y=1):
    """Run OvM1Block once; return (carry_set, EnemyDeadMask after)."""
    mem = Mem()
    r = mem.ram
    pf = bytearray(12)                     # PF0Buf rows 0-3 (N=4 stride 4)
    for row in (0, 1, 2, 3):               # the envelope: walls everywhere,
        for cell in range(20):             # then the patch punches one open
            wall(pf, cell, row)
    for cell, row in open_cells:
        pf[row + COLOFF[cell]] &= ~COLMASK[cell] & 0xFF
    base = L0["PF0Buf"] & 0x7F
    for i, v in enumerate(pf):
        r[(base + i) & 0x7F] = v
    r[Z["RoomPF0Lo"]] = meta_a
    r[Z["RoomPF0Hi"]] = meta_b
    r[Z["EnemyDeadMask"]] = dead
    r[Z["LevelStartRoom"]] = 0x80 if key else 0x00
    r[Z["CollisionX"]] = vl
    r[Z["CollisionCellY"]] = cell_y
    r[Z["CollisionEndY"]] = end_y
    r[Z["RectCount"]] = 0

    mpu = MPU(memory=mem)
    mpu.pc = L0["OvM1Block"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(400):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return bool(mpu.p & C_FLAG), r[Z["EnemyDeadMask"]]
    sys.exit(f"OvM1Block never returned (pc=${mpu.pc:04X}, bank={mem.bank})")


# Live room values: MetaA $39 = right-half strip, m1_col+1 = 3 (col 2),
# M1X = 8*3 + $4F = 103 -> display cell 25 -> mirrored PF cell 39 - 25 = 14.
META_R = 0x39
META_L = 0x30                              # same column, LEFT half -> M1X 23

# 1. THE BUG: right door, its mirrored cell (14) open -> must block.
blocked, _ = call_ovm1(META_R, [(14, 1)], vl=100)
assert blocked, ("right-side locked door did NOT block: the overlay read the "
                 "wrong PF cell (mirror must be 39 - cell)")

# 1b. THE SECOND BUG (2026-10-23, user report: "I can enter inside it, but I
#     can't pass its right side"): the door is an 8 px block [M1X-7, M1X] and
#     the player box is 7 lit px, so the block must fire as soon as the boxes
#     TOUCH — at vl = M1X-13 (box right edge on the strip's left edge). The
#     narrow test (vl in [M1X-6, M1X]) let him walk 7 px in and stopped him on
#     the far side, i.e. the block plane looked one tile right of the art.
blocked, _ = call_ovm1(META_R, [(14, 1)], vl=103 - 13)
assert blocked, ("right-side door let the player touch it: vl = M1X-13 (box "
                 "edge on the strip's left edge) must block, not M1X-6")
blocked, _ = call_ovm1(META_R, [(14, 1)], vl=103 - 14)
assert not blocked, ("the door blocked one px too early: vl = M1X-14 has no "
                     "contact with the strip")

# 2. Left door at the same column still blocks (no mirror involved).
blocked, _ = call_ovm1(META_L, [(5, 1)], vl=20)
assert blocked, "left-side locked door stopped blocking"

# 3. A solid patch cell is a plain wall: passable (PHM already blocked it).
blocked, _ = call_ovm1(META_R, [(6, 1)], vl=100)
assert not blocked, "the overlay blocked on a solid cell (false positive)"

# 4. Key held: the touch destroys the strip (b4) and the walk passes.
blocked, dead = call_ovm1(META_R, [(14, 1)], vl=100, key=True)
assert not blocked, "a keyed touch was still blocked"
assert dead & 0x10, f"keyed touch did not destroy the strip (mask ${dead:02X})"

# 5. Already destroyed strip: transparent, no second change.
blocked, dead = call_ovm1(META_R, [(14, 1)], vl=100, dead=0x10)
assert not blocked, "a destroyed strip still blocked"
assert dead == 0x10, f"destroyed strip mask changed to ${dead:02X}"

print("test_m1_door: OK (right door blocks on contact, one px clear passes, "
      "left door blocks, solid passable, key unlocks, destroyed transparent)")
