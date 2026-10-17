# Deep refactor v4 — verified plan (2026-10-16)

Supersedes `plans/bank0_space_plan.md`, `plans/architecture_plan_v3.md`, and the
"bank0 is 100% full / freeing space needs a 4-bank pin shift" premise in
`docs/bank_layout.md`. **Those were built on a false assumption; see §0.**

> **Rule for this document:** every claim is tagged **[VERIFIED]** (measured from
> `bank*.lst` / proven with a build probe) or **[ASSUMED]** (must be verified
> before it is relied on). No step ships without its verification.

---

## 0. The wrong premise (what made the old plans fail)

Old plans said: *"Removing content before a `.ds` pin frees NOTHING (the fill
grows); freeing space requires shifting the downstream pins across 4 banks."*

**Half wrong.** A `.ds $X` pin does two separate things:
1. it fixes the **address of the next content** at `$X` (twins stay aligned), and
2. it **fills the gap** from the current PC to `$X`.

Removing upstream content makes the **fill grow** — and that fill is **usable
code/data space in the same bank**. So removal *does* free space; it just does
not move the tracked "pre-pad headroom" number. [VERIFIED]

The build's `WARN: pre-pad headroom only N bytes (ends $X, limit $FC68)` measures
**only one gap** — the one right before `org $FC68`. It does **not** measure the
internal `.ds` fills. "1 byte headroom" was read as "bank0 full"; bank0 was not.

### Proof [VERIFIED 2026-10-16]
bank0 has a **225-byte contiguous free run at `$F7FC–$F8DC`** (content ends
`$F7FB`; the `$F8DD` sprite pin is at `$F8DD`). Probe: inserted
`.ds $F7FC + 200 - *, 0` (reserved 200B) → `PlayerSpriteA` stayed `$F8DD`,
`./build.sh` green. Space is directly usable; **no pin shift required.**

---

## 1. User requirements (recorded — the target layout)

1. **Deep refactor freeing LOTS of space** for many new features (no matter what).
2. **Main game kernel stays in bank0.**
3. **HUD and other kernels → bank1.**
4. **Smaller kernels → start of bank2.**
5. **Remaining bank2 + bank3 → stages/rooms data.**
6. **Try to free ZP.**
7. **Compact anything that can be compacted.**
8. **Keep a diagram/table of where every kernel / data-table lives (which bank).**
9. **Every plan step must be feasibility-checked before it is committed** — no
   more plans that fail.

---

## 2. Verified free space right now (measured from `bank*.lst`)

Numbers below are `.ds` fill slacks (`target − fill_start`) plus `org` gaps.
`[V]` = verified by a build probe; `[m]` = measured from the listing.

| Bank | Free region | Size | How it's freed / used | Status |
|---|---|---|---|---|
| bank0 | `$F7FC–$F8DC` | **225B** | before the `$F8DD` sprite pin — contiguous | `[V]` probe: 200B reserved, green |
| bank0 | `$FC4F–$FC67` (E4 gap) | 25B | after `MothExitPad`, before `org $FC68` | `[V]` (Step 0) |
| bank0 | scattered fills | ~95B | before `$F9B8`(3) `$FB00`(3) `$FBD0`(40) `$FBE0`(4) `$FBE8`(2) `$FBF8`(10) `$FC49`(5) `$FDE1`(3) `$FE00`(1) `$FEED`(3) `$FFE0`(6) `$FFEC`(14) | `[m]` |
| bank1 | `$F042–$F53F` | **~1278B** | before `org $F540` (MenuMain) | `[m]` (org gap) |
| bank1 | `$FDE3–$FEE6` | 260B | before the `$FEE7` CallPad pin | `[m]` |
| bank1 | `$FF0F–$FFF9` | 235B | after bank1 `fineAdjust`/pads | `[m]` |
| bank1 | `$F8F4–$F936` | 67B | before `$F937` (`StripBlastCheck`) | `[m]` |
| bank1 | `$FCC7–$FCFF` | 57B | after the CallPad block | `[m]` |
| bank2 | largest `$FA*-$FB*` fills | scattered | level-data window + code pins; fragmented | `[m]` |
| bank3 | `$F0A3–$F7FF` | **~1885B** | before `org $F800` | `[m]` |
| bank3 | `$FE..-$FF..` + others | ~600B | scattered | `[m]` |

**Takeaway:** there is already **~3400B** of free ROM (bank0 225B+, bank1 ~1270B+,
bank3 ~1885B+). The old plans were chasing a phantom; the immediate blocker is
**logistics (where each thing lives + cross-bank coupling)**, not total bytes.

---

## 3. Verified bank/twin mechanics (the constraints any move must respect)

