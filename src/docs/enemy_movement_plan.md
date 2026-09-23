# Enemy Movement Plan

Per-type behaviors (user spec 2026-09-23) + editor initial facing.
Baby steps: implement → build → **user validates in Stella** → next.
No room-JSON schema change (`dir` already exists). **Do not commit** until user says so.

**Editor requirement (user):** every placed enemy **must show facing direction** on the
canvas (arrow/icon ←/→), not only a hidden `dir` field — so the designer can see
which way snake/moth will move first.

---

## Spec

| Type | ID | Movement | Facing (`dir`) |
|------|----|----------|----------------|
| Spider | 0 | Vertical only: hang from web line (placement Y), bob **2× player height = 16 px** down and back. X fixed. | Unused for motion |
| Bat | 1 | **No movement.** | Unused |
| Snake | 2 | Horizontal L/R, **patrol span = visible GRP1 width (4px, `$f0`)**: spawn ↔ spawn±4, side = initial facing (out full width, back full width). **May sit in walls** (no wall collision). **First move = facing.** **1 px / 2 frames.** Ignores `range_*` (user 2026-09-23). | Required |
| Tentacle | 3 | Horizontal only: **follow player X at ½ player speed**. No vertical move. | Unused |
| Giant moth | 4 | Horizontal span ~**10× sprite width** (use `range_*` as limits). **First move = facing.** Vertical = **sine** on placement Y, amplitude = sprite height (8 px); phase advances with horizontal motion. | Required |

**Colors (already in `EnemyColorTable` — verify only, no change expected):**

| Type | Byte | Look |
|------|------|------|
| Spider | `$14` | dark yellow |
| Bat | `$F2` | brown |
| Snake | `$C4` | green |
| Tentacle | `$0E` | white |
| Moth | `$22` | dark orange |

**Constants / existing facts:**

- `MAX_ENEMIES = 4` per room (`convert_level.py`).
- ROM record stride 6: `type, x, y, range_min, range_max, dir`.
- `dir` already in JSON: `+1` right, `-1` left. Editor currently always writes `1`.
- `range_*` stored as `px(column, 4)` — **no** `enemy_x_px` offset. Bounce limits must be converted to the same X space as live enemy X (apply `enemy_x_px` at load, or compare in column space).
- `enemy_x_px`: `target = column*4`; return `target+4` if `target<11` else `target+7`.
- Player height = 8, width used in hit tests = `PLAYER_WIDTH` / `PLAYER_HEIGHT`.
- Horizontal player ≈ **1 px/frame** when held (confirm in S3). Tentacle = **1 px every 2 frames**.
- GRP1 snake/miner = **4×8** (`$f0` / `PLAYER_WIDTH`); `ENEMY_WIDTH=4` for patrol span (was wrongly 8 → 4px gap past wall flush).
- `SelectActiveObject` + `CheckEnemyHit` **read ROM** today → must read **RAM shadow** after S2.
- ZP shared all banks — new RAM must be checked against `docs/zp_layout_skill.md` before allocating.

---

## Open defaults (change only if user overrides)

- **S1 spider:** `Y ∈ [y0, y0+16]`, bounce, 1 px every 2 frames (web at top).
- **S1 tentacle:** 1 px / 2 frames toward `RoomX` (½ of 1 px/frame).
- **S1 moth sine:** 16-step table, amplitude 8; `phase += 1` each time X moves 1 px; period = 16 px horizontal.
- **S1 speed default:** 1 px / 2 frames for snake/moth unless range span feels too fast.

---

## Steps

### S0 — Plan + research ✅

- [x] Spec captured; ROM/RAM, `dir`, ranges, colors, `MAX_ENEMIES=4` documented.

---

### S1 — Editor: initial facing

No JSON schema change (`dir` already in `EnemyData`).

- [x] **S1.1** Facing control: button **“Initial facing: → (F)”** under tools +
      **F** on canvas toggles →/←. Default → (`dir=1`).
