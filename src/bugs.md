# Known Bugs & Deferred Items

Catch-all list of small issues left behind while shipping features.
Cadence (user decision 2026-10-06): implement a few features, then stop
and do a complete rescan — sometimes a redesign — of everything here at
once. Date each entry; close with a one-line fix note when done.

Info lines per entry (added 2026-10-07, user request): **Player:** what
someone running the game sees today; **Benefit:** what the fix gives them.
No entry is worked on without user greenlight.

## Open bugs

1. **sim_frame_budget f3 transition frame off 263** (filed 2026-10-06 as
   263.20; re-measured 2026-10-09 as 262.72 — sign flipped when the
   title flow re-phased, same ±56c wall-phase slack family).
   **Status: ANALYZED 2026-10-09 — no player-visible effect; the
   `_wall_bad` ±0.35 exception stays (filing said ±0.25).**
   Root cause (py65 sub-segment probe: marks at StartFrame /
   VBLTimer / .WaitVBLANK / .Row|TitleKernel / Overscan): title and
   cave are two self-consistent sub-line phase loops — title starts at
   phase 65c (entry 173c), cave at 45c (entry 193c). The entire −21c
   sits in entry (StartFrame→VBLTimer) = first VSYNC WSYNC stall
   (76−phase: 10c vs 31c); f3 runs title's entry + cave's pinned rest
   (vblwork/ker/over all cave-equal on f3) → structurally short; the
   cave loop re-locks itself by f6, no downstream effect (VBL poll,
   overscan absorb, SP all normal).
   Flicker impossible: frame line count = boundary crossings
   floor(end/76)−floor(start/76) — f3 = 1348−1085 = **263 lines**
   (start phase 66c ≥ 21c needed to keep 263 → 45c margin; would
   need span ≤262.13 at this phase to drop a line).
   Optional metric-only fix (NOT done): cut ~20c from title kernel's
   post-final-WSYNC tail so both loops lock at phase 45 and the
   exception can go — title-kernel surgery in the regression-prone
   zone for zero player gain. Probe method rebuildable from these
   landmarks (PCs from bank0.lst: StartFrame $F041, VBLTimer $F053,
   .WaitVBLANK $F0EB, .Row $F0F7, TitleKernel $F9F8, Overscan
   $F19A; clear `wsync_seen` after each stall).
   **Player:** none — transition renders the standard 263 lines
   (filing's "possible 1-frame flicker" cannot trigger at these
   phases).
   **Benefit if parity fix done:** sim prints exactly 263.00 on f3.
2. **test_phase3_ball: frame lines [263,264]** (2026-10-06, M1 `adc #1`
   fix +4c in VBL). User decision: leave. Fix later = find a 4c+ cut on
   the VBL worst path (budget the LATEST-in-path, not the first frame).
   NOTE: passed once after the intro-screen flow landed (2026-10-06,
   frames re-phased) — may be scenario-phased rather than dead; confirm
   in the rescan.
   **Status: CLOSED 2026-10-10 (rescan).** PASSES consistently; the
   residual [263,264] note above never reproduced in the battery window.
3. **BombEnemyBlast can kill lamps (type 5)** — no type check in the
   blast loop (last seen 2026-09-23, still unverified).
    FIXED 2026-10-07: body moved to bank2 ($FD6A — this entry's "$FD6B"
    was a stale comment and is what the hand-synced tramp operand
    copied → bug 10; `BombEnemyBlastBody`,
   `lda (EnemyDataLo),Y / cmp #LAMP` skip) via $FDD8 pad twin (stub in
   kernel.asm; post-switch fetch needs byte-identical bank2 copy), body
   returns A=kill flag, BombTick awards +50 (pads can't nest); PlayerSpriteA
   re-pinned $F8DD, body kept out of test_title_demo's TitleJetColors span.
 4. **Tentacle enters walls slightly on the left probe** (user-accepted).
    PHM entry uses PLAYER origin/width for the candidate box; fix =
    per-enemy origin offset in `UE_Tentacle`.
    **Root cause (2026-10-10):** ink = 4 px at `vl = X-5/X-7` (bank2
    moth `.Mvl` convention — "SetObjectXPos draws ~5/7 px LEFT of A"),
    but the probe swapped the raw candidate into `RoomX`, so PHM's
    PLAYER prologue derived `lit-left = arg-4/arg-7` with the bin on
    `RoomX-PlayerDir` → tested box missed the cell left of the ink at
    cand 8/12 (1-px wall overlap; cell-level proof, both facings).
    **Status: FIXED 2026-10-10.** `UE_Tentacle` probes
    `RoomX = candidate-1`, guarded `cand >= 5` (RoomX<=3 wraps PHM's
    negative visible-left to 255 = ColOff OOB walk; cand<=4 ink is
    off-screen anyway). Model sweep: K=0 misses = 4 cases (cand 8/12
    × facing), guarded K=-1 = 0 misses, 0 unsafe. Guards:
    `test_cell_map` tentacle-probe section (316 checks: box ⊇ ink for
    all cand/facing + sensitivity asserts the OLD formula misses) and
    `test_enemy_movement` source assert (guarded `sbc #1` before the
    probe `sta RoomX`, negative-tested). build.sh + sims + battery green.
    **Tuning (2026-10-10, same session):** X gate `&3` → `&1` — user
    reported the post-fix motion chunky/slow; `&1` = 1 px / 2 frames =
    0.5 px/frame = half the player's 1 px/frame (the `&3` was 0.25 —
    half of half). `test_enemy_movement` gate assert updated. The
    `&1` gate alone still delivered only 0.125 px/f — probe
    false-blocks at bob Y≥133: #13 (fixed same day, this is why the
    second "too slow" report came after this fix).
    **Player:** tentacle sprite overlaps the left wall line while probing
    (cosmetic only — collision stays correct).
    **Benefit:** sprite never crosses the wall edge.
5. **test_editor_roundtrip fails on dirty git tree** — needs committed
   tree; not a code bug.
   **Status: FIXED-as-skip 2026-10-10.** Leg2 (regen + `git diff
   src/generated`) now pre-checks `git status` for uncommitted WIP in
   src/rooms|src/generated and SKIPS with an explicit note (leg1 field
   roundtrip always runs). The skip is visible in output — a silently
   corrupt generated/ would still show as WIP dirt, not a green lie.
