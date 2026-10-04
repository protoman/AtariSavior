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

from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402

SRC = ROOT / "src"
ROOMS = SRC / "rooms"

need0 = {"EnterRoom", "RoomBandColor", "LevelPFDataLo", "LevelPFDataHi",
         "LevelEnemyLo", "LevelEnemyHi", "EnemyCount", "RoomNo"}
L0 = parse_labels(SRC / "bank0.lst", need0)
missing0 = need0 - L0.keys()
if missing0:
    sys.exit(f"bank0.lst labels missing: {sorted(missing0)}")

levels = []
for n in (1, 2, 3):
    names = {f"LEVEL{n}_RoomDataTable", f"LEVEL{n}_RoomEnemies"}
    got = parse_labels(SRC / "bank2.lst", names)
    missing = names - got.keys()
    if missing:
        sys.exit(f"bank2.lst labels missing: {sorted(missing)}")
    levels.append((n, got))


def enter_room(mem: Mem, table: int, enemies: int, room: int) -> None:
    r = mem.ram
    r[L0["LevelPFDataLo"] - 0x80] = table & 0xFF
    r[L0["LevelPFDataHi"] - 0x80] = table >> 8
    r[L0["LevelEnemyLo"] - 0x80] = enemies & 0xFF
    r[L0["LevelEnemyHi"] - 0x80] = enemies >> 8
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
    for n, syms in levels:
        data = json.loads((ROOMS / f"level_{n:03d}.json").read_text())
        level = data.get("level", data)
        table = syms[f"LEVEL{n}_RoomDataTable"]
        enemies = syms[f"LEVEL{n}_RoomEnemies"]
        for i, room in enumerate(level["rooms"]):
            mem = Mem()
            enter_room(mem, table, enemies, i)
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
            checks += 1
    print(f"test_band_restage: OK ({checks} rooms, RoomBandColor restaged "
          f"per room)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
