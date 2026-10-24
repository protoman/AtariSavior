# Layout plan — position first, shapes second (2026-10-24)

**User rule (2026-10-24):** the generator must first decide the *room position
layout* (a grid where each `#` is a room, `S` the start, `E` the goal), then
give every room a shape that provides exactly the exits its neighbours
require. A room's exits are never authored by hand — they are derived from
adjacency. The editor validates the same rule on save.

This is the successor of `band4_plan.md`'s "generator plans emit four bands"
item: the bands are in, the *layout* is still a two-column serpentine.

## The target style (user's example)

```
..S.............
..#.............
###.#########..E
#...#...#...#..#
#####...########
```

33 rooms: a stem from `S` down into a junction row, a 9-room corridor with a
gap, four vertical spurs, two horizontal runs at the bottom, and `E` reached
from above at the far right. Junctions, corridors, spurs and (at least) one
loop. Level `n` only has `n` rooms (max 20), so the example is the *style*, not
a literal target.

## Two hard constraints (measured, not negotiable)

### 1. A side opening is ALWAYS on both edges

The playfield is **reflected** (`CTRLPF` D0 = 1): model cell 0 is drawn at
display columns 0-1 *and* 38-39, and `PlayerHitsMap` mirrors the same way. So a
room cannot have a left-only or right-only passage: `SHAPE_H` cuts cell 0 and
both edges open. Consequence: a room with exactly ONE horizontal neighbour also
shows a **dead aperture** on its far side. That is harmless — the exit scan
finds no room (`bank2 ExitNoneB2`) and the player just stops at the edge — but
it is visible and must be accepted as the price of the mirror.

(The generator's notes say the same: "the turn rooms also show a dead aperture
on their far side".)

### 2. The shape library is capped at 64, and we are at 53

The shape index is **6 bits** (`LEVEL_FORMAT = 7`, one shape byte per room), so
64 model shapes is the format limit; `test_generator` enforces it plus a
`kShapeBudget = 56` generation budget. A shape is keyed by
`(exits | 2Gap | START/GATE/WATER/CHANNEL | arch)` — the arch bits alone are 8
values, so the count is `exit-combos × arches`, not `exit-combos`.

**Measured 2026-10-24:** switching `SHAPE_H` from "the serpentine's turn" to
"any horizontal neighbour" turned the 2-column serpentine into a ladder (both
columns overlap on 10 rows) and the base library jumped from **53 to 65 shapes
— over the 64 cap**. So the adjacency rule cannot ship alone; it ships with a
layout whose adjacency graph is *designed* (few ties) and with the arch
rotation budgeted.

## Design

### Layout builder (deterministic)

- Grid up to 15 × 15 (`POSITION_SPAN`, 4 bits per axis in the position byte).
- `n` rooms for level `n` (play order = walk order, room 0 = `S`).
- A **seeded LCG** (seed = level number) carving a spanning tree over a small
  lattice, plus a bounded number of ties (loops) and spurs. Seeded, not RNG:
  two runs must stay byte-identical (`test_generator` asserts it).
- `S` = the topmost-leftmost room (the kernel drops the player in at cell 4/8
  of band 0); `E` = the room farthest from `S` in grid steps (the miner room,
  which must also be a water goal room from level 4).
- Ties/spurs are capped per level so the shape library stays under 64 (see the
  budget below).

### Exits from adjacency (the rule the validator already enforces)

For each room, `N`/`S` = a room above/below, `H` = ANY room left or right
(both edges open, constraint 1). Every pair is carved on both sides, and the
vertical pairs keep the shared gap columns (8/9, or 3/6 on two-gap levels).
Bands: side links in band 1 (band 2 stays the archetype's ledge band), vertical
links in bands 0 and 3.

### Shape budget

```
combos (N?,S?,H?)            : 7   (NS, N, S, H, NH, SH, NSH)
2Gap doubling (N/S combos)   : ~13
role variants (START/GATE/WATER/CHANNEL + hot) : ~6
arches per combo             : 1-2 (base), extra archetypes only if it fits
                              -> target: <= 56 (budget), never > 64 (format)
```

Arch rotation must therefore be keyed by the exit combo (a room type gets ONE
archetype family), not applied as an independent multiplier.

### Steps

1. `LayoutMaze(level)` replaces `LevelWalk`: grid, spanning tree, ties, `S`/`E`.
2. `RoomShapeMask` takes exits from adjacency (the 2026-10-24 rule, reverted in
   `DataSerializer.cpp` until this lands).
3. Ribbon the arch pools by exit combo; measure `used.size()`; fail the build
   if > `kShapeBudget`, and `test_generator` fails above 64.
4. Gates: `test_room_links` (bands match on both sides), `test_generator`
   (shape count, byte-identical reruns, passages == adjacency count),
   `RoomConnectivityProblem` (every room crossable), `convert` (hard-fails a
   half-carved/mismatched link), battery.
5. Regenerate the live stage and re-freeze the test banks.

### Interactions to keep in mind

- **Crunch rooms** are hazards, not gates, once band 2 is open: the player waits
  in the low band and moves on. No geometry coupling, no special-cased shapes;
  the stub at cell 0 is permanent, so a side exit in a crunch room is only
  usable from band 2 (fine — band 2 is open).
- **Async blocks / locked doors** still need a column open in band 1 and walled
  in bands 0 and 2: the band-2 archetype ledges provide those columns.
- **Side links + water rooms**: the raft lane and the miner rock live in the
  bottom band; a side link does not touch them.
