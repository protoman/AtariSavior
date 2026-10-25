#!/usr/bin/env python3
"""M1 strip at the LEFT screen edge: collision must follow where it is DRAWN.

User report 2026-10-25 (level 7 room 1, first room): walking left into the
async wall at the far left, "half the player (width) can move inside the wall".

Root cause: SetObjectXPos strobes RESM1 inside HBLANK for any argument below
15, where the object cannot sit further left than the clamp; the same effect is
why the PLAYER's visible left edge is RoomX-4 below x=15 instead of RoomX-7
(PHM prologue / PHMOverlay). The col-0 strip (M1X = 7, argument 8) is therefore
DRAWN 3 px right of the [M1X-7, M1X] contract: [3, 10]. OvM1Block still tested
contact against [0, 7], so the player stopped flush at vl = 8 with 3 of his 7
lit pixels inside the drawn wall.

Contract after the fix: for M1X < 14 (argument < 15) the strip occupies
[M1X-4, M1X+3], i.e. contact window vl in [M1X-10, M1X+3]. Strips with
M1X >= 14 keep the old window [M1X-13, M1X].

Calls the real frozen OvM1Block (see test_m1_door.py for the harness).
Run: /home/iuri/python3/bin/python3 tools/test_m1_edge.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels, BANK0  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "src" / "tests" / "frozen"
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



META_COL0 = 0x10                           # m1_col+1 = 1 (col 0), LEFT half -> M1X 7
META_COL1 = 0x20                           # col 1 -> M1X 15 (argument 16, no clamp)

# col 0: drawn [3, 10]  -> touching at vl <= 10 (lit [vl, vl+6] reaches px 3 at vl >= -3)
blocked, _ = call_ovm1(META_COL0, [(1, 1)], vl=10)
assert blocked, ("col-0 strip is drawn at [3,10] but vl=10 (3 lit px inside it) "
                 "was NOT blocked - the player walks half into the wall")
blocked, _ = call_ovm1(META_COL0, [(1, 1)], vl=11)
assert not blocked, "col-0 strip blocked at vl=11 (one px clear of the art)"
blocked, _ = call_ovm1(META_COL0, [(1, 1)], vl=0)
assert blocked, "col-0 strip must block a player standing at the left edge"

# col 1 (M1X 15): unchanged window [2, 15]
blocked, _ = call_ovm1(META_COL1, [(3, 1)], vl=15)
assert blocked, "col-1 strip stopped blocking at vl=15"
blocked, _ = call_ovm1(META_COL1, [(3, 1)], vl=16)
assert not blocked, "col-1 strip blocked one px early (vl=16)"

print("test_m1_edge: OK (col-0 strip blocks at its DRAWN position [3,10]; "
      "col-1 window unchanged)")
