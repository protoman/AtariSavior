# HERO-Aligned Kernel Plan (2026-10-21)

**Goal:** move the renderer from "compute at runtime" to HERO's "precompute per
line" model, so that four things become possible without cutting gameplay:

1. **Wall colour is never stolen by a sprite** → the async block (M1) stays
   wall-coloured even when an enemy/miner/bomb shares its scanlines.
2. **Two objects draw every frame** → no `SelectActiveObject` rotation flicker.
3. **Sprites taller than 8 rows**, with per-line colour (HERO's 26-line GRP1
   object), instead of one 8-row art row per type.
4. **None of the above costs scanlines we do not have** — the budget comes from
   deleted work and from a bank0 eviction funded by shrinking the live stage.

**Space trade (user-approved 2026-10-21):** the live stage drops from 20 to
**4 levels**. Level data is generated, so nothing is lost: the 20-level stage is
kept as a test-owned reference and the generator still exercises 20 levels in
`tools/test_generator.py` (temp dir, never the live file).

---

## 0. Baseline (measured this session)

`tools/rom_size_report.py --md`:

| bank | code | data | fill | free |
|---|---|---|---|---|
| bank0 | 3045 | 370 | 663 | 681 |
| bank1 | 2452 | 449 | 1001 | 1195 |
| bank2 | 1273 | 1757 | 1065 | 1066 |
| bank3 | 1174 | 1055 | 1856 | 1867 |

- Level data (20 levels): index 140 + tables/blocks/extras 2128 + models 334 =
  **2602 B**; converter capacity report: bank2 level-table slot **1676 B used /
  647 B slack**, bank3 extras **632/1088** (456 slack), bank3 shapes
  **334/747** (413 slack, 53 shapes).
- bank0 is byte-full: pre-pad headroom ~1 B, twins pinned at `$F8DD`/`$FDDA`/
  `$FDE1`/`$FC68`/`$FF00`.
- `.Line` worst path **measured** (`plans/hero_cycle_ledger.md`): 72 line
  cycles (73 on the `A0=10` line, where `PlayerColTable` crosses `$F8/$F9`), so
  **0 c against the 73 c contract, 3 c to the absolute line**. Easy lines sit at
  52-65 c but each ends in its own `WSYNC`, so **slack is not transferable** —
  only the worst path matters.
- `.Row` setup line **measured**: it is a **2-scanline window** (WSYNC store at
  c90/93 of a 152 c window) with **~60 free cycles after `sta PF2`**. That
  window, not the `.Line`, is where the per-band repositioning (Phase 5) lives.
- Live stage: **28 of 42** async rooms show the enemy-coloured dash (all blocks
  sit on band 1, the band enemies live in).

**Measured after the 4-level cut** (Phase 1 step 5, 2026-10-21):

- level data **2602 B → 127 B** (index 28 + tables/blocks/extras 51 + models 48);
- bank2 level-table slot: 79 B used → **slack 2244 B** (the eviction target);
- bank3 extras **8 B / 1088** (slack 1080), shapes **48 B / 747** (slack 699);
- bank0 pre-pad headroom **16 B** (ends `$FC58`) — the AGENTS "1 B" note was
  stale; the 12 B `BeamMask` table plus the folded fetch went into the `$FExx`
  fill, so the pre-pad figure did not move.

**Measured after the StageSlot1 eviction** (step 1 of the 2026-10-22 handoff,
`tools/rom_size_report.py --md`):

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3128 | 434 | 516 | 3562 | 534 |
| bank1 | 2448 | 449 | 1005 | 2897 | 1199 |
| bank2 | 1537 | 168 | 2390 | 1705 | 2391 |
| bank3 | 1174 | 155 | 2766 | 1329 | 2767 |

- bank0 **3816 → 3562 used** (−254 B); the `$F744` fill now holds only
  `Slot1Hook` (`$F750`) and **202 B** of free space up to the `ObjSprites` pin
  (`$F850`) — that is the Phase 4/6 workspace.
- `StageSlot1` + `PinSlot0` + an `ObjSpriteOffTable` copy live in bank2's
  `$FAC0-$FBCF` block (slot `spill_F9D9` end moved `$FBD0 → $FAC0`; the level
  data still starts at `$F9D9`, so no generated address moved). Block is
  flush against the `$FBD0` EnterRoom twin pin: growth there fails the build.
- Entry is the split pad `CallPad_StageSlot1` at `$FBE5` / bank2 `jmp` at
  `$FBE8` (`verify_build.MOVE_PADS`). Frame budget unchanged: wall model
  `{265: 3, 267: 1098}`, cave WSYNC 195 — i.e. the eviction cost no line.
- bank2 level-table slack **2244 → 1969 B** (the eviction target for Phases 5-6
  data is still open).

---

## Phase 0 — Cycle ledger from `bank0.lst` — ✅ DONE (2026-10-21)

Result: `plans/hero_cycle_ledger.md` + `tools/cycle_ledger.py`. Headline: the
`.Line` worst path is **72 line cycles** (73 on the `A0=10` line, page-cross),
so 0 c against the contract; the `.Row` setup line is a **2-line window with
~60 free cycles**; the beam fold is confirmed (−4 c) and the other two
candidates are closed; the `.ObjZero` colour restore already exists, so the
tint is a carrier problem (Phase 3 rewritten).

### Original procedure (kept for re-measurement)

**Why:** every later phase spends the same resource (cycles on the worst
`.Line` path and on the `.Row` setup line). We currently only have arithmetic in
comments. Get the real numbers first.

Work:
1. Parse `src/bank0.lst` for the `.Line` region and the `.Row` setup region.
2. For each of the path classes, tabulate PC → mnemonic → cycles → cumulative
   phase (CPU cycles from the start of the line), and the exact landing phase of
   every store (`COLUP0`, `ENAM0`, `GRP0`, `GRP1`, `COLUP1`, `PF0/1/2`,
   `COLUPF`, `ENABL`, `WSYNC`):
   - colour+beam both on / colour on beam off / both off;
   - player in-window / out (`.GrpSkip`);
   - object in-window / first line below (`.ObjZero` A==8) / out.
3. Compute slack per path = 73 − worst cumulative (the project's stall limit;
   the `sta WSYNC` write must land ≤ c73).
