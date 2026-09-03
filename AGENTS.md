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
- $0A CTRLPF - Control playfield (D0=reflect: 0=repeat 1=reflect; D1=score mode: 0=normal 1=score; D4=ball size: 0=1clk 1=2clk; D5=ball enabled). Use $01 for a normal reflected playfield; add $02 only for score mode.
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
With CTRLPF D0=1 (reflect):
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
- RESPx resets the sprite counter to the current color clock; each loop
  iteration in the positioning routine must be exactly 5 CPU cycles = 15
  color clocks so the coarse grid matches the fine range.
- HMx adds a fine offset of -8 to +7 color clocks.
- HMOVE (written during HBLANK) applies all fine motion.

CRITICAL HMPx encoding (bits 4-7): positive (0..+7) moves LEFT, negative
(-1..-8) moves RIGHT. The classic `sbc #15; bcs` loop is only 4 cycles
(12 clocks/block) and does NOT give pixel-precise positioning — the coarse
step (12) must equal the fine span (15). Use the River Raid algorithm:
compute fine = `((X+1)&15)` then `eor #7` / `asl x4` into HMP0, and a coarse
delay count via `(X+1)/16` with /15 correction; then a `dey;bpl` delay loop
that is PAGE-ALIGNED so the taken `bpl` crosses a page (3 cycles), making the
loop 5 cycles (15 clocks). RESP0 is written at the end of the delay loop.
HMOVE is applied later (at kernel entry, during HBLANK).

## Stella Emulator Tips
- Stelladaptor / 2600-daptor for real controller input
- Use `stella rom.bin` to run
- Debugger: `stella -debug rom.bin`
- In-game: Press ` (backtick) to enter debugger; Alt+Enter for fullscreen

### Stella Debugger Commands
Once in the debugger (backtick or -debug flag):

**Execution control:**
- `run` — resume emulation
- `frame` — advance one full frame (262 scanlines)
- `scanline N` — advance to scanline N
- `step` / `s` — step one CPU instruction
- `trace` / `t` — step and print state
- `exit` — quit Stella

**Breakpoints:**
- `break $F100` — set breakpoint at address $F100
- `breakset` / `bp N` — list breakpoints
- `breakclear N` — clear breakpoint N
- `clearbreaks` — clear all breakpoints
- `breakif {condition}` — conditional breakpoint (e.g. `breakif {a == 3}`)

**State examination:**
- `print <expr>` — evaluate/print an expression (hex/dec/bin). To read a memory
  address, dereference with `*` (e.g. `print *$81` reads the byte at playerY).
  Note: `print $81` prints the literal value `$81`, NOT memory. There is no
  `peek`/`memory`/`poke` command in Stella 7.0.
- `ram` — dump zero-page RAM ($80-$FF); `ram <addr> <val>` writes a value
- `tia` — show all TIA register values
- `riot` — show RIOT timer/IO state
- `pc` / `a` / `x` / `y` / `s` — show program counter / registers
- `c` / `z` / `n` / `v` / `d` / `i` — show individual CPU flags

**Display:**
- `scanline` — show current scanline count
- `cycles` — show CPU cycles this frame
- `video` — toggle per-scanline TIA state dump

**Useful watch expressions for breakif:**
- `{_scan==50 && _cyc==0}` — break at start of scanline 50
- `{_cyc>68 && _cyc<76}` — break during HBLANK
- `{peek(0x81) == 100}` — break when playerY ($81) equals 100
- `{peek(0x80) != 78}` — break when playerX ($80) changes from default

**ROM header analysis:**
- `rom` — dump ROM info (bankswitch type, etc.)
- `rom` flags to verify: `bankswitch F6`, `startBank 3`

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
- GRP0 (and PFx) must be written during HBLANK (color clocks 0-68), BEFORE the
  visible portion starts at color clock 68. Writing GRP0 late (during the visible
  portion) causes partial/glitched sprite rendering (e.g. only ~60% of the sprite
  shows and it flickers). To fit GRP0 + playfield in HBLANK, PRE-COMPUTE the
  sprite byte for scanline N+1 during scanline N and store it in a variable, then
  `lda var` / `sta GRP0` at the top of the next scanline. 1 CPU cycle = 3 color
  clocks.

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

## Local Reference Library

The `docs/` directory contains downloaded public references and source examples:

- `docs/tutorial/` contains Andrew Davie's Atari 2600 Memories tutorial sessions covering display timing, initialization, playfields, sprites, positioning, and vertical movement.
- `docs/stella/` contains Stella's public user and debugger documentation.
- `docs/examples/` contains public `johnidm/asm-atari-2600` examples, including small kernels and larger complete games.
- `docs/README.md` records source URLs, attribution, and which examples are useful for this project.

Check upstream license and attribution terms before redistributing or reusing substantial example code.

### Verified TIA Playfield Rules

- `CTRLPF` bit 0 is playfield reflection. `$00` repeats the left half; `$01` reflects it.
- `CTRLPF` bit 1 selects score mode; it is not the reflection bit.
- `PF0` uses bits 7-4 and is displayed before `PF1`; `PF2` follows with hardware-specific bit order.
- TIA state persists between scanlines. A kernel must write registers at deterministic points and budget every scanline to 76 CPU cycles.
- `WSYNC` stalls until the end of the current scanline. Code after `WSYNC` must still fit before the next visible portion.
- A 4K image uses standard/no bankswitching in Stella. An F6 image is 16K and requires F6 bankswitching.
