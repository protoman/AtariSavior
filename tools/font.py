#!/usr/bin/env python3
"""Compact lowercase sprite-font generator (13_plus2 "small font" format).

Source of truth for every text glyph in the game (HUD + menu). The glyph
bitmaps come verbatim from Paul Slocum's 13 chars + 2 demo
(docs/tutorial/13_plus2.asm), which renders two overlapping sprite copies so
one interleaved byte shows two characters. Each glyph is 5 rows; fonthi holds
the left columns (bits 7/6/5), fontlo the right columns (bits 3/2/1). Codes
are 0,5,10,... = glyph index * 5, so `lda fontlo,x` with x = code returns the
glyph's first row and +1..+4 the rest. Tables are emitted as one contiguous
block (fonthi followed by fontlo) kept within one 256-byte page so no indexed
load ever crosses a page.

The demo aliases i=_1 and o=_0; this tool keeps both spellings sharing one
glyph.

Emitted file:
  {name}_font_fonthi / {name}_font_fontlo  — the tables
  CH_{NAME}_{:02X} equ per glyph code       — codes for building text tables
  {name}_texts                               — string -> code list helper table

Usage:
    font.py <name> <glyphs> <texts> <output>
      glyphs = shell-quoted glyph string, e.g. "levelscorbmti0123456789."
      texts  = semicolon-separated strings to emit as coded text tables, e.g.
               "level;score 00.000"

    font.py slots <prefix> <lines> <output>
      lines  = semicolon-separated 'label:text' pairs; each emits a 40-byte
               per-scanline slot table '{prefix}_{label}' (<=15 chars text).
"""

from pathlib import Path
import sys

# fonthi byte for each glyph, in the canonical order from the demo. A glyph's
# code == its index * 5. i and o are the demo aliases for 1 and 0.
PRIORITY = list("abcdefghijklmnopqrstuvwxyz0123456789 .,/()*=-+")

_FONTHI = {
    " ": ["00000000", "00000000", "00000000", "00000000", "00000000"],
    "a": ["10100000", "10100000", "11100000", "10100000", "01000000"],
    "b": ["11000000", "10100000", "11000000", "10100000", "11000000"],
    "c": ["01100000", "10000000", "10000000", "10000000", "01100000"],
    "d": ["11000000", "10100000", "10100000", "10100000", "11000000"],
    "e": ["11100000", "10000000", "11000000", "10000000", "11100000"],
    "f": ["10000000", "10000000", "11000000", "10000000", "11100000"],
    "g": ["01100000", "10100000", "10100000", "10000000", "01100000"],
    "h": ["10100000", "10100000", "11100000", "10100000", "10100000"],
    "1": ["01000000", "01000000", "01000000", "01000000", "01000000"],
    "j": ["10000000", "01000000", "01000000", "01000000", "11100000"],
    "k": ["10100000", "10100000", "11000000", "10100000", "10000000"],
    "l": ["11100000", "10000000", "10000000", "10000000", "10000000"],
    "m": ["10100000", "10100000", "10100000", "11100000", "10100000"],
    "n": ["10100000", "10100000", "10100000", "10100000", "11000000"],
    "0": ["01000000", "10100000", "10100000", "10100000", "01000000"],
    "p": ["10000000", "10000000", "11000000", "10100000", "11000000"],
    "q": ["01100000", "11100000", "10100000", "10100000", "01000000"],
    "r": ["10100000", "10100000", "11000000", "10100000", "11000000"],
    "s": ["11000000", "00100000", "01000000", "10000000", "01100000"],
    "t": ["01000000", "01000000", "01000000", "01000000", "11100000"],
    "u": ["01100000", "10100000", "10100000", "10100000", "10100000"],
    "v": ["01000000", "01000000", "10100000", "10100000", "10100000"],
    "w": ["10100000", "11100000", "10100000", "10100000", "10100000"],
    "x": ["10100000", "10100000", "01000000", "10100000", "10100000"],
    "y": ["01000000", "01000000", "01000000", "10100000", "10100000"],
    "z": ["11100000", "10000000", "01000000", "00100000", "11100000"],
    "2": ["11100000", "10000000", "01000000", "00100000", "11000000"],
    "3": ["11100000", "00100000", "01100000", "00100000", "11100000"],
    "4": ["00100000", "00100000", "11100000", "10100000", "10100000"],
    "5": ["11100000", "00100000", "11100000", "10000000", "11100000"],
    "6": ["01000000", "10100000", "11000000", "10000000", "01100000"],
    "7": ["10000000", "10000000", "10000000", "10000000", "11100000"],
    "8": ["11100000", "10100000", "11100000", "10100000", "11100000"],
    "9": ["01000000", "00100000", "11100000", "10100000", "11100000"],
    ".": ["00000000", "00000000", "00000000", "00000000", "01100000"],
    ",": ["00000000", "00000000", "00000000", "00001000", "00100000"],
    "/": ["10000000", "01000000", "01000000", "01000000", "00100000"],
    "(": ["00100000", "01000000", "01000000", "01000000", "00100000"],
    ")": ["10000000", "01000000", "01000000", "01000000", "10000000"],
    "*": ["10100000", "01000000", "11100000", "01000000", "10100000"],
    "=": ["00000000", "11100000", "00000000", "11100000", "00000000"],
    "+": ["00000000", "01000000", "11100000", "01000000", "00000000"],
    "-": ["00000000", "00000000", "11100000", "00000000", "00000000"],
}

