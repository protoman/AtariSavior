#!/usr/bin/env python3
"""Power-bar table generator (bugs.md #30) — uniform drain chunks.

Regenerates bank1.asm's BarDelayTable / BarFineTable from path cycle
counts (never hand-transcribe — the 2026-09-23 hand pass caused 9
mismatches, power_bar_smooth_plan.md H3b-3).

Design (2026-10-11 user report):
  * Full bar (B >= 117) renders ALL YELLOW for the first 4 seconds
    (renderer gate `cpy #BAR_MAX-3`), so the first red appears at t=4s —
    exactly one chunk period later (report: "already red at start",
    "first one should take the same time each chunk needs").
  * Drain = one visible step every K=4 BarLevel decs (4 seconds),
    step size 1-2 cycles = 3-6 px (plan spec: "step <=6px every <=4s"),
    strictly monotone (pos(B) <= pos(B+1); red only ever grows).
  * pos(B) = flip cycle of the mid-line COLUPF yellow->red write:
        pos = {F0:12, F1:14, F2:20, F3:30, F4:31} + 5*A     (H3a/H3c paths)
    A caps from H3a cycle budget: F0/F1 <=11, F2 <=10, F3/F4 <=8
    (content <=71, the shipped limit — do NOT raise without a listing
    recount: >=74c WSYNC gaps are the stripe-overrun family).
  * Reachable positions are all integers <=71 EXCEPT those == 3 (mod 5);
    the generator snaps targets down to the nearest reachable value.

Run:  /home/iuri/python3/bin/python3 tools/gen_bar_tables.py [--check]
  --check  only verify the tables already in bank1.asm (CI-style).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK1 = ROOT / "src" / "bank1.asm"

K = 8               # seconds (BarLevel decs) per visible chunk
FULL_HOLD = 7       # extra decs held all-yellow after t=0 (first red at t=K=8)
BAR_MAX = 120
FIRST_RED_B = BAR_MAX - FULL_HOLD - 1   # 116: first B rendered through the red path

BASE = {0: 12, 1: 14, 2: 20, 3: 30, 4: 31}
A_CAP = {0: 11, 1: 11, 2: 10, 3: 8, 4: 8}
POS_MAX = 71                       # shipped content cap (H3c-2)
POS_FULL = 74.7                    # body-end equivalent of the all-yellow path


def reachable():
    """pos -> (fine, delay) for every reachable pos <= POS_MAX."""
    table = {}
    for f, base in BASE.items():
        for a in range(A_CAP[f] + 1):
            p = base + 5 * a
            if p <= POS_MAX:
                # prefer the first path that yields a pos (F order = 0..4)
                table.setdefault(p, (f, a))
    return table


REACH = reachable()


def targets():
    """One pos per K-block; strictly decreasing with 1-2 cycle steps
    (3 only where 1-2 are unreachable — the sparse bottom band)."""
    starts = list(range(FIRST_RED_B, -1, -K))     # 116,112,...,0 (30 blocks)
    pos = POS_MAX                                 # 71 at first red
    out = [pos]
    d3 = 0
    for _ in range(len(starts) - 1):
        for d in (2, 1, 3):
            cand = pos - d
            if cand in REACH:
                if d == 3:
                    d3 += 1
                pos = cand
                break
        else:
            raise SystemExit(f"no reachable step below {pos}")
    out_tail = []
    # rebuild as list
    seq = [POS_MAX]
    pos = POS_MAX
    d3 = 0
    for _ in range(len(starts) - 1):
        # prefer 4c (12px) steps: first-bite ~14px, so chunks of the same
        # order make bite/chunk ~ 1.2 (was 5-6x with 1c/3c steps)
        for d in (4, 3, 2, 1):
            cand = pos - d
            if cand in REACH:
                if d == 3:
                    d3 += 1
                pos = cand
                break
        seq.append(pos)
    return starts, seq, d3


def build_levels():
    """pos for every B in 0..BAR_MAX (B >= FIRST_RED_B+1 = full = pos_hi)."""
    starts, tgs, _d3 = targets()
    pos_hi = POS_MAX
    levels = [pos_hi] * (BAR_MAX + 1)
    for i, s in enumerate(starts):
        for b in range(s, max(-1, s - K), -1):
            if 0 <= b <= BAR_MAX:
                levels[b] = tgs[i]
    # full-hold band (B >= 117): pos_hi (rendered by the yellow-only path
    # anyway; value kept so the table stays monotone)
    for b in range(FIRST_RED_B + 1, BAR_MAX + 1):
        levels[b] = pos_hi
    return levels


def verify(levels):
    errs = []
    for b in range(BAR_MAX):
        if levels[b] > levels[b + 1]:
            errs.append(f"non-monotone at B={b}: {levels[b]} -> {levels[b + 1]}")
    for b in range(BAR_MAX + 1):
        p = levels[b]
        if p not in REACH:
            errs.append(f"B={b}: pos {p} unreachable")
        if p > POS_MAX:
            errs.append(f"B={b}: pos {p} > {POS_MAX}")
    # chunk cadence: for B < FIRST_RED_B, pos must change only on K-boundaries
    for b in range(FIRST_RED_B, -1, -1):
        if levels[b] != levels[b + 1] and (FIRST_RED_B - b) % K != 0:
            errs.append(f"B={b}: change off the {K}-dec grid")
    # chunk step sizes: 1-3c (3-9px); aim is mostly 3c so the chunk is
    # the same order as the first bite (report: bite was 5-6x a chunk)
    starts, tgs, d3 = targets()
    for i in range(1, len(tgs)):
        d = tgs[i - 1] - tgs[i]
        if not (1 <= d <= 4):
            errs.append(f"chunk step {d}c at block {i} (want 1-4c)")
    n3 = sum(1 for i in range(1, len(tgs)) if tgs[i - 1] - tgs[i] >= 3)
    if n3 * 2 < len(tgs) - 1:
        errs.append(f"only {n3}/{len(tgs) - 1} steps are >=3c (want >=1/2)")
    # B=0 must render visually full-red: flip x = 3*pos - 68 must sit at
    # or before the body's left edge (x=4, PF0=$E0 4px margin) so every
    # body pixel is right of the flip.
    if levels[0] > 24:
        errs.append(f"pos(0)={levels[0]} > 24: empty bar would show yellow")
    # first-red bite vs avg chunk (report: bite should be <= ~2x chunk)
    # +3px(160): F4A8 (top block) renders ~1c earlier than 31+5A lists
    # (measured first red 28px/320 vs 22px predicted); later states on
    # F1/F0 paths matched the table exactly, so the offset is top-block only.
    bite = (POS_FULL - levels[FIRST_RED_B]) * 3.0 + 3.0
    chunk = (POS_FULL - levels[0]) * 3.0 / (len(tgs) - 1)
    if chunk > 0 and bite / chunk > 1.7:
        errs.append(f"bite/chunk ratio {bite / chunk:.2f} > 1.7 "
                    f"(bite {bite:.1f}px, chunk {chunk:.1f}px)")
    return errs, bite, chunk


def emit_table(name, levels):
    vals = [levels[b] if name == "BarDelayTable" else None for b in range(BAR_MAX + 1)]
    return vals


def render(name, delay_of, fine_of):
    vals = [delay_of[b] if name == "BarDelayTable" else fine_of[b]
            for b in range(BAR_MAX + 1)]
    lines = []
    for i in range(0, len(vals), 16):
        chunk = ",".join(str(v) for v in vals[i:i + 16])
        lines.append(f"    .byte {chunk}")
    return "\n".join(lines)


def patch_bank1(delay_of, fine_of, write=True):
    src = BANK1.read_text()
    pat_delay = re.compile(r"(BarDelayTable:[^\n]*\n)((?:\s*\.byte[^\n]*\n)+)")
    pat_fine = re.compile(r"(BarFineTable:[^\n]*\n)((?:\s*\.byte[^\n]*\n)+)")
    new = pat_delay.sub(lambda m: m.group(1) + render("BarDelayTable", delay_of, fine_of) + "\n", src)
    new = pat_fine.sub(lambda m: m.group(1) + render("BarFineTable", delay_of, fine_of) + "\n", new)
    if new == src:
        print("no table change (identical)")
        return True
    if write:
        BANK1.write_text(new)
        print(f"patched {BANK1}")
    return True


def main():
    check = "--check" in sys.argv
    levels = build_levels()
    fine_of = {b: REACH[levels[b]][0] for b in range(BAR_MAX + 1)}
    delay_of = {b: REACH[levels[b]][1] for b in range(BAR_MAX + 1)}
    errs, bite, chunk = verify(levels)
    starts, tgs, d3 = targets()
    print(f"blocks: {len(tgs)}  first red at t={BAR_MAX - FIRST_RED_B}s "
          f"(B={FIRST_RED_B}), {d3}x3c step(s)")
    print(f"first bite {bite:.1f}px  avg chunk {chunk:.1f}px  "
          f"ratio {bite / chunk:.2f}")
    print(f"pos schedule: {tgs}")
    if errs:
        print("FAIL:")
        for e in errs:
            print("  " + e)
        sys.exit(1)
    print("verify OK: monotone, reachable, 1-4c steps, K-grid, ratio<=1.7")
    if check:
        # verify the tables actually IN bank1.asm match the generator
        src = BANK1.read_text()
        for name, want in (("BarDelayTable", delay_of), ("BarFineTable", fine_of)):
            m = re.search(rf"{name}:[^\n]*\n((?:\s*\.byte[^\n]*\n)+)", src)
            got = [int(v) for v in re.findall(r"[0-9]+", m.group(1))]
            bad = [b for b in range(BAR_MAX + 1) if got[b] != want[b]]
            if bad:
                print(f"FAIL {name}: {len(bad)} entries stale, e.g. B={bad[:5]}")
                sys.exit(1)
        print("bank1 tables match generator")
    else:
        patch_bank1(delay_of, fine_of)
        print("NOTE: re-run ./build.sh (bank1 tables changed)")


if __name__ == "__main__":
    main()
