# Savior Kernel — Architecture

## Key Principle: Always Follow HERO First

**The Activision developers who created HERO are smarter than both of us combined. When in doubt, do NOT come up with "better" ideas. Just follow their path.** Look at what they did, understand why, and replicate it. Every time we tried to invent our own approach (inline bank-switching, NUSIZ copies for HUD elements, custom positioning), it failed or produced poor results. Every time we followed HERO's patterns (fold-pad bank switching, PF-based HUD rendering, SetObjectXPos), it worked.

**When implementing any feature, ALWAYS look at how HERO does it first and follow that approach.** HERO is the reference architecture. If there are multiple ways to implement something, HERO's way is the default choice. Only deviate from HERO's approach if there is a clear technical reason documented in this file. This applies to: rendering, HUD elements, sprite techniques, positioning, collision, sound, and every other aspect of the game.

**When something works in HERO, do NOT tell the user that following that idea will not work.** If HERO uses a technique for a specific feature (e.g., 3 lives, 5 bombs), and it works, then implement it the same way. Do not suggest alternatives or claim the approach has limitations. The fact that HERO does it proves it works.

**Before claiming how HERO implements something, ALWAYS look at the actual code first.** Do not suppose or assume based on partial understanding. Check hero_bank1.asm, the comparison code, and data tables (especially lookup tables like LFF3E for NUSIZ values, LFF6D for positioning, LFF96 for sprite data). If the code contradicts your assumption, the code wins — update your understanding and tell the user what you found, not what you thought.

**Why this rule exists:** In this session, the agent was told HERO uses NUSIZ copies for lives/bombs but kept insisting it was wrong and suggested 13+2 instead. Later found LFF3E=$30,$30,$20,$20 proving HERO uses NUSIZ. The agent was also told HERO uses PF for score but kept suggesting sprites. The pattern: the agent reads a PART of the code, forms an assumption, then defends it instead of reading more. The fix: read the FULL relevant section, trace the data flow, and verify against the actual disassembly before responding.

**What we already use from HERO (keep these, do NOT replace):**
- Reflected playfield (CTRLPF D0=1) — symmetric cave design
- PF registers written ONCE per tile row (TIA persists across scanlines)
- Fixed-time kernel with unconditional inner loop (no per-scanline branches)
- Andrew Davie's session-24 horizontal positioning (SetObjectXPos with div15 loop + page-aligned fineAdjustTable)
- HMOVE applied during HBLANK after RESP0/HMP0 are set
- Joystick read from SWCHA with 4× LSR to shift bits to D0-D3
- Frame timing: 3 VSYNC + 37 VBLANK + 192 kernel + 30 overscan = 262 scanlines
- F4 bankswitching (32K, 8 banks × 4K)

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

### Critical Rule: Reproduce the User's Report Through THEIR Entry Point

**When the user says a tool/feature "does not work", reproduce it with the exact
tool, tab and entry point they use — never a nearby internal function.** On
2026-10-18 the user reported that Delete did nothing on a hcrunch row (they said
it three times, and even warned "assume your tests might fail"). The agent's
regression case called `MapCanvas::ApplyBrushAt` directly with `BrushTool::
ERASE_AIR` (the empty brush) and passed — while the user was clicking
`BrushTool::DELETE_ENTITY`, a different tool handled by a different branch that
only erased entities. The test was green, the user's click was a literal no-op,
and the agent spent a session doubting a correct report.

Rules:
- **A green test that does not use the user's path proves nothing about their
  path.** Name the tool/tab/entry point in the test (here: `DELETE_ENTITY`, the
  Level tab) and drive it the way the UI does.
- **The user's observation outranks your model of the code.** If they say it
  fails and your reading says it cannot, your reading is incomplete — find the
  other branch. "I checked and it should work" is not an answer.
- Do not ask them to re-verify something they already verified; reproduce it.

### Critical Rule: Red Test First — Reproduce, Then Fix

**Before fixing a bug, write a test that FAILS because of that bug, run it and
see it red, and only then touch the code. The fixed code must turn that same
test green.** (User rule 2026-10-23.) A fix without a red test is a guess: it
cannot show the bug was real, and nothing stops it from silently regressing.

