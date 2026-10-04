# Asymmetric Playfield Plan — phased implementation

Goal: rooms whose right half does NOT mirror the left (HERO-style off-center
gaps). Method = HERO's double-phase PF write (verified in
`docs/hero_asymmetric_rooms.md`): a `STA PFx` with CPU phase ≤ ~44 paints the
LEFT half, phase ≥ ~50 (after color clock 147) paints only the RIGHT half.

Our kernel writes PF once per 48-line band → halves always equal. This plan
adds a *late* right-trio write on each row's setup line, plus the data to feed
it — **without regressing the 262-line frame, the 76-cycle `.Line`, the 1B
bank0 headroom, or symmetric rooms' ROM size**.

## Measured baseline (2026-10-03)

| Item | Value |
|---|---|
| Models | 8 (`models_data.asm`), 3 rows each |
| Per-model ROM today | ~44B: 9B PF (3×PF0/1/2) + rect list (count + 4B/rect + hot) |
| All level data ROM | ~480B (models 356B + room tables 124B) — lives in **bank2** |
| Symmetric PF growth | **+0 B** (see encoding D2) |
| Worst-case asymmetric model | **+~30B** (9B right PF rows + flag + ~15–20B right rects) |
| All 8 models asymmetric | ≈ **+240B** vs 16K — negligible; bank2 has the space (data at $F9D9+, gaps noted in AGENTS) |
| bank0 pre-pad headroom | **1 B** (`ends $FC67, limit $FC68`) — all kernel code growth must be pad/bank2 or net-cut |
| Rect walk | `RcW1=$CC`, walk sees **left half only**; prologue endpoint-mirrors cols to 39 (`kernel.asm:2320,2399`) |
| WallMask | b3–6 = masks for **wall rects 0–3** (`MASK_BITS`); models 5/6 already warn 6 wall rects (cell-swap open item — **dependency**, see Risks) |
| RAM | PF0Buf $C3 / PF1Buf $C6 / PF2Buf $C9 (3B each, rows 0–2); **no free sequential ZP**; stomp zone $E0–$EF (bank1 HUD) holds only per-frame-rebuilt data (ColupfBuf pattern) |

**Conclusion to "will ROM grow a lot?"** No. Encoding below keeps every
current room byte-identical; only *actually asymmetric* models pay (+9B PF +
rects + 1 flag). The expensive parts are timing and collision, not ROM.

## Design decisions

- **D1 — model granularity.** Asymmetry is a property of the model shape
  (rooms share models); one flag per model, not per row/room.
