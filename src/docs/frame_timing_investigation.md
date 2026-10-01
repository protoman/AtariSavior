# Frame Timing Status — Bug A Fix + Open Anomalies (2026-09-28)

Status of the Bug A fix (VBLANK timer expiring mid-setup → exploded frames) and
the frame-length anomalies still under investigation.

---

## 1. What is SOLID (measured, do not re-derive)

| Fact | Value | Source |
|------|-------|--------|
| Setup cost `f04d → f0cb` | **T = 3439c** (45.2 lines), deterministic in test room | phase_1/stop_1+2, re-measured 2nd pair |
| Old timer `#43` | 2752c → **always expired** during setup (687c over) | TIM64T model |
| Post-expiry mechanism | INTIM ÷1 garbage phase → first `lda INTIM` clears bit → ÷64 resume → wait = value×64c | `/tmp/opencode/M6532.cxx` |
| INTIM read = 81 | 81×64 = 5184c ≈ 68-line measured wait | model matches measurement |
| Fix applied | `kernel.asm:406` `lda #43` → **`lda #60`** (3840c, 401c headroom) | built 11:02:35, `bank0.lst:408 f04b a9 3c` ✓ |
| Frame model (post-fix) | VBLANK 50.5 + kernel 148 + HUD 51 + overscan 30 + VSYNC 3 = **282.5** | section sums |
| Observed good frame | **RIGHT = 281** ✓ matches model | user check3 first value |
| Pre-fix section lengths | VBLANK 113 (45.2+68 garbage), kernel 148 (147+1), HUD 51 (48+3) | phase 1+2 record sheet |
| Pre-fix frame values | 301, 310, 34, 224, 442-class all seen | screenshots + user |

### Stella frame-boundary mechanics (source-verified)

- RIGHT field = `tia.scanlinesLastFrame()` = `myCurrentFrameFinalLines`
  (`TiaInfoWidget.cxx:310`), set only in `notifyFrameComplete()`
  (`AbstractFrameManager.cxx:91-99`) = `myCurrentFrameTotalLines` at that instant.
- LEFT field = `tia.scanlines()` = `myCurrentFrameTotalLines` (count in current frame,
  resets to 0 at each boundary). So `Scn L|R` = current line | last frame total.
  (Full field table + tooltips + box-order proof: AGENTS.md "Scn Ln fields".)
- `notifyFrameComplete` fires only from `setState(waitForFrameStart)`
  (`FrameManager.cxx:189`), reached by 3 paths:
  1. **VSYNC falling edge** while state = `waitForVsyncEnd` (VSYNC pulse ≥ 2 lines) — normal.
  2. **waitForVsyncStart timeout**: `myVsyncLineCount > 50` while armed
     (`FrameManager.cxx:68-72`), armed = `(totalLines > 259 || first frame) && (VBLANK on || totalLines > 624)`.
  3. **waitForVsyncEnd timeout**: VSYNC stuck on > 50 lines (`:78-81`).
- Metrics: `frameSizeNTSC=262, maxLinesVsync=50, ystartNTSC=23, baseHeightNTSC=228`
  (`FrameManager.hxx:37-50`) → frame-state ends ≈ line 251, timeout would fire ≈ 310
  **iff armed**.
- `FrameLayoutDetector` (its own timeout `waitForVsync=100`) runs ONLY during boot
  `autodetectFrameLayout` (`Console.cxx:270 → :299`), not during gameplay.

### Audit: no stray VSYNC/VBLANK writes exist

- VBLANK write sites: `kernel.asm:402` (on), `:513` (off, kernel entry),
  `:718` (on, overscan). bank1: **zero**. No raw `sta $01` anywhere.
- VSYNC write sites: `kernel.asm:391/396` only (the normal 3-line pulse).
- `kernel.asm:350 sta $00,X` = boot ZP clear, X=$80..$FF — **cannot** hit $00. Suspicion cleared.

---

## 2. Current issues

### Issue 1 — check3 values `281, 442, 20` (281 ✓, 442 ✗, 20 ✗)
- 281 = predicted normal frame → fix works on normal frames.
- **442 unexplained.** 442 − 282 ≈ 160 lines ≈ a garbage ÷64 wait
  (INTIM ≈ 191 × 64c ≈ 161 lines).
- **20 unexplained.** 20-line frame cannot be a full frame (setup alone = 50.5).
  Must be a sliver = boundary fired early somewhere, VSYNC-off completed 20 lines later.
- No INTIM/f0d4 data yet to localize which timer expired.

