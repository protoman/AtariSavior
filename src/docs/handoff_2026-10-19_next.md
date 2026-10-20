# Handoff / plan — next session (2026-10-19 →)

Everything below is grounded in measurements recorded in
`docs/code_size_audit.md` (what the 9.3 KB of code is) and
`docs/crunch_unification_plan.md` (crunch chunks + size ledger).

## 0. State at handoff (all committed, tree green)

- HEAD `14d9620` (A3 + C2 + C3). Build + both sims + 42-test battery + title
  demo green; frozen banks re-frozen.
- Sizes: b0 3540 used / 556 free · b1 3182 / 914 · b2 2098 / 1998 · b3 2102 /
  1994. Largest bank2 holes: 315 B `$FC4C-$FD86`, 503 B `$F9D9-$FBCF` (data
  window, empty), 141 B `$FF59`. Largest bank3: 322 B `$FC3E-$FD7F`.
  Level data **556 B**: index + tables in bank2, models + blocks in bank3.
- Code: **9213 B** (A3 -42, C2 -85). Fill/pad tax: 4468 B.
- Cross-bank pads: ~85 sites.

### Rules that bit us (do not relearn)

1. **Twin offset = `sta+3`.** A bank2↔bank3 pad's twin is the first byte
   fetched after the switch. Pin with `.ds <addr> - *, 0` **before** the block
   label — inside the block it is a BRK in the fall-through path (both times
   it reset the game to GameStart).
2. **`sim_bomb_fuse` runs before the ROM is concatenated** — it validates the
   *previous* `savior.bin`. After a chain change run
   `cat bank0.bin bank1.bin bank2.bin bank3.bin > savior.bin` once by hand,
   then re-run the sim.
3. **PhaseBlink ordering:** after `StageBandTab`'s band/ball staging, before
   the overlay pack (`VcrShutter` overwrites `Temp`/`BandTab` for the shutter
   cell). Moving it earlier silently killed every crunch kill.
4. Room meta is **staged at entry** (`RoomMetaA/B` = `$99/$9A`, the dead
   pointer pair). No `(RoomPF0Lo),Y` reads remain; do not reintroduce them.
5. No new `jsr` in the room-load / VBL / collision chains (measured stack
   floor; `sim_bomb_fuse` min-SP guard).
6. Never `git add -A src`; stage `src/rooms`/`src/generated` explicitly and
   diff them.

## 1. Chunk A3 — level data → bank3 — **DONE 2026-10-19**

Result: bank2 **2098** used (was 3261), bank3 2187. Build + both sims +
42-test battery + title demo green, frozen banks re-frozen. `bank2` has
315 B at `$FC4C-$FD86` and the (empty) 503 B `$F9D9` data window is now the
biggest contiguous run — C2's ~420 B fits.

Traps found while landing it (add to §"Rules that bit us"):
- **The return tail of a bank3 body must sit at the address bank2 fetches
  post-switch.** `B3RoomBlocks` ends `sta $1FF8` PINNED at `$F458`; bank2's
  `ERBlocksDone` `jmp` is at `$F45B`. Putting the tail at the end of the body
  ($F406) made bank2 execute fill -> GameStart (silent reboot).
- **HOF entry moved to `$FFEC` in BOTH bank0 and bank2.** bank3's `$FE93`
  is inside OvShutBand's `.OSline`; bank2 needs its own live pad because
  `OvM1Block` `jmp HotOverlapFlag` runs with bank2 selected. Bank3 serves the
  image at `$FFEF` (guard updated in `check_moth_tramp`).
- `verify_build --sync-bank3-labels` is the new pass-1 step: it writes
  `generated/bank3_labels.asm` (block EQUs for bank2) and self-heals the
  `CallPad_BuildColupF` / `HotOverlapFlag` literals in kernel/bank1/bank2.
- Test migration: block labels/bytes come from bank3 (`L3` / `BANKS[3]`);
  code labels stay bank2. `test_fixtures` now injects into bank3.
  `src/tests/generated/` was regenerated (adds `*_blocks.asm`,
  `spill_bank3.asm`).
