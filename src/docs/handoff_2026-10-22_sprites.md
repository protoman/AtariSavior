# Handoff — sprite refactor, next session (written 2026-10-22)

Read `plans/hero_kernel_plan.md` § "Backlog after Phase 6" first; this file is
the state note + the exact next step. Tree is **clean**, `build` + both sims +
the full battery are **green** at `a588479`.

## What landed today (all verified, all committed)

| commit | what |
|---|---|
| `db57c66` | **Enemy record `type\|dir` (b7) masking.** `UEDispatch` and `CheckEnemyHit` now `and #%01111111`; converter emits `dir: 0` for LAMP/RAFT. Before this, a raft authored dir=right read `$87`, missed `cmp #ENEMY_RAFT` and its body never ran (the "raft jitter" report). |
| `34e6759` | user stage edit (raft moved, level 4 room 4). |
| `5e0dff9` / `7144613` | 12-row object art (stride 12, `OBJ_WINDOW` folded into `PLAYER_HEIGHT = 12`), then snake/raft halved to rows 0-5 solid so the log floats ON the surface. |
| `0e6b482` | **fall clamp fix**: the high-byte-only `cmp #>MAX_FALL` rewrote every speed in `$0100..$017F` to `$0180`, so thrust was computed and thrown away each frame. Now compares the low byte; a terminal fall stops in 10 frames. |
| `3c35d03` + `1400722` | **slot-1 HMOVE fixes**: the hook's mid-frame HMOVE must clear `HMP0`/`HMM0`/`HMBL` (else the player's fine adjust is applied twice = the "zig-zag"), and those clears must sit **before** the `WSYNC` (else it is a LATE HMOVE and slot 1's sprite snaps in ~4 px steps). |
| `4e55124` | **phantom M1 dash**: `PositionBallM1` read `CollisionEndX` (the laser wall-clamp's scratch) as M1X. M1X now lives in `LevelEnemySpare2`/`$B0`, never written today. |
| `10bd6fa` | **miner flicker**: `PinSlot0` pins slot 0 to the other candidate in two-band rooms (`FlickerFrame = desired + count - 1`); bomb keeps its 1-of-4 frames; ≥3 candidates skip the pin. |
| `a588479` | plan backlog + `PinSlot0` guard. |

## Current bank0 map (from `bank0.lst` / `rom_size_report`)

```
SelectActiveObject  $F629      StageSlot1   $F750      Slot1Hook  $F815
ObjSprites          $F850      CallPad_RaftBody $F8C0  PositionBallM1 $F9C1
ObjColorTab         $FB1F      PinSlot0     $FB8B      FoldIndirect $FEF6
BandStart           $FE00      EnemyColorTable $FE04   ObjSpriteOffTable $FE0C
```

- `$F744` fill now runs `StageSlot1` + `Slot1Hook` and ends at the `ObjSprites`
  pin (`$F850`) with ~0 B slack. **This is the space that step 1 must free.**
- `$FB20` fill: `ObjColorTab` (108 B) + `PinSlot0` (~50 B), ~20 B left.
- `$FE00-$FE8F` fill: `BandStart` (4) + `EnemyColorTable` (8) +
  `ObjSpriteOffTable` (8) — all `abs,X`, address-irrelevant.
- Pre-pad ends `$FC58`, limit `$FC68` (**16 B**). Page guard: `ObjSprites`
  low byte + 107 must stay ≤ 255 (currently `$50`+107 = 187 ✓).
- Sizes: bank0 used 3816 / free 280; level data 127 B.

## Step 1 landed (2026-10-22): `StageSlot1` + `PinSlot0` are in bank2

| what | where |
|---|---|
| `StageSlot1B2` (+ `PinSlot0`, `ObjSpriteOffTable` copy) | bank2 `$FAC0-$FBCF` |
| entry pad | kernel `CallPad_StageSlot1` = `StageSlot1` at `$FBE5` (`sta $1FF8`) |
| pad's other half | bank2 `$FBE8` = `jmp StageSlot1B2` |
| exits | `jmp ReturnPad` (`$FBF8`) → `sta $1FF6` + bank0's `rts` |
| guard | `verify_build.MOVE_PADS` (both halves + operand) |
| freed | bank0 `$F744` fill: **202 B** between `Slot1Hook` (`$F750`) and the `ObjSprites` pin (`$F850`) |

- Bank0 went **3816 → 3562 used**; bank2's `spill_F9D9` slot end moved
  `$FBD0 → $FAC0`, so level data still starts at `$F9D9` and **no generated
  address moved** (only `generated/symbols.asm` changed, which is bank0's own
  symbol dump).
- The body is instruction-for-instruction the old one: the only two changes are
  `jsr FoldIndirect` → `lda (FetchPtr),Y` (the records live in bank2, so the two
  bank switches per read are gone) and every `rts` → `jmp ReturnPad`. Verified
  by a normalised diff of `git show HEAD:src/kernel.asm` against the new block —
  119/119 and 40/40 lines identical.
- Frame budget **unchanged** (`{265: 3, 267: 1098}`, cave WSYNC 195), so the
  pad's extra bank switch cost no scanline. Full battery green after
  `freeze_test_banks.sh`.
- The bank2 block ends **flush** at `$FBCF` (the `$FBD0` EnterRoom twin pin):
  any growth there fails the build with `Origin Reverse-indexed` — that is the
  intended alarm, not a bug.

## Step 2 landed (2026-10-22): Phase 4's VDEL premise was wrong — P0 half only

**Read `plans/hero_kernel_plan.md` § "Phase 4" first.** Short form:

- **VDEL is a cross-buffer latch, not a one-line delay** (Stella
  `Player::grp`/`updatePattern`/`shufflePatterns`): a GRP write lands in
  `myPatternNew` and renders at once; with VDEL the live pattern is
  `myPatternOld`, latched by the OTHER player's write. HERO also clears
  `VDELP0/1` at cave entry — it uses VDEL only for its HUD text.
- Measured `.Line` store phases: `COLUP0 c19`, `ENAM0 c25`, `GRP0 c35`,
  `GRP1 c58`, `COLUP1 c65`. A sprite's pixels start at `(61+X)/3`, so a store
  reaches the next line only for sprites left of `GRP0→44 px`, `GRP1→113 px`,
  `COLUP1→134 px`.
- **Landed:** cave `VDELP0 = 1`, `VDELP1 = 0` (VBL init, +2 B, 0 c). The
  player's art/colour boundary moves from X < 44 to X < 113 px *and* art row r
  now shares a scanline with `PlayerColTable[r]`. Wall model unchanged
  (`{265: 3, 267: 1098}`), every path cycle identical. Guard:
  `tools/test_vdel_cave.py`.
- **Not landed:** P1 VDEL (would latch on the earlier `GRP0` store = worse), and
  the per-line staged colour byte (needs **+6 c**, the worst path has **4 c**).
- **USER CHECK NEEDED:** the player sprite now sits one scanline lower for
  X ∈ [44,113) (it used to be one line high there). Eyeball it in Stella: art
  and colours must line up row-for-row, no flicker/seam changes.

## Step 3 landed (2026-10-22): Phase 6 FORMAT — 16-row object window

`OBJ_WINDOW = 16` split from `PLAYER_HEIGHT = 12` (hit box), tables 9 × 16 =
144 B each, stride-16 `OBJ_*`, `ObjSprites` base `$F850 → $F830` (still ends at
the `$F8C0` pin), page guard `+71 → +143`. Every design has 4 new rows: art
`$00` blanks (reserved), colour = the design's own. **Zero visual change, 0 c**
(`cmp #OBJ_WINDOW` = same size). Full details + the two traps in
`plans/hero_kernel_plan.md` § "Phase 6 — 16-row object window".

Traps this dug up (both guarded now):
- `OBJ_BOMB = 128 = $80` broke the `bmi` "no object" sentinel: the bomb's `P1`
  was never positioned (`test_bomb_render_x`). Slot 0 now branches once on
  `cmp #$FF` (`.SOBlank` replaced `.SONoObj`); slot 1 keeps `bmi` (miner/enemies
  < `$80`) with the invariant commented. **Budget:** 6 c of comparisons in the
  VBL = 268-line frames in `test_phase3_ball`; 2 c is what fits.
- `check_equ_sync` only compared `$hex` values, so the decimal `OBJ_*`
  hand-copies in bank2 drifted silently — the guard now compares decimals too.

Remaining Phase 6 work is **art-led**: fill rows 12-15 of a design (+ its
colour rows), one type per commit. Hit box stays 12 until a gameplay ruling.

## OPEN — user report 2026-10-22: "miner + enemy flickering again"

**Diagnosed: same-band, and that is the documented limit — not a regression.**
`StageSlot1` only pairs candidates that sit in DIFFERENT 48-line bands; two
objects on the same scanlines cannot share one GRP1. Measured from the live
stage (`miner_y` is a tile row → `px*12`, enemy `y` likewise):

| level / room | miner (drawn) | enemy | bands | verdict |
|---|---|---|---|---|
| L2 room 2 | 84 (+3 = 87) | y row 5 → 60 | 1 / 1 | **same band → 30 Hz rotation** |
| L3 room 3 | 87 | y row 4 → 48 | 1 / 1 | **same band → 30 Hz rotation** |
| L4 room 4 | 87 | y row 8 → 96 | 1 / 2 | paired ✓ (the case `PinSlot0` exists for) |

The panel is built: `tools/test_slot1_pair.py` drives the REAL `jsr StageSlot1`
through the bank switch (pad `$FBE5` → bank2 `$FBE8`) and asserts the pair, the
`PinSlot0` value (`desired + count - 1`), the same-band skip, and the miner's
`+3` draw offset — so the two-band path is provably sound.

Ways to clear the two same-band rooms (all outside the kernel):
1. **Stage edit (user).** Move ONE of the two objects into another band:
   L2 room 2 enemy row 5 → row 3 (36, band 0) or row 8 (96, band 2);
   L3 room 3 enemy row 4 → row 3 or row 8 (`miner_y` 7 could move instead, but
   it is one number per level). Cell must be air and respect 1 element/row.
2. **Accept** 30 Hz on those two rooms (HERO flickers the same way when two
   objects share a band).
3. **Phase 7** (ball/M1 as a third channel) — the miner is 4 px wide
   (`MINER_WIDTH`), so the ball *could* carry a 4-px vertical silhouette, but
   that is a new renderer, not a fix.

Ruled out by measurement: a mid-band reposition (it needs a per-line line
counter compare, ~6-8 c/line, and `.Line` has 4 c).

## Agreed order (do not reorder without a reason)

1. **Space move (next step, mechanical).** Move `StageSlot1` (194 B) out of the
   `$F744` fill into a bank2 slot behind a `jsr` (bank2 free = 2666 B, plenty).
   It is called from `SelectActiveObject`'s two tails, so a `jsr` is already the
   call shape — only the callee address changes. Keep `Slot1Hook` where it is
   (it is inline in `.Row`, branch targets inside it) unless it also fits.
   Verify: `verify_build` pins/twins + both sims + full battery (this step must
   be **behaviour-identical**; no visual check needed).
   ✅ **DONE 2026-10-22** — see "Step 1 landed" below.
2. **Phase 4 — VDEL pipeline.** `VDELP1` for `GRP1`/`COLUP1` written a line
   ahead + HERO's one-byte-per-line "colour + draw flag" staged at room load.
   Gate: byte-identical output, `.Line` worst path not worse, Stella SCN/seam
   oracles. Must land alone.
   ⚠️ **PREMISE REFUTED 2026-10-22** — VDEL is a cross-buffer latch, not a
   one-line delay, and HERO clears it for the cave. The affordable half landed
   (`VDELP0 = 1`, player art/colour now aligned for X < 113 px); P1 VDEL would
   be worse and the staged colour byte is 2 c short. Details + measured split
   table in `plans/hero_kernel_plan.md` § "Phase 4".
3. **Phase 6 — 16-row art** (144 B/type), in the format Phase 4 leaves behind.
   One pass over the tables; window constant and art/colour rows grow together.
4. **Phase 3 — async tint** (content-gated: nothing to fix until level 7).
   After Phase 4 it should mostly be a staging/data change; it must stage
   `M1X = $B0`.
5. **Phase 7 (optional)** — ball/M1 as real extra slots.

Why this order: space before Phase 4 (Phase 4 adds kernel code; never evict
inside a restructure), Phase 4 before the art growth (Phase 4 redefines the
colour table — growing first means writing it twice), Phase 4 before Phase 3
(explicit per-line colour ownership is what Phase 3's carrier problem is about).

## Verified-and-not-a-bug (do not "fix")

- **`BallX` in `Temp` is safe**: the VBL order is `SelectActiveObject` (its
  `StageSlot1` tail clobbers `Temp`) → `CallPad_BuildColupF` (bank2
  `StageBandTab` re-stages `BallX`) → `PositionBallM1` (reads it). If that order
  ever changes, give `BallX` its own byte.
- **The bomb's 1-of-4 frames still hide the lower-band object** on those frames
  — by design (the pin is skipped while `ObjBase == OBJ_BOMB`).
- **`M1X` (`$B0`) is deliberately never written today** — that is what removes
  the phantom dash. Phase 3's room load must stage it.

## Standing invariants added today (guarded)

- Enemy record = `type|dir` in ONE byte: mask b7 at every type compare
  (`tools/test_enemy_movement.py` asserts the mask in `UEDispatch` and
  `CheckEnemyHit`; `test_raft` case 5c asserts `$07` and `$87` both dispatch).
- A second `HMOVE` in a frame must clear the fine registers it must not
  re-apply, **before** the preceding `WSYNC` (`tools/test_slot1_hmove.py`).
- The velocity clamp must compare the low byte when `vyHi == >MAX_FALL`
  (`tools/test_jet_clamp.py`, ROM-level).
- Editor enemy `x` is a DISPLAY COLUMN (0..39): `enemy_x_px(c) = c*4 + (4 if
  c*4 < 11 else 7)`. Never read it as a pixel X.

## Commands

```bash
cd src && ./build.sh                    # builds + sim_bomb_fuse + sim_frame_budget
bash tools/freeze_test_banks.sh         # AFTER any bank-code change, BEFORE the battery
for f in ../tools/test_*.py tools/test_*.py; do \
  /home/iuri/python3/bin/python3 "$f" >/dev/null 2>&1 || echo "FAIL $f"; done
/home/iuri/python3/bin/python3 tools/rom_size_report.py --md   # ledger for the plan
```

## Stella notes from today (read `docs/stella_debug_recipe.md` first)

- **`break <addr>` is forbidden** (F6 mirrors addresses across banks) and
  `breakLabel` cannot work — the build emits no `.sym`. My mistake today.
- **The debugger screenshot already contains the ZP grid** (`00xx` RIOT panel)
  plus a `Label: ram_XX` box with the selected cell's value — read it, do not
  ask for RAM again.
- `watch $XX` printed the *address* in the value slot in this build (all three
  entries matched their own address), so do not trust it for values; use the
  grid / the `Label` box.
- The py65 harness answers semantics (carry, state machines, cycles); Stella is
  only for "what does the TIA actually draw".
