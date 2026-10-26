#!/usr/bin/env python3
"""Convert Atari 2600 screenshot to ASCII art for visual verification.

Usage: python3 tools/screenshot_to_ascii.py <screenshot.png> [y_start] [y_end] [threshold]

Always use this after taking a Stella screenshot to VERIFY what actually renders.
Never trust analysis scripts alone — READ THE ASCII OUTPUT.
"""
import sys
from PIL import Image

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <screenshot.png> [y_start] [y_end] [threshold]")
        sys.exit(1)

    path = sys.argv[1]
    y_start = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    y_end = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    threshold = int(sys.argv[4]) if len(sys.argv) > 4 else 180

    img = Image.open(path)
    pixels = img.load()
    w, h = img.size

    # Find the actual content bounds
    actual_y_start = max(0, min(y_start, h - 1))
    actual_y_end = min(h, y_end)

    # Scale: map 160 TIA color clocks to terminal width
    # Stella screenshots are ~800px wide, so ~5px per color clock
    # We'll show every other pixel to fit in terminal
    x_scale = 2  # show every Nth pixel

    print(f"Screenshot: {path} ({w}x{h})")
    print(f"Row range: y={actual_y_start}-{actual_y_end}, threshold={threshold}")
    print(f"X scale: every {x_scale}th pixel")
    print()

    # Print x-axis ruler
    ruler = ""
    for x in range(0, min(w, 160 * 5), 5 * x_scale):
        tia_x = x // 5
        if tia_x % 10 == 0:
            ruler += f"{tia_x:>3}"
        elif tia_x % 5 == 0:
            ruler += "  ."
        else:
            ruler += "   "
    print(f"TIA: {ruler}")
    print("    " + "-" * (len(ruler) - 3))

    for y in range(actual_y_start, actual_y_end):
        line = f"{y:>3}|"
        for x in range(0, min(w, 160 * 5), x_scale):
            r, g, b = pixels[x, y][:3]
            brightness = (r + g + b) / 3
            if brightness > 220:
                line += "\033[97m#\033[0m"  # bright white
            elif brightness > threshold:
                line += "\033[93m+\033[0m"  # dim yellow
            elif brightness > 60:
                line += "\033[90m.\033[0m"  # dark gray
            else:
                line += " "
        print(line)

    # Print character detection
    print()
    print("=== Character detection (bright columns) ===")
    for y in range(actual_y_start, actual_y_end):
        bright_x = []
        for x in range(0, min(w, 160 * 5)):
            r, g, b = pixels[x, y][:3]
            if (r + g + b) / 3 > threshold:
                bright_x.append(x // 5)  # TIA color clock
        if bright_x:
            # Group consecutive
            groups = []
            cur = [bright_x[0]]
            for i in range(1, len(bright_x)):
                if bright_x[i] - bright_x[i-1] <= 2:
                    cur.append(bright_x[i])
                else:
                    groups.append(cur)
                    cur = [bright_x[i]]
            groups.append(cur)
            desc = ", ".join(f"[{g[0]}-{g[-1]}]({g[-1]-g[0]+1})" for g in groups)
            print(f"  y={y}: {desc}")

if __name__ == "__main__":
    main()
