# Power Bar Smooth Drain Plan

Two issues + confirmed choices:

1. **Full bar shows red + horizontal red stripes** (until first decrease).
2. **Drain too chunky** (7.5 s/step) → **1 second per step** (user pick).
3. **Full bar = pure yellow**; red appears only after first step (user OK).

**Do not build/screenshot in automation** — user validates each step and confirms before next.

---

## Root causes (verified 2026-09-23)

1. **B=16 → `BarDelayTable[16]=10` → `.TimerLoop` = 78 cycles > 76.**
   - `sta WSYNC` overruns into the next scanline; that line is never repainted
     and keeps `COLUPF=red` + PF solid → **full-width red stripes**.
   - A=10 also writes red at red@=70 (~15 px) on the “good” lines → **red sliver at full**.
   - B=15 uses A=9 → 73c ≤ 76 → stripes stop after first decrease (matches
     report + `power_bar_issue.png` y=354..367: 3 good + 3 all-red rows).

2. **16 × 450 frames = 7.5 s/step**, ~38 px jump — too coarse.

**Target:** `BarLevel` 0..120, `TickCounter` 60 frames/step → 120 × 60 = 7200 =
**120.0 s exact**. Drop `TickHi` two-phase. Full (`BarLevel=120`) = all yellow.

---

## Steps

### Step F — Full bar all-yellow + loop ≤76c

- [x] **F1.** `src/bank1.asm`: define `BAR_MAX = 16` (G raises to 120).
- [x] **F2.** Hoist full check **before** `.TimerLoop`:
      `ldy BarLevel / cpy #BAR_MAX / beq .BarYellowOnly`.
      Full → `.YLoop` (3× yellow only, ~20c). Red path unchanged structure
      (73c at A=9) — full check must NOT sit inside the line loop (that was +4c → 77+).
- [x] **F3.** `BarDelayTable` max A=**9** (last three entries `9,9,9`, no A=10).
- [x] **F4.** Build green: 4×4096, fold-pads `$FC68`/`$FC70` byte-identical,
      table has no A=10, `cpy #BAR_MAX` present. Cycle recount: red A=9 ≤73c,
      full `.YLoop` ~13c/line.
- [x] **F5.** **User test:** boot / full bar — **zero red** on bar rows, **no
      horizontal red stripes**. Report pass/fail.

**Commit F** after F5 pass: `Power bar fix F: full bar all-yellow; loop ≤76c`. [x]

---

### Step G — 1-second drain (120 steps) + drop TickHi

- [x] **G1.** `src/kernel.asm`: remove `TickHi = $F4` EQU and all
      `TickHi` / `#195` / phase reloads (init, overscan tick, `.TimerReset`,
      `CheckMinerPickup`).
- [x] **G2.** Timer init + reset + miner pickup:
      `lda #120 / sta BarLevel` + `lda #60 / sta TickCounter`.
- [x] **G3.** Overscan tick:
      ```
      dec TickCounter
      bne .TimerDone
      lda #60 / sta TickCounter
      dec BarLevel
      beq .TimerExpired
      ```
- [x] **G4.** `src/bank1.asm`: move `BarDelayTable` + `BallXTable` to free
      space after `SetObjectXPos_b1` (~`$F750`), **before** `.ds $FC68`.
- [x] **G5.** Expand tables to 121 entries (B=0..120):
      - `BarDelayTable[B] = round(B * 9 / 120)` for B≥1; `[0]=0`; never 10.
      - `BallXTable[B]` monotonic, all in **4..155**; `[0]=4`;
        `[120]` ≈ right edge of body (142–155).
- [x] **G6.** Comments: 60 f/step, 120 steps, 120 s; no TickHi.
- [x] **G7.** Build. Verify: no `TickHi`/`#195` in bank0, tables at expected
      offset, fold-pads match (FC70 jmp synced to Overscan `$F103` after
      kernel shrink), 4×4096, no new ZP conflicts.
- [ ] **G8.** **User test:** full=pure yellow; red sliver ≤~1 s; edge moves
      ~every 1 s (smooth ~5 px steps); empty + life lost at **120 s ±2**;
      no ball in grey margins. Report pass/fail.

**Commit G** after G8 pass: `Power bar fix G: 120-step 1s tick; drop TickHi`.
G8 **FAIL** (2026-09-23): first drop = big red chunk; then uneven ~5s gaps;
step size ~60px. → Step H.

---

### Step H — HERO-like granularity (fix G8 visual)

