#!/usr/bin/env python3
"""Room-to-room links must be open on BOTH sides, in a shared band.

User rule 2026-10-24 (layout-driven exits): the level's room POSITIONS come
first; each room's exits are then derived from its neighbours. The runtime
exit does not test the neighbour's wall — it fires when the player reaches the
screen edge (`RoomX ==` min/max; the vertical link when the player's Y leaves
the cave) — so a passage carved on one side only, or on different bands on
each side, drops the player INSIDE A WALL in the room he arrives in.

This test authors small stages (test-owned models, never the live stage) and
drives `convert_level.check_stage_connections` — the same function the build
calls for every stage file, so the editor and the converter share one rule.

Cases:
  1. good horizontal pair, both open in bands 1+2 -> OK
  2. good horizontal pair, both open in band 1 only -> OK (any shared band)
  3. A open in band 1, B open in band 2 -> FAIL (no shared band)
  4. A open, B closed -> FAIL (half-carved link)
  5. vertical pair sharing a column -> OK
  6. vertical pair with disjoint columns -> FAIL
  7. vertical pair where the upper floor is open at a column the lower ceiling
     walls -> FAIL (the player keeps his X through the link, 2026-10-24)
  8. the live stage file -> OK (guards the current content)

Run: /home/iuri/python3/bin/python3 tools/test_room_links.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import convert_level as C  # noqa: E402

AIR, WALL = 0, 1
W, H = 10, 4          # editor room grid (one row per drawn band)


def model(mid, bands):
    """bands = 4 strings of 10 cells ('#' wall, '.' air)."""
    assert len(bands) == H
    tiles = []
    for row in bands:
        assert len(row) == W, row
        tiles += [WALL if ch == "#" else AIR for ch in row]
    return {"id": mid, "name": f"M{mid}", "width": W, "height": H,
            "tiles": tiles}


def room(rid, mid, x, y):
    return {"room_id": rid, "model_id": mid, "room_x": x, "room_y": y,
            "enemies": [], "lamps": []}


def stage(models, rooms):
    models_by_id = {m["id"]: m for m in models}
    level = {"level_id": 1, "rooms": rooms,
             "miner_room": rooms[-1]["room_id"], "miner_y": 8.0,
             "miner_x": 4.0, "start_room": 0,
             "wall_r": 40, "wall_g": 130, "wall_b": 90}
    return models_by_id, [(1, level)]


def run(name, models, rooms, expect_fail):
    models_by_id, levels = stage(models, rooms)
    try:
        C.check_stage_connections(models_by_id, levels)
        got = None
    except ValueError as err:
        got = str(err)
    ok = (got is not None) == expect_fail
    head = "ok  " if ok else "FAIL"
    detail = ("refused: " + got.split(' — ')[0]) if got else "accepted"
    print(f"  {head} {name}: {detail}")
    return ok


def main() -> int:
    good = []          # shared snapshot of every passing case
    fails = 0

    # Two-row model used for side links: band 0/3 structural walls.
    def side(band1_open, band2_open, top="##.#######", bottom="##.#######"):
        b1 = ("." if band1_open else "#") + ("#" if band1_open else ".") + "#" * 8
        b2 = ("." if band2_open else "#") + ("#" if band2_open else ".") + "#" * 8
        # keep the vertical corridor open at cells 8,9 in every band
        b1 = b1[:8] + ".."
        b2 = b2[:8] + ".."
        return [top, b1, b2, bottom]

    cases = [
        ("both bands", side(True, True), side(True, True), False),
        ("band 1 only", side(True, False), side(True, False), False),
        ("band 2 only", side(False, True), side(False, True), False),
        ("band 1 vs band 2", side(True, False), side(False, True), True),
        ("one side closed", side(True, True), side(False, False), True),
    ]
    # Plugs: a room with an edge opening and no room on that side carries a
    # solid async patch on that edge in every aperture band (user rule
    # 2026-10-24) — otherwise the link check refuses the stage for a dead
    # aperture before it ever looks at the pair.
    def plugged(rid, mid, x, rows, east_room):
        r = room(rid, mid, x, 0)
        bands = [b for b in (1, 2) if rows[b][0] == "."]
        patches = []
        if x == 0:
            patches += [[b, 0, 1, 1] for b in bands]
        if not east_room:
            patches += [[b, 9, 1, 0] for b in bands]
        if patches:
            r["asym_patches"] = patches
        return r

    for name, a, b, fail in cases:
        models = [model(0, a), model(1, b)]
        rooms = [plugged(0, 0, 0, a, True), plugged(1, 1, 1, b, False)]
        if not run(name, models, rooms, fail):
            fails += 1

    # New rule (user 2026-10-24): an edge opening with NO room that way is a
    # dead aperture — refuse it unless the edge is plugged. The lone room here
    # opens band 1 on both edges, so it needs one plug per side.
    models = [model(0, side(True, False))]
    if not run("dead aperture unplugged", models, [room(0, 0, 0, 0)], True):
        fails += 1
    lone = room(0, 0, 0, 0)
    lone["asym_patches"] = [[1, 0, 1, 1], [1, 9, 1, 0]]
    if not run("dead aperture plugged", models, [lone], False):
        fails += 1

    # Vertical: upper room's last band vs lower room's band 0.
    up_open = ["########..", "#.........", "########..", "########.."]
    dn_same = ["########..", "#.........", "########..", "########.."]
    dn_other = ["####....##", "#.........", "########..", "########.."]
    models = [model(0, up_open), model(1, dn_same)]
    if not run("vertical shared column", models,
               [room(0, 0, 0, 0), room(1, 1, 0, 1)], False):
        fails += 1
    models = [model(0, up_open), model(1, dn_other)]
    if not run("vertical disjoint columns", models,
               [room(0, 0, 0, 0), room(1, 1, 0, 1)], True):
        fails += 1
    # User report 2026-10-24 (stuck_002.png): a merely SHARED column is not
    # enough — the player KEEPS HIS X through a vertical link, so EVERY column
    # the upper room's floor is open at must be open in the lower room's
    # ceiling. Falling at the extra column spawns him inside the lower ceiling,
    # where StepDown refuses until he walks out: "it stops falling when I
    # appear on the next screen". This case PASSED before the rule (it shares
    # column 8) and must fail now.
    dn_partial = ["#######..#", "#.........", "########..", "########.."]
    models = [model(0, up_open), model(1, dn_partial)]
    if not run("vertical partial column", models,
               [room(0, 0, 0, 0), room(1, 1, 0, 1)], True):
        fails += 1

    # The live stage must satisfy the rule (it is what the build converts).
    live = ROOT / "rooms" / "stage.json"
    if live.exists():
        models_by_id, raw = C.load_stage(live)
        levels = []
        for n, lv in enumerate(raw, start=1):
            rooms = sorted(lv["rooms"], key=lambda r: r["room_id"])
            levels.append((n, dict(lv, rooms=rooms)))
        try:
            C.check_stage_connections(models_by_id, levels)
            print(f"  ok   live stage: 20 levels accepted")
        except ValueError as err:
            print(f"  FAIL live stage: {err}")
            fails += 1

    print(__doc__.splitlines()[0])
    if fails:
        print(f"test_room_links: FAIL ({fails})")
        return 1
    print("test_room_links: OK (shared band on both sides, vertical columns "
          "matched, half-carved links refused)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
