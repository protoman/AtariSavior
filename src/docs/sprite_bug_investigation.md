# Player Sprite Bug Investigation

## Symptoms
- Player sprite has extra "bleeding" pixels to the RIGHT of the main body
- Extra pixels match the color of each sprite row (confirmed by debug coloring)
- Blocks appear every frame, no flicker
- Blocks change per room (room-specific data)
- When player touches ground in room 2, screen stretches at player position
- Bug appeared when the "eye notch" was added to the sprite

## Debug Test Results

### Test 1: Disable GRP1 (force $00)
- **Result:** Blocks still appear → NOT from GRP1

### Test 2: Zero out PF0/PF1/PF2 registers
- **Result:** Blocks still appear → NOT from playfield

### Test 3: Disable CTRLPF priority ($05 → $01)
- **Result:** Blocks still appear → NOT from playfield priority

### Test 4: Disable GRP0 entirely (force $00)
- **Result:** Blocks disappear → **CONFIRMED: blocks are from GRP0**

### Test 5: Debug colors (COLUP0 = Y*16 per row)
- **Result:** Each sprite row shows distinct color, extra pixels match each row's color
- Player body appears at expected width (4 TIA pixels)
- Extra pixels are to the RIGHT, same color as corresponding row

## Root Cause Found

### NUSIZ0 = $0A (should be $00)

At the GRP0 write (`breakLabel f0ca`):
- `print *$04` → **$0A** (%00001010 = 2 copies medium + 2-clock missile)
- Expected: $00 (single copy, no missile)

### Why NUSIZ0 is wrong

**Kernel setup writes $00 correctly:**
- ROM bytes at $F073: `a9 00 85 04` = `lda #0; sta NUSIZ0`
- This IS the correct code

**But something overwrites NUSIZ0 between setup and kernel loop:**
- Only ONE `sta NUSIZ0` ($85 $04) exists in kernel area ($F070-$F100)
- That write is at $F075 (the setup write)
- No other `sta $04` found in the kernel area

**HUD band (bank1) writes NUSIZ0 multiple times:**
- Last write: `lda #$10; sta NUSIZ0` at $F6C4-$F6C6
- $10 = %00010000 = single copy player + 2-clock missile
- NOT $0A

### Mystery
The kernel setup writes NUSIZ0=$00, but the debugger shows $0A during the kernel. No code between setup and kernel loop writes to $04. The source of $0A is unknown.

## Other Findings

### Debugger quirk
- `print *$83` shows CXM0P ($00) instead of RAM value
- Correct syntax for Stella 7.0: `print $83` shows the symbol, `print *$xx` reads memory
- `print *$b1` at GRP0 breakpoint showed $8E — this is FlickerFrame ($B1), NOT ActiveObjectOn ($B3)

### Fold-pad return address
- Fold-pad at $FC70: `lda #0; sta $1FF6; jmp $F0DA`
- $F0DA is INSIDE the kernel loop (GRP1 code: `lda ActiveObjectOn`)
- This is intentional — the fold-pad returns to the kernel loop after the HUD band

### Sprite data (verified correct)
```
PlayerSpriteRight:         PlayerSpriteLeft:
Row 0: ████.... ($F0)     Row 0: ████.... ($F0)
Row 1: ████.... ($F0)     Row 1: ████.... ($F0)
Row 2: ██...... ($C0)     Row 2: ..██.... ($30)  ← eye notch
Row 3: ████.... ($F0)     Row 3: ████.... ($F0)
Row 4: ████.... ($F0)     Row 4: ████.... ($F0)
Row 5: ████.... ($F0)     Row 5: ████.... ($F0)
Row 6: ████.... ($F0)     Row 6: ████.... ($F0)
Row 7: ████.... ($F0)     Row 7: ████.... ($F0)
```

### PlayerGrp0 buffer (verified correct)
- `print *$f8` → $F0 (row 0) ✓
- `print *$fa` → $C0 (row 2, eye notch) ✓

## Next Steps
1. Set watchpoint on $04 (NUSIZ0) to catch the exact moment it changes to $0A
2. Check if the kernel setup code is actually executing (maybe fold-pad jumps over it?)
3. Verify the fold-pad return path doesn't bypass the kernel setup
4. Check if bank1's NUSIZ0 writes persist across bank switches

## TIA Color Notes (from research)
- Color byte format: `(hue << 4) | (luma << 1)`
- $F0 = hue 15, luma 0 (white/grey)
- $C0 = hue 12, luma 0 (red)
- $1E = hue 1, luma 7 (bright yellow — player color)
- $00 = black
- Debug colors ($10, $20, $30...) are at luma 0 = very dark
- Stella uses hue-major palette table
