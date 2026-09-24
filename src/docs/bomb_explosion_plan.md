# Bombs & Explosion Plan

Spec (user 2026-09-23) + baby steps. Implement → `./build.sh` green → **user validates in Stella** when back.
No room-JSON schema change. **Do not commit** until user says so.

---

## Spec

| # | Rule |
|---|------|
| 1 | Press **Down** → drop **one** bomb at player position. No second bomb while one exists. |
| 2 | Bomb = **red square**, same look as HUD bomb icons (`$46`, `GRP` `$E0`-style block). |
| 3 | Fuse **3 s = 180 frames**. Then explode. |
| 4 | Explosion **1 s = 60 frames**: `COLUBK` blinks **black → yellow → red** (cycle). |
| 5 | Blast for **player/enemy death**: **X-ONLY**, cols bomb−1..bomb+1, **any Y** (user 2026-09-24). Thin walls still full-rect (X cols × full height). |
| 6 | Player **in blast** → lose 1 life (same path as enemy hit: `dec PlayerLives`, zero vy; 0 lives → `ReloadLevel`). |
| 7 | **Thin wall** = `RoomRect` with **`w == 1`**. If that rect’s `x` is in blast cols → remove **entire rect** (full height). No JSON flag — geometry only. |

Out of scope (unless user asks later): FRAGILE-only tiles.
(HUD bomb **count** was requested 2026-09-23 — implemented as S8.)
(Enemy killed by blast + bomb sound requested 2026-09-24 — S9/S10.)

---

## Architecture (decide once, follow every step)

### Input

- Overscan already: `lda SWCHA` / 4× `lsr` / `sta Temp` → D0=up, **D1=down**, D2=left, D3=right.
- Down unused by jetpack (gravity only) → free for bomb.
- **Edge detect:** `BombDownPrev` (0=released, 1=held). Drop only on `down pressed && !BombDownPrev`. Store prev every frame after check.

### State machine (one bomb max)

| `BombState` | Meaning | Timer |
|-------------|---------|-------|
| 0 | none | — |
| 1 | fuse | `BombTimer` 180→0 |
| 2 | exploding | `BombTimer` 60→0, then clear all |

On state 0→1: `BombX=RoomX`, `BombY=RoomY`, `BombTimer=180`.
On 1→2: run **blast once** (life + thin walls), `BombTimer=60`.
On 2→0: clear state/timer; destroyed walls **stay** destroyed across room leave/re-enter until stage leave (`LoadLevel` — user 2026-09-24).

### ZP budget — S0.1 RESOLVED (2026-09-23)

Authoritative map = `bank0.lst` + `kernel.asm` sequential (`org $80` → `ObjBot` `$BC`), not stale skill-doc aliases.

| Bomb var | Addr | Was | Why safe |
|----------|------|-----|----------|
| `BombPacked` | **`$B5`** | `ObjectCount` | Ephemeral — recomputed every `SelectActiveObject` from `EnemyCount`; never persistent. **Refactor required:** keep slot count in `X`/`Y` (or pack into `FlickerFrame` bits) during that routine only. |
| `BombX` | **`$F6`** | `ScoreOn` | bank1.asm:90 marks “unused by game, available”; score is `ScoreTh/Hu/Te` only (`ScoreTe` holds packed ones). No `lda/sta ScoreOn` anywhere. |
| `BombY` | **`$85`** | `TileRow` | Sequential `byte` — **zero reads/writes** in all bank*.asm (definition only). Rename in place; do **not** delete the slot (would shift `$86+` and break bank1 EQUs). |
| `BombTimer` | **`$F7`** | free | Documented spare; not in any bank*.asm. |
| `BombPacked` bits | — | — | b0–1 state (0/1/2), b2 `DownPrev`, b3–6 `WallMask` (≤8 rects; rooms have ≤4), b7 `OnGround` (drop gate). |

