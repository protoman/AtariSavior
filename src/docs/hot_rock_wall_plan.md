# Hot Rock Wall Plan

Spec (user 2026-09-24, TODO line 1) + baby steps. Implement → `./build.sh` green → user validates in Stella.
Data format change is accepted as part of this feature (new tile type). Migrate converters + emit; existing models use tiles `{0,1}` only — no migration of stage files required until someone paints hot walls.

---

## Spec

| # | Rule |
|---|------|
| 1 | Editor Model tab: new terrain brush **Hot Rock Wall** (`TileType` / `BrushTool` value **8**). |
| 2 | In game: hot cells **pulse COLUPF yellow ↔ red** (per tile row). |
| 3 | Touching a hot cell **kills the player** (same life path as enemy/timer hit). |
| 4 | Bomb still treats a thin wall that is **half `#` + half `H`** as destroyable — blast removes the whole wall piece (both materials). |

Out of scope unless asked: horizontal hot+normal in the **same** row pulsing only part of the row (TIA has one COLUPF per tile row → whole row pulses). Documented below.

---

## Architecture

### Data (converters)

- Char **`H`** = hot rock; **`#`** = normal solid; **`.`** = air.
- `tile_to_char`: `0 → '.'`, `8 → 'H'`, else `'#'` (other editor tiles stay solid).
- `read_room`: allow `.#H`.
- `pf_values`: solid = `#` or `H` (hot is a wall for the playfield).
- **Rects (main)** = `find_rectangles` over solid = `#H` → one collision/bomb list (half/half thin wall can merge or stay as two `w==1` rects; bomb marks every `w==1` rect in blast cols → both parts go).
- **Hot rects (appended)** = `find_rectangles` over `H` only → death + pulse source.
- Room blob layout (still one `RoomRects` pointer, **no new ZP pointer**):

```
RoomRects:
  .byte n                  ; solid rects (collision + bomb)
  .byte x,y,w,h × n
  .byte n_hot              ; hot-only rects (death + pulse)
  .byte x,y,w,h × n_hot
```

Bomb/PlayerHitsMap walks use **only `n`** (stop before `n_hot`). New hot walk starts at offset `1+4n`.

### Pulse (kernel)

- VBLANK each frame: `BuildColupF` writes the **final COLUPF byte for all 12 rows** into `ColupfBuf` ($E7–$F2): stripe first (rows 0-3,8-11 = `LevelWallColor`, 4-7 = `LevelWallColor2`), then hot rows overwrite with pulse color (`TickCounter` bit 4 → `COLOR_HOT_Y`/`COLOR_HOT_R`).
- `.Row`: `lda ColupfBuf,X / sta COLUPF` only. Inline stripe+hot tests were 84–109c (budget 76c) → would skip scanlines; precompute fits (~58c for whole `.Row` entry).
- **`$F0–$F2` overlap:** `ColupfBuf` bytes 9–11 share `PlayerBombs`/`BombSnd`/`RoomWallMask`. `BuildColupF` saves them to `CollisionCellY`/`CollisionEndX`/`CollisionEndY` (free from VBLANK through kernel; first collision use is overscan movement/`BombMarkWalls` after restore). `.AfterRows` restores before `jmp $FC68` (HUD + overscan).
- Bank1 clobbers `$E0–$EF` during HUD; VBLANK rebuilds before cave kernel.
- **Limitation:** one COLUPF per tile row → a row with mixed `#`/`H` pulses entirely.

### Death

- New `CheckHotTouch` in overscan (next to `CheckEnemyHit`): footprint vs hot rects (mirror cols like `PlayerHitsMap`). Hit → same path as `CEH_Stay` / timer: `dec PlayerLives`, zero vy; 0 lives → `ReloadLevel`.
- Does **not** change blocking: hot already blocks via main solid rects.

### ZP

- No new sequential ZP (map full after bomb work).
- `ColupfBuf` = `$E7–$F2` (12 bytes) — final per-row COLUPF; overlaps `$F0–$F2` bombs (save/restore above).
- Hot rect pointer = `RoomRectsLo/Hi` + offset (computed).

### Editor tree

- **Active:** `src/tools/editor` (two-tab, last commit 2026-09-23).
- Root `tools/editor` is older (single list, 2026-09-07); restored in worktree this session. **Only `src/tools/editor` is edited** unless user asks to sync the root copy.

