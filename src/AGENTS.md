# Savior Kernel — Architecture

## Overview

A from-scratch Atari 2600 game kernel modeled after Activision's HERO (1984). Built
in `src/` as a standalone project with no dependencies on the older prototype.

## ROM Layout

- **16K ROM** — F6 bankswitch (4 banks × 4K each)
- Bank0: `kernel.asm` — main game code, cave kernel, player logic
- Bank1-3: stubs (switch to bank0, ready for future expansion)
- Output: `savior.bin` (16K)

### F6 Bankswitching

| Bank | Address Range | Power-up | Contents |
|------|--------------|----------|----------|
| Bank0 | $F000-$FFFF | — | Game code + cave kernel |
| Bank1 | $F000-$FFFF | — | Stub → bank0 |
| Bank2 | $F000-$FFFF | — | Stub → bank0 |
| Bank3 | $F000-$FFFF | Yes | Stub → bank0 + reset vector |

Bank select: `STA $1FF6` (bank0), `$1FF7` (bank1), `$1FF8` (bank2), `$1FF9` (bank3).
Power-up bank is bank3; its reset vector at $FFFC points to the stub which switches to bank0.

## Frame Timing (262 scanlines @ 60Hz NTSC)

| Section    | Scanlines | Notes |
|------------|-----------|-------|
| VSYNC      | 3         | Sync pulse |
| VBLANK     | 37        | Game logic + sprite positioning |
| Kernel     | 192       | 144 cave + 48 HUD band |
| Overscan   | 30        | Input + movement |
| **Total**  | **262**   | NTSC standard |

## Memory Map

### Zero-page ($80-$FF, 128 bytes)

| Address | Name       | Purpose |
|---------|------------|---------|
| $80     | RoomX      | Player X position (0-159) |
| $81     | RoomY      | Player Y position (0-191) |
| $82     | Scanline   | Current scanline counter |
| $83     | LineCount  | Scanlines remaining in tile row |
| $84     | TileRow    | Current tile row (0-11) |
| $85-$86 | Grp0Ptr    | Player sprite pointer (unused yet) |
| $87     | Temp       | Scratch |

### TIA Registers (write-only at $00-$2F)

Key registers used:
- `$1B` GRP0 — Player sprite graphics
- `$1C` GRP1 — Object sprite graphics
- `$0D/$0E/$0F` PF0/PF1/PF2 — Playfield registers (persist across scanlines)
- `$08` COLUPF — Playfield color
- `$09` COLUBK — Background color

### TIA Read (active-low joystick at $0280)

- D4 = Up, D5 = Down, D6 = Left, D7 = Right (0 = pressed)

## Kernel Architecture

### Key Principle: Fixed-Time Inner Loop

The kernel's `.Line` loop must execute exactly the same number of cycles on
every scanline to avoid flicker. The2600 TV frame is 262 scanlines at 60Hz;
each scanline is 76 CPU cycles. If the loop exceeds 76 cycles on any
scanline, WSYNC stalls until the NEXT scanline, making the frame longer.

### Structure (HERO pattern)

```
.Row (×12):       PF setup — write PF0/PF1/PF2 ONCE per tile row
                   (TIA registers persist — no need to rewrite per scanline)
.Line (×12):      Sprite rendering — the tight inner loop
                   Unconditional: same instruction stream every scanline
```

### Per-scanline cycle budget (76 max)

Our `.Line` loop worst-case:

| Section        | Cycles (off-screen) | Cycles (on-screen) |
|----------------|--------------------|--------------------|
| GRP0 check     | 16                 | 19                 |
| Loop control   | 16                 | 16                 |
| **Total**      | **32**             | **35**             |

Both well within 76-cycle limit. No flicker.

### PF Write Strategy

PF registers (PF0/PF1/PF2) are written ONCE per tile row in `.Row`.
The TIA persists these values across all 12 scanlines of the row.
This saves 36 cycles per scanline (3 writes × 12 cycles each).

## Build

```bash
./build.sh          # builds savior.bin (16K, F6)
```

Requires: `dasm` (6502 cross-assembler)

## Testing

Run in Stella:
```bash
stella savior.bin        # normal emulation
stella -debug savior.bin # debugger
```

## Development Plan

### Phase 1: Basic Rendering ✅ (in progress)
- [x] VSYNC/VBLANK/Overscan frame timing
- [x] Kernel: 12 tile rows × 12 scanlines + 48 HUD band
- [x] Cave playfield with reflected mode (CTRLPF D0=1)
- [x] Player sprite (GRP0) — 8×8 square
- [x] Joystick movement (up/down/left/right)
- [ ] Fix cave shape (currently vertical bars — needs proper walls)
- [ ] Proper wall collision bounds

### Phase 2: Player Sprite & Positioning
- [ ] Horizontal positioning via RESP0/HMP0 (Andrew Davie algorithm)
- [ ] Player sprite art (not just a square)
- [ ] Smooth movement with proper pixel bounds
- [ ] Collision box matching visual sprite