- [x] **S1.2** Place uses `m_initialFacing` (`eData.dir = ±1`), not hardcoded `1`.
- [x] **S1.3** **Facing indicator:** white **▶/◀** triangle beside every enemy
      marker on canvas; updates on flip + after reload (`dir` from JSON).
- [x] **S1.4** Click existing enemy with enemy brush **flips** `dir` (no stack).
      F / button flips the *next* placement facing.
- [x] **S1.5** Save/load: `dir` round-trips in JSON (cereal already serializes it).
- [ ] **S1.6** **User validates editor:** place snake/moth left and right; **arrows
      visible on every enemy**; facing flips when changed; reopen file keeps
      facing + arrows.

**Files:** `tools/editor/src/MapCanvas.cpp/.hpp`, `MainWindow.cpp/.hpp`.

**Build:** `cmake --build tools/editor/cmake-build-debug --target savior_editor`
— OK (2026-09-23).

---

### S2 — RAM shadow (no behavior change)

ROM is not writable. Movement needs live X/Y/(dir/phase).

- [x] **S2.1** Free ZP found: sequential vars end `$BC`; free `$BD-$C2` (6).
      Packed layout:
      - `EnemyRamX[4]` = `$BD`
      - ~~`EnemyRamY[4]` = `$F3`~~ **removed 2026-09-23** — `$F3-$F6` is bank1
        score (`ScoreTh..ScoreOn`); bank1 HUD writes it every game frame.
        Y stays in ROM (stride +2) until S5 spider needs live Y.
      - `EnemyRamD` = `$C1` (dir bits 0-3)
      - `EnemyRamP` = `$C2` (moth phase + spider vdir)
      - ~~`$F7` spare / move gate~~ **removed** — snake now 1 px/frame.
      ~~Overlap `$BF-$C2` = bank1 score~~ **false** — bank1 score moved to
      `$F3-$F6`; `$BF-$C2` is enemy-only. Recorded in `zp_layout_skill.md`.
- [x] **S2.2** `EnterRoom` → `LoadEnemyRam`: copy ROM `x,y,dir` → RAM.
      Spider vdir init `%1111` (down). Bounce limits stay in ROM (convert at S4).
- [x] **S2.3** `SelectActiveObject`: X/Y from RAM; type still ROM (color).
- [x] **S2.4** `CheckEnemyHit`: X from RAM; **Y from ROM** (not shadowed).
- [x] **S2.5** Build + fold-pads + 4×4096 — OK (2026-09-23). **User:** game plays
      as before (enemies static, hit still works, colors same).

---

### S3 — Player horizontal speed baseline

- [x] **S3.1** Code read (`CheckP0Left`/`CheckP0Right`, `kernel.asm` l.587–620):
      **1 px/frame held** — one `dec/inc RoomX` per overscan when stick held
      (collision undoes). Matches expect.
- [x] **S3.2** Documented: player X = **1 px/frame held**. Snake = same
      (gate removed in S4.6). Tentacle remains ½ player → 1 px / 2 frames
      (separate gate when S7 lands).

---

### S4 — Snake patrol (first moving type)

- [x] **S4.1** Overscan `UpdateEnemies` (after `EndInputCheck`, before miner/hit):
      snake `X += dir` (packed `EnemyRamD`); bounce vs `range_min`/`range_max`
      **converted on the fly** (`UE_ConvRange`: rom+4 if <11 else +7) — live-X
      space matches `enemy_x_px` spawn.
