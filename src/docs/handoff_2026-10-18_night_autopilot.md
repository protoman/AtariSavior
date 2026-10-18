# Handoff — night auto-pilot, 2026-10-17 → 18

Context: user asleep; instruction "work on all remaining tasks and features like
the raft". Everything below is committed, gated and on `master`.

## Committed tonight (newest last)

| commit | what |
|---|---|
| `55c1495` | editor: room-level async **data model** + startup migration + brushe refuse |
| `50f0a7b` | bank3 `.PhRec` literals re-synced to the LIVE layout |
| `3ac41a8` | docs: async model→room invariants (AGENTS) + `feature_tiles_plan` Phase 7 |
| `b341052` | user's `TODO.txt` (added blind) |
| `ce1cdda` | editor: room-level async **brushes** (the option-4 request, finished) |
| `84e15dc` | QA stage: durable generator + **water/raft room**, raft proven in-game |
| `fde1a6c` | AGENTS: stale lamp item resolved, phase-wall ruling, raft status |
| `0c9fee1` | QA sweep **picture set** (`tools/qa_shots.py`, 8 PNGs) |

Gates at HEAD: `./build.sh` green (verify_build + both py65 sims) · battery
**38/38** · editor builds + `--selftest` (models *and* level/migration) ·
`test_editor_roundtrip` OK · `qa_build.sh` + `qa_sweep.py` **18 checks green**
(with and without `QA_SHOTS=1`).

## What tonight actually changed for gameplay

- **Async walls are per-ROOM now** (strips + phase/vcrunch/hcrunch cells) — see
  AGENTS "Async walls live on the ROOM" for the invariants. The editor can
  author them from the LEVEL tab ("D. Async Door", "A. Async Strip",
  "P. Phase Wall", "V. Vertical Crunch", "C. Horizontal Crunch"); opening an
  older project migrates it once and says so in the status bar.
- **The raft is proven in-game** (it already existed as data + PF): a row-2
  `RAFT` tile is a solid platform you stand on (~RoomY 84) while the
  `bottom_band` water kills at `RoomY >= 125`. `qa_sweep` now lands on the
  ledge, walks INTO the water to prove it kills, and crosses a 4-cell raft
  bridge to the goal. **Motion was never specified** — a moving/rideable raft
  needs a ruling from you (it would be a new object type: data record + carry
  physics + render + editor brush).
- **Bug fix found stale:** the "blast kills lamps" item was already fixed
  2026-10-07; it now has its missing regression guard (`tools/test_bomb_lamp.py`).

## Remaining work, with my assessment

1. **Editor GUI pass (you) — cheap.** The relocation compiles, selftests and
   round-trips, but the Qt GUI itself was never opened tonight (headless).
   Open the editor, load `src/rooms`, place a door + a phase wall in a room,
   save, run `./build.sh`: that is the whole acceptance test for `ce1cdda`.
2. **Put the features into the LIVE levels (content) — cheap, needs your OK.**
   `src/tests/qa/rooms` is a ready-made 7-room set (key/phase/door/vcrunch/
   hcrunch/water-raft). Because async is per-room now, a room can reuse any of
   your existing model shapes — I did NOT touch `src/rooms` while you slept.
3. **Game-over screen — medium, needs a design ruling.** Today `PlayerLives=0`
   just resets to 3 and reloads the level (`LoseLife`). A real game-over means
   a text screen + wait for RESET/SELECT. The title's 48px pipeline lives in
   bank1 and could host it, but bank0 is full (1B) so it needs a cross-bank
   pad, and the AGENTS frame-timing rules apply (sim-proof required).
4. **Phase 9 leftovers:** background music (needs your ear; the ch0 machinery +
   `test_intro_music` exist), screen transitions, difficulty settings, high
   score table.
5. **Phase 10 content:** 5+ designed levels, per-level enemy patterns, boss,
   secret rooms.
6. **Phase-6 sweets:** play the QA ROM in Stella for the real screenshot set
   (`bash tools/qa_build.sh` → `/tmp/opencode/savior_qa.bin`); the sim-rendered
   set is already in `src/screenshots/qa/`.

