#!/usr/bin/env python3
"""Convert a 10x3 text room into a HERO-style reflected room include.

Grid (D7, plan asymmetric_pf_plan): 10 logical columns x 3 playable bands +
a 48-line grey HUD band below (drawn by the kernel, not stored in room
data). One logical cell = 2 hardware PF pixels (8 color clocks); the TIA
reflects the 40-pixel playfield (CTRLPF D0=1), so rooms must be left-right
symmetric; the kernel emits one PF0/PF1/PF2 triple per tile row, written
once per 48-line band.

Emitted data (C11 2026-10-21 — a SHAPE block is 3 bytes):
  - Shape/Rows: three 1 B ROW-POOL indices (band 0/1/2), expanded by bank3
    `B3RoomBlocks` through the global `RowPoolPF0/1/2` columns into PF0Buf.
    Band 1's index byte b7 = the model's `mid_band_type` (hot) flag: hot
    cells only ever exist on model row 1, so the flag rides that band.
    The hot count + 5 B/record stream is GONE — HOT collision is derived
    from the PF row 1 the loader expands (`HotOverlapBody`, gated by MetaB
    b6), so a bombed parent cell stops being hot automatically (the punch
    clears the PF cell).
  - The legacy per-grid form (`with_meta=True`, the standalone convert_room
    CLI output) still emits RoomRects (count + 5 B records), TilePF0/1/2 and
    the packed meta pair — converter unit tests only, no stage data.
C5 (2026-10-20): the MetaA/MetaB pair left this block (the fixed
`TilePF0+9/+10` contract is retired) — it lives in the room EXTRAS stream
(`meta_bytes`), and the RightPF/RightRects payload is gone (dead since C4).
All per-row tables (PF triples) are emitted at TABLE_STRIDE (= 3, the
playable bands) since S4.2; only the first 3 entries are drawn — the old
12-byte padding existed for bank0's +12/+12 pointer arithmetic, which
EnterRoom now does as +3/+3.
"""

from pathlib import Path
import sys

WIDTH = 10                  # D7: logical cells per half (was 20 pre-D7)
HEIGHT = 3                  # AUTHORED rows (the editor's grid). N=4 (C13,
                            # 2026-10-23) needs 4 drawn bands, so a shape block
                            # carries SHAPE_ROWS indices and a 3-row model is
                            # padded by repeating its bottom row until the
                            # editor grows a 4th row.
SHAPE_ROWS = 4              # bands the kernel draws (kernel TILE_ROWS)
TABLE_STRIDE = 3            # S4.2: per-row table size (was 12 — kernel
                            # EnterRoom now does +3/+3)
WALL_PARENT_MASK = 0x08      # hot record mask: nonzero = PF-cell parent gate


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


