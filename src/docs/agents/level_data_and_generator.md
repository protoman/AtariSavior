# Level data format and the stage generator

_Data-format migration, async walls/extras/row pool, the bank2/bank3 level-data split, and the generator rules (phase, hcrunch)._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

## File-Format Changes Require Data Migration

When changing a serialized or generated data format, update all existing project data and its generators in the same change. Preserve compatibility with older files through an explicit version/default migration, or migrate those files before requiring the new format. Verify both legacy loading and new-format round trips; never leave checked-in data behind the code's schema.

**Async walls live on the ROOM (2026-10-17 move — do NOT put them back on the model).**
`room.asym_patches` = `[[row, col, tile, side?], ...]` (ball/M1 strip, door; ≤2,
both sides may differ) and `room.feature_cells` = `[[row, col, tile], ...]`
(P/V/C = 10/11/12, row 1 only, one kind per room). The model keeps only the
SHAPE (`tiles` = air/wall/hot/raft + `mid_band_type`); a model that still
carries `asym_patches` or a P/V/C grid tile is STALE and `convert` hard-fails it
with a migration hint. Why the room owns it: one model shape is reused by rooms
with different async, and the editor edits the room, not the model.

Consequences that are easy to get wrong:
- **A room points at its shared MODEL SHAPE; async rides a per-level EXTRAS
  stream** (C5 2026-10-20). The shape block is EXACTLY the 3 row-pool indices
  (C11 2026-10-21, `LEVEL_FORMAT = 6`) — both the `TilePF0+9/+10`
  MetaA/MetaB contract AND the per-shape hot stream are RETIRED. A room with
  the shape byte's b7 set carries an extras record (selected by the counts
  byte's b5-0 ordinal): `flags (n_patches b1-0 | n_features b5-2)`, `MetaA`,
  `MetaB`, 1 B/patch (`band b7-6 | side b4 | col b3-0` — the DRAWN band, not
  the authored row: a 3-row model's row 2 is band 3 and band 2 is the AIR
  pad), 1 B/feature (`kind
  b7-6 | col b3-0`), then — feature rooms only — the room's FEATURE-record
  stream (`count` + 5 B records, all b7-set classes: `$80` phase cell / `$82`
  hcrunch prefix). Hot cells are NOT records: see the hot bullet below.
- **HOT DEATH IS PF-DERIVED** (C11 2026-10-21): convert promotes EVERY row-1
  wall cell of a `mid_band_type=1` model, so a hot shape's hot cells ARE its
  solid row-1 PF cells, and the C4 bomb punch clears PF cells — a blasted
  (thin) parent cell stops being hot with no record and no parent gate.
  `HotOverlapBody` (bank3) sweeps the player box's display columns over
  `PF0Buf + 1 + ColOff[X]` gated by `MetaB` b6 (hot rooms only; it only runs
  on a cell-walk hit). The one PF-OPEN hot cell — the M1 block on the hot band
  — is staged by `ExtrasLoad` in `RoomM1Hot` (`$AF`, col+1) from the room's
  side-1 row-1 patch and dies with the strip (`EnemyDeadMask` b4). Hot cells
  never exist on rows 0/2. Do NOT re-introduce per-shape hot records: the
  shape block is 3 bytes and `verify_build.check_shape_blocks` hard-fails a
  count byte / `RoomRects` label / 5 B record.
- **Band gates: MetaA b0-2 + MetaB b4, and the collision pack has FOUR bits**
  (2026-10-24). `BandTab` ($CF-$D2) is one $ff/$00 ENABL byte per band, staged
  by `B3StageBand` from the 4-bit mask through `BandTpl` (16 rows x 4 B).
  `MetaA` b3 is the left-door flag, so band 3's gate lives in `MetaB` b4; the
  retired phase-1 bridge (`BandTab+2` -> `BandTab+3`) lit the ball in the AIR
  band of a migrated room — never re-add a mirror. The VBL pack `$8F`
  carries b0-3 = the four gates (b3 doubles as the M1-present flag when NO
  band is painted, so an M1-only room still packs nonzero), b4-7 =
  right_col+1; `OvHead/OvTail` are the 4-band pairs `15,14,12,8` / `1,3,7,15`
  in BOTH bank0 and bank2 (a 3-entry copy made a band-3 strip pass-through).
  Guards: `tools/test_async_band3.py`, `tools/test_phase3_ball.py`,
  `tools/test_cell_map.py` (asym sweep covers band 3).