- `emit_spills` sizes only the bank2 table files; bank3 has a fixed org.

## 1c. Chunk C2 — **DONE 2026-10-19**

Deleted `PhHcrPre`/`HOVFeatPre`; the crunch dispatchers read record fields
directly from `(FetchPtr),Y` (same bank since A3). No stack shuttle: only the
record base is pushed. bank3 code 1761 -> **1676** (-85 B), total code 9298 ->
**9213**. 16-case hcrunch + vcrunch/phase tests green, frozen banks re-frozen.
Decision on the open question changed by A3's result: **the crunch machine
stays in bank3** (both its walker and its consumer are there; moving it to
bank2 would re-add two switches and save nothing).

Next: C3 (drop retired twins if any remain, fold `HcrPush`/`HcrClock` if a
zero-risk form exists), then the reorg (PF-table score).

## 1b. (historical) A3 plan — level data → bank3

**Why first:** C2 needs ~420 B contiguous in bank2; the biggest hole is 192 B.
A3 frees the level-data spill slots (256 + 111 + 427 B) and turns bank3 into
the data bank.

### Steps (each ends build + sims + battery + freeze + commit)

1. `tools/convert_level.py`
   - per-room async blocks → `generated/level_00N_blocks.asm`
     (the `emit_room_block` calls currently appended to `level_00N_rooms.asm`);
   - `models_data.asm` stays a file but is included from **bank3**;
   - emit `generated/spill_bank3.asm` listing `models_data.asm` + all
     `level_00N_blocks.asm` (include list, same shape as `spill_*.asm`);
   - tables (`RoomDataTable`, connections, enemy tables, RoomEnemies) stay in
     `level_00N_rooms.asm` (bank2);
   - keep `_gen_data_size`/`emit_spills` working for the *bank2* files only.
2. `tools/verify_build.py --sync-bank3-labels`
   - parse `bank3.lst`, export only block labels (`M<digits>*`, `L<digits>R<digits>*`,
     `B3*` if needed) as EQUs into `generated/bank3_labels.asm`;
   - `check_levels` must look for blocks in `level_00N_blocks.asm`.
3. `src/build.sh` two-pass order:
   convert → **bank3 pass 1** → `--sync-bank3-labels` → bank2 → existing syncs
   (`--sync`, `--sync-overscan`, `--sync-phrec`) → **bank3 pass 2** → bank0 →
   bank1 … then the usual pad/verify/sims. (Pass 1 only exports symbols; pass 2
   is the shipping image.)
4. `bank3.asm`: `include "generated/spill_bank3.asm"` at a free org (the
   `$F3B0+` region or `$F800+`), after the existing pinned pads.
5. `bank2.asm`: drop `models_data.asm` + `level_00N_rooms_data.asm` includes;
   `include "generated/bank3_labels.asm"` so the room table's `.word`s resolve.
6. Move the four block readers to bank3 (all tail-call, 0 pushes):
   - `EnterRoomB2`'s **tail**: rect unpack + 9-byte PF copy → `B3RoomBlocks`
     (bank3), entered after the enemy record/bomb reset, returns via
     `ReturnPad`. Must preserve the `X = EnemyCount` contract — use Y + ZP
     scratch for the cache index.
   - `PhaseBlink` (walks the record stream) — bank3; its caller `StageBandTab`
     is already there (`B3StageBand`). This also kills the SBT↔PhaseBlink
     ping-pong and its two pads (~12 B).
   - `BuildColupF`'s hot-rect walk — either move `BuildColupF` wholesale (its
     caller pad already exists) or split the walk out; the stripe/pulse part
     reads no level data.
   - `HotOverlapBody` (bank2 `$FCF0`) — move to bank3 and retarget the bank0
     `$FE90` pad (`sta $1FF8` → `sta $1FF9`, operand → bank3 body). **0 bank0
     bytes**; update `check_moth_tramp` to pin the new operand.
