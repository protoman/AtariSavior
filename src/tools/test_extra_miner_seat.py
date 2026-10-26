#!/usr/bin/env python3
"""An extra miner (record type 15) stands with his feet ON the ground of any band.

User reports 2026-10-26: placing one in band 1 was refused ("top at 99 px" was the
level miner's own height), and then "the editor should place him exactly over the
ground, not a bit inside the other band". His 12 visible rows end on the band's
last line: top = 36 * (band + 1) - 9 = 27 / 63 / 99 px (9 art rows, 2026-10-26) (stage y 2.25 / 5.25 / 8.25; +-3 px
is still accepted for data saved before the editor snapped). The cells he covers
must be air and the cell under him solid.
Run: /home/iuri/python3/bin/python3 tools/test_extra_miner_seat.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import convert_level as C  # noqa: E402


def model(rows):
    return {"id": 0, "width": 10,
            "tiles": [1 if ch == "#" else 0 for r in rows for ch in r]}


def check(rows, y, x=18.0):
    m = model(rows)
    room = {"room_id": 0, "model_id": 0, "room_x": 0, "room_y": 0,
            "enemies": [{"type": 15, "x": x, "y": y, "dir": 1,
                         "range_min": 0, "range_max": 0, "speed": 0}]}
    try:
        C.check_rooms_against_models([room], {0: m}, "t", 5, 8.0, 4.0)
    except ValueError as e:
        return str(e)
    return None


SOLID_UNDER = ["..........", "..........", "##########", "##########"]
# floor of band 1 (y 5.25) and of band 2 are both legal on a room whose rows 2/3
# are solid; the band-0 row has air under it (band 1) so it is not a seat.
assert check(SOLID_UNDER, 5.25) is None, check(SOLID_UNDER, 5.25)
msg = check(SOLID_UNDER, 8.25)
assert msg is None or "floor" in msg or "WALL" in msg, msg   # band 2 is wall here
# exact standing heights, and a height that is no band's standing row is refused
assert check(SOLID_UNDER, 5.0) is None, check(SOLID_UNDER, 5.0)
msg = check(SOLID_UNDER, 6.0)
assert msg and "y 2.25, 5.25 or 8.25" in msg, f"y=6 must be refused with the heights: {msg}"
# the old (floor band only) value still works on a room with a floor band
FLOOR = ["..........", "..........", "..........", "##########"]
assert check(FLOOR, 8.0) is None, check(FLOOR, 8.0)
# no floor under band 1 -> refused
msg = check(["..........", "..........", "..........", "##########"], 5.0)
assert msg and "no floor" in msg, msg
# User report 2026-10-26 (level 1 room 1, model 2): a miner on display column 36,
# canvas row 7 was called "inside a WALL (band 1, cell 0)". The seat check used
# the REQUESTED sprite X (4*col + 7, which pins the TIA coarse position) instead
# of the VISIBLE left edge (4*col, convert_level.enemy_x_px docstring): column
# 36 draws on px 144-151 = cell 18 -> model cell 1 (air), not the edge wall.
MODEL2 = ["##.......#", "#.........", "####..##..", "########.."]
assert check(MODEL2, 5.25, x=36.0) is None, check(MODEL2, 5.25, x=36.0)
# and the columns that DO touch the wall are still refused (col 38-39 = cell 0)
msg = check(MODEL2, 5.25, x=38.0)
assert msg and "WALL" in msg, msg
print("test_extra_miner_seat: OK (feet on the ground of any band, other heights refused)")
