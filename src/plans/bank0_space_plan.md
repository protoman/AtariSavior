# Bank0 space plan — clear room for future content

> **SUPERSEDED 2026-10-16 by `docs/refactor_v4_plan.md`.** The premise here ("a
> `.ds` pin makes removal free nothing; space needs a 4-bank pin shift") is
> wrong: the pin's fill is itself usable space, and bank0 has a verified 225B
> free run at `$F7FC–$F8DC`. Read `docs/refactor_v4_plan.md` first.

**Status:** plan (2026-10-16). Baseline build is green; working tree clean.

> ## ⚠ CORRECTION (2026-10-16, after starting step 1)
>
> **Removing code/data from *before* a `.ds` pin frees NOTHING.** A pin
> `.ds $X - *, 0` fills to `$X`; if the content before it shrinks, the fill
> simply grows, `$X` stays, and everything after `$X` is unchanged → the
> pre-pad end (`$FC67`) does not move. Conversely **adding** bytes before a pin
> errors (`Origin Reverse-indexed`) because the fill is already ~0.
>
> This means the original §"Movable chunks" premise is **wrong**: moving the
> title kernel (`$F9FB–$FAFF`, before the `$FB00`/`$FBD0` pins) would shrink
> the `$FB00`-pin content and just grow that fill — **0 bytes freed**.
>
> **Bank0 has ~20 pins** (`$F8DD $F9B8 $FB00 $FBD0 $FBD6 $FBE0 $FBE8 $FBF8
> $FC49 $FE00 $FE48 $FE90 $FE96 $FEF0 $FEF6 $FF00 $FFE6 $FFFA`), most of them
> **cross-bank byte-identity twins** (bank1/bank2/bank3 copies at the same
> address). Freeing real space therefore needs one of:
> - **(T) tail moves only** — content AFTER the last pin in each region. Pre-pad
>   tail = `MothYDerive` (`$FC4F–$FC67`, ~24B) → move it out to free ~24B.
>   Post-pad tail = the `$FFE6+` region. **Small (tens of bytes).**
> - **(R) RE-PIN** — remove a chunk AND move the downstream twin pins down by
>   the same amount, updating every cross-bank twin (bank1/bank2/bank3) + every
>   hardcoded address reference + the `verify_build`/test guards. This is the
>   only way to reclaim hundreds of bytes, and it is a coordinated 4-bank
>   operation (this is what past sessions did — the AGENTS records pin moves
>   `$FB84→$FBC0→$FBF8`). **The real plan is a re-pin, not a "chunk move".**
>
> Recommended: do **(T)** first (safe, ~24B, unblocks nothing by itself but
> proves the tail-move pattern), then scope **(R)** for the title kernel +
> `TitleFont` (a ~300B re-pin: move the `$FB00`/`$FBD0`/`$FBFC`/`$FC49` pins down
> past the removed kernel and re-sync the twins). The §"Movable chunks" lists
> still name the *content* worth relocating; only the freed-size math changes
> (it is the pin shift, not the content size, that yields space).

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

## R progress (2026-10-16, auto-pilot)

**Decision: title kernel → bank1** (user: keep code to bank0/bank1 + maybe
bank2-start; keep bank3 data-only; don't spread code to bank3).

- **R slice 1 (done, `2122eef`):** `jmp $FBF8` → `jmp ReturnPad` (label in
  kernel/bank1/bank2) — ROM byte-identical; de-risks the `ReturnPad` pin shift.
- **R1.1 — needs NO new code:** bank1 ALREADY has a page-aligned copy,
  `SetObjectXPos_b1` (`$F7F2`) + `fineAdjustBegin_b1` (`$FF00`, page-aligned),
  used by the HUD bar. bank1 also has **1307B free** (`$F025–$F53F`). The
  kernel can call `SetObjectXPos_b1` directly — no bank2 copy needed, which
  sidesteps the bank2-fragmentation blocker entirely.
- **R1.2 blocker (fold chain):** `TitleKernel` calls `jsr TitlePlayerFold` /
  `jsr FooterFold`. Those are bank0 stubs → bank2 bodies (`FooterBand`,
  `TitlePlayerBand`) that exit via `jmp ReturnPad` = **`sta $1FF6` (bank0
  hardcoded)**. A bank1 kernel cannot use them — the bodies must move/duplicate
  into bank1 (`FooterBand`+`FooterFont`+`TitlePlayerBand`, and `TitlePlayerBand`
  →`TitleBandPrep`). These folds are **kernel-only** callers, so the bodies can
  move bank2→bank1 (bank2 loses the fill, no space change there; bank0's
  `FooterFold`/`TitlePlayerFold` stubs become dead). Net: bank1 grows ~200B
  (has room), bank0 shrinks by the kernel+font (~310B) after the pin shift.

**Next:** (R1.2) move kernel+font + fold bodies to bank1; entry from
`KernelInit .TkPath` (bank0→bank1 tramp) + exit `jmp Overscan` (bank1→bank0
return); repoint the kernel's `jsr`s to `bank1` targets. Then (R1.3) verify, and
(R1.4) shift the `$FB00/$FBD0/$FBD6/$FBE0/$FBE8/$FBF8/$FC49` pins down.


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

## Sequenced plan (batch-shift model — 2026-10-16 revision)

**The pin shift is the ONLY step that frees bank0** (moving content alone just
grows the `.ds` fills). So do **all content moves first**, then **one** pin
shift. Do NOT interleave moves with shifts.

**Kernel clarification (user 2026-10-16):** the thing to move is the **title/
intro kernel** (`TitleKernel` `$F9FB`, a cold splash-screen display kernel), NOT
the main cave kernel. The main cave kernel + all core gameplay stay in bank0.
See `docs/bank_layout.md` for the full kernel/bank map.

### Phase A — settle the target layout
- bank0 = main game code + cave kernel.
- bank1 = HUD + title subsystem + Phase-4 crunch bodies (+ event routines if
  chosen).
- bank2 = start-of-bank code + all data.
- bank3 = data only + the mandatory 5-byte stub.

### Phase B — content moves (order = easy/self-contained first; each verified; NONE frees space yet)
- **B1. `YToRowTable` compression** (compute/nest) + tiny tables. Low risk.
- **B2. Cold helpers → bank1/bank2** (`ExitRoom*`, `CheckMinerPickup`,
  `DeriveEnemyY`, `LoseLifeBand`/`CheckBandTouch`).
- **B3. `ObjColorTab` (+ its reader, or a fold) → bank2.**
- **B4. Title kernel subsystem → BANK2** (corrected 2026-10-16: NOT bank1).
  The title machinery is `bank0↔bank2` twin-coupled — `TitleBandPrep` sets
  `Grp0Ptr` to `PlayerWalkA/B`/`TitleJetSprite` and `TitlePlayerBand` reads the
  sprite from bank2's byte-twins at bank0's sprite addresses (`$F8DD`/`$FDE7`).
  So the kernel+`TitleFont` must join its helpers (`TitlePlayerBand`,
  `TitleBandPrep`, `FooterBand`, `FooterFont`) in **bank2**:
  - needs a bank2 `SetObjectXPos`+`fineAdjust` copy — place at `$FBA7..$FBC5`
    (41B free run); NOT page-aligned but the `lda fineAdjustTable,Y`
    page-cross-equivalence holds there (`(table-241)` low byte + Y carries), so
    the 5c contract stands;
  - kernel `jsr`s → the bank2 fold bodies directly (already same-bank);
  - entry `KernelInit .TkPath` (bank0→bank2 tramp) + exit `jmp Overscan`
    (bank2→bank0 return).
  (The earlier bank1 idea is void — bank1 can't host the sprite twins.)
- Optional (bigger): post-pad **event** routines (`DropArm`/`DropStep`/…) →
  bank1. Hotter + call-web → only if more space is needed.

### Phase C — the single pin shift (this is where the bytes appear)
- Shift the `$FB00/$FBD0/$FBD6/$FBE0/$FBE8/$FBF8/$FC49` pins **down** by the
  total removed, in **all banks** (twins). `ReturnPad` literals already track
  the label (R slice 1, `2122eef`). Net freed ≈ total Phase-B bytes.

### Phase D — verify + unblock Phase 8
- `./build.sh`, full battery, Stella title + gameplay screenshots.
- Then the Phase 8 respawn hover (~20B) + a ZP byte if still needed.

### Phase E — R2 (separate, later): stop spreading code
- Move the bank3 crunch bodies → bank1; make bank3 data-only. Rewrites the
  Phase-4 `bank2↔bank3` tramp web → `bank2↔bank1`. Do after R1.


## Test gates (run after every move)

- `./build.sh` — `verify_build` (byte-identity pins + ZP EQU sync),
  `sim_bomb_fuse` (stack), `sim_frame_budget` (wall-model/VBL/overscan).
- Full battery (`../tools/test_*.py`), especially: `test_menu_flow`,
  `test_title_demo`, `test_miner_colors`, `test_phase2_ball`,
  `test_phase3_ball`, `test_hcrunch`, `test_vcr_shutter`, `test_cell_map`,
  `test_laser_*`.

## Expected outcome

The batched Phase-B moves + the single Phase-C pin shift target **~500-700B**
freed in bank0, at which point the "don't grow bank0" rule is enforceable
rather than aspirational. `docs/bank_layout.md` records the kernel/bank map for
future placement decisions.
