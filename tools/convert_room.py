#!/usr/bin/env python3
"""Convert a 20x12 text room into a HERO-style reflected room include.

Grid: 20 columns x 12 playable rows + a 4-row grey HUD band below (drawn by
the kernel, not stored in room data). Each tile is 8 color-clocks wide and 12
scanlines tall, so the 12 playable rows fill the top 144 lines and the HUD the
bottom 48 of the 192-line screen. The TIA reflects the 20-bit playfield
(CTRLPF D0=1), so rooms must be left-right symmetric; the kernel emits one
PF0/PF1/PF2 triple per tile row, written once per 12-line band.

Emitted data:
  - RoomRects: compressed rectangle list for the 6502 collision code.
    Format: 1 byte count, then count * 4 bytes (x, y, width, height) in tile
    coordinates.  The collision routine mirrors each rectangle to the right
    half at runtime, so only the left-half (0-19 column) layout is stored.
  - TilePF0/TilePF1/TilePF2: one byte per tile row for the kernel.
All per-row tables (PF triples) are PADDED to 12 bytes so
bank0's table arithmetic (+12 / +12 / +24) works unchanged; only the first
12 entries are drawn.
"""

from pathlib import Path
import sys

WIDTH = 20
HEIGHT = 12                 # playable tile rows (rows 12-15 are the HUD band)
TABLE_STRIDE = 12           # padded per-row table size (bank0 index math)


def read_room(path: Path) -> list[str]:
    rows = [line.rstrip("\n") for line in path.read_text().splitlines()]
    if len(rows) != HEIGHT:
        raise ValueError(f"{path}: expected {HEIGHT} rows, got {len(rows)}")
    for number, row in enumerate(rows, 1):
        if len(row) != WIDTH:
            raise ValueError(
                f"{path}: row {number} must have {WIDTH} columns, got {len(row)}"
            )
        if any(cell not in ".#" for cell in row):
            raise ValueError(f"{path}: row {number} contains a character other than . or #")
    return rows


def pf_values(row: str) -> tuple[int, int, int]:
    """Map a 20-column text row to PF0/PF1/PF2 bytes.

    With reflection, column c is playfield pixel c of the left half:
      cols 0-3   -> PF0 bits 7-4 (bit 7 = pixel 0 = leftmost)
      cols 4-11  -> PF1 bits 7-0 (bit 7 = pixel 4)
      cols 12-19 -> PF2 bits 0-7 (bit 0 = pixel 12)
    """
    solid = [cell == "#" for cell in row]
    pf0 = 0
    for col in range(4):
        if solid[col]:
            pf0 |= 0x10 << col   # PF0: col0->bit4 (leftmost), col1->bit5, col2->bit6, col3->bit7
    pf1 = 0
    for col in range(4, 12):
        if solid[col]:
            pf1 |= 0x80 >> (col - 4)
    pf2 = 0
    for col in range(12, 20):
        if solid[col]:
            pf2 |= 0x01 << (col - 12)
    return pf0, pf1, pf2


def find_rectangles(rows: list[str]) -> list[tuple[int, int, int, int]]:
    """Find rectangular blocks of solid tiles in the room.

    Returns a list of (x, y, width, height) tuples for each solid rectangle.
    Uses a greedy algorithm: scan left-to-right, top-to-bottom; when a solid
    tile is found, extend right then down to form the largest possible rectangle.
    """
    height = len(rows)
    width = len(rows[0])
    visited = [[False] * width for _ in range(height)]
    rects = []

    for row in range(height):
        for col in range(width):
            if rows[row][col] != "#" or visited[row][col]:
                continue
            w = 1
            while col + w < width and rows[row][col + w] == "#" and not visited[row][col + w]:
                w += 1
            h = 1
            while row + h < height:
                ok = True
                for c in range(col, col + w):
                    if rows[row + h][c] != "#" or visited[row + h][c]:
                        ok = False
                        break
                if not ok:
                    break
                # Thin (w==1) must stop before a row that joins a wider run
                # so the bomb only removes the truly 1-wide segment.
                if w == 1:
                    left = col > 0 and rows[row + h][col - 1] == "#"
                    right = col + 1 < width and rows[row + h][col + 1] == "#"
                    if left or right:
                        break
                h += 1
            for r in range(row, row + h):
                for c in range(col, col + w):
                    visited[r][c] = True
            rects.append((col, row, w, h))

    return rects


def emit(rows: list[str], output: Path, prefix: str = "", source: str = "room") -> None:
    triples = [pf_values(row) for row in rows]
    stride = max(TABLE_STRIDE, len(rows))

    lines = [
        f"; Generated from {source}. Do not edit by hand.",
    ]
    if not prefix:
        lines.append(f"ROOM_TILE_COLUMNS = {WIDTH}")
        lines.append(f"ROOM_TILE_ROWS = {len(rows)}")

    rects = find_rectangles(rows)
    rect_name = prefix + "RoomRects"
    lines.append(f"{rect_name}:")
    lines.append(f"  .byte {len(rects)}                  ; number of rectangles")
    for x, y, w, h in rects:
        lines.append(f"  .byte {x}, {y}, {w}, {h}  ; x, y, width, height")

    for name, register in zip(("TilePF0", "TilePF1", "TilePF2"), range(3)):
        lines.append(f"{prefix}{name}:")
        table = [f"${triple[register]:02x}" for triple in triples]
        table += ["$00"] * (stride - len(table))
        lines.append("  .byte " + ", ".join(table))

    output.write_text("\n".join(lines) + "\n")


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("usage: convert_room.py INPUT.txt OUTPUT.asm [PREFIX]", file=sys.stderr)
        return 2
    prefix = sys.argv[3] if len(sys.argv) == 4 else ""
    try:
        rows = read_room(Path(sys.argv[1]))
        emit(rows, Path(sys.argv[2]), prefix=prefix, source=Path(sys.argv[1]).name)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())