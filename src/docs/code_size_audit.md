# Code-size audit — 2026-10-19 (post-chunk A2, commit `78d996b`)

Goal: find out where the 9.3 KB of code really goes, what is duplicated, and
what is simply more game than HERO — before deciding on a reorganisation.
Everything below is measured from `bank*.lst` (dasm listing: every emitted byte
attributed to its enclosing global label) and from `bank*.bin` (byte-level
duplication search). Nothing here is estimated unless it says so.

## 1. Inventory

| bank | code | data | used | free | role today |
|---|---|---|---|---|---|
| bank0 | 3180 | 360 | 3540 | 556 (1 B pre-pad) | kernel, VBL, overscan, physics, collision, laser, level load |
| bank1 | 2628 | 554 | 3182 | 914 | HUD band, title, sounds, raft body, wall marking |
| bank2 | 2513 | 748 | 3261 | 835 | room load, enemies, bomb, laser clamp, overlays, title sequence |
| bank3 | 1019 | 74 | 1093 | 3003 | crunch bodies |
| **total** | **9340** | **1736** | **11076** | **5308** | + 4571 B fill |

Top routines (bytes, bank):
`MenuMain` 806 b1 · `SelectActiveObject` 289 b0 · `VCS3` 271 b3 ·
`TitleKernel` 270 b1 · `TitleSequence` 267 b2 · `RaftBody` 266 b1 ·
`MothDoWalk` 216 b2 · `UpdateP0Vertical` 214 b0 · `BombMarkWalls` 214 b1 ·
`HOVFeatEntry` 210 b3 · `EnterRoomB2` 179 b2 · `PhaseBlink` 173 b2 ·
`LaserInput` 171 b0 · `LoadLevel` 156 b0 · `BuildColupF` 144 b2 ·
`PlayerHitsMap` 140 b0 · `SetupScorePointers` 123 b1 · `PhHcrEntry` 125 b3 ·
`VcrShutter` 129 b2 · `OvM1Block` 128 b2 · `CaveKernelRow` 67 b0.

## 2. Feature cost map (clusters, bank-spanning)

| cluster | bytes | where |
|---|---|---|
| HUD: score/lives/bombs/bar | **1033** | `MenuMain` 806 + `SetupScorePointers` 123 + `DigitGfx` 104 (data) |
| title + intro + footer + music | **978** (+fonts/sprites) | `TitleKernel` 270, `TitleSequence` 267, `TitleBandPrep` 104, `FooterBand` 101, `MusicTick` 99, `TitlePlayerBand` 89, `TitleFont` 48 |
| crunch (v + h shutters) | **1324** | `VCS3` 271, `HOVFeatEntry` 210, `VcrShutter` 129, `PhHcrEntry` 125, `B3StageBand` 132, `SBT_B` 53, `OvShutBand` 63, `OvM1Block` 128, `HOVafterGate` 68, `HcrPush` 70, `HcrClock` 61, tables 14 |
| enemies | ~795 | `SelectActiveObject` 289 (shared), `MothDoWalk` 216, `UE_Tentacle` 84, `CEH_HasMore` 81, `MothRoutine` 64, `DeriveEnemyY` 61 |
| kernel + core | ~1111 | `VBLTimer` 136, `SliceReentry` 135, `Overscan` 109, `CaveKernelRow` 67, `StartFrame` 38 + inline `.Row`/`.Line` bodies |
| physics / collision | ~640 | `UpdateP0Vertical` 214, `LoadLevel` 156, `PlayerHitsMap` 140, `StepDown` 57, `DropArm` 59 |
| room load / staging | ~496 | `EnterRoomB2` 179, `PhaseBlink` 173, `BuildColupF` 144 |
| bomb / tally | ~536 | `BombTick` 72, `BombMarkWalls` 214, `BombEnemyBlastBody` 90, `TallyEntry` 97, `TallyWork` 63 |
| laser | ~380 | `LaserInput` 171, `LaserWallClamp` 94, `LaserClampDone` 79 |

## 3. Duplication found (measured)

1. **Cross-bank switch machinery: 92 sites / 512 B.** 80 pads
   (`sta $1FFx / jmp` = 6 B), 8 returns (4 B), 4 others. Banks: b0 36, b1 23,
   b2 24, b3 9. This is F6 structural, but the *count* is a consequence of the
   current ad-hoc placement, not of the design.
2. **The same 4-byte bit table exists three times**: `EnemyBitTable` in bank0,
   `EnemyBitTable` again in bank2, `RaftBitTab` in bank1 (same `$01,$02,$04,$08`).
