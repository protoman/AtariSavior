#!/usr/bin/env python3
"""AddScore packed-BCD regression + 6-digit score + extra lives.

2026-10-02 (square-digit score bug): 25+75 = 100 must become ScoreTe=$00 and a
carry. The old routine added BINARY and stored $9A raw -> glyph index 10 -> the
solid-block score digit (screenshots/score_issue_002.png).

2026-10-27 (user): the score only reached 9,999 (ScoreTh was ONE binary digit,
and level 1 alone is worth ~1,200), and the player must get an EXTRA LIFE every
50,000 points, max 8 lives. New layout, no new zero-page byte — three packed-BCD
bytes: ScoreTe = tens|ones, ScoreHu = thousands|hundreds, ScoreTh =
hundred-thousands|ten-thousands. Max 999,999 (stays there). A carry INTO ScoreTh
is a 10,000 crossing; ScoreTh's low digit 0 or 5 then means 100k/50k.

Driver: plants `jsr AddScore` at $80, runs until ReturnPad's rts comes back to
$83, and compares ScoreTh/Hu/Te + PlayerLives against a plain-integer reference
(score + amount capped at 999,999; +1 life per 50,000 boundary crossed, cap 8)
over boundary cases (every Te x amount around each 50k and 10k edge, the cap)
and a deterministic scatter of the whole range.

Run: /home/iuri/python3/bin/python3 tools/test_addscore.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(8)]

SC_TH, SC_HU, SC_TE = 0x73, 0x74, 0x75   # $F3/$F4/$F5 (addr & $7F)
LIVES = 0x2C                              # PlayerLives $AC
MAX_LIVES = 8
PC_ENTRY, PC_RETURN = 0x80, 0x83         # jsr at $80, rts target $83


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.bank = 1

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.banks_[self.bank][a - 0xF000]
        if 0x1FF4 <= a <= 0x1FFB:
            return 0
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
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


def pack(d):
    return (d // 10) * 16 + (d % 10)


def add(score, amt_dec, lives):
    """Run AddScore once; returns (score_bytes, lives, bank, sp)."""
    mem.ram[SC_TH] = pack(score // 10000)
    mem.ram[SC_HU] = pack(score // 100 % 100)
    mem.ram[SC_TE] = pack(score % 100)
    mem.ram[LIVES] = lives
    mpu.a = pack(amt_dec)                  # AddScore takes the amount in A
    mpu.pc, mpu.sp, mem.bank = PC_ENTRY, 0xFF, 1
    for _ in range(500):
        if mpu.pc == PC_RETURN:
            return ((mem.ram[SC_TH], mem.ram[SC_HU], mem.ram[SC_TE]),
                    mem.ram[LIVES], mem.bank, mpu.sp)
        mpu.step()
    sys.exit(f"AddScore did not return (pc=${mpu.pc:04X}, bank={mem.bank})")


def ref(score, amt, lives):
    """Plain-integer ground truth: cap 999,999; +1 life per 50k crossed, max 8."""
    new = min(score + amt, 999999)
    gained = new // 50000 - score // 50000
    lives2 = min(lives + gained, MAX_LIVES) if lives < MAX_LIVES else lives
    return ((pack(new // 10000), pack(new // 100 % 100), pack(new % 100)),
            lives2)


def cases():
    seen = []
    # every Te at each edge: 10k multiples +/- the amounts, the 50k boundaries,
    # and the cap
    for edge in list(range(0, 1000000, 10000)):
        for off in (-80, -76, -75, -51, -50, -1, 0, 1, 24, 25, 99):
            sc = edge + off
            if 0 <= sc <= 999999:
                seen.append(sc)
    seen += [999999, 999950, 999925, 999900, 999999 - 74, 999999 - 49]
    x = 12345
    for _ in range(4000):                     # deterministic scatter
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        seen.append(x % 1000000)
    return sorted(set(seen))


def main() -> int:
    fails, infra = [], []
    total = 0
    for sc in cases():
        for amt in (50, 75):
            for lives in (1, 3, 7, 8):
                total += 1
                got = add(sc, amt, lives)
                exp = ref(sc, amt, lives)
                if (got[0], got[1]) != exp:
                    fails.append((sc, amt, lives, got[:2], exp))
                if got[2] != 0:
                    infra.append(("bank not 0 after ReturnPad", sc, amt, got[2]))
                if got[3] < 0xFF - 2:
                    infra.append(("stack leak", sc, amt, got[3]))
    if fails or infra:
        print(f"FAIL: {len(fails)}/{total} mismatches, {len(infra)} infra "
              f"issues; first 5:")
        for f in fails[:5]:
            print(f"  score={f[0]} +{f[1]} lives={f[2]}: got "
                  f"(bytes, lives)={f[3]} expected={f[4]}")
        for f in infra[:5]:
            print(" ", f)
        return 1
    # the screenshot repro: 2525 + 75 -> 2600, both nibbles valid
    got = add(2525, 75, 3)
    assert got[0] == (0x00, 0x26, 0x00) and got[1] == 3, got
    # the user's rule, spelled out: 49,950 + 50 = 50,000 -> one extra life
    got = add(49950, 50, 3)
    assert got[0] == (0x05, 0x00, 0x00) and got[1] == 4, got
    # ... and not twice for the same crossing, and never past 8
    got = add(50000, 50, 4)
    assert got[1] == 4, got
    got = add(99950, 50, 8)
    assert got[0] == (0x10, 0x00, 0x00) and got[1] == 8, got
    print(f"PASS: {total} cases (cap 999,999; +1 life per 50,000, max 8)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
