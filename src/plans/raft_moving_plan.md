# Raft (moving, rideable) — implementation plan

Status 2026-10-18 (late): **IMPLEMENTED and guarded.** Everything below is the
design as decided; this preamble records what actually landed and where.

As built:
- **bank1 `RaftBody` at $FDE3** (bank1's `.ds $FEE7` fill, ~216 B of dead space
  before the moth-twin pin). Bank0 enters it through **`CallPad_RaftBody`,
  pinned at $F8C0** (`sta $1FF7 / jmp $FDE3`), in the **$F82C pin gap** next to
  `CEH_Key` — the pre-pad END ($FC68) is untouched because that gap is upstream
  of the $F8DD sprite pin.
  **The tramp is a twinned pair:** `bank1.asm` holds the same 6 bytes at $F8C0,
  because `sta $1FF7` makes the CPU fetch the `jmp` opcode and operand from
  bank1. The first version of this feature put the tramp in the gap with no
  twin and would have jumped into bank1's own body bytes; the guard is
  `verify_build.check_raft_tramp`, and the integration case in `test_raft.py`
  is what proves the whole path (the unit cases enter the body directly).
- **Dispatch folded:** `UpdateEnemies`' 18 B tentacle/moth/snake compare chain
  became one `jmp UEDispatch` (+3 B). `UEDispatch` (same gap) re-tests all four
  types with absolute jumps and tail-jumps to the bodies, so stack depth is
  unchanged. Net: **15 B of pre-pad headroom returned**; it pays for the two new
  table bytes (`EnemyColorTable[7]`, `ObjSpriteOffTable[7]`) and the CEH reorder.
- **`CheckEnemyHit`**: the KEY check became `bcc .CEHkill / bne CEHNext`, so
  type 7 is walked over (a platform is not a target) for +2 B instead of +4.
- **`bank2 BombEnemyBlastBody`**: a blast passes through the raft (it cannot be
  destroyed under the rider).
- **Tests:** `tools/test_raft.py` (42nd battery entry) drives the real body —
  float line, both parity steps, all three PF arms *including the mirrored
  right half*, rails, carry + pin + vy reset, thrust escape, empty-raft no-op.
  `test_enemy_movement.py` was retargeted at `UEDispatch` (the dispatch left
  `UpdateEnemies`, so its structure string assertions moved with it).

