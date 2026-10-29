#!/usr/bin/env python3
"""Playthrough bot: plays the GENERATED stage through the real ROM (py65).

Boots the live ROM (bank*.bin + bank0.lst, built from rooms/stage.json), picks a
level on the title with SELECT, starts it with RESET and then plays it with the
JOYSTICK ONLY - no RAM pinning of the player, no hand-made room loads - until the
level tally starts (every miner rescued) or the bot gives up. It is the
engine-level counterpart of tools/stage_reach.py (which only proves that a route
EXISTS in a model): it checks that the route can really be flown.

How it plays
  * The route comes from stage_reach's cell graph (room, band, 8-px cell): the
    same graph the generator uses, with the exits, the miners and the bomb strips.
  * A closed-loop controller flies it from the real position in RAM (RoomX/RoomY):
    centre on a cell, climb/fall through shafts, hold altitude in a band, leave
    by an edge. The laser is held down the whole time.
  * Lives are topped up every frame by default (--mortal turns that off), so a
    death costs the time of a respawn but never restarts the run; deaths are
    counted and reported as hazard exposure.

  playbot.py [LEVEL ...] [--mortal] [--frames N] [-v]
      LEVEL = 1-based level numbers (default: all 20)

Exit status 1 when any selected level was not finished.
"""
import argparse
import heapq
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import parse_labels  # noqa: E402
import stage_reach as SR  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

UP, DOWN, LEFT, RIGHT, NONE = 0xEF, 0xDF, 0xBF, 0x7F, 0xFF   # SWCHA, active low
NAMES = ("RoomX", "RoomY", "RoomNo", "DropTarget", "Level", "PlayerLives",
         "Hover", "BombPacked", "EnemyCount", "EnemyDeadMask", "LevelMinerRoom",
         "MinerX", "MinerY", "LevelStartRoom", "BarLevel", "PlayerBombs",
         "StartFrame", "PF0Buf", "PF1Buf", "PF2Buf", "vyHi", "RoomRectsLo",
         "RoomRectsHi", "RoomPF0Lo", "RoomPF0Hi", "LevelConnSpare", "LevelPFDataLo",
         "LevelPFDataHi", "LevelRoomN")
BANDS = 4
BAND_PX = 36
PLAYER_H = 22


