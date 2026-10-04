#!/usr/bin/env python3
"""Convert a 10x3 text room into a HERO-style reflected room include.

Grid (D7, plan asymmetric_pf_plan): 10 logical columns x 3 playable bands +
a 48-line grey HUD band below (drawn by the kernel, not stored in room
data). One logical cell = 2 hardware PF pixels (8 color clocks); the TIA
reflects the 40-pixel playfield (CTRLPF D0=1), so rooms must be left-right
symmetric; the kernel emits one PF0/PF1/PF2 triple per tile row, written
once per 48-line band.

Emitted data:
  - RoomRects: compressed rectangle list for the 6502 collision code.
    Format: 1 byte count, then count * 4 bytes (x, y, width, height).
    Coordinates are DISPLAY columns (4 color clocks each, left half =
    columns 0-19) — the runtime compares them against px/4 text columns
    directly, so logical cell c is emitted as x=2c, w=2*cell_w (D7 pair).
    The collision routine mirrors each rectangle to the right half at
    runtime, so only the left-half layout is stored.
  - TilePF0/TilePF1/TilePF2: one byte per tile row for the kernel; each
    logical cell sets a PF bit PAIR (encoder bit-pairing, D7).
All per-row tables (PF triples) are emitted at TABLE_STRIDE (= 3, the
playable bands) since S4.2; only the first 3 entries are drawn — the old
12-byte padding existed for bank0's +12/+12 pointer arithmetic, which
EnterRoom now does as +3/+3.
"""

from pathlib import Path
import sys

WIDTH = 10                  # D7: logical cells per half (was 20 pre-D7)
HEIGHT = 3                  # playable color bands (HUD is drawn separately)
TABLE_STRIDE = 3            # S4.2: per-row table size = the 3 playable bands
                            # (was 12 — kernel EnterRoom now does +3/+3)
MASK_BITS = (0x08, 0x10, 0x20, 0x40)  # kernel BombMaskBit, wall rects 0-3


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
    """Map a 10-column logical row (D7 grid) to PF0/PF1/PF2 bytes.

    Each logical cell c sets the hardware bit PAIR (2c, 2c+1). Display-col
    mapping with reflection (left half, 4 color clocks per PF bit):
      expanded cols 0-3   -> PF0 bits 4-7 (bit 4 = leftmost)
      expanded cols 4-11  -> PF1 bits 7-0 (bit 7 = display col 4)
      expanded cols 12-19 -> PF2 bits 0-7 (bit 0 = display col 12)
    Hot rock (H) is solid for the playfield, same as #.
    """
    solid = [cell in "#H" for cell in row]
    if len(solid) != WIDTH:
        raise ValueError(f"pf_values: expected {WIDTH} columns, got {len(row)}")
    s20 = [s for s in solid for _ in (0, 1)]   # D7 bit-pairing
    pf0 = 0
    for col in range(4):
        if s20[col]:
            pf0 |= 0x10 << col   # PF0: col0->bit4 (leftmost), col1->bit5, col2->bit6, col3->bit7
    pf1 = 0
    for col in range(4, 12):
        if s20[col]:
            pf1 |= 0x80 >> (col - 4)
    pf2 = 0
    for col in range(12, 20):
        if s20[col]:
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


