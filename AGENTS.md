# Atari 2600 Development Notes

## CURRENT PROTOTYPE ARCHITECTURE (HERO-direct, supersedes tile-budget notes)
- **F6 bankswitching (16K, 4 banks):** game code lives in `comparison/lo-a-rad-dragon/bank0.asm`
  (landing pad + `Main` + kernel + room/level data + vectors at $FFFC). Bank0 begins
  with a 5-byte pad (`ds.b 5`) + `jmp Main`; F6 powers up in bank3, whose stub
  (`lda #0; sta $1FF6`) selects bank0 and lands on that pad. Banks 1-3 are placeholders
  (same stub; bank3 holds the reset vector at physical $3FFC). Output is the 4 bank
  binaries concatenated via `./build_game_f6.sh` into `savior.bin`.
- `bank0.asm` includes `generated/level_001_room_001.asm` + `generated/level_001_room_002.asm`.
- Exactly HERO's rendering model: **reflected playfield with playfield priority
  (CTRLPF=$05), symmetric cave, player as a plain sprite over it.** No
  asymmetric PF2-right rewrites, no menu region, no 96-row/kernel-units,
  no 20x24 tile budget. Rooms are 20x16 text grids (`rooms/*.txt`), each tile
  = 8 color-clocks wide x 12 scanlines tall; the whole 192-line screen IS the
  cave. Rows MUST be left-right palindromes (the TIA mirrors the 20-bit half).
- `tools/convert_room.py` emits one PF0/PF1/PF2 triple per tile row (kernel
  writes each register ONCE per 12-line band; TIA persists) plus a 1-byte-per-
  tile RoomTileMap + RoomRowLo/Hi for collision. Render and collision both
  derive from this one file. Supports a PREFIX argument so multiple rooms can
  coexist in the same ROM without symbol collisions; `convert_level.py` uses
  `L{n}R{room}` (level n, room index+1).
