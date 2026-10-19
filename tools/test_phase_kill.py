"""Phase-cell crush kill — HotOverlapBody .HOVfeature unit test (2026-10-13).

User ruling: when a phase wall APPEARS while the player is inside the cell,
it kills (hot-rock death path, Temp b7 → bank0 `jsr LoseLife`).

Contract under test (bank2.asm .HOVfeature):
  * $80 record + EnemyDeadMask b5 armed + candidate box contained in the
    cell rect → Temp b7 set (kill), C=1 exit.
  * b5 clear (blink OFF half) → pass, no kill.
  * $81 (vcrunch) is SKIPPED in .HOVfeature (record-path walk, stack-stomp
    2026-10-13) — kill rides OvShutBand's overlay miss path instead
    (test_vcr_shutter case5 + test_phase_kill_frame); $82 (hcrunch, not
    generated yet) likewise takes the record path only when shipped.
  * Legacy b7-clear records unchanged: mask bit matches BombPacked → skip,
    unbombed wall piece + inside → kill (parity with pre-feature behavior).

Run: /home/iuri/python3/bin/python3 tools/test_phase_kill.py  (from src/)
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SRC = TOOLS.parent / "src"
sys.path.insert(0, str(TOOLS))

from py65.devices.mpu6502 import MPU  # noqa: E402
from test_cell_map import Mem as Mem02, RTS_SENTINEL, parse_labels  # noqa: E402

L2 = parse_labels(SRC / "bank3.lst", {
    "HotOverlapBody", "CollisionCellX", "CollisionCellY",
    "CollisionEndX", "CollisionEndY", "RoomRectsLo",
    "EnemyDeadMask", "BombPacked", "Temp",
})
need = ({"HotOverlapBody", "CollisionCellX", "CollisionCellY",
         "CollisionEndX", "CollisionEndY", "RoomRectsLo",
         "EnemyDeadMask", "BombPacked"} - L2.keys())
if need:
    sys.exit(f"labels missing: {sorted(need)}")
TEMP = L2.get("Temp", 0x88)

STREAM = 0xA0
# synthetic hot stream: solid count 0, hot count 1, record = mask,x,y,w,h
REC = {"x": 4, "y": 1, "w": 2, "h": 1}
# box = (CollisionCellX max col, CollisionCellY top row,
#        CollisionEndX min col, CollisionEndY bottom row) — PHM semantics;
# HOV overlap = box vs [x, x+w) x [y, y+h), inclusive-edge overlap.
INSIDE = (5, 1, 4, 1)      # same cols/row as the record
OUTSIDE = (1, 1, 0, 1)     # box left of the record
BELOW = (5, 2, 4, 2)       # same cols, row under the record
ARMED = 0x20               # EnemyDeadMask b5 = blink solid this frame


def run(mask: int, box: tuple[int, int, int, int],
        dead_mask: int, bomb_packed: int = 0) -> int:
    """HotOverlapBody over one record; returns Temp (b7 = kill)."""
    mem = Mem02()
    r = mem.ram
    r[STREAM - 0x80:STREAM - 0x80 + 7] = bytes(
        [0, 1, mask, REC["x"], REC["y"], REC["w"], REC["h"]])
    for name, val in (("RoomRectsLo", STREAM),
                      ("CollisionCellX", box[0]), ("CollisionCellY", box[1]),
                      ("CollisionEndX", box[2]), ("CollisionEndY", box[3]),
                      ("EnemyDeadMask", dead_mask),
                      ("BombPacked", bomb_packed)):
        r[L2[name] - 0x80] = val
    r[TEMP - 0x80] = 0
    mem.bank = 3
    mpu = MPU(memory=mem)
    mpu.pc = L2["HotOverlapBody"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return r[TEMP - 0x80]
    sys.exit("HotOverlapBody never returned (sentinel not reached)")


def killed(temp: int) -> bool:
    return bool(temp & 0x80)


cases = [
    ("armed + inside", run(0x80, INSIDE, ARMED), True),
    ("disarmed + inside", run(0x80, INSIDE, 0), False),
    ("armed + outside", run(0x80, OUTSIDE, ARMED), False),
    ("armed + below", run(0x80, BELOW, ARMED), False),
    ("armed + inside + $81 vcrunch -> record path skipped (kill = OvShutBand)",
     run(0x81, INSIDE, ARMED), False),
    ("legacy $40 unbombed + inside", run(0x40, INSIDE, 0, 0x00), True),
    ("legacy $40 bombed + inside", run(0x40, INSIDE, 0, 0x40), False),
]
bad = [(n, t, want) for n, t, want in cases if killed(t) != want]
if bad:
    for n, t, want in bad:
        print(f"FAIL {n}: Temp=${t:02X} kill={killed(t)} want={want}")
    sys.exit(1)
print("test_phase_kill: OK (crush kill armed/inside only; $81 record path "
      "skipped, $82 gated; bombed/disarmed/outside pass; legacy gates "
      "unchanged)")
