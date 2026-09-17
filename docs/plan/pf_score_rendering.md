# Plan: Switch Score Rendering from Sprite to Playfield (PF)

## Goal
Replace the current sprite-based score display (GRP0/GRP1 + ScoreSpriteFont + RESP positioning) with PF-based score display (PF0/PF1/PF2 per-scanline). This frees ROM space, ZP variables, and simplifies bank2 significantly.

## Scope
- **Score line ("nnnn"):** Convert to PF-based rendering
- **Level line ("LVnn"):** Keep as sprites (pre-computed in bank0 VBLANK, minimal code)

## Current State
- **bank2** renders "LVnn" level line and "nnnn" score line using GRP0/GRP1 sprites
- Score uses **ScoreSpriteFont** (10 digits × 8 bytes = 80 bytes ROM in bank2)
- Font data loaded via 4 digit loops (~200 bytes of loop code in bank2)
- Font packed into FontP0/P1 + ScoreDigit2/3 (20 bytes ZP)
- RESP positioning needed for each sprite pair (~60 bytes SetObjectXPos calls)
- **bank0** VBLANK pre-computes level digits into FontP0/P1 (10 bytes ZP)

## Target: PF-Based Score
- Each digit rendered as **3-pixel-wide PF pattern** (fits in PF0/PF1/PF2)
- Digits stored as **5-byte row tables** in ROM (one table per digit 0-9)
- Score rendered by writing PF0/PF1/PF2 per-scanline — no sprites needed
- Level line can stay as sprites (only 2 chars "LV") or also convert to PF

## PF Digit Layout (4 digits across screen)
```
Pixel:  0-3   4-11  12-19  20-27  28-35  36-39
        PF0   PF1    PF2   PF2(r) PF1(r) PF0(r)
        [1]   [2]    [2]   [3]    [3]    [4]
```
- Each digit = 3 PF pixels wide (12 color clocks)
- 4 digits fit in 40 PF pixels with gaps
- PF0 nibble: left digit (4 pixels, only 3 used)
- PF1 byte: second digit (8 pixels, only 3 used)
- PF2 byte: third digit mirrored + fourth digit start
- With reflection (CTRLPF D0=1), right half mirrors left → only need to set left half

## ZP Variables Freed
| Variable | Bytes | Current Use | After Change |
|----------|-------|-------------|--------------|
| FontP0 | 5 | Level/score font rows | **Freed** (or reused for level sprites) |
| FontP1 | 5 | Level/score font rows | **Freed** |
| ScoreDigit2 | 5 | Score digit 2-3 rows | **Freed** |
| ScoreDigit3 | 5 | Score digit 4 rows | **Freed** |
| ScoreTh/Te/Hu/On | 4 | Score digit values | Keep (needed for PF lookup) |
| Temp | 1 | Scratch | Keep |
| **Total freed** | **20 bytes** | | |

## ROM Space Freed
| Item | Bytes | Notes |
|------|-------|-------|
| ScoreSpriteFont | ~80 | 10 digits × 8 bytes (only 5 used per digit) |
| Score font loading loops | ~120 | 4 digit loads × ~30 bytes each |
| Score compose loop | ~50 | Pack pairs into FontP0/P1 |
| Score positioning (SetObjectXPos ×2) | ~40 | RESP positioning for P0/P1 |
| Score rendering loop | ~20 | GRP0/GRP1 write loop |
| **Total freed** | **~310 bytes** | |

## New ROM Needed
| Item | Bytes | Notes |
|------|-------|-------|
| PF digit lookup table | ~50 | 10 digits × 5 rows × 1 byte |
| Score PF rendering code | ~60 | 5 scanlines × PF0/PF1/PF2 writes |
| **Total added** | **~110 bytes** | |

**Net ROM savings: ~200 bytes** — significant for the phased kernel space budget.

## Implementation Steps

### Phase 1: Design PF Digit Layout
- [ ] Define PF pixel layout for 4 digits (which PF register holds which digit)
- [ ] Calculate pixel positions for each digit (centered or left-aligned)
- [ ] Verify reflection mode works correctly with digit layout
- [ ] Create PF lookup table: `PFDigitFont` — 10 digits × 5 rows, each row is a PF pattern byte

### Phase 2: Rewrite bank2 Score Rendering
- [ ] Remove old score code (digit loading loops, compose loop, RESP positioning, GRP rendering)
- [ ] Add new score code:
  - Load digit values from ScoreTh/Te/Hu/On
  - For each of 5 scanlines:
    - Compute PF0 = digit1 pattern (nibble)
    - Compute PF1 = digit2 pattern (byte)
    - Compute PF2 = digit3|digit4 pattern (byte, or mirrored)
    - Write PF0, PF1, PF2
    - sta WSYNC
- [ ] Verify timing fits in bank2 (remove ~200 bytes, add ~110 bytes)

### Phase 3: Clean Up ZP and bank0
- [ ] Remove ScoreDigit2/3 ZP variables (no longer needed)
- [ ] Keep FontP0/P1 ZP (still used by level sprites)
- [ ] Keep bank0 VBLANK level digit pre-computation (still needed for level sprites)
- [ ] Update bank2 ZP declarations

### Phase 4: Verify and Test
- [ ] Build and verify no assembly errors
- [ ] Test score display shows correct digits
- [ ] Test level display still works (unchanged sprites)
- [ ] Test score updates when score changes
- [ ] Verify no visual artifacts (flicker, misalignment)
- [ ] Measure bank2 scanline count (should be faster without sprite positioning)

## PF Digit Font Data (example)
```asm
; 3 pixels wide, stored as PF bit patterns
; Bit 7 = leftmost pixel, bit 5 = rightmost pixel of digit
PFDigitFont:
; Digit 0:  ###
;           # #
;           # #
;           # #
;           ###
  .byte %11100000, %10100000, %10100000, %10100000, %11100000
; Digit 1:   #
;            #
;            #
;            #
;            #
  .byte %01000000, %11000000, %01000000, %01000000, %11100000
; ... (digits 2-9)
```

## Risks
- PF-based digits are wider than sprite digits (3 PF pixels = 12 color clocks vs 3 sprite pixels = 3 color clocks)
- Score may look "stretched" compared to current sprite rendering
- Reflection mode means left/right halves mirror — need to account for this in digit placement
- Level line stays as sprites (simpler, only 2 chars, pre-computed in VBLANK)
- bank2 timing changes — need to verify HUD still fits in 58 scanlines

## Dependencies
- None — this change is self-contained in bank2 + bank0 VBLANK
- Can be done independently of the kernel flicker fix
