#!/usr/bin/env python3
"""SELECT during a game refills the power bar; a game over returns to the title on the level
that was being played (user 2026-11-11). Flies the real ROM (tools/playbot Console), level 9:
  * BarLevel = 50, press SELECT -> BarLevel is 120 again (it used to stay at 50);
  * one life left, stand in the level's hot band until the run ends -> the title is back
    (DropTarget $FF, lives 3, bar full) with Level still 8 (= level 9), not 0.
Run: /home/iuri/python3/bin/python3 tools/test_select_gameover.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402


def main() -> int:
    con = P.Console()
    con.boot(9)
    base = con.save()
    con.w("BarLevel", 50)
    con.swchb = 0xFD
    for _ in range(3):
        con.frame()
    con.swchb = 0xFF
    for _ in range(3):
        con.frame()
    if con.r("BarLevel") != 120:
        print(f"FAIL: SELECT during a game left BarLevel at {con.r('BarLevel')} (want 120)")
        return 1
    con.restore(base)
    con.w("PlayerLives", 1)
    for i in range(4000):
        if con.r("DropTarget") == 0 and con.r("PlayerLives") >= 1:
            con.w("RoomY", 40)                    # level 9 room 1: band 1 is hot
        con.frame(P.RIGHT if (i // 40) % 2 == 0 else P.LEFT)
        if con.r("PlayerLives") == 3 and con.r("DropTarget") == 0xFF:
            break
    else:
        print("FAIL: the run never ended")
        return 1
    if con.r("Level") != 8:
        print(f"FAIL: after the game over the title shows Level {con.r('Level') + 1}, want 9")
        return 1
    # --- user 2026-11-11: died in level 8 tapping UP, the title came back on 9. The title
    # now ignores every key for ~1 s after a game over; later presses work as before.
    lvl = con.r("Level")
    for i in range(40):                           # inside the grace: UP + FIRE taps
        con.frame(P.UP if (i // 3) % 2 == 0 else P.NONE, (i // 3) % 2 == 0)
    if con.r("Level") != lvl or con.r("DropTarget") != 0xFF:
        print(f"FAIL: keys tapped just after the game over changed the title "
              f"(Level {lvl + 1} -> {con.r('Level') + 1}, DropTarget ${con.r('DropTarget'):02X})")
        return 1
    for _ in range(40):                           # grace over, everything released
        con.frame(P.NONE)
    con.frame(P.UP)
    for _ in range(3):
        con.frame(P.NONE)
    if con.r("Level") != (lvl + 1) % 20:
        print(f"FAIL: UP after the grace no longer steps the level ({con.r('Level') + 1})")
        return 1
    print("test_select_gameover: OK (SELECT refills the bar; game over keeps the level "
          "and ignores keys for ~1 s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
