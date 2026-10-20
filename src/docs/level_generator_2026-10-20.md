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
