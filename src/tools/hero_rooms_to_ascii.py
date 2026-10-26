#!/usr/bin/env python3
"""Extract HERO's cave rooms as ASCII straight from ROM (no screenshots).

How HERO draws caves (docs/asymmetric_pf_plan.md "HERO verification" +
docs/hero/hero_bank0.asm:59-60,232-233): PF0/PF1/PF2 written at band
boundaries only, reflect ON (CTRLPF $35), left half = PF0/1/2 (20 TIA px
= 10 cells of 2 px), right half = hardware mirror.

Steps:
  1. run hero.bin under py65 (Probe from probe_hero_overlay.py),
  2. collect PF0/PF1/PF2 writes during cave lines per frame,
  3. rebuild one ASCII row per band write-group (PF triplet),
  4. decode: cell c = PF px(2c..2c+1), wall iff both px set;
     full row = left 10 cells + mirrored right 10,
  5. dedupe frames -> unique rooms; print as ASCII blocks.

Usage: tools/hero_rooms_to_ascii.py [frames] [out.md]   (default 600)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_hero_overlay import Probe, default_input, ROM_PATH, CAVE_LO, CAVE_HI  # noqa: E402

# PF px (0..19) -> bit source
def px_bits(pf0, pf1, pf2):
    px = [0] * 20
    for i in range(4):                      # PF0: bit4 = leftmost
        px[0 + i] = (pf0 >> (4 + i)) & 1
    for i in range(8):                      # PF1: bit7 = leftmost
        px[4 + i] = (pf1 >> (7 - i)) & 1
    for i in range(8):                      # PF2: bit0 = leftmost
        px[12 + i] = (pf2 >> i) & 1
    return px


def decode_row(pf0, pf1, pf2):
    """(PF0,PF1,PF2) -> 20-char ASCII (left 10 cells + mirrored right)."""
    px = px_bits(pf0, pf1, pf2)
    left = []
    for c in range(10):
        both = px[2 * c] & px[2 * c + 1]
        either = px[2 * c] | px[2 * c + 1]
        if both != either:                  # half-cell -> mark with %, count
            left.append("%" if either else ".")
        else:
            left.append("#" if both else ".")
    left_s = "".join(left)
    return left_s + left_s[::-1], left_s


def collect(p, cave_lo, cave_hi):
    """per frame: ordered PF write groups during cave lines."""
    groups = {}   # f -> list of (line, pf0, pf1, pf2) latest values
    cur = {}
    last_line = {}
    for (f, ln, ph, nm, val, _pc) in p.events:
        if nm not in ("PF0", "PF1", "PF2"):
            continue
        if not (cave_lo <= ln <= cave_hi):
            continue
        if ln not in cur or ln > max(cur):  # new line -> close previous group
            pass
        cur.setdefault(f, {})
        # group by scanline: line -> {reg: val}
        cur[f].setdefault(ln, {})[nm] = val
    return cur


def main():
    nframes = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    rom = ROM_PATH.read_bytes()
    p = Probe(rom)
    p.run(nframes, input_fn=default_input)

    print(f"frames={p.frame} events={len(p.events)}")

    # raw: PF write lines per frame (sanity)
    per_frame_lines = {}
    for (f, ln, ph, nm, val, _pc) in p.events:
        if nm in ("PF0", "PF1", "PF2") and CAVE_LO <= ln <= CAVE_HI:
            per_frame_lines.setdefault(f, set()).add(ln)
    sample = sorted(per_frame_lines.items())[:10]
    print("sample cave-PF frames (lines):",
          [(f, sorted(s)) for f, s in sample])

    groups = collect(p, CAVE_LO, CAVE_HI)

    rooms = {}   # tuple of rows -> [first frame]
    for f in sorted(groups):
        rows_here = []
        for ln in sorted(groups[f]):
            d = groups[f][ln]
            if len(d) < 3:                   # partial group (event cut?)
                continue
            rows_here.append((ln, d["PF0"], d["PF1"], d["PF2"]))
        if not rows_here:
            continue
        key = tuple((a, b, c) for _, a, b, c in rows_here)
        rooms.setdefault(key, []).append(f)

    print(f"unique cave PF patterns: {len(rooms)}")
    lines_out = []
    for i, (key, frames) in enumerate(sorted(rooms.items(), key=lambda kv: kv[1][0])):
        lines_out.append(f"### pattern {i}  frames {frames[0]}-{frames[-1]} "
                         f"({len(frames)} frames)")
        for (pf0, pf1, pf2) in key:
            full, left = decode_row(pf0, pf1, pf2)
            lines_out.append(f"  {full}   pf={pf0:02X},{pf1:02X},{pf2:02X} "
                             f"left={left}")
        lines_out.append("")
        print(lines_out[-3] if False else f"pattern {i}: {len(frames)} frames, "
              f"{len(key)} rows")
    text = "\n".join(lines_out)
    if out_path:
        out_path.write_text(text + "\n")
        print(f"wrote {out_path}")
    else:
        print(text)


if __name__ == "__main__":
    main()
