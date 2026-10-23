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

With `--stage STAGE.json OUTDIR [ROOMS_DIR]` the same outputs are produced from
ONE unified stage file (`{"stage": {"models": [...], "levels": [...]}}`; the
bare form is accepted too) whose `models` list replaces models/models.json and
whose `levels` array is the play order (level number = ordinal). E1 2026-10-20.

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
# C1 (2026-10-20): 2 = grid-position connections (1 B/room, exits derived).
# C2 (2026-10-20): 3 = shape-index room records. The per-room block word is
# gone: a room stores a 6-bit SHAPE INDEX (one byte column), the grid position
# and the enemy count; the block address comes from LEVEL_ShapeTable and the
# first enemy record is derived by summing the earlier rooms' counts.
# C5 (2026-10-20): 4 = async EXTRAS stream. A room record's b7 (owns-extras)
# + the count byte's extras index select a variable-length record in the
# level's extras stream (after the enemy records): flags, MetaA/MetaB,
# 1 B/patch, 1 B/feature, then [feature rooms] the room's FEATURE-record
# stream. That retired the per-room blocks and the `TilePF0+9/+10` meta
# contract: a room points at its shared model SHAPE and the loader (bank2
# ExtrasLoad) applies the patches/features and stages MetaA/MetaB.
# C3 (2026-10-20): 5 = ROW DICTIONARY. A shape block stores 3 one-byte
# row-pool indices (band 0/1/2) instead of the 9 raw PF bytes; the pool (3 B
# per DISTINCT row) is emitted once per game in models_data.asm as
# `RowPoolPF0/1/2` + `LEVEL_ROW_COUNT`.
# C11 (2026-10-21): 6 = PF-DERIVED HOT. The shape block is EXACTLY the 3 row
# indices — the hot count byte and the 5 B/record hot stream are gone (hot
# cells ARE the solid row-1 PF cells of a hot shape), band 1's index b7 carries
# `mid_band_type`, and the extras record stream keeps FEATURE records only
# (M1/hot records are derived). `HotOverlapBody` sweeps the expanded PF row 1.
LEVEL_FORMAT = 6
# New tile values (ai_new_tiles plan Phase 1). LOCKED_DOOR lives ONLY in
# asym_patches (side 0 = async ball strip, MetaB b7); the three grid tiles
# paint model cells and emit b7 feature records in the hot record stream.
LOCKED_DOOR = 9
PHASE = 10
VCRUNCH = 11                # RETIRED 2026-10-19 (vertical crunch removed)
HCRUNCH = 12
RAFT = 6                    # RAFT **tile**: a static row-2 platform
RAFT_ENTITY = 7             # RAFT **entity** (enemies[] type 7): the moving,
                            # rideable raft (plans/raft_moving_plan.md)
LAMP_ENTITY = 5             # wall lamp: the drawn art (bracket on its LEFT)
LAMP_MIRROR = 13            # wall lamp, MIRRORED design (bracket on its right).
                            # b3-0 carries the type, so 8-15 are free; the kernel
                            # maps both to `cmp #LAMP` with `and #%00000111`.
MAGMA_FALL = 7
FEATURE_TILES = (PHASE, HCRUNCH)
FEATURE_NAME = {PHASE: "phase", HCRUNCH: "hcrunch"}
VCRUNCH_REMOVED = "tile 11 (VCRUNCH) removed; use PHASE 10"
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
        raise ValueError(VCRUNCH_REMOVED)
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


def room_who(room: dict) -> str:
    """Human identity for an error message (async lives on the ROOM now)."""
    return f"room {room.get('room_id', '?')} (model {room.get('model_id', '?')})"


def room_patches(room: dict) -> list:
    """Room-level async strips — relocated from ModelData 2026-10-17 so one
    model shape can be reused by rooms with different async walls."""
    patches = room.get("asym_patches") or []
    if not isinstance(patches, list):
        raise ValueError(f"{room_who(room)}: asym_patches must be a list")
    return patches


def room_feature_cells(room: dict) -> list[tuple[int, int, int]]:
    """Room-level P/V/C cells: [[row, col, tile], ...] -> [(row, col, tile)].

    Feature tiles are no longer model grid tiles: the model keeps the SHAPE
    (a feature cell's model tile migrates to SOLID_WALL, same PF byte) and the
    room supplies the behaviour cells. One special kind per room, row 1 only
    (user rules R1/R2, 2026-10-14)."""
    who = room_who(room)
    out: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int]] = set()
    for cell in room.get("feature_cells") or []:
        if not (isinstance(cell, (list, tuple)) and len(cell) == 3
                and all(isinstance(v, int) for v in cell)):
            raise ValueError(
                f"{who}: feature cell {cell!r} must be [row, col, tile]")
        row, col, tile = cell
        if tile == VCRUNCH:
            raise ValueError(f"{who}: {VCRUNCH_REMOVED}")
        if tile not in FEATURE_TILES:
            raise ValueError(
                f"{who}: feature tile {tile} is not a feature tile "
                f"({FEATURE_NAME} — 10/12)")
        if not 0 <= row < HEIGHT:
            raise ValueError(f"{who}: feature row {row} out of 0..{HEIGHT - 1}")
        if not 0 <= col < WIDTH:
            raise ValueError(
                f"{who}: feature col {col} out of 0..{WIDTH - 1} (D7 grid)")
        if row != 1:
            raise ValueError(
                f"{who}: {FEATURE_NAME[tile]} at row {row} — special features "
                "live on the middle band (row 1)")
        if (row, col) in seen:
            raise ValueError(f"{who}: duplicate feature cell (row {row}, col {col})")
        seen.add((row, col))
        out.append((row, col, tile))
    # NOTE: the "one special kind per room" rule is NOT enforced here — the
    # per-cell list is also used to probe mixed grids. convert_room.lines()
    # (special_kinds) and verify_build's room loop own that gate.
    return out


def room_door_flag(room: dict) -> bool:
    """True when the ROOM carries a LOCKED_DOOR async strip (was MetaB b7)."""
    return any(
        len(p) >= 3 and p[2] == LOCKED_DOOR
        and (p[3] if len(p) == 4 else 0) == 0
        for p in room_patches(room)
    )


def room_m1_door_flag(room: dict) -> bool:
    """True when the ROOM carries a LOCKED_DOOR door (MetaA b3).

    Since Phase 5 (2026-10-17) BOTH halves use the M1 strip: a side-1 door is
    the left door, a side-0 door is authored as the right door (MetaA b0=1).
    """
    return any(
        len(p) >= 3 and p[2] == LOCKED_DOOR
        for p in room_patches(room)
    )


def async_kinds(room: dict) -> list[str]:
    """Special-feature kinds present in a ROOM's async: door first, then
    phase/hcrunch by tile id."""
    kinds: list[str] = []
    if room_door_flag(room):
        kinds.append("door")
    for t in sorted({c[2] for c in room_feature_cells(room)}):
        if t in FEATURE_NAME:
            kinds.append(FEATURE_NAME[t])
    return kinds


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
    # blinking are mutually exclusive). Hcrunch is allowed on hot: its cells
    # keep the 'C' char (the band's other cells are H).
    hot = bool((model if model else room).get("mid_band_type", 0))
    who = room_who(room)
    feats = {(r, c): t for r, c, t in room_feature_cells(room)}
    if feats and hot and any(t == PHASE for t in feats.values()):
        raise ValueError(
            f"{who}: phase on the hot middle band — hot and blinking are "
            "mutually exclusive (turn the hot flag off)")
    rows = []
    for y in range(HEIGHT):
        line = []
        for x in range(WIDTH):
            t = tiles[y * WIDTH + x]
            if t == LOCKED_DOOR:
                raise ValueError(
                    f"{who}: tile 9 LOCKED_DOOR belongs in asym_patches "
                    "(async strip), not the grid")
            if t in FEATURE_TILES:
                raise ValueError(
                    f"{who}: model grid carries feature tile "
                    f"{FEATURE_NAME[t]} — features live on the ROOM now "
                    "(room.feature_cells); migrate with "
                    "tools/migrate_async_to_rooms.py")
            if (y, x) in feats:
                line.append(tile_to_char(feats[(y, x)]))
            elif y == 1 and hot and t != 0:
                line.append("H")
            else:
                line.append(tile_to_char(t))
        rows.append("".join(line))
    return rows


