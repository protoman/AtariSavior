# Fix Laser Flicker — VBLANK Pre-computation Plan

## Problem

The kernel `.Line` block takes up to **84 cycles** in the worst case (sprite visible + object visible + laser active on matching scanline). The 2600 budget is 76 cycles per scanline. This causes frame-stretching flicker on every scanline where all three conditions overlap.

## Cycle Analysis (current kernel, WSYNC at END)

```
.Line:
  GRP0 block:   18 cycles (no sprite) to 30 cycles (sprite visible)
  GRP1 block:   11 cycles (no object) to 25 cycles (object visible)
  ENAM0 block:  11 cycles (laser off) to 21 cycles (laser active + match)
  inc Scanline: 5 cycles
  sta WSYNC:    3 cycles
  ─────────────────────────────────────────
  Best case:    48 cycles ✓
  Worst case:   84 cycles ✗ (8 over budget!)
```

The flicker happens when: player visible (8 scanlines) + enemy visible (8 scanlines) + laser active (any scanline while LaserActive > 0). In the second room (which has enemies), firing the laser triggers flicker on every scanline where player and enemy overlap vertically.

## Root Cause: Three Expensive Conditional Blocks

1. **GRP0 (30 cycles visible)**: bounds check + `PlayerDir` branch + direct table load + `jmp`
2. **GRP1 (25 cycles visible)**: `ActiveObjectOn` check + subtraction + bounds check + `jmp`
3. **ENAM0 (21 cycles active+match)**: `LaserActive` check + `eor` + `bne` + `jmp`

## Solution: VBLANK Pre-computation + Simplified Kernel

Pre-compute three values during VBLANK. The kernel reads single bytes instead of doing multi-step checks. Reuse collision-scratch ZP bytes (`$8C-$90`) which are free during the kernel (collision detection runs in overscan only).

### ZP Reuse Map

| ZP Address | Original Var | Kernel Reuse | Purpose |
|-----------|-------------|-------------|---------|
| `$8c` | CollisionX | Grp0PtrLo | GRP0 sprite table pointer (low) |
| `$8d` | CollisionCellX | Grp0PtrHi | GRP0 sprite table pointer (high) |
| `$8e` | CollisionCellY | ObjTop | Object visible top scanline |
| `$8f` | CollisionEndX | ObjBot | Object visible bottom scanline |
| `$90` | CollisionEndY | LaserScanline | Laser match scanline (or $FF) |

These5 bytes are collision-scratch variables only used in `CheckEnemyHit` / `PlayerHitsMap` during overscan. They are never accessed during the kernel or VBLANK.

## Implementation Steps

### Step 1: Add ZP aliases for reused variables

In bank0.asm, after the existing variable declarations, add aliases:

```asm
; Kernel scratch (reused from collision vars — only accessed in overscan)
Grp0PtrLo       = CollisionX       ; $8c
Grp0PtrHi       = CollisionCellX   ; $8d
ObjTop          = CollisionCellY   ; $8e
ObjBot          = CollisionEndX    ; $8f
LaserScanline   = CollisionEndY    ; $90
```

**Verify:** Assembles without errors. These are EQU aliases, no new ZP allocation.

### Step 2: Pre-compute GRP0 pointer in VBLANK

After the HMOVE/stelladaptor positioning block and before the PF buffer copy, add:

```asm
; --- Pre-compute GRP0 sprite table pointer (based on PlayerDir) ---
  ldy #>PlayerSpriteRight
  ldx #<PlayerSpriteRight
  lda PlayerDir
  beq .UseRightSprite
  ldy #>PlayerSpriteLeft
  ldx #<PlayerSpriteLeft
.UseRightSprite:
  stx Grp0PtrLo
  sty Grp0PtrHi
```

**Verify:** Assembles. Test in Stella: player sprite should render identically to before (this step only pre-computes the pointer; the kernel still uses the old code until Step5).

### Step 3: Pre-compute object scanline range in VBLANK

After Step2, add:

```asm
; --- Pre-compute object scanline range (for GRP1 kernel check) ---
  lda ActiveObjectOn
  beq .NoObjPrep
  lda ActiveObjectY
  sta ObjTop
  clc
  adc #PLAYER_HEIGHT
  sta ObjBot
  jmp .ObjPrepDone
.NoObjPrep:
  lda #$ff      ; all scanlines < $ff → bcc always taken → NoObject
  sta ObjTop
.ObjPrepDone:
```

**Verify:** Assembles. Test in Stella: enemies should still render (kernel unchanged, just pre-computing values).

### Step 4: Pre-compute laser scanline in VBLANK

After Step3, add:

```asm
; --- Pre-compute laser scanline (for ENAM0 kernel check) ---
  lda LaserActive
  beq .NoLaserPrep
  lda LaserY
  sta LaserScanline
  jmp .LaserPrepDone
.NoLaserPrep:
  lda #$ff      ; impossible scanline → never matches → ENAM0 always off
  sta LaserScanline
.LaserPrepDone:
```

**Verify:** Assembles. Test in Stella: laser should still render (kernel unchanged).

### Step 5: Rewrite kernel `.Line` with optimized blocks

Replace the three conditional blocks in `.Line`:

**GRP0 block (new, 25 cycles visible / 18 not):**
```asm
; --- GRP0: use pre-computed pointer (no PlayerDir branch) ---
  lda Scanline          ; 3
  sec                   ; 2
  sbc PlayerY           ; 3
  cmp #PLAYER_HEIGHT    ; 2
  bcs .NoSprite         ; 2-3
  tay                   ; 2
  lda (Grp0Ptr),Y       ; 5  ← indirect indexed, no direction check
  jmp .Put              ; 3
.NoSprite:
  lda #0                ; 2
.Put:
  sta GRP0              ; 3
```

