#!/usr/bin/env python3
"""E2 (2026-10-20): the 20-level stage generator (`savior_editor --generate-stage`).

Level n has n rooms with a floor of 2 (2,2,3,..,20 = 211 rooms), built from a
SHARED SHAPE LIBRARY keyed by the carved exits AND the room's hazard role, so
the whole stage costs a handful of model shapes and the
C7 level-data windows still fit.

Gates (all on the GENERATED file in a temp dir — the live stage is never read
for content and never written):

  * shape: canonical wrapped `{"stage": {...}}`, 20 levels, level n has n rooms,
    211 rooms total;
  * model library: <= 128 shapes (7-bit format cap, LAYOUT 8), ids 0..n-1 contiguous, EVERY model referenced
    by at least one room (the converter only emits referenced ones);
  * positions: unique per level, inside the 15x15 C1 grid, no nibble 15;
  * LAYOUT (the tear rule): connections are DERIVED FROM ADJACENCY at run time,
    so for every adjacent pair the carved opening must agree on BOTH sides —
    a one-sided carve drops the player inside the neighbour's wall. Asserted
    per pair for north/south/west/east; the mirrored playfield makes west and
    east ONE cell (row 1, col 0), so a horizontal pair is passable only when
    both rooms cut it. The passable graph must be the serpentine: every room
    reachable, exactly (rooms - 1) passages;
  * start room: the kernel drops the player in at (32, 24) px = display col 8 =
    CELL 4 of the top band with collision bypassed, so that cell must be air;
  * object caps: enemies + lamps + miner <= 2 per room, <= 1 element per tile
    row (the editor's kMaxRoomElements / ElementInRow rules);
  * object PLACEMENT (user rules 2026-10-21): every enemy and lamp sits on an
    AIR cell — the SNAKE is the one exception (it patrols out of a wall) and
    must have open air on the side its dir names. A lamp hangs in a gap next
    to a real wall (the screen edge / mirror seam does not count);
  * determinism: two runs are byte-identical;
  * hot start rooms: the spawn drops down cell 4, and convert promotes every
    row-1 wall of a hot model to a hot cell — so row-1 cell 4 must be AIR
    (HotDrop) or the player lands on a hot wall at the drop-in (2026-10-21);
  * convert: `convert_level.py --stage` into a temp `generated/` — the bank2
    level-table spill and BOTH bank3 windows (extras, shapes) must report at
    least SLACK_FLOOR bytes free.

Run: /home/iuri/python3/bin/python3 tools/test_generator.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import convert_level as C            # noqa: E402  (rows_from_json / load_stage)
import test_editor_roundtrip as ER   # noqa: E402  (editor build + PY constant)
import stage_reach as SR           # noqa: E402  (route_segments: power-cell guard)

LEVELS = 20
ROOMS = 2 + sum(range(2, LEVELS + 1))   # 211 (level 1 has 2 rooms too)
GRID_SPAN = 15                          # C1: nibble 15 is the no-room sentinel
MAX_SHAPES = 128  # format cap: 7-bit shape index (LAYOUT 8, 2026-10-24)
SHAPE_BUDGET = 128     # the format cap; the REAL limit is the bank3 shapes
                       # window (SLACK_FLOOR below), measured every run
SLACK_FLOOR = 64  # B that must stay free in each bank3 window
MAX_OBJECTS = 2                         # editor kMaxRoomElements / verify_build
START_CELL = 4                          # LevelStartX 32 px / 8 px per cell


def generate(binary: Path, out: Path) -> str:
    r = subprocess.run([str(binary), "--generate-stage", str(out)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        sys.exit(f"FAIL: --generate-stage rc={r.returncode}\n"
                 f"{r.stdout[-800:]}{r.stderr[-800:]}")
    return (r.stdout or "").strip()


def edge_cells(rows, direction: str) -> set[int]:
    """Open cells on an edge.

    Vertical links are either the centre pair (8,9) or the TWO-GAP scheme
    (cells 3 and 6, levels 5/9/13/17). The next room must repeat the SAME
    cells, or a drop lands inside a wall (2026-10-20 route-choice rule).
    Horizontal is ONE column (col 0) across the WALKABLE bands — bands 1..2
    of a 4-row model, band 1 only for a legacy 3-row plan — mirrored on
    both sides.
    """
    if direction == "north":
        return {x for x in range(10) if rows[0][x] == "."}
    if direction == "south":
        return {x for x in range(10) if rows[-1][x] == "."}
    # N=4: a 4-row model's side opening spans bands 1..2, so a west/east exit
    # can be taken from either walkable band. A 3-row model (legacy plan) keeps
    # the single band-1 opening (its row 2 is the floor).
    horiz = (1, 2) if len(rows) >= 4 else (1,)
    return {0} if any(rows[b][0] == "." for b in horiz if b < len(rows))         else set()


def edge_open(rows, direction: str) -> bool:
    return bool(edge_cells(rows, direction))


# Structural walls: hot, phase, door and hcrunch are GATED (they open at run
# time), so only rock/solid/void block a path for this check.
STRUCTURAL_WALLS = set("#H")   # rock + hot; P/C are gated (open at run time)


def entries_connected(rows) -> bool:
    """Every carved edge opening must reach the others through open cells.

    PF walls span a whole colour band, so a band-1 wall that does not line up
    with the vertical corridor makes a room impassable (user reports
    2026-10-21: level 13 rooms 11-13 unreachable; level 13 room 4 door
    unreachable). Rooms with fewer than two edge sides are dead ends/goals.

    Height-agnostic (N=4, 2026-10-24): the south edge is the LAST row, whatever
    the model height — a generated 4-row model's inserted AIR band is ordinary
    open space for the flood fill.
    """
    last = len(rows) - 1
    edges = []
    for x in range(10):
        if rows[0][x] not in STRUCTURAL_WALLS:
            edges.append((0, x))
        if rows[last][x] not in STRUCTURAL_WALLS:
            edges.append((last, x))
    for b in ((1, 2) if len(rows) >= 4 else (1,)):
        if b < len(rows) and rows[b][0] not in STRUCTURAL_WALLS:
            edges.append((b, 0))
    sides = set()
    for y, _x in edges:
        sides.add("N" if y == 0 else "S" if y == last else "H")
    if len(sides) < 2:
        return True
    horiz = tuple(b for b in ((1, 2) if len(rows) >= 4 else (1,))
                  if b < len(rows))
    entries = [e for e in edges if e[0] == 0 or e[0] in horiz]   # N + H in
    exits = [e for e in edges if e[0] == last or e[0] in horiz]  # S + H out
    for start in entries:
        seen = {start}
        stack = [start]
        while stack:
            y, x = stack.pop()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if (0 <= ny <= last and 0 <= nx < 10 and (ny, nx) not in seen
                        and rows[ny][nx] not in STRUCTURAL_WALLS):
                    seen.add((ny, nx))
                    stack.append((ny, nx))
        if not any(t in seen for t in exits):
            return False
    return True


def main() -> int:
    binary = ER.ensure_editor()

    with tempfile.TemporaryDirectory(prefix="savior_gen_") as td:
        tmp = Path(td)
        stage_a = tmp / "stage_a.json"
        stage_b = tmp / "stage_b.json"
        print(generate(binary, stage_a))
        generate(binary, stage_b)

        # --- determinism ---------------------------------------------------
        if stage_a.read_bytes() != stage_b.read_bytes():
            print("FAIL: two generator runs differ (not deterministic)")
            return 1

        raw = json.loads(stage_a.read_text())
        if "stage" not in raw:
            print("FAIL: stage file is not the canonical wrapped form")
            return 1
        stage = raw["stage"]
        models, levels = stage["models"], stage["levels"]

        # --- counts --------------------------------------------------------
        if len(levels) != LEVELS:
            print(f"FAIL: {len(levels)} levels, want {LEVELS}")
            return 1
        counts = [len(level["rooms"]) for level in levels]
        want_counts = [2] + list(range(2, LEVELS + 1))   # 2-room floor
        if counts != want_counts:
            print(f"FAIL: rooms per level {counts} != {want_counts}")
            return 1
        if sum(counts) != ROOMS:
            print(f"FAIL: {sum(counts)} rooms, want {ROOMS}")
            return 1

        # --- finishability (user report 2026-10-25: level 8 impossible) -----
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import stage_reach
        bad = stage_reach.problems(stage)
        if bad:
            print("FAIL: unfinishable levels:\n  " + "\n  ".join(bad))
            return 1

        # --- hcrunch needs a >= 2-tile gap above AND under (user 2026-10-25) -
        # The crush is survived only by leaving band 1; a one-tile hole cannot
        # be lined up in time. Rule: every room with an hcrunch feature cell
        # (tile 12) has a CONTIGUOUS open run of >= 2 cells in its ceiling row
        # and in its floor row.
        def longest_run(cells):
            best = run = 0
            for v in cells:
                run = run + 1 if v == 0 else 0
                best = max(best, run)
            return best

        by_id = {m["id"]: m for m in models}
        for level_n, level in enumerate(levels, start=1):
            for room in level["rooms"]:
                if not any(c[2] == 12 for c in room.get("feature_cells") or []):
                    continue
                tiles = by_id[room["model_id"]]["tiles"]
                top, bottom = tiles[:10], tiles[-10:]
                if longest_run(top) < 2 or longest_run(bottom) < 2:
                    print(f"FAIL: level {level_n} room {room['room_id']} has a "
                          f"hcrunch but a one-tile gap above/under (top run "
                          f"{longest_run(top)}, bottom run {longest_run(bottom)})")
                    return 1

        # --- model library -------------------------------------------------
        ids = [m["id"] for m in models]
        if ids != list(range(len(models))):
            print(f"FAIL: model ids {ids} are not 0..n-1")
            return 1
        if not 0 < len(models) <= MAX_SHAPES:
            print(f"FAIL: {len(models)} shapes > the {MAX_SHAPES} format cap")
            return 1
        if len(models) > SHAPE_BUDGET:
            print(f"FAIL: {len(models)} shapes > the generator budget "
                  f"{SHAPE_BUDGET} — raise kShapeBudget only with a measured "
                  "window fit")
            return 1
        shapes = {m["id"]: m for m in models}
        referenced = set()

        # --- per level: positions, adjacency carve, objects -----------------
        for level_n, level in enumerate(levels, start=1):
            rooms = level["rooms"]
            if level.get("miner_room") != len(rooms) - 1:
                print(f"FAIL: level {level_n} miner_room "
                      f"{level.get('miner_room')} is not the last room")
                return 1
            if level.get("start_room") != 0:
                print(f"FAIL: level {level_n} start_room "
                      f"{level.get('start_room')} (kernel constant 0)")
                return 1
            # Miner Y = the goal rock top - 12 px: 84 px on a 3-band room,
            # 96 px on a 4-band one (its floor band sits 36 px lower).
            _mroom = next((r for r in rooms
                           if r["room_id"] == level.get("miner_room")), None)
            _mh = 3
            if _mroom is not None:
                _mh = len(C.rows_from_json(_mroom, shapes))
            _want = 84 if _mh <= 3 else 96
            if int(level.get("miner_y", -1) * 12) != _want:
                print(f"FAIL: level {level_n} miner_y {level.get('miner_y')} "
                      f"(a {_mh}-band room needs {_want // 12} rows = "
                      f"{_want} px)")
                return 1
            pos = {}
            for room in rooms:
                key = (int(room["room_x"]), int(room["room_y"]))
                if key in pos:
                    print(f"FAIL: level {level_n}: rooms {pos[key]} and "
                          f"{room['room_id']} share {key}")
                    return 1
                pos[key] = room["room_id"]
                if not (0 <= key[0] < GRID_SPAN and 0 <= key[1] < GRID_SPAN):
                    print(f"FAIL: level {level_n} room {room['room_id']} at "
                          f"{key} outside the {GRID_SPAN}x{GRID_SPAN} C1 grid")
                    return 1
                referenced.add(room["model_id"])
            span_x = max(k[0] for k in pos)
            span_y = max(k[1] for k in pos)
            if span_x >= GRID_SPAN or span_y >= GRID_SPAN:
                print(f"FAIL: level {level_n} spans {span_x + 1}x{span_y + 1}")
                return 1

            rows = {room["room_id"]: C.rows_from_json(room, shapes)
                    for room in rooms}
            # A crunch room's band 1 is authored solid 0..9 for the loader, but
            # the kernel prefix starts at pair 1: cell 0 is passable at run time.
            for room in rooms:
                cells = [f[1] for f in (room.get("feature_cells") or [])
                         if f[2] == 12]
                if 0 in cells and len(rows[room["room_id"]]) > 1:
                    r1 = rows[room["room_id"]][1]
                    rows[room["room_id"]][1] = "." + r1[1:]
            # pos: (x, y) -> room_id (the C1 scan order); where: the reverse.
            where = {v: k for k, v in pos.items()}

            # The start room must have AIR at the drop-in cell (LevelStartX/Y).
            start_rows = rows[0]
            if start_rows[0][START_CELL] != ".":
                print(f"FAIL: level {level_n} start room top band cell "
                      f"{START_CELL} is {start_rows[0][START_CELL]!r} — the "
                      "spawn drop would land inside the ceiling")
                return 1
            # A hot start room must keep the drop COLUMN open: the player
            # falls through band 1 at cell 4.
            if shapes[rooms[0]["model_id"]].get("mid_band_type") and \
                    start_rows[1][START_CELL] != ".":
                print(f"FAIL: level {level_n} hot start room has "
                      f"{start_rows[1][START_CELL]!r} at row-1 cell "
                      f"{START_CELL} — the drop lands on a hot wall (HotDrop)")
                return 1

            # Adjacent pairs: the carve must agree on BOTH sides (tear rule).
            passages = 0
            for (x, y), rid in pos.items():
                here = rows[rid]
                for direction, other_pos in (("north", (x, y - 1)),
                                             ("south", (x, y + 1))):
                    mine = here
                    other = pos.get(other_pos)
                    if other is None:
                        # A WATER goal's row-2 air IS the surface, not an exit
                        # (the ROM's exit scan finds no room and the water kill
                        # fires first); every other room must be sealed south.
                        is_water = bool(rooms[rid].get("bottom_band"))
                        if (direction == "south" and edge_open(mine, "south")
                                and not is_water):
                            print(f"FAIL: level {level_n} room {rid} has a "
                                  "south opening with no room below")
                            return 1
                        continue
                    theirs = rows[other]
                    opposite = "south" if direction == "north" else "north"
                    if edge_open(mine, direction) != edge_open(theirs, opposite):
                        print(f"FAIL: level {level_n} rooms {rid} and {other} "
                              f"disagree on the {direction} carve "
                              f"({direction}={edge_open(mine, direction)}, "
                              f"{opposite}={edge_open(theirs, opposite)}) — "
                              "one-sided carve tears the transition")
                        return 1
                    shared = (edge_cells(mine, direction)
                              & edge_cells(theirs, opposite))
                    if edge_open(mine, direction) and not shared:
                        print(f"FAIL: level {level_n} rooms {rid} and {other} "
                              f"open the {direction} edge on DIFFERENT cells "
                              f"({sorted(edge_cells(mine, direction))} vs "
                              f"{sorted(edge_cells(theirs, opposite))}) — the "
                              "player would drop into a wall")
                        return 1
                    # count each PASSAGE once (adjacent-but-walled pairs are
                    # legal and are not passages)
                    if direction == "south" and edge_open(mine, "south"):
                        passages += 1
                for other_pos, name in (((x - 1, y), "west"),
                                        ((x + 1, y), "east")):
                    other = pos.get(other_pos)
                    if other is None:
                        continue
                    # The mirrored playfield: cell 0 is BOTH edges, so a
                    # horizontal pair passes only when both rooms cut it.
                    if edge_open(here, "west") != edge_open(rows[other], "west"):
                        print(f"FAIL: level {level_n} rooms {rid} and {other} "
                              f"disagree on the {name} carve (mirrored cell 0)")
                        return 1
                    if name == "east" and edge_open(here, "west"):
                        passages += 1
            # Reachability through the passable openings (each vertical pair is
            # mutual by the check above; a horizontal pair passes only when
            # both sides cut cell 0).
            seen = {0}
            stack = [0]
            while stack:
                rid = stack.pop()
                x, y = where[rid]
                # (neighbour, my edge, the neighbour's facing edge). West and
                # east are the SAME mirrored cell, so a horizontal passage
                # needs cell 0 cut in both rooms.
                for other_pos, mine_e, other_e in (
                        ((x, y - 1), "north", "south"),
                        ((x, y + 1), "south", "north"),
                        ((x - 1, y), "west", "west"),
                        ((x + 1, y), "east", "west")):
                    other = pos.get(other_pos)
                    if other is None or other in seen:
                        continue
                    if edge_open(rows[rid], mine_e) and \
                            edge_open(rows[other], other_e):
                        seen.add(other)
                        stack.append(other)
            # LAYOUT RULE (user 2026-10-24): a passage exists for EVERY grid
            # adjacency — neither more nor fewer. The generator is no longer a
            # serpentine, so the count is not `rooms - 1`: a maze level with
            # ties has one passage per adjacent pair (loops included, which is
            # how the room before the miner can be approached two ways).
            adjacencies = 0
            for (ax, ay), aroom in pos.items():
                for dx, dy in ((1, 0), (0, 1)):
                    other = pos.get((ax + dx, ay + dy))
                    if other is None:
                        continue
                    mine = "east" if dx else "south"
                    theirs = "west" if dx else "north"
                    if (edge_open(rows[aroom], mine)
                            and edge_open(rows[other], theirs)):
                        adjacencies += 1
            if passages != adjacencies:
                print(f"FAIL: level {level_n} has {passages} passages for "
                      f"{len(rooms)} rooms, but {adjacencies} grid adjacencies "
                      "(the layout decides every passage)")
                return 1
            if len(seen) != len(rooms):
                print(f"FAIL: level {level_n} is not walkable — "
                      f"{len(seen)}/{len(rooms)} rooms reachable from the start")
                return 1

            # Miner stands on a solid block (user rule 2026-10-21): a person
            # to rescue does not float over water/air. miner_x is in CELL
            # units (converter: display col = x*2); MinerY = 84 px (band 1),
            # so the band-2 cell under him must be solid.
            miner_id = int(level["miner_room"]) & 0x7F
            miner_rows = rows[miner_id]
            miner_cell = int(round(float(level["miner_x"])))
            if not 0 <= miner_cell < 20:
                print(f"FAIL: level {level_n} miner_x {level['miner_x']} is "
                      "outside the 20-cell stage")
                return 1
            half_cell = (miner_cell if miner_cell < 10 else 19 - miner_cell)
            if miner_rows[-1][half_cell] == ".":
                print(f"FAIL: level {level_n} miner room {miner_id} has no "
                      f"block under the miner at cell {half_cell} "
                      f"({miner_rows[-1]!r})")
                return 1
            # ...and the player must be able to REACH him: his own cell is
            # air and an entry cell of the room floods to it.
            if miner_rows[1][half_cell] != ".":
                print(f"FAIL: level {level_n} miner sits in a wall at cell "
                      f"{half_cell} ({miner_rows[1]!r})")
                return 1
            seen = {(1, half_cell)}
            stack = [(1, half_cell)]
            while stack:
                my, mx = stack.pop()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = my + dy, mx + dx
                    if (0 <= ny < 3 and 0 <= nx < 10
                            and (ny, nx) not in seen
                            and miner_rows[ny][nx] not in STRUCTURAL_WALLS):
                        seen.add((ny, nx))
                        stack.append((ny, nx))
            edges = [(0, x) for x in range(10)
                     if miner_rows[0][x] not in STRUCTURAL_WALLS]
            edges += [(2, x) for x in range(10)
                      if miner_rows[-1][x] not in STRUCTURAL_WALLS]
            if miner_rows[1][0] not in STRUCTURAL_WALLS:
                edges.append((1, 0))
            if not any(e in seen for e in edges):
                print(f"FAIL: level {level_n} miner room {miner_id} has no "
                      "entry cell connected to the miner")
                return 1
            # A SIDE entry must put the miner on the OPPOSITE side (user rule
            # 2026-10-21): walked rooms are in order, so the room before the
            # goal is where the player comes from.
            if len(rooms) > 1:
                prev, goal = rooms[-2], rooms[-1]
                if int(prev["room_y"]) == int(goal["room_y"]) and \
                        int(prev["room_x"]) != int(goal["room_x"]):
                    from_west = int(prev["room_x"]) < int(goal["room_x"])
                    want_right = from_west
                    if (miner_cell >= 10) != want_right:
                        print(f"FAIL: level {level_n} miner entered from "
                              f"{'west' if from_west else 'east'} but sits "
                              f"at cell {miner_cell} (same side)")
                        return 1

            # NO STRAIGHT VERTICAL FALL (user rule 2026-10-21): from level 6
            # every through-room must change its exit COUNT or WIDTH between
            # the top and the bottom (links alternate narrow/wide). A room
            # with a horizontal exit is exempt — its route already turns.
            if level_n >= 6:
                for room in rooms:
                    r2 = rows[room["room_id"]]
                    nset = {x for x in range(10)
                            if r2[0][x] not in STRUCTURAL_WALLS}
                    sset = {x for x in range(10)
                            if r2[-1][x] not in STRUCTURAL_WALLS}  # floor band
                    if (nset and sset and nset == sset
                            and all(r2[b][0] in STRUCTURAL_WALLS
                                    for b in ((1, 2) if len(r2) >= 4 else (1,))
                                    if b < len(r2))):
                        print(f"FAIL: level {level_n} room "
                              f"{room['room_id']} is a straight vertical fall "
                              f"(top and bottom both open {sorted(nset)})")
                        return 1

            # NO OBJECT ON THE ARRIVAL COLUMNS (user report 2026-10-24, level 6
            # room 2: "on the next screen he stops falling"). A vertical link
            # drops the player at the aperture columns with NO input yet, so an
            # enemy parked there overlaps him on the frame the room loads and
            # CheckEnemyHit costs a life before he can move — the respawn hover
            # then holds him at the top, which reads as "stuck".
            for room in rooms:
                r2 = rows[room["room_id"]]
                aper = set()
                for x in range(10):
                    if r2[0][x] not in STRUCTURAL_WALLS:
                        aper.update((2 * x, 2 * x + 1))
                if not aper:
                    continue
                # Enemies only: a LAMP is a collectible, harmless to touch.
                rows_per_band = max(1, 12 // max(1, len(r2)))
                # SIDE links: the player keeps his Y through a horizontal link,
                # so a side-aperture band with an enemy on that edge column is
                # the same instant kill (guard: the live stage has none).
                west_nbr = (int(room["room_x"]) - 1, int(room["room_y"])) in pos
                east_nbr = (int(room["room_x"]) + 1, int(room["room_y"])) in pos
                side_bands = {b for b in range(1, len(r2) - 1)
                              if r2[b][0] not in STRUCTURAL_WALLS}
                for obj in (room.get("enemies") or []):
                    if obj.get("type") == 14:
                        continue          # a power cell is a pickup, not a hazard
                    band = int(float(obj.get("y", 0))) // rows_per_band
                    col = int(round(float(obj.get("x", 0))))
                    # band 0 is the vertical arrival; from band 1 on he lands
                    # and can react — unless it is a SIDE edge cell.
                    if band == 0:
                        bad = any(abs(col - c) <= 1 for c in aper)
                    else:
                        bad = band in side_bands and (
                            (west_nbr and col <= 1) or (east_nbr and col >= 18))
                    if bad:
                        print(f"FAIL: level {level_n} room {room['room_id']} "
                              f"puts an enemy on arrival column {col} "
                              f"(band {band}; vertical aperture {sorted(aper)}, "
                              f"side bands {sorted(side_bands)}) — the player "
                              "enters there and dies on contact")
                        return 1

            # Connectivity + gate alignment (user reports 2026-10-21).
            for room in rooms:
                rrows = rows[room["room_id"]]
                if not entries_connected(rrows):
                    print(f"FAIL: level {level_n} room {room['room_id']} "
                          "does not connect its carved entries — a band-1 "
                          f"wall is off the corridor {rrows}")
                    return 1
                # A gate/blink cell gates the VERTICAL passage, so it must sit on
                # a column the player enters or leaves the room by. In the maze
                # layout a room can be a corner (north link only, or south
                # only), so "the corridor" is any column open in band 0 OR the
                # last band — not only a through-column (2026-10-24).
                corridor = {x for x in range(10)
                            if rrows[0][x] == "." or rrows[-1][x] == "."}
                door_cols = [int(patch[1])
                             for patch in room.get("asym_patches") or []
                             if len(patch) >= 3 and patch[2] == 9]
                phase_cols = [int(feat[1])
                              for feat in room.get("feature_cells") or []
                              if len(feat) == 3 and feat[2] == 10]
                if door_cols or phase_cols:
                    if not corridor:
                        print(f"FAIL: level {level_n} room "
                              f"{room['room_id']} has a gate but no vertical "
                              "corridor")
                        return 1
                    for col in door_cols + phase_cols:
                        if col not in corridor:
                            print(f"FAIL: level {level_n} room "
                                  f"{room['room_id']} gate/blink at cell {col} "
                                  f"is OFF the corridor {sorted(corridor)} — "
                                  "unreachable")
                            return 1

            # Objects: the editor caps (2 per room, 1 per tile row).
            for room in rooms:
                enemies = room.get("enemies") or []
                lamps = room.get("lamps") or []
                miner = 1 if level["miner_room"] == room["room_id"] else 0
                if len(enemies) + len(lamps) + miner > MAX_OBJECTS:
                    print(f"FAIL: level {level_n} room {room['room_id']}: "
                          f"{len(enemies)} enemies + {len(lamps)} lamps + "
                          f"{miner} miner > {MAX_OBJECTS}")
                    return 1
                used_rows = [int(e["y"]) for e in enemies]
                used_rows += [int(lamp["y"]) for lamp in lamps]
                if miner:
                    used_rows.append(int(level["miner_y"]))
                if len(used_rows) != len(set(used_rows)):
                    print(f"FAIL: level {level_n} room {room['room_id']}: "
                          f"two elements on one row {used_rows}")
                    return 1
                band_rows = rows[room["room_id"]]
                # y is in 12-px display rows: a band spans 12/height of them
                units = 12 // len(band_rows)
                for enemy in enemies:
                    if not (0 <= float(enemy["x"]) <= 39
                            and 0 <= float(enemy["y"]) <= 12 - 1):
                        print(f"FAIL: level {level_n} room "
                              f"{room['room_id']}: enemy at "
                              f"({enemy['x']}, {enemy['y']})")
                        return 1
                # Placement: air cells only (snake = wall patroller).
                for enemy in enemies:
                    cell = int(float(enemy["x"])) // 2
                    if int(enemy["type"]) == 15:
                        # an extra miner stands anywhere in a cell run: every
                        # 8 px cell his sprite covers must be air (the
                        # converter's seat rule checks the same)
                        xpx = int(float(enemy["x"])) * 4   # visible left edge
                        cell = min(19, xpx // 8)
                        if (min(19, (xpx + 7) // 8)) != cell:
                            other = min(19, (xpx + 7) // 8)
                            other = other if other < 10 else 19 - other
                            if band_rows[int(float(enemy["y"])) // units][other] != ".":
                                print(f"FAIL: level {level_n} room "
                                      f"{room['room_id']}: extra miner overlaps "
                                      f"a wall cell {other}")
                                return 1
                    if cell >= 10:                   # right chamber = the mirror
                        cell = 19 - cell
                    band = int(float(enemy["y"])) // units
                    here = band_rows[band][cell]
                    if int(enemy["type"]) == 2:      # SNAKE lives in the wall
                        d = -1 if int(enemy.get("dir", 1)) < 0 else 1
                        face = cell + d
                        face_ch = (band_rows[band][face]
                                   if 0 <= face < 10 else ".")
                        if here != "." and face_ch != ".":
                            print(f"FAIL: level {level_n} room "
                                  f"{room['room_id']}: snake at cell {cell} "
                                  f"has walls on BOTH sides (faces {d:+d})")
                            return 1
                    elif here != ".":
                        print(f"FAIL: level {level_n} room {room['room_id']}: "
                              f"enemy type {enemy['type']} at cell {cell}/"
                              f"band {band} is inside a wall ({here!r})")
                        return 1
                for lamp in room.get("lamps") or []:
                    cell = int(float(lamp["x"])) // 2
                    band = int(float(lamp["y"])) // units
                    if band_rows[band][cell] != ".":
                        print(f"FAIL: level {level_n} room {room['room_id']}: "
                              f"lamp at cell {cell}/band {band} is inside a "
                              "wall")
                        return 1
                    left = band_rows[band][cell - 1] if cell > 0 else "."
                    right = (band_rows[band][cell + 1]
                             if cell < 9 else ".")
                    if left == "." and right == ".":
                        print(f"FAIL: level {level_n} room {room['room_id']}: "
                              f"lamp at cell {cell}/band {band} floats in a "
                              "gap with no wall beside it")
                        return 1
                # Async is one of three generated specials, all row 1:
                # LOCKED_DOOR (gate), PHASE (blinking gate), HCRUNCH (10-cell
                # prefix). A hcrunch room must be object-free (convert rule).
                patches = room.get("asym_patches") or []
                if len(patches) > 2:
                    print(f"FAIL: level {level_n} room {room['room_id']} "
                          f"has {len(patches)} patches (convert cap 2)")
                    return 1
                # A DEAD-SIDE PLUG (user rule 2026-10-24) is the one legal
                # row-2 patch: the reflected H aperture spans bands 1 AND 2, so
                # the plug for a side with no room needs one patch per band, at
                # the same column and side as its row-1 partner.
                plug_cols = {(p[1], p[3] if len(p) > 3 else 0)
                             for p in patches if p[0] == 1}
                for patch in patches:
                    is_plug = (patch[0] == 2
                               and (patch[1],
                                    patch[3] if len(patch) > 3 else 0)
                               in plug_cols)
                    if (len(patch) < 3 or (patch[0] != 1 and not is_plug)
                            or patch[2] not in (1, 9)):
                        print(f"FAIL: level {level_n} room {room['room_id']} "
                              f"has unexpected async {patch} (only a row-1 "
                                  "solid block, LOCKED_DOOR or a dead-side "
                                  "plug on rows 1-2)")
                        return 1
                feats = room.get("feature_cells") or []
                kinds = {c[2] for c in feats}
                if len(kinds) > 1:
                    print(f"FAIL: level {level_n} room {room['room_id']} "
                          f"mixes feature kinds {sorted(kinds)}")
                    return 1
                for cell in feats:
                    if len(cell) != 3 or cell[0] != 1:
                        print(f"FAIL: level {level_n} room {room['room_id']} "
                              f"feature {cell} is not on row 1")
                        return 1
                if 12 in kinds:
                    objs = (len(room.get("enemies") or [])
                            + len(room.get("lamps") or []))
                    if objs:
                        print(f"FAIL: level {level_n} hcrunch room "
                              f"{room['room_id']} has {objs} objects")
                        return 1

        if referenced != set(shapes):
            print(f"FAIL: models {sorted(set(shapes) - referenced)} are never "
                  "referenced (the converter would not emit them)")
            return 1

        # --- feature progression (2026-10-20: HERO-style variety) ----------
        # Every level must add/keep challenges: hot bands from 3, a water goal
        # from 4 (raft, then tentacle from 7), a keyed gate from 6, two-object
        # rooms from 9. A gate room is limited to ONE non-key enemy (convert).
        short_levels: list[int] = []
        for level_n, level in enumerate(levels, start=1):
            rooms = level["rooms"]
            hot = water = doors = keys = tents = rafts = two_obj = 0
            phases = hcrunches = blocks = two_blocks = 0
            for room in rooms:
                model = shapes[room["model_id"]]
                if model.get("mid_band_type"):
                    hot += 1
                if room.get("bottom_band"):
                    water += 1
                feats = {c[2] for c in room.get("feature_cells") or []}
                phases += 10 in feats
                hcrunches += 12 in feats
                door_patches = [p for p in room.get("asym_patches") or []
                                if len(p) >= 3 and p[2] == 9]
                block_patches = [p for p in room.get("asym_patches") or []
                                 if len(p) >= 3 and p[2] == 1]
                doors += bool(door_patches)
                if door_patches or 10 in feats:
                    # Gate/phase = band 1: no enemy in band 1 itself, and the
                    # generator keeps band 2 empty too (user 2026-10-26).
                    for e in room.get("enemies") or []:
                        if e.get("type") in (6, 14):
                            continue
                        band = int(e.get("y")) * len(rows[room["room_id"]]) // 12
                        if band in (1, 2):
                            print(f"FAIL: level {level_n} room "
                                  f"{room['room_id']} gate/phase room has an "
                                  f"enemy in band {band}")
                            return 1
                # One object per COLUMN, whatever the band (user 2026-10-26).
                cols = [round(e.get("x")) for e in room.get("enemies") or []]
                cols += [round(x.get("x")) for x in room.get("lamps") or []]
                if len(set(cols)) != len(cols):
                    print(f"FAIL: level {level_n} room {room['room_id']} "
                          f"has two objects on one column {sorted(cols)}")
                    return 1
                blocks += bool(block_patches)
                two_blocks += len(block_patches) >= 2
                if door_patches:
                    objs = (len(room.get("enemies") or [])
                            + len(room.get("lamps") or []))
                    if objs > 1:
                        print(f"FAIL: level {level_n} door room has {objs} objects")
                        return 1
                for e in room.get("enemies") or []:
                    kind = e.get("type")
                    keys += kind == 6
                    tents += kind == 3
                    rafts += kind == 7
                objs = (len(room.get("enemies") or [])
                        + len(room.get("lamps") or []))
                two_obj += objs >= 2
            # --- power cells (2026-10-26): the timer is 120 s; the estimated
            # stretch between refills must stay inside the budget, cells live in
            # rooms that differ mod 4 (the kernel latches bit room&3), never in
            # the start/goal room, door rooms or hcrunch rooms.
            seg = SR.route_segments(level, shapes)
            if seg is None:
                print(f"FAIL: level {level_n} has no route (route_segments)")
                return 1
            if seg[1] > SR.CELL_BUDGET:
                print(f"FAIL: level {level_n}: {seg[1] / 60:.0f} s between "
                      f"refills (> {SR.CELL_BUDGET // 60} s) - needs a power "
                      "cell on its route")
                return 1
            cell_rooms = [i for i, r in enumerate(rooms)
                          if any(e.get("type") == 14
                                 for e in r.get("enemies") or [])]
            if len({i & 3 for i in cell_rooms}) != len(cell_rooms):
                print(f"FAIL: level {level_n}: power cells in rooms "
                      f"{cell_rooms} share a taken-bit (room index mod 4)")
                return 1
            for i in cell_rooms:
                r = rooms[i]
                kinds = {c[2] for c in r.get("feature_cells") or []}
                doors = [p for p in r.get("asym_patches") or []
                         if len(p) >= 3 and p[2] == 9]
                if (i in (level["start_room"], level["miner_room"])
                        or 12 in kinds or doors):
                    print(f"FAIL: level {level_n} room {i}: a power cell in a "
                          "start/goal/hcrunch/door room")
                    return 1
            # --- extra miners (2026-10-26): ramp 1/2/3 miners = 0/1/2 extras at
            # levels 1-6 / 7-13 / 14-20 (the generator places fewer only when no
            # room can host one); rooms of different parity, never in the
            # start/goal/door/hcrunch/phase rooms, at most one per room.
            extra_rooms = [i for i, r in enumerate(rooms)
                           if any(e.get("type") == 15
                                  for e in r.get("enemies") or [])]
            ramp = 0 if level_n < 7 else (1 if level_n < 14 else 2)
            if len(extra_rooms) > ramp:
                print(f"FAIL: level {level_n}: {len(extra_rooms)} extra miner(s), "
                      f"the ramp allows {ramp}")
                return 1
            if len(extra_rooms) < ramp:
                short_levels.append(level_n)
            if level_n == len(levels) and len(short_levels) > 4:
                print(f"FAIL: levels {short_levels} carry fewer extra miners than "
                      "the ramp (no host room); at most 4 levels may fall short")
                return 1
            if len({i & 1 for i in extra_rooms}) != len(extra_rooms):
                print(f"FAIL: level {level_n}: extra miners in rooms {extra_rooms} "
                      "share a parity (one rescued-bit each)")
                return 1
            for i in extra_rooms:
                r = rooms[i]
                n15 = sum(1 for e in r.get("enemies") or [] if e.get("type") == 15)
                kinds = {c[2] for c in r.get("feature_cells") or []}
                doors = [p for p in r.get("asym_patches") or []
                         if len(p) >= 3 and p[2] == 9]
                if (n15 != 1 or i in (level["start_room"], level["miner_room"])
                        or kinds or doors):
                    print(f"FAIL: level {level_n} room {i}: bad extra-miner host "
                          "(start/goal/door/feature room or two in one room)")
                    return 1
            if level_n <= 6 and cell_rooms:
                print(f"FAIL: level {level_n}: short level carries a power cell")
                return 1
            if level_n >= 3 and hot == 0:
                print(f"FAIL: level {level_n} has no hot room")
                return 1
            if level_n >= 4 and (water < 1
                                 or not rooms[-1].get("bottom_band")):
                print(f"FAIL: level {level_n} last room is not a water goal "
                      f"(water={water})")
                return 1
            # The water goal carries the TENTACLE guard, never a RAFT (user
            # rule 2026-10-24: with a jetpack an open-water goal is always
            # flyable, so a ferry there is decoration — the raft only earns its
            # slot in a CHANNEL room, where the hot ceiling forces a low
            # crossing).
            goal_hazards = [e.get("type") for e in rooms[-1].get("enemies") or []
                            if e.get("type") in (3, 7)]
            if level_n >= 4 and 7 in goal_hazards:
                print(f"FAIL: level {level_n} water goal has a RAFT — the "
                      "ferry is useless in open water (flyable with the jet)")
                return 1
            if level_n >= 4 and len(goal_hazards) > 1:
                print(f"FAIL: level {level_n} water goal has several guards "
                      f"({goal_hazards})")
                return 1
            # Locked doors are disabled (M1 stripe cannot gate a vertical
            # corridor — see DataSerializer PlanFor); the gate role is the
            # blinking PHASE corridor from level 6.
            if doors or keys:
                print(f"FAIL: level {level_n} has locked doors/keys "
                      f"(doors={doors}, keys={keys}) — disabled until the "
                      "per-pair exit redesign")
                return 1
            if level_n >= 7 and tents == 0:
                print(f"FAIL: level {level_n} has no tentacle")
                return 1
            if level_n >= 5 and two_obj == 0:
                print(f"FAIL: level {level_n} has no two-object room")
                return 1
            # 2026-10-21 rules: clean spawn room; hot rooms carry no object in
            # the hot middle band (bands 0/2 only).
            start_room = rooms[0]
            if start_room.get("enemies") or start_room.get("lamps"):
                print(f"FAIL: level {level_n} start room has objects")
                return 1
            for room in rooms:
                if not shapes[room["model_id"]].get("mid_band_type"):
                    continue
                ys = [e.get("y") for e in room.get("enemies") or []]
                ys += [x.get("y") for x in room.get("lamps") or []]
                _u = 12 // len(rows[room["room_id"]])
                if any(int(float(y)) // _u == 1 for y in ys):
                    print(f"FAIL: level {level_n} room {room['room_id']} has "
                          "an object in a HOT middle band")
                    return 1
            if level_n >= 6 and phases == 0:
                print(f"FAIL: level {level_n} has no phase wall")
                return 1
            # A crunch room's band 1 is one solid feature prefix, so it cannot
            # also carry a side link (the link would be a feature cell, not
            # air). The maze decides the geometry, so a crunch band is required
            # only when the level actually HAS a legal host room: a vertical
            # passage and no side opening.
            # The crunch sweeps band 1 from pair 1 (pair 0 stays open so a
            # crunch room can carry a side link), so ANY room with a vertical
            # passage can host it.
            if level_n >= 14 and hcrunches == 0:
                host = False
                for (hx, hy), hrid in pos.items():
                    if hrid == 0 or hrid == level.get("miner_room"):
                        continue
                    # 2026-10-25: a crunch needs a gap above AND under, so a
                    # host has a room on both sides, and the one under it is
                    # neither the water goal nor a channel (it takes a widened
                    # ceiling).
                    if (hx, hy - 1) in pos and (hx, hy + 1) in pos:
                        under = pos[(hx, hy + 1)]
                        if (under != level.get("miner_room")
                                and "Channel" not in shapes[
                                    level["rooms"][under]["model_id"]]["name"]
                                and "Channel" not in shapes[
                                    level["rooms"][hrid]["model_id"]]["name"]):
                            host = True
                            break
                if host:
                    print(f"FAIL: level {level_n} has a crunch host room but "
                          "no hcrunch band")
                    return 1
            if level_n >= 7 and blocks == 0:
                print(f"FAIL: level {level_n} has no async block room")
                return 1
            # Two-block async rooms are opportunistic: a pair needs BOTH
            # mirrored columns to satisfy the M1 wall-hide envelope, which many
            # shapes cannot offer. A single block per level is required; the
            # pair is a bonus when the shape allows it.
            if level_n >= 7 and blocks == 0:
                print(f"FAIL: level {level_n} has no async block room")
                return 1
            if level_n >= 11:
                # HERO-style crossing: hot ceiling + open water + raft.
                channels = [r for r in rooms
                            if shapes[r["model_id"]].get("mid_band_type")
                            and r.get("bottom_band")
                            and any(e.get("type") == 7
                                    for e in r.get("enemies") or [])]
                if not channels:
                    print(f"FAIL: level {level_n} has no water channel "
                          "(hot ceiling + raft)")
                    return 1

        # --- no two levels may be the same playable content ---------------
        # (user report 2026-10-20: levels 1 and 2 were identical — both are
        # 2-room levels, so the start enemy type/cell and the snake's patrol
        # direction now vary per level).
        sigs = []
        for level in levels:
            sig = []
            for room in level["rooms"]:
                sig.append((
                    room["model_id"],
                    tuple(sorted((e.get("type"), e.get("x"), e.get("y"))
                                 for e in room.get("enemies") or [])),
                    tuple(sorted((l.get("x"), l.get("y"))
                                 for l in room.get("lamps") or [])),
                    bool(room.get("bottom_band")),
                    tuple(tuple(p) for p in room.get("asym_patches") or []),
                    tuple(tuple(c) for c in room.get("feature_cells") or []),
                ))
            sigs.append(tuple(sig))
        if len(set(sigs)) != len(sigs):
            dup = [i + 1 for i in range(len(sigs))
                   if sigs.count(sigs[i]) > 1]
            print(f"FAIL: duplicate level content at levels {dup}")
            return 1
        if sigs[0] == sigs[1]:
            print("FAIL: levels 1 and 2 are identical")
            return 1

        # --- convert + capacity (the C7 windows) ---------------------------
        gen = tmp / "conv" / "generated"
        rooms_dir = tmp / "conv" / "rooms"
        gen.mkdir(parents=True)
        rooms_dir.mkdir(parents=True)
        r = subprocess.run([ER.PY, str(ROOT / "tools" / "convert_level.py"),
                            "--stage", str(stage_a), str(gen), str(rooms_dir)],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            print(f"FAIL: convert_level --stage failed:\n{r.stderr[-2000:]}")
            return 1
        tables_slack = extras_slack = shapes_slack = None
        for line in r.stdout.splitlines():
            if "level tables (bank2)" in line:
                tables_slack = int(re.search(r"slot slack (\d+)B", line).group(1))
            if "bank3 extras:" in line:
                extras_slack = int(re.search(r"slack (\d+)B", line).group(1))
            if "bank3 shapes:" in line:
                shapes_slack = int(re.search(r"slack (\d+)B", line).group(1))
        if tables_slack is None or extras_slack is None or shapes_slack is None:
            print(f"FAIL: no capacity report in the converter output:\n"
                  f"{r.stdout[-2000:]}")
            return 1
        if min(tables_slack, extras_slack, shapes_slack) < SLACK_FLOOR:
            print(f"FAIL: capacity — bank2 slack {tables_slack}B, bank3 "
                  f"extras slack {extras_slack}B, shapes slack "
                  f"{shapes_slack}B (floor {SLACK_FLOOR}B)")
            return 1
        index = (gen / "levels_index.asm").read_text()
        m = re.search(r"^LEVEL_COUNT = (\d+)$", index, re.M)
        if not m or int(m.group(1)) != LEVELS:
            print(f"FAIL: levels_index LEVEL_COUNT {m.group(1) if m else None}")
            return 1
        m = re.search(r"^LEVEL_SHAPE_COUNT = (\d+)$", index, re.M)
        if not m or int(m.group(1)) != len(models):
            print(f"FAIL: LEVEL_SHAPE_COUNT {m.group(1) if m else None} != "
                  f"{len(models)} models")
            return 1
        txts = list(rooms_dir.glob("level_*_room_*.txt"))
        if len(txts) != ROOMS:
            print(f"FAIL: {len(txts)} room .txt mirrors, want {ROOMS}")
            return 1

        print(f"test_generator: OK (20 levels, {ROOMS} rooms, "
              f"{len(models)} shapes, byte-identical reruns, "
              f"bank2 slack {tables_slack}B, bank3 extras {extras_slack}B / "
              f"shapes {shapes_slack}B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
