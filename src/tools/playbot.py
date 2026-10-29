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
import collections
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
         "LevelPFDataHi", "LevelRoomN", "EnemyRamX", "EnemyRamY", "EnemyRamD")
BANDS = 4
BAND_PX = 36
PLAYER_H = 22


# ---------------------------------------------------------------------------
# the console
# ---------------------------------------------------------------------------
class Console:
    def __init__(self, rom_dir=None):
        """rom_dir: where bank*.bin / bank0.lst are (default: the live build here; the
        PAL / PAL60 variants are built in a scratch tree, see tools/build_variant.sh)."""
        rom_dir = Path(rom_dir) if rom_dir else ROOT
        self.banks = [bytearray((rom_dir / f"bank{i}.bin").read_bytes()) for i in range(8)]
        lab = parse_labels(rom_dir / "bank0.lst", set(NAMES))
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

    def save(self):
        m = self.mpu
        return (bytes(self.ram), bytes(self.tia), self.bank, self.swcha, self.swchb,
                self.inpt4, self.frames,
                (m.a, m.x, m.y, m.sp, m.pc, m.p, m.processorCycles))

    def restore(self, snap):
        ram, tia, self.bank, self.swcha, self.swchb, self.inpt4, self.frames, regs = snap
        self.ram[:] = ram
        self.tia[:] = tia
        m = self.mpu
        m.a, m.x, m.y, m.sp, m.pc, m.p, m.processorCycles = regs

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
        # raft rooms: the water row can only be entered by dropping onto the raft,
        # which waits at its spawn cell (x column / 2) until somebody stands on it
        self.raft_cell = {}
        for i, r in enumerate(rooms):
            for e in r.get("enemies") or []:
                if e.get("type") == SR.RAFT_ENTITY if hasattr(SR, "RAFT_ENTITY") \
                        else e.get("type") == 7:
                    self.raft_cell[i] = int(round(e["x"])) // 2
        # a blown strip is only open for the visit: EnterRoom closes it again
        self.orig_bombs = [set(g[1]) for g in self.grids]

    def neighbours(self, node):
        ri, b, f = node
        r = self.rooms[ri]
        air = self.grids[ri][0]
        outs = [(ri, b + 1, f), (ri, b - 1, f), (ri, b, f + 1), (ri, b, f - 1)]
        # a water room has no way out through the floor: the water row is no floor
        # (the player hovers 103 px high over it) and it kills before any exit
        if b == len(air) - 1 and (r["room_x"], r["room_y"] + 1) in self.at \
                and not r.get("bottom_band"):
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
                if nr == ri and nr in self.raft_cell and nb == BANDS - 1 \
                        and b == BANDS - 2 and nf != self.raft_cell[nr]:
                    continue              # the water row: only onto the raft
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
                self.last_cost = cost
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
        self.death_log = []
        self.safe = False
        self.trace = collections.deque(maxlen=48)   # last frames, dumped on a death
        self.doing = "start"
        self.log_path = None
        self.level_no = 0
        self.hi_override = None
        self.forced = []
        self.waited = 0
        self.log = []

    def killer(self, pre):
        """(room 1-based, x, y, cause) of the frame before a life was lost."""
        rn, x, y, slots = pre
        room = self.lv.rooms[rn]
        causes = []
        recs = [e for e in room.get("enemies") or []]
        names = {0: "spider", 1: "bat", 2: "snake", 3: "tentacle", 4: "moth", 7: "raft"}
        for i, (ex, ey) in enumerate(slots):
            if i < len(recs) and abs(x - ex) <= 14 and -18 <= ey - y <= 22:
                causes.append(names.get(recs[i]["type"], f"enemy{recs[i]['type']}"))
        b = band_of(y)
        feats = {c[2] for c in (room.get("feature_cells") or [])}
        model = self.lv.models[room["model_id"]]
        if not causes:
            if room.get("bottom_band") and y >= 112:
                causes.append("water")
            elif 10 in feats and b == 1:
                causes.append("phase wall")
            elif 12 in feats:
                causes.append("crusher")
            elif model.get("mid_band_type") and b == 1:
                causes.append("hot rock")
            else:
                causes.append("?")
        return rn + 1, x, y, "/".join(causes)

    # ---- one frame ---------------------------------------------------------
    def snapshot_state(self, sw):
        """One trace row: everything that can explain a death, as the ROM sees it."""
        c = self.c
        room = self.lv.rooms[c.r("RoomNo")]
        recs = room.get("enemies") or []
        en = []
        for i in range(min(3, c.r("EnemyCount"))):
            t = recs[i]["type"] if i < len(recs) else -1
            en.append((t, c.ram[(c.lab["EnemyRamX"] & 0x7F) + i],
                       c.ram[(c.lab["EnemyRamY"] & 0x7F) + i]))
        return {"f": c.frames, "room": c.r("RoomNo") + 1, "x": c.r("RoomX"),
                "y": c.r("RoomY"), "vy": c.r("vyHi"), "sw": sw & 0xFF,
                "hover": c.r("Hover"), "clock": c.ram[0xC2 & 0x7F],
                "dm": c.ram[0xBA & 0x7F], "enemies": en, "doing": self.doing}

    def explain(self, rows):
        """Facts about the last frame before a life was lost, and the cause they point
        to. rows[-1] is the frame the player was alive in."""
        r = rows[-1]
        room = self.lv.rooms[r["room"] - 1]
        x, y = r["x"], r["y"]
        facts, causes = [], []
        names = {0: "spider", 1: "bat", 2: "snake", 3: "tentacle", 4: "moth",
                 7: "raft", 15: "miner"}
        for t, ex, ey in r["enemies"]:
            dx, dy = ex - x, ey - y
            if abs(dx) <= 14 and -18 <= dy <= 22:
                causes.append(names.get(t, f"enemy{t}"))
            if abs(dx) <= 40 and abs(dy) <= 40:
                facts.append(f"{names.get(t, t)} at dx={dx:+d} dy={dy:+d}")
        crow = self.crunch_band(room)
        if crow is not None:
            n = self.crunch_pairs(r["clock"])
            top, bot = 36 * crow, 36 * crow + 36
            facts.append(f"hcrunch row band {crow}, clock {r['clock']}, covers pairs 1..{n} "
                         f"(x<{8 * n + 8} and x>{159 - 8 * n - 8})")
            if y + 22 > top and y < bot and any(
                    8 * p < x + 4 and 8 * p + 8 > x - 10 or
                    8 * (19 - p) < x + 4 and 8 * (19 - p) + 8 > x - 10
                    for p in range(1, n + 1)):
                causes.append("crusher")
        feats = {fc[2]: fc for fc in room.get("feature_cells") or []}
        if 10 in feats:
            on = bool(r["dm"] & 0x20) and not r["dm"] & 0x40
            facts.append(f"phase wall cell {feats[10][1]}: {'ON' if on else 'off'} "
                         f"(clock {r['clock'] % 90}/90)")
            col = feats[10][1]
            if on and any(8 * cell - 12 <= x <= 8 * cell + 16 for cell in (col, 19 - col)) \
                    and band_of(y) == feats[10][0]:
                causes.append("phase wall")
        model = self.lv.models[room["model_id"]]
        if model.get("mid_band_type") and band_of(y) == 1:
            facts.append("hot band (row 1)")
            if not causes:
                causes.append("hot rock?")
        if room.get("bottom_band") and y >= 112:
            causes.append("water")
        if not causes:
            causes.append("?")
        return "/".join(causes), facts

    def step(self, sw=NONE):
        c = self.c
        lives = c.r("PlayerLives")
        pre = (c.r("RoomNo"), c.r("RoomX"), c.r("RoomY"),
               [(c.ram[(c.lab["EnemyRamX"] & 0x7F) + i], c.ram[(c.lab["EnemyRamY"] & 0x7F) + i])
                for i in range(min(3, c.r("EnemyCount")))])
        self.trace.append(self.snapshot_state(sw))
        c.frame(sw, fire=True)
        if c.r("PlayerLives") < lives:
            self.deaths += 1
            rn, x_, y_, why = self.killer(pre)[0:4]
            cause, facts = self.explain(list(self.trace))
            self.death_log.append((c.frames, rn, x_, y_, cause))
            self.write_log({"event": "death", "level": self.level_no, "frame": c.frames,
                            "room": rn, "x": x_, "y": y_, "cause": cause,
                            "doing": self.doing, "facts": facts,
                            "trace": list(self.trace)})
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

    def write_log(self, rec):
        if self.log_path:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(rec) + "\n")

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
        hi = 14 if band == 0 else 12   # band 0: the thrust inertia must not carry
                                       # him out through the ceiling (an exit up)
        if band == BANDS - 1 and self.lv.rooms[self.c.r("RoomNo")].get("bottom_band"):
            hi = 2                     # the water kills from y 115: fly y 108..114
        if self.hi_override is not None:
            hi = self.hi_override
        crow = self.crunch_band(self.lv.rooms[self.c.r("RoomNo")])
        if crow is not None and band + 1 == crow:
            hi = min(hi, 2)            # the crunch row is right below: the 22-px box
                                       # must stay clear of it even when he sags
        elif crow is not None and band - 1 == crow:
            hi = 26                    # ... or right above: do not overshoot upward
        if self.c.r("vyHi") >= 0x80:
            return NONE                # already rising: the jet is slow to fade, so
                                       # more thrust now only carries him out the top
        return UP if y > BAND_PX * band + hi else NONE

    def phase_ahead(self, x, x_t, band):
        """True while a phase wall (45 frames ON / 45 OFF, mod-90 clock on EnemyRamP)
        sits just ahead on `band` and is not open for long enough to cross."""
        c = self.c
        if c.ram[0xBA & 0x7F] & 0x40:
            return False                          # crushed once: open for the visit
        room = self.lv.rooms[c.r("RoomNo")]
        dx = 1 if x_t > x else -1
        for fc in room.get("feature_cells") or []:
            b, col, t = fc[0], fc[1], fc[2]
            if t != 10 or b != band:
                continue
            for cell in (col, 19 - col):
                lo, hi = 8 * cell, 8 * cell + 8
                ahead = (lo - x) if dx > 0 else (x - hi)
                if -4 <= ahead <= 26:
                    ph = c.ram[0xC2 & 0x7F] % 90
                    if ph < 45 or ph > 62:        # ON, or OFF with < 28 frames left
                        return True
        return False

    def crunch_band(self, room):
        """Band index of the room's hcrunch row, or None."""
        rows = [fc[0] for fc in room.get("feature_cells") or [] if fc[2] == 12]
        if not rows:
            return None
        m = self.lv.models[room["model_id"]]
        return rows[0] if len(m["tiles"]) // m["width"] != 3 else (0, 1, 3)[rows[0]]

    @staticmethod
    def crunch_pairs(p):
        """Covered pairs 1..n of the hcrunch prefix at clock p (HcrClock in bank3:
        s = P>>4; dwell 0-3, grow 4-12, fast retract 13-15)."""
        s = (p & 255) >> 4
        eff = 0 if s < 4 else s - 3 if s < 13 else 3 * (15 - s)
        return 1 + min(eff, 9)

    def crunch_wait(self, run, ahead=70, room=None, delay=0):
        """Hold still until the hcrunch (clock EnemyRamP, period 256) cannot catch the
        flight `run` = [(x, band), ...] (one x per cell, 1.4 px/frame assumed). The prefix
        covers pairs 1..n of 8 px from both side walls, so a shaft far from the
        wall is clear for most of the period and a dash across fits the dwell +
        retract window: the crunch is a timing gate, not a forced kill."""
        c = self.c
        room = room or self.lv.rooms[c.r("RoomNo")]
        rows = [fc[0] for fc in room.get("feature_cells") or [] if fc[2] == 12]
        if not rows:
            return
        m = self.lv.models[room["model_id"]]
        h = len(m["tiles"]) // m["width"]
        band = (rows[0] if h != 3 else (0, 1, 3)[rows[0]])
        bs = [b for _x, b in run]
        if not (min(bs) - 1 <= band <= max(bs)):
            return                                  # the box clears the crunch row
        # the flight as (x, y) points: a node's y is its band's hover height; the
        # player moves 1.4 px/frame sideways and 1.2 px/frame vertically
        pts = [(x, 36 * b_ + 12) for x, b_ in run]
        track = [(pts[0][0], -200.0)] * delay        # still in the room before
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            vy_ = 1.0 if yb < ya else 1.4          # the jet climbs slowly, he falls faster
            n_ = max(1, int(max(abs(xb - xa) / 1.4, abs(yb - ya) / vy_)))
            for i_ in range(n_):
                track.append((xa + (xb - xa) * i_ / n_, ya + (yb - ya) * i_ / n_))
        track.append(pts[-1])
        dur = len(track)
        top, bot = 36 * band, 36 * band + 36        # the crunch row's y span

        def clear(p):
            for t, (xt, yt) in enumerate(track):
                if not (yt + 22 > top and yt < bot):
                    continue                        # the 22-px box is off the row
                lo, hi = xt - 10, xt + 4
                n = self.crunch_pairs(p + t)
                for pair in range(1, n + 1):
                    for a_ in (8 * pair, 8 * (19 - pair)):
                        if a_ < hi and a_ + 8 > lo:
                            return False
            return True
        self.doing = f"waiting for the crunch (run {run[0]}..{run[-1]})"
        for _ in range(400):
            if c.ram[0xBA & 0x7F] & 0x80:
                return                              # spent: parked for the visit
            if clear(c.ram[0xC2 & 0x7F]):
                return dur
            self.step(self.altitude(band_of(c.r("RoomY"))))

    def shoot_ahead(self, x, y, dx):
        """True while a live killable enemy is level with us, ahead and close: stand
        still facing it (the held laser kills it) instead of walking into it. At most
        150 frames per approach, so a stationary one does not hold the bot forever."""
        c = self.c
        room = self.lv.rooms[c.r("RoomNo")]
        recs = room.get("enemies") or []
        mask = c.ram[0xBA & 0x7F]
        for i in range(min(3, c.r("EnemyCount"), len(recs))):
            if mask >> i & 1 or recs[i]["type"] in (3, 7):
                continue                          # dead / tentacle / raft
            ex = c.ram[(c.lab["EnemyRamX"] & 0x7F) + i]
            ey = c.ram[(c.lab["EnemyRamY"] & 0x7F) + i]
            if abs(ey - y) <= 18 and 0 < (ex - x) * dx <= 72:
                self.shoot_wait = getattr(self, "shoot_wait", 0) + 1
                self.threat_dx = ex - x
                if self.shoot_wait < 400:
                    return True
        else:
            self.shoot_wait = 0
        return False

    def to_x(self, x_t, band, maxf=400):
        """Walk along `band` until RoomX == x_t exactly."""
        for _ in range(maxf):
            x = self.c.r("RoomX")
            if x == x_t:
                return True
            y = self.c.r("RoomY")
            if BAND_PX * band <= y <= BAND_PX * band + 14:
                sw = (RIGHT if x < x_t else LEFT) & self.altitude(band)
                if self.phase_ahead(x, x_t, band):
                    sw = self.altitude(band)      # wait for the wall's OFF half
                elif self.shoot_ahead(x, y, 1 if x_t > x else -1):
                    # face it (a tap toward it turns him round) and keep 28 px away:
                    # the held laser, 4 px/frame, kills what it touches. Enemies
                    # that do not patrol (stationary bats) never come to us.
                    dx_ = self.threat_dx
                    sw = self.altitude(band)
                    if abs(dx_) > 28 and self.c.frames % 6 == 0:
                        sw = (RIGHT if x_t > x else LEFT) & sw
            else:
                # the 22-px box still overlaps the band above/below: sideways
                # now would crush him in a wall edge (the spawn at RoomY 24)
                sw = self.altitude(band)
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
                self.edge_safe(cur, nxt, lambda _c, _n: self.bomb_strip(_n))
                continue                          # re-check the same edge, strip gone
            self.path, self.path_i = path, i
            self.doing = f"edge {cur}->{nxt}"
            ok = self.edge_safe(cur, nxt)
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
            self.prev_end = c.frames

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
        self.doing = f"bomb strip {strip}"
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

    def collect_run(self, k):
        """Nodes of the path from index k on that stay in k's room along a shaft (one
        column) or along a band: [(x, band), ...], and the last index used."""
        path = self.path
        run = [(x_for_cell(path[k][2]), path[k][1])]
        b0 = path[k][1]
        while k + 1 < len(path) and path[k][0] == path[k + 1][0] and (
                (len(run) < 8 and path[k][2] == path[k + 1][2])
                or (path[k][1] == path[k + 1][1] == b0 and len(run) < 24)):
            k += 1
            run.append((x_for_cell(path[k][2]), path[k][1]))
        return run, k

    def edge_safe(self, cur, nxt, fn=None):
        """Fly the edge; with `safe` on, a life lost on it is UNDONE (snapshot) and the
        edge retried: first after waiting in place and/or hovering higher or lower,
        then from the START OF THE EDGE BEFORE (a bat under a shaft is lethal by the
        time the drop has landed). If no variant gets through alive the edge is
        FORCED: the level, not the bot, takes the life (recorded in `forced`)."""
        fn = fn or self.edge
        if not self.safe:
            return fn(cur, nxt)
        c = self.c
        snap = (c.save(), self.hover, self.deaths, len(self.death_log), cur, nxt)
        ok = fn(cur, nxt)
        if self.deaths == snap[2]:
            self.prev = snap
            return ok
        first = self.death_log[snap[3]:]
        prev = getattr(self, "prev", None)
        if prev is not None and (prev[5] != cur or c.frames != snap[0][6]
                                 or getattr(self, "prev_end", None) != snap[0][6]):
            prev = None                       # not the edge right before (touch / bomb between)
        for scope in ((snap, prev) if prev else (snap,)):
            for hi_ov in (None, 2, 24):
                for wait in range(0, 300, 12):
                    if scope is snap and hi_ov is None and wait == 0:
                        continue              # that was the first attempt
                    sv, hover, d0, n0, e_cur, e_nxt = scope
                    c.restore(sv)
                    self.hover, self.deaths = hover, d0
                    del self.death_log[n0:]
                    self.hi_override = hi_ov
                    self.doing = (f"edge {cur}->{nxt} RETRY wait={wait} hover={hi_ov} "
                                  f"from {'before' if scope is prev else 'here'}")
                    for _ in range(wait):
                        self.step(self.altitude(band_of(c.r("RoomY"))))
                    good = self.deaths == d0
                    if good and scope is prev:
                        self.edge(e_cur, e_nxt)       # replay the edge before
                        self.clear_hover()
                        good = self.deaths == d0
                    if good:
                        ok = fn(cur, nxt)
                        good = self.deaths == d0
                    self.hi_override = None
                    if good:
                        self.say(f"edge {cur}->{nxt} safe: wait {wait}, hover {hi_ov}, "
                                 f"from {'the edge before' if scope is prev else 'here'}")
                        self.waited += 1
                        self.prev = scope if False else (c.save(), self.hover,
                                                         self.deaths, len(self.death_log),
                                                         cur, nxt)
                        return ok
        self.forced.append((cur, nxt, first[0] if first else None))
        return ok

    def edge(self, cur, nxt):
        """Fly one graph edge. True when the player is where `nxt` says."""
        c = self.c
        (r0, b0, f0), (r1, b1, f1) = cur, nxt
        if r0 != r1:
            # (EnterRoom restarts the crunch clock at 64: the wait happens inside,
            # below the crunch row, by the in-room run)
            return self.exit_room(cur, nxt)
        run, k = self.collect_run(self.path_i)
        if len(run) == 1:
            run.append((x_for_cell(f1), b1))
        go = getattr(self, "crunch_go", None)
        if go and go[0] == c.r("RoomNo") and self.path_i <= go[1] and c.frames < go[2]:
            pass                                    # already cleared this whole run
        else:
            dur = self.crunch_wait(run)
            if dur:
                self.crunch_go = (c.r("RoomNo"), k, c.frames + dur)
        if b0 == b1 and b0 == BANDS - 1 and self.lv.rooms[r0].get("bottom_band"):
            return self.ride(cur, nxt)
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
            if b1 > b0 and self.hi_override is not None and y > BAND_PX * b1 - 12:
                sw = self.altitude(b1)        # retry variant: brake into the band
            if c.r("RoomX") != x_for_cell(f0):
                sw &= RIGHT if c.r("RoomX") < x_for_cell(f0) else LEFT
            self.step(sw)
        return False

    def ride(self, cur, nxt):
        """Along the WATER row: the raft is the only floor. It moves (1-1.5 px per
        frame, right first) only while he stands on it, so after landing on it the
        bot lets it carry him and steps off when the target cell comes by."""
        c = self.c
        (r0, b0, f0), (r1, b1, f1) = cur, nxt
        x_t = x_for_cell(f1)
        for _ in range(900):
            x = c.r("RoomX")
            if abs(x - x_t) <= 1:
                return True
            self.step(NONE)
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
        # The visiting order matters: crossing a raft room or a bomb strip is only
        # possible one way round, so try every order (<= 3 miners) and take the
        # shortest one that has a route for every leg.
        import itertools
        start = (c.r("RoomNo"), band_of(c.r("RoomY")), cell_of(c.r("RoomX")))
        best = None
        for perm in itertools.permutations([self.lv.miner] + list(self.lv.extras)):
            cur, total = start, 0
            for t in perm:
                leg = self.lv.route(cur, t)
                if leg is None:
                    total = None
                    break
                total += self.lv.last_cost       # a spider zone costs SR.DANGER: a
                cur = t                          # hazard-free order always beats a short one
            if total is not None and (best is None or total < best[0]):
                best = (total, perm)
        if best is None:
            raise GiveUp("no order of the miners has a route for every leg")
        targets = list(best[1])
        self.say("order", targets)
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
        self.doing = f"touch miner {tgt}"
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


