#!/usr/bin/env python3
"""AddScore packed-BCD regression (square-digit score bug, 2026-10-02).

Repro: score 2525, bomb a thin wall (+75) -> 25+75 = 100 must become
ScoreTe=$00 / ScoreHu=6 (screen "002600"). The old routine added BINARY
and only fixed up sums >= $A0: 0x25+0x75 = 0x9A stored raw, so the ones
nibble A -> glyph index 10 -> DigitGfx+80 = past the 10-glyph font = the
solid-block last digit in screenshots/score_issue_002.png.

Driver: plants `jsr AddScore` at $80, runs until ReturnPad's rts comes
back to $83, compares ScoreTh/ScoreHu/ScoreTe against a decimal
reference over every valid input: th 0-9 x hu 0-9 x te 00-99 x amt
{$50 (kills/tally), $75 (wall)}.

Run: /home/iuri/python3/bin/python3 tools/test_addscore.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(4)]

SC_TH, SC_HU, SC_TE = 0x73, 0x74, 0x75   # $F3/$F4/$F5 (addr & $7F)
PC_ENTRY, PC_RETURN = 0x80, 0x83         # jsr at $80, rts target $83


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.bank = 1

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.banks_[self.bank][a - 0xF000]
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
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


def label(path: Path, name: str) -> int:
    pat = re.compile(rf"\s+([0-9a-f]{{4}})\s+{name}\s*$")
    for line in path.read_text(errors="replace").splitlines():
        m = pat.search(line)
        if m:
            return int(m.group(1), 16)
    sys.exit(f"label {name} not found in {path.name}")


mem = Mem()
mem.banks_ = BANKS
from py65.devices.mpu6502 import MPU  # noqa: E402
mpu = MPU(memory=mem)

ADDSCORE = label(SRC / "bank1.lst", "AddScore")
mem.ram[0:3] = bytes([0x20, ADDSCORE & 0xFF, ADDSCORE >> 8])   # jsr AddScore


def add(th, hu, te_dec, amt_dec):
    """Run AddScore once; returns (th, hu, te_packed, bank, sp)."""
    def pack(d):
        return (d // 10) * 16 + (d % 10)

    mem.ram[SC_TH], mem.ram[SC_HU], mem.ram[SC_TE] = th, hu, pack(te_dec)
    mpu.a = pack(amt_dec)                  # AddScore takes the amount in A
    mpu.pc, mpu.sp, mem.bank = PC_ENTRY, 0xFF, 1
    for _ in range(500):
        if mpu.pc == PC_RETURN:
            return (mem.ram[SC_TH], mem.ram[SC_HU], mem.ram[SC_TE],
                    mem.bank, mpu.sp)
        mpu.step()
    sys.exit(f"AddScore did not return (pc=${mpu.pc:04X}, bank={mem.bank})")


def ref(th, hu, te_dec, amt_dec):
    """Decimal ground truth incl. AddScore's carry/cap semantics."""
    s = te_dec + amt_dec
    te2, carry = s % 100, s // 100
    hu2, th2 = hu, th
    if carry:
        hu2 += 1
        if hu2 == 10:
            hu2, th2 = 0, th + 1
            if th2 == 10:
                th2 = 9
    return th2, hu2, te2


def main() -> int:
    bcd_fails, infra = [], []
    total = 0
    for th in range(10):
        for hu in range(10):
            for te in range(100):
                for amt in (50, 75):
                    total += 1
                    got = add(th, hu, te, amt)
                    exp = ref(th, hu, te, amt)
                    exp_packed = (exp[2] // 10) * 16 + (exp[2] % 10)
                    if (got[0], got[1], got[2]) != (exp[0], exp[1],
                                                    exp_packed):
                        bcd_fails.append((th, hu, te, amt, got[:3], exp))
                    if got[3] != 0:
                        infra.append(("bank not 0 after ReturnPad",
                                      th, hu, te, amt, got[3]))
                    if got[4] < 0xFF - 2:
                        infra.append(("stack leak", th, hu, te, amt, got[4]))
    if bcd_fails or infra:
        print(f"FAIL: {len(bcd_fails)}/{total} BCD mismatches, "
              f"{len(infra)} infra issues; first 5:")
        for f in bcd_fails[:5]:
            print(f"  th={f[0]} hu={f[1]} te={f[2]} amt={f[3]}: "
                  f"got={f[4]} expected={f[5]}")
        for f in infra[:5]:
            print(" ", f)
        return 1
    # explicit screenshot repro: 2525 + 75 -> 2600, both nibbles valid
    th, hu, te_packed, bank, _sp = add(2, 5, 25, 75)
    assert (th, hu, te_packed) == (2, 6, 0x00), (th, hu, te_packed)
    print(f"PASS: {total} BCD cases (incl. screenshot repro 2525+75=2600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