### Phase 3: Collision Detection
- [ ] Player-to-playfield collision (CXP0FB)
- [ ] Wall collision prevention (don't walk through walls)
- [ ] Room boundary checks (don't leave room edges)
- [ ] Collision response (bounce/stop)

### Phase 4: Room System
- [ ] Room data format (20×12 tile grids in ROM)
- [ ] Room connections (up/down/left/right exits)
- [ ] Room transitions (load new room on exit)
- [ ] Multiple rooms per level
- [ ] Room-specific enemy placement

### Phase 5: Enemies (GRP1)
- [ ] Enemy sprite rendering (GRP1)
- [ ] Enemy positioning (RESP1/HMP1)
- [ ] Basic enemy AI (patrol, chase)
- [ ] Enemy-player collision
- [ ] Multiple enemy types

### Phase 6: HUD Display
- [ ] Score display (3 digits)
- [ ] Lives display
- [ ] Timer display
- [ ] Level indicator
- [ ] HUD rendering in the 48-line band

### Phase 7: Gameplay
- [ ] Laser/weapon system (missile 0)
- [ ] Bomb system (ball)
- [ ] Wall destruction
- [ ] Item collection
- [ ] Level progression
- [ ] Win/lose conditions

### Phase 8: Jetpack Physics
- [ ] Gravity (constant downward force)
- [ ] Thrust (upward force when button held)
- [ ] Inertia (momentum)
- [ ] Fuel management
- [ ] Vertical collision with ceiling

### Phase 9: Polish
- [ ] Sound effects (engine, laser, explosions)
- [ ] Music (background theme)
- [ ] Color schemes per level
- [ ] Screen transitions
- [ ] Title screen
- [ ] Game over screen
- [ ] Difficulty settings

### Phase 10: Levels & Content
- [ ] Design 5+ levels with increasing difficulty
- [ ] Level-specific enemy patterns
- [ ] Boss encounters
- [ ] Secret rooms/areas
- [ ] High score tracking

## HERO Architecture Reference

### Key Patterns to Follow

1. **Reflected Playfield**: CTRLPF D0=1 — left half mirrors to right.
   Cave design is symmetric about center seam.

2. **PF Persistence**: Write PF0/PF1/PF2 ONCE per tile row. TIA persists
   values across all 12 scanlines of that row. Saves 36 cycles/scanline.

3. **Fixed-Time Kernel**: Same instruction stream every scanline. No
   conditional branches that change cycle count. Sprite data from
   pre-computed buffers. PF data from lookup tables.

4. **Horizontal Positioning**: RESP0 for coarse (every 15 color clocks),
   HMP0 for fine (-8 to +7). HMOVE applied during HBLANK.

5. **Vertical Positioning**: Kernel scanline counter matches player Y.
   Sprite rendered when scanline falls within player's 8-line range.

6. **Collision**: TIA hardware collision registers (CXP0FB, CXPPMM, etc.)
   checked in VBLANK/Overscan after frame renders.

### Hero's Cave Structure

```
Row 0-3:   ####....................................####   (thick walls)
Row 4-7:   ##..........................................##   (thin walls)
Row 8-11:  ###################....#####################   (bottom passage)
```

The cave is 20 logical columns wide. With reflection, each half mirrors.
PF0/PF1/PF2 define the left half; TIA mirrors the right.

### Playfield Register Layout (Left Half)

| Register | Bits    | Pixels (color clocks) |
|----------|---------|----------------------|
| PF0      | 7-4     | 0-3 (leftmost)       |
| PF1      | 7-0     | 4-11                 |
| PF2      | 0-7     | 12-19 (reversed)     |

## Differences from HERO

| Feature | HERO | This kernel |
|---------|------|-------------|
| ROM size | 8K (F8 bankswitch) | 16K (F6 bankswitch) |
| PF writes | Per-scanline (ROM tables) | Per-tile-row (simpler) |
| Sprite data | `(zp),Y` from ROM | ZP indexed (`PlayerGrp0,Y`) |
| VDEL | Used for sprite pipeline | Not used (simpler) |
| Enemies | Yes (miner + enemies) | Not yet |
| Rooms | Multiple connected rooms | Single hardcoded room |
| HUD | Score/lives/time text | Grey band only |
| Jetpack | Physics with gravity | Simple up/down |

## Debugging

### Stella Debugger

- `stella -debug savior.bin` — launch with debugger
- Backtick (`) — enter debugger from emulation
- `run` — resume execution
- `breakLabel <addr>` — set bankswitch-safe breakpoint
- `clearbreaks` — clear all breakpoints
- `scanline` — show current scanline

### Timing Measurement

Use `breakLabel` at two addresses, subtract Scn values:

1. `clearbreaks`
2. `breakLabel <start_addr>` → run → note Scn value
3. `clearbreaks`
4. `breakLabel <end_addr>` → run → note Scn value
5. Subtract to get duration in scanlines

**NEVER use `break`** — it fires at the physical ROM address in ALL banks
(causes cross-bank contamination with bankswitched ROMs).

### Pseudo-registers (Stella 7.0)

- `_scan` does NOT work — resolves to $00 (CXM0P)
- `breakif {_scan == N}` is UNRELIABLE
- Use `breakLabel` + Scn field instead
