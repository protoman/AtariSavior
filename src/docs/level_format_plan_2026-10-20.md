# Level format plan — 20 levels / 210–400 rooms

**2026-10-20, read-only design at HEAD (post-evac C3). This file is the only change.**
Measured from `bank0/1/2/3.lst`, `generated/*.asm`, `generated/symbols.asm`,
`tools/convert_level.py`, `tools/convert_room.py`, `tools/verify_build.py` and
`rooms/*.json`. Every number is **measured** unless marked **est.**

Goal (user): **20 levels, increasing room counts, up to 20 rooms in one level.**
Two targets are costed: **210 rooms** (1..20 progression) and **400 rooms** (20×20),
plus the worst case of a **unique model per room** (which is what the editor's
own `GenerateAll20DefaultLevels` emits).

## 0. Verdict up front

| | today's format | compact v2 (this doc) |
|---|---|---|
| bytes/room (all-in, today's density) | **25.6 B** (410 B / 16 rooms) | **≈8–9 B** |
| 210 rooms | 5.3 KB (3.8 KB with zero async, 7.5 KB unique models) | **1.9 KB** (2.2 KB at 1 enemy/room) |
| 400 rooms | 10.0 KB (7.2 KB zero async, 14.1 KB unique models) | **3.4 KB** (4.0 KB at 1 enemy/room, 4.5 KB unique models) |
| 210 rooms fits bank2 alone (1464 free)? | **no** (2.6× over) | **no** (needs the split) |
| 210 fits bank3 alone (4086, walkers there)? | **no** (5314 > 2221 data budget) | **yes** (1934 ≤ 2221) |
| 210 fits "bank2 enlarged by moving code out"? | **no** (only 187 B is movable) | **no** (needs the split) |
| 210 fits the two-bank split? | **no** (bank3 shapes 3 654 + 1 013 = 4 667 > 4 086) | **yes**, 1 736 / 2 133 free |
| 400 fits anywhere today? | **no** (min 7.2 KB, no placement) | **yes** (split: 848 / 1 523 free; even the unique-model + 1-enemy corner fits at 320 / 893 — §3.3) |

Two **hard caps** in the current format block the goal independently of size:
**≤15 rooms per level** (connection nibbles, `$F` = none) and **≤31 enemy
records per level** (`RoomEnemies` b5-1). Both are removed by the proposal.

Recommended sequence: **chunk 1 = grid-position connections** (lifts the 15-room
cap, halves the connection table, cold path only). Then room-record packing,
shape dictionary, cell-collision rect drop, async extras. §5.

---

## 1. Current format cost (measured)

### 1.1 The 410 B, itemised

`tools/rom_size_report.py --md` prints "index 28 + tables/blocks 216 + models
166"; the 216 splits as follows (byte counts from the generated files):

| item | L1 | L2 | L3 | L4 | total |
|---|---|---|---|---|---|
| rooms | 2 | 2 | 6 | 6 | **16** |
| level index (`levels.asm`, 7 B/level) | 7 | 7 | 7 | 7 | **28** |
| `RoomDataTable` (2 B/room, absolute word) | 4 | 4 | 12 | 12 | **32** |
| `RoomConnections` (2 B/room) | 4 | 4 | 12 | 12 | **32** |
| `RoomEnemies` (1 B/room) | 2 | 2 | 6 | 6 | **16** |
| `EnemyDataTable` (4 B/record; 2+1+6+0 records) | 8 | 4 | 24 | 0 | **36** |
| tables subtotal | 18 | 14 | 54 | 30 | **116** |
| per-room blocks (async rooms) | 19 | 0 | 0 | 81 | **100** |
| models (`models_data.asm`, 8 emitted) | | | | | **166** |
| **total** | | | | | **410** |

Note: the stage has **16 rooms** (2+2+6+6), not 18 — the brief's 18 is not what
`rooms/*.json` holds. `models.json` defines 12 models but only **8** are emitted
(`M1..M8`); models 9–12 are unreferenced. Enemy records: **9** (0.56/room).

### 1.2 Record cost formulas (measured from `generated/*.asm`)

A shape block (`M<id>` or `L<n>R<r>`) is emitted by
`convert_level.emit_room_block` → `convert_room.lines`:

```
shape block = 1 (nrect) + 2·nrect + 1 (hot count) + 5·hot + 9 (PF0/1/2 ×3 rows)
              + 2 (MetaA/MetaB)                        = 13 + 2·nrect + 5·hot
asymmetric room, additionally: +9 (RightPF rows) + 5 + 4·rrect (RightRects)
```

* models: 19 B (3 rects), 21 B (4), 25 B (6) → **166 B for 8 = 20.75 B/model**
* per-room blocks: L1R1 19, L4R2 24 (1 hcrunch feature), L4R5 17, L4R6 40
  (RightPF 9 + RightRects 14) → **100 B for 4 blocks = 25 B/block**
* level entry: 7 B (miner room, miner x, 2 wall colours, room-table word, n)
* room tables: **5 B/room** (2 ptr + 2 conn + 1 enemy meta) + **4 B/record**
* enemy record: 4 B `type, x, y, dir` (type ≤3 bits, dir 1 bit → 27 of 32 bits
  used)

### 1.3 Marginal bytes

| unit | bytes |
|---|---|
| marginal room (tables only, shares a model) | **5 B** + 4 B/enemy |
| marginal room that owns a block (async) | 5 + (13+2·nrect) = **17–25 B** |
| marginal enemy record | **4 B** |
| marginal model, if not shared | **19–25 B** (20.75 measured avg) |
| amortised model at today's reuse (2 rooms/model) | 10.4 B/room |
| **all-in today** | **25.6 B/room** |

### 1.4 Overhead and redundancy (each measured)

1. **Absolute pointer words — 32 B today, 2 B/room forever.** They carry only the
   *identity* of one of 8 distinct shapes; the address is `base + 3·index`.
2. **Connection bytes — 32 B today, 0 B of real information.** `connection_bytes()`
   *derives* up/down/left/right purely from `room_x`/`room_y` adjacency; the ROM
   stores the result of a computation that is already in the JSON. Worse, the
   nibble pack **caps a level at 15 rooms** (`nibble_room` raises >14; the readers
   compare against `$0f`). `bank2.asm:1635/1649/1660/1675`.
3. **Per-room blocks — 100 B (25 B/block).** Three of the four exist only because
   the room meta must sit at the fixed offset `TilePF0+9/+10` that
   `B3RoomBlocks` reads; the left PF of a *patch-only* async room is identical to
   its model's block.
4. **Duplicated PF rows — 50%.** 8 models × 3 rows = 24 row slots, **12 distinct**
   `(PF0,PF1,PF2)` triples. 36 of the 72 model PF bytes are repeats. The four
   per-room blocks add 12 more row slots that mostly repeat model rows.
5. **`RightPF0/1/2` + `RightRects` — 23 B (L4R6) have no reader.** `grep` over
   every `.asm` finds only the labels (`generated/level_004_blocks.asm:56`,
   `generated/bank3_labels.asm` — a stale snapshot). The D6 ball overlay and
   `PHMOverlay` replaced right-rect collision; the emission survived. Verify with
   `test_asym_data` before deleting.
6. **Always-zero hot-count byte — 11 B** (8 models + L1R1 + L4R5 + L4R6; L4R2 is
   the only non-zero). Round-3 audit already flagged it; it matters at 400 rooms
   (400 B) but not today.
7. **Enemy records 4 B for 27 bits**, and the per-room first-record pointer is
   redundant because records are already contiguous in room order (the converter
   emits them in room order) — deriving the index by summing counts removes the
   **31-record/level cap** as well.
8. **Level entry repeats the palette**: `wall_r/g/b` and `wall2_*` are sent as two
   `nearest_byte` colours (2 B/level) although the editor already indexes a
   `kLevelPalettes[20]` table (`DataSerializer.cpp:206`).

---

## 2. Capacity model

### 2.1 Scenarios (today's format)

Assumptions: 5 B/room tables, 4 B/enemy at 0.56 records/room, models shared 2
rooms/model at 20.75 B, async 28% of rooms at 25 B, 7 B/level.
"Zero async" and "unique model per room" are the measured bounds either side.

| scenario | 210 rooms | 400 rooms |
|---|---|---|
| today's density (2 rooms/model, 28% async) | **5 314 B** | **9 986 B** |
| zero async rooms (symmetric only) | 3 839 B | 7 186 B |
| unique model per room (`GenerateAll20DefaultLevels` style) | 7 493 B | 14 136 B |

### 2.2 Free space per placement (measured)

| placement | free for level data | note |
|---|---|---|
| (a) bank2, walkers in bank2 | **1 464 B** in 15 runs; largest runs 429 (`$F453`), 295 (`$F790`), 184, 88, 87, 84 | report-style ledger |
| (b) bank3, all level data + its walkers in bank3 | 4 086 − **1 865** walkers = **2 221 B** | walkers: `EnterRoomB2` 169, shape cluster 990, `moth` 262, LHT 87, blast 74, exits 94, `LoadLevelB2` 93, `LevelConnB2` 13, tables (ColOff/ColMask, OvHead/Tail, enemy bits) 53, pads/ReturnPad ~30 (LWC 184 stays in bank2 — it reads ZP buffers only) |
| (c) bank2 enlarged by moving code out | **1 464 + 187 = 1 651 B** | only `B3StageBand` (187) is data-free enough to leave; the rest of the shape cluster reads the block stream, and moth/LHT/blast read the enemy records — they cannot leave without their data |
| (d) two-bank split: rooms+enemies+their walkers in bank2, shapes + their walkers in bank3 | bank2 **1 464** (rooms/enemies), bank3 4 086 − 1 013 (boot 11 + shape cluster 990 + pads 12) = **3 073 B** (shapes) | the pre-evac-C2 layout; the split is a *revert of C2/C3 for the shape subset*, already scripted in `evac_plan_2026-10-20.md` |

### 2.3 Fit verdict, today's format

| placement | 210 rooms | 400 rooms |
|---|---|---|
| (a) bank2 alone | **NO** — 3 839 minimum vs 1 464 (2.6×); and no 700 B contiguous run exists | **NO** |
| (b) bank3 alone | **NO** — 3 839 vs 2 221 (1 618 over) | **NO** — 7 186 vs 2 221 |
| (c) enlarged bank2 | **NO** — 3 839 vs 1 651 | **NO** |
| (d) split | **NO with today's async mix** (shapes 2 179 + async 1 475 = 3 654 + 990 walkers + 23 boot/pads = 4 667 > 4 086; 571 over). **YES only with zero async rooms** (2 179 + 1 013 = 3 192; bank2 1 660 needs +226, easily met) | **NO** — shapes 4 150 + 2 800 + 1 013 = 7 963 |

**Conclusion: today's format cannot reach the goal.** 210 rooms need a
symmetric-only stage and both banks; 400 rooms have no placement at all.

---

## 3. Compact format proposal — `LEVEL_FORMAT = 2`

Design constraints kept: `room_x/room_y/model_id` in the JSON (no stage edits),
room entry is a cold path (all derivation allowed there), the meta is consumed
**only at room load** (not per frame — verified: `B3RoomBlocks` copies PF into
`PF0Buf` and stages `MetaA/B` into `$99/$9A`; the kernel reads only ZP), and
`LevelDataTable` stays at `$F700` (`LEVEL_DATA_ADDR`).

### 3.1 Records

**Level entry, 6 B** (was 7): miner room, miner x, palette index, n rooms,
room-table word. Colours come from a shared 20×2 B palette table (40 B).

**Room record, 3 B** (was 5):

```
+0  shape index  b5-0 (≤63 shapes per level)   b6 band flag   b7 owns-extras
+1  grid position (x<<4 | y)  -- replaces RoomConnections entirely
+2  enemy count b7-6 (0-3)     extras index b5-0 (0 = none)
```

* Connections become **derived**: an exit scans the level's 1-byte position
  column for `(x,y∓1)` / `(x∓1,y)` — ≤20 iterations, ~5c each, cold path, no
  per-frame cost. This also removes the 15-room cap (grid 16×16 = 256 cells).
* The **first enemy record index is derived** by summing counts of rooms `0..n-1`
  (records stay contiguous in room order, as the converter already emits them).
  Removes the 31-record/level cap.
* `b7` selects an entry in the level's **extras stream** (async patches / feature
  cells), so a symmetric room pays nothing for them.

