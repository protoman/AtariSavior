# Changelog

Release versions live in `VERSION` (build.sh stamps them into the ROM, the manual
cover prints them, `tools/release.py` names the artifacts from them).

## 1.2.0

**Rebuilt ROM structure, 32 levels (1.1.1 was never released: its fixes ship here)**

- **The ROM is rebuilt** (layout v3): code first, then the room models, then the levels, with
  the boot stub in every bank, bank selectors by role, and the level data split over two room
  banks (A: levels 1-24, B: levels 25-32).
- **32 levels, 484 rooms** (was 20), all inside the frame budget; the generator ramps rooms,
  creatures, miners and speed up to level 32.

Everything that was planned for 1.1.1:

- **Pillars, async walls and doors are solid again.** The 1.1.0 cave kernel reused `$8F` as
  scratch, which zeroed the packed collision byte bank3 stages there for the HUD to copy, so
  every pillar (ball/M1 strip), bomb wall and locked door could be walked through. The
  kernel's scratch byte moved (`S1Adj` shares `$92` with `CtxNext`); `test_async_wall.py` walks
  into every start-room patch of the real ROM.
- The rescue miner stands on the side opposite the REAL entrance (the neighbour on the map, not
  the room listed before the goal: levels 7 and 19 had him on the wrong side) and every miner
  - the goal one and the extra ones - faces the entrance (it was always facing right).
- No bat sits in a pocket of one or two cells that nobody can reach (level 3 room 2, level 6
  room 2, level 19 room 16, level 20 room 14 had one): the generator keeps bats in air runs of
  at least four cells and the stage lost those four useless bats.
- SELECT during a game resets the power bar and its clock.
- After a game over the title comes back on the level you were playing (with or without a
  SaveKey), and ignores every key for about a second, so the taps that were flying the ship
  neither step the level nor start a new game.
- A pillar (ball strip) on a hot band kills on touch, like the left pillar and the hot walls
  around it. Any element on a hot-wall band is hot.
- The two band colours of a level are different hues now (orange and blue, cyan and red, green
  and pink...) instead of the same colour lightened.
- **No more landing inside a wall between two rooms.** The water-channel room of levels 11 to
  32 opened its lower side band all the way to the screen edge while its neighbours open only
  the upper one, so leaving it by the lower band put the ship inside the neighbour's wall (level
  32 and 21 more levels, 44 links). The generator now opens a room's side link in one band
  only, and the build refuses any stage where the two rooms of a side link, or the two rooms of
  a vertical link, do not open exactly the same bands/columns. `test_link_arrival.py` checks
  every link of the stage statically and by flying every crossing.
- Frame budget: all 484 rooms of the 32 levels keep the fixed frame length (the laser hit test
  scans the enemy list once, the moth only walks with 18 overscan units left).
- **PAL frame is 312 lines again.** Since the NTSC overscan grew from 45 to 48 units the PAL
  picture ran one line short (311 lines, a constant). The PAL overscan is 72 units now (132 units
  are exactly 312 lines), and the release also simulates the heaviest room on the PAL60 and PAL
  builds.
- **No band or wall colour looks like a door.** The locked door's stripe is bright yellow, and
  some levels used the same yellow for their band (or a near-yellow wall). The generator never
  picks a yellow-family colour for a wall or a band now, and `test_generator.py` fails on one.

## 1.1.0

**New cave kernel, new levels, slower raft**

- New HERO-style gameplay kernel (bank 6): a steadier picture. The frame is now a fixed 280
  lines (NTSC; the VBL window holds the prologue and the overscan window the collision work even in the heaviest rooms), the flicker
  that rolled the picture in rooms with two creatures is gone, and the player art no longer
  repeats rows at band boundaries.
- **The raft is half as fast** (0.75 px/frame at full speed, 0.5 while it takes off), so it
  is possible to step off it where the room asks you to.
- The 20 stages were regenerated with new level rules:
  - vertical rooms vary: the four bands are never all the same width and the top opening
    differs from the bottom one; wide caverns link rooms, so the same shaft no longer
    repeats;
  - hot rock appears from level 5 and as HERO-style barriers (a wide space with narrow,
    offset gaps), not as painted tunnels;
  - a hot band entered from the side leaves 2 open cells to stop in (inertia), and rooms
    with a raft keep 2 free columns under the hot ceiling at each water edge;
  - every room is checked to be crossable (water/raft rooms that could not be crossed are
    gone), and no creature or lamp sits in air the player cannot reach;
  - every level from 5 has a room with two objects.
- Editor: Generate shows a progress bar; the crusher is drawn on both sides of the room
  and animated like in the game; the level map marks it with inward arrows.
