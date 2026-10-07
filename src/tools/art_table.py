#!/usr/bin/env python3
"""art_table.py — start_screen art -> TitleArtRows (bank2, 8 B/row).

Sprite-slice title kernel model (2026-10-06):
  * Objects/line: P0 pattern @ phi, P1 pattern @ phi+9, M0 @ +18,
    M1 @ +27 (strobes chained 3 cycles apart = 9 px). No ball lane —
    bank2 ArtLine stores no ENABL (dropped 2026-10-07).
  * Display cadence: 2 scanlines per art row (VDEL): line A = prefetch+
    GRP write (full budget), line B = mode stores + delay + strobes.
  * Per-row fields (8 bytes, fixed):
      k, f   delay after prefix: D = 5k + filler(f)   f: 0 none, 1 nop(2),
             2 bit(3), 3 bit+bit(6), 4 nop+nop(4)   -> D%5==1 uses f=3,k-1
      g0, g1 GRP0/GRP1 chunk bytes (P0/P1 pattern)
      n0, n1 NUSIZ0/NUSIZ1 values (P0/P1 single + M0/M1 width bits 4-5)
      e0, e1 ENAM0/ENAM1 ($02 on / $00 off)
  * Strobe timing (HBLANK-aware): RESP0 instruction start C_s satisfies
    x = 3*(C_s+2) - 68 + LAT for P0 at x = OFF + phi, i.e.
    C_s = round((OFF + phi - LAT + 68)/3 - 2). Encoder needs an exact
    (f,k) reachable cycle: C_s = 7 + PATH[f] + kp(k) <= MAXCS.

Run: /home/iuri/python3/bin/python3 tools/art_table.py > generated/title_art.asm
"""
import sys
from pathlib import Path
from PIL import Image

SRC = Path(__file__).resolve().parent.parent
ART = SRC / "art" / "start_screen_trimmed.png"
# Helmet art removed from the title screen 2026-10-07 (user: reference
# only, better idea comes later). Table stays: ArtFold still runs its
# 60 WSYNC (frame timing), rows all-blank = band black. Flip to True
# to re-encode (encoder kept: per-row phi, >=95% coverage measured).
ART_ENABLED = False
# Timing (2026-10-06 recalibration — first Stella screenshot showed art
# ~70px left: the old model forgot HBLANK, RESP at cycle C lands at
#   x = 3*(C+2) - 68 + LAT   (68cl HBLANK, write on 3rd cycle of sta):
LAT = 4              # strobe -> picture clocks (calibrate from screenshot).
                     #   4->5 tested 2026-10-07: NO x shift (target_cs round
                     #   absorbs 1/3) -> not an X knob. X moves in 3px steps
                     #   only via reachable (OFF+phi) sums.
OFF = 51             # screen X of art column 0 (was 52; retuned with
                     #   per-row phi 2026-10-07: xoff lands {54,55,56} ->
                     #   row-to-row steps <=2px). delay_kf reachable set
                     #   at 51 = {7..12, 19..30, 34..40}; 52 gave center
                     #   77 at 83.9% single-phi.
HBL = 68             # HBLANK color clocks
MAXPHI = 44          # art width - 1

# D-line cycles from sta WSYNC to RESP0 instruction start:
#   prefix (ldy+lda=7) + f-chain + k-block
PATH = {0: 3, 1: 12, 2: 17, 3: 24, 4: 21}   # f-chain (bank2.lst, f=3 > f=4!)
MAXCS = 53           # D-line: cs + 20 + WSYNC write (2) <= 75 (measured:
                     # P-line=76c was +3 from a redundant jmp; D stays cs+20)


def kp(k):
    """k-block: ldy+lda+tay (9) + beq(3 if k==0 else 2) + 5k loop."""
    return 12 if k == 0 else 10 + 5 * k


def target_cs(phi):
    """RESP0 instruction-start cycle so P0 lands at OFF+phi."""
    return round((OFF + phi - LAT + HBL) / 3 - 2)

# model constants for scoring (4 chunks, 9px pitch, starts 1 mod 3;
# ball lane dropped 2026-10-07 — bank2 ArtLine has no ENABL store and
# phi+36 >= 37 never touches content (ends x33))


def best_width(start, row, w):
    """Best missile width for the lane at `start`: a 1/2/4/8 block
    anchored at start. Rank = net (covered - extra) >= 0, then max
    covered. net>=0 keeps right-edge runs (2026-10-07: net>=1 dropped
    cols 30-33, leaving the art 2px narrow); net<0 = a solid BAR of
    mostly-empty pixels (the old rule accepted any width-8 whose lit
    count beat the best full run). Returns (width, n); (0, 0) =
    draw nothing (missing pixel beats a bar)."""
    best = None                       # key (net, n)
    for width in (1, 2, 4, 8):
        if start + width > w:
            continue
        n = sum(row[start:start + width])
        if n == 0:
            continue
        net = 2 * n - width
        if net < 0:
            continue
        if net == 0:
            # half-lit block: only if the lit pixels are one contiguous
            # run (right-edge trim); scattered n4 → 8-wide solid blob
            # (2026-10-07 top-right rect artifacts).
            run = best_run = 0
            for i in range(width):
                run = run + 1 if row[start + i] else 0
                best_run = max(best_run, run)
            if best_run != n:
                continue
        key = (net, n)
        if best is None or key > best[0]:
            best = (key, width, n)
    return (best[1], best[2]) if best else (0, 0)


