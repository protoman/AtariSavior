#!/usr/bin/env python3
"""New-tile data pipeline fixtures (ai_new_tiles plan Phase 1 / CHECK 1).

Covers:
   1. feature chars flow: grid tiles 10/11/12 -> P/V/C rows, solid for
      pf_values, kept off the hot-band coercion;
   2. convert_room.lines emits b7 feature records in the hot stream:
      $80 per phase cell, $81 vcrunch bbox, $82 hcrunch band prefix —
      and the hot count byte includes them;
   3. hcrunch rejects (fail loudly): cells spanning bands, non-prefix
      cols, hot middle band (rows_from_json);
   4. LOCKED_DOOR rejects in the grid (rows_from_json);
   5. door: resolve passes on side 0, model_door_flag, MetaB b7 set
      (ball_col+1 | $80), mixed side-0 tiles rejected, door on side 1 /
      hot band rejected;
   6. legacy emission (no feature chars, no door) stays byte-identical
      to the plain call;
   7. KEY = enemy type 6 flows through _enemy_tables.

Run: /home/iuri/python3/bin/python3 tools/test_features_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_level  # noqa: E402
import convert_room  # noqa: E402


def grid(rows3):
    """10x3 tiles from three 10-char rows ('.'=0, '#'=1, P/V/C=10/11/12)."""
    val = {".": 0, "#": 1, "H": 8, "P": 10, "V": 11, "C": 12}
    tiles = []
    for row in rows3:
        assert len(row) == 10, row
        tiles += [val[ch] for ch in row]
    return tiles


def model(tiles, **extra):
    m = {"id": 91, "width": 10, "height": 3, "tiles": tiles}
    m.update(extra)
    return m


def rows_of(m):
    return convert_level.rows_from_json({"model_id": m["id"]}, {m["id"]: m})


def emitted(m, door=None):
    left = rows_of(m)
    res = convert_level.resolve_asym_patches(m, left)
    asym, ball_x, m1_x = res if res else (None, 0, 0)
    if door is None:
        door = convert_level.model_door_flag(m)
    return convert_room.lines(left, prefix=f"M{m['id']}", source="test",
                              asym_rows=asym, asym_ball_x=ball_x,
                              asym_m1_x=m1_x, door=door)


def byte_line(lines, label):
    i = lines.index(label)
    line = lines[i + 1]
    assert line.lstrip().startswith(".byte"), f"{label}: {line!r}"
    payload = line.split(".byte", 1)[1].split(";")[0]
    return [int(b.strip().lstrip("$"), 16) for b in payload.split(",")]


def hot_records(lines):
    """(count, [(mask, x, y, w, h), ...]) from the hot stream."""
    i = lines.index("M91RoomRects:")
    count_line = None
    for j in range(i, len(lines)):
        if "number of hot rectangles" in lines[j]:
            count_line = j
            break
    assert count_line is not None, "hot count line missing"
    payload = lines[count_line].split(".byte", 1)[1].split(";")[0]
    count = int(payload.strip())
    recs = []
    for j in range(count_line + 1, count_line + 1 + count):
        payload = lines[j].split(".byte", 1)[1].split(";")[0]
        recs.append(tuple(int(b.strip().lstrip("$"), 16)
                          for b in payload.split(",")))
    # next line after the stream must be TilePF0 (records fully consumed)
    assert "M91TilePF0:" in lines[count_line + 1 + count], \
        "hot stream length != count byte"
    return count, recs


def expect_reject(fn, needle):
    try:
        fn()
    except ValueError as exc:
        assert needle in str(exc), f"reject reason {exc!r} lacks {needle!r}"
        return
    raise AssertionError(f"expected ValueError with {needle!r}")


def main() -> int:
    open10 = ["." * 10] * 3

    # --- 1. feature chars: grid -> rows, PF-solid, hot off --------------
    m = model(grid(["P.V.C.....", "#" * 10, ".........."]),
              mid_band_type=1)
    rows = rows_of(m)
    assert rows[0] == "P.V.C.....", rows
    assert rows[1] == "H" * 10, rows          # plain walls go hot
    pf = convert_room.pf_values(rows[0])
    # P at cell0 (pairs 0-1), V cell2 (4-5), C cell4 (8-9)
    assert pf == (0x30, 0xCC, 0x00), pf
    # feature tile keeps its char on the hot band (hcrunch allowed there)
    m_hotfeat = model(grid(["." * 10, "C.." + "." * 7, "." * 10]),
                      mid_band_type=1)
    assert rows_of(m_hotfeat)[1] == "C.." + "." * 7

    # --- 2. feature records in the hot stream ---------------------------
    # phase cells (0,0) and (0,2): expect two $80 records
    count, recs = hot_records(emitted(model(
        grid(["P.P." + "." * 6, "." * 10, "." * 10]))))
    assert count == 2 and recs == [(0x80, 0, 0, 2, 1), (0x80, 4, 0, 2, 1)], \
        (count, recs)

    # vcrunch bbox: cells (2,0),(2,1),(1,0) -> x0 y1 w4 h2
    count, recs = hot_records(emitted(model(
        grid(["." * 10, "VV" + "." * 8, "V.." + "." * 7]))))
    assert count == 1 and recs == [(0x81, 0, 1, 4, 2)], (count, recs)

    # hcrunch prefix cols 0-3 on band 2 -> one $82 record
    count, recs = hot_records(emitted(model(
        grid(["." * 10, "." * 10, "CCCC" + "." * 6]))))
    assert count == 1 and recs == [(0x82, 0, 2, 8, 1)], (count, recs)

    # hot rect + feature share the stream: band1 wall (hot) + phase cell
    count, recs = hot_records(emitted(model(
        grid(["P" + "." * 9, "#" * 10, "." * 10]), mid_band_type=1)))
    assert count >= 2 and recs[1][0] == 0x80, (count, recs)

    # --- 3. hcrunch rejects: span bands / non-prefix; hot band ALLOWED ----
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "CC" + "." * 8,
                                    "CC" + "." * 8]))),
        "span bands")
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "." * 10,
                                    ".C.C" + "." * 6]))),
        "not a contiguous prefix")
    # hot band + hcrunch = allowed (user rule 2026-10-12): C cells keep
    # their char, record still emitted
    count, recs = hot_records(emitted(model(
        grid(["." * 10, "CCCC" + "." * 6, "." * 10]), mid_band_type=1)))
    assert count == 1 and recs == [(0x82, 0, 1, 8, 1)], (count, recs)

    # phase/vcrunch on the hot middle band = hard error (mutually exclusive)
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "P" + "." * 9, "." * 10]),
                              mid_band_type=1)),
        "phase on the hot middle band")
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "." * 9 + "V", "." * 10]),
                              mid_band_type=1)),
        "vcrunch on the hot middle band")

    # --- 4. LOCKED_DOOR in the grid rejects ------------------------------
    door_tiles = grid(["." * 10] * 3)
    door_tiles[0] = convert_level.LOCKED_DOOR
    expect_reject(
        lambda: convert_level.rows_from_json(
            {"model_id": 91}, {91: model(door_tiles)}),
        "LOCKED_DOOR")

    # --- 5. door: resolve + MetaB b7 + envelope rejects ------------------
    door_model = model(grid(["." * 10] * 3),
                       asym_patches=[[0, 3, convert_level.LOCKED_DOOR],
                                     [2, 3, convert_level.LOCKED_DOOR]])
    assert convert_level.model_door_flag(door_model)
    lines = emitted(door_model)
    # ball col 3 -> ball_col+1 = 4, | $80
    assert byte_line(lines, "M91MetaB:") == [0x84], \
        f"door MetaB {byte_line(lines, 'M91MetaB:')} != [84]"
    # plain patch model keeps MetaB b7 clear
    plain = model(grid(["." * 10] * 3), asym_patches=[[0, 3, 1]])
    assert not convert_level.model_door_flag(plain)
    pb = byte_line(emitted(plain), "M91MetaB:")
    assert pb == [0x04] and not (pb[0] & 0x80), pb
    # mixed side-0 tiles (door + plain patch)
    expect_reject(
        lambda: emitted(model(grid(["." * 10] * 3),
                              asym_patches=[[0, 3, convert_level.LOCKED_DOOR],
                                            [2, 3, 1]])),
        "must ALL be")
    # door as an M1 patch
    expect_reject(
        lambda: emitted(model(grid(["#" * 10] * 3),
                              asym_patches=[[0, 3, convert_level.LOCKED_DOOR,
                                             1]])),
        "SIDE-0")
    # door on the hot middle band
    expect_reject(
        lambda: emitted(model(grid(["." * 10] * 3),
                              asym_patches=[[1, 3, convert_level.LOCKED_DOOR]],
                              mid_band_type=1)),
        "hot middle band")
    # door without any ball strip cannot set b7 (door flag without ball)
    expect_reject(
        lambda: convert_room.lines(["." * 10] * 3, prefix="M91",
                                   source="test", door=True),
        "needs a side-0")

    # --- 6. legacy emission stays byte-identical -------------------------
    legacy = model(grid(["." * 10, "#" * 10, "." * 10]))
    out_a = emitted(legacy, door=False)
    left = rows_of(legacy)
    out_b = convert_room.lines(left, prefix="M91", source="test")
    assert out_a == out_b, "legacy emission must be byte-identical"
    count, recs = hot_records(out_a)
    assert all(r[0] < 0x80 for r in recs), "no b7 masks in legacy stream"

    # --- 7. KEY = enemy type 6 flows through _enemy_tables ---------------
    rooms = [{"room_id": 0, "enemies": [{"type": 6, "x": 5.0, "y": 4.0,
                                         "dir": 1}], "lamps": []}]
    tbl = "\n".join(convert_level._enemy_tables("LEVEL1", rooms))
    assert ".byte 6, " in tbl, f"KEY type missing:\n{tbl}"
    # lamp stays 5 and type range check in verify_build allows 0-4,6
    rooms[0]["enemies"][0]["type"] = 4
    assert ".byte 4, " in "\n".join(
        convert_level._enemy_tables("LEVEL1", rooms))

    print("test_features_data: OK (chars + records + rejects + door MetaB + "
          "legacy identical + KEY type 6)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

