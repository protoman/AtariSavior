#!/usr/bin/env python3
"""Convert a level editor JSON (cereal format) into HERO-style room data.

The editor stores rooms with a `room_x`/`room_y` grid position; connections
are derived from adjacency on that grid (up/down/left/right = neighbours one
cell away). Outputs:

  - rooms/level_XXX_room_YYY.txt       one canonical text grid per room
  - generated/level_XXX_room_YYY.asm   per-room PF/map data (via convert_room)
  - generated/level_XXX_rooms.asm      per-level tables + LEVEL{n}_* constants

With `--levels LEVELS.asm a.json b.json ...` it also emits a single index:
  - generated/levels_data.asm          includes every level's per-room data
  - generated/levels.asm               includes every level's tables, LEVEL_COUNT,
                                       and the per-level LevelDataTable the game
                                       reads to start a level / place the miner.

Rooms in the JSON keep their order as the game's room index (0-based). Symbols
are prefixed per level (LEVEL{n}_*, L{n}R{room}) so several levels can coexist
in one ROM without collisions. The level number comes from the input file name
(level_002.json -> 2), falling back to the JSON `level_id` field.
"""

from pathlib import Path
import json
import re
import sys

import convert_room

WIDTH = 10                  # D7: logical cells per half (was 20 pre-D7)
# Playable color bands per room (the bottom 48 scanlines render as HUD).
HEIGHT = 3
ROOM_NONE = 0xFF
# New tile values (ai_new_tiles plan Phase 1). LOCKED_DOOR lives ONLY in
# asym_patches (side 0 = async ball strip, MetaB b7); the three grid tiles
# paint model cells and emit b7 feature records in the hot record stream.
LOCKED_DOOR = 9
PHASE = 10
VCRUNCH = 11
HCRUNCH = 12
RAFT = 6
MAGMA_FALL = 7
FEATURE_TILES = (PHASE, VCRUNCH, HCRUNCH)
FEATURE_NAME = {PHASE: "phase", VCRUNCH: "vcrunch", HCRUNCH: "hcrunch"}
# Byte that renders the editor default (56,104,144 = hue A, luma 2) under the
# emulator-aware encoding in nearest_byte: (hue << 4) | (luma << 1) = 0xA4.
LEVEL_WALL_COLOR_DEFAULT = 0xA4

# Atari 2600 TIA NTSC 128-color chart, hue-major: [hue][luma] = (r, g, b).
# MUST match src/tools/editor/src/AtariPalette.cpp kPalette exactly (same RGB values
# are used by the editor's color picker so round-tripping is stable).
# NOTE: the ROM byte is NOT the classic (luma<<4)|hue; see nearest_byte for the
# emulator-aware encoding that makes the editor pick display correctly.
kPalette = [
    # hue 0  grey
    [(0x00, 0x00, 0x00), (0x40, 0x40, 0x40), (0x6c, 0x6c, 0x6c), (0x90, 0x90, 0x90),
     (0xb0, 0xb0, 0xb0), (0xc8, 0xc8, 0xc8), (0xdc, 0xdc, 0xdc), (0xec, 0xec, 0xec)],
    # hue 1  gold
    [(0x44, 0x44, 0x00), (0x64, 0x64, 0x10), (0x84, 0x84, 0x24), (0xa0, 0xa0, 0x34),
     (0xb8, 0xb8, 0x40), (0xd0, 0xd0, 0x50), (0xe8, 0xe8, 0x5c), (0xfc, 0xfc, 0x68)],
    # hue 2  orange
    [(0x70, 0x28, 0x00), (0x84, 0x44, 0x14), (0x98, 0x5c, 0x28), (0xac, 0x78, 0x3c),
     (0xbc, 0x8c, 0x4c), (0xcc, 0xa0, 0x5c), (0xdc, 0xb4, 0x68), (0xe8, 0xcc, 0x7c)],
    # hue 3  red-orange
    [(0x84, 0x18, 0x00), (0x98, 0x34, 0x18), (0xac, 0x50, 0x30), (0xc0, 0x68, 0x48),
     (0xd0, 0x80, 0x5c), (0xe0, 0x94, 0x70), (0xec, 0xa8, 0x80), (0xfc, 0xbc, 0x94)],
    # hue 4  red
    [(0x88, 0x00, 0x00), (0x9c, 0x20, 0x20), (0xb0, 0x3c, 0x3c), (0xc0, 0x58, 0x58),
     (0xd0, 0x70, 0x70), (0xe0, 0x88, 0x88), (0xec, 0xa0, 0xa0), (0xfc, 0xb4, 0xb4)],
    # hue 5  magenta
    [(0x78, 0x00, 0x5c), (0x8c, 0x20, 0x74), (0xa0, 0x3c, 0x88), (0xb0, 0x58, 0x9c),
     (0xc0, 0x70, 0xb0), (0xd0, 0x84, 0xc0), (0xdc, 0x9c, 0xd0), (0xec, 0xb0, 0xe0)],
    # hue 6  purple
    [(0x48, 0x00, 0x78), (0x60, 0x20, 0x90), (0x78, 0x3c, 0xa4), (0x8c, 0x58, 0xb8),
     (0xa0, 0x70, 0xcc), (0xb4, 0x84, 0xdc), (0xc4, 0x9c, 0xec), (0xd4, 0xb0, 0xfc)],
    # hue 7  blue-violet
    [(0x14, 0x00, 0x84), (0x30, 0x20, 0x98), (0x4c, 0x3c, 0xac), (0x68, 0x58, 0xc0),
     (0x7c, 0x70, 0xd0), (0x94, 0x88, 0xe0), (0xa8, 0xa0, 0xec), (0xbc, 0xb4, 0xfc)],
    # hue 8  blue
    [(0x00, 0x00, 0x88), (0x1c, 0x20, 0x9c), (0x38, 0x40, 0xb0), (0x50, 0x5c, 0xc0),
     (0x68, 0x74, 0xd0), (0x7c, 0x8c, 0xe0), (0x90, 0xa4, 0xec), (0xa4, 0xb8, 0xfc)],
    # hue 9  light blue
    [(0x00, 0x18, 0x7c), (0x1c, 0x38, 0x90), (0x38, 0x54, 0xa8), (0x50, 0x70, 0xbc),
     (0x68, 0x88, 0xcc), (0x7c, 0x9c, 0xdc), (0x90, 0xb4, 0xec), (0xa4, 0xc8, 0xfc)],
    # hue A  sky blue
    [(0x00, 0x2c, 0x5c), (0x1c, 0x4c, 0x78), (0x38, 0x68, 0x90), (0x50, 0x84, 0xac),
     (0x68, 0x9c, 0xc0), (0x7c, 0xb4, 0xd4), (0x90, 0xcc, 0xe8), (0xa4, 0xe0, 0xfc)],
    # hue B  teal
    [(0x00, 0x40, 0x2c), (0x1c, 0x5c, 0x48), (0x38, 0x7c, 0x64), (0x50, 0x9c, 0x80),
     (0x68, 0xb4, 0x94), (0x7c, 0xd0, 0xac), (0x90, 0xe4, 0xc0), (0xa4, 0xfc, 0xd4)],
    # hue C  green
    [(0x00, 0x3c, 0x00), (0x20, 0x5c, 0x20), (0x40, 0x7c, 0x40), (0x5c, 0x9c, 0x5c),
     (0x74, 0xb4, 0x74), (0x8c, 0xd0, 0x8c), (0xa4, 0xe4, 0xa4), (0xb8, 0xfc, 0xb8)],
    # hue D  yellow-green
    [(0x14, 0x38, 0x00), (0x34, 0x5c, 0x1c), (0x50, 0x7c, 0x38), (0x6c, 0x98, 0x50),
     (0x84, 0xb4, 0x68), (0x9c, 0xcc, 0x7c), (0xb4, 0xe4, 0x90), (0xc8, 0xfc, 0xa4)],
    # hue E  olive
    [(0x2c, 0x30, 0x00), (0x4c, 0x50, 0x1c), (0x68, 0x70, 0x34), (0x84, 0x8c, 0x4c),
     (0x9c, 0xa8, 0x64), (0xb4, 0xc0, 0x78), (0xcc, 0xd4, 0x88), (0xe0, 0xec, 0x9c)],
    # hue F  brown
    [(0x44, 0x28, 0x00), (0x64, 0x48, 0x18), (0x84, 0x68, 0x30), (0xa0, 0x84, 0x44),
     (0xb8, 0x9c, 0x5c), (0xd0, 0xb4, 0x6c), (0xfc, 0xe0, 0x8c), (0xff, 0xee, 0x94)],
]