def lane_score(phi, row, w):
    """Realizable lit pixels for this phi: P lanes are full 8-bit
    patterns (exact), M lanes limited to best_width()."""
    c = 0
    for start in (phi, phi + 9):
        for i in range(8):
            if start + i < w and row[start + i]:
                c += 1
    for start in (phi + 18, phi + 27):
        c += best_width(start, row, w)[1]
    return c


def delay_kf(phi):
    """Exact (f,k) whose C_s = target_cs(phi), within MAXCS, or None
    (the phi-delta loop then tries a neighboring lane)."""
    t = target_cs(phi)
    for f in range(5):
        for k in range(16):
            c = 7 + PATH[f] + kp(k)
            if c > MAXCS:
                continue
            if c == t:
                return k, f
    return None


def main():
    if not ART_ENABLED:
        h = 30
        print("; generated by tools/art_table.py — DO NOT EDIT")
        print("; art DISABLED 2026-10-07 (title screen: text only,")
        print(";   copyright band added; encoder kept for later)")
        print("    .byte $00                  ; +1 align: (ArtPtr),Y never crosses")
        print("TitleArtRows:")
        for y in range(h):
            print("    .byte 0,0,0,0,0,0,0,0            ; blank row")
        print(f"; {h} rows x 8 B = {h*8} bytes (single page F700)")
        return
    im = Image.open(ART).convert("RGBA")
    w, h = im.size
    px = im.load()
    lit = [[1 if (px[x, y][3] > 40 and sum(px[x, y][:3]) > 150) else 0
            for x in range(w)] for y in range(h)]
    tot = cov = 0
    rows_out = []
    # Per-row phi (2026-10-07, forecast recovery >=95%): single global
    # phi caps at 86.0% (lane gaps eat 14-23 lit px/row-set). At OFF=51
    # EVERY reachable phi has xoff = 3*target_cs - 54 - phi in
    # {54,55,56} -> drawn pixels move <=2px row-to-row, so per-row phi
    # no longer shreds positionally (old shred = gap alternation).
    # Two phi clusters fit the art: {7..12} left window, {19..23}
    # right-only rows. Tie-break: closest to previous row's phi, then
    # to 10 (stability). Measured 180/186 = 96.8%, max step 2px.
    # Fallback if outlines look dotted: drop {19..23} -> 176/186.
    allowed = [p for p in range(1, min(MAXPHI, w - 1) + 1)
               if delay_kf(p) and (7 <= p <= 12 or 19 <= p <= 23)]
    prev = 10
    for y, row in enumerate(lit):
        s = sum(row)
        if not s:
            rows_out.append((y, None, 0))
            continue
        tot += s
        best = max(lane_score(p, row, w) for p in allowed)
        phi = min((p for p in allowed if lane_score(p, row, w) == best),
                  key=lambda q: (abs(q - prev), abs(q - 10)))
        prev = phi
        kf = delay_kf(phi)
        cov += best
        g0 = g1 = 0
        for i in range(8):
            if 0 <= phi + i < w and row[phi + i]:
                g0 |= 0x80 >> i
            if 0 <= phi + 9 + i < w and row[phi + 9 + i]:
                g1 |= 0x80 >> i
        # solids: M lanes at phi+18 / phi+27 only (see best_width)
        w0 = best_width(phi + 18, row, w)[0]
        w1 = best_width(phi + 27, row, w)[0]
        code = {0: 0, 1: 0, 2: 1, 4: 2, 8: 3}
        e0 = 0x02 if w0 else 0
        e1 = 0x02 if w1 else 0
        n0 = 0x30 if w0 else 0x00          # P0 single (bits0-2=0) + M0 w<<4? bits4-5
        # NUSIZ missile width = bits 4-5 of NUSIZ0: width code<<4
        n0 = (code[w0] << 4) & 0x30
        n1 = (code[w1] << 4) & 0x30
        k, f = kf
        rows_out.append((y, (k, f, g0, g1, n0, n1, e0, e1), 1))
    print("; generated by tools/art_table.py — DO NOT EDIT")
    print(f"; art {w}x{h} lit={tot} covered={cov} = {100*cov/max(1,tot):.1f}%")
    print(f"; LAT={LAT} OFF={OFF} HBL={HBL} MAXCS={MAXCS} per-row phi (calibrate)")
    print("    .byte $00                  ; +1 align: (ArtPtr),Y never crosses")
    print("TitleArtRows:")
    for y, ent, ok in rows_out:
        if not ok:
            print("    .byte 0,0,0,0,0,0,0,0            ; blank row")
        else:
            print("    .byte " + ",".join(f"${v:02X}" for v in ent) +
                  f"              ; y={y}")
    print(f"; {h} rows x 8 B = {h*8} bytes (single page F700)")


if __name__ == "__main__":
    main()
