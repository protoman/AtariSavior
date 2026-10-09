# Known Bugs & Deferred Items

Catch-all list of small issues left behind while shipping features.
Cadence (user decision 2026-10-06): implement a few features, then stop
and do a complete rescan — sometimes a redesign — of everything here at
once. Date each entry; close with a one-line fix note when done.

Info lines per entry (added 2026-10-07, user request): **Player:** what
someone running the game sees today; **Benefit:** what the fix gives them.
No entry is worked on without user greenlight.

## Open bugs

1. **sim_frame_budget f3 transition frame = 263.20 lines** (2026-10-06,
   title kernel work). Tolerance 0.15, over by 15c. VBL *work* on f3 is
   94c LOWER than baseline — pure wall-phase/tick-quant inheritance from
   the lighter title overscan, not real extra work. Accepted with a
   documented exception in `_wall_bad` (title→cave transition frame gets
   ±0.25). Real fix later: find the +15c (probe StartFrame→VBLTimer
   arm sub-segments) or make title frame phase byte-parity with cave.
   Family: documented ±56c wall phase slack (2026-10-02 VBL measure notes).
   **Player:** possible 1-frame flicker/jump entering a level from title.
   **Benefit:** rock-solid 263-line transition.
2. **test_phase3_ball: frame lines [263,264]** (2026-10-06, M1 `adc #1`
   fix +4c in VBL). User decision: leave. Fix later = find a 4c+ cut on
   the VBL worst path (budget the LATEST-in-path, not the first frame).
   NOTE: passed once after the intro-screen flow landed (2026-10-06,
   frames re-phased) — may be scenario-phased rather than dead; confirm
   in the rescan.
   **Status:** PASSES 2026-10-07 battery (only test_phase2_ball fails) —
   stale, close at rescan.
3. **BombEnemyBlast can kill lamps (type 5)** — no type check in the
   blast loop (last seen 2026-09-23, still unverified).
   FIXED 2026-10-07: body moved to bank2 $FD6B (`BombEnemyBlastBody`,
   `lda (EnemyDataLo),Y / cmp #LAMP` skip) via $FDD8 pad twin (stub in
   kernel.asm; post-switch fetch needs byte-identical bank2 copy), body
   returns A=kill flag, BombTick awards +50 (pads can't nest); PlayerSpriteA
   re-pinned $F8DD, body kept out of test_title_demo's TitleJetColors span.
4. **Tentacle enters walls slightly on the left probe** (user-accepted).
   PHM entry uses PLAYER origin/width for the candidate box; fix =
   per-enemy origin offset in `UE_Tentacle`.
   **Player:** tentacle sprite overlaps the left wall line while probing
   (cosmetic only — collision stays correct).
   **Benefit:** sprite never crosses the wall edge.
5. **test_editor_roundtrip fails on dirty git tree** — needs committed
   tree; not a code bug.
   **Status:** PASSES 2026-10-07 battery — stale, close at rescan.
6. **M1 block wall-shade stripe** — 8-line `LevelWallColor2` stripe
   inside the yellow M1 block (screenshots/assymetric, 2026-10-06).
   Unexplained, cosmetic.
   **Player:** darker band across one wall block (looks like a seam).
   **Benefit:** uniform block color.
7. **verify_build warns: model 5/6 have 6 wall rects > 5** — cell-swap
   must cover all cache walkers before release.
   **Player:** no symptom today; if a walker reads a stale rect → wrong
   wall collision on those models once enabled.
   **Benefit:** removes a release blocker.
8. **Title frames f0/f1 not exactly 263** (262.61 / 262.93 raw) —
   boot-frame quant, same family as item 1. Keyed below f2 so the wall
   assert skips them today.
   **Player:** tiny frame-length wobble in the first 2 boot frames
   (usually invisible).

## Latent risks (verified once, fragile)

9. **Stella renders 8-wide missiles 1 clock left of the [A-7,A] player
   contract.** M1 fixed empirically (`PositionBallM1` passes M1X+1,
   pixel-measured 2026-10-06). **Ball (selector 4) and laser M0 carry
   the same suspicion — unverified.** Screenshot-check before trusting
   ball/laser X. Stella TIA source never fetched (repo path unresolved).
   **Player:** laser/ball possibly 1px off from where collision logic
   thinks — shots look like near-misses on walls.
   **Benefit:** shot visual == hit logic.
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

13. **Piece 1 code complete, Stella test NOT done.** Flow (2026-10-06,
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
    **Player:** untested flows (unknown until Stella run); known:
    holding RESET past drop-in landing bounces you back to title.
    **Benefit:** verified menu flow, no bounce-back.
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
16. **Title font sizing — WORK IT** (2026-10-08 user greenlight).
    S.A.V.I.O.R. title letters are very small: bank font is 8×7 rows;
    mock (`screenshots/title_mock.png`) used 2× scale chunky.
    **Benefit:** bigger, bolder title letters.
    **Player:** tiny title text today.

## Backlog (from AGENTS development plan)

17. Per-scanline PF lookup tables for cave patterns (HERO LFA00-style).
    **Benefit:** richer per-row cave texture like HERO.
18. HUD level indicator (2026-10-08 user spec): at the start of a
    level, show something like **LV001 in place of the score** for the
    opening moments (design: duration + exact display open).
    **Player:** no level number on screen; **benefit:** player knows
    which level they're on.
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
    open: (b) convert_level emits its own org+include spill lines
    from a measured free-gap map, so adding a level never touches
    bank2.asm; long-term (c) plan P4 (docs/level_bank_plan.md):
    level data in bank3, per-level bank select.
    **Player:** build dies with `bank2.asm: error: Origin
    Reverse-indexed` whenever levels or models grow past the window.
    **Benefit:** add a level = drop the JSON + build, no asm surgery.
28. **Level data costs too much ROM per level** (2026-10-08, user).
    Level 4 = ~72B of tables (6 rooms: 4 conn bytes + enemy records +
    word pairs each) and models_data is 389B for 12 shared models —
    total block 681B vs the 509B window (item 27). Find compressions:
    pack connections 2/room (nibble directions), run-length the PF tile
    rows (mostly $00/$ff runs), compact enemy records, skip per-level
    scalars the game never reads, emit one PF stream for identical
    rooms. **Player:** none today (ROM full = build error, item 27);
    **Benefit:** many more levels per bank and fewer spill
    re-placements.

## Rescan checklist (when the batch is closed)

- [ ] `./build.sh` fully green (all sims, zero new warns)
- [ ] Battery `tools/test_*.py` — only known failures allowed
- [ ] Stella: title flow, level select, one full playthrough per level
- [ ] Screenshot-verify ball/laser X vs PF (item 9)
- [ ] Re-read AGENTS lessons vs actual code (drift check)
- [ ] Close or re-date every entry above