**Extras record (async rooms only), 4–7 B (5 B typical):**

```
+0  flags: n_patches b3-2, n_features b5-4, feature kind b7-6, reserved b1-0
+1..    2 B MetaA/MetaB (the bytes that lived at TilePF0+9/+10)
        1 B/patch:  row b7-6 | side b4 | col b3-0   (tile is always wall)
        1 B/feature: kind b7-6 | col b3-0           (row is always 1)
```

A patch-only room therefore costs **4–6 B** where today it costs a 17–25 B block.
A feature-cell room costs 5–7 B *plus* the left-PF cells it turns solid — the
loader sets those PF bits from the column list (the P/C cells are solid in the
left half: `convert_room.py:73`), so the 9 B PF repeat disappears. Non-async
rooms carry **no** meta: `MetaA = 0` and `MetaB`'s hot bit is already implied by
the shape's hot count.

**Shape (model) record, 3 B + dictionary**

```
shape: 3 B = row index for band 0, 1, 2   (1 B each, index into the row pool)
row pool entry: 3 B = PF0, PF1, PF2 for one band
```

* Measured redundancy today: 12 distinct rows for 24 row slots (50%). The pool is
  global and saturates; 40–90 entries (120–270 B) cover a full game.
* The meta leaves the block, which is what finally kills the `TilePF0+9/+10`
  contract — a **deliberate migration** (§3.4).
