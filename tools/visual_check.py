#!/usr/bin/env python3
"""Visual regression check for Stella screenshots of savior.bin.

Usage:
  python3 tools/visual_check.py <screenshot.png> [options]

Required checks (gate PASS/FAIL):
  content      non-black game content exists
  playfield    cave walls + open space in game area (structure)
  hud_band     grey HUD band present
  hud_text     white score/level text in HUD

Reported (informational unless --strict):
  player       compact bright-yellow blob (COLOR_PLAYER $1E) in game area
  hud_sprites  colored HUD sprites (lives/bombs/timer)
  timer_bar    yellow/red bar pixels (only with --expect-bar)

Options:
  --json           machine-readable JSON
  --ascii Y0 Y1    ASCII art of row range
  --expect-bar     require timer-bar colors in upper HUD
  --strict         player missing => FAIL

Exit 0 = PASS, 1 = FAIL.
"""
import argparse
import json
import sys
from collections import Counter
from PIL import Image


def is_black(c, thr=40):
    return sum(c[:3]) < thr


def is_grey(c, lo=70, hi=160):
    r, g, b = c[:3]
    return lo <= r <= hi and lo <= g <= hi and lo <= b <= hi and max(r, g, b) - min(r, g, b) <= 25


def is_white(c, thr=190):
    r, g, b = c[:3]
    return r >= thr and g >= thr and b >= thr


def is_player_yellow(c):
    """COLOR_PLAYER $1E = kPalette[1][7] = (0xfc, 0xfc, 0x68). Allow AA spread."""
    r, g, b = c[:3]
    return r >= 180 and g >= 160 and b < 150 and r >= g - 40


def content_bounds(px, w, h, thr=40):
    rows = [y for y in range(h) if any(not is_black(px[x, y], thr) for x in range(0, w, 3))]
    cols = [x for x in range(w) if any(not is_black(px[x, y], thr) for y in range(0, h, 3))]
    if not rows or not cols:
        return None
    return cols[0], rows[0], cols[-1], rows[-1]


