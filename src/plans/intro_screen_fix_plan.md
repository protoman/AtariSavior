# Plan: Fix Intro Screen

## Goal

Fix the intro screen (`DropTarget=$FD` path) to match `intro_screen_mess_fixed.png`:
- "S.A.V.I.O.R." title centered at the top, no artifacts
- Jet art clean, centered, no stray horizontal/vertical lines
- Copyright text at bottom right

---

## Visual Diff Analysis

| Bug | Buggy (`bug_intro.png`) | Fixed (`intro_screen_mess_fixed.png`) |
|---|---|---|
| Title text | Too far right; stray `_` after the dot | Centered, clean |
| Art | Shredded with horizontal slices at wrong X | Clean helmet shape, centered |
| Missiles | Two red vertical lines extending below art | None |
| Copyright | Absent | Purple small-font bottom-right |

---

## Root Causes (traced from code)

### Bug 1 — Title text mispositioned + stray character

**File**: `kernel.asm` lines 2691-2693

```asm
lda #3                       ; NUSIZ = 3 copies close
sta NUSIZ0
sta NUSIZ1
```

NUSIZ `$03` = "3 copies close" (score technique). But `SetObjectXPos` at
line 2699 positions P0 at X=60 **assuming NUSIZ is already `$03`** — that
is correct. The issue is the P0 base is X=60, P1 base is X=68.

With `NUSIZ=$03` (3 copies close, 8px spacing each) and P0 at X=60, the
three copies land at:
- Copy 1: x=60
- Copy 2: x=76
- Copy 3: x=92

These 3 copies of P0 display slots 1-3 ("S.", "A.", "V."), and P1's 3
copies at x=68/84/100 display slots 4-6 ("I.", "O.", "R."). So the
two-letter-wide text block starts at x=60 and ends at x=100+8=108.
Center of 160px screen = 80. Text center = (60+108)/2 = 84 → shifted right.

The `_` stray cursor: NUSIZ `$03` includes missile M0 width bits. If
`NUSIZ0=$03`, the `bit1:0` field = single P0 (ok), but `bit5:4` (missile
M0 width) = `00` = 1px. Since `ENAM0` is cleared, this should be harmless.
The stray `_` is more likely the **score position** from the previous HUD
frame leaking (this is title frame, but VBL still runs `SetObjectXPos` for
the player+enemy which positions at `RoomX`).

**Real problem**: `TitleKernel` calls `SetObjectXPos` for P0@60 and P1@68
AFTER the HMOVE that already positioned the cave player sprite. But the
VBLANK runs normally including `sta HMOVE` at line 594. The title's
`SetObjectXPos` calls generate `RESP0/RESP1` writes, then `TitleKernel`
does a fresh `sta WSYNC / sta HMOVE` at lines 2703-2704. This should work.

The actual stray `_` is the **missile M0** — looking at the bug screenshot, the
cursor-like `_` is positioned ~x=100 (after "R."). ENAM0 should be 0 (cleared
at TitleKernel entry). But `LaserInput` in overscan may re-enable ENAM0.

> [!IMPORTANT]
> The title `_` artifact after "R." is M0 (laser missile). Even though
> `TitleKernel` clears `ENAM0` at line 2687, the **next frame's VBL**
> runs `jsr LaserInput` (overscan line 965) which re-arms ENAM0 based on
> fire state. Title frames should suppress laser rendering.

**Fix**: `TitleKernel` must clear `ENAM0` AFTER the VBL laser processing,
not before. The right place: clear it in the **kernel** (it already does
at line 2687), but we also need to keep it off across the per-scanline
loop. Currently ENAM0 is only written by `BeamMask` inside `.Line`'s
player window — but `TitleKernel` never runs `.Line`. So ENAM0 from VBL's
`LaserInput` call persists during TitleKernel. → Clear ENAM0 at the **start
of the text-drawing loop** or right before the first WSYNC.

Actually, looking again at `TitleKernel` line 2686-2687:
```asm
    sta ENABL
    sta ENAM1
    lda #COLOR_TITLE
    sta COLUP0
    sta COLUP1
    lda #3
    sta NUSIZ0
    sta NUSIZ1
```
ENAM0 is NOT cleared here! Only ENABL and ENAM1. ENAM0 keeps whatever
LaserInput set. → Add `sta ENAM0` after the `sta ENAM1`.

