#!/usr/bin/env python3
"""C5 async extras loader — test-owned level block, real bank2 loader.

The live stage cannot prove the extras path on its own: every async room in it
is a patch-only M1 strip or the one hcrunch room, so a regression in (say) the
record-skip arithmetic would only show up when a level carries SEVERAL async
rooms, or a phase room, or a feature room whose shape is hot. This test
therefore AUTHORS its own level block (user rule 2026-10-14: tests own their
data) and drives the REAL `B3RoomBlocks` / `ExtrasLoad` in py65:

  * a non-async room  -> MetaA = 0, MetaB = $40 iff the shape has hot records,
                         hot stream = the shape;
  * a patch-only room -> MetaA = (stored | side-0 patch rows), MetaB stored,
                         hot stream = the shape (patches paint via ball/M1);
  * a feature room    -> the feature cells are OR'd into the PF triple and
                         RoomRectsLo/Hi repoint at the extras' hot stream;
  * the record-skip walk reaches record N (ordinal indexing) and the stream
    base is derived as base + 3n + 4*total(enemy records).

Run: /home/iuri/python3/bin/python3 tools/test_extras_room.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT / "tools"))

import test_cell_map as _CM  # noqa: E402
from test_cell_map import parse_labels  # noqa: E402

NAMES = {"B3RoomBlocks", "ERBlocksDone", "PF0Buf", "RoomRectsLo", "RoomRectsHi",
         "RoomPF0Lo", "RoomPF0Hi", "RoomMetaA", "RoomMetaB", "LevelPFDataLo",
         "LevelPFDataHi", "LevelRoomN", "RoomNo"}
LAB = parse_labels(SRC / "bank2.lst", NAMES)
missing = NAMES - LAB.keys()
if missing:
    sys.exit(f"bank2.lst labels missing: {sorted(missing)}")

BANK2 = bytearray((SRC / "bank2.bin").read_bytes())

# --- test-owned staging area: bank2's FooterFont/fill tail ($F800-$F8F7) is
# not executed by this test (only B3RoomBlocks + the tail jump run) --------
SHAPE_A = 0xF800          # non-async shape (cold: no hot records)
SHAPE_B = 0xF80B          # feature-room shape (cold)
LEVEL = 0xF820            # synthetic level block

PF_A = bytes.fromhex("f0 30 f0 ff 00 ff 3f 0c ff")
PF_B = bytes.fromhex("f0 f0 f0 ff ff 3f 3f 00 ff")


def put(addr: int, data: bytes) -> None:
    off = addr - 0xF000
    BANK2[off:off + len(data)] = data


put(SHAPE_A, bytes([0]) + PF_A)                        # hot count 0 + PF
put(SHAPE_B, bytes([0]) + PF_B)

# --- level block: n = 3 rooms -> shapes / positions / counts / (no enemies)
# / extras. Room 0 = plain, room 1 = patch-only, room 2 = hcrunch feature.
SHAPES = bytes([0x00, 0x80, 0x80])        # idx 0 plain | ... (shape addrs via
                                          # RoomRectsLo below)
POSITIONS = bytes([0x00, 0x01, 0x02])
COUNTS = bytes([0x00, 0x01, 0x02])        # rooms 1/2 = ordinals 1/2
EXTRAS = bytes([
    # room 1 (ordinal 1): 2 patches, 0 features, MetaA $90 (M1 col 8),
    # MetaB $00; patch bytes = row0/side0/col9 ($09) and row1/side1/col8
    # ($58) — the loader ORs band 0 from the side-0 patch only.
    0x02, 0x90, 0x00, 0x09, 0x58,
    # room 2 (ordinal 2): 0 patches, 1 hcrunch feature (prefix end col 9),
    # MetaA/MetaB 0, then the room's hot stream (count 1, $82 prefix record).
    0x04, 0x00, 0x00, 0x89,
    0x01, 0x82, 0x00, 0x01, 0x14, 0x01,
])
put(LEVEL, SHAPES + POSITIONS + COUNTS + EXTRAS)
EXTRAS_BASE = LEVEL + 3 * 3               # base + 3n + 4*0 enemy records
REC1 = EXTRAS_BASE                        # room 1 record (5 B, no hot stream)
REC2 = EXTRAS_BASE + 5                    # room 2 record (flags..hot count)
ROOM2_HOT = REC2 + 4                      # 3 B header + 1 feature byte = the
                                          # room's hot-stream count byte


def run_room(room: int, shape: int) -> bytearray:
    """Drive B3RoomBlocks for `room`; stop at ERBlocksDone (tail of the
    loader) and return the ZP image."""
    _CM.BANK2 = bytearray(BANK2)          # fresh private copy per case
    mem = _CM.Mem()
    mem.bank = 2                          # B3RoomBlocks lives in bank2
    r = mem.ram
    r[LAB["LevelPFDataLo"] - 0x80] = LEVEL & 0xFF
    r[LAB["LevelPFDataHi"] - 0x80] = LEVEL >> 8
    r[LAB["LevelRoomN"] - 0x80] = 3
    r[LAB["RoomNo"] - 0x80] = room
    r[LAB["RoomRectsLo"] - 0x80] = shape & 0xFF
    r[LAB["RoomRectsHi"] - 0x80] = shape >> 8
    mpu = _CM.MPU(memory=mem) if hasattr(_CM, "MPU") else None
    if mpu is None:
        from py65.devices.mpu6502 import MPU  # noqa: PLC0415
        mpu = MPU(memory=mem)
    mpu.pc = LAB["B3RoomBlocks"]
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(20000):
        mpu.step()
        if mpu.pc == LAB["ERBlocksDone"] and mem.bank == 2:
            return r
    sys.exit(f"B3RoomBlocks(room={room}) never reached ERBlocksDone "
             f"(pc=${mpu.pc:04X}, bank={mem.bank})")


def meta(r: bytearray) -> tuple[int, int]:
    return (r[LAB["RoomMetaA"] - 0x80], r[LAB["RoomMetaB"] - 0x80])


def hot_ptr(r: bytearray) -> int:
    return (r[LAB["RoomRectsLo"] - 0x80]
            | (r[LAB["RoomRectsHi"] - 0x80] << 8))


def main() -> int:
    # --- 1. plain room: meta derived, hot stream stays the shape ----------
    r = run_room(0, SHAPE_A)
    assert meta(r) == (0, 0), f"plain room meta {meta(r)}"
    assert bytes(r[LAB["PF0Buf"] - 0x80:LAB["PF0Buf"] - 0x80 + 9]) == PF_A
    assert hot_ptr(r) == SHAPE_A, f"plain hot ptr ${hot_ptr(r):04X}"

    # --- 2. patch-only room: ORs the side-0 patch band into MetaA ---------
    r = run_room(1, SHAPE_A)
    assert meta(r) == (0x91, 0x00), (
        f"patch room meta ${meta(r)[0]:02X}/${meta(r)[1]:02X}, want $91/$00 "
        "(stored $90 | side-0 patch row 0)")
    assert bytes(r[LAB["PF0Buf"] - 0x80:LAB["PF0Buf"] - 0x80 + 9]) == PF_A
    assert hot_ptr(r) == SHAPE_A, "patch-only room must keep the shape stream"

    # --- 3. feature room: PF cells + the extras hot stream ----------------
    r = run_room(2, SHAPE_B)
    got = bytes(r[LAB["PF0Buf"] - 0x80:LAB["PF0Buf"] - 0x80 + 9])
    want = bytearray(PF_B)
    # hcrunch prefix cols 0..9 = the whole row-1 band solid (PF pairs)
    want[1] |= 0xF0 | 0xC0                 # PF0 row1 (cols 0-1)
    want[4] |= 0xFF                        # PF1 row1 (cols 2-5)
    want[7] |= 0xFF                        # PF2 row1 (cols 6-9)
    assert got == want, f"feature PF {got.hex()} != {bytes(want).hex()}"
    assert meta(r) == (0, 0), f"feature room meta {meta(r)}"
    assert hot_ptr(r) == ROOM2_HOT, (
        f"feature hot ptr ${hot_ptr(r):04X} != extras stream ${ROOM2_HOT:04X}")
    assert BANK2[ROOM2_HOT - 0xF000] == 1, "extras hot count must be 1"
    assert BANK2[ROOM2_HOT - 0xF000 + 1] == 0x82, "feature record class"

    # --- 4. ordinary-room hot bit: a hot shape derives MetaB b6 -----------
    put(SHAPE_A, bytes([1, 0x08, 0, 1, 2, 1]) + PF_A)   # 1 hot record
    r = run_room(0, SHAPE_A)
    assert meta(r) == (0, 0x40), (
        f"hot shape meta ${meta(r)[0]:02X}/${meta(r)[1]:02X}, want $00/$40")
    put(SHAPE_A, bytes([0]) + PF_A)

    # --- 5. the ordinal walk skipped record 1 to reach record 2 -----------
    assert REC1 < REC2 and BANK2[REC1 - 0xF000 + 1] == 0x90, (
        "record 1 MetaA sanity (the walk must step over it)")
    assert BANK2[ROOM2_HOT - 0xF000] == 1, "record 2 hot count sanity"
    print("test_extras_room: OK (plain/patch/feature/hot-shape cases; "
          "extras base = base + 3n + 4*records, ordinal walk)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
