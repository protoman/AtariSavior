#!/usr/bin/env python3
"""Flicker check in EVERY room (not only the 40 heaviest): enter each room of the live stage the
way a room exit does, then measure 90 frames with the TIA model (laser released and held):
  * the VBL work leaves >= 150c of the window,
  * every ordinary frame is TV_CAVE_LINES long (+-1 allowed on <= 3% of frames).
Run: /home/iuri/python3/bin/python3 tools/test_frame_all_rooms.py [--jobs N] [LEVEL ...]
"""
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402
import test_frame_stability as F  # noqa: E402


def one_level(level):
    con0 = P.Console()
    con0.boot(level)
    base = con0.save()
    bad, n = [], 0
    for ri, room in enumerate(F.STAGE["levels"][level - 1]["rooms"]):
        for fire in (False, True):
            con = P.Console()
            con.restore(base)
            if ri:
                con.w("LevelConnSpare", ri | 0x80)
                for _ in range(4):
                    con.frame(P.NONE)
                if con.r("RoomNo") != ri:
                    bad.append(f"L{level} room {ri + 1}: could not enter")
                    break
            con.w("PlayerLives", 8)
            if ri == F.STAGE["levels"][level - 1]["miner_room"]:
                # touching the miner starts the level tally (a different, steady scene):
                # keep the player on the far side so the room itself is what is measured
                con.w("RoomX", 140 if con.r("MinerX") < 80 else 10)
            lens, rows, vbl = F.measure(con, fire, 90)
            n += 1
            total = sum(lens.values())
            off = total - lens.get(F.TARGET, 0)
            msg = f"L{level} room {ri + 1} fire={fire}: lines {dict(lens)}, VBL {vbl}/{F.VBL_WINDOW}c"
            if vbl > F.VBL_WINDOW - 150:
                bad.append(msg + "  <- VBL work leaves < 150c")
            elif off > 0.03 * total or any(k not in (F.TARGET - 1, F.TARGET, F.TARGET + 1) for k in lens):
                bad.append(msg + "  <- unstable frame length")
    return bad, n


def main():
    jobs = 6
    args = sys.argv[1:]
    if "--jobs" in args:
        i = args.index("--jobs")
        jobs = int(args[i + 1])
        del args[i:i + 2]
    levels = [int(a) for a in args] or list(range(1, 21))
    bad, total = [], 0
    with Pool(jobs) as pool:
        for b, n in pool.imap_unordered(one_level, levels):
            bad += b
            total += n
    for b in bad:
        print("FAIL:", b)
    if bad:
        return 1
    print(f"test_frame_all_rooms: OK ({total} room/laser runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