### Issue 2 — verification check 1/2 never reported
- Check 1 (INTIM value after `step` at f0cb) and check 2 (f0d4 Scn ≈ 50) missing.
- Without them we cannot prove the new ROM is what Stella is running.

### Issue 3 — stop1.png shows `A $2b #43` at f04d (11:02:50)
- New code must load `#60` ($3C). $2B = old `#43`.
- stop2.png (f0cb) is value-identical pre/post fix (setup unchanged) → indistinguishable.
- RIGHT=224 in stop2.png also unexplained (Frame 55, Scn 45|224).
- Possible: screenshots captured from a session started before rebuild. User insists
  build is current — treat as **open contradiction**, not settled.

### Issue 4 — pre-fix `310/34` alternation not derivable from FrameManager model
- Phase 2 proof: fc68 @ Scn 261 + HUD 51 = 312; f18a hit at **Frame 12 Scn 2** →
  boundary fired at **count 310** (mid-HUD), then VSYNC-off at ≈344 → sliver 34.
- But arming model: VBLANK is OFF during HUD (off at kernel entry Scn 113, nothing
  re-enables until overscan Scn 312) → armed window = overscan only (312→342 = 31
  lines < 51) → **timeout should never fire** → model predicts constant 345-frame.
- Observed 310/34 ≠ model 345 ⇒ **one of the arming assumptions is wrong** (or a
  notify path we have not found). This same unknown may produce 442/20.
- Also: `277 + garbage-wait` alone reproduces 301 (wait 24), 310 (wait 33),
  442 (wait 165) — variable setup length → variable garbage → variable frames.
  But it cannot produce 34 or 20 (those need an early boundary).

### Issue 5 — playfield still broken
- Expected: P3.x folds left playfield in intermediate state until **P3.3**.

### Issue 6 — frame length after fix ≈ 281, target 262
- Overruns: kernel +1, HUD +3, band setup +3 (pre-fix measurements); timer
  #60 grew VBLANK section by +13.5 lines vs old design 37.
- Trim step required before shipping (see §4).

---

## 3. My guesses on what is wrong (ranked, each with decisive test)

### G1 (strong) — 442 = timer-expiry garbage wait, same family as Bug A
One of the two timers expired on that frame and the first `lda INTIM` read a
garbage value ≈191 → ÷64 resume wait ≈ 160 lines → frame ≈ 282+160 = 442.

- **Candidate A — setup `#60` (3840c) exceeded.** Headroom is only 401c; hot-rect
  rect-walks and BCF loops vary per room/frame (enemy movement changes walk length).
  Heavy frame → setup > 3840 → expiry → garbage.
  Test: breakLabel `f0d4` when 442 appears → Scn ≈ **210** proves setup expiry
  (50.5 + 160), Scn ≈ 50 proves setup fine.
- **Candidate B — overscan `#35` (2240c) exceeded.** P3.1 added +474c fold work to
  overscan; overscan work was never measured. Work > 2240 → expiry → garbage wait.
  Test: breakLabel `f18a` + next-frame `f04d` delta > 30 lines proves overscan expiry.
- Fix if A: raise timer / move LoadPFBuffer+hot-rect work to overscan (structural,
  deferred to trim step). Fix if B: raise `#35` or cut overscan work.

### G2 (medium) — 20 = sliver from an early boundary (same unknown as G3)
A boundary fired at count N, second boundary (VSYNC-off) at N+20. Needs the
unknown early-boundary mechanism of G3; alternatively a boot/pause artifact
(first frames: `myTotalFrames==0` disables arming clause).
Test: reproduce with RIGHT sampling every few seconds in one session; note the
companion frame (a 20 is usually preceded/followed by an oversized frame summing
to ~282).

### G3 (medium) — unknown notify path explains pre-fix 310/34 (and maybe 20)
Model says timeout can't arm during HUD (VBLANK off, audited write sites), yet a
boundary provably fired at 310. Candidates:
- (a) `myYStart/myHeight`/state-entry lines differ from assumption (vsize/vcenter
  adjustments) shifting the armed window earlier;
- (b) a notify path outside the three found (jitter? `missingScanlines`? a second
  `setState(waitForFrameStart)` caller);
- (c) VBLANK register state during HUD differs from write-site audit
  (unlikely — audit complete).
Test: after fix stays 281 constant, G3 is historical (pre-fix only, explain for
AGENTS.md). If 442/20 keep recurring, G3 is live → dump FrameManager state at the
unexpected boundary (`breakLabel` at a HUD address + watch Scn crossing).