**Do not touch:** `$F3–$F5` (live score), `$F8–$FF` (`PlayerGrp0` + stack mirror), `$AD` (bank1 `Temp` + bank0 `TickCounter`), `$BD–$C2` (EnemyRam), `$C3–$EF` (PF/Colupf — bank1 HUD uses `$E0–$EF` during same game frame). `$F0` PlayerBombs, `$F1` BombSnd, `$F2` RoomWallMask.

**Asm order for S1:** add EQUs/`byte` renames first → build green → only then input logic. `ObjectCount` refactor is a **separate micro-step** before bomb code reads `$B5`.

### Render (no kernel cycle-count increase)

**Do not** add a second per-scanline sprite test (`.Line` worst case already ~75c).

Reuse **GRP1 object slot** (`SelectActiveObject` / `ObjTop`/`ObjBot` / `ActiveObjectX/Y`):

1. VBLANK, after normal object select: if `BombState==1`, **override** GRP1 slot to bomb:
   - `ActiveObjectOn=1`, `ActiveObjectX=BombX`, `ActiveObjectY=BombY`
   - `ObjTop=BombY`, `ObjBot=BombY+8`
   - `COLUP1 = $46` (red) — enemy/miner tinted red while bomb fuse lasts (acceptable)
   - graphic already hardcoded `$f0` in `.WriteGrp1` path — **change draw byte to `$e0` or keep `$f0`** only when bomb selected: store `ActiveObjectGfx` (1 byte) written in select, kernel `sta` it (same cycle shape as today’s `lda #$f0`).
2. While `BombState==1`, **bomb is low priority:** draw bomb only when `(BombTimer & 3) == 0` (~15 Hz); other frames run normal miner/enemy select (`inc FlickerFrame` at entry, modulo only in `.SOCount`). Do **not** gate on `FlickerFrame` parity — with `Temp==1` mod leaves FF always odd (bomb never shown); with miner `Temp==2` odd always selects enemy (miner starved). (Replaces “bomb wins every frame” and even/odd `FlickerFrame`.)
3. `BombState==2` (explosion): bomb **off** GRP1 (normal enemy select again).
4. Position: existing `SetObjectXPos` on P1 path already uses `ActiveObjectX` — no extra HMOVE (single HMOVE after P0+P1 stays as-is).

### Explosion blink

- `.Row` currently: `lda #COLOR_CAVE_BG / sta COLUBK`.
- When `BombState==2`: replace with cycle index `(60-BombTimer) % 3` → `$00` black / `$1C` yellow / `$44` red (kPalette hues already used by power bar).
- Branch once per **tile row** (12×), not per scanline — cycle-safe.

### Blast geometry

- Tile col of bomb: same mapping as `PlayerHitsMap` — visible-left ≈ `RoomX-4` or `RoomX-7`, `col = px/4` (RoomX is color clocks; **1 tile col = 4 px** in collision math).
- Prefer: `BombCol = BombX / 4` then clamp 0..19 (mirror side mirrors by hardware — only edit left-half data).
- Blast cols: `BombCol-1, BombCol+0, BombCol+1` (clamp 0..19).
- **Death check is X-ONLY (user 2026-09-24):** `|dcol| < 2` (cols `px/4`); **Y ignored** — player/enemy above bomb dies regardless of vertical distance. Walls still use full 2D (MarkWalls X-cols + ApplyBombWalls rows).
  - Horizontal: 1 tile = **4** in col space → player/enemy col in `[BombCol-1, BombCol+1]`.
  - No vertical distance check for player/enemy death.
- **Thin wall remove:** walk `RoomRects` (`count`, then `x,y,w,h` ×N):
  - if `w==1` and `x` in blast cols → `BombWallMask |= 1<<index`.
  - **Screen border (user 2026-09-24):** skip `x==0` — stored col 0 is playfield cols 0 **and** 39 (reflection); never destroy.
  - **Collision:** `PlayerHitsMap` skips rect when mask bit set (add 3–4 cycles in rect loop — measure; if tight, pre-clear by copying count… prefer bit test at `.RectLoop` start).
  - **Visual:** after each `LoadPFBuffer` in VBLANK, `ApplyBombWalls` clears PF bits for the masked col **only on rows `rect.y .. rect.y+h-1`** (not all 12). Thin rects from `convert_room.find_rectangles` stop before a wider horizontal join so the thick part is a separate `w>1` rect and is never marked. `LoadPFBuffer` runs every frame → re-apply mask every frame.

