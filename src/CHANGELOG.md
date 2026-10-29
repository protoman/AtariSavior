# Changelog

Release versions live in `VERSION` (build.sh stamps them into the ROM, the manual
cover prints them, `tools/release.py` names the artifacts from them).

## 1.0.0 (release candidate 1: `1.0.0-rc1`)

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
