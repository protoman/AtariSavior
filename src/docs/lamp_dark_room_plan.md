# Lamp / Dark Room Plan

Spec (user, 2026-09-24): lamp object already in editor. Touch → crash → room dark.
No JSON schema change (lamps already in `RoomData.lamps`).

---

## Spec

| # | Rule |
|---|------|
| 1 | White 4×8 square (same footprint as player/enemies; GRP1 `$f0` already). |
| 2 | Player footprint overlap → lamp crashes, **no life loss**. |
| 3 | Room dark: COLUBK + COLUPF **black**; lamp + enemies **medium grey** `$0A`. |
| 4 | Dark persists across room leave/re-enter until `LoadLevel` (level end) or `ReloadLevel` (all lives). |
| 5 | Bomb fuse (state=1) in dark room: COLUPF **dark grey** `$04` until explode (state=2 → black again). |
| 6 | Explosion blink (COLUBK) still runs in dark rooms during state=2. |

---

## Architecture (reuse — no new ZP)

### Lamp = enemy type 5

Converter merges `room.lamps` into the flat enemy table as `type=5`, `x/y` via existing `enemy_x_px`/`px`. Count includes lamps. Entire flicker/collision pipeline reused.

- `LAMP = 5` constant; `EnemyColorTable` 6th byte `$0E` (white) — overridden when dark.
- No new LevelDataTable stride, no LampLo/Hi ZP, no RoomLamps table.

### RoomDarkMask — `EnemyRamD` bits 4–7

| Bits | Meaning |
|------|---------|
| 0–3 | enemy dir (unchanged) |
| 4–7 | dark flag for room 0–3 (`bit4=room0` … `bit7=room3`) |

- **Max 4 rooms with dark persistence** (current levels have 2).
- `LoadEnemyRam`: preserve `$F0` high nibble when writing dir bits.
- `LoadLevel`: zero `EnemyRamD` before `EnterRoom` → clears dark on level end/reload.
- Room change must **not** clear high nibble (persist).

### Rendering

| State | COLUBK | COLUPF | GRP1 objects |
|-------|--------|--------|--------------|
| Lit | Temp (blink/black) | stripe/hot | type colors / white lamp |
| Dark, no bomb | `$00` | `$00` | grey `$0A` (lamp + enemies; miner unchanged) |
| Dark, fuse state=1 | `$00` | `$04` | grey |
| Dark, explode state=2 | blink | `$00` | grey |

`BuildColupF` end: if dark → override all 12 rows (fuse `$04` else `$00`).
VBLANK Temp: if dark → `$00` except existing state=2 blink path.

### Touch

`CheckEnemyHit`: load type at `EnemyIndex*6`; `type==5` → if bit4+RoomNo clear, set it; `rts` (no life, no `DeadEnemyIdx`). Skip further lamp hits while dark.

---

## Steps

- [x] **W0** Write this plan.
- [x] **W1** `convert_level.py`: emit `room.lamps` as type-5 enemy rows. Smoke: `.byte 5, 27, 48, 0, 0, 1`, count=1, x=`enemy_x_px(5)`.
- [x] **W2** kernel: `LAMP=5`, `EnemyColorTable+$0E`, `IsRoomDark`/`SetRoomDark` (bit 4+RoomNo of `EnemyRamD`), `LoadEnemyRam` preserve `$F0`, `LoadLevel` clears `EnemyRamD`.
- [x] **W3** `SelectActiveObject` dark grey for enemies/lamp; `CheckEnemyHit` type-5 path (`CEH_Lamp` = `SetRoomDark`+`rts`, no `DeadEnemyIdx`/life).
- [x] **W4** VBLANK Temp dark → black (state=2 blink still wins); `BuildColupF` dark → all rows `$00`/fuse `$04`.
- [x] **W5** `./build.sh` green + assert pack ALL PASS — Overscan moved `$F143`→**`$F14D`**, bank1 `jmp $F14D` synced, folds byte-identical, sizes 4×4096+16384, converter lamp probe, no new ZP EQU.
- [x] **W6** User Stella verify — **done** (2026-09-24).

## Ambiguities (defaults chosen)

- Touch lamp: **no life loss** (spec silent).
- “Playfield black like background”: walls + bg both black; only sprites visible.
- “Bomb active” = fuse **state=1** only; state=2 → black (matches “until it exploded”).
