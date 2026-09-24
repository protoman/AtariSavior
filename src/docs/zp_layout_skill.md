# Zero-Page Layout — Skill Reference

**Authoritative source:** sequential `byte` labels + `EQU`/`=` in `src/kernel.asm`
(verified against `bank0.lst` 2026-09-23 after bomb work). Bank1 EQUs from
`src/bank1.asm`. Do not trust older alias tables below this line's date.

## Overview

The Atari 2600 has 128 bytes of zero-page RAM ($80-$FF). All F6 banks share the
same physical ZP. Writing to a ZP address in one bank corrupts the value for
ALL banks.

**Exception:** Bank1 (menu) and bank0 (game) never run simultaneously.
Fold-pad handoff + bank0 VBLANK (`LoadPFBuffer`, game re-init) re-establishes
bank0 state. Bank1 may overlap bank0 PF/HUD addresses — document any overlap.

## Critical Rules

1. **Never use $100-$1FF as a buffer.** Mirrors $80-$FF (same 128 bytes).
2. **Never remove a middle sequential `byte`** — shifts every later address
   and breaks bank1 EQUs / fold-pad assumptions. Rename in place.
3. **New bank0 sequential vars go after `$BC`.** Free: `$BD-$C2` only if
   EnemyRam is relocated (currently occupied). After bomb work there is
   **no free sequential bank0 byte** — reuse scratch (`Temp`, collision
   temps) or steal a documented bank1-only address.
4. **Grep all `bank*.asm` before defining `$xx` EQU** in any bank.
5. **Do not touch from bank1 (live score/bomb):** `$F3-$F5` score,
   `$F6` BombX, `$F7` BombTimer, `$F0` PlayerBombs (read-only in bank1 HUD),
   `$F1` BombSnd (bank1 must not write),
   `$F8-$FF` PlayerGrp0 + stack mirror,
   `$AD` bank1 `Temp` (bank0 `TickCounter`), `$BD-$C2` EnemyRam,
   `$B5` BombPacked, `$85` BombY.

## Bank0 Sequential ZP ($80-$BC) — verified

| Addr | Name | Purpose |
|------|------|---------|
| $80 | RoomX | Player X (0-159) |
| $81 | RoomY | Player Y (0-191) |
| $82 | PlayerDir | Eye facing 0/1 |
| $83 | Scanline | Kernel scanline (0-191) |
| $84 | LineCount | Scanlines left in tile row |
| $85 | BombY | Bomb drop Y (scanline snapshot) |
| $86 | Grp0Ptr | Player sprite ptr lo (scratch) |
| $87 | Grp0PtrHi | Player sprite ptr hi (scratch) |
| $88 | Temp | General scratch (VBLANK COLUBK, ObjectCount, …) |
| $89 | MapPtrLo | Rect-list walk ptr lo |
| $8A | MapPtrHi | Rect-list walk ptr hi |
| $8B | CollisionX | Collision/mirror scratch |
| $8C | CollisionCellX | Player max tile col |
| $8D | CollisionCellY | Player top tile row |
| $8E | CollisionEndX | Player min tile col |
| $8F | CollisionEndY | Player bottom tile row |
| $90 | RoomRectsLo | Room rect list ptr lo |
| $91 | RoomRectsHi | Room rect list ptr hi |
| $92 | RectCount | Rect loop counter |
| $93 | vyLo | Y velocity lo (signed 16) |
| $94 | vyHi | Y velocity hi |
| $95 | PlayerYSub | Y subpixel accumulator |
| $96 | JetPower | Jet thrust 0..JET_MAX |
| $97 | StepsLeft | Vertical step budget |
| $98 | RoomNo | Current room index |
| $99 | RoomPF0Lo | TilePF0 ptr lo |
| $9A | RoomPF0Hi | TilePF0 ptr hi |
| $9B | RoomPF1Lo | TilePF1 ptr lo |
| $9C | RoomPF1Hi | TilePF1 ptr hi |
| $9D | RoomPF2Lo | TilePF2 ptr lo |
| $9E | RoomPF2Hi | TilePF2 ptr hi |
| $9F | LevelPFDataLo | Level RoomDataTable lo |
| $A0 | LevelPFDataHi | Level RoomDataTable hi |
| $A1 | LevelConnLo | RoomConnections lo |
| $A2 | LevelConnHi | RoomConnections hi |
| $A3 | Level | Level index |
| $A4 | LevelMinerRoom | Miner room index |
| $A5 | MinerX | Miner X |
| $A6 | MinerY | Miner Y |
| $A7 | LevelStartRoom | Spawn/teleport room |
| $A8 | LevelStartX | Spawn/teleport X |
| $A9 | LevelStartY | Spawn/teleport Y |
| $AA | LevelWallColor | COLUPF rows 0-3, 8-11 |
| $AB | LevelWallColor2 | COLUPF rows 4-7 |
| $AC | PlayerLives | Lives 0-3 |
| $AD | TickCounter | 1s power-bar step |
| $AE | BarLevel | Power bar 0-16 |
| $AF | LevelEnemyLo | Level enemy table lo |
| $B0 | LevelEnemyHi | Level enemy table hi |
| $B1 | EnemyDataLo | Room enemy data lo |
| $B2 | EnemyDataHi | Room enemy data hi |
| $B3 | EnemyCount | Enemies in room |
| $B4 | FlickerFrame | GRP1 slot index |
| $B5 | **BombPacked** | b0-1 state, b2 DownPrev, b3-6 WallMask, b7 spare |
| $B6 | ActiveObjectOn | GRP1 object visible |
| $B7 | ActiveObjectX | GRP1 object X |
| $B8 | ActiveObjectY | GRP1 object Y |
| $B9 | EnemyIndex | Selected enemy slot |
| $BA | DeadEnemyIdx | Killed enemy / $FF |
| $BB | ObjTop | GRP1 top scanline |
| $BC | ObjBot | GRP1 bottom scanline |

