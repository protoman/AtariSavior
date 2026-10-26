# Enemy speed multiplier (2026-10-26)

User request: every 5 levels the enemies get faster: x1.5, x2, x2.5, x3 ...

| Level (1-based) | 1-5 | 6-10 | 11-15 | 16-20 | 21+ |
|---|---|---|---|---|---|
| multiplier | x1 | x1.5 | x2 | x2.5 | x3 |

`EnemySpd` = `2 + Level / 5` half-units per frame (0-based Level), set by
`LoadLevelB2` (`.LLspd`, a subtract-5 loop).

## Mechanism
* Every enemy motion was gated by / derived from a SHARED clock (`EnemyRamP` for
  the bat, spider, tentacle and moth bobs and the moth patrol; `TickCounter` for
  the snake and the tentacle chase). Those clocks also drive the player's walk
  cycle, the water tide, the hcrunch band and the laser tone, so they cannot be
  sped up. Enemies now read their own clock, `EnemyClk` (`$D7`). The raft (a
  platform) and the hazards keep the shared clocks.
* `UpdateEnemies` runs one PASS per clock tick. `UEPrologue` (hole `$FE7B`) adds
  `EnemySpd` to the odd-half carry `EnemyFrac`, `passes = sum >> 1` (x1.5 runs
  1, 2, 1, 2 ... passes) and does the first `inc EnemyClk`; `UE_Exit` jumps to
  `UEEpilogue` (hole `$FBE8`), which runs the next pass (`inc EnemyClk`, back to
  `UEBody`) or returns. Entry and exit are `jmp`s, never a nested `jsr`, so the
  stack floor (min SP `$F8`) is unchanged. `DeriveEnemyY` reads the final clock
  once per frame, so the Y bobs advance `EnemySpd / 2` ticks per frame too.
* ZP `$D7-$DA` (the old "$CC-$DF free" note was stale; see zp_layout_skill.md).

## Cost
Each extra pass re-runs the whole enemy update (<= 3 enemies; the tentacle probe and
the moth rect walk dominate). `sim_frame_budget` at level 20 (x2.5) in a tentacle
room: the steady frames are identical to the pre-change ROM (same median segment
cycles, same list of bad frames); only the room-transition frame grows (+447c on a
frame that was already over budget).

## Guards
`tools/test_enemy_speed.py` (EnemySpd per level, passes per frame 20/30/40/50/60
ticks over 20 frames for x1..x3, and no enemy gate left on a shared clock),
`test_enemy_movement.py` (source guards updated to `EnemyClk`).
