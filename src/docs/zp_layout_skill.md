# Zero-Page Layout — Skill Reference

**Authoritative source:** sequential `byte` labels + `EQU`/`=` in `src/kernel.asm`
(verified against `bank0.lst` 2026-10-01 after Phase 3). Bank1 EQUs from
`src/bank1.asm`, bank2 from `src/bank2.asm`. Machine-checked every build by
`verify_build.check_equ_sync` (cross-bank hand-copy drift + stomp-zone rule).
Do not trust older alias tables below this line's date.

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
3. **Sequential block ends at `$BB`** (`ObjBot` removed S3.0b — it was the
   last decl; nothing shifts after it). `$BC` onward are explicit EQUs
   (`RoomBandColor`, `EnemyRamX`…): you may re-point an EQU, but a NEW
   sequential `byte` after `$BB` would land on `$BC` = RoomBandColor —
   there is still **no free sequential bank0 byte**. Reuse scratch
   (`Temp`, collision temps) or steal a documented bank1-only address.
4. **Grep all `bank*.asm` before defining `$xx` EQU** in any bank — then
   let `check_equ_sync` verify it (it compares every shared name against
   the kernel authority map).
5. **Do not touch from bank1 (live score/bomb):** `$F3-$F5` score,
   `$F6` BombX, `$F7` BombTimer, `$F0` PlayerBombs (read-only in bank1 HUD),
   `$F1` BombSnd (bank1 must not write), `$F2` RoomWallMask (bank1 must not write),
    `$F8-$FF` stack mirror only (PlayerGrp0 buffer removed 2026-09-24 — never buffer here),
   `$AD` bank1 `Temp` (bank0 `TickCounter`), `$BD-$BF`+`$C1-$C2` EnemyRam,
   `$C0` LaserState (bank0 laser S1),
   `$B5` BombPacked, `$85` BombY.
6. **STOMP-ZONE RULE (S3.2, machine-enforced):** bank1 HUD writes `$E0-$EF`
   every frame (score ptrs + bar temps). Bank0 state written ONCE and read
   across frames must live **below `$E0`**. Documented exceptions (both
   window-ordered, both machine-checked ordering): `ColupfBuf` `$E7`
   (rebuilt every VBLANK before the next kernel read) and `EnemyRamY`
   `$E2-$E4` (written at overscan entry, every read before the next
   stomp). Staged-only bytes may sit in the zone (`FetchPtr` `$E5-$E6`:
   stage→read happens inside one VBL/overscan batch, HUD runs between
   batches). Violation symptom: field silently zeroed/changed every HUD
   frame → this is exactly how rect4.h broke the tentacle (S3.2).

## Bank0 Sequential ZP ($80-$BC) — verified

