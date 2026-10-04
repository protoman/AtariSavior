#!/usr/bin/env python3
"""One-time D7 grid migration: pair-merge 20-col model grids to 10-col.

Plan D7 (resolved 2026-10-04, decision (a)): pair-merge with the
**open-wins** rule — a pair becomes open if either member is open, so every
>=2-old-col passage survives by construction (misaligned runs widen instead
of closing); cost: walls adjacent to passages thin by <=1 old col (user
reviews rendered stages later). Among two solid members the result is hot
if either member is hot, else wall.

Idempotent: models already at width 10 are left untouched and the file is
not rewritten when nothing changes. Aborts BEFORE writing if any migrated
model exceeds the rect-cache capacity (5 solid rects — the EnterRoom cache
copy reads exactly count+5 rects) and warns at the WallMask mask budget (4
maskable rects; pre-existing class for some models).

Run: /home/iuri/python3/bin/python3 tools/migrate_d7_grid.py [--dry]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_room import find_rectangles  # noqa: E402

MODELS = Path(__file__).resolve().parent.parent / "src/rooms/models/models.json"
OLD_W = 20
NEW_W = 10
HEIGHT = 3
RECT_CACHE_MAX = 5       # EnterRoom cache: count byte + 5 rects ($CC-$DF)
WALLMASK_BUDGET = 4      # WallMask b3-6 — rects 0-3 maskable (Risk 1)


def merge_pair(a: int, b: int) -> int:
    """open-wins, then hot-if-either among solids (tile values: 0/8/other)."""
    if a == 0 or b == 0:
        return 0
    if a == 8 or b == 8:
        return 8
    return a


def merge_tiles(tiles: list[int], width: int) -> list[int]:
    out = []
    for row in range(HEIGHT):
        base = row * width
        for c in range(0, width, 2):
            out.append(merge_pair(tiles[base + c], tiles[base + c + 1]))
    return out


def rows_of(tiles: list[int], width: int) -> list[str]:
    chars = {0: ".", 8: "H"}
    return [
        "".join(chars.get(tiles[y * width + x], "#") for x in range(width))
        for y in range(HEIGHT)
    ]


def main() -> int:
    dry = "--dry" in sys.argv[1:]
    data = json.loads(MODELS.read_text())
    models = data.get("models_file", data).get("models", [])
    changed = False
    abort = False
    for model in models:
        mid = model.get("id")
        w, h = model.get("width"), model.get("height")
        tiles = model.get("tiles", [])
        if w == NEW_W and h == HEIGHT and len(tiles) == NEW_W * HEIGHT:
            print(f"model {mid}: already 10x3 — skipped")
            continue
        if w != OLD_W or h != HEIGHT or len(tiles) != OLD_W * HEIGHT:
            print(f"model {mid}: unexpected geometry {w}x{h} "
                  f"({len(tiles)} tiles) — NOT a legacy 20x3 grid, abort")
            return 1
        old_rows = rows_of(tiles, OLD_W)
        new_tiles = merge_tiles(tiles, OLD_W)
        new_rows = rows_of(new_tiles, NEW_W)
        rects_old = find_rectangles(old_rows, solids="#H")
        rects_new = find_rectangles(new_rows, solids="#H")
        open_old = sum(r.count(".") for r in old_rows)
        open_new = sum(r.count(".") for r in new_rows)
        print(f"model {mid}: open cells {open_old} -> {open_new} (of "
              f"{OLD_W * HEIGHT} -> {NEW_W * HEIGHT}), "
              f"wall rects {len(rects_old)} -> {len(rects_new)}")
        if len(rects_new) > RECT_CACHE_MAX:
            if len(rects_new) > len(rects_old):
                print(f"  ABORT: {len(rects_new)} solid rects > rect-cache "
                      f"capacity {RECT_CACHE_MAX} AND worse than before "
                      f"({len(rects_old)})")
                abort = True
            else:
                print(f"  warn: {len(rects_new)} solid rects > rect-cache "
                      f"capacity {RECT_CACHE_MAX} — pre-existing "
                      f"({len(rects_old)} before merge), not worsened")
        elif len(rects_new) > WALLMASK_BUDGET:
            print(f"  warn: {len(rects_new)} solid rects > WallMask budget "
                  f"{WALLMASK_BUDGET} (pre-existing class; maskable = 0-3)")
        model["width"] = NEW_W
        model["tiles"] = new_tiles
        changed = True
    if abort:
        print("ABORT: no file written")
        return 1
    if not changed:
        print("nothing to migrate")
        return 0
    if dry:
        print("dry run — no file written")
        return 0
    MODELS.write_text(json.dumps(data, indent=4) + "\n")
    print(f"wrote {MODELS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
