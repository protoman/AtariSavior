#!/usr/bin/env python3
"""A bomb block must be bombable from where the player can stand (2026-10-26).

User report (level 18): the start room's designed block (an M1 strip at col 7)
could not be bombed from the arrival side. Measured on the real ROM with the
live stage: a bomb dropped at RoomX 49 (left of the strip) never sets the strip's
dead bit, one at RoomX 66 (right of it) does. The blast window is centred 7 px
LEFT of the player (BombX = RoomX, visible left = BombX - 7, +-2 display
columns), so the player must be on the strip's CENTRE side, standing on ground
within 2 cells. stage_reach.level_grids treats every other strip as a WALL and
reports its room; the generator drops such a block.
Run: /home/iuri/python3/bin/python3 tools/test_bomb_reach.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_reach as SR  # noqa: E402


def model(rows):
    return {"id": 0, "width": 10,
            "tiles": [1 if ch == "#" else 0 for r in rows for ch in r]}


def dead(rows, patches, start_col_hint=None):
    m = model(rows)
    lv = {"start_room": 0, "miner_room": 0,
          "rooms": [{"room_id": 0, "model_id": 0, "room_x": 0, "room_y": 0,
                     "asym_patches": patches, "enemies": []}]}
    _g, d = SR.level_grids(lv, {0: m})
    return d


# Level 18's start room (model 54): arrival column 4, the strip at col 7 (left
# half, side 1): the player never reaches cells 8-9 without crossing it.
START = ["##.....###", "#.........", "###....###", "###.######"]
assert dead(START, [[1, 7, 1, 1]]) == [0], \
    "a strip whose centre side is cut off from the arrival must be dead"

# Move the strip to the left of the arrival (col 2): the player stands to its
# right (cells 3-4) on the band-3 floor, in air cells reachable from the drop.
LEFT = ["###....###", "#.........", "#..#...###", "###.######"]
assert dead(LEFT, [[1, 1, 1, 1]]) == [], \
    "a strip with ground to its right (cells l+1 / l+2) must stay bombable"
print("test_bomb_reach: OK (centre-side ground decides whether a strip can be bombed)")