def nearest_byte(r: int, g: int, b: int) -> int:
    """Emulator-aware TIA color byte closest to an RGB triple.

    Stella 7.0 with TV filtering OFF (tv.filter=0) indexes its 256-entry
    palette directly by the 8-bit byte, and that palette is stored hue-major
    with (color, 0) pairs. So the displayed color equals kPalette[hue][luma]
    only when the ROM byte is (hue << 4) | (luma << 1). The classic
    (luma << 4) | hue instead displays (byte>>4) as the hue and
    ((byte&0xf)>>1) as the luma, scrambling colors (picked blue -> orange).
    Verified empirically on the local Stella with tools/palette_test.asm.
    Picking cell (hue, luma) in the editor now renders that same classic
    chart color in the emulator (WYSIWYG).
    """
    best_byte = 0
    best_dist = None
    for hue in range(16):
        for luma in range(8):
            pr, pg, pb = kPalette[hue][luma]
            dr, dg, db = r - pr, g - pg, b - pb
            dist = dr * dr + dg * dg + db * db
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_byte = (hue << 4) | (luma << 1)
    return best_byte


def tile_to_char(value: int) -> str:
    """Editor tiles: AIR open, everything else solid #.

    Legacy HOT_ROCK_WALL (8) coerces to a normal wall: hot is no longer a
    per-cell tile but the model's mid_band_type selector (row 1 only, see
    rows_from_json). LOCKED_DOOR (9) renders solid (the async strip IS a
    wall stripe). Feature tiles map to their own grid chars (P/V/C — solid
    for PF and rects, scanned by convert_room.lines for feature records).
    """
    if value == 0:
        return "."
    if value == LOCKED_DOOR:
        return "#"
    if value == PHASE:
        return "P"
    if value == VCRUNCH:
        return "V"
    if value == HCRUNCH:
        return "C"
    return "#"


def load_models(models_path: Path) -> dict:
    """models/models.json -> {id: model}; {} when missing/invalid."""
    if not models_path.exists():
        return {}
    try:
        models_data = json.loads(models_path.read_text())
        models_list = models_data.get("models_file", models_data).get("models", [])
        return {m["id"]: m for m in models_list}
    except (OSError, ValueError, KeyError):
        return {}