def resolve_asym_patches(model: dict, room: dict,
                         left_rows: list[str]
                         ) -> tuple[list[str] | None, int, int, bool, bool] | None:
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
    patches = room_patches(room)
    if not patches:
        return None
    mid = model.get("id")
    who = room_who(room)
    if len(patches) > 2:
        raise ValueError(
            f"{who}: {len(patches)} asym patches — envelope allows "
            f"TWO blocks max (stacked on two bands, or a pair on one band)")
    right_cols: set[int] = set()
    left_cols: set[int] = set()
    left_patch_rows: set[int] = set()
    seen: set[tuple[int, int, int]] = set()
    has_right = False
    m1_door_right = False
    right = ["".join(left_rows[y][WIDTH - 1 - k] for k in range(WIDTH))
             for y in range(HEIGHT)]
    for p in patches:
        if not (isinstance(p, (list, tuple)) and len(p) in (3, 4)
                and all(isinstance(v, int) for v in p)):
            raise ValueError(
                f"{who}: asym patch {p!r} must be [row, col, tile] or "
                f"[row, col, tile, side] (side 0 = right/ball, 1 = left/M1)")
        side = p[3] if len(p) == 4 else 0
        if side not in (0, 1):
            raise ValueError(
                f"{who}: patch {p!r} side {side} not in 0 (right/ball) "
                f"1 (left/M1)")
        row, col, tile = p[0], p[1], p[2]
        if (row, col, side) in seen:
            raise ValueError(
                f"{who}: duplicate asym patch (row {row}, col {col}, "
                f"side {side}) — the same cell twice is one block")
        seen.add((row, col, side))
        if tile in FEATURE_TILES:
            raise ValueError(
                f"{who}: tile {tile} is a grid tile — feature tiles "
                "(phase/hcrunch) cannot be asym patches")
        if tile == LOCKED_DOOR:
            if row != 1:
                raise ValueError(
                    f"{who}: LOCKED_DOOR patch at row {row} — the "
                    "door lives on the middle band (row 1)")
            if model.get("mid_band_type"):
                raise ValueError(
                    f"{who}: LOCKED_DOOR on the hot middle band — "
                    "turn the hot flag off (door and hot are mutually "
                    "exclusive)")
        if not 0 <= row < HEIGHT:
            raise ValueError(f"{who}: patch row {row} out of 0..{HEIGHT - 1}")
        if not 0 <= col < WIDTH:
            raise ValueError(
                f"{who}: patch col {col} out of 0..{WIDTH - 1} (D7 grid)")
        char = tile_to_char(tile)
        if side == 0 and tile == LOCKED_DOOR:
            # Phase 5: a RIGHT-half door is drawn by the M1 strip (yellow
            # COLUP1, OvM1Block collision, key touch-unlock), positioned on
            # the right by MetaA b0=1 (bank2 StageBandTab M1OffTab). No ball.
            m1_door_right = True
            left_cols.add(col)
            left_patch_rows.add(row)
            continue
        if side == 1:
            # M1: paints wall-colored color over an OPEN left cell.
            if char not in "#H":
                raise ValueError(
                    f"{who}: M1 patch at row {row} col {col} must paint "
                    f"a wall tile (M1 only adds color, tile {tile!r} is open)")
            left_cols.add(col)
            left_patch_rows.add(row)
            continue
        mirror = left_rows[row][WIDTH - 1 - col]
        if char == "." and mirror in "#H":
            raise ValueError(
                f"{who}: subtractive patch at row {row} col {col} "
                f"(opens a cell whose mirror is wall — D6 is additive-only)")
        right_cols.add(col)
        has_right = True
        right[row] = right[row][:col] + char + right[row][col + 1:]
    if len(right_cols) > 1:
        raise ValueError(
            f"{who}: ball patches span columns {sorted(right_cols)} — "
            f"envelope allows exactly ONE column-x per side (single ball x; "
            f"a run wider than 1 cell needs >1 column and is rejected too)")
    side0_tiles = {p[2] for p in patches
                   if len(p) >= 3 and (p[3] if len(p) == 4 else 0) == 0}
    if LOCKED_DOOR in side0_tiles and len(side0_tiles) > 1:
        others = sorted(t for t in side0_tiles if t != LOCKED_DOOR)
        raise ValueError(
            f"{who}: side-0 patches mix LOCKED_DOOR with tile(s) "
            f"{others} — a door model's async patches must ALL be "
            "LOCKED_DOOR")
    side1_tiles = {p[2] for p in patches if len(p) >= 4 and p[3] == 1}
    if LOCKED_DOOR in side1_tiles and len(side1_tiles) > 1:
        others = sorted(t for t in side1_tiles if t != LOCKED_DOOR)
        raise ValueError(
            f"{who}: side-1 patches mix LOCKED_DOOR with tile(s) "
            f"{others} — a door model's M1 patches must ALL be LOCKED_DOOR")
    m1_door = (LOCKED_DOOR in side1_tiles) or m1_door_right
    if len(left_cols) > 1:
        raise ValueError(
            f"{who}: M1 patches span columns {sorted(left_cols)} — "
            f"envelope allows exactly ONE column-x per side (single M1 x)")
    m1_x = 0
    if left_cols:
        m1_col = next(iter(left_cols))
        # A right-half door's M1 bar sits at x = 87+8*col, but its wall-hide
        # depends on the reflected PF as well: one of {col, WIDTH-1-col} can
        # be open while the other is wall, and ENAM1 latches the WHOLE cave —
        # so require BOTH columns to satisfy the envelope for a right door.
        cols = ({m1_col, WIDTH - 1 - m1_col} if m1_door_right else {m1_col})
        for b in range(HEIGHT):
            for cc in sorted(cols):
                cell = left_rows[b][cc]
                if b in left_patch_rows and cell in "#H":
                    raise ValueError(
                        f"{who}: M1 patch band {b} col {cc} is wall — "
                        f"the whole-cave ENAM1 latch would hide the patch "
                        f"(wall-hide guard)")
                if b not in left_patch_rows and cell not in "#H":
                    raise ValueError(
                        f"{who}: M1 cell col {cc} is open in band {b} "
                        f"with no patch — the whole-cave ENAM1 latch would "
                        f"paint it (wall-hide guard: wall the cell or patch "
                        f"the band)")
        m1_x = 7 + 8 * m1_col
    ball_x = 87 + 8 * next(iter(right_cols)) if has_right else 0
    if has_right and model.get("mid_band_type"):
        # Ball patch cells on row 1 follow the middle-band selector too
        # (rows_from_json already promoted the mirrored base cells).
        right[1] = "".join("H" if c == "#" else c for c in right[1])
    return (right if has_right else None), ball_x, m1_x, m1_door, m1_door_right


def model_specials(model: dict) -> list[str]:
    """Special-feature kinds still encoded on a MODEL — must be EMPTY since
    the async move (2026-10-17). Kept as the migration tripwire."""
    kinds: list[str] = []
    if model.get("asym_patches"):
        kinds.append("door/strip")
    for t in sorted(set(model.get("tiles") or [])):
        if t in FEATURE_NAME:
            kinds.append(FEATURE_NAME[t])
    return kinds


def check_model_objects(model: dict, who: str) -> None:
    """MODEL-level static rules + the async-migration tripwire.

    Async (asym strips + feature cells) lives on the ROOM since 2026-10-17, so
    a model carrying either key is stale data: the per-room rules (special
    alone, object caps) are enforced in check_rooms_against_models instead.
    Raft stays model-level (it is a static grid object, row 2 only)."""
    stale = model_specials(model)
    if stale:
        raise ValueError(
            f"{who}: model still carries async {stale} — async lives on the "
            "ROOM now (room.asym_patches / room.feature_cells); migrate with "
            "tools/migrate_async_to_rooms.py")
    w = int(model.get("width", WIDTH))
    tiles = model.get("tiles") or []
    for i, t in enumerate(tiles):
        if t == RAFT and i // w != 2:
            raise ValueError(
                f"{who}: RAFT at row {i // w} — the raft lives on the "
                "bottom band (row 2, the water strip)")


BAND_RULE_HARD = False   # flip to True once the live stage has no violators
_BAND_WARNED: set[str] = set()   # one line per room (the pass runs twice)


