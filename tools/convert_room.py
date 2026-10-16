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
    Format: 1 byte count, then count * 2 packed bytes —
    [x<<2|y], [w<<2|h] (x,w <= 63 in 4px cols; y,h band 0-3).
    The EnterRoom cache copy unpacks to the 4-byte walk form (x, y, w, h).
    Coordinates are DISPLAY columns (4 color clocks each, left half =
    columns 0-19) — the runtime compares them against px/4 text columns
    directly, so logical cell c is emitted as x=2c, w=2*cell_w (D7 pair).
    The collision routine mirrors each rectangle to the right half at
    runtime, so only the left-half layout is stored.
    Hot records (5 bytes: mask, x, y, w, h) stay UNPACKED after the
    hot-count byte.
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
        if any(cell not in ".#HPVC" for cell in row):
            raise ValueError(
                f"{path}: row {number} contains a character other than "
                "., #, H, P, V or C"
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
    Hot rock (H) is solid for the playfield, same as #; feature cells
    (P phase / V vertical crunch / C horizontal crunch) are solid too.
    """
    solid = [cell in "#HPVC" for cell in row]
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
          asym_ball_x: int = 0,
          asym_m1_x: int = 0,
          hot_m1: list[tuple[int, int]] | None = None,
          door: bool = False,
          m1_door: bool = False,
          hot: bool | None = None) -> list[str]:
    """Build the asm lines for a grid (shared by per-room and per-model emission).

    asym_rows (D2/D3, models only): resolved right-half rows in right_col
    order (col 0 = center-adjacent) when the model carries asym_patches.
    asym_ball_x: D6 ball x (SetObjectXPos arg, drawn clocks [A-7, A]) from
    resolve_asym_patches — emitted with the flag.
    asym_m1_x: D6 M1 x (left-col block, SetObjectXPos arg) — 0 = no M1.
    hot_m1: (row, col) cells of side-1 (M1) patches that sit on the hot
    band (mid_band_type) — emitted as mask-$00 hot records in the LEFT
    stream: the M1 cell is PF-open by envelope so it never lands in
    find_rectangles(rows, "H") — without this record touching the block
    on a hot band never ran the hot-death check (and a hot-only model
    would not even pulse its band). $00 = no blastable parent → never
    dies with a wall (the strip dies via EnemyDeadMask b4 instead).
    After the TilePF tables EVERY model gets a 2-byte packed meta block:
        M<id>MetaA:  .byte ((m1_col+1)<<4) | band_mask | (b3 = left door)
                     (b0-2 = band0/1/2 ENABL gates: bit set = band differs
                      from its mirror = ball band; staged to BandTab $ED-$EF
                      as $01/$00. m1_col+1: 0 = no M1 patch. b3 set = the
                      M1 strip is a LOCKED_DOOR async patch — P2b sizes M1
                      to 4 clk and the key (not the bomb) opens it.)
        M<id>MetaB:  .byte (ball_col+1) or 0, b7 = async door/vcrunch,
                     b6 = mid_band_type hot (rule 2026-10-14)
                     (ball_col: BallX = 87+8*ball_col, staged to Temp $88
                      via 8*(ball_col+1)+86; 0 = no ball = symmetric.
                      b7 set = the model's side-0 strip is a LOCKED_DOOR
                      async patch — P2 stages CTRLPF $25 instead of $35
                      (also set for vcrunch: the shutter kill gate).
                      Staging must mask b7/b6 out of the ball-col math.
                      b6 set = the model's mid_band_type is Hot: the
                      shutter/crunch kill tests use touch semantics (any
                      part of the drawn block) instead of containment.)
    bank2 reads this block (StageBandTab in the BuildColupF tail) — a bank0
    (RoomPF0Lo) read would fetch bank0's $F9xx zero pad. M1X = 8*(m1_col+1)-1
    = 7+8*left_col, staged to CollisionEndX $8E (kill-gated by
    EnemyDeadMask b3/b4). MetaB=0 ⇔ symmetric (verify_build).
    Asym models continue with (RightPF0 now at TilePF0+11):
        M<id>RightPF0/1/2:  3 bytes (stride 3; D4: pf_values(reversed(B)))
        M<id>RightRects:    same stream shape as RoomRects; x/w in
                            right-half cell space x2 (x=0 center-adjacent,
                            4px cols), y/band rows; hard-fails above the
                            WallMask budget (4 maskable rects, Risk 1).
    Symmetric models (asym_rows=None) emit meta 0,0 and no Right* block.
    """
    triples = [pf_values(row) for row in rows]
    stride = max(TABLE_STRIDE, len(rows))

    out = [
        f"; Generated from {source}. Do not edit by hand.",
    ]
    if not prefix:
        out.append(f"ROOM_TILE_COLUMNS = {WIDTH}")
        out.append(f"ROOM_TILE_ROWS = {len(rows)}")

    # C (hcrunch) cells are NOT static rects (2026-10-16): the shutter's
    # covered prefix is DYNAMIC solidity — PhHcrEntry rewrites the band
    # every VBL from the clock (row & ~P(full) | P(n)), and the PF cell
    # walk follows the buffers. A static C-rect would wall the whole
    # sweep corridor once the C extent grows to the screen center.
    rects = find_rectangles(rows, solids="#HPV")
    hot_rects = find_rectangles(rows, solids="H")
    # find_rectangles works in logical cells (0..9); the runtime compares
    # rect x/w against 4-px display columns, so emit x/w in pairs (D7).
    rect_name = prefix + "RoomRects"
    out.append(f"{rect_name}:")
    out.append(f"  .byte {len(rects)}                  ; number of rectangles")
    for x, y, w, h in rects:
        p0, p1 = (2 * x) << 2 | y, (2 * w) << 2 | h
        if p0 > 255 or p1 > 255 or y > 3 or h > 3:
            raise ValueError(
                f"rect out of pack range: x={2*x} y={y} w={2*w} h={h} "
                f"(need x,w<=63 and y,h<=3 for the 2-byte rect format)")
        out.append(f"  .byte ${p0:02x}, ${p1:02x}  ; packed (x<<2|y, w<<2|h)")
    # Hot-only block after solid rects: death + pulse. Walks of solid rects
    # must stop at the count byte and never enter this section.
    # Record = mask, x, y, w, h (5 bytes). mask = BombMaskBit of the solid
    # rect that contains this hot rect (kernel's death check skips the hot
    # piece once that wall is blasted — hot_rock_wall_plan rule 4);
    # $00 = no blastable parent (parent outside rects 0-3, or none) → never dies.
    m1_hot = list(hot_m1 or ())
    # Feature cells (P phase, V vertical crunch, C horizontal crunch) ride
    # the hot record stream with b7 set in the mask byte — legacy masks
    # ($00/$08/$10/$20/$40) never set b7, so legacy emission is unchanged
    # (byte-identical when no feature char is present).
    #   $80 phase   : [mask, 2c, row, 2, 1] one record per cell (left-half
    #                  coords; the runtime mirrors like rects)
    #   $81 vcrunch : [mask, x, y, w, h] bbox of all V cells
    #   $82 hcrunch : [mask, 0, band, w, 1] band + prefix extent from col 0
    phase_cells: list[tuple[int, int]] = []
    v_cells: list[tuple[int, int]] = []
    c_cells: list[tuple[int, int]] = []
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if cell == "P":
                phase_cells.append((r, c))
            elif cell == "V":
                v_cells.append((r, c))
            elif cell == "C":
                c_cells.append((r, c))
    feats: list[str] = []
    special_kinds = {ch for ch, cells in (("P", phase_cells),
                                          ("V", v_cells),
                                          ("C", c_cells)) if cells}
    if door and special_kinds:
        raise ValueError(
            f"{source}: door model also has feature tile(s) "
            f"{sorted(special_kinds)} — special features are alone per room "
            "(door XOR phase XOR vcrunch XOR hcrunch)")
    if len(special_kinds) > 1:
        raise ValueError(
            f"{source}: mixed special features {sorted(special_kinds)} — "
            "special features are alone per room "
            "(door XOR phase XOR vcrunch XOR hcrunch)")
    for r, c in phase_cells:
        if r != 1:
            raise ValueError(
                f"{source}: phase cell at row {r} — special features live "
                "on the middle band (row 1)")
        feats.append(f"  .byte $80, {2 * c}, {r}, 2, 1  ; phase cell")
    if v_cells:
        rs = [r for r, _ in v_cells]
        cs = [c for _, c in v_cells]
        if any(r != 1 for r in rs):
            raise ValueError(
                f"{source}: vcrunch cells at rows {sorted(set(rs))} — the "
                "sprite shutter slices only the middle band (row 1; "
                "top/bottom bands are entry/exit corridors)")
        feats.append(
            f"  .byte $81, {2 * min(cs)}, {min(rs)}, "
            f"{2 * (max(cs) - min(cs) + 1)}, {max(rs) - min(rs) + 1}  "
            f"; vcrunch bbox")
    if c_cells:
        bands = {r for r, _ in c_cells}
        if bands != {1}:
            raise ValueError(
                f"{source}: hcrunch cells at rows {sorted(bands)} — the "
                "crunch band must be the middle band (row 1)")
        cols = sorted(c for _, c in c_cells)
        if cols != list(range(cols[-1] + 1)):
            raise ValueError(
                f"{source}: hcrunch cells at cols {cols} are not a contiguous "
                "prefix from col 0 (need cols 0..n in one band)")
        feats.append(
            f"  .byte $82, 0, {next(iter(bands))}, {2 * (cols[-1] + 1)}, 1  "
            f"; hcrunch band prefix")
    out.append(f"  .byte {len(hot_rects) + len(m1_hot) + len(feats)}              "
               f"; number of hot rectangles")
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

    # M1 patch cells on the hot band (PF-open by envelope → not in the 'H'
    # walk): mask $00 = never dies with a wall; the strip itself dies via
    # EnemyDeadMask b4 (OvM1Block skips the block path before the hot check).
    for mrow, mcol in m1_hot:
        out.append(f"  .byte $00, {2 * mcol}, {mrow}, 2, 1  "
                   f"; mask, x, y, w, h (M1 block cell, hot band)")
    out.extend(feats)


    for name, register in zip(("TilePF0", "TilePF1", "TilePF2"), range(3)):
        out.append(f"{prefix}{name}:")
        table = [f"${triple[register]:02x}" for triple in triples]
        table += ["$00"] * (stride - len(table))
        out.append("  .byte " + ", ".join(table))

    # Asym meta at TilePF0+9..+10 — 2 packed bytes, ALWAYS present
    # (bank2 StageBandTab reads blindly; bank0 gets staged copies in ZP).
    # MetaA = ((m1_col+1)<<4) | band_mask (b0-2 = band0/1/2 gates);
    # MetaB = ball_col+1 (0 = no ball). 0 nibbles = feature absent.
    band_mask = 0
    if asym_rows is not None:
        for band in range(3):
            if asym_rows[band] != rows[band][::-1]:
                band_mask |= 1 << band
    m1_col_plus = 0
    if asym_m1_x:
        m1_col_plus = ((asym_m1_x - 7) >> 3) + 1
    out.append(f"{prefix}MetaA:")
    if m1_door and not asym_m1_x:
        raise ValueError(
            f"{source}: LOCKED_DOOR side 1 needs an M1 patch strip")
    out.append(
        f"  .byte ${(m1_col_plus << 4) | band_mask | (0x08 if m1_door else 0):02x}"
        "                  ; (m1_col+1)<<4 | band mask"
        + (" | $08 left door" if m1_door else ""))
    ball_col_plus = 0
    if asym_ball_x:
        ball_col_plus = ((asym_ball_x - 87) >> 3) + 1
    # Sprite shutter (vcrunch_shutter_plan Phase B): a vcrunch model packs
    # MetaB b7 so bank2 PHMOverlay's miss path runs the shutter kill test
    # (the punched-open cell no longer trips the PF cell walk). b7 shares
    # its slot with the door flag — door+feature is rejected via "special
    # features are alone per room" above. The M1 slot cannot be shared
    # (the shutter stages CollisionEndX for its mirror M1 each frame):
    # an M1 strip patch or side-1 door would fight it every frame.
    # A side-0 ball patch IS allowed (user model 2026-10-14): the shutter
    # owns Temp $88/BallX while it runs; the static band marker yields.
    if hot is None:
        hot = any("H" in row for row in rows)
    has_vcrunch = any(cell == "V" for row in rows for cell in row)
    if has_vcrunch and (m1_door or asym_m1_x):
        raise ValueError(
            f"{source}: vcrunch cannot share a model with an M1 strip/side-1 "
            f"door (the shutter owns the M1 slot every frame)")
    if door:
        if not asym_ball_x:
            raise ValueError(
                f"{source}: LOCKED_DOOR needs a side-0 (ball) patch strip")
        out.append(f"{prefix}MetaB:")
        out.append(
            f"  .byte ${ball_col_plus | 0x80 | (0x40 if hot else 0):02x}"
            "                  ; (ball_col+1) | $80 async door"
            + (" | $40 hot" if hot else ""))
    else:
        out.append(f"{prefix}MetaB:")
        out.append(
            f"  .byte ${ball_col_plus | (0x80 if has_vcrunch else 0) | (0x40 if hot else 0):02x}"
            "                  ; (ball_col+1)"
            + (" | $80 vcrunch shutter" if has_vcrunch else
               ", 0 = no ball")
            + (" | $40 hot" if hot else ""))

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
        r_rects = find_rectangles(asym_rows, solids="#HPVC")
        if len(r_rects) > 4:
            found = ", ".join(
                f"(col {x}, row {y}, {w}x{h})" for x, y, w, h in r_rects)
            raise ValueError(
                f"{source}: {len(r_rects)} right wall rects > WallMask budget 4 "
                f"(Risk 1 — do not silently wrap); found: {found}. Merge the "
                "wall blocks on the right half (paint the gap between them, or "
                "erase the stray cell) — WallMask (BombPacked b3-6) has only 4 "
                "destroy bits")
        # Phase 4 item 2's COMBINED left+right <= 4 is deferred: plan 4.2
        # gates it on 'once flag-gated masks exist' (right rects entering the
        # runtime cache). RightRects are ROM-only today (cell-walk PHM + ball
        # render consume no mask slots), and every real model's mirror
        # fragments to 3-6 rects — combined<=4 would block all asym content
        # (measured 2026-10-04: models 1-7 sum 6..12). Re-add when a cache
        # loader lands.
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
