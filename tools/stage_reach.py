#!/usr/bin/env python3
"""Stage FINISHABILITY check - can the player reach the miner of every level?

User report 2026-10-25: "level 8 looks impossible to finish" (and 9, 15, 18 -
no route at all). The playfield is MIRRORED, so a room is two chambers (the
left half and its mirror) that only join where the centre seam is open across
a whole band. Exits keep the side: a westward move lands in the neighbour's
RIGHT chamber, an eastward one in its LEFT, and a vertical link keeps the
chamber. The per-room connectivity check only ever sees one half, so a level
whose rooms all wall the centre splits into parallel universes and the miner
is unreachable.

Model (kept in step with DataSerializer.cpp AnalyseReach - the generator runs
the same search and repairs a failing level; this is the independent guard):
  * 20-column full map, air = model cell 0 (hot/solid = wall); a 3-row model is
    padded with the open band 2 like convert_room.band_map();
  * a SOLID async patch (M1 left strip -> full col c, ball right strip ->
    full col 10+c) costs one bomb to cross; door/phase/crunch cells are gated
    at run time and count as passable;
  * vertical links need the same full column open on both sides, side links
    the same band (1 or 2) open on the edge column (0 <-> 19);
  * the drop-in is the START room, band 0, display col 8 (full col 4);
  * the water band counts as passable (channel rooms ferry on a raft);
  * a SPIDER (type 0) hangs at a fixed x and bobs 24 px down: every cell a
    colliding player can occupy (lit span [EX-13, EX+6] +-2 px, over the bands
    the bob sweeps) is a hazard the route must not need (user report
    2026-10-25: level 8 room 3, "the only way I can continue is dying by the
    enemy below the path"). Costed like a wall: a route through one is a
    failure.
Rule: a level must be finishable with at most ONE bomb and that bomb may only
be the START room's designed block (user rule 2026-10-21); every other route
must be open.

  stage_reach.py [stage.json]        report; exit 1 on any failing level
"""
import heapq
import json
import sys

SOLID_WALL = 1


DANGER = 1000


def enemy_x_px(col):
    c4 = int(round(col)) * 4
    return c4 + (4 if c4 < 11 else 7)


