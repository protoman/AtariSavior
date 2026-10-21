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

Gate: **bank0 pre-pad headroom ≥ 40 B** (Phases 2-5 add instructions, twins and
new tables) and the tree green with the 4-level stage as the default build.

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

## Phase 4 — VDEL pipeline (HERO's write discipline)

- Use `VDELP1` (and keep the score's `VDELP0/1` usage) so `GRP1`/`COLUP1` can be
  written one line ahead of the pixels; the colour write leaves the critical
  window and per-line colour changes stop being cycle-critical.
- In the same phase, replace the per-band + per-object colour sources with the
  HERO shape: **one byte per line = colour + draw flag** for the object window
  (the `$DD69`/CTL analogue), staged per room, so "who owns this line's colour"
  is decided at room load instead of by runtime persistence.
- Gate: visual output identical to Phase 3 (VDEL is invisible when staged
  correctly), sim + battery green, `.Line` worst path not worse.

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
- If the coarse `RESP1` needs a WSYNC-anchored slot, it can use the halt tail of
  the setup window (the CPU resumes exactly at the third line's cycle 0), which
  is why the wall model can stay **267.0**. If it cannot, the sim decides and the
  target is updated in the same commit.
- Result: `SelectActiveObject` stops rotating — it becomes the staging routine;
  both objects draw every frame, each with its own colour.

Gate: `sim_frame_budget` wall model (267.0, or the measured new target), SCN
single-value oracle at the kernel landmark, staged screenshot showing
enemy + miner + player in one frame with no flicker.

---

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