| Addr | Name | Purpose |
|------|------|---------|
| $80 | RoomX | Player X (0-159) |
| $81 | RoomY | Player Y (0-191) |
| $82 | PlayerDir | Eye facing 0/1 |
| $83 | LaserBeamOn | S2.2r2 beam gate: $02 held / $00 else (was Scanline, dead since S2.2) |
| $84 | LineCount | Scanlines left in tile row |
| $85 | BombY | Bomb drop Y (scanline snapshot) |
| $86 | Grp0Ptr | Player sprite ptr lo (scratch) |
| $87 | Grp0PtrHi | Player sprite ptr hi (scratch) |
| $88 | Temp | General scratch (VBLANK COLUBK, ObjectCount, …) |
| $89 | RcBase | Rect cache **count** (sequential decl — was MapPtrLo; the $89 slot now hosts the count so the 20 rect bytes fit $CC-$DF clear of bank1's $E0 stomp — S3.2-fix, see cache row) |
| $8A | MapPtrPad1 | Was MapPtrHi (rect4.y) — dead pad, keeps the sequential block from shifting |
| $8B | CollisionX | Collision/mirror scratch |
| $8C | CollisionCellX | Player max tile col |
| $8D | CollisionCellY | Player top tile row |
| $8E | CollisionEndX | Player min tile col |
| $8F | CollisionEndY | Player bottom tile row |
| $90 | RoomRectsLo | Room rect list ptr lo |
| $91 | RoomRectsHi | Room rect list ptr hi |
| $92 | RectCount / RowIdx | Rect loop counter (post-kernel); kernel tile-row index (alias, re-inited at kernel entry) |
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
| $B5 | **BombPacked** | b0-1 state, b2 DownPrev, b3-6 WallMask, b7 OnGround |
| $B6 | ObjBase | GRP1 design offset into ObjSprites (0 = off; was ActiveObjectOn) |
| $B7 | ActiveObjectX | GRP1 object X |
| $B8 | ActiveObjectY | GRP1 object Y |
| $B9 | EnemyIndex | Selected enemy slot |
| $BA | EnemyDeadMask | per-enemy dead bits b0-2 (0 = alive; was DeadEnemyIdx $FF=none) |
| $BB | ObjTop | GRP1 top scanline |

Sequential allocation ends at `$BB` (ObjBot `$BC` removed S3.0b; next
sequential byte would be `$BC`, but `$BD+` are explicit EQUs and `$BC` is
`RoomBandColor`'s EQU).

## Bank0 EQUs (fixed addresses, no sequential byte)

| Addr | Name | Notes |
|------|------|-------|
| $BD | EnemyRamX | 3 bytes live enemy X ($BD-$BF, slots 0-2 only — `EnemyRamX[3]` would collide with `$C0` LaserState; slot bound enforced by `convert_level.MAX_ENEMIES=3` (runtime ceiling), while the policy cap is 2 objects/room enforced three ways: editor `kMaxRoomElements=2`, `convert_level` rooms from JSON, `verify_build` enemies+lamps ≤2) |
| $C0 | LaserState | laser S1: b7 held, b6 prev, b1-0 sweep phase |
| $C1 | EnemyRamD | Packed dir bits 0-3 |
| $C2 | EnemyRamP | Free-running frame clock (`inc` once/frame in RefreshEnemyY; gates bat/spider/tentacle derives; init `$F0` on room load = harmless seed) |
| $BC | RoomBandColor | Band-color cache — **own byte since S3.1** (was `$D2` = PF1Buf[3]; the whole `$D1`/`$D2`-alias class is deleted). VBL stage → kernel `.WaterRow` (plain abs = 4c at any address) + overscan `CheckBandTouch`; nobody else writes `$BC`. |
| $C3-$C5 | PF0Buf | TilePF0 rows 0-2 (**packed S3.1**, was `$C3-$CE`). Rows 0-2 pure since S3.4 (Y → `$E2`); pattern written by EnterRoom `LoadPFBuffer` only, never stomped. |
| $C6-$C8 | PF1Buf | TilePF1 rows 0-2 (**packed S3.1**, was `$CF`). Kernel `.Row` X=0..2 + bank1 `ClearPFColumn`. |
| $C9-$CB | PF2Buf | TilePF2 rows 0-2 (**packed S3.1**, was `$DB`). |
| $89 + $CC-$DF | Rect cache | **count + rects0-4 UNIFORM (S3.2)** — count `RcBase=$89` (sequential decl), walk base `RcW1=$CC`, stride 4 for all five rects (Y=0..19): no windows, no `.Stage3` (both deleted), mask index4 = `$00` table entry (rect4 never in WallMask). rect4 x,y,w,h = `$DC-$DF`. ABW tables EQU-derived — cannot go stale. **STOMP-ZONE RULE:** every persistent byte here must stay < `$E0` — the first S3.2 layout ended at `$E0` and bank1's `scorePtr1` lo (leading zero) zeroed rect4.h every HUD frame → probes passed through rect4 walls (tentacle walked inside walls). Guarded by `check_equ_sync` (`RcW1+19 ≤ $DF`). FetchPtr lives at `$E5` (fold operand byte-guarded: FOLD_BYTES). |
| $E2-$E4 | EnemyRamY | Live Y, private 3B (S3.4) — sits in the bank1 stomp zone but window-safe (write/read between stomps — kernel ZP contract block). |
| $E5-$E6 | FetchPtr | Fold-indirect pointer (moved `$E0→$E5` S3.2 to free `$E0`, then out of the cache entirely). Staged-only: batch stage→read inside one VBL/overscan window; bank1 `scorePtr3+1/scorePtr4` share the bytes in HUD. Fold operand is byte-guarded (`FOLD_BYTES` in verify_build). |
| $E7-$F2 | ColupfBuf | Final COLUPF × 12 rows — but only rows 0-2 ($E7-$E9) are ever written (TILE_ROWS=3; rows 9-11 are the bombs' own bytes, no overlap machinery since S3.0b). Bank1 clobbers $E7-$EF during HUD; VBLANK rebuilds every frame (S2.1 blocker, see progress doc). |
| $F3 | ScoreTh | Shared with bank1 score |
| $F4 | ScoreHu | |
| $F5 | ScoreTe | |
| $F6 | **BombX** | Bomb drop X snapshot (bank1 must not write) |
| $F7 | **BombTimer** | Fuse/explode frames |
| $F0 | **PlayerBombs** | Bombs left 0..5 (lives at `$F0` physically = old ColupfBuf[9]; nothing writes it but bomb logic since S3.0b) |
| $F1 | **BombSnd** | Frames of bomb audio left (S10; 0=silent) |
| $F2 | **RoomWallMask** | Packed destroyed thin-wall mask until stage leave: bits0-3 room0 rects, bits4-7 room1 rects (b3-6 of BombPacked saved/restored in EnterRoom; LoadLevel zeros it) |
| $F8-$FF | *(free)* | **stack mirror only** — PlayerGrp0 removed (kernel reads ROM via `Grp0Ptr`); never put a buffer here |

Bank1 HUD `$E0-$EF` (score ptrs + bar temps) stomps ColupfBuf rows 0-2 and
the `EnemyRamY` overlay every frame. Safe because: Colupf is rebuilt every
VBLANK (before the next kernel read), and `EnemyRamY` is rewritten at
overscan entry — every Y read sits between the write and the next stomp
(window diagram in kernel.asm's ZP contract block).

**Save-temp lifetime (obsolete since S3.0b):** the bomb save/restore into
`CollisionCellY/EndX/EndY` was deleted — `BuildColupF` writes rows 0-2
only and nothing else touched `$F0-$F2` between save and restore.

## Bank1 ZP (menu / HUD) — verified EQUs

| Addr | Name | Purpose | Bank0 conflict |
|------|------|---------|----------------|
| $AC | PlayerLives | Shared lives | same |
| $AD | Temp | Bank1 scratch | bank0 TickCounter (different phase) |
| $AE | BarLevel | Shared bar | same |
| $E0-$EB | scorePtr1-6 | 6 digit ptrs | stomps ColupfBuf[0-2] ($E7-$E9) + EnemyRamY ($E2-$E4) every frame — both safe by rebuild/write window (see above); $E5/$E6 additionally time-partition with kernel `FetchPtr` (S3.2: bank0 stages only in VBL/overscan batches, HUD rebuilds after) |
| $EC | scbrdCnt | Score loop | ColupfBuf dead-row overlap OK |
| $ED | scbrdTmp | Score temp | ColupfBuf dead-row overlap OK |
| $EE | DelayCnt | Power-bar delay | ColupfBuf dead-row overlap OK |
| $EF | FineCnt | Power-bar fine | ColupfBuf dead-row overlap OK |
| $F3-$F5 | ScoreTh/Hu/Te | Score digits | shared |
| $8D/$8E/$8F | CollisionCellY/EndX/EndY | Bank0 collision temps (bomb save slots deleted S3.0b) | bank1 must not use |
| — | GameMode | Fold-pad mode flag | check `bank1.asm` before use |
| — | HUD slots | `HudSlotsRam` etc. | see bank1 / HUD notes |

## Bottom band (2026-09-24)

- **Home = `$D2` (2026-09-28)** — alias of `PF1Buf[3]`, a fill-only dead row
  (kernel `.Row` reads X=0..2; `ClearPFColumn` rows 0..2; bank1 has no `$D2`
  EQU). First attempt `$EC` failed (inside `ColupfBuf` row 5); then `$D1` =
  `PF1Buf[2]` failed (kernel `lda PF1Buf,X` X=2 rendered the band color as the
  bottom-band PF1 wall — phase_1 dump `$D1=00` vs model `$ff`).
- Band color is the RoomEnemies per-room 4th byte (`ptr_lo, ptr_hi, count, bottom_color`).
  Read via `LoadRoomBottomColor` (`.WaterRow` band strip + overscan `CheckBandTouch`).
- Sequential map remains full after bomb work; do not add a new sequential
  `byte` casually. (Band color: since **S3.1** it has its own byte at `$BC` —
  the freed ObjBot slot — the alias-over-dead-row trick above is history.)

**Removed / do not reintroduce:** bank1 `ScoreOn` at `$F6` (now BombX);
old DigitPtr* at `$F4/$F6/$F8`.

## Bank2 (level data + offloaded bodies) — verified EQUs

Bank2 holds: frozen level data (`$F9D9+`), `MothRoutine` (its own rect
walk — shares the ZP cache), `BuildColupF`, `HotOverlapBody`,
`LaserHitTestBody`, the fold block + tramp pads. Its EQUs are hand-copies
of kernel addresses — **`check_equ_sync` verifies every shared name each
build** (historical bugs: stale `TickCounter=$AC`, stale `RcBase`). Bank2
must never allocate a ZP address kernel doesn't define.

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
| BombPacked | $B5 | state+DownPrev only on room change; WallMask saved to `$F2` |
| BombY | $85 | snapshot on drop |
| BombX | $F6 EQU | snapshot on drop |
| BombTimer | $F7 EQU | 180 fuse / 60 explode |
| RoomWallMask | $F2 EQU | pack both rooms' WallMask; **zeroed only by `LoadLevel`** |

WallMask bits b3-6 = rect index 0-3 (`BombMaskBit` ROM table
`$08,$10,$20,$40,$00` — 5th entry `$00` since S3.2: the uniform walk
touches index 4 (rect4), which is never masked).
EnterRoom pack: old room0 → `$F2` b0-3; old room1 → `$F2` b4-7; restore inverse into BombPacked b3-6.

## Stack depth (re-measured 2026-10-01, after Phase 3)

`sim_bomb_fuse` (every build): **gameplay min SP = `$F9`** (guard ≥ `$F8`),
whole-run min SP = `$F7` (guard ≥ `$F7`). Phase 3 + S5.x fold removals
improved the historical `$F8`-boundary gameplay figure by 1 byte — but the
rule stands: **the stack page mirrors ZP; buffers at `$F8-$FF` are
forbidden; measure, never infer.**
