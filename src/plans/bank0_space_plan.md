# Bank0 space plan — clear room for future content

**Status:** plan (2026-10-16). Baseline build is green; working tree clean.

## Rule (user, 2026-10-16)

**Do not add anything to bank0 unless it is very needed. New code/data goes to
bank2 (or bank1) by default.** This plan exists because bank0 is at 100% and
byte-identity-frozen — the 2026-10-16 respawn-hover (Phase 8) could not be
implemented at all (needs ~20B) without a bank0 refactor.

## Current bank0 budget (2026-10-16, from `bank0.lst`)

| Region | Range | Notes |
|--------|-------|-------|
| Pre-pad code | `$F000-$FC67` (3176B) | 1 byte headroom (`ends $FC67, limit $FC68`) |
| Fold pads + CallPads | `$FC68-$FC70` / `$FBF8-$FC48` | **pinned byte-identity** (bank1/bank2 twins) |
| Post-pad code | `$FC70-$FEFE` | full |
| Fixed data | `$FF00` fineAdjustTable, `$FF0F` SetObjectXPos | **pinned** |
| Vectors | `$FFFA-$FFFF` | |
| Real data (no `.ds`) | ~367B | ObjColorTab 72, ObjSprites 72, TitleFont 48, YToRowTable 37, sprite/walk/col tables ~84, BeamMask 12, misc |
| Code | pre-pad ~2719B + post-pad ~663B | |

Counted labels: 263. The `.ds` fills between pinned blocks are not free space
(they only exist to reach the pins).

## Hard constraints (do not break)

- **Cross-bank reads:** bank0 CANNOT read bank1/bank2 data with `abs,X/Y`.
  Moving a table to another bank requires relocating its READER too (or adding
  a fold). Moving a `.byte` table alone = silent garbage.
- **Byte-identity pins** (any size change before them must be offset by an equal
  removal so the `.ds` absorbs the shift — adding bytes breaks `verify_build`):
  fold pads `$FC68`/`$FC70`, CallPads `$FBF8-$FC47`, sprite twins `$F8DD`
  (PlayerSpriteA/B/WalkA/B + PlayerColTable), blast tramp `$FDDA`,
  `PickPlayerFrame` `$FDE1`, `fineAdjustBegin` `$FF00`, `SetObjectXPos` `$FF0F`.
- **Page-cross-critical:** `SetObjectXPos` `bcs .Div15Loop` (5c contract), and
  the kernel `.Line` `abs,Y` fetches (`ObjSprites`, `PlayerColTable`,
  `(Grp0Ptr),Y`). Code motion near these flips a taken branch across a page.
- **Stack depth:** `sim_bomb_fuse` gates gameplay min SP ≥ `$F8` — a new `jsr`
  level in a deep path moves the danger line 2B down.
- **Timing:** `sim_frame_budget` wall-model 267; `sim_bomb_fuse` VBL/overscan
  budgets. Bank switches cost cycles — bad on hot paths (overscan entry, VBL).
- **ZP is full** (`$80-$BB` sequential + `$BC` RoomBandColor + `$BD+` EQUs +
  `$F0-$F7` + `$F8-$FF` stack). A new persistent byte needs a relocation.

## Movable chunks (ranked by win / risk)

### 1. Title subsystem → bank2 (~390B, COLD) — best target
`TitleKernel` (104), `.TkBlnk` 15, `.TkLoop` 54, `.TkFooterPad` 7, `.TkPlayer`
61, `.TkPostFooterPad` 17, `TitleSelect` 25, `TitleIntro` 44, the title folds
(`TitleSequenceFold`/`FooterFold`/`TitlePlayerFold` 18), `TitleWork` +
`TitleTailAudio` (~39), `PickPlayerFrame` (6), `TitleFont` (48).
Runs **only on the title/intro** — no gameplay timing pressure, so a bank
switch per title frame is free.
- **Dependencies:** `TitleWork` does `jsr LoadLevel`, `jsr BombTick` (bank0);
  the title kernel tail `jmp StartFrame` (bank0); entered via `jmp TitleKernel`
  (frame dispatch, line ~2661); `DropStep` `beq TitleWork`; `RefreshEnemyY`
  `jmp TitleWork`; `TitleIntro` tail-jumps `TitleTailAudio`.