- **[VERIFIED] Twin pins.** Cross-bank `sta $1FFx` + `jmp/rts` tramps must be
  **byte-identical at the same address** in both banks. Twin sets (address: banks)
  from the listing:
  - `$F8DD` (0,2) sprite art; `$F9B8` (0,2) overlay tramp; `$F9AC` (1,2);
  - `$FBD0 $FBD6 $FBE0 $FBE8` (0,2) fold tramps; `$FBEE` (2,3);
  - `$FBF8` (0,1,2) ReturnPad; `$FC68 $FC70` (0,1) fold pads;
  - `$FDE1` (0,2) frame tramp; `$FE00` (0,2) ObjColorTab/PHMOverlay slot;
  - `$FE90 $FE96 $FEE7 $FEF0 $FEF6 $FFE6` tramp twins; `$FF00` fineAdjust (0,1,2).
- **[VERIFIED] Bank1's HUD packs to `$FBE6`** (18B slack to the `$FBF8` twin).
  This is why the `$FBF8` ReturnPad/CallPad block **cannot** shift down — a −29
  probe failed with `bank1.asm(1308): Origin Reverse-indexed`. So the *consolidate
  via pin-shift* route is blocked until bank1's pre-`$FBF8` HUD shrinks.
- **[VERIFIED] bank0 cannot read bank1/2/3 data by `abs,X/Y`** — a moved table
  needs its reader moved (or a fold). The kernel `.Line` reads `ObjSprites,X`,
  `ObjColorTab,X`, `PlayerColTable,Y`, `BeamMask,Y` in the hot loop → those must
  stay in bank0 (or be staged into ZP).
- **[VERIFIED] bank2's `BombEnemyBlastBody` ends `$FDD2`** → the shared tramp
  mirror can't go below `$FDD3`; PostPad content is effectively immovable.
- **[VERIFIED] `.ds` adding rule:** adding content into an existing fill is safe
  (fill shrinks) as long as it ends at/before the pin target; going past the
  target → `Origin Reverse-indexed`.

---

## 4. Target layout (diagram)

```
bank0  MAIN GAME CODE + cave kernel
       $F000..$F7FB  gameplay (overscan/VBL/kernel)         <- existing
       $F7FC..$F8DC  ***225B FREE — new gameplay code here***  [V]
       $F8DD         PlayerSpriteA/B + PlayerWalkA/B + PlayerColTable (twin)
       $F9B8         overlay tramp (twin)
       $F9FB..$FBCF  title kernel + helpers/fonts (COLD)   <- MOVE to bank1 (goal 3)
       $FBD0..$FC67  fold tramps + CallPads + MothExitPad (twin-locked)
       $FC68..$FEFE  post-pad handlers   (some -> bank1)
       $FF00..$FFFF  fineAdjust + SetObjectXPos + vectors (pinned)
bank1  HUD + OTHER KERNELS
       $F042..$F53F  ***~1278B FREE — new HUD/kernels here***  [m]
       $F540..$FBE6  MenuMain HUD (packed) + helper pads (twin-locked)
       $FDE3..$FEE6  ***260B FREE***
       title kernel target (needs bank1 SOXP + fold bodies)  <- TARGET
bank2  SMALL KERNELS (start) + a bit of code
       $F010..$F0A2  EnterRoomB2 + MothRoutine              <- existing
       $F0A3? gap    free-ish; small-kernel target
       $F100..$F9D8  title bands/fonts + level window
       $F9D9..$FBD5  ROOM/STAGE DATA window (move to bank3 to shrink)  <- data goal
bank3  STAGES / ROOMS DATA (data-only + mandatory stub)
       $F000..$F0A2  power-up stub + crunch bodies  <- crunch bodies -> bank1
       $F0A3..$F7FF  ***~1885B FREE — room/stage data target***  [m]
```

---

## 5. Plan — each step feasibility-checked before commit

Legend: `[V]` verified now · `[?]` must be verified by a probe/build before doing it.

**Phase 0 — foundation (do first; unblocks everything)**
- **0.1 [DONE] Prove fills are usable.** 225B @ `$F7FC` confirmed usable. `[V]`
- **0.2 Fix the tooling.** `verify_build.check_rom` must report **all** free runs
  per bank, not just the `$FC68` gap, so "headroom" stops lying. `[?]`
- **0.3 Record the live bank map** (auto-generated from `bank*.lst` into
  `docs/bank_layout.md`) so the table can never go stale. `[?]`

**Phase 1 — free ZP (independent, low risk; goal 6)**
- **1.1 Derive `RoomPF1*/RoomPF2*` from `RoomPF0*`** (`+3`/`+6`): **−4B**
  (`$9B-$9E`). Cost: `lda/+adc #3` at the few staging reads. `[m]` (already
  analysed in `architecture_plan_v3.md` §Phase3 item 1).
- **1.2 Free `$F6/$F7`**: inline one leaf out of the deep call path so gameplay SP
  bottoms at `$F8`; `$F6/$F7` become safe persistent bytes. `[?]` (must re-run
  `sim_bomb_fuse` stack guard).
- **1.3 Bracket `$E0/$E1` scratch** (documented spare; staged-only). `[?]`
- Result: **~4B guaranteed + up to ~4B**; enough for physics/raft state.

**Phase 2 — use the space that already exists (goal 1,2,4)**
- **2.1 bank0 new gameplay code → `$F7FC` fill (225B).** Proven. `[V]`
- **2.2 bank1 new HUD/kernel code → `$F042` (1278B).** `[m]`
- **2.3 bank3 stage/room data → `$F0A3` (1885B).** `[m]`
- No pin shift needed for any of this.

