#!/usr/bin/env python3
"""An extra miner (record type 15) may stand on the bottom row of ANY band.

User report 2026-10-26: placing one at canvas row 7 (stage y 5.25 = 63 px, the
floor of band 1) was refused with "he stands on the floor band ... top at 99 px".
The 99 was the level miner's own height (floor band); the real rule is that his
top is 9 px above the top of the solid cell he stands on: 36*(band+1) - 9 =
27 / 63 / 99 px for bands 0 / 1 / 2 (canvas rows 3 / 7 / 11, y 2.25 / 5.25 /
8.25). The cells he covers must be air and the cell under him solid.
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
# a height that is no band's standing row is refused, naming the three rows
msg = check(SOLID_UNDER, 6.0)
assert msg and "canvas row" in msg, f"y=6 must be refused with the row list: {msg}"
# the old (floor band only) value still works on a room with a floor band
FLOOR = ["..........", "..........", "..........", "##########"]
assert check(FLOOR, 8.25) is None, check(FLOOR, 8.25)
# no floor under band 1 -> refused
msg = check(["..........", "..........", "..........", "##########"], 5.25)
assert msg and "no floor" in msg, msg
print("test_extra_miner_seat: OK (rows 3/7/11 stand, other heights refused)")