- **The editor authors one ROW PER DRAWN BAND** (2026-10-24): `hero::kRoomHeight
  = 4`, so `models.json`/`stage.json` may carry 4-row models (10x4). The
  converter accepts BOTH: 3 rows = the legacy grid, expanded to
  `[r0, r1, AIR, r2]` by `convert_room.band_map()`; 4 rows = one row per band
  (identity). `DataSerializer::MigrateToFourBands` does that same expansion on
  LOAD, so opening an old stage re-saves it 4-row, and it moves room patches
  authored on the old bottom row (row 2 -> row 3). The E2 QA generator
  (`Build20LevelStage`) still speaks THREE bands via its own `kGenRows` — its
  plans, exits and QA expectations are 3-band, and its models migrate on load
  like any legacy file.
  **M1 strip caveat when a 3-row stage becomes 4-row:** the async M1 strip is
  a WHOLE-CAVE latch (`ENAM1`), so its column must be wall-or-patched in EVERY
  band. The old bottom row (the floor) hid it in band 2; the inserted AIR band
  does not, so `resolve_asym_patches` now hard-fails with "band 2 col N is open
  air and has no patch" and the editor prints the same warning on migration.
  Fix per room: wall that cell, or extend the strip with a side-1 patch for
  band 2. Do NOT auto-wall it in the migration — a wall cell is band-tall and
  would split the corridor for the OTHER rooms sharing the model.
- **The shape's PF bytes are a ROW DICTIONARY** (C3 2026-10-20): each band is a
  1 B index into the global `RowPoolPF0/1/2` columns (3 B per DISTINCT row,
  emitted once in `models_data.asm` with `LEVEL_ROW_COUNT`). The indices sit at
  `block + 0..2` (C11) and band 1's b7 = the model's `mid_band_type` hot flag,
  so `LEVEL_ROW_COUNT` must stay ≤ 128. The loader expands them into `PF0Buf`
  (`lda RowPoolPFn,X / sta PF0Buf+3n,Y`). Never emit raw PF into a shape:
  `verify_build.check_shape_blocks` hard-fails it.
- **The level-data subsystem is SPLIT across two banks (C7 2026-10-20)** and
  the split is the invariant: a routine may only dereference data in ITS OWN
  bank. **bank2 = the ROOM half** (`LevelDataTable` entries, the per-level
  `RoomShapes`/`RoomPositions`/`RoomCounts` block + flat `EnemyDataTable`) with
  its walkers `EnterRoomB2`, `ExitScanB2`/`ExitDirB2` + the four exit bodies,
  `LoadLevelB2`, `MothRoutine`, `LaserWallClamp`/`LaserHitTestBody`,
  `BombEnemyBlastBody`. **bank3 = the SHAPE half** (shape blocks + row pool +
  `LEVEL_ShapeTable` + the async extras streams + the `LevExtrasLo/Hi` base
  table) with its walkers `B3RoomBlocks`/`ExtrasLoad`, `PhaseBlink`/
  `BuildColupF`/`BCFDarkRun`, `HotOverlapBody`/`HOVFeatEntry`,
  `B3StageBand`, `PhHcrEntry`/`CrPfx`/`HcrClock`.
