# 13+2 HUD Implementation Plan

## Overview
Implement HERO-style 13+2 sprite technique for the HUD to render:
- Timer bar (yellow, depleting)
- Lives (up to 9 green squares)
- Bombs (5 red squares)
- Score ("0000" text)

## Architecture
The 13+2 technique uses:
- P0 with NUSIZ0=$03 (3 copies) + P1 with NUSIZ1=$03 (3 copies) + ball = 13 character columns
- VDELP0/VDELP1 for vertical delay pipeline
- 6 font pointers in ZP ($80-$AA) loaded during VBLANK
- TEXTDISP macro: 76-cycle render loop per scanline (exactly 1 scanline)
- HudCopy: unrolled 40-byte copy from ROM slot tables to ZP

## ZP Layout (13+2 slots overlap with cave kernel vars — safe because they run at different times)

| Address | Cave Kernel Use      | 13+2 Use       |
|---------|---------------------|----------------|
| $80-$84 | RoomX, RoomY, Scan, LineCt, TileRow | charp (5 bytes) |
| $85-$87 | Grp0Ptr, Grp0Hi, Temp | chara (first 3 bytes) |
| $88-$A7 | (unused by cave)    | chara-charg (rest) |
| $A9-$AD | (unused by cave)    | temp, line, count, textptr, savesp |

## Implementation Steps

### Step 0: Architecture Evaluation (optional — do only if needed)
- [ ] Check current bank0 ROM size vs 4K limit
- [ ] Estimate total code size after 13+2 implementation
- [ ] If >3.5K, plan bank restructuring:
  - Bank0: kernel + game logic + room data
  - Bank1: HUD rendering (13+2 kernel + font data + slot tables)
  - Bank2-3: reserved for future expansion
- [ ] Decide: implement now or defer to when space runs out

### Step 1: ZP Layout & Font System
- [ ] Add 13+2 ZP constants to kernel.asm ($80-$AD)
- [ ] Add score digit font data (0-9, 5 bytes each) to ROM — reuse from `generated/hud_font.asm`
- [ ] Verify `generated/hud_slots.asm` format matches our kernel needs
- [ ] **Test:** Assemble, verify ZP addresses don't conflict, check ROM size

### Step 2: HudCopy Routine
- [ ] Implement unrolled 40-byte copy: `lda (ptr),Y` → `sta charp,Y` × 40
- [ ] Source: ROM slot table (160 bytes per text line)
- [ ] Dest: ZP $80-$A7 (charp..charg)
- [ ] Must complete in ~448 cycles (within one VBLANK section)
- [ ] **Test:** Load "LEVEL" text into ZP, verify bytes with Stella debugger

### Step 3: TEXTDISP Macro (76-cycle render loop)
- [ ] Define TEXTDISP macro matching Paul Slocum's tutorial pattern
- [ ] Reads 6 font bytes from chara-charg
- [ ] Writes GRP0/GRP1 at specific cycle positions
- [ ] Sets NUSIZ1=$03, VDELP1=1, RESP0/RESP1, HMOVE mid-scanline
- [ ] Exactly 76 cycles = 1 scanline
- [ ] **Test:** Render single "TEST" string in Stella, verify characters appear

### Step 4: RenderText Routine
- [ ] Leading WSYNC + 5 TEXTDISP rows = one text line in 12 scanlines
- [ ] Manages charp..charg Y-offset for multi-row font
- [ ] Clears GRP0/GRP1, ENAM0/ENAM1, ENABL after rendering
- [ ] **Test:** Render full text line, verify 12-scanline timing

### Step 5a: Timer Bar (keep PF approach)
- [ ] Keep current PF-based timer bar (simple, no text needed)
- [ ] Yellow bar, 70% width, 8 scanlines
- [ ] **Test:** Verify timer bar still renders correctly

### Step 5b: Lives Display (13+2 text)
- [ ] Generate slot table for "LIVES: 9" (or dynamic count)
- [ ] HudCopy → ZP during VBLANK
- [ ] RenderText in HUD band (12 scanlines)
- [ ] Green color via COLUP0/COLUP1
- [ ] **Test:** Lives count updates (3→9), text renders correctly

### Step 5c: Bombs Display (13+2 text)
- [ ] Generate slot table for "BOMBS: 5" (or dynamic count)
- [ ] HudCopy → ZP during VBLANK
- [ ] RenderText in HUD band (12 scanlines)
- [ ] Red color via COLUP0/COLUP1
- [ ] **Test:** Bomb count updates, text renders correctly

### Step 5d: Score Display (13+2 text)
- [ ] Generate slot table for "SCORE: 0000"
- [ ] HudCopy → ZP during VBLANK
- [ ] RenderText in HUD band (12 scanlines)
- [ ] White color via COLUP0/COLUP1
- [ ] **Test:** Score updates, text renders correctly

### Step 6: Testing & Polish
- [ ] Verify 262-scanline budget — no frame drops
- [ ] Stella debugger: check scanline counts per HUD element
- [ ] Test edge cases: 0 lives, 9 lives, 0 bombs, max score
- [ ] Verify HUD fits in 48 scanlines total
- [ ] Adjust colors (green lives, red bombs, yellow timer, white score)
- [ ] Commit and merge to main

## Cycle Budget (48 scanlines)
- Timer bar (PF): 8 scanlines
- Spacer: 2 scanlines
- Lives text (13+2): 12 scanlines
- Spacer: 2 scanlines
- Bombs text (13+2): 12 scanlines
- Spacer: 2 scanlines
- Score text (13+2): 12 scanlines
- Remaining: 2 scanlines
- **Total: 48 scanlines**

## Key References
- `docs/tutorial/13_plus2.asm` — Paul Slocum's original tutorial
- `generated/menu_13plus2.asm` — ported version for menu (bank1)
- `generated/hud_slots.asm` — precomputed slot tables
- `generated/hud_font.asm` — compact sprite font (21 glyphs)
- `comparison/lo-a-rad-dragon/bank0.asm` — HudBand, RenderText, HudCopy
- `comparison/lo-a-rad-dragon/bank2.asm` — FontP0/FontP1, ScoreKernel

## Status
- [ ] Step 0: Architecture Evaluation
- [ ] Step 1: ZP Layout & Font System
- [ ] Step 2: HudCopy Routine
- [ ] Step 3: TEXTDISP Macro
- [ ] Step 4: RenderText Routine
- [ ] Step 5a: Timer Bar
- [ ] Step 5b: Lives Display
- [ ] Step 5c: Bombs Display
- [ ] Step 5d: Score Display
- [ ] Step 6: Testing & Polish
