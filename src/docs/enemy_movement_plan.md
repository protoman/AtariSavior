# Enemy Movement Implementation Plan

Status: **E0 COMPLETE (user-validated 2026-09-26). E1 + E2 + E3 IMPLEMENTED
(build+tests green, derived-Y + swap-probe design).
E-gate round 1 (user Stella test) FAILED 3 of 4 checks — fixes implemented
2026-09-27, re-test pending (see "E-gate round 1" below).
E4 BLOCKED on space decision; E5 not started.**
E0 shipped with one bug found in gate: the $C3 alias was clobbered by
VBLANK's `LoadPFBuffer` every frame after init — fixed by `RefreshEnemyY`
at overscan entry (lesson recorded in AGENTS.md "Lessons Learned").

## E-gate round 1 (user feedback 2026-09-27) — fixes in tree, re-test pending

| Check | Verdict | Root cause | Fix |
|-------|---------|------------|-----|
| Bat speed | Too fast (1 px/frame) | gate read `TickCounter` directly | clock `>>1` → 1 px / 2 frames |
| Spider | Counted down 8 px, then **teleported** to bottom, repeated | `TickCounter` is the **60-frame game timer** (60→1, reload): `(TC>>3)&63` only ever sees 0..7 and counts DOWN, wrap 0→7 = jump | free-running frame clock `EnemyRamP` (`inc` in `RefreshEnemyY`); spider gate `clock>>2`, span 24, **dwell at top** (`p>=48 → delta 0`) so the 256-wrap lands inside the flat zone. Gate ÷4 (not spec ÷8): a 48-step phase can never align with a 256-step clock; 64-step ÷4 can. |
| Tentacle X | Never moved horizontally | `PlayerHitsMap` → `YToCellRow` does `tax`: **X (enemy slot) clobbered** by the probe — `sta EnemyRamX,X` wrote to `EnemyRamX[row]`, not the tentacle's slot | push/pop slot X around `jsr PlayerHitsMap` (`txa/pha ... pla/tax`; PLA preserves C) |
| Water band | Painted the whole bottom 48-px band | TILE_ROWS refactor left band color on all of row 2 | split row 2: bodies 36 + `.WaterRow` pass (own setup line + 11 bodies = 12-line strip, `bottom_band_plan` rule 2); death `RoomY>=125`, respawn `-=12` (spec rules 2/4) |

Also: `bank1` ToGameStub `jmp $F167` → `$F178` (Overscan moved after the
kernel edits — fold-pad guard caught it).

**Round-2 user gates (all pending):** bat 1 px/2f flap; spider down 24 px
over ~4 s, up, short dwell at top, no jump at wrap; tentacle slides 1 px/4f
toward player until wall; water strip = thin bottom strip (~12 lines) above
HUD, touching it kills and respawns 12 px up.

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

Speeds (accepted): bat 1 px/2f (**user E-gate: halve the original 1 px/frame**);
spider 1 px/4f ÷4 gate with top dwell (**spec ÷8 impossible statelessly** — see
E-gate table; range 24 px kept); tentacle X 1 px/4f (**user E-gate round 2:
halve again from ÷2**) / Y ÷8; moth X ÷2 (+ phase tick
÷2); snake ÷4 (unchanged). Gates read the `EnemyRamP` frame clock (snake keeps
`TickCounter & 3` — stateful, wrap hiccup harmless).

User answers: moth sine = ±6 px (1 tile total travel); moth range =
spawn ±48 patrol; tentacle stops at walls + has the slow 2 px vertical bob.

## Architecture facts

- ROM record stride 6: `type, x, y, range_min, range_max, dir`
  (`convert_level.py`, editor `EnemyData` already has range/dir fields —
  **no editor changes needed**; we use spawn-relative constants like snake).
- RAM shadow: `EnemyRamX` $BD-$BF (live X), `EnemyRamD` $C1 (b0-3 h-dir,
  b4-7 RoomDarkMask), `EnemyRamP` $C2 (**free-running frame clock** since
  E-gate fix — `inc` once/frame in `RefreshEnemyY`; init `#$F0` on room load
  = harmless seed), `EnemyDeadMask` $BA, `LaserState` $C0.
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

**Design change (implemented): derived Y, no stored movement state.**
No free ZP byte exists for a persistent bat vdir/offset, and `EnemyRamY`
($C3-$C5) is clobbered every VBLANK by `LoadPFBuffer`. So bat live Y is
*derived* each overscan in `DeriveEnemyY` (called from `RefreshEnemyY`):
`Y = ROM spawn y + tri(TickCounter & 3)` where tri = 0,1,2,1
(phase 3 mapped to 1) → bobs [spawn, spawn+2] at 1 px/frame, always
down/bob (no vdir bit needed — triangle is inherent). Static enemies use
ROM y unchanged. No `UpdateEnemies` bat arm (would double-apply), no
bank2 fold needed for E1/E2. Space recovered for `DeriveEnemyY` (+34B):
offset calcs → `ldy EnemyOffTable,X` (−6 UE, −9 draw, −6 CEH),
`BitMaskTable` moved to tail hole, shared `GetConnIdx` ExitRoom helper
(−5). Bank2 fold pads remain a fallback — E3 fitted without them (sub +
swap-probe); E4 needs the space decision.

- [x] `DeriveEnemyY` + `RefreshEnemyY` rework + dispatch trims
      (bounds [spawn, spawn+2] inherent; no wall check per spec).
- [x] `tools/test_enemy_movement.py` extended (derive branch, triangle
      mapping, no UE bat arm, level_001 room0 = bat).
