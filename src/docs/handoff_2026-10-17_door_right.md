# Handoff — Phase 5 key + async doors (2026-10-17 session)

## Objective
Finish Phase 5 (`docs/feature_tiles_plan.md`): the TYPE-6 KEY pickup + doors.
The key and doors now work; **one rendering bug remains**.

## What is DONE and verified by the user in Stella
- **Key**: yellow, pickup on touch → no death, the key vanishes, `KeyHeld`
  (`LevelStartRoom $A7` b7) latched; never reappears; door opens on touch.
- **Doors**: BOTH halves now render/collide through the **M1 strip** (yellow
  `COLUP1`, `OvM1Block` collision, key touch-unlock). User: "Looks to be
  working well" — yellow, blocks, opens with the key.

## Commits this session (in order)
- `b3e932b` key pickup + `KeyHeld` + render-skip; parked-object ghost fix
  (bugs #34 — `.SONoObj` now parks `ObjTop = 144 - RoomY`).
- `d90b990` right door (ball strip) touch-unlock.
- `9da4837` `build.sh` regenerates `generated/symbols.asm` (`-s`) every build.
- `ea13f1f` **tests decoupled from live data** — see the rules section.
- `5599ff5`, `50f7435` frozen bank images tracked + `.gitignore` exception.
- `6f13d9c` bank2 `StageBandTab` stages the M1 x-offset by door side.
- `3affbd4` re-freeze after the staging change.
- `162dc3c`, `3e9b1fc` converter + `OvM1Block` collision apply the side
  offset; wall-hide envelope checks both columns.

## OUTSTANDING BUG (the only one)
**A blinking BROWN (wall-coloured) tile, 1 band tall × 1 cell wide, in the
TOP band at the room's opening, in the door room (level 1 room 1 = model 1).
It is NOT part of that room.** User marked it with a green border in
`screenshots/bugs/door_right.png`.

### What is already known
- Door room PF (rendered from the ROM, `generated/models_data.asm` model 1):
  ```
  band0: #########..#########   <- opening at screen cells 9,10 (x72-87)
  band1: #..................#   <- door band (M1 stripe at cell 11 = x88-95)
  band2: ####################
  ```
  `M1TilePF0/1/2 = $f0,$30,$f0 / $ff,$00,$ff / $3f,$00,$ff`
  `M1MetaA = $29` (m1_col+1=2 | $08 door | $01 right), `M1MetaB = $00`.
- It is **not the M1**: band 0 is solid at the M1's column, and the M1 is a
  single full-height latch bar (one x), so it can't paint a 1-band bar at a
  different x.
- `COLUPF` in that room takes `$1C` (yellow, door band) and `$20/$22` (the
  two wall browns) → a BROWN artifact = a **solid PF cell drawn in a
  wall-coloured row**.
- The blink = whatever rewrites that cell (~32-frame phase) — the phase
  blink / the `ColupfBuf` hot pulse / the per-room PF build.

### My probe was NOT faithful — start here
`tools/test_laser_walk_wall.py::load_room(n)` is a HAND-EnterRoom. Adding
`W.MODEL[1] = ("M1TilePF0","M1RoomRects")` lets you load the door room, but
the trace shows `ENAM1 = [0]` and `ENABL = [0]` (no missile enabled) while the
user *sees* the door stripe → **the hand-load does not reproduce the live
room state.** Do not trust conclusions from it.

### NEXT STEP (concrete)
1. Get the player into the door room **through the real `EnterRoom`** (in-game
   / the sim's normal flow), then dump `PF0Buf/PF1Buf/PF2Buf` ($C3-$CB) and
   diff cell-by-cell against the model's rows → find the stray SOLID bit at
   row0/col9 (or its mirror).
2. Find the writer of that cell (the asym/`right` emission, the band-mask/
   `BandTab` path, the `ColupfBuf` stripe, or the phase/hot rewrite).
3. Suspect list (in order):
   - **band_mask regression**: the OLD ball door emitted `MetaA` band_mask
     `$02`; the M1-door form computes `asym = None` → **band_mask `$00`**.
     `BandTab`/`ENABL` derive from it — a real side effect of the conversion
     to review.
   - the `right`/asym-patch emission for a door (`has_right=False`).
   - the `ColupfBuf` per-row "stripe + hot" build for an M1-door room.

## Architecture as it now stands (Phase 5 doors)
- **Both halves use the M1 strip.** A side-0 (right-half) `LOCKED_DOOR` is
  emitted as the right-half M1 door:
  `MetaA = (col+1)<<4 | band_mask | $08 | $01`, `MetaB = $00` (no ball).
  `MetaA` **bit0 is free** for a door (its band mask is `$02` — verify this
  still holds) and means "M1 strip on the RIGHT half".
- **Staging** (`bank2.StageBandTab`): `RectCount ($92)` ← `M1OffTab[MetaA&1]`
  (`$ff` = left `-1`, `$4f` = right `+79`); the M1 block does
  `clc / adc RectCount` (was `sec/sbc #1`) → `M1X = 7+8*col` / `87+8*col`.
  `M1OffTab` is a 2-byte table at the end of `StageBandTab`.
- **Collision** (`bank2.OvM1Block`): same `M1OffTab` offset applied to its own
  `M1X` derivation (it used to re-derive `7+8*col`, which tested the MIRROR x
  → walk-through).
- **`bank2.OvShutBand`** still has the ball-door key hook (`b3`) — now dead
  for doors (they have no ball), kept for the non-door ball strips.
- **Envelope** (`convert_level.resolve_asym_patches`): a right door requires
  BOTH `{col, WIDTH-1-col}` to satisfy the M1 wall-hide envelope (the
  whole-cave `ENAM1` latch leaks through whichever column is open).

## Rules / constraints (do not break)
- **Tests must NOT read live data** (AGENTS, re-asserted 2026-10-17): no
  `src/*.bin`, `src/*.lst`, `src/generated/**`. ROM-byte tests read
  `src/tests/frozen/` (banks+labels) built by `tools/freeze_test_banks.sh`
  from `src/tests/rooms` + `src/tests/generated`. **Re-run the freeze after
  any ROM code change** (it restores live data + rebuilds `savior.bin`).
  Re-added files need `git add -f` (the `*.bin`/`*.lst` ignore still catches
  them; a `.gitignore` exception for `src/tests/frozen/` exists).
- Never read/write `src/TODO.txt`; never delete files without permission.
- bank0 pre-pad headroom = **1B**. The bank2 `StageBandTab` window ends at the
  `$F4C4` pin with ~7B spare after the staging change. The VBL has real margin
  (`sim_frame_budget` stayed OK with +12c) — the earlier "cycle-locked"
  conclusion was WRONG.
- The user's uncommitted work (DO NOT touch): `src/rooms/*`,
  `src/generated/*`, `src/TODO.txt`.

## Useful scripts / state
- `./build.sh` runs: convert → dasm ×4 → `verify_build` → `sim_bomb_fuse` →
  `sim_frame_budget`. Battery: `for t in tools/test_*.py src/tools/test_*.py`.
  At handoff: **build green, battery 38/38**.
- `tools/freeze_test_banks.sh` — re-freeze `src/tests/frozen/`.
- Everything is committed **except** the user's stage data + `TODO.txt`.
