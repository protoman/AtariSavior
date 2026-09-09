#!/usr/bin/env python3
"""Generate the asymmetric-playfield start screen for the bank1 menu.

The TIA has no text capability; the menu renders each scanline as FULL-WIDTH
playfield data with the classic asymmetric trick: write the left 20 cells
during HBLANK, then RE-write the right 20 cells mid-line. CTRLPF is 0 while
the menu is shown so the mid-line rewrites win. One playfield cell = 4 color
clocks, so every dot in the fonts/art below is exactly one cell wide and one
SCANLINE tall; the compositions use vertical scaling (vscale) to get near-
square proportions on a real TV (a 4-clock cell reads roughly square when
drawn ~3 scanlines tall).

This script composes a 40 x 192 cell canvas, then converts each row into the
six PF bytes the kernel pokes per scanline (left 20 cells -> PF0 bits 4-7,
PF1 bits 7-0, PF2 bits 0-7; right 20 cells -> same mapping). Six 192-byte
tables are emitted, each page-aligned so the kernel's indexed loads never
cross a page.

Font: the SAME lowercase 13_plus2 sprite font as the HUD (tools/font.py,
3x5 glyphs, 1-cell letterspacing). The title/2600 are drawn at scale 3,
the copyright line at scale 2, the prompt at scale 2 - matching the
uppercase fonts they replace, so the menu and HUD share one letterform.
"""

from pathlib import Path

from font import glyph_rows, PRIORITY

ROWS = 192
COLS = 40


# The lowercase 13_plus2 font shared with the HUD (font.py), 3x5 glyphs.
LC = {c: glyph_rows(c) for c in PRIORITY}

# White for the non-title text, orange (hue 2 luma 4 => $28) for the title.
COLOR_PLAIN = 0x0E
COLOR_TITLE = 0x28


def line_text(text, font, gap=0):
    """Return the concatenated bitmap rows for a string (gap empty cells
    between glyphs). Raises if the line is wider than COLS."""
    glyphs = [font[c] for c in text]
    rows = []
    h = len(glyphs[0])
    for r in range(h):
        bits = ""
        for i, g in enumerate(glyphs):
            if i:
                bits += "." * gap
            bits += g[r]
        rows.append(bits)
    w = len(rows[0])
    if w > COLS:
        raise ValueError(f"line too wide ({w} > {COLS}): {text!r}")
    return rows, w


def poke(grid, rows, x, y):
    for i, r in enumerate(rows):
        if y + i >= ROWS:
            break
        target = grid[y + i]
        for c, bit in enumerate(r):
            if bit == "X":
                target[x + c] = "X"


def hero_art():
    """A HERO-style jetpack guy (facing right), drawn once per scanline.
    Playfield cells are ~4 color clocks wide, so the drawing is deliberately
    a wide/bold silhouette to read well at this low resolution."""
    g = [list("." * COLS) for _ in range(34)]

    def rect(x0, y0, x1, y1):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                g[y][x] = "X"

    # helmet (rounded, corners cut)
    rect(13, 2, 27, 8)
    g[2][13] = g[2][27] = "."
    # visor band with a dark eye opening
    rect(15, 4, 24, 5)
    for y in (4, 5):
        for x in (17, 18):
            g[y][x] = "."
    # neck
    rect(18, 9, 21, 10)

    # torso + belt
    rect(16, 10, 24, 20)
    rect(18, 13, 20, 15)          # chest light (dark hole)
    for x in range(17, 24):
        g[19][x] = "."            # belt slit

    # front arm (hanging, with hand)
    rect(26, 10, 28, 20)
    rect(26, 21, 28, 22)

    # back shoulder
    rect(14, 10, 15, 12)

    # jetpack: twin tanks behind, strap to the belt
    rect(3, 11, 8, 21)
    for y in range(12, 21):
        g[y][5] = "."             # divider -> two tanks
    rect(4, 22, 7, 23)            # exhaust nozzle
    rect(9, 19, 15, 20)           # belt strap

    # legs (split) + boots
    rect(17, 21, 18, 26)
    rect(20, 21, 21, 26)
    rect(15, 27, 18, 29)
    rect(20, 27, 23, 29)

    return ["".join(r) for r in g]


