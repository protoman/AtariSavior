# Fix GRP1 Flicker — Option 2 (Primary) + Option 3 (Fallback)

## Context
GRP1 `sta GRP1` fires at cycle ~47, past RESP1's HBLANK position (~15-20).
Shift register starts at cycle 68 with stale data → corrupted object rendering.
Both GRP0 and GRP1 must be written before cycle 68 (HBLANK end).

**Goal:** Write GRP1 during HBLANK (cycle ~16), write GRP0 unconditionally
during HBLANK (cycle ~38). Eliminate GRP0 conditional check via VBLANK
pre-computation. Worst case ≤57 cycles (19 cycles margin).

---

## Option 2: Pre-computed GRP0 + GRP1-First Kernel

### Step 1: Swap GRP0/GRP1 write order in kernel `.Line`
- [ ] Move GRP1 block BEFORE GRP0 block in `.Line` (lines 465-500)
- [ ] GRP1 fires at cycle ~16, GRP0 fires at cycle ~38
- [ ] Both within HBLANK (before shift register starts at cycle 68)
- [ ] **Verify:** `./build_game_f6.sh` assembles clean
- [ ] **Verify:** Stella launches, player renders, objects render without corruption
- [ ] **Verify:** All 5 detection checks PASS
- [ ] **Commit:** "Swap GRP0/GRP1 order: GRP1 first in HBLANK"

### Step 2: Pre-compute GRP0 during VBLANK
- [ ] Add `Grp0Byte = MapPtrLo` EQU alias ($8A — free during kernel, PF copy done)
- [ ] In VBLANK after HMOVE positioning, before PF copy:
  - Load `PlayerY`
  - Check if player is visible (PlayerY < 192 - PLAYER_HEIGHT)
  - If visible: `LDY PlayerY / LDA (Grp0Ptr),Y / STA Grp0Byte`
  - If not visible: `LDA #0 / STA Grp0Byte`
  - NOTE: This computes ONE byte for scanline PlayerY. For the 8 visible
    rows, the kernel still needs `(Grp0Ptr),Y` addressing. So this step
    only eliminates the `cmp PlayerY / bcs .NoSprite / tay` conditional
    check — not the indirect indexed load.
  - Actually: keep `(Grp0Ptr),Y` in kernel but remove conditional by using
    a ZP range check: if `Scanline < PlayerY` or `Scanline >= PlayerY+8`,
    skip the load. This doesn't save much.
  - **REVISED approach:** Keep GRP0 conditional but with GRP1 first. The swap
    alone fixes the timing. Pre-computation adds complexity without fixing
    the core issue. **Step 2 is deferred.**

### Step 3: Remove `.Row` WSYNC to restore frame timing
- [ ] Remove `inc Scanline` + `sta WSYNC` from `.Row` (lines 462-463)
- [ ] Frame returns to 262 scanlines (currently 274 due to 12 extra WSYNCs)
- [ ] **Verify:** Frame is 262 scanlines (Stella scanline counter)
- [ ] **Verify:** HUD text at correct vertical position
- [ ] **Verify:** Cave positioned correctly
- [ ] **Commit:** "Remove .Row WSYNC: restore 262-scanline frame"

### Step 4: Update documentation
- [ ] Update `docs/plan/constant_cycle_kernel.md` with new cycle counts
- [ ] Update `AGENTS.md` kernel section
- [ ] **Commit:** "Update kernel docs: GRP1-first timing"

### Step 5: Full game verification
- [ ] `./build_game_f6.sh` — no errors
- [ ] Stella — no crash
- [ ] Player sprite — all 4 directions correct
- [ ] Cave walls — no garbled PF
- [ ] HUD text — Level/Score/Lives/Time
- [ ] Laser — fires and renders
- [ ] Enemies — NO corruption (core fix)
- [ ] Miner — renders, collision works
- [ ] Room transitions — left/right work
- [ ] Detection script — all 5 checks PASS

---

## Option 3: Full HERO-Style Split (Fallback)

**Only implement if Option 2 fails.** This is a major refactor: split the cave
kernel into two passes — object pass (GRP1 conditional) + cave pass
(GRP0+PF unconditional).