def check_rooms_against_models(rooms: list[dict], models_by_id: dict,
                               who_prefix: str,
                               miner_room: int = -1,
                               miner_y: float | None = None) -> None:
    """Per-room object rules against the room's model special (2026-10-14).

    hcrunch rooms: no objects at all. Door rooms: at most one
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
        kinds = async_kinds(room)
        enemies = room.get("enemies") or []
        lamps = room.get("lamps") or []
        miner = miner_room == index
        if "hcrunch" in kinds:
            if enemies or lamps or miner:
                raise ValueError(
                    f"{who}: hcrunch room has objects (enemies/lamps/miner) "
                    "— the crunch band needs the sprite slot")
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
        # --- one object per 48-line BAND, the miner included -----------------
        # The kernel has ONE GRP1: StageSlot1 pairs two objects only when they
        # are in different bands (tools/test_slot1_pair.py). Two objects on the
        # same scanlines keep the 30 Hz rotation, which reads as flicker.
        # Tile row -> px = row*12, band = px//48 = row//4.
        seated = [(f"enemy {i}", float(e.get("y", 0)))
                  for i, e in enumerate(enemies)]
        seated += [(f"lamp {i}", float(l.get("y", 0)))
                   for i, l in enumerate(lamps)]
        if miner and miner_y is not None:
            seated.append(("the miner", float(miner_y)))
        bands: dict[int, list[str]] = {}
        for what, tile in seated:
            bands.setdefault(int(tile) // 4, []).append(what)
        for band, whats in sorted(bands.items()):
            if len(whats) > 1:
                msg = (f"{who}: {len(whats)} objects in band {band} "
                       f"({', '.join(whats)}) — one GRP1 cannot draw them on "
                       "the same scanlines; move one into another band "
                       "(the miner counts as an occupant)")
                if BAND_RULE_HARD:
                    raise ValueError(msg)
                if msg not in _BAND_WARNED:
                    _BAND_WARNED.add(msg)
                    print(f"WARN: {msg}")
        tiles = model.get("tiles") or []
        if any(t == RAFT for t in tiles) and not room.get("bottom_band"):
            raise ValueError(
                f"{who}: model has RAFT tiles but the room is not water "
                "(bottom_band=false)")
        bottom_rows = None
        for e in enemies:
            etype = int(e.get("type", 0))
            if etype not in (3, RAFT_ENTITY):   # TENTACLE / RAFT
                continue
            what = "tentacle" if etype == 3 else "raft"
            if not room.get("bottom_band"):
                raise ValueError(
                    f"{who}: {what} in a room without the bottom band — "
                    f"{what}s live in the water")
            row = int(float(e.get("y", 0))) // 4
            if row != 2:
                raise ValueError(
                    f"{who}: {what} at display row {e.get('y')} — {what}s "
                    "live on the bottom band (model row 2)")
            if etype != RAFT_ENTITY:
                continue
            # The moving raft floats on OPEN water: its spawn cell must be
            # water (an open model cell), never a ledge/wall, so it can start
            # patrolling immediately (user rule: "placed only above water").
            if bottom_rows is None:
                bottom_rows = rows_from_json(room, models_by_id)
            ex = float(e.get("x", 0))
            if not 0 <= ex <= 39:
                raise ValueError(f"{who}: raft x={e.get('x')} out of 0..39")
            dcol = int(ex)
            cell = dcol // 2 if dcol < 20 else (39 - dcol) // 2
            if bottom_rows[2][cell] != ".":
                raise ValueError(
                    f"{who}: raft at display col {dcol} sits on "
                    f"{bottom_rows[2][cell]!r} — the raft floats on OPEN "
                    "water (paint the cell as air)")


# C1 (2026-10-20) — grid-position connections (LEVEL_FORMAT = 2).
# A room stores ONE byte: (x - level_min_x) << 4 | (y - level_min_y), each
# nibble 0..14. Nibble 15 is the "no room" sentinel and is never emitted, so
# the runtime exit scan can step a neighbour position with plain byte
# arithmetic: a wrap at a grid edge (x-1 at x=0, y+1 at y=14, ...) always
# lands in a nibble-15 byte, which no room owns -> "no exit", with no guard
# code. Per-axis span 15 (225 cells), i.e. up to 20 rooms/level with room to
# spare (the old nibble-room-index pack capped a level at 15 ROOMS).
POSITION_SPAN = 15


def position_bytes(rooms: list[dict]) -> list[int]:
    """Per-room `(x<<4|y)` grid-position byte, normalised to the level origin.

    Connections are NOT stored any more: they are the JSON's room_x/room_y
    adjacency, resolved at run time by scanning this column (bank2
    ExitScanB2, cold path). Normalising per level keeps adjacency while
    letting a level sit anywhere in the editor grid (level 4 uses room_x=-1).
    """
    xs = [int(room.get("room_x", 0)) for room in rooms]
    ys = [int(room.get("room_y", 0)) for room in rooms]
    if not rooms:
        raise ValueError("level has no rooms")
    min_x, min_y = min(xs), min(ys)
    span_x, span_y = max(xs) - min_x, max(ys) - min_y
    if span_x >= POSITION_SPAN or span_y >= POSITION_SPAN:
        raise ValueError(
            f"level spans {span_x + 1} columns x {span_y + 1} rows — the "
            f"grid-position byte supports {POSITION_SPAN} x {POSITION_SPAN} "
            "cells (nibble 15 is the no-room sentinel); move the rooms closer")
    result: list[int] = []
    owner: dict[int, int] = {}
    for index, room in enumerate(rooms):
        pos = ((int(room.get("room_x", 0)) - min_x) << 4) | (
            int(room.get("room_y", 0)) - min_y)
        if pos in owner:
            raise ValueError(
                f"rooms {owner[pos]} and {index} share grid position "
                f"({room.get('room_x')}, {room.get('room_y')}) — exits are "
                "resolved by scanning positions, so positions must be unique")
        owner[pos] = index
        result.append(pos)
    return result


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


# --- C5 (2026-10-20): async extras records ---------------------------------
# Feature kind nibble in the 1 B/feature entries (the record class byte in the
# extras FEATURE record stream is $80 phase / $82 hcrunch; the extras byte
# uses compact kinds).
EXTRAS_PHASE = 1
EXTRAS_HCRUNCH = 2


def _parse_hot_line(line: str) -> list[int]:
    """`  .byte $08, 4, 1, 2, 1  ; note` -> [8, 4, 1, 2, 1]."""
    payload = line.split(".byte", 1)[1].split(";")[0]
    return [int(v.strip().lstrip("$"), 16) for v in payload.split(",")]


def room_extras(room: dict, model: dict, rows: list[str],
                who: str) -> tuple[bytes, int]:
    """Build one C5 extras record for an async room: (bytes, n_features).

    Layout: flags, MetaA, MetaB, 1 B/patch, 1 B/feature, then [features] the
    room's FEATURE-record stream (count + 5 B records).
    The meta pair is the retired `TilePF0+9/+10` payload; the patch list is
    the live geometry the loader derives the MetaA band mask from (asserted
    here so the two encodings cannot drift).

    C11 (2026-10-21): the record stream holds FEATURE records only ($80 phase
    / $82 hcrunch) — the shape's static hot cells and the M1 block cell are
    no longer copied here. Hot collision is derived from the PF row 1 the
    loader expands (a feature room's phase/hcrunch cells MOVE PF bits every
    VBL, so the live PF is the correct source), and the M1 block cell is
    re-derived from the patch list at load (`RoomM1Hot`).
    """
    res = resolve_asym_patches(model, room, rows)
    asym, ball_x, m1_x, m1_door, m1_right = (
        res if res else (None, 0, 0, False, False))
    hot = bool(model.get("mid_band_type"))
    meta_a, meta_b = convert_room.meta_bytes(
        rows, asym_rows=asym, asym_ball_x=ball_x, asym_m1_x=m1_x,
        hot=hot, door=False, m1_door=m1_door, m1_right=m1_right, source=who)
    patch_bytes: list[int] = []
    derived_mask = 0
    for patch in room_patches(room):
        row, col = patch[0], patch[1]
        side = patch[3] if len(patch) == 4 else 0
        patch_bytes.append((row << 6) | (side << 4) | col)
        if side == 0:
            derived_mask |= 1 << row   # ball band gate (MetaA b0-2)
    if (meta_a & 0x07) != derived_mask:
        raise ValueError(
            f"{who}: MetaA band mask ${meta_a & 0x07:02x} != the side-0 patch "
            f"rows ${derived_mask:02x} — the extras patch list and the packed "
            "meta drifted")
    feats = room_feature_cells(room)
    feature_bytes: list[int] = []
    if feats:
        kinds = {t for _r, _c, t in feats}
        if len(kinds) != 1:
            raise ValueError(
                f"{who}: mixed special features {sorted(kinds)} — special "
                "features are alone per room")
        kind = kinds.pop()
        if room_door_flag(room):
            raise ValueError(
                f"{who}: door and feature cells in one room (door XOR "
                "phase XOR hcrunch)")
        if kind == HCRUNCH:
            cols = sorted(c for _r, c, _t in feats)
            feature_bytes.append((EXTRAS_HCRUNCH << 6) | cols[-1])
        else:
            for _r, col, _t in sorted(feats, key=lambda f: f[1]):
                feature_bytes.append((EXTRAS_PHASE << 6) | col)
    if len(patch_bytes) > 3:
        raise ValueError(f"{who}: {len(patch_bytes)} extras patches > 3 "
                         "(flags b1-0)")
    if len(feature_bytes) > 15:
        raise ValueError(f"{who}: {len(feature_bytes)} feature bytes > 15 "
                         "(flags b5-2)")
    out = bytearray([len(patch_bytes) | (len(feature_bytes) << 2),
                     meta_a, meta_b])
    out += bytes(patch_bytes)
    out += bytes(feature_bytes)
    if feature_bytes:
        _hot_lines, feat_lines = convert_room.hot_records(
            rows, hot_m1=(), hot=hot, door=False, source=who)
        records = [_parse_hot_line(line) for line in feat_lines]
        out.append(len(records))
        for record in records:
            out += bytes(record)
    return bytes(out), len(feature_bytes)


def extras_record_lines(record: bytes, n_features: int, note: str) -> list[str]:
    """One `.byte` block for an extras record, with per-section comments."""
    flags = record[0]
    n_patch = flags & 0x03
    comment = (f"  ; {note}: {n_patch} patch(es), {n_features} feature(s)"
               f", MetaA ${record[1]:02x} MetaB ${record[2]:02x}")
    return [f"  .byte " + ", ".join(f"${b:02x}" for b in record) + comment]


def write_tables(level: dict, rooms: list[dict], positions: list[int],
                 output: Path, level_n: int, models_by_id: dict = None) -> None:
    prefix = f"LEVEL{level_n}"
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
                               int(level.get("miner_room", 0)) & 0x7F,
                               level.get("miner_y", 0))
    lines = [
        f"; Generated from {level.get('name', 'level')} (level {level_n}). "
        "Do not edit by hand."
    ]
    # (d) 2026-10-20: start_room and miner_y left the per-level entry — the
    # kernel uses the constants 0 / 84 (start x/y did the same on 2026-10-19).
    # Hard-fail instead of silently dropping an authored value.
    if int(level.get("start_room", 0)) != 0:
        raise ValueError(
            f"level {level_n}: start_room = {level.get('start_room')} but the "
            "level entry no longer stores it (kernel constant 0)")
    if px(int(level.get("miner_y", 0)), 12) != 84:
        raise ValueError(
            f"level {level_n}: miner_y = {level.get('miner_y')} rows but the "
            "level entry no longer stores it (kernel constant 84 px = 7 rows)")
    lines += [
        f"{prefix}_START_ROOM = {level.get('start_room', 0)}",
        f"{prefix}_WALL_COLOR = ${wall:02x}",
        f"{prefix}_WALL_COLOR2 = ${wall2:02x}",
        f"{prefix}_MINER_ROOM = {miner_room}",
        f"{prefix}_MINER_X = {enemy_x_px(float(level.get('miner_x', 0)) * 2)}",
        f"{prefix}_MINER_Y = {px(level.get('miner_y', 0), 12)}",
        "",
    ]
    lines += [
        "; Room shape index (C2 2026-10-20): ONE byte per room =",
        ";   b5-0 SHAPE INDEX into LEVEL_ShapeTable (levels_index.asm)",
        ";   b6   bottom-band flag",
        ";   b7   owns-extras (C5): the room has a record in the level's",
        ";        AsyncExtras stream (selected by the counts byte's b5-0)",
        "; C5 (2026-10-20): an async room points at its SHARED MODEL shape;",
        "; the patches/features/meta come from the extras record, so there are",
        "; no per-room blocks any more. A room without a model is rejected",
        "; (the shape must be shared). C11 (2026-10-21): block = 3 row-pool",
        "; indices — the hot count/stream is gone (hot derives from PF row 1).",
        f"{prefix}_RoomShapes:",
    ]
    extras_index: dict[int, int] = {}
    extras_lines: list[str] = []
    for index, room in enumerate(rooms):
        model = models_by_id.get(room.get("model_id")) if models_by_id else None
        if model is None:
            raise ValueError(
                f"level {level_n} room {index}: no model_id — C5 needs a "
                "shared model shape for every room")
        shape = f"SHAPE_M{model['id']}"
        async_room = room_has_async(room)
        why = "async extras" if async_room else f"model {model['id']}"
        flags = (0x40 if _room_bottom_color(room) else 0) | (
            0x80 if async_room else 0)
        value = f"{shape} | ${flags:02x}" if flags else shape
        lines.append(f"  .byte {value} ; room {index} ({why})")
        if not async_room:
            continue
        rows = rows_from_json(room, models_by_id)
        record, nfeat = room_extras(room, model, rows,
                                    f"level {level_n} room {index}")
        extras_index[index] = len(extras_index) + 1
        extras_lines += extras_record_lines(record, nfeat,
                                            f"room {index}")
    lines.append("")
    lines.append(
        "; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,")
    lines.append(
        "; (x<<4 | y) normalised to the level origin. Exits are DERIVED at")
    lines.append(
        "; room load by scanning this column (bank2 ExitScanB2), so no")
    lines.append(
        "; connection bytes are stored: a nibble of 15 never occurs and marks")
    lines.append("; a neighbour outside the grid.")
    lines.append(f"{prefix}_RoomPositions:")
    for index, pos in enumerate(positions):
        lines.append(f"  .byte ${pos:02x} ; room {index} "
                     f"({pos >> 4}, {pos & 0x0F})")
    lines += _enemy_tables(prefix, rooms, extras_index, models_by_id)
    output.write_text("\n".join(lines) + "\n")

    # C7 (2026-10-20): the async EXTRAS stream is its OWN file now, because it
    # lives in BANK3 with the shapes and the walkers that read it every VBL
    # (a feature room's FEATURE-record stream sits inside the record — record
    # walkers and record data must share a bank, and a fold on the VBL path is
    # 25c/byte).
    # The space it used to take in the level's bank2 table block comes back to
    # the table slots, so net level data is unchanged.
    extras_path = output.with_name(
        output.name.replace("_rooms.asm", "_extras.asm"))
    if extras_lines:
        extras_head = [
            f"; Generated from {level.get('name', 'level')} (level {level_n}).",
            "; Do not edit by hand. C7 (2026-10-20): bank3 async EXTRAS stream —",
            "; one record per owns-extras room, in room order (the counts byte's",
            "; b5-0 is the 1-based ORDINAL). Record layout:",
            ";   +0 flags: n_patches b1-0 | n_features b5-2",
            ";   +1 MetaA  +2 MetaB  (the retired TilePF0+9/+10 pair — the",
            ";      loader stages it into $99/$9A)",
            ";   +3.. 1 B/patch: row b7-6 | side b4 | col b3-0 (tile = wall)",
            ";   ..   1 B/feature: kind b7-6 (1 = phase, 2 = hcrunch",
            ";        prefix end) | col b3-0",
            ";   ..   [n_features > 0] 1 B count + 5 B/FEATURE record — the",
            ";        live feature geometry ($80 phase cell / $82 hcrunch",
            ";        prefix). Static hot + the M1 block cell are derived by",
            ";        the loader (PF row 1 + the patch list) — C11.",
            f"{prefix}_AsyncExtras:",
        ] + extras_lines
    else:
        extras_head = [
            f"; Generated from {level.get('name', 'level')} (level {level_n}).",
            "; C7 (2026-10-20): no async rooms in this level — the label is a",
            "; ZERO so levels_extras.asm can index every level uniformly (the",
            "; loader never dereferences it: no room has b7 set).",
            f"{prefix}_AsyncExtras = 0",
        ]
    extras_path.write_text("\n".join(extras_head) + "\n")

    # C5 (2026-10-20): the per-room async blocks are RETIRED (the extras
    # stream above replaces them). Keep writing the *_blocks.asm file as a
    # comment-only stub so the include list / tooling keeps resolving.
    block_lines = [
        f"; Generated from {level.get('name', 'level')} (level {level_n}).",
        "; C5 (2026-10-20): per-room blocks RETIRED — async rooms point at",
        "; their shared model shape and carry an async-extras record instead.",
    ]
    blocks_path = output.with_name(
        output.name.replace("_rooms.asm", "_blocks.asm"))
    blocks_path.write_text("\n".join(block_lines) + "\n")


# Runtime ceiling for a room's enemies+lamps: EnemyRamX has only 3 slots —
# slot 3 would collide with LaserState at $C0 (docs/zp_layout_skill.md).
# The POLICY cap is 2 objects/room (editor kMaxRoomElements=2, verify_build
# enemies+lamps <=2); this slice only guards the hardware slot bound.
MAX_ENEMIES = 3
# Per-enemy byte layout in LEVEL{n}_EnemyDataTable (see _enemy_tables).
ENEMY_STRIDE = 3  # S4.1: 6 -> 4 (range_min/range_max dropped from ROM, dead:
                  # kernel skips them); 2026-10-21: 4 -> 3 (dir packed into
                  # type's b7: 1 = left). Layout = type|dir, x, y.


# A level with no bottom_band room still needs a BAND_COLOR equ for the
# generated index comment; the flag is never set, so the value is inert.
BAND_COLOR_FALLBACK = 1


def _room_bottom_color(room: dict) -> int:
    """Bottom-band TIA color byte for a room (0 = band off)."""
    if not room.get("bottom_band"):
        return 0
    color = nearest_byte(
        int(room.get("bottom_r", 0)),
        int(room.get("bottom_g", 0)),
        int(room.get("bottom_b", 0)))
    return color if color != 0 else 1  # never emit 0 when band is on


def _lamp_type(room: dict, col: float, y: float, models_by_id: dict | None) -> int:
    """Which lamp DESIGN this placement uses (user 2026-10-22).

    The art carries its wall bracket on the LEFT, i.e. the lamp faces right.
    A lamp whose wall is on its right therefore needs the mirrored design,
    which is enemy TYPE 13 (the kernel maps 5 and 13 to the same lamp).

    The editor stores a lamp at the centre of its 8 px cell. Display columns
    are 4 px and the stage is mirrored (cols 20-39 map back to 19..0), so the
    logical cell is (col if col < 20 else 39 - col) // 2 — 10 cells per half.
    A screen edge counts as a wall.
    """
    model = models_by_id.get(room.get("model_id")) if models_by_id else None
    src = model or room
    tiles = src.get("tiles") or []
    width = int(src.get("width", WIDTH))
    if len(tiles) != width * HEIGHT:
        return LAMP_ENTITY              # no grid to read: keep the drawn art
    band = max(0, min(int(y) // 4, HEIGHT - 1))   # 4 rows of 12 px per band
    c = int(round(float(col)))
    logical = c if c < 20 else 39 - c              # mirrored stage: 39-c
    cell = min(logical // 2, width - 1)            # 2 display cols per cell

    def solid(cell_index: int) -> bool:
        return tiles[band * width + cell_index] != 0

    left = solid(cell - 1) if cell > 0 else True   # screen edge counts as wall
    right = solid(cell + 1) if cell < width - 1 else True
    if right and not left:
        return LAMP_MIRROR                        # wall on the right: mirror
    return LAMP_ENTITY


def _enemy_tables(prefix: str, rooms: list[dict],
                  extras_index: dict[int, int] | None = None,
                  models_by_id: dict | None = None) -> list[str]:
    """Emit the level's per-room enemy counts and its flat enemy table.

    Enemies are positioned in EDITOR stage coordinates: x is a full-stage
    display column (0..39 across both mirror halves, so the game screens can
    differ per side) and y is a room row (0..11). Column -> room pixel uses
    4 px/column (one playfield block), row -> scanline uses 12 px/row,
    matching the existing level/miner coordinate conversion. Lamp x is stored
    at the tile center and shifted left by half its 4px sprite width.

    LEVEL{n}_EnemyDataTable is a flat list of ENEMY_STRIDE-byte records:
    byte 0 = type (b3-0) | dir (b7: 1 = left, matching the old $FF dir byte),
    byte 1 = x, byte 2 = y (2026-10-21: 3 B; range_min/range_max dropped from
    ROM in S4.1 — nothing read them; the editor JSON still carries those).

    LEVEL{n}_RoomCounts has one byte per room (C2 2026-10-20):
    (count << 6 | extras index). The records stay contiguous in room order,
    so the FIRST record index is DERIVED at room load by summing the counts
    of the rooms before it (bank2 EnterRoomB2) — the old packed index field
    capped a level at 31 records and is gone. C5 (2026-10-20): the low six
    bits are the room's 1-based ORDINAL in the level's AsyncExtras stream
    (0 = no extras); the band flag lives in the shape column.
    """
    flat: list[tuple[int, int, int, int]] = []
    counts: list[int] = []
    extras_index = extras_index or {}
    # Lamp entries are merged into the enemy table as type 5 (kernel LAMP) or
    # 13 (the wall-mirrored design; see _lamp_type).
    LAMP_TYPE = LAMP_ENTITY
    for index, room in enumerate(rooms):
        entities = [e for e in (room.get("enemies") or [])]
        for lamp in (room.get("lamps") or []):
            entities.append({
                # 5 = drawn art, 13 = its mirror: chosen from the wall the lamp
                # hangs on, so no dir bit is needed (a b7-set lamp used to slip
                # past the raw `cmp #LAMP` guards in the laser bodies).
                "type": _lamp_type(room, lamp.get("x", 0), lamp.get("y", 0),
                                   models_by_id),
                "x": lamp.get("x", 0),
                "y": lamp.get("y", 0),
                "dir": 0,
            })
        entities = entities[:MAX_ENEMIES]
        counts.append(len(entities))
        for enemy in entities:
            type_ = int(enemy.get("type", 0))
            x = float(enemy.get("x", 0))
            if type_ in (LAMP_ENTITY, LAMP_MIRROR):
                x -= 0.5  # editor stores lamp center; GRP1 data is left-aligned
            # The RAFT has no authored direction either: its dir bit lives in
            # EnemyRamD and only seeds the first patrol leg. Emitting b7 made
            # `cmp #RAFT` in the bomb blast miss, so a dir=right raft could be
            # destroyed by its own rider's bomb.
            direction = 0 if type_ == RAFT_ENTITY else int(enemy.get("dir", 1))
            flat.append((
                type_,
                enemy_x_px(x),
                px(float(enemy.get("y", 0)), 12),
                direction,
            ))
    lines = [""]
    lines += [
        "; Per-room enemy count (C2 2026-10-20): ONE byte = count<<6 |",
        "; extras ordinal (C5: 1-based index into LEVELn_AsyncExtras, 0 =",
        "; none; the enemy record index is derived at room load).",
        f"{prefix}_RoomCounts:",
    ]
    for index, count in enumerate(counts):
        assert count <= 3, f"{prefix}: room {index} has {count} records (>3)"
        packed = (count << 6) | extras_index.get(index, 0)
        lines.append(
            f"  .byte ${packed:02x} ; room {index}: {count} record(s)"
            + (f", extras {extras_index[index]}"
               if index in extras_index else ""))
    lines += [
        "",
        f"; Enemy data: {len(flat)} enemy records across {len(rooms)} rooms, "
        f"{ENEMY_STRIDE} bytes each (type|dir, x, y).",
        f"{prefix}_EnemyDataTable:",
    ]
    for type_, x, y, dir_ in flat:
        assert 0 <= type_ <= 13, f"{prefix}: enemy type {type_} does not fit b3-0"
        packed = type_ | (0x80 if dir_ < 0 else 0)
        lines.append(f"  .byte ${packed:02x}, {x}, {y}")
    return lines


def emit_room_block(prefix: str, room: dict, model: dict, rows: list[str],
                    source: str, pool) -> list[str]:
    """One shared model SHAPE block (3 row-pool indices) for `prefix`.

    C5 (2026-10-20): the model block is the STATIC shape only — the
    MetaA/MetaB pair moved to the room extras stream, so `with_meta=False`.
    There are no per-room blocks any more (async rooms share the model shape
    and carry an extras record). C3 (2026-10-20): the 9 raw PF bytes became 3
    one-byte row-pool indices (`pool`, built once for the whole game).
    C11 (2026-10-21): the hot stream is gone too — the block is exactly the
    three indices (band 1's b7 = `mid_band_type`)."""
    if model is None:
        res = None
        hot = False
    else:
        res = resolve_asym_patches(model, room, rows)
        hot = bool(model.get("mid_band_type"))
    asym, ball_x, m1_x, m1_door, m1_right = (
        res if res else (None, 0, 0, False, False))
    return convert_room.lines(
        rows, prefix=prefix, source=source,
        asym_rows=asym, asym_ball_x=ball_x, asym_m1_x=m1_x,
        hot_m1=(),
        door=False,          # Phase 5: no ball doors — a side-0 door is the
                             # right M1 door (MetaA b0=1)
        m1_door=room_m1_door_flag(room),
        m1_right=m1_right,
        hot=hot,
        with_meta=False,
        pool=pool)


def room_has_async(room: dict) -> bool:
    """True when the ROOM owns a data block (async strips / feature cells).

    Those rooms can no longer share a model block: the meta lives at a fixed
    offset inside the (PF + meta + stream) block the room points at."""
    return bool(room.get("asym_patches") or room.get("feature_cells"))


# C2 (2026-10-20): the room record stores the shape index in b5-0, so the
# whole game can address 64 distinct blocks. That is the plan's C3 ceiling
# until the row dictionary lands; fail loudly instead of emitting a truncated
# index.
MAX_SHAPES = 64


def _shape_stream(generated: Path, level_numbers: list[int] | None = None) -> list[str]:
    """Block labels in models_data.asm include order (= shape index).

    This order IS the contract: bank2's EnterRoomB2 reads
    `LEVEL_ShapeTable[index]`, and the converter numbers the table by walking
    the SAME files in the same order. C5 (2026-10-20): only the shared model
    shapes are emitted (the per-room block stream is retired, and its
    byte-identical dedupe pass with it).
    """
    pattern = re.compile(r"^(M\d+)Shape:")
    order: list[str] = []
    # C7: only THIS stage's block files — a stale file from another stage
    # (e.g. a leftover 210-room tree) must not contribute shape labels.
    if level_numbers is None:
        block_paths = sorted(
            generated.glob("level_[0-9][0-9][0-9]_blocks.asm"))
    else:
        block_paths = [generated / f"level_{n:03d}_blocks.asm"
                       for n in level_numbers]
    files = [generated / "models_data.asm"] + [
        p for p in block_paths if p.exists()]
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line.strip())
            if match:
                order.append(match.group(1))
    return order


