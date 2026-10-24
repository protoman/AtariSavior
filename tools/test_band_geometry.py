#!/usr/bin/env python3
"""Four-band geometry contract: kernel, converter and emitted data must agree.

The cave is growing from 3 bands of 48 lines to 4 bands of 36 (CAVE_LINES stays
144, HUD stays 48) so stages can carry a 10x4 grid — more vertical complexity
without touching sprite sizes, colours or the frame budget. This test pins the
three layers TOGETHER on purpose: a half-landed migration (kernel 4 bands but
data still 3 rows, or the reverse) is a broken ROM, and a piecemeal check would
pass while the ROM is wrong.

Contract:
  kernel     TILE_ROWS = 4, LINES_PER_TILE = 36 (a multiple of 4 so
             `line>>2` indexing stays exact), CAVE_LINES = 144,
             PLAYER_MAX_Y = CAVE_LINES - PLAYER_SPRITE_H,
             YToRowTable maps every line to its band exactly;
  converter  WIDTH 10, LEVEL_FORMAT 7, SHAPE_ROWS 4 (the editor still
             authors HEIGHT = 3 rows, so a shape block pads band 3 with a
             copy of band 2 — phase 3 of plans/band4_plan.md flips both);
  data       every shape block carries SHAPE_ROWS row-pool indices.

Run: /home/iuri/python3/bin/python3 tools/test_band_geometry.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
K = (SRC / "kernel.asm").read_text(encoding="utf-8")
CL = (ROOT / "tools" / "convert_level.py").read_text(encoding="utf-8")
CR = (ROOT / "tools" / "convert_room.py").read_text(encoding="utf-8")

WANT_BANDS = 4
WANT_LINES = 36           # 4 x 36 = 144 (CAVE_LINES unchanged)
WANT_FORMAT = 7


def kconst(name):
    m = re.search(rf"^{name}\s*=\s*(\$?)([0-9A-Fa-f]+)\b", K, re.M)
    if not m:
        sys.exit(f"kernel.asm: {name} not found")
    return int(m.group(2), 16 if m.group(1) else 10)


def cconst(name):
    m = re.search(rf"^{name}\s*=\s*(\d+)\b", CL, re.M)
    if not m:
        sys.exit(f"convert_level.py: {name} not found")
    return int(m.group(1))


fails = []


def want(got, expect, what):
    if got != expect:
        fails.append(f"{what} = {got}, want {expect}")


# --- kernel geometry -------------------------------------------------------
bands = kconst("TILE_ROWS")
lines = kconst("LINES_PER_TILE")
want(bands, WANT_BANDS, "kernel TILE_ROWS")
want(lines, WANT_LINES, "kernel LINES_PER_TILE")
want(lines % 4, 0, "kernel LINES_PER_TILE % 4 (line>>2 row indexing)")
want(kconst("CAVE_LINES"), bands * lines, "kernel CAVE_LINES (bands x lines)")
sprite_h = kconst("PLAYER_SPRITE_H") if re.search(r"^PLAYER_SPRITE_H", K, re.M) else 12
want(kconst("PLAYER_MAX_Y"), bands * lines - sprite_h,
     "kernel PLAYER_MAX_Y (cave bottom - sprite height)")

# The line->band table: one entry per 4 scanlines, band = line // LINES_PER_TILE.
m = re.search(r"^YToRowTable:\s*\n((?:\s*\.byte[^\n]*\n)+)", K, re.M)
if not m:
    fails.append("kernel.asm: YToRowTable not found")
else:
    body = re.sub(r";[^\n]*", "", m.group(1))
    table = [int(b.strip().lstrip("$"), 16)
             for b in re.sub(r"\.byte", "", body).replace("\n", ",").split(",")
             if b.strip()]
    for idx, val in enumerate(table[:bands * lines // 4]):
        expect = min((idx * 4) // lines, bands - 1)
        if val != expect:
            fails.append(f"YToRowTable[{idx}] = {val}, want {expect} "
                         f"(line {idx * 4} -> band {expect})")
            break

# --- converter -------------------------------------------------------------
want(cconst("WIDTH"), 10, "converter WIDTH")
want(cconst("LEVEL_FORMAT"), WANT_FORMAT, "converter LEVEL_FORMAT")


def crconst(name):
    m = re.search(rf"^{name}\s*=\s*(\d+)\b", CR, re.M)
    if not m:
        sys.exit(f"convert_room.py: {name} not found")
    return int(m.group(1))


want(crconst("SHAPE_ROWS"), WANT_BANDS, "converter SHAPE_ROWS (bands per shape)")
# Authored rows stay 3 until the editor grows a 4th row (phase 3); the shape
# block is padded, so the ROM side is already on 4 bands. Guard the pair so a
# half-flip (HEIGHT 4 without an editor, or SHAPE_ROWS 3) is caught here.
if crconst("HEIGHT") not in (3, WANT_BANDS):
    fails.append(f"converter HEIGHT = {crconst('HEIGHT')}, want 3 (authored) "
                 f"or {WANT_BANDS} (editor phase done)")

# --- emitted data ----------------------------------------------------------
mda = (SRC / "generated" / "models_data.asm").read_text(encoding="utf-8")
shapes = re.findall(r"^M\d+Rows:\s*\n\s*\.byte([^\n;]*)", mda, re.M)
if not shapes:
    fails.append("generated/models_data.asm: no shape blocks")
else:
    counts = {len([b for b in s.split(",") if b.strip()]) for s in shapes}
    want(counts, {WANT_BANDS}, "shape block index count(s)")

if fails:
    print("test_band_geometry: FAIL (3-band ROM)")
    for f in fails:
        print("  - " + f)
    sys.exit(1)

print(f"test_band_geometry: OK ({bands} bands x {lines} lines = "
      f"{bands * lines} cave lines, LEVEL_FORMAT {WANT_FORMAT}, "
      f"{len(shapes)} shape blocks with {WANT_BANDS} indices)")
