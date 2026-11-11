#!/usr/bin/env python3
"""The async patch walls (M1 left strip / ball right strip) are SOLID in the real game.

User report 2026-11-11 (level 9 room 1): "I am supposed to blast the right hot-wall pillar,
but I can just pass through it." Root cause: the bank6 cave kernel reuses $8F (S1Adj) as a
scratch byte, but bank3's SBT_B packs the overlay byte into $8F and bank1's HUD copies it to
LineCount ($84) AFTER the cave -> always 0 -> OverlayTramp skipped PHMOverlay: every async
wall, ball strip and door was walk-through from 1.1.0 on. Every test staged its own bytes, so
nothing noticed. This one flies the REAL ROM (tools/playbot Console) through the real title ->
drop-in entry path of every level whose START room has a patch, and walks into each patch:
  * ball strip [row, c, tile, 0] = full column 10+c: walk RIGHT through that band from the
    left, the player must stop at the strip (RoomX <= 8*(10+c) + 1);
  * M1 strip [row, c, tile, 1] = full column c: walk LEFT from the right, the player must
    stay out of it (RoomX >= 8*c + 8 + 7 - 2).
Run: /home/iuri/python3/bin/python3 tools/test_async_wall.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402


def band_y(band: int) -> int:
    return band * P.BAND_PX + 14          # band_of(y) = (y + 11) // 36 == band


def main() -> int:
    stage = json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]
    bad, checked, unproven = [], 0, []
    for n, lv in enumerate(stage["levels"], 1):
        con = P.Console()
        con.boot(n)
        base = con.save()
        for ri, room in enumerate(lv["rooms"]):
          patches = [p for p in (room.get("asym_patches") or [])
                     if len(p) >= 4 and p[2] == 1]               # solid wall patches
          for row, col, _tile, side in patches:
            con.restore(base)
            if ri:                              # enter room ri the way a room exit does
                con.w("LevelConnSpare", ri | 0x80)
                for _ in range(4):
                    con.frame(P.NONE)
                assert con.r("RoomNo") == ri, (n, ri, con.r("RoomNo"))
            con.w("PlayerLives", 8)
            con.w("RoomY", band_y(row))
            if side == 0:                      # ball strip: full column 10 + col
                f = 10 + col
                con.w("RoomX", max(4, 8 * f - 16))
                xs, left = [], False
                for _ in range(90):
                    prev_y = con.r("RoomY")
                    con.frame(P.RIGHT)
                    if con.r("RoomNo") != ri:
                        left = abs(prev_y - band_y(row)) <= 2   # a side exit, not a fall
                        break
                    xs.append(con.r("RoomX"))
                ok = not left and bool(xs) and max(xs) <= 8 * f + 1
                if ok and max(xs) < 8 * f - 6: unproven.append((n, ri + 1, row, f))
                what = f"ball strip col {f}: max RoomX {max(xs) if xs else '?'} > {8 * f + 1}"
            else:                              # M1 strip: full column col
                f = col
                con.w("RoomX", 8 * f + 8 + 7 + 14)
                xs, left = [], False
                for _ in range(90):
                    prev_y = con.r("RoomY")
                    con.frame(P.LEFT)
                    if con.r("RoomNo") != ri:
                        left = abs(prev_y - band_y(row)) <= 2   # a side exit, not a fall
                        break
                    xs.append(con.r("RoomX"))
                ok = not left and bool(xs) and min(xs) >= 8 * f + 8 + 7 - 2
                if ok and min(xs) > 8 * f + 8 + 7 + 6: unproven.append((n, ri + 1, row, f))
                what = f"M1 strip col {f}: min RoomX {min(xs) if xs else '?'} < {8 * f + 13}"
            checked += 1
            if not ok:
                bad.append(f"level {n} room {ri + 1} band {row}: walked through the {what}")
    if bad:
        print("FAIL:\n  " + "\n  ".join(bad))
        return 1
    print("unproven (never reached the strip):", unproven)
    print(f"test_async_wall: OK ({checked} patch walls solid in the real ROM)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
