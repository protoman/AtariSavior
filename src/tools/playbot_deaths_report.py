#!/usr/bin/env python3
"""Markdown report of the playbot's deaths, with the ROOM OF DEATH drawn.

  playbot.py --log deaths.jsonl 3 17 ...      (one JSON line per death / give-up)
  python3 tools/playbot_deaths_report.py deaths.jsonl [more.jsonl ...] > report.md

Each death gets its level / room (1-based), model, cause, what the bot was doing, the facts the
bot collected, and a picture of the room: `#` wall, `.` air, `=` hot-rock row, `P` the player,
letters the enemies (s snake, m moth, b bat, p spider, t tentacle, r raft, M miner, ? other) at
the frame before the life was lost. One character = 8 px wide (the room is the model's left half plus its mirror), 12 px high; a band is 3 text rows.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]
MODELS = {m["id"]: m for m in STAGE["models"]}
NAMES = {0: "spider", 1: "bat", 2: "snake", 3: "tentacle", 4: "moth", 7: "raft", 15: "miner"}
LETTER = {0: "p", 1: "b", 2: "s", 3: "t", 4: "m", 7: "r", 15: "M"}


def picture(room, last):
    model = MODELS[room["model_id"]]
    w, h = model["width"], model["height"]
    tiles = model["tiles"]
    rows = []
    for r in range(h):
        half = "".join("#" if tiles[r * w + c] else "." for c in range(w))
        line = half + half[::-1]              # the playfield is reflected: 10 cells + their mirror
        hot = model.get("mid_band_type") and r == 1
        rows.append([("=" if hot and ch == "#" else ch) for ch in line])
    grid = []
    for r in range(h):                        # 3 text rows per 36 px band
        for _ in range(3):
            grid.append(list(rows[r]))
    def put(x, y, ch):
        cx, cy = min(19, max(0, x // 8)), min(len(grid) - 1, max(0, y // 12))
        grid[cy][cx] = ch
    for t, ex, ey in last["enemies"]:
        put(ex, ey + 6, LETTER.get(t, "?"))
    put(last["x"], last["y"] + 11, "P")       # the sprite is 22 px tall: mark its middle
    return "\n".join("    " + "".join(r) + ("   <- band %d" % (i // 3) if i % 3 == 0 else "")
                     for i, r in enumerate(grid))


def main(paths):
    deaths = []
    for p in paths:
        for line in Path(p).read_text().splitlines():
            d = json.loads(line)
            if d.get("event") == "death":
                deaths.append(d)
    deaths.sort(key=lambda d: (d["level"], d["frame"]))
    print(f"# Playbot deaths ({len(deaths)})\n")
    for d in deaths:
        room = STAGE["levels"][d["level"] - 1]["rooms"][d["room"] - 1]
        model = MODELS[room["model_id"]]
        last = d["trace"][-1]
        print(f"## Level {d['level']}, room {d['room']} (frame {d['frame']}): {d['cause']}\n")
        print(f"- model {room['model_id'] + 1} \"{model.get('name', '')}\""
              f"{' (hot middle band)' if model.get('mid_band_type') else ''}, "
              f"bottom_band={room.get('bottom_band', False)}")
        print(f"- player at x={last['x']} y={last['y']} (the frame before the life was lost), bot doing: `{d['doing']}`")
        en = ", ".join(f"{NAMES.get(t, t)} ({ex},{ey})" for t, ex, ey in last["enemies"]) or "none"
        print(f"- enemies in that frame: {en}")
        feats = [f for f in room.get("feature_cells") or []]
        if feats:
            print(f"- feature cells (band, col, type): {feats}")
        if d["facts"]:
            print("- facts: " + "; ".join(d["facts"]))
        print("\n```\n" + picture(room, last) + "\n```\n")


if __name__ == "__main__":
    main(sys.argv[1:])
