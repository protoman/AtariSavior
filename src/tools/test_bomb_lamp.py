#!/usr/bin/env python3
"""Bomb blast vs LAMP guard (bank2 BombEnemyBlastBody).

The 2026-10-07 fix made the blast pass THROUGH a lamp (LAMP = type 5) instead
of killing it: the old inline loop set the lamp's dead bit, so the lamp
vanished (no dark-room trigger, +50 score for nothing — bugs.md 3). This is the
regression guard that fix never got: every case stages synthetic enemy records
into a private copy of the frozen bank2 image and drives the real body.

Cases:
  1. enemy (slot 0) then lamp (slot 1)  -> the ENEMY dies, the LAMP survives
  2. lamp only                          -> A=0, no dead bit
  3. lamp (slot 0) then enemy (slot 1)  -> the skip must CONTINUE the loop, the
                                           enemy still dies
  4. enemy pre-marked dead, then lamp   -> nothing new dies
  5. enemy out of range (|dcol| >= 2)   -> A=0
  6. two enemies in range               -> exactly ONE kill (first live slot)

Run: /home/iuri/python3/bin/python3 tools/test_bomb_lamp.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import test_cell_map as CM  # noqa: E402
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

SRC = ROOT
FROZEN = SRC / "tests" / "frozen"

NEED = {"EnemyBitTable", "EnemyOffTable", "EnemyDataLo", "EnemyDataHi",
        "EnemyRamX", "EnemyCount", "EnemyDeadMask", "EnemyIndex", "BombX",
        "CollisionCellX"}
L0 = parse_labels(FROZEN / "bank0.lst", NEED)
L2 = parse_labels(FROZEN / "bank2.lst",
                  NEED | {"BombEnemyBlastBody"})
# C7: the shape blocks live in bank3, so the scratch address is a bank3 label
# (same address space; the private bank2 copy is only the staging buffer).
L3 = parse_labels(FROZEN / "bank3.lst", {"M5Shape"})
missing = (NEED | {"BombEnemyBlastBody"}) - set(L0) - set(L2)
if missing:
    sys.exit(f"labels missing: {sorted(missing)}")

# test_cell_map exposes the banks as immutable bytes: take a mutable copy for
# this process so the synthetic records can be staged (never the live ROM).
CM.BANK2 = bytearray(CM.BANK2)

Z = {k: v & 0x7F for k, v in L2.items() if 0x80 <= v <= 0xFF}
BODY = L2["BombEnemyBlastBody"]
SCRATCH = L3["M5Shape"]      # private bank2 copy holds the staged records

LAMP = 5
ENEMY = 1
BOMB_X = 40                      # screen px -> col 10


def run(records, ram_x, dead_mask=0, bomb_x=BOMB_X):
    """Drive BombEnemyBlastBody; returns (A, EnemyDeadMask).

    records = [(type, x), ...] in slot order, staged at SCRATCH in the private
    frozen bank2 image (restored afterwards, so runs stay independent)."""
    off = SCRATCH - 0xF000
    size = 3 * len(records)
    saved = bytes(CM.BANK2[off:off + size])
    for i, (t, x) in enumerate(records):
        CM.BANK2[off + 3 * i:off + 3 * i + 3] = bytes((t, x, 0))
    try:
        mem = Mem()                   # frozen banks; bank=2 for the body
        mem.bank = 2
        r = mem.ram
        r[Z["EnemyDataLo"]] = SCRATCH & 0xFF
        r[Z["EnemyDataHi"]] = SCRATCH >> 8
        r[Z["EnemyCount"]] = len(records)
        r[Z["EnemyDeadMask"]] = dead_mask
        r[Z["EnemyIndex"]] = 0
        r[Z["BombX"]] = bomb_x
        for i, x in enumerate(ram_x):
            r[Z["EnemyRamX"] + i] = x
        mpu = MPU(memory=mem)
        mpu.pc = BODY
        mpu.a = mpu.x = mpu.y = 0
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(4000):
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                return mpu.a, r[Z["EnemyDeadMask"]]
        sys.exit(f"BombEnemyBlastBody never returned (pc=${mpu.pc:04X})")
    finally:
        CM.BANK2[off:off + size] = saved


def main() -> int:
    b0, b1 = 1 << 0, 1 << 1

    a, dm = run([(ENEMY, BOMB_X), (LAMP, BOMB_X)], [BOMB_X, BOMB_X])
    assert (a, dm) == (1, b0), (
        f"enemy+lamp: A={a} deadmask=${dm:02X}, want (1, ${b0:02X}) — the "
        f"lamp must survive")

    a, dm = run([(LAMP, BOMB_X)], [BOMB_X])
    assert (a, dm) == (0, 0), (
        f"lamp only: A={a} deadmask=${dm:02X} — the blast must pass through")

    a, dm = run([(LAMP, BOMB_X), (ENEMY, BOMB_X)], [BOMB_X, BOMB_X])
    assert (a, dm) == (1, b1), (
        f"lamp+enemy: A={a} deadmask=${dm:02X}, want (1, ${b1:02X}) — the "
        f"lamp skip must continue the loop")

    a, dm = run([(ENEMY, BOMB_X), (LAMP, BOMB_X)], [BOMB_X, BOMB_X],
                dead_mask=b0)
    assert (a, dm) == (0, b0), (
        f"dead enemy + lamp: A={a} deadmask=${dm:02X}, want (0, ${b0:02X})")

    a, dm = run([(ENEMY, BOMB_X + 12)], [BOMB_X + 12])
    assert (a, dm) == (0, 0), (
        f"far enemy: A={a} deadmask=${dm:02X} — |dcol| >= 2 must not kill")

    a, dm = run([(ENEMY, BOMB_X), (ENEMY, BOMB_X)], [BOMB_X, BOMB_X])
    assert (a, dm) == (1, b0), (
        f"two enemies: A={a} deadmask=${dm:02X} — one kill per blast, first "
        f"live slot only")

    print("test_bomb_lamp: OK (blast kills enemies, passes through lamps "
          "(type 5), one kill per blast, range gate holds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