- [x] **S4.2** **First move = facing:** dir only from ROM at `LoadEnemyRam`; not forced.
- [x] **S4.3** **No wall collision** for snake (by design — can live in walls).
- [x] **S4.4** Bounce: **on-the-fly** `UE_ConvRange` (no RAM for range arrays).
- [x] **S4.6** **Snake blink-back fix (2026-09-23):**
      1. bank1 `ScoreTh..On` `$BF-$C2` → **`$F3-$F6`** (was corrupting
         `EnemyRamX[2]/[3]/D/P` every HUD frame via fire BCD + digit math).
      2. **`sta WSYNC` / `sta HMOVE` after `SelectActiveObject`** — P1 HMP
         was set but never latched; stale HMP1 (bank1 score P1@68) caused
         coarse 15px jumps / blink to wrong X.
      3. **Removed 1px/2f gate** (`EnemyRamSpare`) — snake moves **1 px/frame**
         like player and HERO (`INC`/`DEC` per frame).
      4. `EnemyRamY` dropped; Y from ROM in Select/CheckEnemyHit.
- [x] **S4.5** **User validated:** snake slides L/R smoothly, no blink,
      reverses at range, first move = editor facing, passes through walls.
- [x] **S4.7** **User adjustments (2026-09-23, post-S4.5):**
      1. **Patrol span = visible GRP1 width** — not editor `range_*`.
         Bounds: ROM spawn X ↔ spawn ± `ENEMY_WIDTH`, side from ROM dir
         (initial facing). Path: out full width, back full width to spawn.
      2. **No wall collision** — confirmed already true (no `PlayerHitsMap`
         for snake; can sit in walls / move inside open playfield freely).
      3. **Half speed** — 1 px / 2 frames via `TickCounter & 1` gate in
         `UpdateEnemies` (even frames only). `UE_ConvRange` removed from
         snake path (deleted — no other callers).
- [x] **S4.7b** **Width bug + flush stop (2026-09-23, snake_001/002):**
      `ENEMY_WIDTH` was 8 but snake draws `GRP1=$f0` = **4px**. From spawn
      inside wall `[0,7]` visible-left≈4, flush=8 needs travel **4**; `+8`
      overshot → gap between wall and snake (user measured up to 8px game).
      Fix: `ENEMY_WIDTH=4` matches `$f0`. **Lesson below — moth is at risk.**
- [ ] **S4.8** **User:** snake patrols ±4px from spawn (flush with wall edge,
      no gap), half speed, still no wall collision, no blink.

---

### Lessons learned (apply to moth / any span-based mover)

**L1 — Span constant MUST equal the drawn GRP1 bitmap width, not a guessed “8×8”.**
Snake lesson (S4.7b): `ENEMY_WIDTH=8` vs `lda #$f0` (bits 7–4 only = **4px**)
gave a gap of (8−4)=4px past wall flush (looked like 8px on scaled Stella shots).
Moth plan says “~**10× sprite width**”: if moth is also `$f0`, span = **40px**,
not 80. Before coding moth bounds, open the `GRP1` value in the kernel and
count set bits × NUSIZ copies. Update `ENEMY_WIDTH` / `MOTH_SPAN` from that
number only.

**L2 — “Fully out of wall” ≠ spawn+span if spawn is already near the exit.**
Flush position = first X where **visible left edge** is past the last wall
pixel. `enemy_x_px` adds +4/+7 so the **editor column** matches the visible
edge; runtime bounds must use the same logical X as `EnemyRamX` /
`SetObjectXPos`. Do not mix raw playfield-column pixels with `EnemyRamX`
without applying the same offset. When a mover starts inside a wall, verify:
`visible(spawn) + drawn_width == visible(rmax)` lands on `wall_last+1`.

**L3 — User screenshots beat “logic is clean in Stella”.**
`UpdateEnemies` can be perfect while the **drawn** width/offset is wrong.
Breakpoints also hide timing-only bugs; measure gap in **game pixels**
(Stella scale), not raw PNG pixels (`screenshots/snake_001.png`).

**L4 — Moth checklist (before S8):**
1. Confirm moth `GRP1` width (and NUSIZ if multi-copy).
2. `span = 10 * drawn_width` (40 if `$f0`).
3. `range_*` in ROM are `px(column,4)` — convert to `EnemyRamX` space or
   compare in column space consistently (old `UE_ConvRange` lesson).
4. Sine Y amplitude = **drawn height** (8), not a guessed size.
5. Snap test: start, max L, max R — gap to wall must be 0 when “fully out”.

