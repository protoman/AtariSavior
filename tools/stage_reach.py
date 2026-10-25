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


def _grid(model, room):
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
        bomb.add((band, p[1] if side == 1 else 10 + p[1]))
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
    grids = [_grid(models[r["model_id"]], r) for r in rooms]
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


def problems(stage):
    """stage = the parsed JSON's ['stage'] dict -> list of failure strings."""
    models = {m["id"]: m for m in stage["models"]}
    out = []
    for n, lv in enumerate(stage["levels"], start=1):
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
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "rooms/stage.json"
    bad = problems(json.load(open(path))["stage"])
    for b in bad:
        print("stage_reach: " + b)
    print(f"stage_reach: {'FAIL' if bad else 'OK'} ({path})")
    sys.exit(1 if bad else 0)
