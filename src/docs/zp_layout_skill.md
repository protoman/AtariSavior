# Zero-Page Layout — Skill Reference

## Overview

The Atari 2600 has 128 bytes of zero-page RAM ($80-$FF). All F6 banks share the
same physical ZP. Writing to a ZP address in one bank corrupts the value for
ALL banks. This document maps every byte to prevent cross-bank conflicts.

## Critical Rule

**ZP is shared across ALL banks.** Before defining new ZP variables in any bank,
check that addresses don't conflict with variables used by other banks.

**Exception:** Bank1 (start screen) and bank0 (game) never run simultaneously.
Fold-pad handoff reinitializes bank0's ZP during VBLANK. So bank1 can safely
use addresses that overlap bank0's PF buffers — but the addresses must be
documented here to prevent future confusion.

## Bank0 ZP Map (Game Code)

### $80-$B2: Game Variables (51 bytes)

| Addr | Name | Purpose |
|------|------|---------|
| $80 | RoomX | Player X position (0-159), alias PlayerX |
| $81 | RoomY | Player Y position (0-191), alias PlayerY |
| $82 | PlayerDir | Sprite eye facing: FACING_RIGHT(0) or FACING_LEFT(1) |
| $83 | vyLo | Y velocity low byte (subpixel; signed 16-bit, +=down) |
| $84 | vyHi | Y velocity high byte (whole pixels/frame, signed) |
| $85 | PlayerYSub | Subpixel accumulator for Y velocity integration |
| $86 | JetPower | Jet thrust 0..JET_MAX; ramps +1/frame while Up held |
| $87 | StepsLeft | Per-frame Y pixel steps remaining (vertical physics) |
| $88 | Scanline | Current kernel scanline counter |
| $89 | LineCount | Scanlines remaining in current tile row |
| $8A | MapPtrLo | Room tile map pointer (low) |
| $8B | MapPtrHi | Room tile map pointer (high) |
| $8C | CollisionX | Collision check X coord, alias Grp0Ptr (low) |
| $8D | CollisionCellX | Collision check cell X, alias Grp0Ptr (high) |
| $8E | CollisionCellY | Collision check cell Y, alias ObjTop |
| $8F | CollisionEndX | Collision check end X, alias ObjBot |
| $90 | CollisionEndY | Collision check end Y, alias LaserScanline |
| $91 | RoomPFDataLo | Current room TilePF0 table address (low) |
| $92 | RoomPFDataHi | Current room TilePF0 table address (high) |
| $93 | RoomRectsLo | Current room rectangle collision data (low) |
| $94 | RoomRectsHi | Current room rectangle collision data (high) |
| $95 | RoomNo | Current room index into RoomDataTable |
| $96 | Level | Current level index (0 = first level) |
| $97 | LevelDataLo | Pointer into LevelDataTable (low) |
| $98 | LevelDataHi | Pointer into LevelDataTable (high) |
| $99 | LevelPFDataLo | Active level RoomDataTable base (low) |
| $9A | LevelPFDataHi | Active level RoomDataTable base (high) |
| $9B | LevelConnLo | Active level RoomConnections base (low) |
| $9C | LevelConnHi | Active level RoomConnections base (high) |
| $9D | LevelWallColor | COLUPF for walls rows 0-3, 8-11 (emulator-aware) |
| $9E | LevelWallColor2 | COLUPF for walls rows 4-7 (emulator-aware) |
| $9F | LevelMinerRoom | Room index holding the miner for active level |
| $A0 | MinerX | Miner spawn X (logical room pixel coords) |
| $A1 | MinerY | Miner spawn Y |
| $A2 | LevelEnemyLo | Active level RoomEnemies table base (low) |
| $A3 | LevelEnemyHi | Active level RoomEnemies table base (high) |
| $A4 | EnemyDataLo | Current room enemy data base address (low) |
| $A5 | EnemyDataHi | Current room enemy data base address (high) |
| $A6 | EnemyCount | Number of enemies in current room (0..MAX_ENEMIES) |
| $A7 | FlickerFrame | GRP1 slot index for this frame |
| $A8 | ObjectCount | Enemies + (1 if miner's room) |
| $A9 | ActiveObjectOn | 1 when current room owns GRP1 object this frame |
| $AA | ActiveObjectX | GRP1 object X (room pixel 0..159) |
| $AB | ActiveObjectY | GRP1 object Y (scanline 0..191) |
| $AC | EnemyIndex | Selected enemy index within room's enemy data |
| $AD | Temp | General scratch |
| $AE | LevelStartRoom | Active level origin room (spawn + enemy-hit teleport) |
| $AF | LevelStartX | Active level origin X |
| $B0 | LevelStartY | Active level origin Y |
| $B1 | EnemyLoopCount | CheckEnemyHit loop counter |
| $B2 | GameMode | 0 = start screen (bank1), nonzero = game (bank0) |

### $B3-$BC: Font Data (10 bytes)

| Addr | Name | Purpose |
|------|------|---------|
| $B3-$B7 | FontP0 | P0 character font data (5 rows) — used by bank2 |
| $B8-$BC | FontP1 | P1 character font data (5 rows) — used by bank2 |

### $BD-$C2: Laser + Score Digits (6 bytes)

| Addr | Name | Purpose |
|------|------|---------|
| $BD | LaserActive | 0 = inactive, nonzero = frames remaining |
| $BE | LaserY | Scanline where the laser beam is drawn |
| $BF | ScoreTh | Score thousands digit (0-9, BCD) |
| $C0 | ScoreHu | Score hundreds digit (0-9, BCD) |
| $C1 | ScoreTe | Score tens digit (0-9, BCD) |
| $C2 | ScoreOn | Score ones digit (0-9, BCD) |

### $C3-$F2: PF/Color Buffers (48 bytes)

| Addr | Name | Purpose |
|------|------|---------|
| $C3-$CE | PF0Buf | TilePF0 values (12 bytes, one per tile row) |
| $CF-$DA | PF1Buf | TilePF1 values (12 bytes, one per tile row) |
| $DB-$E6 | PF2Buf | TilePF2 values (12 bytes, one per tile row) |
| $E7-$F2 | ColupfBuf | COLUPF per tile row, stripe colors (12 bytes) |

### $F3-$F7: FREE (5 bytes)

No bank0 variables allocated here. Safe for bank1 to use.

### $F8-$FF: Player Sprite (8 bytes)

| Addr | Name | Purpose |
|------|------|---------|
| $F8-$FF | PlayerGrp0 | Player sprite rows (8 bytes, computed per frame) |

### EQU Aliases (no bytes allocated, just name aliases)

| Alias | Address | Notes |
|-------|---------|-------|
| ScoreDigit2 | $C6 | Within PF0Buf range — leftover, not used at runtime |
| ScoreDigit3 | $CB | Within PF1Buf range — leftover |
| Grp1Value | $CB | Pre-computed GRP1 value ($F0 when visible, 0 otherwise) |
| Enam0Value | $CC | Pre-computed ENAM0 value ($02 when laser active, 0 otherwise) |
| Grp0Ptr | $8C | Alias for CollisionX (low byte of GRP0 sprite table pointer) |
| ObjTop | $8E | Alias for CollisionCellY |
| ObjBot | $8F | Alias for CollisionEndX |
| LaserScanline | $90 | Alias for CollisionEndY |

## Bank1 ZP Map (Start Screen)

Bank1 runs the start screen independently of bank0. Since bank0 and bank1
never run simultaneously (fold-pad trampoline switches between them, and
bank0 reinitializes its ZP during VBLANK), bank1 can safely use addresses
that overlap bank0's PF buffers.

### Current Bank1 ZP Allocation

| Addr | Name | Purpose | Overlaps bank0? |
|------|------|---------|----------------|
| $AD | Temp | Scratch variable | Yes (bank0 Temp) — safe, bank0 reinit |
| $AE | RowCnt | Score render row counter (old, to be removed) | Yes (bank0 LevelStartRoom) |
| $B3 | PF0ScoreBuf | Unused with sprite approach (to be removed) | Yes (bank0 FontP0) |
| $B8 | PF1ScoreBuf | Unused with sprite approach (to be removed) | Yes (bank0 FontP1) |
| $C6 | PF2ScoreBuf | Unused with sprite approach (to be removed) | Yes (bank0 PF0Buf+3) |
| $F0 | ScoreTh | Thousands digit | No bank0 var here |
| $F1 | ScoreHu | Hundreds digit | No bank0 var here |
| $F2 | ScoreTe | Tens digit | No bank0 var here |
| $F3 | ScoreOn | Ones digit | No bank0 var here |
| $F4 | DigitPtr1 | Old digit 0 pointer (to be removed) | No bank0 var here |
| $F6 | DigitPtr2 | Old digit 1 pointer (to be removed) | No bank0 var here |
| $F8 | DigitPtr3 | Old digit 2 pointer (to be removed) | Yes (bank0 PlayerGrp0) |

### Proposed Bank1 ZP for 6-Digit Score Kernel

| Addr | Name | Purpose | Overlaps bank0? |
|------|------|---------|----------------|
| $E0-$EB | scorePtr1-6 | 6 digit font pointers (2 bytes each, 12 total) | Yes (PF2Buf+ColupfBuf) — safe |
| $EC | scbrdCnt | Loop counter (7 to 0) | Yes (ColupfBuf) — safe |
| $ED | scbrdTmp | Mid-scanline temp cache | Yes (ColupfBuf) — safe |
| $EE | DelayCnt | Bar delay A preloaded once per HUD frame (bank1 only) | Yes (ColupfBuf+7) — safe; VBLANK reloads ColupfBuf |
| $EF | FineCnt | Bar fine delay cycles 0/2/3/4 (bank1 H3 only) | Yes (gap before ScoreTh $F0) — safe |
| $F0 | ScoreTh | Thousands digit | No conflict |
| $F1 | ScoreHu | Hundreds digit | No conflict |
| $F2 | ScoreTe | Tens digit | No conflict |
| $F3 | ScoreOn | Ones digit | No conflict |

**Why $E0-$ED is safe for bank1:** These addresses fall within bank0's
PF2Buf ($DB-$E6) and ColupfBuf ($E7-$F2) ranges. But bank0 only reads
these during the cave kernel, which runs in bank0 frames. Bank1 (start
screen) never reaches the cave kernel. When control returns to bank0 via
fold pad, VBLANK reinitializes all PF/Colupf buffers from ROM before the
cave kernel reads them.

## Bank2 ZP Map (Game HUD)

Bank2 is called from bank0's kernel via fold-pad trampoline at $FC78.
It shares bank0's ZP fully (runs within the same frame as bank0).

| Addr | Name | Purpose |
|------|------|---------|
| $B3-$B7 | FontP0 | Reused from bank0 (P0 font data for Level line) |
| $B8-$BC | FontP1 | Reused from bank0 (P1 font data for Level line) |
| $C3-$CE | PF0ScoreBuf | Score PF0 values (reuses PF0Buf after Level done) |
| $CF-$DA | PF1ScoreBuf | Score PF1 values (reuses PF1Buf) |
| $DB-$E6 | PF2ScoreBuf | Score PF2 values (reuses PF2Buf) |
| $C2 | ScoreTh | Thousands digit (alias into bank0 PF0Buf range) |
| $C3 | ScoreHu | Hundreds digit (alias into bank0 PF0Buf range) |
| $C4 | ScoreTe | Tens digit |
| $C5 | ScoreOn | Ones digit |
| $AD | Temp | Scratch (same as bank0) |

## ZP Allocation Rules

1. **Never use $100-$1FF as a buffer.** On the 2600, this mirrors $80-$FF
   (same 128 bytes). Writing `STA $0170,X` corrupts ALL ZP variables.

2. **New bank0 variables go AFTER existing ones.** Current end is $F2
   (ColupfBuf). Free range: $F3-$F7 (5 bytes only). PlayerGrp0 at $F8-$FF
   is computed per-frame and not safe for persistent storage.

3. **Bank1 variables at $E0-$ED are safe** because bank1 and bank0 never
   run simultaneously. Document any new bank1 allocations here.

4. **Bank2 variables must not add new ZP addresses.** Bank2 reuses bank0's
   PF buffers after the Level line is rendered (the buffers are no longer
   needed for cave rendering at that point in the frame).

5. **Before defining a new ZP variable, grep all bank*.asm files** for the
   target address to check for conflicts. A symbol defined as an EQU
   (`= $xx`) does not allocate a byte but will cause assembler errors if
   duplicated.

## Historical Crashes (Lessons Learned)

- **$E0-$EB conflict (fixed):** Bank1 previously wrote digit pointers to
  $E0-$EB which overlapped bank0's level data pointers. Caused crashes when
  switching from start screen to game. Fixed by moving bank0 level pointers
  to sequential allocation within the $97-$A5 range.

- **Stack page as buffer (reverted):** Attempted to use $0170-$01FF as a
  GRP pre-computation buffer. On the 2600, $0100-$01FF mirrors $80-$FF,
  so writing there corrupted ALL ZP variables. Crashed the game on left/right
  input. Reverted in commit e8c55c5.

- **Cross-bank ZP writes:** Any new variable added to bank0 must be checked
  against bank1's allocations and vice versa. The fold-pad trampoline
  does not save/restore ZP — both banks write freely and rely on
  reinitialization at entry.
