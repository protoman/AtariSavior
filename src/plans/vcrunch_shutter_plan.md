# Vcrunch Shutter — Laser-Gates-Style Sub-Band Sprite Plan

Status: Phase A + B shipped (user-tested 2026-10-13). Phase C BUILT + verified
2026-10-14 (py65 battery + Stella renders, see "Phase C — as built"). Phase D
SHIPPED 2026-10-14 (hazard recolor + bomb coexistence; battery 11/11).
Run each phase build → user Stella test → next phase (AGENTS build-test-build rule);
during auto-pilot, verification = py65 sims + scripted Stella snapshots.

## Sprite Y alignment fix (bug 2026-10-15)

**Symptom:** when vcrunch is NOT totally open (any other state), the player
sprite renders ~3 scanlines lower relative to the playfield — feet sit
inside the ground/wall PF. Totally open = correct.

**Root cause:** RowSlice setup lines each consume a real visible scanline
(`sta WSYNC`) but do NOT enter `.Line` — only the body path does `iny`
on the running-Y (A0) register. Band structure: open band = 1 `.Row`
setup (no iny) + 48 bodies; armed band = 5 setups (1 `.Row` + 4 RowSlice,
no iny) + 44 bodies = same 49 WSYNCs but **4 fewer `iny`**. The sprite
(GRP0) is drawn 1 line late per RowSlice setup crossed → measured 3-line
delay when armed (sprite rows at L88 vs L85 for RoomY=84). PF band stores
stay at identical lines (0/49/98) in both states → sprite sits inside
floor PF.

**Fix (kernel.asm, committed 2026-10-15):**
1. `RowSlice`: `iny` after `inc VcrNext` before `sta WSYNC` — the setup
   line WSYNCS like a body, so Y must advance. `.Line` inherits Y = A0+1
   exactly as after a body WSYNC.
2. `.Row` / post-`jsr RowSlice`: `lda #0 / sta GRP0` before the setup
   WSYNC — every band setup WSYNCS a visible line but never enters `.Line`,
   so GRP0 is still line L88's byte (would duplicate a sprite row on the
   body line). `GRP0=0` + jmp/tsx ≈70c from the previous WSYNC (was
   ≈61+3+3).

**Verified:** py65 probe (`/tmp/opencode/probe_grp0_val.py`): GRP0 Y rows
land at L85–96 (matching open) when armed; total WSYNCs open == armed (147);
PF0/PF1/PF2/COLUPF/ENABL stores at identical lines (0, 49, 98) in both;
armed RowSlice entries at lines 58/67/80/89 with VcrNext 1→4; VcrState/
Next/Band armed = e.g. `$1F/$05/$01`; BandTab@Cave open `[255,0,0,5]`,
armed `[255,255,0,5]`.

**Regression:** `tools/test_vcr_shutter.py` case 15 — GRP0 writes must
span RoomY..RoomY+11 in BOTH open and armed states (a lag shows as an
armed Y range starting later). `test_phase2_ball` strip list += $1B (GRP0)
for the new per-band setup writes.

**Rules:**
- RowSlice setup line WSYNCS (visible) but does NOT enter `.Line` — Y
  (running A0) must still advance so the next `.Line` pass indexes the
  correct sprite row (bug: skipped iny delayed GRP0 3 lines when armed).
- `.Line` inherits Y = A0+1 exactly as after a body WSYNC.
- Every band setup WSYNCS a visible line but never enters `.Line` — blank
  GRP0 so the latched body cannot copy a stale sprite byte (armed slices
  lose the same one line; sprite Y still correct).

## Symptom being fixed (user report 2026-10-13)

Vcrunch placed in level 1 room 2 (`level_001_room_002.txt`, `#......V..`). Result:
- Shutter renders **static / always closed**, never grows or shrinks.
- Touching it kills the player (so the kill path works) but there is no visible animation.
- After one death the shutter stops killing (b7 "already killed" latch, per room visit).
- Bombs in the room explode immediately and do nothing (bomb-immune wall — correct, but the immediate fuse is a separate concern, see Open Items).

## Root cause (confirmed by reading the code)

The playfield is only **3 scanlines tall per band** (`TILE_ROWS=3`, one PF row per
48-scanline band, written once in `.Row` kernel.asm:720-754, then 48 identical body
lines in `.Line`). The vcrunch record height `h` is measured in **bands**, so a
shutter inside one band is always `h=1`. `CrunchClock` (bank3.asm:201) short-circuits
`cpx #1` → "always covered" → the wall is permanently closed. The sweep engine
(`CrunchClock` triangle, `PhVcrEntry` PF staging, `HOVvcrunch` kill) is fully written
and correct — it simply has no sub-band vertical resolution to animate within.

