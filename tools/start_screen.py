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

Fonts (all hand-designed bitmaps, 1 cell per dot - NOT column-derivations):
  F5x7  title font, 1-cell letterspacing (SAVIOR / 2600, colored orange)
  F3x5  body font, 1-cell letterspacing (copyright / studio credits)
  F34   small thin prompt font, 1-cell letterspacing (PRESS FIRE / TO START)
"""

from pathlib import Path

ROWS = 192
COLS = 40


# ---------------------------------------------------------------------------
# F5x7 title font (rows are single strings of X and .). Used for SAVIOR/2600.
# ---------------------------------------------------------------------------
F5 = {
    "A": ("..X..", ".X.X.", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "I": ("XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "XXXXX"),
    "O": ("XXXXX", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXXX"),
    "R": ("XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"),
    "S": (".XXX.", "X...X", "X....", ".XXX.", "....X", "X...X", ".XXX."),
    "V": ("X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."),
    "0": ("XXXXX", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXXX"),
    "2": ("XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"),
    "6": ("XXXXX", "X....", "X....", "XXXXX", "X...X", "X...X", "XXXXX"),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
}


# ---------------------------------------------------------------------------
# F3x5 body font (3 columns x 5 rows), 1-cell letterspacing at render time.
# ---------------------------------------------------------------------------
F3 = {
    "A": (".X.", "X.X", "XXX", "X.X", "X.X"),
    "B": ("XX.", "X.X", "XX.", "X.X", "XX."),
    "C": ("XX.", "X..", "X..", "X..", "XX."),
    "D": ("XX.", "X.X", "X.X", "X.X", "XX."),
    "E": ("XXX", "X..", "XXX", "X..", "XXX"),
    "F": ("XXX", "X..", "XXX", "X..", "X.."),
    "I": ("XXX", ".X.", ".X.", ".X.", "XXX"),
    "L": ("X..", "X..", "X..", "X..", "XXX"),
    "M": ("X.X", "XXX", "XXX", "X.X", "X.X"),
    "N": ("X.X", "XXX", "XX.", "X.X", "X.X"),
    "O": ("XXX", "X.X", "X.X", "X.X", "XXX"),
    "P": ("XX.", "X.X", "XX.", "X..", "X.."),
    "R": ("XX.", "X.X", "XXX", "X.X", "X.X"),
    "S": ("XXX", "X..", "XXX", "..X", "XXX"),
    "T": ("XXX", ".X.", ".X.", ".X.", ".X."),
    "U": ("X.X", "X.X", "X.X", "X.X", "XXX"),
    "V": ("X.X", "X.X", "X.X", "X.X", ".X."),
    "W": ("X.X", "XXX", "XXX", "X.X", "X.X"),
    "0": ("XXX", "X.X", "X.X", "X.X", "XXX"),
    "2": ("XXX", "..X", "XXX", "X..", "XXX"),
    "6": ("XX.", "X..", "XXX", "X.X", "XXX"),
    "(": (".X.", "X..", "X..", "X..", ".X."),
    ")": (".X.", "..X", "..X", "..X", ".X."),
    "/": ("..X", "..X", ".X.", "X..", "X.."),
    " ": ("...", "...", "...", "...", "..."),
}


# ---------------------------------------------------------------------------
# F3x4 prompt font (3 columns x 4 rows), 1-cell letterspacing: smaller and
# thinner than F3 ("PRESS FIRE" / "TO START" at scale 3 = 12 rows tall).
# ---------------------------------------------------------------------------
F34 = {
    "A": (".X.", "X.X", "XXX", "X.X"),
    "E": ("XXX", "X..", "XX.", "XXX"),
    "F": ("XXX", "X..", "XX.", "X.."),
    "I": ("XXX", ".X.", ".X.", "XXX"),
    "O": ("XXX", "X.X", "X.X", "XXX"),
    "P": ("XXX", "X.X", "X.X", "XX."),
    "R": ("XXX", "X.X", "XX.", "X.X"),
    "S": ("XXX", "X..", "..X", "XXX"),
    "T": ("XXX", ".X.", ".X.", ".X."),
    " ": ("...", "...", "...", "..."),
}

# vscale for the prompt. Each playfield cell is hardwired 4px wide (4 color
# clocks), so a 1-scanline dot reads as a 4:1 horizontal smear no matter how
# narrow the font is. vscale 3 = near-square dots; vscale 2 = a thin font
# whose dots are still 2:1 wide (the classic TIA look). We use 2.
PROMPT_SCALE = 2

# White for the non-title text, orange (hue 2 luma 4 => $28) for SAVIOR/2600.
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

    def place(text, font, y, scale, gap=0):
        rows, w = line_text(text, font, gap)
        scaled = []
        for r in rows:
            scaled += [r] * scale
        poke(grid, scaled, center(rows, w), y)
        return len(scaled)

    # --- title: SAVIOR / 2600, big font (orange band rows 4..48) ---
    place("SAVIOR", F5, 4, 3, gap=1)
    place("2600", F5, 28, 3, gap=1)

    # --- copyright ---
    place("(C) 2026", F3, 58, 3, gap=1)
    place("UPPERLAND", F3, 76, 3, gap=1)

    # --- hero art ---
    poke(grid, hero_art(), 0, 98)

    # --- fine menu text ---
    # Draw smaller prompt using the F34 font (3 columns, gap=1) split across
    # two lines so it fits the 40-column playfield perfectly.
    place("PRESS FIRE", F34, 136, PROMPT_SCALE, gap=1)
    place("TO START", F34, 148, PROMPT_SCALE, gap=1)

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