#!/usr/bin/env python3
"""Room-dark 8-bit mask check (assert-based, no framework).

Drives bank1 IsRoomDark/SetRoomDark headless (py65) and asserts the
split mask: rooms 0-3 = EnemyRamD bits 4-7, rooms 4-7 = LaserState bits
5-2 (LaserState b7/b6/b1-0 preserved), rooms 8+ = always lit and
SetRoomDark no-op (never crashes). Static asserts cover the kernel-side
preservers (LaserInput/DropArm keep dark bits, LoadLevel clears them).
Also drives bank2 BuildColupF (BCFDarkRun tail): ColupfBuf must go black
/ fuse-grey for a dark room 4 (UI room 5 — the stale 4-room inline that
left the level-003 lamp looking dead, 2026-10-03).

Run: /home/iuri/python3/bin/python3 tools/test_room_dark.py
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cell_map import parse_labels, FROZEN, Mem as BankMem  # noqa: E402
BANK1 = (SRC / "bank1.bin").read_bytes()
BANK2 = (SRC / "bank2.bin").read_bytes()
BANK3_BLK = (SRC / "bank3.bin").read_bytes()  # C7: BuildColupF in bank3
KERNEL = (SRC / "kernel.asm").read_text(encoding="utf-8")
BANK1_SRC = (SRC / "bank1.asm").read_text(encoding="utf-8")
BANK2_SRC = (SRC / "bank2.asm").read_text(encoding="utf-8")

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

labels2 = {}
for line in (SRC / "bank3.lst").read_text(errors="replace").splitlines():
    m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                 r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$", line)
    if m:
        labels2.setdefault(m.group(2), int(m.group(1), 16))
for need in ("BuildColupF", "ReturnPad"):
    if need not in labels2:
        sys.exit(f"label {need} missing from bank3.lst")
ADDR2 = {k: labels2[k] for k in ("BuildColupF", "ReturnPad")}

ROOM_NO = 0x98
ENEMY_RAM_D = 0xC1
LASER_STATE = 0xC0
# BuildColupF / BCFDarkRun inputs (addr & $7F)
COLUPF_BUF = 0xE7
WALL1, WALL2 = 0xAA, 0xAB
TICK = 0xAD
BOMB_PACKED = 0xB5
RECTS_LO, RECTS_HI = 0x90, 0x91
STRIPE1, STRIPE2 = 0x1C, 0x44


class Mem:
    def __init__(self, rom=BANK1):
        self.rom = rom
        self.ram = bytearray(128)

    def __getitem__(self, a):
        a &= 0xFFFF
        if 0xF000 <= a <= 0xFFFF:
            return self.rom[a - 0xF000]
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


def run_bcf(room_no, d, ls, bomb=0):
    """Run bank3 BuildColupF; return ColupfBuf rows 0-2.

    Rect stream at $00A0: solid count 0, hot count 0 → the hot walk
    beq's straight to the dark check (no ROM stream needed).
    """
    mem = Mem(rom=BANK3_BLK)
    r = mem.ram
    r[ROOM_NO - 0x80] = room_no
    r[ENEMY_RAM_D - 0x80] = d
    r[LASER_STATE - 0x80] = ls
    r[BOMB_PACKED - 0x80] = bomb
    r[WALL1 - 0x80] = STRIPE1
    r[WALL2 - 0x80] = STRIPE2
    r[TICK - 0x80] = 0
    r[RECTS_LO - 0x80] = 0xA0          # stream lo in ZP ($00A0)
    r[RECTS_HI - 0x80] = 0x00          # stream hi — RAM, not ROM
    r[0xA0 - 0x80] = 0                 # solid count
    r[0xA1 - 0x80] = 0                 # hot count → skip walk
    mpu = MPU(memory=mem)
    mpu.pc = ADDR2["BuildColupF"]
    mpu.sp = 0xFF
    for _ in range(192):              # P2b StageBandTab grew ~14 instrs
        mpu.step()
        if mpu.pc == ADDR2["ReturnPad"]:
            return [r[COLUPF_BUF - 0x80 + i] for i in range(3)]
    sys.exit(f"BuildColupF never returned (pc=${mpu.pc:04X})")


def check_select_object_dark() -> None:
    """A1: SelectActiveObject (bank0) must color a dark-room enemy grey through
    the REAL cross-bank dark path — bank0 body -> CallPad_IsRoomDark ($FC0E
    `sta $1FF7`) -> bank1 IsRoomDark -> ReturnPad -> bank0.

    C1 (2026-10-20) had moved the body to bank2, where the split was
    re-implemented inline; A1 moved it back, so this drives the bank0 routine
    over a fabricated one-enemy room and reads COLUP1. It also exercises the
    body's FoldIndirect read of the enemy TYPE (bank0 -> bank2 -> bank0), so a
    broken fold or a stale pad shows up as a wrong color / a hang here."""
    lab = parse_labels(FROZEN / "bank0.lst", {"SelectActiveObject"})
    assert "SelectActiveObject" in lab, \
        "frozen bank0.lst has no SelectActiveObject (re-freeze?)"
    rts = 0x0101                       # RTS_SENTINEL (test_cell_map)
    MOTH = 4
    OBJ_MOTH, COLOR_DARK_OBJ, COLOR_MOTH = 12, 0x0A, 0x22
    Z = {"EnemyDataLo": 0x31, "EnemyDataHi": 0x32, "EnemyCount": 0x33,
         "FlickerFrame": 0x34, "BombPacked": 0x35, "RoomNo": 0x18,
         "LevelMinerRoom": 0x24, "EnemyDeadMask": 0x3A, "COLUP1": 0x07,
         "ObjBase": 0x36, "ActiveObjectX": 0x37, "ActiveObjectY": 0x38,
         "ObjTop": 0x3B, "RoomY": 0x01, "EnemyRamX": 0x3D, "EnemyRamY": 0x62,
         "EnemyRamD": 0x41, "LaserState": 0x40, "LevelStartRoom": 0x27}

    def draw(room_no, d, ls):
        class ObjMem(BankMem):
            """Bank-switching Mem that also records TIA writes ($00-$3F)."""
            def __init__(self):
                super().__init__()
                self.tia = {}

            def __setitem__(self, a, v):
                a &= 0xFFFF
                if a < 0x80:
                    self.tia[a] = v & 0xFF
                    return
                BankMem.__setitem__(self, a, v)

        mem = ObjMem()
        mem.bank = 0
        r = mem.ram
        r[Z["EnemyDataLo"]] = 0x80     # record base = $0180 (RAM, test-owned)
        r[Z["EnemyDataHi"]] = 0x01
        r[0x00] = MOTH                 # type at record +0 (EnemyOffTable stride 3)
        r[Z["EnemyCount"]] = 1
        r[Z["FlickerFrame"]] = 0
        r[Z["BombPacked"]] = 0
        r[Z["RoomNo"]] = room_no
        r[Z["LevelMinerRoom"]] = 0x7F  # miner in another room -> no miner slot
        r[Z["LevelStartRoom"]] = 0
        r[Z["EnemyDeadMask"]] = 0
        r[Z["EnemyRamX"]] = 80
        r[Z["EnemyRamY"]] = 84
        r[Z["EnemyRamD"]] = d
        r[Z["LaserState"]] = ls
        r[Z["RoomY"]] = 0x50
        r[Z["ObjBase"]] = 0xAA         # sentinel: must be rewritten
        mpu = MPU(memory=mem)
        mpu.pc = lab["SelectActiveObject"]
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(4000):
            mpu.step()
            if mpu.pc == rts:
                break
        else:
            sys.exit(f"SelectActiveObject never returned (pc=${mpu.pc:04X}, "
                     f"bank={mem.bank})")
        assert mem.bank == 0, "the draw path must come back to bank0"
        assert r[Z["ObjBase"]] == OBJ_MOTH, f"ObjBase={r[Z['ObjBase']]:02X}"
        assert r[Z["ObjTop"]] == ((84 - 0x50 + 1) & 0xFF), \
            f"ObjTop={r[Z['ObjTop']]:02X} (must stay RoomY-relative)"
        return mem.tia.get(Z["COLUP1"], 0)

    # rooms 0-3: EnemyRamD b4-7
    assert draw(0, 0x00, 0x00) == COLOR_MOTH, "room0 lit"
    assert draw(0, 0x10, 0x00) == COLOR_DARK_OBJ, "room0 dark (b4)"
    assert draw(1, 0x20, 0x00) == COLOR_DARK_OBJ, "room1 dark (b5)"
    assert draw(3, 0x80, 0x00) == COLOR_DARK_OBJ, "room3 dark (b7)"
    assert draw(0, 0x20, 0x00) == COLOR_MOTH, "room0 must ignore b5 (room1's bit)"
    # rooms 4-7: LaserState b2-5
    assert draw(4, 0x00, 0x04) == COLOR_DARK_OBJ, "room4 dark (laser b2)"
    assert draw(7, 0x00, 0x20) == COLOR_DARK_OBJ, "room7 dark (laser b5)"
    assert draw(4, 0x00, 0x00) == COLOR_MOTH, "room4 lit"
    assert draw(4, 0x00, 0x40) == COLOR_MOTH, "room4 must ignore laser b6"
    assert draw(4, 0x10, 0x00) == COLOR_MOTH, "room4 must ignore EnemyRamD b4"
    # rooms 8+: no mask bit, always lit, never crash
    for room in (8, 9, 200):
        assert draw(room, 0xFF, 0xFF) == COLOR_MOTH, f"room{room} must stay lit"


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

    # --- bank2 BuildColupF dark override (BCFDarkRun) ----------------------
    stripes = [STRIPE1, STRIPE2, STRIPE1]
    assert run_bcf(4, 0x00, 0x00) == stripes, \
        "room4 lit must keep stripe colors"
    assert run_bcf(4, 0x00, 0x04) == [0x00, 0x00, 0x00], \
        "room4 dark (UI room 5 lamp) must blacken walls"
    assert run_bcf(4, 0x00, 0x04, bomb=1) == [0x04, 0x04, 0x04], \
        "room4 dark + fuse: dark grey walls"
    assert run_bcf(4, 0x00, 0x04, bomb=2) == [0x00, 0x00, 0x00], \
        "room4 dark + explode: black walls (blink is bg-only)"
    assert run_bcf(1, 0x20, 0x00) == [0x00, 0x00, 0x00], \
        "room1 dark (EnemyRamD b5) must blacken walls"
    assert run_bcf(1, 0x00, 0x00) == stripes, \
        "room1 lit must keep stripe colors"
    assert run_bcf(8, 0xFF, 0xFF) == stripes, \
        "room8 must stay lit"

    # --- kernel-side preservers (static) ---------------------------------
    assert KERNEL.count("and #LASER_DARK") >= 1, \
        "DropArm must mask with LASER_DARK"
    assert KERNEL.count("and #LASER_KEEP") >= 1, \
        "LaserInput prologue must mask with LASER_KEEP (dark|rearm b0)"
    assert re.search(r"and #%11000111\s*;.*rooms 4-7", BANK2_SRC), \
        "LoadLevelB2 (bank2 since C2) must clear LaserState dark bits"
    assert BANK1_SRC.count("cmp #8") >= 2, \
        "IsRoomDark/SetRoomDark must guard rooms 8+"

    # --- A1: the bank0 renderer's dark path (pad -> bank1 IsRoomDark) -----
    check_select_object_dark()

    print("room-dark 8-bit mask: OK "
          "(0-3=EnemyRamD, 4-7=LaserState b5-2, 8+ always lit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