def rows_from_json(room: dict, models_by_id: dict = None) -> list[str]:
    # If room has model_id and models are available, look up tiles from model
    model = None
    if models_by_id and "model_id" in room:
        model = models_by_id.get(room["model_id"])
        if model:
            tiles = model.get("tiles", [])
            width = model.get("width", WIDTH)
        else:
            tiles = room.get("tiles", [])
            width = room.get("width", WIDTH)
    else:
        tiles = room.get("tiles", [])
        width = room.get("width", WIDTH)
    if width != WIDTH:
        raise ValueError(f"room {room.get('room_id')}: width {width} != {WIDTH}")
    if len(tiles) != WIDTH * HEIGHT:
        raise ValueError(
            f"room {room.get('room_id')}: expected {WIDTH * HEIGHT} tiles, got {len(tiles)}")
    # mid_band_type (0/absent = Rock Solid, 1 = Hot): the selector is
    # authoritative for row 1 — every non-AIR cell there becomes 'H'.
    # Rows 0/2 never get hot; a legacy tile 8 there coerces to '#'.
    # Phase is FORBIDDEN on the hot band (rule 2026-10-12: hot and
    # blinking are mutually exclusive). Vcrunch IS allowed on hot (user
    # rule 2026-10-14: both crunch walls respect the hot flag — hot ON
    # = touching any part of the drawn block kills). Hcrunch was already
    # allowed: its cells keep the 'C' char (the band's other cells are H).
    hot = bool((model if model else room).get("mid_band_type", 0))
    who = room.get("room_id", f"model {room.get('model_id', '?')}")
    rows = []
    for y in range(HEIGHT):
        line = []
        for x in range(WIDTH):
            t = tiles[y * WIDTH + x]
            if t == LOCKED_DOOR:
                raise ValueError(
                    f"{who}: tile 9 LOCKED_DOOR "
                    "belongs in asym_patches (async side-0 strip), not the grid")
            if t in FEATURE_TILES:
                # Special features live ONLY on the middle band (row 1) —
                # top/bottom bands are entry/exit corridors (user rule
                # 2026-10-14). Phase stays mutually exclusive with hot;
                # hcrunch/vcrunch are allowed there.
                if y != 1:
                    raise ValueError(
                        f"{who}: {FEATURE_NAME[t]} at row {y} — special "
                        "features live on the middle band (row 1)")
                if t == PHASE and hot:
                    raise ValueError(
                        f"{who}: phase on the hot middle band "
                        "— hot and blinking are mutually exclusive "
                        "(turn the hot flag off)")
                line.append(tile_to_char(t))
            elif y == 1 and hot and t != 0:
                line.append("H")
            else:
                line.append(tile_to_char(t))
        rows.append("".join(line))
    return rows


