# Power cell (2026-10-26)

User request: an object that fully recharges the timer, for stages that need
more than the 120 s bar; the generator estimates the time and places cells.

## Runtime
* Enemy record **type 14 = KEY|8** (b3 folds away under every `and #7`, so the
  type consumers that never learnt about cells treat it as a key).
* `CheckEnemyHit` -> key arm -> **`CEH_KeyDisp`** (bank0, `$FBA2` hole after
  `ObjColorTab`): re-reads the record, a type-14 record vanishes (dead bit, no
  life, no score), `BarLevel = 120`, and bit `RoomNo & 3` of
  `LevelStartRoom` b3-0 latches. `TickCounter` is untouched on purpose.
* **Once per level**: bank2 `EBLER_Next -> EBLCellCheck` pre-marks a taken cell
  dead on every room entry. The bits live with the level (reset by `LoadLevel`;
  a normal death keeps them, like the key). `LF_B0Tail` used to load
  `LevelStartRoom` as the respawn room; it loads `#0` now (the start room is a
  constant), which is what freed b6-0.
* Keys and cells are **not targets any more**: laser tip, laser body and bomb
  blast skip type 6/14 (a shot key used to die for the visit).
* Art: 4 rows (`$7E,$A5,$A5,$7E`, the atomic cell) in the KEY block's rows 12-15, so the KEY
  window is now 12 rows (`ObjHeightTab[6]`, both banks); `ObjHeightTab[14]=4`,
  `ObjSpriteOffTable[14]=OBJ_CELL(12)`, colours all cyan (`$9E`) in
  `ObjColorTab`. bank2's slot-1 type tables moved to `$FC29` (they now cover
  types 13/14 and the slot-1 type mask is `#$0F`).

## Tooling
* Editor: brush `E. Power cell` (`BrushTool::ADD_CELL`, `EnemyType::POWER_CELL`).
* `convert_level`: type 14 allowed; hard-fails two cells in rooms that agree
  mod 4 in one level, and a cell in a door room. `verify_build` accepts 14.
* Generator (`PlanPowerCells`, last pass): `AnalyseReach` now also returns the
  cheapest route in **estimated play time**. Constants (`kRoute*`, `kCell*`;
  mirrored in `tools/stage_reach.py`, tune BOTH): human = 3x the ideal 1 px/frame
  / 30 frames per band, +4 s per room entered, budget 90 s between refills,
  cells aimed ~65 s after the previous refill. A cell goes on a route cell at
  least 3 steps from the room's arrival/exit, in a 4-row room (not start, goal,
  door, hcrunch, phase, water floor), evicting a plain enemy when the room is
  full. Current stage: levels 10, 19 and 20 get one cell each.
* Guards: `tools/test_power_cell.py` (real frozen CheckEnemyHit / EBLER /
  laser / blast), `test_generator` (longest stretch <= 90 s, cell rooms
  distinct mod 4, no cell in start/goal/hcrunch/door, none below level 9),
  `stage_reach.problems` (warns when a live stage needs a cell).

## Not done / caveats
* The time model is a heuristic; nobody has timed a human on these levels.
  Raise `kRouteHuman` or lower the budget if cells feel late.
* The cell sprite has not been looked at in Stella.

## Pickup sounds (2026-10-26)
`PickupSnd` (bank0, `$FC3C` hole): A = AUDF0 pitch, channel 0 square for 8 frames
through the `BombSnd` hold (UpdateBombSound counts it down, the laser/jet sounds
respect it). Cell = 6 (highest, `CellTail`), key = 9, miner rescue = 12
(`MinerMore`); the tally coin stays 24 (lowest). The last miner's blip is the
tally's own coin. Guards: `test_power_cell.py` (key and cell set the hold),
`test_miners.py` (rescue).
