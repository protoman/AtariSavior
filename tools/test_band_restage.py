#!/usr/bin/env python3
"""EnterRoom must restage RoomBandColor (regression: level 1 room 1 death).

Bug (user report 2026-10-04): leaving level-002 room 1 (the ONLY band-on
room in the game) upward spawned at Y=PLAYER_MAX_Y=132 >= 125 with the
SOURCE room's still-staged ON band color -> CheckBandTouch killed the
player inside the band-less target room. Other levels: every room's band
is off, so the stale value was 0 and nothing fired.

EnterRoom's enemy batch folds per-room record +0/+1/+2 (ptr lo/hi/count);
+3 = bottom_color (same byte the VBL fold stages). The fix folds +3 too.

Drives the real EnterRoom (all its FoldIndirect batches + LoadPFBuffer +
LoadEnemyRam) for EVERY room of every level and asserts RoomBandColor
== 0 iff the room's bottom_band is off, plus EnemyCount sanity.

Run: /home/iuri/python3/bin/python3 tools/test_band_restage.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

import test_cell_map as _CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402

SRC = ROOT / "src"
ROOMS = SRC / "rooms"

# Sanctioned live-tracking exception (AGENTS): this test drives the built
# ROM's EnterRoom against the LIVE level jsons, so it must read the LIVE
# bank images. test_cell_map.Mem defaults to the frozen test-owned banks —
# pointing its bank globals at src/bank*.bin keeps the frozen data out of
# this test without duplicating the Mem class. (Reading frozen banks here
# mixes the test-owned level layout with live labels → EnterRoom reads the
# wrong table and the run never returns.)
for _i in range(4):
    setattr(_CM, f"BANK{_i}", (SRC / f"bank{_i}.bin").read_bytes())
Mem = _CM.Mem

need0 = {"EnterRoom", "RoomBandColor", "LevelPFDataLo", "LevelPFDataHi",
         "LevelRoomN", "EnemyCount", "RoomNo", "RoomRectsLo", "RoomRectsHi",
         "EnemyDataLo", "EnemyDataHi", "PF0Buf", "Level"}
L0 = parse_labels(SRC / "bank0.lst", need0)
missing0 = need0 - L0.keys()
if missing0:
    sys.exit(f"bank0.lst labels missing: {sorted(missing0)}")

levels = []
for n in (1, 2, 3, 4):
    names = {f"LEVEL{n}_RoomShapes", f"LEVEL{n}_RoomCounts",
             f"LEVEL{n}_EnemyDataTable"}
    got = parse_labels(SRC / "bank2.lst", names)
    missing = names - got.keys()
    if missing:
        sys.exit(f"bank2.lst labels missing: {sorted(missing)}")
    levels.append((n, got))

ZMETA = parse_labels(SRC / "bank2.lst", {"RoomMetaA", "RoomMetaB"})
if {"RoomMetaA", "RoomMetaB"} - ZMETA.keys():
    sys.exit(f"bank2.lst labels missing: {sorted(ZMETA)}")

# C3 (2026-10-20): the row dictionary — the shape block stores 3 indices and
# the loader expands them through these three SoA columns into PF0Buf.
POOL = parse_labels(SRC / "bank3.lst",
                    {"RowPoolPF0", "RowPoolPF1", "RowPoolPF2"})
if {"RowPoolPF0", "RowPoolPF1", "RowPoolPF2"} - POOL.keys():
    sys.exit(f"bank2.lst labels missing: {sorted(set(POOL) or {'RowPool'})}")

sys.path.insert(0, str(ROOT / "tools"))
import convert_level as CL  # noqa: E402
import convert_room as CR  # noqa: E402

MODELS = CL.load_models(SRC / "rooms" / "models" / "models.json")


def enter_room(mem: Mem, table: int, room_count: int, room: int,
               level: int = 1) -> None:
    """Stage what LoadLevel stages (C4): the level block base + its room count.
    The RoomPositions / RoomCounts / enemy-record bases are the block's
    +n / +2n / +3n offsets (C2 2026-10-20: 3 B shape-index room records),
    derived by the readers."""
    r = mem.ram
    r[L0["LevelPFDataLo"] - 0x80] = table & 0xFF
    r[L0["LevelPFDataHi"] - 0x80] = table >> 8
    r[L0["LevelRoomN"] - 0x80] = room_count
    # C7 (2026-10-20): ExtrasLoad indexes bank3's per-level extras base table
    # with `Level` ($A3) — LoadLevelB2 sets it in the real game; the harness
    # stages what LoadLevel would (level is 1-based on the command line).
    r[L0["Level"] - 0x80] = level - 1
    mpu = MPU(memory=mem)
    mpu.pc = L0["EnterRoom"]
    mpu.a = room
    mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(20000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return
    sys.exit(f"EnterRoom(room={room}) never returned "
             f"(pc=${mpu.pc:04X}, bank={mem.bank})")


def main() -> int:
    checks = 0
    # C2: model block addresses (the shared M<id> blocks) — an async room must
    # NOT land on one of these, whatever its shape index says.
    model_blocks = parse_labels(
        SRC / "bank3.lst", {f"M{mid}RoomRects" for mid in range(16)})
    for n, syms in levels:
        data = json.loads((ROOMS / f"level_{n:03d}.json").read_text())
        level = data.get("level", data)
        table = syms[f"LEVEL{n}_RoomShapes"]
        enemy_data = syms[f"LEVEL{n}_EnemyDataTable"]
        rooms = level["rooms"]
        counts = [min(len(r.get("enemies") or []) + len(r.get("lamps") or []), 3)
                  for r in rooms]
        for i, room in enumerate(rooms):
            mem = Mem()
            enter_room(mem, table, len(rooms), i, n)
            band = mem.ram[L0["RoomBandColor"] - 0x80]
            want_on = bool(room.get("bottom_band"))
            if want_on:
                assert band != 0, (
                    f"level {n} room {i}: band ON in JSON but "
                    f"RoomBandColor=0 after EnterRoom (restage missing?)")
            else:
                assert band == 0, (
                    f"level {n} room {i}: RoomBandColor=${band:02X} but room "
                    f"has no band (stale value survived EnterRoom)")
            got_count = mem.ram[L0["EnemyCount"] - 0x80]
            want_count = min(len(room.get("enemies") or [])
                             + len(room.get("lamps") or []), 3)
            assert got_count == want_count, (
                f"level {n} room {i}: EnemyCount={got_count} want "
                f"{want_count} (wrong LevelEnemy record?)")
            # --- C2: packed per-room record → the right enemy record base ---
            want_rec = enemy_data + 4 * sum(counts[:i])
            got_rec = (mem.ram[L0["EnemyDataLo"] - 0x80]
                       | (mem.ram[L0["EnemyDataHi"] - 0x80] << 8))
            assert got_rec == want_rec, (
                f"level {n} room {i}: enemy record base ${got_rec:04X} want "
                f"${want_rec:04X} (packed count/index field misread)")
            # --- C3: TilePF0 derived from the rect list (rects + 2 + 2*n) ---
            rects = (mem.ram[L0["RoomRectsLo"] - 0x80]
                     | (mem.ram[L0["RoomRectsHi"] - 0x80] << 8))
            # --- C5 (2026-10-20): every room points at its shared MODEL
            # shape; the async extras are applied on top (patches/features/
            # meta) by the loader. So the block equals the model block for
            # every room, and the PF/meta/patch state must match the JSON.
            model = room.get("model_id")
            label = f"M{int(model)}RoomRects" if model is not None else None
            assert model is not None, (
                f"level {n} room {i}: no model_id (C5 needs a shared shape)")
            assert label in model_blocks, (
                f"level {n} room {i}: model {model} has no emitted shape "
                f"({label})")
            # A patch-only (or plain) room keeps the shape as its hot stream;
            # a FEATURE room repoints it at the extras copy, so the shape
            # identity is only directly observable in the non-feature case
            # (the PF bytes below still prove the shape was the source).
            feats_room = CL.room_feature_cells(room)
            shape = model_blocks[label]
            if not feats_room:
                assert rects == shape, (
                    f"level {n} room {i}: block ${rects:04X} != model shape "
                    f"{label} ${shape:04X}")
            # C4/C3 (2026-10-20): block = hot stream | 3 row-pool indices;
            # the rows sit at block + 1 + 5*hot (the old raw-PF offset), so
            # the loader expands them through RowPoolPF0/1/2 into PF0Buf.
            blocks = _CM.BANK3
            nhot = blocks[shape - 0xF000]
            rows_at = shape + 1 + 5 * nhot
            idx = blocks[rows_at - 0xF000:rows_at - 0xF000 + 3]
            want_pf = bytearray()
            for column in ("RowPoolPF0", "RowPoolPF1", "RowPoolPF2"):
                base = POOL[column] - 0xF000
                want_pf += bytes(blocks[base + i] for i in idx)
            assert len(want_pf) == 9
            # --- expected meta + features from the JSON (independent of the
            # generated bytes: the converter helpers re-derive them) ---
            rows = CL.rows_from_json(room, MODELS)
            # C3 (2026-10-20): the pool expansion must reproduce the SHAPE's raw
            # rows (feature cells are a room-level OR applied later), i.e. the
            # row dictionary is storage only, never a content change.
            mm = MODELS[int(model)]
            shape_rows = CL.rows_from_json(
                {"model_id": int(model), "tiles": mm.get("tiles"),
                 "width": mm.get("width", 10)}, MODELS)
            want_from_rows = bytes([CR.pf_values(r)[reg] for reg in range(3)
                                    for r in shape_rows])
            assert bytes(want_pf) == want_from_rows, (
                f"level {n} room {i}: expanded rows {bytes(want_pf).hex()} != "
                f"pf_values(room rows) {want_from_rows.hex()}")
            res = CL.resolve_asym_patches(CL.load_models(
                SRC / "rooms" / "models" / "models.json")[int(model)],
                room, rows)
            asym, ball_x, m1_x, m1_door, m1_right = (
                res if res else (None, 0, 0, False, False))
            want_a, want_b = CR.meta_bytes(
                rows, asym_rows=asym, asym_ball_x=ball_x, asym_m1_x=m1_x,
                hot=bool(MODELS[int(model)].get("mid_band_type")),
                door=False, m1_door=m1_door, m1_right=m1_right,
                source=f"level {n} room {i}")
            async_room = bool(room.get("asym_patches")
                              or room.get("feature_cells"))
            got_a = mem.ram[ZMETA["RoomMetaA"] - 0x80]
            got_b = mem.ram[ZMETA["RoomMetaB"] - 0x80]
            if async_room:
                assert (got_a, got_b) == (want_a, want_b), (
                    f"level {n} room {i}: staged MetaA/MetaB "
                    f"${got_a:02X}/${got_b:02X} != JSON "
                    f"${want_a:02X}/${want_b:02X} (extras record misread)")
            else:
                want_hot = 0x40 if nhot else 0
                assert (got_a, got_b) == (0, want_hot), (
                    f"level {n} room {i}: symmetric room must derive MetaA=0 "
                    f"and MetaB=$40*hot, got ${got_a:02X}/${got_b:02X} "
                    f"(hot count {nhot})")
            # feature cells: solid in the PF buffer (loader applies them) and
            # the hot stream comes from the extras copy
            feats = feats_room
            for _row, col, _tile in feats:
                pair = col
                mask = [0x30, 0xC0, 0xC0, 0x30, 0x0C, 0x03,
                        0x03, 0x0C, 0x30, 0xC0][pair]
                off = 0 if pair < 2 else 3 if pair < 6 else 6
                want_pf[off + 1] |= mask
            hot_ptr = (mem.ram[L0["RoomRectsLo"] - 0x80]
                       | (mem.ram[L0["RoomRectsHi"] - 0x80] << 8))
            # C3 (2026-10-20): the PF0Buf the kernel renders MUST be exactly
            # the pool expansion (+ the feature-cell bits the loader ORs in).
            got_pf = bytes(mem.ram[L0["PF0Buf"] - 0x80:
                                 L0["PF0Buf"] - 0x80 + 9])
            assert got_pf == bytes(want_pf), (
                f"level {n} room {i}: loaded PF0Buf {got_pf.hex()} != "
                f"expected {bytes(want_pf).hex()} (row-pool expansion)")
            if feats:
                assert hot_ptr != shape, (
                    f"level {n} room {i}: feature room must point the hot "
                    "stream at its extras record, not the model shape")
                assert blocks[hot_ptr - 0xF000] == 1, (
                    f"level {n} room {i}: extras hot stream count should be 1 "
                    f"(got {blocks[hot_ptr - 0xF000]})")
            else:
                assert hot_ptr == shape, (
                    f"level {n} room {i}: hot stream must stay the shape")
            checks += 1
    print(f"test_band_restage: OK ({checks} rooms, RoomBandColor + derived "
          f"enemy record + shared model shape + PF/extras equivalence "
          f"per room)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
