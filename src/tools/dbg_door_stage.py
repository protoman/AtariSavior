"""Stage a copy of the live stage whose LEVEL 1 ROOM 1 IS a door room.

Rows: band 0/2 wall everywhere, band 1 open from col 5 (the envelope wants a
wall at the strip column in the unpatched bands, and the door needs open cells
either side). Door = side-1 LOCKED_DOOR at col 5 -> strip at x = 7 + 8*5 = 47.
The player starts at RoomX = 32 and walks right into it.

Writes /tmp/opencode/door_stage.json. Never touches src/rooms.
"""
import copy
import json
from pathlib import Path

ROOT = Path("/home/iuri/Desenvolvimento/atari_2600/ai_savior")
stage = json.load(open(ROOT / "rooms/stage.json"))
st = stage["stage"]

rows = ["##########", "####......", "##########"]
tiles = []
for row in rows:
    tiles += [1 if ch == "#" else 0 for ch in row]

mid = max(m["id"] for m in st["models"]) + 1
st["models"].append({
    "id": mid,
    "name": "door_test",
    "width": 10,
    "height": 3,
    "mid_band_type": None,
    "tiles": tiles,
})

lv = st["levels"][0]
lv["start_room"] = 0
if lv.get("miner_room") == 0:
    lv["miner_room"] = 1
room = copy.deepcopy(lv["rooms"][0])
room.update({
    "room_id": 0,
    "model_id": mid,
    "enemies": [],
    "lamps": [],
    "feature_cells": [],
    "asym_patches": [[1, 5, 9, 1]],
    "bottom_band": False,
})
lv["rooms"][0] = room

out = Path("/tmp/opencode/door_stage.json")
out.write_text(json.dumps(stage, indent=1))
print(f"staged: model {mid} rows {rows}, door side1 col5 (M1X=47) -> {out}")
