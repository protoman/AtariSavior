#!/usr/bin/env python3
"""HUD key indicator: a yellow BALL on the lives row while KeyHeld is set.

2026-10-27: the key moved from P1 to the BALL (P1 now draws lives 5-8, see
test_hud_lives.py). Same contract otherwise: yellow while KeyHeld, absent without.

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

FROZEN = ROOT / "tests" / "frozen"

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


ENABL, COLUPF, CTRLPF = 0x1F, 0x08, 0x0A


def key_ball(tia):
    """(ENABL index, COLUPF at that point, ball size bits) of the lives-row key
    ball — the first ENABL write that lights it — else None."""
    for i, (_, a, v) in enumerate(tia):
        if a == ENABL and v & 2:
            col = size = None
            for _, a2, v2 in tia[:i]:
                if a2 == COLUPF:
                    col = v2
                if a2 == CTRLPF:
                    size = (v2 >> 4) & 3
            return i, col, size
    return None


RESBL = 0x14


def lives_row_writes(tia):
    """The lives row's TIA writes: the line after the ball's RESBL strobe (the
    bombs row also lights GRP0, so a band-wide scan cannot tell them apart)."""
    line = next((l for l, a, _v in tia if a == RESBL), None)
    return [] if line is None else [w for w in tia if w[0] == line + 1]


def lives_squares_drawn(tia):
    return any(a == GRP0 and v for _, a, v in lives_row_writes(tia))


# 1. THE FEATURE: with the key held a yellow 8-clock ball is drawn on the lives
#    row; the band keeps its 48 lines either way.
tia_key, ws = run_band(key_held=True)
assert ws == BAND_LINES, (f"band is {ws} scanlines with the key held, "
                         f"budget is {BAND_LINES}")
tia_off, ws_off = run_band(key_held=False)
assert ws_off == BAND_LINES, (f"band is {ws_off} scanlines without the key, "
                             f"budget is {BAND_LINES}")
kb = key_ball(tia_key)
assert kb, "key held but the ball was never enabled"
assert kb[1] == 0x1C, f"key ball colour ${kb[1]} != $1C (yellow)"
assert kb[2] == 3, f"key ball size bits {kb[2]} != 3 (8 clocks)"

# 2. Without the key the ball is never lit and nothing is yellow.
assert key_ball(tia_off) is None, "ball enabled without the key held"
# (the power bar legitimately uses yellow COLUPF earlier, so only look at the
# lives row and everything after it)
after = [w for w in tia_off if w[0] > next(l for l, a, _v in tia_off if a == RESBL)]
assert all(v != 0x1C for _, a, v in after if a in (COLUP1, COLUPF)), (
    "something was set yellow ($1C) after the lives row without the key held")

# 3. Lives: still drawn with the key held; with 0 lives the row draws nothing
#    but keeps its lines, and the key ball is still shown.
assert lives_squares_drawn(tia_key), "the lives squares vanished from the row"
tia_zero, ws_zero = run_band(key_held=True, lives=0)
assert ws_zero == BAND_LINES, f"band is {ws_zero} scanlines with 0 lives"
assert not lives_squares_drawn(tia_zero), "0 lives still drew lives squares"
assert key_ball(tia_zero), "the key ball disappeared when PlayerLives = 0"

print("test_hud_key: OK (48-line band kept; yellow 8-clock ball on the lives "
      "row while KeyHeld, absent without the key, 0-life row intact)")
