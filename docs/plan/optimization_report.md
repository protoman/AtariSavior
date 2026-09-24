# Optimization Report: Reduce ZP/RAM/bank0 Size to Eliminate Flicker

## Current State
- Kernel worst case: **79 cycles** (3 over 76 budget)
- Flicker occurs when: player visible + enemy visible + laser active (rare but NOT acceptable)
- ZP used during kernel: ~64 bytes (game vars + PF buffers)
- ZP free during kernel: ~70 bytes (after score variable removal)
- bank0 ROM: at capacity (GameStart at $f500)

## Root Cause Analysis

The kernel `.Line` body has three conditional sections that cause variable cycle counts:

| Section | Best | Worst | Delta | Source of variation |
|---------|------|-------|-------|-------------------|
| GRP1 (enemy) | 13c | 22c | +9c | Object visibility check |
| GRP0 (player) | 17c | 24c | +7c | Player range check (ZP buffer) |
| ENAM0 (laser) | 13c | 17c | +4c | Laser scanline match |
| Loop control | 15c | 16c | +1c | LineCount branch |
| **Total** | **58c** | **79c** | **+21c** | |

**Worst case = 79c.** Need to reach ≤76c. **Gap: 3 cycles.**

## Optimization Opportunities

### 1. Pre-compute GRP1 visibility flag (saves up to 9c)
**Current:** 22c worst case (two comparisons + BIT skip)
**Proposed:** Pre-compute during VBLANK, store in ZP
```
; During VBLANK:
lda #0
sta Grp1Value          ; default: no object
lda ActiveObjectOn
beq .NoGrp1
; Object is active — check if it's visible THIS frame
; (store ObjTop, ObjBot already done)
; The check happens in kernel, but we can pre-compute
; whether the object is visible on ANY scanline

; In kernel (simplified):
lda Grp1Value          ; 3c (load pre-computed)
sta GRP1               ; 3c
```
**Savings:** 22c → 6c = **16 cycles** (when object visible)
**ZP cost:** 1 byte (Grp1Value at $C7, reusing freed space)
**Risk:** Low — object visibility doesn't change within a frame

### 2. Pre-compute ENAM0 visibility flag (saves up to 11c)
**Current:** 17c worst case (comparison + BIT skip)
**Proposed:** Pre-compute during VBLANK, store in ZP
```
; During VBLANK:
lda #0
sta Enam0Value          ; default: no laser
lda LaserActive
beq .NoEnam0
lda #$02
sta Enam0Value          ; laser active
.NoEnam0:

; In kernel (simplified):
lda Enam0Value          ; 3c (load pre-computed)
sta ENAM0               ; 3c
```
**Savings:** 17c → 6c = **11 cycles** (when laser active)
**ZP cost:** 1 byte (Enam0Value at $C8, reusing freed space)
**Risk:** Low — laser state doesn't change within a frame

### 3. Optimize GRP0 range check (saves 1-2c)
**Current:** 24c worst case (subtract + compare + ZP load + jmp)
**Proposed:** Eliminate jmp by restructuring
```
; Current:
  lda Scanline       ; 3
  sec                 ; 2
  sbc PlayerY         ; 3
  cmp #PLAYER_HEIGHT  ; 2
  bcs .NoSprite       ; 2
  tay                 ; 2
  lda PlayerGrp0,Y   ; 4
  jmp .Put            ; 3  ← can we eliminate this?
.NoSprite:
  lda #0              ; 2
.Put:
  sta GRP0            ; 3

; Optimized (BIT skip):
  lda Scanline       ; 3
  sec                 ; 2
  sbc PlayerY         ; 3
  cmp #PLAYER_HEIGHT  ; 2
  bcs .NoSprite       ; 2
  tay                 ; 2
  lda PlayerGrp0,Y   ; 4
  .byte $2c           ; 4  BIT skip
.NoSprite:
  lda #0              ; 2
  sta GRP0            ; 3
```
**Savings:** 24c → 25c (BIT skip is WORSE!) — **No improvement possible**
**Note:** The jmp is already optimal. BIT skip adds 1c.

### 4. Remove unused ZP variables (free ~5 bytes)
**Candidates:**
- `FontPtrLo2` / `FontPtrHi2` ($bf-$c0): reserved, unused → **2 bytes**
- `frame_phase` ($c1): reserved, unused → **1 byte**
- `FontPtrLo` / `FontPtrHi` ($bd-$be): reserved, unused → **2 bytes**

**Total freed: 5 bytes** (can be used for GRP1/ENAM0 pre-computation)

### 5. Remove dead code from bank0 (free ~20-50 bytes ROM)
**Candidates:**
- `LoadFontDigit` subroutine: only used by VBLANK pack, can be inlined
- `PackLevelLine` subroutine: only used once, can be inlined
- Unused collision code: check for dead branches

### 6. Optimize VBLANK timing (free ~5 scanlines)
**Current:** VBLANK has 18 WSYNC waits (ldx #18)
**Proposed:** Reduce to 13 after adding pre-computation code
**Benefit:** More VBLANK time for pre-computation

## Combined Impact

| Optimization | Cycles saved | ZP freed | ROM freed |
|-------------|-------------|----------|-----------|
| GRP1 pre-compute | 16c (rare) | 1 byte | 0 |
| ENAM0 pre-compute | 11c (rare) | 1 byte | 0 |
| Remove unused ZP | 0 | 5 bytes | 0 |
| Remove dead code | 0 | 0 | ~20-50 bytes |
| **Total** | **27c** | **7 bytes** | **~20-50 bytes** |

**New worst case:** 79c - 27c = **52 cycles** (well under 76!)

**Note:** GRP1 and ENAM0 savings only apply when those objects are active. But even without them, the kernel is at 79c which is only 3 over budget.

## Recommended Implementation Order

1. **Remove unused ZP variables** (5 bytes freed, no risk)
2. **Pre-compute GRP1 flag** (1 byte ZP, saves 16c when enemy visible)
3. **Pre-compute ENAM0 flag** (1 byte ZP, saves 11c when laser active)
4. **Remove dead code** (ROM savings, no risk)
5. **Verify kernel timing** (measure with Stella debugger)

## Risk Assessment
- **Low risk:** Removing unused ZP, removing dead code
- **Medium risk:** Pre-computing GRP1/ENAM0 flags (must ensure VBLANK timing is correct)
- **No risk:** All changes are backward-compatible (HUD rebuild later)

## Expected Outcome
- Kernel worst case: **52-58 cycles** (down from 79)
- Zero flicker on ALL scanlines
- ~7 bytes additional ZP freed
- ~20-50 bytes ROM freed
