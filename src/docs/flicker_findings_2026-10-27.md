# Frame-length flicker — sweep findings (2026-10-27/28, user: "flicker when I used the laser")

Method: `tools/sweep_frame_budget.sh` runs `sim_frame_budget.py` (fire held, thrust, a
bomb) in all 211 rooms of the live stage. `build.sh` only gates level 1 room 1.
Debug knobs added to the sim: `SIM_SPD` (force EnemySpd), `SIM_WSDBG` (per-frame kernel
WSYNC count, player/laser state, key, lives, kernel lines), `SIM_WSPC` (+`SIM_WSPC_FROM`)
(WSYNC call sites that differ between the shortest and longest kernel frame),
`SIM_WSLINES` (physical lines between consecutive WSYNCs, per frame shape),
`SIM_GAPDBG` + `SIM_GAPMIN` + `SIM_GAPSEQ` (instruction trail of a long gap).

## What the metric means

The WSYNC COUNT per frame is NOT the frame length. Row entry (`$F106`, `$F10F`) always
spans 2 physical lines and the slot-1 hook (`$F7AA`) spans 3, so a frame with the hook
has 196 WSYNCs and a frame without it has 197, and both are 202 physical lines. Only the
physical total matters (`SIM_WSLINES kernel_lines=`). The first draft of this note blamed
the 92-176 cycle gaps at the row entry; level 1 has them too, so they are normal.

## Cause 1 (fixed): level banner on level 20

For 120 frames after a level loads, `SetupScorePointers` shows "LV 0 t o". Its tens digit
came from a `cmp #10 / sbc #10 / inx` loop, 12 cycles per tens. At level 20 (2 passes) the
HUD setup crossed a line boundary and the whole banner ran 203 kernel lines (a 1-line
jump when the banner ended). Replaced by two 20-byte tables (`LvOnes8`, `LvTens8`).
Checked: level 20 is 202 lines in every frame.

## Result of the re-run (211 rooms, after the banner fix)

Every room is now 202 kernel lines in every frame (`SIM_WSLINES`): the kernel itself is
stable. What is left is OVERSCAN overrun: frames of 273-310 lines (a rolling picture for
that frame) in 193 of 211 rooms, 4,346 of 232,311 frames (1.9%), growing with the level:

| levels | bad frames per room (of ~1,100) |
|---|---|
| 1-5 | 0 |
| 6-10 | 0-30 (x1.5 enemy speed) |
| 11-15 | 30-60 (x2) |
| 16-20 | 90-140 (x2.5), longest frame 290-310 lines |

## The enemy speed multiplier IS the remaining cause (earlier note was wrong)

`L16 room 1` with `EnemySpd` forced to 2 (x1): 1,049 of 1,099 frames are 272 lines;
natural x2.5: 955. `SIM_UECOST=1` measures one `UpdateEnemies` call: 2 enemies cost
324-636 cycles at EnemySpd 5 (2-3 passes of ~200 cycles). The overscan has ~600 cycles
of slack at level 1, and the laser frames (`LaserHitTest` ~260, `PlayerHitsMap`,
`CheckBandTouch`) eat most of it, so laser + extra passes overflows. This matches the
user's "flicker when I use the laser".

## Options (not applied: each changes gameplay or needs Stella)

1. Cap the multiplier at x1.5 (EnemySpd <= 3): zero cost increase over the budget except
   level 6-10 spikes; enemies on levels 11-20 are slower than designed.
2. Skip the extra passes on frames where the laser is active (enemies hiccup while firing).
3. Run one pass in the VBL (it has ~270 cycles spare at level 16: too little for a pass).
4. Make a pass cheaper (profile `UE_*` per type; ~200 cycles per pass for 2 enemies).
5. Spread the passes over two frames (one extra pass every other frame, same average
   speed, half the peak). Needs EnemySpd semantics changed in `UEPrologue`.

Recommended: 5, then re-run `tools/sweep_frame_budget.sh` (target: bad frames < 1%).

## Result (2026-10-28): overscan governor in `UEEpilogue`

A/B on five rooms showed the laser hit-test gate (alternate-frame enemy loop in bank2)
changes nothing (144 vs 144 bad frames in L16 room 1). `SIM_OVPROF=3100` (cycles per
routine, frames over 3100c vs the rest) and the `PHMCALLS` lines show the real cause:
`PlayerHitsMap` is called 2-4 times on the bad frames (StepDown per falling pixel + the
horizontal step, ~250-300c each) and the 2-3 enemy passes stack on top.

Fix: `UEEpilogue` starts an EXTRA pass only while `INTIM >= UE_MIN_INTIM` (12 units =
768c); otherwise the pass is dropped. The first pass always runs. `SIM_GOV=N` emulates it
without a rebuild (N=12 and 16 were equal). Sweep: 4,276 -> 1,904 bad frames of 231,889
(1.84% -> 0.82%); L16 room 1 144 -> 53. Cost: ~7% of enemy passes dropped in the worst
rooms (enemies slow down only on frames that were about to overrun).
`tools/test_enemy_speed.py` covers it (section 2b).

Left: ~1 frame per room in levels 1-5 (boot/room entry) and 2-20 per room above that,
all PlayerHitsMap-heavy frames. Next candidate: test the fall in one call for vy >= 2.