Two deliberate simplifications, both for review:
1. **Inertia = a one-frame hold on the turn frame.** A true multi-frame spin-up
   ramp needs one byte of per-raft state; the ZP map has none free (EnemyRamD's
   high nibble is bank1's RoomDarkMask — checked in the code, not assumed). The
   user's "inertia" therefore reads as mass on reversal, not an acceleration
   curve. Say the word and I carve a byte and add the ramp.
2. **The raft borrows the snake's art** (a solid 8x8 block). `ObjSprites` is
   exactly 72 B and ends at $FF00, so there is no bank0 room for dedicated raft
   art; a solid block reads as a floating platform. Moving a sprite out (or
   freeing 8 B) would allow real raft art.

Playing it: `bash tools/raft_build.sh` builds `/tmp/opencode/savior_raft.bin`
from a staged COPY of the stage (the level-2 water room carries the raft instead
of its tentacle) and restores the live stage + live ROM on exit. In game: level
2 -> descend from the start room into the water room, stand on a ledge, let the
raft come under you, step off to drop onto it.

Authoring: the editor's `ADD_RAFT` brush now writes a **type-7 ENTITY** (bottom
band, water room, open cell — the same rule shape as the tentacle). NOTE the
object cap: the live water room (level 2 room 1) already holds the tentacle and
the level's miner (2 objects = the cap), so a live raft needs one of those slots
freed. Swapping the tentacle out there breaks `sim_bomb_fuse` (it bombs that
room's wall for the "hole" check), so the live stage was left untouched; author
the raft with the brush wherever a water room has a free slot.

## What exists today (and is NOT a raft)

- `RAFT` tile 6 → `tile_to_char` falls through to `#`, so a raft cell is a
  plain SOLID playfield cell. Useful as a static platform/ledge over water
  (proven: `tools/qa_sweep.py` water room, `tools/test_water_band.py` for the
  kill rule, `src/screenshots/qa/07_water_ledge.png`). It does not move, carry
  or look like a raft.
- `grep -i raft` over `kernel.asm`/`bank1..3.asm` = **0 hits**.
- Editor `ADD_RAFT` paints that TILE (row 2, water room, on AIR).
- Converter validates it: `RAFT` row 2 only, raft models need `bottom_band`.
- `bottom_band` water kills at `RoomY >= 125` and respawns one tile above.

## User spec (2026-10-18)

- Placed **only above water**.
- Player boards it; it **carries him to the other side, then returns**.
- **Fast: 1.5× player speed** (player walk = 1 px/frame → raft 1.5 px/frame).
- **Inertia**: the take-off when the player is on it is not instantaneous.
- Reference: HERO — but `docs/hero/hero_bank0.asm` is a RAW DiStella dump
  (cycle-count comments only, no semantics) and `hero_bank1.asm` likewise, so
  there is no labelled routine to copy. Behaviour must be built from this spec;
  the numeric choice below follows it.

## Decisions taken (review these tomorrow)

1. **The raft is an ENTITY, not a tile** (`EnemyType 7 = RAFT`), because it
   needs a live x + direction. The static `RAFT` tile stays as-is for
   ledges/bridges (existing data keeps working; new moving rafts are entities).
2. **Range is derived at runtime, not stored**: the raft's row-2 cell in front
   of it is tested against the PF (water = open, ledge/border = solid) and it
   turns around at the first solid cell. That makes "travels to the other side"
   exact for any water span with **zero new data** and zero new ZP.
3. **Speed = 1.5 px/frame** via +1/+2 px alternating on the frame-parity bit of
   the existing free-running clock (`EnemyRamP & 1`) — average exactly 1.5, no
   new state byte.
4. **Inertia = a spin-up ramp**: while the player is aboard, the raft ramps from
   0 → 1.5 px/frame over ~16 frames (a counter in the entity's own `EnemyRamD`
   slot, high nibble) instead of snapping to speed. Empty raft moves at full
   speed. (Alternative reading — "the player's take-off has inertia" — is not
   representable: the player has no horizontal velocity state, only 1 px/frame
   steps. Say the word and I will add a vx byte instead.)
5. **Boarding**: while the player's box `[RoomX-7,RoomX] × [RoomY,RoomY+11]`
   overlaps the raft's top row, pin `RoomY` to the raft's top and add the raft's
   per-frame dx to `RoomX` (carry). Stepping off/up resumes normal flight. The
   water below stays lethal, so riding is the only way across.
6. **Placement rule**: entity on model row 2 (`y/4 == 2`) whose spawn cell is
   OPEN, in a room with `bottom_band` (same shape as the tentacle rule).

## The bank0 problem (measured) and the plan

Bank0 is **1 byte** from its `$FC68` limit, and the enemy-type dispatch in
`UpdateEnemies` is a chain of `cmp #T / bne / jmp UE_Body` (5-6 B per type), so
a new type costs bytes bank0 does not have. **Fix (net −15 bytes — measured):** the whole three-type compare chain in
`UpdateEnemies` is tentacle (7 B) + moth (7 B) + snake (4 B) = 18 B; replacing
it with a single 3 B `jmp UEDispatch` frees **15 B**, which pays for the two new
table bytes (`ObjSpriteOffTable[7]`, `EnemyColorTable[7]`) *and* leaves slack.
`UEDispatch` (in the gap) re-tests every type and tail-jumps to its body. The
earlier "net −1 byte" note in this file was wrong — only the snake compare was
being replaced.

**Original single-compare variant (kept for reference):**

- Replace the snake tail `cmp #ENEMY_SNAKE / bne UE_Next` (4 B) with
  `jmp UE_Dispatch` (3 B) and put `UE_Dispatch` in the **`$F82C` pin gap**
  (the same gap `CEH_Key` uses; it had 177 B slack) — that gap is inside the
  bank and *before* the `$FC68` origin, so code added there does not push the
  pre-pad end. `UE_Dispatch` re-tests SNAKE and RAFT and tail-jumps to the
  bodies.
- **Raft body (~60-80 B) also in that gap**: move, PF-edge turn-around, carry +
  pin, spin-up ramp. No ZP byte needed (uses `EnemyRamX/D[slot]`), no new ROM
  data, no bank2/bank3 tramp.
- Guards to add: `verify_build` (the `$F82C` gap still fits; the dispatch jmp
  target is in range), `test_cell_map`-style PF-cell parity for the edge test,
  and a py65 battery test (`test_raft.py`): boards, is carried to the far
  ledge, turns, returns empty, rider stays safe (RoomY < 125), water still
  kills a non-rider.

## Data / editor work (can be done WITHOUT the kernel byte problem)

- `convert_level`: accept enemy type 7; validate row 2 + spawn cell open +
  `bottom_band`; emit it in the existing 4-byte record (type,x,y,dir) — no
  format change beyond the new legal type.
- `verify_build`: same allowlist + rules (it currently allows 0-4 and 6).
- Editor: `ADD_RAFT` becomes an ENTITY placement (like `ADD_TENTACLE`) with the
  row-2/water validation instead of painting tile 6; `EnemyType::RAFT = 7`.
- Tests: converter case (accepted + 3 rejects) and an editor brush test case.

## Why this is not in tonight

The kernel half touches the single most constrained area of the ROM (bank0
pre-pad + the pinned $FC68 origin + the byte-identity-fold guards). Doing it
half-verified overnight, with no way to look at the result in Stella, risks the
whole build for a feature that can be finished cleanly in one supervised pass.
The data/editor half is independent and can land first — say the word and I
start there tomorrow, or I do the whole thing in one go with you watching.