4. Confirm or refute the three candidates from `docs/hero_async.md` §4:
   - laser beam block fold (one colour byte carrying the beam flag, HERO's
     CTL-bit0 trick): expected **−4 c**;
   - object window test (`tya/sec/sbc/cmp/bcs` = 11 c) replaced by a VBL-staged
     row start + counter: expected **−4 c**;
   - loop control (`sta WSYNC/dec/bne` = 11 c vs HERO's `DEY/BMI` = 4 c): Y is
     the running `A0` (sprite row index), so this is expected **0 c** — record
     why, close the item.
5. Do the same for the `.Row` setup line (currently 74-77 c) — Phase 5 needs its
   exact slack.

Deliverable: `plans/hero_cycle_ledger.md` (tables pasted above), linked from this
plan. Gate: tree unchanged except the new doc; `sim_frame_budget` untouched.

---

## Phase 1 — Space: 4-level stage (✅ done) + bank0 eviction (next)

**Why:** Phases 2-6 need bank0 bytes and a *move target*. The level cut is the
only source of free space that costs no gameplay.

Steps:
1. **Preserve, do not delete:** `cp src/rooms/stage.json
   src/tests/stages/stage_20_levels.json` (test-owned; `build.sh` only reads
   `rooms/stage.json` or `STAGE_FILE`). The 20-level stage stays recoverable and
   rebuildable any time with `STAGE_FILE=… ./build.sh`.
2. Regenerate `rooms/stage.json` with **4 levels** through the editor/generator
   (`--generate-stage`; extend the CLI if the count is hard-coded — `PlanFor(l)`
   is level-indexed, so 4 levels is a truncation, not a new design). Never hand
   edit rooms/models/generated.
3. Sync the kernel hand-copy: `LEVEL_COUNT = 20 → 4` (`bank0.lst` guarded by
   `tools/test_level_bank.py`).
4. Re-freeze the test banks (`bash tools/freeze_test_banks.sh`) and run the full
   battery. Expected fallout to fix, not to mask:
   - `test_level_bank` (LEVEL_COUNT/LEVEL_SHAPE_COUNT sync) — expected to pass
     after step 3;
   - `test_band_restage` (walks the live stage) — adapts, must stay green;
   - `sim_bomb_fuse` forces level 2 — still exists in a 4-level stage;
   - generator feature gates (phase ≥6, async ≥7, hcrunch ≥14) become vacuous on
     the live stage **by design**. Coverage of those features stays in
     `src/tests/rooms` (already carries 1–3 async patches + a feature room per
     level 3/4) and in `tools/test_generator.py` (20 levels, temp dir).
5. Re-run `tools/rom_size_report.py --md` **and** the converter capacity report
   into a temp dir
   (`python3 tools/convert_level.py --stage src/rooms/stage.json "$TMP"`) and
   paste the new numbers into §0 of this plan.
6. **Evict bank0 chunks** into the freed bank2 slot, following
   `plans/bank0_space_plan.md` (survey + "Movable chunks"). Order: title
   subsystem (~390 B cold) first, then the next cold block from the survey.
   Every move is atomic across banks: code **and** its data move together, the
   reader crosses too (call pad + byte-identical twin where a `sta $1FFx` must
   survive), `verify_build` pins updated, then build + both sims + battery.
   Commit per chunk.

Gate: tree green with the 4-level stage as the default build (done), and the
remaining eviction scoped as a **re-pin**, not a chunk move.

### Eviction is a re-pin, and Phases 5-6 mostly need it only for DATA

`plans/bank0_space_plan.md`'s correction applies: content before a `.ds` pin
cannot be moved without shifting the pin **and every cross-bank twin**
(`$F8DD $F9B8 $FB00 $FBD0 $FBFC $FC49 $FE00 $FE48 $FE90 $FEF0 $FEF6 $FF00
$FFE6`). Consequences for this plan:

- **Code bodies do not need the re-pin.** The kernel's 16 B of pre-pad slack
  (`$FC58-$FC67`) is enough for `jsr` hooks; bodies live in the bank2 slot
  (2244 B free) behind a CallPad + `ReturnPad`, the established pattern.
- **Art data does.** `ObjSprites` ($FE48-$FE8F) and `ObjColorTab`
  ($FE00-$FE47) sit flush against the `$FE90`/`$FE48` pins, so tall art (Phase
  6) needs the `$FE00` cluster re-pinned down by the added rows — a coordinated
  4-bank move (bank0 art + every twin + `verify_build` pins + `frozen/`).
  Do that once, for a batch of types, not per type.
- `BeamMask`'s 12 B freed by Phase 2 went into the `$FExx` fill (the pads absorb
  it), so the pre-pad figure did not move — expected, same reason.

---

## Phase 2 — Reclaim per-line cycles — ✅ the beam fold LANDED (2026-10-21)

Measured after the fold (`tools/cycle_ledger.py`): P1 **72 → 68**, P2 65 → 61,
P3 70 → 66 line cycles; `BeamMask` deleted, `verify_build` pins PlayerColTable
bit 1 == row 2 only, `test_laser_s4` rewritten. Wall model unchanged (267.0).



**Phase 0 closed two of the three candidates** (`plans/hero_cycle_ledger.md`
§2): the object window is already minimal (7 c to compute the row + 4 c to test)
and the loop counter cannot come out of Y (Y is the running sprite row). Only
the beam fold survives:

1. **Beam fold — −4 c, byte-negative.** `PlayerColTable[2]` is
   `COLOR_P_YELLOW = $1E` (bit 1 = 1) and every other row is `$48`/`$08`
   (bit 1 = 0), i.e. the table *already* carries the ENAM0 enable bit that
   `BeamMask` repeats. `lda PlayerColTable,Y / sta COLUP0 / and LaserState /
   sta ENAM0` = 13 c against today's 17 c; `BeamMask` (12 B) and its page guard
   are deleted; `verify_build` gains "bit 1 set only at index 2".

Gate: `sim_frame_budget` cave target stays 267.0; the ledger's P1 drops to 68
line cycles (69 on the `A0=10` line) — that 4 c is the entire budget for any
later `.Line` work, so spend it deliberately.

Gate: Phase 0 ledger shows **≥ 8 c freed** on the worst path with the wall model
unchanged (`sim_frame_budget` cave target stays 267.0).

---

## Phase 3 — Async-block tint: a CARRIER fix, not kernel work

> **Sequencing note (2026-10-21):** with the live stage cut to 4 levels the
> generator emits **no async blocks at all** (`patch = level >= 7`) and no
> phase rooms (`>= 6`), so this phase is deferred until the stage grows again.
> The kernel paths stay covered by `src/tests/rooms` (async + phase rooms) and
> by `tools/test_generator.py` (20 levels, temp dir). Re-open this phase when
> level 7 exists — the design below is unchanged.

**Corrected by Phase 0** (`plans/hero_cycle_ledger.md` §4): the `.ObjZero` A==8
`COLUP1` restore is *already in the kernel* (`$f176`, +6 c, already inside the
A==8 path). The sticky colour is fixed. What remains is the 8 scanlines where
the object and the block are both painted with `COLUP1`: one colour register per
line, so no per-line table — HERO's or ours — can give them different colours.
HERO separates by **channel** (moving objects on `COLUP0`/P0, painted/static
elements on `COLUP1`/P1+M1).

Cheapest real fix (the narrow option 2 from the 2026-10-21 discussion, all
measured): move the async block onto the **ball** (`COLUPF`), which no sprite
ever writes.

1. Generator: single-block rooms author the block on the mirror cell (side 0,
   right index `rc = 9 - c`) — cold rooms only, no engine change.
2. Hot rooms (13 of 42 today): stage `RoomM1Hot` from a side-0 row-1 patch as a
   **display** cell (bank3, ~15 B) and route the ball's solid hit through
   `HotOverlapFlag` (`.OSBsolid`'s `sec/rts` → `jmp HotOverlapFlag`, 3 B ↔ 3 B,
   byte-neutral; the body already returns C=1 when cold).
3. Pair rooms keep one M1 block (one ball x per frame) and take the generator
   rule "no enemy/lamp in the M1 block's band".

Verify: staged demo (the `tools/raft_build.sh` pattern) with an enemy on the
block's row; A/B screenshots.

Do **not** try to solve this on the `.Line` side: the measured budget is 0 c and
the physics does not allow it.

---

## Phase 4 — VDEL pipeline: the premise was WRONG (2026-10-22); P0 half landed

**VDEL is not a one-line delay.** Stella (`Player::grp` / `updatePattern` /
`shufflePatterns`) is explicit: a `GRP` write lands in `myPatternNew` and is
rendered **immediately**; with VDEL the live pattern is `myPatternOld`, which is
latched when the **other** player is written. So VDEL moves the landing point to
the other register's store cycle — it cannot make a "written one line ahead"
pipeline by itself, and for P1 it would make things worse (its latch is `GRP0`'s
earlier store). HERO agrees: it clears `VDELP0`/`VDELP1` at cave entry
(`$F2xx: lda #0 / sta $25 / sta $26 / sta $1B / sta $1C`) and uses VDEL only for
its HUD text.

**Measured store phases in our `.Line`** (`tools/cycle_ledger.py`, P1):
`COLUP0 c19`, `ENAM0 c25`, `GRP0 c35`, `GRP1 c58`, `COLUP1 c65`, `WSYNC c68`.
A sprite's pixels start at cycle `(61+X)/3`, so a store only reaches the NEXT
line when the sprite sits left of the boundary:

| store | lands on this line for X ≥ | meaning |
|---|---|---|
| `COLUP0` c19 | — (never) | per-row colour is always this line ✓ |
| `GRP0` c35 | 44 px | player art one line HIGH + colour row off by one |
| `GRP1` c58 | 113 px | object art one line high |
| `COLUP1` c65 | 134 px | object colour row off by one in X∈[113,134) |

**Landed (this pass): `VDELP0 = 1`, `VDELP1 = 0` for the cave** (VBL init,
+2 B, **0 c**). P0's landing moves from `GRP0`'s c35 to `GRP1`'s c58, so the
player's art is correct for **X < 113 px (was < 44)** *and* art row `r` now sits
on the same scanline as `PlayerColTable[r]` — today the art is one line above
its colour for X ≥ 44. Cost: nothing; the wall model stays `{265: 3, 267: 1098}`
and every `.Line` path cycle is byte-identical. Guard:
`tools/test_vdel_cave.py` (frozen-image VDEL init + "every `.Line` path stores
`GRP1`", which is what drives P0's latch — a missing store freezes the player at
the last latched row).

**Not landed — P1 stays immediate, on purpose:** `VDELP1` would latch on
`GRP0`'s c35 store (worse than its own c58) while its colour stays at c65.

**Not landed — the "one byte per line = colour + draw flag" staging: 2 c short.**
A deterministic per-line colour needs the `COLUP1` store in the horizontal
blank (≤ c22), i.e. the byte fetched by the previous line and written from ZP at
the head: `.Grp1` `lda ObjColorTab,X / sta ObjCol` (7 c, unchanged) + head
`lda ObjCol / sta COLUP1` (6 c) = **+6 c** against the **4 c** the worst path
has (WSYNC at c68, `A0=10` crossing line c69, contract ≤ c73). Parked, not
abandoned: the shapes that fit are (a) `ObjSprites+ObjBase` pre-staged into a
2-byte ZP pointer so `lda (ptr),Y` replaces `adc ObjBase/tax/lda abs,X`
(−4 c, needs 2 free ZP bytes — none), or (b) a cut elsewhere.

---

## Phase 5 — Second sprite window (flicker fix)

- Per band: stage the band's object parameters (`ObjBase`, `ObjTop`, X, colour)
  then reposition `P1` at the band boundary. Our bound is small: the editor
  already allows **≤ 1 element per row**, so a room has at most 2 objects and
  they are always in **different bands** → exactly one extra reposition.
- **Cost is 0 extra lines** (Phase 0): the `.Row` setup pass is already a
  2-scanline window with **~60 free cycles after `sta PF2`** — put the per-band
  `RESP1` + `HMP1` + the parameter switch there (after c81, so no
  timing-critical store moves). The `HMOVE` strobe needs HBLANK: the CPU already
  resumes at **cycle 0-3 of the band's first body line**, so `sta HMOVE` inserted
  between the setup's `sta LineCount` and `.Line` lands in HBLANK for free.
- **Measured correction (2026-10-21, after reading `SetObjectXPos`): a
  reposition costs +2 lines, not 0.** `SetObjectXPos` opens with `sta WSYNC`
  (it must start on a line boundary) and its div15 loop runs inside that line;
  the `HMOVE` then needs the NEXT line's HBLANK. So a repositioned band costs
  setup (2 lines) + positioning (1) + HMOVE (1) = **+2 lines vs today**.
  Same cost for phase 6's taller window? No — that is +1 c on the window test,
  no lines.
  Therefore: reposition **only the band that actually hosts the second object**
  (a room with 1 object pays nothing), and expect the wall model to become
  room-dependent — `sim_frame_budget` keeps its 267.0 assertion for the
  single-object scenario and gains a second scenario for the 2-object one.
- Two-slot staging fits the "free in gameplay, bank1-only after the cave read"
  bytes at `$EA-$EC` (ZP map rule 6): slot-1 `ObjBase1/ObjTop1/ObjX1`, staged in
  the VBL exactly like the slot-0 trio, plus one `Obj1Band` byte (which band
  hosts slot 1) so the setup line's `cpx Obj1Band / bne` is 4 B of hook.
  `SelectActiveObject` becomes the stager (no rotation); the slot-0 path and
  the bomb/miner/tally special cases keep their current priority rules.
  **ZP has no free 4th byte for `Obj1Band`** — two ways out, decide at
  implementation time: (a) encode the band in `ObjBase1` bit 7 (all `OBJ_*`
  bases are < 128), or (b) derive it on the setup line from
  `ObjTop1 + RoomY` with two compares (~12 c of the ~60 free). Also keep the
  invariant **slot 0 = the lower band**: bands run 0→1→2, so slot 1's copy can
  never need restoring after a later band.
- Result: `SelectActiveObject` stops rotating — it becomes the staging routine;
  both objects draw every frame, each with its own colour.

Gate: `sim_frame_budget` wall model (267.0, or the measured new target), SCN
single-value oracle at the kernel landmark, staged screenshot showing
enemy + miner + player in one frame with no flicker.

---

## Phase 5 — LANDED (2026-10-21): second GRP1 window, no flicker

`kernel.asm`: `StageSlot1` (VBLANK, called from both `SelectActiveObject` tails)
+ `Slot1Hook` (inline in the `.Row` setup after `sta PF2`) + `BandStart` table.
ZP slot 1 = `$EA/$EB/$EC` (`ObjBase1/ObjTop1/ObjX1`), the bank1-HUD-only bytes
(ZP doc rule 6: VBL write -> cave read is the safe window).

**Rule (jitter-proof, and the reason for the shape of the code):** slot 1
depends ONLY on the room's geometry, never on `SelectActiveObject`'s rotation.
It is staged only when the room's live candidates (enemies + miner) span two
bands, and then it is the HIGHEST-band candidate. The first version used
"first candidate above slot 0's band", which made the frame alternate
**267/269 lines every 4th frame** (the bomb owns `BombTimer&3==0`, so slot 0's
band flipped with it) — `sim_frame_budget` caught it immediately
(`cave kernel WSYNC diverged: [195, 197]`). Never re-derive slot 1 from slot 0.

**Cost:** the early-out (5c) sits in the setup line's free tail, so a
single-band room pays 0. A room that DOES host slot 1 pays 2 lines at that
band (SetObjectXPos must start on a line boundary; the HMOVE needs the next
line's HBLANK) -> 269 lines. Constant per room, so no shimmer.

**Known limits (by design, not bugs):**
- Same-band rooms keep the old 30 Hz rotation: two objects in one band cannot
  share one GRP1 sprite.
- Slot 0 still owns its rotation (bomb priority), so a lower-band object
  blinks on the bomb's 1-of-4 frames.
- `REFP1` is not switched per band yet: slot 1 draws with slot 0's reflection.

**Current reach: zero.** The live 4-level stage has NO room with two objects
(`rooms/*.json`: 0 rooms with 2+ objects), and neither does `src/tests/rooms`,
so the path is inert and the sim never enters it (wall model stays 267
everywhere: `{265: 3, 267: 1098}`).

**Verification recipe when a 2-object stage exists** (do this BEFORE trusting
it in play): author a room in `src/tests/rooms` with one enemy at Y<48 and one
at 48<=Y<96, `bash tools/freeze_test_banks.sh`, then assert (a) the room's
frames measure 269 lines, (b) both objects are drawn in the SAME frame
(py65: GRP1 writes in two bands with `ObjBase` swapped at the band boundary),
(c) the solo-object rooms still measure 267.

## Two-band rooms: no more 1-of-2 flicker (2026-10-22)

`StageSlot1` pinned slot 1 to the highest-band candidate, but slot 0 kept
ROTATING through all candidates (`FlickerFrame` modulo the count), so in a room
whose two objects span two bands (raft in band 2 + miner in band 1) the lower
one was drawn only on the frames the rotation landed on it — the miner flicker
the user reported.

Fix: `PinSlot0` (new, in the free `$FB20` fill), called from `StageSlot1` right
after the two-band check. It writes `FlickerFrame = desired + count - 1` so the
next frame's `inc` + modulo lands exactly on the OTHER candidate:
- slot 1 = the miner -> slot 0 = enemy slot 0;
- slot 1 = an enemy -> slot 0 = the miner;
- no miner (two enemies) -> slot 0 = `max_index ^ 1`.
The bomb keeps its own 1-of-4 frames (the pin is skipped while `ObjBase` is
`OBJ_BOMB`). Same-band rooms never reach the pin, so their rotation is
unchanged. Verified in py65 in the raft+miner room: `FlickerFrame` pinned,
slot 1 = the raft, slot 0 = the miner every frame.

## Phantom M1 dash fixed (2026-10-22)

`PositionBallM1` enabled M1 whenever `CollisionEndX` was non-zero, but that byte
is the **laser wall-clamp's scratch** (`LaserWallClamp .LWpSet` writes a marker
there every frame) and the async M1 staging does not exist yet (Phase 3 is
deferred). So any leftover marker lit M1 at a garbage X — the short dash the
user saw hovering over the raft (band colour, 1 line tall).

