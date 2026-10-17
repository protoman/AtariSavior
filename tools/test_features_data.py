#!/usr/bin/env python3
"""New-tile data pipeline fixtures (ai_new_tiles plan Phase 1 / CHECK 1).

Covers:
   1. feature chars flow: grid tiles 10/11/12 -> P/V/C on the middle
      band (row 1, rule 2026-10-14), solid for pf_values, kept off the
      hot-band coercion; hot + phase stays mutually exclusive (vcrunch
      now ALLOWED on hot — user rule 2026-10-14, MetaB b6 flags it);
   2. convert_room.lines emits b7 feature records in the hot stream:
      $80 per phase cell, $81 vcrunch bbox, $82 hcrunch band prefix —
      all carrying y=1, and the hot count byte includes them;
   3. special-feature rejects (fail loudly): P/V/C off row 1 (both
      layers), hcrunch spanning bands / non-prefix cols, door XOR
      feature exclusivity, mixed P/V/C;
   4. LOCKED_DOOR rejects in the grid (rows_from_json);
   5. door (row-1 patch only): resolve passes on side 0, model_door_flag,
      MetaB b7 set (ball_col+1 | $80), mixed side-0 tiles rejected, door
      on side 1 / hot band rejected;
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
    asym, ball_x, m1_x, m1_door, m1_right = res if res else (None, 0, 0, False, False)
    if door is None:
        # Phase 5: every LOCKED_DOOR is emitted as an M1 door (MetaA b3, and
        # b0 for the right half) — no ball door any more, matching
        # convert_level's call site.
        door = False
    return convert_room.lines(left, prefix=f"M{m['id']}", source="test",
                              asym_rows=asym, asym_ball_x=ball_x,
                              asym_m1_x=m1_x, door=door,
                              m1_door=m1_door, m1_right=m1_right,
                              hot=bool(m.get("mid_band_type")))


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
        needs = [needle] if isinstance(needle, str) else list(needle)
        assert any(n in str(exc) for n in needs), \
            f"reject reason {exc!r} lacks any of {needs!r}"
        return
    raise AssertionError(f"expected ValueError with {needle!r}")


def main() -> int:
    open10 = ["." * 10] * 3

    # --- 1. feature chars: middle band (row 1), PF-solid, hot off -------
    # Special features live ONLY on row 1 (rule 2026-10-14); phase is
    # mutually exclusive with hot here, so no hot flag in this model.
    m = model(grid(["." * 10, "P.V.C.....", "." * 10]),
              mid_band_type=0)
    rows = rows_of(m)
    assert rows[1] == "P.V.C.....", rows
    assert rows[0] == "." * 10 and rows[2] == "." * 10, rows
    pf = convert_room.pf_values(rows[1])
    # P at cell0 (pairs 0-1), V cell2 (4-5), C cell4 (8-9)
    assert pf == (0x30, 0xCC, 0x00), pf
    # plain walls on the hot band still go H (no features in that model)
    walls = model(grid(["." * 10, "#" * 10, "." * 10]), mid_band_type=1)
    assert rows_of(walls)[1] == "H" * 10, rows
    # feature tile keeps its char on the hot band (hcrunch allowed there)
    m_hotfeat = model(grid(["." * 10, "C.." + "." * 7, "." * 10]),
                      mid_band_type=1)
    assert rows_of(m_hotfeat)[1] == "C.." + "." * 7

    # --- 2. feature records in the hot stream (all y=1) -----------------
    # phase cells (1,0) and (1,2): expect two $80 records on row 1
    count, recs = hot_records(emitted(model(
        grid(["." * 10, "P.P." + "." * 6, "." * 10]))))
    assert count == 2 and recs == [(0x80, 0, 1, 2, 1), (0x80, 4, 1, 2, 1)], \
        (count, recs)

    # vcrunch bbox: cells (1,0..2) -> x0 y1 w6 h1 (the sprite shutter
    # slices only the middle band)
    count, recs = hot_records(emitted(model(
        grid(["." * 10, "VVV" + "." * 7, "." * 10]))))
    assert count == 1 and recs == [(0x81, 0, 1, 6, 1)], (count, recs)

    # special features off row 1 = hard error (entry/exit corridors)
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "." * 10, "V" + "." * 9]))),
        "special features live on the middle band")
    expect_reject(
        lambda: emitted(model(grid(["P" + "." * 9, "." * 10, "." * 10]))),
        "special features live on the middle band")
    # convert_room's own band check (belt for direct, non-JSON callers)
    expect_reject(
        lambda: convert_room.lines(["V" + "." * 9, "." * 10, "." * 10],
                                   prefix="M91", source="test"),
        "vcrunch cells at rows")

    # hcrunch off row 1 = hard error
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "." * 10, "CCCC" + "." * 6]))),
        "special features live on the middle band")
    # hcrunch prefix cols 0-3 on the middle band -> one $82 record
    count, recs = hot_records(emitted(model(
        grid(["." * 10, "CCCC" + "." * 6, "." * 10]))))
    assert count == 1 and recs == [(0x82, 0, 1, 8, 1)], (count, recs)

    # --- 3. hcrunch rejects: span bands / non-prefix; hot band ALLOWED ----
    # Span needs two rows — rows_from_json rejects those first, so call
    # convert_room directly (belt layer for non-JSON callers).
    expect_reject(
        lambda: convert_room.lines(["." * 10, "CC" + "." * 8,
                                    "CC" + "." * 8],
                                   prefix="M91", source="test"),
        "crunch band must be the middle band")
    expect_reject(
        lambda: emitted(model(grid(["." * 10, ".C.C" + "." * 6,
                                    "." * 10]))),
        "not a contiguous prefix")
    # hot band + hcrunch = allowed (user rule 2026-10-12): C cells keep
    # their char, record still emitted
    count, recs = hot_records(emitted(model(
        grid(["." * 10, "CCCC" + "." * 6, "." * 10]), mid_band_type=1)))
    assert count == 1 and recs == [(0x82, 0, 1, 8, 1)], (count, recs)

    # phase on the hot middle band = hard error (mutually exclusive)
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "P" + "." * 9, "." * 10]),
                              mid_band_type=1)),
        "phase on the hot middle band")
    # vcrunch on the hot middle band = ALLOWED (user rule 2026-10-14:
    # both crunch walls respect the hot flag) — MetaB b6 carries it.
    # All-V row = no 'H' cell, so the flag must ride the explicit hot=.
    m_vhot = model(grid(["." * 10, "." * 9 + "V", "." * 10]),
                   mid_band_type=1)
    assert rows_of(m_vhot)[1] == "." * 9 + "V", rows_of(m_vhot)
    vb = byte_line(emitted(m_vhot), "M91MetaB:")
    assert vb == [0xC0], f"vcrunch+hot MetaB {vb} != [C0] (b7 shutter|b6 hot)"
    # same model cold (no flag) -> $80 only
    vcold = model(grid(["." * 10, "." * 9 + "V", "." * 10]))
    assert byte_line(emitted(vcold), "M91MetaB:") == [0x80]
    # vcrunch cannot share the M1 slot with a side-1 strip / door
    # (M1 envelope: patch col open in its band, walls in the others)
    expect_reject(
        lambda: emitted(model(grid(["#" + "." * 9, "." * 9 + "V",
                                    "#" + "." * 9]),
                              asym_patches=[[1, 0, 1, 1]])),
        "shutter owns the M1 slot")

    # exclusivity (rule 2026-10-14): door XOR phase XOR vcrunch XOR hcrunch
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "P" + "." * 9, "." * 10]),
                              asym_patches=[[1, 3,
                                             convert_level.LOCKED_DOOR]])),
        ["special features are alone per room", "wall-hide guard"])
    expect_reject(
        lambda: emitted(model(grid(["." * 10,
                                    "P" + "." * 4 + "V" + "." * 4,
                                    "." * 10]))),
        "mixed special features")

    # --- 4. LOCKED_DOOR in the grid rejects ------------------------------
    door_tiles = grid(["." * 10] * 3)
    door_tiles[0] = convert_level.LOCKED_DOOR
    expect_reject(
        lambda: convert_level.rows_from_json(
            {"model_id": 91}, {91: model(door_tiles)}),
        "LOCKED_DOOR")

    # --- 5. door: right-M1 form (Phase 5) --------------------------------
    # A side-0 LOCKED_DOOR is authored as the RIGHT-half M1 door:
    # MetaA = (col+1)<<4 | band_mask | $08 (door) | $01 (right half),
    # MetaB = $00 (no ball) — the M1 gives the yellow COLUP1 stripe +
    # OvM1Block collision + the key touch-unlock on BOTH halves. The M1
    # wall-hide envelope applies: the door's col is wall in bands 0/2 (the
    # parked M1 hides there) and open in band 1 (its own band).
    door_model = model(grid(["#" * 10, "." * 10, "#" * 10]),
                       asym_patches=[[1, 3, convert_level.LOCKED_DOOR]])
    assert convert_level.model_door_flag(door_model)
    lines = emitted(door_model)
    _a = byte_line(lines, "M91MetaA:")
    assert _a and (_a[0] & 0x08), \
        f"door MetaA {_a} must set the $08 (LOCKED_DOOR) bit"
    assert _a[0] & 0x01, \
        f"door MetaA {_a} must set the $01 (right-half) bit for a side-0 door"
    assert byte_line(lines, "M91MetaB:") == [0x00], \
        f"door MetaB {byte_line(lines, 'M91MetaB:')} != [00] (doors use M1, no ball)"
    # plain patch model keeps MetaB b7 clear
    plain = model(grid(["." * 10] * 3), asym_patches=[[0, 3, 1]])
    assert not convert_level.model_door_flag(plain)
    pb = byte_line(emitted(plain), "M91MetaB:")
    assert pb == [0x04] and not (pb[0] & 0x80), pb
    # mixed side-0 tiles (door on row 1 + plain patch elsewhere)
    expect_reject(
        lambda: emitted(model(grid(["." * 10] * 3),
                              asym_patches=[[1, 3, convert_level.LOCKED_DOOR],
                                            [2, 3, 1]])),
        "must ALL be")
    # --- 5b. side-1 door: MetaA b3 + envelope (P2b) ----------------------
    # M1 envelope: col open in the patched band, wall in the others.
    left1 = ["." * 10, "...#......", "...#......"]   # patch row 0 (plain)
    left1d = ["...#......", "." * 10, "...#......"]  # patch row 1 (door)
    m1door = model(grid(left1d),
                   asym_patches=[[1, 3, convert_level.LOCKED_DOOR, 1]])
    assert convert_level.model_m1_door_flag(m1door)
    assert not convert_level.model_door_flag(m1door), \
        "side-1 door must not set MetaB b7"
    l1 = emitted(m1door)
    # m1 col 3 -> m1_col+1 = 4 -> $40 | b3 door
    assert byte_line(l1, "M91MetaA:") == [0x48], \
        f"side-1 door MetaA {byte_line(l1, 'M91MetaA:')} != [48]"
    assert byte_line(l1, "M91MetaB:") == [0x00], \
        f"side-1 door MetaB {byte_line(l1, 'M91MetaB:')} != [00]"
    # plain M1 patch keeps MetaA b3 clear
    plain_m1 = model(grid(left1), asym_patches=[[0, 3, 1, 1]])
    pa = byte_line(emitted(plain_m1), "M91MetaA:")
    assert pa == [0x40] and not (pa[0] & 0x08), pa
    # mixed side-1 tiles (door on row 1 + plain M1 on row 0) — both
    # patched bands open, remaining band wall (M1 envelope) so the
    # no-mix check is what fires
    expect_reject(
        lambda: emitted(model(grid(["." * 10, "." * 10, "...#......"]),
                              asym_patches=[[1, 3, convert_level.LOCKED_DOOR,
                                             1],
                                            [0, 3, 1, 1]])),
        "M1 patches must ALL be LOCKED_DOOR")
    # m1_door flag without an M1 strip
    expect_reject(
        lambda: convert_room.lines(["." * 10] * 3, prefix="M91",
                                   source="test", m1_door=True),
        "needs an M1 patch strip")
    # side-1 door on the hot middle band (same reject as side 0)
    expect_reject(
        lambda: emitted(model(grid(left1),
                              asym_patches=[[1, 3, convert_level.LOCKED_DOOR,
                                             1]],
                              mid_band_type=1)),
        "hot middle band")
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

