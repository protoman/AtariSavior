# Constant-Cycle Kernel Plan

## Goal
Convert the kernel from variable-cycle conditional branches (45-81 cycles/scanline, 20/27 paths over budget) to a HERO-style constant-cycle design (~58-63 cycles/scanline).

## Problem Analysis

### Current Kernel Cycle Counts
| Check | Cheap path | Expensive path | Delta |
|-------|-----------|---------------|-------|
| GRP0 (sprite) | `lda #0` (2c) | `tay` + `lda table,Y` + `jmp` (9c) | **+7c** |
| GRP1 (object) | `beq` taken (3c) | range check + `jmp` (14c) | **+11c** |
| ENAM0 (laser) | `beq` taken (3c) | `eor` + `jmp` (10c) | **+7c** |

Combined worst case: **+25 cycles** over minimum.

### Additional Issue
The `.Row` PF setup (~49 cycles) runs on the SAME scanline as the first `.Line` iteration. Total: ~123 cycles on tile-row transitions — eats 2 entire scanlines per tile row.

### Why Previous Stack Attempt Failed
- Pushed 192 GRP0 bytes onto stack via `pha`
- Bank2's HUD trampoline doesn't pop them → 48 stale bytes → stack corruption
- Crash on left/right input (invalid instruction in Stella)
- Push loop ran without WSYNC making VBLANK timing depend on PlayerY

**Root cause:** Using actual stack operations (`pha`/`pla`) conflicts with bank switching and JSR/RTS.

## Solution: Stack-Page Buffer Approach

**Key insight:** Write directly to the stack PAGE ($0170-$01FF) as a buffer without using stack operations. SP is untouched → bank2's JSR/RTS works normally.

---

## Phase 1: GRP0 Stack-Page Buffer ($0170-$01FF)

### VBLANK Code (replaces 33-scanline wait)
```vbl
; Push 144 zeros into stack page (12 tile rows × 12 scanlines)
    ldx #$FF
    txs                     ; SP = $FF (for clean loop only)
    lda #0
    ldx #144
.PushLoop:
    pha                     ; pushes to $0170+..., SP decrements
    dex
    bne .PushLoop
    ; Now SP is at $0170+144 = $0200+... → wrap to $0100 area
    ; Actually: SP starts $FF, 144 pushes → SP = $FF - 144 = $67
    ; Stack page $0170-$01FF is now filled with zeros

; Overwrite 8 sprite entries at $0170+PlayerY
    ldx #PLAYER_HEIGHT - 1
    ldy PlayerY
.SpritePush:
    lda PlayerSpriteRight,X  ; or PlayerSpriteLeft,X based on direction
    sta $0170,Y              ; write directly to stack page
    iny
    dex
    bpl .SpritePush

; Restore SP for kernel/bank2
    ldx #$FF
    txs
```

### Kernel Change
```vbl
; OLD: 18-29 cycles (conditional branches)
  lda Scanline
  sec
  sbc PlayerY
  cmp #PLAYER_HEIGHT
  bcs .NoSprite
  tay
  lda PlayerSpriteRight,Y
  jmp .Put
.NoSprite:
  lda #0
.Put:
  sta GRP0

; NEW: 8 cycles (constant)
  ldy Scanline
  lda $0170,Y        ; read pre-computed GRP0
  sta GRP0
```

**Saves: 10-21 cycles per scanline**

### After Kernel
```vbl
    ldx #$FF
    txs             ; restore SP before bank2 JSR
    jsr ToBank2     ; fold pad → bank2 HUD
```

---

## Phase 2: PF ZP Lookup Tables

### Current Approach (~20 cycles)
```vbl
    txa / tay
    lda (MapPtrLo),Y / sta PF0     ; 5+3 = 8
    tya / clc / adc #12 / tay      ; 2+2+2+2 = 8
    lda (MapPtrLo),Y / sta PF1     ; 5+3 = 8
    tya / clc / adc #12 / tay      ; 2+2+2+2 = 8
    lda (MapPtrLo),Y / sta PF2     ; 5+3 = 8
    ; Total: ~48 cycles (plus X manipulation)
```

### New Approach (~18 cycles)
```vbl
; During VBLANK: copy 12 entries each from ROM to ZP
    ldx #11
.CopyPF:
    lda TilePF0,X     ; from ROM
    sta PF0Buf,X      ; ZP $B0-$BB
    lda TilePF1,X
    sta PF1Buf,X      ; ZP $BC-$C7
    lda TilePF2,X
    sta PF2Buf,X      ; ZP $C8-$D3
    dex
    bpl .CopyPF

; In kernel:
    lda PF0Buf,X / sta PF0      ; 3+3 = 6
    lda PF1Buf,X / sta PF1      ; 3+3 = 6
    lda PF2Buf,X / sta PF2      ; 3+3 = 6
    ; Total: 18 cycles (vs ~48)
```