def resolve_asym_patches(model: dict,
                         left_rows: list[str]
                         ) -> tuple[list[str] | None, int, int] | None:
    """D3 asym_patches -> (right rows|None, ball x, m1 x), or None (no patches).

    Right rows are in right_col order (col 0 = center-adjacent); they start
    as the mirror of the left rows and get the patches applied on top.
    None (first element) = no right-side patches at all (the right half
    stays the plain mirror — no ball asymmetry, no Right* block emitted).

    ball x (D6, Phase 2): one SetObjectXPos arg for the whole cave frame.
    Calibrated object model (kernel S6b): arg A draws clocks [A-7, A];
    right_col c occupies clocks [80+8c, 87+8c] (2 display cols x 4 clks,
    right half starts at 80) -> A = 87 + 8c (c=0..9 -> 87..159).

    m1 x (D6, Phase A): left cell l occupies clocks [8l, 8l+7] ->
    SetObjectXPos arg A = 7 + 8l (0 = no M1 patch). ENAM1 is a whole-cave
    latch (PositionBallM1), so per-band visibility comes from the WALL-HIDE
    guard below, not a band gate.

    Patch formats (JSON arrays of ints — the editor round-trips them):
      [row, col, tile]            right side (ball) — legacy, unchanged
      [row, col, tile, side]      side 0 = right (ball), 1 = left (M1)

    D6/D6+M1 envelope (fail loudly):
      - row in bands 0..2, col in 0..9 (D7 grid), side in {0, 1};
      - TWO patches max (2 blocks: stacked on two bands, or a pair on one
        band); duplicate (row, col, side) rejected;
      - ONE column per side: all right patches share one right_col (single
        ball x), all left patches share one left cell (single M1 x); the
        two sides may use different columns (case 3: side-by-side blocks);
        same side + same band + two different x is physically impossible
        (one ball/M1, one x each) and falls out of this rule;
      - ball patches additive-only (target open where the mirror cell is
        wall — the ball can only ADD paint); a run wider than 1 cell needs
        >1 column, so the single-column rule rejects it too;
      - M1 patches must PAINT (tile solid — M1 only adds color) and pass
        the wall-hide guard: because ENAM1 latches the whole cave, the M1
        cell must be wall (#/H) in every band WITHOUT an M1 patch (PF
        priority hides the parked M1 there) and open in every band WITH
        one (a wall cell would hide the patch it claims to show).
        Ball mask and M1 mask may differ.
    """
    patches = model.get("asym_patches") or []
    if not patches:
        return None
    mid = model.get("id")
    if len(patches) > 2:
        raise ValueError(
            f"model {mid}: {len(patches)} asym patches — envelope allows "
            f"TWO blocks max (stacked on two bands, or a pair on one band)")
    right_cols: set[int] = set()
    left_cols: set[int] = set()
    left_patch_rows: set[int] = set()
    seen: set[tuple[int, int, int]] = set()
    has_right = False
    right = ["".join(left_rows[y][WIDTH - 1 - k] for k in range(WIDTH))
             for y in range(HEIGHT)]
    for p in patches:
        if not (isinstance(p, (list, tuple)) and len(p) in (3, 4)
                and all(isinstance(v, int) for v in p)):
            raise ValueError(
                f"model {mid}: asym patch {p!r} must be [row, col, tile] or "
                f"[row, col, tile, side] (side 0 = right/ball, 1 = left/M1)")
        side = p[3] if len(p) == 4 else 0
        if side not in (0, 1):
            raise ValueError(
                f"model {mid}: patch {p!r} side {side} not in 0 (right/ball) "
                f"1 (left/M1)")
        row, col, tile = p[0], p[1], p[2]
        if (row, col, side) in seen:
            raise ValueError(
                f"model {mid}: duplicate asym patch (row {row}, col {col}, "
                f"side {side}) — the same cell twice is one block")
        seen.add((row, col, side))
        if tile in FEATURE_TILES:
            raise ValueError(
                f"model {mid}: tile {tile} is a grid tile — feature tiles "
                "(phase/vcrunch/hcrunch) cannot be asym patches")
        if tile == LOCKED_DOOR:
            if row != 1:
                raise ValueError(
                    f"model {mid}: LOCKED_DOOR patch at row {row} — the "
                    "door lives on the middle band (row 1)")
            if model.get("mid_band_type"):
                raise ValueError(
                    f"model {mid}: LOCKED_DOOR on the hot middle band — "
                    "turn the hot flag off (door and hot are mutually "
                    "exclusive)")
        if not 0 <= row < HEIGHT:
            raise ValueError(f"model {mid}: patch row {row} out of 0..{HEIGHT - 1}")
        if not 0 <= col < WIDTH:
            raise ValueError(
                f"model {mid}: patch col {col} out of 0..{WIDTH - 1} (D7 grid)")
        char = tile_to_char(tile)
        if side == 1:
            # M1: paints wall-colored color over an OPEN left cell.
            if char not in "#H":
                raise ValueError(
                    f"model {mid}: M1 patch at row {row} col {col} must paint "
                    f"a wall tile (M1 only adds color, tile {tile!r} is open)")
            left_cols.add(col)
            left_patch_rows.add(row)
            continue
        mirror = left_rows[row][WIDTH - 1 - col]
        if char == "." and mirror in "#H":
            raise ValueError(
                f"model {mid}: subtractive patch at row {row} col {col} "
                f"(opens a cell whose mirror is wall — D6 is additive-only)")
        right_cols.add(col)
        has_right = True
        right[row] = right[row][:col] + char + right[row][col + 1:]
    if len(right_cols) > 1:
        raise ValueError(
            f"model {mid}: ball patches span columns {sorted(right_cols)} — "
            f"envelope allows exactly ONE column-x per side (single ball x; "
            f"a run wider than 1 cell needs >1 column and is rejected too)")
    side0_tiles = {p[2] for p in patches
                   if len(p) >= 3 and (p[3] if len(p) == 4 else 0) == 0}
    if LOCKED_DOOR in side0_tiles and len(side0_tiles) > 1:
        others = sorted(t for t in side0_tiles if t != LOCKED_DOOR)
        raise ValueError(
            f"model {mid}: side-0 patches mix LOCKED_DOOR with tile(s) "
            f"{others} — a door model's async patches must ALL be "
            "LOCKED_DOOR")
    side1_tiles = {p[2] for p in patches if len(p) >= 4 and p[3] == 1}
    if LOCKED_DOOR in side1_tiles and len(side1_tiles) > 1:
        others = sorted(t for t in side1_tiles if t != LOCKED_DOOR)
        raise ValueError(
            f"model {mid}: side-1 patches mix LOCKED_DOOR with tile(s) "
            f"{others} — a door model's M1 patches must ALL be LOCKED_DOOR")
    m1_door = LOCKED_DOOR in side1_tiles
    if len(left_cols) > 1:
        raise ValueError(
            f"model {mid}: M1 patches span columns {sorted(left_cols)} — "
            f"envelope allows exactly ONE column-x per side (single M1 x)")
    m1_x = 0
    if left_cols:
        m1_col = next(iter(left_cols))
        for b in range(HEIGHT):
            cell = left_rows[b][m1_col]
            if b in left_patch_rows and cell in "#H":
                raise ValueError(
                    f"model {mid}: M1 patch band {b} col {m1_col} is wall — "
                    f"the whole-cave ENAM1 latch would hide the patch "
                    f"(wall-hide guard)")
            if b not in left_patch_rows and cell not in "#H":
                raise ValueError(
                    f"model {mid}: M1 cell col {m1_col} is open in band {b} "
                    f"with no patch — the whole-cave ENAM1 latch would paint "
                    f"it (wall-hide guard: wall the cell or patch the band)")
        m1_x = 7 + 8 * m1_col
    ball_x = 87 + 8 * next(iter(right_cols)) if has_right else 0
    if has_right and model.get("mid_band_type"):
        # Ball patch cells on row 1 follow the middle-band selector too
        # (rows_from_json already promoted the mirrored base cells).
        right[1] = "".join("H" if c == "#" else c for c in right[1])
    return (right if has_right else None), ball_x, m1_x, m1_door


def model_door_flag(model: dict) -> bool:
    """True when the model carries a LOCKED_DOOR async patch (MetaB b7)."""
    return any(
        len(p) >= 3 and p[2] == LOCKED_DOOR
        and (p[3] if len(p) == 4 else 0) == 0
        for p in (model.get("asym_patches") or [])
    )


def model_m1_door_flag(model: dict) -> bool:
    """True when the model carries a side-1 LOCKED_DOOR (MetaA b3)."""
    return any(
        len(p) == 4 and p[3] == 1 and p[2] == LOCKED_DOOR
        for p in (model.get("asym_patches") or [])
    )


def model_specials(model: dict) -> list[str]:
    """Special-feature kinds present in a model (door patches + grid tiles).

    Order: door first (async patch), then phase/vcrunch/hcrunch by tile id.
    """
    kinds: list[str] = []
    if model_door_flag(model):
        kinds.append("door")
    for t in sorted(set(model.get("tiles") or [])):
        if t in FEATURE_NAME:
            kinds.append(FEATURE_NAME[t])
    return kinds


def check_model_objects(model: dict, who: str) -> None:
    """Special features are alone; raft is bottom-band (user rule 2026-10-14)."""
    kinds = model_specials(model)
    if len(kinds) > 1:
        raise ValueError(
            f"{who}: mixed special features {kinds} — special features are "
            "alone per room (door XOR phase XOR vcrunch XOR hcrunch)")
    w = int(model.get("width", WIDTH))
    tiles = model.get("tiles") or []
    has_obj_tile = any(t in (RAFT, MAGMA_FALL) for t in tiles)
    for i, t in enumerate(tiles):
        if t == RAFT and i // w != 2:
            raise ValueError(
                f"{who}: RAFT at row {i // w} — the raft lives on the "
                "bottom band (row 2, the water strip)")
    if has_obj_tile:
        for k in ("door", "vcrunch", "hcrunch"):
            if k in kinds:
                raise ValueError(
                    f"{who}: {k} model also has raft/magma tiles — "
                    f"{k} rooms block objects (vcrunch/hcrunch need the "
                    "sprite slot; door allows a single enemy only)")


