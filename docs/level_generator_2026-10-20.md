
## 10. Gate and phase rooms: enemy in the floor band (2026-10-26)

The gate/phase cell is row 1 (band 1). Crossing used to cost two lives (the
crush, then the band-0 bat the player fell back onto -
`screenshots/bugs/enemy_double_kill`). The generator now puts that room's one
enemy in the FLOOR band (band 3), leaving band 2 empty between gate and enemy,
and the arrival pass may only relocate it to the floor band or drop it. Hand-
authored rooms are not restricted. The twogap spider pass skips Phase rooms.
`test_generator` fails a gate/phase room with a non-key enemy in band 1 or 2
(live generate: 19 phase rooms keep an enemy, 9 have none for lack of floor air).

Also enforced and tested: no two objects (enemies, lamps) share a column in any
room, whatever the band.

## 11. Extra miners and power cells (2026-10-26)

See `docs/miners_2026-10-26.md` and `docs/power_cell_2026-10-26.md`. The last
passes of the stage build are: finishability repair -> `PlaceExtraMiners` ->
`PlanPowerCells`. Cells may sit on any reachable air cell of a route room (the
nearest free one) and a full room gives up a plain enemy.
