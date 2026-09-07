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

WIDTH = 20
# Playable rows per room (the bottom 4 tile rows render as a grey HUD band and
# are NOT part of room data: rooms store only the playable cave).
HEIGHT = 12
ROOM_NONE = 0xFF
# Byte that renders the editor default (56,104,144 = hue A, luma 2) under the
# emulator-aware encoding in nearest_byte: (hue << 4) | (luma << 1) = 0xA4.
LEVEL_WALL_COLOR_DEFAULT = 0xA4

# Atari 2600 TIA NTSC 128-color chart, hue-major: [hue][luma] = (r, g, b).
# MUST match tools/editor/src/AtariPalette.cpp kPalette exactly (same RGB values
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
    """Editor tiles: AIR stays open, everything else becomes solid #."""
    return "." if value == 0 else "#"


def rows_from_json(room: dict) -> list[str]:
    tiles = room.get("tiles", [])
    width = room.get("width", WIDTH)
    if width != WIDTH:
        raise ValueError(f"room {room.get('room_id')}: width {width} != {WIDTH}")
    if len(tiles) != WIDTH * HEIGHT:
        raise ValueError(
            f"room {room.get('room_id')}: expected {WIDTH * HEIGHT} tiles, got {len(tiles)}")
    rows = [
        "".join(tile_to_char(tiles[y * WIDTH + x]) for x in range(WIDTH))
        for y in range(HEIGHT)
    ]
    return rows


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


def hex_or_none(value: int) -> str:
    return "ROOM_NONE" if value == ROOM_NONE else f"${value:02x}"


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
                 output: Path, level_n: int) -> None:
    prefix = f"LEVEL{level_n}"
    room_prefix = f"L{level_n}R"
    # Two wall colors: the playfield's 12 tile rows are drawn in 4-row stripes:
    # rows 0-3 color 1, rows 4-7 color 2, rows 8-11 color 1 again.
    wall = nearest_byte(
        int(level.get('wall_r', 56)),
        int(level.get('wall_g', 104)),
        int(level.get('wall_b', 144)))
    wall2 = nearest_byte(
        int(level.get('wall2_r', 40)),
        int(level.get('wall2_g', 130)),
        int(level.get('wall2_b', 90)))
    lines = [
        f"; Generated from {level.get('name', 'level')} (level {level_n}). "
        "Do not edit by hand."
    ]
    lines += [
        f"{prefix}_START_ROOM = {level.get('start_room', 0)}",
        f"{prefix}_WALL_COLOR = ${wall:02x}",
        f"{prefix}_WALL_COLOR2 = ${wall2:02x}",
        f"{prefix}_START_X = {px(level.get('start_x', 0), 8)}",
        f"{prefix}_START_Y = {px(level.get('start_y', 0), 12)}",
        f"{prefix}_MINER_ROOM = {level.get('miner_room', 0)}",
        f"{prefix}_MINER_X = {px(level.get('miner_x', 0), 8)}",
        f"{prefix}_MINER_Y = {px(level.get('miner_y', 0), 12)}",
        "",
    ]
    lines.append(
        f"; Room data: one ({room_prefix}<n>TilePF0, ...RoomRowLo) word pair per room,"
        " indexed by RoomNo.")
    lines.append(f"{prefix}_RoomDataTable:")
    for index, room in enumerate(rooms):
        lines.append(
            f"  .word {room_prefix}{index + 1}TilePF0, "
            f"{room_prefix}{index + 1}RoomRowLo ; room {index}")
    lines.append("")
    lines.append(
        "; Room connections: up/down/left/right target room index per room ($ff = none).")
    lines.append(f"{prefix}_RoomConnections:")
    for index, conn in enumerate(connections):
        up, down, left_, right = conn
        lines.append(
            f"  .byte {hex_or_none(up)}, {hex_or_none(down)}, "
            f"{hex_or_none(left_)}, {hex_or_none(right)} ; room {index}")
    lines += _enemy_tables(prefix, rooms)
    output.write_text("\n".join(lines) + "\n")


# A room may hold up to this many enemies (matches the editor's own cap).
MAX_ENEMIES = 4
# Per-enemy byte layout in LEVEL{n}_EnemyDataTable (see _enemy_tables).
ENEMY_STRIDE = 6


