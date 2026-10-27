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
   `$F1` BombSnd (bank1 must not write),
    `$F8-$FF` stack mirror only (PlayerGrp0 buffer removed 2026-09-24 — never buffer here),
   `$AD` bank1 `Temp` (bank0 `TickCounter`), `$BD-$BF`+`$C1-$C2` EnemyRam,
   `$C0` LaserState (bank0 laser S1),
   `$B5` BombPacked, `$85` BombY.
7. **PHASE-SHARING RULE (2026-10-22): a byte may be shared by two owners when
   their LIFETIMES never overlap — but only with a documented contract, a
   reset at the phase boundary, and a grep proving the other owner is dead.**
   The first case, and the shape to copy: the title melody needed two bytes
   (`MelPtr`/`MelTimer`) only while the TITLE runs, and on title frames the
   bomb block never executes (`DropTarget != 0` → `DropStep`), so the melody
   now lives in `$F6`/`$F7` (= `BombX`/`BombTimer`). That freed `$9D`/`$9E`,
   which the CAVE kernel needs on **both** kinds of frame (the title previews
   the stage with real room objects) — so those two could not be shared, the
   music's could. On the way back to the title (`SELECT+RESET` at
   `GameStart`'s tail) the two bytes are cleared, so the theme restarts instead
   of reading `MusicMel` with a stale gameplay value.
   Checklist before sharing: (a) name the two phases, (b) grep every reader of
   the byte in all four banks and prove the non-owner never runs in the other
   phase, (c) reset at the transition (the phase that "receives" the byte must
   not inherit the other's state), (d) write the contract at the EQU in BOTH
   banks, (e) if the read can happen in both phases, sharing is NOT allowed.
   **The room-change case is the same rule:** anything scoped to a ROOM
   (`EnemyDataLo/Hi`, `EnemyCount`, `EnemyRamX/Y/D/P`, `RoomRectsLo/Hi`,
   `RoomMetaA/B`, `LevelConnSpare`) is re-derived by `EnterRoomB2` every time a
   room is entered — a new per-room byte MUST be staged on that path (and
   nothing may read it before the first room load), otherwise it silently
   carries the previous room's value, exactly like the 2026-10-22 melody bug.
8. **STOMP-ZONE RULE (S3.2, machine-enforced):** bank1 HUD writes `$E0-$EF`
   every frame (score ptrs + bar temps). Bank0 state written ONCE and read
   across frames must live **below `$E0`**. Documented exceptions (both
   window-ordered, both machine-checked ordering): `ColupfBuf` `$E7`
   (rebuilt every VBLANK before the next kernel read) and `EnemyRamY`
   `$E2-$E4` (written at overscan entry, every read before the next
   stomp). Staged-only bytes may sit in the zone (`FetchPtr` `$E5-$E6`:
   stage→read happens inside one VBL/overscan batch, HUD runs between
   batches; `BandTab` `$ED`: bank2 `StageBandTab` stages it in VBL, the
   cave `.Row` gate reads it, bank1 `scbrdTmp` stomps only after the cave
   is done). Violation symptom: field silently zeroed/changed every HUD
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
| $89 | ZPSpare89 | **FREE** (was `RcBase`, the rect-cache count — retired with the cache by plan C4 2026-10-20; kept allocated so the sequential block does not shift. bank1's `ClearPFColumn` uses it as `CPCScratch` during a bomb punch) |
| $8A | DropTarget | Spawn drop-in target Y (0 = idle; **$FF = title-screen sentinel**, valid targets ≤ 191). Was MapPtrPad1 dead pad — slot kept so the sequential block doesn't shift |
| $8B | CollisionX | Collision/mirror scratch |
| $8C | CollisionCellX | Player max tile col |
| $8D | CollisionCellY | Player top tile row; **time-partitioned**: VBL `StageBandTab` stages the P2b door stripe color ($80 = none / $1C = yellow) for the cave band-setup line's `COLUP1` write; overscan PHM's prologue restages it as the top-row temp AFTER the kernel — lifecycles never overlap |
| $8E | CollisionEndX | Player min tile col; **time-partitioned**: overscan PHM/LWC/blast/laser stage+read their own min-col, and VBL `StageBandTab` stages the D6 M1X (TilePF0+14, 0=none) for `PositionBallM1`'s same-VBL read — window closes before overscan restages, so the alias never crosses frames |
| $8F | CollisionEndY | Player bottom tile row |
| $90 | RoomRectsLo | Record-stream ptr lo: the room's extras FEATURE-record stream, or the static `RoomNoStream` `$00` count (C11 2026-10-21 — a shape block carries no stream any more) |
| $91 | RoomRectsHi | Room data block ptr hi |
| $92 | RectCount / RowIdx | Hot-record loop counter (post-kernel; also room-block scratch in `B3RoomBlocks`); kernel tile-row index (alias, re-inited at kernel entry) |
| $93 | vyLo | Y velocity lo (signed 16) |
| $94 | vyHi | Y velocity hi |
| $95 | PlayerYSub | Y subpixel accumulator |
| $96 | JetPower | Jet thrust 0..JET_MAX |
| $97 | StepsLeft | Vertical step budget |
| $98 | RoomNo | Current room index |
| $99 | RoomPF0Lo | Block-loader scratch: TilePF0 ptr lo inside B3RoomBlocks/ExtrasLoad, then OVERWRITTEN with the room's staged MetaA for the whole visit (`RoomMetaA` — same byte; the 3 PF rows are contiguous from TilePF0) |
| $9A | RoomPF0Hi | Same dual use: TilePF0 ptr hi during the load, then the staged MetaB (`RoomMetaB`; C5 2026-10-20: the pair comes from the room extras, not the block) |
| $9B | BarIdx | Power-bar table idx `(BarLevel+7)>>3` (synced in kernel overscan, read by bank1 HUD) |
| $9C | Hover | Respawn hover flag (bugs.md #1): 1 while armed (LoseLife), cleared at LoadLevel |
| $9D | MelPtr | Intro music: melody stream index (bank1 MusicTick) |
| $9E | MelTimer | Intro music: melody frames left (bank1 MusicTick) |
| $9F | LevelPFDataLo | Level RoomDataTable lo |
| $A0 | LevelPFDataHi | Level RoomDataTable hi |
| $A1 | LevelRoomN | Rooms in this level (C1/C4 2026-10-20: RoomPositions = block+2n (1 B/room, LEVEL_FORMAT 2), RoomEnemies = +3n, enemy records = +4n) |
| $A2 | LevelConnSpare | bank2 exit-scan target (C1 2026-10-20; was LevelConnHi, pointer derived) |
| $A3 | Level | Level index |
| $A4 | LevelMinerRoom | Miner room index |
| $A5 | MinerX | Miner X |
| $A6 | MinerY | Miner Y |
| $A7 | LevelStartRoom | b7 = KeyHeld; b6-4 = miners still to rescue (b4 own, b5/b6 extras by RoomNo&1); b3-0 = power cells taken (bit RoomNo&3); the start room is the constant 0. Seeded by LoadLevelB2 |
| $A8 | LevelStartX | Spawn/teleport X |
| $A9 | LevelStartY | Spawn/teleport Y |
| $AA | LevelWallColor | COLUPF rows 0-3, 8-11 |
| $AB | LevelWallColor2 | COLUPF rows 4-7 |
| $AC | PlayerLives | Lives 0-3 |
| $AD | TickCounter | 1s power-bar step |
| $AE | BarLevel | Power bar 0-16 |
| $AF | RoomM1Hot | C11 2026-10-21: hot-band M1 block cell = `col+1` (0 = none), staged by bank3's `ExtrasLoad` from the room's side-1 row-1 patch (was `LevelEnemySpare`; kernel decl carries the new name — `check_equ_sync` pairs it with bank3's EQU) |
| $B0 | M1X (LevelEnemySpare2) | async M1 block X, staged by the room load (0 = none). **Never use as scratch**: the old source was `CollisionEndX`, the laser wall-clamp's scratch, and a leftover there drew a phantom M1 dash in every room (fixed 2026-10-22) |
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
| $D7-$DA | **EnemyClk / EnemySpd / EnemyFrac / EnemyPass** | Enemy speed multiplier (2026-10-26): the ENEMY clock (every enemy gate/bob reads it, not EnemyRamP/TickCounter), half-units per frame `2 + Level/5` (set by LoadLevelB2), the odd-half carry, and the passes left this frame. `$CC-$D6` are NOT free any more (PF2Buf `$CB-$CE`, BandTab `$CF-$D2`, ColupfBuf `$D3-$D6`) - the old '$CC-$DF FREE' note was stale; `$DB-$DF` are the only free bytes left in the persistent zone. |
| $CC-$DF | **FREE (20 B)** | Was the solid-rect ZP cache (rect0-4, `RcW1`). **Retired by plan C4 (2026-10-20)**: every collision walker (player, laser, moth, bomb punch, hot parent) tests the PF buffers, so there is no cache and no rect list in the block data. Reclaim, not a shift: nothing is allocated here. **STOMP-ZONE RULE still applies to every persistent byte** — the first S3.2 layout ended at `$E0` and bank1's `scorePtr1` lo zeroed rect4.h every HUD frame, which is why the old cache had to stay below `$E0`. FetchPtr lives at `$E5`. |
| $E2-$E4 | EnemyRamY | Live Y, private 3B (S3.4) — sits in the bank1 stomp zone but window-safe (write/read between stomps — kernel ZP contract block). |
| $E5-$E6 | FetchPtr | Fold-indirect pointer (moved `$E0→$E5` S3.2 to free `$E0`, then out of the cache entirely). Staged-only: batch stage→read inside one VBL/overscan window; bank1 `scorePtr3+1/scorePtr4` share the bytes in HUD. Fold operand is byte-guarded (`FOLD_BYTES` in verify_build). |
| $EA-$EC | (free in gameplay) | Tile 11 VCRUNCH was removed 2026-10-19, together with its `VcrState`/`VcrNext`/`VcrBand` slice staging; the cave kernel derives every band length locally now. The bytes remain bank1-only ($EA/$EB = scorePtr6 lo/hi, $EC = scbrdCnt) and are built after the cave read, so a future gameplay writer may use them only with the usual staged-only window (rule 6). |
| $ED | BandTab | Phase 3 asym-ball band gate bytes (3B, `$ff` = ball band). Staged by bank2 `StageBandTab` (BuildColupF tail) every VBL; read by `.Row`'s `lda BandTab,X / sta ENABL`; bank1 HUD `scbrdTmp` stomps `$ED` only after the cave read (staged-only, rule 6). Bank2 mirrors the EQU (`check_equ_sync` pins both to kernel). |
| $E7-$F2 | ColupfBuf | Final COLUPF × 12 rows — but only rows 0-2 ($E7-$E9) are ever written (TILE_ROWS=3; rows 9-11 are the bombs' own bytes, no overlap machinery since S3.0b). Bank1 clobbers $E7-$EF during HUD; VBLANK rebuilds every frame (S2.1 blocker, see progress doc). |
| $F3 | ScoreTh | Score 100k\|10k, packed BCD (2026-10-27; was one binary digit, max 9,999). Shared with bank1 |
| $F4 | ScoreHu | Score 1k\|100, packed BCD |
| $F5 | ScoreTe | Score tens\|ones, packed BCD. Max 999,999; a carry INTO ScoreTh = +10,000 and awards the extra life (every 50,000, max 8 `PlayerLives`) |
| $F6 | **BombX** | Bomb drop X snapshot (bank1 must not write) |
| $F7 | **BombTimer** | Fuse/explode frames |
| $F0 | **PlayerBombs** | Bombs left 0..5 (lives at `$F0` physically = old ColupfBuf[9]; nothing writes it but bomb logic since S3.0b) |
| $F1 | **BombSnd** | Frames of bomb audio left (S10; 0=silent) |
| $F2 | **TallyTicks** | Level-bonus countdown (50-pt units). **#18 banner alias:** bank1 `LevelShowTimer` shares the byte — bit7 = banner flag (armed `$F8`, decs to `$80` in `SetupScorePointers`); tally ARM (<=127) or the boot-intro gate (DropTarget=$FD skips the arm in LoadLevel) kills the banner instantly. Was listed "free" here 2026-10-02 — stale; TallyTicks predates the 2026-10-09 banner. |
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
| $E0-$EB | scorePtr1-6 | 6 digit ptrs | stomps ColupfBuf[0-2] ($E7-$E9) + EnemyRamY ($E2-$E4) every frame — both safe by rebuild/write window (see above); $E5/$E6 additionally time-partition with kernel `FetchPtr` (S3.2: bank0 stages only in VBL/overscan batches, HUD rebuilds after); $EA/$EB additionally = `VcrState`/`VcrNext` until they were retired with tile 11 (2026-10-19) |
| $EC | scbrdCnt | Score loop | ColupfBuf dead-row overlap OK; `VcrBand` was retired with tile 11 (2026-10-19) |
| $ED | scbrdTmp | Score temp | ColupfBuf dead-row overlap OK; also kernel `BandTab` (Phase 3 band gate bytes) — staged every VBL and read by the cave BEFORE this HUD stomp, so the time-partition is safe (staged-only, see rule 6) |
| $EE | DelayCnt | Power-bar delay | ColupfBuf dead-row overlap OK |
| $EF | FineCnt | Power-bar fine | ColupfBuf dead-row overlap OK |
| $F3-$F5 | ScoreTh/Hu/Te | Score, 3 packed-BCD bytes (6 digits) | shared |
| $8D/$8E/$8F | CollisionCellY/EndX/EndY | Bank0 collision temps (bomb save slots deleted S3.0b) | bank1 must not use |
| — | GameMode | Fold-pad mode flag | check `bank1.asm` before use |
| — | HUD slots | `HudSlotsRam` etc. | see bank1 / HUD notes |

## Bottom band (2026-09-24)

- **Home = `$D2` (2026-09-28)** — alias of `PF1Buf[3]`, a fill-only dead row
  (kernel `.Row` reads X=0..2; `ClearPFColumn` rows 0..2; bank1 has no `$D2`
  EQU). First attempt `$EC` failed (inside `ColupfBuf` row 5); then `$D1` =
  `PF1Buf[2]` failed (kernel `lda PF1Buf,X` X=2 rendered the band color as the
  bottom-band PF1 wall — phase_1 dump `$D1=00` vs model `$ff`).
- Band color is NOT in the RoomEnemies record any more (2026-10-20 pack): the
  record is ONE byte (`count<<6 | first record index<<1 | bottom-band flag`)
  and the color is the single game-wide `BAND_COLOR` (generated
  `levels_equ.asm`, included by bank2 before `EntryRoomB2`). Convert rejects a
  second water color.
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

## Lifetime audit (2026-10-22) — who re-stages what, and when

Rule 7 says a shared byte must be reset at the phase handover. This is the map
of that handover for every existing ZP byte, produced by
`tools/zp_lifetime_audit.py` (re-run it after adding any byte):

| lifetime | bytes | re-staged by |
|---|---|---|
| **frame scratch** (never crosses a phase) | `Temp`, `FetchPtr`, `EnemyIndex`, `CollisionX/CellX/CellY/EndX/EndY`, `RectCount`, `StepsLeft`, `BarIdx`, `ObjBase/ObjTop/ActiveObject*`, `ObjBase1/ObjTop1/ObjX1`, `ObjHeight/ObjHeight1`, `FlickerFrame`, `BallX`(Temp), `BandTab` | every frame, by design — nothing to reset |
| **room** | `EnemyDataLo/Hi`, `EnemyCount`, `EnemyRamX/Y/D/P`, `EnemyDeadMask`, `RoomRectsLo/Hi`, `RoomMetaA/B`(= `RoomPF0Lo/Hi`), `RoomNo`, `RoomBandColor`, `LevelConnSpare` | `EnterRoomB2` → `LoadEnemyRam` (EBLER_Loop) → `B3RoomBlocks`/`ExtrasLoad` — **every** room entry, including the first |
| **level** | `Level`, `LevelRoomN`, `LevelPFDataLo/Hi`, `LevelStartRoom/X/Y`, `LevelWallColor/2`, `MinerX`, `MinerY`, `LevelMinerRoom` | `LoadLevelB2` — once per level (the miner is level data: one per level, deliberately NOT per room) |
| **run** (survives level changes) | `PlayerLives` (GameStart/LoseLife), score (`ScoreHu/Th/Te`), `PlayerBombs` (LoadLevelB2 re-fills) | `GameStart` |
| **phase** (title ⇄ game ⇄ tally) | `DropTarget` (sentinel), `BombX`/`BombTimer` (= the title melody, rule 7) | the phase entry itself: `GameStart` ($FF title), `DropArm`, `TallyEntry` ($FE) |
| **window-ordered exceptions** | `ColupfBuf` `$E7`, `EnemyRamY` `$E2-$E4`, staged-only bytes in `$E0-$EF` | see rule 8 (stomp zone) |

Audit result: every room-scoped byte has a writer on the room-load path, so
entering a room cannot inherit the previous room's geometry. The one deliberate
exception is the miner trio (`MinerX`/`MinerY`/`LevelMinerRoom`): it is LEVEL
data — if a future feature wants a per-room miner, it must be staged inside
`EnterRoomB2` and this table updated.

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
| BombPacked | $B5 | state+DownPrev only on room change; b3-6 WallMask live in-room only (pack/restore deleted, plan 5.2) |
| BombY | $85 | snapshot on drop |
| BombX | $F6 EQU | snapshot on drop |
| BombTimer | $F7 EQU | 180 fuse / 60 explode |
| ~~RoomWallMask~~ | ~~$F2 EQU~~ | **deleted, plan 5.2 (D1-B)** — `$F2` now FREE |

~~WallMask b3-6~~ — **retired, plan 5.1b/C4 (2026-10-20)**: `BombMarkWalls`
no longer sets mask bits (`BombMaskBit`, the ABW rect tables and `PairGone`
are gone). A repeat blast is blocked by the buffer itself (the punched D7
cell is empty). **C11 (2026-10-21): `HOVHotPfGate` is gone.** Hot death is
derived from the PF buffers directly — `HotOverlapBody` sweeps the player
box's display columns over PF row 1 (gated by `RoomMetaB` b6), so a punched
thin parent is simply not solid and stops being hot: no record, no gate.
`$AF RoomM1Hot` stages the one PF-OPEN hot cell (the M1 block).
EnterRoom pack/restore into `$F2` deleted (5.2, D1-B): holes reset on
room change, and the re-entered wall is bombable again (buffer clear).

## Stack depth (re-measured 2026-10-01, after Phase 3)

`sim_bomb_fuse` (every build): **gameplay min SP = `$F9`** (guard ≥ `$F8`),
whole-run min SP = `$F7` (guard ≥ `$F7`). Phase 3 + S5.x fold removals
improved the historical `$F8`-boundary gameplay figure by 1 byte — but the
rule stands: **the stack page mirrors ZP; buffers at `$F8-$FF` are
forbidden; measure, never infer.**
