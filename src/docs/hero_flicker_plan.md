# No-Flicker Objects Plan — implement hero_flicker.md (2026-10-01)

Spec: `docs/hero_flicker.md` conclusion — HERO does NOT rotate objects between
frames. Every visible object renders EVERY frame; one hardware register is
reused across Y bands by mid-frame `RESP`/`HMOVE` repositioning, extra objects
use missiles/ball. Our `SelectActiveObject` frame rotation
(`kernel.asm:1842`, `FlickerFrame` $B4) is exactly what HERO avoids.

Rule: build-test-build. Each step = `./build.sh` green + user validates in
Stella before the next step starts. Budgets are measured from `bank0.lst`,
never from comments.

---

## Current state (verified)

| Fact | Where |
|------|-------|
| One GRP1 slot, rotated across `FlickerFrame` 0..N-1 (bomb only 1 of 4 frames) | `SelectActiveObject` `kernel.asm:1850` |
| Slots = enemies + miner (+bomb), N ≤ 4; `kMaxRoomElements=3`, 1 element/room-row → **entities never share a band** | `zp_layout_skill.md` rule 3, editor |
| Kernel `.Line` renders one object window `ObjTop..ObjTop+7`, no `jsr` in body (running-Y) | `kernel.asm:627-695`, worst body 61c, WSYNC @c69 |
| Positioning: `SetObjectXPos` = `sta WSYNC` + div15 (5c/15clk, single page `$FF10-$FF1F`) + `HMP0,X`/`RESP0,X` — **no HMOVE inside**; HMOVE applied once in VBLANK `kernel.asm:521-522` | `kernel.asm:3254` |
| Double-HMOVE already bit us once (stale HMP1 / doubled P0 fine) | `kernel.asm:457-459` |
| Cave `CTRLPF=$05` (reflect+priority), set once at init `kernel.asm:417`; ball width bits unused in cave; `ENABL` forced 0 at kernel entry `kernel.asm:583` | |
| `ENAM0` laser proves per-line missile enable works in `.Line` | `kernel.asm:658-665` |
| M1 (`$1E`) unused in cave; ball free in cave (HUD ball only in HUD band) | |
| ZP **full** — no free sequential byte; freed bytes must be reuse-in-place | `zp_layout_skill.md` |
| Stack: kernel already uses `.WaterRow` jsr; one more jsr level inside kernel = SP $FD, guard floor $F8 | AGENTS stack guard |
| Editor/convert guarantees: ≤3 elements, ≤1 per room-row; `EnemyRamX` 3 slots | |

## Related finding (do NOT mix into this plan's steps)

Band-transition split line (the blinking thin yellow line in
`screenshots/bug_hot_wall.png`): `.Row`'s PF0/1/2 + COLUPF stores execute
~33-60 CPU cycles after the previous WSYNC = **inside the visible zone**, so
the transition scanline renders left half = OLD band, right half = NEW band
with OLD band's color until the COLUPF store (~clock 111). At row1→row2 in a
hot room old color = pulsing yellow over row2's PF2=$3f mirror (x351-446) →
the visible line. Same mechanism exists at every band boundary (row0→row1 is
green-on-green → invisible). A full fix needs the whole row-advance+PF setup
inside HBLANK (≤22.7c) which the current 28c advance + ~35c stores cannot
reach — treat as its own investigation, NOT a flicker step.

---

## Target architecture

1. **P1 = cave entities, no rotation.** One entity per band (editor rule).
   VBLANK builds a per-band descriptor {slot id, X, Y, ObjBase, color}.
   Each band positions P1 once, mid-frame, with the SAME `SetObjectXPos`
   (identical bytes → identical pixel/collision mapping as the VBLANK path).
2. **Bomb → BALL.** Position once in VBLANK (`RESBL` path via X=2 selector —
   extend `SetObjectXPos`), render its 8-line window by per-line `ENABL`
   writes in `.Line` (same pattern as laser `ENAM0`). No mid-frame
   positioning, no collision changes (bomb has no CX gameplay today).
   Ball width via CTRLPF bits (same encoding HUD already uses for the power
   bar — verify value against TIA doc in step F4, do not guess).
3. **Lamp stays an "enemy" P1 slot** (it already is type 5 in `EnemyCount`).
   M1 stays unused (YAGNI).
4. **Delete rotation**: `FlickerFrame`, slot modulo, bomb 1-of-4 gating.

Fallbacks (decided in F1, before any kernel rewrite):
- **F1 fail (positioning does not fit the line budget):** keep `SelectActiveObject`
  rotation for entities, but move bomb to BALL (removes bomb-vs-entity
  flicker) — partial win, no kernel line changes.
