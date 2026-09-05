#!/usr/bin/env python3
"""Convert a 20x16 text room into an assembler tile-map include."""

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


def emit(rows: list[str], output: Path) -> None:
    lines = [
        "; Generated from rooms/level_001_room_001.txt. Do not edit by hand.",
        f"ROOM_TILE_COLUMNS = {WIDTH}",
        f"ROOM_TILE_ROWS = {HEIGHT}",
        "RoomTileMap:",
    ]
    lines.extend(f"  .byte " + ", ".join("$01" if cell == "#" else "$00" for cell in row)
                 for row in rows)
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