7. Tests: every ROM-byte test that reads **block bytes** must switch to
   `BANKS[3]` + `bank3.lst`. Candidates (grep for `BANKS[2]` at
   `TilePF0`/`RoomRects`/`Meta*`/`EnemyData` addresses):
   `test_bomb_strip`, `test_bomb_half_wall`, `test_bomb_user_sequence`,
   `test_cell_map`, `test_fixtures`, `test_laser_close`, `test_laser_kill_window`,
   `test_laser_walk_wall` (shared `load_room`), `test_phase2_ball`,
   `test_phase3_ball`, `test_phase_kill_frame`, `test_vcr_shutter`,
   `test_hcrunch`, `test_room_dark`, `test_enemy_movement`, `test_raft`.
   Code-label users (`StageBandTab`, `MothDoWalk`, …) stay on `bank2.lst`.

**Expected:** bank2 3261 → ~2100-2500 B (data -556, readers -~600 if all four
move), bank3 holds data + readers with room left.

## 2. Chunk C2 — crunch consolidation — **DONE 2026-10-19** (−85 B; stack shuttle removed, see §1c)

- Move `PhHcrEntry` + `CrPfx0/1/2` + `HcrClock` + `HcrPush` (~420 B) from
  bank3 into the hole vacated by the level data (bank2), then merge the PF
  staging with `VcrShutter` (also bank2).
- `$FC34` (PhHcrPre → PhHcrEntry tramp) becomes a local `jmp`; delete the
  bank3 twin; the `$FCC1-$FCDD` return pads collapse to `jmp PhNext` /
  `jmp HOVnext` in bank2.
- Unify the mask tables (`OvHead/OvTail` vs `CrPfx*`) and the clock
  (`VcrStateTab` 32 B vs `CrunchClock`).
- **Expected:** 200-300 B. **Actual:** 85 B (the shuttle was ~100 B; the
  "move to bank2" half became pointless after A3). Tests green. Keeping the
  machine in bank3 is the recorded decision.

## 3. Chunk C3/C4 — small cleanup

- Fold `HcrPush`/`HcrClock` into the staging path once C2 has merged banks.
- Drop the retired legacy twin images (`$FB57/$FB61/$FD7B` in bank3) and
  re-pin the pads. ~6-15 B.

## 4. Reorganisation (after the crunch)

### 4a. Score renderer → HERO PF-table score — **DISPROVEN 2026-10-19**

The audit claim ("HERO renders its score from baked per-scanline PF images")
is contradicted by HERO's own code (`docs/hero/hero_bank0.asm`, assembled to a
4K image and disassembled — no screenshots used as evidence):

- `$DF00` is an **8x8 sprite glyph font**: 10 digits (0-9), 8 bytes each,
  then letters/blank. Rendered as bitmaps they are unmistakably 0-9.
- HUD setup fills zero-page pointer **high bytes with `$DF`** (`LDX #$0B /
  LDA #$DF / STA $85,X / DEX/DEX ...` at `$D0E6-$D0F4`), i.e. pointers into
  that glyph table.
- Rendering is `LDA ($xx),Y` → `STA $1B` (GRP0) / `STA $1C` (GRP1) in 8-row
  loops (`$D47F-$D4FD` for the 5-letter row, `$D15E-$D17A` and `$D23C+` for
  other sprite rows), with `STA $25/$26` (VDELP0/1), `STA $04/$05`
  (NUSIZ0/1) and `STA $06/$07` (COLUP0/1).
- No PF (`$0D/$0E/$0F`) writes exist in the score/HUD path; PF is the terrain.

So HERO's score is **sprite-based with a glyph table and (zp),Y fetch** — the
same technique as our `MenuMain` 48px score + `DigitGfx`. The PF variant could
not show six distinct centered digits anyway (20 bits × 4 clocks, repeated or
mirrored).

Conclusion: no rewrite. The 1033 B cluster is HERO-parity, not waste. The
audit's §2/§4a wording is corrected in `docs/code_size_audit.md`.
If a smaller/coarser score is ever acceptable as a *design* change (not a
compaction), the PF variant would also force a layout change (score would have
to sit in one 80 px half and be duplicated) — user decision, not a free win.

