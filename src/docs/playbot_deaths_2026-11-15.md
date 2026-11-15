# Playbot deaths — all 32 levels, new ROM (commit 9cbaa7f), 2026-11-15

Run: `tools/playbot.py` on every level, live stage (484 rooms), NTSC. All 32 levels finish (tally reached).
12 deaths in 10 levels. Re-run with `--log` for the last 48 frames of each (deterministic: same frames as the
earlier run before the bomb change, so none of this is caused by the bomb staging or the bank reorg).

## Summary

| # | Cause | Deaths | Forced? |
|---|-------|--------|---------|
| A | Bot free-falls down a shaft (no input) onto an enemy waiting at the bottom | 8 | no — steering sideways avoids it |
| B | Bot steps toward a moth that wandered next to it | 1 | no |
| C | Bot arrives from below at an x where the room's snake starts | 1 | no — a different arrival x avoids it |
| D | Bot waits inside a phase wall's span; wall switches on | 1 | no |
| E | Bot flies diagonally with its feet in the hot band (probable; not confirmed) | 1 | no (to be confirmed) |

None of the 12 looks like a game bug. All are bot weaknesses; the playbot's own `killer()` labelled four of them "?"
because the snake sat 23 px below (its window is 22), so those four are really snakes.

## Detail

### A. Falling onto an enemy at the bottom of a shaft (8)
The bot crosses a band edge downward (`edge (room, 2, c) -> (room, 3, c)`) with the stick released, so it falls at a
constant 1-2 px/frame straight down column x = 55 (23, 39, 71 elsewhere) and lands on an enemy patrolling the floor
(snakes at y = 120, moths at y = 50 / 122). In every trace the enemy is 2-5 px off the bot's x and the bot never steers.

| Level | Frame | Room | x, y at death | Enemy |
|---|---|---|---|---|
| 3  | 1064 | 2  | 39, 100 | moth at (39, 122) |
| 17 | 2929 | 12 | 71, 97  | snake at (67, 120) (labelled "?") |
| 18 | 3220 | 12 | 55, 97  | snake at (52, 120) (labelled "?") |
| 18 | 3655 | 17 | 55, 98  | snake at (50, 120) |
| 22 | 1562 | 11 | 55, 98  | snake at (53, 120) + snake at (69, 84) |
| 28 | 3195 | 15 | 55, 98  | snake at (52, 120) |
| 29 | 7159 | 15 | 23, 97  | snake at (20, 120) (labelled "?") |
| 32 | 3699 | 18 | 55, 28  | moth at (55, 50), mid-air |

A human would nudge left/right during the 8+ frames of the fall. Bot fix: steer away from any enemy whose x is within
~14 px of the drop column, or wait at the top for it to patrol away (the bot already has `--safe` to retry an edge).

### B. Level 20, frame 2214, room 11 (moth)
The bot stands still at (55, 48) for 30+ frames waiting at an edge; a moth wanders to (47, 46), 8 px left. On the
last frame the bot presses LEFT (`sw $BF`) — straight into it. Bot error: it moved toward an enemy 8 px away.

### C. Level 25, frame 1377, room 6 (snake)
The bot climbs out of room 10 at x = 71 and arrives at the bottom of room 6 (y = 122). Enemies reset to their authored
positions on entry, and the snake starts at x = 67 on the floor, 4 px from the arrival column: contact on the first
frame. Entering at another x within the link width avoids it. Generator note (optional): a floor patrol that starts
under a link arrival column makes the entry a coin toss for a player who does not pick the column.

### D. Level 26, frame 2852, room 10 (phase wall)
The bot waits at (24, 36) for 8+ frames while the phase wall at cell 2 cycles; its span (x 4..32 in band 1) contains the
bot, and the wall turns on (clock 22/90) while it is inside. The wait position must be outside the span.

### E. Level 22, frame 4338, room 14 (no enemy in the room) — probable, not confirmed
The bot enters room 14 from above at (47, 0) and flies right and down to (71, 14). The room is model 95
("Shape n+H+2Gap+HotGate+wideCeil", `mid_band_type` 1: the middle band is hot rock) and the global phase bit `dm` is
on ($20). At y = 14 the 22 px sprite already reaches y = 36, the top of band 1, whose cells 4-5 (x 64..95) are hot rock.
So it most likely burned its feet on the hot band while the gate was on. The bot's explainer only knows the hot band
when the *top* of the sprite is in it (`band_of(y) == 1`), which is why it printed `?`. I did not replay this one
with the sprite box to prove it; if you want, I can check the ROM's hot-rock overlap rect against this position.

## What was not looked at
- No Stella run; all from the py65 playbot.
- Whether level 25 / the A-class shafts are fair for a human at normal speed (they are for any steering input).