* Hot rects keep their separate stream (1 B count + 5 B/record) — hot is a
  behaviour, not derivable from PF.
* **Solid rect lists are dropped** (see §4): the PF buffers *are* the collision
  map once `cell_collision_plan` phases 5.1b/7.1 land.

**Enemy record, 3 B** (was 4): `type<<1|dir`, `x`, `y`.

### 3.2 Byte estimates

| item | 210 rooms (105 shapes, 59 async, 118 records) | 400 rooms (200 shapes, 112 async, 224 records) |
|---|---|---|
| level entries 6 B × 20 | 120 | 120 |
| palette table | 40 | 40 |
| room records 3 B | 630 | 1 200 |
| extras (5 B/async room) | 295 | 560 |
| enemy records 3 B | 354 | 672 |
| shape records 3 B | 315 | 600 |
| row pool (60 / 80 entries × 3) | 180 | 240 |
| **total** | **1 934 B** | **3 432 B** |

Sensitivities (est.): 1 enemy/room → +276 / +528; unique model per room
(210 / 400 shapes) → +315 / +600 and a larger row pool (+90 / +180);
no row dictionary (9 B/model) → +630 / +1 350. Worst realistic 400-room case
(unique models, 1 enemy/room): **4 590 B ≈ 4.5 KB**.

### 3.3 Placement verdicts, compact v2

Split ownership (the natural one — the extras are applied by the block reader,
which lives with the shapes): **bank2 = room records + enemy records + their
walkers; bank3 = level entries + palette + shape records + row pool + extras +
the 990 B shape cluster + boot/pads (1 013 B)**.

| placement | 210 rooms | 400 rooms |
|---|---|---|
| (a) bank2 alone (1 464) | **NO** — 1 934 vs 1 464 (470 over) | **NO** |
| (b) bank3 alone (2 221 for data) | **YES** — 1 934, 287 free | **NO** — 3 432 vs 2 221 (1 211 over) |
| (c) enlarged bank2 (1 651) | **NO** — 283 over | **NO** |
| (d) split | **YES** — bank2 rooms 630 + records 354 = 984 → **1 736 free**; bank3 120 + 40 + 315 + 180 + 295 + 1 013 = 1 963 → **2 133 free** | **YES** — bank2 1 200 + 672 = 1 872 → **848 free**; bank3 120 + 40 + 600 + 240 + 560 + 1 013 = 2 573 → **1 523 free** |

Split capacities: bank2 available = 4 096 − 1 376 non-shape usage = **2 720 B**;
bank3 available = 4 096 − 1 013 = **3 083 B**.

The worst realistic 400 case (unique models, 1 enemy/room) still fits:
bank2 1 200 + 1 200 = 2 400 (**320 free**), bank3 120 + 40 + 1 200 + 270 + 560 +
1 013 = 3 203 (**893 free**). No second split and no extra moves are needed —
which is the reason the extras/entries live in bank3 rather than bank2.


The split is a *revert of evac C2/C3 for the shape subset only* (models, blocks,
`B3RoomBlocks`, `PhaseBlink/BuildColupF/BCFDarkRun`, `HotOverlapBody`,
`B3StageBand`, `PhHcrEntry/CrPfx/HcrClock`, `HOVFeatEntry` = 990 B + data), and
`evac_plan_2026-10-20.md` already documents every file/pad/test that touches it.

### 3.4 Reader / converter changes and the meta contract

