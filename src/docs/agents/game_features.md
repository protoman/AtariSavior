# Game features — raft entity and laser missile

_Per-entity invariants (raft ferry, laser contact missile). Read before touching either._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

### Critical Rule: the Raft Is a Type-7 Entity With a Bank1 Body

The moving, rideable raft (`EnemyType 7`, user spec 2026-10-18) is **not a
tile**: the `RAFT` tile 6 stays a static row-2 platform. The live raft is an
enemy ENTITY whose body is **bank1 `RaftBody` at $FDE3** (bank1's `.ds $FEE7`
fill — dead space), entered from bank0 by **`CallPad_RaftBody`, PINNED at
$F8C0**, which is `sta $1FF5 / jmp $FDE3` (6 bytes in the `$F82C` gap). The
type dispatch was folded into `UEDispatch` (same gap) to pay for it — that is
where the old inline `cmp #ENEMY_TENTACLE/MOTH/SNAKE` chain now lives, and
`test_enemy_movement.py` asserts against `UEDispatch`, not `UpdateEnemies`.

**A cross-bank call needs a byte-identical TWIN — this is the trap that cost a
whole debugging detour.** `sta $1FF5` switches banks, so the `jmp` OPCODE and
its OPERAND are fetched from bank1 at the same address, not from the code that
writes them. `bank1.asm` therefore carries the same 6 bytes at `$F8C0`
(`.ds $F8C0 - *` in both files, then `$8D,$F5,$1F,$4C,$E3,$FD`), whose target
is bank1's own `RaftBody`. Without the twin the tramp jumped into whatever
bank1 held at that address. Guards: `verify_build.check_raft_tramp` (identity +
operand == bank1's `RaftBody` label) and — the case that actually caught it —
the integration case in `tools/test_raft.py`, which drives the REAL path
(`UpdateEnemies` -> `UEDispatch` -> tramp -> bank1 body -> `ReturnPad`); the
unit cases enter `RaftBody` directly and cannot see a broken tramp.

Invariants (each one has a reason, do not "clean up"):
- **The raft's Y is kernel-owned AND tide-driven**: `RaftBody` writes
  `EnemyRamY` = `125 + off` every frame, *after* `RefreshEnemyY`, so the authored
  y is ignored on purpose. `off` is the **tide** (VBL stages `36+off` into
  `CollisionX`; the kernel draws the water strip as the band's last `12-off`
  lines, so the surface line is `132+off`): the raft's bottom row sits exactly on
  the moving surface and bobs with the water it floats on. **Never re-introduce a
  fixed raft Y** — the water surface moves (0-3 lines) and the raft must follow.
  The body mirrors the VBL's triangle (`p = EnemyRamP>>4`: p0-3 down, p4-7 up,
  p8-15 rest) because `CollisionX` is clobbered by the input rect-walks before
  `UpdateEnemies`: **the two formulas must be kept in step by hand** (the tide
  block in the VBL and `.RaftTide` in bank1), and `tools/test_raft.py` pins the
  triangle against every phase.
- **The rider pin runs at `.RaftGo`, not on the move path** (2026-10-22): a raft
  boxed in by solid row-2 cells turns every frame and `.RaftTurn` returns before
  the carry, so pinning on the move path let the rider sink through a stuck
  raft into the water-kill loop. Rising still escapes via the ride gate. Never
  move the pin back into `.RaftRide`; guard `tools/test_raft.py` case 5b.
- **A rider is pinned to the raft's top minus 12** (`113+off`, worst case 116)
  — always clear of the 125 water-kill line — with `vyLo/vyHi` zeroed so gravity
  cannot accumulate into the water. Thrust (vyHi < 0) skips the pin, so the
  player can always fly off. The pin rides the tide with the raft.