---

## Steps

### E — Editor (`src/tools/editor`)

- [x] **E1** `LevelData.hpp`: `HOT_ROCK_WALL = 8`.
- [x] **E2** `MapCanvas.hpp`: `BrushTool::HOT_ROCK_WALL = 8` (tile brush range).
- [x] **E3** `MapCanvas.cpp`: `GetTileColor` → hot orange/red; `ApplyBrushAt` paints tile 8 with solid-tile branch.
- [x] **E4** `MainWindow.cpp`: `modelTools` entry + `MakeToolIcon` case.
- [ ] **E5** Build editor (cmake) — user can paint and save.

### C — Converters

- [x] **C1** `convert_level.tile_to_char`: `8 → 'H'`.
- [x] **C2** `convert_room`: accept `H`; `pf_values` solid = `#H`; main `find_rectangles` solid = `#H`; emit hot rects after solid count block.
- [x] **C3** Regenerate `generated/*.asm` — rooms with no hot → `n_hot=0` only; verify existing rooms unchanged except trailing `.byte 0`.
- [x] **C4** Assert: existing rooms still parse; new sample with `H` yields hot rect.

### G — Game (`kernel.asm`)

- [x] **G1** VBLANK: `BuildColupF` writes final COLUPF (stripe + hot pulse) into `ColupfBuf` (after `LoadPFBuffer`); saves `$F0–$F2`.
- [x] **G2** Kernel `.Row`: `lda ColupfBuf,X / sta COLUPF`; `.AfterRows` restores bombs before HUD.
- [x] **G3** `HotOverlapFlag` + `LoseLifeHot` from `PlayerHitsMap`/`EndInputCheck`; life path matches enemy hit.
- [x] **G4** Bomb: confirm half/half thin wall both marked (main list solid=`#H`).
- [x] **G5** `./build.sh` green + assert pack (sizes, folds, Overscan, bomb asserts, `n_hot` in emitted asm).
- [x] **G6** Fix Y-offset death: `HotOverlapFlag` row-walk used 3×`dey` from `base+2` → `base-1` (hot-count byte as `rect.y`) so death sat ~3 rows above the pulse; now 1×`dey` to `base+1`, same as `PlayerHitsMap`.

### Verify

- [ ] User: Stella — touch bottom of visible hot wall → die; touch above visible hot wall → safe; pulse correct; bomb clears split thin wall.

---

## Assert additions

- Emitted room asm for a hot room contains `n_hot` line / second rect block.
- Rooms without hot: last byte of rects section is `0` for hot count (or `.byte 0` hot count).
- `ColupfBuf` referenced from `BuildColupF` and kernel `.Row`; bombs restored at `.AfterRows` before `jmp $FC68`.
- `HotOverlapFlag` called once from `PlayerHitsMap`; `LoseLifeHot` once from `EndInputCheck`.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Main rect walk reads into hot block | All solid walks use count `n` only; hot walks use offset `1+4n`. |
| Half/half not destroyed together | Main list solid=`#H` so geometry is one wall; bomb still `w==1` → any thin segment in blast. |
| Pulse fights bank1 HUD | `ColupfBuf` rebuilt every VBLANK before kernel. |
| `$F0–$F2` clobbered by `ColupfBuf` | Saved to collision temps in `BuildColupF`; restored at `.AfterRows` before HUD/overscan. |
| `.Row` > 76c | No runtime stripe/hot branches — one ZP indexed load. |
| ZP exhaustion | No new ZP; reuse `ColupfBuf`. |
| Two editor trees diverge | Edit only `src/tools/editor`. |

**G5 build note:** Inline stripe+hot removed (budget). `ColupfBuf` + save/restore. Overscan `$F130`; bank1 fold `jmp` synced to `$F130`. Folds byte-identical (`FC68`/`FC70`); sizes 4×4096; assert pack ALL PASS. `.Row` body ≈58c.

**G6 note (2026-09-24):** Death displaced up vs pulse. Root: after column check Y=`base+2`, triple `dey` landed `base-1` = hot-count (1) for first hot rect (`y=4`) → fake range rows 1–4 vs visual 4–7. Bottom of wall no-death; above wall dies. Fix: one `dey` only (match solid walk). Rebuild: folds/Overscan unchanged (edit is after fold pads).
