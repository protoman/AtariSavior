#!/usr/bin/env python3
"""Asym data pipeline + D6 envelope fixtures (asymmetric_pf_plan Phase 1
items 3-4 / CHECK 1).

Covers:
   1. synthetic asymmetric model: resolve_asym_patches + convert_room.lines
      emit packed meta (MetaA/MetaB), stride-3 right rows with hand-derived
      CHECK 0 encoder bytes, and a right rect stream;
  2. legacy model (no asym_patches field): emission has no asym block and
     is byte-identical to the plain symmetric call;
  3. envelope rejects (fail loudly): >2 patches (two-block cap),
     duplicate cell, subtractive patch, patches spanning
     >1 column (also the >1-cell run case), out-of-range row/col, malformed
     patch, M1 side=2/open-tile/two-left-cols, M1 wall-hide guard
     (patch-on-wall + open-unpatched);
  4. convert-side right-rect budget: >4 right wall rects raises (Risk 1);
  5. M1-only model (side=1, no ball) + case 3 fixture (side-by-side
     ball+M1, ball_x=143, m1_x=71).

Run: /home/iuri/python3/bin/python3 tools/test_asym_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_level  # noqa: E402
import convert_room  # noqa: E402

# Synthetic 10x3 model: band0/2 fully open, band1 wall cols0-7 (left half
# logical cells) -> mirror gives the right rows the patches sit on.
BASE_TILES = (
    [0] * 10
    + [1] * 8 + [0, 0]
    + [0] * 10
)


def make_model(patches=None, tiles=None):
    m = {"id": 90, "width": 10, "height": 3,
         "tiles": BASE_TILES if tiles is None else tiles}
    if patches is not None:
        m["asym_patches"] = patches
    return m


def emitted(model):
    """resolve + emit -> (asm lines list, (right rows, ball x, m1 x) | None)."""
    # Async lives on the ROOM (2026-10-17): the model keeps the shape, the
    # room carries the strips. These synthetic cases move the model's patch
    # list onto a room dict.
    room = {"room_id": 0, "asym_patches": model.get("asym_patches") or []}
    left = convert_level.rows_from_json({"model_id": model["id"]},
                                        {model["id"]: model})
    res = convert_level.resolve_asym_patches(model, room, left)
    asym, ball_x, m1_x, m1_door, m1_right = res if res else (None, 0, 0, False, False)
    lines = convert_room.lines(left, prefix=f"M{model['id']}",
                               source="test", asym_rows=asym,
                               asym_ball_x=ball_x, asym_m1_x=m1_x,
                               m1_door=m1_door)
    return lines, res


def byte_line(lines, label):
    i = lines.index(label)
    line = lines[i + 1]
    assert line.lstrip().startswith(".byte"), f"{label}: {line!r}"
    payload = line.split(".byte", 1)[1].split(";")[0]
    return [int(b.strip().lstrip("$"), 16) for b in payload.split(",")]


def expect_reject(model, needle):
    try:
        emitted(model)
    except ValueError as exc:
        assert needle in str(exc), f"reject reason {exc!r} lacks {needle!r}"
        return
    raise AssertionError(f"model {model} accepted — envelope must fail loudly")


def main() -> int:
    # --- 1. valid synthetic asym model (case 1: stacked blocks) ---------
    # patches at right_col 0 in bands 0+2 — TWO blocks max, one over the
    # other on two bands = one ball x (additive: mirror cell open in both).
    # Hand-derived right rows / D4 bytes:
    #   band0: mirror ".........." + patch col0 -> "#........."
    #          reverse -> ".........#" -> only cell9 -> pair cells18,19
    #          -> pf0 $00, pf1 $00, pf2 $C0
    #   band1: NO patch -> plain mirror "..########"
    #          reverse -> "########.." -> cells0-7 solid
    #          -> pf0 $F0 (cells0-3), pf1 $FF (cells4-11),
    #             pf2: cells6,7 set -> bits0-3; 8,9 clear -> $0F
    #   band2: same as band0 -> $00, $00, $C0
    model = make_model(patches=[[0, 0, 1], [2, 0, 1]])
    lines, res = emitted(model)
    assert res is not None
    asym, ball_x, m1_x, _m1_door, _m1r = res
    assert len(asym) == 3
    assert ball_x == 87, f"ball x {ball_x} != 87 (right_col 0 = 87+8*0)"
    assert m1_x == 0, f"m1 x {m1_x} != 0 (no side-1 patches)"
    assert asym[0] == "#........." and asym[1] == "..########" \
        and asym[2] == "#.........", asym
    # packed meta: MetaA = (m1_col+1)<<4 | band_mask (bands 0+2 -> $05,
    # no M1), MetaB = ball_col+1 (col 0 -> 1)
    assert byte_line(lines, "M90MetaA:") == [0x05], \
        f"MetaA {byte_line(lines, 'M90MetaA:')} != [05]"
    assert byte_line(lines, "M90MetaB:") == [0x01], \
        f"MetaB {byte_line(lines, 'M90MetaB:')} != [01]"
    # meta sits directly after TilePF2 (kernel reads TilePF0+9..+10)
    assert lines.index("M90MetaA:") == lines.index("M90TilePF2:") + 2, \
        "MetaA must be the byte right after TilePF2's .byte line"
    assert lines.index("M90MetaB:") == lines.index("M90MetaA:") + 2, \
        "MetaB must be the byte right after MetaA's .byte line"
    # C5 (2026-10-20): RightPF/RightRects are RETIRED (no reader since C4) —
    # the per-grid meta-pair emission stays for the extras/unit-test path.
    assert not any("RightPF" in l or "RightRects" in l for l in lines), \
        "C5: the right-half block must not be emitted"

    # --- 2. legacy model (no field): meta 0,0, no Right block ------------
    legacy = make_model(patches=None)
    out_a, res_a = emitted(legacy)
    assert res_a is None
    left = convert_level.rows_from_json({"model_id": 90}, {90: legacy})
    out_b = convert_room.lines(left, prefix="M90", source="test")
    assert out_a == out_b, "legacy emission must be byte-identical"
    assert byte_line(out_a, "M90MetaA:") == [0], "sym MetaA must be $00"
    assert byte_line(out_a, "M90MetaB:") == [0], "sym MetaB must be $00"
    assert out_a.index("M90MetaB:") == out_a.index("M90MetaA:") + 2, \
        "sym MetaB must still sit after MetaA (2-byte meta always present)"
    assert not any("RightPF" in l or "RightRects" in l for l in out_a), \
        "legacy emission must contain no Right block"

    # --- 2b. partial bands: only band0 patched -> MetaA band bit 0 --------
    partial = make_model(patches=[[0, 0, 1]])
    out_p, res_p = emitted(partial)
    assert res_p is not None
    assert byte_line(out_p, "M90MetaA:") == [0x01], \
        "band0 mask bit only -> MetaA $01 (no M1)"
    assert byte_line(out_p, "M90MetaB:") == [0x01], "ball_col 0 -> MetaB 1"

    # --- 2c. M1-only (side=1, no ball): case 2 stack ---------------------
    # BASE tiles: cell3 open in bands 0/2, wall in band1 -> patch bands {0,2}.
    m1_only = make_model(patches=[[0, 3, 1, 1], [2, 3, 1, 1]])
    out_m, res_m = emitted(m1_only)
    assert res_m is not None
    asym_m, bx_m, m1x_m, _, _ = res_m
    assert asym_m is None, "M1-only keeps the right half a plain mirror"
    assert bx_m == 0, f"ball x {bx_m} != 0 (no right patches)"
    assert m1x_m == 31, f"m1 x {m1x_m} != 31 (left col 3 = 7+8*3)"
    assert byte_line(out_m, "M90MetaA:") == [0x40], \
        "M1-only: (m1_col+1)=4 in high nibble, band mask 0"
    assert byte_line(out_m, "M90MetaB:") == [0], "M1-only MetaB = 0 (no ball)"

    # --- 2d. case 3: side-by-side same band, different x (ball + M1) -----
    # tiles: band0 all open; bands 1/2 wall at cell 8 (M1 wall-hide).
    case3_tiles = [0] * 10 + [1] * 9 + [0] + [1] * 9 + [0]
    case3 = make_model(patches=[[0, 7, 1], [0, 8, 1, 1]], tiles=case3_tiles)
    out_c, res_c = emitted(case3)
    assert res_c is not None
    asym_c, bx_c, m1x_c, _, _ = res_c
    assert asym_c is not None, "ball patch present -> right rows emitted"
    assert bx_c == 143, f"ball x {bx_c} != 143 (right_col 7 = 87+8*7)"
    assert m1x_c == 71, f"m1 x {m1x_c} != 71 (left col 8 = 7+8*8)"
    assert byte_line(out_c, "M90MetaA:") == [0x91], \
        "(m1_col+1)=9 high nibble | band0 mask -> $91"
    assert byte_line(out_c, "M90MetaB:") == [0x08], "ball_col 7 -> MetaB 8"
    assert not any("RightPF" in l or "RightRects" in l for l in out_c), \
        "case3: no right-half block (C5 retirement)"

    # --- 3. envelope rejects --------------------------------------------
    # subtractive: band0 is open, its mirror at right_col0 is open too —
    # use band1 (wall) mirrored: right_col8 mirrors left cell1 = wall.
    expect_reject(make_model(patches=[[1, 8, 0]]), "subtractive")
    # multi-column / >1-cell run: two columns span the ball width.
    expect_reject(make_model(patches=[[1, 0, 1], [1, 3, 1]]),
                  "ONE column")
    expect_reject(make_model(patches=[[1, 0, 1], [1, 1, 1]]),
                  "ONE column")
    # two blocks max (case 1/2 configs only) + duplicate cell
    expect_reject(make_model(patches=[[0, 0, 1], [1, 0, 1], [2, 0, 1]]),
                  "TWO blocks max")
    expect_reject(make_model(patches=[[0, 0, 1], [0, 0, 1]]),
                  "duplicate asym patch")
    # out-of-range
    expect_reject(make_model(patches=[[3, 0, 1]]), "row 3")
    expect_reject(make_model(patches=[[1, 10, 1]]), "col 10")
    # malformed patch
    expect_reject(make_model(patches=[[1, 0]]), "must be [row, col, tile]")
    # M1-side envelope: side out of range, open tile, two left columns
    expect_reject(make_model(patches=[[0, 0, 1, 2]]),
                  "not in 0 (right/ball)")
    expect_reject(make_model(patches=[[0, 3, 0, 1]]), "wall tile")
    expect_reject(
        make_model(patches=[[0, 3, 1, 1], [0, 4, 1, 1]]),
        "ONE column")
    # M1 wall-hide guard (whole-cave ENAM1 latch):
    # cell3 open in band 2 with no patch -> latch would paint it
    expect_reject(make_model(patches=[[0, 3, 1, 1]]), "wall-hide guard")
    # cell3 wall in a patched band -> latch would hide the patch
    expect_reject(make_model(patches=[[0, 3, 1, 1], [1, 3, 1, 1]]),
                  "hide the patch")

    # --- 4. C5 (2026-10-20): the SHAPE is meta-free and the room extras
    # record carries the pair + the patch bytes. Same synthetic model as
    # case 1 (patches on bands 0+2, right_col 0).
    # C3 (2026-10-20): the shape stores 3 row-pool indices, so it needs a
    # pool; the emitted indices must expand to the RAW rows (equivalence).
    pool = convert_room.RowPool()
    shape = convert_room.lines(left, prefix="M90", source="test",
                               with_meta=False, pool=pool)
    assert not any("MetaA" in l or "MetaB" in l for l in shape), \
        "with_meta=False must not emit the pair (TilePF0+9/+10 retired)"
    assert not any("TilePF" in l for l in shape), \
        "the shape block must not carry raw PF bytes (C3 row dictionary)"
    i = shape.index("M90Rows:")
    idx = [int(v.strip().lstrip("$"), 16)
           for v in shape[i + 1].split(".byte", 1)[1].split(";")[0].split(",")]
    assert len(idx) == 4, f"M90Rows: {len(idx)} indices, want 4 (N=4)"
    # N=4: 4 band indices; a 3-row model becomes [r0, r1, AIR, r2].
    want_rows = (list(left[:-1]) + [".........."] * (4 - len(left))
                 + [left[-1]])
    assert [pool.rows[k] for k in idx] == [
        convert_room.pf_values(r) for r in want_rows], (
        "expanded rows != pf_values(rows) — the row dictionary changed bytes")
    # N=4: four band rows are referenced per shape (the AIR pad row is a
    # pool entry of its own), so a 3-row model uses four pool slots.
    assert pool.uses == 4, f"pool uses {pool.uses} != 4 (one per band)"
    room = {"room_id": 0, "model_id": 90,
            "asym_patches": [[0, 0, 1], [2, 0, 1]]}
    record, nfeat = convert_level.room_extras(
        room, legacy, convert_level.rows_from_json(room, {90: legacy}),
        "test room")
    # flags (2 patches, 0 features) | MetaA $05 | MetaB $01 | 2 patch bytes
    # (row<<6 | side<<4 | col: $00 and $80)
    assert record == bytes([0x02, 0x05, 0x01, 0x00, 0x80]), record.hex()
    assert nfeat == 0

    # --- 5. M1-only extras: MetaA carries (m1_col+1)<<4 and no band mask,
    # and a side-1 patch byte sets b4 (row 0 -> $10 | col 3 = $13).
    room_m = {"room_id": 0, "model_id": 90,
              "asym_patches": [[0, 3, 1, 1], [2, 3, 1, 1]]}
    rec_m, nf_m = convert_level.room_extras(
        room_m, legacy, convert_level.rows_from_json(room_m, {90: legacy}),
        "test room m1")
    assert rec_m == bytes([0x02, 0x40, 0x00, 0x13, 0x93]), rec_m.hex()
    assert nf_m == 0

    print("test_asym_data: OK (valid + partial bands + M1-only + case3 + "
          "legacy + 11 envelope rejects + right budget + combined deferred)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
