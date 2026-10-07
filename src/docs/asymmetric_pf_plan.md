# Asymmetric Playfield Plan — phased implementation

Goal: rooms whose right half does NOT mirror the left (HERO-style off-center
gaps/walls).

**Current mechanism = D6 / O2 ball-mask overlay** (fork resolution
2026-10-04, HERO-verified — see "HERO verification" and "O2/D6 envelope"
below): keep the mirrored PF, paint the difference with the TIA ball
(COLUPF-colored, PFP-hidden under real walls, exactly 1 cell = 8 clks at
one x per cave frame under the D7 10-col grid, additive-only). The original double-phase late right-trio write
(D5, method from `docs/hero_asymmetric_rooms.md`) is **dead — superseded**;
its O1 analysis survives as the recorded fallback.

The invariants every phase must keep: the 262-line frame, the 76-cycle
`.Line`, the 1B bank0 headroom, and symmetric rooms' ROM size.

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
  on a right-half pane (right_col 0–9 under D7 — 0 = the column
  adjacent to center; 0–19 was the pre-D7 20-col grid).
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
- **D7 — grid = 10 columns per half, 3 bands × 48 lines (user decision
  2026-10-04, "the HERO way").** 1 logical cell = 2 hardware PF pixels
  (8 clks = 32 screen px at 4px/clk); the encoder sets both bits of each
  pair identically.
  - Kernel/frame/CPU: **unchanged** — still 3 PF stores per band, PF
    persists, `.Line` untouched; only bit-pairing inside the bytes
    differs. Bands stay 3 × 48 (the 4-band variant was evaluated and
    rejected same day: medium cost, ZP reshuffle, full map re-row).
  - Ball = 8 clks = **exactly 1 cell** → every patch is cell-aligned;
    D6's "≤2 cells" was stated in the old 4-clk grid and means **1 cell**
    with the ball, 2 cells (16 clks) only with the parked M1 upgrade.
  - Player = 8 clks = 1 cell wide → 1-cell passages are exact-fit
    (HERO-tight); draw unit = ball unit = collision-rect unit.
  - Coarser cells merge wall runs → fewer rects per model → eases the
    WallMask 4-slot overflow (Risk 1).
  - **Migration (repo rule — all data + generators in one change):**
    `rooms/*.txt` (20-col → 10), `models.json` grids, editor MapCanvas
    cell size, convert/verify width constants, X-side cell division in
    collision, and all fixtures (`test_cell_map`, `test_asym_encoder`,
    `test_asym_data`). Legacy 20-col input must fail loudly after the
    flip (no silent width guessing). **Sub-decision RESOLVED
    2026-10-04 = (a) auto pair-merge**, user reviews rendered stages
    later. Merge rule = **open-wins** (pair → open if either member is
    open): every ≥2-old-col passage survives by construction (any open
    member keeps the pair open — misaligned runs widen instead of
    closing); cost = walls adjacent to passages thin by ≤1 old col
    (visual, user reviews). Wall-wins was rejected: it kills
    pair-misaligned 2-col corridors that the old grid could pass.

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
1. `convert_room.py`/`convert_level.py`: accept `asym_patches` (Option B —
   D3 resolved; Option A/40-col rejected); detect symmetry;
   emit flag + right rows + right rect list **only for asymmetric models**.
2. `verify_build.py`: guard — symmetric models' emitted bytes must match the
   pre-change output exactly; asymmetric models must have flag + right rows
   with stride 3; right rects ≤ WallMask budget (see Risks).
3. New `tools/test_asym_data.py`: synthetic asymmetric model → expected
   ROM bytes (fixture from CHECK 0) + legacy `models.json` (no field) →
   byte-identical output.
4. **D6 envelope guards** (added 2026-10-04, fail loudly in convert +
   `verify_build`): all patches of a model must share ONE column-x and
   fit ≤1 cell (8 clks — the ball; 2 cells only with M1); subtractive
   patches (target open where mirror = wall) rejected; fixtures:
   subtractive model must fail, multi-column model must fail, >1-cell
   run must fail, valid 1-cell single-column model must pass.
