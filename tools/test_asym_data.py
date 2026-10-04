#!/usr/bin/env python3
"""Asym data pipeline + D6 envelope fixtures (asymmetric_pf_plan Phase 1
items 3-4 / CHECK 1).

Covers:
  1. synthetic asymmetric model: resolve_asym_patches + convert_room.lines
     emit flag, stride-3 right rows with hand-derived CHECK 0 encoder bytes,
     and a right rect stream;
  2. legacy model (no asym_patches field): emission has no asym block and
     is byte-identical to the plain symmetric call;
  3. envelope rejects (fail loudly): subtractive patch, patches spanning
     >1 column (also the >1-cell run case), out-of-range row/col, malformed
     patch;
  4. convert-side right-rect budget: >4 right wall rects raises (Risk 1).

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
    """resolve + emit -> (asm lines list, (right rows, ball x) | None)."""
    left = convert_level.rows_from_json({"model_id": model["id"]},
                                        {model["id"]: model})
    res = convert_level.resolve_asym_patches(model, left)
    asym, ball_x = res if res else (None, 0)
    lines = convert_room.lines(left, prefix=f"M{model['id']}",
                               source="test", asym_rows=asym,
                               asym_ball_x=ball_x)
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
    # --- 1. valid synthetic asym model ---------------------------------
    # patches at right_col 0 in all three bands (same column = one ball x;
    # additive: mirror cell is open everywhere it is painted).
    # Hand-derived right rows / D4 bytes:
    #   band0: mirror ".........." + patch col0 -> "#........."
    #          reverse -> ".........#" -> only cell9 -> pair cells18,19
    #          -> pf0 $00, pf1 $00, pf2 $C0
    #   band1: mirror "..########" + patch col0 -> "#.########"
    #          reverse -> "########.#" -> cells0-7 + 9 solid
    #          -> pf0 $F0 (cells0-3), pf1 $FF (cells4-11),
    #             pf2: cells12-15 set -> bits0-3; 16,17 clear; 18,19 set
    #             -> $CF
    #   band2: same as band0 -> $00, $00, $C0
    model = make_model(patches=[[0, 0, 1], [1, 0, 1], [2, 0, 1]])
    lines, res = emitted(model)
    assert res is not None
    asym, ball_x = res
    assert len(asym) == 3
    assert ball_x == 87, f"ball x {ball_x} != 87 (right_col 0 = 87+8*0)"
    assert asym[0] == "#........." and asym[1] == "#.########" \
        and asym[2] == "#.........", asym
    flag = byte_line(lines, "M90AsymFlag:")
    assert flag == [1], f"AsymFlag {flag} != [1]"
    assert byte_line(lines, "M90BallX:") == [87], \
        f"BallX {byte_line(lines, 'M90BallX:')} != [87]"
    # meta sits directly after TilePF2 (kernel reads TilePF0+9..+13)
    assert lines.index("M90AsymFlag:") == lines.index("M90TilePF2:") + 2, \
        "AsymFlag must be the byte right after TilePF2's .byte line"
    assert lines.index("M90BallX:") == lines.index("M90AsymFlag:") + 2, \
        "BallX must be the byte right after AsymFlag's .byte line"
    # Phase 3 band gate bytes: all three bands patched in this fixture
    assert lines.index("M90Band0:") == lines.index("M90BallX:") + 2, \
        "Band0 must be the byte right after BallX's .byte line"
    assert byte_line(lines, "M90Band0:") == [0xFF], "band0 must be $ff"
    assert byte_line(lines, "M90Band1:") == [0xFF], "band1 must be $ff"
    assert byte_line(lines, "M90Band2:") == [0xFF], "band2 must be $ff"
    assert lines.index("M90RightPF0:") == lines.index("M90Band2:") + 2, \
        "RightPF0 must follow Band2 (meta = 5 bytes, RightPF at +14)"
    assert byte_line(lines, "M90RightPF0:") == [0x00, 0xF0, 0x00]
    assert byte_line(lines, "M90RightPF1:") == [0x00, 0xFF, 0x00]
    assert byte_line(lines, "M90RightPF2:") == [0xC0, 0xCF, 0xC0]
    assert "M90RightRects:" in lines
    # right rects: col0 spine rows0-2 + band1 cols2-9 -> 2 rects (<= budget)
    rc = byte_line(lines, "M90RightRects:")
    assert rc[0] == 2, f"right rect count {rc[0]} != 2"

    # --- 2. legacy model (no field): meta 0,0, no Right block ------------
    legacy = make_model(patches=None)
    out_a, res_a = emitted(legacy)
    assert res_a is None
    left = convert_level.rows_from_json({"model_id": 90}, {90: legacy})
    out_b = convert_room.lines(left, prefix="M90", source="test")
    assert out_a == out_b, "legacy emission must be byte-identical"
    assert byte_line(out_a, "M90AsymFlag:") == [0]
    assert byte_line(out_a, "M90BallX:") == [0]
    assert byte_line(out_a, "M90Band0:") == [0], "sym Band0 must be $00"
    assert byte_line(out_a, "M90Band1:") == [0], "sym Band1 must be $00"
    assert byte_line(out_a, "M90Band2:") == [0], "sym Band2 must be $00"
    assert out_a.index("M90Band0:") == out_a.index("M90BallX:") + 2, \
        "sym Band0 must still sit after BallX (5-byte meta always present)"
    assert not any("RightPF" in l or "RightRects" in l for l in out_a), \
        "legacy emission must contain no Right block"

    # --- 2b. partial bands: only band0 patched -> $ff, $00, $00 ----------
    partial = make_model(patches=[[0, 0, 1]])
    out_p, res_p = emitted(partial)
    assert res_p is not None
    assert byte_line(out_p, "M90Band0:") == [0xFF], "patched band0 = $ff"
    assert byte_line(out_p, "M90Band1:") == [0x00], "mirror band1 = $00"
    assert byte_line(out_p, "M90Band2:") == [0x00], "mirror band2 = $00"

    # --- 3. envelope rejects --------------------------------------------
    # subtractive: band0 is open, its mirror at right_col0 is open too —
    # use band1 (wall) mirrored: right_col8 mirrors left cell1 = wall.
    expect_reject(make_model(patches=[[1, 8, 0]]), "subtractive")
    # multi-column / >1-cell run: two columns span the ball width.
    expect_reject(make_model(patches=[[1, 0, 1], [1, 3, 1]]),
                  "ONE column")
    expect_reject(make_model(patches=[[1, 0, 1], [1, 1, 1]]),
                  "ONE column")
    # out-of-range
    expect_reject(make_model(patches=[[3, 0, 1]]), "row 3")
    expect_reject(make_model(patches=[[1, 10, 1]]), "right_col 10")
    # malformed patch
    expect_reject(make_model(patches=[[1, 0]]), "must be [row, right_col, tile]")

    # --- 4. convert-side right-rect budget (Risk 1) ----------------------
    five_rects = ["#.#.#.#.#.", "..........", ".........."]
    try:
        convert_room.lines(left, prefix="M90", source="test",
                           asym_rows=five_rects)
    except ValueError as exc:
        assert "WallMask budget" in str(exc), f"budget reason: {exc}"
    else:
        raise AssertionError("5 right wall rects must hard-fail (Risk 1)")

    print("test_asym_data: OK (valid + partial bands + legacy + "
          "6 envelope rejects + budget)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