**Saves: ~30 cycles per scanline on tile-row transitions**

---

## Phase 3: COLUPF Buffer

### Current Approach (5-13 cycles, 3 branches)
```vbl
    cpx #4 / beq .BandColor2
    cpx #8 / bne .ColorStripeDone
    lda LevelWallColor / bne .ColorStripeApply
.BandColor2:
    lda LevelWallColor2
.ColorStripeApply:
    sta COLUPF
```

### New Approach (6 cycles, constant)
```vbl
; During VBLANK: fill 12-byte buffer
    ldx #11
    lda LevelWallColor
.FillOuter:
    sta ColupfBuf,X     ; ZP $D4-$DF
    dex
    cpx #7
    bne .FillOuter
    ldx #7
    lda LevelWallColor2
.FillInner:
    sta ColupfBuf,X
    dex
    bpl .FillInner

; In kernel:
    lda ColupfBuf,X / sta COLUPF    ; 3+3 = 6
```

**Saves: 2-7 cycles per scanline + eliminates 3 branches**

---

## Phase 4: Move PF Setup Into Kernel Loop (WSYNC at Start)

### Critical Issue
The `.Row` PF setup (~49 cycles) runs on the SAME scanline as the first `.Line` iteration. Total: ~123 cycles on tile-row transitions — eats 2 entire scanlines.

### Fix
Move PF writes INTO the kernel loop. Write PF every scanline (same value for 12 scanlines in a tile row; TIA persists, but writing is harmless and keeps timing constant).

### New Kernel Structure
```vbl
.Line:
    sta WSYNC           ; 3  ← WSYNC at START (like HERO)
    ldy Scanline        ; 3
    lda $0170,Y         ; 5  ← GRP0 from buffer
    sta GRP0            ; 3
    ; ... GRP1 check (compact, ~12c) ...
    sta GRP1            ; 3
    ; ... ENAM0 check (compact, ~8c) ...
    sta ENAM0           ; 3
    lda PF0Buf,X        ; 3  ← PF from ZP tables
    sta PF0             ; 3
    lda PF1Buf,X        ; 3
    sta PF1             ; 3
    lda PF2Buf,X        ; 3
    sta PF2             ; 3
    lda ColupfBuf,X     ; 3  ← color from buffer
    sta COLUPF          ; 3
    inc Scanline        ; 5
    dec LineCount       ; 5
    bne .Line           ; 3
```

### Estimated Cycle Count
- WSYNC: 3
- GRP0: 8 (constant)
- GRP1: ~12 (variable, small range)
- ENAM0: ~8 (variable, small range)
- PF0/PF1/PF2: 18 (constant)
- COLUPF: 6 (constant)
- Loop control: 13
- **Total: ~58-63 cycles** (constant for PF/GRP0/colupf)

---

## Phase 5: VBLANK Timing Adjustment

### Current VBLANK
- ~37 scanlines (standard)
- Currently wastes time with 33-scanline wait loop

### New VBLANK Budget
- Push loop (144 zeros): ~19 scanlines
- Sprite overwrite (8 bytes): ~2 scanlines
- PF/COLUPF copy: ~6 scanlines
- Positioning (P0, P1, missiles, ball): ~6 scanlines
- **Total: ~33 scanlines**
- Add ~4 scanline wait to fill to 37

---

## Phase 6: SP Restoration Before Bank2

### Current Code
```vbl
    jsr ToBank2     ; fold pad → bank2
```

### Fixed Code
```vbl
    ldx #$FF
    txs             ; restore SP
    jsr ToBank2     ; fold pad → bank2
```

**Required because:** The push loop in Phase 1 changes SP. Must restore before any JSR/RTS in bank2.

---

## Implementation Order

| Step | Change | Risk | Verify |
|------|--------|------|--------|
| 1 | VBLANK push loop + overwrite into $0170-$01FF | Low | GRP0 from buffer in kernel |
| 2 | PF ZP buffers + kernel reads from $B0/$BC/$C8 | Low | Cave walls render |
| 3 | COLUPF buffer + kernel reads from buffer | Low | Band colors correct |
| 4 | Move PF setup into kernel loop (WSYNC at start) | **High** | Full game test |
| 5 | VBLANK timing adjustment | Medium | Image positioned correctly |
| 6 | SP restoration before bank2 | Medium | No crash on input |