## Traversal lessons worth keeping (they cost me an hour tonight)

- **Collision box is `[RoomX-7, RoomX]`** (7 lit px, reported at the right
  edge). An 8 px one-cell gap leaves a **1 px** drop window — author lanes as
  TWO cells (16 px) or the player ping-pongs on the edge.
- **An M1 door can never be touched while falling**: the wall-hide envelope
  forbids the door column and its mirror from being open in rows 0/2, and those
  cells are exactly the fall path. Door rooms need a floor to walk into the bar.
- **Input is active-low**: two directions must **AND** the masks
  (`UP_RIGHT = UP & RIGHT`); ORing releases both.
- **A band death re-drops the player** (`DropTarget = death_y-12`, input
  bypassed during the drop) and arms the respawn hover, which pins Y — so the
  recovery order is: wait the drop, thrust UP out of band 2, then move
  sideways. Walking first jams against the ledge because y is inside its cell.
- **A full-band phase stripe is not crossable in one pass** (45 f window vs
  ~55 f fall) — that is your ruling: one-time crushable wall.

## Commands

```
./build.sh                                   # ROM + verify_build + both sims
for t in tools/test_*.py src/tools/test_*.py; do /home/iuri/python3/bin/python3 $t; done
./src/tools/editor/cmake-build-debug/savior_editor --selftest src/tests/rooms/models/models.json
bash tools/qa_build.sh                       # QA ROM -> /tmp/opencode/savior_qa.bin
/home/iuri/python3/bin/python3 tools/qa_sweep.py
QA_SHOTS=1 /home/iuri/python3/bin/python3 tools/qa_sweep.py   # + PNGs
/home/iuri/python3/bin/python3 tools/gen_qa_stage.py          # regenerate the QA stage
```


---

## Addendum — raft landed (same night, later session)

The moving raft is now IN the ROM and guarded (see `plans/raft_moving_plan.md`
for the as-built section: bank1 `RaftBody` at $FDE3, the twinned `CallPad_RaftBody`
at $F8C0, the folded `UEDispatch`, the two table bytes, the bank2 bomb skip).
`tools/test_raft.py` is battery entry 42 and now also drives the REAL cross-bank
path (UpdateEnemies -> dispatch -> tramp -> bank1 body -> ReturnPad); the build is
green with both sims.

**To play it:** `bash tools/raft_build.sh` -> `/tmp/opencode/savior_raft.bin` —
a staged COPY of the live stage whose level-2 water room carries the raft instead
of its tentacle (level 2 -> descend from the start room; the raft patrols the
channel, drop onto it from a ledge). The live stage is never modified: room 1 is
at the 2-object cap and swapping the tentacle in place breaks `sim_bomb_fuse`,
and models 2/3 are solid at display cols 0-1 / 38-39 so no new level-2 room can
be reached from the start room.

**Tide + colour (user feedback, same session):** the raft now RIDES THE TIDE.
The water surface is not static — the VBL stages `36+off` into `CollisionX` and
the kernel draws the strip as the band's last `12-off` lines — so `RaftBody` sets
its Y to `125+off` and its bottom row sits on the moving surface (the rider's pin
follows it, worst case 116 < the 125 kill line). The raft is **white** now
(`ObjSpriteOffTable[7] = OBJ_LAMP`, frame colour `$0e`) — LAMP is the only white
blocky 8x8 and `ObjSprites` has no spare bytes, so a dedicated design needs 8 art
+ 8 colour bytes freed.

**Rule recorded in AGENTS:** the LIVE stage (`src/rooms`, `models.json`,
`src/generated`) belongs to you — the agent does not edit it, tests use the
frozen/test-owned copies and anything playable gets a staged demo build
(`tools/raft_build.sh`).

**Lesson worth keeping** (the one real bug of the session, caught before you
ever saw it): a cross-bank call needs a byte-identical TWIN, because `sta $1FF7`
makes the CPU fetch the `jmp` opcode AND its operand from the other bank at the
same address. My first tramp had no twin — it would have jumped into bank1's own
body bytes. `verify_build.check_raft_tramp` now asserts the pair, and the
integration case in `test_raft.py` drives the real path so this class of mistake
cannot ship silently.