def finish(con, lv, mortal, verbose, budget, safe=False, log=None, level_no=0):
    pilot = Pilot(con, lv, mortal, verbose)
    pilot.log_path, pilot.level_no = log, level_no
    pilot.safe = safe
    try:
        pilot.play(budget)
        ok, why = False, "the route ended without a tally"
    except Done:
        ok, why = True, "tally started"
    except GiveUp as e:
        ok, why = False, str(e)
        pilot.write_log({"event": "giveup", "level": pilot.level_no, "why": why,
                         "doing": pilot.doing, "trace": list(pilot.trace)})
    return ok, why, pilot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--mortal", action="store_true")
    ap.add_argument("--frames", type=int, default=7200)
    ap.add_argument("-v", action="store_true")
    ap.add_argument("--log", help="append one JSON line per death / give-up (last 48 frames, "
                                  "enemies, crunch/phase state, what the bot was doing)")
    ap.add_argument("--safe", action="store_true",
                    help="undo a lost life and retry the edge later; what still dies is FORCED")
    ap.add_argument("--rom-dir", help="bank*.bin + bank0.lst of a variant build "
                                      "(tools/build_variant.sh, KEEP=1)")
    a = ap.parse_args()
    stage = json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]
    levels = a.levels or list(range(1, len(stage["levels"]) + 1))
    bad = 0
    for n in levels:
        con = Console(a.rom_dir)
        con.boot(n)
        lv = Level(stage, n)
        t0 = con.frames
        ok, why, pilot = finish(con, lv, a.mortal, a.v, a.frames, a.safe, a.log, n)
        used = con.frames - t0
        print(f"level {n:2d}: {'DONE' if ok else 'FAIL'}  {used:5d} frames  "
              f"deaths {pilot.deaths}  rooms {len(pilot.rooms_seen)}/{len(lv.rooms)}"
              f"  - {why}")
        for f_, r_, x_, y_, why_ in pilot.death_log:
            print(f"           death: frame {f_}, room {r_}, x={x_} y={y_}  ({why_})")
        if a.log and not ok:
            print(f"           (give-up context in {a.log})")
        if a.safe:
            print(f"           retried-and-saved edges: {pilot.waited}, FORCED edges: {len(pilot.forced)}")
            for cur_, nxt_, d_ in pilot.forced:
                print(f"           FORCED {cur_} -> {nxt_}: {d_}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
