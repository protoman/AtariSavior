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

## Implementation Steps

### Phase 1: ZP Layout & Font System
- [ ] Define ZP layout: charp($80), chara($85), charb($8a), charc($8f), chard($94), chare($99), charf($9e), charg($a3)
- [ ] Define text slot variables: temp($a9), line($aa), count($ab), textptr($ac), savesp($ad)
- [ ] Define FontP0($b3) and FontP1($b8) for score digit data
- [ ] Create score font data (0-9, 5 bytes each) in ROM
- [ ] Create HUD slot tables (generated/hud_slots.asm already exists — verify format)

### Phase 2: HudCopy Routine
- [ ] Implement HudCopy: unrolled 40-byte copy from ROM slot table to ZP (charp..charg)
- [ ] Each copy reads (HudPtrLo),Y and writes to charp,Y
- [ ] Must complete in ~448 cycles (within one VBLANK section)
- [ ] Test with a single text line

### Phase 3: TEXTDISP Macro
- [ ] Implement TEXTDISP macro (76-cycle render loop)
- [ ] Each TEXTDISP renders one row of characters
- [ ] Sequence: 5 TEXTDISP rows per text line (5px tall font)
- [ ] Include NUSIZ1/VDELP1 setup, GRP0/GRP1 writes, HMOVE mid-scanline
- [ ] Test with a single "TEST" string

### Phase 4: RenderText Routine
- [ ] Implement RenderText: leading WSYNC + 5 TEXTDISP rows
- [ ] Must complete in exactly 12 scanlines per text line
- [ ] Test rendering one line of text

### Phase 5: HUD Integration
- [ ] Replace current PF-based HUD with 13+2 rendering
- [ ] Timer bar: yellow bar (may keep PF approach for simplicity)
- [ ] Lives: "LIVES: 9" text via 13+2
- [ ] Bombs: "BOMBS: 5" text via 13+2
- [ ] Score: "SCORE: 0000" text via 13+2
- [ ] Ensure total HUD fits in 48 scanlines

### Phase 6: Testing & Polish
- [ ] Verify no frame drops (262 scanline budget)
- [ ] Test with Stella debugger — check scanline counts
- [ ] Test lives increase (3→9) and bomb count changes
- [ ] Verify score updates correctly
- [ ] Adjust colors (green lives, red bombs, yellow timer, white score)
- [ ] Commit and merge to main

## Key References
- `docs/tutorial/13_plus2.asm` — Paul Slocum's original tutorial
- `generated/menu_13plus2.asm` — ported version for menu (bank1)
- `generated/hud_slots.asm` — precomputed slot tables
- `comparison/lo-a-rad-dragon/bank0.asm` — HudBand, RenderText, HudCopy
- `comparison/lo-a-rad-dragon/bank2.asm` — FontP0/FontP1, ScoreKernel

## Cycle Budget
- 48 scanlines total for HUD band
- Timer bar: ~8 scanlines (PF approach)
- Lives text: ~12 scanlines (5 TEXTDISP + setup)
- Bombs text: ~12 scanlines (5 TEXTDISP + setup)
- Score text: ~12 scanlines (5 TEXTDISP + setup)
- Spacers: ~4 scanlines
- Total: ~36 scanlines (leaves margin)

## Status
- [ ] Phase 1: ZP Layout & Font System
- [ ] Phase 2: HudCopy Routine
- [ ] Phase 3: TEXTDISP Macro
- [ ] Phase 4: RenderText Routine
- [ ] Phase 5: HUD Integration
- [ ] Phase 6: Testing & Polish