def build():
    grid = [list("." * COLS) for _ in range(ROWS)]

    def center(rows, w):
        return (COLS - w) // 2

    def place(text, font, y, scale, gap=1):
        rows, w = line_text(text, font, gap)
        scaled = []
        for r in rows:
            scaled += [r] * scale
        poke(grid, scaled, center(rows, w), y)
        return len(scaled)

    # --- title: savior / 2600 in the lowercase HUD font (orange band 4..48) ---
    place("savior", LC, 4, 3)
    place("2600", LC, 26, 3)

    # --- copyright ---
    place("(c) 2026", LC, 58, 2)
    place("upperland", LC, 72, 2)

    # --- hero art ---
    poke(grid, hero_art(), 0, 98)

    # --- fine menu text ---
    place("press fire", LC, 140, 2)
    place("to start", LC, 154, 2)

    colors = [COLOR_TITLE if 4 <= y <= 48 else COLOR_PLAIN for y in range(ROWS)]
    return ["".join(r) for r in grid], colors


def pf_bytes(row):
    """Left 20 cells + right 20 cells -> (PF0L, PF1L, PF2L, PF0R, PF1R, PF2R).

    TIA mapping (verified in convert_room.py):
      cols 0-3   -> PF0 bits 4-7 (col0 -> bit4)
      cols 4-11  -> PF1 bits 7-0 (col4 -> bit7)
      cols 12-19 -> PF2 bits 0-7 (col12 -> bit0)
    The right half re-uses the same mapping for cols 20-39.
    """
    solid = [c == "X" for c in row]
    out = []
    for base in (0, 20):
        pf0 = 0
        for i in range(4):
            if solid[base + i]:
                pf0 |= 0x10 << i
        pf1 = 0
        for i in range(8):
            if solid[base + 4 + i]:
                pf1 |= 0x80 >> i
        pf2 = 0
        for i in range(8):
            if solid[base + 12 + i]:
                pf2 |= 0x01 << i
        out += [pf0, pf1, pf2]
    return out


def emit(rows: list[str], output: Path) -> None:
    """Emit the bank1 start-screen tables.

    All 192 rows are emitted as six scanline tables (PF0L/PF1L/PF2L for the
    left half, PF0R/PF1R/PF2R for the right), each page-aligned so the
    kernel's indexed loads never cross a page. The title color is derived in
    the kernel from the row number (rows 4..48 orange), so there is NO
    per-scanline color table; StartScreenColors is kept as a single 192-byte
    row-color table the kernel reads once per scanline."""
    assert len(rows) > 0
    tables = {"PF0L": [], "PF1L": [], "PF2L": [], "PF0R": [], "PF1R": [], "PF2R": []}
    for row in rows:
        p0, p1, p2, q0, q1, q2 = pf_bytes(row)
        tables["PF0L"].append(p0)
        tables["PF1L"].append(p1)
        tables["PF2L"].append(p2)
        tables["PF0R"].append(q0)
        tables["PF1R"].append(q1)
        tables["PF2R"].append(q2)
    n_pf = len(rows)

    lines = [
        "; Start screen: full-width asymmetric playfield bitmap, one entry per",
        "; playfield scanline. The menu kernel writes the left table during",
        "; HBLANK and the right table mid-line after the left half has been drawn.",
        "; COLUPF is NOT table-driven: the menu kernel derives it from the row",
        f"; number (orange {COLOR_TITLE:02X} for rows 4..48, else {COLOR_PLAIN:02X}).",
        "; Generated by tools/start_screen.py - do not edit by hand.",
        f"START_SCREEN_LINES = {n_pf}",
        f"START_SCREEN_ROWS = {ROWS}",
        "",
    ]
    for name in ("PF0L", "PF1L", "PF2L", "PF0R", "PF1R", "PF2R"):
        lines.append(f"StartScreen{name}:")
        vals = tables[name]
        for i in range(0, len(vals), 16):
            chunk = vals[i : i + 16]
            lines.append("    .byte " + ",".join(f"${b:02X}" for b in chunk))
        lines.append("")

    lines.append("StartScreenColors:")
    colors = [0x28 if 4 <= y <= 48 else 0x0E for y in range(ROWS)]
    for i in range(0, len(colors), 16):
        chunk = colors[i : i + 16]
        lines.append("    .byte " + ",".join(f"${b:02X}" for b in chunk))
    lines.append("")
    output.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    grid, _ = build()
    out = Path("generated/start_screen.asm")
    out.parent.mkdir(exist_ok=True)
    emit(grid[:ROWS], out)
    print(f"start screen: {out} ({out.stat().st_size} bytes)")