def find_hud_band(px, w, x0, x1, y0, y1):
    """Longest contiguous grey run (>=15px). Ignores stray grey rows at edges."""
    grey_rows = []
    span = max(1, (x1 - x0) // 3)
    for y in range(y0, y1 + 1):
        grey = sum(1 for x in range(x0, x1 + 1, 3) if is_grey(px[x, y]))
        grey_rows.append(grey > span * 0.5)
    best = None
    run_start = None
    for i, ok in enumerate(grey_rows):
        y = y0 + i
        if ok and run_start is None:
            run_start = y
        elif not ok and run_start is not None:
            length = y - run_start
            if best is None or length > (best[1] - best[0] + 1):
                best = (run_start, y - 1)
            run_start = None
    if run_start is not None:
        length = y1 - run_start + 1
        if best is None or length > (best[1] - best[0] + 1):
            best = (run_start, y1)
    if not best or (best[1] - best[0] + 1) < 15:
        return None
    return best


def color_hist(px, x0, y0, x1, y1, step=2):
    c = Counter()
    for y in range(y0, y1 + 1, step):
        for x in range(x0, x1 + 1, step):
            c[px[x, y][:3]] += 1
    return c


def find_yellow_blob(px, x0, y0, x1, y1):
    """Compact player-yellow region in game area. Returns bbox or None."""
    pts = []
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if is_player_yellow(px[x, y]):
                pts.append((x, y))
    if len(pts) < 30:
        return None, len(pts)
    # density: bbox fill should be reasonably solid for a sprite
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
    # reject huge sparse regions (walls of similar hue)
    fill = len(pts) / float(bw * bh)
    if bw > 120 or bh > 80 or fill < 0.25:
        return None, len(pts)
    if bw < 4 or bh < 4:
        return None, len(pts)
    return (bx0, by0, bx1, by1, bw, bh, fill), len(pts)


def ascii_art(path, y0, y1, thr=80):
    img = Image.open(path)
    px = img.load()
    w, h = img.size
    y0 = max(0, y0)
    y1 = min(h - 1, y1)
    print(f"ASCII {path} y={y0}..{y1}")
    for y in range(y0, y1 + 1):
        line = f"{y:3d}|"
        for x in range(0, min(w, 640), 4):
            c = px[x, y][:3]
            b = sum(c) / 3
            if b > 200:
                line += "#"
            elif b > thr:
                line += "+"
            elif b > 30:
                line += "."
            else:
                line += " "
        print(line)


def analyze(path, expect_bar=False, strict=False):
    img = Image.open(path).convert("RGB")
    px = img.load()
    w, h = img.size
    res = {"file": path, "size": [w, h], "checks": [], "pass": True}

    def check(name, ok, detail="", required=True):
        res["checks"].append({
            "name": name,
            "ok": bool(ok),
            "required": required,
            "detail": detail,
        })
        if required and not ok:
            res["pass"] = False

    bounds = content_bounds(px, w, h)
    if not bounds:
        check("content", False, "all black")
        return res
    cx0, cy0, cx1, cy1 = bounds
    check("content", True, f"x={cx0}..{cx1} y={cy0}..{cy1}")

    hud = find_hud_band(px, w, cx0, cx1, cy0, cy1)
    if hud:
        hy0, hy1 = hud
        check("hud_band", (hy1 - hy0 + 1) >= 30, f"y={hy0}..{hy1} ({hy1 - hy0 + 1}px)")
        game_y1 = hy0 - 1
    else:
        check("hud_band", False, "no grey band")
        hy0 = hy1 = None
        game_y1 = cy1

    gx0, gy0, gx1, gy1 = cx0, cy0, cx1, game_y1
    if gy1 <= gy0 + 5:
        check("playfield", False, "game area empty")
        return res

    hist = color_hist(px, gx0, gy0, gx1, gy1, step=2)
    total = sum(hist.values()) or 1
    wall_colors = [
        (c, n) for c, n in hist.most_common()
        if n > total * 0.02 and not is_black(c) and not is_grey(c) and not is_white(c)
    ]
    wall_px = sum(n for _, n in wall_colors)
    black_px = sum(n for c, n in hist.items() if is_black(c))
    wall_frac = wall_px / total
    open_frac = black_px / total

    # Structure = both walls AND open space (single wall color is normal)
    check("playfield", wall_frac >= 0.05 and open_frac >= 0.05,
          f"wall={wall_frac:.0%} open={open_frac:.0%} colors={[c for c,_ in wall_colors[:3]]}")
    check("map_structure", wall_frac < 0.98 and open_frac < 0.98,
          f"not solid/empty (wall={wall_frac:.0%} open={open_frac:.0%})")

    # Player: compact yellow blob
    blob, npx = find_yellow_blob(px, gx0, gy0, gx1, gy1)
    if blob:
        bx0, by0, bx1, by1, bw, bh, fill = blob
        detail = f"bbox=({bx0},{by0})-({bx1},{by1}) {bw}x{bh} fill={fill:.2f} px={npx}"
        check("player", True, detail, required=strict)
    else:
        check("player", False, f"no compact yellow blob (yellowish_px={npx})",
              required=strict)

    # HUD text + sprites
    if hy0 is not None:
        white_n = sum(
            1 for y in range(hy0, hy1 + 1) for x in range(0, w, 2)
            if is_white(px[x, y])
        )
        check("hud_text", white_n > 30, f"white_px={white_n}")

        hud_hist = color_hist(px, cx0, hy0, cx1, hy1, step=2)
        colored = [
            (c, n) for c, n in hud_hist.most_common()
            if n > 20 and not is_grey(c) and not is_white(c) and not is_black(c)
        ]
        check("hud_sprites", len(colored) >= 1, f"top={colored[:4]}")

        if expect_bar:
            yellow = red = 0
            for y in range(hy0, min(hy0 + 40, hy1 + 1)):
                for x in range(0, w, 2):
                    r, g, b = px[x, y][:3]
                    if r > 180 and g > 160 and b < 140:
                        yellow += 1
                    elif r > 140 and g < 100 and b < 100:
                        red += 1
            check("timer_bar", yellow + red > 15,
                  f"yellow={yellow} red={red}", required=True)

    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ascii", nargs=2, type=int, metavar=("Y0", "Y1"))
    ap.add_argument("--expect-bar", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    res = analyze(args.path, expect_bar=args.expect_bar, strict=args.strict)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"Screenshot: {res['file']} {res['size'][0]}x{res['size'][1]}")
        for c in res["checks"]:
            if c["ok"]:
                mark = "PASS"
            elif c["required"]:
                mark = "FAIL"
            else:
                mark = "WARN"
            print(f"  {mark}  {c['name']:14s} {c['detail']}")
        print(f"Overall: {'PASS' if res['pass'] else 'FAIL'}")

    if args.ascii:
        ascii_art(args.path, args.ascii[0], args.ascii[1])

    sys.exit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
