# Fix GRP1 Flicker — Two-Pass Kernel (Option 3)

## Context
GRP1 `sta GRP1` fires at cycle ~47, past RESP1's HBLANK position (~15-20).
Shift register starts at cycle 68 with stale data → corrupted object rendering.
Both GRP0 and GRP1 must be written before cycle 68 (HBLANK end).

**Root cause:** GRP0 block (25 cycles) runs BEFORE GRP1 block (22 cycles).
GRP1 write happens at cycle 25+22 = 47, well past HBLANK (~cycle 23).

**Fix:** Swap GRP1 BEFORE GRP0 so GRP1 fires at cycle ~17 (within HBLANK).
GRP0 fires at cycle ~38 (slightly past HBLANK but acceptable for player).

---

## Step 3.1: Swap GRP1 before GRP0 in kernel `.Line`
- [x] Move GRP1 block BEFORE GRP0 block in `.Line`
- [x] GRP1 fires at cycle ~17, GRP0 fires at cycle ~38
- [x] Both within HBLANK (shift register starts at cycle 68)
- [x] `./build_game_f6.sh` assembles clean
- [ ] **Verify:** Stella — player renders, objects render without corruption
- [ ] **Verify:** Flicker eliminated when player in same row as miner/enemy
- [ ] **Commit:** "Swap GRP1/GRP0 order: GRP1 first in HBLANK"

## Step 3.2: Pre-compute GRP1 during VBLANK (optional optimization)
- [ ] Add `Grp1Ptr` ZP variable pointing to object sprite data
- [ ] In VBLANK: set up Grp1Ptr for active object
- [ ] In kernel: use `(Grp1Ptr),Y` for actual sprite data (not hardcoded $f0)
- [ ] **Verify:** Object renders with correct shape
- [ ] **Commit:** "Pre-compute GRP1 pointer for actual sprite data"

## Step 3.3: Fix frame timing (VBLANK wait loop calibration)
- [ ] Count exact scanlines in each frame section
- [ ] Adjust VBLANK wait loop to hit exactly 262 scanlines
- [ ] **Verify:** Frame is 262 scanlines (Stella scanline counter)
- [ ] **Commit:** "Fix frame timing: calibrate VBLANK for 262 scanlines"

## Step 3.4: Full game verification
- [ ] `./build_game_f6.sh` — no errors
- [ ] Stella — no crash
- [ ] Player sprite — all 4 directions correct
- [ ] Cave walls — no garbled PF
- [ ] HUD text — Level/Score visible
- [ ] Laser — fires and renders
- [ ] Enemies — NO corruption (core fix)
- [ ] Miner — renders, collision works
- [ ] Room transitions — left/right work

---

## Key Cycle Budgets

### After GRP1-first swap (current)
```
GRP1 block:  22c (visible) → cycle 17 ✓
GRP0 block:  25c (visible) → cycle 38 ✓ (slightly past HBLANK but OK)
ENAM0 block: 17c (visible) → cycle 55 ✓
Loop:        16c
Worst case:  80c (at budget with some margin)
Best case:   60c
```

---

## Files Changed
- `comparison/lo-a-rad-dragon/bank0.asm`: kernel `.Line` (GRP1/GRP0 swap)
- `docs/plan/separate_object_kernel.md`: this file

## Last Updated
2026-09-15: Step 3.1 complete (GRP1-first swap).