6. **M1 block wall-shade stripe** — 8-line `LevelWallColor2` stripe
   inside the yellow M1 block (screenshots/assymetric, 2026-10-06).
   **Status: FIXED 2026-10-09** (case A park; bomb-window color =
   accepted residual, future check below).
   **Root cause found 2026-10-09 (two mechanisms):** the stripe is NOT
   PF — COLUPF writes are exactly 3/frame (band starts, py65-measured).
   It is the D6 parked-M1 patch (missile1, `PositionBallM1`, ENAM1
   whole-cave latch) which takes its color from **COLUP1**, shared with
   the P1 object path:
   - **Case A (static, select screen / L3):** with no active object,
     `.SONoObj` parked the GRP1 window at `ObjTop=0` = ON the player's
     own rows; the window wrote `COLUP1 = ObjColorTab[0..] = $00` for
     8 lines every frame → patch painted $00 = the darker band.
     **FIXED:** `.SONoObj` parks ObjTop=144 — window (Scanline −
     (RoomY+144) mod 256) never lands in the cave while player Y < 112.
     Zero kernel cycles; sims + battery green.
   - **Residual 1:** player Y ≥ 112 (floor): 144 wraps → window hits
     scanlines (Y−112)..(Y−105) (top band) — $00 poison returns there.
     Value-guard (`beq` on $00 color) would fix everywhere but costs
     +2c on the ON path → WSYNC write c73+ = +1 line/frame (sim 271);
     the .Line budget has zero slack (comment worst 61c +2 margin).
   - **Residual 2 (case B):** a real object window (enemy/bomb — bomb
     drops make the bomb the active object) writes its color to COLUP1
     → the patch shows the object color for those 8 lines. M1/P1 share
     COLUP1 by hardware; fix needs ENAM1-off during windows (+2c, same
     budget wall) or a design change (per-band patch enable in .Row
     has slack +3c but doesn't fix the color during the window).
     **User-tested 2026-10-09: select screen + L3 clean (case A fix
     verified); bomb drop still shows a bit of color on the asym block
     = ACCEPTABLE by user — future check only.**
   Cycle-blocked fixes need a 2c `.Line` re-claim first (see kernel
   .Line budget comment — recount from bank0.lst, never trust notes).
   **Player:** darker/wrong-color band across one wall block;
   **Benefit:** uniform block color.
 7. **verify_build warns: model 5/6 have 6 wall rects > 5** — cell-swap
    must cover all cache walkers before release.
    **Status 2026-10-10: (i) FIXED — hybrid shipped (rect4 walk +
    PairGone); (ii) open.** What shipped, and why NOT the original
    cell-sweep design: buffer adjacency CANNOT distinguish thin walls —
    find_rectangles merges maximal runs, so every shipped thin rect has
    a solid neighbor slab (verified all 8 models: all thins have L or R
    neighbors; a neighbor-test sweep would make most cave stubs
    unbreakable). Shipped instead: (a) BMW walk covers rects 0-4 (was
    0-3; clamp moved to the bank2 cache load, RcBase ≤ 5); ABW tables +
    BombMaskBit grew a 5th entry ($00 — rect4 never in WallMask, zp doc
    S3.2); (b) rect idx4 has no mask bit → `PairGone` (leaf at $FACC)
    reads the pair buffer in row LineCount — solid → punch+count,
    already-EMPTY → skip = double-score guard for the maskless slot
    only (idx0-3 keep the mask path byte-for-byte). Rect5 stays
    unwalkable (ZP cache ends $DF) — shipped models have no thin rect
    at idx5; revisit only if a future model puts one there. **Also
    fixed (pre-existing since plan 5.1, caught by the new test): the
    col x+1 punch passed the ABW table VALUE (the rect's ZP address)
    as the ClearPFColumn col instead of deref'ing rect.x — every thin
    wall's second half was punched at a garbage col.** Budget: BMW ran
    in the bomb 1→2 edge (rare frame); sims + battery green, no OVER
    regression. (ii) 7.1 = stop emitting solid rects + kill this WARN
    (only after (i) settles in play).
    **Player:** bombs can break thin walls at cache slot 4 (was
    silently unbreakable); no half-walls from the col-x+1 garbage
    punch.
    **Benefit:** release blocker downgraded to the 7.1 data-pipeline
    item.
8. **Title frames f0/f1 not exactly 263** (262.61 / 262.93 raw) —
   boot-frame quant, same family as item 1. Keyed below f2 so the wall
   assert skips them today.
   **Status: ANALYZED 2026-10-10 — no player-visible effect, same
   proof as item 1 (boundary crossings, not raw average).** py65 probe
   with budget-sim-identical inputs (fire held, RESET at f1/f4, WSYNC
   wall model): StartFrame-to-StartFrame spans f0..f4 =
   263.21 / 263.00 / 263.00 / 263.01 / 262.72 raw — and every one
   crosses exactly 263 scanline boundaries (floor(end/76)−floor(start/76)),
   including the sub-263 raw f4. The TV shows boundary crossings; a
   262-line frame is impossible at these phases (needs span ≤262.13 at
   phase ≥21c, per item 1's math). Raw <263 = phase slack inside the
   last line, not a missing line. The `f<2` wall-assert keying stays
   (raw metric noise, zero flicker risk).
   **Player:** none — boot renders 263 lines on f0/f1.
   **Benefit if metric fix done:** wall assert could cover f0/f1
   (metric-only; boot-phase surgery in the regression-prone zone for
   zero player gain — NOT done).
   **Player:** tiny frame-length wobble in the first 2 boot frames
   (usually invisible).
9. **Laser pass-through on flush wall hold (right-facing)** — user
   2026-10-10: player walks flush against a 1-tile-width wall, fires,
   beam emerges past the tile. Full chain: wall-center clamp attempt
   built + reverted same day (frame lockup from `RectCount` scratch
   clobber — see AGENTS Critical Rule); consume-on-contact redesign
   shipped (`beq .LaserContact`) but the residual reproduced in
   `tools/test_laser_walk_wall.py` (RED commit `1acc120`): flush stop
   puts the origin AT the rect face so the eye lands mid-tile (8px
   tile, eye = face+4); travel's first candidate `eye+4` is already
   past the far edge → clear → committed → the swept cell is never
   tested → no contact event → no consume.
   **Status: FIXED 2026-10-10 (Option A — rearm at the eye).**
   LaserState b0 (`LASER_REARM`): `.LaserContact` `inc`s it after the
   eye restart; the next held frame `dec`s it and jumps `.LaserInit`
   (re-tests the eye instead of stepping). Flush hold = 1 LWC/frame,
   beam held at the eye; open-hold cadence alternates
   travel-consume/eye-retest = same 1 LWC/frame avg. Travel ±4 unified
   through `StepDelta` table (frees the bytes; pad to TallyTramp
   $FFE6 intact). Prologue mask `LASER_KEEP` = dark|rearm (b0 must
   survive the every-frame store). Walk repro now green (24/24
   contacts, LX frozen at eye); `test_laser_wall` model rearm-aware
   (b0 captured at LaserInput rts); `test_room_dark` static guard
   updated for LASER_KEEP. Left-facing control never ran in the repro
   (no left-approach interior wall in rooms 0/1 — placement, WARN
   only).
   **Player:** laser no longer crosses a 1-tile wall when fired
   flush; beam holds at the eye while the tile is solid.
   **Benefit:** the "dumb contact missile" contract now also covers
   the mid-tile-eye geometry, not just the tip-in-wall case.
10. **Bomb leaves a 1-col wall sliver beside the punched thin wall**
    (user 2026-10-10, `screenshots/bugs/sync_wall_half_destroyed.png`).
    Level 1 room 2 (room_id 1, model 1, symmetric): thin wall rect
    `(12,1,2,1)` = display cols 12-13 row1. After a bomb on it: cols
    12-13 punch clean (+75 once, WallMask correct), BUT col 14 (and
    its reflection col 25) renders as a full-height wall sliver in the
    middle band — "removes only half of it" (user).
    **Measured (pixel scan of the PNG, scale 4.0 px/TIA, borders
    calibrate exactly):** middle-band wall runs = cols 0-1 (border),
    14, 25 (mirror of 14), 38-39 (mirror border). ROM verified: bank2
    `M1TilePF2` row1 = `$03` (bits0-1 = cols12-13 ONLY — bit2/col14
    never set); rects match source; `ClearPFColumn` masks are
    AND-only (col14 mask `$FB` clears bit2, cannot set it); sole
    PF2Buf writers = EnterRoom 9-byte load + AND-punch; `PairGone`
    is idx4-only (model1 has 4 rects, never runs); M1StripBlast
    skips (MetaA=$00). **An AND-punch cannot produce a set bit2 —
    the col14 wall bit has no known writer.** Same symptom family as
    the pre-5727966 "col x+1 garbage punch" (entry 7) but that left
    col x+1; this leaves col x+2 with an "impossible" bit — different
    mechanism.
     **Status: FIXED 2026-10-10 — root cause = tramp operand
     off-by-one (same family as the hand-synced-literal lessons).**
     The `$FDD8` tramp was `sta $1FF8 / jmp $FD6B`, but
     `BombEnemyBlastBody` lives at `$FD6A` — entry executed the operand
     byte of `lda EnemyCount` (`a5 b3`) as an opcode. Garbage stream:
     `LAX ($F0),Y` / `ALR ($A5),Y` / **`inc $4A,X`** — with the real
     room's register state `X=$80`, `inc` physically increments `$CA`
     (PF2 band1) → wall bits set with NO store that can explain it
     (exactly the "impossible bit2" pixel-scan above). Proven by two
     Stella `logTrace` instruction traces (parser: store+RMW+mirror
     scans against built bins): the `inc` ran on all 4 blasts, X=$80
     only at frames 1157/1699 → `$CA 03→04` (shot f1176) → `04→05`
     (shot f1733), corroborated by RAM-grid screenshots `$CA=04`/`05`.
     The sliver is render-only: `inc` touched the PF buffer, never the
     rect cache → collision/walk-through unaffected (cosmetic).
     Fix: both tramp copies → `jmp $FD6A` (kernel.asm source + bank2
     twin `.byte $4C, $6A, $FD`). Escape lessons + autonomous repro
     recipe: `lessons_learned.md`. Guards added to verify_build (RED on
     the pre-rebuild bins): `check_blast_tramp` (byte-identity AND
     operand == `BombEnemyBlastBody` — byte-identity alone was
     satisfied by two equally-wrong copies) + `check_tramp_targets`
     (generic: every `sta $1FFx`+`jmp` target must be a
     destination-bank listing row start). verify_build +
     sim_bomb_fuse + sim_frame_budget + battery 27/27 green.
    **Benefit:** bombs clear thin walls completely again.
11. **Editor grid still shows pre-D7 (old tile) format** (user-reported
    2026-10-10). Context: D7 grid flip (commit 3423ecc, 2026-10-04)
    doubled tile width — one logical tile now = 8px = what was 2 tiles
    before (`convert_level.py` `WIDTH = 10` "was 20 pre-D7"). The game
    data pipeline is on the new 10-col grid, but the editor's grid
    display still renders the old 20-col/tile-size layout.
    **Root cause (2026-10-10):** `MapCanvas::paintEvent` drew the grid
    border (and the patch/fragile/reinforced decorations) once per
    display col — 40 boxes, one per 4px half-cell — the pre-D7
    cell-per-col look. D7 cells are 2 display cols (8px), so the
    correct grid is 20 boxes. Placement/edit granularity was never
    wrong (only the visual grid).
    **Status: FIXED 2026-10-10.** Borders + per-cell decorations now
    drawn once per model cell (`dcol & 1 == 0`, `cellRect` spans 2
    display cols — even start holds on both halves; right half mirrors
    `39-dcol`); fill still per display col (patch/color logic
    unchanged). Mouse/`ApplyBrushAt` untouched — clicking/enemy
    placement keeps its granularity. Verified: editor rebuilt (cmake),
    screenshot `screenshots/assymetric/bug11_grid_after.png` (20-cell
    grid, cell-wide cyan patch outline), `test_editor_roundtrip`
    selftest OK, full battery green.
    **Player:** none directly (display/authoring confusion — rooms
    drawn/edited against the wrong grid scale risk misaligned walls).
    **Benefit:** editor WYSIWYG matches in-game tile size.
12. **Bomb "does nothing" on the right wall — BMW window matched
     rect.x only, not the wall's span** (user 2026-10-10: "bomb not
     destroying the right wall at all. Left wall working fine").
     Root cause: `BombMarkWalls` matched `rect.x ∈ [bombcol-2,
     bombcol+2]` (folded mirror space) as a single point — the thin
     wall's span is `[x, x+1]`, so bombs whose window STARTS at
     `x+1` missed entirely (0 `ClearPFColumn` calls = "nothing
     happens"). The mirror instance needs window coverage of the FAR
     col (27 for rect x=12): natural flush drops beside it land at
     fold 15 (bombx 104-107, window [13,17] vs span [12,13]) → miss;
     left-side natural drops land fold 10-14 → hit — hence the
     asymmetric report. (Same family as the pre-existing "bomb@104
     window miss, BMW×3 ClearPFColumn×0" finding from the 2026-10-10
     trace session.)
     **Measured:** `tools/bomb_window_sweep.py` (diagnostic, not in
     battery) — before: punch only fold 10-14; after: fold 10-15 both
     sides, fold ≥16 correct miss (bomb 3+ cols from wall).
     **Status: FIXED 2026-10-10.** Span-overlap match in the BMW walk
     (`w==2` first, then `x<=hi` and `x+1>=lo`; temp-hold x in
     `CollisionEndY`, punch path rewrites it with the last row before
     `ClearPFColumn` reads — no contract change). Growth (~9B)
     overflowed the pre-`$FBF8` content end ($FBF5 = 2B slack →
     Origin Reverse-indexed) → the 4 ABW tables + `BombMaskBit`
     (25B) relocated to the `$F010` fill gap in bank1 (abs-indexed
     only by BMW; `test_phm_walk`'s `^BombMarkWalls:.*?^ABWXTab`
     source anchor retargeted to `^ReturnPad`).
     **Tests:** `test_bomb_half_wall` gained case C (bombx 104 =
     fold 15 right — the user drop) + case D (bombx 68 = fold 15
     left — proves window edge, not mirror), RED before the fix, green
     after; the test now stages a **frozen fixture copy** of the room
     (FIXTURE_PF/FIXTURE_RR literals captured 2026-10-10) with a
     ROM-equality gate, so `src/rooms/*.txt` WIP edits fail loudly
     here instead of silently drifting the contract (user-requested
     "room copies the editor does not touch").
     **Player:** bombs destroy thin walls from every natural drop
     position on both sides.
     **Benefit:** blast window = true ±2 overlap semantics for 2-col
     walls on both sides.
13. **Tentacle X speed ~0.125 px/f — YToRowTable OOB at
    EnemyRamY ≥ 133** (user 2026-10-10: tentacle "not fluid, ~10% of
    gap crossing"; second report after the #4 `&1` gate fix — the gate
    was already 0.5 px/f, the probe was swallowing the steps).
    **Root cause:** `YToRowTable` has 36 entries (idx 0-35 = the
    documented envelope "Max A = PLAYER_MAX_Y+11 = 143"). Tentacle
    spawn y = 132 (level_002 room1 record `.byte 3,71,132,1`) + bob
    triangle (EnemyRamP>>3, 32f period) → RoomY 132/133/134 → EndY
    index `(RoomY+11)>>2` = 36 = OOB → reads the next opcode byte
    (`$A5` = `lda RoomY`) as `CollisionEndY` → cell walk rows 2..165
    through RAM past PF0/1/2Buf → false C=1 on ~24 of every 32 bob
    frames; only the Y=132 frames probed clean → 1 px per 32f
    (measured move gaps `[2,2,2,26]` = 0.125 px/f). The player can
    never trigger it: `PLAYER_MAX_Y = 132` → idx ≤ 35; the tentacle
    is the only PHM caller with Y ≥ 133. Test gap: `test_cell_map`
    `y_reps` ≤ 120 (idx ≤ 32) — parity never exercised idx 36.
    **Status: FIXED 2026-10-10.** Table +1 byte `.byte 2` (idx36 =
    clamp to the last cave row: box bottom 144/145 is past the cave
    0-143 → walk row 2 = floor wall, never `PF0Buf+3` = $C6, not a
    buffer byte). Pre-pad headroom 1B absorbed it exactly (ends
    $FC67); zero runtime cost — a `jsr TentProbeY` clamp helper was
    built first and rejected: every post-pad window is pin-full
    (max free fill 3B at `$FDE1`; `$FE00`/`$FE90`/`$FE96`/`$FEF6`/
    `$FF00` = 0-1B, twin pins `$FDD8`/`$FDE1` address-frozen).
    **Guards:** `test_enemy_movement` 37-entry table assert (was
    36); `test_cell_map` model `YTOROW = [min(i//12, 2) ...]` +
    `y_reps` gains 134 (EndY idx36 end-to-end through py65 PHM).
    **Measured:** py65 `/tmp/opencode/tent_speed.py` phase A idle
    chase: gaps `[2,2,2,...]` steady = **0.5 px/f** (was `[2,2,2,26]`
    = 0.125) = half the player's 1 px/frame — the `&1` gate intent
    (f8b46ac). Phase B wall-holds verified correct geometry (probe
    box `cand-1` conservative 1px into the col wall; ink still
    overlaps the player box). Script note: SWCHA `0xF7` = P1 right —
    P0 right = `0x7F` (the crossing phase never moved the player).
    **Player:** tentacle closes at half player speed, fluid; stops
    flush at real walls only.
    **Benefit:** chase distance closes 4× faster; the bob no longer
    randomizes blocked/clear.

## Latent risks (verified once, fragile)

9. **Laser position: REVERTED to original + wall-suppress shipped
   (2026-10-09, user decision).** The day's position work (Stella-source
   +1, nose eye, arg+2/+8, dir-split) walked in circles — user ruling:
   "return the position code to the original; do nothing (no beam at
   all) if the player is facing a wall, buzz sound only."
   **Shipped:** original eye/draw/LHT window restored (502d6db state);
   `LaserWallClamp` hit (A=2) now routes to `LaserWallOff`: clears b1
   (armed) so kernel `ENAM0 = BeamMask & LaserState` = 0 next frame and
   parks HMM0 — NO beam while a wall is at the tip; b7 untouched so
   `UpdateLaserSound` (gated on b7) keeps buzzing. Kill/lamp keep the
   original re-eye behavior. Contract enforced by
   `tools/test_laser_close.py` (5472-frame sweep: wall/strip tip ⇒ b1
   clear + HMM0 parked; sims + battery 20/21).
   **Residual notes (for a future look, NOT active work):** the eye-
   past-thin-wall spawn case can show the original beam for a frame
   until the first travel contact suppresses it; the S6b log
   (`docs/laser_s6_log.md`) + clamp postmortem in this entry's history
   hold the deeper fix designs (226c clamp = over budget).
   **Player:** no beam (buzz only) when firing at a wall face-to-face;
   **Benefit:** no visual pass-through, laser logic left alone.

10. **Cross-bank Temp conflict:** bank1 `Temp=$AD` = bank0 `TickCounter`
    slot — deliberate, allowlisted (`check_equ_sync.ZP_ALLOW`). Fragile
    if either side's frame phase changes.
    **Player if it breaks:** score/timer corrupt or jump (HUD clobbers
    the game clock).
    **Benefit:** removes a silent alias — relocate or re-allowlist.
11. **Bank1 HUD stomp zone $E0-$EF** every frame; persistent bank0
    state must stay below $E0 (guard: `check_equ_sync`).
    **Player if it breaks:** persistent field state zeroed each HUD
    frame → walls/enemies vanish or corrupt (stomp-zone symptom).
    **Benefit:** keeps the guard the only line of defense honest.
12. **Trace tooling:** `savior.script` / `autoexec.script` must stay
    renamed `*.tracebak`; Stella7 sqlite `dbg.logtrace` must be reset
    after any trace session (see AGENTS debugging section).
    **Player:** none — dev-only. Trace mode makes the game crawl.

8b. **SELECT takes 3 presses to raise the stage number** (user report
   2026-10-06): press 1 = leave intro, press 2 = swallowed (swallow-first
   rule keeps stage 1 visible), press 3 = moves to 2. The swallow was
   requested for the HUD-visible stage screen, but combined with the
   intro exit it reads as a dead press. Fix later = drop the swallow, or
   swallow only when the count was never yet shown.
   **Player:** dead button press — 2nd SELECT after intro doesn't move
   the stage number.
   **Benefit:** every SELECT press responds.
   FIXED 2026-10-07: swallow removed from `TitleSelect` (kernel.asm fill
   region) — every edge now does level+1/wrap/LoadLevel; `TitleSelFlag`
   EQU dropped (TallyTicks owns $F2 alone). Build + sims green, battery
   20/21. Stella press-through still on the rescan checklist (13).

## Title screen — unfinished pieces (2026-10-06)

13. **Piece 1 menu flow — CLOSED 2026-10-10 (py65, test_menu_flow.py).** Original flow (2026-10-06,
    rev2): boot → intro (black, purple "S.A.V.I.O.R." — digit row
    removed per user); first SELECT/RESET edge → old title (first room
    + HUD count); old title SELECT = swallow-first +1 (flag $F2 — moved
    from $EC which the HUD zeroed every frame), RESET = start game;
    gameplay SELECT/RESET → old title (idle-gated: DropTarget==0, so
    the start-game press cannot bounce back while falling); intro never
    shows again (sentinel $FD; DropStep → TitleIntro jmp-in/tail-jmp
    out). RESIDUAL: RESET held *past landing* still re-fires to title
    (level-triggered, no edge byte available) — release before the
    drop-in finishes. Verify both transitions, level wrap 3→1.
    **Status: CLOSED 2026-10-10 — py65 self-test, no Stella needed.**
    `tools/test_menu_flow.py` walks the whole flow against live RAM:
    intro $FD -> RESET -> title $FF (intro never reappears, whole-run
    monitor); title idle holds; SELECT held 3 frames = exactly one edge;
    full LEVEL_COUNT=4 cycle with exact wrap + title state kept (entry's
    "3->1" stale — LEVEL_COUNT=4, display wrap 000004->000001); title
    RESET zeroes score, arms fall, lands DROPT==0; SELECT held mid-fall
    never bounces (idle gate verified); landed SELECT -> title, second
    RESET -> game (repeatable). Entry's "swallow-first + flag $F2" is
    stale too — swallow removed 2026-10-07 (8b), tally owns $F2.
    Residual unchanged/documented: a switch held PAST landing re-fires
    (release before drop-in finishes).
    **Player:** menu flows verified end-to-end in sim.
    **Benefit:** switch-edge/gate regressions caught by the battery.
14. **Jet-art leftovers audit** (2026-10-08 — original jet-art piece
    CANCELLED, art removed). Grep the tree for dead references:
    `art/start_screen.png`, `screenshots/title_mock.png`,
    `tools/mock_title.py`, title-art generators, plan docs (pairs with
    26). **Player:** none — dev cleanup; **benefit:** no misleading
    stale refs.
    — FIXED 2026-10-08: audit clean. `art/start_screen.png` and
    `tools/mock_title.py` gone; `generated/title_art.asm` already
    deleted; no code references remain (only history mentions in plan
    docs). `screenshots/title_mock.png` KEPT deliberately — entry 16
    uses it as the sizing mock.
16. **Title font sizing — DONE** (2026-10-08 greenlight, shipped 2026-10-09).
    Shipped: title text spread 44px → **86px** (NUSIZ6 32px pitch, drawn
    grid p=34 via SetObjectXPos 41/57 — hardware max for 6 glyph slots);
    font = 5px letters bits7-3 + **2px gap** bits2-1 + 1px baseline dot
    bit0 (8px cell hard limit: 6+2+2 does not fit); rounded S, open-tip V.
    py65 slot decode = 6/6 byte-exact vs ROM; battery 20/21 (test_title_demo
    position asserts updated to 41/57).
    **The "V renders like 9" root cause = VDEL promote x vs NUSIZ copy grid
    (measured, py65 promote watch):** TitleKernel's cross-buffer writes flip
    P0/P1 content at FIXED x regardless of sprite position — P0: S from
    line-start, **V@64**, O@82; P1: A from line-start, **I@73**, R@91
    (stable ±0 across lines). A glyph cell (8px) must sit ENTIRELY inside
    its sprite's zone; old grid p=29 put V's cell at 61-68 → pixels 61-63
    still showed S + 64-68 V = mixed rows that read as "9". Slot grid
    constraint solve (zones S[0,63] V[64,81] A[0,72] I[73,90] O[82,] R[91,])
    → **p ∈ [32,35]**; chose 34 (2px margin at V, 1px at I).
    **Rule: changing title NUSIZ/positions must re-solve cells against the
    measured promote table — the promote xs are fixed by the loop's cycle
    timing, not by the sprite positions.** Verify = py65 promote watch +
    per-slot pixel decode (scripts pattern in this entry's session).
    **Player:** none today; bigger/2×-taller letters need bank0 space first
    (pre-pad 1B; title font at $FB00 in main) — free bytes (#25) first.

## Backlog (from AGENTS development plan)

17. Per-scanline PF lookup tables for cave patterns (HERO LFA00-style).
    **Benefit:** richer per-row cave texture like HERO.
18. **HUD level indicator — DONE** (2026-10-08 spec, shipped 2026-10-09).
    "LV001" replaces the score in the score slot for the first 120 frames
    (2s) of a level: bank1 `SetupScorePointers` (moved next to the glyphs
    at $FD68 — bank1 pre-pad $F937 pin has ~1B slack) points scorePtr1-6
    at new glyphs 10/11/12 = blank/L/V; Level+1 splits to tens/ones via
    repeated subtract (hundreds '0', LEVEL_COUNT <= 99). Armed in
    LoadLevel, gated on DropTarget != $FD (boot intro call must leave
    the TallyTicks slot alone — see alias below). py65 verified: attract
    keeps the slot 0, banner ptrs exact, score restored after expiry.
    **ZP alias:** LevelShowTimer = **$F2 = TallyTicks** (bit7 = banner
    flag, decs $F8..$80; tally ARM <=127 kills the banner instantly —
    miner pickup during the banner window used to double-dec the tally,
    +50pts/tick). Lifetimes: banner = gameplay entry, tally = level-exit
    bonus, intro phase = boot (gated). The zp doc's "$F2 free" was
    stale — fixed there. **Player:** sees which level they're on;
    **Benefit:** level context at every stage start.
21. Residual flicker investigation postponed (user-led) — S6.4-S6.6
    rules prevent making it worse; resume during a rescan.
    **Player:** occasional unexplained flicker in heavy frames.
    **Benefit:** real root-cause fix.
22. Exit-crossing `EnterRoom` +1665c spikes (f327 class) — FIXED
    2026-10-09: body moved to bank2 ($F010) via twin tramp at $FB84
    (guarded by verify_build check_enterroom_tramp); direct (ptr),Y
    reads replace folds, 9-byte PF loop replaces 3 phases. SIM_EXIT
    f265 spike 7287→5546c (−1741c), bad-frame list unchanged, min SP
    $F7→$F9. Residual 5546c = documented rect-walk heavy-frame family
    (frame-budget rule 2). Sim lesson: frame landmarks must be
    bank-gated — EnterRoomB2's rect loop parked pc on bank0's
    StartFrame address ($F041), counting fake frames that stole the
    f2/f5 RESET pulses (title stuck $FD); gated in bomb_fuse/tally/
    laser_wall.
    **Player:** judder/flicker when crossing room exits (up to +14
    lines on spike frames).
    **Benefit:** smooth room transitions.
23. Editor flicker budget: max 2 elements/room, 1 per row — stays until
    a GRP1 multi-object solution.
    **Player:** none (editor-side cap); **benefit when lifted:** more
    simultaneous room elements.
24. BombPlayerBlast kills player within ±1 col by design — remind in
    playtest feedback; revisit if it feels unfair.
    **Player:** own bomb kills from 1 column away — may feel unfair.
    **Benefit if changed:** fairer blast radius (only if playtest says).
25. Pre-pad headroom 1B (build WARN) — bank0 pre-pad is full; any new
    pre-pad code requires a cut first (leaf-to-fill pattern).
    **Player:** none today; **blocks:** next pre-pad feature until a
    cut lands.
26. **Stale intro-art references** — historical title notes and plans
    still mention removed start-screen art/generators. Reconcile those
    references in a separate cleanup pass; keep out of gameplay-demo
    work.
    **Status: RECONCILED 2026-10-10 (docs-only pass).** The only live
    reference was `src/plans/intro_screen_fix_plan.md` — now carrying a
    HISTORICAL banner (art pipeline removed 2026-10-08 per #14; current
    intro = #16 font, plan2 is the current plan; steps must not be
    executed). No other .md/asm mentions `mock_title`/`art_table`/
    `title_art`/`start_screen` (verified by repo grep). NEEDS USER
    APPROVAL (deletion rule): orphan
    `src/tools/__pycache__/art_table.cpython-312.pyc` (source removed,
    bytecode left) — delete with user permission, keep until then.
    **Player:** none — docs only; prevents misleading future work.
27. **Level-data overflow of bank2's data slots = build dies
    `Origin Reverse-indexed`** (2026-10-08, level 4). The window is
    pinned at the end by address-fixed pads (twins in every bank).
    Level 4 + models.json growth took the block to 681B vs the 509B
    window. Stopgap landed 2026-10-08: `convert_level.py --levels`
    emits `generated/levels_index.asm` (EQUs + LevelDataTable tail);
    bank2.asm spills level 4 + index into the `$F800` fill gap
    (start $F767, 153B) and level 3 into the `.ds $F970` gap
    (start $F901, 111B); the window keeps models + levels 1-2
    (start $F9D9, end $FB84 after the #22 tramp, 427B). Remaining
    slack: window 30B, $F767 37B, $F901 19B, $F840 64B (free),
    $F5A4 92B (free) — ~2 small levels left, then re-place.
    (a) DONE 2026-10-09: `verify_build.py --precheck` runs in
    build.sh BEFORE dasm — parses bank2.asm include-blocks + pad
    literals, measures generated file sizes, resolves each slot's
    start (org literal exact / first label from bank2.lst), prints
    the placement map with slack per slot (now 37/19/30B) and fails
    early on overflow (verified with an injected +40B spill). Still
    open: (b) DONE 2026-10-09: `convert_level --levels` now emits
    `generated/spill_*.asm` include-lists from a fixed slot map
    (first-fit, big levels first, index first per slot) — bank2.asm
    carries one static include per gap (F767/F901/window + new F840
    slot, 64B) and adding a level never edits bank2.asm; precheck
    flattens nested includes before measuring. $F5A4 (92B) stays
    unusable: it assembles before levels_index defines ROOM_NONE.
    long-term (c) plan P4 (docs/level_bank_plan.md):
    level data in bank3, per-level bank select.
    **Player:** build dies with `bank2.asm: error: Origin
    Reverse-indexed` whenever levels or models grow past the window.
    **Benefit:** add a level = drop the JSON + build, no asm surgery.
28. **Level data costs too much ROM per level** (2026-10-08, user).
    Level 4 = ~72B of tables (6 rooms: 4 conn bytes + enemy records +
    word pairs each) and models_data was 345B for 11 shared models.
    **Status: DONE 2026-10-09 (main win shipped, rest catalogued).**
    SHIPPED: solid rects packed 2B/rect `[x<<2|y, w<<2|h]` (emitter
    convert_room.py with range assert; EnterRoomB2 `.EBrcW` unpacks to
    the 4B ZP walk form — walkers/cache untouched; HotOverlapBody +
    BuildColupF hot offsets ×2; test_laser_wall hot poke ×2).
    models_data 345→269B (data_size); bank2 window 397→321 of 427B
    (slack 30→106B), sims + battery green (commit 949583d).
    Candidate audit: nibble connections ALREADY shipped (levels 1-4);
    identical-room PF ALREADY deduped (models_data); PF-row RLE moot
    (band cut left only 9B PF + 2B meta per model); "skip unread
    level scalars" DISPROVEN — LoadLevel reads all 14 stride bytes;
    enemy record 4→3B BLOCKED (x/y are 8-bit pixels = 21b and the
    readers sit in bank0 pre-pad, 1B headroom).
    Still possible later: RoomDataTable drop PF0 word → derive
    `PF0 = Rects + 2 + 2*count + 5*hotcount` in EnterRoomB2
    (−64B raw / ~−34B net; needs a Temp/RectCount scratch audit);
    RoomEnemies drop ptr → sum counts loop + kernel:522 stride ×2
    (−32B raw / ~−10B net); pack RightRects (−20B, but ROM-only
    cell-walk PHM + ball readers = hot path). Note: `tools/
    explore_laser.py` still parses the old 4B rect stream (stale dev
    probe, not in battery).
    **Player:** none today (ROM full = build error, item 27);
    **Benefit:** ~1-2 more levels fit before spill re-placement
    (with the #27a free gaps, ~4-6 levels).

29. **Frequent gameplay screen flicker: image jumps a couple pixels
    up/down; almost always when dropping a bomb** (2026-10-09, user —
    work later). Small vertical jitter (a few px) during normal play,
    near-constant on bomb drop. Suspect family = frame-length variance
    (262 vs 263+ lines scrolls the whole picture; AGENTS frame-budget
    flicker rules + item 21) with the bomb-drop path (BombPacked state
    machine, drop input in overscan/VBL) as the trigger to bisect.
    Start from `sim_frame_budget` `SIM_HIST`/mark windows around the
    drop frames + wall-model line counts, then the drop handler's VBL
    cost. **Player:** constant visual jitter during play, worst on bomb
    drop; **Benefit:** stable picture.
    - **Class A — FIXED 2026-10-10 (agent).** Root cause: the `.Line`
      kernel body on the player's A0=11 line (color fetch + GRP0 blank
      same iteration) overlapped the GRP1 object window = **78c > 76c**;
      `sta WSYNC` landed 2c into the next line → full-line stall → +1
      scanline on every frame whose flicker-rotated object window hit
      that line (24 stalls per SIM_LEVEL=2 window, frame-parity
      pairs). Same family also produced the SIM_LEVEL=0 FLY 264-frame
      bad frames (Class C) and6 EXIT=down cave micros. Fix: color/beam
      gate at A0=10 (`cpy #PLAYER_SPRITE_H-1`) — row 11 renders row 10's
      COLUP0/ENAM0 writes (both tables `[10]==[11]`, verify_build guard
      #5 asserts + gate presence). Worst path 78c→61c, net 0 bytes
      (headroom stays1B). Verified: SIM_LEVEL=2 bad 24→0; SIM_LEVEL=0
      default/FLY={Y,X,M} all 0 bad; EXIT=down cave micros gone;
      battery 26/26; TIA-trace diff vs pre-fix baseline = only the58
      skipped COLUP0=$08 +58 ENAM0=$00 writes (per-frame, nothing else).
    - **Class B — FIXED 2026-10-11 (agent).** Root cause was a CRASH, not
      a heavy frame: the death chain `main→jsr CheckEnemyHit→jmp LoseLife→
      jsr ReloadLevel→jsr LoadLevel→jsr EnterRoom` ran at SP=$F7, so the
      `jsr EnterRoom` return address sat on $F6/$F7 (BombX/BombTimer RAM
      mirrors); `EnterRoomB2`'s `sta BombTimer` zeroed the pushed PCH and
      ReturnPad's `rts` popped ($00<<8|BombX)+1 = $009A → ZP executed as
      code → $F008 pad → **GameStart REBOOT to title**. That produced BOTH
      the f265 296-line frame AND the whole title-264 family (bad list
      [265..276]). Only 3-slot-upstream paths were poisoned (CheckEnemyHit
      / timer death); bomb (4 slots) and water-band (5 slots) sat on
      safe cells — which is why only some deaths "rebooted".
      Fix: `ReloadLevel` tail-jmps `LoadLevel` (−1 slot → return lands
      on $F8/$F9 stack-only cells on every death path). The old post-code
      (vy/JetPower zeros + rts) is dead but kept byte-identical — deleting
      it shifted the $FDCD blast-tramp byte-identity guard; LoadLevel ends
      in DropArm which zeroes the same (JetPower=4 now survives the
      wrap-death drop-in, matching the .LLStay normal-death path).
      Guards added: sim_frame_budget silent-reboot detector (post-landing
      `$F000` re-entry → structural fail), bank-keyed pc_hist (pc-alias
      trap), `transition_frames` exemption for the death+respawn pair
      (reload chain runs +1 TIM64T tick = 3264c measured → +0.83/+0.22
      lines on exactly 2 frames; wall/overscan gates exempt ONLY these).
      Pre-existing, unchanged: `bomb exploded (state2 seen)` FAIL in
      SIM_EXIT=down (confirmed identical pre-fix — bomb never reaches
      state 2 in this scenario; not a regression).
      Verified: SIM_EXIT=down bad wall list **empty** (was 296-line
      crash + 12-frame title family); build.sh green; battery 26/26;
      SIM_FLY {Y,X,M} all 0 bad at 265.0; no structural notes.
    - **Class C (residual seam) — FIXED 2026-10-11 (agent).** Root cause:
      TIM64T expires on a 64-cycle tick and the INTIM poll (`.WaitVBLANK`)
      exits up to 63c late; the band-0 `.Row` setup WSYNC gap is ~75c, so
      the kernel start line oscillated ±1 with the tick phase (Stella
      trace: first `.Line` WSYNC at scn 20 on 100 frames / scn 21 on 51
      frames under bomb+thrust input; HUD seam flipped rows 144/194,
      62/58 split over 120 detector frames). py65 WSYNC counts were
      constant (cave 147 / HUD 48) — the variance was the tick-phase
      straddle, invisible to count-based guards. Fix: two re-anchor
      `sta WSYNC`s — (1) at `StartFrame` before the VSYNC pulse
      (overscan-end quant → VSYNC phase-lock), (2) after `.WaitVBLANK`
      with VBLANK still on (VBL quant → kernel-entry line-lock; blank
      line, invisible). +2 lines/frame → wall-model 263→265 (both
      re-anchors counted); `OVER_ABSORB` 3222→3223 (+1c page-cross from
      the +4 bytes of code motion — ledgered, not new work); f2/f3
      transition exception widened to ±1.0 (was f3-only ±0.35).
      Verified: Stella trace first-kernel-WSYNC scn 21 on 152/152
      frames; pixel detector single seam signature 120/120 frames
      (was 62/58); sim_frame_budget 265.0 clean on default + FLY
      {Y,X,M}; battery 26/26; `test_phase3_ball` expectation
      updated to {264,265}. Tooling: `tools/measure_bar_cycles.py`
      (py65 WSYNC/span/VBL/overscan under thrust+fire).

30. **Power bar: red at game start + first chunk too big + uneven
    chunk timing** (2026-10-11, user). Reported three symptoms:
    (a) bar already lost a chunk (red) the moment gameplay starts;
    (b) the first red chunk appears too fast — it should take the same
    time as every later chunk; (c) that first chunk is ~2-4× bigger
    than a normal one.
    **Status: FIXED 2026-10-11 (agent).** Three root causes, three fixes:
    - **(a) timer ran during the forced drop-in** — `DropStep` tail-jumps
      `OverscanAudio`, which contains the TickCounter/BarLevel block, so
      the ~1-2 s game-start fall burned 1-2 bar steps before the player
      could act. Fix: gate ONLY `dec BarLevel` on `lda DropTarget / bne
      .TimerDone` (`kernel.asm` timer block). TickCounter keeps counting
      (jet-flutter clock `TickCounter&4` and second-phase stay frame-exact
      — important: `test_phase2_ball`'s bit-identity leg proved that
      freezing TC shifts PickPlayerFrame flutter and breaks the baseline
      trace). +5B absorbed by the pre-pad `$F8DD` pad slack (headroom
      still ends $FC67).
    - **(b) first red at t=1s** — the full bar (`BarLevel=BAR_MAX`) is a
      special yellow-only path, so ANY first decrement showed red.
      Fix: renderer now holds the yellow-only path for `B >= BAR_MAX-3`
      (`bank1.asm` `cpy #(BAR_MAX-3)`), so the first red lands on the
      4th decrement = t=4s = exactly one chunk period.
    - **(c) chunk sizes/timing were irregular** — BarDelay/BarFine
      tables (H3c regeneration) drift: measured steps {0,3,6,9,11}px at
      irregular intervals (82 of 120 seconds showed NO movement, then
      6-11px jumps; +36px at the bottom; first bite 11px vs normal 3px).
      Fix: both tables regenerated by `tools/gen_bar_tables.py` —
      monotone staircase, one visible step every K=4 decs (4 s exactly),
      step 1-2 cycles (3-6 px), positions snapped to reachable
      (base,5A) pairs (pos ≡3 mod 5 unreachable), cap pos≤71 (content
      budget unchanged — listing-checked), B=0 renders full-red
      (pos≤23). `gen_bar_tables.py --check` verifies bank1 tables match
      the generator (CI-style, hand edits now fail loudly).
    **Verification:** battery 26/26 (incl. phase2 bit-identity — TC
    sequence preserved); build.sh green; py65: decs exactly every 60f,
    full-hold B=120..117, first red (B→116) on the 4th dec; Stella
    dense capture (saveSnap every 10/30 script-frames, red-width
    probe): NO red for the first ~4 s, then chunk boundaries EXACTLY
    every 240 emulated frames (Stella `frame N` runs ~1.6×N
    emulated frames — 15 shots×16f and 5 shots×48f both = 240), steps
    6/12 px(320-space) = 1-2 cycles. First-bite vs chunk ≈ 2.04×
    (structural: body-end 74.7c vs max red-path pos 71c = 11.1px
    floor; would need a new (A,F) path or content>71 to shrink —
    ceiling noted, revisit only if user still perceives it).
    **Status: USER PASS 2026-10-11** (after the K=8 retest, 1bf92af).
    **Player:** timer bar starts full, drains in uniform visible steps
    on a fixed cadence; no red before the first chunk's worth of time.
    **Follow-up (noted, not fixed):** returning to title mid-run via
    SELECT and starting a new game does NOT reset BarLevel/TickCounter
    (stale bar possible on the 2nd+ game from title); would need ~10B
    in the fill region at TitleWork RESET.
    - **Retest (2026-10-11, user):** timing fixed ("a chunk being
      removed so soon" gone) but first chunk still ~5-6x a normal one.
      Measured: bite = 14px(160) vs first steps of 3px (the K=4 top
      steps were 1-2c while the F4 top block renders 1c early — bite
      28px/320 vs 6-12px steps). Second fix: K=4 -> **K=8** — chunks
      now 3-4 cycles (9-12px, mostly 4c) every 8s, full-hold 7 decs
      (first red at t=8s = one chunk), generator ratio gate <=1.7
      (actual schedule: bite 14.1px / chunk 11.7px = 1.20 computed;
      Stella dense re-measure: bite 28px vs +18..24px steps =
      **1.17-1.56x**, boundaries exactly 480 emu frames = 8s,
      red first appears ~emu558 = t=8s after landing ✓). The F4A8
      top-block -1c render offset is documented in the generator
      (bite calc +3px) — would need a path recount to remove; not
      worth it at <=1.56x.

31. **Jetpack inertia: ~1s spin-up + ~1s float after release**
    (2026-10-11, user — feature). Spec: pressing Up starts the engine
    sound immediately but the player takes ~1 second to actually start
    flying; releasing Up must not start the fall immediately — also
    ~1 second — so the player can glide horizontally before having to
    thrust or fall.
    **Status: IMPLEMENTED 2026-10-11 (agent), awaiting user feel-test.**
    - **Root cause of the snappy feel:** JetPower ramped +1/frame to
      JET_MAX=$20 — net lift (cumulative thrust = gravity) after only
      ~15 frames (0.25s); decay was also fast.
    - **Fix (kernel.asm, UpdateP0Vertical):** the +1 ramp step now
      runs only on the free-running clock's every-4th frame
      (`EnemyRamP & 3 == 0`); decay stays -1/frame (fast throttle
      bleed + stored rise-clamp momentum = the float). JET_MAX
      $20 -> $14 (20): with the ÷4 ramp, net lift (vy=0) at exactly
      60 frames = **1.0s of held-Up**; full thrust at 80f.
      Sound was already press-gated (SWCHA D4 in bank1
      UpdateJetSound) — buzz starts on the press, pitch revs with
      JetPower. +7B ramp gate absorbed by the pre-pad $F8DD pad
      slack (headroom stays $FC67).
    - **Measured (py65, boot-to-gameplay):** press-to-first-upward-
      move = 73 frames (1.22s, includes gravity settling onto the
      floor first); release-to-first-downward-move = 51 frames
      (0.85s). Both "around 1 second" per spec.
    - **Side effect + companion trim:** the slower spin-up keeps the
      player grounded longer, so the SIM_FLY=X bomb now drops and
      lands a falling+enemy-probe+hot-scan coincidence on its frame
      (3260c > 3223 band, wall 266.11). Trimmed the hot-scan walk
      `.CWCol` (kernel.asm): X seeded per row + `cpx` instead of
      reload+cmp = -8c/cell (~-90c on that frame) — same walk
      semantics (stx keeps CollisionX fresh for HotOverlapFlag);
      -3B. FLY={X,Y,M} all 0 bad again; battery 26/26.
    - Also added: sim `transition_frames` now covers the bomb-punch
      event (CallPad_BombMarkWalls entry) — same one-frame event
      exemption class as the death/respawn reload.
    - **Retest 1 (2026-10-11, user):** spin-up "perfect"; fall still
      started too soon (decay -1/frame = open-air fall at 0.58s).
    - **Clarified spec (user):** on release the climb must stop in
      ~0.3s, THEN the player must hold the same Y for ~1s before
      falling (not a momentum glide).
    - **Final design (this session's main rework):** float state lives
      in **JetPower, b7 = float flag, low 7 bits = countdown** —
      NOT StepsLeft (two collisions found the hard way: StepsLeft is
      RefreshEnemyY's SWCHB latch byte — title edge contract — and
      .UpSteps rewrites it on every rising frame, killing any
      StepsLeft-based float within 1 frame). Release edge (thrust
      1..127, b7 clear, vy != 0) loads $80+54 (first pass $80+80 =
      ~0.9s hover; user: 1s too long → halved, ~0.5s pinned); physics skips the
      thrust subtraction while b7 set (gravity-only decel = phase A);
      when vy >= 0 Y is re-zeroed every frame (pinned) until the
      countdown clears the flag, then normal gravity resumes.
      Up-press cancels the float (bpl-guarded — an unguarded clear
      wiped JetPower every held frame and the ramp could never build).
      Reverted in the process: REY latch float-skip, ColOff/ColMask
      relocation + $FDD8 re-pin, fall-gate StepsLeft clear, the
      StepsLeft PENDING/HOLD machine, and the ÷2 decay.
    - **Measured (py65):** press spin-up unchanged (~1s, floor then
      lift); release: stop-climb 26f (0.43s), Y pinned ~28f
      (~0.5s, halved per user retest), fall ~48-54f =
      **~0.85s after release** (spec: 0.3s stop + ~0.5s same-Y ✓).
      Countdown lives at $80+54.
    - **Fixture updates (sim_frame_budget, honest scenario drift):**
      X/B fly pulses stop at f500 (rapid 5/12 re-presses + pinned
      releases hover forever, vy never reaches the 256 StepDown
      threshold → OnGround never sets → landed=None); scenario window
      440→1100 (slower landing + 180f fuse); transition exemption
      margin ±1.0→±1.1 (death frame measured 266.01 = exactly +1
      TIM64T tick + wall slack after the drop-in timing shift).
    - Companion trim kept from retest 1: `.CWCol` hot-scan -8c/cell
      (-3B); sim transition_frames covers the bomb-punch event.
    **Player:** press = buzz + lift-off ~1s; release = stop ~0.3s,
    hover in place ~1s, fall ~1.3s after release. Verify feel.
## Rescan checklist (when the batch is closed)

- [ ] `./build.sh` fully green (all sims, zero new warns)
- [ ] Battery `tools/test_*.py` — only known failures allowed
- [ ] Stella: title flow, level select, one full playthrough per level
- [ ] Screenshot-verify ball/laser X vs PF (item 9)
- [ ] Re-read AGENTS lessons vs actual code (drift check)
- [ ] Close or re-date every entry above