- **Positioning-line spill** (worst X=159 returns at cycle ~76): options in
  order — (a) pre-`sec` before `jsr` and shave 2c inside the routine's
  kernel variant, (b) dedicate 2 lines per band and take the body line from
  48→47 (band total unchanged), (c) split coarse (RESP-only on one line) /
  fine (HMOVE next line).

---

## Line/cycle budget for mid-frame positioning (the hard constraint)

A `SetObjectXPos` call inside the cave costs:
- caller line L tail: pre-work (descriptor fetch, ≤~30c) + `jsr` (6c) +
  routine's `sta WSYNC` (3c) → line L ends;
- line L+1: `sec` + div15 (≤11 iters ≈ 54c) + `tay/lda/sta HMP/sta RESP`
  (13c) + `rts` (6c) ≈ 73-76c for X≥150 — **must end ≤c73** so the caller's
  next `sta WSYNC` lands on the same line; if it spills, line L+2 is
  consumed by WSYNC = +1 scanline/band = 265-line frames = forbidden;
- caller L+2: normal body from c0.

Band line accounting must stay identical: each band gives up ONE existing
body line as the positioning line (`setup + 48 bodies` → `setup +
positioning + 47 bodies`). Frame stays 262. Every `.Line` path must keep
`sta WSYNC` write ≤ c73 — recount from `bank0.lst` after each kernel edit
(AGENTS: never trust comment cycle counts).

HMOVE ordering (double-HMOVE lesson `kernel.asm:457`):
1. VBLANK: position P0 + P1-fallback + BALL, single `sta HMOVE` (existing),
2. then **`sta HMCLR`** (or write 0 to each HMP) so later HMOVEs are no-ops
   for them,
3. mid-frame: write `HMP1` inside `SetObjectXPos`, then `sta HMOVE` in the
   HBLANK of the line after positioning (P0/HMP0 now 0 → unaffected),
4. `HMCLR` again after, so the next frame's VBLANK HMOVE starts clean.

Collision: entities stay on P1 → `CXP1FB`/`CXPPMM` paths unchanged. Ball
only for the bomb (no CX gameplay). If a future object moves to M1/ball with
gameplay collision, route `CXM0FB/CXP0FB` in the same step.

---

## Steps

### F0 — Baseline (no code change)
- Screenshot a 3-element room; note which objects flicker and at what rate
  (`FlickerFrame` modulo N). Record frame length 262 (`Scn Ln` right box
  after a frame boundary) and min SP.
- Re-verify editor guarantee in data: every room's elements occupy distinct
  rows (`convert_level` / emitted level asm). Assert exists in
  `verify_build` (enemies+lamps ≤3) — extend later in F7 if needed.

### F1 — Feasibility spike: ONE mid-frame P1 position (gate for everything)
- Add kernel-callable `SetObjectXPosK` (byte-identical to
  `SetObjectXPos` except tail handling; MUST stay in `$FF10-$FF1F`/single
  page — verify_build guard already pins it) and use it on exactly ONE band
  (band 0), replacing one body line.
- Pre-work on line L: reload existing single-object descriptor (reuse
  current `SelectActiveObject` output — no new descriptors yet).
- Add `HMCLR` after VBLANK's HMOVE (step list above) — alone this is
  already a correctness fix candidate; test player position unchanged.
- Verify: `./build.sh`; Stella: frame still 262 with 0/1/2/3 objects and
  all X (test X<15, X≈80, X≥150 — right-edge object must not drift;
  compare against `SetObjectXPos` VBLANK pixel position from
  sprite_bug_investigation method); player collision with walls unchanged
  (walk into thin wall at col 17); WSYNC write ≤c73 on every path
  (`bank0.lst` recount + `breakLabel` timing if needed).
- **Decision point:** pass → F2; fail → fallback F1 (bomb→ball only).

### F2 — VBLANK band descriptors (staging only, no render change)
- Replace rotation bookkeeping with: for each band 0-2, store slot id
  (0=none, 1=miner, 2+ = enemy index+1) — **3 bytes, reuse-in-place**:
  `FlickerFrame` ($B4), `ObjBot` ($BC, write-only/no readers), `EnemyIndex`
  ($B9 scratch after use). Document aliases in `zp_layout_skill.md`.
- Descriptor build still reads live `EnemyRamX/EnemyRamY`, `MinerX/Y`,
  `IsRoomDark`, `EnemyColorTable`, `ObjSpriteOffTable` (all existing).
- Keep kernel reading the OLD single-object path this step (staged values
  unused) → zero visual change. `./build.sh` + sim green; user smoke test.