### G4 (open contradiction) — session/build mismatch in verification
stop1.png `A $2b #43` proves that capture ran old code. If check3's 442/20 came
from the same old session: old frame = 277 + variable garbage wait fits 442
exactly (wait 165); 281 could not come from old code → the three values would be
from mixed sessions. User rejects this — resolve with check1/check2 only
(A = $3C at f04d, INTIM small at f0cb, f0d4 Scn ≈ 50), not by argument.

---

## 4. What needs to be fixed

1. **Prove the fix is live** — user runs checks 1-3 (below). Blocks everything else.
2. **Eliminate 442** — locate which timer expires (G1 test), then either:
   - setup: raise `#60`/move work structurally (trim step), or
   - overscan: raise `#35`/cut P3.1 fold work.
3. **Explain 20 + pre-fix 310/34** (G2/G3) — record mechanism in AGENTS.md
   Lessons Learned once proven; do not guess in code.
4. **Trim to 262 lines** — current post-fix ≈ 281. Fix kernel +1 / HUD +3 / band +3
   overruns, re-tune VBLANK timer downward after setup work is moved, re-measure.
5. **P3.3** — restore playfield visuals; then user Stella gameplay gate.
6. **Docs** — update `level_bank_plan.md` P3.0/P3.2 numbers; add AGENTS.md lessons:
   INTIM ÷64/÷1 model, Scn LEFT|RIGHT field order, register `A hex #dec` display,
   breakLabel loop-head rule (f0cb Delta=7).
7. Commit only when user asks (P3.1 + docs still uncommitted, last commit `542acc5`).

---

## 5. Remaining steps (order)

1. **User verification (BLOCKING):**
   - Check 1: breakLabel `f0cb`, `step` once, read A → expect small INTIM
     (≈ $03..$07), **not** a wrapped/garbage value; also A at `f04d` must be `$3c #60`.
   - Check 2: breakLabel `f0d4` → Scn LEFT ≈ **50** (was 113 pre-fix).
   - Check 3: `clearbreaks`, let it run, sample RIGHT 5-10× → expect constant
     ≈281; record any 442/20 with Frame number + LEFT value at sample time.