Fix: the M1 X now lives in its **own** byte, `M1X = LevelEnemySpare2 ($B0)`
(documented FREE), read by `PositionBallM1`. Nothing writes it today, so no
phantom; the Phase 3 room load must stage it (and only it).

## The "raft zig-zag" was the slot-1 mid-frame HMOVE (2026-10-22, root cause)

User repro: level 4 room 4, hands off, the rider slides relative to the raft.
Debugger RAM (from the user's screenshots — the ZP grid is already in them)
showed `RoomX` = 55,56,57,58,59,59 = **+1 px/frame, exactly the raft's step**,
so the carry was right. The *drawn* player, though, advanced ~2 px/frame and
sawed back and forth — a fine-adjust (HMP0) artifact, not logic.

Cause: `Slot1Hook` (Phase 5) repositions the second object mid-frame and strobes
its own `HMOVE`. HMP0/HMM0/HMBL still hold the PLAYER's / laser's / ball's fine
values from the VBL, so that second HMOVE applied them again — the player's fine
adjust doubled. As `RoomX` walks through a coarse cell the fine value cycles
0..14, so the drawn X jumps +15 and back: the visible zig-zag. It needs TWO
objects spanning two bands (here raft + miner), which is why other rooms are
clean.

Fix: before the hook's HMOVE, clear HMP0/HMM0/HMBL (HMP1 stays — it belongs to
the slot-1 sprite, set just above). Verified in py65: the VBL HMOVE ($F0AC)
carries HMP0 = $10/$F0/$E0..., the hook HMOVE ($F844) now carries **$00**.

