# Band 2 drawing sheet (2026-10-24)

Band index runs top to bottom, 36 lines each: band 0 = ceiling, band 1 = the
walking aisle, **band 2 = the third band from the top**, band 3 = floor /
water strip / miner rock.

Legend: `#` wall (solid, collides), `.` air, `H` hot wall (kills on touch),
`P` phase cell (blinks solid/air), `C` crunch cell (feature overlay).

Each drawing: model half (10 cells) then the 20 columns as drawn (the
playfield reflects at cell 9). Object y is a 12-px display row.

## Shape n+S — plain room, both vertical links (single wide gap at 8/9)

**live (band 2 = neck)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  #......... | #.................#
b2  72-107  ########.. | ########...########   the descent
b3 108-143  ########.. | ########...########
```
**widened (band 2 = band 1 aisle + pillars at cells 2 and 7)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  #......... | #.................#
b2  72-107  #.#....#.. | #.#....#...#....#.#   chamber + pillars
b3 108-143  ########.. | ########...########
```
## Shape n+S+2Gap — route choice: two separate gaps at 3 and 6

**live (band 2 = neck)**

```
b0  0- 35   ###.###### | ###.###########.###
b1  36- 71  #......... | #.................#
b2  72-107  ###.##.### | ###.##.#####.##.###   the descent
b3 108-143  ###.##.### | ###.##.#####.##.###
```
**widened (band 2 = band 1 aisle + pillars at cells 2 and 7)**

```
b0  0- 35   ###.###### | ###.###########.###
b1  36- 71  #......... | #.................#
b2  72-107  #.#....#.. | #.#....#...#....#.#   chamber + pillars
b3 108-143  ###.##.### | ###.##.#####.##.###
```
## Shape N+Water — water goal room (bottom band = water, miner rock)

**live (band 2 = neck)**

```
b0  0- 35   ########.. | ########...########
b1  36- 71  #......... | #.................#
b2  72-107  ########.. | ########...########   the descent
b3 108-143  #..##..... | #..##.........##..#
```
**widened (band 2 = band 1 aisle + pillars at cells 2 and 7)**

```
b0  0- 35   ########.. | ########...########
b1  36- 71  #......... | #.................#
b2  72-107  #.#....#.. | #.#....#...#....#.#   chamber + pillars
b3 108-143  #..##..... | #..##.........##..#
```
## Shape n+H+Channel — channel: hot shaft over open water, cross low on the raft

**live (band 2 = neck)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  .......... | ...................
b2  72-107  ########.. | ########...########   the descent
b3 108-143  #......... | #.................#
```
**widened (band 2 = band 1 aisle + pillars at cells 2 and 7)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  .......... | ...................
b2  72-107  ..#....#.. | ..#....#...#....#..   chamber + pillars
b3 108-143  #......... | #.................#
```
## Shape n+S+Gate — phase corridor: band 1 has walls except the corridor cell 8

**live (band 2 = neck)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  ########.# | ########.#.########
b2  72-107  ########.# | ########.#.########   no aisle to widen: band 2 must stay the corridor
b3 108-143  ########.. | ########...########
```
*widened == live for this shape.*

## Shape N+H+Gallery — hot room with an arch/gallery (arch content lands in band 3)

**live (band 2 = neck)**

```
b0  0- 35   ########.. | ########...########
b1  36- 71  .......... | ...................
b2  72-107  ########.. | ########...########   the descent
b3 108-143  ########## | ###################
```
**widened (band 2 = band 1 aisle + pillars at cells 2 and 7)**

```
b0  0- 35   ########.. | ########...########
b1  36- 71  .......... | ...................
b2  72-107  ..#....#.. | ..#....#...#....#..   chamber + pillars
b3 108-143  ########## | ###################
```
## HCRUNCH room (live: level 15 room 5, Shape n+S + band-1 crunch cells 0..9)

The crunch is a **feature overlay on band 1**: the whole band is authored as
crunch cells (0..9) and the engine closes the prefix in from the left. It is
not part of the model, so widening band 2 would open a path *under* it.

**live (works today: band 2 is solid, nobody can go under)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  #......... | #.................#
b2  72-107  ########.. | ########...########   solid -> the crunch gates
b3 108-143  ########.. | ########...########
```
**widened naively (BROKEN: the player drops under the crunch)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  #......... | #.................#
b2  72-107  #.#....#.. | #.#....#...#....#.#   open -> bypass
b3 108-143  ########.. | ########...########
```
**hcrunch keeps the neck (C1: every other room widened)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  #......... | #.................#
b2  72-107  ########.. | ########...########
b3 108-143  ########.. | ########...########
```
**hcrunch with a shorter prefix (C2: crunch 0..5, band 2 walled only there)**

```
b0  0- 35   ########.# | ########.#.########
b1  36- 71  #......... | #.................#
b2  72-107  ######.... | ######.......######   walls under the crush, chamber on the right
b3 108-143  ########.. | ########...########
```