2. Diagnose anomalies per §3 tests (setup vs overscan localization breakpoints
   `f05a`/`f060`/`f066` if needed — measure, don't trust comment cycle counts).
3. Trim step → 262 lines; re-measure frame total.
4. P3.3 playfield restore → user validates in Stella.
5. AGENTS.md lessons + plan doc update.
6. (Later) E4 moth — plan P5.2; verify_build/test diff-mode simplification.

---

## 6. Open questions for the user

- Check 1/2 results (A at f0cb after step; f0d4 Scn).
- When exactly did 442 and 20 appear: same session as the 281? Frame numbers?
  Same room or after a room change?
- Was stop1.png (A $2b at f04d) taken in a Stella session started AFTER the
  11:02:35 rebuild? (Needed to close Issue 3.)

---

## 7. RESOLUTION (2026-09-28, phase_1 step3 data + source trace)

All current-build frame values are now explained by ONE mechanism family:
**timer-expiry garbage wait → pulse late → Stella timeout boundary + pulse
boundary (double boundaries) + jitter emulation.**

### Confirmed facts (source-verified)

- **Arming during overscan IS real:** `TIA.cxx:2141` →
  `setVblank(value & 0x02U)` — our `lda #2 / sta VBLANK` writes (`:402`,
  `:718`) set `myVblank = TRUE`. With `totalLines > 259`, lines **260-311
  count** whenever the CPU is in overscan (VBLANK reg on, `:718`) or still in
  the VBLANK period. → `waitForVsyncStart` timeout fires at line ≈311
  (`myVsyncLineCount > 50`) **iff the VSYNC pulse hasn't arrived yet**.
- **G3 resolved (pre-fix 310/34):** Issue-4's "armed window = 31 lines"
  arithmetic used the *garbage-frame* section layout (VBLANK 113) for a
  boundary that came from a *normal-section + overscan-garbage* frame:
  normal sections put overscan start ≈ line 252 → armed from 260 → overscan
  `#35` expiry delays the pulse past 311 → timeout boundary at 311
  (observed 310) → pulse lands `sliver` later (observed 34, and 20/129/119
  family). No unknown notify path exists; the three documented paths suffice.
- **Garbage-wait model (M6532.cxx):** expiry → `myTimer=0xFF` ÷1 → first
  `lda INTIM` returns `(0xFF - cycles_since_expiry) mod 256`, clears TimerBit
  → ÷64 resumes → wait = `value×64c`, **variable 0..16320c (0..215 lines)**
  depending on where expiry landed relative to the wait-loop entry.

### phase_1 RIGHT values, fully classified

| RIGHT | Mechanism |
|-------|-----------|
| **293** | clean `#75` frame (setup 4527c < 4800c; matches step5 F.Cycle 4755 at kernel entry + 192 + overscan) |
| **310** | timeout boundary at ≈311: **overscan `#35` expired** (work > 2240c), pulse delayed past 311, window 260-311 in overscan with myVblank on |
| **119 / 129** | pulse boundary immediately after that timeout (interval = garbage overshoot past 311 = 119/129 lines) |
| **476** | **VBLANK `#75` expired** mid-setup (variable setup > 4800c: bomb/dark/blink paths) → garbage wait pushes the kernel over lines 260-311 (VBLANK reg off → window NOT armed → no timeout) → pulse-to-pulse at 476 |

### Flicker root cause

Non-262 frames (293/310/476...) make Stella's **jitter emulation**
(`FrameManager.cxx:87-90, :191-193`) shift the render window per frame →
whole-screen oscillation, on top of the double-boundary phase slips.

### Fixes applied this session (build green, tests pass)

1. **`RoomBandColor` `$D1` → `$D2`** — `$D1` = PF1Buf[2] collided with the
   kernel's `lda PF1Buf,X` (X=2): band color (room 0 = `$00`) rendered as the
   bottom band's PF1 wall every frame (dump: `$D1=00` vs model `$ff`) →
   the "gaps in bottom band" + "collision incorrect" symptoms. `$D2` =
   PF1Buf[3], a dead fill row (kernel reads X=0..2; ClearPFColumn rows 0..2;
   bank1 has no `$D2` EQU).
2. **`LoadPFBuffer` fill cut 12 → 3 bytes/phase** — bytes 3-11 were dead
   weight (all generated models = 00 there). Saves ≈27 folds ≈ 850c →
   VBLANK headroom ≈273c → ≈1100c, so variable setup no longer blows `#75`
   (kills the 476-class); also stops the fill clobbering `$D2`.

### Still open (P3.4) — RESOLVED 2026-09-29

- **Overscan `#35` post-P3.1** → measured via `/tmp/opencode/measure_p34.py`
  (py65, INTIM model, per-frame margins): overscan work worst **2104c**
  (heavy, enemy room, P3.4 rect cache in), VBLANK work worst **1311c**.
- **Frame = 293, target 262** → timers trimmed `#75 → #23` (1472c, +161c
  headroom) and `#35 → #50` (3200c, +1096c headroom); 23+50 = 73 TIM64T
  units → 3 + 19.4 + 197.5 + 42.1 = **262**. Measured lens: all 262.09-262.30
  except rare transition frames 265.99 / 275.45 (one-shot LoadLevel/EnterRoom
  spikes; noted, not fixed).
- **263.x line cluster (≈48% of quiet frames) = bank1 HUD +1 line**, NOT the
  cave kernel. Bisect: k1=`.Row $F0F4`, k2=`jmp $FC68 $F187`, k3=`Overscan
  $F18A`; span growth = `k3−k2` only. WSYNC count constant (48) → line
  skip, not structure. PC-diff between hud51/hud52 frames: `.BarRedFull`
  (power-bar Fine∈{2,3,4} path) only. Cycle gaps: bar line-3 tail
  (`F667..F688`) = **76c → `.BarGap` WSYNC starts at c76 = full-line stall**;
  lines 1/2 enter theirs at c73 (safe). Root cause: `.R3: sty COLUPF /
  jmp .BarGap` — the `jmp` sat AFTER the red boundary write (tables
  BarDelay/BarFine/BallX untouched by the cut) and jumped to the next
  instruction. Deleted (bank1.asm); line-3 content now 73c = lines 1/2.
  Result: quiet ≥263 frames 240 → 2 (the transition spikes).
  **Rule: content after `sty COLUPF` (post-boundary) is table-independent
  and trimmable; content before it is table-coupled (regen required).**
  Also: measure tools matched `v==75`/`v==35` literals for INTIM probes —
  now order-based (1st TIM64T write of frame = VBLANK, 2nd = overscan).
- step4/step5 dump re-check after fix: `$D1` should read **`ff`** (model),
  `$D2` = band color (room 0 = `00`).