### Architecture
```
Object pass:  GRP1 conditional (miner/enemy), ENAM0 (laser) — variable cycles
Cave pass:    GRP0 from (zp),Y + PF from tables — constant 57 cycles
HUD pass:     bank2 text rendering — unchanged
```

### Step 3.1: Restructure kernel into two-pass loop
- [ ] Add new `.ObjectLine:` loop BEFORE `.Line` loop
- [ ] `.ObjectLine:` handles GRP1 conditional + ENAM0 only (~30 cycles)
- [ ] `.Line:` handles GRP0 conditional + PF from tables only (~40 cycles)
- [ ] Both loops iterate over the same scanlines (12 rows × 12 lines = 144)
- [ ] **Verify:** Both loops assemble, frame structure correct
- [ ] **Commit:** "Two-pass kernel: object pass + cave pass"

### Step 3.2: Object pass — GRP1 + ENAM0
- [ ] Object pass writes GRP1 at cycle ~16 (within HBLANK)
- [ ] Object pass writes ENAM0 at cycle ~30 (within HBLANK)
- [ ] PF not written in object pass (cave pass handles it)
- [ ] GRP0 not written in object pass (cave pass handles it)
- [ ] Loop uses `Scanline` counter, same as cave pass
- [ ] **Verify:** Objects render without corruption
- [ ] **Verify:** Laser renders correctly
- [ ] **Commit:** "Object pass: GRP1 + ENAM0 in HBLANK"

### Step 3.3: Cave pass — GRP0 + PF (unconditional)
- [ ] Cave pass writes GRP0 via `(Grp0Ptr),Y` — no conditional
- [ ] Cave pass writes PF0/PF1/PF2 from ZP buffers (TIA persists)
- [ ] Cave pass writes COLUPF from buffer
- [ ] 57 cycles/scanline (matches HERO's $DC00 kernel)
- [ ] **Verify:** Player renders correctly
- [ ] **Verify:** Cave walls render correctly
- [ ] **Commit:** "Cave pass: unconditional GRP0 + PF"

### Step 3.4: Frame timing and VBLANK adjustment
- [ ] Two passes each iterate 144 scanlines → total kernel = 288 scanlines!
- [ ] Need to reduce: either objects render fewer lines, or use interleave
- [ ] **Alternative:** Object pass renders only the 8 scanlines where the
    object is visible (PlayerY..PlayerY+7), cave pass renders all 144.
- [ ] **Verify:** Total frame = 262 scanlines
- [ ] **Commit:** "Fix two-pass frame timing"

### Step 3.5: Remove `.Row` WSYNC (same as Option 2 Step 3)
- [ ] Remove `inc Scanline` + `sta WSYNC` from `.Row`
- [ ] **Commit:** "Remove .Row WSYNC"

### Step 3.6: Update documentation
- [ ] Update `docs/plan/constant_cycle_kernel.md`
- [ ] Update `AGENTS.md`
- [ ] **Commit:** "Update docs: two-pass kernel architecture"

### Step 3.7: Full game verification (same as Option 2 Step 5)
- [ ] All 10 verification checks PASS
- [ ] **Commit:** "Two-pass kernel verified working"

---

## Key Cycle Budgets

### Option 2 (after swap)
```
GRP1 block:  22c (visible) → cycle 16 ✓
GRP0 block:  25c (visible) → cycle 38 ✓
ENAM0 block: 17c (visible) → cycle 55 ✓
Loop:        12c
Worst case:  76c (at budget)
Best case:   58c
```

### Option 3 (two-pass)
```
Object pass:  GRP1 22c + ENAM0 17c + loop 12c = 51c (worst)
Cave pass:    GRP0 25c + PF 21c + COLUPF 7c + loop 12c = 65c (worst)
```

---

## Files Changed
- `comparison/lo-a-rad-dragon/bank0.asm`: kernel `.Line` + `.Row`
- `docs/plan/separate_object_kernel.md`: this file
- `docs/plan/constant_cycle_kernel.md`: updated cycle counts
- `AGENTS.md`: kernel architecture section

## Last Updated
2026-09-15: Plan created for Option 2 (primary) + Option 3 (fallback).