- **Mechanic:** a bank0→bank2 entry tramp + a bank2→bank0 return (fold-pad
  pattern), plus small bank0 stubs where the title calls bank0 leaves.
- **Risk:** medium — the title already bit-rotted once (the 2026-10-06 TitleWork
  shrink broke `$FDE1`). Gate with `test_menu_flow`, `test_title_demo`,
  `test_phase2_ball` (title frames).

#### Step-1 findings (2026-10-16, before implementing)
Surveying the actual code shows the title move is a **multi-step refactor**, not
a single chunk move — two hard blockers:
1. **`TitleKernel` calls `jsr SetObjectXPos` SIX times mid-kernel** (entry
   P0/P1, player band P0/P1, footer restore P0/P1). `SetObjectXPos` is **pinned
   at `$FF0F` in bank0** and its `bcs .Div15Loop` / page-aligned `fineAdjust`
   timing is load-bearing. A bank2 kernel therefore needs a **bank2
   `SetObjectXPos` copy + its own PAGE-ALIGNED fineAdjust table** (~35B), or the
   kernel can't move. Duplicating a cycle-tuned, pin-guarded routine is the
   riskiest part of the whole plan.
2. **Every cross-bank transition needs a SAME-ADDRESS byte-identical twin**
   (the fold-pad / CallPad rule). The existing twin slots (`$FBFC-$FC47`
   CallPads, `$FC68/$FC70` fold pads, `$FBD0-$FBEE` return pads) are **full** —
   a new entry/exit/return needs a fresh mutually-free bank0+bank2 address pair.
   The title kernel also exits via `jmp Overscan` and `jsr FooterFold`, both
   bank0, so the exit needs a shared-block tramp too.
3. The cold **helpers** call bank0 directly: `TitleWork` → `jsr LoadLevel`;
   `TitleIntro` → `jsr DropArm` + `jsr TitleSequenceFold`; `TitleTailAudio` →
   `jsr BombTick` + `jsr CallPad_UpdateBombSound` + `jmp StartFrame`. Moving
   them needs a bank2→bank0 return mechanism — **the codebase has no
   bank2→bank0 `jsr` today** (only bank0→bank2/3 and the data fold), so this
   pattern must be established first.

**Revised step 1 (sub-ordered, each verified before the next):**
- 1a. Create ONE reusable bank0↔bank2 tramp slot pair at a mutually-free
  address (freed from the title region once it shrinks) + prove a bank0→bank2
  `jsr`/return round-trip with the smallest cold leaf (`TitleSelect`, 25B).
- 1b. Move the title helpers (`TitleWork`/`TitleIntro`/`TitleTailAudio`) using
  that tramp + a bank2→bank0 call gate for `LoadLevel`/`BombTick`/`DropArm`/
  `StartFrame`.
- 1c. Duplicate `SetObjectXPos` + a page-aligned `fineAdjust` in bank2, then
  move `TitleKernel` + loops + `TitleFont`.
- 1d. Move the title folds' bank2 bodies (they may already be in bank2 — check
  `bank2.lst`) and retire their bank0 stubs.

Alternatively, if 1c proves too risky, keep the kernel in bank0 and bank only
the helpers + font (smaller win, ~150B), or pivot to a lower-coupling chunk
(§4 cold leaves / §2 data with a cold reader).

### 2. Data tables → bank2 (up to ~250B after TitleFont)
`ObjColorTab` (72, read by `SelectActiveObject`), `ObjSprites` (72, read by
`SelectActiveObject` + the kernel `.Grp1`), `YToRowTable` (37, read by
`PlayerHitsMap`), `BeamMask` (12), `EnemyColorTable`/`ObjSpriteOffTable` (12),
`EnemyBitTable` (4), `BombBlinkColors` (4), `EnemyOffTable` (3).
- **Strategy:** relocate the READER into bank2 alongside the table (e.g.
  `SelectActiveObject` → bank2), **or** keep the reader and add a dedicated
  fold for the table. The sprite/walk/col tables (`$F8DD`) have bank2 art
  twins at the SAME address (`test_miner_colors` asserts EQU + byte identity)
  — they are NOT duplicated waste; leave them.