- **The raft is a GREEN SOLID block** (`ObjSpriteOffTable[7] = OBJ_SNAKE` +
  `$c4`): a log/trunk floating on the water (user ruling 2026-10-18 — the white
  LAMP art's notch read as odd). Every `ObjSprites` entry is 8x8, so the solid
  block is not larger; it just reads bigger than the notched art, which helps the
  player land on it. `ObjSprites` is exactly 72 B and ends at `$FF00`, so a
  dedicated raft design would need 8 art bytes freed somewhere.
- **The turn-around reads the playfield**, not rects and not data: the row-2
  cell beyond the leading edge, reflect mapping (display col >= 20 mirrors to
  39-col), mask table `RaftCellMasks`. It therefore works in any water span and
  needs no new ZP and no new ROM data. `RaftBitTab` exists because bank1 cannot
  read bank0's `EnemyBitTable`.
- **The enemy record packs `type|dir` in ONE byte (b7 = dir)** — every type
  compare must mask b7 (`UEDispatch: and #%01111111`, `CheckEnemyHit`, and the
  bank2 blast/laser bodies). 2026-10-22: the user's raft had dir=right, read
  `$87`, missed `cmp #ENEMY_RAFT`, and its body never ran (no tide, no motion,
  no rider pin) — the "raft jitter" report. Lamps/rafts carry no direction, so
  the converter emits `dir: 0` for them (keeps the RAW `cmp #LAMP` guards in
  the blast + both laser bodies working). Editor enemy `x` is a DISPLAY COLUMN
  (0..39): `enemy_x_px(c) = c*4 + (4 if c*4 < 11 else 7)` — never read it as a
  pixel X.
- **`EnemyRamD` bits 4-7 are bank1's RoomDarkMask** — never usable as raft
  state (that is why there is no speed ramp).
- Bank1 body rules apply: it must not call a CallPad or any bank0 routine, and
  it uses **bank0's `Temp` ($88)** explicitly — bank1's own `Temp` symbol is
  `$AD` = bank0's `TickCounter`, and writing that would stall the game timer.
- Guards: `tools/test_raft.py` (battery: unit cases + the cross-bank
  integration case), `verify_build.check_raft_tramp` + the CallPad literal
  check, and `bank2`'s blast skip.
- **Inertia (the take-off ramp) is IN** (2026-10-18). State = `PlayerBombs`
  ($F0) spare high bits: b2-0 stay the bomb count, b7 = "ridden last frame",
  b6-b3 = the ramp level stepping every 2nd frame, so the raft leaves at
  1 px/frame and reaches the full 1/2 parity (1.5 avg) after ~30 frames
  (~0.5 s).
- **The raft is a FERRY (user rule 2026-10-18): it moves ONLY while the player is
  over it.** The ride test gates the whole motion block, so it parks the moment
  he steps (or flies) off; parking also clears the ramp state, so the next
  take-off ramps again. Position reset = `LoadEnemyRam` re-copying the record's
  spawn x on room entry (leave/return and it is back at its start). Do not
  "restore" a self-returning raft: an empty one must stay put.
  **Contract:** only `RaftBody` writes b7-3; the bomb code touches b2-0 (its
  `dec` is guarded by a non-zero count so it cannot borrow upward) and every
  reader of the count masks `#%00000111` — the drop guard, bank1's two HUD
  reads, and bank2's `TallySum` (split into the `$F939` slack because the inline
  tally region ends at a hard `org`). `LoadLevel`/`ReloadLevel` write the whole
  byte, which merely resets the ramp.
- **bank1 layout, do not re-shuffle blindly:** `RaftBody` (+ the ramp) lives in
  the `$FDE3` fill and the playfield probe + its two tables (`RaftCellSolid`,
  `RaftBitTab`, `RaftCellMasks`) in the `$F822` fill. The body is 236 B and the
  probe block 51 B; they must stay in separate fills because together they
  overrun `$FDE3` (287 > 260). The probe is reached by absolute `jsr`/`abs,X`
  only, so it can sit in any bank1 fill — but a block whose relative branches
  belong to the body (e.g. `.RaftTurn`, which both arms branch to) must stay
  within 127 bytes of it.
- **The tally frame draws the MINER only** (user 2026-10-18): during the points
  counting (`DropTarget = $FE`) `SelectActiveObject` skips enemies, the raft and
  the bomb, and zeroes `FlickerFrame`. That frame bypasses the overscan, so
  `RefreshEnemyY` never runs while bank1's HUD writes `$E0-$EF` — `EnemyRamY`
  ($E2-$E4) is left holding score-pointer bytes, and anything drawn from it
  appears at a garbage Y (the raft "jumped to the middle of the screen"). Do not
  relax this to "just re-derive Y": the HUD stomp is the invariant, the gate is
  the fix. Guarded by the `tally_gate` case in `tools/test_raft.py`.