def _enemy_tables(prefix: str, rooms: list[dict]) -> list[str]:
    """Emit the level's flat enemy table and the per-room enemy records.

    Enemies are positioned in EDITOR stage coordinates: x is a full-stage
    display column (0..39 across both mirror halves, so the game screens can
    differ per side) and y is a room row (0..11). Column -> room pixel uses
    4 px/column (one playfield block), row -> scanline uses 12 px/row,
    matching the existing level/miner coordinate conversion.

    LEVEL{n}_EnemyDataTable is a flat list of ENEMY_STRIDE-byte records:
    type, x, y, range_min, range_max, dir (range/speed are reserved for
    future patrolling; only type/x/y are consumed today).
    LEVEL{n}_RoomEnemies has one 4-byte record per room:
    ptr_lo, ptr_hi, count, pad.
    """
    flat: list[tuple[int, int, int, int, int, int]] = []
    counts: list[int] = []
    for index, room in enumerate(rooms):
        enemies = [e for e in (room.get("enemies") or [])][:MAX_ENEMIES]
        counts.append(len(enemies))
        for enemy in enemies:
            flat.append((
                int(enemy.get("type", 0)),
                enemy_x_px(enemy.get("x", 0)),
                px(float(enemy.get("y", 0)), 12),
                px(float(enemy.get("range_min", 0)), 4),
                px(float(enemy.get("range_max", 0)), 4),
                int(enemy.get("dir", 1)),
            ))
    lines = [""]
    lines += [
        f"; Enemy data: {len(flat)} enemy records across {len(rooms)} rooms, "
        f"{ENEMY_STRIDE} bytes each (type,x,y,range_min,range_max,dir).",
        f"{prefix}_EnemyDataTable:",
    ]
    for type_, x, y, rmin, rmax, dir_ in flat:
        lines.append(f"  .byte {type_}, {x}, {y}, {rmin}, {rmax}, {dir_}")
    lines += [
        "",
        "; Per-room enemy records: ptr_lo, ptr_hi, count, pad.",
        f"{prefix}_RoomEnemies:",
    ]
    for index, count in enumerate(counts):
        if count:
            start = sum(counts[:index]) * ENEMY_STRIDE
            lines.append(
                f"  .byte <({prefix}_EnemyDataTable+{start}), "
                f">({prefix}_EnemyDataTable+{start}), {count}, 0 ; room {index}")
        else:
            lines.append(
                f"  .byte <({prefix}_EnemyDataTable), "
                f">({prefix}_EnemyDataTable), 0, 0 ; room {index}")
    return lines


def write_levels_index(output: Path, json_paths: list[Path]) -> None:
    """Emit levels_data.asm (per-room includes) + levels.asm (tables/LevelDataTable).

    The game reads LevelDataTable[Level] to start a level and place the miner:
      offset 0..7 start_room, start_x, start_y, miner_room, miner_x, miner_y,
      wall_color, wall_color2; offset 8..11 the level's RoomDataTable and
      RoomConnections base addresses. Entry stride is LEVEL_DATA_STRIDE (=12).
    """
    generated = output.parent
    data_lines = ["; Generated by convert_level.py --levels. Do not edit by hand.", ""]
    table_lines = ["; Generated by convert_level.py --levels. Do not edit by hand.", ""]
    levels = []
    for path in json_paths:
        level = json.loads(path.read_text())
        if "level" in level:          # cereal wraps the level in an NVP
            level = level["level"]
        level_n = level_number_from_path(path) or int(level.get("level_id", 1))
        levels.append((level_n, level))
        rel = generated.name
        data_lines.append(f'    include "{rel}/level_{level_n:03d}_rooms_data.asm"')
        table_lines.append(f'    include "{rel}/level_{level_n:03d}_rooms.asm"')
    data_lines.append("")
    (generated / "levels_data.asm").write_text("\n".join(data_lines) + "\n")

    table_lines += [
        "",
        "LEVEL_DATA_STRIDE = 12",
        f"LEVEL_COUNT = {len(levels)}",
        "",
        "; Per-level entry (stride 12): start room/x/y, miner room/x/y, both wall",
        "; colors, then the level's RoomDataTable and RoomConnections bases.",
        "LevelDataTable:",
    ]
    for level_n, _level in levels:
        prefix = f"LEVEL{level_n}"
        table_lines += [
            f"  .byte {prefix}_START_ROOM, {prefix}_START_X, {prefix}_START_Y, "
            f"{prefix}_MINER_ROOM, {prefix}_MINER_X, {prefix}_MINER_Y, "
            f"{prefix}_WALL_COLOR, {prefix}_WALL_COLOR2",
            f"  .word {prefix}_RoomDataTable, {prefix}_RoomConnections",
        ]
    table_lines += [
        "",
        "; Per-level enemy table base (LEVEL{n}_RoomEnemies). Indexed by Level.",
        "LevelEnemyTable:",
    ]
    for level_n, _level in levels:
        table_lines.append(f"  .word LEVEL{level_n}_RoomEnemies")
    output.write_text("\n".join(table_lines) + "\n")


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

    level_n = level_number_from_path(json_path) or int(level.get("level_id", 1))
    try:
        for index, room in enumerate(rooms):
            rows = rows_from_json(room)
            txt = rooms_dir / f"level_{level_n:03d}_room_{index + 1:03d}.txt"
            asm = generated_dir / f"level_{level_n:03d}_room_{index + 1:03d}.asm"
            txt.write_text("\n".join(rows) + "\n")
            convert_room.emit(rows, asm, prefix=f"L{level_n}R{index + 1}",
                              source=txt.name)

        connections = connection_bytes(rooms)
        tables = Path(str(out_prefix) + "_rooms.asm")
        write_tables(level, rooms, connections, tables, level_n)

        # Emit a file that includes every per-room data file, so the game
        # assembler needs only this single include and picks up rooms added
        # in the editor without editing bank0.asm. Include paths are relative
        # to the build working directory (the repo root), matching the style
        # used elsewhere.
        data_include = generated_dir / f"level_{level_n:03d}_rooms_data.asm"
        data_include.write_text(
            "\n".join(f'    include "{generated_dir.name}/{asm.name}"'
                      for asm in sorted(
                          (generated_dir / f"level_{level_n:03d}_room_{i + 1:03d}.asm"
                           for i in range(len(rooms)))) ) + "\n")

        print(f"wrote {len(rooms)} room grids and tables -> {tables}")
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))