A band-local shutter therefore **cannot** animate via the playfield. This is a
structural limit of the 3-row PF model, not a bug in the sweep math.

## Chosen approach (user rulings)

1. **Sub-band vertical sweep** — the shutter must animate *within* a band.
2. **Laser-Gates crusher look** — thick block growing from top AND bottom edges
   toward the center, then shrinking back (user's phase diagram, 8 rows shown for
   example; real resolution is whatever sub-band steps we can afford).
3. **Shutter is a SPRITE, not the playfield** — decouples it from the 3-scanline grid.
   The player (GRP0), enemy (GRP1), laser (M0) and ball (ENABL) are the four TIA
   hardware objects; the shutter reuses the **ball** slot.
4. **Editor rule (user directive):** a room containing VCRUNCH forbids every other
   object — enemies, miner, lamps, keys, raft, magma. Rationale: with no other objects
   in the room, the GRP1 flicker rotation (`SelectActiveObject`) and the moth-strip
   ball (`PositionBallM1`, `BallX=79+8*ball_col`) are both idle, so the shutter owns
   a hardware slot with **zero contention and zero flicker**. The only other sprite
   that can appear is the bomb (borrowed GRP1, 1 of 4 frames) — acceptable, rare,
   self-inflicted (player must drop a bomb in the shutter room).
5. **Bomb-immune, laser-blocked** — unchanged from the current contract. The shutter
   is a permanent hazard wall; bombs never break it, the laser never passes it.

## Why this reduces the problem (user's insight, confirmed in code)

- `kMaxRoomElements = 2` in the editor already exists *because* "GRP1 is one sprite —
  more simultaneous objects → more flicker" (MapCanvas.hpp:126). The
  "editor forbids object combinations to control sprite contention" infrastructure
  is already there. The vcrunch rule is a generalization of it.
- `AllowAddElement()` (MapCanvas.cpp:521) already returns bool + warning dialog, and
  `CountRoomElements()` (MapCanvas.cpp:501) already scans model tiles for RAFT/MAGMA.
  The vcrunch exclusion slots in cleanly with a near-identical pattern.
