# 48-Pixel Sprite Score Rendering — Skill Reference

## The Technique (6-Digit Score Hack)

The Atari 2600 natively provides two 8-pixel-wide player sprites. By triplicating each (NUSIZ=3) and interleaving them, we get 6 digit slots across the screen. The "hack" is changing GRP0/GRP1 mid-scanline to show different digits in each copy.

### How It Works

**Hardware Triplication:**
- NUSIZ0=3 → 3 copies of Player 0, close spacing
- NUSIZ1=3 → 3 copies of Player 1, close spacing
- Interleaved: P0-P1-P0-P1-P0-P1 = 6 digit positions

**VDELP0/VDELP1 Cross-Buffer Mechanism:**
- When VDELP0=1, writing to GRP0 changes GRP0A (buffer), not the live display
- When VDELP1=1, writing to GRP1 changes GRP1A (buffer), not the live display
- CRITICAL: Writing to GRP0 copies GRP1→GRP1A. Writing to GRP1 copies GRP0→GRP0A.
- This creates 4 "virtual" registers (GRP0, GRP0A, GRP1, GRP1A) from 2 physical ones

**Mid-Line Register Swapping:**
- While the electron beam draws the current sprite copy, the CPU loads the next digit's data
- The VDELP buffering ensures the correct data appears in the correct slot
- Every cycle matters — 1 extra cycle (page crossing) shifts the display by 3 pixels

### Font Data Format

- 8 pixels wide × 8 rows tall per digit
- 1 byte per row, MSB-first (bit7 = leftmost pixel)
- 10 digits × 8 bytes = 80 bytes total
- MUST be page-aligned (256-byte boundary) for fast `(zp),Y` addressing
- First byte of each digit is $00 (blank row for spacing)

Example digit "0":
```
.byte %0              ; blank row (spacing)
.byte %01111100       ; .XXXXX.
.byte %11000110       ; XX...XX
.byte %11000110       ; XX...XX
.byte %11000110       ; XX...XX
.byte %11000110       ; XX...XX
.byte %11000110       ; XX...XX
.byte %01111100       ; .XXXXX.
```

### Render Loop (6 digits, 71 cycles + WSYNC = 74)

From `score48pix.asm`:
```asm
    ; Setup (before scanline)
    LDA #$03
    STA NUSIZ0          ; 3 copies close
    STA NUSIZ1          ; 3 copies close
    STA VDELP0          ; vertical delay ON
    STA VDELP1          ; vertical delay ON
    ; Position RESP0 and RESP1 to interleave 6 slots
    ; Set HMP0/HMP1 for fine positioning

    ; Per-scanline render loop
    LDY #7              ; 8 rows (0-7)
    STY scbrdCnt
.scoreLoop:
    LDY <scbrdCnt           ; 3c
    LDA (scorePtr6),Y       ; 5c  Load digit 6 data
    TAX                     ; 2c  Cache in X
    STA WSYNC               ; 3c  Wait for scanline start
    LDA (scorePtr1),Y       ; 5c  Load digit 1
    STA.w GRP0              ; 4c  Store digit 1 (VDELP0 buffers it)
    LDA (scorePtr2),Y       ; 5c  Load digit 2
    STA GRP1                ; 3c  Push digit 1, buffer digit 2
    LDA (scorePtr3),Y       ; 5c  Load digit 3
    STA GRP0                ; 3c  Push digit 2, buffer digit 3
    LDA (scorePtr4),Y       ; 5c  Load digit 4
    STA <scbrdTmp           ; 3c  Cache in temp
    LDA (scorePtr5),Y       ; 5c  Load digit 5
    LDY <scbrdTmp           ; 3c  Y = digit 4
    STY GRP1                ; 3c  Push digit 3, buffer digit 4
    STA GRP0                ; 3c  Push digit 4, buffer digit 5
    STX GRP1                ; 3c  Push digit 5, buffer digit 6
    STX GRP0                ; 3c  Push digit 6 (final)
    DEC <scbrdCnt           ; 5c
    BNE .scoreLoop          ; 3c
```

### Cycle Timing (Critical!)

- 1 CPU cycle = 3 color clocks (pixels)
- 1 scanline = 76 CPU cycles = 228 color clocks
- The render loop takes 71 cycles + 3 (WSYNC) = 74 cycles per scanline
- 2 cycles of margin — page crossing adds 1 cycle, breaking timing
- Font data MUST be page-aligned to avoid page crossing penalties

### Positioning

- RESP0 and RESP1 must be positioned to interleave 6 digit slots
- Each digit is 8 pixels wide, slots are 16 pixels apart (close spacing)
- HMP0/HMP1 for fine positioning (within 15-pixel blocks)
- Standard centered position: RESP0 at pixel ~56, RESP1 at pixel ~72

### Digit Pointer Setup

Before the render loop, set up 6 pointers to the digit data:
```asm
; For score value stored as BCD:
; ScoreTh=thousands, ScoreHu=hundreds, ScoreTe=tens, ScoreOn=ones
; Each pointer = base address of digit × 8

    LDA #>DigitGfx
    STA scorePtr1+1    ; high byte for all pointers
    STA scorePtr2+1
    STA scorePtr3+1
    STA scorePtr4+1
    STA scorePtr5+1
    STA scorePtr6+1

    ; Low bytes = #<DigitGfx + (digit × 8)
    ; e.g., for digit "3": offset = 3 × 8 = 24
```

### Adaptation for 4 Digits

For our game (4 digits "1234"), use fewer copies:
- Option A: NUSIZ0=3 (3 copies) + NUSIZ1=0 (1 copy) = 4 slots
- Option B: NUSIZ0=1 (2 copies) + NUSIZ1=1 (2 copies) = 4 slots

The render loop simplifies to 4 GRP writes instead of 6.

### Common Pitfalls

1. **Font not page-aligned** → page crossing adds 1 cycle → display shifts 3 pixels
2. **VDELP not enabled** → GRP writes go directly to live display → timing breaks
3. **Wrong NUSIZ values** → wrong number of copies → wrong digit count
4. **RESP0/RESP1 misaligned** → digits overlap or have gaps
5. **Not clearing GRP0/GRP1 before loop** → stale data appears

### Reference Files

- `src/docs/font/examples/score48pix.asm` — Clean 6-digit kernel
- `src/docs/font/examples/burger8e.asm` — Complete game with 5-digit score
- `src/docs/font/examples/burger8b.asm` — Variant with 6-digit score
- `docs/hero/hero_bank0.asm` — HERO's score kernel at $D327-$D372

### Key Insight from HERO

HERO uses PF registers for score, not sprites. But the PRINCIPLE is the same:
- Per-scanline updates (not per-tile like the cave kernel)
- Pre-computed data per scanline
- The font shapes are encoded in the data, not as a separate font array

The 48-pixel sprite technique is SHARPER than PF-based rendering because:
- PF pixels are 4 color clocks wide (blocky)
- Sprite pixels are 1 color clock wide (sharp)
- Sprites can be positioned at any X coordinate
- Sprites have per-pixel color control

### Implementation Order

1. Create 8×8 font data (10 digits, page-aligned)
2. Set up NUSIZ0/NUSIZ1, VDELP0/VDELP1
3. Position RESP0/RESP1 for 4-digit layout
4. Implement 4-digit render loop
5. Set up digit pointer calculation from score variables
6. Test with hardcoded "1234"
7. Add dynamic score update
