#!/usr/bin/env python3
"""View -> Map (LevelMapWindow, `savior_editor --map-png`) must show what the
room editor shows.

2026-10-27 (user: level 6 room 5, level 7 rooms 6 and 7): a room with ONE side
neighbour has a dead aperture on its far edge (the playfield is reflected). The
generator plugs it with an async wall (ball = right edge, M1 = left edge), and
the room editor draws the plug, but the map viewer painted every room from ONE
mirrored half, so the plug was stamped at the centre seam and the real edge
looked like an open exit to nowhere. The map is the user's main way to check
the structure of a level: it must never disagree with the editor.

Gate (on a GENERATED stage in a temp dir, never the live one): render each
level's map and, for every dead-end room, read the pixel on the open edge of
every band whose model row has the aperture (cell 0 open). It must be a WALL
colour (level wall / wall2), not air.

Run: /home/iuri/python3/bin/python3 tools/test_map_viewer.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_editor_roundtrip as ER   # noqa: E402  (editor binary path)

from PIL import Image                # noqa: E402

# LevelMapWindow.cpp geometry
MARGIN, HEADER = 16, 22
COL_W, ROW_H, COLS = 12, 18, 40
ROOM_W, ROOM_H = COLS * COL_W, 12 * ROW_H
BAND_H = 3 * ROW_H


def main() -> int:
    binary = ER.ensure_editor()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage.json"
        r = subprocess.run([str(binary), "--generate-stage", str(stage)],
                           capture_output=True, text=True, timeout=300)
        if r.returncode:
            print("FAIL: --generate-stage\n" + r.stderr[-800:])
            return 1
        data = json.loads(stage.read_text())["stage"]
        models = {m["id"]: m for m in data["models"]}
        checked = 0
        for level_n, level in enumerate(data["levels"], start=1):
            rooms = level["rooms"]
            pos = {(q["room_x"], q["room_y"]) for q in rooms}
            dead = []
            for i, q in enumerate(rooms):
                x, y = q["room_x"], q["room_y"]
                west, east = (x - 1, y) in pos, (x + 1, y) in pos
                if west != east:
                    dead.append((i, q, west))
            if not dead:
                continue
            png = Path(tmp) / f"l{level_n}.png"
            r = subprocess.run([str(binary), "--map-png", str(stage),
                                str(png), str(level_n)],
                               capture_output=True, text=True, timeout=120,
                               env=env)
            if r.returncode:
                print(f"FAIL: --map-png level {level_n}\n" + r.stderr[-800:])
                return 1
            img = Image.open(png).convert("RGB")
            air = {(15, 15, 20), (32, 32, 44)}
            for i, q, west in dead:
                t = models[q["model_id"]]["tiles"]
                ox = MARGIN + q["room_x"] * ROOM_W
                oy = HEADER + MARGIN + q["room_y"] * ROOM_H
                # west-only room -> the aperture left open is the RIGHT edge
                px = ox + (COLS - 1) * COL_W + COL_W // 2 if west \
                    else ox + COL_W // 2
                for band in range(4):
                    if t[band * 10] != 0:        # cell 0 solid: no aperture
                        continue
                    py = oy + band * BAND_H + BAND_H // 2
                    got = img.getpixel((px, py))
                    checked += 1
                    if got in air:
                        edge = "right" if west else "left"
                        print(f"FAIL: level {level_n} room {i + 1} band "
                              f"{band + 1}: the {edge} edge looks OPEN in the "
                              f"map viewer {got}, but the generator plugged it "
                              f"(patches {q.get('asym_patches')}) — the map "
                              f"must show the async wall")
                        return 1
        if not checked:
            print("FAIL: no dead-end room found — the test checked nothing")
            return 1
    print(f"test_map_viewer: OK ({checked} dead-end apertures drawn plugged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
