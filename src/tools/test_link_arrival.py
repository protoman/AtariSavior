#!/usr/bin/env python3
"""Every room link, flown in the REAL ROM: the arrival is safe (no wall, no instant death).

User 2026-11-11: "this is FULL of bugs, look for them too". The earlier tests staged their
own data; this one takes every room-to-room crossing of the live stage (playbot.Level's cell
graph: an open edge cell on both sides), puts the player on the exit cell of the source room,
pushes through the exit with the joystick and then lets go for 20 frames with the laser held (a bat on the doorstep is shot, as a player does).
  * the room must change to the neighbour the map says (a one-way or mislinked exit fails),
  * the player must not land inside a playfield wall,
  * PlayerLives must not drop within those 20 frames on EVERY crossing of a link (a hazard on one
    arrival column is a choice, one on all of them is a trap).
Run: /home/iuri/python3/bin/python3 tools/test_link_arrival.py [LEVEL ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402

PUSH = {(1, 0): P.RIGHT, (-1, 0): P.LEFT, (0, 1): P.DOWN, (0, -1): P.UP}


def landing_mismatches(stage, numbers) -> list[str]:
    """Static LANDING check on the real playfield grids (user report 2026-11-17, level
    32: a 2-band side gap beside a 1-band one dropped the player inside a wall).
    The exit fires at the screen edge in ANY open band/column and never tests the
    neighbour, so for every link the open cells of the two edges must be IDENTICAL:
    side links (cell 0 mirrored = f 19 -> 0 east, 0 -> 19 west) in every band,
    vertical links (the player keeps his X) in every column, both directions.
    The graph walk below only flies crossings where BOTH sides are open, so a
    cell open on one side only was never exercised."""
    out = []
    for n in numbers:
        lv = P.Level(stage, n)
        for ri, room in enumerate(lv.rooms):
            for dx, fs, fd, name in ((1, 19, 0, "east"), (-1, 0, 19, "west")):
                nr = lv.at.get((room["room_x"] + dx, room["room_y"]))
                if nr is None:
                    continue
                a, b = lv.grids[ri][0], lv.grids[nr][0]
                sa = [i for i in range(len(a)) if a[i][fs]]
                sb = [i for i in range(len(b)) if b[i][fd]]
                if sa != sb:
                    out.append(f"level {n}: room {ri + 1} -> {name} room {nr + 1}: "
                               f"open bands {sa} vs {sb} (landing inside a wall)")
            nr = lv.at.get((room["room_x"], room["room_y"] + 1))
            if nr is not None and not room.get("bottom_band"):
                a, b = lv.grids[ri][0], lv.grids[nr][0]
                up = [c for c in range(20) if a[len(a) - 1][c]]
                dn = [c for c in range(20) if b[0][c]]
                if up != dn:
                    out.append(f"level {n}: room {ri + 1} above room {nr + 1}: floor "
                               f"columns {up} vs ceiling columns {dn} (landing inside a wall)")
    return out


def main() -> int:
    stage = json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]
    want_all = [int(a) for a in sys.argv[1:]] or range(1, len(stage["levels"]) + 1)
    problems = landing_mismatches(stage, want_all)
    if problems:
        print("FAIL: links whose two edges are not open in the same cells:")
        for p in problems[:20]:
            print("  " + p)
        return 1
    want = [int(a) for a in sys.argv[1:]] or range(1, len(stage["levels"]) + 1)
    bad, checked, lethal, safe = [], 0, {}, set()
    for n in want:
        lv = P.Level(stage, n)
        con = P.Console()
        con.boot(n)
        base = con.save()
        seen = set()
        for ri, room in enumerate(lv.rooms):
            air = lv.grids[ri][0]
            for b in range(len(air)):
                for f in range(20):
                    if not air[b][f]:
                        continue
                    for (nr, nb, nf), _c, _d in lv.neighbours((ri, b, f)):
                        if nr == ri or (ri, nr, b, f) in seen:
                            continue
                        seen.add((ri, nr, b, f))
                        d = (lv.rooms[nr]["room_x"] - room["room_x"],
                             lv.rooms[nr]["room_y"] - room["room_y"])
                        sw = PUSH.get(d)
                        if sw is None:
                            continue
                        con.restore(base)
                        con.w("PlayerLives", 8)
                        if ri:
                            con.w("LevelConnSpare", ri | 0x80)
                            for _ in range(4):
                                con.frame(P.NONE)
                        con.w("RoomX", P.x_for_cell(f))
                        con.w("RoomY", b * P.BAND_PX + 14)
                        moved = False
                        for _ in range(160):
                            con.frame(sw, True)
                            if con.r("RoomNo") != ri:
                                moved = True
                                break
                        tag = f"level {n} room {ri + 1} -> {nr + 1} (band {b + 1}, cell {f})"
                        checked += 1
                        if not moved:
                            continue          # something in the way: the graph is looser than the ROM
                        lives = con.r("PlayerLives")
                        for _ in range(3):
                            con.frame(P.NONE, True)
                        if con.r("RoomNo") != nr:
                            bad.append(f"{tag}: landed in room {con.r('RoomNo') + 1}")
                            continue
                        if con.r("PlayerLives") < lives:
                            lethal.setdefault((n, ri, nr), []).append(tag)
                            continue
                        x, y = con.pos()
                        if con.pf_wall(2 * P.cell_of(x), P.band_of(y)):
                            bad.append(f"{tag}: arrived inside a wall at x={x} y={y}")
                        for _ in range(20):
                            con.frame(P.NONE, True)
                        if con.r("PlayerLives") < lives:
                            lethal.setdefault((n, ri, nr), []).append(tag)
                        else:
                            safe.add((n, ri, nr))
    # a hazard on ONE arrival column is a choice (take another); a link whose every
    # crossing kills is a trap
    for key, tags in lethal.items():
        if key not in safe:
            bad.append(f"every crossing kills: {tags[0]} (+{len(tags) - 1} more)")
    if bad:
        print("FAIL:\n  " + "\n  ".join(bad))
        return 1
    print(f"test_link_arrival: OK ({checked} crossings flown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