**Phase 3 — kernel relocation (goal 3; the "deep" part)**
- **3.1 Title kernel sub-system → bank1.** Blockers (from old plan §Step-1,
  still true): kernel `jsr`s `SetObjectXPos` (bank1 has `SetObjectXPos_b1` +
  page-aligned `fineAdjustBegin_b1` — reuse, `[m]`); kernel calls
  `TitlePlayerFold`/`FooterFold` whose bank2 bodies **must move to bank1** (they
  `jmp ReturnPad` = bank0; a bank1 caller would return to bank0 → broken). So the
  move = kernel + `TitleFont` + `FooterBand`/`TitlePlayerBand`/`TitleBandPrep`+
  fonts/sprites to bank1. Each sub-step build-verified. `[?]` (verify by moving
  the *smallest* piece first — `TitleSelect` — as a canary, then the kernel).
- **3.2 Small kernels → start of bank2** (e.g. game-over band later). `[?]`

**Phase 4 — consolidation (optional; only if contiguous bank0 space is needed)**
- **4.1 Shrink bank1's pre-`$FBF8` HUD** by ≥26B (move a HUD helper to
  `$FDE3`/`$FCC7` free space) → then the `$FBF8` block can shift down and bank0's
  scattered fills merge. `[?]`
- **4.2 Relocate bank2's level window (`$F9D9-$FBA6`) → bank3** → bank2 fold pins
  shift up → bank0 fills grow. `[?]` (cross-bank level reads required — size it
  first).

**Phase 5 — keep the map current (goal 8)**
- **5.1** `docs/bank_layout.md` regenerated from the listings each build (0.3).

---

## 6. What is explicitly NOT claimed

- No claim that the `$FB00..$FC49` pin shift works — it is **blocked by bank1**
  until Phase 4.1. [VERIFIED failure]
- No claim of "hundreds of bytes by moving post-pad routines" — post-pad is
  twin-walled by bank2. [VERIFIED]
- Numbers tagged `[m]` are listing-derived and must be confirmed with a probe
  before that space is used for anything irreversible.

---

## 7. Progress log

| Step | Commit | Result |
|---|---|---|
| Corrected model + verified plan | `6ae2786` | docs |
| **D1.1** reclaim dead ZP `RoomPF1/2` | `<D1.1>` | **+4 ZP** (`$9B-$9E` = `ZpSpare0-3`); addresses stable |
| **Phase 3.1 canary** `TitleSelect` -> bank1 | `91c5d8a` | **+29B bank0** (`.ds $FBD0` fill 40->69B) |
| **Phase 3** title kernel+font+bands+fonts -> bank1 | `81e4f6b` | **+309B bank0** (`.ds $FB00` fill 3->261B; `.ds $FBD0` 69->117B) |

### Bank0 free space now (verified from `bank0.lst`)

| Region | Size | Notes |
|---|---|---|
| `$F7FC-$F8DC` | **225B** | before the `$F8DD` sprite pin |
| `$F9FB-$FAFF` | **261B** | where the title kernel used to be (before `$FB00` pin) |
| `$FB5B-$FBCF` | **117B** | title font/helpers region (before `$FBD0` pin) |
| `$FC61-$FC67` | 7B | E4 gap remainder (CallPads grew) |
| **Total** | **~610B** | contiguous-ish chunks usable by new gameplay code |

### Bank1 free space now
- `$F357-$F53F` (~489B, after the moved title block, before `MenuMain` `org $F540`)
- `$FDE3-$FEE6` (260B), `$FCC7-$FCFF` (57B), `$FF0F-$FFF9` (235B).

### Remaining (not done; each needs a fresh verification)
- **D4 dead-data removal is BLOCKED**: bank2's now-dead title bodies
  (`FooterBand`/`TitlePlayerBand`/`TitleBandPrep`/fonts) are referenced by
  bank2's `$FBE0`/`$FBE8` fold twins and their `.ds` pins anchor that twin block
  — removing them needs the bank1/bank2 pin surgery first.
- **D2 table compaction**: `BarDelayTable`/`BarFineTable` (242B) are
  period-8 → ~30B, but the reader needs `(B-1)>>3` (~+10c) and the bar path is
  budget-tight; verify against `sim_frame_budget` before attempting.
- **D3.1 level data -> bank3** (`$F9D9-$FBA6` ~461B): needs reader rewiring
  (`EnterRoomB2` direct reads → fold). Size it before attempting.
- **D1.2/D1.3** more ZP (`$F6/$F7`, `$E0/$E1`): needs a stack-depth inline.

### Test/sim updates required by Phase 3 (done)
- `sim_frame_budget.PC_TITLE` -> bank0 `CallPad_TitleKernel` (sim is bank-aware).
- `verify_build.check_callpads` handles `sta $1FF6` pads (bank1→bank0 exit).
- `src/tools/test_title_demo.py` reads the title code from bank1 now.