def _grid(model, room, sides=(True, True)):
    """sides = (west room exists, east room exists): the EDGE plug strip (left M1 at
    col 0, right ball at col 9) on a side with no room behind it cannot be bombed
    (bank1 gate, 2026-10-26), so it is a WALL. Interior strips stay bombable."""
    w, t = model["width"], list(model["tiles"])
    h = len(t) // w
    rows = list(range(h))
    if h == 3:                       # band_map: [r0, r1, AIR, r2]
        rows = [0, 1, -1, 2]
    air = [[rows[b] < 0 or t[rows[b] * w + (f if f < 10 else 19 - f)] == 0
            for f in range(20)] for b in range(len(rows))]
    bomb = set()
    for p in room.get("asym_patches") or []:
        if len(p) < 3 or p[2] != SOLID_WALL:
            continue
        band = p[0] + (1 if h == 3 and p[0] >= 2 else 0)
        side = p[3] if len(p) > 3 else 0
        col = p[1] if side == 1 else 10 + p[1]
        edge = p[1] == (0 if side == 1 else 9)    # the dead-side PLUG cell
        if edge and not sides[0 if side == 1 else 1]:
            air[band][col] = False               # unbreakable: left needs the west
            continue                             # room, right the east room
        bomb.add((band, col))
    danger = set()
    nb = len(rows)
    for e in room.get("enemies") or []:
        if e.get("type") != 0:
            continue
        ex = enemy_x_px(e["x"])
        top = int(round(e["y"] * 12))
        b0 = max(0, min(nb - 1, top // 36))
        b1 = max(0, min(nb - 1, (top + 24 + 14) // 36))
        for b in range(b0, b1 + 1):
            for f in range(max(0, (ex - 15) // 8), min(19, (ex + 8) // 8) + 1):
                danger.add((b, f))
    return air, bomb, danger


def analyse(level, models):
    """-> (bombs or None, [rooms whose patch the cheapest route crosses],
    [rooms whose spider zone it crosses])."""
    rooms = level["rooms"]
    at = {(r["room_x"], r["room_y"]): i for i, r in enumerate(rooms)}
    grids = [_grid(models[r["model_id"]], r,
                   ((r["room_x"] - 1, r["room_y"]) in at,
                    (r["room_x"] + 1, r["room_y"]) in at)) for r in rooms]
    s = min(max(level["start_room"], 0), len(rooms) - 1)
    goal = min(max(level["miner_room"], 0), len(rooms) - 1)
    sf = next((f for f in (4, 3, 5, 2, 6, 7, 8, 9) if grids[s][0][0][f]), 4)
    start = (s, 0, sf)
    best = {start: 0}
    parent = {}
    pq = [(0, start)]
    while pq:
        cost, node = heapq.heappop(pq)
        if best.get(node, 1 << 30) < cost:
            continue
        ri, b, f = node
        if ri == goal:
            crossed, hazard, cur = [], [], node
            while cur is not None:
                cr, cb, cf = cur
                if (cb, cf) in grids[cr][1]:
                    crossed.append(cr)
                if (cb, cf) in grids[cr][2]:
                    hazard.append(cr)
                cur = parent.get(cur)
            return cost % DANGER, crossed, hazard
        air = grids[ri][0]
        r = rooms[ri]
        outs = [(ri, b + 1, f), (ri, b - 1, f), (ri, b, f + 1), (ri, b, f - 1)]
        if b == len(air) - 1 and (r["room_x"], r["room_y"] + 1) in at:
            outs.append((at[(r["room_x"], r["room_y"] + 1)], 0, f))
        if b == 0 and (r["room_x"], r["room_y"] - 1) in at:
            o = at[(r["room_x"], r["room_y"] - 1)]
            outs.append((o, len(grids[o][0]) - 1, f))
        if b in (1, 2):
            if f == 19 and (r["room_x"] + 1, r["room_y"]) in at:
                outs.append((at[(r["room_x"] + 1, r["room_y"])], b, 0))
            if f == 0 and (r["room_x"] - 1, r["room_y"]) in at:
                outs.append((at[(r["room_x"] - 1, r["room_y"])], b, 19))
        for nr, nb, nf in outs:
            ga, gb, gd = grids[nr]
            if not (0 <= nb < len(ga) and 0 <= nf < 20 and ga[nb][nf]):
                continue
            c = (cost + (1 if (nb, nf) in gb else 0)
                 + (DANGER if (nb, nf) in gd else 0))
            nn = (nr, nb, nf)
            if best.get(nn, 1 << 30) > c:
                best[nn] = c
                parent[nn] = node
                heapq.heappush(pq, (c, nn))
    return None, [], []


# --- play-time model (power cells, 2026-10-26) --------------------------------
# The bar is 120 steps of 60 frames. Nothing here can play a level, so the model
# ESTIMATES: one full-map column = 8 px at 1 px/frame, one band ~30 frames, a
# human needs ~3x the ideal time plus ~4 s of look-around per room entered.
# Constants are kept in step with DataSerializer.cpp (kRoute*/kCell*): tune both.
ROUTE_HUMAN = 3
ROUTE_H = 8 * ROUTE_HUMAN
ROUTE_V = 30 * ROUTE_HUMAN
ROUTE_ROOM = 240
CELL_BUDGET = 90 * 60            # no stretch between refills may pass 90 s
BAR_FRAMES = 120 * 60
POWER_CELL = 14
EXTRA_MINER = 15


def extra_miner_nodes(level, models):
    """-> [(room, band, full col)] stand cells of the EXTRA miners (record type
    15): they stand on the floor band's top like the level's own miner."""
    out = []
    for i, r in enumerate(level["rooms"]):
        m = models[r["model_id"]]
        bands = len(m["tiles"]) // m["width"]
        bands = 4 if bands == 3 else bands
        for e in r.get("enemies") or []:
            if e.get("type") == EXTRA_MINER:
                vis = int(round(e["x"])) * 4          # visible left edge (px)
                band = min(bands - 1, int(round(e["y"] * 12)) // 36)
                out.append((i, band, min(19, (vis + 3) // 8)))
    return out


def reach_cells(level, models):
    """Every (room, band, col) reachable without a bomb or a spider zone."""
    rooms = level["rooms"]
    at = {(r["room_x"], r["room_y"]): i for i, r in enumerate(rooms)}
    grids = [_grid(models[r["model_id"]], r,
                   ((r["room_x"] - 1, r["room_y"]) in at,
                    (r["room_x"] + 1, r["room_y"]) in at)) for r in rooms]
    s = min(max(level["start_room"], 0), len(rooms) - 1)
    sf = next((f for f in (4, 3, 5, 2, 6, 7, 8, 9) if grids[s][0][0][f]), 4)
    seen = {(s, 0, sf)}
    stack = [(s, 0, sf)]
    while stack:
        ri, b, f = stack.pop()
        air = grids[ri][0]
        r = rooms[ri]
        outs = [(ri, b + 1, f), (ri, b - 1, f), (ri, b, f + 1), (ri, b, f - 1)]
        if b == len(air) - 1 and (r["room_x"], r["room_y"] + 1) in at:
            outs.append((at[(r["room_x"], r["room_y"] + 1)], 0, f))
        if b == 0 and (r["room_x"], r["room_y"] - 1) in at:
            o = at[(r["room_x"], r["room_y"] - 1)]
            outs.append((o, len(grids[o][0]) - 1, f))
        if b in (1, 2):
            if f == 19 and (r["room_x"] + 1, r["room_y"]) in at:
                outs.append((at[(r["room_x"] + 1, r["room_y"])], b, 0))
            if f == 0 and (r["room_x"] - 1, r["room_y"]) in at:
                outs.append((at[(r["room_x"] - 1, r["room_y"])], b, 19))
        for nr, nb, nf in outs:
            ga, gb, gd = grids[nr]
            if not (0 <= nb < len(ga) and 0 <= nf < 20 and ga[nb][nf]):
                continue
            if (nb, nf) in gb or (nb, nf) in gd or (nr, nb, nf) in seen:
                continue
            seen.add((nr, nb, nf))
            stack.append((nr, nb, nf))
    return seen


def route_segments(level, models):
    """-> (total_estimate, longest_stretch) in frames, or None when the level
    cannot be finished. The route must visit EVERY extra miner and then reach the
    level's own miner; it is the cheapest in ESTIMATED TIME where a power cell
    the route steps on resets the 'since last refill' clock (a cell is always
    worth taking). longest_stretch is the worst gap between refills on the best
    route; the generator guarantees longest_stretch <= CELL_BUDGET."""
    rooms = level["rooms"]
    at = {(r["room_x"], r["room_y"]): i for i, r in enumerate(rooms)}
    grids = [_grid(models[r["model_id"]], r,
                   ((r["room_x"] - 1, r["room_y"]) in at,
                    (r["room_x"] + 1, r["room_y"]) in at)) for r in rooms]
    cells = {}
    for i, r in enumerate(rooms):
        h = len(grids[i][0])
        for e in r.get("enemies") or []:
            if e.get("type") == POWER_CELL:
                f = int(round(e["x"])) // 2
                u = 12 // max(1, len(models[r["model_id"]]["tiles"])
                              // models[r["model_id"]]["width"])
                b = min(h - 1, int(e["y"]) // max(1, u))
                cells[(i, b, f)] = True
    extras = {n: k for k, n in enumerate(extra_miner_nodes(level, models))}
    full = (1 << len(extras)) - 1
    s = min(max(level["start_room"], 0), len(rooms) - 1)
    goal = min(max(level["miner_room"], 0), len(rooms) - 1)
    sf = next((f for f in (4, 3, 5, 2, 6, 7, 8, 9) if grids[s][0][0][f]), 4)
    # label-correcting search on (node, miners taken) -> (stretch, total): a
    # refill makes the stretch 0, so costs are not monotone along a path;
    # minimise the stretch first (it is what the timer cares about), then the
    # total.
    start = (s, 0, sf, 0)
    best = {start: (0, 0)}
    stack = [start]
    while stack:
        node = stack.pop()
        stretch, total = best[node]
        ri, b, f, got = node
        air = grids[ri][0]
        r = rooms[ri]
        outs = [(ri, b + 1, f, ROUTE_V), (ri, b - 1, f, ROUTE_V),
                (ri, b, f + 1, ROUTE_H), (ri, b, f - 1, ROUTE_H)]
        if b == len(air) - 1 and (r["room_x"], r["room_y"] + 1) in at:
            outs.append((at[(r["room_x"], r["room_y"] + 1)], 0, f, ROUTE_ROOM))
        if b == 0 and (r["room_x"], r["room_y"] - 1) in at:
            o = at[(r["room_x"], r["room_y"] - 1)]
            outs.append((o, len(grids[o][0]) - 1, f, ROUTE_ROOM))
        if b in (1, 2):
            if f == 19 and (r["room_x"] + 1, r["room_y"]) in at:
                outs.append((at[(r["room_x"] + 1, r["room_y"])], b, 0, ROUTE_ROOM))
            if f == 0 and (r["room_x"] - 1, r["room_y"]) in at:
                outs.append((at[(r["room_x"] - 1, r["room_y"])], b, 19, ROUTE_ROOM))
        for nr, nb, nf, w in outs:
            ga, gb, gd = grids[nr]
            if not (0 <= nb < len(ga) and 0 <= nf < 20 and ga[nb][nf]):
                continue
            if (nb, nf) in gd:
                continue
            w += 600 if (nb, nf) in gb else 0
            ns, nt = stretch + w, total + w
            if (nr, nb, nf) in cells:
                ns = 0
            ng = got | (1 << extras[(nr, nb, nf)] if (nr, nb, nf) in extras else 0)
            nn = (nr, nb, nf, ng)
            if nn not in best or (ns, nt) < best[nn]:
                best[nn] = (ns, nt)
                stack.append(nn)
    reached = [v for k, v in best.items() if k[0] == goal and k[3] == full]
    if not reached:
        return None
    return min(reached)[1], min(reached)[0]


def problems(stage):
    """stage = the parsed JSON's ['stage'] dict -> list of failure strings."""
    models = {m["id"]: m for m in stage["models"]}
    out = []
    for n_, lv in enumerate(stage["levels"], start=1):
        n = n_
        bombs, crossed, hazard = analyse(lv, models)
        if bombs is None:
            out.append(f"level {n}: the miner is unreachable")
        elif hazard:
            where = sorted({lv["rooms"][c]["room_id"] + 1 for c in hazard})
            out.append(f"level {n}: the only route passes a spider's column "
                       f"in room(s) {where}")
        elif bombs > 1 or any(c != 0 for c in crossed):
            where = sorted({lv["rooms"][c]["room_id"] + 1 for c in crossed})
            out.append(f"level {n}: the only route crosses {bombs} async "
                       f"block(s) in room(s) {where} (only the start room's "
                       "designed block may be on the route)")
        else:
            reach = reach_cells(lv, models)
            lost = [n for n in extra_miner_nodes(lv, models) if n not in reach]
            if lost:
                where = sorted({lv["rooms"][n[0]]["room_id"] + 1 for n in lost})
                out.append(f"level {n_}: extra miner(s) in room(s) {where} cannot "
                           "be reached without a bomb or a spider zone")
                continue
            seg = route_segments(lv, models)
            if seg is None:
                out.append(f"level {n}: no route visits every miner")
            elif seg[1] > CELL_BUDGET:
                out.append(f"level {n}: an estimated {seg[1] / 60:.0f} s "
                           f"between timer refills (budget "
                           f"{CELL_BUDGET // 60} s of the {BAR_FRAMES // 60} s "
                           "bar) - the route needs a power cell")
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "rooms/stage.json"
    bad = problems(json.load(open(path))["stage"])
    for b in bad:
        print("stage_reach: " + b)
    print(f"stage_reach: {'FAIL' if bad else 'OK'} ({path})")
    sys.exit(1 if bad else 0)