- **D2 — encoding (the "half + separate list" the user suggested).**
  - Symmetric model: emit exactly today's bytes (9B PF left-trio + rects
    mirrored at runtime). Flag = 0. **Zero growth, byte-identical ROM.**
  - Asymmetric model: additionally emit right-trio rows (3B × affected rows,
    ≤9B) + a right-half rect list (only for the right half's decomposition)
    + flag = 1. `enter-time` load fills a second 9B RAM set (or reads ROM —
    Phase 0 decides).
  - Flag storage: 1 byte per model table row (or a global bitmask byte for
    all 8 models — decide in Phase 0; bitmask = 1B total).
- **D3 — right-half source data in the editor: DECIDED = Option B** (2026-10-03, user):
  `models.json` gains optional `asym_patches: [[row, right_col, tile], ...]`
  applied over the mirrored right half. JSON size unchanged for symmetric
  models; legacy files load with `[]` (explicit default = migration rule
  satisfied); convert resolves patches → right rows; editor = overlay paint
  on a right-half pane (right_col 0–19, 0 = the column adjacent to center).
  ROM never sees patches, only resolved rows.
  (Option A — width-40 models — recorded as rejected alternative: more
  editor/serializer work; ROM zero-growth could have been kept either way.)
- **D4 — reflect stays ON** (`CTRLPF=$05`/cave `$35` like HERO). The stored
  right-trio bytes must be bit-order-adjusted for reflect at convert time
  (same rule as `pf_values`, reversed column order). Exact byte derivation
  is a Phase 0 proof (one known pattern → predicted bytes → verified render).
- **D5 — where the late write lands: the row's existing setup line.**
  `.Line` is untouched (fixed-time invariant preserved). Setup line today
  ≈69/76c — the late trio (`3×(lda+sta)` ≈ 15c from RAM, 24c from ROM
  indirect) must fit in phase ≥50 with WSYNC ≤73. Phase 0 probe decides
  RAM vs ROM staging and whether the setup line fits or a line must be
  reclaimed (fallback F1 below).
  **SUPERSEDED by Phase 0 results** (setup-line late write only affects the
  transition line — body lines re-paint both halves from the persistent
  register state, so bands stay mirror-symmetric; and the free window is
  14-15c < even the RAM trio). See "Phase 0 results" fork O1-O3.

## Fallback F1 — if the setup line cannot fit (decide only after Phase 0 probe)

3 extra lines/frame (one per row's late-write line) = 265 ≠ 262 → requires
a frame rebalance (candidates: VBL 37→35 with TIM64T re-window — VBL margin
measured +237c ≈ 3 lines; HUD band; NOT overscan — its work meter is already
at the window). This is a separate investigation with its own sim gates and
must not be started before D5's probe fails. Estimate: last resort.

## Phases (build-test-build: stop after each CHECK and get user sign-off
before the next phase when the phase touches kernel/timing/data format)

### Phase 0 — measurements & proofs (no behavior change)
1. py65 probe (extend the `hero_asymmetric_rooms.md` harness): dump our
   `.Row` setup line's write phases (PF0/1/2, COLUPF) on a real frame →
   confirm left writes land ≤44 and find the free window ≥50 (if any).
2. Count exact cycles available on the setup line for the late block
   (worst path) → choose RAM (15c) vs ROM-indirect (24c) staging; if neither
   fits ≤73 → trigger F1 investigation.
3. ZP audit for +9B right buffers: map every writer/reader of $E0–$EF and
   $C6–$CF per `docs/zp_layout_skill.md`; either find a per-frame-rebuilt
   9B home in the stomp zone (ColupfBuf pattern) or commit to ROM-indirect
   staging (zero RAM).
4. Encoder proof: hand-derive register bytes for one known right-half
   pattern under reflect (D4) → write as a unit test fixture.
5. Pre-pad byte budget: how many bytes `.Row` can grow in bank0 (expect:
   none — design the flag dispatch as `jsr CallPad_*` to bank2, the
   established `CallPad_BombMarkWalls` pattern, if inline does not fit).
   Record numbers in this file (append a "Phase 0 results" section).

**CHECK 0:** probe output + chosen staging (RAM/ROM) + flag-dispatch shape
+ encoder fixture committed; `./build.sh` + battery 11/11 (nothing changed
in ROM yet — fixture is a new test only).

### Phase 1 — data pipeline (convert only; ROM byte-identical for current content)
1. `convert_room.py`/`convert_level.py`: accept `asym_patches` (Option B) or
   40-col models (Option A — whichever D3 resolves to); detect symmetry;
   emit flag + right rows + right rect list **only for asymmetric models**.
2. `verify_build.py`: guard — symmetric models' emitted bytes must match the
   pre-change output exactly; asymmetric models must have flag + right rows
   with stride 3; right rects ≤ WallMask budget (see Risks).
3. New `tools/test_asym_data.py`: synthetic asymmetric model → expected
   ROM bytes (fixture from CHECK 0) + legacy `models.json` (no field) →
   byte-identical output.

**CHECK 1:** regenerate all levels → `git diff generated/` **empty**
(proves zero growth for current content); new test passes; battery 11/11.

### Phase 2 — kernel staging (load only; rendering unchanged)
1. EnterRoom (bank2 body / fold as needed): load flag + right rows per D2
   (RAM home from CHECK 0 or set the ROM right-rows pointer).
2. No PF write changes yet — symmetric rendering must be bit-identical.

**CHECK 2:** build green, `sim_frame_budget` 263.0±0.15 every frame,
battery 11/11, Stella smoke ≤262 / min SP ≥$F8 (one run only — no loops);
user plays one stage: nothing visible changed.

### Phase 3 — the late right-trio write (flag/staging-gated)
1. Implement D5's block on the row setup line (Phase 0 shape): left trio
   early as today, right trio at phase ≥50, `sta WSYNC` still ≤73 (recount
   from `bank0.lst`/`bank2.lst`, never from comments).
2. For symmetric staging (same bytes) the block may run unconditionally;
   for distinct right rows it is flag-gated via the CallPad dispatch.
3. Verify with a py65 render probe: capture PF register values at clock 100
   (left) and clock 200 (right) for one line of an asymmetric test room →
   right ≠ left; for a symmetric room → right shows mirror as today.

**CHECK 3:** phase probe passes (right write ≥50, WSYNC ≤73, frame 262,
sim invariant, battery 11/11). **User test (mandatory):** symmetric rooms
look unchanged; one forced-asymmetric test model (temp patch in
`models.json`) shows an off-center gap exactly where painted.

### Phase 4 — collision & gameplay on right-half walls
1. `convert_room` emits right-half rects for asymmetric models; PHM skips
   the endpoint-mirror prologue (`kernel.asm:2320`) when the flag is set and
   walks both rect lists instead (X-preserve rule around `PlayerHitsMap`
   applies; PLA preserves carry — keep probe carry semantics).
2. Bomb wall destruction: `BombMarkWalls`/`ApplyBombWalls` use WallMask
   bits — right-half wall rects consume the same 4 mask slots → enforce
   `wall_rects ≤ 4` across BOTH halves at convert time (fail loudly).
3. Laser kill window + enemy Y/X derives assume mirrored rects? Audit
   `LaserHitTest`, `CheckP0Left/Right`, `UE_*` probes for half-space
   assumptions (they read rects or cols — each gets the flag treatment).

**CHECK 4:** static PHM sim (extend `test_cell_map.py` fixtures with an
asymmetric room: expected hit/miss cells on both halves); wall-bomb tests
(`test_laser_wall.py`, bomb tests) pass with an asymmetric fixture; battery
11/11. **User test:** walk into both halves' walls, bomb a right-half wall,
laser a right-half enemy behind an off-center gap.

### Phase 5 — editor UX (D3's chosen option)
1. Option B: right-half overlay pane + patch paint/save/load (round-trip);
   Option A: 40-col models + width migration (both loaders + verify).
2. `verify_build.check_room_txt`/models checks updated for the new field/
   width; regenerate every level from the editor and confirm
   `git diff generated/` is still empty for untouched content.

**CHECK 5:** editor round-trip (open → paint asym → save → convert →
bytes match test fixture); battery + full build; user draws an asymmetric
room end-to-end.

### Phase 6 — QA sweep
Battery, both sims, one Stella smoke run, user screenshot pass: off-center
gap room, bombs, laser, enemies, HUD, dark rooms (flag must not disturb
ColupfBuf/`BuildColupF`), title/drop-in, level advance.

**CHECK 6:** user sign-off → commit (with TODO.txt per repo rule).

## Risks / dependencies (read before starting a phase)

1. **WallMask = 4 slots total**; models 5/6 already exceed the rect budget
   (open "cell-swap" item). Right-half walls land **after or with** that
   work — convert must hard-fail `wall_rects > 4` per model once flag-gated
   masks exist. Do not silently wrap.
2. **bank0 = 1B.** Anything grown inline in pre-pad code must be net-cut
   elsewhere or relocated to bank2 via pads. `.Row` is pre-pad — D5's block
   needs the CHECK 0 byte budget first.
3. **Setup-line overrun = skipped scanline** (the 2026-09-25/29 bug family).
   Any WSYNC landing ≥74 doubles a row and pushes the frame to 263+ → the
   sim wall-model + `bank0.lst` cycle recount are mandatory gates, not
   optional.
4. **Stomp zone:** if right rows go to $E0–$EF they MUST be rebuilt every
   frame (bank1 HUD zeros $E0–$EF) — EnterRoom-only load is NOT enough for
   persistent bytes; follow the ColupfBuf $E7 exception pattern or keep
   staging in ROM.
5. **Bank-aliased PCs:** py65 probe must pair (pc, bank) — `$Fxxx` addresses
   are ambiguous across banks (AGENTS py65 rule).
6. **D3 is a user decision** (Option B vs A) — do not start Phase 1 until
   it is answered.

## Phase 0 results (2026-10-03)

Artifacts: `tools/probe_row_phases.py` (py65, self-contained, boot-poke +
console-RESET pattern from `sim_frame_budget.py`), `tools/test_asym_encoder.py`
(D4 fixture, pure python). `./build.sh` green, battery **12/12** (11 + new
encoder test), sims OK. No ROM changes.

### 1. Probe output — our `.Row` setup line (gameplay frame 30)

| Store | Measured phase | kernel.asm:630 comment | Δ |
|---|---|---|---|
| PF0 | 28 (row0) / 30 (rows 1-2) | c34 | −6 |
| PF1 | 35 / 37 | c41 | −6 |
| COLUPF | 42 / 44 | c48 | −6 |
| COLUBK | 48 / 50 | c54 | −6 |
| PF2 | 55 / 57 | c61 | −6 |
| WSYNC (line end) | 70 | c69 | +1 |

- **Comment is stale by ~6c** (AGENTS "never trust comment cycle counts"
  recurrence). Rows 1-2 cost +2c over row0 (row-advance branch path).
- **Free window after the last PF store: 14-15c** (≈11c after PF2's 4c
  store completes) — **less than one `lda zp,X`+`sta abs` pair (8c) per
  register: a RAM-staged late trio needs 24c, ROM-indirect ≈36c** (the
  plan's earlier "15c RAM" figure was wrong). Setup line cannot host any
  late trio as-is → for the old D5 this meant F1; D5 is superseded anyway.
- **Cave body lines carry zero PF writes** (only setup lines 23/72/121 +
  floor/HUD transitions) — our kernel confirmed boundary-only, same as
  every reachable HERO trace.

### 2. Timing model — what persistent asymmetry actually costs

Paint windows (CPU cycles on the line; HBLANK ends c22.7): left cells are
painted c22.7-49 (color clocks 68-147), right c49.3-75.7 (148-227).
Per-register windows for independent halves (left cell groups: PF0
clk68-83, PF1 84-115, PF2 116-147; right groups: PF2 148-191, PF1 180-211,
PF0 212-227):

- L-PF0 ≤22.7, L-PF1 ≤28, L-PF2 ≤38.7
- R-PF0 27.7-70.7, R-PF1 38.3-60, R-PF2 49-63.7

A feasible interleaved per-line schedule exists (L trio first ~30c, R trio
by ~60c) — but it needs **all 6 stores on every line of the band**:
6×(`lda zp,X`+`sta abs`) = **48c** minimum (the plan's "15c" was wrong),
≈56c with loop control.

- `.Line` worst path is 61c → +48 = 109 ≫ 76: **per-line writes cannot go
  into `.Line`.** A dedicated lean line (writes only) fits (~56c), leaving
  ~20c for sprites — enough for a minimal GRP0 path at best; enemies/
  laser/beam do not fit.
- One write on the setup line only splits the transition line; body lines
  re-read the persistent register set → both halves mirror it. **D5 as
  written can never produce a full-height asymmetric band.**

### 3. ZP audit (task 3)

No contiguous 9B free anywhere (`$F2` is the only free byte; sequential
block ends `$BB`). Staging candidates for the 9B right-trio:

- **`$E0-$E8` (inside bank1's scorePtr window `$E0-$EB`)** — viable with the
  ColupfBuf time-partition: bank0 VBL writes → cave band reads → HUD band
  stomps (bank1 rebuilds scorePtrs every frame) → next VBL rewrites.
  Caveats: `$E5-$E6` = FetchPtr (its VBL stage order vs the right-rows
  write must be checked at Phase 2), `$E2-$E4` = EnemyRamY (live during
  cave — do not overlap: prefer `$E0-$E1`+`$E5-$EB` or reposition).
- **ROM-indirect** — 0 RAM, ≈13c/read (`lda (ptr),Y` + `sta`); too slow for
  per-line use, fine for EnterRoom-time loads into RAM.
- **`$E7-$EF` exactly 9B is NOT free** — `$E7-$E9` = ColupfBuf rows 0-2,
  needed during the cave band (same window as right rows).

### 4. Staging / dispatch / encoder (CHECK 0 deliverables)

- **Flag dispatch shape (mechanism-independent): `jsr CallPad_*` to bank2**
  (established `CallPad_BombMarkWalls` pattern — pre-pad headroom is 1B,
  inline is impossible regardless of fork).
- **Staging choice: DEFERRED to the fork below** (Phase 2's load shape
  depends on which rendering mechanism wins; RAM-vs-ROM argument is
  recorded in §3 either way).
- **Encoder proof: `tools/test_asym_encoder.py` — 3 fixtures pass.**
  `encode_right(B) = pf_values(reverse(B))` (D4 reflect rule), verified by
  a reflect-mode render back to B; hand-derived bytes `($F0,$FF,$3F)` and
  `($F0,$FF,$E7)`; symmetric mirror baseline round-trips.

### 5. Fork — mechanism decision REQUIRED before Phase 2/3 (user)

D5 is dead; the probe + timing math leave three real options:

- **O1 — dedicated lean band (HERO-HUD-style).** Asymmetric rooms render
  the cave band via per-line dual writes (56c pattern lines), sprites on
  interleaved/equal lines. Cost: enemy/player coexistence needs a frame
  rebalance + flicker tradeoff (HERO's HUD flickers by design). Highest
  fidelity, highest risk — effectively F1+ redesign of the cave kernel.
- **O2 — overlay mask (zero-kernel-growth).** Keep symmetric PF; mask the
  difference with the **ball** (free in cave: bomb uses GRP1, ball is
  disabled at kernel entry — a `#$80` vs `#0` on that one store = 0 extra
  lines, ball X set once in VBL). Ball max width 8 color clocks = exactly
  2 cells. Only works for diff shapes ≤8 clks wide at one fixed x (a
  1-cell-shifted center gap fits: HERO.png's disputed "wall" x470-514 is
  exactly 2 cells = ball width, wall-colored = invisible overlay). ENABL
  per-line gating costs +9c on `.Line` (61→70, WSYNC@76 = over) → must be
  row-constant or moved to the setup line.
- **O3 — re-examine the goal.** Every reachable HERO frame (5 game modes ×
  420 frames, all boundary-only, body write-free) contradicts the doc's
  "HERO writes PF twice per scanline" claim for caves (only HERO's *HUD*
  shows true per-line double writes, phases 32/39/46). The screenshot's
  ~1-cell off-center gap is within the cell-grid origin uncertainty
  (±22-37px scatter) and/or explained by O2's ball mask. HERO may simply
  not have asymmetric caves — if so, decide what WE actually want (true
  per-line rooms = O1 cost; masked gaps = O2 cost).

Phase 1 (data pipeline: `asym_patches` → flag + right rows, byte-identical
regeneration) is mechanism-independent and can start at CHECK 0 sign-off;
Phases 2-3 are blocked on O1/O2/O3.