### 4b. Dedupe list (measured in `docs/code_size_audit.md` §3)

| item | bytes |
|---|---|
| one row/band conversion (`YToRowTable` 48 B + `BandRowFromLine` + inline `/48`) | ~70 |
| one bit table (now `EnemyBitTable` ×2 + `RaftBitTab`) | 8 + call sites |
| one `M1OffTab` (bank2 + bank3 copies) | 4 |
| one band-mask table set | ~20 |
| one crunch clock | ~50 |
| walker prologue (PHM/MothDoWalk) — only if a fold-free sharing trick exists | ~40 |
| `SetupScorePointers` trim: drop the LV001 banner path + simplify BCD split (HERO's pointer setup is ~30 B; ours 123 B) | ~80-100 |

### 4c. Target layout (one feature = one bank)

| bank | content |
|---|---|
| bank0 | kernel + VBL/overscan + input + physics + collision (hot loop, pinned) |
| bank1 | HUD + audio + title |
| bank2 | gameplay: room load, enemies, bomb, laser, overlays, **crunch** |
| bank3 | data (level + models) + overflow |

Metric to watch: cross-bank pads (currently 92).

### 4d. Still-open long-term goal

User wants **code in bank0+bank1 only** (or at most half of bank2). Measured
after A3/C2: code alone is **9213 B** vs 8192 in two banks, so it needs ~1 KB
more off. Candidates: the title cluster (978 B, keep for now), tally/banner
(220), pad co-location (~100 B), and the de-fragmentation pass (§8).
Also on the wish list for parity with HERO: Activision-style logo screen,
more colours per stage, HERO's 13+2 HUD columns.

## 8. Fill / fragmentation options (added 2026-10-19)

**Fill is layout slack, not a budget.** It is the `.ds` padding between a block
end and the next *pinned* address, plus the 4K tail. Shrinking code usually
makes it grow (the gap before a pin widens — bank3 fill went 1355 → 1386 after
C2 removed 85 B). The metric that matters is **largest contiguous free hole
per bank**, because that is what a new feature can actually use.

Options, cheapest first:

1. **Use the gaps (fill → used).** Move cold tables/leaf routines into the big
   holes. Current largest runs: bank2 `$F9D9-$FBCF` 503 B (empty data window),
   `$FC4C-$FD86` 315 B, `$FF59-$FFE5` 141 B; bank3 `$FC3E-$FD7F` 322 B,
   `$FECB-$FFEE` 292 B, `$FB08-$FBED` 230 B, `$F290-$F3AB` 284 B. Zero
   behaviour change; the block's labels move, the syncs already handle literals.
2. **De-fragment per bank.** Reorder/compact blocks so used areas are
   contiguous and all slack ends in one tail run. Same byte count, more usable
   contiguous space (and fewer >127-byte branch hazards).
3. **Remove pins by removing tramps.** Co-locate routines so cross-bank pads
   disappear (audit: 92 sites / 512 B; measured ceiling ~100 B genuinely
   recoverable). Each removed pad is one fixed address and two merges.
4. **Fewer banks (repack).** Used 10,922 B < 12,288 B, so a 3-bank fit is
   possible in principle. It saves ROM bytes, not gameplay bytes, needs a full
   repack of the pinned map, and F6 still ships 16K. Treat as a long-term
   layout project, not a compaction tweak.

Do NOT re-pin anything that a cross-bank literal depends on without running the
full build (the sync steps rewrite operands; `sim_bomb_fuse` runs on the
previous `savior.bin`).

## 9. Stage-data compaction (added 2026-10-19)

Measured composition of the 556 B of level data (`rom_size_report`):
- 304 B blocks/models: 12 model blocks + 6 async room blocks, each =
  9 B PF + 2 B meta + rect stream (~2 B/solid rect, 5 B/hot-feature record);
  **rect streams total 174 B**.
- 196 B per-level tables: `RoomDataTable` 4 B/room, connections 2 B/room,
  enemy records 4 B each, `RoomEnemies` 4 B/room (16 rooms, ~9 enemies).
- 56 B `levels_index` (LevelDataTable stride 14).

Ceiling: **556 B total**. "Turn it into code" does not automatically win —
specialised code costs ≥ the data it replaces unless it also deletes generic
machinery. Options with measured/estimated value:

| # | idea | saves | cost/risk |
|---|---|---|---|
| S1 | `RoomDataTable` word pairs → 1 word/room, PF derived from the rect stream (`2 + 2*solid + 5*hot`) | 32 B data | **TRIED + REVERTED 2026-10-19**: derivation cost +37 B code → net **+5 B worse**. Do not retry without a cheaper derivation. |
| S2 | `RoomEnemies` 4 B/room → 2 B/room (base word + count/band + prefix sum) | 24 B data | **TRIED + REVERTED 2026-10-19**: +36 B decode → net **+12 B worse**. Like S1, the loader arithmetic outcosts the record bytes. |
| S3 | enemy record 4 B → 3 B (type+dir packed with x) | ~9 B | +~10 B decode |
| S4 | `LevelDataTable` stride 14 → 12 (drop redundant start x/y constants, they are fixed 32/24) | **DONE** −14 B used (code −6, data −8) | trivial; kernel sets `LevelStartX/Y` to 32/24 immediates |
| S5 | derive SOLID rects at room entry from the 9 PF bytes (drop the generated solid streams; keep hot/M1/feature records) | ~100 B data | ~100-150 B of code + must reproduce convert's rect merge exactly and fit the 5-slot cache; net ≈ 0 and medium risk |
| S6 | RLE/pack the PF bytes (mostly $FF/$00 runs), expand at room entry | ~60-100 B | ~60 B decoder; room load is not hot; low risk |

Recommended order: ~~S4~~ (done), then S2/S3 only if a real need appears; skip S1
(measured net loss), skip S5 (net-zero, highest risk); S6 last. Note HERO's own
player-vs-wall collision is NOT hardware (`CXP0FB $30` is never read in its bank;
only `$32/$33/$34` for ball/missile/PP are), so "use CX like HERO" is not a
shortcut.

**Post-S4 ledger** (`rom_size_report --md`): b0 3534/562, b1 3182/914,
b2 2090/2006, b3 2102/1994 — total used **10908**, free 5476,
code 9207 / data 1701 / fill 4482. The pre-pad headroom warning is unchanged
(a `.ds` pad after `LoadLevel` absorbs the 6 freed bytes; bank0 is still 1 B).

**Post-pad-cleanup ledger** (same day, `c110b3f`): deleted the dead
`CallPad_ClearPFColumn` pad (no call site in any bank; the body is reached
directly from `BombMarkWalls`) from bank0 and bank1, which shifts the pad block
by 6 B — `CallPad_BuildColupF`'s post-switch image moved `$FC3B → $FC35` in
bank3 and bank2's twin `$FC38 → $FC32`. Used **10896** (b0 −6 code, b1 −6
code, fill +12), free 5488.