Guard: `tools/test_slot1_hmove.py` (static: the three clears must precede the
hook's HMOVE, and HMP1 must not be cleared). Space: +11 B in the `$F744` fill,
paid by moving `EnemyColorTable` + `ObjSpriteOffTable` (both `abs,X`) into the
free `$FE00` fill.

**Rule 1:** any second `HMOVE` in a frame must be preceded by clearing every
fine register it must not re-apply — HMOVE is not idempotent for untouched HMPs.

**Rule 2 (the follow-up bug, same session):** those clears must sit BEFORE the
`sta WSYNC` that precedes the HMOVE, never between WSYNC and HMOVE. They cost
~14 cycles, and an HMOVE written after cycle 0 of HBLANK gives up part of the
fine shift (late-HMOVE penalty) — slot 1's sprite then snaps in ~4 px steps
("the raft moves one tile at a time"). Verified in py65: the hook's HMOVE is
3 cycles after its WSYNC, the same as the VBL reference HMOVE ($F0AC), with
HMP0 = 0. `tools/test_slot1_hmove.py` now asserts clears < WSYNC < HMOVE.

## Raft: the REAL cause was the record's dir bit (2026-10-22, follow-up)

The user was right that the raft was not on a wall. Editor enemy `x` is a
DISPLAY COLUMN (0..39): `convert_level.enemy_x_px(12)` = **55 px**, and the
converter hard-fails a raft whose cell is not open water — so the raft was
never boxed in. (An earlier note in this file claiming x=12 px was wrong:
editor column 12 -> 55 px.)

Real cause: the enemy record packs **type|dir in ONE byte** (b7 = dir) and
`UEDispatch` compared it RAW against `cmp #ENEMY_RAFT`. The user's raft had
dir=right, so it read **$87** and fell through every type arm — `RaftBody`
never ran. Measured in the real ROM (level 4 room 4, `EnemyData=$FA09`):
record `$87,111,96`, `RaftBody` never entered, `EnemyRamY` stuck at the
authored 96 (no tide), so nothing floated and no rider could be pinned.

Fix: mask b7 at the single type-compare entry (`UEDispatch: and #%01111111`)
and in `CheckEnemyHit` (a dir=right enemy read $81 and was unkillable). Lamps
and rafts have no direction, so the converter now emits `dir: 0` for them —
that restores the RAW `cmp #LAMP` guards in the bomb blast and both laser hit
bodies at zero ROM cost (a b7-set lamp read $85 and was blast-killable).

Verified in the real frame loop: `ran=True`, `EnemyRamY` = 125/126 (tide),
rider offset **0** on every frame (`dx == dRaft`).

Guards: `tools/test_raft.py` case 5c (UEDispatch must dispatch `$07` AND
`$87`) and `tools/test_enemy_movement.py` (static: the mask at UEDispatch's
entry and in CheckEnemyHit). Space: the +4 B pushed the `$F744` fill 4 B over,
so `BandStart` moved into the free `$FE00` fill (`cmp BandStart,X` is abs,X).

**Lesson:** one byte carrying two fields is a trap for every `cmp` — mask at
the compare site, and prefer emitting a canonical value (dir 0) for types that
do not use the field.

## Jet: the REAL cause was the fall clamp (2026-10-22, follow-up)

The ramp change alone did not fix the user report ("press Up after a room
change and he does not stop until the ground"). Reproduced in the simulator on
level 4 (3 stacked gap rooms): after the transition `JetPower` was $30 (thrust
at max) yet `vy` stayed **exactly $0180** every frame.

Write-trace of one frame: `vyLo` = $88 (gravity) -> $58 (thrust subtracted) ->
**$80** (clamp). The down clamp compared only the HIGH byte:

    cmp #>MAX_FALL / bcc .Integrate / lda #>MAX_FALL ... sta vyLo

With `vyHi == $01` the `cmp` is EQUAL, so every speed in $0100..$017F was
rewritten to exactly $0180. Thrust was computed and thrown away — a falling
player could never be slowed, at any JetPower.

Fix: compare the low byte when the high bytes match (`bne .FallClamp` /
`lda vyLo / cmp #<MAX_FALL / bcc .Integrate`). Verified in the real frame loop:
`vy` now steps $0180 -> $0158 -> $0130 -> ... -> rising, arresting in 10 frames.

Guard: `tools/test_jet_clamp.py` (new) drives the real inline
`UpdateP0Vertical` block on the frozen banks with a poked airborne state:
terminal-fall thrust must reduce vy by exactly `JET_MAX - GRAVITY`, the brake
must finish in <= 12 frames, a 2.0 px/frame overspeed must still clamp to
MAX_FALL, and a sub-1 px/frame fall must be left alone. It was RED on the
pre-fix frozen bank.

**Lesson:** a byte-wise clamp that compares only the high byte *rewrites* every
value in the same high-byte page. Model-based tests (which use a proper `>`
compare) cannot see it — only a ROM-level test can.

## Jet physics: HERO feel (2026-10-22, user report)

Symptom: falling at terminal speed, pressing Up barely helped — the fall only
reversed after ~1 s (more than a room height). Cause: thrust was a ramped
accumulator behind a `EnemyRamP & 3` gate, so JetPower grew 1/4 frames and
stayed BELOW gravity (8) for ~32 frames; at terminal 1.5 px/frame the net
deceleration was 12/256 px/frame² → ~32 frames after the ramp finally caught up.

Fix (behaviour, HERO-style — a held jet catches a fall immediately):
- While FALLING (vy > 0) and Up held: `JetPower = JET_MAX` at once.
- From rest / while rising: ramp +1 EVERY frame (gate removed) to JET_MAX.
- `JET_MAX` $14 -> $30 (48): net climb accel 40/frame², capped by the -$0100
  rise clamp, so max climb stays 1 px/frame; a terminal fall stops in 10 frames.
- Float-on-release ($B6 countdown) and the respawn hover are untouched (they
  key off `JetPower >= GRAVITY+1`, which is reached sooner now, not later).

Guards: `tools/test_respawn_hover.py` (new `brake_frames()` assertion: <= 12
frames from a terminal fall, plus the updated ramp mirror) and
`tools/test_water_respawn.py` (same mirror). Both sims green, battery 0 fails.

## Raft bug fixed (2026-10-22, user report: rider "zig-zags" on the raft)

**Cause (proven, not guessed):** in the authored raft room (level 4 room 4 of
`rooms/stage.json`: model 2, `bottom_band`) row 2 is solid at logical cols
0,3,4 / 15,16,19 (PF0 $90, PF1 $80, PF2 $98). The raft's authored x=12 puts its
span (cols 1..3) INSIDE that ledge, so BOTH probes hit a wall and it turns
every frame without ever moving (unit chain: 13 frames, 0 px). `.RaftTurn`
returns before `.RaftRide`, so the pin never ran → the rider fell through the
stuck raft, crossed the 125 water-kill line, respawned, and repeated. That
position churn is the "keeps changing / zig-zags very fast" report.

**Fix:** the rider pin moved from `.RaftRide` into `.RaftGo` (right after the
ride gate), so it no longer depends on the raft being able to move. Rising
still escapes through the gate (`vyHi < 0` → `.RaftNoRide`), so the thrust rule
is intact. Guard: `tools/test_raft.py` case 5b — a boxed-in raft must not move,
must still pin the rider to `raft_top - 12`, and must zero the fall speed, over
a 40-frame chain (fails on the pre-fix frozen bank, passes after).

**Still a DATA issue:** the raft cannot ferry anything while it is boxed in.
The open water in that room is logical cols 5..14 (x 20..59), so the raft's
record should sit around x=40. The live stage is the user's — tell them, do not
edit it.

## Phase 6 — tall enemy art LANDED (2026-10-21)

Every GRP1 object (enemy/miner/bomb/raft/key) is now **12 rows tall** instead
of 8: `OBJ_WINDOW = 12` is the draw window, `PLAYER_HEIGHT` stays 8 so the
collision/overlap tests (`#PLAYER_SPRITE_H + PLAYER_HEIGHT - 1`) are unchanged.

- **Hit box matches the art (2026-10-22):** `PLAYER_HEIGHT = 12` is now both the
  draw window and the enemy/miner collision box, so the `objToObj` Y tests
  (`#PLAYER_SPRITE_H + PLAYER_HEIGHT - 1`) accept RoomY - objY in [-11, +11].
  The separate `OBJ_WINDOW` alias from the first cut was folded back into
  `PLAYER_HEIGHT` — one constant, no indirection. Battery stayed 0 fails.
- `OBJ_*` EQUs and `ObjSpriteOffTable` use stride 12 (0,12,...,96); max index
  107. `verify_build`'s page guard was bumped 71 -> 107.
- `ObjColorTab` (108 B) lives in the `$FB20` fill at `$FB1F`; `ObjSprites`
  (108 B) in the `$F744` fill tail at `$F850` (pinned by `.ds $F850`; low byte
  $50 + 107 = 187, one page).
- Art: each type keeps its 8 original rows and gains 4 (legs / tail / taper /
  post / teeth). Colour rows 8-11 = the type's own colour (miner = grey legs).
- Zero cycle cost: only the compare constant and the index offsets changed, so
  `sim_frame_budget` still reports the same wall model (267) and the battery is
  0 fails.

**Trap fixed on the way:** `parse_lst` in `verify_build` only sees a label line
with NO trailing comment — putting `; ...` on `ObjSprites:` / `ObjColorTab:`
makes the label invisible and the guards fail with "label not found".

**Stale-expectation tests updated with the stride** (they hardcode offsets, not
labels): `test_miner_colors` (56/8/40/64 -> 84/12/60/96), `test_raft`
(OBJ_MINER 56 -> 84), `test_room_dark` (OBJ_MOTH 8 -> 12).

### Next in Phase 6 (optional)

- Art polish: the 4 new rows per type are first-pass; a screenshot pass can
  improve legs/wings.
- 16 rows/type (144 B each) does NOT fit yet: it needs the Phase 5 code moved
  out of the `$F744` fill first.
- Colour rows 8-11 tint the M1 block on those lines (Phase 3, deferred — the
  live 4-level stage emits no async blocks).

## Phase 6 — first 26-row design LANDED: SPIDER (2026-10-22, user art)

The user authored the SPIDER as a 26-row, 8-px design (HERO's object height,
measured from `hero.bin` `$DD69` bit0 = rows 11..36). This is the first type to
use the per-type `ObjHeightTab`, so it also exercised every consequence of a
design growing:

- **Offsets are no longer a uniform stride.** A design owns its block, so
  SPIDER (26) pushes everything after it: KEY 0, MOTH 16, SPIDER 32, LAMP 58,
  TENTACLE 74, BAT 90, SNAKE 106, MINER 122, BOMB 138 → table size 154 B
  (was 144). `ObjHeightTab[SPIDER] = 26`, every other type still `OBJ_WINDOW`.
- **`ObjSprites` base moved `$F830` → `$F826`** so the table still ends before
  the `$F8C0` RaftBody pin AND stays in one page (`$26 + 153 = $BF`).
  `verify_build`'s page guard is now `+153` (was `+143`), and
  `test_miner_colors` checks the same bound.
- **`ObjColorTab` is 154 B at `$FB1F`** (ends `$FBB9`, still clear of the
  `$FBD0` pin). SPIDER colour bands: `$14` legs (rows 0-8), `$22` thorax,
  `$1C` bright abdomen (rows 10-14), `$22`, `$14` legs again.
- **`OBJ_BOMB = 138 = $8A` has bit 7 set.** Safe only because nothing tests a
  *drawable* design with `bmi` — `.Row`'s `bmi` is `ObjBase1` (slot 1) and the
  bomb never reaches slot 1; `.SODone` compares `#OBJ_BOMB` for equality and
  the blank sentinel is `$FF`. Keep it that way.
- **Tests derive the offsets instead of hardcoding them** (`test_miner_colors`,
  `test_raft`, `test_slot1_pair` parse the `OBJ_*` EQUs from `kernel.asm`), and
  `test_slot1_pair` now also asserts `OBJ_LAMP - OBJ_SPIDER ==
  ObjHeightTab[SPIDER]` so the art block and the draw window can never drift.
- Zero cycle cost: the `.Line` worst path is unchanged (61 c, WSYNC store 69),
  wall model unchanged, both sims + full battery green, pre-pad headroom 16 B.

Still 16 rows: BAT, MOTH, TENTACLE, PLAYER (+ the small objects LAMP/KEY/
SNAKE/RAFT/MINER/BOMB). Each one that graduates moves the offsets below it —
the tests now follow automatically.

## Phase 6 — tall sprites: table relocation DONE (2026-10-21), growth next

`ObjColorTab` (72 B) + `ObjSprites` (72 B) were RELOCATED out of the pinned
`$FE00-$FE8F` cluster into free fills, so they can grow without shifting a
single pin. Zero behaviour change; build + both sims + full battery green.

- Colour table -> `$FB20` fill (176 B, 32 B spare at 8-row size).
- Art table -> `$F744` fill, right after the Phase 5 code.
- `$FE00-$FE8F` is now `    .ds $FE90 - *, 0`, which keeps `FoldIndirect` at
  `$FE90` (the old HOF tramp) — do not delete that fill.
- `verify_build` needed no change: its only art guard is
  "`ObjSprites+<max offset>` stays in one page", and it resolves the label.
  New base low byte + max offset must stay <= 255.

### Measured facts that shape the growth (2026-10-21)

- The GRP1 draw window is `cmp #PLAYER_HEIGHT` (`kernel.asm` .Grp1, `$F1xx`)
  with `PLAYER_HEIGHT = 8`. **Growing the art means a bigger window**, so the
  growth step introduces `OBJ_WINDOW` for the draw test and leaves
  `PLAYER_HEIGHT` at 8: `PLAYER_HEIGHT` also feeds the enemy/player overlap
  test (`#PLAYER_SPRITE_H + PLAYER_HEIGHT - 1`, two sites) — changing it would
  change collision and `test_cell_map`/`test_phm_walk` expectations.
- Per-type blocks are indexed as `ObjBase + row`, offsets come from
  `ObjSpriteOffTable` and the `OBJ_*` EQUs, so ALL types must share one stride.
- Space: 12 rows/type = 108 B per table (216 B total). Art (108) fits the
  `$F744` fill, colour (108) fits the `$FB20` fill -> split them, 12 rows is
  affordable; 16 rows (144 B each) does not fit without moving the Phase 5
  code first.
- Colour rows 8-11 must NOT be left as junk: they tint the M1 block on those
  scanlines (Phase 3, deferred) — use the type's own colour, not 0.

### Growth step (next commit)

1. `OBJ_WINDOW = 12`; use it in `.Grp1`'s `cmp` (the reflection branch's flags
   follow the same cmp — no second change).
2. `OBJ_*` EQUs -> 0,12,24,...,96 and `ObjSpriteOffTable` -> the same values.
   The art table must then start on a page-safe address: max index is
   `OBJ_BOMB + 11 = 107`, so the base's low byte must be <= 148. Use
   `    .ds $F780 - *, 0` before `ObjSprites` (low byte $80 + 107 = 235, one
   page) — the Phase 5 code currently ends in that fill, so the pad both pins
   the address and proves the code still fits.
3. Art: 12 rows per type (4 new rows invented per type; the miner needs real
   legs so its feet read correctly).
4. Colour: 12 rows per type, rows 8-11 = the type's dominant colour.
5. Verify: `ObjSprites` low byte + 107 <= 255 (page guard), build, sims,
   battery, then a screenshot A/B against the previous ROM.

## Phase 6 — Taller, richer sprites (the payoff)

- The object path already indexes `ObjSprites`/`ObjColorTab` by
  `ObjBase + row`, so tall art is **not** a rewrite:
  - window size: replace `cmp #PLAYER_HEIGHT` (2 c) with `cmp ObjHeight` (3 c),
    a per-type height staged in ZP like `ObjTop` → **+1 c** (funded by Phase 2);
  - art: per type, each extra row costs 1 art byte + 1 colour byte (~2 B/row);
    an 18-row extension is ~36 B. Art must live in **bank0** (the kernel reads
    it `abs,X` while bank0 is selected), so Phase 1's eviction is what pays.
- Convert one type per commit (rows 12-26, HERO's tall-object shape) with an A/B
  screenshot; the 8-row types stay as they are until converted.
- Also usable for the **player** (taller jetpack silhouette) once the object path
  is proven.

Gate: battery + sims + SCN oracle; screenshots per converted type.

---

## Phase 7 (optional) — Extra slots

- Ball/M1 per-band enable as genuine extra objects (they share `COLUPF` /
  `COLUP1`, so only for wall-coloured or same-colour elements). With Phase 3 in
  place the async block no longer *needs* this; it is a capacity feature for
  rooms that want a third element.
- **There is exactly ONE ball**, and Phase 3 wants it as the async-block
  carrier while Phase 7 wants it for the miner (only 4 px wide, so the ball
  *could* carry a 4-px silhouette). A room cannot have both an async block and
  a ball-carried object — decide which before building either.

---

## Backlog after Phase 6 (ordered, 2026-10-22)

Everything below is a known open item; the order is by "risk removed per byte".

1. **`PinSlot0` assumes at most 2 candidates.** With three (two enemies + the
   miner) slot 0 = the miner and slot 1 = the max-Y enemy, so the middle object
   is never drawn. Guard: skip the pin when the candidate count is >= 3 (the
   rotation then handles it, flicker and all). ~5 B in the `$FB20` fill.
2. **Phase 4 — VDEL pipeline** (next sprite-architecture step): `VDELP1` so
   `GRP1`/`COLUP1` are written a line ahead, and the per-band + per-object
   colour sources become HERO's one-byte-per-line "colour + draw flag" staged
   at room load. Gate: identical output, `.Line` worst path not worse. This is
   a kernel + staging restructure — start it as its own chunk.

   move out of the `$F744` fill first (it is full again after the HMOVE fix),
   e.g. `StageSlot1` into a bank2 slot behind a `jsr`. Then the object window
   constant and the art/colour tables grow together.
   ✅ **FORMAT DONE 2026-10-22** — see the Phase 6 section below (16-row window,
   4 blank rows reserved per design; authoring the art is what remains).
   ✅ **The eviction is DONE (2026-10-22)**: `StageSlot1` + `PinSlot0` are in
   bank2 (`$FAC0`), the `$F744` fill has **202 B** free between `Slot1Hook`
   (`$F750`) and the `ObjSprites` pin (`$F850`), and the pad is
   `CallPad_StageSlot1` (`$FBE5`). Phase 6 can grow the art down from `$F850`
   once the `$FE00` cluster re-pin is planned.
4. **Phase 3 — async-block tint** (blocked on stage content: no async blocks
   exist until level 7). Needs the carrier decision (generator band separation /
   ball-`COLUPF` carrier / PF pillar), bank3 `RoomM1Hot` display-cell staging,
   `.OSBsolid -> jmp HotOverlapFlag`, and it must stage `M1X = $B0` (reserved,
   deliberately never written today).
5. **Phase 7 (optional)** — ball/M1 as real extra slots for rooms that want a
   third element.

**Checked and NOT a bug (do not "fix" it):** `BallX` still lives in `Temp`,
which `StageSlot1` clobbers — but the VBL order is `SelectActiveObject` (and its
`StageSlot1` tail) -> `CallPad_BuildColupF` (bank2 `StageBandTab` re-stages
`BallX` into `Temp`) -> `PositionBallM1` (reads it). The staged value is always
fresh. If that order ever changes, give `BallX` its own byte.

**Standing rule (guarded by `tools/test_slot1_hmove.py`):** a second `HMOVE` in
a frame must clear every fine register it must not re-apply (`HMP0`/`HMM0`/
`HMBL`) and those clears must sit BEFORE the `WSYNC` that precedes the `HMOVE`.

## Phase 6 — 16-row object window (LANDED 2026-10-22, format only)

**What landed:** `OBJ_WINDOW = 16` is now a constant *separate from*
`PLAYER_HEIGHT = 12` (the hit box), `ObjSprites`/`ObjColorTab` are 9 × 16 =
144 B each (stride-16 `OBJ_*` EQUs, `ObjSprites` base moved `$F850 → $F830` so
the table still ends at the `$F8C0` RaftBody pin, page guard `+71 → +143`), and
every design got 4 extra rows: **art = `$00` blanks reserved for authoring,
colour = the design's own colour**. Visual output is unchanged; the window just
has room now. Cost: +72 B, **0 c** (`cmp #OBJ_WINDOW` replaces `cmp #12`).

**Two traps this dug up — both now guarded:**

1. **`$FF` sentinels vs. bit 7.** `OBJ_BOMB` is now 128 = `$80`, and the tail's
   `lda ObjBase / bmi` "no object" test read it as empty: the bomb's `P1` was
   never positioned and its `ObjTop` was parked (caught by
   `tools/test_bomb_render_x.py`). Slot 0 now uses one `cmp #$FF`, and both
   `P1`-positioning and `ObjTop` staging branch from it (`.SOBlank` replaced
   `.SONoObj`). Slot 1 keeps `bmi` — it only ever holds an enemy design or the
   miner (< `$80`); that invariant is commented at the `.Row` early-out.
   **Cost note:** three `cmp/beq` sites cost **6 c** in the VBL and pushed
   `test_phase3_ball` to 268-line frames; **2 c** is what the window pays.
2. **equ-sync only checked hex.** The bank2 `OBJ_*` hand-copies are decimal, so
   the stride change drifted silently. `check_equ_sync` now also compares
   `Name = <decimal>` — with the copy fixed to stride 16.

**Still open (art-led, one type per commit):** fill a design's rows 12-15 (art
+ the matching `ObjColorTab` rows). HERO's object is 26 lines with a colour per
line; ours is per-design, so a taller design costs 2 B per row. The hit box
stays 12 until a gameplay ruling — drawing height must not silently enlarge it.

**ZP blocker RESOLVED (2026-10-22).** The melody only runs on title frames while
the bomb block never does (`DropTarget != 0` → `DropStep`), so the melody state
moved to `$F6`/`$F7` (= `BombX`/`BombTimer`) and the title entry clears it —
`docs/zp_layout_skill.md` rule 7 (PHASE-SHARING) + § "Lifetime audit" record the
general law. `$9D`/`$9E` are now `ObjHeight`/`ObjHeight1`.

**Next step (plumbing, no visual change):**
1. `ObjHeightTable` (9 B, design offset / 16) in the `$F744` fill.
2. Stage `ObjHeight` next to `ObjBase` in `SelectActiveObject` (enemy path:
   `lda ObjHeightTable,X`; miner/bomb: a constant) and `ObjHeight1` in
   `StageSlot1`; `Slot1Hook` copies it with the trio.
3. `.Line`: `cmp ObjHeight` replaces `cmp #OBJ_WINDOW`. **Measured: a ZP
   compare is 3 c, not 2 c** — the worst path goes 60 → 61 and the WSYNC store
   c68 → c69 (contract ≤ 73, so it lands with 4 c to spare).
4. Then art per type (art + `ObjColorTab` rows + the table byte), one commit
   each, with the hit box still 12 until a gameplay ruling.

## Phase 5b — mid-band slot swap: ATTEMPTED AND WITHDRAWN (2026-10-22)

**Goal:** let the miner share a 48-line band with an enemy (it sits, the enemy
walks past, their windows never overlap) without the 30 Hz rotation.

**Mechanism that was built:** `StageSlot1` paired same-band candidates whose
drawn windows were >= `OBJ_WINDOW` apart, staged the pair with `ObjBase1` bit 7
set (so the `.Row` hook skips it) plus `ObjSwap` (= `ObjTop1-1`, in `$A2`
shared with `LevelConnSpare`), and `.ObjNoRes` ran the swap at that line: copy
the trio, `SetObjectXPos`, `HMOVE`, then `jmp CaveLine` to re-run the row.

**It works** (`tools/test_slot1_midband.py` proved both designs in one frame),
**but two artifacts are inherent to it** and both were visible in play:

1. **One duplicated sprite row.** The swap needs `SetObjectXPos`' own scanline
   plus its HMOVE line; on those lines the body does not run, so the GRP0 latch
   keeps the previous byte — the player's art row is displayed twice (the
   reported "legs repeated").
