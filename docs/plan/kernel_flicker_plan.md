# Kernel Flicker Elimination Plan

## Goal
Reduce kernel worst case from 79 to ≤76 cycles by pre-computing GRP1/ENAM0 flags during VBLANK.

## Checkpoint 1: Remove unused ZP variables
- [ ] Remove `FontPtrLo` ($bd), `FontPtrHi` ($be) — unused
- [ ] Remove `FontPtrLo2` ($bf), `FontPtrHi2` ($c0) — unused
- [ ] Remove `frame_phase` ($c1) — unused
- [ ] Build and verify no errors
- **Freed: 5 bytes ZP**

## Checkpoint 2: Add ZP aliases for pre-computed flags
- [ ] Add `Grp1Value = $c7` (reusing freed ScoreDigit3 space)
- [ ] Add `Enam0Value = $c8` (reusing freed ScoreDigit3 space)
- [ ] Build and verify no errors

## Checkpoint 3: Pre-compute GRP1 flag during VBLANK
- [ ] After existing ObjTop/ObjBot setup, add:
  ```
  lda #0
  sta Grp1Value          ; default: no object
  lda ActiveObjectOn
  beq .NoGrp1Prep
  lda #$f0
  sta Grp1Value          ; object active → $f0
  .NoGrp1Prep:
  ```
- [ ] Build and verify no errors
- **Checkpoint test:** GRP1 should render correctly (object visible when in range)

## Checkpoint 4: Pre-compute ENAM0 flag during VBLANK
- [ ] After existing LaserScanline setup, add:
  ```
  lda #0
  sta Enam0Value         ; default: no laser
  lda LaserActive
  beq .NoEnam0Prep
  lda #$02
  sta Enam0Value         ; laser active → $02
  .NoEnam0Prep:
  ```
- [ ] Build and verify no errors
- **Checkpoint test:** Laser should render correctly when active

## Checkpoint 5: Rewrite kernel GRP1 to use pre-computed flag
- [ ] Replace current GRP1 section with:
  ```
  ; --- GRP1: load pre-computed value ---
  lda Grp1Value          ; 3c
  sta GRP1               ; 3c
  ```
- [ ] Build and verify no errors
- **Cycle count: 6c** (down from 22c)
- **Checkpoint test:** Object renders correctly when in range, disappears when out of range

## Checkpoint 6: Rewrite kernel ENAM0 to use pre-computed flag
- [ ] Replace current ENAM0 section with:
  ```
  ; --- ENAM0: load pre-computed value ---
  lda Enam0Value         ; 3c
  sta ENAM0              ; 3c
  ```
- [ ] Build and verify no errors
- **Cycle count: 6c** (down from 17c)
- **Checkpoint test:** Laser renders correctly when active

## Checkpoint 7: Verify kernel timing
- [ ] Build final ROM
- [ ] Run Stella debugger: `clearbreaks` → `breakLabel f139` → `run`
- [ ] Check worst case scanline count
- [ ] **Target: ≤76 cycles per scanline**
- [ ] Visual test: player + enemy + laser overlap → no flicker

## Expected Result
| Section | Before | After |
|---------|--------|-------|
| GRP1 | 22c | 6c |
| GRP0 | 24c | 24c |
| ENAM0 | 17c | 6c |
| Loop | 16c | 16c |
| **Worst case** | **79c** | **52c** |
| **Flicker** | Yes (3c over) | **None** |

## Files Modified
- `comparison/lo-a-rad-dragon/bank0.asm` — VBLANK pre-computation + kernel rewrite