_FONTLO = {
    " ": ["00000000", "00000000", "00000000", "00000000", "00000000"],
    "a": ["00001010", "00001010", "00001110", "00001010", "00000100"],
    "b": ["00001100", "00001010", "00001100", "00001010", "00001100"],
    "c": ["00000110", "00001000", "00001000", "00001000", "00000110"],
    "d": ["00001100", "00001010", "00001010", "00001010", "00001100"],
    "e": ["00001110", "00001000", "00001100", "00001000", "00001110"],
    "f": ["00001000", "00001000", "00001100", "00001000", "00001110"],
    "g": ["00000110", "00001010", "00001010", "00001000", "00000110"],
    "h": ["00001010", "00001010", "00001110", "00001010", "00001010"],
    "1": ["00000100", "00000100", "00000100", "00000100", "00000100"],
    "j": ["00001000", "00000100", "00000100", "00000100", "00001110"],
    "k": ["00001010", "00001010", "00001100", "00001010", "00001000"],
    "l": ["00001110", "00001000", "00001000", "00001000", "00001000"],
    "m": ["00001010", "00001010", "00001010", "00001110", "00001010"],
    "n": ["00001010", "00001010", "00001010", "00001010", "00001100"],
    "0": ["00000100", "00001010", "00001010", "00001010", "00000100"],
    "p": ["00001000", "00001000", "00001100", "00001010", "00001100"],
    "q": ["00000110", "00001110", "00001010", "00001010", "00000100"],
    "r": ["00001010", "00001010", "00001100", "00001010", "00001100"],
    "s": ["00001100", "00000010", "00000100", "00001000", "00000110"],
    "t": ["00000100", "00000100", "00000100", "00000100", "00001110"],
    "u": ["00000110", "00001010", "00001010", "00001010", "00001010"],
    "v": ["00000100", "00000100", "00001010", "00001010", "00001010"],
    "w": ["00001010", "00001110", "00001010", "00001010", "00001010"],
    "x": ["00001010", "00001010", "00000100", "00001010", "00001010"],
    "y": ["00000100", "00000100", "00000100", "00001010", "00001010"],
    "z": ["00001110", "00001000", "00000100", "00000010", "00001110"],
    "2": ["00001110", "00001000", "00000100", "00000010", "00001100"],
    "3": ["00001110", "00000010", "00000110", "00000010", "00001110"],
    "4": ["00000010", "00000010", "00001110", "00001010", "00001010"],
    "5": ["00001110", "00000010", "00001110", "00001000", "00001110"],
    "6": ["00000100", "00001010", "00001100", "00001000", "00000110"],
    "7": ["00001000", "00001000", "00001000", "00001000", "00001110"],
    "8": ["00001110", "00001010", "00001110", "00001010", "00001110"],
    "9": ["00001100", "00000010", "00001110", "00001010", "00001110"],
    ".": ["00000000", "00000000", "00000000", "00000000", "00000110"],
    ",": ["00000000", "00000000", "00000000", "00001000", "00000100"],
    "/": ["00000000", "00001000", "00001000", "00001000", "00000100"],
    "(": ["00000000", "00001000", "00001000", "00001000", "00000000"],
    ")": ["00000000", "00001000", "00001000", "00001000", "00000000"],
    "*": ["00001010", "00000100", "00001110", "00000100", "00001010"],
    "=": ["00000000", "00001110", "00000000", "00001110", "00000000"],
    "+": ["00000000", "00000100", "00001110", "00000100", "00000000"],
    "-": ["00000000", "00000000", "00001110", "00000000", "00000000"],
}

