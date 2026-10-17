#!/home/iuri/python3/bin/python3
"""Intro music guard (2026-10-16).

Boots the ROM (power-on = the $FD intro screen), runs intro frames, and
asserts the music player drives both TIA voices: AUDC0=4 (Square) + AUDC1=6
(Bass), AUDV0/1=7, and the melody pitch (AUDF0) steps through the sequence.
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

AUDC0, AUDC1, AUDF0, AUDF1, AUDV0, AUDV1 = 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A
I_DROP = 0x0A

frame = 0
pitches = []          # (frame, AUDF0) on intro frames
bad = []              # frames where the music registers are wrong
intro_frames = 0

while frame < 400:
    mpu.step()
    if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
        frame += 1
        if mem.ram[I_DROP] == 0xFD:      # still on the intro screen
            intro_frames += 1
            if frame > 3:                # after boot ZP-clear + first tick
                if (mem.tia[AUDV0] != 7 or mem.tia[AUDV1] != 7
                        or mem.tia[AUDC0] != 4 or mem.tia[AUDC1] != 6):
                    bad.append((frame, mem.tia[AUDC0], mem.tia[AUDC1],
                                mem.tia[AUDV0], mem.tia[AUDV1]))
                pitches.append(mem.tia[AUDF0])
                if frame % 20 == 0:
                    print(f"  f{frame}: AUDF0={mem.tia[AUDF0]} "
                          f"MusPos={mem.ram[0x1D]:02X} MusTimer={mem.ram[0x1E]:02X} "
                          f"DT={mem.ram[I_DROP]:02X}")

print(f"intro frames={intro_frames}; bad audio regs={len(bad)}")
print(f"melody pitches seen: {sorted(set(pitches))}")
if bad:
    for b in bad[:5]:
        print("  bad", b)
    sys.exit(1)
assert intro_frames > 60, "did not stay on the intro screen"
assert not bad, "music registers wrong on intro frames"
assert len(set(pitches)) >= 4, "melody is not advancing through the sequence"
print("PASS: intro music driving AUD0 (Square) + AUD1 (Bass), melody advancing")