2. **The band grows 2-3 scanlines taller**, so every band below it is drawn
   2-3 px lower than the collision map says — the player appears to sink into
   / float above the walls (the reported "inside the PF"). A band's PF is
   uniform, so nothing *looks* wrong inside the band; the damage is the band
   BOUNDARY moving.

Also dug out on the way (worth keeping in mind for any future mid-frame
reposition): **`SetObjectXPos` ends with `tay`** and destroys the `.Line`
running row — the first version of the swap did not re-seed Y and drew the
player as a few rows in the wrong place ("the miner vanishes" was the same
bug). The guard `tools/test_slot1_midband.py` now asserts that a same-band pair
changes neither the frame length nor the player's art row count.

**Rule that stands: one GRP1 object per 48-line band, the miner included.**
`tools/convert_level.py` warns per offending room (level 2 room 2 and level 3
room 3 on the current stage) — it is a WARNING because the live stage still has
them. Moving an object into another band, or Phase 7 (the ball/M1 as a real
second channel — the miner is only 4 px wide) are the ways to clear it.

---

## Verification protocol (every phase, non-negotiable)


1. `./build.sh` (runs both sims: `sim_bomb_fuse`, `sim_frame_budget`).
2. `bash tools/freeze_test_banks.sh` **before** trusting any battery run after a
   bank-code change.
