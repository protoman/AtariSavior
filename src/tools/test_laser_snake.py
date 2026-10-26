#!/usr/bin/env python3
"""Laser vs a snake drawn over its wall (user report 2026-10-20).

Symptom: the snake lives inside its wall by design (it retreats into it), so
its sprite is drawn over a SOLID cell. The contact missile tested the tip CELL
for a wall before any enemy, so a shot that visibly crossed the snake was
consumed by the wall and nothing died.

Fix (`bank2.LaserTipEnemy`): before the wall clamp, award a hit to an enemy
whose SPRITE COVERS THE TIP PIXEL (eX-7 <= tip <= eX, i.e. eX in
[tip, tip+7]). An enemy behind the wall cannot match (the tip px sits inside
the solid cell and the next sprite starts past it), so no shooting through
walls.

Cases (py65, frozen banks, direct routine entry — no boot):
  A  solid tip cell + snake covering the tip          -> A=$50, dead bit 0
  B  solid tip cell + enemy 8 px right of the tip     -> A=2 wall, alive
  C  left-facing; tip = A-7, snake covering it        -> A=$50
  D  air tip, enemy overlapping the BEAM body from
     the left edge (classic body-box kill)            -> A=$50 (body loop)

Run: /home/iuri/python3/bin/python3 tools/test_laser_snake.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

import test_cell_map as _CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402

SRC = ROOT
FROZEN = SRC / "tests" / "frozen"

# Frozen ROM image + labels (AGENTS test-data rule). Mutate the image copy so
# the staged enemy record can be authored in place.
for _i in range(8):
    setattr(_CM, f"BANK{_i}", bytearray((FROZEN / f"bank{_i}.bin").read_bytes()))
Mem = _CM.Mem
BANKS = {i: getattr(_CM, f"BANK{i}") for i in range(4)}

L2 = parse_labels(FROZEN / "bank2.lst", {
    "LaserHitTestBody", "LevelPFDataLo", "LevelPFDataHi", "LevelRoomN",
    "EnemyDataLo", "EnemyDataHi", "EnemyRamX", "EnemyRamY", "EnemyDeadMask",
    "EnemyCount", "RoomY", "PlayerDir", "CollisionX", "RoomMetaA", "RoomMetaB",
    "LEVEL1_EnemyDataTable", "ReturnPad"})
L0 = parse_labels(FROZEN / "bank0.lst", {"PF0Buf", "RoomY", "PlayerDir",
                                         "CollisionX", "Temp"})
for need, got, where in (({"LaserHitTestBody", "LevelPFDataLo", "LevelPFDataHi",
                           "EnemyDataLo", "EnemyDataHi", "EnemyRamX",
                           "EnemyRamY", "EnemyDeadMask", "EnemyCount",
                           "RoomY", "PlayerDir", "CollisionX", "RoomMetaA",
                           "RoomMetaB", "LEVEL1_EnemyDataTable"}, L2,
                          "bank2.lst"),
                         ({"PF0Buf"}, L0, "bank0.lst")):
    lack = need - set(got)
    if lack:
        sys.exit(f"{where} missing labels: {sorted(lack)}")

PF0_BUF = L0["PF0Buf"]
SNAKE = 2
LAMP = 5
D = lambda name: L2.get(name) or L0.get(name)


def _zp(mem: Mem, name: str, value: int) -> None:
    mem.ram[D(name) - 0x80] = value & 0xFF


def _zp_get(mem: Mem, name: str) -> int:
    return mem.ram[D(name) - 0x80]


def run_case(enemy_x: int, enemy_y: int, room_y: int, tip_arg: int,
             player_dir: int, stub_solid: bool, enemy_type: int = SNAKE):
    """Drive bank2's LaserHitTestBody; return (A result, dead mask)."""
    mem = Mem()
    # Enemy record: overwrite record 0 of level 1's table in the image copy
    # (2026-10-21: 3 B — type|dir b7, x, y; dir unused here).
    rec = L2["LEVEL1_EnemyDataTable"] - 0xF000
    BANKS[2][rec + 0] = enemy_type
    BANKS[2][rec + 1] = enemy_x & 0xFF
    BANKS[2][rec + 2] = enemy_y & 0xFF

    _zp(mem, "EnemyDataLo", L2["LEVEL1_EnemyDataTable"] & 0xFF)
    _zp(mem, "EnemyDataHi", L2["LEVEL1_EnemyDataTable"] >> 8)
    _zp(mem, "EnemyCount", 1)
    _zp(mem, "EnemyDeadMask", 0)
    _zp(mem, "EnemyRamX", enemy_x)
    _zp(mem, "EnemyRamY", enemy_y)
    _zp(mem, "RoomY", room_y)
    _zp(mem, "PlayerDir", player_dir)
    _zp(mem, "CollisionX", tip_arg)
    _zp(mem, "RoomMetaA", 0)                    # no M1 strip / no patches
    _zp(mem, "RoomMetaB", 0)
    mem.ram[PF0_BUF - 0x80:PF0_BUF - 0x80 + 9] = (
        b"\xff" * 9 if stub_solid else b"\x00" * 9)

    mem.bank = 2
    mpu = MPU(memory=mem)
    mpu.pc = L2["LaserHitTestBody"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(4000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return mpu.a, _zp_get(mem, "EnemyDeadMask")
    sys.exit(f"LaserHitTestBody never returned (pc=${mpu.pc:04X}, "
             f"bank={mem.bank})")


def main() -> int:
    # A: right-facing, tip = CollisionX = 40, snake sprite [33, 40] covers 40.
    a, dead = run_case(40, 60, 60, 40, 0, stub_solid=True)
    assert a == 0x50 and dead & 0x01, (
        f"A: snake on a solid tip cell not killed (A=${a:02X}, "
        f"dead=${dead:02X}) — the wall preempted the tip enemy")

    # B: same solid tip, enemy 8 px right of it (sprite starts past the tip).
    a, dead = run_case(48, 60, 60, 40, 0, stub_solid=True)
    assert a == 0x02 and not dead & 0x01, (
        f"B: enemy behind the wall died through it (A=${a:02X}, "
        f"dead=${dead:02X})")

    # C: left-facing tip = CollisionX-7 = 33, snake sprite [26, 33] covers 33.
    a, dead = run_case(33, 60, 60, 40, 1, stub_solid=True)
    assert a == 0x50 and dead & 0x01, (
        f"C: left-facing tip enemy not killed (A=${a:02X}, dead=${dead:02X})")

    # D: air tip; enemy overlaps the beam BODY only (sprite [26, 33] vs beam
    #    [33, 40]): the tip pass must skip it and the body loop must kill.
    a, dead = run_case(33, 60, 60, 40, 0, stub_solid=False)
    assert a == 0x50 and dead & 0x01, (
        f"D: body-overlap kill regressed (A=${a:02X}, dead=${dead:02X})")

    # E: air tip, enemy fully left of the beam -> nothing.
    a, dead = run_case(24, 60, 60, 40, 0, stub_solid=False)
    assert a == 0 and not dead & 0x01, (
        f"E: out-of-box enemy killed (A=${a:02X}, dead=${dead:02X})")

    print("test_laser_snake: OK (5 cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