**Evidence**
- `hero_granularity.png`: one HERO step = **5px red** (Y x=242..697, R x=698..702)
  ≈ **~1 TIA clock** at that scale.
- Ours (`bar_progress_2s/7s`): **~60px** / ~15 clocks per visible step.
- `power_bar_fix_plan.md:139` admitted we skipped HERO’s early-shutoff ZP tables.

**Root causes (code + measurement)**
1. **`BarDelayTable` A=0..9 only**, `dey/bne` = **5c/step = 15 clocks** (~60px)
   when A ticks; `round(B*9/120)` makes A change only every ~6–13s.
2. **Reach short:** `red@ = 5A+20` ⇒ A=9 → pixel **~126**, body ends **~155**.
   Near-full (`B=119`, A=9) shows red **126..155 (~104px)** = G8 “big chunk”.
3. **`BallXTable` out of sync:** A=9 ball ≈ **155**, red@ ≈ **126** (ball leads ~28px).

**Target**
- Visual step ≈ HERO (~few px / ~1 clock class), even cadence.
- Red@ spans full body (pixel 4..155); ball sits **on** red start (same model).
- Thin orange boundary (H2+) once timing is precise.

**Constraints**
- HUD line ≤76c; fold-pads `$FC68`/`$FC70` byte-identical after every bank1 change.
- New ZP: `DelayCnt` (**$EE**, bank1 only, after `scbrdTmp=$ED`) — confirm
  `zp_layout_skill.md` before keep.
- No build/screenshot in automation — user validates each checkbox.

#### H1 — Reach full width + align ball (no orange yet)

- [x] **H1a.** `bank1.asm`: preload delay once (`sta DelayCnt`) before bar lines;
      unroll 3 lines + `ldx DelayCnt` so **A can reach 11** (red@ → pixel 150)
      within 76c (A=11 = **76c exact**, 2× NOP pad). Keep full-bar `.BarYellowOnly` path.
- [x] **H1b.** `BarDelayTable[121]`: `A = round(B * 11 / 120)` (0..11), `[0]=0`,
      never 12. Comment: `red@ STA @ 5A+18`, `pixel = 15A-15` (A≥1) — verified vs hand count.
- [x] **H1c.** `BallXTable[121]`: **same formula as red@** `px=15A-15` clamp 4..155
      (`[0]=4`), monotonic; no ball ahead of red (both tie to A).
- [x] **H1d.** Build: 4×4096, fold-pads match, **cycle count A=11 ≤76** (hand count;
      listing after build).
- [ ] **H1e.** **User test:** near-full first drop = **small sliver** (not ~100px);
      edge moves with ball; no stripes; full still all-yellow; 120s life.

**Commit H1** after H1e: `Power bar fix H1: full-width red@ + aligned ball`.

#### H2 — Thin orange boundary (missile0, COLUP0 independent of COLUPF)

- [ ] **H2a.** Ball/missile share `COLUPF` with PF ⇒ **invisible on body**.
      Use **missile0** (`COLUP0=$2A`, `RESPM0`/`HMM0` via `SetObjectXPos` X=2)
      at `BallX`; `ENAM0` on for bar lines only; NUSIZ0 = 1-clock width.
- [ ] **H2b.** Bar `CTRLPF` **D2=0** (no PF priority) so missile draws over PF;
      restore `$05` after bar (score path already does).
- [ ] **H2c.** Pad: extra `SetObjectXPos` WSYNC → HUD pad `ldx #9` → **#8**
      (both lives paths still 48).
- [ ] **H2d.** Build + **user test:** orange tick on boundary every step,
      follows red edge; no wide orange stripe (≤~8 clocks).

**Commit H2** after H2d: `Power bar fix H2: missile orange boundary`.

#### H3 — Cadence / step size polish (HERO mechanism decoded)

**HERO decode (2026-09-23, bank0 `$D3A4`/`$D3BF`, bank1 `$F5DC`)**
- Bar level `$AB` (0..`$51`); ball X = full-res encode of `$AB`→`$D7`
  (÷15 coarse + fine nibble) → `RESPBL`/`HMBL` → **1 clock / level**.
- PF fill tables `$DC69/$DC6B/$DC76` indexed `$AB>>3` = **coarse** (every 8
  units). Body can jump; **ball is the fine indicator**.
- Our H1e fail: `BallXTable` also went through 11-step `A` → ball+body both
  ~60px. 6502 has **no 1-cycle instruction** (min 2c) → mid-line `COLUPF`
  fine cannot beat 2c = 6 clk ≈ **24px** on first `F0→F2`; then +1c = 12px.

