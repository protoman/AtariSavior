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
         "EnemyDataLo", "EnemyDataHi", "PF0Buf"}
L0 = parse_labels(SRC / "bank0.lst", need0)
missing0 = need0 - L0.keys()
if missing0:
    sys.exit(f"bank0.lst labels missing: {sorted(missing0)}")

levels = []
for n in (1, 2, 3):
    names = {f"LEVEL{n}_RoomShapes", f"LEVEL{n}_RoomCounts",
             f"LEVEL{n}_EnemyDataTable"}
    got = parse_labels(SRC / "bank2.lst", names)
    missing = names - got.keys()
    if missing:
        sys.exit(f"bank2.lst labels missing: {sorted(missing)}")
    levels.append((n, got))


def enter_room(mem: Mem, table: int, room_count: int, room: int) -> None:
    """Stage what LoadLevel stages (C4): the level block base + its room count.
    The RoomPositions / RoomCounts / enemy-record bases are the block's
    +n / +2n / +3n offsets (C2 2026-10-20: 3 B shape-index room records),
    derived by the readers."""
    r = mem.ram
    r[L0["LevelPFDataLo"] - 0x80] = table & 0xFF
    r[L0["LevelPFDataHi"] - 0x80] = table >> 8
    r[L0["LevelRoomN"] - 0x80] = room_count
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
        SRC / "bank2.lst", {f"M{mid}RoomRects" for mid in range(16)})
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
            enter_room(mem, table, len(rooms), i)
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
            # --- C2 (2026-10-20): the shape table routed this room's block ---
            # The block word is gone, so the only thing selecting the block is
            # LEVEL_ShapeTable[shape index]: an async room must land on its OWN
            # per-room block (never the shared model block), a plain room on
            # the shared model block.
            model = room.get("model_id")
            label = f"M{int(model)}RoomRects" if model is not None else None
            if label in model_blocks:
                async_room = bool(room.get("asym_patches")
                                  or room.get("feature_cells"))
                if async_room:
                    assert rects != model_blocks[label], (
                        f"level {n} room {i}: async room loaded the SHARED "
                        f"model block {label} (${rects:04X}) — the shape "
                        "index/table routed it wrong")
                else:
                    assert rects == model_blocks[label], (
                        f"level {n} room {i}: symmetric room loaded "
                        f"${rects:04X}, want the model block {label} "
                        f"${model_blocks[label]:04X} (shape index/table)")
            # C4 (2026-10-20): block = hot stream | PF | meta; the solid
            # rect list is retired, so TilePF0 = block + 1 + 5*hot_count.
            blocks = _CM.BANK2
            nhot = blocks[rects - 0xF000]
            pf0 = rects + 1 + 5 * nhot
            want_pf = bytes(blocks[pf0 - 0xF000:pf0 - 0xF000 + 9])
            got_pf = bytes(mem.ram[L0["PF0Buf"] - 0x80:
                                   L0["PF0Buf"] - 0x80 + 9])
            assert got_pf == want_pf, (
                f"level {n} room {i}: PF cache {got_pf.hex()} != the block's "
                f"PF triple at ${pf0:04X} {want_pf.hex()} (TilePF0 derivation)")
            checks += 1
    print(f"test_band_restage: OK ({checks} rooms, RoomBandColor + derived "
          f"enemy record + shape-table block routing + derived TilePF0 "
          f"per room)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