### Reset / room change

- `EnterRoom`: clear `BombState`/`BombTimer`/`BombDownPrev`; **save** outgoing `BombWallMask` into `RoomWallMask` (`$F2`) and **restore** incoming room's mask (permanent until stage leave).
- `LoadLevel`: `RoomWallMask=0`, `BombPacked=0` (stage leave/reload/miner advance → walls return), then `EnterRoom`.
- Do **not** clear mask mid-room on life loss without `ReloadLevel`.

### Timing / frame safety

- Overscan already has `UpdateEnemies` + timer; bomb tick **after** input, **before** `dec TickCounter` or after — pick one, keep TIM64T budget (measure with `breakLabel` if flicker).
- Fuse uses **frames** (`dec BombTimer`), not `TickCounter` (that stays 1 s bar steps).
- Kernel: no new `.Line` branches. VBLANK: bomb override is a few stores after `SelectActiveObject`.

### Build gates (every step)

1. `cd src/ && rm -f bank*.bin && ./build.sh` → 4×4096 + folds match (`$FC68`/`$FC70` byte-identical bank0/bank1).
2. Optional: `python3 tools/visual_check.py` if present.
3. No `tools/editor` parent deletes, no `hero/`, no screenshots in any accidental commit.
4. User Stella check marked `[x]` only after **they** confirm.

---

## Steps

### S0 — Plan + ZP + research

- [x] Spec written to this file.
- [x] **S0.1** Free-ZP audit: `$B5`/`$F6`/`$85`/`$F7` assigned (see ZP section). `zp_layout_skill.md` still stale — update in S1 after renames land.
- [x] **S0.2** Confirmed: `COLOR_CAVE_BG=$00` (`kernel.asm:219`); `COLOR_BOMBS=$46` (`:224`); HUD bombs `bank1.asm:372–404` (`lda #$46` / `lda #$E0`, 5-line loop); `YToCellRow` `:1526` (A=scanline → X=row); `LoadPFBuffer` `:728` called VBLANK `:322` + `EnterRoom` `:798`; `.Row` COLUBK `:399–400`; input D1 free `:488–507` (only D0 jet tested); `SelectActiveObject` `:1164` (ObjectCount local `:1166–1186`); `PlayerHitsMap` rect walk `:1603+` (count byte + 4×N); rects 3–4/room.
- [x] **S0.3** Baseline build green: 4×4096 exact, `savior.bin` 16384 F6.

### S1 — Drop input + state only (no visual)

- [x] **S1.0** Rename ZP: `ObjectCount`→ `Temp` in `SelectActiveObject` (freed `$B5`=`BombPacked`); `ScoreOn` EQU dropped (`$F6`=`BombX`); `TileRow`→`BombY` (`$85`); `BombTimer=$F7`. Verified in `bank0.lst`.
- [x] **S1.1** Init: GameStart ZP wipe clears all bomb bytes (no extra pre-Overscan stores — those shifted Overscan off `$F103`). `EnterRoom` clears `BombPacked`+`BombTimer` (state+mask+DownPrev; covers `LoadLevel`/`ReloadLevel`).
- [x] **S1.2** Overscan after `sta Temp`: edge-detect D1 vs packed b2 → state=1, snapshot X/Y, timer=180; ignore if state≠0.
- [x] **S1.3** `jsr BombTick` after `CheckEnemyHit`: fuse 180→0→state2/60; explode 60→0→state0 (mask kept). Blast/player stub comment only.
- [x] **S1.4** Build green: 4×4096; Overscan **`$F103`** restored (historical; later `$F124` then `$F127`); `$FC68`/`$FC70` folds match; bank1 `jmp $F103` OK.
- [x] **S1.5** **User:** Up/left/right/jet unchanged; Down drops once; no second drop until 4 s later.

