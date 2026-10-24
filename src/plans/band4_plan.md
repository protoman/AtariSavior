# Four-band cave (N=4) — migration plan

User decision 2026-10-23: go from 3 bands of 48 lines to **4 bands of 36** so
stages carry a **10x4** grid — more vertical complexity, same total cave
height, same sprite sizes, same colours, same no-flicker rules. The 32K of F4
space is what makes the extra level data affordable.

## Geometry (as built, 2026-10-23)

| | before | now |
|---|---|---|
| `TILE_ROWS` | 3 | **4** |
| `LINES_PER_TILE` | 48 | **36** (multiple of 4 — `YToRowTable` indexes `line>>2`) |
| `CAVE_LINES` | 144 | 144 (**unchanged**) |
| `PLAYER_SPRITE_H` | 22 (8x22 art) | unchanged |
| `PLAYER_MAX_Y` | 122 | 122 (**unchanged**) |
| water surface (first water body) | cave line `132+off` | `132+off` (**unchanged**) |
| cave picture lines | 147 (4 setups + 143 bodies) | **148** (4 setups + 144 bodies) |
| frame wall-model | cave **267.0** / title **267.0** | cave **270.0** / title **267.0** |

Band = 1 setup line + 36 bodies. The bottom band is `24+off` bodies followed by
the `.WaterRow` pass (`12-off` bodies), so the *bodies* total exactly
`CAVE_LINES` (144) and the water surface keeps its absolute line. Measured with
`sim_frame_budget` (constant per kernel kind, no jitter).

## ZP (no new bytes; all four tables live in the freed `$CC-$DF` window)

| byte(s) | before | now |
|---|---|---|
| `PF0Buf`/`PF1Buf`/`PF2Buf` | `$C3/$C6/$C9`, stride **3** | `$C3/$C7/$CB`, stride **4** (rows 0-3, `$C3-$CE`) |
| `BandTab` | `$ED` (3 B; `$F0` = `BombX`) | `$CF-$D2` (4 B) |
| `ColupfBuf` | `$E7` (3 used) | `$D3-$D6` (4 B) — out of the bank1 stomp zone |

`ColOff` is `0/4/8` in **all four** banks (kernel, bank1, bank2, bank3) — every
one of them is a hand copy and every one had to be found.

## Data format (`LEVEL_FORMAT = 7`)

A shape block carries **four** row-pool indices. `convert_room.SHAPE_ROWS = 4`
and the authored grid is still `HEIGHT = 3`, so a 3-row model **pads band 3 with
a copy of band 2** (the migration default; the live stage keeps working). The
hot flag still rides band 1's index b7.

`tools/test_band_geometry.py` pins kernel + converter + emitted data together
(red before the migration, green after) so it cannot half-land.

## What the migration found (each caught by a test, all fixed)

- bank1/bank2/bank3 `ColOff` were still `0/3/6` → every cell walk (laser,
  moth, hot-overlap, punch, PHM) read the wrong register for display cols 4-19.
- bank3 feature-cell staging (`ExtrasLoad`) and `PhaseBlink` used hardcoded PF
  offsets `1/4/7` → features painted the wrong registers.
- `OvHead`/`OvTail` (overlay band masks) had 3 entries → band 3 read garbage;
  now 4 entries (band 3 mirrors band 2, because the pack's mask has 3 bits).
  Paid for by moving both tables + `EnemyBitTable` into the `$FFE6-$FFF1` data
  tail and shortening the moth walk by 3 B (its window is byte-full).
- `BandStart` was still `0,48,96,144` → the Slot1Hook band gate swapped on the
  wrong band.
- Title: cave band 0 is 36 lines now, so `TitleBand` draws **three** 36-line
  bands (36 + 3x36 = 144 visible) — title frame unchanged at 267.0.

## Open items (in priority order)

1. **Slot1Hook costs +2 lines when it fires** (flicker class — the only red
   test). Repro: `tools/test_slot1_midband.py` (it stages the SAME two objects
   in both configurations now, so the compare is like for like):
   - same band (band 1, 44/60) → no pair → **270 lines**;
   - different bands (44/100) → pair staged + hook → **272 lines**.
   The hook is documented as "2 lines spent, `-2` on `LineCount`", and the
   `-2` IS executed (`.SHcount`), so the extra must be a late `sta WSYNC` in
   the inlined positioning: the measured WSYNC sequence for the hooked band has
   two intervals of ~115c (a line + 39c) instead of the plain band's
   `76,76,156`. Do NOT blind-patch the `-2` to `-3`/`-4`: the cost may depend on
   `ActiveObjectX` (the div15 loop), so first measure at X=40 vs X=140 with the
   same staged room (the midband test's `step()` can log WSYNC gaps — see the
   git history of this file for the instrumented version). Fix belongs in the
   hook's alignment: the first `sta WSYNC` must land before the line ends for
   every X (the draw's c58 GRP1 write is the latest store in `.Row`'s setup).
   Acceptance: `test_slot1_midband` green AND `sim_frame_budget` cave still
   constant 270.0.
2. **Async band mask still has 3 bits** (MetaA b0-2; b3 = the M1/door flag).
   Band 3 therefore mirrors band 2 for the ball/M1 gate (`B3StageBand` copies
   `BandTab+2` -> `BandTab+3`). `test_cell_map`'s asym sweep is restricted to
   rows 0-1 for that reason. Phase 2: take one of MetaB's free bits (b4/b5) as
   the band-3 gate, extend the pack (`SBT_B`) and drop the mirror.
3. **Editor** still authors 3 rows. Until it grows a 4th row the bottom band of
   every room is a copy of the row above it (visible seam). Phase 3: 10x4 grid,
   4 rows per model, `HEIGHT = 4`, band-occupancy warnings per 36-line band,
   `stage.json` migration (band 3 = copy of band 2 as today's default).
4. `plans/hero_kernel_plan.md` and `src/AGENTS.md` still describe 3x48 in the
   overview text (`TILE_ROWS=3`, "one GRP1 object per 48-line band", the water
   split description, the frame total). Update in the docs pass (phase 4).

## Phases

1. **Kernel engine + data format** — DONE (commit `69723c5` + follow-ups).
2. **MetaB band-3 bit** (open item 2) — small, converter + `B3StageBand` + pack.
3. **Editor 10x4 + stage migration** — largest chunk; the user authors stages.
4. **Docs/AGENTS pass** + delete the phase-1 bridge notes.
