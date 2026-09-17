# Fix Kernel Flicker: Phased Rendering Approach

## Problem
The kernel `.Line` loop at $f139 has three conditional sections (GRP1, GRP0, ENAM0) that add variable cycles per scanline. Worst case = 80 cycles (4 over 76), causing flicker on scanlines where player + enemy overlap.

## Current Cycle Breakdown (`.Line` body)

| Section | Best case | Worst case | Variation |
|---------|-----------|------------|-----------|
| GRP1 (object check) | 13c | 24c | +11 |
| GRP0 (player check) | 19c | 25c | +6 |
| ENAM0 (laser check) | 13c | 19c | +6 |
| Loop control | 15c | 16c | +1 |
| **Total** | **60c** | **84c** | **+24** |

Worst case exceeds 76c → WSYNC overflows → flicker.

## Solution: Three-Phase Kernel

Split the `.Line` loop into three phases based on PlayerY. Each phase eliminates the GRP0 conditional check, fixing the flicker.

### Phase 1: Scanlines 0 to PlayerY-1 (player NOT visible)
- **GRP0 = 0** (no range check, just `lda #0 / sta GRP0` = 5c)
- GRP1 = conditional (enemy check)
- ENAM0 = conditional (laser check)

### Phase 2: Scanlines PlayerY to PlayerY+7 (player VISIBLE)
- **GRP0 = player data** (load from pre-computed ZP buffer, 17c)
- GRP1 = conditional (enemy check)
- ENAM0 = conditional (laser check)

### Phase 3: Scanlines PlayerY+8 to 191 (player NOT visible)
- **GRP0 = 0** (no range check, 5c)
- GRP1 = conditional (enemy check)
- ENAM0 = conditional (laser check)

## New Cycle Count (with GRP1/ENAM0 jmp optimizations)

| Section | Best case | Worst case | Notes |
|---------|-----------|------------|-------|
| GRP1 (optimized) | 13c | 22c | jmp instead of BIT skip |
| GRP0 (Phase 1/3) | 5c | 5c | Fixed: just `lda #0` |
| GRP0 (Phase 2) | 17c | 17c | Fixed: ZP buffer load |
| ENAM0 (optimized) | 13c | 16c | jmp instead of BIT skip |
| Loop control | 15c | 16c | Same |

**Phase 1/3 worst case:** 22 + 5 + 16 + 16 = **59 cycles** ✓
**Phase 2 worst case:** 22 + 17 + 16 + 16 = **71 cycles** ✓

Both under 76 → **flicker eliminated**.

## Implementation Steps

### Step 1: Pre-compute player graphics in ZP during VBLANK
- During VBLANK, copy 8 bytes of player graphic data from ROM to ZP ($90-$97)
- Uses existing `Grp0Ptr` pointing to the ROM data
- Cost: ~50 cycles (~0.7 scanlines)

### Step 2: Restructure kernel into three phases
Replace the single `.Line` loop with three loops:

```asm
; Phase 1: scanlines 0 to PlayerY-1 (player not visible)
    lda PlayerY        ; 3
    sta PhaseEnd       ; 3
    ldy #0             ; 2  (scanline counter)
.Phase1:
    ; GRP0 = 0 (5c fixed)
    ; GRP1 = conditional (22c worst)
    ; ENAM0 = conditional (16c worst)
    ; loop control
    iny                ; 2
    cpy PhaseEnd       ; 3
    bne .Phase1        ; 3

; Phase 2: scanlines PlayerY to PlayerY+7 (player visible)
    ldx #0             ; 2  (offset into player graphic)
.Phase2:
    ; GRP0 = PlayerGrp0,X (17c fixed)
    ; GRP1 = conditional (22c worst)
    ; ENAM0 = conditional (16c worst)
    ; loop control
    inx                ; 2
    cpx #8             ; 2
    bne .Phase2        ; 3

; Phase 3: scanlines PlayerY+8 to 191 (player not visible)
    ; GRP0 = 0 (5c fixed)
    ; GRP1 = conditional (22c worst)
    ; ENAM0 = conditional (16c worst)
    ; loop control until scanline 191
```

### Step 3: Optimize GRP1 and ENAM0 with jmp
Replace BIT skip with jmp for both:

```asm
; GRP1 (optimized)
    lda Scanline       ; 3
    cmp ObjTop         ; 3
    bcc .NoObject      ; 2
    cmp ObjBot         ; 3
    bcs .NoObject      ; 2
    lda ObjGrp1        ; 3  (pre-computed graphic data)
    jmp .PutGrp1       ; 3
.NoObject:
    lda #0             ; 2
.PutGrp1:
    sta GRP1           ; 3

; ENAM0 (optimized)
    lda Scanline       ; 3
    cmp LaserScanline  ; 3
    bne .LaserOff      ; 2
    lda #$02           ; 2
    jmp .PutLaser      ; 3
.LaserOff:
    lda #0             ; 2
.PutLaser:
    sta ENAM0          ; 3
```

### Step 4: Handle edge cases
- PlayerY = 0: Skip Phase 1, run Phase 2 (scanlines 0-7), then Phase 3
- PlayerY = 184: Run Phase 1 (scanlines 0-183), skip Phase 2, skip Phase 3
- PlayerY > 184: Clamp to 184

### Step 5: Verify and test
- Build: `./build_game_f6.sh`
- Measure: `breakLabel f177` → Scn value, `breakLabel fc80` → Scn value
- Visual: Check for flicker reduction in Stella

## Memory Usage
- Player graphic data: 8 bytes in ZP ($90-$97)
- PhaseEnd variable: 1 byte in ZP (can reuse existing Temp at $AD)
- No additional buffers needed

## VBLANK Time Budget
- Pre-computing player graphics: ~50 cycles (~0.7 scanlines)
- Existing VBLANK code: ~30 scanlines
- Total: ~31 scanlines (within 35-scanline VBLANK)

## Risks
1. **Three-phase kernel adds complexity** — more code, more bug surface
2. **GRP1/ENAM0 still conditional** — variable cycles remain (but worst case is now 59c/71c, under 76c)
3. **Edge cases** — PlayerY = 0 or 184 need careful handling
4. **PF timing** — PF setup WSYNC must still fire at the correct point in each phase

## Verification Steps
1. Build: `./build_game_f6.sh`
2. Measure frame: `stella savior.bin` → `clearbreaks` → `breakLabel f177` → `run` → note Scn
3. Measure bank2: `breakLabel fc80` → `run` → note Scn
4. Check flicker: visual inspection in Stella (player + enemy overlap scanlines)
