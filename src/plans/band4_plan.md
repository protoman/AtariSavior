# Four-band cave (N=4) — migration plan

User decision 2026-10-23: go from 3 bands of 48 lines to **4 bands of 36** so
stages carry a **10x4** grid — more vertical complexity, same total cave height,
same sprite sizes, same colours, same no-flicker rules. The 32K of F4 space is
what makes the extra level data affordable.

## Geometry (verified against the current kernel)

| | today | target |
|---|---|---|
| `TILE_ROWS` | 3 | **4** |
| `LINES_PER_TILE` | 48 | **36** (must stay a multiple of 4 — `YToRowTable` indexes `line>>2`) |
| `CAVE_LINES` | 144 | 144 (**unchanged**) |
| `PLAYER_SPRITE_H` | 22 (8x22 art) | unchanged |
| `PLAYER_MAX_Y` | 122 | 122 (**unchanged** — 144 - 22) |
| Water / tide line | RoomY ~125 | unchanged |
| HUD band | 48 | unchanged |
| cave scanlines | 4 setup + 143 bodies = 147 | 4 setup + 144 bodies = **148** |
| frame total | 265 | **266** |

Band cost: `1 setup (WSYNC) + L bodies`. Today the bottom band is split
(`36+off` bodies + a `.WaterRow` pass with its own setup, `11-off` bodies).
Target: the water strip is the **bottom 12 lines of band 3**, inside the same
pass (`24+off` bodies, then `12-off` water bodies) — that keeps the total at
4 setups, so the cave grows by exactly **1 line** (one more band, one fewer body
per band). Frame 265 -> 266 means updating, in the SAME change, the
`sim_frame_budget` target, `test_phase3_ball`'s line set and any comment that
cites 265 (AGENTS RULE 3).

## ZP: no new bytes needed

`$CC-$DF` is **FREE (20 B)** — the retired solid-rect cache
(`docs/zp_layout_skill.md`). The 4th PF row costs 3 bytes and the per-band
tables grow by 1 each:

- `PF0Buf`/`PF1Buf`/`PF2Buf` become stride **4** (`$C3-$CE`), so the
  `PF0Buf+row+ColOff` walks use `ColOff = 0/4/8` (was `0/3/6`). Every
  `lda PFxBuf,X` site is label-based and needs no edit; the loader's stride-3
  folds and `ClearPFColumn` do.
- `ColupfBuf` rows 0-3 (`$E7-$EA`) — the allocation already claims 12 bytes.
- `BandTab` rows 0-3 (`$ED-$F0`) — **collides with `BombX` `$F0`**, so `BandTab`
  moves into the free window (e.g. `$D8-$DB`). One writer (`StageBandTab`) and
  one reader (`.Row`).

## Layer contract (the red test)

`tools/test_band_geometry.py` (written first, **red today**) pins all three
layers together, because a half-landed migration is a broken ROM:

- kernel: `TILE_ROWS 4`, `LINES_PER_TILE 36`, `CAVE_LINES 4x36`,
  `PLAYER_MAX_Y = CAVE_LINES - PLAYER_SPRITE_H`, and `YToRowTable` maps every
  line to its band exactly (`band = line // 36`);
- converter: `WIDTH 10`, `HEIGHT 4`, `LEVEL_FORMAT 7`;
- data: every shape block carries **4** row-pool indices.

## Phases (each must build + sims green before the next)

1. **Kernel engine (no data change).** 4 bands x 36, stride-4 PF buffers,
   `YToRowTable` (36 entries), water strip inside band 3, `BandTab`/`ColupfBuf`
   relayout, hot band index read from data instead of the literal 1, bottom-band
   rules (`RAFT` row 3, water kill, respawn). In this phase the loader keeps
   staging 3 rows and **duplicates row 2 into row 3** as the migration default,
   so the ROM stays playable.
2. **Data format 7.** Converter `HEIGHT 4` + shape block 4 indices + hot flag on
   the model's hot band index; extras band mask 4 bits (band 3 takes a free
   `MetaB` bit — `b4`/`b5` are unused); row pool re-measured against
   `LEVEL_ROW_COUNT <= 128`; `stage.json` migration (3-row models get the old
   row 2 duplicated as the new bottom row, then the author edits).
3. **Editor.** 10x4 grid, band occupancy rules, model migration on load,
   `LEVEL_FORMAT 7` write. Largest single chunk; the user authors stages.
4. **Rules/docs.** Update AGENTS (band rules, water/hot/raft "bottom band"
   wording), the level format doc, and the battery expectation.

## Risks / invariants to keep

- **One hot band, one water band, per-band object windows** — unchanged; only
  the band INDEX becomes data-driven. The hot cells stay PF-derived (C11).
- **`.Line` cycle budget is untouched** (the body is the same instruction
  stream); only the loop count per band changes, so no per-line timing work.
- **Every `48`/`12`/`row 2` literal** must be found: `YToRowTable`,
  `YToCellRow`, `DeriveEnemyY`, `.WaterRow` tide math, raft tide/pin,
  water-kill `RoomY`, respawn hover, tentacle clamp, `SelectActiveObject`
  band gates, the `.Row` `cpx #TILE_ROWS-1` split.
- A 36-line band holds the 22 px player plus an 8 px enemy with margin, but a
  band must never drop below ~24 lines (player + positioning).

## Status

- [x] Red test `tools/test_band_geometry.py` (fails: 3 bands / 48 lines /
  HEIGHT 3 / FORMAT 6 / 3 indices) — committed as the migration's failing test.
- [ ] Phase 1 kernel engine
- [ ] Phase 2 data format 7 + stage migration
- [ ] Phase 3 editor
- [ ] Phase 4 rules/docs
