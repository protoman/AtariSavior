#!/usr/bin/env python3
"""Analyze Atari 2600 game screenshots to verify game elements are present.

Usage: python3 tools/analyze_screenshot.py <screenshot.png>

Reports presence/absence of:
- Playfield (cave walls)
- HUD background
- HUD text (LEVEL, score)
- Player sprite
- Enemies
"""
import sys
from PIL import Image

def classify(r, g, b):
    """Classify a pixel into a game element category."""
    if r == 0 and g == 0 and b == 0:
        return 'black'
    if r < 10 and g < 10 and b < 10:
        return 'near_black'
    # Cave walls (green)
    if 35 < r < 55 and 70 < g < 100 and 10 < b < 30:
        return 'cave_green'
    # HUD background (grey)
    if 48 < r < 62 and 48 < g < 62 and 48 < b < 62:
        return 'hud_grey'
    # White text (LEVEL, score)
    if r > 200 and g > 200 and b > 200:
        return 'white_text'
    # Player sprite (orange/yellow)
    if r > 200 and g > 140 and b < 80:
        return 'player'
    # Enemy colors
    if r > 220 and g > 70 and g < 100 and b > 60 and b < 90:
        return 'enemy_red'
    if r > 100 and g > 180 and b > 170:
        return 'enemy_cyan'
    return f'other({r},{g},{b})'

def analyze(path):
    img = Image.open(path)
    pixels = img.load()
    w, h = img.size
    print(f'Screenshot: {w}x{h}\n')
    
    # Count pixels per category
    cats = {}
    for y in range(h):
        for x in range(0, w, 2):
            c = classify(*pixels[x, y][:3])
            cats[c] = cats.get(c, 0) + 1
    
    print('Pixel counts:')
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        if count > 10:
            print(f'  {cat:20s}: {count:6d} px')
    
    # Find player bounding box
    player_xs, player_ys = [], []
    for y in range(h):
        for x in range(w):
            r,g,b = pixels[x,y][:3]
            if r > 200 and g > 140 and b < 80:
                player_xs.append(x)
                player_ys.append(y)
    if player_xs:
        print(f'\nPlayer bbox: x={min(player_xs)}-{max(player_xs)}, y={min(player_ys)}-{max(player_ys)}')
        print(f'  Size: {max(player_xs)-min(player_xs)+1}x{max(player_ys)-min(player_ys)+1} px')
    else:
        print('\nPlayer: NOT FOUND')
    
    # Health check
    has_cave = cats.get('cave_green', 0) > 1000
    has_hud = cats.get('hud_grey', 0) > 100
    has_text = cats.get('white_text', 0) > 10
    has_player = cats.get('player', 0) > 10
    
    print(f'\n=== Health Check ===')
    print(f'  Playfield (cave): {"OK" if has_cave else "MISSING"} ({cats.get("cave_green", 0)} px)')
    print(f'  HUD background:   {"OK" if has_hud else "MISSING"} ({cats.get("hud_grey", 0)} px)')
    print(f'  HUD text:         {"OK" if has_text else "MISSING"} ({cats.get("white_text", 0)} px)')
    print(f'  Player sprite:    {"OK" if has_player else "MISSING"} ({cats.get("player", 0)} px)')
    
    ok = has_cave and has_hud and has_text and has_player
    print(f'\n  Overall: {"PASS" if ok else "FAIL"}')
    return ok

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <screenshot.png>')
        sys.exit(1)
    ok = analyze(sys.argv[1])
    sys.exit(0 if ok else 1)
