# 20-level stage generator (`--generate-stage`) — E2, 2026-10-20

The editor now PRODUCES the full progression the game is designed for: **20
levels, level n has n rooms (210 rooms)**, written as ONE unified stage file
(E1 schema). Content tooling only — the ROM format, the converter and the live
stage (`src/rooms/`) are untouched.

## 1. Entry points

* **File > Generate 20-Level Stage...** — Save dialog, defaulting to
  `<game data dir>/stage20.json`. The generator never picks a path itself, so
  the live stage can only be overwritten by an explicit user choice (and the
  dialog asks before replacing an existing file). The current project is not
  touched and the file is not opened.
* **`savior_editor --generate-stage <path>`** — headless twin (same
  `DataSerializer::Build20LevelStage`), used by the tests and by scripted
  builds.
* It prints `generatestage: OK (20 levels, 210 rooms, 7 shapes) -> <path>`.

Build/play the result WITHOUT touching the live stage:

```bash
src/tools/editor/cmake-build-debug/savior_editor --generate-stage /tmp/stage20.json
SIM_PY=/bin/false STAGE_FILE=/tmp/stage20.json ./build.sh /tmp/savior_stage20.bin
stella /tmp/savior_stage20.bin
```

(`SIM_PY=/bin/false` skips the sims for staged builds — they probe LIVE room
content, the same rule `qa_build.sh` / `raft_build.sh` follow.)

## 2. The layout rule (why it cannot tear a transition)