**Each step committed separately so we can revert independently.**

---

## ZP Memory Map (Updated)

```
$80-$8F  Player physics and game state
$90-$9F  Font/sprite data (used by RenderText)
$A0-$AF  Game variables
$B0-$BB  PF0Buf (12 bytes) — NEW
$BC-$C7  PF1Buf (12 bytes) — NEW
$C8-$D3  PF2Buf (12 bytes) — NEW
$D4-$DF  ColupfBuf (12 bytes) — NEW
$E0-$EF  Game variables (existing)
$F0-$FF  Game variables (existing)
```

## Stack Page Map (Updated)

```
$0170-$01FF  GRP0 buffer (144 zeros + 8 sprite bytes) — NEW
$0100-$016F  Actual stack (grows down from $FF)
```

---

## Risk Assessment

- **Step 4 is highest risk** — moving WSYNC to start of kernel changes all timing. If wrong, entire screen garbles. Test immediately after.
- **Step 1 is the key fix** — eliminates the biggest source of variable cycles (GRP0 check: +7-10 cycles variance).
- **GRP1 and ENAM0 conditional checks remain** — they add ~3-5 cycles variance, but total stays under 76. Full elimination would require another 144-byte buffer (doesn't fit in ZP or stack page alongside GRP0).

---

## Results (2026-09-15)

### What worked
- **PF ZP buffers** (`PF0Buf`, `PF1Buf`, `PF2Buf`, `ColupfBuf` at $B0-$DF): copied from ROM once per frame during VBLANK. Kernel reads via `LDA PF0Buf,x` (4c) instead of `LDA (MapPtrLo),y` (5c) + `clc/adc` (4c). Eliminates indirect indexed addressing and page-crossing risk from the kernel.
- **COLUPF buffer**: eliminates 3-branch color stripe check (`cpx #4 / cpx #8 / bne`) from the kernel.
- **VBLANK timing**: PF copy (~5 scanlines) + 25 WSYNC waits ≈ 30 scanlines, matching the old33-scanline wait.

### What failed (DO NOT REPEAT)
- **Stack-page GRP0 buffer ($0170-$01FF)**: On the 2600, $0100-$01FF mirrors $80-$FF (the same128 bytes of ZP RAM). Writing `sta $0170,x` in a fill loop corrupts ALL ZP variables (PlayerY, RoomX, etc.). The 2600 has NO separate stack memory — the stack is the same RAM as ZP, just accessed via a different address range. **NEVER use the stack page as a buffer on the 2600.**
- **PF writes per-scanline in .Line**: Adding `LDA PF0Buf,x / STA PF0` etc. (28 cycles) to every .Line iteration pushed the total from ~56-64 cycles to ~84-92 cycles on EVERY scanline. Since WSYNC waits until the END of the current scanline, every scanline overflowed into the next, effectively doubling frame time → massive flicker. **PF registers persist in TIA — write them ONCE per tile row in .Row, not per-scanline.**

### Current kernel architecture
```
.Row:   PF0/PF1/PF2/ColupF from ZP buffers (once per tile row, ~28 cycles)
.Line:  GRP0 conditional (~15-29c) + GRP1 conditional (~12c) + ENAM0 conditional (~8c) + WSYNC + loop
        Best case: 56 cycles. Worst case: 75 cycles (player visible + object + laser).
        Flicker only when ALL three conditions are active simultaneously.
```

### Remaining flicker
The GRP0 conditional check adds 7-10 cycles when the player is visible (direction check + table lookup + JMP). Combined with GRP1 (12c) and ENAM0 (8c), worst case is ~75 cycles — just under budget. But the tile-row transition scanline (where .Row PF setup + first .Line run on the same scanline) can push to ~80+ cycles, causing 1-line flicker at tile boundaries. This is acceptable for now.

---

## Verification Checklist

After each phase, verify:
1. Assembles without errors (`./build_game_f6.sh`)
2. No Stella crash on startup
3. Player sprite renders correctly (all 4 directions)
4. Cave walls render correctly (no garbled PF)
5. HUD text renders (Level/Score/Lives/Time)
6. Laser fires and renders
7. No flicker on stationary screen
8. Left/right room transitions work
9. Enemies render (even if flickering)
10. Miner renders and collision works

---

## Last Updated
2026-09-15: Plan created after HERO kernel analysis and failed stack-based GRP0 attempt.
