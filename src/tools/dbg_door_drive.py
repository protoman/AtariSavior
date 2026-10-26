"""Walk a staged door ROM in py65 and report the player's state per frame.

Usage: dbg_door_drive.py <rom.bin> [--door-x N] [--dump-at X]

Tracks RoomX, RoomY, PlayerLives and (with --dump-at) the door-room staging
bytes at the frame the player first reaches that X. No emulator involved.
"""
import re
import sys
from pathlib import Path

from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT
ROM = Path(sys.argv[1])
BANKS = [bytearray(ROM.read_bytes()[i * 4096:(i + 1) * 4096]) for i in range(8)]
DOOR_X = int(sys.argv[sys.argv.index("--door-x") + 1]) if "--door-x" in sys.argv else 0
DUMP_AT = int(sys.argv[sys.argv.index("--dump-at") + 1]) if "--dump-at" in sys.argv else 0
JOY = int(sys.argv[sys.argv.index("--joy") + 1], 16) if "--joy" in sys.argv else 0x7F
FLY = "--fly" in sys.argv

LBL = {}
for line in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_.][A-Za-z0-9_.]*)"
                 r"(?:\s+subroutine)?\s*(?:;.*)?$", line)
    if m:
        LBL.setdefault(m.group(2), int(m.group(1), 16))
        continue
    z = re.match(r"^\s*\d+\s+U([0-9a-f]{4})\s+.*?(\w+)\s+byte", line)
    if z:
        LBL.setdefault(z.group(2), int(z.group(1), 16))
        continue
    e = re.match(r"^\s*\d+\s+U?[0-9a-fA-F]{4}\s+(?:[0-9a-f]{2}\s+)+"
                 r"([A-Za-z_.][A-Za-z0-9_.]*)\s+=\s+\$([0-9a-fA-F]+)", line)
    if e:
        LBL.setdefault(e.group(1), int(e.group(2), 16))

STARTFRAME = LBL["StartFrame"]
ROOMX = LBL["RoomX"] & 0x7F
ROOMY = LBL["RoomY"] & 0x7F
LIVES = LBL["PlayerLives"] & 0x7F


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 7
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x40

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            return 0
        if a == 0x000C:
            return self.inpt4
        if 0x1FF4 <= a <= 0x1FFB:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF4 <= a <= 0x1FFB:
            self.bank = a - 0x1FF4
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            self.tia[a & 0x3F] = v


def main() -> int:
    mem = Mem()
    mpu = MPU(memory=mem)
    mpu.pc = BANKS[7][0xFFC] | (BANKS[7][0xFFD] << 8)
    mpu.sp = 0xFF

    frame = -1
    rows = []
    dumped = False
    steps = 0
    while frame < 160:
        steps += 1
        if steps > 60_000_000:
            print("runaway at frame", frame)
            return 1
        if mem.bank == 0 and mpu.pc == STARTFRAME:
            frame += 1
            mem.swchb = 0xFC if 2 <= frame <= 6 else 0xFF   # SELECT+RESET
            if FLY:
                # jet pulses (UP+RIGHT) so he can cross the open right half
                low = mem.ram[ROOMY] > 78       # thrust only when sinking
                mem.swcha = 0x6F if low else 0x7F
                if frame < 25:
                    mem.swcha = 0xFF
            else:
                mem.swcha = JOY if frame >= 25 else 0xFF
            x, y, lv = mem.ram[ROOMX], mem.ram[ROOMY], mem.ram[LIVES]
            if frame >= 0:
                rows.append((frame, x, y, lv))
            if DUMP_AT and not dumped and x >= DUMP_AT:
                dumped = True
                g = lambda n: mem.ram[LBL[n] & 0x7F]
                print(f"--- frame {frame}: RoomX={x} RoomY={y} lives={lv}")
                print(f"    packed=${g('LineCount'):02X} MetaA=${g('RoomPF0Lo'):02X} "
                      f"MetaB=${g('RoomPF0Hi'):02X} DeadMask=${g('EnemyDeadMask'):02X}")
                for b in range(3):
                    print(f"    band {b}: PF0=${mem.ram[(LBL['PF0Buf']+b)&0x7F]:02X} "
                          f"PF1=${mem.ram[(LBL['PF1Buf']+b)&0x7F]:02X} "
                          f"PF2=${mem.ram[(LBL['PF2Buf']+b)&0x7F]:02X}")
        mpu.step()

    print("frame: RoomX RoomY lives")
    for f, x, y, lv in rows[::5][:22]:
        print(f"  {f:3d}: {x:3d} {y:3d} {lv}")
    xs = [r[1] for r in rows]
    print("peak RoomX:", max(xs), " final lives:", rows[-1][3],
          " final RoomY:", rows[-1][2])
    if DOOR_X:
        if max(xs) >= DOOR_X + 2:
            print("VERDICT: CROSSED the strip -> door did NOT block")
            return 1
        if max(xs) >= DOOR_X - 4:
            print("VERDICT: STOPPED at the strip -> door BLOCKED")
            return 0
        print("VERDICT: never reached the strip")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