### Bug 2 — Art horizontal slicing / wrong X position

**File**: `bank2.asm` ArtLine (~line 914), `generated/title_art.asm`

The art appears shredded and at the wrong horizontal position. The `OFF=67`
constant in `art_table.py` sets where column 0 of the art lands on screen.
The `LAT=4` is the latency calibration. If either is wrong, the art will be
mispositioned.

From the fixed screenshot, the art is centered around x=80, and it's about
45px wide, so it should span x~57..102. With `OFF=67`, art column 0 = x=67,
and the art is 45px wide: span = 67..112. This is shifted right from the
correct center of 80 (should be ~57..102 for 45px art). Correct OFF = ~57.

The horizontal slicing artifact (stripes going left) suggests the RESP strobe
cycle timing is off — some rows land far to the left (early strobe) or right
(late strobe). This is likely a **calibration issue** with `LAT` and `OFF`.

**Fix**: Re-calibrate `OFF` and `LAT` in `art_table.py` to center the art.
`OFF` = desired left edge x of art, and should be adjusted so the art
center matches x=80. Current art is 45px wide → OFF should be 80-22 = 58.

> [!IMPORTANT]
> The `art_table.py` constants `OFF` and `LAT` need calibration using a
> Stella screenshot to measure actual art position vs expected.
> The fixed screenshot shows the art at approx x=68..112, center ~90.
> Adjust `OFF` from 67 to match observed center, then re-run `art_table.py`.

### Bug 3 — Two vertical red lines below the art

**File**: `kernel.asm` lines 2784-2785

```asm
    jsr ArtFold                  ; bank2: art setup+60 WSYNCs, ReturnPad
    lda #0
    sta ENAM0                    ; art leaves missiles enabled — pad would
    sta ENAM1                    ;   draw two stale vertical lines
```

The comment already explains the fix IS there — but the lines are visible
in the screenshot. This means `ArtFold` takes more than 60 scanlines OR the
ENAM0/ENAM1 clears don't land before the next visible WSYNC.

Actually: the 117-line pad at line 2786-2790 comes AFTER the clears:
```asm
    ldx #117                     ; pad: 198 - 20 text - 60 art - 1 close
.TkPad:
    sta WSYNC
    dex
    bne .TkPad
```
The `sta WSYNC` uses A=0 (from the last `sta ENAM1`). During those 117
pad scanlines, ENAM0 and ENAM1 are already 0. So the lines should NOT
appear. → The lines likely come from the art band (y=60..119) where the
art doesn't properly clear ENAM0/ENAM1 on the last row.

Looking at `ArtLine`: the per-row table sets `e0` and `e1` (ENAM0/ENAM1)
per row. If any art row has missiles enabled and there's no disable at the
bottom, the last enabled missile persists after the art. But `ReturnPad`
just does `sta $1FF6 / rts` — doesn't touch TIA.

**Fix**: `TitleKernel` must zero ENAM0 and ENAM1 immediately after
`jsr ArtFold` returns. The code at lines 2784-2785 already does this —
but A might not be 0 at that point. Looking at `ReturnPad` → `rts`, A
comes back as whatever `ArtLine` left in A (last `sta $1FF8` wrote 0 into
bank select). Actually:

```asm
ArtLine's .ALdone:
    jmp $FBF8     ; ReturnPad twin
ReturnPad:
    sta $1FF6     ; A = whatever it was
    rts
```

So A is whatever ArtLine last loaded. The fix at line 2784:
```asm
    lda #0
    sta ENAM0
    sta ENAM1
```
This IS correct. But the missile lines in the screenshot appear DURING the
art band, not after. → The art table data sets some rows with e0/e1=2 even
on "blank" portions of the art (the legs/body extending down).

Looking at `title_art.asm`: rows 13-23 have `e0=$02` or `e1=$02` (missiles
enabled). The missiles are used to fill in narrower parts of the art. But
if the missiles are positioned at the wrong X (strobe calibration off), they
appear as stray lines.

### Bug 4 — Missing copyright text

**File**: `kernel.asm` TitleKernel (after the pad)

The fixed screenshot shows `©2026 IVRIFIEDORUK` at bottom-right.
This is rendered using small text in the mock tool (`mock_title.py`) but
not in the actual game. The game needs PF-based or sprite-based small text
in the pad section.

