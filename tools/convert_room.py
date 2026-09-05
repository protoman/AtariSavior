#!/usr/bin/env python3
"""Convert a 20x16 text room into a HERO-style reflected room include.

Grid: 20 columns x 16 rows. Each tile is 8 color-clocks wide and 12
scanlines tall, so the whole 192-line visible screen IS the cave (no menu
region). The TIA reflects the 20-bit playfield (CTRLPF D0=1), so rooms must
be left-right symmetric; the kernel emits one PF0/PF1/PF2 triple per tile
row, written once per 12-line band.

Emitted data:
  - RoomTileMap + RoomRowLo/Hi: one byte per tile for the 6502 collision code.
  - TilePF0/TilePF1/TilePF2: one byte per tile row for the kernel.
"""

from pathlib import Path
import sys

WIDTH = 20
HEIGHT = 16


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
      cols 0-3   -> PF0 bits 4-7 (bit 4 = leftmost)
      cols 4-11  -> PF1 bits 7-0
      cols 12-19 -> PF2 bits 0-7 (bit 0 = leftmost)
    """
    solid = [cell == "#" for cell in row]
    pf0 = 0
    for col in range(4):
        if solid[col]:
            pf0 |= 0x10 << col   # col0 → bit4, col1 → bit5, etc.
    pf1 = 0
    for col in range(4, 12):
        if solid[col]:
            pf1 |= 0x80 >> (col - 4)
    pf2 = 0
    for col in range(12, 20):
        if solid[col]:
            pf2 |= 0x01 << (col - 12)
    return pf0, pf1, pf2


def emit(rows: list[str], output: Path) -> None:
    triples = [pf_values(row) for row in rows]

    lines = [
        "; Generated from rooms/level_001_room_001.txt. Do not edit by hand.",
        f"ROOM_TILE_COLUMNS = {WIDTH}",
        f"ROOM_TILE_ROWS = {HEIGHT}",
        "RoomTileMap:",
    ]
    for row in rows:
        bytes_ = [1 if cell == "#" else 0 for cell in row]
        lines.append("  .byte " + ", ".join(f"${b:02x}" for b in bytes_))

    lines.append("RoomRowLo:")
    lines.append("  .byte " + ", ".join(
        f"< (RoomTileMap+{row}*{WIDTH})" for row in range(HEIGHT)))
    lines.append("RoomRowHi:")
    lines.append("  .byte " + ", ".join(
        f"> (RoomTileMap+{row}*{WIDTH})" for row in range(HEIGHT)))

    for name, register in zip(("TilePF0", "TilePF1", "TilePF2"), range(3)):
        lines.append(f"{name}:")
        lines.append("  .byte " + ", ".join(
            f"${triple[register]:02x}" for triple in triples))

    output.write_text("\n".join(lines) + "\n")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: convert_room.py INPUT.txt OUTPUT.asm", file=sys.stderr)
        return 2
    try:
        rows = read_room(Path(sys.argv[1]))
        emit(rows, Path(sys.argv[2]))
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())