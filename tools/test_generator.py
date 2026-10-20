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
  * model library: <= 32 shapes, ids 0..n-1 contiguous, EVERY model referenced
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
  * determinism: two runs are byte-identical;
  * convert: `convert_level.py --stage` into a temp `generated/` — the bank2
    level-table spill and the bank3 shape window must both report slack.

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

LEVELS = 20
ROOMS = 2 + sum(range(2, LEVELS + 1))   # 211 (level 1 has 2 rooms too)
GRID_SPAN = 15                          # C1: nibble 15 is the no-room sentinel
MAX_SHAPES = 32
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
    Horizontal is ONE cell (row 1, col 0), mirrored on both sides.
    """
    if direction == "north":
        return {x for x in range(10) if rows[0][x] == "."}
    if direction == "south":
        return {x for x in range(10) if rows[2][x] == "."}
    return {0} if rows[1][0] == "." else set()


def edge_open(rows, direction: str) -> bool:
    return bool(edge_cells(rows, direction))


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

        # --- model library -------------------------------------------------
        ids = [m["id"] for m in models]
        if ids != list(range(len(models))):
            print(f"FAIL: model ids {ids} are not 0..n-1")
            return 1
        if not 0 < len(models) <= MAX_SHAPES:
            print(f"FAIL: {len(models)} shapes > the {MAX_SHAPES} budget")
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
            if int(level.get("miner_y", -1) * 12) != 84:
                print(f"FAIL: level {level_n} miner_y {level.get('miner_y')} "
                      "(convert needs exactly 7 rows = 84 px)")
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
            # pos: (x, y) -> room_id (the C1 scan order); where: the reverse.
            where = {v: k for k, v in pos.items()}

            # The start room must have AIR at the drop-in cell (LevelStartX/Y).
            start_rows = rows[0]
            if start_rows[0][START_CELL] != ".":
                print(f"FAIL: level {level_n} start room top band cell "
                      f"{START_CELL} is {start_rows[0][START_CELL]!r} — the "
                      "spawn drop would land inside the ceiling")
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
            # The serpentine is a TREE: exactly one PASSAGE per room beyond the
            # first. Any extra one would be an accidental (mirror) connection;
            # adjacent-but-walled pairs are legal and are not counted.
            if passages != len(rooms) - 1:
                print(f"FAIL: level {level_n} has {passages} passages for "
                      f"{len(rooms)} rooms (want exactly {len(rooms) - 1})")
                return 1
            if len(seen) != len(rooms):
                print(f"FAIL: level {level_n} is not walkable — "
                      f"{len(seen)}/{len(rooms)} rooms reachable from the start")
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
                for enemy in enemies:
                    if not (0 <= float(enemy["x"]) <= 39
                            and 0 <= float(enemy["y"]) <= 11):
                        print(f"FAIL: level {level_n} room "
                              f"{room['room_id']}: enemy at "
                              f"({enemy['x']}, {enemy['y']})")
                        return 1
                # Async is one of three generated specials, all row 1:
                # LOCKED_DOOR (gate), PHASE (blinking gate), HCRUNCH (10-cell
                # prefix). A hcrunch room must be object-free (convert rule).
                patches = room.get("asym_patches") or []
                if len(patches) > 2:
                    print(f"FAIL: level {level_n} room {room['room_id']} "
                          f"has {len(patches)} patches (convert cap 2)")
                    return 1
                for patch in patches:
                    if len(patch) < 3 or patch[0] != 1 or patch[2] not in (1, 9):
                        print(f"FAIL: level {level_n} room {room['room_id']} "
                              f"has unexpected async {patch} (only a row-1 "
                              "solid block or LOCKED_DOOR)")
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
            if level_n >= 3 and hot == 0:
                print(f"FAIL: level {level_n} has no hot room")
                return 1
            if level_n >= 4 and water != 1:
                print(f"FAIL: level {level_n} has no water goal (water={water})")
                return 1
            if level_n >= 4 and rafts + tents != 1:
                print(f"FAIL: level {level_n} water goal has no raft/tentacle")
                return 1
            if level_n < 7 and level_n >= 4 and rafts == 0:
                print(f"FAIL: level {level_n} water goal should carry a raft")
                return 1
            if level_n >= 6 and (doors == 0 or keys != doors):
                print(f"FAIL: level {level_n} gate/key mismatch "
                      f"(doors={doors}, keys={keys})")
                return 1
            if level_n >= 7 and tents == 0:
                print(f"FAIL: level {level_n} has no tentacle")
                return 1
            if level_n >= 9 and two_obj == 0:
                print(f"FAIL: level {level_n} has no two-object room")
                return 1
            if level_n >= 11 and phases == 0:
                print(f"FAIL: level {level_n} has no phase wall")
                return 1
            if level_n >= 14 and hcrunches == 0:
                print(f"FAIL: level {level_n} has no hcrunch band")
                return 1
            if level_n >= 7 and blocks == 0:
                print(f"FAIL: level {level_n} has no async block room")
                return 1
            if level_n >= 12 and two_blocks == 0:
                print(f"FAIL: level {level_n} has no two-block async room")
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
        tables_slack = bank3_slack = None
        for line in r.stdout.splitlines():
            if "level tables (bank2)" in line:
                tables_slack = int(re.search(r"slot slack (\d+)B", line).group(1))
            if "bank3 data" in line:
                bank3_slack = int(re.search(r"slack (\d+)B", line).group(1))
        if tables_slack is None or bank3_slack is None:
            print(f"FAIL: no capacity report in the converter output:\n"
                  f"{r.stdout[-2000:]}")
            return 1
        if tables_slack <= 0 or bank3_slack <= 0:
            print(f"FAIL: capacity — bank2 slack {tables_slack}B, "
                  f"bank3 slack {bank3_slack}B")
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
              f"bank2 slack {tables_slack}B, bank3 slack {bank3_slack}B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