3. Full battery: every `tools/test_*.py` + `src/tools/test_title_demo.py`.
4. Stella oracles for anything touching the kernel: `logTrace` SCN at the first
   kernel WSYNC must be a **single** value across ≥100 frames, and the seam-row
   probe must form one signature across ≥120 frames.
5. Visual phases: staged demo build + A/B screenshots (live stage untouched).
6. `tools/rom_size_report.py --md` → update §0 of this plan and the project
   ledger in the same commit. Commit per phase with the phase name.

## Risk register

| Risk | Mitigation |
|---|---|
| Branch page-cross / fixed-time drift (the historical ±1-line family) | Phase 0 ledger, same-page guards in `verify_build`, sim + SCN oracle |
| bank0 twins and `$FFF6-$FFF9` hotspot | `verify_build` pins; never place fetched bytes in `$FFFx6-$FFF9` |
| Stack depth (`sim_bomb_fuse` SP ≥ $F8) | no extra `jsr` levels on the walk paths; sim is the gate |
| Level-count assumptions in tests | Phase 1 step 4 enumerates and fixes them; generator coverage stays at 20 levels in temp |
| Eviction breaking a cross-bank call | code+data+twin move together; `check_raft_tramp`-style guards for each new pad |
| Feature coverage lost with 4 levels | `src/tests/rooms` (async + phase already present) + `test_generator` (20 levels) |

## Order & effort (sessions)

| Phase | Effort | Risk |
|---|---|---|
| 0 ledger | done | none (read-only) |
| 1 space (cut done, evict next) | 1-2 | medium (bank moves) |
| 2 cycles (beam fold done) | 1 | medium-high (kernel timing) |
| 3 tint fix | 0.5 | low once 2 lands |
| 4 VDEL/colour table | 0.5-1 | medium |
| 5 second window | 1-2 | high (extra lines + HMOVE) |
| 6 tall sprites | 1-2 | medium |
| 7 extra slots | optional | low |

## Player art: 22 rows, hit box follows the art (2026-10-22, user design)

The user drew a 22-row, 8-px player (helmet / visor / jetpack / flame / legs /
boots, 4 frames). User ruling: **the hit box follows the art**, so
`PLAYER_HEIGHT = 22` and `PLAYER_SPRITE_H = 22` (was 12 for both).

Consequences, all landed together:

- `PLAYER_MAX_Y` 132 -> **122** (`CAVE_LINES - PLAYER_SPRITE_H`; the feet land
  on 143 = the cave bottom). bank2's hand-copy of the EQU moved with it.
