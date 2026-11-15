# Playbot deaths — all 32 levels, new ROM (commit 9cbaa7f), 2026-11-15

Run: `tools/playbot.py` on every level, live stage (484 rooms), NTSC, all 32 levels reach the tally.
Pictures: `tools/playbot_deaths_report.py <logs>` (`#` wall, `.` air, `=` hot-rock row, `P` player,
`s` snake, `m` moth, `b` bat, `p` spider, `M` miner; one character = 8 px wide, 12 px high; the room is the
model's left half plus its mirror). The bot is deterministic: the deaths of the first run happened on the same
frames before today's bomb change, so none of them comes from the bomb staging or the bank reorg.

## Result

| | First run | After the playbot changes |
|---|---|---|
| Levels finished | 32/32 | 32/32 |
| Deaths | 12 in 10 levels | 9 in 8 levels |

| Cause (first run) | Deaths | Now |
|---|---|---|
| A. Free fall down a shaft onto an enemy waiting at the bottom | 8 (L3, 17, 18 x2, 22, 28, 29, 32) | **still 7** (L3, 17, 18 x2, 28, 29 + L32 moth); L22 fixed by the arrival/phase changes |
| B. Walked into a moth that drifted next to the bot (L20) | 1 | fixed |
| C. Arrived from below next to the room's snake (L25) | 1 | fixed (the router prefers another arrival column) |
| D. Waited inside a phase wall's span (L26) | 1 | fixed (also: the 8-bit clock wraps at 256, so the wall comes on up to 15 frames before a mod-90 phase says) |
| E. Feet in the hot-rock band (L22 room 14, probable) | 1 | fixed (no death there now) |
| new: moth rising under the bot, L15 room 6 | - | 1 |

## What changed in the bot (tools/playbot.py)
- phase walls: never stop inside a wall's span; start crossing only when the OFF window is long enough, counting the clock wrap;
- hot band: keep the 22-px box 6 px higher in a band directly above a hot middle band;
- router: arrival cells within 20 px of a hazard enemy's start cost 200 extra, so another column wins when there is one;
- moths/snakes ahead: back off to 16 px, turn with one tap, then hold and fire (the laser needs the enemy in front);
- before a drop, wait up to 300 frames while an enemy is under the shaft (does not help: see below).

## Why class A is still open
All remaining snake deaths are the same pattern: a one-column shaft whose floor is patrolled by a snake that stays
within 20 px of the column. The snake moves ~0.1 px/frame, so waiting does not clear it, and the sprite touches it at
y = 98 while the shaft walls still stop any sideways step (the box is clear of the walls only from y = 108). A side column
exists in none of these rooms (I tried: it also stranded the bot in a dead end on levels 18, 22 and 28 and was removed).
A human has the same problem unless he shoots or bombs the snake first. Options, not done: (1) let the bot drop a
bomb from a ledge above, (2) lower itself to the shaft mouth and fire at the snake when the laser row lines up,
(3) treat it as FORCED (the bot already has ), (4) make the generator keep floor patrols out from under a
one-column shaft. Your call.

### Remaining deaths (9)

#### Level 3, room 2 (frame 1557): moth

- model 109 "Shape n+S+Ladder+wideFloor", bottom_band=False
- player at x=39 y=92 (the frame before the life was lost), bot doing: `edge (1, 2, 4)->(1, 3, 4)`
- enemies in that frame: bat (55,49), moth (39,114)
- facts: moth at dx=+0 dy=+22

```
    ########.##.########   <- band 0
    ########.##.########
    ########.##.########
    #..................#   <- band 1
    #.....b............#
    #..................#
    ##...###....###...##   <- band 2
    ##...###....###...##
    ##..P###....###...##
    ##................##   <- band 3
    ##..m.............##
    ##................##
```

#### Level 15, room 6 (frame 2457): ?

- model 64 "Shape N+H+wideTop", bottom_band=False
- player at x=45 y=21 (the frame before the life was lost), bot doing: `edge (5, 0, 5)->(5, 0, 4)`
- enemies in that frame: miner (79,99), moth (47,44)
- facts: moth at dx=+2 dy=+23

```
    ###....#....#....###   <- band 0
    ###....#....#....###
    ###..P.#....#....###
    ....................   <- band 1
    .....m..............
    ....................
    ########....########   <- band 2
    ########....########
    ########.M..########
    ####################   <- band 3
    ####################
    ####################
```

#### Level 17, room 12 (frame 3493): snake

- model 11 "Shape S+H+Ladder", bottom_band=False
- player at x=71 y=98 (the frame before the life was lost), bot doing: `edge (11, 2, 8)->(11, 3, 8)`
- enemies in that frame: miner (39,99), snake (70,120)
- facts: miner at dx=-32 dy=+1; snake at dx=-1 dy=+22

```
    ####################   <- band 0
    ####################
    ####################
    ....................   <- band 1
    ....................
    ....................
    ##...###....###...##   <- band 2
    ##...###....###...##
    ##..M###....###...##
    ########P...########   <- band 3
    ########s...########
    ########....########
```

#### Level 18, room 12 (frame 4109): snake

- model 18 "Shape S+H+2Gap+Pillars", bottom_band=False
- player at x=55 y=98 (the frame before the life was lost), bot doing: `edge (11, 2, 6)->(11, 3, 6)`
- enemies in that frame: miner (79,99), snake (49,120)
- facts: miner at dx=+24 dy=+1; snake at dx=-6 dy=+22

```
    ####################   <- band 0
    ####################
    ####################
    ....................   <- band 1
    ....................
    ....................
    ##.....#....#.....##   <- band 2
    ##.....#....#.....##
    ##.....#.M..#.....##
    ###.##P######.##.###   <- band 3
    ###.##s######.##.###
    ###.##.######.##.###
```

#### Level 18, room 17 (frame 5175): snake

- model 89 "Shape n+S+2Gap+Ladder+wideCeil", bottom_band=False
- player at x=55 y=98 (the frame before the life was lost), bot doing: `edge (16, 2, 6)->(16, 3, 6)`
- enemies in that frame: snake (50,120), snake (7,48)
- facts: snake at dx=-5 dy=+22

```
    ##................##   <- band 0
    ##................##
    ##................##
    #..................#   <- band 1
    s..................#
    #..................#
    ##...#.#....#.#...##   <- band 2
    ##...#.#....#.#...##
    ##...#.#....#.#...##
    ###.##P######.##.###   <- band 3
    ###.##s######.##.###
    ###.##.######.##.###
```

#### Level 22, room 11 (frame 2742): snake

- model 33 "Shape n+S+H+2Gap+Ladder", bottom_band=False
- player at x=55 y=104 (the frame before the life was lost), bot doing: `edge (10, 2, 6)->(10, 3, 6)`
- enemies in that frame: snake (47,120), snake (65,84)
- facts: snake at dx=-8 dy=+16; snake at dx=+10 dy=-20

```
    ###.############.###   <- band 0
    ###.############.###
    ###.############.###
    ....................   <- band 1
    ....................
    ....................
    ##...#.#....#.#...##   <- band 2
    ##...#.#s...#.#...##
    ##...#.#....#.#...##
    ###.##P######.##.###   <- band 3
    ###.#s.######.##.###
    ###.##.######.##.###
```

#### Level 28, room 15 (frame 3827): snake

- model 89 "Shape n+S+2Gap+Ladder+wideCeil", bottom_band=False
- player at x=55 y=98 (the frame before the life was lost), bot doing: `edge (14, 2, 6)->(14, 3, 6)`
- enemies in that frame: snake (53,120), snake (10,48)
- facts: snake at dx=-2 dy=+22

```
    ##................##   <- band 0
    ##................##
    ##................##
    #..................#   <- band 1
    #s.................#
    #..................#
    ##...#.#....#.#...##   <- band 2
    ##...#.#....#.#...##
    ##...#.#....#.#...##
    ###.##P######.##.###   <- band 3
    ###.##s######.##.###
    ###.##.######.##.###
```

#### Level 29, room 15 (frame 8143): snake

- model 111 "Shape n+S+H+Pillars+wideFloor", bottom_band=False
- player at x=23 y=98 (the frame before the life was lost), bot doing: `edge (14, 2, 2)->(14, 3, 2)`
- enemies in that frame: moth (39,54), snake (18,120)
- facts: snake at dx=-5 dy=+22

```
    ########.##.########   <- band 0
    ########.##.########
    ########.##.########
    ....................   <- band 1
    ....................
    ....m...............
    ##.....#....#.....##   <- band 2
    ##.....#....#.....##
    ##.....#....#.....##
    ##P...............##   <- band 3
    ##s...............##
    ##................##
```

#### Level 32, room 18 (frame 4295): moth

- model 75 "Shape N+s+2Gap+Profile1", bottom_band=False
- player at x=55 y=32 (the frame before the life was lost), bot doing: `edge (17, 0, 6)->(17, 1, 6)`
- enemies in that frame: miner (39,99), moth (55,54)
- facts: moth at dx=+0 dy=+22

```
    ###.##.######.##.###   <- band 0
    ###.##.######.##.###
    ###.##.######.##.###
    #.....P..##........#   <- band 1
    #........##........#
    #.....m..##........#
    ###..##########..###   <- band 2
    ###..##########..###
    ###.M##########..###
    ###.############.###   <- band 3
    ###.############.###
    ###.############.###
```


### First run, all 12 deaths (before the playbot changes) (12)

#### Level 3, room 2 (frame 1064): moth

- model 109 "Shape n+S+Ladder+wideFloor", bottom_band=False
- player at x=39 y=100 (the frame before the life was lost), bot doing: `edge (1, 2, 4)->(1, 3, 4)`
- enemies in that frame: bat (55,49), moth (39,122)
- facts: moth at dx=+0 dy=+22

```
    ########.##.########   <- band 0
    ########.##.########
    ########.##.########
    #..................#   <- band 1
    #.....b............#
    #..................#
    ##...###....###...##   <- band 2
    ##...###....###...##
    ##...###....###...##
    ##..P.............##   <- band 3
    ##..m.............##
    ##................##
```

#### Level 17, room 12 (frame 2929): ?

- model 11 "Shape S+H+Ladder", bottom_band=False
- player at x=71 y=97 (the frame before the life was lost), bot doing: `edge (11, 2, 8)->(11, 3, 8)`
- enemies in that frame: miner (39,99), snake (67,120)
- facts: miner at dx=-32 dy=+2; snake at dx=-4 dy=+23

```
    ####################   <- band 0
    ####################
    ####################
    ....................   <- band 1
    ....................
    ....................
    ##...###....###...##   <- band 2
    ##...###....###...##
    ##..M###....###...##
    ########P...########   <- band 3
    ########s...########
    ########....########
```

#### Level 18, room 12 (frame 3220): ?

- model 18 "Shape S+H+2Gap+Pillars", bottom_band=False
- player at x=55 y=97 (the frame before the life was lost), bot doing: `edge (11, 2, 6)->(11, 3, 6)`
- enemies in that frame: miner (79,99), snake (52,120)
- facts: miner at dx=+24 dy=+2; snake at dx=-3 dy=+23

```
    ####################   <- band 0
    ####################
    ####################
    ....................   <- band 1
    ....................
    ....................
    ##.....#....#.....##   <- band 2
    ##.....#....#.....##
    ##.....#.M..#.....##
    ###.##P######.##.###   <- band 3
    ###.##s######.##.###
    ###.##.######.##.###
```

#### Level 18, room 17 (frame 3655): snake

- model 89 "Shape n+S+2Gap+Ladder+wideCeil", bottom_band=False
- player at x=55 y=98 (the frame before the life was lost), bot doing: `edge (16, 2, 6)->(16, 3, 6)`
- enemies in that frame: snake (50,120), snake (7,48)
- facts: snake at dx=-5 dy=+22

```
    ##................##   <- band 0
    ##................##
    ##................##
    #..................#   <- band 1
    s..................#
    #..................#
    ##...#.#....#.#...##   <- band 2
    ##...#.#....#.#...##
    ##...#.#....#.#...##
    ###.##P######.##.###   <- band 3
    ###.##s######.##.###
    ###.##.######.##.###
```

#### Level 20, room 11 (frame 2214): moth

- model 13 "Shape N+H+2Gap+Ladder", bottom_band=False
- player at x=55 y=48 (the frame before the life was lost), bot doing: `edge (10, 1, 5)->(10, 1, 4)`
- enemies in that frame: 14 (143,84), moth (47,46)
- facts: moth at dx=-8 dy=-2

```
    ###.##.######.##.###   <- band 0
    ###.##.######.##.###
    ###.##.######.##.###
    ....................   <- band 1
    .....mP.............
    ....................
    ##...#.#....#.#...##   <- band 2
    ##...#.#....#.#..?##
    ##...#.#....#.#...##
    ####################   <- band 3
    ####################
    ####################
```

#### Level 22, room 11 (frame 1562): snake/snake

- model 33 "Shape n+S+H+2Gap+Ladder", bottom_band=False
- player at x=55 y=98 (the frame before the life was lost), bot doing: `edge (10, 2, 6)->(10, 3, 6)`
- enemies in that frame: snake (53,120), snake (69,84)
- facts: snake at dx=-2 dy=+22; snake at dx=+14 dy=-14

```
    ###.############.###   <- band 0
    ###.############.###
    ###.############.###
    ....................   <- band 1
    ....................
    ....................
    ##...#.#....#.#...##   <- band 2
    ##...#.#s...#.#...##
    ##...#.#....#.#...##
    ###.##P######.##.###   <- band 3
    ###.##s######.##.###
    ###.##.######.##.###
```

#### Level 22, room 14 (frame 4338): ?

- model 96 "Shape n+H+2Gap+HotGate+wideCeil" (hot middle band), bottom_band=False
- player at x=71 y=14 (the frame before the life was lost), bot doing: `edge (13, 0, 8)->(13, 0, 9)`
- enemies in that frame: none

```
    ##................##   <- band 0
    ##................##
    ##......P.........##
    ....==.======.==....   <- band 1
    ....==.======.==....
    ....==.======.==....
    ###.##.######.##.###   <- band 2
    ###.##.######.##.###
    ###.##.######.##.###
    ####################   <- band 3
    ####################
    ####################
```

#### Level 25, room 6 (frame 1377): snake

- model 44 "Shape N+s+H", bottom_band=False
- player at x=71 y=122 (the frame before the life was lost), bot doing: `edge (5, 3, 8)->(5, 2, 8)`
- enemies in that frame: 14 (95,12), snake (67,120)
- facts: snake at dx=-4 dy=-2

```
    ########....########   <- band 0
    ########...?########
    ########....########
    ....................   <- band 1
    ....................
    ....................
    ########....########   <- band 2
    ########....########
    ########....########
    ########.##.########   <- band 3
    ########s##.########
    ########P##.########
```

#### Level 26, room 10 (frame 2852): phase wall

- model 47 "Shape s+H+2Gap", bottom_band=False
- player at x=24 y=36 (the frame before the life was lost), bot doing: `edge (9, 1, 3)->(9, 1, 2)`
- enemies in that frame: none
- feature cells (band, col, type): [[1, 2, 10]]
- facts: phase wall cell 2: ON (clock 22/90)

```
    ####################   <- band 0
    ####################
    ####################
    ...P................   <- band 1
    ....................
    ....................
    ###.##.######.##.###   <- band 2
    ###.##.######.##.###
    ###.##.######.##.###
    ###.############.###   <- band 3
    ###.############.###
    ###.############.###
```

#### Level 28, room 15 (frame 3195): snake

- model 89 "Shape n+S+2Gap+Ladder+wideCeil", bottom_band=False
- player at x=55 y=98 (the frame before the life was lost), bot doing: `edge (14, 2, 6)->(14, 3, 6)`
- enemies in that frame: snake (52,120), snake (9,48)
- facts: snake at dx=-3 dy=+22

```
    ##................##   <- band 0
    ##................##
    ##................##
    #..................#   <- band 1
    #s.................#
    #..................#
    ##...#.#....#.#...##   <- band 2
    ##...#.#....#.#...##
    ##...#.#....#.#...##
    ###.##P######.##.###   <- band 3
    ###.##s######.##.###
    ###.##.######.##.###
```

#### Level 29, room 15 (frame 7159): ?

- model 111 "Shape n+S+H+Pillars+wideFloor", bottom_band=False
- player at x=23 y=97 (the frame before the life was lost), bot doing: `edge (14, 2, 2)->(14, 3, 2)`
- enemies in that frame: moth (39,42), snake (20,120)
- facts: snake at dx=-3 dy=+23

```
    ########.##.########   <- band 0
    ########.##.########
    ########.##.########
    ....................   <- band 1
    ....m...............
    ....................
    ##.....#....#.....##   <- band 2
    ##.....#....#.....##
    ##.....#....#.....##
    ##P...............##   <- band 3
    ##s...............##
    ##................##
```

#### Level 32, room 18 (frame 3699): moth

- model 75 "Shape N+s+2Gap+Profile1", bottom_band=False
- player at x=55 y=28 (the frame before the life was lost), bot doing: `edge (17, 0, 6)->(17, 1, 6)`
- enemies in that frame: miner (39,99), moth (55,50)
- facts: moth at dx=+0 dy=+22

```
    ###.##.######.##.###   <- band 0
    ###.##.######.##.###
    ###.##.######.##.###
    #.....P..##........#   <- band 1
    #.....m..##........#
    #........##........#
    ###..##########..###   <- band 2
    ###..##########..###
    ###.M##########..###
    ###.############.###   <- band 3
    ###.############.###
    ###.############.###
```

