# Power Bar Fix Plan

Four reported issues + confirmation that **120 s** is the real life-loss /
bar-empty limit (68 s was only a test value).

## Root causes (verified 2026-09-23)

1. **Three-part bar `-.----------.-`** — `PF0=$70` leaves **bit 7 OFF**
   (not bit 4). Each reflected half renders `[12 ON][4 OFF][64 ON]` →
   inner gaps at TIA ~12 and ~144 plus edge segments where margins belong.
   Comment “$70 = bit4 OFF” is wrong.
2. **Orange stripe** — `lda #$2A / sta COLUPF` after delay, before red
   (bank1.asm ~149). Costs ≥5 cycles → ~12-clock orange band.
3. **~20 s solid yellow** — `BarLevel` 16→11 all hit `cpy #11 / bcs .NoRed`
   (6 × 255 frames ≈ 25.5 s). Delay `5B−1` + overhead overruns 76 c for
   B≥11 with orange; even without orange only B≤11 fits.
4. **~70 s not 120 s** — `16 × 255 = 4080` frames = 68.0 s.
   **120 s = 7200 frames = 16 × 450.** Needs a second tick byte.

## Timing budget (after Step B, no orange)

```
after WSYNC:
  lda #$1C / sta COLUPF / lda BarLevel / tay / beq / cpy / bcs  = 16 c
  delay (table[B])                                              = D cycles
  lda #$44 / sta COLUPF                                         = 5 c
  dex / bne                                                     = 5 c
total ≤ 76  →  D ≤ 50
```

Delay table max 50 cycles → `red@ = 16 + D + 5 ≤ 71` for every B=1..16.
B=0 stays immediate red. Ball X recomputed from the same `red@` model.

## ZP / budget constraints

- Tick high byte: **`$F4`** (`TickHi`) — free in `zp_layout_skill.md` ($F3–$F7);
  `$F3` is `ScoreOn` EQU in kernel.asm (do not use $F3).
- HUD band still exactly **48** scanlines (no new WSYNC).
- Fold-pads `$FC68` / `$FC70` byte-identical after every bank1 change.
- New delay table: 17 bytes — place after `BallXTable` (post fold-pad data).

---

## Steps

### Step A — Continuous bar + real margins

- [x] **A1.** `src/bank1.asm`: `lda #$70` → `lda #$E0` for bar PF0;
      update comment (bit4=OFF = leftmost margin).
- [x] **A2.** Fix stale “$70 = bit4 OFF” notes in
      `docs/power_bar_plan.md` + AGENTS.md power-bar section (pointer only).
- [x] **A3.** Build (`rm -f bank1.lst && ./build.sh`); verify 4×4096 +
      fold-pads `$FC68/$FC70` match.
- [x] **A4.** Stella screenshot `power_bar_fix_A.png`; pixel runs must be
      `[G][Y body continuous][G]` with **no** inner gaps; visual_check PASS.
- [x] **A5.** Commit `Power bar fix A: PF0=$E0 continuous body + margins`.

### Step B — Yellow/red only (no orange)

- [x] **B1.** Delete `lda #$2A` + `sta COLUPF` before `.BarRed`.
- [x] **B2.** Threshold `cpy #11` → `cpy #12` (B=11 fits at
      `red@=5·11+20=75 ≤ 76` until Step C replaces the delay).
- [x] **B3.** Build + fold-pad check.
- [x] **B4.** Screenshot `power_bar_fix_B.png`: zero orange-classified
      pixels on bar rows; Y→R hard edge; visual_check PASS.
- [x] **B5.** Commit `Power bar fix B: remove orange COLUPF stripe`.

### Step C — Delay table (red from first drain steps) + BallXTable

- [x] **C1.** Design 17-entry `BarDelayTable` (B=0..16), each D≤50,
      monotonic; document `red@(B)=16+D(B)+5` in comment.
      Actual: A=round(B*10/16) ∈ 0..10, red@=5A+20 ≤70, total ≤75c.
- [x] **C2.** Replace `.BarDelay` loop with indexed load
      (`ldy BarLevel / lda BarDelayTable,Y`) + branch-if-zero skip;
      keep B=0 → immediate red, B≥1 always writes red.
- [x] **C3.** Recompute `BallXTable[17]` from `red@` → visible px
      (same formula as bank1 comment); keep entries in 4..155.
- [x] **C4.** Place both tables after fold-pads (data, not execution path).
- [x] **B/C shared:** Build + fold-pad + resolve-symbol check.
- [x] **C5.** Screenshot at boot (B=16): tiny red sliver at right edge
      (not full yellow). Screenshot mid-drain: red advances every level.
      → `power_bar_fix_C_boot.png`: Y492+R116, continuous, no gaps.
- [x] **C6.** visual_check PASS + manual Y/R/O pixel runs (O must be 0).
- [x] **C7.** Commit `Power bar fix C: delay table + BallXTable`.

### Step D — 120 second timer

- [x] **D1.** ZP: `TickHi = $F4` in kernel.asm + bank1 (if HUD needs it);
      grep all banks for `$F4` before use. ($F3=ScoreOn — blocked.)
- [x] **D2.** Init: `TickCounter=255`, `TickHi=1`, `BarLevel=16`.
- [x] **D3.** Overscan tick:
      ```
      dec TickCounter
      bne .TimerDone
      lda TickHi
      beq .LevelTick          ; phase 2 finished → dec BarLevel
      lda #0 / sta TickHi
      lda #195 / sta TickCounter   ; 195 + 255 = 450
      jmp .TimerDone
      .LevelTick:
      lda #1 / sta TickHi
      lda #255 / sta TickCounter
      dec BarLevel
      beq .TimerExpired
      ```
- [x] **D4.** Same reload pattern at life-reset + level-change sites
      (currently `lda #255 / sta TickCounter` ×3 after init).
- [x] **D5.** Build; confirm no new ZP conflicts (`zp_layout_skill.md`).
      Fold-pad FC70 fixed: bank1 `jmp $F107` matches bank0 Overscan.
- [x] **D6.** Stella stopwatch: first red sliver ≤ ~8 s; bar empty +
      life lost at **120 s ± 2 s**. User verified live: 120s works.
      Boot shot `power_bar_fix_D_boot.png` PASS (Y+R continuous, no orange).
- [x] **D7.** Commit `Power bar fix D: 120s two-phase tick (450 frames/level)`.

### Step E — Ball never in margin

- [x] **E1.** Clamp every `BallXTable` entry to 4..155 (after A's $E0).
      Done in C3: entries clamped 4..155.
- [x] **E2.** Build + screenshot: no ball pixel in grey margins at B=0/16.
      User verified live: no ball in margins, all working.
- [x] **E3.** Commit `Power bar fix E: clamp ball X inside bar body`.

---

## Verify (final)

- [ ] **V1.** Full build green, fold-pads byte-identical, 4×4096.
- [ ] **V2.** visual_check on fix_A..E screenshots all PASS.
- [ ] **V3.** Manual pixel audit: one continuous Y/R body, grey margins,
      no orange, red appears within first drain step, 120 s expiry.
- [ ] **V4.** Push `feature/power-bar`.

## Out of scope

- Sub-cycle orange separator (removed on purpose).
- 2-byte `BarLevel` (not needed; 16 levels × 450 f = 120 s exact).
- Hero’s exact early-shutoff ZP cycle tables (we use a simpler table).
