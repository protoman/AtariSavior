#!/usr/bin/env python3
"""Migrate old room JSON files to the new model/instance format."""
import json
import sys
from pathlib import Path

def tiles_key(tiles):
    return tuple(tiles)

def migrate_level(data):
    level = data["level"]
    if "models" in level:
        print(f"  Level {level['level_id']}: already migrated")
        return data
    old_rooms = level.get("rooms", [])
    if not old_rooms:
        return data
    models = []
    tile_to_model_id = {}
    for room in old_rooms:
        key = tiles_key(room.get("tiles", []))
        if key not in tile_to_model_id:
            model_id = len(models)
            tile_to_model_id[key] = model_id
            models.append({
                "id": model_id,
                "name": f"Model {model_id + 1}",
                "width": room.get("width", 20),
                "height": room.get("height", 12),
                "tiles": room.get("tiles", [])
            })
    new_rooms = []
    for room in old_rooms:
        key = tiles_key(room.get("tiles", []))
        new_rooms.append({
            "room_id": room["room_id"],
            "model_id": tile_to_model_id[key],
            "room_x": room["room_x"],
            "room_y": room["room_y"],
            "enemies": room.get("enemies", []),
            "lamps": room.get("lamps", [])
        })
    level["models"] = models
    level["rooms"] = new_rooms
    for field in ["start_x", "start_y"]:
        if field in level:
            del level[field]
    print(f"  Level {level['level_id']}: {len(models)} models, {len(new_rooms)} rooms")
    return data

def main():
    for filepath in sys.argv[1:]:
        path = Path(filepath)
        if not path.exists():
            continue
        print(f"Processing {path.name}...")
        with open(path) as f:
            data = json.load(f)
        data = migrate_level(data)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"  Saved {path.name}")

if __name__ == "__main__":
    raise SystemExit(main())