- [x] **H3a.** Implemented in `bank1.asm`:
      - `FineCnt=$EF`; `BarFineTable` Fine∈{0,2,3,4} (skip 1);
        delay `5*A+Fine`; drop 2×NOP pad.
      - Cycle budget: maxA[F0]=11 (75c), maxA[F2]=10 (74c),
        maxA[F3/F4]=8 (74c); all 121 pairs ≤76 (listing).
      - `BallXTable[B]`: `4+round(B*146/120)`, **step 1..2 every level**
        (HERO-class smooth ball ≤8px), aligned red@ via A/F from ball px.
      - Build green, fold-pads match.
- [ ] **H3b.** **User test FAIL** (2026-09-23): (1) intermittent red/yellow
      horizontal stripes after ~couple s near-full; (2) red edge looked
      non-monotonic (25→5→25→30→10%).
- [x] **H3b-1.** Stripe root causes (both fixed):
      (a) line-2 `beq .R2` page-cross F5→F6 (`f5f8`/`f5fc`→`f60c`);
      (b) first fix used executed `jmp`+pad → setup **78c >76** (overrun).
      Final: never-executed `.ds 25` after YellowOnly `jmp` (branch skips it;
      +6 over first `.ds 19` attempt which still left 2 XC), setup ≤76c,
      **0 page-crosses** in bar region (verified in listing).
- [x] **H3b-2.** Non-monotonic (standing still, no miner): body tables are
      monotonic; only `sta BarLevel=120` are TimerExpired/CheckMinerPickup.
      Visual cause: `CTRLPF` ball size was `BarLevel&3` → width 1/2/4/8
      **oscillated every step** (edge appeared to jump both ways). Fixed:
      constant ball size — but first attempt used `lda #$00` (**wrong**: D0=0
      no reflect → right half REPEATS, center notch; D2=0 no priority).
      Correct = `lda #$05` (reflect + priority + 1-clock ball).
- [x] **H3b-3.** **Retest FAIL #2** (2026-09-23): stripes at updates 1/2/6;
      red edge non-monotonic feel (stuck then 9px jump); ball≠red@.
      Roots decoded from HERO + cycle audit:
      (a) content ≥74c → `STA WSYNC` starts too late (needs ≤73 so 3c fits
          in 76) → line overrun = stripes at A=11/F=0 (75c) and A=10/F=2 (74c);
      (b) only 36–37 safe `(A,F)` pairs for 120 levels, Fine table not even
          → sticks of 4–8 levels then 9–15px jumps;
      (c) `BallXTable` linear ≠ red@ → ball/body desync.
- [x] **H3c.** Build-verified (2026-09-23), **user retest #1 FAIL**:
      stripes gone; still big chunks + back-and-forth.
- [x] **H3c-1.** Root cause: slim (F=0) vs full (F≠0) paths have different
      cycle counts to red write → `BallX` (formula) ≠ body red (actual cycles)
      → ball and edge disagree, appear to reverse. Also Fine used {0,2,3,4}
      only → 9px gaps at path switches.
- [x] **H3c-2.** Fix: ball = actual pixel `3*cycles-69` from each path;
      Fine ∈ {0,1,2,3,4} (F=1 = slim + 2c nop/line fills 3px gaps);
      tables regenerated from path cycle counts. Build: fold MATCH, 0 XCs,
      ball==body 0 mismatches, mono, stick≤4, jumps **3/6 only**, content≤71.
      **User retest #2:** no stripes; monotonic red (no back-and-forth);
      step ≤6px every ≤4s; ball on edge; full = all-yellow. Report pass/fail.

**Commit H3** after H3b (if any code change).

**Commit G+H** when G8 replaced by H1e pass: combined message OK if needed.

---

## Verify (final)

- [ ] **V1.** Full build green, fold-pads byte-identical, 4×4096.
- [ ] **V2.** No red at full, no stripes any `BarLevel`; orange ≤ thin (H2+).
- [ ] **V3.** Granularity ≈ HERO (user vs `hero_granularity.png`), 120 s life,
      margins clean.
- [ ] **V4.** Push `feature/power-bar` (after user’s other pending issues).

---

## Out of scope

- 2-byte `BarLevel` (not needed; 120 fits in one byte).
- Ball disabled at full (optional; keep unless user objects).
- Exact HERO early-shutoff ZP byte values (we match **behavior**: reach +
  1-clock-class steps + aligned marker — not a byte copy of `$D0,$C8,..`).
