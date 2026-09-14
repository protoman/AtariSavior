#!/usr/bin/env python3
"""Detect game elements in Atari 2600 screenshots.
Checks for actual PATTERNS, not just color presence.
"""
import sys
from PIL import Image

def check_playfield(pixels, w, h):
    """Cave playfield: colored wall pixels on left and/or right sides of screen."""
    # Sample pixel colors in the cave area to find the wall color
    wall_colors = {}
    for y in range(h // 4, h * 3 // 4):
        for x in range(0, w, 5):
            r, g, b = pixels[x, y][:3]
            if (r, g, b) != (0, 0, 0) and (r, g, b) != (7, 7, 7):
                key = (r // 30, g // 30, b // 30)
                wall_colors[key] = wall_colors.get(key, 0) + 1

    if not wall_colors:
        return False, "no non-black pixels"

    # Most common non-black color is likely the wall
    wall_color_rgb, wall_count = max(wall_colors.items(), key=lambda x: x[1])
    wall_r, wall_g, wall_b = wall_color_rgb[0]*30, wall_color_rgb[1]*30, wall_color_rgb[2]*30

    # Count wall pixels on left and right halves
    left = sum(1 for y in range(h//4, h*3//4) for x in range(0, w//2, 3)
               if abs(pixels[x,y][0]-wall_r) < 40 and abs(pixels[x,y][1]-wall_g) < 40 and abs(pixels[x,y][2]-wall_b) < 40)
    right = sum(1 for y in range(h//4, h*3//4) for x in range(w//2, w, 3)
                if abs(pixels[x,y][0]-wall_r) < 40 and abs(pixels[x,y][1]-wall_g) < 40 and abs(pixels[x,y][2]-wall_b) < 40)

    ok = left > 500 and right > 500
    return ok, f"wall=rgb({wall_r},{wall_g},{wall_b}) left={left} right={right} px"

def check_player(pixels, w, h):
    """Player: yellow/orange square ANYWHERE on screen."""
    count = 0
    min_x, max_x, min_y, max_y = w, 0, h, 0
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y][:3]
            if r > 200 and g > 140 and b < 80:
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                count += 1
    ok = count > 10
    return ok, f"{count} px at ({min_x}-{max_x}, {min_y}-{max_y})"

def check_hud(pixels, w, h):
    """HUD: grey band in bottom 30% of screen."""
    rows = 0
    for y in range(int(h*0.7), h):
        gc = sum(1 for x in range(w//4, 3*w//4) if all(c > 80 for c in pixels[x,y][:3]))
        if gc > w // 8:
            rows += 1
    return rows > 10, f"{rows} grey rows"

def check_level(pixels, w, h):
    """Level text: white/light pixels in top-left area of screen."""
    count = sum(1 for y in range(30, 80) for x in range(w//4, w//2)
                if all(c > 150 for c in pixels[x,y][:3]))
    return count > 5, f"{count} white pixels"

def check_score(pixels, w, h):
    """Score: white pixels near center-top of screen."""
    count = sum(1 for y in range(30, 80) for x in range(w//2-60, w//2+60)
                if all(c > 150 for c in pixels[x,y][:3]))
    return count > 10, f"{count} white pixels"

def analyze(path):
    img = Image.open(path)
    px = img.load()
    w, h = img.size
    print(f'Screenshot: {w}x{h}\n')
    checks = [
        ('Playfield', check_playfield(px, w, h)),
        ('Player', check_player(px, w, h)),
        ('HUD', check_hud(px, w, h)),
        ('Level', check_level(px, w, h)),
        ('Score', check_score(px, w, h)),
    ]
    for name, (ok, detail) in checks:
        print(f'{name:10s}: {"PASS" if ok else "FAIL"} - {detail}')
    print(f'\nOverall: {"PASS" if all(ok for _,(ok,_) in checks) else "FAIL"}')

if __name__ == '__main__':
    analyze(sys.argv[1])