- **Note:** `ObjSprites` is fetched by the kernel `.Line` via `abs,X` — moving
  it is a page-cross/timing risk (rule above). Prefer moving `ObjColorTab` +
  its reader.

### 3. Cold leaf routines → bank2 (~150-250B)
`CheckMinerPickup` (35), `DeriveEnemyY` (33), `ExitRoomUp/Down/Left/Right`
(~90), `TallyWork`, `LoseLifeBand`/`CheckBandTouch` (27), `SelectActiveObject`
(35, but hot). Move only cold ones; hot routines (`CheckEnemyHit`,
`SelectActiveObject`, `PlayerHitsMap`, `RefreshEnemyY`, `BombTick`) cost
overscan cycles via a tramp — avoid unless the cycle ledger allows it.

## Compression opportunities

- `YToRowTable` (37B): `A>>2`-indexed 4-row table — the AGENTS precedent
  (floor-nesting `floor(floor(A/4)/12)==floor(A/48)`) already shrank it once;
  re-check for further nesting / compute.
- `ObjColorTab` (72B): 9 slots × 8 rows — check whether the mine/enemy colors
  can be derived from `EnemyColorTable` + a stride instead of a full table.
- `ObjSprites` (72B): 9 sprites × 8 rows — art; likely irreducible.
- `.ds` fills: audit the pinned gaps (`$F8DD`, `$FDDA`, `$FDE1`, `$FC68`) —
  some slack may be reclaimable by re-pinning, but each pin matches a bank2
  twin, so verify with `verify_build`.
- Effectively-dead post-code (e.g. `ReloadLevel`'s unreachable tail) is kept
  byte-identical for address stability — **do not** remove without checking the
  downstream twins.

## Move mechanics (reuse the existing patterns)

- **Bank0 → bank2 entry (`jmp` tail):** bank0 `sta $1FF8; jmp $Fxxx`; bank2
  holds a byte-identical `jmp` at the SAME address (fold-pad rule).
- **Bank0 → bank2 `jsr` (returns):** CallPad pattern — body executes the
  bank select, `rts` is fetched from the bank0 twin at the return PC.
- **Bank2 → bank0 leaf call:** the bank2 body must switch back before the
  `jsr`/`jmp` operand fetch, with the twin at the same address.
- **Pins move safely on REMOVAL only:** deleting bytes before a `.ds` pin lets
  the `.ds` grow; ADDING bytes breaks the pin (offsets everything after).

## Sequenced plan

1. **Title subsystem → bank2** (prime the tramps + `TitleFont`). Target: free
   ~390B. Gate: `test_menu_flow`/`test_title_demo`/`test_phase2_ball` + build.
2. **`ObjColorTab` + `SelectActiveObject` reader → bank2** (or a fold). +~100B.
3. **`YToRowTable` compression** (compute/nest instead of a 37B table) and the
   small tables. +~50B.
4. **Cold leaf routines** as needed (`ExitRoom*`, `CheckMinerPickup`,
   `DeriveEnemyY`). +~150B.
5. **Then unblock Phase 8**: the respawn hover (needs ~20B) + a ZP byte
   (relocate one if still needed).

## Test gates (run after every move)

- `./build.sh` — `verify_build` (byte-identity pins + ZP EQU sync),
  `sim_bomb_fuse` (stack), `sim_frame_budget` (wall-model/VBL/overscan).
- Full battery (`../tools/test_*.py`), especially: `test_menu_flow`,
  `test_title_demo`, `test_miner_colors`, `test_phase2_ball`,
  `test_phase3_ball`, `test_hcrunch`, `test_vcr_shutter`, `test_cell_map`,
  `test_laser_*`.

## Expected outcome

Title move alone unblocks the Phase 8 hover and restores headroom for future
content. Steps 1-4 target **~500-700B** freed in bank0, at which point the
"don't grow bank0" rule is enforceable rather than aspirational.
