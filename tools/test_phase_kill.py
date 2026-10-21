"""Hot-overlap death — HotOverlapBody unit test (C11 PF-derived hot, 2026-10-21).

C11 replaced the per-shape 5 B/record hot stream with a PF sweep: convert
promotes EVERY row-1 wall of a mid_band_type=1 model, so the hot cells ARE the
solid row-1 PF cells; the C4 bomb punch clears PF0Buf cells, so a blasted
parent cell stops being hot automatically. Contract under test:

  * MetaB b6 (hot room) + a SOLID row-1 cell inside the player box → kill
    (Temp b7 set, C=1 exit);
  * the same box in a COLD room (b6 clear) → pass, even over a solid cell
    (that solidity is ordinary collision, handled before this body);
  * a bomb-PUNCHED (empty) row-1 cell + hot room → pass (the punched parent
    must not kill: test_bomb_half_wall rides the same path);
  * the box must overlap ROW 1: a box entirely on rows 0/2 never kills;
  * hot-band M1 block cell (PF-open, staged in RoomM1Hot): kills while the
    strip is alive (EnemyDeadMask b4 clear), passes once the strip is dead;
  * feature-record stream: $80 phase needs b5 armed + box overlap (then
    latches b6); $82 hcrunch is always hot on band 1; $81 is inert.

Run: /home/iuri/python3/bin/python3 tools/test_phase_kill.py  (from src/)
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SRC = TOOLS.parent / "src"
sys.path.insert(0, str(TOOLS))

from py65.devices.mpu6502 import MPU  # noqa: E402
from test_cell_map import Mem as Mem02, RTS_SENTINEL, parse_labels  # noqa: E402

L2 = parse_labels(SRC / "bank3.lst", {   # C7: HotOverlapBody is bank3
    "HotOverlapBody", "CollisionCellX", "CollisionCellY",
    "CollisionEndX", "CollisionEndY", "RoomRectsLo", "RoomRectsHi",
    "RoomMetaB", "RoomM1Hot", "EnemyDeadMask", "BombPacked", "Temp",
    "PF0Buf",
})
need = ({"HotOverlapBody", "CollisionCellX", "CollisionCellY",
         "CollisionEndX", "CollisionEndY", "RoomRectsLo", "RoomRectsHi",
         "RoomMetaB", "RoomM1Hot", "EnemyDeadMask", "BombPacked", "PF0Buf"} -
        L2.keys())
if need:
    sys.exit(f"labels missing: {sorted(need)}")
TEMP = L2.get("Temp", 0x88)

STREAM = 0xA0
HOT = 0x40                 # MetaB b6: mid_band_type hot
# box = (CollisionCellX max col, CollisionCellY top row,
#        CollisionEndX min col, CollisionEndY bottom row) — PHM semantics;
# the sweep is display cols min..max over PF row 1.
INSIDE = (5, 1, 4, 1)      # row-1 box over display cols 4-5
OUTSIDE = (1, 1, 0, 1)     # same row, cols 0-1 (cell bit clear)
BELOW = (5, 2, 4, 2)       # same cols, rows below the hot band
ARMED = 0x20               # EnemyDeadMask b5 = blink solid this frame
PHASE_REC = [0x80, 4, 1, 2, 1]       # class,x,y,w,h (one phase cell)
HCRUNCH_REC = [0x82, 0, 1, 20, 1]    # class,x,y,w,h (fixed prefix)


def run(mask_hot: bool = True, box=(5, 1, 4, 1), dead_mask: int = 0,
        pf_row1: int = 0x80, stream: list[int] | None = None,
        m1hot: int = 0) -> int:
    """HotOverlapBody over one staged room state; returns Temp (b7 = kill).

    pf_row1 stages the PF row-1 cell at display col 4 (PF1Buf row 1, bit 7);
    0x00 = the parent cell was bomb-punched."""
    mem = Mem02()
    r = mem.ram
    if stream:
        payload = bytes([len(stream)] + stream)
        r[STREAM - 0x80:STREAM - 0x80 + len(payload)] = payload
        ptr = STREAM
    else:
        ptr = 0xF8B7                      # bank3's static $00 count byte
    for name, val in (("RoomRectsLo", ptr & 0xFF), ("RoomRectsHi", ptr >> 8),
                      ("CollisionCellX", box[0]), ("CollisionCellY", box[1]),
                      ("CollisionEndX", box[2]), ("CollisionEndY", box[3]),
                      ("RoomMetaB", HOT if mask_hot else 0),
                      ("RoomM1Hot", m1hot),
                      ("EnemyDeadMask", dead_mask),
                      ("BombPacked", 0)):
        r[L2[name] - 0x80] = val
    r[TEMP - 0x80] = 0
    # PF row 1, display col 4 -> PF1Buf + 1, bit 7 (ColMask[4] = $80).
    r[L2["PF0Buf"] + 3 + 1 - 0x80] = pf_row1
    mem.bank = 3              # C7: the hot walkers live in bank3
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
    ("hot + solid row-1 cell + inside", run(True, INSIDE), True),
    ("hot + box off the solid cell", run(True, OUTSIDE), False),
    ("hot + box below the hot band", run(True, BELOW), False),
    ("cold room + solid cell (no hot sweep)", run(False, INSIDE), False),
    # C4 punch: a thin parent cell is emptied in the PF buffer, so the hot
    # piece dies with the wall — no record gate needed any more.
    ("hot + bomb-punched parent cell", run(True, INSIDE, pf_row1=0x00), False),
    # --- hot-band M1 block cell (PF-open, staged at load) ---------------
    ("hot + M1 cell col 2 + strip alive", run(True, (5, 1, 4, 1), m1hot=3,
                                             pf_row1=0x00), True),
    ("hot + M1 cell col 2 + strip dead", run(True, (5, 1, 4, 1), dead_mask=0x10,
                                            m1hot=3, pf_row1=0x00), False),
    ("hot + M1 cell away from the box", run(True, (5, 1, 4, 1), m1hot=9,
                                            pf_row1=0x00), False),
    # --- feature records -------------------------------------------------
    ("phase armed + inside", run(False, INSIDE, dead_mask=ARMED,
                                stream=PHASE_REC), True),
    ("phase disarmed + inside", run(False, INSIDE, stream=PHASE_REC), False),
    ("phase armed + outside", run(False, OUTSIDE, dead_mask=ARMED,
                                stream=PHASE_REC), False),
    ("phase armed + below", run(False, BELOW, dead_mask=ARMED,
                               stream=PHASE_REC), False),
    ("$81 inert", run(False, INSIDE, dead_mask=ARMED,
                      stream=[0x81, 4, 1, 2, 1]), False),
    # hcrunch: the covered prefix always starts at col 0, so the box must
    # reach display col 0/1 (n=1 at clock 0 = the first 2-col cell).
    ("hcrunch + inside band 1", run(False, (1, 1, 0, 1),
                                   stream=HCRUNCH_REC), True),
    ("hcrunch + box below band 1", run(False, BELOW, stream=HCRUNCH_REC),
     False),
]
bad = [(n, t, want) for n, t, want in cases if killed(t) != want]
if bad:
    for n, t, want in bad:
        print(f"FAIL {n}: Temp=${t:02X} kill={killed(t)} want={want}")
    sys.exit(1)
print("test_phase_kill: OK (PF-derived hot sweep, punched parent passes, "
      "M1 block cell gated on the strip, phase/hcrunch/inert records)")
