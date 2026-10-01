# Frame Timing Investigation — Claude Analysis (2026-09-28)

**Status:** In progress. Updated frequently as analysis runs.

---

## 0. What I am looking at

Starting point: `frame_timing_investigation.md` describes:
- Bug A (VBLANK timer #43 expiring during setup) → fixed with `lda #60`.
- Post-fix frame ≈ 281 lines, target 262.
- Anomalous frames: 442, 20.
- Three open issues: overscan timer may also expire (G1B), unknown early-boundary (G2/G3), HUD+kernel overruns.

All addresses confirmed from `bank0.lst`:
- `$f04b` `a9 3c` = `lda #60; sta TIM64T` (VBLANK timer) ← fix is live
- `$f0cb` = `.WaitVBLANK`
- `$f0d4` = kernel entry (VBLANK off)
- `$f18a` = `Overscan`
- `$f18e` `a9 23` = `lda #35; sta TIM64T` (overscan timer)
- `$f2fb` = `.WaitOverscan`

---

## 1. Cycle accounting (static, no Stella needed)

### VBLANK section (f04b → f0d4)

Setup cost measured = **3439c** (from investigation doc, deterministic on test room).

Timer `#60` = 3840c. Remaining after setup = 3840 - 3439 = **401c** headroom.
401c ÷ 64 (TIM64T units) → INTIM ≈ 6 at wait entry.

VBLANK section total cycles: ~3839c (timer) + ~6c (VBLANK off) ≈ **3845c**.
In scanlines: 3845 ÷ 76 ≈ **50.6 lines** — matches reported "50.5".

Target VBLANK: 37 lines = 37 × 76 = 2812c.
Setup (3439c) **already exceeds** 2812c by **627c**. Cannot reach 37-line VBLANK without
removing work. The `#60` timer is not the cause of the overrun — it just reveals
that setup has grown past the 37-line budget.

### Cave kernel (f0d4 → jmp $FC68)

```
Row 0: 1 setup sta WSYNC + 48 body WSYNCs = 49 lines
Row 1: 1 setup sta WSYNC + 48 body WSYNCs = 49 lines
Row 2: 1 setup sta WSYNC + 36 body WSYNCs = 37 lines
WaterRow: 1 setup sta WSYNC + 11 body WSYNCs = 12 lines
Total: 49 + 49 + 37 + 12 = 147 lines
```

Target: CAVE_LINES = 144. **Kernel = 144 + 3 = +3 lines** (3 `.Row` setup WSYNCs).

The 3 extra lines come from the 3 per-row `.Row` setup scanlines. These are structural
and cannot be eliminated without changing the kernel layout.

### HUD (bank1 MenuMain)

Planned budget (from bank1 comments):

| Section | WSYNCs |
|---------|--------|
| Top gap (ldx #4 loop) | 4 |
| Ball SetObjectXPos_b1 | 1 |
| HMOVE line | 1 |
| Timer bar (3 bar lines) | 3 |
| Bar gap | 1 |
| Lives SetObjectXPos_b1 | 1 |
| Lives HMOVE | 1 |
| Lives render (ldy #5 loop) | 5 |
| Lives gap | 1 |
| Bombs SetObjectXPos_b1 ×2 | 2 |
| Bombs HMOVE | 1 |
| Bombs render (ldy #5 loop) | 5 |
| Bombs gap (3 WSYNCs) | 3 |
| Score SetObjectXPos_b1 ×2 | 2 |
| Score HMOVE | 1 |
| Score render (ldy #7 = 7 iters) | 7 |
| Pad (ldx #9 loop) | 9 |
| **Total** | **48** |

Planned total: **48**. But investigation says measured = **51** (48+3).

**Source of 3 extra HUD lines:** Unknown from static analysis alone. Candidates:
- (a) Score render loop: `ldy #7; dec scbrdCnt; bne .ScoreLoop` — "ldy #7" then dec/bne
  = 7 iterations if it counts 7→1, or 8 if the loop body runs before the first dec.
  Looking at code: `ldy #7; sty scbrdCnt; .ScoreLoop: ... dec scbrdCnt; bne .ScoreLoop`.
  scbrdCnt starts 7, dec to 6,5,4,3,2,1,0 → 7 iterations (7 WSYNCs). Planned count
  says "7 ScoreLoop" = correct (not 8). Not the cause.
- (b) The `.NoLives` branch pads +2 WSYNC extra. If PlayerLives=0 the blank path adds
  2 extra pads AND the `.LivesDone` has a gap WSYNC = total lives section becomes 2+1=3?
  Code: `.NoLives: ldy #5 loop (5 WSYNC) + 2 extra WSYNC (sta WSYNC ×2) = 7`. Lives
  path has: 1 (SetObj) + 1 (HMOVE) + 5 (loop) + 1 (gap) = 8. NoLives path: 5+2+1? That
  would be 8 too. Comment says "+2 WSYNC so both paths total 48" — intended equal.
- (c) Measurement might include cave kernel +3 miscounted as HUD. Post-VBLANK lines from
  kernel setup code before first WSYNC could shift scanline boundary.
- (d) Bank-switch overhead: `jmp $FC68` switches to bank1; that costs 0 WSYNCs. Bank1
  returns via `jmp $FC70` to bank0 fold-pad which jumps to `Overscan`. No extra WSYNC.

**Most likely explanation:** the "HUD 51" measurement captured the 3 `.Row` setup lines in
the kernel pass that precedes the HUD. The kernel total is 147 lines (not 144); those extra 3
were attributed to the kernel as "+1" and HUD as "+3" — but they are really all in the kernel.
The 51-line HUD report may be from measurement timing (breakLabel at jmp $FC68 vs actual HUD
start = the .AfterRows code that restores atoms, which runs as part of kernel visible time).

### Overscan (f18a → jmp StartFrame)

TIM64T = #35 → 35 × 64 = 2240c budget.

**P3.1 added to overscan (UpdateEnemies fold calls):**
- 15 fold reads × ~26c each = 390c
- 6 stage sites × ~14c each = 84c  
- Total addition: ~474c

**Pre-P3.1 overscan baseline:** unknown (never measured, per investigation doc).
Pre-P3.1 overscan included: RefreshEnemyY, joystick, bomb edge-detect, LaserInput,
vertical physics (StepDown/StepUp loops × max vy), horizontal movement + collision,
enemy dispatch (was returning immediately for enemy types without movement code),
CheckEnemyHit, BombTick, audio, TickCounter.

Rough estimate of pre-P3.1 minimum (no movement, straight path):
- RefreshEnemyY (~50c), joystick (~20c), bomb check (~30c), LaserInput (~80c),
  physics (~50c idle), H/V movement no-op (~40c), UpdateEnemies no-op (~50c),
  CheckMinerPickup (~30c), CheckEnemyHit (~50c), BombTick (~30c), audio (~40c),
  TickCounter (~20c) ≈ **~490c minimum**.

With P3.1 addition: 490 + 474 = ~964c minimum. Still well under 2240c.

**HOWEVER**: heavy-frame worst case (full enemy movement + collision walks + bomb ticking):
- StepDown loop: up to ~8 steps × ~40c = 320c per pixel of fall; multiple pixels = 640-1000c
- CheckEnemyHit collision: ~80c × enemy count
- UpdateEnemies: snake + 2 enemy folds = ~300c
- P3.1 folds: +474c

Heavy worst case: 490 + 474 + 800 (movement) + 200 (hit checks) ≈ **1964c**.
Still ~276c under 2240c.

**CONCLUSION: G1B (overscan expiry) is UNLIKELY on most frames** given this estimate.
The 474c addition still leaves ~276c headroom in heavy frames. The 442 anomaly is more
likely G1A (setup expiry) triggered on a specific heavy-frame VBLANK.

---

## 2. Most likely source of 442-frame anomaly

**G1A: VBLANK setup timer #60 (3840c) exceeded on a heavy frame.**

Headroom = 401c. Heavy-frame VBLANK additions:
- P3.1 fold calls that moved to VBLANK: 1 band-color fold = ~26c (small).
- LoadPFBuffer: fixed cost (12 × 3 reads = 36 loads × 6c each = 216c; this was
  already there pre-P3.1; no change in VBLANK budget from P3.1).
- SelectActiveObject: calls FoldIndirect (2 folds). That's 2×26c = 52c ADDED by P3.1
  per frame (if enemy slot active).
- UpdateEnemies fold calls run in OVERSCAN, not VBLANK. Only the band-color fold and
  SelectActiveObject folds run in VBLANK.

Wait — let me recheck. The P3.1 changes:
- Stage sites: `LoadEnemyRam` top, `UpdateEnemies/UE_Start`, `DeriveEnemyY`, 
  `SelectActiveObject`, `CEH_HasEnemies`, `LaserHitTest`.

`SelectActiveObject` runs in VBLANK (line 424 in kernel.asm). It contains fold calls.
The plan doc says "2 reads folded in SO" = 2 × 26c = **52c added to VBLANK**.
Plus 1 stage site (~14c).

Total VBLANK P3.1 addition: 1 band-color fold (26c) + 2 SO folds (52c) + ~3 stages (42c)
≈ **~120c** added to VBLANK since pre-P3.1.

Previous setup cost was measured at 3439c. Pre-P3.1 setup = 3439 - 120 = ~3319c.
Pre-P3.1 headroom with #60 (3840c): 3840 - 3319 = **521c** → still plenty.

With P3.1: 3439c, headroom 401c. This should not overflow #60 unless variation is >401c.

**Variation sources in VBLANK setup:**
- `SetObjectXPos`: fixed cost.
- `SelectActiveObject`: fold cost varies by enemy type/active status (~52c max delta).
- `LoadPFBuffer`: fixed (loop always 12 iterations).
- `ApplyBombWalls`: varies by bomb state (~20-100c).
- `BuildColupF`: fixed cost.
- BG color logic: ~40c.

Max variation ≈ 100-150c. Well under 401c headroom. **G1A should not trigger with #60.**

---

## 3. Revised assessment: 442 is probably from PRE-FIX session

The investigation doc §4 (G4): "The three values 281/442/20 could be from mixed sessions."
Given:
- 442 = 282 + 160 = post-fix frame + garbage ÷64 wait ≈ 160 lines.
- With OLD timer #43 (2752c) and 3319c setup (pre-P3.1), overflow = 3319 - 2752 = 567c.
  INTIM after ÷1 phase: approximately (567 ÷ 64) = ~8... but actually the ÷1 phase works
  differently. The INTIM value after overflow is the count of ÷1 cycles remaining from
  the rollover. This is documented in the investigation as INTIM ≈ 191 × 64c ≈ 161 lines.
- 442 is consistent with OLD #43 + variable overflow on a heavy frame.

If the 281/442/20 were from different sessions (one post-fix, one pre-fix), then:
- 281: post-fix, normal frame ✓
- 442: pre-fix, heavy frame (setup overflow) ✓  
- 20: pre-fix, sliver from early boundary ✓

**If this is correct, the 442 anomaly is already fixed by the #60 change.**
The user needs to verify this by running post-fix only and sampling RIGHT many times.

---

## 4. Root cause of 281-line frame (structural)

The frame is 281 instead of 262. **19 extra lines.**

| Section | Design | Actual | Delta |
|---------|--------|--------|-------|
| VSYNC | 3 | 3 | 0 |
| VBLANK | 37 | 50.5 | **+13.5** |
| Cave kernel | 144 | 147 | **+3** |
| HUD | 48 | 51* | **+3*** |
| Overscan | 30 | 30 | 0 |
| **Total** | **262** | **281.5** | **+19.5** |

*HUD 51 may be mismeasured — see §1.

### Why VBLANK is 50.5 lines (not 37)

Setup = 3439c > 2812c (37 lines). Setup grew beyond budget through successive feature
additions (P3.1 fold calls). The timer `#60` just lets it finish gracefully.

**Cannot fix VBLANK overrun by tuning the timer.** Lowering the timer below 3439c
reproduces Bug A. The only fix is to move VBLANK work into overscan.

### Why cave kernel is 147 lines (not 144)

3 `.Row` setup `sta WSYNC` calls (one per tile row pass). These are structural —
each pass requires ONE setup scanline to sync and set PF registers.

**Fix options:**
- Remove 3 setup WSYNCs: impossible while PF registers need setup and WSYNC sync.
- Absorb 3 lines into VBLANK: would need VBLANK to end on a scanline boundary
  cleanly then fall through to .Row without WSYNC. Complex timing.
- Accept 3 extra kernel lines and compensate elsewhere.

### Summary of fixes needed

The frame overrun is structural:
1. VBLANK has grown too large (setup > 37-line budget by 627c).
2. Kernel has 3 unavoidable setup WSYNCs.

To reach 262 lines requires either:
- Move ~627c of VBLANK work to overscan (frees 8.2 VBLANK lines), **AND**
- Fix overscan timer to account for added overscan work, **AND**  
- Fix the VBLANK timer back to ~#44 (fitting new shorter VBLANK work), **AND**
- Accept kernel +3 and compress HUD from 51→48 (or 48→45).

**Or simply accept 281 and ship — many commercial 2600 games run non-262-line frames.**
Stella and real hardware both cope fine. The "target 262" is a design ideal.

---

## 5. Immediate actionable fix: overscan timer guard

Even if 442 is from a pre-fix session, it's prudent to verify overscan doesn't expire.

**Measurement from the investigation §5 step 1:**
- breakLabel `$f2fb` (.WaitOverscan), run, read INTIM at breakpoint.
- If INTIM > 0, overscan is fine.
- If INTIM = 0 immediately, overscan overran → raise #35.

Current estimate: overscan does NOT overflow (heavy frame ≈ 1964c < 2240c).
**No immediate code change needed for overscan.**

---

## 6. What DOES need fixing now

### 6.1 Playfield broken (Issue 5, P3.3 not done)

`LoadPFBuffer` uses `lda (RoomPF0Lo),Y` = direct reads from bank0 addresses.
The level data moved to bank2 in P2.4, so these reads return stale bank0 bytes.
The pointers `RoomPF0Lo/Hi` etc. point into bank2 data range, but bank0 is selected
when the VBLANK reads them → garbage playfield.

**Fix: implement P3.3** — route `LoadPFBuffer` 36 reads through `FoldIndirect`.

### 6.2 Frame length 281 vs 262 (Issues 6 / §4)

Not critical for gameplay — Stella handles it. BUT the overscan timer `#35` (2240c)
was designed for 30 scanlines. If VBLANK expands to ~50 scanlines without adjusting
overscan, the frame pacing is off (game runs at ~60Hz but with ~281-line frames = 
slightly slower than NTSC 262-line ideal, ~54Hz effective).

**Acceptable short-term:** leave at 281 until P3.3 is stable.
**Long-term:** move work from VBLANK to overscan, retune timers to hit 262.

### 6.3 The 442/20 anomaly

Per §3, most likely from a pre-fix session. If user confirms post-fix-only runs
show consistent 281, these anomalies are resolved.

---

## 7. Plan to verify and fix (ordered)

1. **Verify fix is live (blocks everything):**
   - `stella -debug savior.bin` → breakLabel `f04b` → run → read A = expect `$3c` (#60)
   - breakLabel `f0cb` → run → `step` once → read INTIM = expect small (3-7), not 191.
   - `clearbreaks` → run 60+ seconds → sample RIGHT repeatedly → expect ~281 constant.

2. **If 442 still appears post-fix:**
   - breakLabel `f0d4` when 442-frame occurs → read Scn.
   - Scn ≈ 50 → VBLANK OK (overscan cause). Scn ≈ 210 → VBLANK overrun.
   - Fix accordingly (raise that section's timer).

3. **Implement P3.3 (restore playfield):**
   - Follow `level_bank_plan.md` P3.3 to route `LoadPFBuffer` reads through FoldIndirect.
   - Verify visually in Stella (walls correct = data path proof).

4. **Trim frame to 262 (deferred):**
   - Move LoadPFBuffer from VBLANK into overscan (single-slot read optimization).
   - Retune VBLANK timer (#60 → #44-ish after work moves out).
   - Retune overscan timer (#35 → #50-ish after work moves in).
   - Verify total frame = 262 lines.

---

## 8. Specific fix: P3.3 LoadPFBuffer folding (THE blocking issue)

The playfield is visually broken. This is the most important fix.

### Current code (kernel.asm LoadPFBuffer ~line 1059)

```asm
LoadPFBuffer:
    ldy #0
.LPB_Loop:
    lda (RoomPF0Lo),Y    ; reads bank0 (stale!) — data is in bank2
    sta PF0Buf,Y
    lda (RoomPF1Lo),Y    ; same problem
    sta PF1Buf,Y
    lda (RoomPF2Lo),Y    ; same problem
    sta PF2Buf,Y
    iny
    cpy #12
    bne .LPB_Loop
    rts
```

### Fix per P3.3 plan

Stage `FetchPtr` before each phase, then fold each of the 36 reads.
The plan notes that PF2 phase must re-stage per row because dest `$E0` is hit at row 5+.

Structure (from level_bank_plan.md P3.3):
```
; Phase 0: PF0 — stage once, 12 folds (dest $C3-$CE, never touches $E0)
; Phase 1: PF1 — stage once, 12 folds (dest $CF-$DA, safe)
; Phase 2: PF2 — per-row stage (dest $DB-$E6, hits $E0 at row 5)
;   rows 0..4: can stage once if we start before $E0 write window
;   rows 5..11: each fold writes dest=$E0+n → overwrites FetchPtr → MUST re-stage per row
```

Wait — `PF2Buf` base is `$DB` (from the alias table). Row 5 dest = `$DB + 5 = $E0`.
So at row 5, `sta PF2Buf+5` writes `FetchPtr` (the low byte). Row 6 writes `FetchPtr+1`.
Both corrupt the pointer BEFORE we've finished reading.

The plan says: "per-row stage PF2 ptr (dest hits $E0 at row5+), 12 folds."

Simplest correct implementation:
```asm
; Phase 0: PF0 — stage once
lda RoomPF0Lo
sta FetchPtr
lda RoomPF0Hi  
sta FetchPtr+1
ldy #0
.LPB_PF0:
jsr FoldIndirect      ; Y=0..11, reads PF0[Y] from bank2
sta PF0Buf,Y
iny
cpy #12
bne .LPB_PF0

; Phase 1: PF1 — stage once (PF0 write dest was $C3-$CE, $E0 untouched)
lda RoomPF1Lo
sta FetchPtr
lda RoomPF1Hi
sta FetchPtr+1
ldy #0
.LPB_PF1:
jsr FoldIndirect
sta PF1Buf,Y
iny
cpy #12
bne .LPB_PF1

; Phase 2: PF2 — must re-stage AFTER each write that hits $E0 (rows 5+)
; PF2Buf = $DB; row 5 dest = $E0 = FetchPtr (alias); row 6 dest = $E1 = FetchPtr+1
; Solution: stage once for rows 0..4; re-stage EVERY row for rows 5..11.
; Simpler: just re-stage every row (always safe, costs 4c×12 extra = 48c total).
ldy #0
.LPB_PF2:
; Re-stage FetchPtr from RoomPF2Lo/Hi (4 instructions, ~14c)
lda RoomPF2Lo
sta FetchPtr
lda RoomPF2Hi
sta FetchPtr+1
jsr FoldIndirect      ; reads PF2[Y] from bank2
sta PF2Buf,Y
iny
cpy #12
bne .LPB_PF2
rts
```

**Wait — this is wrong!** After `sta PF2Buf,Y` when Y=5, we write to `PF2Buf+5 = $E0 = FetchPtr`.
The `iny` advances Y, then at the top of next iteration we re-stage — so FetchPtr is restored
before the next fold. **This works correctly** because we re-stage at the TOP of each loop
iteration, before the fold.

But there's another problem: after `sta PF2Buf+5`, FetchPtr = PF2[5] (a random data byte).
Then `iny` = 6, `cpy #12` (not taken), and we re-stage — OK. The stale FetchPtr between
`sta PF2Buf,Y` and the next re-stage is harmless (FoldIndirect is not called there).

**Cost increase:**
- Phase 0: was 12 × (lda + sta) = 24 ops ≈ 72c → now 12 × 26c fold = 312c. **+240c**.
- Phase 1: same. **+240c**.
- Phase 2: was 12 × 15c = 180c → now 12 × (14c stage + 26c fold) = 480c. **+300c**.
- Loop overhead change: was one loop for all 3, now 3 loops. Small.
- Total VBLANK addition: ~240 + 240 + 300 + misc ≈ **~800c** added.

With current VBLANK setup at 3439c and timer #60 (3840c headroom 401c):
**3439 + 800 = 4239c > 3840c → VBLANK TIMER WILL EXPIRE IF TIMER STAYS AT #60!**

### Critical: must raise VBLANK timer for P3.3

New VBLANK setup ≈ 4239c. Timer must be raised:
- `#66` = 4224c — too close (might fail on heavy frames).
- `#70` = 4480c — 241c headroom. Safer.

With `#70`: VBLANK section = 4480c + ~6c ≈ 4486c ÷ 76 ≈ **59 lines**.
Frame total: 3 + 59 + 147 + 51 + 30 = **290 lines** — worse than 281.

This confirms the investigation's concern: P3.3 makes VBLANK even longer.

### Alternative: move LoadPFBuffer to overscan

If LoadPFBuffer runs in overscan instead of VBLANK:
- VBLANK loses ~800-1000c of work → setup ≈ 3439 - 970 = 2469c.
- Timer can drop: 2469c ÷ 64 = #39 → 2496c (27c headroom) or #40 (2560c, 91c headroom).
- With #40: VBLANK = 2560 + ~6c ≈ 2566c ÷ 76 ≈ **33.8 lines**.
  That's UNDER 37 lines! Use timer #44 = 2816c: 2816-2469=347c headroom. VBLANK = 37 lines ✓.
- Overscan gains ~800c: 1964 + 800 = 2764c > 2240c (#35 = 2240c) → overscan timer ALSO expires!
- Must raise overscan timer: 2764 ÷ 64 = #43 → 2752c (too close) or #46 = 2944c (180c headroom).
- Overscan wait = 2944c ÷ 76 = 38.7 scanlines → MUST TRIM other overscan sections to fit 30 lines.

This is the "structural trim" the investigation doc defers to a later step.

---

## 9. Conclusion: immediate fix for P3.3 (just get playfield working)

**For now**: implement P3.3 with a raised VBLANK timer, accepting frame = ~290 lines.
The playfield being broken is the most important problem. Frame length is a polish issue.

**Simplest correct P3.3 + timer raise:**
1. Replace `LoadPFBuffer` body with 3-phase fold loop (as described in §8).
2. Raise VBLANK timer from `lda #60` to `lda #70`.
3. Build → verify playfield correct in Stella.
4. Accept ~290-line frame temporarily.
5. Timer/frame trimming = separate step.

---

## 10. Update (analysis complete, starting fix)

P3.3 approach confirmed. Two implementation options:

**Option A (simple, wrong re-staging):** Re-stage FetchPtr at top of PF2 loop every iteration.
Cost ≈ +800c VBLANK. Timer: #70.

**Option B (optimal):** Only re-stage when about to write to $E0 or $E1 (rows 5 and 6).
Same approach but saves 10 × 14c = 140c on PF2. Net VBLANK addition ≈ +660c. Timer: #66.

Going with **Option A** for clarity and correctness. Can optimize later.

---

*Last updated: 2026-09-28. See below for implementation notes.*