class RowPool:
    """C3 (2026-10-20) — the global row dictionary (one per build).

    Every model band is a (PF0, PF1, PF2) triple; the stage has far fewer
    DISTINCT rows than row slots (12 distinct / 36 slots at C3 landing), so
    the pool stores each row once (3 B) and the shape block carries a 1 B
    index per band instead of the 9 raw PF bytes.

    Emission form: three SoA columns (`RowPoolPF0/1/2`, 1 B/row) so the
    loader needs ONE index register (X) and no second pointer:

        lda RowPoolPF0,X / sta PF0Buf,Y
        lda RowPoolPF1,X / sta PF0Buf+3,Y
        lda RowPoolPF2,X / sta PF0Buf+6,Y

    Indices are stable (first-use order) because conversion walks the models
    in sorted id order; the pool is emitted after all shapes, in
    models_data.asm, so `_shape_stream()`'s label order is untouched.
    """

    def __init__(self) -> None:
        self.rows: list[tuple[int, int, int]] = []
        self._index: dict[tuple[int, int, int], int] = {}
        self.uses = 0

    def index_of(self, triple: tuple[int, int, int],
                 source: str = "room") -> int:
        idx = self._index.get(triple)
        if idx is None:
            if len(self.rows) > 0xFF:
                raise ValueError(
                    f"{source}: row pool needs more than 256 rows "
                    "(3 rows x 256 = 768 B > bank2's block slot) — merge "
                    "model bands or split the level-data bank")
            idx = len(self.rows)
            self._index[triple] = idx
            self.rows.append(triple)
        else:
            # dedupe must never rewrite a row: the loader expands indices
            assert self.rows[idx] == triple, (
                f"{source}: row pool index {idx} holds {self.rows[idx]} "
                f"but asked for {triple}")
        self.uses += 1
        return idx

    def lines(self) -> list[str]:
        """asm for LEVEL_ROW_COUNT + the three columns (models_data.asm)."""
        out = [
            "",
            "; C3 (2026-10-20): ROW DICTIONARY — one 3 B entry per DISTINCT",
            "; (PF0,PF1,PF2) band row for the whole game. A shape block carries",
            "; 3 one-byte indices (band 0/1/2) into these SoA columns; bank2's",
            "; B3RoomBlocks expands them into PF0Buf at room load.",
            f"LEVEL_ROW_COUNT = {len(self.rows)}",
        ]
        for name, reg in (("RowPoolPF0", 0), ("RowPoolPF1", 1),
                          ("RowPoolPF2", 2)):
            out.append(f"{name}:")
            if self.rows:
                out.append("  .byte " + ", ".join(
                    f"${row[reg]:02x}" for row in self.rows))
            else:
                out.append("  .byte $00  ; no rows (empty stage)")
        return out


def pf_values(row: str) -> tuple[int, int, int]:
    """Map a 10-column logical row (D7 grid) to PF0/PF1/PF2 bytes.

    Each logical cell c sets the hardware bit PAIR (2c, 2c+1). Display-col
    mapping with reflection (left half, 4 color clocks per PF bit):
      expanded cols 0-3   -> PF0 bits 4-7 (bit 4 = leftmost)
      expanded cols 4-11  -> PF1 bits 7-0 (bit 7 = display col 4)
      expanded cols 12-19 -> PF2 bits 0-7 (bit 0 = display col 12)
    Hot rock (H) is solid for the playfield, same as #; feature cells
    (P phase / C horizontal crunch) are solid too.
    """
    solid = [cell in "#HPC" for cell in row]
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


