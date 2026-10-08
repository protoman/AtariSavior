# Line-budget fix plan — 2026-10-05

Context: `sim_frame_budget` wall-model gate failing (47/439 frames ≈264 lines;
was 441 before the A0=11 `.ObjZero` stall fix earlier today).

## Root cause (measured, not guessed)

One cave `.Line` body = **78c** (stall threshold 76, AGENTS safe rule 73).
Fires when the player 12-row color/GRP0 window and the object "A==8 first
line below window" are the SAME physical line (coincidence every 4th frame =
player Y substep). Exact breakdown from py65 body trace (raw f86, `body_sum=78`):

| Segment | Cycles |
|---|---|
| loop control (`dec LineCount` + `bne .Line`) | 8 |
| color + beam (`PlayerColTable` + `BeamMask/and/ENAM0`) | 21 |
| GRP0 in-window (`iny/cpy/bcs/lda(zp),Y/sta`) | 14 |
| GRP1 obj section (`tya/sec/sbc/cmp/bcs`) | 12 |
| `.ObjZero` A==8 path (incl `ldx RowIdx` restore) | 20 |
| `sta WSYNC` | 3 |
| **total** | **78** |

## Options considered

| # | Option | Verdict | Reason |
|---|---|---|---|
| A1 | Temp-restore: `sta Temp` in `.Row` + `lda Temp / sta COLUP1` in `.ObjZero` (−4c) | **CHOSEN (revised)** | Original rejection stood on `.Row` row2 = 76c zero margin: `sta Temp` (+3c) pushed setup gaps 77/79 = stall every frame. Resolved by the LineCount-after-WSYNC reorder (same bytes, −3c from the gap window, +3c onto the first body line — LineCount has no reader until the line's `dec` tail). Final: gaps 74/76, first body 75/72, worst line 78→74. |
| A2 | Stage temp on obj-in line, read on A==8 | subsumed by C1 | C1 is the same trick with X instead of a new ZP byte |
| C1 | X-restore: obj-in path ends `ldx RowIdx` (+3c on ~8 lines, those have 66c worst → 72), `.ObjZero` drops its `ldx RowIdx` (−3c on A==8) | attempted → failed → reverted | Did not hold on its own; superseded by A1 (`.ObjZero` restore became `lda Temp`). Row-advance keeps its unconditional `ldx RowIdx` reload. |
| C2 | Layout fall-through: move `.ObjZero` before `.AfterObj`, tails fall (−3c each), in-range pays `jmp` (+3c, has 66c headroom) | not applied | Conditional ("only if sim after C1 still fails") — A1+LineCount-reorder passed without it. |
| D1 | `Temp $88` ZP audit for A1 | done (A1 rejected anyway) | Kernel has NO Temp reader/writer between `.Row` and `.ObjZero`; VBL writers (StageBandTab, obj count) and overscan reader (joystick) both outside the window — Temp would have been safe; `.Row` margin killed A1, not ZP |
| F2 | Single-color jet (`PlayerColTable` removed, −7c×12 lines = −84c/frame) | **REJECTED** | HERO writes COLUP0 EVERY scanline from a (zp),Y table (hero_bank0.asm `LDA ($97),Y / ... / STA COLUP0` in the cave kernel) = per-row color is hero-true. AGENTS hero-first rule. |
| F1 | Beam: VBL-precomputed RAM table, drop `and LaserBeamOn` (−3c/line) | **REJECTED** | needs 8-12B RAM table; ZP full (no free sequential byte), LDA zp,Y doesn't exist. Branch-on-mask variants leave ENAM0 stale (old "bar showed without fire" bug class) |
| E1 | LineCount moved to X (`dex/bne` = −3c/line) | **REJECTED** | X collides with sprite `tax` (needs obj-in restore anyway ≈ C1's cost) AND ZP `$84` semantics: bank1 HUD writes `CollisionEndY→$84`, overscan PHM gates on `$84` — kernel stopping its `$84` writes changes a cross-bank contract |
| G1 | New kernel | **REJECTED** | 394/439 frames already exact; worst line 3c over; greenfield = weeks, same 76c wall |
| G2 | Weaken wall-model assert | **REJECTED** | forbidden (AGENTS frame-budget rule 1) |
| B1 | Option 2a: fold-pad `Overscan` literal automation (bank1 `jmp $Fxxx` hand-sync) | **CHOSEN step 3** | hand-sync fired again today ($F194→$F195); recurring trap, cheap automation |
| B2 | Option 2b: relocate a bank0 leaf to bank2 gap ($F37C-$F9D8) for 30-50B headroom | **revised → NOT executed** | Premise re-measured: the "1B pre-pad headroom" = verify_build's warn on the row before `org $FC68` = the `$FC49`-pin/E4 zone (MothYDerive fills it to $FC67). The main-growth zone = `.ds $FBF8 - *, 0` fill **$F9DB-$FBF7 = 541 B free** (lst row `F9DB .ds $FBF8 - *, 0`; PositionBallM1, eb156db, is the standing precedent — "the body sits in the $F9C4..$FBF7 fill"). New mid-file code grows into that fill; pads/pins absorb. A DropArm tramp move would add bank2 ZP mirrors + tramp byte-copy risk for headroom that already exists. |

## Chosen sequence (as executed)

1. C1 (X-restore) → attempted, failed, reverted
2. C2 (layout) — conditional, never triggered
3. A1 (revised) + split-tail `.Row` (eb156db) + LineCount-after-WSYNC reorder
   → build → sim GREEN
4. B1 (fold-pad automation) — landed in the prior session
5. B2 (bank2 leaf relocation) — revised to NOT executed (measurement below)
6. Full `./build.sh` + battery `tools/test_*.py`

## Known pre-existing quirks noted along the way (NOT fixed, out of scope)

- A==8 restore during the WATER strip: A1's `lda Temp` reads the `.Row`-staged
  band color (no X indexing) — the old `ldx RowIdx / lda ColupfBuf,X` dead-row
  read ($EA = bank1 scorePtr6) is gone with A1.

## Scenario gates finding (AGENTS expected Y=1/X=0/M=1; measured Y=40/X=16/M=13)

Two PRE-EXISTING causes (not from this session's edits — the stall trails are
A1/LC-independent: mid-band, `bne .Line` taken, resume pc `$F14D`):

1. **A0=11 coincidence line = 77c**: color+beam + taken `bcs .GrpZero` (3c) +
   obj-in. The normal obj-in line = 76c zero slack, so branch polarity is
   zero-sum — no branch reshuffle fits. Fix = duplicate the GRP0-blank + obj +
   tail fall-through for the GrpZero path (~30B, zone-A bytes fine) =
   **C3 registered, deferred**: kernel hot-zone surgery (page/cycle guards)
   + scenario gates are user-led per AGENTS (flicker/heavy-frame rule 3).
2. **OVER spikes** (max 3489/3258 > 3222 absorb) = documented heavy-frame
   family (rect-walk coincidence + f138 `EnterRoom` +1665c class) — user-led.

## Outcomes (filled 2026-10-05 session close)

- C1: attempted → failed → reverted (stale comment removed from row-advance).
- C2: not applied (conditional never triggered).
- A1: **CHOSEN (revised)** — `sta Temp` (.Row line ~688) + `bne .ObjNoRes /
  lda Temp` (.ObjZero A==8 only) + `beq .AfterObj` (1B saved vs jmp);
  enabled by moving `sta LineCount` after `sta WSYNC` in BOTH `.Row` setup
  paths (rows0/1 and `.RowLinesTide`). Gaps 77/79 → 74/76; first body
  rows0/1 = 75c, row2 = 72c; worst line 78c → 74c.
- B1: done (prior session) — verify_build `sync_overscan_literal` rewrites
  bank1's fold `jmp $Fxxx` + guard; hand-sync trap closed.
- B2: **revised → not executed** — 541 B free in the main-growth fill
  ($F9DB-$FBF7); see table row. DropArm was the only qualifying pure leaf
  (59B, event-driven) — tramp + bank2 mirror machinery measured and not needed.
- final sim/battery: `./build.sh` → wall-model **{263: 441}** all frames,
  assertions PASS, stall histogram = known-safe baseline only
  (65c/106c/124c/128c, ObjZero stalls 0); battery **19/20** —
  test_editor_roundtrip fails only at its pre-existing git gate (dirty tree,
  commits forbidden without request).
- battery repairs this session: test_enemy_movement `.Row` structural gate
  updated (comment-stripped gcode: LineCount after WSYNC); test_miner_colors →
  `bank2.asm` hand-copy EQUs `PlayerSpriteA $F8D8` / `PlayerSpriteB $F8E4`;
  test_phase2_ball baseline regenerated with the EQU-resync recipe (docstring
  updated) — bit-identical TIA trace at 26274 writes.