### Measured floor (2026-10-19)

Every remaining stage-data idea was built and measured, not estimated:
S1 **+5 B worse**, S2 **+12 B worse**, S4 **−14 B** (the only free win), and a
`SetupScorePointers` loop trim broke `sim_frame_budget` (+1 line: 6×`sta abs`
is 24c, the 2-step loop is 64c — the HUD band has no slack, revert).

Structural reason the crumbs stop here: every bank region is anchored by
absolute `.ds` pins (cross-bank twins + page-aligned font), so shrinking code
*inside* an anchored region only grows that region's fill — it never moves the
end. Only a deletion *after* the last pin would create headroom, and bank0's
last bytes are the `CallPad_MusicTick` pad. Consequence: **bank0's 1-byte
pre-pad headroom is structural**, not a compaction failure; any new bank0
feature needs a bank0 deletion, not a size win elsewhere.

### Merged title screen over the live stage (2026-10-19, same day)

The old two-step title (intro splash `$FD` + "old title" level select `$FF`)
was merged into ONE `$FF` screen. Design (user spec): the **stage itself** is
the background — the TitleKernel draws the room's three PF rows from the
buffers `EnterRoom` staged, plus the player at the level start — with the
S.A.V.I.O.R. logo and the credit footer drawn over it. The HUD band follows
(`jmp MenuMain`), so **the score shows level+1**, lives/bombs/bar unchanged.
The theme plays on `$FF`; SELECT cycles the level (loads the preview), RESET
starts the game (drop-in). `LoadLevel`'s banner gate skips LV001 on `$FF`.

