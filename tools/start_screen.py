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

In addition to the playfield canvas the bank1 menu draws ONE or more lines of
THIN SPRITE TEXT using the "text24" technique (see docs/examples/text24.asm:
two 8-px sprites, NUSIZ=$06 double size, VDEL shadow registers, two frames
that alternate the 24 character slots -> 1-color-clock text resolution). This
script pulls the 5-row glyph strips out of the reference font table and emits
them as StartText24Left/StartText24Right (same layout as text24.asm's
left_text/right_text: one glyph's 5 rows contiguous, char code = index*5),
plus the padded 24-byte tag strings MenuPromptText/MenuCreditsText.

Fonts (all hand-designed bitmaps, 1 cell per dot - NOT column-derivations):
  F5x7  title font, 1-cell letterspacing (SAVIOR / 2600, colored orange)
  F3x5  body font, 1-cell letterspacing (copyright / studio credits)
  F34   small thin prompt font, 1-cell letterspacing (PRESS FIRE / TO START)
"""

import re
from pathlib import Path

ROWS = 192
COLS = 40

# text24 sprite-text reference: its font tables live in docs/examples/text24.asm
# (part of the johnidm/asm-atari-2600 collection; see docs/README.md). We read
# the ordered glyph names + 5-row strips here so the ROM's 5-byte char codes
# match the reference kernel's expectations exactly.
TEXT24_SRC = Path(__file__).resolve().parent.parent / "docs/examples/text24.asm"

# Two 24-slot sprite-text lines: the credited studio line and the fire prompt.
# The reference renders 24 character slots per line; short strings are padded
# with spaces so all lines occupy the same centered slot span (slots 3..20).
# "(C) 2026 UPPERLAND" and "PRESS FIRE TO START" are both 18 glyphs.
MENU_LINES = {
    "credits": "(C) 2026 UPPERLAND",
    "prompt": "PRESS FIRE TO START",
}
MENU_LINE_SLOTS = 24


def load_text24_font(src: Path):
    """Parse text24.asm's text_data section: ordered (char, code, [5 rows],
    [5 rows]) per glyph. Code = index*5 like the reference."""
    text = src.read_text()
    lines = text.splitlines()

    def line_of(pat):
        for i, ln in enumerate(lines):
            if re.match(pat, ln):
                return i
        raise ValueError(f"{pat!r} not found in {src.name}")

    seg = lines[line_of(r"^left_text$") : line_of(r"^right_text$")]
    seg = [ln.split(";")[0] for ln in seg]       # ignore commented glyphs
    seg_text = "\n".join(seg)
    labels = re.findall(r"^\s*(\w+)\s*=\s*\*\s*-\s*text_data", seg_text, re.M)
    strips = [int(b, 2) for b in re.findall(r"\.byte\s+%([01]+)", seg_text)]
    labels = [l for l in labels if l != "text_data_height"]
    assert len(labels) == len(strips) // 5, (len(labels), len(strips))
    left_rows = [strips[i * 5 : i * 5 + 5] for i in range(len(labels))]

    # same glyphs, right strips, from the right_text section (no height
    # constant there; the strip column ends at the final ROM-banner ECHO)
    r0 = line_of(r"^right_text$")
    r1 = line_of(r"^.*ECHO ")
    seg_r = [ln.split(";")[0] for ln in lines[r0:r1]]
    strips_r = [int(b, 2) for b in re.findall(r"\.byte\s+%([01]+)", "\n".join(seg_r))]
    assert len(labels) == len(strips_r) // 5, (len(labels), len(strips_r))

    # label -> output char
    def ch(lab):
        if lab.startswith("__") and len(lab) == 3:
            return lab[2]                      # __A .. __Z, __0 .. __9
        return {
            "_sp": " ", "_pd": ".", "_qu": "?", "_ex": "!",
            "_cm": ",", "_hy": "-", "_pl": "+", "_ap": "'",
            "_lp": "(", "_rp": ")", "_co": ":", "_sl": "/",
            "_eq": "=", "_qt": '"', "_tr": "^",
        }.get(lab)
    chars = []
    for i, lab in enumerate(labels):
        right = strips_r[i * 5 : i * 5 + 5]
        c = ch(lab)
        assert c is not None, lab
        chars.append((c, i * 5, left_rows[i], right))
    return chars


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


def emit(rows: list[str], output: Path,
         t24: list[int], strings: dict[str, str]) -> None:
    """Emit the bank1 tables.

    ROM budget (F6 bank, fold pads at $fd00/$fe00 force everything into the
    $f000..$fcff window): the playfield tables are emitted for rows 0..139
    ONLY (rows 140..191 are a blank canvas - the menu kernel runs the text24
    band at 140..149 and hardcodes the blank rows 150..191, so no bytes are
    spent on them). The title COLOR is derived in the kernel from the row
    number (rows 4..48 orange), so there is NO per-scanline color table.
    The sprite-text font is trimmed to the glyphs the menu lines need and
    merged into ONE 220-byte page-aligned table (left half = glyph code*1,
    right half at offset T24_FONT_RIGHT), so the band's indexed loads reach
    at most offset 219 and can never cross their page.
    """
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
        "; Rows 0..139 are emitted (title band + credits + hero art); rows 140..",
        f"; {ROWS} on screen are a blank canvas, so this file holds no bytes for",
        "; them (the text24 band covers 140..149, the kernel hardcodes 150..191).",
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

    # --- merged text24 sprite-text font (trimmed to the menu's glyphs) ---
    # One glyph = 5 contiguous rows; char code = index*5 (0..105 for 22 glyphs).
    # StartText24Font holds the LEFT strips at offsets 0..109 and the RIGHT
    # strips at offsets T24_FONT_RIGHT..T24_FONT_RIGHT+109. The band loads
    # `lda StartText24Font+{row},x` and `ora StartText24Font+{row}+T24_FONT_RIGHT`
    # with x = char code, so every load stays inside offsets 0..219 < 256, and
    # the single page-aligned table can never cross a page (the band's per-scan
    # cycle budget depends on that).
    glyphs = _T24_GLYPHS
    assert 0 < len(glyphs) * 5 == len(t24) // 2
    lines += [
        f"; text24 thin sprite text (docs/examples/text24.asm), trimmed to the",
        f"; {len(glyphs)} glyphs the menu lines use. Char code = index*5.",
        f"T24_FONT_RIGHT = {len(glyphs) * 5}",
    ]
    lines.append("    align 256")
    lines.append("StartText24Font:")
    for i in range(0, len(t24), 16):
        chunk = t24[i : i + 16]
        lines.append("    .byte " + ",".join(f"${b:02X}" for b in chunk))
    lines.append("")

    # --- 28-byte text-window tables (one per line) ---
    # The single-band kernel ALWAYS reads slot base 0 from the ZP TextBuf, so
    # the menu copies a 24-byte window into TextBuf every VBLANK:
    #   odd  Clock -> copy String[0..23]  (slot bases {0,1,4,5,...}  visible)
    #   even Clock -> copy String[2..25]  (slot bases {2,3,6,7,...}  visible)
    # String = 2 leading spaces + centered 24 chars + 2 trailing spaces.
    for label, text in strings.items():
        n = len(text)
        left_pad = (MENU_LINE_SLOTS - n) // 2
        padded = [" "] * left_pad + list(text) + [" "] * (MENU_LINE_SLOTS - n - left_pad)
        assert len(padded) == MENU_LINE_SLOTS, len(padded)
        codes = [" "] * 2 + padded + [" "] * 2
        assert len(codes) == MENU_LINE_SLOTS + 4
        final = []
        for c in codes:
            for entry in glyphs:
                if entry[0] == c:
                    final.append(entry[1])
                    break
            else:
                raise ValueError(f"char {c!r} not in text24 font for {label}")
        lines += [
            f"; text24 window {label!r}: {text!r} centered in {MENU_LINE_SLOTS} chars",
            f"; + 2-space margins. Odd frames copy [0..24), even [2..26).",
            f"Menu{label[0].upper()}{label[1:]}String:",
            "    .byte " + ",".join(f"${c:02X}" for c in final),
            "",
        ]
    output.write_text("\n".join(lines) + "\n")


# filled by main(); kept module-level so emit() can look up char codes
_T24_GLYPHS: list = []


if __name__ == "__main__":
    _T24_GLYPHS.extend(load_text24_font(TEXT24_SRC))
    # trim the font down to the glyphs the two menu lines actually use (the
    # F6 bank has no room for 51*2*5 = 510 bytes of unused glyph strips)
    needed = {c for line in MENU_LINES.values() for c in line} | {" "}
    _T24_GLYPHS = [g for g in _T24_GLYPHS if g[0] in needed]
    assert len(_T24_GLYPHS) <= 51
    # merged table: left strips then right strips
    t24 = [r for _, _, left, _ in _T24_GLYPHS for r in left] + \
          [r for _, _, _, right in _T24_GLYPHS for r in right]
    assert len(t24) == 2 * len(_T24_GLYPHS) * 5
    strings = {name: MENU_LINES[name] for name in MENU_LINES}
    grid, _ = build()
    out = Path("generated/start_screen.asm")
    out.parent.mkdir(exist_ok=True)
    emit(grid[:ROWS], out, t24, strings)
    print(f"start screen: {out} ({out.stat().st_size} bytes)"
          f", text24 glyphs={len(_T24_GLYPHS)}, lines={list(strings)}")