What needs YOUR call when you are back:
1. **Inertia**: implemented as a one-frame hold on the turn frame. A real
   multi-frame spin-up needs one ZP byte (none free — EnemyRamD's high nibble is
   RoomDarkMask) — say the word and I carve one.
2. **Art**: the raft borrows the snake's solid 8x8 block (`ObjSprites` is full to
   $FF00). Freeing 8 B would give it real raft art.
3. **Where to fly it**: authoring is the editor's `ADD_RAFT` brush (type-7
   entity, water room, open cell). The live water room (level 2 room 1) is full
   (tentacle + the level's miner = the 2-object cap), and swapping the tentacle
   out breaks `sim_bomb_fuse` (it bombs that room for the wall-hole check), so
   the live stage was deliberately left untouched. Options if you want it in the
   live game: move the miner, drop the tentacle, or let me add a second water
   room to level 2.

## Addendum 2 — sim_bomb_fuse was coupled to the live stage (user caught)

The user removed the tentacle from their water room (raft + miner now) and
`sim_bomb_fuse` failed its **tentacle coverage** check. Cause: the sim forced
Level 2 and relied on that room's AUTHORED record being a type-3 tentacle
(its own comment said so), which violates the live-stage ownership rule. The
tentacle is what exercises the deepest gameplay stack path (the probe's
PlayerHitsMap), so the check exists on purpose.

State now: the check **degrades to a loud `[SKIP]`** instead of failing a build
the user did not break, and the reason is printed. That is a deliberate
downgrade, not a fix.

KNOWN GAP (next session): stage the tentacle from bank2 ROM instead of from the
room — point `EnemyDataLo/Hi` at a bank2 byte that reads 3 (and re-apply it each
live frame, because EnterRoom re-derives the pointer). The first attempt did
exactly that and still never reached the dispatch (`probe_ran` stayed false) with
`EnemyCount=2` and the staged byte verified at $F105; the next step is to trace
`UpdateEnemies`' dispatch for slot 0 in that sim (bank0.lst is the live build,
so the staged pointer and the room's own table can be compared directly).

## Addendum 3 — "player looks wider / hard to fall through the hole": RESOLVED

**Cause was the hcrunch's stage data, not the ROM.** The user removed the hcrunch
row (10 feature cells, one per column) from level 3 room 1 and immediately the
hole became passable again — the hcrunch is a kill-on-touch band stripe, so
dropping through that hole ran into it. No sprite, NUSIZ, positioning or
collision bug existed: the earlier "the player looks wider" reading was the
stripe sitting next to the player.

What it took to get there (all landed):
- the editor's **Delete tool** now clears a P/V/C feature row / asym patch (it
  only erased entities before — the report was correct and the agent's test used
  the wrong brush, see the AGENTS entry-point rule),
- the **spill layout**: `TallySum` moved out of the `.ds $F970` slack into the
  `$F880-$F8B6` pad so a shrinking level data set still builds,
- the `.PhRec` literal re-synced by `verify_build --sync-phrec`.

Lesson for the file: a report of "hard to fall through / looks wider" in a room
carrying a band feature should first be checked against the feature's data, not
the sprite pipeline.

## Addendum 4 — the two open items are closed

1. **`sim_bomb_fuse`'s tentacle coverage is a hard check again.** The tentacle is
   now staged from ROM (EnemyDataLo/Hi -> a bank2 byte reading type 3) with the
   count, the pointer AND `EnemyDeadMask` re-applied every live frame. The dead
   mask was the piece the first attempt missed: the sim's own bomb blast marks
   slot 0 dead, and `UpdateEnemies` skips a dead slot before it can move — so the
   probe never ran even though the staged type was correct. No dependence on the
   user's room data remains (that coupling is what broke when they removed the
   tentacle).
2. **`test_bomb_user_sequence` / `test_laser_close` are green.** They read the
   live `bank2.lst` and expected level 1 to have a second room (`L1R2*`); level 1
   has one room, so they threw KeyError. Re-pointed at the room that exists.

Battery: **43/43**.
