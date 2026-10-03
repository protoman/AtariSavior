#!/usr/bin/env python3
"""Room-dark 8-bit mask check (assert-based, no framework).

Drives bank1 IsRoomDark/SetRoomDark headless (py65) and asserts the
split mask: rooms 0-3 = EnemyRamD bits 4-7, rooms 4-7 = LaserState bits
5-2 (LaserState b7/b6/b1-0 preserved), rooms 8+ = always lit and
SetRoomDark no-op (never crashes). Static asserts cover the kernel-side
preservers (LaserInput/DropArm keep dark bits, LoadLevel clears them).

Run: /home/iuri/python3/bin/python3 tools/test_room_dark.py
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
BANK1 = (SRC / "bank1.bin").read_bytes()
KERNEL = (SRC / "kernel.asm").read_text(encoding="utf-8")
BANK1_SRC = (SRC / "bank1.asm").read_text(encoding="utf-8")

labels = {}
for line in (SRC / "bank1.lst").read_text(errors="replace").splitlines():
    m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                 r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$", line)
    if m:
        labels.setdefault(m.group(2), int(m.group(1), 16))
for need in ("IsRoomDark", "SetRoomDark", "ReturnPad"):
    if need not in labels:
        sys.exit(f"label {need} missing from bank1.lst")
ADDR = {k: labels[k] for k in ("IsRoomDark", "SetRoomDark", "ReturnPad")}

ROOM_NO = 0x98
ENEMY_RAM_D = 0xC1
LASER_STATE = 0xC0


class Mem:
    def __init__(self):
        self.ram = bytearray(128)

    def __getitem__(self, a):
        a &= 0xFFFF
        if 0xF000 <= a <= 0xFFFF:
            return BANK1[a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v & 0xFF
        # everything else (incl. $1FF6 bank hotspots) ignored


from py65.devices.mpu6502 import MPU  # noqa: E402


def call(entry: int, room_no: int, enemy_ram_d: int, laser_state: int):
    """Run a bank1 routine; return (A, flags, EnemyRamD, LaserState)."""
    mem = Mem()
    mem.ram[ROOM_NO - 0x80] = room_no
    mem.ram[ENEMY_RAM_D - 0x80] = enemy_ram_d
    mem.ram[LASER_STATE - 0x80] = laser_state
    mpu = MPU(memory=mem)
    mpu.pc = entry
    mpu.sp = 0xFF                      # ReturnPad's rts never runs (we stop first)
    for _ in range(64):
        mpu.step()
        if mpu.pc == ADDR["ReturnPad"]:   # sta $1FF6/rts not yet executed
            return (mpu.a, mpu.p,
                    mem.ram[ENEMY_RAM_D - 0x80], mem.ram[LASER_STATE - 0x80])
    sys.exit(f"routine ${entry:04X} never returned (pc=${mpu.pc:04X})")


Z_FLAG = 0x02


def is_dark(room_no, d, ls):
    a, p, _, _ = call(ADDR["IsRoomDark"], room_no, d, ls)
    return not (p & Z_FLAG)


def set_dark(room_no, d, ls):
    _, _, d2, ls2 = call(ADDR["SetRoomDark"], room_no, d, ls)
    return d2, ls2


def main() -> int:
    # --- rooms 0-3: EnemyRamD bits 4-7 -----------------------------------
    assert not is_dark(0, 0x00, 0x00), "room0 lit when mask clear"
    d, ls = set_dark(0, 0x00, 0x00)
    assert (d, ls) == (0x10, 0x00), f"room0 dark bit: d={d:02X} ls={ls:02X}"
    assert is_dark(0, d, ls), "room0 dark after SetRoomDark"
    _, ls = set_dark(3, 0x00, 0x00)
    assert ls == 0x00, "rooms 0-3 must not touch LaserState"
    assert set_dark(3, 0x00, 0x00)[0] == 0x80, "room3 -> EnemyRamD b7"

    # --- rooms 4-7: LaserState bits 5-2, laser bits preserved ------------
    d, ls = set_dark(4, 0x00, 0xC1)          # b7/b6/b1-0 = laser state
    assert (d, ls) == (0x00, 0xC5), f"room4: d={d:02X} ls={ls:02X} (want $C5)"
    assert is_dark(4, d, ls), "room4 dark after SetRoomDark"
    d, ls = set_dark(7, 0x00, 0x01)          # b1 = sweep phase
    assert (d, ls) == (0x00, 0x21), f"room7: ls={ls:02X} (want $21)"
    assert is_dark(7, d, ls), "room7 dark after SetRoomDark"
    assert set_dark(4, 0x10, 0x00)[0] == 0x10, "room4 must not touch EnemyRamD"

    # --- rooms 8+: always lit, SetRoomDark no-op, no crash ---------------
    for room in (8, 9, 15, 200):
        assert not is_dark(room, 0xFF, 0xFF), f"room{room} must stay lit"
        d, ls = set_dark(room, 0x37, 0x3D)
        assert (d, ls) == (0x37, 0x3D), f"room{room} SetRoomDark must be a no-op"

    # --- kernel-side preservers (static) ---------------------------------
    assert KERNEL.count("and #LASER_DARK") >= 2, \
        "LaserInput + DropArm must both mask with LASER_DARK"
    assert re.search(r"and #%11000111\s*;.*rooms 4-7", KERNEL), \
        "LoadLevel must clear LaserState dark bits"
    assert BANK1_SRC.count("cmp #8") >= 2, \
        "IsRoomDark/SetRoomDark must guard rooms 8+"
    print("room-dark 8-bit mask: OK "
          "(0-3=EnemyRamD, 4-7=LaserState b5-2, 8+ always lit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