- **To PLAY it without touching the live stage:** `bash tools/raft_build.sh`
  -> `/tmp/opencode/savior_raft.bin`, a staged COPY of the stage whose level-2
  water room carries the raft instead of its tentacle (level 2 -> descend from
  the start room). The live stage must not be edited for this: room 1 is at the
  2-object cap (tentacle + the level's miner), and in-place swapping breaks
  `sim_bomb_fuse` (it forces Level 2 and fabricates that room's enemies), while
  every other level-2 slot is unreachable (models 2/3 are solid at display
  cols 0-1 / 38-39 in all bands). The demo build skips the sims (they probe
  live content) and restores + rebuilds the live ROM on exit, like qa_build.sh.


## Critical Rule: The Laser Is a Dumb Contact Missile — Consumed by Walls, Enemies, Lamps

The laser (missile 0) is an 8 px contact missile drawn `[LaserX-7, LaserX]`.
It is **consumed on contact**: a wall tip-cell (`A=2` from bank2
`LaserWallClamp`), an enemy kill (`A=$50`), and a lamp (`A=1`) all reset
`LaserX` to the eye in the same frame. Travel = `±4 px/frame`, capped at
the old sweep extent (`RoomX±20`); past the cap it restarts at the eye.
That is the entire state machine. Fire buzz continues while held (`b7`
gates `UpdateLaserSound`).

**Contact order is tip-ENEMY, then tip-CELL wall, then the body-box loop**
(`LaserTipEnemy` at `$FE00` → `LaserWallClamp` → `LaserClampDone`; 2026-10-20).
The snake lives *inside* its wall by design, so its sprite is drawn over a
solid cell; wall-first made a visible hit do nothing (user report). The
pre-pass awards a hit only to a sprite that **covers the tip pixel**
(`eX in [tip, tip+7]`, `tip = A` right / `A-7` left), which an enemy behind
the wall cannot satisfy — no shooting through walls. Do not "simplify" this
back to wall-first, and do not widen the pre-pass to the `±7` body window
(that would kill through a thin wall). Guard: `tools/test_laser_snake.py`.

**Never add a wall clamp, hold state, suppress bit, or "stop at wall
center" logic.** On 2026-10-10 a wall-center hold clamp was built
(`LaserWallClamp` overwrote `CollisionX` with a cell-center `LaserX`;
`LaserInput` held the beam there) and it produced two user-visible
failures in one session:

1. **Frame lockup** (black screen, stuck buzz — TIA keeps the last audio
   with no CPU): the cap check compared `RectCount`, which `LaserWallClamp`
   clobbers as scratch, so the left-facing `.LaserMiss ↔ .LaserInit` path
   looped *inside one frame* and the kernel never ran.
2. **Uncapped travel**: the same garbage compare let the right-facing
   bolt fly past `RoomX+20` to the next wall.

The hold also forced a cap reorder (cap moved from before-commit to the
miss arm), re-coupling travel/cap/contact — exactly the machine the
2026-10-08 contact-missile redesign deleted. User directive: a contact
missile is **consumed** by walls; it does not stop, hold, or clamp.

**The rearm bit (LaserState b0, `LASER_REARM`) is NOT hold/clamp
state — do not remove it.** Flush hold puts the eye mid-tile (stop
leaves the origin at the rect face; eye = face+4 inside an 8 px tile)
and the +4 step would jump out past the far edge with no candidate
ever inside the wall (pass-through). `.LaserContact` `inc`s b0; the
next held frame `dec`s it and re-runs `.LaserInit` (re-tests the eye —
1 wall-walk/frame, same as open-hold). Regression test:
`tools/test_laser_walk_wall.py` (walk flush, fire, assert consume).

Contracts to keep:
- Contact never reads a register the callee clobbers. `LaserWallClamp`
  scratch = `RectCount`/`FetchPtr`/`CollisionCellY`/`CollisionEndY`/
  `CollisionEndX`; only `CollisionX` is caller input, and it is
  **not modified**. Result protocol: `A=0` miss / `$50` kill / `1` lamp /
  `2` wall, preserved through ReturnPad (`sta`/`rts` keep A/Z).
- `LaserX` changes only via travel (`±4`) or the eye restart. All three
  contact kinds → `.LaserContact` → `.LaserEye` same frame.
- Bank0 `LaserInput` stays after `$FF20` (pre-$FF00 full); do not move
  `SetObjectXPos`, the fold pads, or pinned entries.

Regression test: `tools/test_laser_clamp.py` — stages a synthetic thin
wall (2 display cols) into the PF buffers at the beam rows, holds fire,
asserts the tip is never drawn past the wall and that contact restarts
at the eye with `b1` armed (no suppress). The 2026-10-10 hold clamp was
first written as a *failing* red test against the pass-through bug, then
abandoned for consume — keep this test green against consume semantics.