ALIASES = {"i": "1", "o": "0"}


def glyph_bytes(ch: str) -> tuple[list[str], list[str]]:
    ch = ALIASES.get(ch, ch)
    if ch not in _FONTHI or ch not in _FONTLO:
        raise ValueError(f"glyph {ch!r} not in the font")
    return list(_FONTHI[ch]), list(_FONTLO[ch])


def glyph_rows(ch: str) -> list[str]:
    """3x5 playfield-cell bitmap (X/.) for one glyph, taken from the demo's
    fonthi left-most three columns. Shared source: the HUD sprite slots and
    the start-screen playfield both derive from this one glyph data."""
    return ["".join("X" if b == "1" else "." for b in row[:3]) for row in glyph_bytes(ch)[0]]


def canonical(chars: str) -> list[str]:
    out = []
    for ch in chars:
        ch = ALIASES.get(ch, ch)
        if ch not in out:
            out.append(ch)
    return out


def slot_bytes(text: str) -> list[int]:
    """Precompute the 40 per-scanline RAM bytes the 13_plus2 stack build
    produces for one text line, as a ROM table for HudCopy.

    This is a faithful simulation of the demo's mainTextLoop, NOT a naive
    glyph-by-glyph layout: the built grid is a sliding window over the push
    stream, so each 5-row slot overlaps its neighbor by one row byte:

        slot k (charp+5k .. charp+5k+4) =
            pair(7-k) rows [r3, r2, r1, r0]  +  pair(6-k) row [r4]
        last slot (charg) =
            solo rows [r3, r2, r1, r0]  +  0x00  (demo's $A7 is cleared RAM)

    Address order is ascending charp..charg (= $b3..$da in this game),
    matching the demo's stack fills (highest addresses first: solo char is
    pushed first and lands in the highest slots). TEXTDISP reads exactly
    these bytes, so copying this table to charp and running RenderLine
    reproduces the demo's screen text byte-for-byte.
    """
    chars = [ALIASES.get(c, c) for c in text]
    if len(chars) > 15:
        raise ValueError(f"text {text!r} longer than 15 chars (1 solo + 7 pairs)")
    while len(chars) < 15:
        chars.append(" ")
    pairs = [(chars[i], chars[i + 1]) for i in range(1, 15, 2)]
    solo = chars[0]
    ram: dict[int, int] = {}
    addr = 0xA6

    def push(v: int) -> None:
        nonlocal addr
        ram[addr] = v
        addr -= 1

    for r in range(5):
        push(int(_FONTLO[solo][r], 2))
    for left, right in pairs:
        for r in range(5):
            push(int(_FONTHI[left][r], 2) | int(_FONTLO[right][r], 2))
    ram[0xA7] = 0
    return [ram[0x80 + m] for m in range(40)]


def _dasm_label(label: str) -> str:
    dasm = "".join(c if c.isalnum() else "_" for c in label)
    if not dasm or dasm[0].isdigit():
        raise ValueError(f"bad slot label {label!r} -> {dasm!r}")
    return dasm