**Contract migration (proposed, not silent):** `TilePF0+9/+10` dies. `MetaA/MetaB`
move into the **extras record** (2 B per async room — non-async rooms derive
`MetaA = 0` and the hot bit from the shape) and `B3RoomBlocks` stages them from
there; `StageBandTab`/`B3StageBand` already read the *staged* bytes
(`RoomMetaA/B` = `$99/$9A`), so only the staging source changes. This is what
removes the per-room block class. If the contract must stay, keep the block for
feature-cell rooms only — costs ~+9 B per such room and keeps the block reader
for both paths.

**Converter** (`tools/convert_level.py`, `tools/convert_room.py`):

| function | change |
|---|---|
| `connection_bytes()` | replaced by `position_bytes()` — emit `room_x<<4|room_y` (already in JSON) |
| `write_tables()` | 3 B room records; drop the pointer word; level entry 6 B + palette index |
| `_enemy_tables()` | 3 B records, no stored first index (assert drops from ≤31 to ≤63) |
| `emit_room_block()` | async-only path: extras bytes; shape path: 3 row indices |
| `dedupe_room_blocks()` | retired (no per-room blocks to dedupe) |
| `write_levels_index()` | `LEVEL_FORMAT = 2`, palette table, new strides |
| `emit_spills()` / `_BLOCK_SLOT` | new slot map (room tables vs shapes) |
| `_gen_data_size()` | unchanged |

**Reader** (bank2 unless noted):

| routine | change | est. bytes |
|---|---|---|
| `EnterRoomB2` | 3 B record decode; shape → block address = `shapeBase + 3·index`; enemy first-record = cumulative sum loop | +40 / −10 |
| `LevelConnB2` + 4 exit handlers | scan the position column instead of masking a nibble | +35 |
| `B3RoomBlocks` | 3 row-pool lookups instead of one 9 B copy; meta from the extras record; rect copy deleted (§4) | −10 |
| `LoadLevelB2` | 6 B stride (×6: `asl / asl / asl − Level*2`), palette lookup | +6 |

All of it is cold path (room entry / level load). **No kernel/VBL/overscan
cycle change**, so `sim_frame_budget` and `sim_bomb_fuse` stay untouched.

---

## 4. 6-rect models (5/6) versus the 5-rect cache

Facts (measured): models 5 and 6 emit **6** rect pairs; `B3RoomBlocks` clamps the
cache copy to 5 (`cmp #6 / lda #5`), so rect 5 is lost and the walk sees a phantom
cell from `$E0+`. `verify_build.check_model_rects` only WARNs (downgraded in
`cell_collision_plan` 1.2). Phases 2.1 (PHM), 3.1 (LWC) and 4.1 (moth) are
already **cell-based**; bombs (`BombMarkWalls`) and the `EnterRoom` rect copy are
not.

| option | code | RAM | data | risk | verdict |
|---|---|---|---|---|---|
| **A. finish cell collision** (`cell_collision_plan` 5.1b cell punch + 7.1 stop emitting rects) | +20…40 B (bank1 punch), −25 B (`B3RoomBlocks` rect copy), −`ABWY/ABWHTab` | **−20 B ZP** (rect cache `$CC-$DF` freed) | **−2 B/rect** everywhere: −62 B today; **−3.9 KB at 400 unique models** | med (bomb score/hole path; own Stella gate) | **RECOMMENDED** |
| B. extend the cache to 6 | +4 B (clamp 6→7, slot) | **+4 B ZP — none free** (`$80-$BB` full, `$BD+` explicit EQUs → every hand-copied bank1/bank2 EQU shifts) | 0 (rects still emitted) | **high** (ZP shuffle vs `check_equ_sync` + stomp zone) | reject |
| C. split models 5/6 into ≤5-rect models | 0 | 0 | content change, duplicates rooms | low but wrong | reject (does not generalise to 20 levels of new models) |
| D. 6th rect via a cell-swap table | +~25 B per walker consumer | 0 | +2–4 B/model | med | reject — this is option A's work, but partial: cell tests are what a swap table would emulate |

**Recommendation: A.** It is the only option that fixes the geometry *and* pays
for the 20-level budget. The data argument is decisive: at 400 rooms with one
model each, solid rect lists are **≈3.9 KB** of the ≈5.7 KB shape cost (400
models × (2 + 2·3.875 rect bytes)); with the cell walkers landed, the PF triple
already encodes the same information. There is no new RAM: the 20 B cache is
released, which is also the only way to gain ZP without shifting the hand-copied
EQU map.

Ordering note: A is **independent** of the format chunks and can land before,
between, or after them — but the compact byte estimates in §3 assume it. If A is
deferred, add 2 B/rect to every shape (210 rooms: +~350 B; 400: +~1.5 KB), which
still fits the split.

---

## 5. Migration and ordered chunks

### 5.1 Migration (converter-side, no `src/rooms` edits)

* `src/rooms/**`, `models.json` and `src/generated/**` are the user's stage and are
  **not touched**. Format v2 is fully derivable from today's JSON
  (`room_x`, `room_y`, `model_id`, `asym_patches`, `feature_cells`, `enemies`,
  `lamps`, palette colours) — so migration is `./build.sh` / `convert_level.py`.