- `bank3.B3RoomBlocks` (PINNED at `$F453`) expands the shape rows, then either
  derives `MetaA=0 / MetaB=$40*hot` (no extras; the hot flag is band 1's index
  b7, C11) or tail-jumps to `ExtrasLoad`, which indexes bank3's
  `LevExtrasLo/Hi[Level]`, walks the stream by the room's 1-based ordinal, ORs
  the side-0 patch rows into MetaA, stages `RoomM1Hot` from a side-1 row-1
  patch, sets the feature PF bits, and repoints `RoomRectsLo/Hi` at the
  extras FEATURE-record stream (`RoomNoStream` when the room has none).
  `B3StageBand` still reads only the STAGED `$99/$9A` pair, so the runtime
  contract is unchanged.
- **The ONE cross-bank call of the room load**: `EnterRoomB2` stages the raw
  shapes byte in `RoomPF0Lo` ($99, loader scratch) + the extras ordinal in
  `LevelConnSpare` ($A2), then executes `sta $1FF7` at `$F450`; the opcode
  fetch at `$F453` comes from bank3, so `B3RoomBlocks` MUST stay pinned there
  (`verify_build.check_bank3_entry`). There is no return pad and no twin: the
  shape step runs **last**, so bank3's chain ends in **bank3's own
  `ReturnPad`** (`sta $1FF4` at `$FBF8`, the `rts` served by bank0) — 0 extra
  stack pushes, which is what keeps `sim_bomb_fuse`'s SP floor.
- **Two traps the C7 order creates** (both cost a debug pass): `ExtrasLoad`
  runs AFTER `LoadEnemyRam`, so it must NOT use `EnemyDataLo` as scratch (its
  feature counter is `EnemyIndex`); and the joystick-shadow refresh moved into
  bank3's `ERLoadDone` because every shape walker uses `Temp` as scratch while
  bank0's input block keeps reading `Temp` for the rest of the frame (the
  2026-10-20 "eye snaps right" lesson).
- The extras records are emitted into `generated/level_00N_extras.asm` (bank3,
  with `levels_extras.asm` as the per-level base table), NOT into the level
  table file: a feature room's FEATURE-record stream lives inside its record
  and the VBL walkers read it in-bank. `emit_spills` (bugs.md 27b) places only
  THIS
  stage's `level_00N_rooms.asm` files (never a glob — a leftover tree from
  another stage would reference shape labels that no longer exist), and
  `levels_index.asm` owns the FIRST window in source order (`spill_F307`)
  because it defines `LEVEL_FORMAT` + the `SHAPE_*` EQUs the room tables use.
  Net-new level data must never be added inside `level_00N_rooms_data.asm` —
  that file is invisible to the spill accounting.
- bank2's level-table windows are the six freed shape clusters plus `$F700`
  (`_SPILL_SLOTS` in `convert_level.py`, 2 323 B; bank2.asm carries the
  matching `.ds` pads). bank3's level data uses **TWO windows** (C12
  2026-10-21): extras (async streams + base table) at `$F010-$F44F` (1 088 B,
  `_BANK3_EXTRAS_SLOT`) and shapes (blocks + row pool + address table) at
  `$F5CC-$F8B6` (747 B, `_BANK3_SHAPES_SLOT`), each capacity-checked by
  `emit_spills`; the shape include list is `spill_bank3_shapes.asm`. The
  shapes window starts where `ERLoadDone` ends — do NOT lower the `.ds` target
  below `*` (DASM `Origin Reverse-indexed`; the old `$F5BF` figure was a stale
  binary measurement).
- The generator has a declared shape budget (`kShapeBudget` in
  `DataSerializer.cpp`, currently 56, two-pass: base library first, extra
  archetypes only if the base fits). `test_generator` gates the shape count,
  a >= 64 B slack floor in every window, and the hot-start drop column
  (HotDrop keeps row-1 cell 4 open).
- `emit_spills` slot starts must be the REAL bank2 include site: `spill_F767`
  begins at `$F700` (bank2 `.ds $F700 - *`), worth 103 B that the old
  `$F767` start hid.
