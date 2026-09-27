#!/usr/bin/env python3
"""Convert a 20x3 text room into a HERO-style reflected room include.

Grid: 20 columns x 3 playable bands + a 48-line grey HUD band below (drawn by
the kernel, not stored in room data). Each tile is 8 color-clocks wide and 48
scanlines tall, so the 3 playable bands fill the top 144 lines and the HUD the
bottom 48 of the 192-line screen. The TIA reflects the 20-bit playfield
(CTRLPF D0=1), so rooms must be left-right symmetric; the kernel emits one
PF0/PF1/PF2 triple per tile row, written once per 48-line band.

Emitted data:
  - RoomRects: compressed rectangle list for the 6502 collision code.
    Format: 1 byte count, then count * 4 bytes (x, y, width, height) in tile
    coordinates.  The collision routine mirrors each rectangle to the right
    half at runtime, so only the left-half (0-19 column) layout is stored.
  - TilePF0/TilePF1/TilePF2: one byte per tile row for the kernel.
All per-row tables (PF triples) are PADDED to 12 bytes so
bank0's table arithmetic (+12 / +12 / +24) works unchanged; only the first
3 entries are drawn.
"""

from pathlib import Path
import sys

WIDTH = 20
HEIGHT = 3                  # playable color bands (HUD is drawn separately)
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
        if any(cell not in ".#H" for cell in row):
            raise ValueError(
                f"{path}: row {number} contains a character other than ., # or H"
            )
    return rows


def _is_solid(cell: str, solids: str) -> bool:
    return cell in solids


def pf_values(row: str) -> tuple[int, int, int]:
    """Map a 20-column text row to PF0/PF1/PF2 bytes.

    With reflection, column c is playfield pixel c of the left half:
      cols 0-3   -> PF0 bits 7-4 (bit 7 = pixel 0 = leftmost)
      cols 4-11  -> PF1 bits 7-0 (bit 7 = pixel 4)
      cols 12-19 -> PF2 bits 0-7 (bit 0 = pixel 12)
    Hot rock (H) is solid for the playfield, same as #.
    """
    solid = [cell in "#H" for cell in row]
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


def find_rectangles(rows: list[str], solids: str = "#") -> list[tuple[int, int, int, int]]:
    """Find rectangular blocks of solid tiles in the room.

    solids: which characters count (default '#'; pass '#H' for all walls,
    'H' for hot-only rects). Returns (x, y, width, height) per rect.
    Uses a greedy algorithm: scan left-to-right, top-to-bottom; when a solid
    tile is found, extend right then down to form the largest possible rectangle.
    """
    height = len(rows)
    width = len(rows[0])
    visited = [[False] * width for _ in range(height)]
    rects = []

    def solid_at(r: int, c: int) -> bool:
        return _is_solid(rows[r][c], solids)

    for row in range(height):
        for col in range(width):
            if not solid_at(row, col) or visited[row][col]:
                continue
            w = 1
            while col + w < width and solid_at(row, col + w) and not visited[row][col + w]:
                w += 1
            h = 1
            while row + h < height:
                ok = True
                for c in range(col, col + w):
                    if not solid_at(row + h, c) or visited[row + h][c]:
                        ok = False
                        break
                if not ok:
                    break
                # Thin (w==1) must stop before a row that joins a wider run
                # so the bomb only removes the truly 1-wide segment.
                if w == 1:
                    left = col > 0 and solid_at(row + h, col - 1)
                    right = col + 1 < width and solid_at(row + h, col + 1)
                    if left or right:
                        break
                h += 1
            for r in range(row, row + h):
                for c in range(col, col + w):
                    visited[r][c] = True
            rects.append((col, row, w, h))

    return rects


def lines(rows: list[str], prefix: str = "", source: str = "room") -> list[str]:
    """Build the asm lines for a grid (shared by per-room and per-model emission)."""
    triples = [pf_values(row) for row in rows]
    stride = max(TABLE_STRIDE, len(rows))

    out = [
        f"; Generated from {source}. Do not edit by hand.",
    ]
    if not prefix:
        out.append(f"ROOM_TILE_COLUMNS = {WIDTH}")
        out.append(f"ROOM_TILE_ROWS = {len(rows)}")

    rects = find_rectangles(rows, solids="#H")
    hot_rects = find_rectangles(rows, solids="H")
    rect_name = prefix + "RoomRects"
    out.append(f"{rect_name}:")
    out.append(f"  .byte {len(rects)}                  ; number of rectangles")
    for x, y, w, h in rects:
        out.append(f"  .byte {x}, {y}, {w}, {h}  ; x, y, width, height")
    # Hot-only block after solid rects: death + pulse. Walks of solid rects
    # must stop at the count byte and never enter this section.
    out.append(f"  .byte {len(hot_rects)}              ; number of hot rectangles")
    for x, y, w, h in hot_rects:
        out.append(f"  .byte {x}, {y}, {w}, {h}  ; hot x, y, width, height")

    for name, register in zip(("TilePF0", "TilePF1", "TilePF2"), range(3)):
        out.append(f"{prefix}{name}:")
        table = [f"${triple[register]:02x}" for triple in triples]
        table += ["$00"] * (stride - len(table))
        out.append("  .byte " + ", ".join(table))

    return out


def emit(rows: list[str], output: Path, prefix: str = "", source: str = "room") -> None:
    output.write_text("\n".join(lines(rows, prefix, source)) + "\n")


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
