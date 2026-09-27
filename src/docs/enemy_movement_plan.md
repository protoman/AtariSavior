# Enemy Movement Implementation Plan

Status: **E0 COMPLETE (user-validated 2026-09-26). E1-E5 not started.**
E0 shipped with one bug found in gate: the $C3 alias was clobbered by
VBLANK's `LoadPFBuffer` every frame after init — fixed by `RefreshEnemyY`
at overscan entry (lesson recorded in AGENTS.md "Lessons Learned").

Workflow: implement stage → build green (`build.sh` + `verify_build.py` +
assert checks) → user tests in Stella → user says "pass" → commit → next stage.

## Specs (confirmed with user 2026-09-26)

| Type | ID | Movement |
|------|----|----------|
| Spider | 0 | Slowly down and back up, 2 tiles max (24 px), hanging from a web. Down first. |
| Bat | 1 | Fast down and back up, only 2 px (wing-flap). Down first. |
| Snake | 2 | Unchanged: patrol 1 px/4 frames, ±`SNAKE_PATROL` from spawn. |
| Tentacle | 3 | Horizontal: chase player at half player speed (1 px / 2 frames), **stops at walls**. Vertical: slow bob, 2 px (1 px / 8 frames). |
| Moth | 4 | Horizontal: patrol spawn ±48 px (6 tiles), ping-pong; **invert immediately at wall**. Vertical: sine ≈ 1 tile total (±6 px) around spawn. |
| Lamp | 5 | Never moves. |

Speeds (accepted): bat every frame; spider ÷8; tentacle X ÷2 / Y ÷8;
moth X ÷2 (+ phase tick ÷2); snake ÷4 (unchanged). Gate = `TickCounter` low bits.

User answers: moth sine = ±6 px (1 tile total travel); moth range =
spawn ±48 patrol; tentacle stops at walls + has the slow 2 px vertical bob.

## Architecture facts

- ROM record stride 6: `type, x, y, range_min, range_max, dir`
  (`convert_level.py`, editor `EnemyData` already has range/dir fields —
  **no editor changes needed**; we use spawn-relative constants like snake).
- RAM shadow: `EnemyRamX` $BD-$BF (live X), `EnemyRamD` $C1 (b0-3 h-dir,
  b4-7 RoomDarkMask), `EnemyRamP` $C2 (b0-3 reserved moth phase, b4-7 reserved
  vdir — init `#$F0` = all down), `EnemyDeadMask` $BA, `LaserState` $C0.
  Live Y does NOT exist yet: draw/CEH/LaserHitTest read ROM y (static today).
- `UpdateEnemies` (overscan, L867): global `TickCounter & 3` gate, dead-skip,
  type dispatch by `cmp #ENEMY_SNAKE / bne UE_Next`, snake-only bounds logic.
  Temp is free here (joystick last read before this call).
- Player collision helper `PlayerHitsMap` (L2262): reads globals
  `RoomX/RoomY/PlayerDir`, box = `PLAYER_WIDTH × PLAYER_SPRITE_H` (7×12),
  walks `RoomRects`, C=1 blocked. Reuse for enemy wall checks by temporarily
  swapping RoomX/RoomY with the enemy position (restore on every path).
  **Known cycle risk:** 3 player calls already nearly overflowed overscan
  TIM64T=35 once (YToCellRow fix, L2228) — enemy calls must be measured per
  stage; fallback = lighter `EnemyProbe` (8×8 box, no PlayerDir/hot-rock).

## E0 design: live Y shadow (`EnemyRamY`)

ZP has **no free bytes** ($80-$BC sequential full; $BD-$C5 used; $C3-$E6 =
PF/Colupf buffers; $F8-$FF = stack). Design (mirrors the existing $F0-$F2
bomb-save alias pattern):

- `EnemyRamY = $C3-$C5` (3 slots) — aliases PF0Buf rows 0-2.
- Who runs when (per frame): overscan movement **writes** Y →
  VBLANK draw **reads** Y → VBLANK `LoadPFBuffer` **overwrites** with PF →
  kernel reads PF. This works ONLY with two order changes:
  1. **VBLANK:** move `jsr SelectActiveObject` BEFORE `jsr LoadPFBuffer`
     (currently L395 LoadPF → L400 Select; swap after verifying
     SelectActiveObject does not read PF buffers).
  2. **EnterRoom tail (L1120):** currently `LoadEnemyRam` then
     `LoadPFBuffer` — swap to `LoadPFBuffer → ApplyBombWalls → LoadEnemyRam`
     so the PF refresh happens before the Y load.
- bank1 must not write $C3-$C5: `PF2ScoreBuf` starts $C6 ✓ (verify —
  add a `verify_build` guard).
- Writers: `LoadEnemyRam`, `UpdateEnemies` (both overscan).
  Readers: `SelectActiveObject` (VBLANK), `CheckEnemyHit`,
  `LaserHitTest` (overscan). All documented in the ZP map comment.

## Stages

### E0 — Infrastructure (no visible change) ✅ COMPLETE (user-validated)

- [x] `EnemyRamY = $C3` decl + ZP-map comment update (alias contract).
- [x] VBLANK swap (`SelectActiveObject` before `LoadPFBuffer`) + EnterRoom
      tail reorder (PF first, `LoadEnemyRam` last).