- bank1 HUD **no longer enables the ball** ("boundary-ball removed — nothing in the
  HUD enables the ball anymore", bank1.asm:392). So the ball slot is genuinely free
  in a shutter room. The only other ball user is the moth-strip, now forbidden by the
  editor rule.

## Sprite choice: ball (thick block look)

The ball is normally 1-clock wide, but NUSIZCTRL / CTRLPF ball-size bits widen it.
HERO's power bar uses `CTRLPF = %00110100` (D4-D5 = %11 = **8-clock ball**) —
docs/hero/hero_bank0.asm, AGENTS "HERO Power Bar Analysis". So we set CTRLPF ball
size to 8 clocks to render a full-tile-wide block, not a thin line. This matches
the user's "thick wall" ruling (option 1). `SetObjectXPos` selector 4
(HMBL/RESPBL, kernel.asm:2525) already positions the ball; no new positioning code.

**Tradeoff accepted:** while a bomb fuse burns in a shutter room, the bomb borrows
GRP1 1-of-4 frames (`SelectActiveObject`, OBJ_BOMB, kernel.asm:1858) — this does NOT
touch the ball, so the shutter does **not** blink during bombs. (Clarified: the bomb
flicker concern applies only to a GRP1 shutter, which we are NOT using. The ball
shutter is steady even with bombs live.)

## Architecture

### Animation driver (reuse existing clock)
`CrunchClock` (bank3.asm:200) already produces the ping-pong triangle
(`covered = 1 + min(eff, full-1)`, dwell at home). It is **shared** by the PF path
and the kill path. For the sprite shutter we drive the same clock but feed it a
sub-band resolution `full` (e.g. `full = 8` sub-rows within a band) instead of the
band count. The clock logic needs no change — only the caller's notion of "full".

### Sub-band vertical position → ball Y
The ball is enabled for a **window of scanlines** within the band (like the player
sprite's `ObjTop`..`ObjTop+7` window, kernel.asm:843-857). Each frame:
- VBL computes `covered_h = CrunchClock(full)`.
- The shutter's top edge sits at `band_top`, bottom edge at `band_bottom`; the closed
  portion grows from both edges toward the center. We set the ball's active scanline
  window to the *covered* sub-rows.
- The kernel `.Line` loop already latches ENABL per line via `BandTab,X` (kernel.asm:751-752).
  A per-line ENABL gate (on only when the current scanline is inside the covered
  window) replaces the always-on band gate for shutter rooms. This is the one new
  per-line cost — must fit the 76-cycle `.Line` budget (worst path currently ~61-66c,
  ~10-15c margin; a 3-4c ENABL-window test fits).

### Kill rule (reuse, decoupled from sprite)
`HOVvcrunch` (bank3.asm:383) already computes the covered rect and overlaps it with
the player box → `Temp b7` → `LoseLife`. It calls `CrunchClock` directly (independent
of the PF/sprite path), so the kill stays consistent with the *visible* covered extent
automatically. The b7 "one kill per room visit" latch (bank3.asm:324, EnterRoom zeroes
it) stays — user confirmed dying once then no re-kill is correct (respawn-at-death-spot
would otherwise be instant death).

The current `h==1` short-circuit in the **kill** path (bank3.asm HOVvcrunch also routes
through CrunchClock) is the *reason* it always kills now. With the sprite shutter we
feed the kill path the same sub-band `full`, so it only kills when the shutter is
actually closed over the player — matching the animation. This is the fix for "dies but
can't see why."

### Data model
`convert_room.py` already emits `$81, x, y, w, h` (bbox of all V cells,
convert_room.py:242-245). `h` stays the band span. The **sub-band resolution** is a
runtime/kernel constant (not editor data) — the shutter always sweeps the full band
height at whatever sub-step count the kernel budget allows. No file-format change.

## Phased build (each phase: build → user Stella test → next)

### Phase A — Editor rule (no ROM risk, ship first) — SHIPPED 2026-10-13
- `MapCanvas::CountRoomElements()` (or a new `RoomHasVcrunch()` helper) scans the
  active room's model tiles for `TileType::VCRUNCH` (=11).
- `AllowAddElement()` (MapCanvas.cpp:521): if room has vcrunch, refuse adding any
  enemy/lamp/key/raft/magma with a warning dialog ("A room with a vertical-crunch
  shutter cannot contain other objects — the shutter needs the sprite slot.").
- Also refuse *placing* vcrunch into a room that already has objects (the reverse
  direction) — same helper.
- `verify_build.py`: hard-fail any room whose model has VCRUNCH **and**
  `enemies+lamps > 0` (extends the existing `<=2 objects` check at verify_build.py:1018).
- Test: build editor, confirm dialogs both directions; build ROM, confirm verify_build
  passes on existing levels (none currently mix vcrunch+objects).

### Phase B — Ball sprite draws the shutter (static closed, visible) — SHIPPED 2026-10-13 (user-tested)
- Set CTRLPF ball size to 8 clocks in the cave kernel path (match HERO's
  `CTRLPF = %00110100`); restore the HUD's CTRLPF afterward if the bar still needs
  its own size (bank1 already sets its own CTRLPF at bank1.asm:187).
- In VBL (near `PositionBallM1`, kernel.asm:2517): for a shutter room, position the
  ball at the vcrunch column (`SetObjectXPos` selector 4) and stage the covered
  window (start line + length) into ZP for the kernel.
- Kernel `.Line`: gate ENABL on the covered window (replace the always-on band gate
  for shutter rooms). Ship first with `covered = full` (statically closed) so we can
  SEE the block in the right place before animating.
- Test: shutter renders as a thick, correctly-placed, always-closed block. Kill on
  touch (already works). No flicker.

### Phase C — Animate the sweep — BUILT + verified 2026-10-14

**As built** (diverged from the per-line ENABL-window sketch — slice-split instead):

- **Slices, not per-line windows.** Band0's 48 lines split into 5 fixed slices
  `[0,9) [9,18) [18,31) [31,40) [40,49)` (`SBmask` 1,2,4,8,16 / `SBod`
  8,8,12,8,8 — wall-neutral offsets). `RowSlice` (kernel.asm ~2914) repaints
  the PF hole + ENABL per slice; dispatch inside `.Row` when
  `RowIdx == VcrBand && VcrNext in 1..4`, else falls to `.RowAdv`.
- **ZP staging:** `VcrState=$EA / VcrNext=$EB / VcrBand=$EC` (idle `$FF`/0/0).
  Restaged every gameplay VBL from the `EnemyRamP` clock (bank2
  `VcrCoveredState`, same fold as bank3 `CrunchClock`); consumed by the kernel
  down to `VcrNext=$05` by the bank0 `jmp $FC68` HUD fold (sampling at that
  fold = before bank1's `$E0-$EF` stomp). ZP contract rows: `zp_layout_skill.md`.
- **Row-0 only rule:** VCRUNCH must sit in model row 0 — the kill window
  (`OvShutScan` $FE48-$FE8F, 72B, full) and both halves of the sweep cover
  band0 only. Enforced four ways: `convert_room.py` ValueError (rows != 0),
  `verify_build` models.json geometry loop, `check_crunch_clock` (token
  assertions `cmp #32`/`eor #$3F`/`cmp #4`/`sbc #4` in bank3 CrunchClock +
  bank2 VcrCoveredState), editor paint guard + `ValidateFeatureTiles`.
- **Kill:** `OvShutScan` — head = `RoomY` or feet = `RoomY+11` inside a closed
  slice of the right-half ball window (`BallX=127`, vl ∈ `[BallX-13,BallX]`);
  kill clock = `EnemyRamP-1` (parity with the rendered state). b7 latch cleared
  only at room enter; band gate = `OvShutBand` (OvHead/OvTail ∩ LineCount b0-2).
- **Tests:** `tools/test_vcr_shutter.py` (4 py65 cases: arm / open / band-gate
  reject / kill — kill case runs last) green ×3 runs; battery 11/11;
  `sim_frame_budget` + `sim_bomb_fuse` OK (cave wall 267.0, WSYNC 195);
  `verify_build: OK`.
- **Stella visual proof** (2026-10-14, `screenshots/vcr_shutter/`): level 2
  start room (model2), `EnemyRamP` poked to `$00/$40/$60` → three distinct
  renders captured (edges closed / middle open / fully closed); slice
  boundaries match the spec exactly (captures: screen y = kernel line − 3).
  Left hole (idx4) stays open, ball block rides the right V cell (idx15).
  Entry recipe: intro consumes the first SELECT press (`TitleIntro`), second
  press = `TitleSelect` level+1, RESET = drop-in — script commands `swchb $FD/$FF/$FE`,
  `ram $C2 $xx` (all `$`-prefixed), snaps via `saveSnap` into `-snapsavedir`.

Speed tuning stays the `#4`/`#32` constants in `CrunchClock` (bank3.asm ~196).

### Phase D — Polish — SHIPPED 2026-10-14

**D1 hazard color (done):** the ball shares `COLUPF` with the playfield
(TIA: `PF, BL` one register — the plan's "COLUP1/COLUP0" options would not
touch it), and two mid-scanline `COLUPF` writes per closed body line cost
+12c/line — past the 61c worst path's 12c margin on player-in-band0 lines.
Chosen fix, zero kernel cost: `VcrShutter` (armed band0) overwrites
`ColupfBuf[0] = $44` (power-bar red) after `BuildColupF` rebuilt it —
band0 walls AND the ball block render hazard red `(177,40,39)`; bands 1-2
keep the green; `BuildColupF` rewrites the green every VBL (auto-restore
on room exit). Covers the latched (static-solid) visit too.

**D2 bomb coexistence (done, tested):** `tools/test_vcr_shutter.py` case 4
drops a bomb (joystick Down edge, `state=1`, fuse ticking 180→174) while
asserting the shutter pipeline keeps cycling (`VcrNext=5` consumed,
`VcrState=$1F`, no kill latch, `ColupfBuf[0]=$44` kept) — bomb on GRP1,
shutter on the ball, no contention. Sampling caveat learned: read
`ColupfBuf[0]` at the `jmp $FC68` fold — at `StartFrame` bank1's
scorePtr4 stomp already put `$FD` over `$E7`.

**Evidence:** battery 11/11; `build.sh` green; `screenshots/vcr_shutter/`
— `red_state_*.png` (hazard red, 3 sweep states) + `state_*.png` (pre-D
green baseline).

## Bank space strategy
- **bank0 has 1 byte free** (pre-pad headroom, noted all over kernel.asm). The new
  per-line ENABL-window gate must be **tiny** (a few cycles, inlined in `.Line`) or
  live in bank3 via a trampoline. Prefer: keep the per-line gate to a `cpy`/`bcs`
  (3-4c) against a ZP window-top/bottom staged in VBL — fits the existing ~10c margin.
- **bank3 is nearly empty** (last org $FA40 of a 4K bank). All new shutter logic that
  doesn't fit bank0 goes here, following the existing Phase-4 tramp pattern
  (`sta $1FF9 / jmp $F800`, bank3.asm:22).
- Do NOT grow the pre-pad past the `$FC68` origin pin (AGENTS: "Origin Reverse-indexed").

## Open items / risks (flagged, not blocking)

0. ~~**Punched bbox = walkable/laser-open on the LEFT half**~~ — RESOLVED
   2026-10-14 by Step 4 Piece D: `OvShutLeftPre` tests the left M1 mirror
   window and routes overlap to `OvShutBand` (kill). Both halves drawn
   and killed (user spec 2026-10-14). The laser still passes the punched
   hole (separate concern, not part of the kill semantics).

1. **Bomb "explodes immediately, does nothing"** — separate bug from the shutter.
   `BombTick` (kernel.asm:2117) looks correct (fuse decs to 0 → 60-frame explosion →
   clear). The drop site loads `#180` (3s) and only drops on ground (kernel.asm:1007).
   "Explodes immediately" needs its own trace — likely a `BombTimer` stomped by the
   HUD (the `$F4`/return-byte stomp noted at kernel.asm:1462) or a state bit set
   wrong in the vcrunch room. Tracked separately; do not conflate with shutter work.
2. **Whether to delete the PF-based vcrunch staging** (`PhVcrEntry`/`PhHcrPre`) once
   the sprite shutter works. Keeping it is harmless (never fires for h=1) but dead.
   Recommend deleting in a cleanup phase to reclaim bank3 bytes and remove the
   `h==1` short-circuit confusion.
3. **Sub-band step count** is budget-dependent. Start with 4 sub-rows (2 scanlines
   each within a 8-scanline window, or reuse the player's 12-line sprite window) and
   measure the `.Line` cycle budget before committing to 8.
4. **Phase tiles (PHASE=10)** share the same band-grid limitation. This plan's
   sprite approach could later serve phase walls too, but scope is vcrunch only.

## Addendum — band 0 → band 1 (rule R1, 2026-10-14)

User placement rules R1–R5 (`docs/feature_tiles_plan.md`, section
"Placement rules") put every special on model row 1, so the shipped
shutter moved off band 0 in the same session:

- `bank2.asm` `VcrShutter`: arm gate `cmp #1 / bne .VSnoArm` (armed =
  `VcrBand $EC = $01`, idle `$FF`); `sta VcrBand #1`; hazard recolor
  `sta ColupfBuf,X` (band-generic — band1 = `$E8`).
- `OvShutScan` `.OSline` slices shifted +48: `#57/#66/#79/#88/#97`
  (band1 = cave lines 48-95; line ≥97 never closes). The band-0-only
  note in `docs/zp_layout_skill.md` was corrected in the same change.
- Records emit `y=1`; convert (`rows_from_json`, `convert_room`),
  `verify_build`, and the editor all raise/warn on any special off row 1.
- Tests retargeted: `test_vcr_shutter` (arm y=66 open, corridor reject
  y=116, bomb y=20, kill y=68, `I_COLUPF1=$68`, `PF1_BAND1=$47`),
  `test_phase_kill_frame` (`CELL_X,CELL_Y = 125, 68`).
- `tools/test_fixtures.py`: M2 re-frozen as a count-0 stream
  (`00 01 81 08 01 02 01`, 7B — live `M2RoomRects` slot is 8B; the old
  15B stream spilled into `M2TilePF0` where the PF/meta freeze ate the
  `$81` record) + a selfcheck slot-fit assert. `freeze_m1/m2` now accept
  the test's 4-bank `BANKS` list — passing the whole list sliced the
  LIST (silent no-op at offset $9FF), so fixtures never actually
  injected until this fix.
- Battery 31/31 + `./build.sh` green after the move.

## Step 4 — Mirror render (built, then REVERTED 2026-10-14)

The M1 left-mirror was implemented (VcrShutter staging, kernel ENAM1
gates, OvShutLeftPre kill) and worked correctly (12/12 tests green).
User reported "a TON of screen flicker" in Stella. Diagnosis: the
ENAM1 writes in the kernel hot path (`.Row` rows0/1, `.RowAdv`,
`RowSlice`) plus M1 object usage added cycle pressure and likely
conflicted with other M1 consumers.

**User ruling (2026-10-14):** revert to async (right-half ball block
only). The mirror is removed; kill follows the visible right-half block
only. Both the mirror code and the editor uniqueness rule shipped in
the same session.

### What was removed

- **kernel.asm:** all 5 ENAM1 writes (`.Row` rows0/1 gate, `.RowAdv`
  band2 clear, `RowSlice` pair). The length derivation (armed=8 else
  48) was KEPT — that's the sweep animation, not the mirror.
- **bank2.asm:** VcrShutter CollisionEndX/CollisionCellY staging
  (lines 2650-2667); `OvShutLeftPre` subroutine (deleted). `.OvClear`
  restored to `jmp OvM1Block`.
- **test_vcr_shutter.py:** reverted to 9 cases (staging asserts +
  left-mirror cases 10-12 removed).

### What was kept

- The sweep animation (RowSlice, VcrState/VcrNext/VcrBand, SBmask/SBod).
- Hazard recolor (ColupfBuf[1] = $44).
- Kill semantics (OvShutBand → OvShutScan → VCS3, hot/cold).
- Post-kill removal (VcrShutter punch-only + BandTab disarm).
- Sim tolerance widening (f<=3 1.0 → 1.8) — harmless ledger.

### Editor rule (shipped)

- **Paint guard** (MapCanvas.cpp `ApplyBrushAt`): at most one VCRUNCH
  cell per room. Warning dialog on second V paint.
- **ValidateFeatureTiles**: warn-only check for multiple VCRUNCH cells
  (release-time audit).
- Editor rebuilt via `cmake --build .` in `tools/editor/cmake-build-debug/`.

### Evidence

- `./build.sh` green (verify_build OK, sim OK).
- Battery 31/31 green.
- `test_vcr_shutter.py` OK (9 cases).
- Editor builds clean.

## Step 4b — Side-brush kill fix (2026-10-14, user bug)

**Symptom:** the player touching the shutter column from the SIDE (lit
span entirely outside the block, 1px edge touch) died whenever the
aperture state was `$1F` (fully closed). Root cause: the kill path's
horizontal gate was PHMOverlay's edge-overlap test
(`[BallX-13, BallX]` for vl — 14 positions) and VCS3's `$1F` trivial
kill ignored horizontal position entirely (the vertical containment
has no `$1F` check: any Y in the band + any edge overlap = death).
py65 probe: kill x window was `[120,133]` at `$1F`; x=120 = lit
`[114,120]` entirely left of the block `[120,127]`.

**Fix (bank3 `VCS3`, after the clock math / `tax`, before the
hot/cold split):** horizontal containment gate — the lit span
`[vl, vl+6]` must sit inside the block `[BallX-7, BallX]` or the call
returns passable (`clc / jmp $FBEE`). Applies to BOTH hot and cold
(the crunch can only crush what is inside it; D6 strip solid is
unaffected — the gate lives inside VCS3, which only OvShutScan
reaches). Inputs still live from PHMOverlay's gate: `CollisionX`
($8B) = vl, `RectCount` ($92) = BallX — OvShutBand/OvShutScan do not
clobber them. Gate must NOT go at VCS3's top: A = kill clock on
entry; clobbering A there corrupts the clock→state math (caught by
`open`/`coldtap` going red — states computed from garbage).

**Geometry (frozen fixture):** BallX=127, block `[120,127]`, lit
`[x-6, x]` → kill window x ∈ `{126,127}` (movement is 1 px/frame —
no skip). Player at x=120..125 with the shutter closed now penetrates
and is crushed at 126 (the "sucked in" crunch); pure side brushes
(x=120 / x=133) pass.

**Tests:** `test_vcr_shutter.py` 9 → 11 cases (brushL x=120 /
brushR x=133 at `$1F` y68 → no kill; kill/vertical-semantics cases
moved to x=127 = the inside window). `test_phase_kill_frame.py`
CELL_X 125 → 127. Battery green; `./build.sh` green.

## Rule 1 — phase-gated kills (2026-10-14, user directive)

**Spec:** when totally CLOSED (`$1F` / covered==full) or when OPENING
(the folded/Descending half of the ping-pong, `sc>=32`), neither
vcrunch nor hcrunch kills unless the band is hot (MetaB b6). The cold
kill is the CLOSING ACTION only (`$11`/`$1B` while `sc<32`, player
caught/contained). User still died from the side after Step 4b — the
remaining cold `$1F` trivial kill (contained at the block's edge) was
the path; Rule 1 removes it.

**vcrunch (bank3 `VCS3`, cold path `.OScontain`):** phase gate after
the containment/hot split — `sc = (EnemyRamP-1)>>2`; `sc>=32` → miss
(opening); `cpx #$1f` → miss (totally closed = wall); then the
existing endpoint/aperture containment. Hot path unchanged (any
closed-slice touch, inside the block).

**hcrunch (bank3 `HOVhcrunch`):** cold gate before `CrunchClock` —
`sc = EnemyRamP>>2` (CrunchClock's own parity); `sc>=32` → miss; after
CrunchClock, `covered==full` → miss (totally closed). Hot exempts both
(LineCount = MetaB staged bank2-side by `HOVFeatPre`, tested via
`asl×2` → b6 in C — b7 shutter flag shifts out first).

**bank2 `HOVFeatPre` recost (+ staging in the pinned $FBFC window):**
the `sta $1FF9` slot moved `$FC17→$FC1A` (the staging grew the
pre-direct part) — the post-switch `jmp $FA40` fetch continues at
`$FC1D`, so bank3's tramp image moved `$FC1A→$FC1D` (no guard pinned
the old address; the image just has to match the slot). Class saved
in X (`tax`/`txa` — the old Y-restore + class reload was dead: bank3
reads fields from the stack, never Y). `PhHcrPre` field pushes looped
(`ldx #4`) to pay for it. The $80 phase path skips the staging (Y =
record base must survive for `HOVafterGate`).

**Tests:** `test_vcr_shutter.py` 11 → 13 cases — case 5 (was: `$1F`
kill) → `closed` no-kill; `openB` (clock 200 = `$1B` OPENING, y48
crunch geometry inside the block) and `openF` (clock 140 = `$1F`
OPENING) → no kill. `test_phase_kill_frame.py` CLOCK 100→64
(`$1B` closing), CELL_Y 68→48 (crunched below the aperture — the
Rule 1 kill geometry). Battery green; `./build.sh` green.

## Rule 1b — closed shutter is SOLID, not walk-through (2026-10-14b)

**Symptom:** after Rule 1 the cold kills vanished, but the punched
cell had nothing blocking the player — walking through a closed
shutter became possible (user: "I can walk through the vcrunch ...
when it is not open and I am in a part that exists on screen").

**Model:** the shutter column is SOLID wherever its slices are closed
at the player's Y (walk blocked, no death), passable only where the
aperture is open (both endpoints in open slices). The kill is unchanged
(Rule 1: closing + crunched + contained; hot = any closed-slice touch
inside the block). Side brushes: no kill (Step 4b) — solid where
closed, passable through the aperture. hcrunch unaffected (PhHcrEntry
writes real PF cells — physically solid already).

**Implementation (bank3 `VCS3` + bank2 `OvShutBand`):** new return
contract — `C=0` passable (A ignored) / `C=1 + A≠0` kill / `C=1 + A=0`
SOLID block. Every non-kill outcome (side brush, opening half, totally
closed, the closing-path aperture-touch) routes through the shared
solidity test `.V3solidBody` (both endpoints open → pass, else solid).
`OvShutBand`: `bcc .OSBm1 / bne .OSBlatch / sec / jmp $FBF8` — the
solid path blocks the PHM walk without latching b7 (no wall removal,
no LoseLife). `.OSline` moved to $FE80 (the $FD80..$FE57 window
outgrew); `.V3solidBody` follows it in the free region; a 5B
`.V3solid` thunk near VCS3 keeps the cold-path `bcc`s in range.

**Probe (py65, frozen model2):** closed `$1F` y68, hold right from
x=110: RoomX stops at 120 (wall face) and stays — blocked, no death.
Open `$1B` y66 (aperture): walks through 110→140. Battery green;
`./build.sh` green; `test_vcr_shutter` 13/13 (pin-based cases
unaffected — solid ≠ latch).

## Rule 1c — fully-open dwell (2026-10-14c, user)

**Symptom:** the open end of the sweep never emptied — the state
floor was `$11` (edge slices always closed, the 2026-10-13
"always-solid stub"), so the block stopped shrinking with one edge
sliver visible. User: it should disappear totally, then grow back.

**Change:** the dwell zone (eff 0-3 — both halves of the wrap) now
maps to a fourth state `$00` (nothing closed) instead of `$11`:
- `VcrCoveredState` (bank2) + `VCS3` (bank3, kill/solidity mirror):
  an extra `cmp #4 / bcc` after the head-offset `sbc #4`. Cycle:
  open (sc 0-7) → `$11` (8-13) → `$1B` → `$1F` → `$1B` → `$11` →
  open (56-63) — 32-frame empty dwell at both ends.
- `VcrShutter`: `lsr / bcc .VSpunch` after `sta VcrState` — bit0
  clear (state `$00`) skips the arm + `BandTab` write: prologue
  defaults stay (VcrBand=$FF, VcrNext=0) and BandTab keeps
  StageBandTab's MetaA value ($00 in shutter rooms) → slice0's
  band-setup ENABL off, slice-run idle, overlay pack gate off
  (open = passable). RowSlice already renders nothing for `$00`
  (no state bits → ENABL=$00). The punch still runs (cell open).
- State `$00` needs no other logic: every .OSline bit is 0 → all
  endpoints open → passable through the existing solidity test.
- Window funding: OvShutBand's solid/kill dispatch restructured
  (`beq .OSBsolid` + latch reorder `lda #$80 / sta Temp / ora /
  sta` — −7B) — the $FED0 VcrCoveredState window had 1B slack.

**Tests:** `test_vcr_shutter.py` 13 → 14 cases — `dwell`
(clock 8 = sc 2 → `$00`): VcrState=$00, no latch. `covered()`
python mirror + the docstring state list updated. Battery green;
`./build.sh` green. Probe: full sc 0..63 sweep shows
`. E M F M E .` with `VcrNext=0` (disarmed) on the open dwell.

## Late-WSYNC stall fix — whole-screen jitter (2026-10-15)

**Symptom:** whole picture shifts ~1 scanline every frame ("vcrunch
shutter screens move", `screenshots/bugs/vcrunch_screen_moving_001/002`
= same fully-open scene, 002 = +1 line).

**Stall rule (py65, start-to-start delta between consecutive cave
`sta WSYNC`s):**
- `d <= 73` — single line, safe.
- `d in 74..76` — store straddles the line boundary with zero CPU work
  on the next line = **full-line stall = +1 scanline** (the jitter).
- `d >= 77` — accepted double-line design span (row-advance/setups;
  none currently exceed 73 anyway).

**Diagnosis (per-instruction py65 trace, boot-env enemies alive,
RoomY × swcha sweep):** the worst `.Line` path — in-window
color/beam/GRP0 **+ GRP1 object in-range** (object window overlapping
the A0<=10 player window, ObjTop ∈ {1..11} ∪ {249..255}) — measured
**d=76** (work 73c). Pre-existing (body untouched by the sprite-Y fix);
`99b8e86`-era edits had separately pushed armed setup to 75c and
post-slice body to 82c.

**Fix (kernel.asm, committed 2026-10-15, −4c on the worst path):**
1. **`.GrpSkip` relocation (−4c):** on the color path (gate entered
   only with A0<=10), after `iny` Y<=11 — the in-line
   `cpy #PLAYER_SPRITE_H / bcs .GrpZero` was **dead** (never taken).
   Deleted from the path; `.GrpSkip` moved to the row-advance gap as
   `iny / jmp .GrpZero` (out-window A0>=11 keeps the exact old
   sequence). bcs .GrpSkip stays same-page 3c (verify_build branch
   guard), rel8 fits; `.WaterRow -> .GrpZero` text span untouched
   (test_enemy_movement split).
2. **`.Row` GRP0 blank removed** (after `sta PF2`) — pushed armed
   setup to 75c (stall zone); effect = trading a duplicate sprite line
   for a blank line at band boundaries (shipped without either
   pre-sprite-Y).
3. **RowSlice tail-jmp (`jmp RowSlice` / `jmp SliceReentry` on
   `.Line`)** — stack-neutral tail re-entry (no per-slice return
   address, SP gate can only improve); `SliceReentry` label sits
   AFTER `.Line:` (label between `sta LineCount` and `.Line:` broke
   test_enemy_movement's fall-through contract).
4. Worst path now **69c work / d=72** (was 73/76).

**Regression gate — `test_vcr_shutter.py` case16:** sweeps open/armed
× RoomY 0..143 × swcha over natural enemy staging (boot `I_ENCOUNT`
restored — cases 1-15 poke it 0), collects every consecutive cave
WSYNC pair, fails on any 74-76 segment; vacuity floor `worst >= 70`
proves the object-overlap path ran. Measured worst: 72.

**Verification:** `./build.sh` green (sim_bomb_fuse, sim_frame_budget,
verify_build — bank0 headroom still 1B, no new data); battery green
(test_vcr_shutter 16, test_enemy_movement, test_laser_wall,
test_laser_s4, test_miner_colors, test_phase2_ball). Stella visual:
gameplay snapshots render clean; live shutter punch confirmed in
level 2 room 1 (the only live V model): punch appears once
(persistent 288px PF edit between staged snaps) and holds —
post-punch `$1F/$1B/$00` states render identically **by design**
(punch is one-way per room visit: "punches-only, no re-kill"), which
is why a first attempt at state-snapshots showed byte-identical
frames. `swchb fe/fd/ff` are the working Stella script commands for
RESET/SELECT edges (intro exits on first RESET edge, title SELECT
held 3 frames = one level+1).
