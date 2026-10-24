#!/usr/bin/env python3
"""C5/C7/C11 async extras loader — test-owned shapes + stream, real bank3
loader.

The live stage cannot prove the extras path on its own: every async room in it
is a patch-only M1 strip or the one hcrunch room, so a regression in (say) the
record-skip arithmetic would only show up when a level carries SEVERAL async
rooms, or a phase room, or a feature room whose shape is hot. This test
therefore AUTHORS its own shapes + extras stream (user rule 2026-10-14: tests
own their data) and drives the REAL B3RoomBlocks / ExtrasLoad in py65:

  * a non-async room  -> MetaA = 0, MetaB = $40 iff the shape is HOT (band 1's
                         index b7, C11), RoomRects = the no-stream sentinel,
                         RoomM1Hot = 0;
  * a patch-only room -> MetaA = (stored | side-0 patch rows), MetaB stored,
                         RoomM1Hot = the hot-band M1 block cell (col+1) when
                         the shape is hot and a side-1 row-1 patch exists
                         (C11: derived from the patch list, no hot record);
  * a feature room    -> the feature cells are OR'd into the PF triple and
                         RoomRectsLo/Hi repoint at the extras' FEATURE-record
                         stream;
  * the record-skip walk reaches record N (ordinal indexing).

C7 (2026-10-20) contract — the loader is BANK3 and takes:
  * RoomPF0Lo ($99) = the raw shapes byte (idx b5-0 | band b6 | extras b7),
    staged by bank2's EnterRoomB2;
  * LevelConnSpare ($A2) = the room's 1-based extras ordinal;
  * Level ($A3) = the level index into the generated LevExtrasLo/Hi base
    table, and LEVEL_ShapeTable for the block address. Both live in bank3,
    so the harness patches them in its PRIVATE bank3 copy.

Run: /home/iuri/python3/bin/python3 tools/test_extras_room.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"   # test-owned banks+labels
sys.path.insert(0, str(ROOT / "tools"))

import test_cell_map as _CM  # noqa: E402
from test_cell_map import parse_labels  # noqa: E402

NAMES = {"B3RoomBlocks", "PF0Buf", "RoomRectsLo", "RoomRectsHi",
         "RoomPF0Lo", "RoomPF0Hi", "RoomMetaA", "RoomMetaB", "Level",
         "LevelConnSpare", "RoomNo", "LEVEL_ShapeTable",
         "LevExtrasLo", "LevExtrasHi", "RoomM1Hot", "RoomNoStream",
         "RowPoolPF0", "RowPoolPF1", "RowPoolPF2"}
LAB = parse_labels(FROZEN / "bank3.lst", NAMES)
missing = NAMES - LAB.keys()
if missing:
    sys.exit(f"bank3.lst labels missing: {sorted(missing)}")

BANK3 = bytearray((FROZEN / "bank3.bin").read_bytes())

# --- test-owned staging area inside bank3's $F010 data window tail ----------
SHAPE_A = 0xF400          # non-async shape (cold: no hot cells)
SHAPE_AH = 0xF410         # same rows, band 1 flagged HOT (b7)
SHAPE_B = 0xF420          # feature-room shape (cold)
EXTRAS = 0xF440           # synthetic extras stream (level 0's base)

# N=4 stride 4: [PF0 r0-r3][PF1 r0-r3][PF2 r0-r3]; row 3 repeats row 2
# (the converter pads a 3-row authored model into 4 drawn bands).
PF_A = bytes.fromhex("f0 30 f0 f0 ff 00 ff ff 3f 0c ff ff")
PF_B = bytes.fromhex("f0 f0 f0 f0 ff ff 3f 3f 3f 00 ff ff")


def put(addr: int, data: bytes) -> None:
    off = addr - 0xF000
    BANK3[off:off + len(data)] = data


def install_rows(pf12: bytes) -> list[int]:
    """C3/C13: write a 12-byte PF image's four band rows (stride 4) into
    the private pool image and return its four row indices (band 0..3).

    A shape block no longer carries PF bytes — it carries 3 one-byte indices
    into RowPoolPF0/1/2, which the loader expands into PF0Buf. The test
    OWNS these pool slots (the private bank3 copy is never played), so the
    columns are rebuilt from a deterministic walk of both fixtures."""
    rows = [(pf12[b], pf12[4 + b], pf12[8 + b]) for b in range(4)]
    idx = []
    for row in rows:
        if row not in _POOL:
            _POOL.append(row)
        idx.append(_POOL.index(row))
    for column, reg in (("RowPoolPF0", 0), ("RowPoolPF1", 1),
                        ("RowPoolPF2", 2)):
        base = LAB[column] - 0xF000
        for i, r in enumerate(_POOL):
            BANK3[base + i] = r[reg]
    return idx


def shape_block(pf12: bytes, hot: bool = False) -> bytes:
    """C11/C13 block layout: exactly the 4 row indices, band 1 b7 = hot."""
    idx = install_rows(pf12)
    if hot:
        idx[1] |= 0x80
    return bytes(idx)


_POOL: list[tuple[int, int, int]] = []

put(SHAPE_A, shape_block(PF_A))
put(SHAPE_AH, shape_block(PF_A, hot=True))
put(SHAPE_B, shape_block(PF_B))

# The loader resolves the shape address through LEVEL_ShapeTable and the
# extras base through LevExtrasLo/Hi[Level]; point rows 0..2 / level 0 at the
# fixtures above (the private copy is the only one touched).
for slot, shape in enumerate((SHAPE_A, SHAPE_A, SHAPE_B, SHAPE_AH)):
    off = LAB["LEVEL_ShapeTable"] - 0xF000 + 2 * slot
    BANK3[off] = shape & 0xFF
    BANK3[off + 1] = shape >> 8
BANK3[LAB["LevExtrasLo"] - 0xF000] = EXTRAS & 0xFF
BANK3[LAB["LevExtrasHi"] - 0xF000] = EXTRAS >> 8

# --- extras stream: room 1 patch-only, room 2 hcrunch feature --------------
# C11 record layout: flags | MetaA | MetaB | 1 B/patch | 1 B/feature |
# then [n_features > 0] count + 5 B/FEATURE records (no hot records any more).
STREAM = bytes([
    # room 1 (ordinal 1): 2 patches, 0 features, MetaA $90 (M1 col 8),
    # MetaB $40 (hot shape); patch bytes = row0/side0/col9 ($09) and
    # row1/side1/col8 ($58) — the loader ORs band 0 from the side-0 patch and
    # stages RoomM1Hot = 8+1 from the side-1 row-1 patch.
    0x02, 0x90, 0x40, 0x09, 0x58,
    # room 2 (ordinal 2): 0 patches, 1 hcrunch feature (prefix end col 9),
    # MetaA/MetaB 0, then the room's FEATURE stream (count 1, $82 record).
    0x04, 0x00, 0x00, 0x89,
    0x01, 0x82, 0x00, 0x01, 0x14, 0x01,
])
put(EXTRAS, STREAM)
REC1 = EXTRAS                       # room 1 record (5 B, no stream)
REC2 = EXTRAS + 5                   # room 2 record (flags..count)
ROOM2_STREAM = REC2 + 4             # 3 B header + 1 feature byte

SHAPE_IDX = {0: 0, 1: 0, 2: 2, 3: 3}   # room -> synthetic table row


def run_room(room: int, ordinal: int = 0) -> bytearray:
    """Drive B3RoomBlocks; stop when the ReturnPad rts reaches the sentinel
    and return the ZP image."""
    _CM.BANK3 = bytearray(BANK3)          # fresh private copy per case
    mem = _CM.Mem()
    mem.bank = 3                          # B3RoomBlocks lives in bank3
    r = mem.ram
    r[LAB["RoomPF0Lo"] - 0x80] = SHAPE_IDX[room] | (0x80 if ordinal else 0)
    r[LAB["LevelConnSpare"] - 0x80] = ordinal
    r[LAB["Level"] - 0x80] = 0            # level 0 -> the fixture base
    r[LAB["RoomNo"] - 0x80] = room
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
        if mpu.pc == _CM.RTS_SENTINEL:
            assert mem.bank == 0, f"returned in bank {mem.bank}"
            return r
    sys.exit(f"B3RoomBlocks(room={room}) never returned "
             f"(pc=${mpu.pc:04X}, bank={mem.bank})")


def meta(r: bytearray) -> tuple[int, int]:
    return (r[LAB["RoomMetaA"] - 0x80], r[LAB["RoomMetaB"] - 0x80])


def stream_ptr(r: bytearray) -> int:
    return (r[LAB["RoomRectsLo"] - 0x80]
            | (r[LAB["RoomRectsHi"] - 0x80] << 8))


def main() -> int:
    nostream = LAB["RoomNoStream"]

    # --- 1. plain cold room: MetaA=0, MetaB=0, no stream, no M1 cell ------
    r = run_room(0)
    assert meta(r) == (0, 0), f"plain room meta {meta(r)}"
    assert bytes(r[LAB["PF0Buf"] - 0x80:LAB["PF0Buf"] - 0x80 + 12]) == PF_A
    assert stream_ptr(r) == nostream, (
        f"plain room stream ${stream_ptr(r):04X} != sentinel ${nostream:04X}")
    assert r[LAB["RoomM1Hot"] - 0x80] == 0, "plain room staged an M1 cell"

    # --- 2. hot shape (band 1 b7): MetaB b6, still no stream --------------
    r = run_room(3)
    assert meta(r) == (0, 0x40), (
        f"hot shape meta ${meta(r)[0]:02X}/${meta(r)[1]:02X}, want $00/$40")
    assert stream_ptr(r) == nostream, "hot room must not point at a stream"

    # --- 3. patch-only room: ORs the side-0 band, stages the M1 cell ------
    r = run_room(1, ordinal=1)
    assert meta(r) == (0x91, 0x40), (
        f"patch room meta ${meta(r)[0]:02X}/${meta(r)[1]:02X}, want $91/$40 "
        "(stored $90 | side-0 patch row 0)")
    assert bytes(r[LAB["PF0Buf"] - 0x80:LAB["PF0Buf"] - 0x80 + 12]) == PF_A
    assert stream_ptr(r) == nostream, "patch-only room must have no stream"
    assert r[LAB["RoomM1Hot"] - 0x80] == 9, (
        f"RoomM1Hot=${r[LAB['RoomM1Hot'] - 0x80]:02X}, want 9 (side-1 row-1 "
        "patch col 8 -> col+1)")

    # --- 4. feature room: PF cells + the extras FEATURE stream ------------
    r = run_room(2, ordinal=2)
    got = bytes(r[LAB["PF0Buf"] - 0x80:LAB["PF0Buf"] - 0x80 + 12])
    want = bytearray(PF_B)
    # hcrunch prefix cols 0..9 = the whole row-1 band solid (PF pairs)
    want[1] |= 0xF0 | 0xC0                 # PF0 row1 (cols 0-1)
    want[5] |= 0xFF                        # PF1 row1 (cols 2-5)
    want[9] |= 0xFF                        # PF2 row1 (cols 6-9)
    print("DBG idx", list(BANK3[SHAPE_B - 0xF000:SHAPE_B - 0xF000 + 4]),
          "pool", list(BANK3[LAB["RowPoolPF0"] - 0xF000:
                           LAB["RowPoolPF0"] - 0xF000 + 6]))
    print("DBG got", got.hex(), "want", bytes(want).hex())
    assert got == want, f"feature PF {got.hex()} != {bytes(want).hex()}"
    assert meta(r) == (0, 0), f"feature room meta {meta(r)}"
    assert stream_ptr(r) == ROOM2_STREAM, (
        f"feature stream ${stream_ptr(r):04X} != extras stream "
        f"${ROOM2_STREAM:04X}")
    assert BANK3[ROOM2_STREAM - 0xF000] == 1, "extras stream count must be 1"
    assert BANK3[ROOM2_STREAM - 0xF000 + 1] == 0x82, "feature record class"

    # --- 5. the ordinal walk skipped record 1 to reach record 2 -----------
    assert REC1 < REC2 and BANK3[REC1 - 0xF000 + 1] == 0x90, (
        "record 1 MetaA sanity (the walk must step over it)")
    assert BANK3[ROOM2_STREAM - 0xF000] == 1, "record 2 stream-count sanity"
    print("test_extras_room: OK (plain/hot/patch/feature cases; bank3 "
          "loader, LevExtras base + ordinal walk, PF-derived hot + M1 cell)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
