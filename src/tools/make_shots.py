#!/usr/bin/env python3
"""Game screenshots from the real ROM (no Stella): the playbot flies a level, and at a
chosen moment the TIA model (tools/tia_render.py) renders what the kernel draws.

  make_shots.py [SCENE ...] [--out DIR]       (default: every scene, DIR = docs/release/screenshots)

Needs the live ROM (./build.sh) and rooms/stage.json, like the playbot. Each scene is
(name, level, predicate): the picture is taken the first time the predicate holds while
the bot plays that level; the laser is held, so the beam shows when something is ahead.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402
import tia_render as T  # noqa: E402


class Capture(Exception):
    def __init__(self, sw):
        self.sw = sw


def near_miner(c, ctx):
    return ctx["room"] == c.r("LevelMinerRoom") & 0x7F and \
        abs(ctx["x"] - c.r("MinerX")) < 26 and abs(ctx["y"] - c.r("MinerY")) < 30


def extra_wall(c, ctx, lv, need, bands=(1, 2, 3)):
    """Playfield columns that are solid NOW beyond the room's static walls: a closed
    crusher shutter or a phase wall that is on."""
    air = lv.grids[ctx["room"]][0]
    for b in bands:
        static = sum(1 for a in air[b] if not a) * 2
        live = sum(1 for col in range(40) if c.pf_wall(col, b))
        if live - static >= need:
            return True
    return False


SCENES = {
    # name: (level, predicate(console, ctx))
    "level03_rescue": (3, near_miner),
    "level06_bat": (6, lambda c, k: k["room"] == 3 and k["in_room"] >= 70),
    "level09_spider": (9, lambda c, k: k["room"] == 5 and k["in_room"] >= 40),
    "level11_raft": (11, lambda c, k: k["room"] == 7 and k["y"] >= 100
                     and k["x"] > 60 and k["in_room"] > 120),
    # the shutter half way across (the wall sweeps in from the side)
    "level14_crusher": (14, lambda c, k: k["room"] in (1, 4) and k["in_room"] >= 20
                        and extra_wall(c, k, k["lv"], 10)
                        and not extra_wall(c, k, k["lv"], 18)),
    "level17_raft_hot": (17, lambda c, k: k["room"] == 9 and k["y"] >= 100
                           and k["x"] > 60 and k["in_room"] > 120),
}


class ShotPilot(P.Pilot):
    def __init__(self, *a, predicate=None, **kw):
        super().__init__(*a, **kw)
        self.predicate = predicate
        self.entered = 0
        self.room = None

    def step(self, sw=P.NONE):
        super().step(sw)
        c = self.c
        rn = c.r("RoomNo")
        if rn != self.room:
            self.room, self.entered = rn, c.frames
        ctx = dict(room=rn, x=c.r("RoomX"), y=c.r("RoomY"), lv=self.lv,
                   in_room=c.frames - self.entered)
        if self.predicate(c, ctx):
            raise Capture(sw)


def shoot(name, level, predicate, stage, outdir):
    con = P.Console()
    con.boot(level)
    lv = P.Level(stage, level)
    pilot = ShotPilot(con, lv, predicate=predicate)
    try:
        pilot.start_frames = con.frames
        pilot.budget = 9000
        pilot.hover = False
        pilot.play(9000)
    except Capture as cap:
        T.attach(con)
        con.w("PlayerLives", 3)          # the bot keeps 8 lives topped up: show 3
        img = con.snapshot(frames=2, swcha=cap.sw, fire=True, scale=(6, 3))
        path = outdir / f"{name}.png"
        img.save(path)
        print(f"{name}: level {level}, room {con.r('RoomNo') + 1}, frame {con.frames} -> {path}")
        return True
    except (P.GiveUp, P.Done) as e:
        print(f"{name}: no shot ({e!r})")
        return False
    print(f"{name}: the predicate never held")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*")
    ap.add_argument("--out", default=str(ROOT / "docs" / "release" / "screenshots"))
    a = ap.parse_args()
    stage = json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ok = True
    if not a.scenes or "title" in a.scenes:
        con = P.Console()
        for _ in range(6):
            con.frame()
        T.attach(con)
        con.snapshot(frames=3, scale=(6, 3)).save(out / "title.png")
        print(f"title -> {out / 'title.png'}")
        a.scenes = [n for n in a.scenes if n != "title"] or ([] if a.scenes else None)
    for name in (a.scenes if a.scenes is not None else SCENES):
        level, pred = SCENES[name]
        ok &= shoot(name, level, pred, stage, out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