- **Prove the test is red on the unmodified build** — run it, read the failing
  assertion, and keep that message naming the actual symptom (e.g. "right-side
  locked door did NOT block"). A test that passes before the fix is testing
  something else.
- **Drive the real routine** (`tools/test_m1_door.py` calls the frozen
  `OvM1Block` with a staged room; `test_jet_clamp.py` calls the real
  `UpdateP0Vertical`) — not a re-implementation of the algorithm, or the test
  can only ever agree with itself.
- **Order that works with the frozen banks:** re-freeze FIRST
  (`tools/freeze_test_banks.sh`) so the frozen image carries the buggy code,
  watch the test go red, then fix, rebuild, re-freeze, watch it go green. A
  stale frozen image makes the red step meaningless.
- Keep the test afterwards as the regression guard, and keep the bug's date,
  symptom and root cause in its docstring (see `test_m1_door.py`,
  `test_jet_clamp.py`, `test_laser_clamp.py`).

### Critical Rule: the LIVE Stage Is the User's — Never Edit It

`src/rooms/`, `src/rooms/models/models.json` and `src/generated/` are the user's
stage. **Do not edit them** (user rule 2026-10-18: "when needed I'll edit the
rooms myself, you should not worry or depend on it"). They change under the
agent's feet, and several gates deliberately pin live content:

- `sim_bomb_fuse` FORCES Level 2 and fabricates that room's enemies (it needs
  room 1's wall rects for the bomb-hole check) — any edit to that room breaks it.
- `sim_frame_budget` / `qa_*` probe live rooms for their scenarios.
- The frozen test banks are built from `src/tests/rooms`, not from the live stage.

So when a feature needs stage data (a room, a spawn, a demo):
1. **frozen/test-owned copies** in `src/tests/` for tests (`tools/freeze_test_banks.sh`
   rebuilds the frozen banks from `src/tests/rooms`), and
2. **a staged demo build** for anything playable — copy the stage, edit the COPY,
   build, restore (`tools/raft_build.sh` is the model: `SIM_PY=/bin/false ./build.sh`
   + a `trap restore EXIT` that rebuilds the live ROM).
If a feature truly needs live stage content, ask the user — do not add it
unasked (the raft's demo ROM exists for exactly this reason).

**Never `git add -A src`.** On 2026-10-18 a blind `git add -A src tools` committed
a REVERTED `src/rooms/level_002.json` — the user had replaced that room's tentacle
with the raft, and the staging scripts (`freeze_test_banks.sh`, `raft_build.sh`
both copy rooms/ to a temp dir, replace it, then restore) left the tree at an
older state that got swept in. The user's edit had to be rebuilt by hand.
Rules: stage `src/rooms` and `src/generated` explicitly and separately, and
always run `git diff --stat -- src/rooms src/generated` before a commit that
touches them. If a freeze/demo script was interrupted, verify the live stage
against the user's intent BEFORE committing anything.

**What we have NOT yet implemented from HERO (implement these next):**
- 13+2 sprite technique for HUD text/indicators (P0×3 + P1×3 + ball = 13 character columns)
  → score DOES use P0×3+P1×3+VDELP (docs/font/48px_score_skill.md); ball/extra columns not yet
- Per-scanline PF lookup tables for cave patterns (HERO uses 8-entry tables at $DC6A/$DC6C/$DC77)
- Second kernel for HUD rendering (HERO calls JSR $DE00 after cave kernel)
  → effectively done: bank1 HUD band runs via the $FC68 fold pad after the cave kernel
- VDELP0/VDELP1 vertical delay pipeline for multi-sprite text → done for score (bank1)
- Font data loaded into zero-page RAM during VBLANK for fast (zp),Y access
  → partial: digit ptrs live in ZP (scorePtr1-6), glyphs stay in ROM ($FD00)
- Ball (ENABL) for HUD indicators

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

## Critical Rule: src/ Is the Project Root — Never Anchor to the Parent

**The project root is `src/` (the agent's working directory). All relative
paths the user gives are relative to `src/`.** Never resolve a path against
the parent folder (`.../ai_savior/`) and never search there unless the user
explicitly says to look at the parent folder.

- User path `screenshots/assymetric/x.png` → `src/screenshots/assymetric/x.png`.
- If a file is "not found", re-anchor to `src/` FIRST before widening any
  search — do not start globbing/find from the parent.
- The env's "workspace root" (`.../ai_savior/`) is a git/tooling anchor,
  NOT the project root. Git commands (`git status`, `git add`) still run
  from wherever the repo lives, but file reads/writes/globs stay in `src/`.
- **User counts rooms/levels from 1** ("level 1 room 2" = `room_id` 1 /
  model 1 in 0-based data, file `level_001_room_002.txt`). When talking
  to the user, always use 1-based room/level numbers.

**Why this rule exists:** 2026-10-06 — the user's screenshot path
`screenshots/assymetric/bug_adjust_collision.png` was resolved against the
parent folder, failed, and the subsequent find/glob widened from the parent
too, missing `src/screenshots/` entirely. The lesson: one wrong base path
poisons every fallback search built on it.

## Critical Rule: NEVER Delete Files Without User Permission

**Deleting files (rm, git rm, moving files to /dev/null, or any operation that removes a tracked or untracked source file) is FORBIDDEN without explicit user approval.** This includes:
- Source files (.asm, .py, .cpp, .hpp, .json, .txt, .sh, etc.)
- Generated files (if they are part of the build pipeline and re-creatable, ask first)
- Config files, build scripts, tool scripts

**What to do instead:** When a file needs to be removed or replaced, tell the user what you want to delete and why. Wait for explicit confirmation. If you accidentally created a file that shouldn't exist, explain which file and ask to delete it.

**Why this rule exists:** On 2026-09-22, the editor source files (MainWindow.hpp, MainWindow.cpp, MapCanvas.hpp, MapCanvas.cpp, LevelData.hpp, DataSerializer.cpp) were lost because they were never added to git, then overwritten without warning. The user's work was destroyed. This must never happen again.

## Critical Rule: NEVER Read or Write TODO.txt

**`src/TODO.txt` is the user's private file. Never open it, grep it, search it, or write it.** Do not use `cat`, `Read`, `Grep`, `Glob` matches, or any tool that would expose its contents. Exclude it from searches. When a commit includes it (user's instruction), `git add TODO.txt` blindly — never inspect contents.

**Data rule:** measurement/debug values come ONLY from screenshots the user provides or from code the agent verified directly. Values that leaked from TODO.txt are forbidden and must be discarded.

**Why this rule exists:** On 2026-09-27 a grep over `src/` surfaced TODO.txt lines containing Stella INTIM readings; those values polluted the timing analysis. The user's TODO file is off-limits — full stop.

## Rule: Estimate First — 20% Timebox on "Can You Do X?" Questions

When the user asks "can you do X in T minutes?", the answer must come from
a **fast mental estimate**, not from investigation. If deciding takes more
than ~20% of T (e.g. >2 min for a 10-min task), the answer is already **NO**
— say NO immediately. Spending the budget on wondering whether you can is
itself the failure.

**Why this rule exists:** 2026-10-06 — user asked "fix frame regression in
10 minutes max?"; the agent started investigating instead of answering, and
had to be told three times to stop.

## Rule: Session Budget Discipline

The model context window is fixed and the ENTIRE conversation (system prompt +
`AGENTS.md` + every tool output) is re-sent each turn. Long sessions do not
"get shorter" — the remaining working budget shrinks with every full-file read,
listing dump and rebuild log. Treat context like the ROM budget: spend it
deliberately.

- **One chunk per session.** Start by reading the current plan/handoff
  (`docs/*_plan.md`, `docs/handoff_*.md`) and a 5-line state note — never
  re-derive what is written down.
- **Read by index, not by file.** `codegraph_explore` first; `grep` with tight
  patterns for a specific symbol; `sed -n 'a,bp'` for a slice. Full-file reads
  of `kernel.asm`/`bank2.asm` (1000+ lines) are a last resort.
- **Filter every command's output**: `./build.sh 2>&1 | grep -E
  "error|Done|sim_|verify_build"`, `tail -5` on sims, `grep -c` for counts.
  Never paste a full `.lst` or a full battery log.
- **Commit after each chunk** (build + both sims + battery green), with the
  chunk name in the message, so a cut-off session always leaves a green tree.
- **Update the size ledger in the same commit**: run
  `tools/rom_size_report.py --md` and paste the table into the active plan
  (per-bank code/data/used/free + level-data total). The ledger is the tripwire
  if a later chunk misbehaves.
- **Re-freeze the test banks** (`tools/freeze_test_banks.sh`) before trusting a
  battery run after ANY bank code change — the frozen images otherwise keep
  executing the previous build and a green battery proves nothing.
- **Budget floor:** when roughly a fifth of the session is left, stop starting
  new edits. Finish/verify the current one, commit, and write the exact next
  step (design, addresses, blocker, files) into the plan/handoff.
- **Never leave the tree broken**: a reverted attempt + a documented design is
  worth more than a half-applied refactor. Record what was learned (the failing
  sim output, the exact stack/address symptom) in the plan.

**Why this rule exists:** 2026-10-19 — a long session (crunch unification +
bank3 level-data move) repeatedly ran out of budget mid-refactor; the bank3
move had to be attempted twice and reverted twice, and the handoff had to carry
the design that the session could no longer execute.

## File-Format Changes Require Data Migration

When changing a serialized or generated data format, update all existing project data and its generators in the same change. Preserve compatibility with older files through an explicit version/default migration, or migrate those files before requiring the new format. Verify both legacy loading and new-format round trips; never leave checked-in data behind the code's schema.

**Async walls live on the ROOM (2026-10-17 move — do NOT put them back on the model).**
`room.asym_patches` = `[[row, col, tile, side?], ...]` (ball/M1 strip, door; ≤2,
both sides may differ) and `room.feature_cells` = `[[row, col, tile], ...]`
(P/V/C = 10/11/12, row 1 only, one kind per room). The model keeps only the
SHAPE (`tiles` = air/wall/hot/raft + `mid_band_type`); a model that still
carries `asym_patches` or a P/V/C grid tile is STALE and `convert` hard-fails it
with a migration hint. Why the room owns it: one model shape is reused by rooms
with different async, and the editor edits the room, not the model.

Consequences that are easy to get wrong:
- **A room points at its shared MODEL SHAPE; async rides a per-level EXTRAS
  stream** (C5 2026-10-20). The shape block is EXACTLY the 3 row-pool indices
  (C11 2026-10-21, `LEVEL_FORMAT = 6`) — both the `TilePF0+9/+10`
  MetaA/MetaB contract AND the per-shape hot stream are RETIRED. A room with
  the shape byte's b7 set carries an extras record (selected by the counts
  byte's b5-0 ordinal): `flags (n_patches b1-0 | n_features b5-2)`, `MetaA`,
  `MetaB`, 1 B/patch (`band b7-6 | side b4 | col b3-0` — the DRAWN band, not
  the authored row: a 3-row model's row 2 is band 3 and band 2 is the AIR
  pad), 1 B/feature (`kind
  b7-6 | col b3-0`), then — feature rooms only — the room's FEATURE-record
  stream (`count` + 5 B records, all b7-set classes: `$80` phase cell / `$82`
  hcrunch prefix). Hot cells are NOT records: see the hot bullet below.
- **HOT DEATH IS PF-DERIVED** (C11 2026-10-21): convert promotes EVERY row-1
  wall cell of a `mid_band_type=1` model, so a hot shape's hot cells ARE its
  solid row-1 PF cells, and the C4 bomb punch clears PF cells — a blasted
  (thin) parent cell stops being hot with no record and no parent gate.
  `HotOverlapBody` (bank3) sweeps the player box's display columns over
  `PF0Buf + 1 + ColOff[X]` gated by `MetaB` b6 (hot rooms only; it only runs
  on a cell-walk hit). The one PF-OPEN hot cell — the M1 block on the hot band
  — is staged by `ExtrasLoad` in `RoomM1Hot` (`$AF`, col+1) from the room's
  side-1 row-1 patch and dies with the strip (`EnemyDeadMask` b4). Hot cells
  never exist on rows 0/2. Do NOT re-introduce per-shape hot records: the
  shape block is 3 bytes and `verify_build.check_shape_blocks` hard-fails a
  count byte / `RoomRects` label / 5 B record.
- **Band gates: MetaA b0-2 + MetaB b4, and the collision pack has FOUR bits**
  (2026-10-24). `BandTab` ($CF-$D2) is one $ff/$00 ENABL byte per band, staged
  by `B3StageBand` from the 4-bit mask through `BandTpl` (16 rows x 4 B).
  `MetaA` b3 is the left-door flag, so band 3's gate lives in `MetaB` b4; the
  retired phase-1 bridge (`BandTab+2` -> `BandTab+3`) lit the ball in the AIR
  band of a migrated room — never re-add a mirror. The VBL pack `$8F`
  carries b0-3 = the four gates (b3 doubles as the M1-present flag when NO
  band is painted, so an M1-only room still packs nonzero), b4-7 =
  right_col+1; `OvHead/OvTail` are the 4-band pairs `15,14,12,8` / `1,3,7,15`
  in BOTH bank0 and bank2 (a 3-entry copy made a band-3 strip pass-through).
  Guards: `tools/test_async_band3.py`, `tools/test_phase3_ball.py`,
  `tools/test_cell_map.py` (asym sweep covers band 3).
- **The editor authors one ROW PER DRAWN BAND** (2026-10-24): `hero::kRoomHeight
  = 4`, so `models.json`/`stage.json` may carry 4-row models (10x4). The
  converter accepts BOTH: 3 rows = the legacy grid, expanded to
  `[r0, r1, AIR, r2]` by `convert_room.band_map()`; 4 rows = one row per band
  (identity). `DataSerializer::MigrateToFourBands` does that same expansion on
  LOAD, so opening an old stage re-saves it 4-row, and it moves room patches
  authored on the old bottom row (row 2 -> row 3). The E2 QA generator
  (`Build20LevelStage`) still speaks THREE bands via its own `kGenRows` — its
  plans, exits and QA expectations are 3-band, and its models migrate on load
  like any legacy file.
  **M1 strip caveat when a 3-row stage becomes 4-row:** the async M1 strip is
  a WHOLE-CAVE latch (`ENAM1`), so its column must be wall-or-patched in EVERY
  band. The old bottom row (the floor) hid it in band 2; the inserted AIR band
  does not, so `resolve_asym_patches` now hard-fails with "band 2 col N is open
  air and has no patch" and the editor prints the same warning on migration.
  Fix per room: wall that cell, or extend the strip with a side-1 patch for
  band 2. Do NOT auto-wall it in the migration — a wall cell is band-tall and
  would split the corridor for the OTHER rooms sharing the model.
- **The shape's PF bytes are a ROW DICTIONARY** (C3 2026-10-20): each band is a
  1 B index into the global `RowPoolPF0/1/2` columns (3 B per DISTINCT row,
  emitted once in `models_data.asm` with `LEVEL_ROW_COUNT`). The indices sit at
  `block + 0..2` (C11) and band 1's b7 = the model's `mid_band_type` hot flag,
  so `LEVEL_ROW_COUNT` must stay ≤ 128. The loader expands them into `PF0Buf`
  (`lda RowPoolPFn,X / sta PF0Buf+3n,Y`). Never emit raw PF into a shape:
  `verify_build.check_shape_blocks` hard-fails it.
- **The level-data subsystem is SPLIT across two banks (C7 2026-10-20)** and
  the split is the invariant: a routine may only dereference data in ITS OWN
  bank. **bank2 = the ROOM half** (`LevelDataTable` entries, the per-level
  `RoomShapes`/`RoomPositions`/`RoomCounts` block + flat `EnemyDataTable`) with
  its walkers `EnterRoomB2`, `ExitScanB2`/`ExitDirB2` + the four exit bodies,
  `LoadLevelB2`, `MothRoutine`, `LaserWallClamp`/`LaserHitTestBody`,
  `BombEnemyBlastBody`. **bank3 = the SHAPE half** (shape blocks + row pool +
  `LEVEL_ShapeTable` + the async extras streams + the `LevExtrasLo/Hi` base
  table) with its walkers `B3RoomBlocks`/`ExtrasLoad`, `PhaseBlink`/
  `BuildColupF`/`BCFDarkRun`, `HotOverlapBody`/`HOVFeatEntry`,
  `B3StageBand`, `PhHcrEntry`/`CrPfx`/`HcrClock`.
- `bank3.B3RoomBlocks` (PINNED at `$F453`) expands the shape rows, then either
  derives `MetaA=0 / MetaB=$40*hot` (no extras; the hot flag is band 1's index
  b7, C11) or tail-jumps to `ExtrasLoad`, which indexes bank3's
  `LevExtrasLo/Hi[Level]`, walks the stream by the room's 1-based ordinal, ORs
  the side-0 patch rows into MetaA, stages `RoomM1Hot` from a side-1 row-1
  patch, sets the feature PF bits, and repoints `RoomRectsLo/Hi` at the
  extras FEATURE-record stream (`RoomNoStream` when the room has none).
  `B3StageBand` still reads only the STAGED `$99/$9A` pair, so the runtime
  contract is unchanged.
- **The ONE cross-bank call of the room load**: `EnterRoomB2` stages the raw
  shapes byte in `RoomPF0Lo` ($99, loader scratch) + the extras ordinal in
  `LevelConnSpare` ($A2), then executes `sta $1FF7` at `$F450`; the opcode
  fetch at `$F453` comes from bank3, so `B3RoomBlocks` MUST stay pinned there
  (`verify_build.check_bank3_entry`). There is no return pad and no twin: the
  shape step runs **last**, so bank3's chain ends in **bank3's own
  `ReturnPad`** (`sta $1FF4` at `$FBF8`, the `rts` served by bank0) — 0 extra
  stack pushes, which is what keeps `sim_bomb_fuse`'s SP floor.
- **Two traps the C7 order creates** (both cost a debug pass): `ExtrasLoad`
  runs AFTER `LoadEnemyRam`, so it must NOT use `EnemyDataLo` as scratch (its
  feature counter is `EnemyIndex`); and the joystick-shadow refresh moved into
  bank3's `ERLoadDone` because every shape walker uses `Temp` as scratch while
  bank0's input block keeps reading `Temp` for the rest of the frame (the
  2026-10-20 "eye snaps right" lesson).
- The extras records are emitted into `generated/level_00N_extras.asm` (bank3,
  with `levels_extras.asm` as the per-level base table), NOT into the level
  table file: a feature room's FEATURE-record stream lives inside its record
  and the VBL walkers read it in-bank. `emit_spills` (bugs.md 27b) places only
  THIS
  stage's `level_00N_rooms.asm` files (never a glob — a leftover tree from
  another stage would reference shape labels that no longer exist), and
  `levels_index.asm` owns the FIRST window in source order (`spill_F307`)
  because it defines `LEVEL_FORMAT` + the `SHAPE_*` EQUs the room tables use.
  Net-new level data must never be added inside `level_00N_rooms_data.asm` —
  that file is invisible to the spill accounting.
- bank2's level-table windows are the six freed shape clusters plus `$F700`
  (`_SPILL_SLOTS` in `convert_level.py`, 2 323 B; bank2.asm carries the
  matching `.ds` pads). bank3's level data uses **TWO windows** (C12
  2026-10-21): extras (async streams + base table) at `$F010-$F44F` (1 088 B,
  `_BANK3_EXTRAS_SLOT`) and shapes (blocks + row pool + address table) at
  `$F5CC-$F8B6` (747 B, `_BANK3_SHAPES_SLOT`), each capacity-checked by
  `emit_spills`; the shape include list is `spill_bank3_shapes.asm`. The
  shapes window starts where `ERLoadDone` ends — do NOT lower the `.ds` target
  below `*` (DASM `Origin Reverse-indexed`; the old `$F5BF` figure was a stale
  binary measurement).
- The generator has a declared shape budget (`kShapeBudget` in
  `DataSerializer.cpp`, currently 56, two-pass: base library first, extra
  archetypes only if the base fits). `test_generator` gates the shape count,
  a >= 64 B slack floor in every window, and the hot-start drop column
  (HotDrop keeps row-1 cell 4 open).
- `emit_spills` slot starts must be the REAL bank2 include site: `spill_F767`
  begins at `$F700` (bank2 `.ds $F700 - *`), worth 103 B that the old
  `$F767` start hid.
- **Never add `n` twice to a 16-bit base with two `adc n`s**: the first carry
  is folded into the second add and lost when the second does not overflow, so
  `base + 2n` points one page low for some room counts (2026-10-20: level 14 of
  the 20-level stage read `EnemyCount=0`; fixed by computing `2n` with `asl`
  first in `EnterRoomB2` and `ExtrasLoad`). The legacy 4-level stage never hit
  the overflow, which is why it survived for so long — guard tests that walk
  every level of the live stage (`test_band_restage`).
- `resolve_asym_patches(model, room, left_rows)`; `room_door_flag` /
  `room_m1_door_flag` / `async_kinds(room)` replaced the model-level helpers.
  `room_extras()` (convert_level) is the single extras emitter; the loader and
  `verify_build` both re-derive its bytes from the JSON, so a drift is red.
- `RightPF0/1/2` + `RightRects` are GONE (no reader since C4) and
  `dedupe_room_blocks` is retired — there are no per-room blocks to dedupe;
  byte-identical MODELS are still emitted once each (the C3 row dictionary is
  the future fix for that).
- ROM-byte tests read FROZEN banks AND frozen labels (`src/tests/frozen/`) —
  never frozen bytes with live `src/bank2.lst` labels (that mismatch silently
  reads the wrong block; it bit `test_band_restage`, `test_bomb_strip` and
  `test_phase3_ball` on the day of the move).

## Overview

A from-scratch Atari 2600 game kernel modeled after Activision's HERO (1984). Built
in `src/` as a standalone project with no dependencies on the older prototype.

## ROM Layout

- **32K ROM** — F4 bankswitch (8 banks × 4K each)
- Bank0: `kernel.asm` — main game code, cave kernel, player logic
- Bank1-3: stubs (switch to bank0, ready for future expansion)
- Output: `savior.bin` (32K)

**Standing rule (2026-10-14): do NOT add new data or features to bank0.**
Bank0 pre-pad headroom is ~1 byte (build warning `ends $FC67, limit $FC68`)
and the fold pads are pinned — every addition forces a reshuffle or a cut.
New ROM content goes to bank2's table slots ($F307/$F453/$F8B7/$F9D9/$FCB8/
$FF59/$FE9C/$F700, `_SPILL_SLOTS`) or bank3's free tail; a smaller leaf helper
can also go after bank0's pads. If a change seems to need bank0 space, move a
leaf helper after
the pads or into bank2 first; only touch bank0 for in-place edits to existing
code. This is why we keep extracting routines out of bank0 every time it fills.

*Reinforced 2026-10-16:* bank0 is now **100% allocated AND byte-identity-frozen**
(pre-pad 1B; post-pad pinned at `$F8DD`/`$FDDA`/`$FDE1`/`$FC68`/`$FF00`).
Adding even 2 bytes breaks `verify_build`'s twin pins. A modest feature (the
Phase 8 respawn hover, ~20B) could not be added at all. **Default answer to
"needs bank0 space" is now: move a chunk OUT first.** Survey + §
"Movable chunks" in `plans/bank0_space_plan.md` (title subsystem ~390B cold →
bank2 is the prime target). Cross-bank catch: bank0 cannot read bank1/bank2
data by `abs` — moving a table requires moving its reader (or a fold) too.

### F4 Bankswitching

| Bank | Address Range | Power-up | Contents |
|------|--------------|----------|----------|
| Bank0 | $F000-$FFFF | — | Game code + cave kernel |
| Bank1 | $F000-$FFFF | — | HUD band, title, sound, fonts, raft body, bomb punch |
| Bank2 | $F000-$FFFF | — | Room half of the level data (entries, room tables, enemy records) + its walkers, moth, LWC/LHT, blast, exits, `LoadLevelB2`, 8 table slots |
| Bank7 | $F000-$FFFF | Yes | Shape half (shape blocks, row pool, shape table, extras streams) + its walkers, boot stub + reset vector |

Bank select (F4): `STA $1FF4` (bank0), `$1FF5` (bank1), `$1FF6` (bank2),
`$1FF7` (bank3), `$1FF8` (bank4), `$1FF9` (bank5), `$1FFA` (bank6),
`$1FFB` (bank7). Power-up bank is **bank7** (F4 reads the reset vector from
the LAST bank); its 5-byte stub is `lda #0 / sta $1FF4` and the fetch after
it comes from bank0, whose $F005 is `jmp GameStart` (byte-identical hand-off).
banks 4-6 are empty 4K windows (`src/bank4..6.asm`); bank7 holds the stub +
vectors. F4's hotspot-mirror zone is **$FFF4-$FFFB** — $FFF4-$FFF9 stay fill;
$FFFA/$FFFB carry the NMI vector and are never read (no interrupts).

## Frame Timing (262 scanlines @ 60Hz NTSC)

| Section    | Scanlines | Notes |
|------------|-----------|-------|
| VSYNC      | 3         | Sync pulse |
| VBLANK     | 37        | Game logic + sprite positioning |
| Kernel     | 192       | 144 cave (4 bands × 36) + 48 HUD band |
| Overscan   | 30        | Input + movement |
| **Total**  | **262**   | NTSC standard |

## Memory Map

### Zero-page ($80-$FF, 128 bytes)

**Authoritative map: `docs/zp_layout_skill.md`** (machine-checked every build
by `verify_build.check_equ_sync` — cross-bank hand-copy drift + stomp-zone
rule). Do NOT copy address tables from this file; it holds only the
load-bearing invariants:

- Sequential `byte` block runs `$80-$BB`; `$BD+` are explicit EQUs.
  **No free sequential byte** — inserting one shifts everything after it
  (bank1/bank2 hand-copied EQUs break silently without the guard).
- **Stomp-zone rule:** bank1 HUD writes `$E0-$EF` every frame; persistent
  bank0 state must live below `$E0` (exceptions: `ColupfBuf` `$E7` rebuilt
  every VBL, `EnemyRamY` `$E2` window-ordered; staged bytes like `FetchPtr`
  `$E5` OK). Violation symptom: field zeroed/changed every HUD frame.
- `$F8-$FF`: stack mirror only — never a buffer (pushes write down into it;
  measured gameplay min SP `$F9`, guard ≥`$F8`).
- `$81` RoomY, `$88` Temp, `$B5` BombPacked, `$F6/$F7` BombX/BombTimer —
  the crash-prone names referenced throughout the lessons below.

### TIA Registers (write-only at $00-$2F)

Key registers used:
- `$1B` GRP0 — Player sprite graphics
- `$1C` GRP1 — Object sprite graphics
- `$0D/$0E/$0F` PF0/PF1/PF2 — Playfield registers (persist across scanlines)
- `$08` COLUPF — Playfield color
- `$09` COLUBK — Background color

### TIA Read (active-low joystick at $0280)

- D4 = Up, D5 = Down, D6 = Left, D7 = Right (0 = pressed)

## Kernel Architecture

### Key Principle: Fixed-Time Inner Loop

The kernel's `.Line` loop must execute exactly the same number of cycles on
every scanline to avoid flicker. The2600 TV frame is 262 scanlines at 60Hz;
each scanline is 76 CPU cycles. If the loop exceeds 76 cycles on any
scanline, WSYNC stalls until the NEXT scanline, making the frame longer.

### MANDATORY: Budget scanlines BEFORE writing code

**Every `sta WSYNC` in the HUD band costs exactly 1 scanline.** The HUD band is 48 scanlines (144-191). Before writing any HUD code, write out the full scanline budget:

```
; Example budget (must sum to 48):
; Timer bar:     6 scanlines
; Gap:           1 scanline
; Lives (3):     9 scanlines (3 per icon)
; Gap:           1 scanline
; Bombs (5):    15 scanlines (3 per icon)
; Gap:           1 scanline
; Score:         5 scanlines
; Pad:           9 scanlines
; TOTAL:        48 scanlines
```

**If the budget exceeds 48, reduce BEFORE coding — not after.** The frame will crash with a grey screen if the HUD band overflows. Each icon rendered on its own scanline (for RESP positioning) costs 3 scanlines: 1 WSYNC in SetObjectXPos + 2 WSYNCs in RenderLifeIcon. Multiply by icon count and add gaps.

### MANDATORY: Keep the kernel entry WSYNC-anchored (bugs.md #29 Class C)

**Two re-anchor `sta WSYNC`s hold the picture still — never delete them, never add cycle-variable code around them:**
1. `StartFrame`: `sta WSYNC` BEFORE `lda #2 / sta VSYNC` (overscan-end tick quant → VSYNC phase-lock).
2. `.WaitVBLANK` exit: `sta WSYNC` while VBLANK is still ON, before `sta VBLANK` off (VBL tick quant → kernel-entry line-lock; blank line, invisible).

**Why:** `TIM64T` ticks every 64 cycles; the `INTIM` poll exits up to 63c late; the band-0 `.Row` setup WSYNC gap is ~75c — without the anchors the kernel start line straddles the 76c boundary and oscillates ±1 with tick phase = whole-screen jitter (62/58 two-class split, 2026-10-11). **WSYNC-count guards cannot see this family** — counts stayed constant through the whole bug. Oracle: Stella `logTrace` SCN at the first kernel WSYNC must be a SINGLE value across ≥100 frames, and the pixel detector's seam rows must form ONE signature across ≥120 frames (`tools/measure_bar_cycles.py` + `stella_shots` row-probe recipe).

**Each anchor costs +1 wall-model line** — when adding one, update `sim_frame_budget`'s 265.0 target, `test_phase3_ball`'s {264,265} set, and any comment citing the frame total in the SAME change. Full lesson: **Timer-quantization phase straddle** in Lessons Learned below.

### Structure (HERO pattern)

```
.Row (×TILE_ROWS=4): PF setup — write PF0/PF1/PF2 ONCE per 36-line band
                   (TIA registers persist — no need to rewrite per scanline)
.Line (×36):      Sprite rendering — the tight inner loop (the bottom band
                   runs 24 bodies + the 12-line .WaterRow strip)
                   Unconditional: same instruction stream every scanline
```

*(Era note: "12 tile rows × 12 scanlines" became 3 bands × 48 lines on
2026-09-28 (`LINES_PER_TILE=48`, `YToRowTable = line/48`) and 4 bands × 36
lines on 2026-10-23 (`CAVE_LINES = 144`, `YToRowTable = line/36`). Band
geometry, the 4-band PF stride (`$CC-$DF`), `BandTab` and the extra TIA x
values live in `plans/band4_plan.md`; the data format is `LEVEL_FORMAT = 7`
with one shape row per drawn band.)*

### Per-scanline cycle budget (76 max)

Our `.Line` loop worst-case:

| Section        | Cycles (off-screen) | Cycles (on-screen) |
|----------------|--------------------|--------------------|
| GRP0 check     | 16                 | 19                 |
| Loop control   | 16                 | 16                 |
| **Total**      | **32**             | **35**             |

Both well within 76-cycle limit. No flicker.

### PF Write Strategy

PF registers (PF0/PF1/PF2) are written ONCE per band in `.Row`.
The TIA persists these values across all 48 scanlines of the band.
This saves three abs-stores per scanline for the whole cave
(144 lines × 12c ≈ 1.7Kc of VBL/kernel time).

## Build

```bash
./build.sh          # builds savior.bin (32K, F4)
```

Requires: `dasm` (6502 cross-assembler)

### DASM Assembly Gotchas

- **`=` definitions MUST start at column 1** — DASM treats indented `=` as
  unknown mnemonics and silently fails. Example: `    Temp = $AD` fails but
  `Temp = $AD` works. This caused bank1 to silently use stale .bin files.
- **ALWAYS verify bank1.bin is actually rebuilt** — if DASM fails but the
  build script catches the error (via `|| echo`), the old .bin is reused.
  Check file timestamps after building.

## Testing

### Test stage data — frozen test-owned copies only (user rule 2026-10-14)

**Tests must never read live `src/rooms/`, `models.json`, or `generated/`**
(models, level jsons, generated slices) and must NOT gate on
ROM↔fixture equality — the user keeps editing stages, so live-coupled
tests break on every edit. **Frozen test copies live in `src/tests/`.**
Test scripts stay where they are (`../tools/test_*.py`,
`src/tools/test_title_demo.py`) and read only from `src/tests/`.
**No editor change to rooms/models may break any test or build.**

**RE-ASSERTED 2026-10-17 (user, emphatic): "When creating tests, create the
rooms, and put them in tests folder. Do not use live-data for tests."**
This means, concretely, that a test **authors its own rooms/models** and
keeps them under `src/tests/` — it does **not** read `src/*.bin`,
`src/*.lst`, or `src/generated/**` (the live build). The earlier
"ROM byte staging" (`test_fixtures.py` injecting into the live
`src/bank2.bin` at live `bank2.lst` label addresses) **VIOLATED this rule**:
because the label addresses come from `bank2.lst`, those tests were coupled
to whatever the editor last wrote into `models_data.asm`, so a model edit
(e.g. model 4 losing its hot rect → a 13B→10B rect slot) broke
`test_fixtures` + `test_hcrunch` + `test_laser_wall`. That mechanism is
**NOT** sanctioned any more — it must be replaced by frozen copies.
**Whenever a ROM-byte fixture is needed: copy the bank image AND the label
set into `src/tests/` and read those, never the live build.**

Two staging mechanisms (both fully test-owned):
- **File copies** (models.json, level jsons, generated slices):
  frozen files under `src/tests/`.
- **Frozen ROM image + labels**: a test-owned `src/tests/bank*.bin` (and a
  frozen label set) — never `src/bank*.bin` / `src/*.lst`. Fixture bytes change only by deliberately
  re-freezing in that module.

Sanctioned exceptions — their job IS to track live data (run them after
`./build.sh`, since they compare live sources against the built ROM):
- converter-validation tests (`test_features_data`, `test_asym_data`)
- `test_band_restage` (live level jsons ↔ built ROM EnterRoom behavior)
- `test_level_bank` (kernel `LEVEL_COUNT` hand-copy ↔ live
  `generated/levels.asm` count — freezing it would break on level add)

**Re-freeze procedure** (only when stage content deliberately changes):
run `./build.sh` first (so `generated/` matches the edited data), then
copy the edited `rooms/level_*.json`, `rooms/models/models.json`, and the
convert outputs under `src/tests/generated/` into `src/tests/` keeping
the same relative tree. `test_editor_roundtrip` regenerates from the
frozen copies into a TEMP dir — it must never write the repo.

Run in Stella:
```bash
stella savior.bin        # normal emulation
stella -debug savior.bin # debugger
```

## Development Plan

### Phase 1: Basic Rendering ✅
- [x] VSYNC/VBLANK/Overscan frame timing
- [x] Kernel: 4 bands × 36 scanlines + 48 HUD band (originally 12×12; cut
      to 3×48 on 2026-09-28, then to 4×36 on 2026-10-23 — `TILE_ROWS=4`,
      `LINES_PER_TILE=36`, `CAVE_LINES=144`)
- [x] Cave playfield with reflected mode (CTRLPF D0=1)
- [x] Player sprite (GRP0) — 8×12, per-row colors, 2-frame jet animation, REFP0 mirror
- [x] Joystick movement (up/down/left/right)
- [x] Fix cave shape — room .txt maps + convert_room (per-room walls, not bars)
- [x] Proper wall collision bounds (rect walk — see Phase 3)

### Phase 2: Player Sprite & Positioning
- [x] Horizontal positioning via RESP0/HMP0 (Andrew Davie algorithm;
      SetObjectXPos pinned to the $FF10 gap + page-cross guards)
- [x] Player sprite art (jet animation, 2 frames)
- [x] Smooth movement with proper pixel bounds (PLAYER_MIN/MAX_X clamps)
- [x] Collision box matching visual sprite (PlayerHitsMap cell range)

### Phase 3: Collision Detection
- [x] Player-to-playfield collision — implemented as the **PF cell walk**
      (PlayerHitsMap), NOT TIA CXP0FB: the PF buffers ARE the collision map
      (plan C4 2026-10-20 — the solid rect lists and the ZP rect cache are
      retired; only hot records stay as a data stream)
- [x] Wall collision prevention (don't walk through walls)
- [x] Room boundary checks (don't leave room edges — exit handlers)
- [x] Collision response (stop + hot-rock bump)

### Phase 4: Room System
- [x] Room data format (rooms/*.txt → convert_level → PF + hot stream in ROM)
- [x] Room connections (up/down/left/right exits — LevelConn*)
- [x] Room transitions (load new room on exit — EnterRoom)
- [x] Multiple rooms per level (2 levels, LEVEL_COUNT guarded)
- [x] Room-specific enemy placement (JSON enemies + editor 3-slot cap)

### Phase 5: Enemies (GRP1)
- [x] Enemy sprite rendering (GRP1, ObjSprites bank0)
- [x] Enemy positioning (RESP1/HMP1 via SetObjectXPos selector 1)
- [x] Basic enemy AI (patrol/chase — moth walk, tentacle probe, derives)
- [x] Enemy-player collision (CheckEnemyHit)
- [x] Multiple enemy types (moth/spider/tentacle/bat/snake/lamp/miner/raft)

### Phase 6: HUD Display
**HERO's HUD per disassembly (corrected — see the "read the FULL section"
rule at the top):** NUSIZ copies for icon rows (`LFF3E = $30,$30,$20,$20`
= lives/bombs), 13+2 (P0×3 + P1×3 + ball) for TEXT rows. An earlier
version of this section claimed HERO used 13+2 for *everything* — that
was the disproven claim.
- [x] Score display (6 digits — bank1, 48px technique: NUSIZ×3 P0/P1 +
      VDELP cross-buffer, `docs/font/48px_score_skill.md`)
- [x] Lives display (bank1 "Line 2", NUSIZ icons)
- [x] Bombs display (bank1 "Line 3", red squares, count = PlayerBombs)
- [x] Timer bar (power bar, bank1 — BarDelay/BarFine/BallX tables)
- [x] Level indicator
- [x] HUD rendering in the 48-line band (bank1 via the $FC68 fold pad)

**Score rendering notes (from HERO disassembly + bumbershootsoft):**

**HERO's actual architecture (follow this):**
- HERO uses **per-scanline PF lookup tables** — NOT a font array + runtime computation
- Each scanline gets its own complete PF0/PF1/PF2 value from ROM tables (LFA00/LFB00/LFC00/LFD00)
- Font data is **baked directly into the PF register values** — there is no separate PFDigitFont
- The score kernel loads ONE source byte per scanline, then ANDs it with per-scanline masks ($BF for PF1, $C2 for PF2) to extract each PF register's portion
- Masks vary per scanline because different rows need different bits masked off
- This eliminates serialization overhead — each scanline's PF values are loaded directly from ROM
- The PF values encode both the digit shape AND the pixel positioning in the PF register bit layout
- Score is 4 scanlines tall (not 5), using 2-pixel-wide digits (not 3)
- The key trick: one source byte encodes PF0 raw, PF1 via AND mask, PF2 via AND mask — saves ROM space and simplifies the kernel

**Why this matters:** HERO's digits look small because the PF lookup tables pre-compute the exact pixel pattern for every scanline. Our approach of computing PF values at runtime from a font array introduces overhead and makes digits wider. To match HERO's look, we should use the same PF-table approach.

**What we currently use (48px sprite score, `docs/font/48px_score_skill.md`):**
- Score is rendered by **bank1** in the HUD band: NUSIZ0/1 = 3 (P0×3 +
  P1×3 = 6 digit slots), VDELP0/1 cross-buffer pipeline
- `scorePtr1-6` ($E0-$EB) → `DigitGfx` ROM font at $FD00, read
  `lda (scorePtrN),Y` per scanline
- The old bumbershootsoft PF-compute approach (CTRLPF SCORE mode +
  `PFDigitFont` + runtime PF values) is **gone** — no `PFDigitFont`
  reference survives anywhere
- HERO's per-scanline PF-table trick (bullets above) remains the
  aspirational reference for pixel-small digits

### Phase 7: Gameplay
- [x] Laser/weapon system (missile 0) — LaserInput/ENAM0/BeamMask/LaserHitTest
- [x] Bomb system (bomb sprite + fuse timer, NOT the ball — BombPacked state machine)
- [x] Wall destruction (BombMarkWalls cell punch: a thin wall = one solid
      D7 cell whose neighbours are empty; the PF buffer is the double-score
      guard — WallMask/ApplyBombWalls retired by C4)
- [x] Item collection (CheckMinerPickup → next level)
- [x] Level progression (inc Level, wraps at LEVEL_COUNT)

### Phase 8: Jetpack Physics
- [x] Gravity (constant downward force — vyLo/vyHi integration)
- [x] Thrust (upward force when button held — JetPower; **HERO feel 2026-10-22**: while
      FALLING a held jet jumps straight to JET_MAX ($30) and stops a terminal
      1.5 px/frame fall in ~10 frames; from rest / while rising it still ramps
      +1/frame so take-off eases in. The old `EnemyRamP & 3` gate + JET_MAX=$14
      needed ~80 frames to beat gravity = a room height of extra falling, bugs #31
      superseded — do not re-add the ÷4 gate to the falling case.)
      **The velocity clamp must compare the low byte** when `vyHi == >MAX_FALL`
      (2026-10-22): the old high-byte-only `cmp` rewrote every speed in
      `$0100..$017F` to exactly `$0180`, so thrust was computed and thrown away
      every frame and no jet could slow a fall. Guard: `tools/test_jet_clamp.py`
      (ROM-level — model-based tests use a proper `>` compare and cannot see it).
- [x] Inertia (momentum — subpixel accumulator PlayerYSub)
- [ ] Fuel management (no fuel system; the power bar is the game TIMER)
- [x] Vertical collision with ceiling (StepUp stops flush)

### Phase 9: Polish
- [x] Sound effects (engine buzz, bomb drop/explode, laser — test_laser_sound.py)
- [ ] Music (background theme)
- [x] Color schemes per level (LevelWallColor/LevelWallColor2 from level data)
- [ ] Screen transitions
- [x] Title screen (level select: DROP-IN sentinel, SELECT/RESET console switches)
- [ ] Game over screen
- [ ] Difficulty settings

### Phase 10: Levels & Content
- [ ] Design 5+ levels with increasing difficulty
- [ ] Level-specific enemy patterns
- [ ] Boss encounters
- [ ] Secret rooms/areas
- [ ] High score tracking

## HERO Architecture Reference

### Key Patterns to Follow

1. **Reflected Playfield**: CTRLPF D0=1 — left half mirrors to right.
   Cave design is symmetric about center seam.

2. **PF Persistence**: Write PF0/PF1/PF2 ONCE per tile row. TIA persists
   values across all 12 scanlines of that row. Saves 36 cycles/scanline.

3. **Fixed-Time Kernel**: Same instruction stream every scanline. No
   conditional branches that change cycle count. Sprite data from
   pre-computed buffers. PF data from lookup tables.

4. **Horizontal Positioning**: RESP0 for coarse (every 15 color clocks),
   HMP0 for fine (-8 to +7). HMOVE applied during HBLANK.

   **CRITICAL: SetObjectXPos must match the comparison branch EXACTLY.**
   A `jmp .Div15Loop` before the div15 loop added 3 cycles (1 pixel) to
   RESP0 timing, causing collision misalignment. This took 2 days to find.
   NEVER add timing-changing instructions to SetObjectXPos without
   verifying pixel-perfect alignment with the comparison branch.

5. **CRITICAL: ZP Address Conflicts Between Banks** — All banks share the
   same 128 bytes of zero-page RAM ($80-$FF). Writing to a ZP address in
   one bank corrupts the value for ALL banks. Before defining new ZP
   variables in any bank, ALWAYS check that the addresses don't conflict
   with variables used by other banks. The ZP map in kernel.asm shows
   bank0's usage; bank1 must use addresses that don't overlap. Known
   safe unused ranges: check kernel.asm ZP allocation before adding new
   variables. Example: $E0-$EB was used by bank0's level data pointers,
   causing crashes when bank1 wrote digit pointers there.

 6. **CRITICAL: ZP Stack Collision ($F8-$FF)** — The2600's128-byte RAM
   mirrors at $0100-$01FF (stack page). The stack pointer starts at $FF
   and grows downward. Any ZP buffer at $F8-$FF shares
   physical RAM with the stack. **JSR pushes return addresses to $FF-$FE,
   overwriting data at those ZP addresses.** If you copy data to a ZP
   buffer and then call JSR, the return address overwrites the buffer.
   Rule: do NOT put buffers at $F8-$FF at all — the stack owns it.
   (Historical: the old PlayerGrp0 buffer sat there and JSRs overwrote
   sprite rows 6-7; removed 2026-09-24 — kernel now reads ROM via
   `Grp0Ptr` with no ZP copy.)
   **The real boundary is the MEASURED deepest SP, not $F8** (2026-09-28):
   nested jsr chains (frame → StepDown → PlayerHitsMap → rect-walk →
   FoldIndirect = 5 levels) drive SP down to **$F6**, stomping $F6/$F7.
   Any new jsr level in a deep path moves the line down by 2 bytes.
   Guard (build gate, `sim_bomb_fuse.py` via `build.sh`): gameplay min
   SP ≥ $F8, whole-run ≥ $F7 (a push writes AT SP then decrements — SP $F7
   = lowest byte written $F8 = boundary kept; SP $F6 = $F7 stomped).
   Never assume "$F6 is free" — check the measured depth first.

7. **Incremental Development** — When making big changes, ALWAYS divide
   the work into small steps and test after each one. Each step should
   add only one piece of functionality. This makes it much easier to
   catch and fix issues early, before the full code is in place. If a
   step breaks something, you know exactly which change caused it.
   Example: building the 48px score renderer required 10+ incremental
   steps (registers → color → positioning → pointers → render loop)
   rather than writing the whole thing at once.
7. **Build-Test-Build** — When implementing a feature, write the plan
   as small, testable pieces. After EACH piece, ask the user to test
   in Stella before moving to the next piece. Do NOT implement the
   entire feature at once — a bug buried in 500 lines is 10x harder
   to find than a bug in 20 lines. Pattern: implement → build → user
   tests → fix if needed → next piece. This is MANDATORY for any
   feature touching the kernel, movement, collision, or room system.

5. **Vertical Positioning**: Kernel scanline counter matches player Y.
   Sprite rendered when scanline falls within player's 8-line range.

6. **Collision**: TIA hardware collision registers (CXP0FB, CXPPMM, etc.)
   checked in VBLANK/Overscan after frame renders.

### Hero's Cave Structure

```
Row 0-3:   ####....................................####   (thick walls)
Row 4-7:   ##..........................................##   (thin walls)
Row 8-11:  ###################....#####################   (bottom passage)
```

The cave is 20 logical columns wide. With reflection, each half mirrors.
PF0/PF1/PF2 define the left half; TIA mirrors the right.

### Playfield Register Layout (Left Half)

| Register | Bits    | Pixels (color clocks) |
|----------|---------|----------------------|
| PF0      | 7-4     | 0-3 (leftmost)       |
| PF1      | 7-0     | 4-11                 |
| PF2      | 0-7     | 12-19 (reversed)     |

## Differences from HERO

| Feature | HERO | This kernel |
|---------|------|-------------|
| ROM size | 8K (F8 bankswitch) | 16K (F6 bankswitch) |
| PF writes | Per-scanline (ROM tables) | Per-band (4 × 36 lines, written once in `.Row`) |
| Sprite data | `(zp),Y` from ROM | `(zp),Y` from ROM (`(Grp0Ptr),Y`, frame picked in VBLANK) |
| VDEL | Used for sprite pipeline | Used by bank1 score (48px technique); cave kernel no |
| Enemies | Yes (miner + enemies) | Yes — moth/spider/tentacle/bat/snake/lamp + miner |
| Rooms | Multiple connected rooms | Yes — multi-room levels, exit handlers + connections |
| HUD | Score/lives/time text | Yes — bank1 band via fold pad (score/lives/bombs/bar) |
| Jetpack | Physics with gravity | Yes — gravity/thrust/inertia (vyLo/vyHi/JetPower) |

## Debugging

### Stella Debugger

- `stella -debug savior.bin` — launch with debugger
- Backtick (`) — enter debugger from emulation
- `run` — resume execution
- `breakLabel <addr>` — set bankswitch-safe breakpoint
- `clearbreaks` — clear all breakpoints
- `scanline` — show current scanline

### Screenshots (Wayland) — agent captures Stella itself

System is **Wayland**; X11 grab tools (`xwd`, `import -window`) fail with
`BadWindow` on the XWayland window — do not use them. Working recipe
(verified 2026-10-06, first title-screen capture):

```bash
# 1. Launch (XWayland display + software video; detached so it survives)
cd src/ && setsid nohup env DISPLAY=:0 stella -video software savior.bin \
  >/dev/null 2>&1 < /dev/null &
sleep 5   # boot + title frames

# 2. Capture the ACTIVE window (Stella has focus after launch).
#    -b = background (required for -o/-d), -a = active window,
#    -e = no decoration, -n = no notify, -d = delay ms
spectacle -b -a -n -e -d 1200 -o /abs/path/src/screenshots/shot.png

# 3. Verify the file exists, Read it as image, then:
pkill -f "stella.*savior"
```

- Never launch bare `stella` or `stella -help` — no ROM arg opens the
  launcher/GUI (user saw a "loading file" window).
- `xwininfo -root -tree | grep '"Stella'` works for window inspection
  (geometry 640x456) but `xwd -id` still fails — spectacle only.
- Stella has NO CLI screenshot flag (checked `-help`).

### Scripted snapshots — deterministic frame captures (autoexec.script)

Source: `screenshots/debug/debug_in_stella.jpeg` (past-session method).
For exact-frame PNGs (better than spectacle for A/B timing checks —
fixed `frame N`, no focus/portal dependency):

```bash
mkdir -p /tmp/opencode/stella_base /tmp/opencode/stella_shots
cat > /tmp/opencode/stella_base/autoexec.script <<'EOF'
frame 5
saveSnap
EOF
cd src/ && setsid nohup env DISPLAY=:0 stella \
  -basedir /tmp/opencode/stella_base -debug \
  -snapsavedir /tmp/opencode/stella_shots savior.bin >/dev/null 2>&1 &
sleep 6            # Stella NEVER exits on its own — background + kill:
pkill -f "stella.*savior"
# PNGs land in /tmp/opencode/stella_shots
```

- `-basedir <tmp>` makes Stella run `autoexec.script` from that dir AND
  keeps the session away from the real Stella settings (sqlite db —
  no `logTrace` pollution from the trace-recipe rules below).
- Script commands that work: `frame #N` (advance N frames),
  `saveSnap` (PNG of current picture), `ram $addr $val` (poke RAM —
  e.g. `ram $81 $40` to set RoomY).
- Traps (measured by past session): `ram` bare hex `a` parses as the
  A register — ALWAYS `$`-prefix (`ram $0a $05`); joystick-style
  script commands (`joy0Right` etc.) do NOT affect the running game;
  no read-back (can't dump RAM/scanline counts out of a script).
- Because of those gaps, real debugging stays in the py65 sims
  (`sim_frame_budget` etc.) — Stella scripts = camera + pokes only.
  Live jitter/pacing still needs human eyes (simulator timing is only
  as good as its hardware model; Stella is the reference).

### Timing Measurement

Use `breakLabel` at two addresses, subtract Scn values:

1. `clearbreaks`
2. `breakLabel <start_addr>` → run → note Scn value
3. `clearbreaks`
4. `breakLabel <end_addr>` → run → note Scn value
5. Subtract to get duration in scanlines

**NEVER use `break`** — it fires at the physical ROM address in ALL banks
(causes cross-bank contamination with bankswitched ROMs).

**py65 PC traces MUST filter the execution bank (2026-09-29):** bank0/bank1
share the $F000-$FFFF address space — a raw PC counter sees bank1 HUD code at
the SAME address as a bank0 routine (tentacle's `beq .TentCommit` at $F5A5 =
bank1's `lda BarDelayTable,Y`), silently mixing them: counts came out ~5× too
high and the "probe path" PCs were bar-red delay instructions. Rule: pair
every `(pc, ...)` count with `mem.bank` (measure's `hpc[(pc,bank)]` does);
a lone hex PC is ambiguous.

**`print *$XX` DEREFERENCES — it is NOT a raw byte read (2026-09-28):**
`*` is Stella's pointer operator: `print *$B5` uses the byte AT `$B5` as an
address and shows THAT cell (observed: `print *$B5` → `ram_81` because
`[$B5]=$81`; `print *$F7` → `CXBLPF|$30(R)` because `[$F7]=$35` pointed at
the TIA collision register at `$35`). Reading a ZP variable raw (measured 2026-10-23, Stella 7.0):
- **`watch $XX` does NOT read memory - it evaluates the expression.** Watching
  `$80`, `$92`, `$99`, `$9A`, `$84`, `$C7` printed the constants `$80`, `$92`,
  `$99`, `$9A`, `$84`, `$C7` - every "value" equal to its own address. The
  earlier note that called it a raw byte read was WRONG; do not use it.
- **Use the hex grid** (the `00xx` table: rows = high nibble, cols = low
  nibble) or the `ram` command. That is the reliable read.
- `print *$XX` is the dereference form and is fine for a plain byte read:
  `print *$9A` shows the byte AT $9A.
Symptom of having used `*` by accident: output names a *different* address
(TIA register or `ram_XX`) than the one you typed.

### Scn Ln fields (TIA info panel) — source: Stella `TiaInfoWidget.cxx`

The row labeled `Scanline` (short form **`Scn Ln`**) holds TWO value boxes
(comment line 32: "current and the last-frame scanline counts, which share a
row"). Box order is fixed by reflow (line 199-200: `{myScanlineCount,
myScanlineCountLast}`) — **left box first, right box second:**

| Box | Widget | Source | Meaning (tooltip) |
|-----|--------|--------|-------------------|
| **LEFT** | `myScanlineCount` | `tia.scanlines()` = `myCurrentFrameTotalLines` | "Current scanline of this frame" — 0 at frame start, +1 per scanline |
| **RIGHT** | `myScanlineCountLast` | `tia.scanlinesLastFrame()` = `myCurrentFrameFinalLines` | "Number of scanlines of last frame" — frozen; updates ONLY at frame boundary |

- Frame boundary = `notifyFrameComplete()` (AbstractFrameManager.cxx:91) →
  RIGHT = totalLines at that instant, LEFT resets to 0. Fired by: VSYNC
  falling edge (≥2-line pulse), or timeout paths (`myVsyncLineCount > 50`).
- So `Scn 45|301` = line 45 of the CURRENT frame; last completed frame was
  301 lines long.
- Cross-checks: `Frame Cycles` ≈ LEFT×76 + Scn Cycle (tooltip: "CPU cycles
  executed this frame"); `Frame` = boundary counter.
- NEVER conclude "frame is N lines" from LEFT — LEFT is a position, not a
  total. Only RIGHT is a frame total, and only right after a boundary it
  actually belongs to.

### Pseudo-registers (Stella 7.0)

- `_scan` does NOT work — resolves to $00 (CXM0P)
- `breakif {_scan == N}` is UNRELIABLE
- Use `breakLabel` + Scn field instead

### Lessons Learned

**ZP bytes are a PHASE resource — share them by lifetime, and reset at the
handover (2026-10-22).** The title melody held `$9D`/`$9E` (`MelPtr`/
`MelTimer`) even though it only runs on title frames, which blocked the
per-type object height (the cave kernel needs two bytes on BOTH title and
gameplay frames, because the title previews the stage with real objects). Fix:
the melody moved to `$F6`/`$F7` = `BombX`/`BombTimer`, which are dead on title
frames (`DropTarget != 0` → `DropStep` skips the bomb block), and the
`SELECT+RESET` title entry clears them so the theme restarts instead of reading
`MusicMel` with a stale gameplay index. Rule + the audit checklist in
`docs/zp_layout_skill.md` rule 7. **The room-change case obeys the same law**:
every per-room byte (`EnemyDataLo/Hi`, `EnemyCount`, `EnemyRamX/Y/D/P`,
`RoomRectsLo/Hi`, `RoomMetaA/B`, `LevelConnSpare`) is re-derived by
`EnterRoomB2`; a new per-room byte must be staged on that path or it carries
the previous room's value.

**Room entry must refresh the joystick shadow `Temp` (2026-10-20, user
report: the eye snapped right on every transition + a 1 px twitch):** bank0's
overscan input block stages `SWCHA>>4` into `Temp` and keeps reading it for
the rest of the frame. `EnterRoomB2` reuses `Temp` for room/record scratch, so
the stale byte faked a held direction after every exit (room index 0..7 has
bit3 clear = "RIGHT pressed"), flipping `PlayerDir` and walking a pixel.
`bank2.EBLER_Done` therefore re-reads `SWCHA` into `Temp` before `ReturnPad`
(14 B, zero per-frame cost; SWCHA is stable within a frame). **Any future
writer of `Temp` inside the room-load chain must not run after that refresh**,
and any new exit path must return through `EBLER_Done`. Guard:
`tools/test_room_input.py` (stubbed port, three patterns).

**F6 hotspot MIRROR zone = $FFF6-$FFF9 — no fetched byte may ever live there
(2026-09-30, E4 moth exit tramp frame-3 crash):** Stella's
`CartridgeEnhanced::peek` (`CartEnh.cxx:157`,
`if(hotspot() >= 0x80 && checkSwitchBank(address & ADDR_MASK, 0) && myRandomHotspots)`,
`ADDR_MASK=$1FFF`, F4 `hotspot()=$1FF4`) calls `checkSwitchBank` on **reads** —
the side effect fires even when `myRandomHotspots` is false (the `&&` already
evaluated it). So ANY instruction fetch at `$FFF4-$FFFB` (the only addresses in
code space with `addr & $1FFF ∈ $1FF4-$1FFB`) switches banks MID-INSTRUCTION.
Real F4 is write-only (reads don't switch), so this bites Stella only — but the
frame died exactly like hardware: the E4 moth exit pad at $FFF2 was
`sta $1FF4 / jmp UE_Next`; the `jmp`'s operand fetches at $FFF6/$FFF7 flipped
bank0→bank1 → operand hi read as $00 → `jmp $007D` → bank1 FF-fill runaway →
HUD ran a 2nd time (+48 lines = 359/360-line frames) → each rogue Overscan
re-entry leaked ~5 stack bytes → SP decayed $FF→$E1 over ~6 passes (~3 frames)
→ `jsr RefreshEnemyY`'s return address (pushed at $01E0/$01E1) was the
FetchPtr mirror, clobbered by DeriveEnemyY staging $FAC5 → `rts` → font data →
SLO/JAM at $FAC9. **py65 could never see this** (its F6 mapper peeks pure ROM).
Fix: exit pad moved to $FC49 (main headroom, `.ds $FC49 - *, 0` pin);
guard `check_moth_tramp` now asserts `$FFF2-$FFF9` = fill in bank0/bank2
(F4: $FFF4-$FFF9 are the hotspot mirrors).
**Rule: treat `$xFFF4-$xFFFB` as reserved; before placing ANY code near
$FFFx, check `addr & $1FFF` against $1FF4-$1FFB.** Recognize this bug family:
sprite/enemy "teleports" + wall pass-through + odd frame lengths + a counter
that decays in steps then never completes → look for a hidden bank flip, then
for stack decay from mid-frame re-entries.

**Tagged Stella trace recipe (needed to SEE addresses):** the pc column only
prints when `disasm.list` has a tag ≥ pc; that list loads when the debugger
prompt first shows (`loadListFile` from `PromptWidget::_firstTime`), which also
runs the ROM-dir script. **The two trace scripts are kept RENAMED to
`*.tracebak` by default** — `src/savior.script.tracebak` and
`~/.config/stella/autoexec.script.tracebak` (both = `logTrace` + `run`); while
active they trace EVERY instruction (millions of lines) and make the game
crawl. To trace: `mv` both back to their exact names (`savior.script` /
`autoexec.script`), run `timeout --signal=KILL 10 stella -debug -loglevel 2
-logtoconsole 1 savior.bin`, then rename them to `*.tracebak` again.
**Stella 7 persists settings in `~/.config/stella/stella.sqlite3` (table
`settings`, no .ini)** — `logTrace` writes `dbg.logtrace=1` there and it
survives sessions, so plain runs keep tracing after a trace session. Reset
after any trace (python sqlite UPDATE): `dbg.logtrace=0`, `logtoconsole=0`,
`loglevel=0`. Symptom of a dirty db: `stella savior.bin` prints a `trace` line
per instruction (game crawls).
— do NOT add `-dbg.logtrace 1` on the CLI (with `-debug` it produced zero trace
lines). Health check WITHOUT addresses (no scripts, no debugger):
`timeout 10 stella -loglevel 2 -logtoconsole 1 -dbg.logtrace 1 savior.bin` —
gives frame/scn/A/X/Y/SP only. Bytes/disasm columns come from the stale
`src/savior.lst` (Sep 16) — trust only
the address + bank columns (bank = `getBank(pc)` at trace time; during the HUD
band, `1/f57d` = the score loop, not the dispatch). Health check: per-frame max
scn must be 262 and min SP ≥ $F9 after boot.

**Explosion flicker = VBL overrun from elapsed-counter loops + per-frame full
PF rebuild (2026-09-29):** the bomb explosion flickered (263-line frames) only
late in state2's 60 frames. Three costs compounded: (1) old `.BgBlink` was an
elapsed/3 subtract loop whose iteration count grew 0→~19 (≈171c) as the
animation aged; (2) `ApplyBombWalls` thin-wall punch +224c per blast; (3) a
full `LoadPFBuffer` (9 folds ≈384c) ran EVERY frame. Worst VBL 1539c >
`TIM64T #23` = 1472c window → VBL ended after the timer → 263-line frame →
flicker. Fixes: constant-time blink `and #3 / tay / lda BombBlinkColors,Y`
(60 frames = 15 exact phase cycles — iteration count fixed forever);
`LoadPFBuffer` split so VBL calls `LoadPF0Only` (3 folds ≈130c, −254c/frame)
and the full rebuild runs only on `EnterRoom` (tail-jmp keeps the stack
guard). Worst VBL 1539→1235c, margin +237c.
*[Postscript S3.4: the VBL `LoadPF0Only` call is now GONE entirely —
`EnemyRamY` moved to `$E2`, so `$C3-$C5` are never stomped and VBL does no
PF rebuild at all (EnterRoom only). The routine survives as
`LoadPFBuffer`'s tail jump. Lesson stands.]*
**Rule:** budget VBL at the
worst path × the LATEST-in-animation iteration count, not the first frame;
elapsed-counter/subtract loops are forbidden in VBL (they age) — use a table
index gated by frame phase. Recount from `bank0.lst` after any VBL growth.

**Stack pushes are INVISIBLE to byte-audits — audit stack DEPTH, not operand
bytes (2026-09-28, bomb never explodes in level 2):** BombTimer ($F7) went
down then bounced back up forever ($33↔$3B), fuse never reached 0, state
stuck at 1, bomb consumed but never exploded. Root cause: the CPU stack page
$0100-$01FF **mirrors** ZP $80-$FF, and the deep call chain
`frame → StepDown → PlayerHitsMap → rect-walk → jsr FoldIndirect` (5 levels)
drove SP to **$F6** — so JSR return-address bytes ($3B = PCL) were pushed
onto $01F7/$01F6 = physically BombTimer/BombX. The fuse `dec` dragged the
byte down, the next frame's stomp shoved it back → the exact bounce the grid
watch showed. **A byte-audit can NEVER find this**: JSR pushes are hardware
writes to $01xx, not instructions with $F7 in their operands. And repeated
pushes of the SAME value (same call site → same PCL) look like no-ops, which
is why the watch showed "unchanging" bytes for a while. The P3.6 fold
refactor added one jsr level per fold — each level moves the danger line
down 2 bytes; the old inline `lda (MapPtrLo),Y` walks had zero extra stack.
**Rule:** any ZP variable at or above the MEASURED deepest SP is unsafe —
measure min-SP in a headless sim (`sim_bomb_fuse.py` write-tracking +
push-trace), never infer safety from "no instruction writes that address".
Symptom signature: a counter/modulo that counts down, then JUMPS back up in
a stable bounce band, while related state machines never complete.

**`TickCounter` is the 60-frame GAME timer — never derive periodic motion from
it beyond `& 7` (2026-09-27, E-gate: spider teleport):** it decrements 60→1
and reloads, so any `>>3` gate only ever sees 0..7 and counts DOWN (0→7 wrap =
sprite jumps to the bottom once per second). Symptom signature: sprite descends
N pixels then **instantly teleports** back to spawn, forever. Fix: free-running
frame clock — `inc EnemyRamP` ($C2, was reserved for moth flags) once per
frame in `RefreshEnemyY`; all derive gates index off it. Alignment rule: the
motion phase period must divide 256 (the clock's wrap) or the wrap shows as a
jump — 48-step phases are impossible; 64-step (gate ÷4) works, and a **dwell
zone** (delta 0 at the wrap landing) hides it entirely. Bat gate = `clock>>1`
(1 px/2f), tentacle bob = `clock>>3`, spider = `clock>>2` + dwell.

**`PlayerHitsMap` clobbers X — save/restore the caller's X around it
(2026-09-27, E-gate: tentacle X frozen):** PHM calls `YToCellRow`, which does
`tax` (X = bottom tile row). `UE_Tentacle` documented "X preserved" and used
X after the probe: `sta EnemyRamX,X` wrote the candidate into
`EnemyRamX[row]` (out of the slot), so the tentacle's real X never changed —
sprite bobs vertically (Y is derived) but never moves horizontally, with NO
error and no crash. Symptom signature: one axis works, the other silently
does nothing after a `jsr` collision helper. Rule: any routine that calls
`PlayerHitsMap`/`YToCellRow` must push/pop X (`txa/pha ... pla/tax` — PLA
does not disturb C, so probe carry survives) unless it provably does not use
X after the call. Static PHM simulation (rect walk at the spawn box) showed
CLEAR — the position math was fine; the register was the bug.

**Kernel row splits must preserve per-pass line totals exactly (2026-09-27,
water strip):** each `.Row` pass costs 1 setup line (ends `sta WSYNC`) + N
`.Line` bodies. Splitting row 2's 48 bodies into 36 + a `.WaterRow` pass
(setup + 11) keeps `1+48 = (1+36) + (1+11)` — frame length unchanged. Adding
a pass with 12 bodies would add one scanline/frame (roll risk). When editing
kernel structure, count WSYNC executions before/after; comment cycle counts
are stale the moment code changes.

**Bank0 space discipline (2026-09-27, E1-E3): main ends ≤ `$FC68`, post-pad
is full — compress DATA before building fold machinery:** `DeriveEnemyY` +
tentacle arm overflowed main (over by 34B). Cheapest fix = compress lookup
tables with **floor-nesting**: `YToRowTable` was 192B indexed by A (A/48);
reindexed by `A>>2` = 48B table — `floor(floor(A/4)/12) == floor(A/48)`, cost
+4c/call. Freed 144B (headroom 4→106B) with zero behavior change. When a
growing dispatch hits the assembler's 127-byte branch limit, do NOT pad
branches — extract a `jsr` subroutine (`UE_Tentacle` after `UE_Exit`, jsr is
absolute) and put the NEW type check FIRST in the dispatch so existing
branches keep their original (short) ranges. E4 moth needs ~95B vs ~33B free:
space options (fold machinery vs more compression vs shared probe helper)
must be decided with the user. Also verified: all overscan `Temp` consumers
(input/hot-bump) run BEFORE `jsr UpdateEnemies`, so UE's probe may own Temp.

**ZP alias lifetime — an alias over a per-frame-refreshed buffer needs its
OWN writer in your read window (2026-09-26, enemy Y at $C3; mechanism
retired S3.4 but the rule is permanent):** `EnemyRamY` was aliased over
`PF0Buf` rows 0-2. The E0 design listed overscan as the
writer and VBLANK as a reader, but `LoadPFBuffer` ALSO writes $C3 every
VBLANK — so after the first frame, draw read PF garbage: **symptom = object
renders for one frame, then vanishes forever** (not a draw/collision bug).
Fix was `RefreshEnemyY` rewriting the alias at overscan entry every frame;
**permanent fix landed in S3.4**: the alias was deleted (Y got private
bytes `$E2-$E4`) and the `$F0-$F2` bomb-save ↔ ColupfBuf save/restore pair
was deleted too (S3.0b — it had been a no-op since the 12-row era).
**Rule before choosing an alias address:** map EVERY writer to those bytes
across the whole frame (including periodic refreshers like
the bank1 HUD), then make sure one of YOUR writers runs after the last
foreign writer and before your next read — every frame, not just at init.
Encode the ordering in verify_build/test (guards exist for exactly this),
and remember the blanket form of this rule: the **stomp-zone rule**
(`check_equ_sync` enforces it — persistent state below `$E0`, see
docs/zp_layout_skill.md Critical Rule 6). The tentacle-inside-walls bug
(2026-10-01) was exactly this family: rect4.h landed on `$E0`, bank1's
scorePtr1 zeroed it every HUD frame.

**Collision misalignment (2026-09-21):** A `jmp .Div15Loop` in SetObjectXPos
added 3 cycles (1 pixel) to RESP0 timing, shifting the sprite's pixel position
right while the collision code expected it left. This caused the player to stop
1+ pixels away from walls. **Fix:** Remove any extra instructions before the
div15 loop — the comparison branch's SetObjectXPos is the reference.

**Shared-GRP1 positioning (2026-10-16, bomb render):** the bomb, enemies and
miner all draw on GRP1 (one sprite, flicker 1/N frames). P1's hardware X
(RESP1/HMP1 via SetObjectXPos) must be set on EVERY object frame — ac4c3ee
moved the bomb's SOXP out of the VBL to the drop only, so on bomb-draw frames
`SelectActiveObject` set `ActiveObjectX = BombX` but P1 still pointed at the
last enemy/miner X: the bomb rendered pinned near that object (collision was
correct — only the sprite was wrong). **Fix:** one shared SOXP in
`SelectActiveObject`'s `.SODone` tail (`ObjBase != 0`), deduped from the
miner/enemy paths. Test: `tools/test_bomb_render_x.py`.

**Branch page-cross in a cycle-tuned loop (2026-09-26, laser S1) — recurrence
of the 2026-09-21 family, via a different mechanism:** a 3-byte `jsr LaserInput`
inserted before SetObjectXPos moved it `$F8F7→$F8FA`, pushing
`bcs .Div15Loop` across the $F8/$F9 page. A taken branch costs 4c across a page
vs 3c within one, so the div15 loop ran at **6c per iteration instead of the
5c contract** — each "15 color-clock" coarse step burned 18, and RESP0 fired
3 color-clocks late **per step** (amplified by the loop, up to ~10 iterations).
- **Symptom signature (recognize BEFORE hunting logic):** sprites render right
  of their logical X by ~3×(X/15) px — drift **grows with X**; far-right
  objects (X≈140) overflow the 160-px window and the position counter wraps
  to the **left edge** (looks like an enemy "teleported across the map");
  player visually ghosts through walls although logical (RoomX) collision is
  intact. "Enemy on wrong side of screen + wall pass-through" = positioning
  TIMING, not collision/enemy code.
- **Rule: ANY size change (even one `jsr`) placed before cycle-tuned code can
  flip a taken branch's page.** After adding/removing bytes in bank0 pre-pad
  code, recheck page contracts from `bank0.lst` — never from comments (the
  ObjSprites comment had already gone stale). Kernel `.Line` fetches to recheck:
  `lda ObjSprites,X` (abs,X), `lda PlayerColTable,Y` (abs,Y),
  `lda (Grp0Ptr),Y` (zp,Y), plus SetObjectXPos's `bcs`.
- **Fix:** SetObjectXPos relocated (byte-identical, address-only) into the
  single-page `$FF10-$FF1F` gap (between the 15-byte fineAdjust table at $FF00
  and `org $FF20`) — the 5c contract is now structural. Note the post-pad
  region was already at 100% capacity (ObjSprites ended exactly at $FF00), so
  that gap was the only free code space.
- **Guards (verify_build.py fails the build):** (1) `bcs .Div15Loop` must
  share a page with `.Div15Loop`; (2) `.Div15Loop` must be in `$FF12-$FF1B`;
  (3) `ObjSprites+71` must stay in-page. Do not weaken these.

**PF0 bit order (2026-09-21):** TIA PF0 has bit 4 = leftmost pixel, NOT bit 7.
The mapping `0x10 << col` is correct. Do NOT "fix" this — it was verified
empirically and matches the comparison branch.

**WSYNC off-by-one overrun — RECURRENCE (2026-09-25):** This exact bug class
has bitten us multiple times (see the `.Line` comment history: "jmp on the hot
path" double-height sprite, and now this). One-cycle-late `sta WSYNC` in the
kernel `.Line` loop stalls a FULL scanline per affected line.

- **Symptom → cause map:** player on same row as enemy/snake → that cave row
  stretches down, HUD pushed down, enemy renders 2× tall (duplicated scanlines);
  GRP1 object flicker (`SelectActiveObject` rotation) makes the overlap
  present only on SOME frames → frame length alternates 262/274 → screen
  oscillates up/down by ~12 lines (one tile) until the object disappears
  (e.g. bomb explodes). If you see these, suspect cycle overrun FIRST.
- **Root cause:** worst path (player sprite in-range + GRP1 object in-range)
  body was 66c, but the `.Line` budget comment claimed 60c — `sta WSYNC`
  started at c74 and its write landed on cycle 76 = one cycle late. The
  comment had an off-by-one; nobody recounted after the sprite code grew.
- **Fix:** running-Y — seed `Y = A0 = Scanline - RoomY` ONCE at kernel entry
  (`sec/sbc RoomY/tay`), let `.Line`'s `iny` advance it (Y after the graphics
  write = next line's A0). Drops the per-line `lda Scanline/sec/sbc/tay`
  (−10c): worst path 66c → 56c, WSYNC write ≈ c66 (10c margin). Row-11 band
  jsr clobbers Y → `tya/pha ... pla/tay` around it (stack balanced).
- **RULE: never trust cycle counts written in comments.** After ANY change to
  `.Line`/kernel, recount the worst path from `bank0.lst` (instruction
  addresses, include branch page-cross) and keep the WSYNC write ≤ c73.
  Comment budget that is stale by 6 cycles = bug shipped twice.
- **Recurrence #3 (2026-09-29, bank1 HUD +1 line → 263-line frames):**
  `.BarRedFull` (power-bar Fine∈{2,3,4}) line-3 tail = 76c → `.BarGap`
  WSYNC started at c76 = full-line stall → HUD band 51→52 lines →
  frame 262→263 on ~48% of frames (only bar-red frames). Killed by deleting
  `.R3`'s `jmp .BarGap` (jumped to the NEXT instruction, after the red
  boundary write). Bisect method that found it: per-frame landmarks
  k1=`.Row` / k2=`jmp $FC68` pad target / k3=`Overscan` + WSYNC-site
  PCs + cycle gaps per WSYNC index — integer segment sums isolate WHICH
  band grew; WSYNC-count constant ⇒ line SKIP (overrun), not structure.
  **Addresses drift with every code change** (Overscan was $F18A then
  $F182/$F176/$F173 through the S3.x refactors) — resolve each landmark
  from `bank0.lst` at use time, never from this file.
   **Bar rule: content AFTER `sty COLUPF` (post-boundary) is
   table-independent (trim freely); content BEFORE it is table-coupled
   (BarDelay/BarFine/BallX regeneration required).**

**Timer-quantization phase straddle at kernel entry = whole-screen ±1
jitter (2026-10-11, bugs.md #29 Class C) — WSYNC-count guards are BLIND
to this family:**

- **Symptom:** whole screen (HUD seam rows 144/194, cave top edge) shifts
  ±1 row on ~half the frames under bomb/thrust input; Stella detector
  shows a 62/58 two-class split of an otherwise identical scene. NOT a
  duplicated row (Class A) — a seam flip.
- **Root cause:** `TIM64T` expires on a 64-cycle tick and the `INTIM`
  poll (`.WaitVBLANK` / `.WaitOverscan`) exits up to 63c late. The
  kernel-entry phase = tick remainder + the band-0 `.Row` setup WSYNC
  gap (~75c) — right at the 76c boundary — so the kernel start line
  oscillated ±1 with the tick phase (measured: first `.Line` WSYNC at
  scn 20 ×100 frames / scn 21 ×51 frames). py65 WSYNC counts stayed
  CONSTANT (cave 147 / HUD 48) the whole time: count-based guards and
  `sim_frame_budget`'s WSYNC-count assertion could never see it.
- **Fix (do NOT remove either):** two re-anchor `sta WSYNC`s —
  (1) `StartFrame` before the VSYNC pulse (overscan-end quant → VSYNC
  phase-lock); (2) after `.WaitVBLANK` with VBLANK still on (VBL quant
  → kernel-entry line-lock; blank line, invisible). Each costs +1 line
  (263→265 wall-model); `OVER_ABSOAD` +1c from code-motion page-cross
  is ledgered in sim_frame_budget.py.
- **RULE 1: the kernel entry must stay WSYNC-anchored.** Any edit that
  puts cycle-variable code between the INTIM poll exit and the first
  kernel WSYNC (or deletes either re-anchor) re-opens the straddle.
  The gap between them is cycle-precise (see the 2026-10-06
  VBL-tail lesson above).
- **RULE 2: count-constant ≠ stable.** When a ±1 seam jitter is
  reported, do NOT trust WSYNC-count or per-section cycle sums — they
  were constant across the whole bug. The oracle that found it: Stella
  `logTrace` SCN distribution at a kernel landmark PC (must be a SINGLE
  value across ≥100 gameplay frames) + the pixel row-probe detector
  (seam rows must form ONE signature over ≥120 frames). Re-run both
  after any kernel-entry/VBL/Overscan timing change.
- **RULE 3: frame-line targets move with re-anchors.** Adding a
  re-anchor WSYNC = +1 wall-model line: update `sim_frame_budget`'s
  265.0 target, `test_phase3_ball`'s {264,265} set, and any comment
  citing the total in the SAME change — leaving one stale = red gate.

**When debugging collision misalignment:**
1. First check if SetObjectXPos matches the comparison branch exactly
2. Check if the fineAdjustTable is identical
3. Check if the PF0/PF1/PF2 data matches what the TIA renders
4. Use Stella to measure actual sprite pixel position vs expected

### Frame-budget flicker — rules (S6.4-S6.6, 2026-10-01)

Residual flicker investigation will resume later (user-led). Until then,
these rules PREVENT making it worse:

1. **The invariant is the wall-model**: `sim_frame_budget` frame lines
   263.0 ±0.15 on every frame ≥2 (Stella-agree). NEVER weaken it. The
   `OVER` meter (corrected 2026-10-25): the legacy `OVER max` figure is the
   whole `Overscan`->`StartFrame` span, i.e. the TIM64T window itself (~3220c
   on EVERY frame, idle `INTIM` poll included) — it is NOT work and says
   nothing about margin. Read the `OVER real work (poll excluded)` line
   instead (max ~1520c in the fly/laser/exit scenarios = ~1680c headroom in
   the 3200c window). `OVER_ABSORB (3223)` only guards the window itself.
   Chase the wall-model, not the ε.
2. **Heavy frames = rect-walk coincidence, not one hot loop.** Every
   measured spike = enemy-probe walk (~480c = prologue ~140 + 5-rect
   loop ~340) + an extra player substep walk (+277..390c) landing on the
   same frame; exit crossings add `EnterRoom` (~769c measured 2026-10-16 —
   the old "+1665c, f327 class" predates the direct-read EnterRoomB2
   rewrite). The VBL half of the crossing spike was a separate bug:
   `SelectActiveObject`'s `FlickerFrame` modulo-subtract loop (`.SOModLoop`)
   grew unbounded in a 0-object room (the modulo is skipped there) and then
   ran O(FlickerFrame) ≈150 iterations in the VBL on the next room with
   objects (+533c / +7 lines) — fixed 2026-10-16 by zeroing `FlickerFrame`
   on the no-object path. One rect walk ≈ 400-600c total; EVERY walker multiplies
   any new rect, new per-frame probe, or loop-body growth (PHM, moth
   walk, LWC, LHT kill scan all share the pattern). Before adding any
   per-frame walk/probe: measure with mark windows + `SIM_HIST`, and
   count how many walks already run that frame (StepDown substeps,
   CheckP0Left/Right, enemy probes, LWC).
3. **Overscan margin at fly+laser baseline is ~1680c** (real work ~1520c of
   3200c, measured 2026-10-25; the old "20-220c" read the poll-inclusive
   span). The VBL is the tight budget (#24 = 1536c, worst ~1370c). New
   overscan work must be net-0 bytes/cycles or it needs a measured cut
   elsewhere in the same change. The gate is `build.sh` (runs the sim);
    scenario gates: `SIM_LEVEL=0 SIM_FLY={Y,X,M}` — **post-title numbers
    (2026-10-02): Y=1 (f138, +1-line EnterRoom), X=0, M=1 (f131, 262.84
    short) bad frames** (was 3/5/1 pre-title; drop-in + title re-phase
    every rect-walk coincidence — landed f138 vs pre-title f81;
    histograms show the same documented family (`.RectLoop` + probe),
    and the new spikes are milder than pre-drop baseline's own X f327
    +14-line EnterRoom spike (gone from the 439-frame window). The sim
    input now includes the console-RESET pulse for the title screen
    (budget sim: f1 released→held f1-2; bomb-fuse/test_laser_wall:
    f1 released, held f2-3). FLY=Y still exits SIM FAILED on the VBL
    assertion (1479 > 1472 — pre-existing class); **judge scenario
    gates by the wall-model bad-frame list only**, never by the exit
    code. VBL numbers changed meaning 2026-10-02: the sim measures from
    `VBLTimer` (TIM64T arm), not StartFrame — the old measure included
    VSYNC phase slack and flapped across 1472 (title transition f2:
    acc 1491 while the real timer window was 1336c); old absolutes are
    not comparable. + default gate + battery `tools/test_*.py` 6/6.
4. **Walk-cut patterns that worked (reuse before inventing):**
   destroyed-rect flag in `rect.w` b7 (S6.4, kills per-rect mask scan);
   col-change gate for enemy probes (S6.5, box-result keyed — walk
   outcome is a pure function of (col,row) box, so any same-box
   candidate may skip); row-before-mask in LWC (S6.6, out-of-band rects
   skip the mask test). Bank2 has ~1.6KB free gap ($F37C-$F9D8) for
   moved gate/bodies; bank0 pre-pad headroom = 1B (cuts only).
5. **Reorder/regroup regressions show up in `test_laser_wall.py`, not
   the sim** (S6.6 bug: mask fall-through jumped to `.LWs1` mid-span
   with stale A — clamp silently never applied). When moving blocks in
   a walk, the fall-through target must be an instruction START; run
   the battery after every structural edit.
6. **`pc_hist`/trace PCs are bank-aliased** — a hot hex PC may be the
   fill poll in ANOTHER bank ($F2CF = `bne .WaitOverscan` in bank0, not
   LWC code). Cross-check bank before blaming a routine (AGENTS py65
   rule, recurrence).

### Title-kernel dispatch regression family (2026-10-06)

**What broke:** one "simple" feature (title screen: black + S.A.V.I.O.R.
via the 48px sprite technique) regressed nearly every guard:
`sim_bomb_fuse` stack stomps, `sim_frame_budget` hang, WSYNC-count
mismatch, wall-model 263→264 on every gameplay frame, plus the earlier
M1 +4c VBL regression (`test_phase3_ball` 263/264, user-left-open).

**Causes (each measured, not guessed):**
1. **jmp-after-jsr stack leak.** KernelInit was `jsr`'d from the frame
   loop; the title path `jmp`'d out without popping → 2B leaked per
   title frame → SP decay → bomb sim stomps. Same family as the F6
   hotspot leak.
2. **Alternate kernel = new sim contract.** TitleKernel skips `.Row` →
   the sim phase machine waited for a landmark that never arrived →
   infinite loop. Every non-cave kernel must register: landmark label,
   WSYNC count, wall-model target.
3. **WSYNC count is measured, not arithmetic.** Title pad was budgeted
   by summing constants (192→195→196→197) across four rebuilds;
   SetObjectXPos self-WSYNCS, the entry WSYNC and the cleanup WSYNC
   each changed the count. Count with a py65 histogram, then set pad.
4. **Kernel-entry span is cycle-precise.** Moving TIA inits into a
   jsr'd `KernelInit` (fill) added jsr/check/rts (~19c) and an entry
   WSYNC to the VBL-tail→`.Row` span → wall 263→264 every cave frame.
   The span had no slack; comments/estimates are not a budget — the
   sim is.
5. **VBL growth shows up late.** M1 `adc #1` (+4c in VBL) only bit
   when a worst path crossed TIM64T #23 — same class as rule 4 above
   the flicker section (budget the LATEST-in-path, not the first).

**Prevention rules:**
1. Kernel/VBL/kernel-entry changes: run `sim_frame_budget.py` +
   `sim_bomb_fuse.py` in isolation IMMEDIATELY after the structural
   edit, BEFORE writing any feature code. Red guard = stop and fix;
   never stack the next feature on a red build.
2. Never `jmp` out of a `jsr` frame without popping (`pla`/`pla`) or
   making it a true tail-call from a routine that never returns.
3. New/alternate kernels: add sim landmark (`PC_TITLE`), declare
   WSYNC count + per-kernel wall target, verify with a py65 WSYNC
   histogram before Stella.
4. Measure WSYNC counts and wall segments empirically; never budget by
   summing comments or mental arithmetic.
5. VBL-tail→first-kernel-WSYNC is one cycle-precise span — any edit
   there is a timing change and needs sim proof before feature work.
6. When a guard fails after a "simple" change, the change is not
   simple. Revert or fix the regression first; do not debug the
   feature and the guard in the same step.

### Title pad stripe = VDEL stale live-slot (2026-10-07)

**Symptom:** solid 2-px vertical stripe (TIA x75-76) through all 117
title-pad scanlines, colored by COLUP0/1 (turned white when we forced
$0E). Survived `ENAM0/ENAM1 = 0` (once and per-pad-line), `NUSIZ0/1 = 0`,
`CTRLPF = 0`, `RESMP0/1 = 2`, `GRP0/GRP1 = 0`.

**Root cause:** `VDELP0/VDELP1` were still **1** (set at scn20 for the
48px text). The post-art `GRP0/GRP1 = 0` clear wrote only the **DELAYED**
slot; the **LIVE** slot kept the frozen stale text glyph (a byte with 2
lit bits at the last RESP position → 2-px column, same byte every line →
solid). Every "obvious" enable reg was correctly 0 — the draw came from
the slot those writes could not reach.

**Fix:** in the title-pad prologue clear, `sta VDELP0 / sta VDELP1`
(=0) **BEFORE** `sta GRP0 / sta GRP1` (=0), so the zeroes land in the
live slot. `kernel.asm` `.TkPad` prologue.

**Rules:**
- **VDEL state is part of "clear the sprite"** — zeroing GRP/ENAM/ENABL
  while VDELP0/1 = 1 is a no-op for the visible slot. Always drop VDEL
  first.
- When all enable regs prove 0 yet pixels persist, suspect the
  OTHER VDEL slot before suspecting emulator/write-path bugs. Diagnosis
  path that worked: color-forcing write (identifies the COLUPx source) →
  reg-class eliminations (NUSIZ/CTRLPF/RESMP/ENAM each measured) →
  read VDELP's last value from the py65 trace (`sta $25/$26` A column).
- Failed-but-reasonable experiments get REMOVED after the fix; only the
  VDEL reorder stays (experiments E1/E4/E6/E7, see
  `plans/intro_screen_fix_plan2.md` Outcome).

### HERO Power Bar Analysis (2026-09-22)

Verified against `docs/hero/hero_bank0.asm` + screenshots `screenshots/hero_001.png`..`hero_007.png`
(bar region x=242..702, y=444..464).

**Visual behavior (measured from screenshots):**
- Single continuous bar, NOT mirrored/symmetric. Yellow (remaining) left,
  red (consumed) right. Red grows right→left as time depletes.
- Orange single-pixel separator at the yellow/red boundary (ball sprite).
- Margins at screen edges (grey background outside the bar).
- Bar height: 3 scanlines (HERO's setup loop runs 3 iterations: X=8→4→0, DEX×4).
- Full→empty progression: hero_001 (100% yellow, 0 red) → hero_007 (3% yellow, 440px red).

**HERO's CTRLPF writes (decoded from raw bytes in hero_bank0.asm):**
- `LDA #$34 / STA CTRLPF` before bar: %00110100 = reflect OFF (D0=0),
  priority ON (D2=1), ball 8 clocks (D4-D5=%11).
- `LDA #$30 / STA CTRLPF` after bar: %00110000 = reflect OFF, priority OFF,
  ball 8 clocks.
- Hero enables ball during bar: `LDA #$90 / STA ENABL` (ball ON) +
  `STA HMM0` (missile/ball horizontal motion).

**Bar setup loop (3 scanlines):**
- `LDA #$D0 / LDX #$08 / SEC`, then per iteration: WSYNC, store A to $87,X,
  SBC #8, store A to $85,X, SBC #8, DEX×4, BPL. Produces values
  $D0,$C8,$C0,$B8,$B0,$A8 in ZP $85-$8F — cycle-count data for the
  mid-scanline COLUPF change (early shutoff technique).

**Color bytes for our bar (kPalette, `(hue<<4)|(luma<<1)`):**
- Yellow: hue 1 luma 6 = **$1C** → RGB(232,232,92) ≈ screenshot (224,224,80).
- Red: hue 4 luma 2 = **$44** → RGB(176,60,60) ≈ screenshot (176,48,48).
- Existing HUD greys/greens unchanged: lives=$C6, bombs=$46, grey BG=$06.

**Our implementation plan (HERO Method 2: playfield + ball):**
- Reflect mode CTRLPF=$05 + PF0=$E0 (bit4 OFF) gives margins at both screen edges.
- PF1=$FF, PF2=$FF for solid bar body.
- Mid-scanline `STA COLUPF` from yellow→red at BarLevel-derived cycle delay.
- Ball (ENABL) at boundary for sub-block smooth edge (step 2).
- BarLevel 0-16, TickCounter max 255 (single byte) ≈ 68 s total (approximation accepted).

**Full plan: `docs/power_bar_plan.md`**

### Power bar: H3c dual-path + H3d yellow-line fix (2026-09-23)

**Architecture (bank1 MenuMain):**
- Setup (PF shape, grey `COLUPF=$06`, GRP0/NUSIZ0, `CTRLPF=$05`) runs **before**
  TopGap — grey-on-grey over the 4 gap lines, so no visible line above the bar.
- After ball `SetObjectXPos` + `sta WSYNC` / `sta HMOVE`: only `lda #1 / sta ENABL`
  + `ldy BarLevel / cpy #BAR_MAX` + path dispatch. **HMOVE-line content ≤51c**
  (must stay ≤76 or the next bar line is skipped → doubled yellow + HUD shift).
- Yellow `COLUPF=$1C` is written **only** on the 3 bar lines. Gap/`BarGap` uses grey.
- Dispatch: `bne .BarRedSetup`; F=0 falls into `.BarRedF0`; `beq .BarRedF1` for F=1;
  `jmp .BarRedFull` for F=2,3,4 (avoid `bne .BarRedFull` page-cross F5→F6).
- Tables: `BarDelayTable` / `BarFineTable` / `BallXTable` (121 entries, B=0..120).
  Fine ∈ {0,1,2,3,4}; BallX = actual body pixel `3*cycles-69` per path.
  **Always regenerate tables from path cycle counts in a script** — hand transcription
  caused 9 mismatches once.

**H3d roots:** (1) yellow `COLUPF`+PF on the HMOVE line = permanent 1px yellow
above bar; (2) red-path setup on that line ≥78c = skipped line = thickness doubles
and HUD rows push down. Fix = move setup before TopGap; keep HMOVE line short.

**Future (user):** smaller px/step + more steps/s (plan **H4**) — redesign tables
under the same ≤73c path budget before changing the tick.

### php/pla X-preserve sets decimal mode (2026-09-23) — NEVER repeat

**Bug:** To keep `EnemyIndex` in X across `jsr IsRoomDark`, code used
`php / tax / <call> / pla / tax / plp`. After `pla`, X still held the **saved
flags** (from `php`), not the saved X. The following `plp` then restored **X
into the flags**. When X happened to have bit 3 set, **D (decimal mode) was
enabled** — every subsequent `ADC`/`SBC` became BCD math. Symptoms: stuck
player, vertical-rectangle miner, black playfield, garbage collision.

**Fix:** Do **not** preserve X across a call with php/pla/tax/plp. Make the
callee clobber-safe and reload the value in the **caller** instead:
`jsr IsRoomDark` (clobbers A/X only, Y safe) then
`lda (EnemyDataLo),Y / tax` to reload type before `EnemyColorTable,X`.

**Rule:** Never invent stack-preserving register dances. If a routine must
return a value, put it in A (or a documented ZP temp). Callers reload.

### Origin Reverse-indexed: bank0 code must end before $FC68 (2026-09-23)

F6 fold pads live at fixed `org $FC68` / `org $FC70`. DASM errors
`Origin Reverse-indexed` if main code (everything before those orgs) grows
past `$FC68`.

**When adding bank0 routines that push the end over `$FC68`:** move **leaf
helpers** (not the fold pads themselves) **after** `org $FC70` — same pattern
as existing `AddScore` / `ReloadLevel` (S5.x moved `HotOverlapFlag` to
bank2 instead). `jsr` is absolute, so post-pad placement is fine. Never
move `Overscan` without syncing bank1's `jmp $Fxxx` (ToGameStub at
`$FC70` must match) — this fired 3× in the S3.x refactors alone
($F182→$F176→$F173); the fold-pad byte-identity guard catches it, but
sync the literal by hand.

**This session:** `AddScore` alone overflowed (fc68→fc72). Fixed by moving
`AddScore` + `ReloadLevel` after the pads. Build green: 4×4096, folds match,
Overscan still `$F14D`.

### Score rewards (2026-09-23): +50 kill, +75 wall, no fire hack

- **Removed** bank1 fire-button `INPT4` → `+$50` hack (was demo-only).
- **`AddScore`** (after fold pads): A = BCD amount (`#$50`/`#$75`).
  `ScoreTe` packed BCD (`tens*16+ones`), `ScoreTh`/`ScoreHu` binary 0-9.
  Overflow: `$a0` wrap → inc Hu; Hu≥10 → wrap, inc Th; Th≥10 → cap 9.
- **Call sites (bank0 overscan):**
  - `CheckEnemyHit` after `sta DeadEnemyIdx` (non-lamp) → `#$50`
  - `BombEnemyBlast` after kill → `#$50`
  - `BombMarkWalls` only when WallMask bit **was clear** → `#$75`
    (and-ora with existing mask; already-broken → skip score)
- **Score persists** across `ReloadLevel` (not cleared on death).
- Score display is 6 digits, right-aligned: `0 0 ScoreTh ScoreHu tens ones` → "000075" for 75 points.
  ptrs 1-2 = leading zero; ptrs 3-6 = value. Max 9999 → "009999".

### Editor flicker budget (2026-09-23)

`MapCanvas`: **max 2 elements/room** (`kMaxRoomElements`) and **max 1 element
per row** (miner/enemy/lamp share a row budget; same ≤2 cap enforced on data
by `verify_build` objects >2). Warnings via `QMessageBox`.
Rationale: GRP1 is one sprite — more simultaneous objects → more flicker
(rotating `SelectActiveObject`). Restrict at authoring time.

### Open items (refresh 2026-10-01)

- **RESOLVED 2026-10-07** — *BombEnemyBlast can kill lamps* (type 5): the
  blast loop now skips LAMP (`bank2.asm BombEnemyBlastBody`: `cmp #LAMP /
  beq .BEBNext`), so a lamp survives, keeps its dark-room trigger and no
  phantom +50 is awarded. **Guard added 2026-10-18:** `tools/test_bomb_lamp.py`
  (6 cases: enemy dies / lamp survives in either slot order, lamp-only = no
  kill, pre-dead enemy, range gate `|dcol| < 2`, one kill per blast). The
  entry above sat stale for 11 days — when picking up an "open item", verify it
  against the code first.
- **Phase wall = one-time crushable wall (user ruling 2026-10-18).** A
  full-band stripe cannot be crossed in one pass: falling 48 px from a standing
  start takes ~55 frames (subgravity 8/256 px/f²) while PhaseBlink's OFF half is
  45 frames — measured by `tools/qa_sweep.py`. That is INTENDED: taking the
  crush kill latches the removal (`EnemyDeadMask b6`), which force-opens the
  cell until the next `EnterRoom`, so the wall costs one life and is open for
  the rest of the room visit. Do not "fix" the blink into a timing gate without
  a new user ruling.
- **Raft = a row-2 platform cell** (`RAFT` tile 6): `tile_to_char` renders it
  as a solid wall cell, so it is a static platform you can stand on (~RoomY 84)
  while the `bottom_band` water below kills at `RoomY >= 125`. Authored with
  the editor's ADD_RAFT brush (row 2, water room, painted on an AIR cell) and
  enforced by convert (`RAFT` row 2 only; raft models need `bottom_band`). It
  is NOT a moving/rideable object — motion has never been specified; ask the
  user before adding any.

- **Cross-bank Temp conflict (documented, allowlisted):** bank1 `Temp` =
  `$AD` = bank0's `TickCounter` slot (NOT bank0's `Temp` at `$88`) —
  bank1 uses it as its score-init first-frame flag (`inc` once). Deliberate;
  `check_equ_sync.ZP_ALLOW` records it. Fragile if either side's frame
  phase changes.
- **Tentacle residual (user-accepted):** probe still lets it enter walls
  slightly on the left — PHM's entry uses PLAYER origin/width for the
  candidate box; fix = per-enemy origin offset in `UE_Tentacle`. Details:
  `docs/bank0_refactor_progress.md` (S3.2 entry).

## Skill References

- `docs/zp_layout_skill.md` — Complete zero-page memory map for all banks (bank0/bank1/bank2), with conflict detection rules and historical crash lessons
- `docs/font/48px_score_skill.md` — 48-pixel sprite score technique (NUSIZ copies + VDELP cross-buffer), known bugs, and implementation guide