Sequential allocation ends at `$BC` (next would be `$BD`).

## Bank0 EQUs (fixed addresses, no sequential byte)

| Addr | Name | Notes |
|------|------|-------|
| $B3 | PF0ScoreBuf | Alias into EnemyCount area — score buffers (legacy name) |
| $B8 | PF1ScoreBuf | Alias |
| $C6 | PF2ScoreBuf | Alias (within PF0Buf) |
| $BD | EnemyRamX | 4 bytes live enemy X |
| $C1 | EnemyRamD | Packed dir bits 0-3 |
| $C2 | EnemyRamP | Packed moth/spider flags |
| $C3-$CE | PF0Buf | TilePF0 (12) |
| $CF-$DA | PF1Buf | TilePF1 (12) |
| $DB-$E6 | PF2Buf | TilePF2 (12) |
| $E7-$F2 | ColupfBuf | COLUPF stripes (12) |
| $F3 | ScoreTh | Shared with bank1 score |
| $F4 | ScoreHu | |
| $F5 | ScoreTe | |
| $F6 | **BombX** | Bomb drop X snapshot (bank1 must not write) |
| $F7 | **BombTimer** | Fuse/explode frames |
| $F0 | **PlayerBombs** | Bombs left 0..5 (S8; ColupfBuf+9, never VBLANK-written) |
| $F1 | **BombSnd** | Frames of bomb audio left (S10; 0=silent) |
| $F2 | free | ColupfBuf tail (unused) |
| $F8-$FF | PlayerGrp0 | 8 player rows **+ stack mirror** — copy only after last JSR |

Bank1 HUD `$E0-$EF` score ptrs/bar temps overlap ColupfBuf — safe because
bank1 runs after cave kernel; VBLANK reloads ColupfBuf via `LoadPFBuffer`.

## Bank1 ZP (menu / HUD) — verified EQUs

| Addr | Name | Purpose | Bank0 conflict |
|------|------|---------|----------------|
| $AC | PlayerLives | Shared lives | same |
| $AD | Temp | Bank1 scratch | bank0 TickCounter (different phase) |
| $AE | BarLevel | Shared bar | same |
| $E0-$EB | scorePtr1-6 | 6 digit ptrs | ColupfBuf/PF2Buf overlap OK |
| $EC | scbrdCnt | Score loop | ColupfBuf overlap OK |
| $ED | scbrdTmp | Score temp | ColupfBuf overlap OK |
| $EE | DelayCnt | Power-bar delay | ColupfBuf overlap OK |
| $EF | FineCnt | Power-bar fine | ColupfBuf overlap OK |
| $F3-$F5 | ScoreTh/Hu/Te | Score digits | shared |
| — | GameMode | Fold-pad mode flag | check `bank1.asm` before use |
| — | HUD slots | `HudSlotsRam` etc. | see bank1 / HUD notes |

**Removed / do not reintroduce:** bank1 `ScoreOn` at `$F6` (now BombX);
old DigitPtr* at `$F4/$F6/$F8`.

## Bank2 (legacy HUD trampoline)

Bank2 is not in the current F6 game path for score (HUD lives in bank0
`HudBand` + bank1 menu). If bank2 is re-enabled, it may only **reuse** bank0
PF buffers / score EQUs — never allocate new ZP addresses.

## Historical Crashes

- **$E0-$EB conflict (fixed):** bank1 digit pointers overwrote bank0 level
  pointers → crash on start→game.
- **Stack page as buffer (reverted e8c55c5):** `$0170-$01FF` mirrors ZP.
- **Score vs EnemyRam ($BF-$C2):** bank1 score corrupted enemy X[2]/dir;
  moved score to `$F3+`.
- **`TileRow` delete shifted `$86+`:** rename only; keep sequential slots.
- **`ObjectCount` at `$B5`:** freed for `BombPacked`; count kept in
  registers during `SelectActiveObject` only.

## Bomb vars (2026-09-23)

| Var | Addr | Reset |
|-----|------|-------|
| BombPacked | $B5 | `EnterRoom` (state+DownPrev+WallMask) |
| BombY | $85 | snapshot on drop |
| BombX | $F6 EQU | snapshot on drop |
| BombTimer | $F7 EQU | 180 fuse / 60 explode |

WallMask bits b3-6 = rect index 0-3 (`BombMaskBit` ROM table `$08,$10,$20,$40`).
