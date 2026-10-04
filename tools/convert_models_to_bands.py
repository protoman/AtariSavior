#!/usr/bin/env python3
"""Convert legacy 20x12 models to full-height color bands (D7: 10x3)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_d7_grid import merge_tiles  # noqa: E402


def convert(path: Path) -> None:
    data = json.loads(path.read_text())
    models = data.get("models_file", data).get("models", [])
    for model in models:
        width = model["width"]
        height = model["height"]
        tiles = model["tiles"]
        if height == 3 and width == 10 and len(tiles) == width * 3:
            continue
        if width != 20 or height != 12 or len(tiles) != width * 12:
            raise ValueError(
                f"model {model.get('id')}: expected legacy 20x12 tile grid "
                f"(got {width}x{height}; a 20x3 leftover must be pair-merged "
                f"by tools/migrate_d7_grid.py first)")

        bands = []
        for band in range(3):
            for x in range(width):
                cells = [tiles[(band * 4 + row) * width + x] for row in range(4)]
                bands.append(cells[0] if all(cell == cells[0] for cell in cells) else 0)
        # D7: pair-merge straight to the 10-col grid (open-wins, same rule
        # as migrate_d7_grid) — legacy output must be valid post-D7 data.
        model["width"] = 10
        model["height"] = 3
        model["tiles"] = merge_tiles(bands, 20)

    path.write_text(json.dumps(data, indent=4) + "\n")


if __name__ == "__main__":
    source = (Path(sys.argv[1]) if len(sys.argv) > 1 else
              Path(__file__).resolve().parent.parent / "src/rooms/models/models.json")
    convert(source)