5. **D7 grid migration (2026-10-04):** flip width 20 → 10 everywhere in
   the pipeline — `rooms/*.txt`, `models.json`, convert/verify width
   constants, encoder bit-pairing (1 logical cell → 2 PF bits), X-side
   collision cell division, `test_cell_map`/`test_asym_encoder`/
   `test_asym_data` fixtures, editor `MapCanvas` cell size (Phase 5
   implements the UI side). Legacy 20-col input → hard error.
   Migration = one-time in-place transform (rooms + models committed at
   10-col) using D7's resolved rule: **pair-merge, open-wins**;
   convert does not carry legacy-width support.

**CHECK 1:** one-time D7 regeneration committed (all rooms/models on the
10-col grid; `git diff generated/` empty on every run **after** that
flip — proves stability, not zero growth); D6 envelope fixtures pass;
battery 11/11.

### Phase 2 — ball staging (D6; symmetric rendering bit-identical)
1. Cave CTRLPF `$05` → **`$35`** (kernel.asm:426): D5-D4=%11 = 8-clk
   ball; PFP D2 already set. Bank1 HUD keeps its own `$05` writes (1-clk
   bar separator unchanged).
2. `SetObjectXPos`: add selector 4 (RESPBL/HMBL — table lives in the
   pinned `$FF10` gap with page-cross guards; recount bytes and re-run
   the verify_build guards after ANY growth). If the gap has no room:
   inline VBL div15 for the ball instead. **Never touch the existing
   div15 loop's timing (AGENTS rule).**
3. VBL: position ball X from patch data — flag-gated; symmetric rooms
   skip (bit-identical).
4. Kernel entry: keep today's `sta ENABL` (A=0, kernel.asm:611) as the
   flag=0 path; flag=1 path leaves the enable to Phase 3's setup-line
   writes (no enable in Phase 2 yet).
5. No PF write changes.

**CHECK 2:** build green; `sim_frame_budget` 263.0±0.15 every frame;
battery 11/11; Stella smoke ≤262 / min SP ≥$F8 (one run); py65 probe on
a cave frame: CTRLPF reads `$35` during the cave, ENABL stays 0,
symmetric rooms bit-identical; user plays one stage: nothing visible
changed.