def write_levels_index(output: Path, json_paths: list[Path]) -> None:
    """Emit models_data.asm + levels_data.asm (includes) + levels.asm (tables).

    Legacy per-level entry point (build.sh's `--levels`): models come from
    models/models.json next to the level files and the level number comes from
    the file name. The unified stage file uses `write_stage()` below, which
    feeds the SAME emitter with the stage's own `models` list.
    """
    models_by_id = load_models(json_paths[0].parent / "models" / "models.json")
    levels = []
    for path in json_paths:
        level = json.loads(path.read_text())
        if "level" in level:          # cereal wraps the level in an NVP
            level = level["level"]
        level_n = level_number_from_path(path) or int(level.get("level_id", 1))
        levels.append((level_n, level))
    _write_levels_index(output, levels, models_by_id)


def write_stage(stage_path: Path, outdir: Path,
                rooms_dir: Path | None = None) -> None:
    """Convert a unified stage file (models + every level) — E1 2026-10-20.

    The stage file is `{"stage": {"models": [...], "levels": [...]}}`; the
    bare `{"models": ..., "levels": ...}` form is accepted too. Each level
    object is EXACTLY the payload of a legacy `level_00N.json` `level` NVP, so
    the emitted bytes are identical to the legacy per-level invocation for the
    same content (see tools/test_stage_json.py).

    The level number is the level's ORDINAL in `levels` (1-based, play order
    = LevelDataTable order). It cannot come from `level_id`: the project's
    files all carry level_id 1 (legacy naming came from the file name), and
    two stage levels may legitimately share a level_id. Ordinal + play order
    is the single stable rule for a file that has no file names.
    Writes the same per-room .txt mirrors and per-level .asm files as
    `convert_level.py LEVEL.json OUT_PREFIX ROOMS_DIR`, then the shared index.
    """
    models_by_id, raw_levels = load_stage(stage_path)
    rooms_dir = rooms_dir or stage_path.parent
    generated = outdir
    levels = []
    for level_n, level in enumerate(raw_levels, start=1):
        rooms = list(level["rooms"])
        rooms.sort(key=lambda r: r["room_id"])
        level = dict(level, rooms=rooms)
        levels.append((level_n, level))
        for index, room in enumerate(rooms):
            rows = rows_from_json(room, models_by_id)
            txt = rooms_dir / f"level_{level_n:03d}_room_{index + 1:03d}.txt"
            txt.write_text("\n".join(rows) + "\n")
        connections = position_bytes(rooms)
        write_tables(level, rooms, connections,
                     generated / f"level_{level_n:03d}_rooms.asm",
                     level_n, models_by_id)
        (generated / f"level_{level_n:03d}_rooms_data.asm").write_text(
            "; All rooms use shared model data (models_data.asm).\n")
    _write_levels_index(generated / "levels.asm", levels, models_by_id)


