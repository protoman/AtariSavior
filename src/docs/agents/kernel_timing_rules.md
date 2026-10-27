# Kernel timing rules — flicker budget, title kernel, VDEL

_Frame-budget flicker rules, the title-kernel dispatch regression family, the title pad VDEL stripe._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

### Frame-budget flicker — rules (S6.4-S6.6, 2026-10-01)

Residual flicker investigation will resume later (user-led). Until then,
these rules PREVENT making it worse:

1. **The invariant is the wall-model**: `sim_frame_budget` frame lines
   263.0 ±0.15 on every frame ≥2 (Stella-agree). NEVER weaken it. The
   `OVER` meter (corrected 2026-10-25): the legacy `OVER max` figure is the
   whole `Overscan`->`StartFrame` span, i.e. the TIM64T window itself (~3220c
   on EVERY frame, idle `INTIM` poll included) — it is NOT work and says
   nothing about margin. Read the `OVER real work (poll excluded)` line
   instead (max ~1520c typical, 2145c worst steady frame; the timer is now #44 =
   2816c after the 2026-10-25 V/O split V #31 + O #44, see bugs.md #16).
   `OVER_ABSORB (2839)` only guards the window itself.
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
3. **Overscan margin at fly+laser baseline is ~670-1300c** (real work
   ~1520-2145c of 2816c, measured 2026-10-25; the old "20-220c" read the poll-inclusive
   span). The VBL is #31 = 1984c with >=107c poll slack in the worst shipped room. New
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