Removed (measured from the listings, replaced with `.ds` where addresses are
pinned): bank2 `TitleSequence` 267 + dead fold images 12; bank1 `TitleBandPrep`
104, `TitlePlayerBand` 89, jet/bomb/blink art 52; bank0 `TitleIntro` 55, three
folds 18, `DropStep` `$FF` shim 7. Added: `TitleKernel` rewritten as the
stage-band kernel (PF rows + player + logo + footer + HUD), the bank1 player
art twins (24 B) and the earlier digits band removed. Result: **10896 → 10362
(-534 B used)**; the black-screen variant measured 10303, so the stage variant
costs **+59 B** — it reconstructs the stage in a dedicated kernel instead of
hijacking the cave kernel's bands (the safe choice: the row-2 setup line has
zero cycle margin, see below).

Line budget: the title frame is a full 3-band + HUD frame, so the wall target
is **267.0 for both kinds** (`sim_frame_budget.target_for` no longer returns
265.0 for title frames; the old black title kernel skipped `.Row`). Tests
`test_title_demo.py`, `test_menu_flow.py` and `test_intro_music.py` follow the
`$FF` contract (score follows the selected level, music ticks on title frames).

Remaining reductions are feature decisions, not compaction:
- LV001 banner: ~76 B (banner path + `L`/`V` glyphs) — now redundant-ish: the
  merged title already shows the selected level. Visible only for 1 s at stage
  start.
- Music (`MusicTick` + melody): ~200-390 B — audible; user wants it kept.
- Credits footer (`FooterBand` + `FooterFont`): ~185 B — visible.

## 5. Open decisions for the user

1. **After A3, does the crunch machine stay in bank3 or move to bank2?**
   Recommendation: **bank2** (C2) — it shares PF staging with `VcrShutter`
   there, and bank3 stays pure data. C2 as written assumes this.
2. The score rewrite (4a) changes how the score looks in a good way only if we
   match HERO's 2-px digits; confirm that is wanted.
3. Title/intro/music: keep for now (decided 2026-10-19).

## 6. Command cheatsheet

```bash
cd src
./build.sh 2>&1 | grep -E "error|Done|sim_|verify"
bash ../tools/freeze_test_banks.sh
for f in ../tools/test_*.py; do /home/iuri/python3/bin/python3 "$f" >/dev/null || echo FAIL $f; done
/home/iuri/python3/bin/python3 tools/test_title_demo.py
/home/iuri/python3/bin/python3 ../tools/rom_size_report.py --md
# after any chain change (sim runs on the PREVIOUS savior.bin):
cat bank0.bin bank1.bin bank2.bin bank3.bin > savior.bin
```

## 7. Watch-outs specific to A3

- The two-pass build means **bank2's `bank3_labels.asm` must exist before bank2
  assembles** — commit the generator and the ordering together.
- `emit_spills` must keep sizing only the bank2 table files; a block that
  overruns its bank3 org must fail loudly in `verify_build`, not silently
  overwrite code.
- `EnterRoomB2`'s tail must not add a stack frame: the room-load chain is at
  the measured floor (`sim_bomb_fuse`).
- `HotOverlapBody` is reached from bank0 by a **tail** call with a C=1
  contract; every exit must still end `sec / jmp $FBF8`.
- After moving `PhaseBlink`, re-run `test_vcr_shutter` and
  `test_phase_kill_frame` first — they are the ones that catch ordering and
  tramp mistakes.