**GRP1 block (new, 22 cycles visible / 14 not):**
```asm
; --- GRP1: pre-computed range check (no subtraction) ---
  lda Scanline          ; 3
  cmp ObjTop            ; 3
  bcc .NoObject         ; 2-3 (below top)
  cmp ObjBot            ; 3
  bcs .NoObject         ; 2-3 (at or past bottom)
  lda #$f0              ; 2
  .byte $2c             ; 4 (BIT skip: skips next lda #0)
.NoObject:
  lda #0                ; 2
  sta GRP1              ; 3
```

**ENAM0 block (new, 17 cycles active+match / 14 not):**
```asm
; --- ENAM0: pre-computed scanline match ---
  lda Scanline          ; 3
  cmp LaserScanline     ; 3
  bne .LaserOff         ; 2-3
  lda #$02              ; 2
  .byte $2c             ; 4 (BIT skip: skips next lda #0)
.LaserOff:
  lda #0                ; 2
  sta ENAM0             ; 3
```

**Verify:** Assembles. Full game test: player, enemies, laser, HUD, room transitions all work.

### Step 6: Update AGENTS.md kernel cycle analysis

Update the "Current kernel cycle count" section with new numbers:

```
Best case (no sprite, no object, no laser): 53 cycles
Worst case (all active): 72 cycles (4 under budget)
Margin: 4 cycles
```

### Step 7: Update constant_cycle_kernel.md with results

Add results section documenting what worked and what failed.

## Expected Cycle Budget (after fix)

| Path | Old | New | Margin |
|------|-----|-----|--------|
| No sprite, no object, no laser | 48 | 53 | 23 under |
| Sprite + object, no laser | 74 | 69 | 7 under |
| Sprite + object + laser (wrong scanline) | **82** | **69** | **7 under** |
| Sprite + object + laser (matching scanline) | **84** | **72** | **4 under** |

All paths under76 cycles. The BIT skip trick (`.byte $2c`) eliminates the `jmp` instructions, saving 3 cycles per block.

## Risk Assessment

- **GRP0 indirect indexed**: `lda (Grp0Ptr),Y` is 5 cycles (possibly 6 if page-crossing). Ensure `PlayerSpriteRight` and `PlayerSpriteLeft` are page-aligned OR that base+7 doesn't cross a page boundary. Check with `align 256` before sprite data.
- **ZP aliasing**: Using collision-scratch bytes as kernel scratch is safe because `CheckEnemyHit` / `PlayerHitsMap` only run in overscan (after the kernel finishes). Verify no kernel code accesses `CollisionX` etc.
- **BIT skip trick**: `.byte $2c` is `BIT $abs` (4 cycles). The skipped instruction's opcode+operand form the address read by BIT. `lda #$f0` → `BIT $02F0` (reads TIA, harmless). `lda #$02` → `BIT $02A9` (reads TIA, harmless). `lda #0` → `BIT $0200` (reads TIA, harmless). All safe.
- **ObjTop=$FF sentinel**: When no object is active, `cmp ObjTop` with ObjTop=$FF means all scanlines 0-191 are < $FF, so `bcc` is always taken → NoObject. Correct.
- **LaserScanline=$FF sentinel**: When laser is inactive, `cmp LaserScanline` with LaserScanline=$FF means no visible scanline (0-191) matches, so `bne` always taken → LaserOff. Correct.

## Verification Checklist

After implementation, verify:
1. `./build_game_f6.sh` assembles without errors
2. Stella launches without crash
3. Player sprite renders correctly (all 4 directions)
4. Cave walls render correctly (no garbled PF)
5. HUD text renders (Level/Score/Lives/Time)
6. Laser fires and renders (no flicker on single-room test)
7. Enemies render (no flicker when player + enemy + laser overlap)
8. Left/right room transitions work
9. Miner pickup works
10. No regressions in detection script (all 5 checks PASS)

## Files Changed

- `comparison/lo-a-rad-dragon/bank0.asm`: Steps 1-5 (ZP aliases + VBLANK pre-computation + kernel rewrite)
- `docs/plan/fix_laser_flicker.md`: This file (created)
- `AGENTS.md`: Step6 (update cycle analysis)

---

## Results (2026-09-15)

### Completed
- Step 1: ZP aliases added (Grp0Ptr, ObjTop, ObjBot, LaserScanline)
- Step 2-4: VBLANK pre-computation added (GRP0 pointer, object range, laser scanline)
- Step 5: Kernel `.Line` rewritten with BIT skip trick
- Build clean, Stella launches, all 5 detection checks PASS
- Zero frame drops on static screenshot

### DASM Gotcha: indirect indexed pointer
`lda (Grp0Ptr),Y` requires `Grp0Ptr` as a SINGLE symbol (low byte address), with high byte at `Grp0Ptr+1`. Cannot use separate `Grp0PtrLo`/`Grp0PtrHi` EQU aliases — DASM resolves the `(),Y` form by looking for `symbol` and `symbol+1`. Initial attempt used separate aliases and failed with "Unresolved Symbol Grp0Ptr". Fixed by defining `Grp0Ptr = CollisionX` (single EQU).

### What the fix achieved
- Worst-case kernel: 84 → 72 cycles (12 cycles saved)
- All kernel paths now under76 cycles
- The BIT skip trick (`.byte $2c`) eliminates `jmp` instructions, saving3 cycles per block
- Collision-scratch ZP bytes ($8C-$90) safely reused as kernel scratch (only accessed in overscan)

### Still needs user verification
- Laser flicker when player + enemy + laser overlap (second room)
- Player sprite rendering in all4 directions
- Room transitions, miner pickup, HUD
- `docs/plan/constant_cycle_kernel.md`: Step7 (add results)