* **Version guard** (the repo's "explicit version/default" rule): `levels.asm`
  emits `LEVEL_FORMAT = 2` and the new strides; `bank2.asm` carries a hand copy;
  `verify_build.check_equ_sync` asserts the pair, and `verify_build` hard-fails
  the room-record shape (stride, `n ≤ 63`, enemy sum ≤ 63) so a stale `generated/`
  tree cannot be silently misread. Rollback = revert commit + rebuild (generated is
  derived); no data migration back is needed.
* Optional-key default already exists for `asym_patches`/`feature_cells`
  (`DataSerializer.cpp` loads them in a try/catch) — old JSON keeps working.

### 5.2 Chunks (each independently green)

Build + both sims + battery + re-freeze before each commit; each chunk leaves the
stage playable.

### C1 — grid-position connections — **LANDED 2026-10-20** (see the C1 entry
in `docs/compaction_findings_2026-10-19.md`)
Replace `RoomConnections` (2 B/room, nibble, **≤15 rooms**) with a 1 B
`(x<<4|y)` position byte and resolve exits by scanning it. Files:
`convert_level.py` (`position_bytes`, `write_tables`), `bank2.asm` (shared
`ExitDirB2` + `ExitScanB2` + 4 stubs), `verify_build` (`check_level_format`,
`check_exit_handlers`), `test_band_restage`, `test_level_bank` (record shape),
new `test_grid_conn`. Delta measured: **−1 B/room** (level data 410 → 394 B,
bank2 free +27 B), zero frame cost. **Cap: 225 cells (15×15), not 256** — the
nibble-15 value is kept as the off-grid sentinel, which removes every
boundary guard from the exit scan and caps a level at 225 rooms (≥ 20 target).
Gate: `test_grid_conn` converts a 20-room level and drives the frozen handlers
for every (room, direction); `test_band_restage` still drives real `EnterRoom`
per room of the live stage.