---

### S5 — Spider vertical bob

- [ ] **S5.1** Spider: ignore horizontal; `Y` oscillates `y0 .. y0+16`, bounce, flip internal dir bit.
- [ ] **S5.2** Speed: 1 px / 2 frames (adjust after user look).
- [ ] **S5.3** Collision uses live Y (already from S2).
- [ ] **S5.4** **User:** spider hangs under web line, walks down 16 px and back; no X drift; hit box follows.

---

### S6 — Bat

- [ ] **S6.1** Explicit no-op in `UpdateEnemies` (or skip type=1).
- [ ] **S6.2** **User:** bat frozen; color `$F2` distinct from others.

---

### S7 — Tentacle follows player

- [ ] **S7.1** Every 2 frames: `X` step 1 px toward `RoomX` (0 when equal).
- [ ] **S7.2** No Y change. No range clamp required (follows player) unless user wants arena limits later.
- [ ] **S7.3** **User:** tentacle tracks player horizontally, visibly slower than player; white `$0E`.

---

### S8 — Moth: horizontal + sine Y

- [ ] **S8.1** Horizontal like snake (`range_*`, first move = facing).
- [ ] **S8.2** Sine table (16 entries, amplitude 8) in ROM; `Y = y0 + SineTable[phase & 15]` (or centered `y0-4+offset` — pick one, comment; default **y0 + table[0..8..0]** hanging from placement).
- [ ] **S8.3** `phase++` when X changes (or every frame — prefer with X so wave ties to flight).
- [ ] **S8.4** **User:** moth flies ~10× width (range), undulates smoothly, first move = facing, orange `$22`.

---

### S9 — Colors + polish pass

- [ ] **S9.1** Confirm all 5 types on screen together (or sequential rooms): five distinct hues, no swap.
- [ ] **S9.2** Overscan still within TIM64T (no frame-length flicker) with 4 moving enemies.
- [ ] **S9.3** Dead enemy (`DeadEnemyIdx`) does not move / not drawn.
- [ ] **S9.4** Room change reloads RAM (positions reset to spawn — correct for revisit).

---

### S10 — Final validation

- [ ] **V1** Full build green, fold MATCH, 4×4096, 0 new page-crosses in game path.
- [ ] **V2** Editor: facing set/visible/persist.
- [ ] **V3** All five behaviors match spec (user checklist above).
- [ ] **V4** No kernel flicker / HUD shift / power-bar regression.
- [ ] **V5** Update `zp_layout_skill.md` + `AGENTS.md` enemy bullet (movement now live).
- [ ] **V6** Commit only when user approves.

---

## Files likely touched

| Area | Files |
|------|--------|
| Editor facing | `tools/editor/src/MapCanvas.cpp`, `MapCanvas.hpp`, maybe `MainWindow.cpp` |
| Game move + RAM | `src/kernel.asm` (`EnterRoom`, `SelectActiveObject`, `CheckEnemyHit`, new `UpdateEnemies`) |
| ZP doc | `src/docs/zp_layout_skill.md` |
| Colors (likely none) | `EnemyColorTable` in `kernel.asm` |
| Converter (likely none) | `convert_level.py` already emits `dir` |

**Not in scope:** laser, bombs, magma/lava data format, sprite art beyond current squares, enemy death by laser.

---

## Risks

1. **ZP tight** — 12-byte shadow may collide; resolve before S2.1 coding.
2. **`range` vs `enemy_x_px` space** — bounce off-by-4/7 if forgotten (S4.4).
3. **Overscan budget** — 4 enemies × types; keep `UpdateEnemies` simple; measure S9.2.
4. **`dir=-1` in DASM** — `.byte -1` → `$FF`; converter already `int(dir)`; verify listing.
5. **Snake in wall** — hit test is footprint vs player only (OK); do not “fix” with wall collision.
6. **Editor facing UX** — if F-key vs checkbox unclear, user redirects in S1.6.