- **Multi-level + miner:** every level is converted from `rooms/level_XXX.json`
  into `generated/level_XXX_rooms.asm` (per-level `LEVEL{n}_START_ROOM/X/Y`,
  `LEVEL{n}_MINER_ROOM/X/Y`, `LEVEL{n}_WALL_COLOR`, `LEVEL{n}_RoomDataTable`,
  `LEVEL{n}_RoomConnections`; tile coords * 8 for X, * 12 for Y become pixel
  bytes). `./build_game_f6.sh` runs `convert_level.py --levels generated/levels.asm`
  to emit `generated/levels.asm` (includes every level's tables + LEVEL_COUNT +
  LevelDataTable, one LEVEL_DATA_STRIDE=12 entry per level: start room/x/y,
  miner room/x/y, wall color, RoomDataTable ptr, RoomConnections ptr) and
  `generated/levels_data.asm` (includes every level's per-room data). Level
  numbers come from the input file name (level_002.json -> 2), not `level_id`.
  The game loads a level via `LoadLevel` (ZP: Level, LevelDataLo/Hi,
  LevelPFDataLo/Hi, LevelConnLo/Hi, LevelWallColor, LevelMinerRoom, MinerX/Y),
  `EnterRoom`/exits index `(LevelPFDataLo),Y`/`(LevelConnLo),Y` instead of
  static `RoomDataTable`/`RoomConnections`. The miner is a green ($c6 on
  COLUP1) 4x8 GRP1 square, positioned in VBLANK with `SetObjectXPos` X=1, drawn
  only when `RoomNo == LevelMinerRoom` by the same per-scanline test as the
  player; touching it (footprint overlap) increments Level (wrapping) and calls
  LoadLevel, respawning at the next level's origin. Playfield priority hides
  the miner behind walls like the player.
- Kernel: per scanline `WSYNC`, sprite byte written when `Scanline - PlayerY`
  in 0..7 (inline; WSYNC absorbs jitter, only constraint is GRP0 lands in
  HBLANK, < ~41 cycles). Coordinates are direct: `PlayerY` = scanline 0..191,
  `PlayerX` = room pixel 0..159 -> TIA via `SetObjectXPos`. Tile row from scanline
  = `/12` (YToCellRow), column = `/8`. Tile rows are drawn top-to-bottom (0..15);
  pressing up DECREASES `PlayerY` (scanline 0 is the top of the screen).
- Constants: PLAYER_MIN_X=4, PLAYER_MAX_X=163, PLAYER_MIN_Y=0, PLAYER_MAX_Y=184
  (keeps the 8-tall sprite flush with the screen edges in open passages).
- **Room system:** `RoomDataTable` (ROM, per room: TilePF0 ptr + RoomRowLo ptr)
  and `RoomConnections` (ROM, per room: up/down/left/right target index, $ff =
  none). `RoomNo` (ZP) indexes into both. `EnterRoom` loads the pointers for a
  given room. `ExitRoomUp`/`ExitRoomDown`/`ExitRoomLeft`/`ExitRoomRight` follow
  the current room's connection and place the player at the opposite edge.
  Vertical exits preserve RoomX, horizontal exits preserve RoomY, so the player
  stays in the aligned passage. `convert_room.py` builds each room file with
  prefixed symbols (Room1*, Room2*) to avoid collisions.

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
step (12) must equal the fine span (15). Used the River Raid algorithm:
compute fine = `((X+1)&15)` then `eor #7` / `asl x4` into HMP0, and a coarse
delay count via `(X+1)/16` with /15 correction; then a `dey;bpl` delay loop
that is PAGE-ALIGNED so the taken `bpl` crosses a page (3 cycles), making the
loop 5 cycles (15 clocks). RESP0 is written at the end of the delay loop.
HMOVE is applied later (at kernel entry, during HBLANK).

IMPLEMENTED IN THIS PROTOTYPE (`SetObjectXPos`, bank0.asm): Andrew Davie's
session-24 routine (docs/tutorial/session-24.html), which is the same
precision without the hand-aligned loop: `sta WSYNC; sec; sbc #15; bcs` then
`tay; lda fineAdjustTable,y; sta HMP0,x; sta RESP0,x`. The coarse loop burns
exactly 15 clocks/step and the page-aligned table (`FineAdjustBegin` is
`align 256`'d) maps each remainder (-15..-1) to an exact HMP nibble; the
indexed load's page-cross supplies the critical extra cycle. X = object
selector (0=player0). It positions the sprite's LEFT edge at the requested
pixel (0..159), so room X coords map 1:1 to visible columns.

## Collision Coordinates and Visible Sprite Footprint
- The game variable passed to `SetObjectXPos` is a logical positioning
  coordinate, not necessarily the visible left edge of the player sprite.
  `RESP0`, the fine-motion nibble, and the player graphics width create a
  visible offset that must be measured against the rendered image.
- Collision checks that compare `PlayerX` or `PlayerY` directly with playfield
  boundaries can therefore allow the sprite to overlap a wall or block an
  opening too early. In the current room prototype, the right wall required a
  substantially smaller logical `PLAYER_MAX_X`, and the top/bottom doorway
  range had to be narrower than the visible opening so the full sprite stayed
  inside the gap.
- Doorway movement must be checked against the player footprint, not only
  against an exact origin coordinate. At a top or bottom exit, horizontal
  movement needs doorway-specific limits; at a left or right exit, vertical
  movement needs the corresponding doorway limits. Rejected movement must
  clamp to the relevant wall or doorway edge, never to an unrelated room
  boundary, to avoid apparent teleporting.
- For future stages with different shapes, represent collision geometry in
  logical room coordinates and convert the player footprint into the same
  coordinate system. A robust move test should evaluate the proposed
  rectangle (or a smaller deliberate collision box) against wall segments and
  doorway rectangles before committing `PlayerX`/`PlayerY`.
- Keep the rendered geometry and collision geometry derived from one room
  definition. The current prototype exposed a specific failure mode: the
  side doorway was rendered from kernel counter values `39..60`, while the
  movement code used the expanded `PlayerY` range `32..68`; the player could
  therefore leave through visibly solid wall area. Do not tune these ranges
  independently.
- The kernel counter and `PlayerY` are not automatically the same vertical
  coordinate system. The player sprite is selected with `scanline - PlayerY`,
  while the room is selected directly from the kernel scanline counter. Generic
  rooms should use named room-space rectangles/segments and explicit
  conversion to both the kernel and player collision coordinates.
- When an opening must contain the entire sprite, convert its visible span to
  an allowed sprite-origin span: `origin_min = opening_min` and
  `origin_max = opening_max - sprite_height + 1`. Using the visible opening's
  maximum directly as `PlayerY` allows the sprite to extend beyond the wall;
  this caused the side exits to remain about one player height too permissive.
- For each proposed movement, test the player's future footprint against the
  room's solid geometry. An exit should be a traversable opening in that same
  geometry, not a separate hardcoded exception. This prevents visual/collision
  drift when room shapes or exit sizes change.
- The prototype uses `RoomX` and `RoomY` as the shared gameplay coordinates.
  `RoomY` follows the kernel's 2-scanline row coordinate, and `RoomX` remains
  a room-space horizontal coordinate. TIA coarse/fine positioning is an output
  conversion performed only by `SetObjectXPos`.
- Keep renderer-specific conversions at the boundary. Collision code should
  never compare against RESP0/HMP0 timing values; it should test the proposed
  room-space player footprint against room-space solids and exits.
- VERIFIED horizontal scale: the playfield is exactly 40 color-clocks wide
  (20-bit half, 4 color clocks per bit), but it SPANS the full 160-clock
  screen (40 blocks x 4 clocks). With reflection (CTRLPF D0=1), playfield
  block q (0..39) shows text column q in the left half (q 0..19) and text
  column 39-q in the right half (q 20..39). So a 20-column room renders as a
  mirrored 40-block full-screen cave, and horizontal collision MUST map the
  player footprint via RoomX>>2 (not >>3) and mirror blocks >=20 back to
  39-q before indexing the tile map. The old >>3 (8px/column) mapping was a
  2x scale error and dislocated left/right collision ~5 tiles to the right.
- The kernel writes one PF0/PF1/PF2 triple per 12-line band and the TIA
  persists it, so vertical tile row == scanline/12 is exact; horizontal is
  the only axis that needs the mirror conversion.

## Color Bytes and Stella Rendering

- Editor and converter share one hue-major 128-color RGB table
  (`tools/convert_level.py` kPalette === `tools/editor/src/AtariPalette.cpp`);
  the editor only stores wall RGB, never a byte, so round trip is stable.
- **Stella 7.0 with TV filtering OFF (`tv.filter=0`, the local default) does NOT
  interpret TIA bytes as the real chip does.** It renders `myPalette[byte]` by
  direct 8-bit index into a hue-major `(color, 0)`-interleaved 256-entry table.
  Hence the displayed color equals the classic chart `kPalette[hue][luma]` ONLY
  when the ROM byte is `(hue << 4) | (luma << 1)`. The textbook `(luma<<4)|hue`
  scrambles: `$2A`/`$17` render orange/gold instead of blue/purple.
- `convert_level.py` `nearest_byte()` therefore emits the emulator-aware byte
  `(hue << 4) | (luma << 1)`. Verified empirically with
  `tools/palette_test.asm` (button-cycled full-screen COLUPF probe); all 8 probe
  bytes matched the direct-index mapping exactly.
- To re-verify colors on a changed Stella/config, rebuild the probe
  (`dasm tools/palette_test.asm -f3 -opalette_test.bin`) and compare the user's
  per-step report against Stella's own palette order, not the classic chart.

## Visual Validation
- Stella launching successfully verifies only that the ROM loads; it does not
  verify rendering, timing, blinking, scrolling, or sprite placement.
- After any visual change, ask the user to confirm what is actually visible
  before treating the change as fixed. Do not infer visual correctness from a
  successful assembly or emulator startup.
- **Do NOT try to capture screenshots by running Stella** in this environment:
  the model cannot view images, and screenshot capture keeps getting aborted.
  When a visual (e.g. a HERO screen, menu, or sprite) must be examined, ask the
  user to either provide an ASCII representation of what they see or take a
  screenshot themselves and describe it.

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
./build_game_f6.sh        # runs the level converters + assembles all 4 banks
# equal to:
dasm comparison/lo-a-rad-dragon/bank0.asm -f3 -ocomparison/lo-a-rad-dragon/bank0.bin
dasm comparison/lo-a-rad-dragon/bank1.asm -f3 -ocomparison/lo-a-rad-dragon/bank1.bin
dasm comparison/lo-a-rad-dragon/bank2.asm -f3 -ocomparison/lo-a-rad-dragon/bank2.bin
dasm comparison/lo-a-rad-dragon/bank3.asm -f3 -ocomparison/lo-a-rad-dragon/bank3.bin
cat comparison/lo-a-rad-dragon/bank0.bin comparison/lo-a-rad-dragon/bank1.bin \
    comparison/lo-a-rad-dragon/bank2.bin comparison/lo-a-rad-dragon/bank3.bin > savior.bin
```

Notes:
- Assemble from the repo root (bank0's `include "generated/..."` paths are root-relative),
  not from inside `comparison/lo-a-rad-dragon/`.
- F6 power-up bank is bank3; its stub (`lda #0; sta $1FF6`) switches to bank0. All four
  banks start with the same 5-byte stub so any startup bank reaches `Main`. DASM here
  requires every mnemonic/directive to be indented (column-1 tokens are labels) AND
  requires `processor 6502` (indented) or it reports "Unknown Mnemonic".

## Development Workflow - Baby Steps

This project follows an incremental development approach:
- Make **small, focused changes** (one fix or feature at a time)
- **Test after each change** - ask user to verify in Stella before proceeding
- If something breaks, revert or fix before continuing
- Document any regressions or side effects found during testing
- Only add complexity after the current change is confirmed working

This prevents cascading issues common in Atari 2600 development where
timing, rendering, and input are tightly coupled.

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

## Verified HERO Reference (hero.bin, Activision)

### Cartridge profile
- `hero.bin` = 8 KB, **F8 bankswitch** (confirmed by Stella `-rominfo`: "F8* (8K)").
- Two 4K banks. Bank 1 lives at $F000-$FFFF at reset (reset vector `00 F0` at
  physical $1FFC). Bank 0 sits at $D000-$DFFF; the "weird" absolute reads in the
  kernel ($DC6A etc.) are just ROM in that lower window, not RAM.
- Banks bounce via the F8 hotspots: bank1 start does `STA $FFF9`
  (select bank0/$D000); bank0 start does `SEI; BIT $FFF9; ...; JSR $F000`
  (back to bank1).

### Disassembly workflow
- DiStella (v3.02) in repo root, e.g. `./distella -pafs hero.bin`.
  - Input must be exactly 2048/4096/8192 bytes; for F8, split banks first:
    `python3 -c "d=open('hero.bin','rb').read(); open('bank0.bin','wb').write(d[:0x1000]); open('bank1.bin','wb').write(d[0x1000:])"`
  - DiStella sets bank0 `ORG $D000`, bank1 `ORG $F000` automatically.
  - DiStella can miss code (kernel looked like `.byte` blobs); cross-check with a
    linear disassembler + hand-decode of raw bytes when a region looks suspicious.

### CTRLPF: reflected playfield, always, no asymmetric mode
- CTRLPF is written **once at startup and never touched again** (single
  `STA CTRLPF` in the whole 8K).
- bank1 init does: `LDA NUSIZ-style; STA NUSIZ1; ORA #$05; STA CTRLPF`.
  `$05` = bits 0 (reflect) + 2 (playfield priority). NUSIZ table is
  `$30,$30,$20,$20`, so CTRLPF ends up `$25` or `$35`:
  D0=1 reflect, D2=1 PF-priority (player drawn BEHIND walls), D1=0 (no score
  mode). Thus both halves always mirror symmetrically and read as one cave.

### Game kernel (bank0 $DC00), 1 scanline = 61 cycles
```
$DC00:  STA WSYNC
        STA RESMP1
        LDA ($91),Y / STA GRP0 / STA GRP1 / STA GRP0     ; player+ghost data, VDEL-style double write
        LDA ($95),Y / STA COLUP0 / STA COLUP1
        LDA $DC6C,X / STA PF2                             ; one scalar write per register
        LDA $DC6A,X / STA PF0
        LDA $DC77,X / STA PF1
        DEY / BPL $DC00
```
- Exactly **one PF0/PF1/PF2 write per scanline** from precomputed per-scanline
  tables; **no mid-line PF2 rewrite**, no asymmetric left/right content.
- Caves are symmetric by design (mirrored by hardware). Scroll-free screens:
  each screen's per-scanline PF pattern set is baked into the bank tables.
- Only the PF registers are written per line; COLUBK/NUSIZ/etc. are latched
  once per frame in VBLANK.
- A second, smaller kernel (also single-write) draws the jetpack/score rows.

### Lesson for this project
- The proven HERO/Adventure approach for a full-screen room + free-move player:
  **reflect the playfield (CTRLPF=$01), design the room symmetric about the
  center seam, bake per-scanline PFs.** The player coexists because playfield
  has priority (D2=1) and vanishes behind solid wall, so no sprite-vs-PF2
  timing conflict exists.
- Our `rooms/level_001_room_001.txt` pattern (`#...##...##...##...#`) is already
  center-symmetric, so CTRLPF=$01 alone makes it read as one continuous cave.

### Verified: the playfield mirror is never broken; asymmetry = objects
- Byte-scanned all of hero.bin for every PF write (`STA $0D/$0E/$0F`): 14 sites
  in bank0, 0 in bank1, one write per register per scanline in every kernel.
  **No mid-line/second PF rewrite exists anywhere.** In reflected mode a
  mid-line rewrite could alter only the right half (columns 20-39 draw later),
  but HERO never does it; the playfield is always perfectly mirrored.
- Per-screen cave patterns are 8-entry tables at `$DC6A/$DC6C/$DC77` (PF0/PF2/
  PF1) indexed by `X = screen & 7` (band 1 uses `$b3^7`, band 2 `($b2+1)^7`).
  Rendered output for all 8 indices is left-right symmetric per row.
- So the "parts added or adjusted afterwards" that look asymmetric on screen
  are **objects drawn on top of the mirrored playfield** (players, missiles,
  ball, and sprite tables like `$DDA0`/`$DA20` for mine carts/platforms), aided
  by playfield priority (D2=1) so objects hide behind walls but show over open
  space. For an asymmetric feature in our game, draw it as an object, not as a
  playfield bit.

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

## Adventure Reference Study

`comparison/adventure/adventure.asm` is kept as a local technical reference. Its
implementation demonstrates several useful, general Atari 2600 patterns without
requiring us to reuse its game data or assets:

- A compact frame loop uses VSYNC, a timed VBLANK section, a visible kernel, and
  an overscan timer. Game state is updated while VBLANK is active, before the
  kernel begins.
- Horizontal player positioning is isolated in `PosSpriteX`. The routine takes
  an X coordinate, subtracts 15 repeatedly to obtain the coarse delay, converts
  the remainder into the HMP high nibble, synchronizes with `WSYNC`, delays with
  `DEY/BPL`, and strobes `RESP0,X`. `X=0` selects player 0; the same routine can
  position other TIA objects through indexed registers.
- `HMOVE` is issued after all object position setup, immediately after a
  `WSYNC`, so fine motion is applied during horizontal blank.
- Vertical sprite graphics are changed during the scanline kernel. The reference
  keeps per-object Y coordinates in RAM and advances graphic data as the beam
  reaches each object.
- Room state is represented as an index into room/object tables. Objects carry
  room, X, and Y state, so only objects belonging to the current room need to be
  drawn or collided.
- Joystick input is read from `SWCHA` as an active-low nibble. Movement is
  converted into a direction mask, then applied to X/Y coordinates in a shared
  movement routine. A separate mask can disable directions during special game
  phases.
- Room transitions are handled as game-state changes after collision/boundary
  checks: select a new room index, then place the player at the corresponding
  entry edge. This is a better foundation for HERO-style connected rooms than
  trying to scroll the playfield first.

For this project, `comparison/lo-a-rad-dragon/bank0.asm` is a clean-room minimal
movement implementation inspired by these hardware techniques. It intentionally
does not copy Adventure's room data, graphics, object tables, or game-specific
logic.

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

### Verified Adventure Room-Kernel Pattern

- Adventure stores each room as complete `PF0/PF1/PF2` triples, not as separate
  features layered with `ORA` during rendering.
- Its kernel reloads all three playfield registers at deterministic scanline
  boundaries from a room-definition pointer. Each triple represents a fixed
  vertical strip, so adding walls changes room data without changing the
  kernel's cycle count.
- The current prototype should follow this pattern: derive each visible
  scanline or fixed-height strip from room geometry, then write all playfield
  registers from that result. Do not OR feature lookup tables into the
  existing playfield state.
- With reflected playfield mode, one PF pattern is mirrored by hardware.
  A right-side-only horizontal feature requires an asymmetric kernel/data
  strategy; simply adding bits to PF1/PF2 produces a mirrored feature.

### Room Tile Budget

- The target logical room layout is fixed at **20 columns x 24 rows**.
- Each logical tile represents **8x8 pixels**.
- The upper **16 tile rows** are the playable map.
- The lower **8 tile rows** are reserved for the menu.
- Room text files and future editor output must stay within this 20x24 budget;
  do not add map rows or columns to solve rendering problems.
- Room data is converted at build time into assembler data. The 6502 kernel
  must consume compact precomputed tables and must not parse text or perform
  expensive tile conversion during visible scanlines.