- [x] Build green (4×4096, verify OK, pre-pad end $FC64) + both test
      suites pass.
- [x] level_001 room0 first-screen enemy → type 1 bat (x=1, y=6,
      range 0-4 kept).
- [ ] **User gate:** bat bobs 2 px fast, up-down flapping at spawn X; laser +
      player collision follow the bob (no ghost hits at spawn Y); snake/spider
      otherwise unchanged; no frame roll.
- [ ] Stop and ask user before E2.

### E2 — Spider (type 0)

**Design: derived like E1** (no bank2 fold needed). `DeriveEnemyY` spider
path: `p = (TickCounter>>3) mod 48`, `delta = p<25 ? p : 48-p` →
spawn..spawn+24, 1 px per 8 frames, down first (triangle is inherent —
the plan's `EnemyRamP` vdir bit is unneeded). No `UpdateEnemies` spider arm.
Space for the +34B derive arm came from compressing `YToRowTable`:
192-entry (A/48) → 48-entry indexed by A>>2 (floor nesting) = −144B,
+4c/call in PlayerHitsMap (2 calls/frame, trivial vs TIM64T=35 budget).
Main headroom now ~106B (E3/E4 derive arms + UE X-arms fit; revisit fold
machinery if E4 overflows).

- [x] `DeriveEnemyY` spider path (mod-48 triangle, shared spawn-add tail);
      dispatch `cmp #ENEMY_SPIDER`.
- [x] `tools/test_enemy_movement.py` extended (spider derive math, no UE
      spider arm, YToRowTable 48-entry guard).
- [x] Build green (4×4096, verify 0 warnings, main ~106B free) + both
      test suites pass.
- [x] Spider already spawns in level_001 room 1 (reachable through exit).
- [ ] **User gate:** slow descent/ascent over 24 px from spawn; collision +
      laser track it; death/score unchanged; no roll.
- [ ] Stop and ask user before E3.

### E3 — Tentacle (type 3)

**Design notes (implemented):**
- Y bob = derived (`DeriveEnemyY` `.DEYTickShift`): same bat triangle
  (0,1,2,1) gated ÷8 → spawn..spawn+2, no vdir state.
- X chase lives in `UpdateEnemies` as a **subroutine `UE_Tentacle`** (tail
  jmp from dispatch, not inline branch): the inline arm pushed snake's
  `UE_Next` branches past the 127-byte range. Dispatch checks tentacle FIRST,
  then snake (keeps the original short snake branches).
- Probe = plan-exact swap+`PlayerHitsMap`: `ActiveObjectX/Y` scratch saves
  player xy (NOT the stack — the original 3×PHA drove SP to $F4 and jsr
  return bytes stomped BombTimer/BombX every 4th frame), put candidate X +
  live `EnemyRamY,X`, call, scratch restore (`lda`/`sta` keep C),
  commit `EnemyRamX,X` only on C=0. Candidate ≥160 (incl. wrap 255) rejected
  pre-probe = room-edge hold. Temp use verified safe (all overscan Temp
  consumers run before `jsr UpdateEnemies`).
- Gate ÷2 (`TickCounter & 1`) = 1 px / 2 frames (half player speed).
- **Cycle budget NOT statically proven** — worst frame = player fall (2 PHM)
  + strafe (2 PHM) + tentacle probe (1 PHM). Existing comment: 3× PHM
  validated, 4-5× unmeasured. **Fallback if user gate shows roll:**
  probe gate ÷4 (`and #3` — slows chase too) or `EnemyProbe` light rect
  walk (plan's original fallback).

- [x] Derived Y bob + `UE_Tentacle` subroutine + dispatch order.
- [x] `tools/test_enemy_movement.py` extended (÷8 gate, probe order
      PHM→restore→commit, pha/pla pairs, subroutine return, dispatch order).
- [x] Build green (4×4096, verify OK, main ~33B free) + both suites pass.
- [ ] **User gate:** tentacle chases at half player speed, stops against
      walls it cannot cross, slow 2 px bob visible, laser/collision track,
      no roll (watch frame in 4-rect room while falling + strafing as it
      chases).
- [ ] Stop and ask user before E4.

### E4 — Moth (type 4, hardest)

**BLOCKED on space decision (~95B needed, ~33B free) + EnemyRamP writer
audit — decide with user after E1-E3 gates.** Options: (1) bank2 fold
machinery (plan's original design — touches all 4 banks + build script,
do it ONCE for E4's ~95B and any future banks); (2) more table/code
compression (next candidates: StartFrame 302B, LoadLevel 136B — both
VBLANK/overscan leaves, risky); (3) shared `UE_ProbeStep` helper (extract
tentacle's swap+PHM probe → moth reuses; ~40B saving, still ~60B short).
Moth Y derive alone (~25B) WOULD fit now — sub-stage option.

- [ ] X handler: ÷2 gate; 1 px along live dir; bounds spawn ±48 AND
      wall probe (same swap+`PlayerHitsMap` as E3); either hit → clamp +
      `jsr UE_FlipDir`.
- [ ] Y: `EnemyRamY = spawnY + TriTable[phase]`, triangle ±6 px, 16 steps;
      phase = `EnemyRamP` b0-3, `++` per moth tick (shared phase — all moths
      in a room bob in sync; ≤3 elements per room, acceptable, documented).
      Recompute from spawn each tick (drift-proof). NOTE: plan said table —
      spider-style `cmp/eor/sbc` triangle avoids the 16B table.
- [ ] **EnemyRamP ($C2) writer audit FIRST** (E0 alias lesson: map every
      writer across the frame before using).
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
