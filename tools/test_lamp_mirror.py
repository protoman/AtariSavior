#!/usr/bin/env python3
"""LAMP wall-side mirror — enemy TYPE 13 (user 2026-10-22).

The lamp art carries its wall bracket on the LEFT (the lamp faces right), so a
lamp whose wall is on its RIGHT uses the horizontal mirror, which is enemy
type 13 (b3-0 holds 8-15 too). The converter picks the type from the room's
grid; the kernel maps 5 and 13 onto the same `cmp #LAMP` with
`and #%00000111`.

Guards here:
  * converter: wall on the left -> type 5, wall on the right -> type 13, and
    the emitted record byte carries it (no b7: lamps never carry a dir bit);
  * ROM: index 13 of ObjSpriteOffTable/ObjHeightTab points at the mirrored
    design, and its 10 rows are the horizontal mirror of index 5's, same
    colours;
  * the lamp compares mask b3 (a raw compare killed a mirrored lamp).

Frozen banks + labels only (AGENTS test-data rule).
Run: /home/iuri/python3/bin/python3 tools/test_lamp_mirror.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"
K = (SRC / "kernel.asm").read_text(encoding="utf-8")
B2 = (SRC / "bank2.asm").read_text(encoding="utf-8")

WIDTH_ = 10
HEIGHT_ = 3
LAMP_ROWS = 10
LAMP = 5
LAMP_MIRROR = 13


def obj_equ(name: str) -> int:
    m = re.search(r"^" + name + r"\s*=\s*(\d+)", K, re.M)
    assert m, f"{name} EQU missing from kernel.asm"
    return int(m.group(1))


OBJ_LAMP = obj_equ("OBJ_LAMP")
OBJ_LAMP_R = obj_equ("OBJ_LAMP_R")

# ---------------------------------------------------------------- converter
import convert_level as CV  # noqa: E402


def model_with(*cells: int) -> dict:
    """A 10x3 model whose BAND 0 has the listed logical cells solid."""
    tiles = [0] * (WIDTH_ * HEIGHT_)
    for cell in cells:
        tiles[cell] = 1
    return {"width": WIDTH_, "tiles": tiles, "mid_band_type": 0}


def lamp_type(model: dict, col: float, y: float) -> int:
    room = {"room_id": 0, "model_id": 7, "lamps": [{"x": col, "y": y}]}
    return CV._lamp_type(room, col, y, {7: model})


# The lamp at display column 6 lives in logical cell 3 (2 columns per cell).
assert lamp_type(model_with(2), 6, 3) == LAMP, "wall on the LEFT keeps the art"
assert lamp_type(model_with(4), 6, 3) == LAMP_MIRROR, (
    "wall on the RIGHT selects the mirrored design")
assert lamp_type(model_with(), 6, 3) == LAMP, "open both sides: keep the art"
assert lamp_type(model_with(2, 4), 6, 3) == LAMP, "both sides solid: keep the art"

# the band matters: a wall in another band must not flip the lamp
m = {"width": WIDTH_, "tiles": [0] * (WIDTH_ * HEIGHT_), "mid_band_type": 0}
m["tiles"][1 * WIDTH_ + 4] = 1
assert lamp_type(m, 6, 3) == LAMP, "a wall in ANOTHER band does not count"
assert lamp_type(m, 6, 5) == LAMP_MIRROR, "the same wall with the lamp in band 1"

# the stage is mirrored: display 39 is logical cell 0, so BOTH screen edges are
# cell 0, whose left neighbour is the edge (a wall)
assert lamp_type(model_with(), 0, 3) == LAMP, "left screen edge is a wall"
assert lamp_type(model_with(), 39, 3) == LAMP, "39 -> logical cell 0, same wall"
assert lamp_type(model_with(5), 30, 3) == LAMP_MIRROR, (
    "display 30 -> logical 9 -> cell 4, right neighbour cell 5 is solid")

# end to end: the emitted record byte is the mirrored type, never 0x80|type
room = {"room_id": 0, "model_id": 7, "lamps": [{"x": 6, "y": 3}], "enemies": []}
data = "\n".join(CV._enemy_tables("LEVEL1", [room], None, {7: model_with(4)}))
rec = re.search(r"LEVEL1_EnemyDataTable:\n  \.byte \$([0-9a-f]{2}), (\d+), (\d+)", data)
assert rec, f"enemy record not emitted:\n{data[-400:]}"
assert int(rec.group(1), 16) == LAMP_MIRROR, (
    f"mirrored lamp record byte ${rec.group(1)} != ${LAMP_MIRROR:02x}")
assert int(rec.group(1), 16) < 0x80, "a lamp must not carry the dir bit"

# ---------------------------------------------------------------- ROM bytes
from test_cell_map import parse_labels  # noqa: E402

NEED = {"ObjSpriteOffTable", "ObjHeightTab", "ObjSprites", "ObjColorTab"}
L = parse_labels(FROZEN / "bank0.lst", NEED)
assert not NEED - L.keys(), f"frozen labels missing: {sorted(NEED - L.keys())}"
bank0 = (FROZEN / "bank0.bin").read_bytes()
off_tab = L["ObjSpriteOffTable"] - 0xF000
height_tab = L["ObjHeightTab"] - 0xF000
sprites = L["ObjSprites"] - 0xF000
colours = L["ObjColorTab"] - 0xF000

assert bank0[off_tab + LAMP] == OBJ_LAMP
assert bank0[off_tab + LAMP_MIRROR] == OBJ_LAMP_R, (
    "ObjSpriteOffTable[13] must be the mirrored lamp design")
assert bank0[height_tab + LAMP] == LAMP_ROWS
assert bank0[height_tab + LAMP_MIRROR] == LAMP_ROWS, (
    "ObjHeightTab[13] must be the lamp's 10 rows")

for row in range(LAMP_ROWS):
    art = bank0[sprites + OBJ_LAMP + row]
    mir = bank0[sprites + OBJ_LAMP_R + row]
    want = int("{:08b}".format(art)[::-1], 2)
    assert mir == want, f"row {row}: mirrored art ${mir:02X} != reversed ${want:02X}"
    assert bank0[colours + OBJ_LAMP_R + row] == bank0[colours + OBJ_LAMP + row], (
        f"row {row}: the mirror must keep the colour")
assert bank0[sprites + OBJ_LAMP] & 0xF0 == 0xF0, "lamp row 0 lost its bracket"

# ------------------------------------------------------- the compare guards
assert re.search(r"and #%00000111[^\n]*\n(?:[^\n]*\n){0,4}\s*cmp #LAMP", K), (
    "CEH_Lamp must mask b3 so type 13 hits `cmp #LAMP`")
b2_lines = B2.splitlines()
cmp_sites = [i for i, l in enumerate(b2_lines) if l.strip() == "cmp #LAMP"]
assert len(cmp_sites) == 3, f"bank2 has {len(cmp_sites)} lamp compares, want 3"
for i in cmp_sites:
    assert any("and #%00000111" in l for l in b2_lines[max(0, i - 6):i]), (
        f"bank2 line {i + 1}: the lamp compare does not mask b3")

print("test_lamp_mirror: OK (type 13 = the wall-mirrored lamp; the converter "
      "picks it from the wall; every lamp compare masks b3)")
