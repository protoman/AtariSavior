#!/usr/bin/env python3
"""mid_band_type (middle-band hot selector) fixtures.

The model field `mid_band_type` (absent/0 = Rock Solid, 1 = Hot) is the
ONLY way hot exists now — the editor's Hot Rock Wall brush is gone and a
legacy tile 8 coerces to a normal wall ('#'):

  1. default model (no key): no 'H' anywhere, legacy load unchanged;
  2. mid_band_type=1: every non-AIR row-1 cell -> 'H'; rows 0/2 stay '#'
     even for a legacy tile 8;
  3. legacy tile 8 -> '#' everywhere (decision C: coerce to normal wall);
  4. convert_room.lines emits the hot-rect stream (death + pulse) for hot
     rows, count 0 for default;
  5. resolve_asym_patches promotes ball-patch cells on row 1 to 'H'
     when the selector is hot ('#' when cold).

Run: /home/iuri/python3/bin/python3 tools/test_mid_band_hot.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_level  # noqa: E402
import convert_room  # noqa: E402

# 10x3 model: row1 walls at cols 0-7 (open 8-9), rows 0/2 open — same
# skeleton as test_asym_data.BASE_TILES.
BASE_TILES = (
    [0] * 10
    + [1] * 8 + [0, 0]
    + [0] * 10
)


def make_model(hot=0, tiles=None, patches=None):
    m = {"id": 91, "width": 10, "height": 3,
         "tiles": BASE_TILES if tiles is None else tiles}
    if hot:
        m["mid_band_type"] = hot
    if patches is not None:
        m["asym_patches"] = patches
    return m


def rows_of(model):
    return convert_level.rows_from_json({"model_id": model["id"]},
                                        {model["id"]: model})


def hot_counts(lines):
    return [int(m.group(1)) for line in lines
            if (m := re.search(r"\.byte (\d+)\s+; number of hot rectangles", line))]


# --- 1. default: no key -> no 'H', legacy byte path unchanged -------------
rows = rows_of(make_model())
assert "H" not in "".join(rows), "default model must not emit 'H'"
assert rows[1] == "#" * 8 + "..", f"default row1 {rows[1]!r}"
assert rows[0] == "." * 10 and rows[2] == "." * 10

# --- 2. selector=hot: row1 walls -> 'H', air stays '.' --------------------
rows = rows_of(make_model(hot=1))
assert rows[1] == "H" * 8 + "..", f"hot row1 {rows[1]!r}"
assert rows[0] == "." * 10 and rows[2] == "." * 10, \
    "hot must never leak into rows 0/2"

# --- 3. legacy tile 8 coerces to a normal wall ----------------------------
t8 = [0] * 30
t8[0] = 8            # row0 col0
t8[10] = 8           # row1 col0 (selector absent -> normal wall)
t8[23] = 8           # row2 col3
rows = rows_of(make_model(tiles=t8))
assert rows[0][0] == "#" and rows[1][0] == "#" and rows[2][3] == "#", \
    f"legacy tile 8 must coerce to '#', got {rows}"
assert "H" not in "".join(rows)
# ...and with selector=hot the row-1 tile 8 becomes hot with the rest.
rows = rows_of(make_model(hot=1, tiles=t8))
assert rows[1] == "H.........", f"hot row1 with legacy tile {rows[1]!r}"

# --- 4. shape block emission (C11 2026-10-21) -----------------------------
# A SHAPE block is exactly `T<id>Shape:` / `T<id>Rows:` + 3 row-pool indices,
# band 1's b7 = the selector. The hot stream is GONE from stage blocks: hot
# death derives from the PF row 1 the loader expands (see test_phase_kill's
# HotOverlapBody cases and test_cell_map's hot sweep).
from convert_room import RowPool  # noqa: E402

pool = RowPool()
cold = convert_room.lines(rows_of(make_model()), prefix="T0", source="test",
                          pool=pool, with_meta=False)
hot = convert_room.lines(rows_of(make_model(hot=1)), prefix="T1",
                         source="test", pool=pool, with_meta=False)
assert "number of hot rectangles" not in " ".join(cold + hot), (
    "a shape block must not carry a hot count / record stream (C11)")


def shape_idx(lines, prefix):
    line = lines[lines.index(prefix + "Rows:") + 1]
    return [int(v.strip().lstrip("$"), 16)
            for v in line.split(".byte", 1)[1].split(";")[0].split(",")]


assert [i & 0x80 for i in shape_idx(cold, "T0")] == [0, 0, 0, 0], (
    f"cold shape indices must have b7 clear, got {shape_idx(cold, 'T0')}")
assert [i & 0x80 for i in shape_idx(hot, "T1")] == [0, 0x80, 0, 0], (
    f"hot flag must ride band 1 only, got {shape_idx(hot, 'T1')}")
# legacy per-grid form (converter unit tests only) still shows the stream
legacy_hot = convert_room.lines(rows_of(make_model(hot=1)), prefix="T1",
                                source="test")
assert hot_counts(legacy_hot) == [1], (
    f"legacy hot-rect stream: row1 cols0-7 must be one rect, got "
    f"{hot_counts(legacy_hot)}")

# --- 5. ball patch on row 1 follows the selector --------------------------
# Patch col 0 (mirror open at left col 9): ball ADDS a wall cell on row 1.
patch = [[1, 0, 1, 0]]
model = make_model(hot=1, patches=patch)
room_hot = {"room_id": 0, "asym_patches": patch}
left_hot = rows_of(model)
right_hot, ball_x, m1_x, _, _m1r = convert_level.resolve_asym_patches(model, room_hot, left_hot)
assert right_hot is not None and ball_x == 87, "ball patch must resolve"
assert right_hot[1][0] == "H", (
    f"hot patch cell must promote to 'H', got {right_hot[1][0]!r}")

model = make_model(patches=patch)          # same patch, selector cold
room_cold = {"room_id": 0, "asym_patches": patch}
left_cold = rows_of(model)
right_cold, _, _, _, _ = convert_level.resolve_asym_patches(model, room_cold, left_cold)
assert right_cold[1][0] == "#", (
    f"cold patch cell must stay '#', got {right_cold[1][0]!r}")

# Emit both streams: hot left row1 run (1) + right run + isolated patch
# cell (2) -> [1, 2]; cold -> all zeros.
hot_lines = convert_room.lines(
    left_hot, prefix="T2", source="test", asym_rows=right_hot,
    asym_ball_x=87, asym_m1_x=0)
# C5 (2026-10-20): only the LEFT stream is emitted — RightRects/RightPF are
# retired (no reader since C4), so the right half contributes no blocks.
assert hot_counts(hot_lines) == [1], (
    f"hot base hot rects expected [1], got {hot_counts(hot_lines)}")
cold_lines = convert_room.lines(
    left_cold, prefix="T3", source="test", asym_rows=right_cold,
    asym_ball_x=87, asym_m1_x=0)
assert hot_counts(cold_lines) == [0], (
    f"cold hot rects expected [0], got {hot_counts(cold_lines)}")

print("PASS: mid_band_type selector fixtures")