Connections are **DERIVED FROM ADJACENCY** at run time (C1: `ExitScanB2` scans
the level's grid-position column); nothing in the data says "connected". So the
carved opening and the neighbour set must agree on BOTH sides of every shared
edge, or the player enters a room inside a wall.

The playfield is **left-right MIRRORED**, which decides the shape of the rule:

* cell 0 of the 10-cell half is the room's **outer edge, drawn on both sides**
  (display cols 0-7 and 152-159) and collision mirrors too (`PlayerHitsMap`
  maps display col >= 20 to 39-col). A horizontal exit is therefore **one
  cell** (row 1, col 0) and is inherently two-sided;
* cell 9 is the **centre seam**, not a boundary. A wall there would split the
  middle band in two and choke the vertical shaft, so the generator leaves it
  open (as the live rooms do: row 1 = `#.........`).

The generator lays rooms out as a **2-column serpentine**:

```
level n <= 10 :  x=0, y=0..n-1                       (pure vertical corridor)
level n >  10 :  x=0, y=0..9  ->  turn  ->  x=1, y=9 -> 10-m going UP
```

* every vertically adjacent pair is carved on both sides (top/bottom band,
  cells 8-9 = the centre shaft);
* horizontally, both columns are occupied on many rows, so those pairs are
  **walled** (solid col 0 / row 1 in both models): the ROM still sees the
  adjacency, but the player can never reach the edge to use it, which the rule
  allows ("carve every adjacent pair OR keep a solid wall at the shared edge");
* the ONE carved horizontal pair is the turn, and **both** of its rooms carry
  the horizontal bit;
* the turn rooms show a dead aperture on their far side (nobody there): the
  exit scan finds no room (`ExitNoneB2`) and the player simply stops at the
  edge. This is the only layout artefact and it cannot tear anything.

Grid span is 1 column x 10 rows, well inside the C1 15x15 cell (nibble 15 is
the no-room sentinel and is never used).

## 3. Shape library (the cost lever)

Models are keyed by the **carved exit set**, three bits: `N`, `S`, `H`
(horizontal), plus `START` for the level's spawn room. West and east share the
`H` bit on purpose — they are the same physical cell, and two models differing
only in "which side" would be byte-identical anyway (the converter counts
duplicate models separately). 210 rooms resolve to **7 shapes**:

| shape | row 0 | row 1 | row 2 | used by |
|---|---|---|---|---|
| `N` | `########..` | `#.........` | `##########` | top of column 1 |
| `S` | `##########` | `#.........` | `########..` | bottom of a 1-column level |
| `N+S` | `########..` | `#.........` | `########..` | column corridors |
| `H` | `##########` | `..........` | `##########` | level 11's only column-1 room |
| `N+H` | `########..` | `..........` | `##########` | the turn pair |
| `Start` | `##........` | `#.........` | `##########` | level 1's single room |
| `S+Start` | `##........` | `#.........` | `########..` | room 1 of levels 2..20 |

Exit spans come from the shared constants in `LevelData.hpp`
(`kVertExitA/B = 8..9`, `kHorizExitA/B = 1`, `kHorizExitCol = 0`) — the same
ones the editor's "Add Room" carving uses.

The `Start` ceiling opening is REQUIRED: the kernel drops the player in at
`LevelStartX/Y = (32, 24)` px = display col 8 = **cell 4 of the top band** with
collision bypassed (`DropStep`), so a solid band there would drop him inside a
wall. Cells 2..9 are open (the live stage's start room is `##........` too).

## 4. Content

* Palettes: the existing `kLevelPalettes` (band 1 colour = palette + 40, clamped).
* Objects (editor caps: **max 2 per room**, **max 1 element per tile row** —
  `kMaxRoomElements` / `ElementInRow`, repeated by `verify_build`):
  room 1 a spider, middle rooms alternate bat / lamp, the last room a wall
  snake plus the miner (rows 3 and 7). Lamps only in rooms 0-7 — the room
  darkness mask (`EnemyRamD` bits) reaches no further, so a deeper room gets a
  bat instead of a lamp that could never darken it.
* Miner: last room, `miner_x = 4` (clear of the bottom-centre shaft),
  `miner_y = 7` (the converter rejects any other row), facing right.
* No async layer: symmetric rooms, no `asym_patches` / `feature_cells`, so the
  stage emits zero extras records.

## 5. Determinism

No RNG, no clock, no unordered container: model ids ARE the ascending shape
keys, rooms are emitted in walk order, and all floats are exactly representable
(1.0 / 1.25 / 1.5 ...), so the cereal JSON is stable. `tools/test_generator.py`
runs the generator TWICE into different files and byte-compares them.

## 6. Capacity (measured on the generated stage)

| measurement | value |
|---|---|
| level tables in bank2 (`levels_index` 140 B + 20 level files) | **1 606 B** — 717 B slot slack of 2 323 B |
| bank3 data (models + extras base table) | **97 B** of 1 088 B — 991 B slack |
| shapes | 7 (`LEVEL_SHAPE_COUNT = 7`), all referenced |
| full `STAGE_FILE=` build | 4 x 4 096 B exactly, `verify_build: OK` (1 warning: 16 B pre-pad headroom, pre-existing), `LEVEL_COUNT` self-heals 4 -> 20 |

Slot placement of the 210-room tree (greedy first-fit, all green):
`$F307` 329/329, `$F453` 427/429, `$F700` 336/340, `$F8B7` 14/290,
`$F9D9` 500/503, `$FCB8` 0/207, `$FE9C` 0/84, `$FF59` 0/141. The three still
empty slots (432 B) are what growth past ~210 rooms would use.

## 7. Tests

`tools/test_generator.py` (headless; never reads live stage content):

* 20 levels, level n has n rooms, 210 rooms, canonical wrapped form;
* model library: <= 16 shapes, ids 0..n-1, EVERY model referenced;
* positions unique, inside the 15x15 C1 grid;
* the tear rule per adjacent pair (north/south/west/east carve agreement,
  mirrored cell 0 treated as one opening), the start cell is air, and the
  PASSAGE graph must be the serpentine tree: connected + exactly
  `rooms - 1` passages;
* object caps (2 per room, 1 per row) and no async;
* determinism (two runs byte-equal);
* `convert_level.py --stage` into a temp `generated/`: `LEVEL_COUNT = 20`,
  `LEVEL_SHAPE_COUNT` == model count, 210 room `.txt` mirrors, and the bank2 /
  bank3 slack are both positive (printed).

## 8. Notes / fixes picked up along the way

* `kVertExitB` was still **11** from the retired 20-cell grid, so the editor's
  "Add Room" carved cells x=10,11 — which are the NEXT ROW's cells 0 and 1
  (row-1 col 0 got erased by adding a room above). Now 9 (`kVertExitB`), one
  shared definition in `LevelData.hpp`.
* "Add Room >" carved col 9 — the centre seam — which is not an edge. Both
  horizontal directions now carve `kHorizExitCol = 0` (the mirrored edge).
* `verify_build.stage_rooms_dir` (the `STAGE_FILE` leg) re-adds
  `cereal_class_version: 1` to each level it materialises: cereal writes that
  key ONCE per archive (the first level), so every level file after the first
  failed `check_level_format` on a staged build.

## G2 (2026-10-20): HERO-style variety + editor rules

The first generated stage was flat (bats only). G2 gives every level a
growing feature mix, in the HERO spirit (level 1 is a single cave; later maps
add red/hot walls, water, tentacles, snakes, spiders and the keyed door):

| from level | feature |
|---|---|
| 1 | 2 rooms minimum (user rule); spider start, wall snake + miner goal |
| 3 | hot middle band (model `mid_band_type = 1`, two wall blocks) |
| 4 | water goal (bottom band) + raft on open water |
| 6 | keyed gate: row-1 gate shape, one `LOCKED_DOOR` cell, key in an earlier room |
| 7 | tentacle on the water goal's surface (replaces the raft) |
| 9 | two-object rooms (bat + spider, one per row) |
| 11 | **phase** gate: the row-1 gap blinks (45 solid / 45 open) |
| 14 | **hcrunch** band: fixed 10-cell row-1 prefix, room is object-free |
| 7 | **async blocks**: a solid patch in an ordinary room (rides WITH enemies) |
| 12 | **two async blocks**: one per side in that room (convert cap = 2) |

Hazards alternate with "breather" rooms; the shape library grows to ~10
entries (exit masks x hazard role) and the converter still fits: 211 rooms
build with (measured) bank2 tables 262 B slack and bank3 shape data 783 B.

`tools/test_generator.py` asserts the schedule (hot from 3, water from 4,
raft then tentacle, gate/key from 6, two-object rooms from 9), the door rule
(one non-key enemy), the tear rule (a water goal's row-2 opening is the
surface, not an exit), determinism and the converter capacity.

## Editor rules (2026-10-20)

* Switching levels **always saves** (no "save changes?" prompt).
* `File > Generate 20 Levels` replaces the stage and **saves immediately** to
  `<gameDataDir>/stage.json` — no save dialog.
* `File > Save Stage` (Ctrl+S) writes the same path.
* Build the editor's stage with `STAGE_FILE=rooms/stage.json ./build.sh`; the
  default `./build.sh` still builds the legacy per-level stage until the
  live-tracking tests are migrated (they pin level 1's tutorial room).


## G3 (2026-10-20): placement fixes + two-gap route choice

* **Snake** lives in the MIDDLE band's left border (cell 0, y=5), not the top
  band: the middle band is open next to it, so it can come out and be shot.
  (The top band's border is 8 cells deep — a snake there was walled in.)
* **Bats/keys/extras** only land on cells the shape actually leaves open:
  gate/phase gap (cell 4), hot shape cell 4, normal cell 2/5, exit corridors
  (cell 8) for the second object and the key fallback. 0 embedded non-snake
  objects across the stage (was 181).
* **Two-gap links** (levels 5, 9, 13, 17): every vertical link uses TWO gaps
  (model cells 3 and 6) in the ceiling and the floor; the room below repeats
  the SAME pair, which the test asserts cell-by-cell (a boolean "open" check
  would hide an 8/9 vs 3/6 mismatch and drop the player into a wall).
* One gap carries a **lamp** (even rooms) or a **spider** (odd rooms), the
  other is empty: the drop is a route choice. Gate/hcrunch rooms and the goal
  room stay out of it (door rule / object cap / miner).
* Water goals in a two-gap level join a two-gap ceiling to the open water
  floor, so the drop always enters through an actual ceiling gap.

Measured: 211 rooms, 20 shapes, staged build `verify_build OK`, bank2 tables
326 B slack, bank3 shape data 317 B slack.

## G4 (2026-10-20): HERO-style water channel + HERO map measurement

**Channel turn** (level 11+): the serpentine's column-0 turn room becomes a
water crossing — hot row-1 ceiling on cells 1..7, the centre cells 8/9 stay the
N shaft, cell 0 is the H exit; the floor is open water with a raft. Flying
across at row 1 is lethal, so the player drops to the low channel and rides the
raft to the side exit (HERO-like, option B). In two-gap levels the ceiling's
two gaps are opened through the hot row so the entry lands in the channel.
Only the column-0 room becomes a channel (the column-1 room is the goal at
n=11 and would put the miner in the water).

**HERO 2600 map measurement** (vgmaps PNGs, levels 1/4/8/12/16/20): the caves
are 153x253 px (level 1, ~1x1.8 room-screens) up to 1071x1267 (level 16,
~6.7x8.8). Slicing them into our 10x3-cell grid (80x144 px half-room, 2030
sliding windows) yields **512 distinct 10x3 patterns** and **137 distinct
10-cell bands**. Sliding windows over a continuous cave inflate the count
(shifts of one ledge look new) and the empty pattern dominates, so read it as
an upper bound/direction — but our 18 shapes / 12 bands is clearly the low end.
Format ceilings: shape index is 6 bits (**<= 64 shapes**), row-pool index is
1 byte (**<= 255 bands**) — a 30-60 archetype library fits.

## G5 (2026-10-20): archetype gallery (HERO-like variety)

Ordinary and hot rooms now get an INTERIOR archetype, chosen deterministically
(3 bits in the shape mask, so the shared-shape dedupe still works):

| id | name | interior (cells 1..7 only) |
|---|---|---|
| 0 | shaft | plain |
| 1 | ladder | ledge row 0 (2-4) + ledge row 2 (5-7) |
| 2 | pillars | row-1 pillars at 3 and 5 |
| 3 | steps | row-0 block 3 + row-1 step 4 |
| 4 | pocket | row-1 niche at 6-7 + row-0 block 6 |
| 5 | zigzag | row-0 2-3 + row-1 5 + row-2 6-7 |
| 6 | Hot2 | row-1 hot blocks 2,3 + 6,7 |
| 7 | HotMid | row-1 hot block 4 (weave) |
| 8 | HotStag | row-1 hot blocks 2 and 6 |

Rules: start/goal/special rooms stay plain; hot rooms pick 6..8 by level;
normal middle rooms pick 1..5 by (level+room); the 2-gap corridor cells are
re-opened after the interior. Special rooms (gate/phase/hcrunch/water/channel)
keep their functional shapes. Async blocks scan for a cell whose MIRROR is
also open, or the MetaA band mask cannot differ from the plain mirror (convert
guard).

Measured: 211 rooms, **37 shapes** (cap 64), staged build `verify_build OK`,
bank2 tables 298 B slack, bank3 shape data **143 B** slack.

## G8 (2026-10-21): placement rules from playtest

* **The start room has NO enemies** (user rule): the spawn room is a corridor,
  an enemy behind the spawn is never met. From level 8 it may carry **hot
  walls** (single HotMid archetype, capacity) and from level 7 an **async
  block** beside the exit gap (col 7, or the first column whose band-0/2 cells
  are walled — the M1 whole-cave strip requires that).
* **Enemies sit in the player's path**: bats/spiders in the centre shaft
  (cell 8, x=16) that every descent crosses; gate/phase bats in the gate gap.
  The goal room's enemy (level 2+) guards the APPROACH corridor — the old wall
  snake at cell 0 was past the miner (x=4) and never fought.
* **One object per room** (miner counts): the extra second enemy from level 9
  is gone — the single GRP1 sprite rotates with the miner, so a second enemy
  doubles the flicker for no gameplay gain (playtest: a room "flickered so much
  it stayed off screen"). Level 1's goal is miner-only, which also keeps the
  two 2-room levels distinct.
* Start top-band opening narrowed to cells 2..6 (the drop slot), keeping 7..9
  walled so the async block's M1 column has walls in bands 0/2.

Measured: 211 rooms, 36 shapes (hot families trimmed to two for capacity),
bank2 610 B / bank3 122 B slack, staged build verify_build OK, battery green.

## G9 (2026-10-21): 2 objects per room restored (band rule)

The user needs TWO objects per room; not drawing one was the wrong fix — the
flicker is the kernel's problem, not the content's.

* Normal rooms: one object in the middle band (the shaft) + from level 5 a
  second on ANOTHER band (top corridor) => 2 objects, one per band.
* HOT rooms: **no object in the hot middle band** (user rule); the other two
  bands may carry one each (bat band 0, spider band 2, both on the shaft).
* Start room: still clean (no enemies/lamps). The key host search now prefers
  middle rooms and the room right before a gate is RESERVED (no second object),
  so a key never falls back into the spawn room.
* Channel bat moved to band 0 (the channel is a hot room).
* `test_generator` pins the rules: 2-object rooms from level 5, clean spawn
  room, no middle-band object in a hot room.

36 shapes; bank2 354 B / bank3 122 B slack; staged build OK, battery 0 fails.
The flicker itself (one GRP1 sprite rotating between the two objects) is a
kernel chunk: per-band multiplexing (draw object A in its band, switch sprite
data/position at the band boundary). The band rule above is exactly what makes
that possible.

## G10 (2026-10-21): flicker root cause (hot-room VBL) + model-3 design note

**Flicker (level 3/4 hot rooms, 268-line frames).** Reproduced with
`SIM_LEVEL=3 SIM_ROOM=1` on the live stage: the VBL worked **1414c** against
the 1472c timer window and crossed a 64-tick phase boundary, adding one line
per frame (the whole-screen jump). The cost was `BuildColupF` walking the hot
rect stream **every VBL** to derive "row 1 is hot" — which is exactly what
`MetaB b6` already says.

Fix (bank3 `BuildColupF`): write the 3 stripe colors, then (if `MetaB b6`) set
row 1 to the hot pulse color. No per-frame stream walk. Measured:
hot room VBL **1414c → 1101c**, frame lines **268 → 267**, wall model clean;
level 7's hot room 1082c. Battery 0 fails.

**Model-3 design note (user, 2026-10-21 — a good example, keep it).**
`Shape S+Start` (id 2 in the current stage):

```
1100000111   row 0: spawn/corridor opening cells 2..6, ledges 7..9
1000000000   row 1: only the outer wall (col 0)
1111111100   row 2: floor with the S gap at 8/9
```

Why it reads well: an **asymmetric top shelf** instead of the bare centre
notch, one clean wall on the left, and the S gap offset from the opening — the
room looks like a cave mouth, not a tube. It works as a **spawn room** (the
drop slot is at cell 4) and, visually/structurally, as a **deeper room**
(pair it with a room whose floor gap matches 2..6, or enter it sideways). Use
this as a template for future archetypes: offset openings + one-sided ledges
beat symmetric centre cutouts.

Test fixture: `src/tests/stages/level4_only.json` = the current level 4 (rooms
+ models), so the hot-room flicker/design can be probed without live changes:
`STAGE_FILE=src/tests/stages/level4_only.json ./build.sh`, then
`SIM_LEVEL=0 SIM_ROOM=1 python3 sim_frame_budget.py`.
`sim_frame_budget` also gained `SIM_VBLPROF=1` (VBL PC histogram) for this class
of investigation.

## G11 (2026-10-21): hot walls must shape the path (playtest screenshots)

Bad (user screenshots `useless_hot_walls*.png`): hot blocks at the sides of the
middle band leave the centre shaft free — the player just falls through and the
hazard is decoration.

Hot archetypes now block the CENTRE (cells 8/9 = the vertical shaft) and force
a detour through an offset gap; objects guard the gap columns:

| id | name | row 1 | use |
|---|---|---|---|
| 6 | HotGate | `#####.####` — one gap at cell 5 | from level 3 |
| 7 | HotSplit | `###.##.###` — gaps at 3 and 6 (choose) | from level 3 |
| 8 | HotComb | `#.#.#.#.##` — weave through 1/3/5/7 | from level 3 |
| 9 | HotAlign | `##.#######` — a single gap at cell 2, far from the shaft | **> level 10** |

`usefull_hot_walls_003` (stop the fall and line up with the gap) = HotAlign.
`usefull_hot_walls_004` (pick the entry, squeeze into the gap, bomb the async
wall) = from level 11 every hot room also gets a **solid async block in its
gap** (thin, bombable, M1 column walled in bands 0/2) — bomb it or take the
longer way around. The inverse case (two paths into one, with the hot wall in
your path) falls out of the same patch.

Capacity note: 40 shapes, bank3 data **5 B slack** — very tight. Further hot
archetypes/variants need a bigger bank3 data window (move the include to a
larger bank3 gap) before landing.

## G12 (2026-10-21): shape budget — the shape library is no longer window-capped

C11 removed the per-shape hot stream (a block is 3 row-pool indices; hot death
derives from the PF row 1), returning ~200 B. `tools/bank3_data_sizes.py` then
measured the two halves: shapes 272 B, extras 611 B — the old single 1 088 B
window had only 5 B slack, which capped the library at 40 shapes.

The bank3 data window is now **two** windows (C12):

| window | address | size | content |
|---|---|---|---|
| extras | `$F010-$F44F` | 1 088 B | per-level async streams + base table |
| shapes | `$F5CC-$F8B6` | 747 B | shape blocks + row pool + shape address table |

The shape half starts where `ERLoadDone` ends (`$F5CC`, not the stale `$F5BF`
figure measured from an older binary — a `.ds` target below the program
counter is a DASM `Origin Reverse-indexed` error, which is exactly how the
first attempt failed). `B3RoomBlocks` reads both halves in-bank, so the split
adds no tramp and no per-frame cost.

The generator now has a **declared shape budget** (`kShapeBudget`, two-pass:
base library first, extra archetypes only if the base fits):

* base: Ladder/Pillars/Steps/Pocket/Zigzag + HotGate/HotSplit/HotComb
  (+ HotAlign > level 10) — 40 shapes;
* budget mode: **Spiral**, **Gallery** (normal), **HotTwin**, **HotStair**
  (hot) and **HotDrop** for hot start rooms — 47 shapes, 322 B of the 747 B
  window (425 B slack);
* `test_generator` gates: shapes <= `SHAPE_BUDGET` (56), every bank3 window
  keeps >= 64 B slack, and a hot start room must keep row-1 cell 4 open
  (HotDrop: the spawn falls down cell 4, and convert promotes every row-1
  wall to a hot cell — HotSplit put a hot cell under the drop).


## 8. Finishability (2026-10-25)

Every generated level must be COMPLETABLE; this is checked on the whole stage,
not per room (`AnalyseReach` in DataSerializer.cpp, twin `tools/stage_reach.py`):

* the search runs on the 20-column FULL (mirrored) map, so the two chambers of a
  room are different places; side links flip the chamber, vertical links keep it;
* a solid async patch costs one bomb; a level may need exactly one - the START
  room's designed block - and nothing else;
* a SPIDER's column (lit span `[EX-13, EX+6]` +-2 px over the bands its 24 px bob
  sweeps) is a hazard the route must not need;
* a failing level is repaired deterministically (the outer loop in
  `Build20LevelStage` rebuilds the stage until it passes): slide/remove the
  spider, flatten an archetype, demote a channel room, drop a ledge block.
  `test_generator.py` asserts the result; `build.sh` only WARNS about the live
  stage (it is the user's file).


## 9. hcrunch gaps (2026-10-25)

A crunch room (levels >= 14) must offer the player a way out of band 1:
a room above and a room below (the one below neither the water goal nor a
channel), and a contiguous gap of at least FOUR tiles (user rule 2026-10-26: `###....###` /
`HHH....HHH` / `###....###`; a 1-2 cell hole is a death trap) in its ceiling
and in its floor. The crunch is mirrored, so the gap serves both sides. Every
shape under 4 gets
`SHAPE_WN` / `SHAPE_WS` (cells 3..6 open), the room under a widened floor
widens its ceiling. `kCrunchShapeCap` keeps the shape library inside the bank3
window by reverting the last crunch rooms (never a level's only one) to
ordinary rooms. `test_generator.py` asserts the gap on every generated crunch.
Runtime: `ExtrasLoad` restarts the frame clock at the grow phase for crunch
rooms so the prefix is moving when the player arrives (`test_hcrunch_entry.py`).