# ---------------------------------------------------------------------------
# the console
# ---------------------------------------------------------------------------
class Console:
    def __init__(self):
        self.banks = [bytearray((ROOT / f"bank{i}.bin").read_bytes()) for i in range(8)]
        lab = parse_labels(ROOT / "bank0.lst", set(NAMES))
        missing = set(NAMES) - set(lab)
        if missing:
            sys.exit(f"bank0.lst is missing labels {sorted(missing)}")
        self.lab = lab
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = NONE
        self.swchb = 0xFF
        self.inpt4 = 0x80
        self.mpu = MPU(memory=self)
        self.pc_frame = lab["StartFrame"]
        self.frames = 0

    # bus (the same minimal model every sim in tools/ uses)
    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.banks[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            return 0
        if a == 0x000C:
            return self.inpt4
        if 0x1FF4 <= a <= 0x1FFB:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF4 <= a <= 0x1FFB:
            self.bank = a - 0x1FF4
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            self.tia[a & 0x3F] = v

    def frame(self, swcha=NONE, fire=False):
        self.swcha = swcha
        self.inpt4 = 0x00 if fire else 0x80
        self.mpu.step()
        while not (self.bank == 0 and self.mpu.pc == self.pc_frame):
            self.mpu.step()
        self.frames += 1

    def r(self, name):
        return self.ram[self.lab[name] & 0x7F]

    def w(self, name, v):
        self.ram[self.lab[name] & 0x7F] = v & 0xFF

    # ---- the title: pick a level, start it ---------------------------------
    def boot(self, level):
        self.frame()
        for _ in range(3):
            self.frame()
        self.w("Level", (level - 2) % 20)      # one SELECT edge = Level + 1
        self.swchb = 0xFD
        self.frame()
        self.swchb = 0xFF
        for _ in range(4):
            self.frame()
        assert self.r("Level") == level - 1, f"title Level {self.r('Level')}"
        self.swchb = 0xFE
        self.frame()
        self.swchb = 0xFF
        for _ in range(500):
            self.frame()
            if self.r("DropTarget") == 0:
                return
        raise RuntimeError("the drop-in never landed")

    # ---- the world as the ROM sees it --------------------------------------
    def pos(self):
        return self.r("RoomX"), self.r("RoomY")

    def pf_wall(self, col40, band):
        """Is playfield column 0..39 solid in this band right now (live PF RAM)?"""
        c = col40 if col40 < 20 else 39 - col40
        if c < 4:
            v = self.ram[(self.lab["PF0Buf"] & 0x7F) + band]
            return bool(v & (0x10 << c))
        if c < 12:
            v = self.ram[(self.lab["PF1Buf"] & 0x7F) + band]
            return bool(v & (0x80 >> (c - 4)))
        v = self.ram[(self.lab["PF2Buf"] & 0x7F) + band]
        return bool(v & (1 << (c - 12)))


def vl_of(x):
    """Visible left edge of the player's 8-px sprite for RoomX (PlayerHitsMap)."""
    return x - 7 if x >= 15 else x - 4


def x_for_cell(f):
    """RoomX that puts the 8-px sprite exactly on 8-px cell f (0..19)."""
    return 4 if f == 0 else 8 * f + 7


def cell_of(x):
    return min(19, max(0, (vl_of(x) + 4) // 8))


def band_of(y):
    return min(BANDS - 1, max(0, (y + PLAYER_H // 2) // BAND_PX))


# ---------------------------------------------------------------------------
# the route
# ---------------------------------------------------------------------------
class Level:
    def __init__(self, stage, number):
        self.n = number
        self.level = stage["levels"][number - 1]
        self.models = {m["id"]: m for m in stage["models"]}
        rooms = self.level["rooms"]
        self.rooms = rooms
        self.at = {(r["room_x"], r["room_y"]): i for i, r in enumerate(rooms)}
        self.grids, self.dead = SR.level_grids(self.level, self.models, self.at)
        mx = int(self.level["miner_x"])
        self.miner = (self.level["miner_room"],
                      min(BANDS - 1, int(self.level["miner_y"] * 12) // BAND_PX),
                      min(19, mx * 1))
        self.extras = SR.extra_miner_nodes(self.level, self.models)
        # a blown strip is only open for the visit: EnterRoom closes it again
        self.orig_bombs = [set(g[1]) for g in self.grids]

    def neighbours(self, node):
        ri, b, f = node
        r = self.rooms[ri]
        air = self.grids[ri][0]
        outs = [(ri, b + 1, f), (ri, b - 1, f), (ri, b, f + 1), (ri, b, f - 1)]
        if b == len(air) - 1 and (r["room_x"], r["room_y"] + 1) in self.at:
            outs.append((self.at[(r["room_x"], r["room_y"] + 1)], 0, f))
        if b == 0 and (r["room_x"], r["room_y"] - 1) in self.at:
            o = self.at[(r["room_x"], r["room_y"] - 1)]
            outs.append((o, len(self.grids[o][0]) - 1, f))
        if b in (1, 2):
            if f == 19 and (r["room_x"] + 1, r["room_y"]) in self.at:
                outs.append((self.at[(r["room_x"] + 1, r["room_y"])], b, 0))
            if f == 0 and (r["room_x"] - 1, r["room_y"]) in self.at:
                outs.append((self.at[(r["room_x"] - 1, r["room_y"])], b, 19))
        for nr, nb, nf in outs:
            ga, gb, gd = self.grids[nr]
            if 0 <= nb < len(ga) and 0 <= nf < 20 and ga[nb][nf]:
                strip = (nb, nf) in gb
                if strip:
                    # a strip is bombed from its CENTRE side, so it can only be
                    # crossed outward: a left-half strip westward, a right-half
                    # one eastward (stage_reach: "bombable only from the centre")
                    out_dx = -1 if nf < 10 else 1
                    if not (nr == ri and nb == b and nf - f == out_dx):
                        continue
                yield (nr, nb, nf), (1 if strip else 0), \
                    (SR.DANGER if (nb, nf) in gd else 0)

    def route(self, start, goal):
        """Cheapest cell path start -> goal (a bomb strip or a spider zone costs
        extra, so the plain route wins when there is one). None = no route."""
        best = {start: 0}
        parent = {}
        pq = [(0, start)]
        while pq:
            cost, node = heapq.heappop(pq)
            if best.get(node, 1 << 30) < cost:
                continue
            if node == goal:
                path = [node]
                while node in parent:
                    node = parent[node]
                    path.append(node)
                return path[::-1]
            for nn, bomb, danger in self.neighbours(node):
                c = cost + 1 + 40 * bomb + danger
                if best.get(nn, 1 << 30) > c:
                    best[nn] = c
                    parent[nn] = node
                    heapq.heappush(pq, (c, nn))
        return None


# ---------------------------------------------------------------------------
# the pilot
# ---------------------------------------------------------------------------
class GiveUp(Exception):
    pass


class Done(Exception):
    """The level tally started: every miner is rescued."""


class Pilot:
    def __init__(self, con, lv, mortal=False, verbose=False):
        self.c = con
        self.lv = lv
        self.mortal = mortal
        self.verbose = verbose
        self.deaths = 0
        self.rooms_seen = set()
        self.last_room = None
        self.log = []

    # ---- one frame ---------------------------------------------------------
    def step(self, sw=NONE):
        c = self.c
        lives = c.r("PlayerLives")
        c.frame(sw, fire=True)
        if c.r("PlayerLives") < lives or (c.r("Hover") and not self.hover):
            self.deaths += 1
        self.hover = bool(c.r("Hover"))
        if not self.mortal:
            c.w("PlayerLives", 8)
        rn = c.r("RoomNo")
        if rn != self.last_room:
            self.last_room = rn
            self.bombs_tried = {}
            self.lv.grids[rn][1].clear()
            self.lv.grids[rn][1].update(self.lv.orig_bombs[rn])
        self.rooms_seen.add(rn)
        if c.r("DropTarget") == 0xFE:
            raise Done()
        if c.frames - self.start_frames > self.budget:
            raise GiveUp(f"out of time at room {c.r('RoomNo')} "
                         f"x={c.r('RoomX')} y={c.r('RoomY')}")

    def say(self, *a):
        if self.verbose:
            print("   ", *a)

    # ---- low-level moves ---------------------------------------------------
    def hold(self, sw, frames):
        for _ in range(frames):
            self.step(sw)

    def clear_hover(self):
        """After a death the respawn hover waits for the first input (bugs.md #1)."""
        for _ in range(60):
            if not self.c.r("Hover"):
                return
            self.step(UP)

    def altitude(self, band):
        """Joystick bits that keep the player inside `band` (gravity is weak: a
        short thrust whenever he sinks below the middle of the band)."""
        y = self.c.r("RoomY")
        return UP if y > BAND_PX * band + 12 else NONE

    def to_x(self, x_t, band, maxf=400):
        """Walk along `band` until RoomX == x_t exactly."""
        for _ in range(maxf):
            x = self.c.r("RoomX")
            if x == x_t:
                return True
            sw = (RIGHT if x < x_t else LEFT) & self.altitude(band)
            self.step(sw)
        return False

    # ---- the plan, edge by edge -------------------------------------------
    def fly(self, path):
        c = self.c
        i = 0
        stuck = 0
        while i < len(path) - 1:
            cur, nxt = path[i], path[i + 1]
            room_before = c.r("RoomNo")
            if room_before != cur[0]:
                # the ROM put us somewhere else (death respawn into another room,
                # an exit taken early): re-sync on the path if we are on it
                if room_before == nxt[0]:
                    i += 1
                    continue
                raise GiveUp(f"left the route: in room {room_before}, expected "
                             f"{cur[0]}/{nxt[0]}")
            if cur[0] == nxt[0] and (nxt[1], nxt[2]) in self.lv.grids[nxt[0]][1]:
                self.bomb_strip(nxt)
                continue                          # re-check the same edge, strip gone
            ok = self.edge(cur, nxt)
            self.say(f"edge {cur}->{nxt} ok={ok} now room {c.r('RoomNo')} "
                     f"x={c.r('RoomX')} y={c.r('RoomY')}")
            if c.r("RoomNo") == nxt[0] and not ok:
                ok = True
            if ok:
                i += 1
                stuck = 0
            else:
                stuck += 1
                self.say(f"stuck on {cur}->{nxt} at x={c.r('RoomX')} y={c.r('RoomY')}")
                if stuck >= 3:
                    raise GiveUp(f"cannot fly {cur}->{nxt} "
                                 f"(x={c.r('RoomX')} y={c.r('RoomY')})")
                self.hold(NONE, 20)
            self.clear_hover()

    def here(self):
        c = self.c
        return (c.r("RoomNo"), band_of(c.r("RoomY")), cell_of(c.r("RoomX")))

    def land(self):
        """Fall (no input) until BombPacked b7 (on the ground) is set."""
        c = self.c
        for _ in range(400):
            if c.r("BombPacked") & 0x80:
                return True
            self.step(NONE)
        return False

    def bomb_strip(self, strip):
        """Open a one-cell async strip with a bomb: stand on the floor 1-2 cells on
        the CENTRE side of it (left-half strips are bombed from the east, right-half
        ones from the west - the blast window is centred 7 px left of the player),
        plant, retreat three cells and wait out the fuse."""
        c = self.c
        ri, b, col = strip
        side = 1 if col < 10 else -1
        air = self.lv.grids[ri][0]
        stand = None
        for d in (1, 2):
            f = col + side * d
            if 0 <= f < 20 and air[b][f] and (b + 1 >= len(air) or not air[b + 1][f]):
                stand = (ri, b, f)
                break
        if stand is None:
            raise GiveUp(f"no floor to bomb the strip {strip} from")
        if getattr(self, "bombs_tried", {}).get(strip, 0) >= 2:
            raise GiveUp(f"the strip {strip} survived two bombs")
        self.bombs_tried = getattr(self, "bombs_tried", {})
        self.bombs_tried[strip] = self.bombs_tried.get(strip, 0) + 1
        if self.here() != stand:
            path = self.lv.route(self.here(), stand)
            if path is None:
                raise GiveUp(f"cannot reach {stand} to bomb {strip} from "
                             f"{self.here()}")
            self.say("walk to the bomb spot", stand, "path", path[:3], "...")
            self.fly(path)
        f = stand[2]
        if not self.to_x(x_for_cell(f), b):
            raise GiveUp("cannot align at the bomb spot")
        if not self.land():
            raise GiveUp("cannot stand on the floor to plant a bomb")
        self.hold(DOWN, 4)                       # plant (edge on the floor)
        away = max(0, min(19, f + side * 3))
        self.say("bomb planted at", c.pos(), "retreat to cell", away)
        self.to_x(x_for_cell(away), b)
        self.land()
        self.hold(NONE, 230)                     # ~3 s fuse + the flash
        self.lv.grids[ri][1].discard((b, col))
        self.say("strip", strip, "should be open")

    def edge(self, cur, nxt):
        """Fly one graph edge. True when the player is where `nxt` says."""
        c = self.c
        (r0, b0, f0), (r1, b1, f1) = cur, nxt
        if r0 != r1:
            return self.exit_room(cur, nxt)
        if b0 == b1:                       # along the band
            return self.to_x(x_for_cell(f1), b0)
        # through a shaft: centre first, then climb / fall
        if not self.to_x(x_for_cell(f0), b0):
            return False
        top = BAND_PX * b1 + 4
        for _ in range(200):
            y = c.r("RoomY")
            if band_of(y) == b1 and (b1 < b0 and y <= BAND_PX * b1 + 14 or b1 > b0):
                if b1 > b0 and y >= BAND_PX * b1 + 2 or b1 < b0:
                    return True
            sw = UP if b1 < b0 else NONE
            if c.r("RoomX") != x_for_cell(f0):
                sw &= RIGHT if c.r("RoomX") < x_for_cell(f0) else LEFT
            self.step(sw)
        return False

    def exit_room(self, cur, nxt):
        c = self.c
        (r0, b0, f0), (r1, b1, f1) = cur, nxt
        a, b = self.lv.rooms[r0], self.lv.rooms[r1]
        dx, dy = b["room_x"] - a["room_x"], b["room_y"] - a["room_y"]
        if dy:                                  # vertical exit: centre, then go
            if not self.to_x(x_for_cell(f0), b0):
                return False
        for _ in range(300):
            if c.r("RoomNo") == r1:
                return True
            if dy < 0:
                sw = UP
            elif dy > 0:
                sw = NONE
            else:
                sw = (RIGHT if dx > 0 else LEFT) & self.altitude(b0)
            if dy:
                x_t = x_for_cell(f0)
                if c.r("RoomX") != x_t:
                    sw &= RIGHT if c.r("RoomX") < x_t else LEFT
            self.step(sw)
        return c.r("RoomNo") == r1

    # ---- a whole level -----------------------------------------------------
    def play(self, budget=7200):
        c = self.c
        self.start_frames = c.frames
        self.budget = budget
        self.hover = False
        targets = [self.lv.miner] + list(self.lv.extras)
        for tgt in targets:
            while True:
                if c.r("DropTarget") == 0xFE:        # the tally started
                    break
                here = (c.r("RoomNo"), band_of(c.r("RoomY")), cell_of(c.r("RoomX")))
                if here == tgt:
                    break
                path = self.lv.route(here, tgt)
                if path is None:
                    raise GiveUp(f"no route {here} -> {tgt}")
                self.say("route", len(path), "cells", here, "->", tgt)
                self.fly(path)
            self.touch(tgt)
        return True

    def touch(self, tgt, px=None):
        """Walk into the miner standing in cell `tgt` of the current room: the
        pickup fires when RoomX - MinerX is in [-6, +3] and the boxes overlap in Y."""
        c = self.c
        room, band, _cell = tgt
        for _ in range(300):
            if c.r("DropTarget") == 0xFE:
                return
            if c.r("RoomNo") != room:
                raise GiveUp(f"left the miner's room {room}")
            mx = px if px is not None else c.r("MinerX")
            x = c.r("RoomX")
            sw = NONE
            if x - mx < -5:
                sw = RIGHT
            elif x - mx > 2:
                sw = LEFT
            else:
                # in range: if it did not fire we are not low enough yet
                sw = NONE
            self.step(sw & self.altitude(band) if sw != NONE else self.altitude(band) if False else sw)
        # a non-final miner is just collected (the level goes on): no tally yet
        return


def finish(con, lv, mortal, verbose, budget):
    pilot = Pilot(con, lv, mortal, verbose)
    try:
        pilot.play(budget)
        ok, why = False, "the route ended without a tally"
    except Done:
        ok, why = True, "tally started"
    except GiveUp as e:
        ok, why = False, str(e)
    return ok, why, pilot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--mortal", action="store_true")
    ap.add_argument("--frames", type=int, default=7200)
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    stage = json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]
    levels = a.levels or list(range(1, len(stage["levels"]) + 1))
    bad = 0
    for n in levels:
        con = Console()
        con.boot(n)
        lv = Level(stage, n)
        t0 = con.frames
        ok, why, pilot = finish(con, lv, a.mortal, a.v, a.frames)
        used = con.frames - t0
        print(f"level {n:2d}: {'DONE' if ok else 'FAIL'}  {used:5d} frames  "
              f"deaths {pilot.deaths}  rooms {len(pilot.rooms_seen)}/{len(lv.rooms)}"
              f"  - {why}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
