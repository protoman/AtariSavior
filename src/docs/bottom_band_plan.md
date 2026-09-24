# Bottom Band Plan

Spec (user, revised 2026-09-24): optional colored band on the bottom tile row of a room.
Reference: `screenshots/hero_water_bottom.png` (thin blue strip above HUD).
Data format change accepted (new per-room fields). Migrate both level JSONs.

---

## Spec

| # | Rule |
|---|------|
| 1 | Per-room option `bottom_band` (bool) + RGB color → `nearest_byte` (0 = off). |
| 2 | Band = tile row **11** only (scanlines 132–143 = 1 field tile). |
| 3 | Where playfield is open, `COLUBK` = band color on those 12 lines. |
| 4 | Touch band (`RoomBottomColor≠0` and `RoomY ≥ 125`) → lose life, respawn `RoomY -= 12` (min 0), zero `vy`/`JetPower`/`PlayerYSub`. |
| 5 | Bomb-blink `Temp` overrides band color when blink is active. |

**Caveat:** death (`RoomY≥125`) fires before down-exit (`PLAYER_MAX_Y=136`). Banded rooms must not rely on down-exit.

Revised from TODO water/lava enum → single bool + color picker (user-approved).

---

## Architecture

### Data

- `RoomData`: `bool bottom_band`, `int bottom_r/g/b` (cereal NVP).
- Converter: `nearest_byte` when band on, else `0`.
- **ROM:** RoomEnemies per-room record 4th byte (unused pad) = color byte.
  No LevelDataTable stride change; no new ZP pointers.

### ZP

**No dedicated RoomBottomColor ZP.** Original plan used `$EC`, but `$EC` is inside
`ColupfBuf` (`$E7–$F2`, row 5) — VBLANK `BuildColupF` overwrites it before every
kernel, and writing it would corrupt row 5 COLUPF. Sequential ZP is full ($80–$BC
+ EnemyRam/PF/Colupf/score/bombs). Band color is read from ROM when needed:

- `LoadRoomBottomColor`: A = RoomEnemies pad for `RoomNo` (Y = RoomNo*4+3).
- Kernel `.Row` X==11: JSR load (after Temp COLUBK); A≠0 and not blink → `sta COLUBK`.
- Overscan `CheckBandTouch` at `EndInputCheck`: JSR load; A≠0 && `RoomY≥125` → `LoseLifeBand`.
- No EnterRoom store, no Overscan reload (ROM is stable; no bank1 clobber risk).

### Kernel

- `.Row`: `cpx #TILE_ROWS-1` / blink off / `LoadRoomBottomColor` ≠0 → `sta COLUBK`.
- Death check after movement at `EndInputCheck` → `CheckBandTouch`: color≠0 && `RoomY≥125` → `LoseLifeBand`.
- `LoseLifeBand`: life path (reload if 0 lives, else zero vel) + `RoomY -= 12` (min 0).

### Editor

- Rooms box: `QCheckBox "Bottom band"` + `QPushButton "Band color"` (NTSC picker).
- `PickBandColor` mirrors `PickWallColor`.
- `UpdateUIFromLevel` syncs checkbox + button style from current room.

---

## Steps

- [x] **W0** Write this plan.
- [x] **W1** `LevelData.hpp` fields + migrate `level_001.json`, `level_002.json`.
- [x] **W2** Editor UI (checkbox + color button + pick handler).
- [x] **W3** `convert_level.py`: emit color into RoomEnemies pad byte.
- [x] **W4** kernel: `LoadRoomBottomColor`, `.Row` band, `CheckBandTouch` + `LoseLifeBand`.
- [x] **W5** `./build.sh` green + assert pack — **33/33 PASS** (sizes, folds `$FC68/$FC70`,
  Overscan moved `$F130`→**`$F143`** after `.Row` growth, bank1 `jmp $F143` synced,
  no RoomBottomColor EQU, pad bytes 0 while band off, converter on/off probes).
- [x] **W6** Update `zp_layout_skill.md` (no new ZP; ROM-read band color).
- [ ] **W7** User validates in Stella (I ask before launching).

## Assert pack additions (W5) — DONE 33/33

- [x] `LoadRoomBottomColor` defined once in `kernel.asm`.
- [x] RoomEnemies pad byte non-zero only when band on (grep generated asm).
- [x] `.Row` band branch present; death check `RoomY` cmp `#125` present.
- [x] Existing checks still PASS (sizes, folds `$FC68/$FC70`, Overscan, bank1 jmp, etc.).
