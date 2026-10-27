#!/usr/bin/env python3
"""HUD lives row: up to 8 squares (user 2026-10-27), key drawn by the ball.

The player earns an EXTRA LIFE every 50,000 points, max 8 (AddScore). The lives
row used to be ONE quad-size P0 (SquarePat[0..3], max 3-4 squares), and a count
above that indexed past the table. Contract, on the REAL bank1 HUD band (`MenuMain`)
in py65 with the frozen banks, recording every TIA write:

  * the band stays 48 WSYNC writes for lives 0..8, key held or not (the extra
    `SetObjectXPos` for the key ball is paid from the pad: 7 -> 6 lines);
  * lives L (1..8): P0 shows min(L,4) squares and P1 shows max(L-4,0), both QUAD
    size (NUSIZ $07), 8 px pitch, P1 in the lives colour ($C6), so the row reads
    as L squares in a line;
  * the KEY is the BALL (HERO draws HUD indicators with it): while KeyHeld,
    ENABL = 2 on the lives row with COLUPF yellow ($1C) and an 8-clock ball
    (CTRLPF D5-4 = 11); with no key the ball is never enabled in the band, and
    P1 is never yellow;
  * RESBL is strobed exactly once in the band (one ball positioning).

Run: /home/iuri/python3/bin/python3 tools/test_hud_lives.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"
L1 = parse_labels(FROZEN / "bank1.lst", {"MenuMain"})
L0 = parse_labels(FROZEN / "bank0.lst",
                  {"PlayerLives", "PlayerBombs", "LevelStartRoom", "LineCount",
                   "BombX", "Level", "TickCounter", "BarLevel"})
Z = {k: v & 0x7F for k, v in {**L0, **L1}.items() if 0x80 <= v <= 0xFF}

WSYNC, NUSIZ0, NUSIZ1, COLUP0, COLUP1, COLUPF = 0x02, 0x04, 0x05, 0x06, 0x07, 0x08
CTRLPF, RESBL, GRP0, GRP1, ENABL = 0x0A, 0x14, 0x1B, 0x1C, 0x1F
BAND_LINES = 48
GREEN, YELLOW = 0xC6, 0x1C
SQUARE = {0: 0x00, 1: 0x80, 2: 0xA0, 3: 0xA8, 4: 0xAA}   # n squares, 8 px apart


class HudMem(Mem):
    def __init__(self):
        super().__init__()
        self.tia, self.wsync = [], 0

    def __setitem__(self, addr, value):
        a = addr & 0xFFFF
        if a < 0x40:
            self.tia.append((self.wsync, a, value & 0xFF))
            if a == WSYNC:
                self.wsync += 1
        super().__setitem__(addr, value)


def run_band(lives, key):
    mem = HudMem()
    r = mem.ram
    r[Z["PlayerLives"]] = lives
    r[Z["PlayerBombs"]] = 5
    r[Z["LevelStartRoom"]] = 0x80 if key else 0x00
    r[Z["BarLevel"]] = 40
    r[Z["LineCount"]] = 0
    r[Z["BombX"]] = 0
    r[Z["Level"]] = 0
    r[Z["TickCounter"]] = 30
    mem.bank = 1
    mpu = MPU(memory=mem)
    mpu.pc, mpu.sp, mpu.a, mpu.x, mpu.y = L1["MenuMain"], 0xFD, 0, 0, 0
    for _ in range(200000):
        mpu.step()
        if mpu.pc == 0xFC70:
            return mem.tia, mem.wsync
    sys.exit(f"HUD band never returned (pc=${mpu.pc:04X}, bank={mem.bank})")


def last_before(tia, i, reg):
    for _, a, v in reversed(tia[:i]):
        if a == reg:
            return v
    return None


def lives_row(tia):
    """(index of the row's first GRP0 write, the row's writes) or (-1, []).

    The lives row is the one that follows the ball's RESBL strobe: the next
    `sta WSYNC` starts the HMOVE line, and the GRP0/GRP1 writes land on it. (The
    bombs row also lights GRP0, so "first lit GRP0" would be wrong at 0 lives.)"""
    line = next((l for l, a, _v in tia if a == RESBL), None)
    if line is None:
        return -1, []
    for i, (l, a, _v) in enumerate(tia):
        if l == line + 1 and a == GRP0:
            return i, [w for w in tia[i:] if w[0] == line + 1]
    return -1, []


def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        sys.exit(1)


for key in (False, True):
    for lives in range(0, 9):
        tia, ws = run_band(lives, key)
        who = f"lives={lives} key={key}"
        check(ws == BAND_LINES, f"{who}: band is {ws} scanlines, budget {BAND_LINES}")
        check(sum(1 for _, a, _v in tia if a == RESBL) == 1,
              f"{who}: RESBL strobed {sum(1 for _, a, _v in tia if a == RESBL)}x, want 1")
        i, row = lives_row(tia)
        check(i >= 0, f"{who}: the lives row was not found (no RESBL line)")
        if lives == 0:
            check(row[0][2] == 0 and next(v for _, a, v in row if a == GRP1) == 0,
                  f"{who}: 0 lives still lit GRP0/GRP1")
        else:
            g0 = row[0][2]
            g1 = next((v for _, a, v in row if a == GRP1), None)
            check(g1 is not None, f"{who}: no GRP1 write on the lives row")
            want0, want1 = SQUARE[min(lives, 4)], SQUARE[max(lives - 4, 0)]
            check((g0, g1) == (want0, want1),
                  f"{who}: GRP0/GRP1 = ${g0:02X}/${g1:02X}, want "
                  f"${want0:02X}/${want1:02X}")
            check(last_before(tia, i, NUSIZ0) == 7 and last_before(tia, i, NUSIZ1) == 7,
                  f"{who}: lives row is not QUAD size on both players")
            if lives >= 5:
                check(last_before(tia, i, COLUP1) == GREEN,
                      f"{who}: P1 lives squares are not green")
        # the key is the ball
        ena = [(idx, v) for idx, (_, a, v) in enumerate(tia) if a == ENABL and v & 2]
        if key:
            check(ena, f"{who}: key held but the ball was never enabled")
            idx = ena[0][0]
            check(last_before(tia, idx, COLUPF) == YELLOW, f"{who}: key ball not yellow")
            check(((last_before(tia, idx, CTRLPF) or 0) >> 4) & 3 == 3,
                  f"{who}: key ball is not 8 clocks wide")
        else:
            check(not ena, f"{who}: ball enabled without the key")
        check(all(v != YELLOW for _, a, v in tia if a == COLUP1),
              f"{who}: P1 coloured yellow (the key is the BALL now)")

print("test_hud_lives: OK (0..8 lives = L squares across P0+P1, key = yellow ball, 48-line band)")
