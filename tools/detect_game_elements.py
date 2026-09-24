#!/usr/bin/env python3
"""Detect game elements in Atari 2600 screenshots."""
import sys
from PIL import Image

def check_playfield(pixels, w, h):
    """Cave playfield: must have BOTH open rows AND rows with passages."""
    open_rows = 0
    passage_rows = 0
    for y in range(80, int(h * 0.7)):
        in_wall = False
        wall_spans = []
        wall_start = 0
        for x in range(80, 720, 2):
            r, g, b = pixels[x, y][:3]
            is_wall = (r > 30 and g > 40) or (r > 80 and g < 50 and b > 100)
            if is_wall and not in_wall:
                wall_start = x
                in_wall = True
            elif not is_wall and in_wall:
                wall_spans.append((wall_start, x))
                in_wall = False
        if in_wall:
            wall_spans.append((wall_start, 720))
        if len(wall_spans) == 0:
            open_rows += 1
        elif len(wall_spans) >= 3:
            passage_rows += 1
    ok = open_rows > 5 and passage_rows > 5
    return ok, f"open={open_rows} passage={passage_rows}"

def check_player(pixels, w, h):
    """Player: non-wall bright pixel anywhere on screen."""
    count = 0
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y][:3]
            is_wall = (r > 30 and g > 40 and b < 30)
            is_bright = (r > 150 and g > 100)
            if is_bright and not is_wall:
                count += 1
    return count > 50, f"{count} px"

def check_hud(pixels, w, h):
    """HUD: grey band anywhere on screen."""
    rows = 0
    for y in range(h):
        gc = sum(1 for x in range(w//4, 3*w//4) if 30 < pixels[x,y][0] < 120)
        if gc > w // 8:
            rows += 1
    return rows > 100, f"{rows} grey rows"

def check_level(pixels, w, h):
    """Level text: white pixels in the FAR LEFT area only (not spanning center)."""
    row_counts = {}
    for y in range(30, 100):
        count = sum(1 for x in range(0, w//4) if all(c > 150 for c in pixels[x, y][:3]))
        if count > 3:
            row_counts[y] = count
    if not row_counts:
        return False, "no white rows in far-left"
    rows = sorted(row_counts.keys())
    span = rows[-1] - rows[0] + 1
    total_rows = len(rows)
    ok = span < 20 and total_rows > 5
    return ok, f"span={span} rows={total_rows}"

def check_score(pixels, w, h):
    """Score: white pixels forming a single line in the CENTER-BOTTOM of the screen."""
    row_counts = {}
    for y in range(h//2, h):  # Score is in bottom half
        count = sum(1 for x in range(w//2-80, w//2+80)
                    if all(c > 150 for c in pixels[x, y][:3]))
        if count > 5:
            row_counts[y] = count
    if not row_counts:
        return False, "no white rows in center"
    rows = sorted(row_counts.keys())
    span = rows[-1] - rows[0] + 1
    total_rows = len(rows)
    ok = span < 15 and total_rows > 5
    return ok, f"span={span} rows={total_rows}"

def analyze(path):
    img = Image.open(path)
    px = img.load()
    w, h = img.size
    print(f'Screenshot: {w}x{h}\n')
    for name, (ok, det) in [
        ('Playfield', check_playfield(px, w, h)),
        ('Player', check_player(px, w, h)),
        ('HUD', check_hud(px, w, h)),
        ('Level', check_level(px, w, h)),
        ('Score', check_score(px, w, h)),
    ]:
        print(f'{name:10s}: {"PASS" if ok else "FAIL"} - {det}')

if __name__ == '__main__':
    analyze(sys.argv[1])