- [x] `LoadEnemyRam`: copy ROM y → `EnemyRamY` for every slot (incl. lamp).
      **+ `RefreshEnemyY` at overscan entry (gate-found bug: VBLANK
      `LoadPFBuffer` clobbers $C3 every frame → enemies vanished after 1
      frame; lesson in AGENTS.md).**
- [x] Y readers switch to RAM: `SelectActiveObject` (`.SOEnemyPattern` — reload
      slot via `EnemyIndex`, `lda EnemyRamY,X`), `CheckEnemyHit`
      (ActiveObjectY source), `LaserHitTest` (vertical test).
- [x] `UpdateEnemies` restructure: drop global ÷4 gate; dispatch skeleton
      (snake arm + `UE_Next` fallthrough — E1-E4 add arms); snake handler
      gets its own `& 3` gate (behavior byte-identical).
- [x] `verify_build` guards: VBLANK order + EnterRoom order (source-order
      regex) + bank1 never writes $C3-$C5.
- [x] Assert checks: `tools/test_enemy_movement.py` (constants sync: gates,
      ranges, dispatch types; Y-alias address; refresh placement).
- [x] **User gate:** snake patrol identical; laser kills identical (spider and
      moth Y now live but static until E1/E4); lamp dark works; CEH/bomb/score
      unchanged; no frame roll; room transitions reload Y correctly.
      **PASSED 2026-09-26 (round 2, after RefreshEnemyY fix).**
- [x] Stop and ask user before E1.

### E1 — Bat (type 1, simplest mover — proves Y pipeline end-to-end)

- [ ] Handler: every frame, `inc/dec EnemyRamY,slot`; bounds [spawn, spawn+2],
      flip via vdir bit (`EnemyRamP` b4-7, shared spider/bat/tentacle, init
      down); no wall check (spec = range only).
- [ ] Extends `tools/test_enemy_movement.py` (bat bounds/flip math).
- [ ] **User gate:** bat bobs 2 px fast, up-down flapping at spawn X; laser +
      player collision follow the bob (no ghost hits at spawn Y); snake/spider
      otherwise unchanged; no frame roll.
- [ ] Stop and ask user before E2.

### E2 — Spider (type 0)

- [ ] Handler: ÷8 gate; bounds [spawn, spawn+24] (2 tiles down), flip vdir,
      down first (init already `%1111`); no wall check (spec = range only —
      if it visibly clips a wall at range end, report and we adjust).
- [ ] Web = motion only, no wire sprite (v1).
- [ ] **User gate:** slow descent/ascent over 24 px from spawn; collision +
      laser track it; death/score unchanged; no roll.
- [ ] Stop and ask user before E3.

### E3 — Tentacle (type 3)

- [ ] X handler: ÷2 gate; move 1 px toward `RoomX`; candidate step →
      swap RoomX/RoomY → `jsr PlayerHitsMap` → restore; blocked = hold
      position (player keeps approaching). Room-edge clamp via same check.
- [ ] Y handler: ÷8 gate; bob [spawn, spawn+2] via vdir bit.
- [ ] Measure overscan budget (Stella: no frame roll while chasing in
      4-rect rooms with fall + strafe) — if roll: implement `EnemyProbe`
      fallback (light rect walk, 8×8 box).
- [ ] **User gate:** tentacle chases at half player speed, stops against
      walls it cannot cross, slow 2 px bob visible, laser/collision track,
      no roll.
- [ ] Stop and ask user before E4.

### E4 — Moth (type 4, hardest)

- [ ] X handler: ÷2 gate; 1 px along live dir; bounds spawn ±48 AND
      wall probe (same swap+`PlayerHitsMap` as E3); either hit → clamp +
      `jsr UE_FlipDir`.
- [ ] Y: `EnemyRamY = spawnY + TriTable[phase]`, triangle ±6 px, 16 steps;
      phase = `EnemyRamP` b0-3, `++` per moth tick (shared phase — all moths
      in a room bob in sync; ≤3 elements per room, acceptable, documented).
      Recompute from spawn each tick (drift-proof).
- [ ] Cycle measure (moth + tentacle + player can each call
      `PlayerHitsMap` same frame — worst case vs TIM64T=35; fallback =
      `EnemyProbe` as in E3).
- [ ] **User gate:** moth patrols 6 tiles each way, turns at wall AND at
      range, visible ±6 px wave, collision/laser track both axes, no roll.
- [ ] Stop and ask user before E5.

### E5 — Final regression

- [ ] Rebuild editor + ROM; bank sizes, fold pads, level regen, ZP doc
      (`docs/zp_layout_skill.md`: EnemyRamY alias + writer/reader contract).
- [ ] Plan status finalized; `tools/test_enemy_movement.py` all green.
- [ ] **User gate:** full Stella pass — all 4 movers + snake + laser sweep
      kills + bombs + room transitions + score + lamp dark + no flicker/roll.
- [ ] Mark complete only after user confirms.

## Notes / accepted approximations

- Enemy wall box reuses player footprint (7×12 vs enemy 8×8, ±1 px via
  `PlayerDir`): coarse but walls are full tile bands; refine only if visible.
- Bat/spider have no wall check by spec (range from spawn only).
- Moth shared phase = synced bobbing across moths in one room.
- Editor unchanged (range/dir fields exist; constants used instead).
