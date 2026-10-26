#!/usr/bin/env python3
"""The async-collision pack in LineCount must survive a feature-record walk.

User report 2026-10-25 (level 8 room 4 as the editor counts, the n+H+Gate
room): "I can cross the whole async wall on the left just walking" - and in
other rooms "half the player moves inside the wall". The wall DID block, but
only on ~5 frames out of 6.

Root cause: bank1's HUD entry copies the VBL-packed collision byte ($8F) into
LineCount ($84); OverlayTramp gates the whole async overlay (ball strip, M1
strip, shutter) on LineCount != 0. HotOverlapBody's feature dispatch
(.HOVfeature, any room with a phase/hcrunch record - Gate rooms) did
`lda RoomMetaB / sta LineCount` as a "re-stage" nobody reads, so every
overscan frame where the player's vertical probe hit the floor (HotOverlapFlag
-> feature walk) zeroed the pack, and the horizontal step of that same frame
saw "symmetric room": the strip was skipped and the player advanced one pixel.
Standing on a floor in a Gate room, that is ~1 px per 6 frames through the wall.

Calls the real frozen HotOverlapBody with a phase record staged and asserts
LineCount comes back untouched. Run: /home/iuri/python3/bin/python3 tools/test_linecount_pack.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"
NEED = {"HotOverlapBody", "CollisionCellX", "CollisionCellY", "CollisionEndX",
        "CollisionEndY", "RoomRectsLo", "RoomRectsHi", "RoomMetaB",
        "RoomM1Hot", "EnemyDeadMask", "BombPacked", "LineCount"}
L = parse_labels(FROZEN / "bank3.lst", NEED)
missing = NEED - L.keys()
if missing:
    sys.exit(f"frozen labels missing: {sorted(missing)}")

STREAM = 0xA0
PHASE_REC = [0x80, 4, 1, 2, 1]          # a feature record: forces .HOVfeature
PACK = 0x08                             # an M1-only room's packed byte


def run(meta_b: int) -> int:
    mem = Mem()
    r = mem.ram
    payload = bytes([1] + PHASE_REC)
    r[STREAM - 0x80:STREAM - 0x80 + len(payload)] = payload
    for name, val in (("RoomRectsLo", STREAM), ("RoomRectsHi", 0),
                      ("CollisionCellX", 5), ("CollisionCellY", 1),
                      ("CollisionEndX", 4), ("CollisionEndY", 1),
                      ("RoomMetaB", meta_b), ("RoomM1Hot", 0),
                      ("EnemyDeadMask", 0), ("BombPacked", 0),
                      ("LineCount", PACK)):
        r[L[name] - 0x80] = val
    mem.bank = 3
    mpu = MPU(memory=mem)
    mpu.pc = L["HotOverlapBody"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return r[L["LineCount"] - 0x80]
    sys.exit("HotOverlapBody never returned")


for meta_b in (0x00, 0x40):
    got = run(meta_b)
    assert got == PACK, (f"feature walk (MetaB ${meta_b:02X}) overwrote the "
                         f"collision pack: LineCount ${PACK:02X} -> ${got:02X}; "
                         "the async overlay is skipped on that frame")

print("test_linecount_pack: OK (feature-record walk leaves LineCount alone)")
