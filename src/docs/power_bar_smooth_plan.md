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

- [ ] **G1.** `src/kernel.asm`: remove `TickHi = $F4` EQU and all
      `TickHi` / `#195` / phase reloads (init, overscan tick, `.TimerReset`,
      `CheckMinerPickup`).
- [ ] **G2.** Timer init + reset + miner pickup:
      `lda #120 / sta BarLevel` + `lda #60 / sta TickCounter`.
- [ ] **G3.** Overscan tick:
      ```
      dec TickCounter
      bne .TimerDone
      lda #60 / sta TickCounter
      dec BarLevel
      beq .TimerExpired
      ```
- [ ] **G4.** `src/bank1.asm`: move `BarDelayTable` + `BallXTable` to free
      space after `SetObjectXPos_b1` (~`$F750`), **before** `.ds $FC68`.
- [ ] **G5.** Expand tables to 121 entries (B=0..120):
      - `BarDelayTable[B] = round(B * 9 / 120)` for B≥1; `[0]=0`; never 10.
      - `BallXTable[B]` monotonic, all in **4..155**; `[0]=4`;
        `[120]` ≈ right edge of body (142–155).
- [ ] **G6.** Comments: 60 f/step, 120 steps, 120 s; no TickHi.
- [ ] **G7.** Build. Verify: no `TickHi`/`#195` in bank0, tables at expected
      offset, fold-pads match, 4×4096, no new ZP conflicts.
- [ ] **G8.** **User test:** full=pure yellow; red sliver ≤~1 s; edge moves
      ~every 1 s (smooth ~5 px steps); empty + life lost at **120 s ±2**;
      no ball in grey margins. Report pass/fail.

**Commit G** after G8 pass: `Power bar fix G: 120-step 1s tick; drop TickHi`.

---

## Verify (final)

- [ ] **V1.** Full build green, fold-pads byte-identical, 4×4096.
- [ ] **V2.** No red at full, no stripes any `BarLevel`, no orange.
- [ ] **V3.** 1 s steps, 120 s life-loss, margins clean (user live).
- [ ] **V4.** Push `feature/power-bar` (after user’s other pending issues).

---

## Out of scope

- Sub-cycle orange separator (still removed).
- Ball disabled at full (optional; keep ball marker unless user objects).
- 2-byte `BarLevel` (not needed; 120 fits in one byte).
