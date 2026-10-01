#!/home/iuri/python3/bin/python3
"""Unit check for UpdateLaserSound (bank1 ch0 "zoom") — no framework.

Loads the routine straight out of bank1.bin and runs it on a stubbed 6502
until its `jmp $FBF8` lands on ReturnPad, then asserts the three gates:

  1. released  — LaserState b7 clear  -> no AUDV0 write (stays silent)
  2. bomb wins — BombSnd > 0          -> no AUDV0 write (blip/explosion own ch0)
  3. held      — both clear           -> AUDC0=LASER_AUD_C, AUDV0=LASER_AUD_V,
                                          AUDF0 from LaserFreqTable[<clock>]

Run: /home/iuri/python3/bin/python3 tools/test_laser_sound.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src'
BANK1 = (SRC / 'bank1.bin').read_bytes()

AUDC0, AUDF0, AUDV0 = 0x15, 0x17, 0x19
BOMBSND, LASERSTATE, ENEMYRAMP = 0xF1, 0xC0, 0xC2
RETURN_PAD = 0xFBF8
LASER_AUD_C, LASER_AUD_V = 2, 9
FREQ_TABLE = [4, 7, 10, 12, 14, 12, 10, 7]


def label(name: str) -> int:
    lst = (SRC / 'bank1.lst').read_text(errors='replace')
    m = re.search(rf'^\s*\d+\s+([0-9a-f]{{4}})\s+{name}\s*$', lst, re.M)
    if not m:
        sys.exit(f'test_laser_sound: label {name} not in bank1.lst')
    return int(m.group(1), 16)


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)

    def __getitem__(self, a):
        a &= 0xFFFF
        if 0xF000 <= a <= 0xFFFF:
            return BANK1[a - 0xF000]
        if 0x80 <= a <= 0xFF:
            return self.ram[a - 0x80]
        if a <= 0x003F:
            return self.tia[a]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0xF000 <= a <= 0xFFFF:
            return
        if 0x80 <= a <= 0xFF:
            self.ram[a - 0x80] = v
        elif a <= 0x003F:
            self.tia[a] = v


def run(held: bool, bomb_snd: int, clock: int) -> Mem:
    from py65.devices.mpu6502 import MPU
    mem = Mem()
    mem[BOMBSND] = bomb_snd
    mem[LASERSTATE] = 0x80 if held else 0x00
    mem[ENEMYRAMP] = clock
    mpu = MPU(memory=mem)
    mpu.pc = label('UpdateLaserSound')
    for _ in range(64):
        if mpu.pc == RETURN_PAD:
            return mem
        mpu.step()
    sys.exit('test_laser_sound: routine never reached ReturnPad $FBF8')


def main() -> int:
    fails: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            fails.append(msg)

    # 1. released: AUDV0 untouched (UpdateBombSound owns the silence path)
    m = run(held=False, bomb_snd=0, clock=0)
    check(m[AUDV0] == 0, f'released: AUDV0={m[AUDV0]} != 0')

    # 2. bomb event owns channel 0 while it lasts
    m = run(held=True, bomb_snd=5, clock=0)
    check(m[AUDV0] == 0, f'bomb active: AUDV0={m[AUDV0]} != 0 (bomb must own ch0)')

    # 3. held: registers written, AUDF from the sweep table for the clock
    for clock, want in [(0, FREQ_TABLE[0]), (8 * 3, FREQ_TABLE[3]),
                        (8 * 7, FREQ_TABLE[7]), (8 * 8, FREQ_TABLE[0])]:
        m = run(held=True, bomb_snd=0, clock=clock)
        check(m[AUDC0] == LASER_AUD_C, f'clock {clock}: AUDC0={m[AUDC0]} != {LASER_AUD_C}')
        check(m[AUDV0] == LASER_AUD_V, f'clock {clock}: AUDV0={m[AUDV0]} != {LASER_AUD_V}')
        check(m[AUDF0] == want,
              f'clock {clock}: AUDF0={m[AUDF0]} != {want} (sweep table index)')

    # 4. whole sweep stays inside the table (no stray AUDF)
    for clock in range(0, 256, 4):
        m = run(held=True, bomb_snd=0, clock=clock)
        check(m[AUDF0] in FREQ_TABLE, f'clock {clock}: AUDF0={m[AUDF0]} not in table')

    for f in fails:
        print(f'  FAIL: {f}')
    if fails:
        print(f'test_laser_sound: FAILED ({len(fails)})')
        return 1
    print('test_laser_sound: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