> [!IMPORTANT]
> Copyright text is a NICE-TO-HAVE, not critical for the art fix.
> It requires either PF playfield text OR a second sprite pass.
> Can be deferred to a separate task.

---

## Proposed Changes

### 1. Fix ENAM0 (laser artifact) in TitleKernel

#### [MODIFY] kernel.asm — TitleKernel TIA init block (~line 2681-2693)

```diff
     sta GRP0                     ; flush VDEL buffers (score-technique pattern)
     sta REFP0
     sta REFP1
     sta ENABL
     sta ENAM1
+    sta ENAM0                    ; MUST clear: LaserInput in VBL arms ENAM0
     lda #COLOR_TITLE
```

### 2. Fix title text horizontal position

The current P0=60/P1=68 positions the 6-slot text spanning x=60..108
(center=84, shifted 4px right from center=80). To center it:
- P0 should be at x=56, P1 at x=64.

#### [MODIFY] kernel.asm — SetObjectXPos calls (~lines 2697-2702)

```diff
-    lda #60
+    lda #56
     ldx #0
     jsr SetObjectXPos            ; P0 slot base (score parity)
-    lda #68
+    lda #64
     ldx #1
     jsr SetObjectXPos            ; P1 slot base
```

> [!NOTE]
> The exact values depend on how `SetObjectXPos` maps pixel→coarse/fine.
> If the current position shows x=60 visually, then -4px = value 56 should
> work, but this needs Stella verification.

### 3. Fix art calibration (re-run art_table.py)

#### [MODIFY] tools/art_table.py — OFF constant

From the bug screenshot, the art appears to start at x≈95 (shifted far right).
The OFF constant needs to move the art left. Target: art center at x=80
with 45px width → OFF ≈ 58.

```diff
-OFF = 67             # screen X of art column 0
+OFF = 58             # screen X of art column 0 (calibrated to center art)
```

Then re-run:
```bash
/home/iuri/python3/bin/python3 tools/art_table.py > generated/title_art.asm
```

> [!IMPORTANT]
> The LAT calibration may also need adjustment. LAT is the strobe-to-pixel
> latency. If the art rows appear as horizontal slices (strobe at wrong phase),
> LAT needs ±1 or ±2 adjustment. This requires iterative Stella testing.

### 4. Fix ENAM0/ENAM1 after art band

Already present in code (lines 2784-2785), but verify A=0 at that point.

#### [MODIFY] kernel.asm — after ArtFold return (~line 2783-2785)

```asm
    jsr ArtFold
    lda #0                       ; ensure A=0 before clearing missiles
    sta ENAM0
    sta ENAM1
```

The `lda #0` is already there. Confirm it's correct in the current code.

---

## Execution Plan (step by step)

1. **Step 1**: Add `sta ENAM0` to TitleKernel init block. Build + test in Stella.
   - Expected: the `_` laser cursor artifact disappears.

2. **Step 2**: Adjust P0/P1 positions (try `lda #56` / `lda #64`). Build + test.
   - Expected: title text moves left toward center.

3. **Step 3**: Adjust `OFF` in `art_table.py`, re-generate, build + test.
   - Expected: art moves to center; if horizontal slices persist, adjust `LAT`.

4. **Step 4** (optional): Copyright text via PF registers in the pad band.

---

## Verification Plan

### Automated Tests
```bash
./build.sh          # must succeed, 0 errors
```

### Manual Verification (Stella)
1. Launch: `stella savior.bin`
2. Verify: "S.A.V.I.O.R." is centered at top, no `_` artifact.
3. Verify: Jet art is clean, centered, no horizontal shred lines.
4. Verify: No vertical red missile lines extend below the art.
5. Press SELECT/RESET → switches to level-select title screen (regression check).

---

## Open Questions

> [!IMPORTANT]
> **Art calibration**: The OFF and LAT constants in `art_table.py` were set
> from a screenshot measurement on 2026-10-06. The bug screenshot suggests
> they may be wrong for the current build. The exact values need iterative
> Stella testing. Approve the plan and we'll dial them in empirically.

> [!IMPORTANT]
> **Copyright text**: The fixed screenshot shows copyright. This requires a
> new rendering pass (PF or sprite). Confirm: should this be included in
> this fix, or deferred?
