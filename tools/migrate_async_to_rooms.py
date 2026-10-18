#!/usr/bin/env python3
"""Migrate the async walls from MODEL to ROOM (data-format change, 2026-10-17).

Before:  model.asym_patches = [[row,col,tile,side],...]   (ball/M1 strip, door)
         model.tiles        = 10/11/12 (P/V/C) feature cells
After:   room.asym_patches  = same encoding (≤2 entries)
         room.feature_cells = [[row,col,tile],...]       (one special kind)
         model.tiles        = static only (P/V/C -> SOLID_WALL, asym_patches
                              dropped) so a shape is reusable by many rooms

Why the model's P/V/C become WALL: tile_to_char() already renders P/V/C as
solid, so rewriting them as SOLID_WALL keeps the converted PF bytes identical.
The room's feature_cells then supplies the behaviour records.

Idempotent: a room that already carries asym_patches/feature_cells is left
alone, and a model that has neither key is skipped.

Usage: python3 tools/migrate_async_to_rooms.py [rooms_dir ...]
       (default: src/rooms src/tests/rooms src/tests/qa/rooms)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATURE_TILES = (10, 11, 12)          # PHASE / VCRUNCH / HCRUNCH
SOLID_WALL = 1
WIDTH, HEIGHT = 10, 3


def migrate_models(path: Path) -> dict[int, dict]:
    """Move asym_patches + feature cells out of every model. Returns
    {model_id: {"patches": [...], "features": [[row,col,tile],...]}}."""
    data = json.loads(path.read_text())
    models = data.get("models_file", data).get("models", [])
    moved: dict[int, dict] = {}
    for m in models:
        patches = m.pop("asym_patches", None) or []
        w = m.get("width", WIDTH)
        h = m.get("height", HEIGHT)
        tiles = m.get("tiles", [])
        feats = []
        for i, t in enumerate(tiles):
            if t in FEATURE_TILES:
                feats.append([i // w, i % w, t])
                tiles[i] = SOLID_WALL          # same PF byte as tile_to_char
        if feats:
            m["tiles"] = tiles
        if patches or feats:
            moved[m["id"]] = {"patches": patches, "features": feats}
    path.write_text(json.dumps(data, indent=1) + "\n")
    return moved


def migrate_level(path: Path, moved: dict[int, dict]) -> int:
    level = json.loads(path.read_text())
    lvl = level.get("level", level)
    n = 0
    for room in lvl.get("rooms", []):
        src = moved.get(room.get("model_id"))
        if not src:
            continue
        if src["patches"] and not room.get("asym_patches"):
            room["asym_patches"] = src["patches"]
            n += 1
        if src["features"] and not room.get("feature_cells"):
            room["feature_cells"] = src["features"]
            n += 1
    path.write_text(json.dumps({"level": lvl}, indent=1) + "\n")
    return n


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or [ROOT / "src/rooms",
                                       ROOT / "src/tests/rooms",
                                       ROOT / "src/tests/qa/rooms"]
    for d in dirs:
        mp = d / "models" / "models.json"
        if not mp.exists():
            print(f"skip {d} (no models/models.json)")
            continue
        moved = migrate_models(mp)
        rooms = 0
        for lv in sorted(d.glob("level_*.json")):
            rooms += migrate_level(lv, moved)
        print(f"{d}: {len(moved)} model(s) migrated "
              f"({sorted(moved)}), {rooms} room field(s) written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
