#!/usr/bin/env python3
"""Up to three miners per level (2026-10-26): every one must be rescued.

Model (user request "up to 3 miners to rescue ... the stage would only finish
once all were rescued"):
  * The level's own miner (LevelDataTable +0/+1, drawn by the miner slot) is the
    PRIMARY. Extra miners are enemy records of type 15 (MINER2); every `and #7`
    consumer folds 15 to 7 (RAFT), CheckEnemyHit sends 14/15 to CEH_KeyDisp.
  * LevelStartRoom b6-4 = miners still to rescue: b4 = the primary, b5/b6 = the
    extras, indexed by RoomNo & 1 (the converter keeps the two extras in rooms
    of different parity). LoadLevelB2 seeds it from the level byte +0:
    `$10 | (byte & $60)`; the room number is `byte & $9F`.
  * A rescue clears its bit. While others remain: the miner vanishes, +500 and a
    blip. When the LAST one is taken the usual tally runs (TallyTramp).
  * Re-entering a room keeps a rescued extra gone (bank2 EBLCellCheck).
  * Lasers and bombs pass through miners (type 15 folds to RAFT: skipped).

Drives the real frozen routines (no live data).
Run: /home/iuri/python3/bin/python3 tools/test_miners.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import test_cell_map as CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "src" / "tests" / "frozen"
MINER2 = 15
REC = 0xFFD0


def labels(bank, names):
    got = parse_labels(FROZEN / f"bank{bank}.lst", set(names))
    miss = set(names) - got.keys()
    if miss:
        sys.exit(f"frozen bank{bank}.lst labels missing: {sorted(miss)}")
    return got


L0 = labels(0, ["CheckMinerPickup", "CheckEnemyHit", "LevelMinerRoom", "MinerX",
                "MinerY", "RoomX", "RoomY", "RoomNo", "ScoreTe", "ScoreHu",
                "ScoreTh", "DropTarget", "EnemyDeadMask", "LevelStartRoom",
                "EnemyCount", "EnemyDataLo", "EnemyDataHi", "EnemyRamX",
                "EnemyRamY", "PlayerLives", "BarLevel", "BombSnd"])
L2 = labels(2, ["EBLER_Loop", "EBLER_Done", "EnemyDeadMask", "LevelStartRoom",
                "RoomNo", "EnemyCount", "EnemyDataLo", "EnemyDataHi",
                "EnemyRamX", "EnemyRamY", "EnemyRamD", "FetchPtr", "Temp",
                "LoadLevelB2", "LF_TailSwap", "LevelDataTable", "Level",
                "LevelMinerRoom", "DropTarget", "LaserTipEnemy",
                "LaserWallClamp", "BombEnemyBlastBody", "BombX", "RoomY",
                "CollisionX", "PlayerDir", "RectCount"])

bank2 = bytearray(CM.BANK2)


def stage(rec_type, x, y):
    bank2[REC - 0xF000:REC - 0xF000 + 3] = bytes([rec_type, x, y])
    CM.BANK2 = bytes(bank2)


def poke(mem, lab, name, val):
    mem.ram[lab[name] - 0x80] = val & 0xFF


def peek(mem, lab, name):
    return mem.ram[lab[name] - 0x80]


def run(mem, bank, pc, stop, x=0, y=0, steps=20000):
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


def score(mem):
    return (peek(mem, L0, "ScoreTh") * 1000 + peek(mem, L0, "ScoreHu") * 100
            + ((peek(mem, L0, "ScoreTe") >> 4) * 10
               + (peek(mem, L0, "ScoreTe") & 15)))


# --- 1. level load seeds the remaining-miners bits ---------------------------
entry = L2["LevelDataTable"] - 0xF000
for byte, want_lsr, want_room in ((0x01, 0x10, 0x01), (0x41, 0x50, 0x01),
                                  (0x62, 0x70, 0x02), (0x82, 0x90 & 0x70 | 0x10, 0x82)):
    saved = bank2[entry]
    bank2[entry] = byte
    CM.BANK2 = bytes(bank2)
    mem = CM.Mem()
    poke(mem, L2, "Level", 0)
    poke(mem, L2, "DropTarget", 0)
    run(mem, 2, L2["LoadLevelB2"], L2["LF_TailSwap"])
    bank2[entry] = saved
    CM.BANK2 = bytes(bank2)
    lsr = peek(mem, L2, "LevelStartRoom")
    assert lsr == want_lsr, (f"level byte ${byte:02X}: LevelStartRoom=${lsr:02X} "
                             f"want ${want_lsr:02X} (miners-left bits b6-4)")
    room = peek(mem, L2, "LevelMinerRoom")
    assert room == want_room, (f"level byte ${byte:02X}: LevelMinerRoom="
                               f"${room:02X} want ${want_room:02X} (the extras "
                               "mask must not leak into the room number)")


# --- 2. the primary miner ----------------------------------------------------
def primary(lsr):
    mem = CM.Mem()
    poke(mem, L0, "LevelMinerRoom", 0x03)
    poke(mem, L0, "RoomNo", 3)
    poke(mem, L0, "MinerX", 60)
    poke(mem, L0, "MinerY", 96)
    poke(mem, L0, "RoomX", 60)
    poke(mem, L0, "RoomY", 96)
    poke(mem, L0, "LevelStartRoom", lsr)
    poke(mem, L0, "DropTarget", 0)
    run(mem, 0, L0["CheckMinerPickup"], RTS_SENTINEL)
    return mem


mem = primary(0x70)                    # primary + both extras outstanding
assert peek(mem, L0, "DropTarget") == 0, \
    "primary miner started the tally while two extras were still to rescue"
assert peek(mem, L0, "LevelStartRoom") == 0x60, (
    f"primary rescue must clear b4 only: LevelStartRoom="
    f"${peek(mem, L0, 'LevelStartRoom'):02X} want $60")
assert peek(mem, L0, "LevelMinerRoom") == 0xFF, \
    "a rescued primary must vanish (LevelMinerRoom = ROOM_NONE)"
assert score(mem) == 500, f"rescue reward: score {score(mem)} want 500"
assert peek(mem, L0, "BombSnd") > 0, "rescue blip not started"

mem = primary(0x10)                    # the primary is the last one
assert peek(mem, L0, "DropTarget") == 0xFE, \
    "rescuing the last miner must arm the tally (DropTarget $FE)"
assert peek(mem, L0, "LevelMinerRoom") == 0x03, \
    "the tally frame still draws the primary: LevelMinerRoom must stay"


# --- 3. an extra miner (record type 15) --------------------------------------
def extra(lsr, room=6):
    stage(MINER2, 60, 99)
    mem = CM.Mem()
    poke(mem, L0, "EnemyCount", 1)
    poke(mem, L0, "EnemyDataLo", REC & 0xFF)
    poke(mem, L0, "EnemyDataHi", REC >> 8)
    poke(mem, L0, "EnemyRamX", 60)
    poke(mem, L0, "EnemyRamY", 99)
    poke(mem, L0, "RoomNo", room)
    poke(mem, L0, "RoomX", 60)
    poke(mem, L0, "RoomY", 96)
    poke(mem, L0, "LevelMinerRoom", 0xFF)
    poke(mem, L0, "LevelStartRoom", lsr)
    poke(mem, L0, "DropTarget", 0)
    poke(mem, L0, "PlayerLives", 3)
    run(mem, 0, L0["CheckEnemyHit"], RTS_SENTINEL)
    return mem


mem = extra(0x70)                      # room 6 -> parity 0 -> bit $20
assert peek(mem, L0, "LevelStartRoom") == 0x50, (
    f"extra miner in room 6 must clear $20: LevelStartRoom="
    f"${peek(mem, L0, 'LevelStartRoom'):02X} want $50")
assert peek(mem, L0, "EnemyDeadMask") == 1, "the rescued extra must vanish"
assert peek(mem, L0, "PlayerLives") == 3, "touching a miner costs no life"
assert peek(mem, L0, "DropTarget") == 0, "tally armed with miners left"
assert score(mem) == 500, f"extra rescue reward: score {score(mem)} want 500"

mem = extra(0x40, room=7)              # room 7 -> parity 1 -> bit $40, last
assert peek(mem, L0, "LevelStartRoom") == 0x00
assert peek(mem, L0, "DropTarget") == 0xFE, \
    "the last extra miner must arm the tally"


# --- 4. room entry keeps a rescued extra gone --------------------------------
def entry_dead(lsr, room=6):
    stage(MINER2, 60, 99)
    mem = CM.Mem()
    poke(mem, L2, "EnemyCount", 1)
    poke(mem, L2, "EnemyDataLo", REC & 0xFF)
    poke(mem, L2, "EnemyDataHi", REC >> 8)
    poke(mem, L2, "RoomNo", room)
    poke(mem, L2, "LevelStartRoom", lsr)
    poke(mem, L2, "EnemyDeadMask", 0)
    mem.ram[L2["FetchPtr"] - 0x80] = REC & 0xFF
    mem.ram[L2["FetchPtr"] + 1 - 0x80] = REC >> 8
    run(mem, 2, L2["EBLER_Loop"], L2["EBLER_Done"])
    return peek(mem, L2, "EnemyDeadMask")


assert entry_dead(0x20) == 0, "an outstanding extra must be alive on entry"
assert entry_dead(0x00) == 1, "a rescued extra (bit clear) must stay dead"
assert entry_dead(0x40) == 1, "the other parity's bit must not keep it alive"
assert entry_dead(0x40, room=7) == 0, "room 7 reads bit $40"

# --- 5. lasers and bombs pass through miners ---------------------------------
stage(MINER2, 100, 60)
mem = CM.Mem()
poke(mem, L2, "EnemyCount", 1)
poke(mem, L2, "EnemyDataLo", REC & 0xFF)
poke(mem, L2, "EnemyDataHi", REC >> 8)
poke(mem, L2, "EnemyRamX", 100)
poke(mem, L2, "EnemyRamY", 60)
poke(mem, L2, "RoomY", 60)
poke(mem, L2, "CollisionX", 100)
poke(mem, L2, "PlayerDir", 1)
mem.ram[L2["FetchPtr"] - 0x80] = REC & 0xFF
mem.ram[L2["FetchPtr"] + 1 - 0x80] = REC >> 8
run(mem, 2, L2["LaserTipEnemy"], L2["LaserWallClamp"])
assert peek(mem, L2, "EnemyDeadMask") == 0, "the laser killed an extra miner"
mem = CM.Mem()
poke(mem, L2, "EnemyCount", 1)
poke(mem, L2, "EnemyDataLo", REC & 0xFF)
poke(mem, L2, "EnemyDataHi", REC >> 8)
poke(mem, L2, "EnemyRamX", 100)
poke(mem, L2, "EnemyRamY", 60)
poke(mem, L2, "BombX", 100)
run(mem, 2, L2["BombEnemyBlastBody"], RTS_SENTINEL)
assert peek(mem, L2, "EnemyDeadMask") == 0, "a bomb killed an extra miner"

print("test_miners: OK (seed, primary/extra rescue, last-one tally, re-entry, "
      "laser/bomb immunity)")
