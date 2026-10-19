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

## 2. Chunk C2 — crunch consolidation (needs A3)

- Move `PhHcrEntry` + `CrPfx0/1/2` + `HcrClock` + `HcrPush` (~420 B) from
  bank3 into the hole vacated by the level data (bank2), then merge the PF
  staging with `VcrShutter` (also bank2).
- `$FC34` (PhHcrPre → PhHcrEntry tramp) becomes a local `jmp`; delete the
  bank3 twin; the `$FCC1-$FCDD` return pads collapse to `jmp PhNext` /
  `jmp HOVnext` in bank2.
- Unify the mask tables (`OvHead/OvTail` vs `CrPfx*`) and the clock
  (`VcrStateTab` 32 B vs `CrunchClock`).
- **Expected:** 200-300 B. Tests: `test_hcrunch`, `test_vcr_shutter`,
  `test_phase_kill_frame`, `test_phase_kill`.

## 3. Chunk C3/C4 — small cleanup

- Fold `HcrPush`/`HcrClock` into the staging path once C2 has merged banks.
- Drop the retired legacy twin images (`$FB57/$FB61/$FD7B` in bank3) and
  re-pin the pads. ~6-15 B.

## 4. Reorganisation (after the crunch)

### 4a. Score renderer → HERO PF-table score (**approved by user**)

- Replace the 48-px sprite score (`MenuMain` loop + `SetupScorePointers` 123 +
  `DigitGfx` 104 data = ~1033 B) with HERO's model: per-scanline PF tables
  baked per digit (`LFA00/LFB00/LFC00/LFD00` pattern), 4-5 scanlines per digit,
  masks per row.
- **Expected 200-400 B.** Highest risk item: visible output changes. Gate:
  `sim_frame_budget` (HUD band line budget) + screenshots + `test_title_demo`
  (title uses the same text technique — decide whether it shares the new
  renderer).
- Precedent: `docs/font/48px_score_skill.md` documents the current technique;
  write the new one next to it.

### 4b. Dedupe list (measured in `docs/code_size_audit.md` §3)

| item | bytes |
|---|---|
| one row/band conversion (`YToRowTable` 48 B + `BandRowFromLine` + inline `/48`) | ~70 |
| one bit table (now `EnemyBitTable` ×2 + `RaftBitTab`) | 8 + call sites |
| one `M1OffTab` (bank2 + bank3 copies) | 4 |
| one band-mask table set | ~20 |
| one crunch clock | ~50 |
| walker prologue (PHM/MothDoWalk) — only if a fold-free sharing trick exists | ~40 |

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
today: code alone is 9340 B vs 8192 in two banks, so it needs ~1.2-3 KB more
off. Keep hunting after the reorg; candidates already identified: the title
cluster (978 B, keep for now), tally/banner (220), and the pad tax (512).
Also on the wish list for parity with HERO: Activision-style logo screen,
more colours per stage, HERO's 13+2 HUD columns.

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
