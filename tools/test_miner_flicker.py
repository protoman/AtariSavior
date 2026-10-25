#!/usr/bin/env python3
"""A dead enemy must not make the surviving object flicker.

User report 2026-10-25: in a room with an enemy and the miner the enemy
flickers (they share GRP1, one slot each), but killing the enemy left the
MINER flickering as well - the miner appeared only every 2nd frame, although
alone it should be drawn every frame.

Root cause: SelectActiveObject rotates over EnemyCount (+1 for the miner)
slots and a dead enemy's slot drew NOTHING (.SOEnemySkip -> ObjBase = $FF)
instead of handing the slot to the surviving object. The same hole made a
room with two enemies flicker its survivor, and a taken KEY (skipped the same
way) wasted a slot.

Drives the real frozen SelectActiveObject for 8 consecutive frames (the
rotation counter lives in FlickerFrame) and asserts which object is staged:
  A  miner + dead enemy          -> miner EVERY frame
  B  two enemies, one dead       -> the live one EVERY frame
  C  miner + live enemy (control)-> both appear, alternating
  D  everything dead, no miner   -> nothing drawn (and no hang)

Run: /home/iuri/python3/bin/python3 tools/test_miner_flicker.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "src" / "tests" / "frozen"
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402

BANKS = [bytearray(open(FROZEN / f"bank{i}.bin", "rb").read()) for i in range(8)]
NAMES = {"SelectActiveObject", "DropTarget", "FlickerFrame", "BombPacked",
         "EnemyCount", "LevelMinerRoom", "RoomNo", "EnemyDeadMask", "ObjBase",
         "MinerX", "MinerY", "EnemyRamX", "EnemyRamY", "EnemyDataLo",
         "EnemyDataHi", "EnemyIndex", "LevelStartRoom"}
L0 = parse_labels(FROZEN / "bank0.lst", NAMES)
miss = NAMES - L0.keys()
if miss:
    sys.exit(f"labels missing: {sorted(miss)}")


import re  # noqa: E402

# OBJ_MINER is a decimal EQU the listing does not echo as an address.
_m = re.search(r"^OBJ_MINER\s*=\s*(\d+)", (ROOT / "src" / "kernel.asm").read_text(),
               re.M)
OBJ_MINER = int(_m.group(1))


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.bank = 0

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        if 0x1FF4 <= a <= 0x1FFB:
            self.bank = a - 0x1FF4
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v & 0xFF


def zp(name):
    return L0[name] - 0x80


def run(enemies, dead, miner, frames=8):
    """-> list of ObjBase per frame. enemies = count; dead = mask b0-2."""
    mem = Mem()
    r = mem.ram
    r[zp("EnemyCount")] = enemies
    r[zp("EnemyDeadMask")] = dead
    r[zp("RoomNo")] = 2
    r[zp("LevelMinerRoom")] = 2 if miner else 5
    r[zp("MinerX")], r[zp("MinerY")] = 60, 70
    for i in range(3):
        r[zp("EnemyRamX") + i] = 40 + 10 * i
        r[zp("EnemyRamY") + i] = 50
    # enemy records live in the (frozen) bank2 ROM image: any readable bytes
    r[zp("EnemyDataLo")], r[zp("EnemyDataHi")] = 0x00, 0xF1
    r[zp("LevelStartRoom")] = 0
    out = []
    for _ in range(frames):
        mem.bank = 0
        mpu = MPU(memory=mem)
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        mpu.pc = L0["SelectActiveObject"]
        for n in range(20000):
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                break
        else:
            sys.exit(f"SelectActiveObject hung (enemies={enemies} dead={dead:#x})")
        out.append(r[zp("ObjBase")])
    return out


def main():
    M = OBJ_MINER
    fails = []

    a = run(1, 0b001, miner=True)
    if a != [M] * 8:
        fails.append(f"A miner + dead enemy flickers: ObjBase per frame {a} "
                     f"(want OBJ_MINER={M} every frame)")

    b = run(2, 0b001, miner=False)
    if 0xFF in b:
        fails.append(f"B two enemies, one dead: survivor drawn only part of "
                     f"the time: {b}")
    b2 = run(2, 0b010, miner=False)
    if 0xFF in b2:
        fails.append(f"B' two enemies, 2nd dead: survivor flickers: {b2}")

    c = run(1, 0, miner=True)
    if M not in c or all(x == M for x in c):
        fails.append(f"C control: live enemy + miner must alternate: {c}")

    d = run(2, 0b011, miner=False)
    if set(d) != {0xFF}:
        fails.append(f"D all dead, no miner: nothing may be drawn: {d}")

    if fails:
        print("FAIL:")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("test_miner_flicker: OK (dead enemy hands its slot to the survivor)")


if __name__ == "__main__":
    main()
