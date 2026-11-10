#!/usr/bin/env python3
"""Frame length / VBL window stability in the HEAVY rooms (the flicker class).

2026-11 regression this guards: the bank6 cave kernel's prologue runs inside the VBL timer
window, and in rooms with an enemy (or two enemies, or an enemy + the miner) bank0's VBL work
(~1500c) plus the prologue (~730c) overran the 1984c window: frames stretched to 279-296 lines
= a rolling, flickering picture. sim_frame_budget missed it because it stopped the VBL
measurement at bank0's .WaitVBLANK, which gameplay frames no longer reach; its scenario room
also has a light VBL. This test reaches REAL rooms with the most objects through the bot and
checks, with the laser held and released:

  * the VBL work (timer arm -> the first INTIM poll of the bank6 kernel) leaves >= 150c of the
    window,
  * every ordinary frame is 272 lines (a stray 273 is allowed up to 3% of the frames: the old
    kernel shows the same overscan spike; room-change frames are skipped),
(Same-band object pairs rotate at 30 Hz by design, so the rows drawn per frame are not checked.)

Run: /home/iuri/python3/bin/python3 tools/test_frame_stability.py [--all]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402
import tia_render as T  # noqa: E402

STAGE = json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]
UNITS = dict(re.findall(r"^(VBL_UNITS|OVER_UNITS)\s*=\s*(\d+)", (ROOT / "colors.inc").read_text(), re.M))
VBL_WINDOW = int(UNITS["VBL_UNITS"]) * 64


def heavy_rooms(limit):
    """(level, room0, objects): rooms with the most GRP1 objects (enemies + the miner)"""
    out = []
    for li, lv in enumerate(STAGE["levels"]):
        for ri, r in enumerate(lv["rooms"]):
            n = len([e for e in r.get("enemies", []) if e.get("type", 0) != 14])
            n += 1 if lv["miner_room"] == ri else 0
            if n >= 2 and ri > 0:
                out.append((n, li + 1, ri))
    out.sort(reverse=True)
    return [(lv, ri, n) for n, lv, ri in out[:limit]]


def reach(level, room):
    con = P.Console()
    con.boot(level)
    pilot = P.Pilot(con, P.Level(STAGE, level), False, False)
    pilot.start_frames = con.frames
    pilot.budget = 4000
    pilot.hover = False

    class Stop(Exception):
        pass
    orig = con.frame

    def fr(swcha=P.NONE, fire=False):
        orig(swcha, fire)
        if con.r("RoomNo") == room:
            raise Stop
    con.frame = fr
    try:
        pilot.play(4000)
    except (Stop, P.Done):
        pass
    con.frame = orig
    return con if con.r("RoomNo") == room else None


def measure(con, fire, frames=90):
    con.__class__ = type("C", (T.TiaConsole, type(con)), {})
    con.tia_init()
    for _ in range(3):
        con.tia_frame()
    base = type(con).__getitem__
    seen, info = [0], {}

    def gi(self, a):
        if (a & 0xFFFF) == 0x284 and self.bank == 6 and not seen[0]:
            seen[0] = 1
            t0, iv, v = self.timer
            info["vbl"] = self._now() - t0
        return base(self, a)
    type(con).__getitem__ = gi
    lens, rows, vbl = Counter(), Counter(), 0
    for _ in range(frames):
        seen[0] = 0
        t0 = con.vtime()
        log = con.tia_frame(P.NONE, fire)
        n = round((con.vtime() - t0) / T.LINE)
        if n < 400:
            lens[n] += 1
            rows[sum(1 for t, r, v in log if r == T.GRP1 and v)] += 1
            vbl = max(vbl, info.get("vbl", 0))
    type(con).__getitem__ = base
    return lens, rows, vbl


def main():
    rooms = heavy_rooms(40 if "--all" in sys.argv else 6)
    bad, tested = [], 0
    for level, room, n in rooms:
        for fire in (False, True):
            con = reach(level, room)
            if con is None:
                break
            lens, rows, vbl = measure(con, fire)
            tested += 1
            total = sum(lens.values())
            off = total - lens.get(272, 0)
            msg = f"L{level} room {room + 1} ({n} objects) fire={fire}: lines {dict(lens)}, VBL {vbl}/{VBL_WINDOW}c"
            if vbl > VBL_WINDOW - 150:
                bad.append(msg + "  <- VBL work leaves < 150c")
            elif off > 0.03 * total or any(k not in (271, 272, 273) for k in lens):
                bad.append(msg + "  <- unstable frame length")
    if not tested:
        print("test_frame_stability: SKIP (no heavy room reachable)")
        return 0
    if bad:
        print("FAIL:")
        for b in bad:
            print("  ", b)
        return 1
    print(f"test_frame_stability: OK ({tested} room/laser runs, VBL window {VBL_WINDOW}c)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
