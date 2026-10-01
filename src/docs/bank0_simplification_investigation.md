# Bank0 Simplification / Optimization Investigation

Date: 2026-10-01
Scope: our own 6507/TIA code only (no HERO comparison). Goal: where bank0
code can be made **smaller, simpler, or cheaper in cycles**, including
refactors that require touching the level data format or trimming gameplay.

All byte figures are **approximate**, derived from `bank0.lst` label-to-label
spans and source-pattern counts. Re-validate with a rebuild + listing diff
after any refactor (the build's own guards are listed in §10).

---

## 1. Measurement basis

| Source | What it gave |
|---|---|
| `bank0.lst` (2955 emitted rows, 3768 emitted bytes) | per-routine byte spans, free-gap map |
| `kernel.asm` (3479 lines, ~50% comments) | duplication pattern counts |
| `bank1.lst` / `bank2.lst` | off-bank free capacity |
| `generated/*.asm` + `tools/convert_level.py` / `convert_room.py` | level data format, strides |
| `tools/verify_build.py` (8 check families) | invariants any refactor must keep green |

### Top bank0 routines by size (label→next-label, includes trailing data)

| Routine | ≈Bytes | Note |
|---|---|---|
| `StartFrame` (VSYNC+VBLANK preamble through kernel entry) | 330 | mixes ~10 concerns |
| `PlayerHitsMap` | 248 | mirror math + fragmented-cache walk + `.Stage3` |
| `SelectActiveObject` | 248 | count/mod/walk/color/position for 1 GRP1 |
| `EnterRoom` | 247 | wall-mask nibble pack + 4 cache-copy loops + 3 fold batches |
| `BuildColupF` | 176 | **runs every frame** in VBLANK |
| `LoadLevel` | 146 | 14 unrolled fold reads |
| `UpdateP0Vertical` (physics) | 135 | |
| `BombMarkWalls` | 124 | duplicates PHM's visible-left/col math |
| `HotOverlapFlag` | 117 | fold walk + `pha` per rect (stack depth!) |
| `Overscan` | 93 | |
| `DeriveEnemyY` / `RefreshEnemyY` | 95 / 86 | |
| `LaserInput` / `LaserHitTest` | 92 / 90 | |
| `UE_Tentacle` / `ApplyBombWalls` | 77 / 77 | |
| `BombEnemyBlast` / `BombPlayerBlast` | 65 / 51 | |

### bank0 free space today (3768B emitted of 4096B)

| Region | Free | Character |
|---|---|---|
| `$FBB5-$FBF7` | **67B** | main-headroom before the `$FBF8` ReturnPad pin |
| `$FC3B-$FC48` | 14B | before MothExitPad pin |
| `$FDF9-$FE0F` | 23B | after `BuildColupF`, before ObjSprites pin |
| `$FE5B-$FEEF` | **149B** | after ObjSprites, before `$FEF0` moth tramp |
| `$FF9D-$FFA5` | 9B | `$FF20+` tail |
| **total** | **≈262B** | main code region itself is at 0B headroom (ends `$FBB4`) |

### Cross-bank capacity (the cheap lever)

| Bank | Emitted | ≈Free | Notes |
|---|---|---|---|
| bank1 | 1442B | **≈2650B** | 1341B contiguous free *before* `MenuMain` ($F540) |
| bank2 | 677B | **≈3400B** | ~1.8KB contiguous at `$F287-$F9D8` |
| bank0 | 3768B | ≈328B | main region full |

`leaf_move_plan` already proved the pattern: move a leaf to bank1/2, keep a
byte-identical CallPad in bank0. A `jsr CallPad_X` costs ~16 extra cycles —
irrelevant in overscan (1096c headroom) and mostly irrelevant in VBLANK.

---

## 2. Findings — direct code duplication (pure bank0 bytes)

### D1. Life-loss path copy-pasted 5×  → save ≈100B  *(biggest pure win)*

Identical sequences counted in `kernel.asm`:

- `lda #0 / sta vyLo / sta vyHi / sta JetPower / sta PlayerYSub` — **7 copies** (14B each ≈ 98B)
- `lda #3 / sta PlayerLives / lda #$00 / sta EnemyDeadMask / jsr ReloadLevel` — **4 copies**
- `dec PlayerLives / bpl …` — **5 sites**: timer expiry (`kernel.asm:1015`),
  `CheckEnemyHit` (`:2110`), `BombPlayerBlast` (`:2251`), `LoseLifeHot`
  (`:3000`), `LoseLifeBand` (`:3051`).

Refactor: one `LoseLife` routine:

```
LoseLife:  dec PlayerLives
           bpl .stay
           lda #3 / sta PlayerLives / lda #0 / sta EnemyDeadMask
           jsr ReloadLevel / rts
.stay:     lda #0 / sta vyLo / sta vyHi / sta JetPower / sta PlayerYSub
           rts
```

Callers keep only their extras (band: `RoomY -= 12`; hot: Temp flag already
set; timer: reload BarLevel). `LoadLevel`/`ReloadLevel` keep their one
zero-physics copy (or `jsr LoseLife.stay`-style shared tail).
≈34B of logic per site → 3B `jsr` per site. **Save ≈100–115B.**

### D2. `ExitRoomUp/Down/Left/Right` — 4 near-identical routines → save ≈45B

Each (`kernel.asm:1656-1704`) = `jsr GetConnIdx` + N×`iny` + `jsr FoldIndirect`
+ `cmp #$ff/beq` + `jsr EnterRoom` + edge store + `rts` ≈ 20B.
One routine with direction index in a register/`CollisionX` + a 4-byte
edge-value table (`MAX_Y, MIN_Y, MAX_X, MIN_X`).

### D3. `LoadLevel` unrolled 14-field read → save ≈60B

`kernel.asm:1750-1795`: 14 × (`jsr FoldIndirect / sta DEST / iny`) ≈ 100B.
FoldIndirect preserves X **and** Y, so a loop works:

```
ldx #0
.loop:  txa / tay              ; rom offset = field index
        jsr FoldIndirect
        ldy DestTab,X          ; ZP dest address for field X
        sta 0,Y                ; abs,Y store into ZP
        inx / cpx #14 / bne .loop
```
≈20B code + 14B `DestTab` ≈ 34B. No new ZP needed (X = dest index, Y rebuilt
from X each iteration). Same fold batch, same depth.

### D4. Overlap-test math duplicated 4–5× → save ≈40–60B

`sbc / clc / adc #K / cmp #M / bcs` span test appears in:
`CheckMinerPickup` X and Y, `CheckEnemyHit` X and Y, `LaserHitTest` Y and X.
A shared `SpanOverlap` helper (inputs: A=lo1, operand lo2, K, M via table or
immediate-carry-in) costs one `jsr` per site (3B) vs ~12B inline each.

### D5. Visible-left / mirror-column math duplicated 3× → save ≈35B

- `PlayerHitsMap` first-block (`kernel.asm:2539-2564`)
- `PlayerHitsMap` last-block (`:2566-2579`)
- `BombMarkWalls` (`:2279-2299`) — comment itself says *"identical to
  PlayerHitsMap"*.

One `PxToHalfCol` helper (A = pixel → A = mirrored half-column 0..19),
20B body replaces 3 × ~20B. Works on the overscan path only (cycle-free).

### D6. Enemy "kill" boilerplate ×3 → save ≈15B

`lda EnemyDeadMask / ora EnemyBitTable,X / sta EnemyDeadMask / lda #$50 /
jsr CallPad_AddScore` — in `CheckEnemyHit`, `BombEnemyBlast`,
`LaserHitTest`. A `KillEnemyX` helper (X = slot) collapses each to `jsr`.

### D7. Snake left/right branches are mirror images → save ≈30B

`UE_SnakeLeft` / `UE_SnakeRight` (`kernel.asm:1447-1497`, ~46B each) differ
only in `inc`/`dec`, `bcc`/`bcs`, and `+patrol`/`-patrol`. Unify: compute
`bound = spawn ± SNAKE_PATROL` once from the initial-dir bit, then one
compare/clamp/flip block.

### D8. `SelectActiveObject` mod-by-subtraction + miner-offset arithmetic

`.SOModLoop` (`kernel.asm:1904-1911`) subtracts in a loop; the miner-slot
offset is recomputed 3 times (`.SOCount`, `.SOEnemy`, the `cmp EnemyCount`
pairs). With ≤4 slots a table `FlickerFrame → slot` (4B) or computing the
modulo only when `FlickerFrame >= count` would flatten it. ≈30–50B plus much
flatter control flow.

---

## 3. Findings — structural (higher value, higher care)

### S1. Fragmented rect cache is the root of several subsystems' complexity

The 21-byte solid-rect cache is split across **four ZP regions** because it
lives in the dead rows of the PF buffers:

```
$C6        count (RcBase)
$C7-$CE    rects 0-1   (window1)
$D3-$DA    rects 2-3   (window2)
$89/$8A    rect4 x,y   (MapPtrLo/Hi)
$DE/$DF    rect4 w,h
```

Consequences paid in code:

| Consequence | Where | ≈Bytes |
|---|---|---|
| 4 separate copy loops `.rcW1-.rcW4` in `EnterRoom` | `kernel.asm:1269-1288` | ~40B (one loop would be ~16B) |
| window-switch logic (`cpy #16 / cpy #8 / lda #RcW2`) in PHM | `:2679-2685` | ~20B |
| `.Stage3` fixed-address rect4 special case | `:2691-2718` | ~28B |
| exit-Y normalisation discipline (`.nrmCol/.nrmRow`) | `:2669-2689` | ~15B |
| `ABWXTab/ABWYTab/ABWWTab/ABWHTab` ZP-address tables | `:2410-2413` | 16B |
| hot-rect walk must fold (not ZP) → `pha` per rect | `HotOverlapFlag` | stack depth +2 |

**Refactor:** reserve one contiguous 21B (or ~37B, see S2) rect cache in a
ZP re-layout (§4), copy with a single loop, walk with `base = RcBase + i*4`.
Deletes `.Stage3`, the window switch, one EnterRoom loop, and the four ABW
tables. **Save ≈90–110B** and removes the trickiest code in PHM.

### S2. Extend the cache to cover hot rects → kills the fold + `pha` in the hot path

`HotOverlapFlag` (117B) folds bank2 per field and does `tya/pha` per rect —
one of the reasons the deepest call chain (`frame → StepDown → PHM →
HotOverlapFlag → FoldIndirect + pha`) reached SP `$F6` (the documented bomb-
fuse stomp). If EnterRoom also copied the hot section (1 count + M×5 ≈ 16B)
into the same cache, the hot walk becomes direct ZP reads: no fold, no `pha`,
−2 stack levels. That in turn **re-opens `jsr`-based factoring** that the
stack guard currently forbids (see S5). `BuildColupF`'s per-frame hot walk
gets the same win (it also folds + `pha` every rect, every frame).

### S3. ZP layout is the binding constraint — it is full, but the buffers are fat

`docs/zp_layout_skill.md`: *"no free sequential bank0 byte"*. But look at the
12-row buffers that were never shrunk after the kernel went to 3 bands:

| Buffer | Declared | Actually read | Dead/aliased tail |
|---|---|---|---|
| `PF0Buf` $C3 | 12B | rows 0-2 (3B = EnemyRamY) | 9B = rect cache win1 |
| `PF1Buf` $CF | 12B | rows 0-2 + `$D2` band color | 8B = rect cache win2 |
| `PF2Buf` $DB | 12B | rows 0-2 (3B) | 9B = rect4 + FetchPtr + 5 truly dead |
| `ColupfBuf` $E7 | 12B | rows 0-2 (3B) | 9B = `$F0-$F2` bombs + dead |

The kernel only ever indexes X=0..2 (`TILE_ROWS=3`). The 12-stride is
legacy from the 20×12 era.

**Refactor (one coordinated ZP re-plan):**

1. Shrink all four buffers to 3-byte arrays → frees ~26B of address space.
2. Place a **contiguous 21–37B rect cache** there (enables S1+S2).
3. Give `EnemyRamY` its **own 3 bytes** (no alias over `PF0Buf[0..2]`).

Effect of (3): **`LoadPF0Only` dies** — the per-frame 3-fold PF0 repair
(`kernel.asm:470`, ~15B code + ~130c/frame VBL) exists *only* because
`RefreshEnemyY` stomps `$C3`. That also deletes:
- the `check_enemy_alias` ordering guard in verify_build,
- the "SelectActiveObject must run before LoadPF0Only" constraint,
- the "LoadEnemyRam must run after PF refresh" constraint,
- the bank1 "must not write $C3-$C5" rule.

Risk: high — every ZP address is a frozen contract (bank1 HUD, score,
verify_build guards, `sim_bomb_fuse.py` write-tracking, comments in
`zp_layout_skill.md`). Must be one atomic change with all tests run.

### S4. `BuildColupF` rebuilds everything every frame (176B code, ~300-500c VBL)

VBLANK budget: worst 1311c of 1472 (`TIM64T #23`, only 161c headroom).
`BuildColupF` per frame = 3 stripe writes + fold walk of *all* hot rects +
`IsRoomDark` pad call + possible dark fill. But its inputs change rarely:

- stripe colors → change only on `LoadLevel`
- hot pulse color → changes only when `TickCounter & $10` flips (every 16 frames)
- dark/fuse state → changes on lamp crash / bomb state edge
- hot rect rows → never change within a level

Refactor: rebuild on a **dirty flag** (set by `EnterRoom`, pulse-phase edge,
dark-state change, `BombMarkWalls`). Steady state = 0 work.
**Cycle win (VBL headroom), byte cost ≈0** (maybe +10B). Complements any
future VBL growth.

### S5. The stack guard forbids the refactors that would pay for themselves

Documented rule: gameplay min SP ≥ `$F8`, whole run ≥ `$F7`. Every `jsr`
level costs 2 bytes of headroom, which is why PHM inlines `YToCellRow`,
tail-`jmp`s `HotOverlapFlag`, and every fold batch is hand-staged.

Root cause is the 4-level chain `frame → StepDown → PHM → (Hot/rect-walk) →
FoldIndirect`. Removing folds from that chain (S2: hot rects in ZP) drops 1-2
levels and makes ordinary `jsr` factoring (D4/D5 helpers) structurally safe
instead of "measure SP in the sim and hope".

**Rule of thumb for this refactor set: ZP-cache consolidation (S1+S2) first,
then helper factoring becomes cheap.**

### S6. Per-frame staging noise

- `sta FetchPtr` × **35** (each stage = 4 instructions ≈ 12B ⇒ ~420B of
  staging in bank0)
- `jsr FoldIndirect` × **57**
- `lda EnemyDataLo/Hi … FetchPtr` staged separately in **6** places
  (`StartFrame`, `EnterRoom`, `LoadEnemyRam`, `UpdateEnemies`,
  `DeriveEnemyY`, `LaserHitTest`)

No single fix without changing the fold protocol, but: routines that run
back-to-back in the same overscan pass (`UpdateEnemies`, `CheckEnemyHit`,
`RefreshEnemyY` all read the same `EnemyData*`) could stage **once** in
`Overscan` and let the callees inherit — ~3 stages saved ≈ 36B + 12 cycles.
Careful: `EnterRoom` re-stages on room change (correctly).

---

## 4. Data-format / level-format changes (bank2 + loader)

These mostly free **bank2** (already 83% free) but several simplify bank0
code measurably.

### F1. Enemy record stride 6 → 4  → save ≈15B bank0 + 2B/enemy data

Current record: `type, x, y, range_min, range_max, dir` (6B).
`range_min/range_max` are **dead**: `UpdateEnemies` comment — *"Ignores
editor range_* per user 2026-09-23"*, and nothing else reads them.

- `LoadEnemyRam`: drop two `iny` skips (`kernel.asm:1377-1379`)
- `UE_Tentacle`/snake folds at `+5` become `+3`
- `EnemyOffTable` values `0,6,12` → `0,4,8` (still a 3B table, or `txa/asl/asl`)
- stride arithmetic everywhere becomes a shift instead of `*6` table
- generator: `ENEMY_STRIDE = 6` → 4 in `convert_level.py`, editor export

Requires updating `test_enemy_movement.py` stride assertions.

### F2. PF table stride 12 → 3  → data-only, simplifies pointer math

`convert_room.py`: `TABLE_STRIDE = 12` pads every `TilePF0/1/2` block to 12
bytes although `HEIGHT = 3`. 9 wasted bytes × 3 registers × per model.
`EnterRoom`'s `+12/+12` pointer arithmetic (`kernel.asm:1236-1249`, 16B)
becomes `+3/+3` (same code, smaller tables). Saves ~27B per model in bank2
— matters only when content grows (bank2 has ~3.4KB free today).

### F3. Drop the hot-rect parent-mask field (gameplay rule change)

`convert_room.py` emits `mask, x, y, w, h` (5B/hot rect); the mask lets a
blasted wall kill its contained hot pieces (`HotOverlapFlag` parent gate,
~10B bank0). If a blasted wall simply leaves the hot rect **dead forever**
or **always alive** (pick one), the field disappears → 4B/hot rect, simpler
walks in `HotOverlapFlag` **and** `BuildColupF`. Gameplay delta is small
(edge case: hot rock sitting inside a bombable 1-wide wall).

### F4. Room wall-mask nibble packing in `EnterRoom` (gameplay change option)

`RoomWallMask` packs two rooms' masks into one byte (nibble per room) and
`EnterRoom` does pack-on-leave + unpack-on-enter (`kernel.asm:1188-1214` +
`:1320-1337`, ≈60B total). Simplification: **destroyed walls reset when you
leave the room** (or persist whole-byte per room in a 2-byte array). Removes
both nibble passes and the save/restore dance; costs a small gameplay change.

### F5. Level record fields (`LevelDataTable` stride 14)

Currently 14B/level: start(3) + miner(3) + wall colors(2) + 3 pointers.
Nothing obviously redundant; `start_x/start_y` are constants 32/24 in both
generators — could go to EQUs (−2B/level, trivial). Low priority.

---

## 5. Gameplay simplifications (bytes + complexity, if you accept the delta)

| Change | ≈Bank0 save | What changes |
|---|---|---|
| Walls reset on room re-enter (F4) | ~60B | destroyed thin walls no longer persist across exits |
| Drop laser sweep phases (fixed beam offset) | ~35B | `SweepOff` table + phase code in `LaserInput`; laser stops "sweeping" |
| Drop hot-parent death rule (F3) | ~10B | see above |
| Drop jet inertia ramp (binary thrust) | ~25B | `.JetCapped/.JetDecay` ramp; jet feels snappier/less floaty |
| Drop second animation frame (`PlayerSpriteB`) | ~20B | no jet-leg flutter; `Grp0Ptr` pick block in VBL shrinks |
| Fixed flicker order (no modulo rotation) | ~30B | `.SOModLoop`; objects blink in fixed slots instead of rotating |
| Enemy patrol bounds from live count instead of ROM dir | ~25B | snake no longer folds ROM `dir` for bounds |

Each is independent; each touches `test_enemy_movement.py` /
`test_laser_s4.py` expectations.

---

## 6. Small / mechanical wins

| Item | Save | Note |
|---|---|---|
| Dead `YToCellRow` subroutine (`kernel.asm:2498`) | ~10B | PHM inlines it; **no `jsr YToCellRow` exists**. But `test_enemy_movement.py:215` text-slices on the label — update the test's anchor |
| `YToRowTable` 48B → compare chain (`cmp #12/cmp #24/cmp #36`) | ~34B | costs +4..6c per PHM call; overscan has 1096c headroom — safe. PHM is called up to ~6×/frame while falling+strafing |
| Write-only `ObjBot` (2 stores + 1 ZP byte) | ~7B + 1 ZP | documented "no readers" (`kernel.asm:2006`) |
| Unused EQUs `LASER_PREV`, `LASER_HP`, `PF2ScoreBuf` ("legacy; no users"), `HUD_ROWS` alias | source only | no ROM bytes; delete for clarity |
| Unreferenced labels `UE_SnakeLeft`, `UpdateP0Vertical` (code reachable by fall-through, label never branched to) | source only | keep code, drop or wire the labels |
| `LoadRoomBottomColor` is now `lda / rts` wrapped by `jsr` ×2 | ~5B | inline the 3-byte load at both sites |
| Comment weight: kernel.asm ≈50% comment lines | 0 | many cycle-count comments are provably stale per AGENTS rule — worth a pass, but never trusted for budgeting |

---

## 7. Where *not* to touch

- **Kernel `.Line` / `.Row` / `.WaterRow`** — cycle-tuned to 61c worst vs
  76c budget; per-pass line totals are load-bearing (262-line frames).
  Any edit requires a fresh worst-path recount from `bank0.lst`.
- **`SetObjectXPos` placement** (`$FF10-$FF1F`) and `fineAdjustTable`
  page alignment — 5c div15 contract, guarded by verify_build.
- **`ObjSprites` base address** (`$FE10`) and `BeamMask` in `$FFxx` —
  both page-cross contracts are guarded.
- **CallPad/ReturnPad byte-identity block** and `$FFF6-$FFF9` mirror zone —
  hard-coded into `verify_build.py` + AGENTS rules.
- **Score/HUD addresses** `$F3-$F5`, `$B3/$B8` — cross-bank shared with
  bank1.

---

## 8. Recommended order (value ÷ risk)

**Phase 1 — pure duplication, no contracts touched (~150-200B, low risk)**
1. D1 `LoseLife` unification (5 sites + 7 zero-physics copies)
2. D3 `LoadLevel` field loop
3. D2 unified `ExitRoom`
4. S6 stages for `EnemyData*` shared across one overscan pass
5. Mechanical wins (§6)

Verify: `./build.sh` (verify_build + sim_bomb_fuse), Stella smoke test,
`test_phm_walk.py` / `test_enemy_movement.py`.

**Phase 2 — cycle budget, no format change (~0B, low risk)**
6. S4 dirty-flag `BuildColupF` (VBL headroom +1311c→~1000c worst)

**Phase 3 — ZP re-plan (the big one: ~120-150B bank0 + removes a per-frame
fold + unlocks stack headroom; HIGH risk, atomic)**
7. Shrink PF/Colup buffers 12→3, contiguous rect cache, private `EnemyRamY`
8. S1 single copy loop + delete `.Stage3`/window-switch/ABW tables
9. S2 hot rects into the cache → `HotOverlapFlag` fold-free, −2 SP levels
10. Delete `LoadPF0Only` + `check_enemy_alias` guard
11. Rewrite `docs/zp_layout_skill.md`, re-measure min SP in `sim_bomb_fuse.py`

**Phase 4 — data format (~15B bank0 + data simplification; touches
generators + editor export + tests)**
12. F1 enemy stride 6→4
13. F3 / F4 only if the gameplay change is accepted

**Phase 5 — offload leaves to bank1/bank2 (up to ~400-500B more bank0 headroom; medium risk, cycle cost ~16c/call)**
14. Candidates in descending size: `BuildColupF` (176B), `BombMarkWalls`
    (124B), `HotOverlapFlag` (117B), `LaserHitTest` (90B), `UE_Tentacle`
    (77B). bank1 has ~2.6KB free, bank2 ~3.4KB.
    Caveats: `HotOverlapFlag` is tail-called from PHM (its `rts` returns
    PHM's caller — a CallPad `sta $1FF7 / jmp` preserves that, a `jsr` would
    not); `BuildColupF` runs in VBLANK (fold-heavy already, +16c is fine
    inside the 161c margin — but re-measure after Phase 2).

**Phase 6 — gameplay cuts (optional, pick per taste)**
15. §5 table, one at a time, user test after each (Build-Test-Build rule).

Rough cumulative ceiling: Phases 1+3+4+5 ≈ **700-900B** of bank0 code
freed (≈20-25% of today's 3768B), plus ~500-800c/frame of VBL/overscan time,
plus the removal of three cross-bank ordering guards.

---

## 9. Functional refactor list (short answer to the question)

| Functionality | Why it benefits | Est. saving |
|---|---|---|
| **Life/death handling** | 5 copies of life logic + 7 of zero-physics | ≈100-115B |
| **Collision rect system** (`PlayerHitsMap` + cache + `HotOverlapFlag` + `ApplyBombWalls`/`BombMarkWalls`) | fragmented cache drives loops/special cases/folds/stack guard | ≈120-160B + 2 stack levels + VBL cycles |
| **Room/level loading** (`EnterRoom`, `LoadLevel`, `ExitRoom*`) | unrolled folds, 4 copy loops, 4 exit clones, nibble packing | ≈150B |
| **ZP layout / PF buffers** | 12-row buffers in a 3-row kernel; alias contracts force per-frame repair | enables everything else; −130c/frame |
| **Enemy iteration** (4 walks: update/select/hit/laser) | repeated stage + dead-mask boilerplate; stride-6 with dead fields | ≈40-60B (+ data) |
| **VBLANK frame prep** (`StartFrame`, `BuildColupF`) | rebuilds static data every frame | cycles, ~0B |
| **Laser** | sweep phase machinery | ≈35B if sweep dropped |
| **Life-loss gameplay paths** (hot/band/timer/enemy/blast) | same as life handling, also shared trigger detection | included above |
| **Vertical physics** | 7 copies of zero-velocity block folded into `LoseLife` | included above |

---

## 10. Constraints any refactor must keep green

- `./build.sh` → `verify_build.py` checks: ROM/4K, fold block byte-identity,
  moth tramp + `$FFF6-$FFF9` fill, callpads (no clobber, frozen jmp
  literals), level TXT round-trip, `check_enemy_alias` (dies with Phase 3),
  frozen `LEVEL_DATA_ADDR`.
- `sim_bomb_fuse.py`: min SP ≥ `$F8` gameplay / ≥ `$F7` whole run —
  re-measure after **any** added `jsr` in a deep path.
- `test_phm_walk.py`, `test_enemy_movement.py` (parses kernel source text —
  anchor labels like `YToCellRow subroutine` are load-bearing for it),
  `test_level_bank.py`, `test_laser_s4.py`, `test_laser_sound.py`.
- Frame = 262 lines; VBL worst ≤ 1472c, overscan worst ≤ 3200c.
- Bank0 main region must end before the `$FBF8` ReturnPad pin (today:
  `$FBB4` = 67B headroom) — `.ds` pins must not move.