- **Water kill origin 125 -> 115**: `CheckBandTouch` tests the sprite ORIGIN,
  and the feet are `RoomY + 21`, so 115 keeps the same feet depth (136) the
  12-row sprite had at 125. `LoseLifeBand`'s "-12 respawn" still clears it.
- **Laser beam rows `RoomY+2..3` -> `RoomY+4..5`** (bank2 `LaserWallClamp` +
  the two enemy Y tests, all `adc +2`), because the visor is art row 4. The
  drawn beam is the row whose colour carries bit 1 — `PlayerColTable[4]`.
- **Raft rider pin 12 -> 22** (`RAFTER_PINFIT`, `RAFTER_YSPAN` 28): the pin
  puts the FEET on the raft top, so it must be the art height.
- **One colour table for all four frames**: rows 15-16 are orange in every
  frame (flame in the jet frames, lit belt/hip in the walk frames), rows 17-18
  blue, 19-21 dark grey. Colours had to be chosen around bit 1 = ENAM0:
  `$0E/$0A/$06/$2A/$82` all set bit 1 and would fire the beam on those rows,
  so white = `$0C`, grey = `$08`, dark grey = `$04`, orange = `$2C`,
  blue = `$88`, red = `$48`, beam = `$1E`.
- **Space**: 4 x 22 + 22 B of art does not fit the old `$F8DD` window (36 B
  there, and `PlayerHitsMap` follows it). The whole block (4 art tables +
  `PlayerColTable`) moved into the **`$FE00` fill at `$FE14`**, is
  relocatable (labels only: `PickPlayerFrame` uses `#<`/`#>`, the kernel reads
  `(Grp0Ptr),Y` and `lda PlayerColTable,Y`), and the `$F8DD` pin is retired.
- Guards updated: `verify_build` now reads `PLAYER_SPRITE_H` and checks
  `[H-2] == [H-1]` (rows 20/21) + bit 1 ONLY at index 4; the cell-map, water,
  laser-window, raft-pin, grid-exit and midband tests derive/carry the new
  numbers. `test_cell_map`'s Y sweep no longer probes above `PLAYER_MAX_Y`
  (the bottom row index must stay inside `YToRowTable`).

## LAMP wall-side mirror — LANDED 2026-10-22 (a99f0d5), type 13

Status: implemented exactly as the resume plan below describes. Residual: a
mirrored lamp that lands in SLOT 1 draws the unmirrored design (StageSlot1B2
masks b3 to index the 8-entry bank2 tables) — lift it when bank2 can afford
12 B for 14-entry table copies.

User ruling: the wall lamp hangs on the wall it is drawn against, and the
converter should pick the side automatically (**no editor change**). The art as
committed (`6155b3d`) carries the bracket on the lamp's LEFT, i.e. it faces
RIGHT; a lamp whose wall is on its right needs the mirrored design.

**Why REFP1 was rejected** (measured, not guessed): `SetObjReflection` is the
only writer that survives the HUD band, and it lives at $FF20 — bank0's
post-pad is FULL (last used byte $FFEF, `.ds $FFF2` follows), so the minimal
15-19 B version does not fit. It would also give ONE mirror value for both
GRP1 slots, so a mirrored lamp and the mirrored miner could not coexist.

**Space audit done in the attempt:**
- bank2's pre-$FF59 block is full too: moving `EnemyOffTable` + `EnemyBitTable`
  (7 B) into the $FFE6 fill frees exactly enough for the 4 B of laser masks
  (both laser bodies read the record RAW and would destroy a b7 lamp) and
  nothing more. That move is safe (abs,X reads, X <= 3, never reaches the
  $FFF6-$FFF9 F6 hotspot mirrors) and is part of the resume plan.

**RESUME HERE — encode the mirror as a TYPE (no b7, no REFP1):**
1. Mirrored lamp = type **13** (b3-0 is 4 bits, 8-15 unused). `dir` stays 0, so
   no record byte changes shape.
2. bank0 data only: `ObjSpriteOffTable` grows to 14 entries (move it from
   $FE0C, which is full, into the $F8A0 fill — 33 B free; index 13 =
   `OBJ_LAMP_R`), `ObjHeightTab` index 13 = 10 (grows into the $F830 pad).
3. `OBJ_LAMP_R` = a 10-row horizontal mirror of LAMP + its 10 colour rows,
   appended after RAFT: offsets 111..120, `ObjSprites` 121 B, page guard +120,
   `test_miner_colors` last = 120.
4. Every `cmp #LAMP` masks `and #%00000111` instead of `%01111111` (SIZE
   NEUTRAL — same 2-byte instruction): kernel `CEH_Lamp`, bank2 blast, bank2
   `StageSlot1B2`. The two laser bodies have no mask today: add
   `and #%00000111` (4 B, funded by the table move above).
5. Known limitation to document in the code: `StageSlot1B2`'s mask drops b3, so
   a mirrored lamp that lands in SLOT 1 draws the unmirrored design. Lifting it
   needs 12 B in bank2 for 14-entry table copies.
6. Converter: `_lamp_dir(room, x, y, models)` returns 5 (wall on the LEFT) or
   13 (wall on the RIGHT), reading `tiles[band*width + cell]` with
   band = y//4 and cell = (col if col < 20 else 39-col)//2; a screen edge
   counts as a wall. The emitter's `type <= 7` assert becomes `<= 13`.
7. Guards: converter test (wall left -> type 5, wall right -> type 13) + a ROM
   test that the design at index 13 is the horizontal mirror of index 5 over
   its 10 rows.

## KNOWN BUG (found 2026-10-22, not fixed): REFP1 follows the ACTIVE object

A room that hosts TWO objects in the same band (e.g. a lamp + the miner) draws
them on alternating frames, and SetObjReflection runs per frame for whichever
object the rotation made active: the miner's mirror (LevelMinerRoom b7) is
written on its frames and 0 on the other's, so the miner's sprite flips
left/right every other frame ("miner goes nuts flipping side", user report with
a lamp demo in level 2 room 2 — that room hosts the level-2 miner).

REFP1 is ONE hardware register for GRP1, so it can only be right when every
object drawn in a frame wants the same mirror. Options when this becomes a
priority: (a) forbid a mirrored lamp and the mirrored miner in one room,
(b) mirror by design block (art table) for every type that can share a room,
(c) keep a per-room "no rotation" rule. The type-13 lamp already uses (b), so
the miner is the only REFP1 user left.

## REFP1-per-object bug FIXED 2026-10-22 (b04c01b) + PinSlot0 guard verified

REFP1 is one register for GRP1 while a frame can draw two objects (Phase 5 band
pairing or the 1-of-2 rotation), so SetObjReflection driving it from the ACTIVE
object made a mirrored miner flip sides every other frame in any room that also
had an object. The miner's mirror (a per-LEVEL flag, miner_room b7) could not
become a design-based mirror like the LAMP's type 13: that needs 16 art rows +
16 colour rows and ObjSprites has 6 B left below the $F8C0 raft-tramp pin.

Fix: SetObjReflection and both its calls are gone. Every GRP1 object is drawn
unmirrored, which is exactly what REFP1 is — the bank1 HUD writes 0 for its
score. Freed 6 B pre-pad + 19 B post-pad. LevelMinerRoom's b7 and the editor's
miner_dir survive in the data but no longer reach the screen; restoring the
facing needs 32 B of art space (or a room-level art selection), not a REFP1
write. verify_build now rejects any `sta REFP1` in bank0.

PinSlot0's 3-candidate guard was already in the source (`cmp #2 / bcs .PSout`);
test_slot1_pair gained the case that proves it (2 enemies + the miner keeps
FlickerFrame untouched, so the rotation stays in charge and the middle object
still gets its frames).
