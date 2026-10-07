# Implementation Plan: Fix Intro Screen

## Goal
Fix the intro screen (`DropTarget=$FD`) to match `screenshots/intro_screen_mess_fixed.png`:
- Center the "S.A.V.I.O.R." title text and remove the trailing `_` artifact.
- Fix the shredded jet art rendering, centering it cleanly.
- Eliminate the two vertical red lines running down the screen.
- Clean up transitions between text, art, and pad scanlines.

---

## Root Causes Confirmed

1. **Stray `_` cursor after "R."**:
   - `TitleKernel` ([kernel.asm:2686](file:///home/iuri/Desenvolvimento/atari_2600/ai_savior/src/kernel.asm#L2686)) zeroes `ENABL` and `ENAM1`, but never zeroes `ENAM0`.
   - `ENAM0` remains enabled from the previous VBL/laser state, displaying as an 8-clock bar right after the text.

2. **Title text shifted right**:
   - P0 is set at x=60 and P1 at x=68.
   - With 3 close copies each (48 pixels total span: x=60..108), the visual center is at x=84 instead of screen center x=80.
   - P0 needs to be x=56, P1 x=64.

3. **Art shredded & horizontal line tears**:
   - **Mid-scanline RESP strobe**: `ArtLine` ([bank2.asm:930-985](file:///home/iuri/Desenvolvimento/atari_2600/ai_savior/src/bank2.asm#L930-L985)) enables `GRP0`, `GRP1`, `ENAM0`, and `ENAM1` on the prefetch line `.Pc`, then calls `sta WSYNC` and strobes `RESP0`, `RESP1`, `RESM0`, `RESM1` mid-scanline on `.Dc`.
   - Resetting sprite counters while graphics and missiles are already active causes TIA horizontal tearing and split sprites.
   - **Missiles lack VDEL**: `VDELP0`/`VDELP1` only delays player sprites, not missiles. Setting `ENAM0`/`ENAM1` on `.Pc` immediately draws missiles on line A with stale positions from earlier lines.

4. **Bottom vertical red lines**:
   - Bottom rows of `TitleArtRows` leave missiles enabled (`e0=$02`), which bleed downward until explicitly cleared.

---

## Proposed Changes

### Component 1: Title text cleanup & centering
#### [MODIFY] [kernel.asm](file:///home/iuri/Desenvolvimento/atari_2600/ai_savior/src/kernel.asm)
- Add `sta ENAM0` during `TitleKernel` TIA init to eliminate the stray cursor.
- Adjust `SetObjectXPos` arguments from 60 / 68 to 56 / 64 to center the title.
- Ensure `ENAM0` and `ENAM1` are zeroed immediately before calling `ArtFold`.

### Component 2: Art generator timing & positioning
#### [MODIFY] [tools/art_table.py](file:///home/iuri/Desenvolvimento/atari_2600/ai_savior/src/tools/art_table.py)
- Calibrate `OFF` from 67 down to ~58 so the helmet art centers around x=80.
- Regenerate `generated/title_art.asm`.

### Component 3: Safe art scanline kernel
#### [MODIFY] [bank2.asm](file:///home/iuri/Desenvolvimento/atari_2600/ai_savior/src/bank2.asm)
- Keep missiles blanked during positioning or strobe objects before enabling graphics.
- Ensure clean exit: disable `ENAM0`, `ENAM1`, `GRP0`, `GRP1` on the final scanline of `ArtLine`.

---

## Verification Plan

### Automated Build & Timing
```bash
./build.sh
/home/iuri/python3/bin/python3 sim_frame_budget.py
```
- Verify 0 assembly errors and constant frame timing (263 scanlines).

### Manual Verification
- Run `stella savior.bin`.
- Check intro screen:
  1. "S.A.V.I.O.R." centered at top without any trailing artifact.
  2. Jet helmet centered and clean without horizontal slices or stray vertical lines.
  3. SELECT/RESET advances cleanly into the game.

---

## Outcome (2026-10-07): pad stripe root-caused and fixed

**Root cause:** `VDELP0/VDELP1` were still 1 from the title text setup
(scanline 20). The post-art `GRP0/GRP1 = 0` clear therefore wrote only the
DELAYED slot — the LIVE slot kept the stale text glyph (a byte with 2 lit
bits, frozen by the VDEL cross-shuffle), drawn at the last RESP position
through all 117 pad scanlines = the solid 2-px stripe.

**Fix** (`kernel.asm`, title-pad prologue clear): write `VDELP0/VDELP1 = 0`
**before** `GRP0/GRP1 = 0` so the zeroes land in the live slot.

**Experiments that did NOT change the stripe** (each measured, then removed):
E1 `NUSIZ0/NUSIZ1/CTRLPF = 0` (width/config unchanged → not missile/ball);
E4 `COLUP0/COLUP1 = $0E` (stripe turned white → colored by COLUP0/1);
E6 per-line `ENAM0/ENAM1 = 0` in the pad loop (→ not re-enable leak);
E7 `RESMP0/RESMP1 = 2` (missile suppression ineffective → not missile).

**Verified:** saveSnap pad zone (y78-193) fully black; text purple
(174,97,220) rows 9-16 x106-199; art red intact; `build.sh` green
(verify_build + sim_bomb_fuse + sim_frame_budget); 3 warnings all
pre-existing (headroom 1B, model 5/6 rect counts). Final shot:
`screenshots/shot_title_6.png`.

---

## Outcome (2026-10-07): art geometry calibrated

**Encoder fixes (`tools/art_table.py`), each measured against
`intro_screen_mess_fixed`:**

1. **Solid-bar artifact** — old rule accepted any partial width-8 whose
   lit count beat the best full run. New `best_width`: rank =
   `(net, n)` with `net = 2n - width`; `net < 0` skipped; `net == 0`
   only if the lit pixels are ONE contiguous run (right-edge trim).
   Scattered half-lit 8-blocks = the remaining top-right blobs — rejected.
2. **Outline shredded by per-row phi** — each row picked its own phi
   (±3..±9 search), jittering lanes horizontally row-to-row. Fixed:
   ONE global phi for every row, chosen by summed `lane_score`
   (emitted in header; = 10). Shape coherent after this (cmp_shapes8).
3. **Gap purple bars** (separate from pad stripe) — VDEL Old slot of one
   player still stale when text closed with 2 GRP writes. Fixed: 4 writes
   (GRP0,GRP1,GRP0,GRP1) before `ldx #61` `.TkGap`. Gap verified empty.
4. **X calibration dead-ends (record, don't re-try):**
   - `delay_kf(phi)` has holes: phi=10 reachable only at
     OFF in {49, 52, 61} (c must equal `7+PATH[f]+kp(k)` exactly;
     right mod-3 is necessary, not sufficient). OFF=52 kept.
   - OFF±3 = ±3px but breaks phi10 (55 → fell back to phi16, left edge
     cols 11-15 lost, center 83.5).
   - LAT 4→5 = NO x shift (target_cs round absorbs 1/3) — not an X knob.
   - Accepted: measured center 77 vs target ~79 (crisp; glow inflates
     ±2) = **±1.5px deviation**. Ours self-consistent with our text
     center 76.5.
5. **Lane-lattice ceiling:** P lanes exact 8-bit; M lanes width-quantized
   (1/2/4/8 anchored at phi+18/phi+27 only — strobe chain is fixed);
   phi gaps at cols 18, 27, 36. Honest coverage **83.9%** (156/186);
   further gains need per-row phi (breaks coherence) — not worth it.
6. **Vertical:** art start line 79 = exact target match; rendered
   lines 79-136 (58; 2 tail lines unlit rows) vs source 60 and target
   79-145 (glow-inflated) — accepted.

**Verified:** final saveSnap — no stray pixels anywhere (text band,
gap, art band, pad all clean); art x67-87, text x53-100; `build.sh`
green. Final shot: `screenshots/shot_title_7.png`.
**Known deviation (accepted):** target copyright line (lines 207-212)
sits below the kernel (overscan) — unrenderable in the 192-line frame.