def check_rooms_against_models(rooms: list[dict], models_by_id: dict,
                               who_prefix: str,
                               miner_room: int = -1) -> None:
    """Per-room object rules against the room's model special (2026-10-14).

    vcrunch/hcrunch rooms: no objects at all. Door rooms: at most one
    enemy, and never a key/lamp/miner. Raft models need water rooms
    (bottom_band). Tentacles live in the water on the bottom band.
    """
    if not models_by_id:
        return
    for index, room in enumerate(rooms):
        model = models_by_id.get(room.get("model_id"))
        if model is None:
            continue
        who = f"{who_prefix} room {index} (model {model['id']})"
        kinds = model_specials(model)
        enemies = room.get("enemies") or []
        lamps = room.get("lamps") or []
        miner = miner_room == index
        if "vcrunch" in kinds or "hcrunch" in kinds:
            kind = "vcrunch" if "vcrunch" in kinds else "hcrunch"
            if enemies or lamps or miner:
                raise ValueError(
                    f"{who}: {kind} room has objects (enemies/lamps/miner) "
                    "— the shutter needs the sprite slot")
        if "door" in kinds:
            if len(enemies) > 1:
                raise ValueError(
                    f"{who}: door room has {len(enemies)} enemies — at "
                    "most ONE enemy per door room")
            if any(int(e.get("type", 0)) == 6 for e in enemies):
                raise ValueError(
                    f"{who}: door room has a KEY enemy — door rooms allow "
                    "a single non-key enemy only")
            if lamps or miner:
                raise ValueError(
                    f"{who}: door room has a lamp/miner — door rooms allow "
                    "a single enemy only")
        tiles = model.get("tiles") or []
        if any(t == RAFT for t in tiles) and not room.get("bottom_band"):
            raise ValueError(
                f"{who}: model has RAFT tiles but the room is not water "
                "(bottom_band=false)")
        for e in enemies:
            if int(e.get("type", 0)) == 3:  # EnemyType::TENTACLE
                if not room.get("bottom_band"):
                    raise ValueError(
                        f"{who}: tentacle in a room without the bottom "
                        "band — tentacles live in the water")
                row = int(float(e.get("y", 0))) // 4
                if row != 2:
                    raise ValueError(
                        f"{who}: tentacle at display row "
                        f"{e.get('y')} — tentacles live on the bottom band "
                        "(model row 2)")


def connection_bytes(rooms: list[dict]) -> list[list[int]]:
    """Per-room [up, down, left, right] neighbours, by room_x/room_y adjacency."""
    twelve = ROOM_NONE
    result = []
    for i, room in enumerate(rooms):
        up = down = left_ = right = ROOM_NONE
        for j, other in enumerate(rooms):
            if i == j:
                continue
            same_x = room["room_x"] == other["room_x"]
            same_y = room["room_y"] == other["room_y"]
            dy = other["room_y"] - room["room_y"]
            dx = other["room_x"] - room["room_x"]
            if same_x and dy == -1:
                up = j
            elif same_x and dy == 1:
                down = j
            elif same_y and dx == -1:
                left_ = j
            elif same_y and dx == 1:
                right = j
        result.append([up, down, left_, right])
    return result


def nibble_room(value: int, direction: str) -> int:
    """Room index or none for one nibble of a packed connection byte."""
    if value == ROOM_NONE:
        return 0xF
    if value > 14:
        raise ValueError(
            f"room index {value} for {direction}: nibble pack allows 0-14 "
            "($F = none)")
    return value


def px(value, per_tile: int) -> int:
    """Tile-coordinate float -> game pixel byte (x: 8 px/tile, y: 12 px/tile)."""
    return int(round(float(value) * per_tile))


def enemy_x_px(column: float) -> int:
    """Full-stage display column (0..39) -> requested sprite X (game pixels).

    SetObjectXPos pins the sprite's requested X, but the TIA coarse/fine grid
    renders its visible LEFT edge with an offset: 4 px below X=15 and 7 px from
    X=15 up (the same offsets PlayerHitsMap compensates for). Without a
    correction every enemy square shows one playfield block (4 px) further left
    than the editor column it was placed on. Request X = target + offset so the
    visible square lands exactly on the chosen column (4 px per block).
    """
    target = px(column, 4)
    return target + 4 if target < 11 else target + 7