3. **Two band-mask table sets for one concept**: `OvHead`/`OvTail` (bank2) and
   `CrPfx0/1/2` (bank3) — both encode "which rows are covered by band N".
4. **Two crunch clock implementations**: `VcrStateTab` (32 B table, bank2) and
   `CrunchClock` (bank3) — plus inline `lsr/lsr` folds in `PhHcrPre`. The old
   `VcrCoveredState` was deleted; the other two remain.
5. **Two row/band conversions**: `YToRowTable` (48 B, bank0) and
   `BandRowFromLine` (bank2), plus an inline `/48` in `MothDoWalk`.
6. **Duplicate cell-walk prologue**: pixel box → cell rows/cols + mirror swap
   exists in `PlayerHitsMap` (~55 B) and `MothDoWalk` (~50 B). Cannot be shared
   without a `jsr`, which the measured stack floor forbids.
7. **`M1OffTab` now exists twice** (bank2 + bank3) — a duplication *created* by
   chunk A2, when the table moved with `StageBandTab`.
8. **Two title renderers**: `TitleKernel` (48px text) and
   `TitleBandPrep`/`TitlePlayerBand` (the jet + footer band) are separate
   passes with their own setup.
9. **Two tally paths**: `TallyWork` (bank0) + `TallyEntry` (bank2), split only
   because of the bank boundary.

## 4. "Does more than needed"

- **48-pixel sprite score**: `MenuMain` 806 + `SetupScorePointers` 123 +
  `DigitGfx` 104 = **~1033 B**. HERO renders its score from baked per-scanline
  PF tables (data), with a much smaller routine. We chose the sprite technique
  in 2026-09 (docs/font/48px_score_skill.md).
- **Title/intro cluster ~978 B + fonts**: animated jet on the title, intro
  sequence (`TitleSequence` 267), music player (99), footer band (101),
  copyright font. HERO's title is a static screen.
- **Tally + level banner + drop-in** ~220 B: presentation features.
- **Crunch cluster 1324 B** for two shutter types.

## 5. Opportunities (base = measured, saving = estimate)

| # | opportunity | base | est. saving | risk | prereq |
|---|---|---|---|---|---|
| 1 | one crunch machine: one mask table, one clock, one staging path | 1324 | **200-300** | medium (tests exist) | A3 (space) |
| 2 | co-locate features so pads disappear (A3+C2) | 512 | **100-150** | medium | A3 |
| 3 | score renderer → PF-table (HERO style) | 1033 | **200-400** | high (visible output) | user OK on look |
| 4 | title/intro simplification (drop music/footer/animated jet) | 978+ | **500-900** | product decision | user |
| 5 | unify row/band math + bit tables + M1OffTab | ~70 | **30-50** | low | — |
| 6 | tally/banner simplification | ~220 | **60-100** | product decision | user |
| 7 | re-pin the 1919 B of pinned fill in banks 0-2 | (fill) | up to 1500 | very high (every literal) | dedicated session |

Realistic total without cutting features and without the re-pin: **~350-500 B**
(items 1, 2, 5). With the score rewrite: **~550-900 B**. With feature cuts:
**~1.5 KB**.

## 6. Proposed reorganisation (one feature = one bank)

| bank | target content |
|---|---|
| bank0 | kernel + VBL/overscan + input + physics + collision (the hot loop) |
| bank1 | HUD + audio + title (presentation) |
| bank2 | gameplay: room load, enemies, bomb, laser, overlays |
| bank3 | data (level data, models) + crunch (the one machine) + overflow |

Rules that come out of this audit:
- a feature lives in ONE bank; no ping-pong pads inside a feature;
- shared tables live in the bank that reads them (or are copied once, with the
  reason written next to them);
- the pad count is a metric to watch (currently 92).

## 7. Sequencing

1. **A3** (level data → bank3, readers follow): stops the hole-shuffling and
   gives bank3 the space the dedupe work needs. ~1 session, established design.
2. **Crunch unification** (item 1 + part of 2): 200-300 B, tests already exist.
3. **Small dedupe** (item 5): 30-50 B, low risk.
4. **Score renderer** (item 3): 200-400 B, needs a user decision on the look.
5. **Title/feature cuts** (items 4 and 6): product decisions.

## 8. Open decisions

- Do we keep the 48px sprite score, or adopt HERO's PF-table score (smaller
  code, different look)?
- Do we keep the animated title + intro music + footer, or a static title?
- Is the re-pin of banks 0-2 worth a dedicated risky session (up to ~1.5 KB)?