**C2 — 3 B room record (shape index + derived enemy base) — LANDED 2026-10-20**
(see the C2 entry in `docs/compaction_findings_2026-10-19.md`; the record is
three 1 B columns, `LEVEL_FORMAT = 3`; level data 394 → 402 B because the
2 B/block address table is +24 B at today's 12-blocks/16-rooms density).
Drop the 2 B absolute word → 1 B shape index into a fixed 3 B shape table;
derive the first enemy record from the count sum (removes the 31-record cap).
Files: `EnterRoomB2`, `B3RoomBlocks` (shape base), converter (`write_tables`,
`_enemy_tables`), `test_level_bank`, frozen banks. Delta: **−1 B/room** (the
record is 4 B after C1) → 210: −210 B; 400: −400 B. Risk: medium — room load and
enemy staging.

**C3 — shape dictionary (row triples) — LANDED 2026-10-20** (was measured-only
at the 36 B gate; the gate was waived by user direction — it is the
foundation for the 20-level content generator, worth −540 B at 105 shapes).
A shape block is now `hot count | 5 B/record | 3 row-pool indices`
(`LEVEL_FORMAT = 5`); the global pool is 3 SoA columns (`RowPoolPF0/1/2`,
3 B per DISTINCT row) emitted once in `models_data.asm` (bank2's level-data
block slot) with `LEVEL_ROW_COUNT`. `B3RoomBlocks` expands the 3 indices
through the pool into `PF0Buf` at room load. Measured: models **110 → 80 B**
(11 shapes × 4 B = 44 + 12 pool entries × 3 B = 36), level data
**277 → 247 B (−30)**, bank2 code **+6 B** (assembled loader: $35 → $3B),
bank2 used **2920 → 2896 (−24)**, total free **7192 → 7216 (+24)**. PF parity
is structural and now asserted three ways (converter expansion assert,
`test_band_restage`'s loaded-`PF0Buf` equality for all 16 live rooms,
`test_cell_map`'s pool↔geometry parity). M10/M11 were left as two (identical,
4 B) blocks: aliasing them now saves 4 B and would delete the
`M11RoomRects`/`M11Rows` labels that the per-model label lookups in the ROM
tests resolve — needs an alias map first, so it belongs with a later chunk.

**C4 — cell collision completion (the 6-rect fix, §4 option A) — LANDED
2026-10-20.** `BombMarkWalls` is a cell punch (PF buffers, thin cell =
solid + empty neighbours); the converter no longer emits solid rects; the
`B3RoomBlocks` cache copy is deleted; `check_model_rects` is retired (models
5/6 stop warning). Hot records keep their 5 B stream (behaviour); their
mask byte is zero/nonzero only (M1 strip vs PF-cell parent gate).
**Measured delta: level data 402 → 308 B (−94 B: models 166 → 96 = the
rect bytes + count, per-room blocks 184 → 160, plus two room blocks that
became byte-identical and deduped); ZP $CC-$DF (20 B) freed, $89 kept
allocated as a spare.** At 400 unique
models the removed lists are ≈ −3.9 KB (est.). Gates: both sims, the full
battery, `sim_bomb_fuse`'s new thin-cell punch probe, `test_bomb_half_wall`
(user bugs #10), and `test_cell_map`'s per-cell 6-rect solidity sweep.

**C5 — async extras (retire per-room blocks) + meta migration — LANDED 2026-10-20.**
Patches/feature-cells/meta ride the level's `AsyncExtras` stream; the loader
(`bank2.ExtrasLoad`, tail-entered from `B3RoomBlocks`) applies them, so an async
room points at its shared MODEL shape and `TilePF0+9/+10` is retired. Measured:
level data **308 → 277 B** (index 52→50, tables/blocks 160→117, models 96→110
because M0/M10/M11 are now referenced shapes too), per-room marginal for a
symmetric room unchanged (**3 B tables + 4 B/enemy**), an async room now **+3 B
record + 3–10 B extras** instead of a 12–35 B block (patch-only 4–5 B, hcrunch
feature 10 B inc. its hot stream), and `RightPF/RightRects` (23 B in L4R6) is
gone. bank2 code +342 B (the extras loader), total free 7603 → 7292 B.
Gates: `test_band_restage` (all 16 live rooms: PF + staged meta byte-identical
through real `EnterRoom`, feature rooms repointing the hot stream),
`test_extras_room` (test-owned level block driven through the real loader:
plain/patch/feature/hot-shape + the ordinal walk), `test_asym_data` (shape has
no meta/right sections; extras bytes), `test_level_bank`/`verify_build`
(format 4, record structure, JSON-derived extras bytes), plus the full battery.

**C6 — 20-level plumbing (small but mandatory).**
`LEVEL_COUNT` 4 → 20 (3 hand copies: `kernel.asm:2341`, `bank1.asm:101`,
`generated`), title level number as packed BCD (`kernel.asm:3245` warns
`LEVEL_COUNT ≤ 9` — the title writes `ScoreTe = Level+1` in binary),
palette table + 6 B level entry, `test_level_bank`, and the doc/ledger.
Delta: −1 B/level + 40 B palette. Risk: low.

**C7 — split placement: the LEVEL-DATA SUBSYSTEM lives in two banks — LANDED
2026-10-20.** (Was "optional"; user goal = a generated 20-level stage, and the
measured 210-room shape does not fit bank2's 1 200 B of free windows.) Full
design + measurements in §7.1. Short form:

* **bank2 keeps the ROOM half**: `LevelDataTable` (level entries), the
  per-level table block (`RoomShapes` / `RoomPositions` / `RoomCounts` + the
  flat `EnemyDataTable`) and every walker that reads THOSE —
  `EnterRoomB2`, `ExitScanB2`/`ExitDirB2` + the four exit bodies,
  `LoadLevelB2`, `MothRoutine`, `LaserWallClamp`/`LaserHitTestBody`,
  `BombEnemyBlastBody`. All reads stay `lda (FetchPtr),Y` in-bank.
* **bank3 takes the SHAPE half back**: the shape blocks + the global row pool
  + `LEVEL_ShapeTable` + the async extras streams (+ their `LevExtrasLo/Hi`
  base table) and the walkers that read them — `B3RoomBlocks`/`ExtrasLoad`,
  `PhaseBlink`/`BuildColupF`/`BCFDarkRun`, `HotOverlapBody` (+
  `HOVHotPfGate`, `HOVFeatEntry`), `B3StageBand`, `PhHcrEntry`/`CrPfx`/
  `HcrClock`. The extras MUST travel with the shapes: a feature room's hot
  stream sits inside its extras record and `PhaseBlink`/`BuildColupF` walk it
  every VBL — record walkers and records share a bank (a fold there would cost
  25c/byte on the VBL path).
* **One cross-bank call in the whole room load**: bank2 executes
  `sta $1FF9` at `$F450` and bank3's `B3RoomBlocks` is pinned at `$F453` (the
  +3 fetch). No return pad and no twin bytes: the shape step runs LAST, so the
  bank3 chain ends in **bank3's own `ReturnPad`** (`$FBF8`) — 0 extra pushes.
  Guard: `verify_build.check_bank3_entry`.
* `EnterRoomB2` order is now: shapes byte (→ `RoomPF0Lo`, band flag) → enemy
  counts/records/`LoadEnemyRam` → stage the owns-extras ordinal in
  `LevelConnSpare` → `jmp ERBlocksPad` → bank3 PF + meta + extras →
  `ERLoadDone` (joystick-shadow refresh) → `ReturnPad`.
* Converter: `LEVEL_ShapeTable` moved into `models_data.asm`; each level's
  extras stream is its own `level_00N_extras.asm` plus `levels_extras.asm`
  (per-level base table indexed by `Level`); `spill_bank3.asm` is bank3's data
  include list, capacity-checked against `_BANK3_DATA_SLOT` ($F010-$F44F,
  1 088 B). bank2's six freed windows became `_SPILL_SLOTS` (2 323 B total)
  and `levels_index.asm` owns the first one in source order (`spill_F307`,
  because it defines `LEVEL_FORMAT` + the `SHAPE_*` EQUs the room tables use).

**Ledger note:** after each chunk run `tools/rom_size_report.py --md` and paste
the table (§7) into this file.

### 5.3 Test / guard checklist (measured file names)

`tools/test_level_bank.py` (LEVEL_COUNT + `LEVEL_DATA_ADDR` + fold),
`test_band_restage.py` (live JSON ↔ real `EnterRoom`), `test_features_data.py`,
`test_asym_data.py`, `test_cell_map.py`, `test_editor_roundtrip.py`
(`NON_CONVERT` file set), `test_bomb_*` / `test_laser_*` (frozen banks),
`verify_build.py` (`check_level_window`, `bank2_data_slots`,
`check_level_window` precheck, `check_equ_sync`, `check_model_rects`,
`LEVEL_DATA_ADDR` sync), `tools/freeze_test_banks.sh`, and `sim_frame_budget` /
`sim_bomb_fuse` (should not move: no kernel/cycle change in C1–C3, C5, C6).

Content limits that 20 levels surface (not ROM capacity, but must be decided):

| limit | where | effect at 20 levels |
|---|---|---|
| dark rooms only 0–7 | `bank1.asm IsRoomDark`: rooms 8+ never dark | rooms above 8 cannot be dark rooms |
| `LEVEL_COUNT ≤ 9` | `kernel.asm:3245` title `ScoreTe` binary write | level 10+ shows a wrong glyph until C6 |
| 3 enemies/room, 2 objects/room | `MAX_ENEMIES = 3`, editor cap | unchanged |
| `Level*7` byte offset | `LoadLevelB2` (max 36 levels) | fine for 20 |
| editor generator makes 2..8 rooms/level, one model per room | `DataSerializer.cpp:257` `numRooms = 2 + l/2`, capped 8 → **124 rooms total** | must be updated to 1..20 (210) and allowed the shared shape pool |

---

## 6. Risks

1. **The split (C7) is a revert of evac C2/C3 for the shape subset.** It is the
   only placement that fits 400 rooms. If the team prefers not to move anything,
   the honest ceiling is ~180 rooms in bank2 (1 464 / ≈8 B/room) — not the goal.
2. **The row pool is the only estimate with real variance.** It is bounded by 3 B
   per distinct row and saturates (12 distinct for today's 8 models). A pathological
   stage with 150 distinct rows costs 450 B — still less than the 9 B/model it
   replaces once there are >25 models.
3. **C5 changes a documented contract** (`TilePF0+9/+10`). Do it as its own chunk,
   with `bank2.StageBandTab`'s reader and `test_cell_map` parity before/after.
4. **Variable-length extras + fixed 3 B records** is deliberate: fixed records keep
   `shape = base + 3·index` and the enemy sum loop trivial. Do not "optimise" into
   variable room records; it would reintroduce a scan on every room load.
5. **Never author 20 rooms into the current format** — the converter raises at
   room index 15, and a level with >31 enemy records overflows the b5-1 index.

## 7. Size ledger (measured at this HEAD — post C7)

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3027 | 370 | 681 | 3397 | 699 |
| bank1 | 2416 | 449 | 1037 | 2865 | 1231 |
| bank2 | 1270 | 193 | 2632 | 1463 | 2633 |
| bank3 | 1205 | 237 | 2649 | 1442 | 2654 |
| **total** | **7918** | **1249** | **6999** | **9167** | **7217** |

C7 delta vs post-C3 (bank2 2 896 used / 1 200 free, bank3 10 / 4 086, total
free 7 216): **bank2 −1 433 used, bank3 +1 432 used, total free +1 B.** The
move is a wash on the 16K budget (the duplicated `ColOff`/`ColMask` 40 B and
the bank3 `ReturnPad`/`ERLoadDone` ~15 B pay for the deleted bank2 pads).

Level data **247 B** = index 28 + tables/blocks/extras 117 + models 102. The
models line is now `11 shapes × 4 B + 12 pool rows × 3 B = 80` **plus the
22 B `LEVEL_ShapeTable`** that left `levels_index.asm` (which dropped 50 → 28):
the total is unchanged, and the shape half is entirely bank3's.
Bank2's table windows (2 323 B capacity, 8 slots): live stage uses 112 B;
`levels_index` sits in `$F307` (first in source order — it defines the EQUs),
the per-level tables in the other seven.
Bank3: code 1 205 B, data 237 B; its `$F010-$F44F` data window holds
models_data + levels_extras (live: 135/1 088 B).
Re-measure with `tools/rom_size_report.py --md` after any change.

### 7.1 C7 capacity proof — a generated 210-room stage fits

Synthetic, test-owned stage (temp dir; never `src/rooms`): 20 levels,
level *n* has *n* rooms (**210 rooms**), 1 enemy/room, 12 recycled shapes.
Built with `STAGE_FILE=<tmp>/stage.json` (`build.sh`'s documented override),
`SIM_PY=/bin/false` (the sims probe LIVE room content — same rule the
`qa_build.sh` / `raft_build.sh` staged builds use; the live build keeps both
sims green, see the gates below).

| measurement | 210 rooms | capacity |
|---|---|---|
| level tables in bank2 (`levels_index` 140 + 20 table files 1 470) | **1 610 B** | 2 323 B in 8 slots → **slack 713 B** |
| bank3 data window (models 108 + extras base table 40) | **148 B** | 1 088 B → **slack 940 B** |
| level data total (`rom_size_report`) | **1 718 B** | (was 247 B for 16 rooms) |
| bank2 | 2 961 used / **1 135 free** | report-style |
| bank3 | 1 451 used / **2 645 free** | report-style |
| total ROM | 10 674 used / **5 710 free** | of 16 384 |

Placement map for the 210-room tree (precheck, all slots green):
`$F307` 329/329 (index + 6 level files), `$F453` 427/429, `$F700` 336/340,
`$F8B7` 21/290, `$F9D9` 497/503, `$FCB8` 0/207, `$FE9C` 0/84,
`$FF59` 0/141. The tightest slot has 0 B left, so the next ~40 rooms would
want the three still-empty slots ($FCB8/$FF59/$FE9C, 432 B) — the placement
list is greedy first-fit, so it starts using them automatically.
`verify_build` is green on that tree (`LEVEL_COUNT` self-heals 4 → 20), and
DASM emits exactly 4 × 4 096 B.

Not changed by C7: `LEVEL_FORMAT 5` (3 B room records, C3 row dictionary, C5
extras stream), the room-load call chain depth (0 new pushes — the split is
two tail jumps), and every per-frame path (the VBL/overscan clusters only
gained a bank byte: `sim_frame_budget` cave 267 / title 265 unchanged).


## 8. Measurement appendix

* Per-file byte counts: `.byte`/`.word` operand counts in `generated/level_00N_rooms.asm`,
  `level_00N_blocks.asm`, `levels.asm`, `models_data.asm`.
* Shape formula: 13 + 2·nrect + 5·hot, checked against every emitted block
  (M1 19, M4 21, M5/M6 25, L1R1 19, L4R2 24, L4R5 17, L4R6 40 → 166 + 100).
* Room/record costs: `bank2.asm` `EnterRoomB2` (room word, enemy byte, `RoomEnemies
  = base+4n`, records `= base+5n`), `LevelConnB2`/exits (nibble masks),
  `_enemy_tables` (4 B stride, ≤31 assert), `convert_level.nibble_room` (≤14).
* Bank occupancy: `tools/rom_size_report.py --md` + a `.lst` emitted-byte scan
  for the free runs (`.ds` counts as free; DASM's row-span attribution adds
  119–201 B of phantom "used" to bank2/3 — not budgeted).
* Walkers in (b)/(d): `evac_plan_2026-10-20.md` §3.1/§3.2 measured cluster sizes
  (R1a 357, R1b 152, R2 114, R3 187, R4 117, R5 63 = 990; plus `EnterRoomB2` 169,
  moth 262, LWC 184, LHT 87, blast 74, exits 94, `LoadLevelB2` 93, tables 60).
* Meta is load-time only: `bank2.asm` `B3RoomBlocks` (`.EBpf` 9-byte copy into
  `PF0Buf`, MetaA/B at Y=9/10 staged to `$99/$9A`).
* `RightPF`/`RightRects` have no reader: `grep -rn "RightPF0\|RightRects" --include=*.asm`
  finds only `generated/*_blocks.asm` labels and the stale `generated/bank3_labels.asm`.
* Cycle/capacity claims about the kernel are cited from `sim_frame_budget`
  (cave 267.0 / title 265.0) and the audits' VBL/overscan margins (VBL 1311/1472c,
  overscan 2104/3200c); not re-simulated here (read-only design).

---

## G12 (2026-10-21) — the 3 B enemy record, landed (supersedes §1.2/§1.3's 4 B)

The long-deferred "3 B enemy" is in. `ENEMY_STRIDE` 4 → **3**:

```
byte 0  type (b3-0) | dir (b7: 1 = left)   ← dir's separate byte is gone
byte 1  x   (full-stage display column -> px, 4 px/col)
byte 2  y   (room row -> scanline, 12 px/row; needs all 8 bits, max 132)
```

`range_min`/`range_max` stay out of ROM (nothing reads them; S4.1), and the
bit budget is 4 + 1 + 8 + 8 = 21 of 24. The editor JSON is unchanged — the
converter packs, so no data migration is needed.

### Readers (all of them)

| reader | change |
|---|---|
| bank2 `EnterRoomB2` record base | `4·idx` → `3·idx` (`asl` + `adc idx`, carry kept into the base add) |
| bank2 `EBLER_Loop` | reads the packed byte once into `Temp`, `and #$0F` for the type, `eor #$80` for the snake invert; `iny` x/y offsets unchanged (+1/+2) |
| kernel + bank2 `EnemyOffTable` | `0,4,8` → `0,3,6` in BOTH hand-copied tables |
| kernel `UpdateEnemies` / `DeriveEnemyY` / `CheckEnemyHit` / `SelectActiveObject` | offsets only (`EnemyOffTable`), +1/+2 iny reads unchanged |
| bank2 `MothRoutine`, `LaserTipEnemy`, `LaserHitTestBody`, `BombEnemyBlastBody` | type via `EnemyOffTable` (stride table), +1 spawn-x iny unchanged |

The snake's authored dir semantics are untouched: the loader still inverts the
live bit (authored dir = where it comes OUT), now by flipping b7.

### Measured (20-level live stage, 211 rooms, 299 enemy/object records)

| | before (24fc7e5) | after | delta |
|---|---|---|---|
| level data total | **3 012 B** | **2 713 B** | **−299 B** |
| — index (20 × 7) | 140 | 140 | 0 |
| — tables/blocks/extras | 2 400 | 2 101 | −299 |
| — models (shapes + row pool) | 472 | 472 | 0 |
| bank2 code / data / used / free | 1 268 / 2 050 / 3 318 / 778 | 1 273 / 1 751 / 3 024 / 1 072 | +5 / −299 / −294 / +294 |
| bank3 (unchanged) | 1 136 / 1 177 / 2 313 / 1 783 | same | 0 |
| total used / free | 11 917 / 4 467 | 11 623 / 4 761 | −294 / +294 |

The 5 code bytes are the loader's mask/invert (`and #$0F`, `eor #$80`,
`sta Temp`), paid from the freed data.

### Guards

`verify_build.check_level_format` now hard-fails: (a) an enemy record line that
is not exactly 3 values (the retired 4 B `type,x,y,dir`), (b) a record count
that disagrees with the RoomCounts column, (c) a type byte with b6-4 set,
(d) either `EnemyOffTable` literal ≠ `0,3,6`, (e) a recorded base that is not
the `asl` + `adc LevelConnSpare` 3·idx idiom, (f) an `EBLER` that does not mask
the type with `and #$0F`. `test_level_bank` re-checks the emitted record
lengths + types, `test_enemy_movement` drives the REAL frozen `EBLER_Loop` over
3 B fixtures and pins both stride tables plus the 3·idx base math.

### Note on the earlier "skip"

`compaction_findings_2026-10-19.md` §"Level-data micro-pack" item (c) skipped
this at **9 B data / ~5 B net** — that estimate was taken on the 4-level,
16-room, 9-record stage. At the 20-level stage the same change is **299 B**:
enemy records are the one per-record cost that scales with content, so the
decision flipped with the stage.

## 7.2 C11+C12 ledger (measured 2026-10-21, `tools/rom_size_report.py --md`)

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3051 | 370 | 657 | 3421 | 675 |
| bank1 | 2416 | 449 | 1037 | 2865 | 1231 |
| bank2 | 1273 | 1751 | 1071 | 3024 | 1072 |
| bank3 | 1174 | 1032 | 1885 | 2206 | 1890 |
| **total** | **7914** | **3602** | **4650** | **11516** | **4868** |

Level data **2567 B** = index 140 + tables/blocks/extras 2105 + models 322.

C11 removed the per-shape hot stream (a shape block is 3 row-pool indices;
hot death derives from the PF row 1), taking level data 2713 -> 2567 B and the
bank3 data window from 5 B to 205 B of slack. C12 then split that window:

| window | address | size | live | slack |
|---|---|---|---|---|
| extras (async streams + base table) | `$F010-$F44F` | 1088 B | 615 B | 473 B |
| shapes (blocks + row pool + table) | `$F5CC-$F8B6` | 747 B | 322 B | 425 B |

The split point is `ERLoadDone`'s end (`$F5CC`); the old `$F5BF` figure was a
stale binary measurement and a `.ds` target below `*` is a DASM
`Origin Reverse-indexed` error. Both halves are read in-bank by
`B3RoomBlocks`, so the split costs no tramp and no per-frame cycles. Bank2
table slack 653 B; the live stage is 47 shapes / 211 rooms.