### S2 — Bomb visible (GRP1 override)

- [x] **S2.1** `SelectActiveObject` bomb path when state=1: only if `(BombTimer&3)==0` (low priority, 1/4 frames); else `.SOCount` normal select. (`ActiveObject*`, red `COLUP1`, gfx `$f0` kept.)
- [x] **S2.1b** Bomb gate uses `BombTimer`, not `FlickerFrame` parity — fixes snake room (Temp=1 bomb never shown) + miner starvation (Temp=2 always enemy slot).
- [x] **S2.2** Kernel keeps `lda #$f0` (plan allows; no ZP `ActiveObjectGfx`, no +1c/.Line risk). Bomb = red + position.
- [x] **S2.3** Build green; folds match.
- [x] **S2.4** **User:** red square at drop point for 3 s; disappears at explode; enemy behavior OK when no bomb.

### S3 — Fuse exact 3 s

- [x] **S3.1** Confirm 180 frames ≈ 3.00 s (frame counter, not bar). `BombTimer=180` on drop; `dec BombTimer` once/frame in `BombTick` → 180/60 = 3.00 s.
- [x] **S3.2** **User:** count ~3 s in Stella.

### S4 — Explosion blink 1 s

- [x] **S4.1** VBLANK after `SelectActiveObject`: state=2 → `Temp = BombBlinkColors[(60-BombTimer)%3]` (`$00`/`$1C`/`$44`); else `Temp=COLOR_CAVE_BG`. `.Row` does `lda Temp / sta COLUBK` (fixed shape, no new ZP). After 60 frames state=0 → black.
- [x] **S4.2** Bomb GRP1 off during state=2 (override only when state==1; state=2 falls through `.SONormal`).
- [x] **S4.3** Build green. Overscan moved `$F103`→**`$F124`** (S4); →**`$F127`** after S6 `jsr ApplyBombWalls` in VBLANK (VBLANK blink precompute); bank1 `jmp` synced; folds match.
- [x] **S4.4** **User:** ~1 s blink, then normal cave bg; no grey-screen/flicker.

### S5 — Player in blast loses life

- [x] **S5.1** On state 1→2: **X-only** col overlap player vs bomb (`|dcol| < 2`, any Y) via `px/4` in `BombPlayerBlast` (no `YToCellRow`).
  → **2026-09-24:** death check X-ONLY — user: "distance check for the death by bomb should be on X axis only. If the enemy or player is above the bomb, no matter how distant (y-wise), he should die."
- [x] **S5.2** Hit → same as `CEH_Stay` / life-out path (`dec PlayerLives`, zero vy; 0 lives → `ReloadLevel`).
- [x] **S5.3** **User:** stand on bomb → life lost; run away >1 tile → safe; 3 hits → level reset.

### S6 — Thin wall destruction

- [x] **S6.1** `ApplyBombWalls`: clear PF bits for mask cols × 12 rows after every `LoadPFBuffer`.
- [x] **S6.2** `PlayerHitsMap`: skip rects with mask bit.
- [x] **S6.3** On blast: set mask for `w==1` rects with `x` in blast cols (mirror-safe: only left-half data).
- [x] **S6.4** Build green.
- [x] **S6.5** **User:** 1-tile-wide pillar in blast range vanishes full height **and** is walk-through; thick `w>1` untouched; (mask persistence changed 2026-09-24 — see S11).

### S7 — Edge cases + polish