### Phase 3 — the patch (flag-gated ENABL on band setup lines)
1. Per-band setup line: enable/disable ENABL in the Phase 0 measured
   free window (14–15c; `lda #imm` + `sta ENABL` ≈ 6c) — on when the
   band shows the patch at ball-x, off otherwise. Flag-gated: symmetric
   rooms execute no ENABL writes (bit-identical). All-bands-patched =
   single enable at kernel entry (HERO's degenerate 2-write latch).
2. Patch-x source: prefer convert-time static byte (1B ball-x; zero
   runtime cost) derived while emitting the right rows — decide against
   EnterRoom derivation by byte budget at Phase 2.
3. py65 render probe: forced-asymmetric test model → RESBL/HMBL phase
   matches ball-x, ENABL set on exactly the patched bands' lines and 0
   elsewhere, left/right pixels differ at ball-x only; symmetric room →
   ENABL never set, pixels mirror as today.
4. Envelope guards from Phase 1 item 4 are live (convert + verify_build
   fail loudly).

**CHECK 3:** probe passes (ball-x phase, ENABL band gating, CTRLPF
`$35`, frame 262, sim invariant, battery 11/11). **User test
(mandatory):** symmetric rooms look unchanged; one forced-patch test
model (temp patch in `models.json`) shows an off-center wall strip
exactly where painted, only in painted bands, hidden where the mirrored
cell is already wall; collision with that strip = CHECK 4.

**Landed 2026-10-04 — final shape (differs from the sketch above):**
1. convert emits 3 extra meta bytes/model: `Band0/1/2` (`$ff` = the
   right row is not the plain left-row mirror) at TilePF0+11..13;
   `BallX` at +10 (0 ⇔ symmetric, verify_build enforces; `87+8*right_col`
   under the D6 envelope). Symmetric models emit 0/0/0.
2. **Staging runs in bank2**, not inline: `BCFDarkRun` (BuildColupF
   tail) now `jmp StageBandTab` → copies BallX→Temp ($88) and
   Band0-2→BandTab ($ED-$EF) every VBL, then `jmp $FBF8` ReturnPad
   (pads never nest, SP depth unchanged). WHY bank2: `models_data` lives
   there — a bank0 `(RoomPF0Lo),Y` read fetches bank0's $F9xx zero pad
   (Phase 2's ball block silently read zeros; passed only because
   sym = 0).
3. VBL ball block moved after `.BgStore` (which now does the single
   per-frame `sta COLUBK`): `lda Temp / beq skip / ldx #4 / jsr
   SetObjectXPos` → RESPBL/HMBL only when BallX ≠ 0, before the one
   HMOVE. Sym runs skip (bit-identical leg strips CTRLPF/ENABL/COLUBK).
4. `.Row` gate: the freed `lda Temp/sta COLUBK` slot (between COLUPF
   and PF2) does `lda BandTab,X / sta ENABL` — 7c (+1c vs the 6c pair),
   PF2 shifts c61→c62 (still past the right-half x449 pixel: thin-yellow
   fix intact). ENABL latches per line: on from each band's first body
   line, water inherits row2, `.AfterRows` starts the HUD line with
   `lda #0 / sta ENABL` (bank1 got no entry clear — +2B tripped
   `.ds $F9C0`; the HUD bar writes its own ENABL anyway).
5. Row advance restructured: `cpx #TILE_ROWS / beq .WaterRow / bcs
   .AfterRows / jmp .Row` (−2B, −2c). Probe_row_phases: setup WSYNC
   writes 71/71/70 (≤73 safe).
6. Hand-sync fallout: bank1 `jmp $F18D` (Overscan moved −3), bank2
   `PlayerSpriteA/B = $F8CA/$F8D6` (pre-pad net −3), `BandTab = $ED`
   mirrored in kernel+bank2 (check_equ_sync pins both).

**CHECK 3 automated gates (2026-10-04):** `tools/test_phase3_ball.py`
(py65, pokes all 32 meta bytes — bands $ff + BallX=100): ENABL ∈
{00,ff} with ≥3 ff/frame, RESPBL+HMBL every frame (proves the bank2
staging ran), frame lines 263 constant, min SP $FB. probe_row_phases
71/71/70, battery **15/15**, both sims OK, Stella smoke 550 frames
worst 262 / min SP $FB. **User test still pending** (CHECK 3 text
above: symmetric unchanged + forced-patch visual).

### Phase 4 — collision & gameplay on patch cells
1. `convert_room` emits right-half rects for asymmetric models; **under
   D6 the patch column is PF-mirror-open but visually wall — those cells
   MUST be in the right rect list** or the player walks through the
   painted strip. PHM skips the endpoint-mirror prologue
   (`kernel.asm:2320`) when the flag is set and walks both rect lists
   instead (X-preserve rule around `PlayerHitsMap` applies; PLA
   preserves carry — keep probe carry semantics).
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
laser a right-half enemy behind the painted wall strip.

### Phase 5 — editor UX (D3's chosen option + D7 grid)
1. Option B: right-half overlay pane + patch paint/save/load (round-trip);
   Option A: 40-col models + width migration (both loaders + verify).
   **D7: cell grid doubles in size (20→10 cols — same wall art,
   chunkier cells); envelope = 1-cell patches painted on the pane.**
2. `verify_build.check_room_txt`/models checks updated for the new field/
   width; regenerate every level from the editor and confirm
   `git diff generated/` is still empty for untouched content.

**CHECK 5:** editor round-trip (open → paint asym → save → convert →
bytes match test fixture); battery + full build; user draws an asymmetric
room end-to-end.

### Phase 6 — QA sweep
Battery, both sims, one Stella smoke run, user screenshot pass: off-center
patch (wall-strip) room, bombs, laser, enemies, HUD, dark rooms (flag must not
disturb
ColupfBuf/`BuildColupF`), title/drop-in, level advance.

**CHECK 6:** user sign-off → commit (with TODO.txt per repo rule).

## Risks / dependencies (read before starting a phase)

1. **WallMask = 4 slots total**; models 5/6 already exceed the rect budget
   (open "cell-swap" item). Right-half walls land **after or with** that
   work — convert must hard-fail `wall_rects > 4` per model once flag-gated
   masks exist. Do not silently wrap.
2. **bank0 = 1B.** Anything grown inline in pre-pad code must be net-cut
   elsewhere or relocated to bank2 via pads. `.Row` is pre-pad — under D6
   the ENABL gate (`lda #imm / sta ENABL` ≈ 6c + flag test) must fit the
   Phase 0 measured 14–15c window **inline**; the flag dispatch may need
   the CHECK 0 CallPad shape, but mid-kernel fold/jsr-into-bank2 is NOT
   yet proven — prefer a kernel-entry latch or an inline ZP-table read
   (`lda Tab,Y / sta ENABL`) decided at Phase 3 byte budget.
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
6. **D3 was a user decision — ANSWERED 2026-10-03 = Option B**
   (`asym_patches` field, see Design decisions). Phase 1 unblocked.

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
  **SUPERSEDED detail (2026-10-04):** per-line ENABL gating is never
  needed — CTRLPF PFP priority (D2) hides the ball under real walls
  automatically (Stella order PF > BL; s1/s2 screenshots show exactly
  this). Per-band visibility = ENABL written on band **setup lines**
  (Phase 0 measured 14–15c free window there ≫ the 6c block), as the
  D6 fork resolution states; whole-cave latch = HERO's degenerate case.
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

## Fork resolution (2026-10-04, user)

- **D6 — mechanism = O2 (ball-mask overlay).** Selected as primary: zero
  `.Line` growth, no frame rebalance, bomb owns GRP1 so ball is free, one
  ENABL store `#$80` vs `#0`, ball X set once in VBL.
  **Constraint:** patch ≤2 cells wide (ball 8 color clocks, CTRLPF `$35`
  D5-D4=%11) at **one ball X for the whole cave frame** — HERO never
  repositions the ball inside the cave (single RESBL at line 50, verified
  across every probe frame/screenshot); per-band **visibility** comes from
  ENABL writes on band setup lines (not per-band X). Under D7's 10-col
  grid the ball is exactly **1 cell**, so the envelope is cell-aligned.
  Full capability envelope + additive-only rule: see "O2/D6 envelope"
  below.
- **O1 (dedicated lean band) = recorded fallback**, to be revived if O2
  fails verification or its ≤2-cell/fixed-x constraint blocks real content.
  All O1 analysis in §2 stays valid for that revival.
- Phases 2-3 rewrite under D6 (ball setup in VBL, ENABL gating on setup
  line, no PF write changes); Phase 4 collision work still required (mask
  cells differ from mirrored rects). Phase 1 unchanged. O3 dropped.

## HERO verification (2026-10-04, py65 dynamic probe)

Deep re-investigation (static disasm + live `tools/probe_hero_overlay.py`
runs, PC-logged TIA writes) — D6 mechanism **confirmed on real HERO code**,
plus one upgrade:

1. **Ball overlay = HERO's asymmetric mechanism (dynamic proof).**
   - Positioner call `$d11c`: `LDA $a0` → Davie div15 routine, **X=4 →
     RESBL** at cave line 50, HMBL line 51. Ball X = ZP `$a0` = 61 → clk60
     → x240-271 = `s_Hero_1` disputed tile, exact match (`rom[$FF77]=61`).
   - **ENABL written twice per frame only:** `$FF` at line 56, `$00` at
     line 174 — TIA latch = stripe **lines 56-173 (full cave height)**.
     No per-line ENABL gating in HERO → O2's "row-constant / setup-line"
     ENABL requirement is exactly what HERO does (0 `.Line` growth).
   - Width = CTRLPF `$35` (D5-D4=%11 = 8 clks), PFP priority (behind
     walls), **color = COLUPF** → wall rows/shading/blink track for free.
2. **M1 = second programmable patch (exists dynamically).** ENAM1 net
   (last write per line) nonzero on lines **59-104** in ~40% of frames;
   RESM1 fired in overscan (line 242, HMM1 ∈ {$00,$51}) → X programmable
   per frame. Laser owns M0 → M1 is free. **Two 1-col patches = ball+M1;
   adjacent pair = one 2-col patch.** `s_Hero_2`'s wall-colored region =
   **x64-111 (48px = 12 clks, cells 4-6), y90-167 (band B only)** —
   per-x uniform: 74 rows band shade ($24) + 4 accent rows ($20) on every
   x → two hardware objects side-by-side (ball 8 + missile 4, or 8+8
   overlapping; ball alone can't exceed 8 clks, sprites can't be 4 clks =
   16px). Cells 4-6 = wall in bands A/C, open in band B → visible only in
   B; right-half duplicate x384-431 = real wall (symmetric cells 15) →
   the patch is NOT mirrored → object paint, not reflect-OFF. The 4-clk
   part needs COLUP1 = wall shades incl. accent on those lines — hero
   writes COLUP1 every cave line (probe default = enemy shading; a state
   with idle P1 could write wall defaults — unverified). Ball X `$a0` has
   gameplay writers (`$d69e/$d6ac/$d992/$f6b0`) → ball may sit at clk16
   in this state (or hidden behind walls at clk60 — cells 15-16 are wall
   in band B, PFP priority hides it). State not reproduced (probe stalls
   before `$d735`) — screenshot-level evidence only.
3. **Cave PF = band-boundary writes only** (lines 53-58, 96-97, 135-136,
   175-176). The per-scanline-PF claim holds for HERO's HUD only, not the
   cave. (Matches §5/O3.)
4. **Per-game tables at boot:** index X = `mem[$80] & 127` →
   `f5=$FF6D[X]` (held-LEFT boot → 147, RIGHT → 44, verified), `a4=$FF6A[X]`
   ∈ {32,192,144,0,4,147,…}. Ball X does **not** follow the index (always
   61 across 128 boot variants).
5. **Probe operation notes:** frame-end = `$d9df → $dff2` data fallthrough
   → `$FFF5 JMP $f042` (switch/title loop). SWCHB active-low: **RESET =
   `$FE`** → `$f075` reboot (`$ba=0, JMP $f007`); SELECT = `$FD` → `$f083`
   sets `$ba=255`. Probe RAM starts 0 = all switches pressed → must write
   `$282=$FF` from frame 0 or every frame reboots. Player = **P1/GRP1**,
   X = `$9b` (moved 32→13 by held direction). Menu gate `$f2` has no
   store — it opens via `DEC $f2` underflow (`$d930`, player within 15 of
   `$bb`); restore reloads (`$d7b0/$d942/$d7ae JSR $d9f1`, table `$da04`)
   need the `$ab` countdown + `$81 & $3f == 0`, never reached in probe.

6. **Screenshot forensics (all three, re-derived 2026-10-04):**
   - **All 3 = REFLECT ON** (mirror 0.925/0.893/0.986 vs dup 0.623/0.725/
     0.729). Proof, not score: mirror windows sample the *same* PF cell
     and offsets (639-x maps cell j offset r → cell j offset 15-r…same
     set) → pure PF cannot mismatch there; a mismatch = non-mirrored
     object over an open cell. Reflect OFF would force dup=1.0 for pure
     PF — measured dup breaks exactly at asymmetric wall cells → ON with
     asymmetric rooms. **No reflect-OFF band exists** (band B of s2
     checked directly: duplicate region = real wall, patch = object).
   - **Mirror-mismatch = object detector** (under ON). Overlay
     visibility = cell open in that band + partner cell rule; PF walls
     always mirror-match.
   - Overlays found: s1 = ball 8 clks x240-271 (= probe clk60, `$a0`=61);
     s2 = 12-clk pair x64-111 (item 2); s3 = none. Plus non-mirrored
     sprites: hero = P1/GRP1 multicolor 8×13 (blue 112,199,255 /
     white / magenta / yellow / dark), X = `$9b`; enemies grey-green /
     orange / yellow.
   - Cave PF per band written ONCE at boundaries (lines 53-58 taper,
     96-97, 135-136, 175-178 taper; CTRLPF `$35` at 58/97/136),
     COLUPF shades $22/$24/$26 per band + accent $20 (line95/134),
     border gradients top $2a→$24, bottom $26→$2c. Three screenshots =
     three different rooms (band patterns differ; probe default room
     matches none — s1/s2 band B match probe `11110000000000000000`).
   - HUD band separate: CTRLPF `$30` (reflect OFF), grey bg, power bar
     = PF+ball at y260-269 (yellow (255,244,86) + red + orange
     separator).

**D6 constraint update (verified):** ball alone ≤2 cells (8 clks, as D6
says — under D7's grid = exactly **1 cell**); **two-object pair observed
= 12 clks (≤16 clks max) = ≤2 D7-cells at one x** — relax the cap if
Phase 3 wires M1 (exact 8+4 vs 8+8 split pending state repro). Color and
per-line gating constraints drop: HERO uses COLUPF auto-tracking and a
setup-line-only ENABL latch. O1 fallback unchanged.

## O2/D6 envelope (verified 2026-10-04, Stella TIA source + screenshots)

Ball capability, from Stella source (`src/emucore/tia/TIA.cxx`) and the
three screenshots:

- **Ball color = COLUPF only.** `TIA::poke` case `COLUPF` calls
  `myPlayfield.setColor(value); myBall.setColor(value);` — COLUP0/COLUP1
  pokes never touch the ball. Mid-line COLUPF writes apply immediately
  ("Playfield/ball color may have changed mid-line") → the ball
  auto-tracks per-band shades and accent lines (exactly what s1/s2 show:
  band `$24` + accent `$20` on every painted pixel).
- **PFP order (CTRLPF D2=1):** `PF → BL → P0/M0 → P1/M1 → BK`, and
  **D1 (score mode) is ignored** under D2=1 ("case Priority::pfp:
  CTRLPF D2=1, D1=ignored") → score mode can never corrupt cave colors.
  Ball hidden under real walls, visible over open cells.
- **Additive-only — CONFIRMED, user-accepted (2026-10-04).** The ball can
  ADD wall color over open mirror cells; it can never punch a hole: its
  only color register is COLUPF (not COLUBK), and under PFP it is behind
  real walls anyway. Score mode gives the ball no alternative color
  source either. Every HERO screenshot patch is additive (s1, s2).
- **Achievable shape per cave frame:**
  - ONE ball X for the whole frame (either half — paint lands at
    absolute x; D3's right-half patches position the ball on the right
    column, left half stays mirror-open → asymmetry both directions).
  - **Exactly 1 logical cell wide (8 clks)** under D7 — ball width =
    cell width; the parked M1 upgrade doubles the span to 2 cells
    (16 clks).
  - Per-band visibility via ENABL on band setup lines (D6 resolution;
    Phase 0 free window 14–15c ≥ ~6c block) → any band may or may not
    show the patch; a whole-cave latch (HERO, 2 writes/frame) only
    works when every open cell of column x in every band is patched or
    already wall.
  - **M1 upgrade path (parked):** second object → ≤16 clks / two
    columns (12 clks observed in s2); needs COLUP1 = wall-shade writes
    on the patched lines (probe default state writes enemy shading
    instead — mechanism unverified). Investigate only if content
    exceeds this envelope.
- **Convert guards (Phase 1, fail loudly):** reject subtractive patches
  (target open where mirror = wall), patches spanning >1 column-x, runs
  wider than the ball (1 cell; 2 with M1), and any patch whose ball-x
  would differ between bands. Editor paints outside the envelope →
  warn. Content that cannot fit → O1 revival (recorded fallback).

## Hot-death envelope fix (2026-10-05, user bug)

**Symptom (user, Stella):** player touching the M1 block on the hot band
was *blocked but never killed*; death came only after blasting (then from
`BombPlayerBlast`, ±1 col / any Y — by design, bomb drops at own feet).

**Root cause:** both overlay envelopes (`OvM1Block` `cmp/sbc #14`,
`PHMOverlay` `sbc #14`) modeled an 8px sprite span `[vl, vl+7]`, but
`PLAYER_WIDTH = 7` — lit span is `[vl, vl+6]` and the hot-rect box uses
`(vl+6)>>2`. Result: 1px dead zone. Block at M1X=71 (cols 16-17): sprite
flush at X=64 (vl=57) stopped 1px short of px64; kill required X=65
(vl=58), which the envelope rejected — `box max col ≤ 15 < rect.x 16` →
blocked, never hot.

**Fix:** envelope tightened `#14` → `#13` in all three sites (M1 test +
wrap guard, ball test); comments/header updated. Sprite now touches the
strip's first pixel exactly when the hot box first overlaps the hot rect
— parity with PF hot walls (die on the 1px-overlap proposal; stop pixel
for a cold block = X 64, same as a PF wall).

**Deliberately NOT changed:** moth-turn `sbc #14` (bank2 ~258 — moth
sprite width, separate object); ball overlay still returns C=1 without
the hot funnel (D6: ball strip never hot; ball/M1 envelopes disjoint for
model 0: ball needs vl ≥ 74, M1 ≤ 71). Ball-side hot rect emission
(convert `hot_m1` for side-1 patches) remains an open latent item —
model 1's `asym_patches` ball patch is cold today.

**Regression:** `tools/test_cell_map.py::hot_death_checks` — 1248 py65
sweeps (full X × both facings × 4 row pairs) asserting `Temp` b7 against
walk/M1-funnel × hot-rect overlap on `M0RoomRects` (both hot rects: the
'H' wall and the M1 block); spec fns (`m1_overlay_hit`, `overlay_hit`)
synced to the 7px span.

## Post-destroy hot-rect leak (2026-10-05, user bug 2)

**Symptom:** after blasting the M1 block, walking over where it stood
still killed the player.

**Root cause:** the walk-hit path reaches `HotOverlapBody`
unconditionally (player standing under the block: the landing proposal
`RoomY+1` straddles into the floor band, the floor cell under the block
is solid → walk hit → body). The body's parent gate was
`mask & BombPacked` — the M1 hot rect is emitted with mask `$00`
("never dies with a wall"), so it stayed live forever; `M1StripBlast`
sets only `EnemyDeadMask` b4, which the funnel honored (`.OvM1no`) but
the body never saw. Pre-destroy this was masked by the envelope (box
could not reach col 16 at the flush stop, X 64 → rect col test failed);
destroy removes the envelope → walk-in → landing proposal → death.

**Fix (bank2 `HotOverlapBody` gate, +10 B, body ends $FD6B < pin
$FDE1):** mask `$00` now gates on `EnemyDeadMask` b4 (dies with the
strip); any other mask keeps the old `BombPacked` wall-piece gate.

**Regression:** `hot_death_checks` now sweeps dead=$00 and dead=$10 —
2496 py65 cases. The dead=$10 pass reproduced the bug headless against
the pre-fix ROM (X=65 Y=90: b7=1 want 0) and passes post-fix.

## Player art 1-bit alignment fix (2026-10-05, user bug 3)

**Symptom:** player penetrates 2-4 px into the M1 block moving
left→right (rightward approach only).

**Root cause:** art bit alignment, not collision. TIA renders GRP
bit7 = leftmost; all four player frames (`PlayerSpriteA/B`,
`PlayerWalkA/B`) shipped with col7 (bit0) lit on body rows and col0
(bit7) empty = authored span **cols1-7**. Every consumer assumes
**cols0-6**: `PLAYER_WIDTH=7`, the walk box `[RoomX-7, RoomX-1]`,
`sbc PlayerDir` (mirror compensation), gotVL's reflected `+1` ("first
lit bit is column 1"), PHM `lit-left = arg-7`, the laser nose anchors.
Net: facing right (REFP0=0) the sprite renders 1 color clock right of
its collision box; at the flush stop X=64 col7 lands on px64 = the
block's first clock. 1 color clock = 2 TV pixels — matches the report.
Facing left the mirror flips the same error into a 2-clock gap
(not reported, same fix).

**Fix:** shift all 48 art bytes left 1 bit (cols1-7 → cols0-6, b0
clear everywhere). No label moved (byte counts unchanged → bank2 EQUs,
test_miner_colors address pins, $FDE7/$FDF3 walk pads all stable).
Comments made stale by the shift updated: jet B row 7 "+3 px vs A" →
"+1 px", walk boot cols (A: 2+6 / 1+6, B: 3+4). Laser nose anchor
`RoomX-3` left alone — post-shift face front is `RoomX-1`, so the
anchor sits 2 px behind the nose = the safe side (wall search starts
inside, never skips a flush wall); the `adc #4` beam spawn becomes 5 px
ahead of the nose instead of 4 (inside the 0/8/16 sweep phase, not
visible).

**Regression:** all 48 rows assert `byte & 1 == 0` (col7 empty); build
green (4×4096, pins held, wall-model sim OK); battery 19/20
(`test_editor_roundtrip` = pre-existing dirty-tree git gate).
`test_phase2_ball`'s golden TIA trace pins GRP0 values → baseline
regenerated with its documented recipe (HEAD banks + current kernel;
working bank1/2 restored byte-identical, verified by md5).

## M1 render off-by-one fix (2026-10-06, user bug 4)

**Symptom:** player sprite penetrates ~1 color clock (4 px) into the
M1 block moving left→right after the art fix (screenshot
`screenshots/assymetric/bug_adjust_collision.png`).

**Evidence (pixel-measured, scale `px = 4*clock - 3`, calibrated on 3
edges):** player sprite rendered `[57,63]` = contract at stop X=64
(`[A-7,A]`) — P0 correct. Block rendered `[63,70]` at staged M1X=71
but must cover PF strip cells 16-17 = `[64,71]`. Overlap = clock 63.

**Root cause:** Stella draws 8-wide missiles one clock left of the
player contract. Code path fully verified otherwise: ROM `M0M1X=$47`
(71) staged to `$8E` (runtime py65 probe: value intact at
`PositionBallM1`), `SetObjectXPos` same A/same routine/linear table
(A=71 → N=5, Y=-4 → landing 71). Player proves the contract; M1
pixels disagree by -1 = TIA missile-vs-player class offset, not a
staging/positioning bug.

**Fix:** `PositionBallM1` passes `staged+1` to `SetObjectXPos`
selector 3 (`clc / adc #1`, +3 B in the $F9C4 fill, VBL +4 c).
Staged `$8E` semantic unchanged (bank2 kill envelope / LWC re-read
ROM M1X). Ball selector 4 left alone — same offset unverified (no
screenshot of ball model). Laser M0 similarly unverified.

**Status:** user Stella-verified fixed (flush both facings). Open:
`test_phase3_ball` regressed 262/263 → **263/264** frame lines
(ball path + M1 path poked worst-case; +4 c in VBL crossed the
window). User decision 2026-10-06: **leave it** — known, not a
blocker. Battery otherwise 18/19 (`test_editor_roundtrip` = pre-existing
dirty-tree git gate).