- **Never add `n` twice to a 16-bit base with two `adc n`s**: the first carry
  is folded into the second add and lost when the second does not overflow, so
  `base + 2n` points one page low for some room counts (2026-10-20: level 14 of
  the 20-level stage read `EnemyCount=0`; fixed by computing `2n` with `asl`
  first in `EnterRoomB2` and `ExtrasLoad`). The legacy 4-level stage never hit
  the overflow, which is why it survived for so long — guard tests that walk
  every level of the live stage (`test_band_restage`).
- `resolve_asym_patches(model, room, left_rows)`; `room_door_flag` /
  `room_m1_door_flag` / `async_kinds(room)` replaced the model-level helpers.
  `room_extras()` (convert_level) is the single extras emitter; the loader and
  `verify_build` both re-derive its bytes from the JSON, so a drift is red.
- `RightPF0/1/2` + `RightRects` are GONE (no reader since C4) and
  `dedupe_room_blocks` is retired — there are no per-room blocks to dedupe;
  byte-identical MODELS are still emitted once each (the C3 row dictionary is
  the future fix for that).
- ROM-byte tests read FROZEN banks AND frozen labels (`src/tests/frozen/`) —
  never frozen bytes with live `src/bank2.lst` labels (that mismatch silently
  reads the wrong block; it bit `test_band_restage`, `test_bomb_strip` and
  `test_phase3_ball` on the day of the move).

## Critical Rule: Generator Hazard Placement — Phase Is Horizontal, Crunch Gaps Are Band 3

**The generator (`Build20LevelStage`) is the product; saved stages are
disposable output** (user 2026-10-27). Rules live in the generator plus a test
in `tools/test_generator.py`. Rooms/levels/models are counted from 1 when
talking to the user (the editor's "Model 32" is data `id` 31); bands may be
0-based, but say which.

- **Phase walls are HORIZONTAL obstacles only** (user 2026-10-27). The player
  walks or flies left/right across them; a blink is too short to fall or climb
  through. Any room with a SIDE link (corridor, L, T, +) can host one; the cell
  (`kPhaseCell`, data col 2, band 2) has WALL directly above and below it and
  band 2 is open from the side edge up to it. Phase rooms do NOT use
  `SHAPE_GATE` (that shape walls band 2 off and is for locked doors). A level
  with no side-linked host drops its phase. Guard: the phase check in
  `test_generator.py`.
- **hcrunch band follows the FIRST ENTRY (user 2026-10-28).** The generator
  does a BFS over the room grid from the start room (`FirstEntry`, vertical
  parent wins ties). First entered from the room ABOVE (falling, little time to
  react) -> crunch on **band 3** (row 2); from BELOW (climbing) -> **band 2**
  (row 1); from the SIDE -> no hcrunch (the room stays ordinary). Row 2 keeps its
  pair 0 solid (the room's only side link is on row 1); its ceiling is the
  middle band and its floor the cave floor, so only the floor gap can need
  widening. Data: `feature_cells` row 1/2; extras feature byte b4 = row 2; the
  `$82` record's y byte = the row (read by `PhHcrEntry` and the HOV handler).
  Touches: a 1 px vertical step that first overlaps the band (feet on its first
  line / head on its last) is a plain wall (land on it, bump it); any other
  overlap kills; a hot band stays deadly on every side. Guards:
  `test_hcrunch.py`, `test_generator.py`.
- **hcrunch needs a >= 4-cell gap above AND below the crunch band** (user
  2026-10-25/26). The crunch band is band 2: its ceiling is band 1 and its
  floor is **band 3**, NOT the cave floor (band 4). `wideBottom` (`SHAPE_WS`)
  opens band 3 as well as band 4. Checking `tiles[-10:]` / the last row was a
  leftover of the 3-row layout and let 2-cell gaps through (levels 17/19,
  found 2026-10-27). Guard: the hcrunch check in `test_generator.py`.
- **`test_generator.py` does not rebuild the editor** (`ensure_editor` only
  builds when the binary is missing): run
  `cmake --build tools/editor/cmake-build-debug` after any generator change, or
  the test measures the stale binary.