def hot_records(rows: list[str], hot_m1: list[tuple[int, int]] | None = None,
                hot: bool | None = None, door: bool = False,
                source: str = "room") -> tuple[list[str], list[str]]:
    """The hot stream section: (legacy hot lines, feature record lines).

    C4 (2026-10-20): the solid rect list is retired, so a block's first
    section is `count` + 5 B records. C5 (2026-10-20): convert_level also
    reuses this for the per-room extras hot section — a feature room's stream
    is built from the ROOM rows (feature cells split/remove the shape's
    legacy hot rects), so the runtime walkers see the same bytes a per-room
    block used to carry.

    Record = mask, x, y, w, h (5 bytes). mask: b7 = feature class; $00 =
    M1 block cell (dies with the strip, EnemyDeadMask b4); nonzero = wall
    parent (the runtime gates on that parent's PF cell still being solid,
    so a thin parent dies with the bomb punch and a thick one never does).
    """
    # C (hcrunch) cells are NOT static rects (2026-10-16): the shutter's
    # covered prefix is DYNAMIC solidity — PhHcrEntry rewrites the band
    # every VBL from the clock (row & ~P(full) | P(n)), and the PF cell
    # walk follows the buffers. `walls` is still computed for the hot parent
    # mask only.
    walls = find_rectangles(rows, solids="#HPV")
    hot_rects = find_rectangles(rows, solids="H")
    hot_lines: list[str] = []
    m1_hot = list(hot_m1 or ())
    # Feature cells (P phase, C horizontal crunch) ride the hot record stream
    # with b7 set in the mask byte — legacy masks ($00/$08/$10/$20/$40) never
    # set b7, so legacy emission is unchanged (byte-identical when no feature
    # char is present).
    #   $80 phase   : [mask, 2c, row, 2, 1] one record per cell (left-half
    #                  coords; the runtime mirrors like rects)
    #   $82 hcrunch : [mask, 0, band, w, 1] band + prefix extent from col 0
    phase_cells: list[tuple[int, int]] = []
    if any(cell == "V" for row in rows for cell in row):
        raise ValueError(
            f"{source}: tile 11 (VCRUNCH) removed; use PHASE 10")
    c_cells: list[tuple[int, int]] = []
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if cell == "P":
                phase_cells.append((r, c))
            elif cell == "C":
                c_cells.append((r, c))
    feats: list[str] = []
    special_kinds = {ch for ch, cells in (("P", phase_cells),
                                          ("C", c_cells)) if cells}
    if door and special_kinds:
        raise ValueError(
            f"{source}: door model also has feature tile(s) "
            f"{sorted(special_kinds)} — special features are alone per room "
            "(door XOR phase XOR hcrunch)")
    if len(special_kinds) > 1:
        raise ValueError(
            f"{source}: mixed special features {sorted(special_kinds)} — "
            "special features are alone per room "
            "(door XOR phase XOR hcrunch)")
    for r, c in phase_cells:
        if r != 1:
            raise ValueError(
                f"{source}: phase cell at row {r} — special features live "
                "on the middle band (row 1)")
        feats.append(f"  .byte $80, {2 * c}, {r}, 2, 1  ; phase cell")
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
    for hx, hy, hw, hh in hot_rects:
        parent = next(
            (
                i
                for i, (x, y, w, h) in enumerate(walls)
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
        else:
            # nonzero = "wall parent" (PF-cell gate). The old BombMaskBit
            # index died with the rect list; only zero/nonzero matters now.
            mask = WALL_PARENT_MASK
        hot_lines.append(f"  .byte ${mask:02x}, {2 * hx}, {hy}, {2 * hw}, {hh}  ; mask, x, y, w, h (4px cols)")

    # M1 patch cells on the hot band (PF-open by envelope → not in the 'H'
    # walk): mask $00 = never dies with a wall; the strip itself dies via
    # EnemyDeadMask b4 (OvM1Block skips the block path before the hot check).
    for mrow, mcol in m1_hot:
        hot_lines.append(f"  .byte $00, {2 * mcol}, {mrow}, 2, 1  "
                         f"; mask, x, y, w, h (M1 block cell, hot band)")
    return hot_lines, feats


def meta_bytes(rows: list[str], asym_rows: list[str] | None = None,
               asym_ball_x: int = 0, asym_m1_x: int = 0,
               hot: bool | None = None, door: bool = False,
               m1_door: bool = False, m1_right: bool = False,
               source: str = "room") -> tuple[int, int]:
    """(MetaA, MetaB) packed pair — C5 (2026-10-20) moved into the room EXTRAS.

    MetaA = ((m1_col+1)<<4) | band_mask | b3 (left door) | b0 (right half)
            b0-2 = band0/1/2 ENABL gates: bit set = band differs from its
            mirror = ball band; staged to BandTab $ED-$EF as $01/$00.
    MetaB = (ball_col+1) | b7 (async door) | b6 (mid_band_type hot)
            ball_col: BallX = 87+8*ball_col, staged to Temp $88 via
            8*(ball_col+1)+86; 0 = no ball.
    """
    if asym_rows is not None:
        if len(asym_rows) != len(rows) or any(
                len(r) != WIDTH for r in asym_rows):
            raise ValueError(
                f"{source}: asym rows must be {len(rows)}x{WIDTH} like the left rows")
    band_mask = 0
    if asym_rows is not None:
        for band in range(3):
            if asym_rows[band] != rows[band][::-1]:
                band_mask |= 1 << band
    m1_col_plus = 0
    if asym_m1_x:
        m1_col_plus = ((asym_m1_x - 7) >> 3) + 1
    if m1_door and not asym_m1_x:
        raise ValueError(
            f"{source}: LOCKED_DOOR side 1 needs an M1 patch strip")
    meta_a = ((m1_col_plus << 4) | band_mask
              | (0x08 if m1_door else 0) | (0x01 if m1_right else 0))
    ball_col_plus = 0
    if asym_ball_x:
        ball_col_plus = ((asym_ball_x - 87) >> 3) + 1
    if hot is None:
        hot = any("H" in row for row in rows)
    if door:
        if not asym_ball_x:
            raise ValueError(
                f"{source}: LOCKED_DOOR needs a side-0 (ball) patch strip")
        meta_b = ball_col_plus | 0x80 | (0x40 if hot else 0)
    else:
        meta_b = ball_col_plus | (0x40 if hot else 0)
    return meta_a, meta_b


def lines(rows: list[str], prefix: str = "", source: str = "room",
          asym_rows: list[str] | None = None,
          asym_ball_x: int = 0,
          asym_m1_x: int = 0,
          hot_m1: list[tuple[int, int]] | None = None,
          door: bool = False,
          m1_door: bool = False,
          m1_right: bool = False,
          hot: bool | None = None,
          with_meta: bool = True,
          pool: RowPool | None = None) -> list[str]:
    """Build the asm lines for a grid (shared by per-room and per-model emission).

    asym_rows (D2/D3, models only): resolved right-half rows in right_col
    order (col 0 = center-adjacent) when the model carries asym_patches.
    asym_ball_x: D6 ball x (SetObjectXPos arg, drawn clocks [A-7, A]) from
    resolve_asym_patches — emitted with the flag.
    asym_m1_x: D6 M1 x (left-col block, SetObjectXPos arg) — 0 = no M1.
    hot_m1: (row, col) cells of side-1 (M1) patches that sit on the hot
    band (mid_band_type) — emitted as mask-$00 hot records in the LEGACY
    per-grid stream (with_meta=True, converter unit tests only). Stage data
    no longer carries them: C11 (2026-10-21) derives the M1 block cell from
    the extras patch list at load (`RoomM1Hot`).

    C5 (2026-10-20) contract change — the MetaA/MetaB pair no longer lives
    in this block (the `TilePF0+9/+10` fixed-offset contract is retired):
    it moved into the room EXTRAS stream (`meta_bytes` feeds it). The
    RightPF/RightRects payload is gone too (dead since C4 — the D6 ball
    overlay and the cell walk replaced right-rect collision).

    C3 (2026-10-20): a SHAPE block (`with_meta=False`) stores the bands as
    three 1 B indices into the shared `RowPool` (3 B/row emitted once for the
    whole game), not the 9 raw PF bytes.

    C11 (2026-10-21): the shape block is EXACTLY those 3 index bytes — the
    hot count and the 5 B/record hot stream are gone (hot is derived from
    the PF row 1 that the loader expands, gated by MetaB b6). Band 1's index
    byte carries b7 = `mid_band_type` (hot cells only ever exist on model
    row 1, so the flag rides that band's index; pool rows stay <= 127).
    `pool` is REQUIRED for that form. The standalone per-grid form
    (`with_meta=True`) keeps the historical stream + TilePF0/1/2 + the
    packed meta pair for the converter unit tests.

    `with_meta=False` emits the shape-only block (what convert_level writes
    for the shared M<id> shapes). with_meta=True keeps the historical
    meta-pair emission for the standalone per-grid path and the converter
    unit tests (asym_rows/asym_* still select the packed values).
    """
    triples = [pf_values(row) for row in rows]
    stride = max(TABLE_STRIDE, len(rows))

    out = [
        f"; Generated from {source}. Do not edit by hand.",
    ]
    if not prefix:
        out.append(f"ROOM_TILE_COLUMNS = {WIDTH}")
        out.append(f"ROOM_TILE_ROWS = {len(rows)}")

    # C11 (2026-10-21): the SHAPE block is 3 row-pool indices ONLY. hot is
    # derived at runtime from the PF row 1 the loader expands (gated by MetaB
    # b6), so the legacy hot stream is not emitted into stage data.
    # hot_records still runs for the LEGACY per-grid form and, for a shape,
    # only to raise the precise reason when a feature tile sneaks into the
    # grid (VCRUNCH / mixed / off-band). Its FEATURE section feeds the room
    # extras stream in convert_level.
    hot_lines, feats = [], []
    if with_meta or any(cell in "PCV" for row in rows for cell in row):
        hot_lines, feats = hot_records(rows, hot_m1=hot_m1, hot=hot,
                                       door=door, source=source)
    if not with_meta:
        if hot_m1:
            raise ValueError(
                f"{source}: a shape block cannot carry M1 hot records — the "
                "M1 block cell is derived from the room's patch list at load")
        if feats:
            raise ValueError(
                f"{source}: feature cell(s) in a shared shape block — feature "
                "cells live on the ROOM (room.feature_cells + extras)")
        # C3 (2026-10-20): 3 row-pool indices instead of 9 raw PF bytes.
        if pool is None:
            raise ValueError(
                f"{source}: with_meta=False needs a RowPool — a shape block "
                "stores row-pool indices (C3)")
        indices = [pool.index_of(triple, source) for triple in triples]
        # C13 (2026-10-23): the cave draws SHAPE_ROWS bands. Until the editor
        # authors a 4th row, the bottom band repeats the last authored row
        # (the same default the loader used during the kernel phase).
        while len(indices) < SHAPE_ROWS:
            indices.append(indices[-1])
        # Equivalence gate: expanding the emitted indices must reproduce the
        # pre-C3 raw bytes, band for band. The loader does exactly this
        # expansion, so a drift here would show up as wrong playfield cells.
        for band, want in enumerate(triples):
            got = pool.rows[indices[band]]
            if got != want:
                raise ValueError(
                    f"{source}: band {band} expands to {got} but the rows "
                    f"encode {want} (row pool drift)")
        if any(idx > 0x7F for idx in indices):
            raise ValueError(
                f"{source}: row-pool index > $7F — band 1's b7 is the "
                "mid_band_type hot flag (LEVEL_ROW_COUNT must stay <= 128)")
        # C11: the flag rides the middle band. Derive it defensively too: a
        # shape whose rows contain 'H' IS hot (rows_from_json derives 'H'
        # from mid_band_type, so the two can only disagree by a caller bug).
        if hot or any(cell == "H" for row in rows for cell in row):
            indices[1] |= 0x80      # C11: hot flag rides the middle band
        out.append(f"{prefix}Shape:")
        out.append(f"{prefix}Rows:")
        out.append("  .byte " + ", ".join(
            f"${idx:02x}" for idx in indices)
            + "  ; row-pool indices (band 0-3; band1 b7 = mid_band hot)")
        return out

    out.append("; LEGACY per-grid block (converter unit tests only): hot "
               "stream + PF + meta")
    out.append(f"{prefix}RoomRects:")
    out.append(f"  .byte {len(hot_lines) + len(feats)}              "
               f"; number of hot rectangles")
    out.extend(hot_lines)
    out.extend(feats)
    for name, register in zip(("TilePF0", "TilePF1", "TilePF2"), range(3)):
        out.append(f"{prefix}{name}:")
        table = [f"${triple[register]:02x}" for triple in triples]
        table += ["$00"] * (stride - len(table))
        out.append("  .byte " + ", ".join(table))
    meta_a, meta_b = meta_bytes(rows, asym_rows=asym_rows,
                               asym_ball_x=asym_ball_x, asym_m1_x=asym_m1_x,
                               hot=hot, door=door, m1_door=m1_door,
                               m1_right=m1_right, source=source)
    out.append(f"{prefix}MetaA:")
    out.append(
        f"  .byte ${meta_a:02x}"
        "                  ; (m1_col+1)<<4 | band mask"
        + (" | $08 door" if m1_door else "")
        + (" | $01 right half" if m1_right else ""))
    out.append(f"{prefix}MetaB:")
    out.append(
        f"  .byte ${meta_b:02x}"
        "                  ; (ball_col+1)"
        + (", 0 = no ball" if not (meta_b & 0x0F) else "")
        + (" | $80 async door" if door else "")
        + (" | $40 hot" if (meta_b & 0x40) else ""))
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
