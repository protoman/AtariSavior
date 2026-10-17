#!/home/iuri/python3/bin/python3
"""Auto-repro bugs.md #1: water death -> respawn -> hold Up.

Boots the real savior.bin, forces Level=1 (second level), turns room 0 into a
water room (pokes the level's band byte), drops the player into the band (a
water death), then holds Up+Right and watches whether he survives the respawn
or falls back into the band (death loop).

Exit 0 = no post-respawn death loop, 1 = still looping.
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
BANKS = [bytearray(open(SRC / f"bank{i}.bin", "rb").read()) for i in range(4)]


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
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
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF6 <= a <= 0x1FF9:
            self.bank = a - 0x1FF6
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


mem = Mem()
from py65.devices.mpu6502 import MPU  # noqa: E402
mpu = MPU(memory=mem)

_LBL = {}
for _l in open(SRC / "bank0.lst", errors="replace"):
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$", _l)
    if _m:
        _LBL.setdefault(_m.group(2), int(_m.group(1), 16))
PC_STARTFRAME = _LBL["StartFrame"]
LOADLEVEL = _LBL["LoadLevel"]
I_ROOMY, I_LENEMY, I_LIVES, I_DROP, I_HOVER = 0x01, 0x2F, 0x2C, 0x0A, 0x1C


def at_init_jsr():
    return (mem[mpu.pc] == 0x20
            and mem[mpu.pc + 1] | (mem[mpu.pc + 2] << 8) == LOADLEVEL
            and mpu.pc < PC_STARTFRAME)


guard = 0
while not at_init_jsr():
    mpu.step()
    guard += 1
    if guard > 200000:
        sys.exit(f"never reached init LoadLevel (pc=${mpu.pc:04X})")
mem.ram[0x23] = 1        # second level

frame = 0
band_poked = False
armed = None            # frame we dropped him into the water
deaths = []             # frames (after the initial) where a life was lost
last_lives = 3
log = []

while frame < 520:
    mpu.step()
    if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
        frame += 1
        mem.swchb = 0xFE if frame in (2, 5) else 0xFF
        dt = mem.ram[I_DROP]
        if not band_poked and dt not in (0xFF, 0xFD) and mem.ram[I_LIVES] > 0:
            lo, hi = mem.ram[I_LENEMY], mem.ram[I_LENEMY + 1]
            band = (hi << 8) | lo
            BANKS[2][band + 3 - 0xF000] = 0x1C      # room 0 band on
            band_poked = True
            armed = frame
            mem.ram[I_ROOMY] = 130
            print(f"band byte @ ${band + 3:04X} forced; RoomY->130 at f{frame}")
        if band_poked and armed is not None and frame > armed:
            y, lv, hv = mem.ram[I_ROOMY], mem.ram[I_LIVES], mem.ram[I_HOVER]
            mem.swcha = 0x6F            # hold Up + Right
            if lv < last_lives:
                last_lives = lv
                if deaths:
                    deaths.append(frame)
                else:
                    deaths.append(frame)  # first real death (the armed one)
                print(f"  f{frame}: DEATH (lives={lv}, RoomY={y})")
            log.append((frame, y, lv, hv))
            if frame % 10 == 0 and frame >= armed:
                print(f"  f{frame}: Y={y} vy={mem.ram[0x14]:02X}{mem.ram[0x13]:02X} "
                      f"JP={mem.ram[0x16]:02X} Hover={hv}")

min_lives = min((lv for _, _, lv, _ in log), default=3)
loop_deaths = max(0, len(deaths) - 1)
tail = [y for (f, y, lv, hv) in log if f >= log[-1][0] - 100] if log else []
print(f"\ntotal deaths={len(deaths)} (lives lost {3 - min_lives}); "
      f"loop deaths after respawn={loop_deaths}")
print("last 100 frames RoomY min/max:", (min(tail), max(tail)) if tail else None,
      "(band starts at 125)")
if loop_deaths == 0:
    print("PASS: no water death loop after respawn")
    sys.exit(0)
print("FAIL: water death loop")
sys.exit(1)