def lines(rows: list[str], prefix: str = "", source: str = "room",
          asym_rows: list[str] | None = None,
          asym_ball_x: int = 0) -> list[str]:
    """Build the asm lines for a grid (shared by per-room and per-model emission).

    asym_rows (D2/D3, models only): resolved right-half rows in right_col
    order (col 0 = center-adjacent) when the model carries asym_patches.
    asym_ball_x: D6 ball x (SetObjectXPos arg, drawn clocks [A-7, A]) from
    resolve_asym_patches — emitted with the flag.
    After the TilePF tables EVERY model gets the 5-byte meta block:
        M<id>AsymFlag:  .byte 0|1    (0 = symmetric: runtime skips ball)
        M<id>BallX:     .byte 0|87+8*right_col  (staged to Temp, bank2)
        M<id>Band0/1/2: .byte 00|ff  (TilePF0+11..+13; Phase 3 ENABL gate:
                        $ff = band differs from its mirror = ball band,
                        $00 = plain mirror; staged to BandTab $ED-$EF)
    bank2 reads this block (StageBandTab in the BuildColupF tail) — a bank0
    (RoomPF0Lo) read would fetch bank0's $F9xx zero pad. BallX doubles as
    the flag (0 ⇔ symmetric, enforced by verify_build).
    Asym models continue with (RightPF0 now at TilePF0+14):
        M<id>RightPF0/1/2:  3 bytes (stride 3; D4: pf_values(reversed(B)))
        M<id>RightRects:    same stream shape as RoomRects; x/w in
                            right-half cell space x2 (x=0 center-adjacent,
                            4px cols), y/band rows; hard-fails above the
                            WallMask budget (4 maskable rects, Risk 1).
    Symmetric models (asym_rows=None) emit meta 0,0,0,0,0 and no Right*
    block — otherwise byte-identical to pre-D7/Phase-1 output.
    """
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
    # find_rectangles works in logical cells (0..9); the runtime compares
    # rect x/w against 4-px display columns, so emit x/w in pairs (D7).
    rect_name = prefix + "RoomRects"
    out.append(f"{rect_name}:")
    out.append(f"  .byte {len(rects)}                  ; number of rectangles")
    for x, y, w, h in rects:
        out.append(f"  .byte {2 * x}, {y}, {2 * w}, {h}  ; x, y, width, height (4px cols)")
    # Hot-only block after solid rects: death + pulse. Walks of solid rects
    # must stop at the count byte and never enter this section.
    # Record = mask, x, y, w, h (5 bytes). mask = BombMaskBit of the solid
    # rect that contains this hot rect (kernel's death check skips the hot
    # piece once that wall is blasted — hot_rock_wall_plan rule 4);
    # $00 = no blastable parent (parent outside rects 0-3, or none) → never dies.
    out.append(f"  .byte {len(hot_rects)}              ; number of hot rectangles")
    for hx, hy, hw, hh in hot_rects:
        parent = next(
            (
                i
                for i, (x, y, w, h) in enumerate(rects)
                if x <= hx and y <= hy and hx + hw <= x + w and hy + hh <= y + h
            ),
            None,
        )
        if parent is None:
            print(
                f"warning: hot rect ({hx},{hy},{hw},{hh}) not inside any wall rect",
                file=sys.stderr,
            )
            mask = 0
        elif parent < len(MASK_BITS):
            mask = MASK_BITS[parent]
        else:
            mask = 0
        out.append(f"  .byte ${mask:02x}, {2 * hx}, {hy}, {2 * hw}, {hh}  ; mask, x, y, w, h (4px cols)")

    for name, register in zip(("TilePF0", "TilePF1", "TilePF2"), range(3)):
        out.append(f"{prefix}{name}:")
        table = [f"${triple[register]:02x}" for triple in triples]
        table += ["$00"] * (stride - len(table))
        out.append("  .byte " + ", ".join(table))

    # Asym meta at TilePF0+9..+13 — ALWAYS present (bank2 StageBandTab
    # reads blindly; bank0 gets the staged copies in ZP).
    out.append(f"{prefix}AsymFlag:")
    if asym_rows is None:
        out.append("  .byte 0                  ; 0 = symmetric (mirror cave)")
        out.append(f"{prefix}BallX:")
        out.append("  .byte 0                  ; ball x unused when symmetric")
    else:
        out.append("  .byte 1                  ; 1 = asymmetric (D6 ball mask)")
        out.append(f"{prefix}BallX:")
        out.append(f"  .byte ${asym_ball_x:02x}                  "
                   f"; D6 ball x = 87+8*right_col ({asym_ball_x})")

    # Phase 3 per-band ENABL gate bytes (TilePF0+11..+13). $ff = this band's
    # right row is NOT the plain mirror of the left row (has an asym patch),
    # $00 = plain mirror.
    for band in range(3):
        on = asym_rows is not None and \
            asym_rows[band] != rows[band][::-1]
        out.append(f"{prefix}Band{band}:")
        out.append(f"  .byte ${0xff if on else 0:02x}                  "
                   f"; band {band} ENABL gate ($ff = ball band)")

    if asym_rows is not None:
        if len(asym_rows) != len(rows) or any(
                len(r) != WIDTH for r in asym_rows):
            raise ValueError(
                f"{source}: asym rows must be {len(rows)}x{WIDTH} like the left rows")
        # D4 reflect: stored right trio = pf_values(reversed(B)); B is in
        # right_col order (col 0 = center-adjacent).
        r_triples = [pf_values(r[::-1]) for r in asym_rows]
        for name, register in zip(("RightPF0", "RightPF1", "RightPF2"), range(3)):
            out.append(f"{prefix}{name}:")
            out.append("  .byte " + ", ".join(
                f"${t[register]:02x}" for t in r_triples))
        r_rects = find_rectangles(asym_rows, solids="#H")
        if len(r_rects) > 4:
            raise ValueError(
                f"{source}: {len(r_rects)} right wall rects > WallMask budget 4 "
                f"(Risk 1 — do not silently wrap)")
        if len(rects) + len(r_rects) > 4:
            # Phase 4 item 2: the bomb WallMask has 4 slots TOTAL — right-half
            # rects consume the same slots once they enter the runtime cache.
            raise ValueError(
                f"{source}: combined wall rects {len(rects)} left + "
                f"{len(r_rects)} right > WallMask budget 4 across both halves "
                f"(Risk 1 — do not silently wrap)")
        r_hot = find_rectangles(asym_rows, solids="H")
        out.append(f"{prefix}RightRects:")
        out.append(f"  .byte {len(r_rects)}                  ; number of rectangles")
        for x, y, w, h in r_rects:
            out.append(f"  .byte {2 * x}, {y}, {2 * w}, {h}  ; x(right_col*2), y, w, h")
        out.append(f"  .byte {len(r_hot)}              ; number of hot rectangles")
        for hx, hy, hw, hh in r_hot:
            parent = next(
                (
                    i
                    for i, (x, y, w, h) in enumerate(r_rects)
                    if x <= hx and y <= hy and hx + hw <= x + w and hy + hh <= y + h
                ),
                None,
            )
            if parent is None:
                print(f"warning: hot rect ({hx},{hy},{hw},{hh}) not inside any "
                      f"right wall rect", file=sys.stderr)
                mask = 0
            elif parent < len(MASK_BITS):
                mask = MASK_BITS[parent]
            else:
                mask = 0
            out.append(f"  .byte ${mask:02x}, {2 * hx}, {hy}, {2 * hw}, {hh}  ; mask, x, y, w, h")

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
