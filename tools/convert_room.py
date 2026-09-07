#!/usr/bin/env python3
"""Convert a 20x12 text room into a HERO-style reflected room include.

Grid: 20 columns x 12 playable rows + a 4-row grey HUD band below (drawn by
the kernel, not stored in room data). Each tile is 8 color-clocks wide and 12
scanlines tall, so the 12 playable rows fill the top 144 lines and the HUD the
bottom 48 of the 192-line screen. The TIA reflects the 20-bit playfield
(CTRLPF D0=1), so rooms must be left-right symmetric; the kernel emits one
PF0/PF1/PF2 triple per tile row, written once per 12-line band.

Emitted data:
  - RoomTileMap + RoomRowLo/Hi: one byte per tile for the 6502 collision code.
  - TilePF0/TilePF1/TilePF2: one byte per tile row for the kernel.
All per-row tables (PF triples and row pointers) are PADDED to 16 bytes so
bank0's table arithmetic (+16 / +16 / +32) works unchanged; only the first
12 entries are drawn/read.
"""

from pathlib import Path
import sys

WIDTH = 20
HEIGHT = 12                 # playable tile rows (rows 12-15 are the HUD band)
TABLE_STRIDE = 16           # padded per-row table size (bank0 index math)


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


def emit(rows: list[str], output: Path, prefix: str = "", source: str = "room") -> None:
    triples = [pf_values(row) for row in rows]
    map_name = prefix + "RoomTileMap"
    stride = max(TABLE_STRIDE, len(rows))

    lines = [
        f"; Generated from {source}. Do not edit by hand.",
    ]
    if not prefix:
        lines.append(f"ROOM_TILE_COLUMNS = {WIDTH}")
        lines.append(f"ROOM_TILE_ROWS = {len(rows)}")
    lines.append(f"{map_name}:")
    for row in rows:
        bytes_ = [1 if cell == "#" else 0 for cell in row]
        lines.append("  .byte " + ", ".join(f"${b:02x}" for b in bytes_))

    # Row pointer tables are padded to the table stride (bank0 indexes them
    # with (+0 lo, +16 hi)); padding rows are never dereferenced (the player
    # stays within the 12 playable rows) but keep the +16 offset valid.
    row_los = [f"< ({map_name}+{row}*{WIDTH})" for row in range(len(rows))]
    row_los += [row_los[0]] * (stride - len(row_los))
    row_his = [f"> ({map_name}+{row}*{WIDTH})" for row in range(len(rows))]
    row_his += [row_his[0]] * (stride - len(row_his))
    lines.append(f"{prefix}RoomRowLo:")
    lines.append("  .byte " + ", ".join(row_los))
    lines.append(f"{prefix}RoomRowHi:")
    lines.append("  .byte " + ", ".join(row_his))

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