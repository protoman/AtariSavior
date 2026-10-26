#!/usr/bin/env python3
"""Power cell (enemy record type 14 = KEY|8): refills the timer, once per level.

Design (2026-10-26, user request "an object that fully recharges the timer"):
  * The cell is object type 14. Every `and #7` consumer folds it to 6 (KEY), so
    CheckEnemyHit sends it to the key arm, which tells the two apart by the
    record (CEH_KeyDisp). Collecting it sets BarLevel = 120, marks the slot dead
    (it vanishes, no life lost, no score) and latches bit (RoomNo & 3) of
    LevelStartRoom b3-0 -- the key uses b7, the start room is a constant, so
    b6-0 are free (LF_B0Tail used to load the byte as the respawn room; it loads
    #0 now).
  * Re-entering the room must NOT bring the cell back (otherwise leaving and
    re-entering is an infinite refill): bank2's EBLER loop pre-marks a taken
    cell dead. Bits reset with LoadLevel (level advance / game over); a normal
    death keeps them, like the key.

Drives the real frozen CheckEnemyHit and EBLER_Loop with a record patched into
the frozen bank2 image (no live data).
Run: /home/iuri/python3/bin/python3 tools/test_power_cell.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import test_cell_map as CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"
CELL = 14
REC = 0xFFD0                      # 3 bytes patched into the frozen bank2 image
                                  # (data only - never executed by the code under test)


def labels(bank, names):
    got = parse_labels(FROZEN / f"bank{bank}.lst", set(names))
    miss = set(names) - got.keys()
    if miss:
        sys.exit(f"frozen bank{bank}.lst labels missing: {sorted(miss)}")
    return got


L0 = labels(0, ["CheckEnemyHit", "EnemyDeadMask", "LevelStartRoom", "BarLevel",
                "RoomNo", "EnemyCount", "EnemyDataLo", "EnemyDataHi",
                "EnemyRamX", "EnemyRamY", "RoomX", "RoomY", "PlayerLives",
                "ScoreTe", "BombSnd"])
L2 = labels(2, ["EBLER_Loop", "EBLER_Done", "EnemyDeadMask", "LevelStartRoom",
                "RoomNo", "EnemyCount", "EnemyDataLo", "EnemyDataHi",
                "EnemyRamX", "EnemyRamY", "EnemyRamD", "FetchPtr", "Temp"])

bank2 = bytearray(CM.BANK2)


def stage(rec_type, x, y):
    bank2[REC - 0xF000:REC - 0xF000 + 3] = bytes([rec_type, x, y])
    CM.BANK2 = bytes(bank2)       # Mem.__getitem__ looks the global up per read


def poke(mem, lab, name, val):
    mem.ram[lab[name] - 0x80] = val & 0xFF


def peek(mem, lab, name):
    return mem.ram[lab[name] - 0x80]


def run(mem, bank, pc, stop, x=0, y=0, steps=3000):
    mem.bank = bank
    mpu = MPU(memory=mem)
    mpu.pc, mpu.a, mpu.x, mpu.y = pc, 0, x, y
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(steps):
        mpu.step()
        if mpu.pc == stop or mpu.pc == RTS_SENTINEL:
            return
    sys.exit(f"never reached ${stop:04X} (pc=${mpu.pc:04X}, bank={mem.bank})")


def base_mem(L):
    mem = CM.Mem()
    poke(mem, L, "EnemyCount", 1)
    poke(mem, L, "EnemyDataLo", REC & 0xFF)
    poke(mem, L, "EnemyDataHi", REC >> 8)
    poke(mem, L, "EnemyRamX", 60)
    poke(mem, L, "EnemyRamY", 60)
    poke(mem, L, "RoomNo", 6)             # 6 & 3 = 2 -> bit 4
    return mem


# --- 1. pickup: CheckEnemyHit on a cell --------------------------------------
stage(CELL, 60, 60)
mem = base_mem(L0)
poke(mem, L0, "RoomX", 60)
poke(mem, L0, "RoomY", 60)
poke(mem, L0, "BarLevel", 37)
poke(mem, L0, "PlayerLives", 3)
poke(mem, L0, "LevelStartRoom", 0)
poke(mem, L0, "EnemyDeadMask", 0)
run(mem, 0, L0["CheckEnemyHit"], RTS_SENTINEL)

assert peek(mem, L0, "BarLevel") == 120, (
    f"cell did not refill the timer: BarLevel={peek(mem, L0, 'BarLevel')}")
assert peek(mem, L0, "EnemyDeadMask") == 1, "cell slot not marked dead"
lsr = peek(mem, L0, "LevelStartRoom")
assert lsr == 0x04, (f"cell must latch bit (RoomNo&3) only: LevelStartRoom="
                     f"${lsr:02X} want $04 (KeyHeld b7 must stay clear)")
assert peek(mem, L0, "PlayerLives") == 3, "cell must not cost a life"
assert peek(mem, L0, "ScoreTe") == 0, "cell must not award score"
assert peek(mem, L0, "BombSnd") > 0, "no pickup blip for the power cell (BombSnd hold)"

# a real key (type 6) still behaves exactly as before
stage(6, 60, 60)
mem = base_mem(L0)
poke(mem, L0, "RoomX", 60)
poke(mem, L0, "RoomY", 60)
poke(mem, L0, "BarLevel", 37)
poke(mem, L0, "LevelStartRoom", 0)
run(mem, 0, L0["CheckEnemyHit"], RTS_SENTINEL)
assert peek(mem, L0, "LevelStartRoom") == 0x80, "key must latch KeyHeld"
assert peek(mem, L0, "BarLevel") == 37, "a key must not touch the timer"
assert peek(mem, L0, "BombSnd") > 0, "no pickup blip for the key (BombSnd hold)"

# --- 2. room entry: a taken cell stays dead ----------------------------------
for taken, want in ((0x04, 1), (0x00, 0), (0x0B, 0)):
    stage(CELL, 60, 60)
    mem = base_mem(L2)
    poke(mem, L2, "LevelStartRoom", taken)
    poke(mem, L2, "EnemyDeadMask", 0)
    mem.ram[L2["FetchPtr"] - 0x80] = REC & 0xFF
    mem.ram[L2["FetchPtr"] + 1 - 0x80] = REC >> 8
    run(mem, 2, L2["EBLER_Loop"], L2["EBLER_Done"])
    got = peek(mem, L2, "EnemyDeadMask")
    assert got == want, (f"EBLER with LevelStartRoom=${taken:02X} (room 6 -> bit "
                         f"$04): EnemyDeadMask=${got:02X} want ${want:02X} - a "
                         "collected cell must not respawn on re-entry")

# an ordinary enemy is never touched by the cell logic
stage(1, 60, 60)
mem = base_mem(L2)
poke(mem, L2, "LevelStartRoom", 0x0F)
poke(mem, L2, "EnemyDeadMask", 0)
mem.ram[L2["FetchPtr"] - 0x80] = REC & 0xFF
mem.ram[L2["FetchPtr"] + 1 - 0x80] = REC >> 8
run(mem, 2, L2["EBLER_Loop"], L2["EBLER_Done"])
assert peek(mem, L2, "EnemyDeadMask") == 0, "a bat was pre-marked dead"

# --- 3. pickups are not targets: laser and blast pass through keys and cells ---
L2b = labels(2, ["LaserTipEnemy", "LaserHitTestBody", "LaserClampDone",
                 "BombEnemyBlastBody", "EnemyDeadMask", "EnemyCount",
                 "EnemyDataLo", "EnemyDataHi", "EnemyRamX", "EnemyRamY",
                 "RoomY", "CollisionX", "PlayerDir", "BombX", "FetchPtr",
                 "RectCount", "RoomNo"])
for rtype in (CELL, 6, 1):
    stage(rtype, 100, 60)
    mem = base_mem(L2b)
    poke(mem, L2b, "EnemyRamX", 100)
    poke(mem, L2b, "EnemyRamY", 60)
    poke(mem, L2b, "RoomY", 60)
    poke(mem, L2b, "CollisionX", 100)       # beam tip on the sprite
    poke(mem, L2b, "PlayerDir", 1)
    poke(mem, L2b, "EnemyDeadMask", 0)
    # LaserTipEnemy runs on to the wall clamp when it finds nothing; stop at
    # the clamp entry (what matters is whether the kill mark was written).
    clamp = labels(2, ["LaserWallClamp"])["LaserWallClamp"]
    run(mem, 2, L2b["LaserTipEnemy"], clamp)
    dead = peek(mem, L2b, "EnemyDeadMask")
    want = 1 if rtype == 1 else 0
    assert dead == want, (f"laser tip vs record type {rtype}: EnemyDeadMask="
                          f"${dead:02X} want ${want:02X} - a key/power cell "
                          "must not be shootable (a bat must)")
    mem = base_mem(L2b)
    poke(mem, L2b, "EnemyRamX", 100)
    poke(mem, L2b, "EnemyRamY", 60)
    poke(mem, L2b, "BombX", 100)
    poke(mem, L2b, "EnemyDeadMask", 0)
    run(mem, 2, L2b["BombEnemyBlastBody"], RTS_SENTINEL)
    dead = peek(mem, L2b, "EnemyDeadMask")
    assert dead == want, (f"bomb blast vs record type {rtype}: EnemyDeadMask="
                          f"${dead:02X} want ${want:02X}")

print("test_power_cell: OK (refill, once per level, key unchanged)")