def emit_slots(prefix: str, entries: list[str], output: Path) -> int:
    header = [
        f"; Generated by tools/font.py (slots mode, {prefix}). Do not edit by hand.",
        "; One 40-byte table per text line, in ZP slot order charp..charg",
        "; ($b3..$da): 8 slots x 5 rows. Each slot is the 13_plus2 sliding",
        "; window over the push stream: pair rows [r3,r2,r1,r0] + next row r4,",
        "; last slot = solo [r3,r2,r1,r0] + 0x00. Copy with HudCopy, render",
        "; with RenderLine (TEXTDISP x5); byte-identical to the demo's RAM.",
        "",
    ]
    body: list[str] = []
    total = 0
    for entry in entries:
        if not entry:
            continue
        label, sep, text = entry.partition(":")
        if not sep:
            raise ValueError(f"slot entry {entry!r} missing ':' (want 'label:text')")
        if not text:
            raise ValueError(f"slot entry {entry!r} empty text")
        body.append(f"{prefix}_{_dasm_label(label)}:")
        for i in range(0, 40, 8):
            row = slot_bytes(text)[i : i + 8]
            body.append("  .byte " + ", ".join(f"${b:02X}" for b in row))
        body.append("")
        total += 40
    output.write_text("\n".join(header + body) + "\n")
    return total


def emit(name: str, chars: str, texts: list[str], output: Path) -> tuple[int, int]:
    glyphs = canonical(chars)
    glyphs.sort(key=lambda g: PRIORITY.index(g) if g in PRIORITY else 255)
    if len(glyphs) * 5 > 128:
        raise ValueError(
            f"{name}: {len(glyphs)} glyphs * 5 = {len(glyphs)*5} > 128 bytes; "
            "fonthi+fontlo must stay within one 256-byte page"
        )

    lines = [
        f"; Generated by tools/font.py ({name}). Do not edit by hand.",
        f"; Compact lowercase sprite font ({len(glyphs)} glyphs, 5 bytes each).",
        "; Glyph codes are 0,5,10,... = offset into fonthi/fontlo, so",
        "; `lda fontlo,x` with x = code loads row 0, +1..+4 the rest.",
        "; fonthi and fontlo are emitted contiguous inside one page so",
        "; indexed loads never cross a page boundary.",
        f"; Glyphs: {''.join(glyphs)}",
        "",
        f"; --- {name}: glyph codes ---",
    ]
    for code, ch in enumerate(glyphs):
        lines.append(f"CH_{name.upper()}_{ord(ch):02X} EQU {code * 5}")
    lines.append("")
    lines.append(f"{name}_font_fonthi:")
    for ch in glyphs:
        hi, _ = glyph_bytes(ch)
        lines.append("  .byte " + ", ".join(f"%{b}" for b in hi))
    lines.append("")
    lines.append(f"{name}_font_fontlo:")
    for ch in glyphs:
        _, lo = glyph_bytes(ch)
        lines.append("  .byte " + ", ".join(f"%{b}" for b in lo))

    table = dict((ch, i * 5) for i, ch in enumerate(glyphs))
    size_texts = 0
    for text in texts:
        if not text:
            continue
        codes = [table[ALIASES.get(c, c)] for c in text]
        size_texts += len(codes) + 1
        sym = f"{name}_text_{text.replace(' ', '_')}"
        lines.append("")
        lines.append(f"{sym}:")
        lines.append("  .byte " + ", ".join(str(c) for c in codes) + ", 0")

    output.write_text("\n".join(lines) + "\n")
    return len(glyphs) * 5, size_texts


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "slots":
        if len(args) != 4:
            print("usage: font.py slots <prefix> <lines> <output>", file=sys.stderr)
            print("  lines = 'label:text;label:text' (text <= 15 chars)", file=sys.stderr)
            return 2
        _, prefix, texts, out = args
        try:
            total = emit_slots(prefix, texts.split(";"), Path(out))
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print(f"slots: {total} bytes -> {out}")
        return 0
    if len(args) != 4:
        print("usage: font.py <name> <glyphs> <texts> <output>", file=sys.stderr)
        print("  texts = semicolon-separated strings ('' for none)", file=sys.stderr)
        return 2
    name, glyphs, texts = args[0], args[1], args[2]
    out = args[3]
    try:
        font, strings = emit(name, glyphs, texts.split(";"), Path(out))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"{name}: font {font} bytes + {strings} text bytes -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())