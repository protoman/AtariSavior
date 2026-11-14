#!/usr/bin/env python3
"""Monkey test: random joystick / fire / bomb / console-switch input on the REAL ROM (py65),
every level, a few seeds. It does not judge play, it hunts for the things that must NEVER
happen whatever the player does:
  * the CPU leaves the ROM or executes BRK (crash), or a frame never ends (hang),
  * Level / lives / power bar / room number out of range,
  * the title or a game over lands on a wrong level,
  * the player ends embedded in a wall for good (stuck: no movement for 600 frames while
    awake and not on the title),
Run: /home/iuri/python3/bin/python3 tools/monkey_fuzz.py [--seeds N] [--frames N] [LEVEL ...]
"""
import argparse
import random
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path(".")
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402

STEP_CAP = 400_000


def run_frame(con, swcha, fire):
    con.swcha = swcha
    con.inpt4 = 0x00 if fire else 0x80
    m = con.mpu
    n = 0
    while True:
        pc = m.pc
        if pc < 0xF000:
            raise RuntimeError(f"PC left the ROM: ${pc:04X}")
        if con[pc] == 0x00:
            raise RuntimeError(f"BRK executed at bank {con.bank} ${pc:04X}")
        m.step()
        n += 1
        if con.bank == 0 and m.pc == con.pc_frame:
            break
        if n > STEP_CAP:
            raise RuntimeError(f"frame never ended (bank {con.bank} pc ${m.pc:04X})")
    con.frames += 1


def worker(args):
    level, seed, frames = args
    rnd = random.Random(seed * 1000 + level)
    con = P.Console()
    con.boot(level)
    nlev = 20
    seen = {"sp": 0xFF, "x": (255, 0), "y": (255, 0)}
    msgs = []
    still = 0
    last = None
    dirs = [P.NONE, P.UP, P.DOWN, P.LEFT, P.RIGHT, P.UP & P.LEFT, P.UP & P.RIGHT,
            P.DOWN & P.LEFT, P.DOWN & P.RIGHT]
    swcha, fire, hold = P.NONE, True, 0
    prev_dt, played = con.r("DropTarget"), con.r("Level")
    for f in range(frames):
        if hold <= 0:
            swcha = rnd.choice(dirs)
            fire = rnd.random() < 0.6
            hold = rnd.randint(4, 50)
        hold -= 1
        con.swchb = 0xFF
        roll = rnd.random()
        if roll < 0.0015:
            con.swchb = 0xFD                  # SELECT
        elif roll < 0.0020:
            con.swchb = 0xFE                  # RESET
        if con.r("PlayerLives") < 3 and rnd.random() < 0.0008:
            con.w("PlayerLives", 3)           # keep the run alive sometimes
        try:
            run_frame(con, swcha, fire)
        except RuntimeError as e:
            return [f"L{level} seed {seed} frame {f}: {e}"], seen
        lv, dt = con.r("Level"), con.r("DropTarget")
        if prev_dt == 0xFF and dt != 0xFF:
            played = lv                       # a game starts on the title's level
        elif dt == 0xFE:
            played = None                     # level tally: the next title level may differ
        elif prev_dt != 0xFF and dt == 0xFF and played is not None and lv != played:
            msgs.append(f"L{level} seed {seed} f{f}: the title came back on level {lv + 1}, "
                        f"the game was level {played + 1}")
            break
        prev_dt = dt
        if lv >= nlev:
            msgs.append(f"L{level} seed {seed} f{f}: Level {lv} out of range")
            break
        lives = con.r("PlayerLives")
        if dt != 0xFF and lives > 3:
            msgs.append(f"L{level} seed {seed} f{f}: lives {lives}")
            break
        if con.r("BarLevel") > 120 and dt != 0xFF:
            msgs.append(f"L{level} seed {seed} f{f}: BarLevel {con.r('BarLevel')}")
            break
        if dt == 0:
            rn = con.r("RoomNo")
            if rn >= con.r("LevelRoomN") and con.r("LevelRoomN"):
                msgs.append(f"L{level} seed {seed} f{f}: RoomNo {rn} >= LevelRoomN {con.r('LevelRoomN')}")
                break
            x, y = con.r("RoomX"), con.r("RoomY")
            seen["x"] = (min(seen["x"][0], x), max(seen["x"][1], x))
            seen["y"] = (min(seen["y"][0], y), max(seen["y"][1], y))
            pos = (rn, x, y)
            still = still + 1 if pos == last and swcha != P.NONE else 0
            last = pos
            if still > 900 and con.r("PlayerLives") > 0:
                pass  # standing against a wall for 15 s with a key held is legal
        seen["sp"] = min(seen["sp"], con.mpu.sp)
    return msgs, seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--frames", type=int, default=12000)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--seed0", type=int, default=1)
    a = ap.parse_args()
    levels = a.levels or list(range(1, 21))
    jobs = [(lv, s, a.frames) for lv in levels for s in range(a.seed0, a.seed0 + a.seeds)]
    bad, sp, xs, ys = [], 0xFF, (255, 0), (255, 0)
    with Pool(a.jobs) as pool:
        for msgs, seen in pool.imap_unordered(worker, jobs):
            bad += msgs
            sp = min(sp, seen["sp"])
            xs = (min(xs[0], seen["x"][0]), max(xs[1], seen["x"][1]))
            ys = (min(ys[0], seen["y"][0]), max(ys[1], seen["y"][1]))
    print(f"monkey: {len(jobs)} runs x {a.frames} frames; min SP ${sp:02X}; RoomX {xs}, RoomY {ys}")
    for b in bad:
        print("FAIL:", b)
    if not bad:
        print("test_monkey: OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
