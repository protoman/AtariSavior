# Atari 2600 Development Notes

## Hardware Architecture

### CPU
- MOS 6502 @ 1.19 MHz
- 128 bytes RAM ($80-$FF)
- 4K address space for cartridge ROM ($F000-$FFFF), expanded via bankswitching

### TIA (Television Interface Adapter) - $00-$3F
Graphics and sound chip. Write addresses:
- $00 VSYNC - Vertical sync (bit 1 = 1 during VSYNC)
- $01 VBLANK - Vertical blank (bit 6 = 1 during VBLANK; bit 1 enables latches for D1 of CX's)
- $02 WSYNC - Wait for sync (stalls CPU until end of scanline)
- $03 RSYNC - Reset sync
- $04 NUSIZ0 - Player 0 size ($xx: xx=0 single, 1=2 copies close, 2=2 med, 3=3 close, 4=2 far, 5=3 med, 6=double size, 7=3 far)
- $05 NUSIZ1 - Player 1 size
- $06 COLUP0 - Player 0 color
- $07 COLUP1 - Player 1 color
- $08 COLUPF - Playfield color
- $09 COLUBK - Background color
- $0A CTRLPF - Control playfield (D0=playfield size: 0=normal 1=wide; D1=0 mirror 1=repeat; D4=ball size: 0=1clk 1=2clk; D5=ball enabled)
- $0B REFP0 - Reflect player 0 (D3)
- $0C REFP1 - Reflect player 1 (D3)
- $0D PF0 - Playfield 0 (bits 4-7, leftmost 4 pixels)
- $0E PF1 - Playfield 1 (bits 7-0, next 8 pixels)
- $0F PF2 - Playfield 2 (bits 0-7, next 8 pixels, reversed)
- $10 RESP0 - Reset player 0 position
- $11 RESP1 - Reset player 1 position
- $12-$14 RESM0, RESM1, RESBL - Reset missiles and ball
- $15-$18 AUDC0/AUDC1/AUDF0/AUDF1 - Audio control/frequency
- $19-$1A AUDV0/AUDV1 - Audio volume
- $1B GRP0 - Graphics player 0
- $1C GRP1 - Graphics player 1
- $1D ENAM0 - Enable missile 0
- $1E ENAM1 - Enable missile 1
- $1F ENABL - Enable ball
- $20 HMP0 - Horizontal motion player 0 (bits 4-7 signed: %1000=-8 to %0111=+7)
- $21-$24 HMP1, HMM0, HMM1, HMBL - Horizontal motion for other objects
- $25 VDELP0 - Vertical delay player 0
- $26 VDELP1 - Vertical delay player 1
- $27-$28 VDELM0, VDELM1 - Vertical delay missiles
- $29 RESMP0 - Reset missile 0 to player 0
- $2A RESMP1 - Reset missile 1 to player 1
- $2B HMOVE - Apply horizontal motion (must write any value after HMPx are set)
- $2C HMCLR - Clear horizontal motion
- $2D CXCLR - Clear collision latches

TIA Read registers ($00-$0D when reading - mirrored at $00-$3F):
- $00 CXM0P - Collision: missile0-player0 (bit6), missile0-player1(bit7)
- $01 CXM1P - Collision: missile1-player0(bit6), missile1-player1(bit7)
- $02 CXP0FB - Collision: player0-playfield(bit7), player0-ball(bit6)
- $03 CXP1FB - Collision: player1-playfield(bit7), player1-ball(bit6)
- $04 CXM0FB - Collision: missile0-playfield(bit7), missile0-ball(bit6)
- $05 CXM1FB - Collision: missile1-playfield(bit7), missile1-ball(bit6)
- $06 CXBLPF - Collision: ball-playfield(bit7), ball-player1(bit6)
- $07 CXPPMM - Collision: player0-player1(bit6), missile0-missile1(bit6)
- $08 INPT0-INPT3 - Dump inputs (paddle)
- $0C INPT4 - Joystick 0 fire button (D7: 0=pressed)
- $0D INPT5 - Joystick 1 fire button (D7: 0=pressed)

### RIOT (RAM-I/O-Timer) - $280-$2FF
- $280 SWCHA - Port A data (joysticks): bits 4-7 = joystick 0, bits 0-3 = joystick 1. Bit 4=up, 5=down, 6=left, 7=right (0=pressed)
- $281 SWACNT - Port A data direction
- $282 SWCHB - Console switches (bit3=B/W, bit7=reset, bit6=select)
- $283 SWBCNT - Port B data direction  
- $284 INTIM - Timer read (counts down)
- $285 TIMINT - Timer interrupt flag
- $294 TIM1T - Set 1 clock timer
- $295 TIM8T - Set 8 clock timer
- $296 TIM64T - Set 64 clock timer (most used for VBLANK/overscan timing)
- $297 T1024T - Set 1024 clock timer

### RAM Map ($80-$FF)
- $80-$8F - Player physics and game state
  - $80 playerX - X position (0-159)
  - $81 playerY - Y position (0-191)
  - $82 playerY_sub - Sub-pixel Y
  - $83 vy_lo - Velocity Y low byte
  - $84 vy_hi - Velocity Y high byte (signed)
  - $85 jetPower - Jet thrust accumulator
  - $86-$8F - Temp and other variables
- $90-$FF - Game specific variables

## TV Frame Structure
Each frame:
1. VSYNC: 3 scanlines (VSYNC on for 3 lines, then off)
2. VBLANK: 37 scanlines (game logic happens here)  
3. KERNEL: 192 visible scanlines
4. OVERSCAN: 30 scanlines (more game logic, prepare for next frame)
Total: 262 scanlines at 60Hz

Use TIM64T for timing: STA TIM64T with value = desired number of lines.
-Timer counts 64 cycles per unit at 1.19MHz = ~76 lines per unit.

### Standard Timing Values
- VBLANK: Wait for 43 (43*64=2752 cycles ≈ 37 scanlines)
- Overscan: Wait for 35 (35*64=2240 cycles ≈ 30 scanlines)

(Note: At 1.19MHz, one scanline = 76 cycles. TIM64T counts at 64 cycles/unit.)

## Playfield Layout
With CTRLPF D1=0 (mirror):
- Pixel 0-3:   PF0 bits 4-7 (leftmost)
- Pixel 4-11:  PF1 bits 7-0
- Pixel 12-19: PF2 bits 0-7
- Pixel 20-27: PF2 bits 7-0 (mirror)
- Pixel 28-35: PF1 bits 0-7 (mirror)
- Pixel 36-39: PF0 bits 7-4 (mirror)

For a simple border:
- Top/bottom rows: PF0=$F0, PF1=$FF, PF2=$FF (all solid)
- Middle rows: PF0=$F0, PF1=$00, PF2=$00 (side borders only)

## Bankswitching - F6 (16K)
- 4 banks of 4K each
- All banks appear at $F000-$FFFF when selected
- Bank select: STA $1FF6 (bank0), $1FF7 (bank1), $1FF8 (bank2), $1FF9 (bank3)
- Physical ROM layout: bank0 at offset $0000, bank1 at $1000, bank2 at $2000, bank3 at $3000

## Player Positioning
The 2600 positions sprites using RESPx (coarse) + HMx (fine).
- RESPx resets the sprite counter to the next color clock
- HMx adds fine offset (-8 to +7 color clocks)
- HMOVE applies all fine motion simultaneously

Standard positioning formula:
- Fine offset = ((X + 4) % 15) - 8

## Stella Emulator Tips
- Stelladaptor / 2600-daptor for real controller input
- Use `stella rom.bin` to run
- Debugger: `stella -debug rom.bin`
- Cheat codes, state saves, and frame advance available in debugger
- In-game: Alt+Enter for fullscreen, ` (backtick) for debugger

## Build Process
```bash
dasm bank0.asm -f3 -obank0.bin
dasm bank1.asm -f3 -obank1.bin
dasm bank2.asm -f3 -obank2.bin
dasm bank3.asm -f3 -obank3.bin
cat bank0.bin bank1.bin bank2.bin bank3.bin > rom.bin
```

## Important Conventions
- All code follows 6502 little-endian conventions
- DASM syntax: `label: instruction operands ; comment`
- Directives: .byte, .word, .ds (define storage), ORG, INCLUDE, EQU (=)
- Zero-page addressing is faster and uses fewer bytes - use for frequently accessed variables
- Branches are relative and limited to ±127 bytes
- JMP/JSR use absolute addresses - careful with bankswitching (use far calls)
- When switching banks, the calling bank's code becomes inaccessible; use trampolines for inter-bank calls
- WSYNC at start of each scanline loop iteration to keep stable timing

## Game Loop Structure
```
Start:
    ; Initialize hardware
    ; Clear RAM
    ; Set up initial state

MainLoop:
    ; VBLANK section (~37 scanlines)
    ; - Read joystick
    ; - Update game logic (physics, AI, etc.)
    ; - Position sprites
    ; - Set timer for VBLANK end
    
    ; KERNEL section (192 scanlines)
    ; - Draw playfield line by line
    ; - Output sprite graphics at correct Y positions
    
    ; OVERSCAN section (~30 scanlines)
    ; - Wrapping logic
    ; - Prepare next frame
    
    jmp MainLoop
```

## Notes on HERO (Activision) reference
- Player has a backpack/jet that allows vertical movement
- Gravity pulls the player down; jet overcomes gravity
- Side-to-side movement in tunnels
- Rescue hostages from collapsing mine
- Timer-based gameplay
- The jet has an initial resistance before it reaches full thrust (inertia)

## Standard Coding Patterns

### Wait for Timer
```
WaitTimer:
    lda INTIM
    bne WaitTimer
```

### Read Joystick
```
    lda SWCHA       ; Read joystick
    ; Bit 4 = up, bit 5 = down, bit 6 = left, bit 7 = right (0=pressed)
    lsr             ; Shift right, now in bits 3-0 for joystick 0
    lsr
    lsr
    lsr
    ; Now bits 3-0 = up, down, left, right (active low)
```

## Knowledge Management
When discovering new information about the Atari 2600 hardware, register behavior,
timing details, or effective coding patterns, add them to this file for future reference.