def load_stage(stage_path: Path) -> tuple[dict, list[dict]]:
    """stage.json -> ({model_id: model}, [level, ...]).

    Accepts the canonical wrapped form and the bare form; a `level` NVP inside
    a level object (cereal's per-level write) is unwrapped for convenience.
    """
    data = json.loads(stage_path.read_text())
    stage = data.get("stage", data)
    models = stage.get("models")
    levels = stage.get("levels")
    if not isinstance(models, list) or not isinstance(levels, list):
        raise ValueError(
            f"{stage_path}: a stage file needs `models` and `levels` lists "
            "(optionally under a `stage` key)")
    models_by_id = {}
    for model in models:
        if not isinstance(model, dict) or "id" not in model:
            raise ValueError(f"{stage_path}: every model needs an `id`")
        models_by_id[model["id"]] = model
    unwrapped = []
    for level in levels:
        if not isinstance(level, dict):
            raise ValueError(f"{stage_path}: levels must be objects")
        unwrapped.append(level.get("level", level))
    return models_by_id, unwrapped


def _write_levels_index(output: Path, levels: list[tuple[int, dict]],
                        models_by_id: dict) -> None:
    """Emit models_data.asm + levels_data.asm (includes) + levels.asm (tables).

    The game reads LevelDataTable[Level] to start a level and place the miner.
    miner_room's high bit carries miner-facing-right; low 7 bits remain room id.
    The entry is 6 scalar bytes + the level block base word + the room count
    (stride 9, C4 2026-10-20; start_x/start_y dropped 2026-10-19 — they were
    the constants 32/24).

    models_data.asm holds each referenced model's PF/rect data ONCE, shared by
    every room (across all levels) whose RoomDataTable points at that model.
    `levels` is [(level_n, level dict)] in play order; `models_by_id` is the
    model registry (legacy project or the stage file's own list).
    """
    generated = output.parent
    data_lines = ["; Generated by convert_level.py --levels. Do not edit by hand.", ""]
    table_lines = ["; Generated by convert_level.py --levels. Do not edit by hand.", ""]
    referenced: set = set()
    for level_n, level in levels:
        for room in level["rooms"]:
            model = models_by_id.get(room.get("model_id"))
            if model is None:
                raise ValueError(
                    f"level {level_n}: a room has no model_id — C5 needs a "
                    "shared model shape for every room (per-room blocks are "
                    "retired)")
            # C5 (2026-10-20): EVERY referenced model needs its shape block
            # now — an async room points at the model shape too and carries
            # its patches/features/meta in the extras stream.
            referenced.add(model["id"])
        check_rooms_against_models(level.get("rooms") or [], models_by_id,
                                   f"level {level_n}",
                                   int(level.get("miner_room", 0)) & 0x7F,
                                   level.get("miner_y", 0))
        rel = generated.name
        data_lines.append(f'    include "{rel}/level_{level_n:03d}_rooms_data.asm"')
        table_lines.append(f'    include "{rel}/level_{level_n:03d}_rooms.asm"')
    data_lines.append("")

    # Shared model playfield + collision data, emitted once for all levels.
    # C3 (2026-10-20): one GLOBAL row pool for the whole game; every shape
    # block references it with 3 one-byte indices instead of 9 raw PF bytes.
    pool = convert_room.RowPool()
    model_lines = ["; Generated by convert_level.py --levels. Do not edit by hand."]
    for mid in sorted(referenced):
        model = models_by_id[mid]
        model_lines.append("")
        # A model block is the STATIC shape only (async lives on rooms now).
        # Its label set stays stable for every referenced model, so the frozen
        # test fixtures (tools/test_fixtures.py injects at M0/M2/M4) and any
        # hand-written reference keep resolving.
        left_rows = rows_from_json({"model_id": mid, "tiles": model.get("tiles"),
                                    "width": model.get("width", WIDTH)},
                                   models_by_id)
        check_model_objects(model, f"models.json model {mid}")
        model_lines += emit_room_block(
            f"M{mid}", {}, model, left_rows, f"models.json model {mid}", pool)
    model_lines += pool.lines()
    model_lines.append("")
    (generated / "models_data.asm").write_text("\n".join(model_lines) + "\n")
    # A3 (2026-10-19): models_data.asm is NOT a bank2 file any more — it is
    # included from bank3 (C7 2026-10-20: the shape half of the level-data
    # subsystem lives there). levels_data.asm is a legacy convenience list
    # (nothing includes it); keep the per-level room-data stubs so old tooling
    # keeps resolving.
    (generated / "levels_data.asm").write_text("\n".join(data_lines) + "\n")

    # --- C7 (2026-10-20): bank3 data include list -------------------------
    # models_data.asm (shape blocks + row pool + LEVEL_ShapeTable, appended
    # below once the shape order is known) and levels_extras.asm (the per-level
    # async extras streams + their base table). bank3.asm includes this file in
    # its $F010-$F44F data window; the fit is checked in emit_spills().
    extras_lines = [
        "; Generated by convert_level.py --levels. Do not edit by hand.",
        "; C7 (2026-10-20): bank3's async EXTRAS streams, one file per level,",
        "; plus the per-level BASE table ExtrasLoad indexes by `Level` ($A3).",
        "; Bank2 stages only the room's 1-based ordinal (LevelConnSpare): the",
        "; counts column lives in bank2, the records live here.",
    ]
    for level_n, _level in sorted(levels, key=lambda item: item[0]):
        extras_lines.append(
            f'    include "generated/level_{level_n:03d}_extras.asm"')
    extras_lines.append(f"LEVEL_EXTRAS_COUNT = {len(levels)}")
    extras_lines.append("LevExtrasLo:")
    extras_lines.append("  .byte " + ", ".join(
        f"<LEVEL{n}_AsyncExtras" for n, _l in sorted(levels,
                                                    key=lambda i: i[0])))
    extras_lines.append("LevExtrasHi:")
    extras_lines.append("  .byte " + ", ".join(
        f">LEVEL{n}_AsyncExtras" for n, _l in sorted(levels,
                                                    key=lambda i: i[0])))
    extras_lines.append("")
    (generated / "levels_extras.asm").write_text(
        "\n".join(extras_lines) + "\n")

    # C12 (2026-10-21): the bank3 data window is SPLIT in two, because the
    # biggest shape library that fits one window is smaller than the shape
    # library the generator can use. The two halves are independent include
    # lists at different addresses — each walker only dereferences data in
    # ITS half, so the split costs nothing at run time:
    #   extras  -> $F010-$F44F (1 088 B): per-level async streams + base table
    #   shapes  -> $F5CC-$F8B6 (  747 B): shape blocks + row pool + shape table
    extras_list = [
        "; Generated by convert_level.py --levels (C12 2026-10-21).",
        "; Include list for BANK3's $F010 EXTRAS window — see bank3.asm.",
        '    include "generated/levels_extras.asm"',
        "",
    ]
    (generated / "spill_bank3.asm").write_text("\n".join(extras_list) + "\n")
    shapes_list = [
        "; Generated by convert_level.py --levels (C12 2026-10-21).",
        "; Include list for BANK3's $F5CC SHAPE window — see bank3.asm.",
        '    include "generated/models_data.asm"',
        "",
    ]
    (generated / "spill_bank3_shapes.asm").write_text(
        "\n".join(shapes_list) + "\n")

    # (a) 2026-10-20: one bottom-band COLOR for the whole game. The per-room
    # flag stays in the RoomShapes byte (b6, C2); the color is a constant
    # (bank2.asm carries the EQU, test_level_bank asserts it matches this).
    band_colors = {
        _room_bottom_color(room)
        for _n, level in levels for room in (level.get("rooms") or [])
    } - {0}
    if len(band_colors) > 1:
        raise ValueError(
            f"{len(band_colors)} distinct bottom-band colors "
            f"{sorted(hex(c) for c in band_colors)} — the room record keeps "
            "only the band FLAG (one color per game); unify the "
            "water color or extend the format")
    band_color = band_colors.pop() if band_colors else BAND_COLOR_FALLBACK
    # (a) 2026-10-20: the single water color, as an EARLY include (< $F010 in
    # bank2), so EnterRoomB2 can `lda #BAND_COLOR` without a hand-copy.
    (generated / "levels_equ.asm").write_text(
        "; Generated by convert_level.py --levels. Do not edit by hand.\n"
        "; One bottom-band color for the whole game: the room record keeps only\n"
        "; the per-room FLAG (convert_level rejects a second\n"
        "; color — extend the format first if that is ever needed).\n"
        f"BAND_COLOR = ${band_color:02x}\n")

    # --- C2 (2026-10-20): shape registry + address table -------------------
    # A room record holds a 6-bit SHAPE INDEX; the block address lives here.
    # The ordinal IS the emission order of models_data.asm (models sorted by
    # id). C5 (2026-10-20): only shared model shapes exist now, so every
    # ordinal is referenced directly (no dedupe aliases).
    shapes = _shape_stream(generated, [n for n, _l in levels])
    if len(shapes) > MAX_SHAPES:
        raise ValueError(
            f"{len(shapes)} distinct shape blocks > the {MAX_SHAPES} the 6-bit "
            "room-record shape index can address — share a model or wait for "
            "the C3 row dictionary")
    shape_index = {name: i for i, name in enumerate(shapes)}
    equ_lines = [f"LEVEL_SHAPE_COUNT = {len(shapes)}"]
    for name in shapes:
        equ_lines.append(f"SHAPE_{name} = {shape_index[name]}")

    # C7 (2026-10-20): the shape ADDRESS table lives in BANK3 next to the
    # blocks (models_data.asm), so bank2's EnterRoomB2 stages only the shape
    # INDEX and needs no bank3 label, no symbol export and no second pass.
    # The ordinal contract is unchanged: SHAPE_<label> == row here.
    with (generated / "models_data.asm").open("a", encoding="utf-8") as fh:
        fh.write("\n; C7 (2026-10-20): shape ADDRESS table — bank3's B3RoomBlocks\n"
                 "; reads it in-bank; the 6-bit room-record index is the row.\n")
        fh.write(f"; LEVEL_SHAPE_COUNT = {len(shapes)} "
                 f"(6-bit index ceiling: {MAX_SHAPES})\n")
        fh.write("LEVEL_ShapeTable:\n")
        for name in shapes:
            fh.write(f"  .word {name}Shape\n")
        fh.write("\n")

    tail_lines = [
        "",
        f"LEVEL_FORMAT = ${LEVEL_FORMAT:02x}",
        "LEVEL_DATA_STRIDE = 7",
        f"LEVEL_COUNT = {len(levels)}",
        "",
        "; Per-level entry (stride 7, (d) 2026-10-20): miner room/x, both wall",
        "; colors, then the level's room-table base and its ROOM COUNT.",
        "; start x/y (32/24), start_room (0) and miner_y (84) are kernel",
        "; constants now — the converter rejects other values.",
        "; Inside a level block (n = ROOM COUNT, C2 2026-10-20; C5 extras):",
        ";   base + 0   RoomShapes     1 B/room (shape idx b5-0 | band b6 |",
        ";                               owns-extras b7; shape = the table below)",
        ";   base + n   RoomPositions  1 B/room (LEVEL_FORMAT 2: x<<4|y,",
        ";                               exits derived by scanning it)",
        ";   base + 2n  RoomCounts     1 B/room (count<<6 | extras ordinal)",
        ";   base + 3n  EnemyDataTable 3 B/record (type b3-0|dir b7, x, y;",
        ";                               first record index derived)",
        ";   ..         AsyncExtras    variable, one record per owns-extras room",
        ";                               (C5; after the enemy records — the",
        ";                               loader derives its base from the count",
        ";                               column sum). Flags/MetaA/MetaB,",
        ";                               1 B/patch, 1 B/feature, then the",
        ";                               FEATURE-record stream when the room",
        ";                               has feature cells (C11: no hot records).",
    ] + equ_lines + [
        "",
        "; Shape block (C11 2026-10-21): EXACTLY 3 row-pool indices (band",
        ";   0/1/2 -> RowPoolPF0/1/2 in models_data.asm; the loader expands",
        ";   them into PF0Buf). Band 1's b7 = mid_band_type (hot); hot death",
        ";   is derived from the expanded PF row 1. LEVEL_ROW_COUNT = rows.",
        "; ASYNC EXTRAS (C7 2026-10-20): the per-room records moved OUT of this",
        ";   block into generated/level_00N_extras.asm (bank3) — a feature",
        ";   room's record stream lives inside it and the VBL walkers read",
        ";   it in-bank, so record walkers and records share a bank. This bank",
        ";   keeps the counts byte's b5-0 ORDINAL and the 3 B/room columns.",
        f"; BAND_COLOR = ${band_color:02x} — the single bottom-band color (every",
        "; bottom_band room must resolve to it; bank2.asm carries the EQU and",
        "; test_level_bank asserts the pair).",
        "LevelDataTable:",
    ]
    for level_n, level in levels:
        prefix = f"LEVEL{level_n}"
        tail_lines += [
            f"  .byte {prefix}_MINER_ROOM, {prefix}_MINER_X, "
            f"{prefix}_WALL_COLOR, {prefix}_WALL_COLOR2",
            f"  .word {prefix}_RoomShapes",
            f"  .byte {len(level['rooms'])} ; {prefix} rooms",
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
    emit_spills(generated, [n for n, _l in levels])


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


# bank2 data-slot gaps (bugs.md 27/27b): (name, slot end).
# Starts come from _SPILL_ORG (the `.ds`/`org` pad that opens each window);
# tools/verify_build.py --precheck re-measures the REAL starts from bank2.lst
# after every build and fails on overflow — keep here in sync.
#
# C7 (2026-10-20): the shape half moved to bank3, so the six windows it used
# to occupy in bank2 are DATA SLOTS now. Order = first-fit preference; the
# biggest windows first so a large level file lands where it fits and the
# small tail slots absorb the index/odd sizes.
_SPILL_SLOTS = [
    ("spill_F9D9", 0xFAA0),   # 304 B (end moved down: StageSlot1 + windows)
    ("spill_F767", 0xF854),   # 340 B (levels_index + room tables; historical)
    ("spill_F453", 0xF600),   # 429 B
    ("spill_F307", 0xF450),   # 329 B
    ("spill_F8B7", 0xF9D9),   # 290 B
    ("spill_FCB8", 0xFD87),   # 207 B
    ("spill_FF59", 0xFFE6),   # 141 B
    ("spill_FE9C", 0xFEF0),   #  84 B
]

# C7 (2026-10-20): BANK3 carried ONE data window for the level-data subsystem.
# C12 (2026-10-21): it is SPLIT in two, because a single window caps the shape
# library below what the generator can use. Both halves are checked here; the
# `.ds` pads that open them live in bank3.asm.
_BANK3_EXTRAS_SLOT = (0xF010, 0xF450)   # async extras + base table (sized)
_BANK3_SHAPES_SLOT = (0xF5CC, 0xF8B7)   # shape blocks + row pool + address table
_BANK3_SLOTS = (
    ("spill_bank3.asm", "extras", _BANK3_EXTRAS_SLOT),
    ("spill_bank3_shapes.asm", "shapes", _BANK3_SHAPES_SLOT),
)

# C7: the index file DEFINES LEVEL_FORMAT / LEVEL_DATA_STRIDE / the SHAPE_*
# EQUs, so it must be included before every room-table file (DASM needs the
# EQUs at the point of use). It therefore owns the FIRST window in bank2's
# source order ($F307) — the greedy pass places the room tables around it.
_INDEX_SLOT = "spill_F307"

_SPILL_ORG = {  # exact slot start (the pad that opens the window)
    "spill_F767": 0xF700,   # include sits after `.ds $F700 - *`
    "spill_F453": 0xF453,
    "spill_F307": 0xF307,
    "spill_F8B7": 0xF8B7,
    "spill_F9D9": 0xF9D9,
    "spill_FCB8": 0xFCB8,
    "spill_FF59": 0xFF59,
    "spill_FE9C": 0xFE9C,
}


def emit_spills(generated: Path, level_numbers: list[int] | None = None) -> None:
    """bugs.md 27b: place level files into bank2's data slots and write
    generated/spill_*.asm include-lists — adding a level never touches
    bank2.asm. Greedy first-fit, big levels first; within a slot the
    index stays first (defines LEVEL_FORMAT) and rooms sort ASC (stable
    addresses per slot). Overflow here = precheck also fails after build.

    C7 (2026-10-20): the slot pool is the whole level-table window set (the
    shape half left for bank3), so 210 rooms fit with slack; the DATA stays in
    one bank with its readers (EnterRoomB2 / exits / LoadLevelB2 / moth /
    LWC / LHT / blast), which is the invariant the split is built on.
    """
    idx = "generated/levels_index.asm"
    if level_numbers is None:
        rooms = sorted(p.name for p in generated.glob("level_*_rooms.asm"))
    else:
        # C7: the exact set this stage emits (never a glob — a previous
        # stage's leftover files would be placed into the ROM and reference
        # shape labels that no longer exist).
        rooms = sorted(f"level_{n:03d}_rooms.asm" for n in level_numbers
                       if (generated / f"level_{n:03d}_rooms.asm").exists())
    sizes = {}
    for name in [Path(idx).name] + rooms:
        p = generated / Path(idx).name if name == Path(idx).name else generated / name
        sizes[name] = _gen_data_size(p)
    caps = {}
    for name, end in _SPILL_SLOTS:
        start = _SPILL_ORG[name]
        caps[name] = end - start
    order = [Path(idx).name] + sorted(rooms, reverse=True)  # big first
    placed: dict = {name: [] for name, _ in _SPILL_SLOTS}
    for item in order:
        sz = sizes[item]
        if item == Path(idx).name:
            if sz > caps[_INDEX_SLOT]:
                raise ValueError(
                    f"levels_index.asm ({sz}B) does not fit the index slot "
                    f"${_SPILL_ORG[_INDEX_SLOT]:04X} "
                    f"({caps[_INDEX_SLOT]}B) — too many levels")
            caps[_INDEX_SLOT] -= sz
            placed[_INDEX_SLOT].append(item)
            continue
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
        head = [Path(idx).name] if Path(idx).name in files else []
        lines = ["; Generated by convert_level.py --levels (bugs.md 27b)."
                 " Do not edit by hand.",
                 "; Include list for this bank2 gap — see emit_spills()."]
        for inc in head + room_files:
            lines.append(f'    include "generated/{inc}"')
        (generated / f"{name}.asm").write_text("\n".join(lines) + "\n")
    total_used = sum(sizes.values())
    print(f"level tables (bank2): {total_used}B in {len(order)} files, "
          f"slot slack {sum(caps.values())}B")

    # --- BANK3 data windows fit (extras + shapes, C12 split) ---------------
    for name, kind, (start, end) in _BANK3_SLOTS:
        blocks = generated / name
        if not blocks.exists():
            continue
        used = 0
        for raw in _expand_includes(blocks, generated):
            used += _gen_data_size(raw)
        slack = end - start - used
        print(f"bank3 {kind}: {used}B of {end - start}B, "
              f"slack {slack}B (${start:04X}-${end - 1:04X})")
        if slack < 0:
            raise ValueError(
                f"bank3 {kind} overflow: {used}B > {end - start}B in "
                f"${start:04X}-${end - 1:04X} — grow the window (bank3.asm) "
                f"or trim a {'shape' if kind == 'shapes' else 'room'}")


def _expand_includes(list_path: Path, generated: Path,
                     depth: int = 0) -> list[Path]:
    """Flatten an include list (spill_bank3 -> levels_extras -> per-level)."""
    out: list[Path] = []
    text = list_path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        mi = re.match(r'\s*include\s+"([^"]+)"', raw)
        if not mi:
            continue
        p = generated / Path(mi.group(1)).name
        if depth < 3 and p.exists() and 'include "' in p.read_text(
                encoding="utf-8"):
            out += _expand_includes(p, generated, depth + 1)
            if any(ln.split(";")[0].strip().startswith((".byte", ".word"))
                   for ln in p.read_text(encoding="utf-8").splitlines()):
                out.append(p)      # the include list ALSO carries data bytes
            continue
        out.append(p)
    return out



def main(argv: list[str]) -> int:
    if argv and argv[0] == "--stage":
        # E1 (2026-10-20): ONE stage file for models + every level.
        #   convert_level.py --stage STAGE.json OUTDIR [ROOMS_DIR]
        # Emits exactly what the legacy per-level invocation + --levels emit
        # for the same content; OUTDIR is the generated/ directory.
        if len(argv) not in (3, 4):
            print("usage: convert_level.py --stage STAGE.json OUTDIR [ROOMS_DIR]",
                  file=sys.stderr)
            return 2
        stage_path = Path(argv[1])
        outdir = Path(argv[2])
        rooms_dir = Path(argv[3]) if len(argv) > 3 else None
        try:
            write_stage(stage_path, outdir, rooms_dir)
        except (OSError, ValueError, KeyError) as error:
            print(error, file=sys.stderr)
            return 1
        print(f"wrote stage -> {outdir} (from {stage_path})")
        return 0

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
        for index, room in enumerate(rooms):
            rows = rows_from_json(room, models_by_id)
            txt = rooms_dir / f"level_{level_n:03d}_room_{index + 1:03d}.txt"
            txt.write_text("\n".join(rows) + "\n")

        connections = position_bytes(rooms)
        tables = Path(str(out_prefix) + "_rooms.asm")
        write_tables(level, rooms, connections, tables, level_n, models_by_id)

        # Rooms with a model AND no async share the M<id>* symbols in
        # models_data.asm. Every other room's block is emitted into the level's
        # table file by write_tables() (see there).
        data_include = generated_dir / f"level_{level_n:03d}_rooms_data.asm"
        data_include.write_text(
            "; All rooms use shared model data (models_data.asm).\n")

        print(f"wrote {len(rooms)} room grids and tables -> {tables}")
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