### F3 — Kernel consumes descriptors band by band
- In `.Row`: load band K's descriptor (ObjBase, ObjTop rel to RoomY,
  color, X) into the existing `ObjBase/ObjTop/COLUP1` slots; positioning
  line per band (from F1) repositions P1 before the object window.
- Object window may cross a band boundary (Y near row edge, sprite 12px):
  position line = line BEFORE window start, even if that belongs to the
  previous band; if the window would start above the previous band's
  positioning capacity, clamp/skip and log (editor test case: element Y at
  row edge).
- Do band 0 only first → user test (object in row 0 solid, X correct,
  collision correct). Then band 1, then band 2 (one commit-sized step
  each, same checks).
- Cycle recount after EACH band: worst `.Line` (player in window + object
  in window) ≤c73 WSYNC; band totals unchanged.

### F4 — Bomb on BALL
- No `SetObjectXPos` change needed: selector already offsets from
  `HMP0/RESP0` (`kernel.asm:3262-3263`) — X=4 addresses `HMBL` ($24) /
  `RESBL` ($14), same as X=2 already does `HMM0`/`RESM0`
  (`kernel.asm:3358`). Call with X=4; verify_build page guard untouched.
- VBLANK: position ball at `BombX` (account for visible-left offset like
  `BombMarkWalls` does, `kernel.asm:2262-2272` — reuse that derivation).
- `.Line`: `ENABL` per line for the bomb window (pattern = laser `ENAM0`,
  table-driven; bomb 8 lines tall, same trick as `BeamMask`).
- CTRLPF: set ball-width bits for the cave; restore after HUD (HUD writes
  CTRLPF at `bank1.asm:135/635`) — add CTRLPF to the kernel-entry reset
  block (`kernel.asm:568-583`) if not already covered.
- Remove bomb from `SelectActiveObject` (bomb 1-of-4 gating becomes dead).
- Verify: fuse countdown visible every frame (no blink), bomb falls at
  BombX, explosion still `state=2` path, frame 262.

### F5 — Delete rotation
- Remove `FlickerFrame` inc/modulo, slot walk, `.SOEnemySkip` dead paths;
  `SelectActiveObject` becomes `BuildBandDescriptors` (name change OK).
- Reuse the freed ROM for descriptor build; bank0 pre-pad headroom is 1
  byte — if it overflows `$FC68`, move a leaf helper after `org $FC70`
  (AGENTS "Origin Reverse-indexed" rule), never the fold pads.
- `./build.sh` green, sim green, full Stella smoke (dark room: lamp color
  path still applies to P1; tentacle/`PlayerHitsMap` X-preserve lesson
  still holds — no changes there).

### F6 — Guards + docs
- `verify_build.py`: (a) `.Div15Loop` page contract still holds with the
  selector; (b) band line counts (setup+positioning+bodies per band) sum to
  the old total — count `sta WSYNC` sites per band before/after; (c) no
  `FlickerFrame` symbol remains.
- Update `zp_layout_skill.md` (reuse-in-place of $B4/$BC/$B9) and AGENTS
  "What we have NOT yet implemented" (drop the SelectActiveObject
  revisit item, add mid-frame P1 reposition to the "what we use" list).
- Optional assert: emitted rooms keep ≤1 element per row (already three
  ways; add the 4th only if F3 finds a violating room).

---

## Risks

| Risk | Mitigation |
|------|------------|
| Positioning line overruns → 263+ line frames (the documented flicker class) | F1 gate before any rewrite; spill fallbacks; frame-length check every step |
| Pixel/collision misalignment (2026-09-21 class) | Same `SetObjectXPos` bytes; page guard; wall-touch test at col 17 each band step |
| Double HMOVE / stale HMP (2026-09-26 class) | Explicit HMCLR ordering above; player position A/B test in F1 |
| ZP exhaustion | Reuse-in-place only ($B4/$BC/$B9); aliases documented |
| Object window crossing band boundary gets cut | Position-before-window rule + edge-Y test case in F3 |
| Stack depth | One jsr level in kernel ($FD), guard $F8 — no nested jsr in `.Line` |
| Ball width / CTRLPF guess wrong | Copy encoding HUD's proven power-bar value; verify vs TIA doc in F4 |
| Bank0 pre-pad (1 byte left) | Move leaf after `$FC70`, never fold pads |

## Out of scope
- Band-transition split line fix (separate investigation, see above).
- 13+2 HUD technique work (bank1, already partly present).
- Same-band entity conflicts (impossible under editor rule; if a data file
  violates it, fix the data).
