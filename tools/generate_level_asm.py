#!/usr/bin/env python3
"""Generate multi-room ASM data from a level JSON file.

Reads a level JSON (with models and room instances) and generates a DASM
include file containing:
  - Per-model PF register data (TilePF0/1/2) and collision rectangles
  - Room data table (pointers to model PF data + rects)
  - Room connections (inferred from room positions)
  - Start position, miner position

Usage: python3 generate_level_asm.py <level.json> <output.asm> [PREFIX]
"""

import json
import sys
from pathlib import Path

WIDTH = 20
HEIGHT = 12


def compute_pf(tiles, width):
    """Compute PF0/PF1/PF2 for each tile row from a tile grid."""
    pf0_list = []
    pf1_list = []
    pf2_list = []
    for row in range(HEIGHT):
        pf0 = pf1 = pf2 = 0
        for col in range(min(width, 4)):
            if tiles[row * width + col] != 0:
                pf0 |= 0x10 << col
        for col in range(4, min(width, 12)):
            if tiles[row * width + col] != 0:
                pf1 |= 0x80 >> (col - 4)
        for col in range(12, min(width, 20)):
            if tiles[row * width + col] != 0:
                pf2 |= 0x01 << (col - 12)
        pf0_list.append(pf0)
        pf1_list.append(pf1)
        pf2_list.append(pf2)
    return pf0_list, pf1_list, pf2_list


def compute_rects(tiles, width, height):
    """Compute collision rectangles (greedy merge)."""
    rects = []
    visited = [[False] * width for _ in range(height)]
    for r in range(height):
        for c in range(width):
            if tiles[r * width + c] == 0 or visited[r][c]:
                continue
            rw = 1
            while c + rw < width and tiles[r * width + c + rw] != 0 and not visited[r][c + rw]:
                rw += 1
            rh = 1
            while r + rh < height:
                ok = True
                for cc in range(c, c + rw):
                    if tiles[(r + rh) * width + cc] == 0 or visited[r + rh][cc]:
                        ok = False
                        break
                if not ok:
                    break
                rh += 1
            for rr in range(r, r + rh):
                for cc in range(c, c + rw):
                    visited[rr][cc] = True
            rects.append((c, r, rw, rh))
    return rects


def infer_connections(rooms):
    """Infer room connections from room positions.
    Returns dict: room_id -> [up, down, left, right] target indices ($ff = none)."""
    # Build position -> room_id map
    pos_map = {}
    for r in rooms:
        pos_map[(r["room_x"], r["room_y"])] = r["room_id"]

    connections = {}
    for r in rooms:
        rx, ry = r["room_x"], r["room_y"]
        rid = r["room_id"]
        conns = [0xff, 0xff, 0xff, 0xff]  # up, down, left, right

        # Check each direction
        for dx, dy, idx in [(0, -1, 0), (0, 1, 1), (-1, 0, 2), (1, 0, 3)]:
            neighbor = pos_map.get((rx + dx, ry + dy))
            if neighbor is not None:
                conns[idx] = neighbor

        connections[rid] = conns
    return connections


def main():
    if len(sys.argv) not in (3, 4):
        print("Usage: generate_level_asm.py <level.json> <output.asm> [PREFIX]",
              file=sys.stderr)
        return 2

    level_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    prefix = sys.argv[3] if len(sys.argv) == 4 else ""

    with open(level_path) as f:
        data = json.load(f)

    level = data["level"]
    level_id = level["level_id"]
    models = level.get("models", [])
    rooms = level.get("rooms", [])

    if not models or not rooms:
        print(f"Error: no models or rooms in {level_path}", file=sys.stderr)
        return 1

    lines = []
    lines.append(f"; Generated from {level_path.name}. Do not edit by hand.")
    lines.append(f"{prefix}START_ROOM = {level.get('start_room', 0)}")
    lines.append(f"{prefix}START_X = {int(level.get('start_x', 8) * 4)}")
    lines.append(f"{prefix}START_Y = {int(level.get('start_y', 2) * 12)}")
    lines.append(f"{prefix}MINER_ROOM = {level.get('miner_room', 0)}")
    lines.append(f"{prefix}MINER_X = {int(level.get('miner_x', 8) * 4)}")
    lines.append(f"{prefix}MINER_Y = {int(level.get('miner_y', 9) * 12)}")
    lines.append(f"{prefix}NUM_MODELS = {len(models)}")
    lines.append(f"{prefix}NUM_ROOMS = {len(rooms)}")
    lines.append("")

    # Emit per-model PF data and rectangles
    for model in models:
        mid = model["id"]
        tiles = model.get("tiles", [0] * (WIDTH * HEIGHT))
        w = model.get("width", WIDTH)
        h = model.get("height", HEIGHT)

        pf0, pf1, pf2 = compute_pf(tiles, w)
        rects = compute_rects(tiles, w, h)

        tag = f"{prefix}M{mid + 1}"

        lines.append(f"{tag}RoomRects:")
        lines.append(f"  .byte {len(rects)}                  ; number of rectangles")
        for x, y, rw, rh in rects:
            lines.append(f"  .byte {x}, {y}, {rw}, {rh}  ; x, y, width, height")

        lines.append(f"{tag}TilePF0:")
        lines.append("  .byte " + ", ".join(f"${v:02x}" for v in pf0))

        lines.append(f"{tag}TilePF1:")
        lines.append("  .byte " + ", ".join(f"${v:02x}" for v in pf1))

        lines.append(f"{tag}TilePF2:")
        lines.append("  .byte " + ", ".join(f"${v:02x}" for v in pf2))
        lines.append("")

    # Room data table: per-room pointers to model's PF data + rects
    lines.append(f"; Room data table: (PF0_ptr, Rects_ptr) per room, indexed by RoomNo.")
    lines.append(f"{prefix}RoomDataTable:")
    for r in rooms:
        mid = r["model_id"]
        tag = f"{prefix}M{mid + 1}"
        lines.append(f"  .word {tag}TilePF0, {tag}RoomRects ; room {r['room_id']}")
    lines.append("")

    # Room connections
    connections = infer_connections(rooms)
    lines.append(f"{prefix}RoomConnections:")
    for r in rooms:
        rid = r["room_id"]
        conns = connections.get(rid, [0xff, 0xff, 0xff, 0xff])
        conn_str = ", ".join(f"${c:02x}" if c != 0xff else "ROOM_NONE" for c in conns)
        lines.append(f"  .byte {conn_str} ; room {rid} (up, down, left, right)")
    lines.append("")

    # Room NONE constant
    lines.append(f"ROOM_NONE = $ff")
    lines.append("")

    output_path.write_text("\n".join(lines) + "\n")
    print(f"Generated {output_path} from {level_path.name}: "
          f"{len(models)} models, {len(rooms)} rooms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