- Internal: the shape library moved to bank 7 (2.8 KB window, up from 747 bytes; 121 shapes);
  `build.sh` skips the slow frame-budget simulation unless `FULL_SIMS=1` (releases always
  run it, plus a frame-budget sweep of every room and a frame-stability check of the
  heaviest ones); the bot flies the stage you see in the editor.

## 1.0.2

**Smoother picture, joystick on the title, demo mode**

- Room changes no longer glitch the picture. Loading the next room used to run in the same
  overscan as the frame that crossed the edge, which in heavy rooms ran up to 11 scanlines
  long (rolling/flickering picture). The exit now only records the target room; the next
  frame is a short blank frame that loads the room, then play resumes. In effect: one
  black frame (1/60 s) at every room change, no more stretched frames.
- Finishing a stage no longer stretches a frame either: the checkpoint save and the load of
  the next stage now run in the same short blank frame.
- A bomb explosion is lighter on the explosion frame: the wall holes still appear at once, but
  the enemy kill, the player hit and the boom now follow one frame later (1/60 s).
- Title screen can be driven with the joystick: UP / DOWN change the stage (DOWN goes
  back, both wrap), FIRE starts the game. SELECT and RESET still work as before.
- Attract mode is back: leave the title untouched for 5 seconds and the demo plays on stage 1
  (the logo and credits disappear while it runs): the player walks, drops a bomb, flies out
  over it firing the laser, waits for the blast and ends where it began, in a seamless loop. Any stick move,
  FIRE, SELECT or RESET returns to the title with your stage selection intact (FIRE does not
  start the game on that press). The demo never costs a life and never saves.

## 1.0.1

**Level fixes (the stage was regenerated)**
- Stacked rooms now have EXACTLY matching openings: a hole in a room's ceiling always has
  a hole in the floor above it. Before, a lower room could keep a ceiling opening with
  nothing above it, so the player flew up into a wall and got stuck with his head in it
  (level 18 room 5 and two more pairs on that level).
- A flooded room never has an entry or exit at its bottom: no more flying up out of a
  room below into the water.
- Bats no longer sit in an exit gap or a floor hole, where the player dropping or
  climbing through could not avoid them (level 2 room 2 and others); a room with no
  clear cell stays empty.
- Extra miners keep 24 px away from every enemy (a spider's reach used to cover the
  pickup spot, levels 8 and 16).
- Spiders and moths get their first-move direction (away from walls and screen edges)
  re-applied after the generator's repairs.

**Game**
- Crusher rooms: the crusher now restarts in its retract phase when you enter the room
  (it still moves on arrival), so a player entering from below has the dwell to climb
  through its row.

**Tools**
- Map viewer: the water band covers only the bottom third of the band, like the editor
  and the game.
- `tools/playbot.py`: `--safe` (undo a lost life and retry; what still dies is reported
  as FORCED), `--log FILE` (one JSON record per death with the last 48 frames and the
  facts behind the cause), waits for phase walls and crushers, shoots stationary enemies.
- `tools/stage_check.sh`: run the bot on freshly generated output without touching the
  live stage. `test_generator` pins the exact-opening and water-room rules.

## 1.0.0

**Game**
- 20 generated levels, each a network of mirrored cave rooms; up to three miners per
  level (all must be rescued), power cells, keys and locked doors, bomb-able thin
  walls, hot rock, phase walls, crushers, flooded rooms with a ferry raft.
- Creatures: spider, bat, snake, tentacle, giant moth; they speed up every five
  levels (x1.5 / x2 / x2.5). Spiders and moths start away from walls and screen
  edges.
- Up to eight lives, an extra life every 50,000 points, score up to 999,999.
- Real game over: back to the title with 0 points; clearing level 20 ends the run
  the same way.
- SaveKey / AtariVox support (right controller port): high score, and the level, lives
  and score at the start of every level; the title opens on the saved level and RESET
  resumes it. The title alternates the level number and the high score.
- Crushers can be stood on and bumped from above or below; their sides still kill.
- The start spawn sits exactly on cell 4.

**TV standards**
- NTSC (60 Hz), PAL60 (60 Hz, PAL colours) and PAL (50 Hz, 312 lines, PAL colours)
  ROMs of the same game; `tools/build_variant.sh pal60|pal` builds them.

**Tools**
- Level editor: real sprites, drag & drop of enemies, lamps and the miner with
  wall/seat snapping, facing set from the toolbar button.
- Stage generator with reachability, hazard and first-move rules; `tools/playbot.py`
  plays all 20 levels on the real ROM with the joystick only.
- A large py65 test battery (`tools/test_*.py`), including HUD pixel positions and
  a bit-level SaveKey (24LC256) model.
- `tools/release.py` builds, gates and stamps a release.

**Manual**
- Instruction manual PDF (`docs/manual/`), built from the ROM art, with the story,
  controls, HUD, creatures, objects, scoring and the SaveKey page.

## 0.8b36 and earlier
Internal betas (see the git history).
