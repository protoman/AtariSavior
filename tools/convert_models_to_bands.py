#!/usr/bin/env python3
"""Convert legacy 20x12 models to 20x3 full-height color bands."""
import json
import sys
from pathlib import Path


def convert(path: Path) -> None:
    data = json.loads(path.read_text())
    models = data.get("models_file", data).get("models", [])
    for model in models:
        width = model["width"]
        height = model["height"]
        tiles = model["tiles"]
        if height == 3 and width == 20 and len(tiles) == width * 3:
            continue
        if width != 20 or height != 12 or len(tiles) != width * 12:
            raise ValueError(f"model {model.get('id')}: expected legacy 20x12 tile grid")

        bands = []
        for band in range(3):
            for x in range(width):
                cells = [tiles[(band * 4 + row) * width + x] for row in range(4)]
                bands.append(cells[0] if all(cell == cells[0] for cell in cells) else 0)
        model["height"] = 3
        model["tiles"] = bands

    path.write_text(json.dumps(data, indent=4) + "\n")


if __name__ == "__main__":
    source = (Path(sys.argv[1]) if len(sys.argv) > 1 else
              Path(__file__).resolve().parent.parent / "src/rooms/models/models.json")
    convert(source)
