#!/home/iuri/python3/bin/python3
"""Intro music guard (2026-10-16).

Boots the ROM (power-on = the $FD intro), runs intro frames, and asserts the
Ukraine-anthem player drives both TIA voices: AUDC0=Lead ($0C), AUDC1=Bass
($06) once notes start, volumes in {0,7} (the anthem opens with rests), and
the melody pitch (AUDF0) advances through the sequence.
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
mel = []
seen_c0 = False
bass_on = []
bad_vol = []
intro = 0
while frame < 1400:
    mpu.step()
    if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
        frame += 1
        if mem.ram[I_DROP] == 0xFD:
            intro += 1
            if mem.tia[AUDV0] != 0:
                seen_c0 = seen_c0 or mem.tia[AUDC0] == 0x0C
                if mem.tia[AUDV0] != 7:
                    bad_vol.append((frame, "v0", mem.tia[AUDV0]))
                mel.append(mem.tia[AUDF0])
            if mem.tia[AUDV1] != 0:
                bass_on.append(frame)

print(f"intro frames={intro}; melody notes seen={len(mel)}; "
      f"distinct AUDF0={sorted(set(mel))[:12]}...")
print(f"AUDC0=Lead seen={seen_c0}; bass-on frames={len(bass_on)}; bad volumes={len(bad_vol)}")
assert intro > 1000, "did not stay on the intro screen"
assert not bad_vol, f"volume must be 7 when playing: {bad_vol[:5]}"
assert len(set(mel)) >= 4, "melody is not advancing"
assert seen_c0, "melody must use the Lead timbre"
assert not bass_on, "bass voice (AUD1) must stay muted"
print("PASS: Ukraine-anthem intro melody (AUD0 Lead), bass muted")