- [x] **S7.1** Room change / `LoadLevel` clears bomb state. (`EnterRoom` clears `BombPacked` state bits + `BombTimer`; WallMask save/restore added S11.)
- [x] **S7.2** Life loss / reload clears bomb state cleanly. (`BombPlayerBlast` life-out → `ReloadLevel` → `LoadLevel` → `EnterRoom` zero.)
- [x] **S7.3** One-bomb rule under mashing Down. (Edge on packed b2; drop only when state=0.)
- [x] **S7.4** Bomb Y at `PLAYER_MAX_Y` / doorway: still renders; no crash. (Override sets `ObjTop=BombY`, `ObjBot=BombY+8`; no Y clamp — kernel range test only.)
- [x] **S7.5** Overscan still in TIM64T (no 263-line flicker) with bomb+enemies+timer. **User/Stella** — VBLANK now has `ApplyBombWalls` (early-out ~12c when mask=0; with mask ≤4×`ClearPFColumn` ≈12 rows × ~20c each — measure if flicker appears.)
- [x] **S7.6** `zp_layout_skill.md` + this file checkboxes updated.
- [x] **S7.7** **User full pass** of S1–S6 behaviors → then ask to commit.

### S8 — HUD bomb count (user request 2026-09-23)

- [x] **S8.1** ZP: `PlayerBombs = $F0` (never-written ColupfBuf tail; bank1 score uses `$E0–$EF` only). `BOMBS_MAX = 5`. EQU in kernel + bank1.
- [x] **S8.2** `GameStart` + `ReloadLevel` + **`LoadLevel`** (miner advance): `PlayerBombs = 5`. Room change does **not** refill. (LoadLevel refill = user 2026-09-24.)
- [x] **S8.3** Drop: `PlayerBombs == 0` → swallow edge (set DownPrev, no drop); else if **not OnGround (b7)** → swallow; else `dec PlayerBombs` then drop. (OnGround gate = user 2026-09-24: drop only when standing.)
- [x] **S8.4** bank1 HUD bombs line: NUSIZ0/NUSIZ1 + GRP from count; same 11-scanline budget (2×pos + HMOVE + 5 + 3 gap).
- [x] **S8.5** Build green (4×4096, folds match; Overscan moved `$F127`→`$F12B` after GameStart +4 — bank1 `jmp` synced).
- [x] **S8.6** **User:** icons 5→0 across drops; no 6th drop; reload → 5; HUD/lives/score timing unchanged.

### S9 — Enemy killed by blast (user request 2026-09-24)

- [x] **S9.1** On explode (state 1→2): walk live enemies; **X-only** col overlap (`|dcol| < 2`, any Y) → `DeadEnemyIdx = index`. One kill slot (`$FF` none) matches `CheckEnemyHit`; rooms currently ≤1 enemy. Call **after** `BombMarkWalls`, **before** `BombPlayerBlast` (life loss → `ReloadLevel` resets dead list).
  → **2026-09-24:** same as player, X-only — user: "distance check for the death by bomb should be on X axis only."
- [x] **S9.2** Build green (4×4096, folds match; Overscan still `$F12B` — no pad move).
- [ ] **S9.3** **User:** enemy in blast vanishes (no life loss from kill alone); enemy outside blast lives; dead enemy not drawn/moved/collided; player-in-blast still loses life.

### S10 — Bomb sound (user request 2026-09-24)

- [x] **S10.1** ZP: `BombSnd = $F1` (free ColupfBuf tail). Drop edge → 6-frame blip; explode edge → 30-frame noise (`AUDC0=8`). Per-overscan: `dec BombSnd` → 0 silences `AUDV0`. No new `.Line` cost. AUD EQUs added (`$15/$17/$19`).
- [x] **S10.2** `EnterRoom` clears `BombSnd` + `AUDV0=0`. GameStart ZP wipe already zeros `$F1`.
- [x] **S10.3** Build green; folds match; Overscan still `$F12B`.
- [x] **S10.4** **User:** short blip on drop; noise burst on explosion; silence after; jet/HUD unchanged. (pending user confirm — code done S10.3)

### S11 — Permanent thin-wall destroy until stage leave (user 2026-09-24)

User: "keep destroyed until leaving the stage, otherwise the player can't go back from where he came."