def level_number_from_path(path: Path) -> int:
    """Level number from the input file name (level_002.json -> 2), else 0."""
    match = re.search(r"level_(\d+)", path.stem, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def write_tables(level: dict, rooms: list[dict], connections: list[list[int]],
                 output: Path, level_n: int, models_by_id: dict = None) -> None:
    prefix = f"LEVEL{level_n}"
    room_prefix = f"L{level_n}R"
    # Two wall colors: bands 0 and 2 use color 1; band 1 uses color 2.
    wall = nearest_byte(
        int(level.get('wall_r', 56)),
        int(level.get('wall_g', 104)),
        int(level.get('wall_b', 144)))
    wall2 = nearest_byte(
        int(level.get('wall2_r', 40)),
        int(level.get('wall2_g', 130)),
        int(level.get('wall2_b', 90)))
    miner_room = int(level.get("miner_room", 0))
    if int(level.get("miner_dir", -1)) > 0:
        miner_room |= 0x80  # kernel uses bit 7 as miner-facing-right flag
    check_rooms_against_models(rooms, models_by_id,
                               f"level {level_n}",
                               int(level.get("miner_room", 0)) & 0x7F)
    lines = [
        f"; Generated from {level.get('name', 'level')} (level {level_n}). "
        "Do not edit by hand."
    ]
    lines += [
        f"{prefix}_START_ROOM = {level.get('start_room', 0)}",
        f"{prefix}_WALL_COLOR = ${wall:02x}",
        f"{prefix}_WALL_COLOR2 = ${wall2:02x}",
        f"{prefix}_START_X = 32",
        f"{prefix}_START_Y = 24",
        f"{prefix}_MINER_ROOM = {miner_room}",
        f"{prefix}_MINER_X = {enemy_x_px(float(level.get('miner_x', 0)) * 2)}",
        f"{prefix}_MINER_Y = {px(level.get('miner_y', 0), 12)}",
        "",
    ]
    lines.append(
        f"; Room data: one ({room_prefix}<n>TilePF0, ...RoomRects) word pair per room,"
        " indexed by RoomNo. Rooms pointing at a model share that model's")
    lines.append(
        "; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).")
    lines.append(f"{prefix}_RoomDataTable:")
    for index, room in enumerate(rooms):
        model = models_by_id.get(room.get("model_id")) if models_by_id else None
        if model is not None:
            mid = model["id"]
            lines.append(
                f"  .word M{mid}TilePF0, M{mid}RoomRects ; room {index} (model {mid})")
        else:
            lines.append(
                f"  .word {room_prefix}{index + 1}TilePF0, "
                f"{room_prefix}{index + 1}RoomRects ; room {index}")
    lines.append("")
    lines.append(
        "; Room connections: 2 bytes/room, nibble-packed "
        "(up<<4|down, left<<4|right); $F = none.")
    lines.append(f"{prefix}_RoomConnections:")
    for index, conn in enumerate(connections):
        up, down, left_, right = conn
        lines.append(
            f"  .byte ${nibble_room(up, 'up'):01x}{nibble_room(down, 'down'):01x}, "
            f"${nibble_room(left_, 'left'):01x}{nibble_room(right, 'right'):01x} "
            f"; room {index}")
    lines += _enemy_tables(prefix, rooms)
    output.write_text("\n".join(lines) + "\n")


# Runtime ceiling for a room's enemies+lamps: EnemyRamX has only 3 slots —
# slot 3 would collide with LaserState at $C0 (docs/zp_layout_skill.md).
# The POLICY cap is 2 objects/room (editor kMaxRoomElements=2, verify_build
# enemies+lamps <=2); this slice only guards the hardware slot bound.
MAX_ENEMIES = 3
# Per-enemy byte layout in LEVEL{n}_EnemyDataTable (see _enemy_tables).
ENEMY_STRIDE = 4  # S4.1: was 6 — range_min/range_max dropped from ROM (dead:
                  # kernel skips them; editor JSON keeps the fields)


def _room_bottom_color(room: dict) -> int:
    """Bottom-band TIA color byte for a room (0 = band off)."""
    if not room.get("bottom_band"):
        return 0
    color = nearest_byte(
        int(room.get("bottom_r", 0)),
        int(room.get("bottom_g", 0)),
        int(room.get("bottom_b", 0)))
    return color if color != 0 else 1  # never emit 0 when band is on


def _enemy_tables(prefix: str, rooms: list[dict]) -> list[str]:
    """Emit the level's flat enemy table and the per-room enemy records.

    Enemies are positioned in EDITOR stage coordinates: x is a full-stage
    display column (0..39 across both mirror halves, so the game screens can
    differ per side) and y is a room row (0..11). Column -> room pixel uses
    4 px/column (one playfield block), row -> scanline uses 12 px/row,
    matching the existing level/miner coordinate conversion. Lamp x is stored
    at the tile center and shifted left by half its 4px sprite width.

    LEVEL{n}_EnemyDataTable is a flat list of ENEMY_STRIDE-byte records:
    type, x, y, dir (S4.1 — range_min/range_max dropped from ROM: nothing
    read them; the editor JSON still carries those fields).
    LEVEL{n}_RoomEnemies has one 4-byte record per room:
    ptr_lo, ptr_hi, count, bottom_color (0 = no bottom band).
    """
    flat: list[tuple[int, int, int, int]] = []
    counts: list[int] = []
    bottoms: list[int] = []
    # Lamp entries are merged into the enemy table as type=5 (kernel LAMP).
    # Same 4-byte stride / RoomEnemies records — no separate lamp table.
    LAMP_TYPE = 5
    for index, room in enumerate(rooms):
        entities = [e for e in (room.get("enemies") or [])]
        for lamp in (room.get("lamps") or []):
            entities.append({
                "type": LAMP_TYPE,
                "x": lamp.get("x", 0),
                "y": lamp.get("y", 0),
                "dir": 1,
            })
        entities = entities[:MAX_ENEMIES]
        counts.append(len(entities))
        bottoms.append(_room_bottom_color(room))
        for enemy in entities:
            type_ = int(enemy.get("type", 0))
            x = float(enemy.get("x", 0))
            if type_ == LAMP_TYPE:
                x -= 0.5  # editor stores lamp center; GRP1 data is left-aligned
            flat.append((
                type_,
                enemy_x_px(x),
                px(float(enemy.get("y", 0)), 12),
                int(enemy.get("dir", 1)),
            ))
    lines = [""]
    lines += [
        f"; Enemy data: {len(flat)} enemy records across {len(rooms)} rooms, "
        f"{ENEMY_STRIDE} bytes each (type,x,y,dir).",
        f"{prefix}_EnemyDataTable:",
    ]
    for type_, x, y, dir_ in flat:
        lines.append(f"  .byte {type_}, {x}, {y}, {dir_}")
    lines += [
        "",
        "; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.",
        f"{prefix}_RoomEnemies:",
    ]
    for index, count in enumerate(counts):
        color = bottoms[index]
        color_hex = f"${color:02x}"
        if count:
            start = sum(counts[:index]) * ENEMY_STRIDE
            lines.append(
                f"  .byte <({prefix}_EnemyDataTable+{start}), "
                f">({prefix}_EnemyDataTable+{start}), {count}, {color_hex} ; room {index}")
        else:
            lines.append(
                f"  .byte <({prefix}_EnemyDataTable), "
                f">({prefix}_EnemyDataTable), 0, {color_hex} ; room {index}")
    return lines


def write_levels_index(output: Path, json_paths: list[Path]) -> None:
    """Emit models_data.asm + levels_data.asm (includes) + levels.asm (tables).

    The game reads LevelDataTable[Level] to start a level and place the miner.
    miner_room's high bit carries miner-facing-right; low 7 bits remain room id.
    The entry contains 8 scalar bytes followed by three word pointers (stride14).

    models_data.asm holds each referenced model's PF/rect data ONCE, shared by
    every room (across all levels) whose RoomDataTable points at that model.
    """
    generated = output.parent
    data_lines = ["; Generated by convert_level.py --levels. Do not edit by hand.", ""]
    table_lines = ["; Generated by convert_level.py --levels. Do not edit by hand.", ""]
    levels = []
    referenced: set = set()
    models_by_id = load_models(json_paths[0].parent / "models" / "models.json")
    for path in json_paths:
        level = json.loads(path.read_text())
        if "level" in level:          # cereal wraps the level in an NVP
            level = level["level"]
        level_n = level_number_from_path(path) or int(level.get("level_id", 1))
        levels.append((level_n, level))
        for room in level["rooms"]:
            if models_by_id.get(room.get("model_id")) is not None:
                referenced.add(models_by_id[room["model_id"]]["id"])
        check_rooms_against_models(level.get("rooms") or [], models_by_id,
                                   f"level {level_n}",
                                   int(level.get("miner_room", 0)) & 0x7F)
        rel = generated.name
        data_lines.append(f'    include "{rel}/level_{level_n:03d}_rooms_data.asm"')
        table_lines.append(f'    include "{rel}/level_{level_n:03d}_rooms.asm"')
    data_lines.append("")

    # Shared model playfield + collision data, emitted once for all levels.
    model_lines = ["; Generated by convert_level.py --levels. Do not edit by hand."]
    for mid in sorted(referenced):
        model = models_by_id[mid]
        model_lines.append("")
        left_rows = rows_from_json({"model_id": mid, "tiles": model.get("tiles"),
                                    "width": model.get("width", WIDTH)},
                                   models_by_id)
        check_model_objects(model, f"models.json model {mid}")
        res = resolve_asym_patches(model, left_rows)
        asym, ball_x, m1_x, m1_door = res if res else (None, 0, 0, False)
        # M1 patches on the hot band (row 1 = rows_from_json's hot row) go
        # into the hot stream: the cells are PF-open so the 'H' walk never
        # sees them — convert_room emits them as mask-$00 records.
        hot_m1 = []
        if model.get("mid_band_type"):
            for p in model.get("asym_patches") or []:
                side = p[3] if len(p) == 4 else 0
                if side == 1 and p[0] == 1:
                    hot_m1.append((p[0], p[1]))
        model_lines += convert_room.lines(
            left_rows, prefix=f"M{mid}", source=f"models.json model {mid}",
            asym_rows=asym, asym_ball_x=ball_x, asym_m1_x=m1_x,
            hot_m1=hot_m1, door=model_door_flag(model),
            m1_door=model_m1_door_flag(model),
            hot=bool(model.get("mid_band_type")))
    model_lines.append("")
    (generated / "models_data.asm").write_text("\n".join(model_lines) + "\n")
    data_lines.insert(2, f'    include "{generated.name}/models_data.asm"')
    (generated / "levels_data.asm").write_text("\n".join(data_lines) + "\n")

    tail_lines = [
        "",
        "LEVEL_DATA_STRIDE = 14",
        f"LEVEL_COUNT = {len(levels)}",
        "",
        "; Per-level entry (stride 14): start room/x/y, miner room/x/y, both wall",
        "; colors, then the level's RoomDataTable and RoomConnections bases.",
        "LevelDataTable:",
    ]
    for level_n, _level in levels:
        prefix = f"LEVEL{level_n}"
        tail_lines += [
            f"  .byte {prefix}_START_ROOM, {prefix}_START_X, {prefix}_START_Y, "
            f"{prefix}_MINER_ROOM, {prefix}_MINER_X, {prefix}_MINER_Y, "
            f"{prefix}_WALL_COLOR, {prefix}_WALL_COLOR2",
            f"  .word {prefix}_RoomDataTable, {prefix}_RoomConnections, {prefix}_RoomEnemies",
        ]
    tail_lines += [""]
    table_lines += tail_lines
    output.write_text("\n".join(table_lines) + "\n")
    # levels_index.asm = the tail alone: bank2 includes it separately from
    # the per-level table files (level-data spill layout, bugs.md 27).
    index_lines = [
        "; Generated by convert_level.py --levels. Do not edit by hand.",
        "; Tail only (EQUs + LevelDataTable) — see bugs.md 27 spill layout.",
    ] + tail_lines
    (generated / "levels_index.asm").write_text("\n".join(index_lines) + "\n")
    emit_spills(generated)


def _gen_data_size(path: Path) -> int:
    """Bytes a generated pure-data .asm contributes (.byte=1, .word=2)."""
    n = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(";")[0].strip()
        if line.startswith(".byte"):
            n += len([o for o in line[5:].split(",") if o.strip()])
        elif line.startswith(".word"):
            n += 2 * len([o for o in line[5:].split(",") if o.strip()])
    return n


# bank2 data-slot gaps (bugs.md 27/27b): (name, slot end, capacity note).
# Starts are pad-derived ($F767/$F901 from the fixed content above them);
# tools/verify_build.py --precheck re-measures the REAL starts from
# bank2.lst after every build and fails on overflow — keep here in sync.
_SPILL_SLOTS = [
    ("spill_F767", 0xF800),   # after FooterFont lead-in  ($F767, 153B)
    ("spill_F901", 0xF970),   # TitleJetColors tail       ($F901, 111B)
    ("spill_window", 0xFB84), # after models+rooms_data   (window, 427B total)
    ("spill_F840", 0xF880),   # TitleBombSprite gap       ($F864, 28B —
                              #  start moved 0xF840->0xF864 when FooterFont
                              #  grew to 13 rows, 2026-10-12; name kept)
    # $F5A4 (92B) NOT usable: it assembles BEFORE levels_index defines
    # ROOM_NONE — a spill slot must sit after the index in source order.
]
_SPILL_ORG = {  # slot start for capacity of the window slot (org $F9D9)
    "spill_window": 0xF9D9,
}


def emit_spills(generated: Path) -> None:
    """bugs.md 27b: place level files into bank2's data slots and write
    generated/spill_*.asm include-lists — adding a level never touches
    bank2.asm. Greedy first-fit, big levels first; within a slot the
    index stays first (defines ROOM_NONE) and rooms sort ASC (stable
    addresses per slot). Overflow here = precheck also fails after build.
    """
    idx = "generated/levels_index.asm"
    rooms = sorted(p.name for p in generated.glob("level_*_rooms.asm"))
    sizes = {}
    for name in [Path(idx).name] + rooms:
        p = generated / Path(idx).name if name == Path(idx).name else generated / name
        sizes[name] = _gen_data_size(p)
    window_used = 0
    m = generated / "models_data.asm"
    if m.exists():
        window_used += _gen_data_size(m)
    for p in sorted(generated.glob("level_*_rooms_data.asm")):
        window_used += _gen_data_size(p)
    caps = {}
    for name, end in _SPILL_SLOTS:
        start = _SPILL_ORG.get(name)
        if start is None:                       # pad-derived constant starts
            start = {"spill_F767": 0xF767, "spill_F901": 0xF901,
                     "spill_F840": 0xF864}[name]
        cap = end - start
        if name == "spill_window":
            cap -= window_used
        caps[name] = cap
    order = [Path(idx).name] + sorted(rooms, reverse=True)  # big first
    placed: dict = {name: [] for name, _ in _SPILL_SLOTS}
    for item in order:
        sz = sizes[item]
        for name, _ in _SPILL_SLOTS:
            if sz <= caps[name]:
                caps[name] -= sz
                placed[name].append(item)
                break
        else:
            raise ValueError(
                f"spill overflow: {item} ({sz}B) fits no bank2 slot "
                f"(remaining caps: {caps}) — grow a gap or split the level")
    for name, files in placed.items():
        room_files = sorted(f for f in files if f != Path(idx).name)
        head = [f] if (f := Path(idx).name) in files else []
        lines = ["; Generated by convert_level.py --levels (bugs.md 27b)."
                 " Do not edit by hand.",
                 "; Include list for this bank2 gap — see emit_spills()."]
        for inc in head + room_files:
            lines.append(f'    include "generated/{inc}"')
        (generated / f"{name}.asm").write_text("\n".join(lines) + "\n")


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--levels":
        if len(argv) < 3:
            print("usage: convert_level.py --levels OUTPUT_INDEX_ASM LEVEL.json...",
                  file=sys.stderr)
            return 2
        output = Path(argv[1])
        try:
            write_levels_index(output, [Path(arg) for arg in argv[2:]])
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return 1
        print(f"wrote levels index -> {output}")
        return 0

    if len(argv) not in (2, 3):
        print("usage: convert_level.py INPUT.json OUTPUT_ASM_PREFIX [ROOMS_DIR]",
              file=sys.stderr)
        return 2
    json_path = Path(argv[0])
    out_prefix = Path(argv[1])
    rooms_dir = Path(argv[2]) if len(argv) > 2 else json_path.parent
    generated_dir = out_prefix.parent

    try:
        level = json.loads(json_path.read_text())
        if "level" in level:          # cereal wraps the level in an NVP
            level = level["level"]
        rooms = level["rooms"]
        rooms.sort(key=lambda r: r["room_id"])
    except (OSError, ValueError, KeyError) as error:
        print(f"failed to parse {json_path}: {error}", file=sys.stderr)
        return 1

    # Load models from models/models.json relative to the level file
    models_by_id = load_models(json_path.parent / "models" / "models.json")

    level_n = level_number_from_path(json_path) or int(level.get("level_id", 1))
    try:
        room_asms = []
        for index, room in enumerate(rooms):
            rows = rows_from_json(room, models_by_id)
            txt = rooms_dir / f"level_{level_n:03d}_room_{index + 1:03d}.txt"
            txt.write_text("\n".join(rows) + "\n")
            # Rooms with a model get their PF/rect data from the shared
            # M<id>* symbols in models_data.asm — no per-room copy.
            if models_by_id.get(room.get("model_id")) is None:
                asm = generated_dir / f"level_{level_n:03d}_room_{index + 1:03d}.asm"
                convert_room.emit(rows, asm, prefix=f"L{level_n}R{index + 1}",
                                  source=txt.name)
                room_asms.append(asm)

        connections = connection_bytes(rooms)
        tables = Path(str(out_prefix) + "_rooms.asm")
        write_tables(level, rooms, connections, tables, level_n, models_by_id)

        # Include list for every per-room data file still emitted (rooms
        # without a model). The game assembler needs only this single include
        # and picks up rooms added in the editor without editing bank0.asm.
        # Include paths are relative to the build working directory (the repo
        # root), matching the style used elsewhere.
        data_include = generated_dir / f"level_{level_n:03d}_rooms_data.asm"
        if room_asms:
            data_include.write_text(
                "\n".join(f'    include "{generated_dir.name}/{asm.name}"'
                          for asm in room_asms) + "\n")
        else:
            data_include.write_text(
                "; All rooms use shared model data (models_data.asm).\n")

        print(f"wrote {len(rooms)} room grids and tables -> {tables}")
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
