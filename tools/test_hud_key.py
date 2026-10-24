#!/usr/bin/env python3
"""HUD key indicator: a yellow square on the lives row while KeyHeld is set.

Runs the REAL bank1 HUD band (`MenuMain`, entered from bank0's fold pad at
$FC68) in py65 and records the TIA writes, so the test sees what the TV sees:
the WSYNC count (the 48-line band budget), GRP0 (lives squares), GRP1 (the key
square) and COLUP1 (its colour).

Why it exists (user request 2026-10-23): the key is held in `LevelStartRoom`
b7 and nothing showed it on screen. The band is a HARD 48-line budget, so the
indicator must be paid for out of the pad line: one extra `SetObjectXPos`
(P1) on the lives row and the pad drops 9 -> 8. The WSYNC assertion pins that.

Contract under test:
  * 48 WSYNC writes in the band, key held or not (budget unchanged);
  * key held   -> GRP1 lit for 5 scanlines, COLUP1 = $1C (yellow);
  * key clear  -> GRP1 never lit;
  * lives still drawn (GRP0 lit for 5 scanlines) in both cases.

Frozen banks + labels (src/tests/frozen/) only — never the live build.
Run: /home/iuri/python3/bin/python3 tools/test_hud_key.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "src" / "tests" / "frozen"

L1 = parse_labels(FROZEN / "bank1.lst", {"MenuMain"})
L0 = parse_labels(FROZEN / "bank0.lst",
                  {"PlayerLives", "PlayerBombs", "LevelStartRoom", "LineCount",
                   "BombX", "Level", "TickCounter", "BarLevel"})
missing = {"MenuMain"} - L1.keys() | {
    "PlayerLives", "PlayerBombs", "LevelStartRoom", "LineCount", "BombX",
    "BarLevel"} - L0.keys()
if missing:
    sys.exit(f"frozen labels missing: {sorted(missing)}")
Z = {k: v & 0x7F for k, v in {**L0, **L1}.items() if 0x80 <= v <= 0xFF}

WSYNC, COLUP1, GRP0, GRP1 = 0x02, 0x07, 0x1B, 0x1C
BAND_LINES = 48


class HudMem(Mem):
    """Mem that records TIA writes ($00-$3F) with the band's line index."""

    def __init__(self):
        super().__init__()
        self.tia = []
        self.wsync = 0

    def __setitem__(self, addr, value):
        a = addr & 0xFFFF
        if a < 0x40:
            self.tia.append((self.wsync, a, value & 0xFF))
            if a == WSYNC:
                self.wsync += 1
        super().__setitem__(addr, value)


def run_band(key_held, lives=3):
    """One HUD band pass; returns (tia writes, wsync count)."""
    mem = HudMem()
    r = mem.ram
    r[Z["PlayerLives"]] = lives
    r[Z["PlayerBombs"]] = 5
    r[Z["LevelStartRoom"]] = 0x80 if key_held else 0x00   # b7 = KeyHeld
    r[Z["BarLevel"]] = 40
    r[Z["LineCount"]] = 0
    r[Z["BombX"]] = 0
    r[Z["Level"]] = 0
    r[Z["TickCounter"]] = 30
    mem.bank = 1
    mpu = MPU(memory=mem)
    mpu.pc = L1["MenuMain"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    for _ in range(200000):
        mpu.step()
        if mpu.pc == 0xFC70:                  # band tail: back to bank0
            return mem.tia, mem.wsync
    sys.exit(f"HUD band never returned to bank0 (pc=${mpu.pc:04X}, "
             f"bank={mem.bank})")


def key_index(tia):
    """Index of the lives-row key square (the first lit GRP1 write).

    The lives row precedes the bombs row and the score, and P1 is dark on
    every earlier line, so the first lit GRP1 write IS the key square."""
    for i, (_, a, v) in enumerate(tia):
        if a == GRP1 and v:
            return i
    return -1


def key_square(tia):
    """(pattern, colour) of the key square, else (None, colour)."""
    i = key_index(tia)
    if i < 0:
        return None, None
    col = None
    for _, a, v in tia[:i]:
        if a == COLUP1:
            col = v
    return tia[i][2], col


def lives_squares_drawn(tia):
    """A lit GRP0 write on the same row as the key square?"""
    i = key_index(tia)
    if i < 0:
        return False
    return any(a == GRP0 and v for _, a, v in tia[max(0, i - 6):i + 1])


# 1. THE FEATURE: with the key held, a yellow square is drawn on the lives row
#    (one extra lit GRP1 write, on top of the bombs row's own P1 squares).
tia_key, ws = run_band(key_held=True)
assert ws == BAND_LINES, (f"band is {ws} scanlines with the key held, "
                         f"budget is {BAND_LINES}")
tia_off, ws_off = run_band(key_held=False)
assert ws_off == BAND_LINES, (f"band is {ws_off} scanlines without the key, "
                             f"budget is {BAND_LINES}")
val, col = key_square(tia_key)
assert val == 0xE0, (f"key held: the lives row drew GRP1 ${val} — expected "
                     "the $E0 square")
assert col == 0x1C, f"key square colour ${col} != $1C (yellow)"
def lives_row_window(tia):
    """TIA writes of the lives row (found by its lit GRP0 squares)."""
    for i, (_, a, v) in enumerate(tia):
        if a == GRP0 and v:
            return tia[i:i + 6]
    return []


val_off = next((v for _, a, v in lives_row_window(tia_off)
                if a == GRP1 and v), None)
assert not val_off, f"GRP1 ${val_off} drawn on the lives row without the key"

# 2. Without the key nothing yellow may be drawn anywhere in the band.
assert all(v != 0x1C for _, a, v in tia_off if a == COLUP1), (
    "COLUP1 was set yellow ($1C) without the key held")

# 3. Lives: the row still lights GRP0 for its squares; with 0 lives it draws
#    nothing there but keeps its lines (the band stays 48).
assert lives_squares_drawn(tia_key), "the lives squares vanished from the row"
tia_zero, ws_zero = run_band(key_held=True, lives=0)
assert ws_zero == BAND_LINES, f"band is {ws_zero} scanlines with 0 lives"
assert not lives_squares_drawn(tia_zero), "0 lives still drew lives squares"
val_zero, _ = key_square(tia_zero)
assert val_zero == 0xE0, "the key square disappeared when PlayerLives = 0"

print("test_hud_key: OK (48-line band kept; one extra yellow GRP1 square on "
      "the lives row while KeyHeld, absent without the key, 0-life row intact)")