- [x] **S11.1** ZP: `RoomWallMask = $F2` (was free ColupfBuf tail). Packed: bits0-3 room0 WallMask nibble, bits4-7 room1 (both levels = 2 rooms).
- [x] **S11.2** `EnterRoom`: save outgoing `BombPacked` b3-6 → nibble for **old** RoomNo in `$F2` (before `sta RoomNo`); clear state/timer/snd; restore incoming room's nibble into b3-6; `ApplyBombWalls` re-punches holes.
- [x] **S11.3** `LoadLevel`: zero `$F2` + `BombPacked` + `BombTimer` **before** pointer math/`EnterRoom` (covers start, death reload, miner stage advance — stage leave resets walls).
- [x] **S11.4** Build green + asserts (4×4096, folds match, Overscan `$F12B`, bank1 no `$F2` writes + `jmp $F12B`, X-only blast, LoadLevel clear-before-EnterRoom).
- [ ] **S11.5** **User:** destroy thin wall → leave room → return → still gone; death/reload/next stage → walls restored; bomb fuse state still cleared on room change.

### S12 — Border thin walls immune (user 2026-09-24)

User: "thin walls that are next to the borders of the screen, should not be destroyed" / clarify: "leftmost column and rightmost column in playfield."

- [x] **S12.1** `BombMarkWalls`: after load `rect.x`, `beq .BMWNext` when `x==0` (stored col 0 = screen cols 0+39 under reflection).
- [x] **S12.2** Build green + assert: MarkWalls has border skip; non-border `w==1` (e.g. L1R1 `x=17`) still markable; L2R2 `(0,4,1,4)` never marked.
- [ ] **S12.3** **User:** bomb next to side thin wall → wall stays; interior pillar (col 17) still vanishes.

---

## Risks (watch early)

| Risk | Mitigation |
|------|------------|
| ZP collision with bank1 | Bomb owns `$B5/$F6/$85/$F7` only; never `$F3–$F5`, `$AD`, `$BD–$C2`, `$F8–$FF` |
| `ObjectCount` free breaks flicker | S1.0 micro-step: keep count in register during `SelectActiveObject` only; build+review before bomb uses `$B5` |
| Removing `TileRow` line shifts EQUs | **Rename only**, keep one `byte` slot at `$85` |
| Kernel flicker from new branches | GRP1 override only; no new `.Line` tests |
| Rect mask vs ROM rects | Mask bits only; do not write ROM |
| PF reload wipes holes | `ApplyBombWalls` after **every** `LoadPFBuffer` |
| Wrong thin-wall test (`w>1`) | Only `w==1`; test with known 1-col pillar in level 1 room 0 |
| Down also used later for “drop through” | Edge-trigger bomb; don’t move player on Down |
| Fold pads after code size change | Rebuild → assert `$FC68`/`$FC70` match; update bank1 `jmp $Fxxx` if Overscan moves |

## Open defaults (change only if user overrides)

- Bomb priority over GRP1 enemy for whole fuse → **changed 2026-09-23:** fuse uses `BombTimer&3==0` (1/4 frames) so miner/enemies keep 3/4 priority; never gate bomb on `FlickerFrame` (Temp=1/2 desync).
- Destroyed thin walls **persist across room leave/re-enter until stage leave** (`LoadLevel` — user 2026-09-24). Packed in `RoomWallMask` `$F2` (room0 low nibble, room1 high nibble).
- Blast uses **X-ONLY col overlap** (±1 col, any Y) for player/enemy death (user 2026-09-24); **thin walls still use full 2D** (MarkWalls X-cols + ApplyBombWalls row range).
- Blast cols = `BombCol-1..BombCol+1` (clamp 0..19).
- **Border thin walls (`x==0`) never destroyed** (user 2026-09-24) — screen cols 0 and 39.
- HUD bomb icons track `PlayerBombs` (5→0); refill on `GameStart`/`ReloadLevel`/`LoadLevel` (level advance).
- Bomb drop **only when OnGround** (`BombPacked` b7): `StepDown` land/floor sets b7; free-fall + `StepUp` clear it; `EnterRoom`/`LoadLevel` zero it.
