# PF-Map Collision Rearchitecture Plan (kill the 5-rect limit)

**Status:** PLANNED — not started. Update checkboxes/notes as steps land.
**Motivation (2026-10-02):** level_003 rooms 2/3 (models 5/6) need 6 wall rects
each; the ZP rect cache holds 5 ($CC-$DF, stomp-zone boundary above, PF buffers
below). Exact minimal cover = 6 for both models — geometry, not greedy. A 6-rect
model loses rect6 on EnterRoom load (count copied raw, only 5 slots) = player
falls through it, and the walker's 6th iteration reads $E0+ (bank1 scorePtr
garbage) as a phantom rect. Interim guard: `verify_build.check_model_rects`
errors on any model >5 rects.

**HERO reference:** byte-scan of `hero.bin` (8K) found ZERO CXP0FB reads — HERO
does not use TIA hardware collision for walls; it tests cave data in software,
so room complexity costs ROM data bytes, not fixed slots. Our render source
(`convert_room.pf_values` → PF0Buf/PF1Buf/PF2Buf in ZP) already IS the
per-cell solidity map, holes included (`ClearPFColumn` punches it).

## Goal

Collision tests the PF buffers directly: any room shape, any rect count,
bounded only by ROM data. Bomb holes collide correctly for free.

## Acceptance criteria

- **A1**: unmodified models 5/6 (6-rect geometry) collide correctly in-game —
  the original bug gone, no model edits.
- **A2**: `build.sh` green (verify + `sim_bomb_fuse` + `sim_frame_budget`) +
  battery green at EVERY step.
- **A3**: no frame-budget regression — record the `OVER` meter before/after each
  walker swap; expect gain (walk ≈400-600c → ≤9 cell tests ≈150-200c).
- **A4**: bombs, hot rocks, laser clamp, enemies behave unchanged.

## Ground rules

- Per AGENTS: one step → build → test → Stella where visual → next step.
  Never two walkers in one step.
- Collision is critical path: battery (`tools/test_*.py`) + both sims gate
  every commit; `sim_frame_budget` wall-model invariant must stay clean.
- py65 checks drive real ROM (like `test_room_dark.py`), not re-implementations.

## Phase 0 — Research & spec (no game code) ✅ DONE 2026-10-02

### 0.1 Walker inventory

| # | Consumer | Location | Data source | Notes |
|---|----------|----------|-------------|-------|
| 1 | `PlayerHitsMap` | kernel:2438, `.RectLoop` 2527-2598 | ZP cache $CC-$DF | callers: CheckP0L/R (992/1011), StepDown (1088), StepUp (1126), UE_Tentacle probe (1568). Tail `jmp HotOverlapFlag` (2578, C=1 contract) |
| 2 | Moth walk | bank2:190-252 (`.MwLoop`) | ZP cache | verbatim PHM copy; HIT → `.MothTurn` |
| 3 | `LaserWallClamp` | bank2:325+ (`.LWrect` 352) | ZP cache | span math + explicit mirror spans + destroyed-test via `MothMaskBit`; entry pinned $F25A (sim gate!) |
| 4 | `HotOverlapBody` | bank2:734-810 | **ROM hot stream** (count-driven, 5B recs: mask,x,y,w,h) | NOT the ZP cache → no 5-slot limit |
| 5 | `BCF` hot-color walk | bank2:640-685 | ROM hot stream | renderer, not collision |
| 6 | `ApplyBombWalls` | kernel:2281-2325 | ZP cache rects0-3 via ABWX/ABWWTab | punches ClearPFColumn + sets rect.w b7; X=3..0 only |
| 7 | `BombMarkWalls` | bank1:945-1027 | ZP cache rects0-3 | count **clamped to 4** (993-995 — no OOB, my earlier OOB claim wrong); w==1 + x!=0 only |
| 8 | `EnterRoom` rect load | kernel:1292-1307 | ROM → 21B copy (count + 20B = rects0-4) | rect5 (6-rect models) NEVER copied + walk count=6 reads $E0+ garbage = THE BUG |
| 9 | `EnterRoom` mask pack/load | kernel:1221-1247, 1332-1356 | RoomWallMask $F2 | see 0.3a |
| 10 | `explore_laser.py` | dev tool | rect model | update at Phase 3 |

Exit handlers (1670-1718): **no rect walk** — EnterRoom only.
`check_model_rects` (verify_build): interim guard.

### 0.2 PF bit-layout spec (verified `convert_room.pf_values` + PHM inputs)

- Room row strings = **20 cols = LEFT HALF only** (WIDTH=20); rect data = left half (`x+w<=20` seam invariant).
- PHM cell range `CollisionEndX`(min)/`CollisionCellX`(max) = **source cols 0-19** already endpoint-mirrored (2475-2506). Moth same.
- LWC beam cols = display space 0-39 (does its own mirror spans).
- **`CellSolid(row, col)` contract: col = DISPLAY col 0-39, mirror if >=20 (c=39-d); row 0-2 (player max: RoomY 132 + 11 = 143 → row 2).** Source cols (<=19) pass through unchanged.

| source col c | buffer | address | mask |
|---|---|---|---|
| 0-3 | PF0 | `$C3+row` | `$10 << c` (bit4+c) |
| 4-11 | PF1 | `$C6+row` | `$80 >> (c-4)` (MSB-first) |
| 12-19 | PF2 | `$C9+row` | `$01 << (c-12)` (LSB-first) |

Tables: `ColOff[c]` = {0×4, 3×8, 6×8} (offset from `$C3+row`), `ColMask[c]` = {10,20,40,80, 80,40,20,10,08,04,02,01, 01,02,04,08,10,20,40,80}. Mirror inside CellSolid.

### 0.3 Open questions — ANSWERED

- **(a) RoomWallMask $F2: ALREADY BROKEN for >2 rooms.** EnterRoom packs room0 → low nibble, **all rooms ≥1 → high nibble (shared)** (1228-1247). level_003 has 6 rooms: leaving room1 → room3 restores room1's mask = phantom holes; rooms≥1 can't hold masks simultaneously. LoadLevel clears $F2 (1734). → **D1 leans strongly (B)** (holes reset on room leave): B fixes a broken feature with ~zero cost; A needs new multi-room storage anyway.
- **(b) Hot: NO CAP, not affected by the 5-slot bug.** Hot = separate ROM count-driven stream (5B records); ZP cache holds SOLID rects only. M5/M6 have 0 hot rects. → **Phase 6 shrinks to verify-only** (no rearchitecture needed).
- **(c) CheckP0Left/Right / StepUp / StepDown / exits:** only consume PHM or EnterRoom — no direct rect walks. Covered by 2.1 / no change.
- **BombMarkWalls count clamped to 4** — rects4+ (6-rect models) silently un-maskable; Phase 5 rewrites punch as cell-based anyway.

**Revised Phase 6:** 6.1 = run/confirm hot parity + py65 spot test; no data change (unless 0.3a D1-A chosen).

## Phase 1 — Cell-test primitive (side-by-side, game untouched) ✅ DONE 2026-10-02

- [x] **1.1 `CellSolid` leaf** — landed bank0 `$FDB2` (insert before the
      `.ds $FE10` ObjSprites pin; budget was $FDB2-$FE0F = 94B, used 65B).
      In: A = display col 0-39 (mirror `39-col` if ≥20 in-line), Y = row 0-2.
      **Out: Z=1 if EMPTY, Z=0 if SOLID** (`and` semantics — do NOT "fix" to
      Z=1-solid; inverting Z needs 2 instrs, branch polarity is free either
      way). Clobbers A/X/Y. Tables `ColOff` ($FDCB) / `ColMask` ($FDDF), 20B
      each (20-entry + in-code mirror — 40-entry tables didn't fit the pin
      budget). DASM gotcha hit: no `\` line continuation in `.byte`.
      **Check:** `tools/test_cell_map.py` — py65 drives CellSolid for
      models + all 3-row level .txt: 2400 cells × 20 geometries parity vs
      `pf_values` geometry + generator cross-check — **PASS**.
- [x] **1.2 Battery member.** **Check:** battery **8/8** + full build green
      (sims OK). NOTE: `check_model_rects` ERROR downgraded to **WARN** this
      phase — cache walkers (moth/LWC/bombs) still break on >5 rects until
      phases 2-5; WARN keeps build/sims gating every step. Restores to full
      deletion at 7.1 (never returns to ERROR — final state = unlimited).

## Phase 2 — PlayerHitsMap swap (the core)

- [x] **2.1 Replace `.RectLoop` body** — DONE 2026-10-02.
      - PHM walk = cell loop in place: `RectCount`=running row,
        `CollisionX`=running col, core = `lda CollisionX / tax / ldy
        RectCount / tya / clc / adc ColOff,X / tay / lda PF0Buf,Y /
        and ColMask,X / bne .CWHit`; row/col sweeps inclusive;
        HIT → `jmp HotOverlapFlag` (C=1 contract), miss → `clc/rts`.
      - **Stack depth unchanged (no jsr)** — an inline-loop choice on
        purpose: `jsr CellSolid` would drop gameplay min-SP $F9→$F7 and
        fail sim_bomb_fuse's `>= $F8` guard. Tables `ColOff`/`ColMask`
        stay post-pad (abs,X reachable); the standalone CellSolid leaf was
        deleted (dead) — its slot now holds only the tables.
      - `RcBase`/`FetchPtr`/`adc #4` stride gone from PHM (asserted);
        moth/LWC/bombs still cache-walk (phases 3-5). EnterRoom cache copy
        kept for them. Destroyed-flag (rect.w b7) skip gone from PHM —
        bomb holes come free from the buffers.
      - Headroom: pre-pad walk replaced by smaller loop (net -~30B).
      **Check:** `tools/test_cell_map.py` rewritten as full-PHM py65 driver —
      every model × RoomX 4..159 × both dirs × 5 row-pair reps = **14040
      boxes parity vs geometry** (prologue math replicated 8-bit in Python;
      hit path exercises bank2 HotOverlapBody via Mem $1FF8 bank emulation);
      `tools/test_phm_walk.py` PHM section re-aimed at cell contract (moth
      rect asserts kept until 4.1); battery **8/8**; `build.sh` green
      (**sim_bomb_fuse min-SP guard passed unchanged**).
- [ ] **2.2 Stella gate (user).** level_003 rooms 2/3 with ORIGINAL 6-rect
      models (A1) + one old level: walls, exits, subpixel slide, tentacle
      probe, DropStep spawn fall.
      **Check:** user confirms → A1 part 1 done → commit.
      Scope note: moth (bank2) and laser clamp still cache-walk → their
      rooms/behaviors get full gates at 4.1 / 3.1; 2.2 covers player +
      static geometry + tentacle probe (PHM-shared).

## Phase 3 — Laser walks

- [ ] **3.1 `LaserWallClamp`** (bank2 ROM walk) → cell tests along beam
      columns; update `explore_laser.py` reference model to match.
      **Check:** `test_laser_wall.py` + `test_laser_s4.py` + battery; Stella:
      beam stops at walls incl. thin-wall/hole columns.
- [ ] **3.2 `LaserHitTest` kill scan** — wall-related rect use → cells;
      enemy-only → documented no-op.
      **Check:** `test_laser_s4.py` + battery + Stella kill-through-corridor.

## Phase 4 — Enemy walkers

- [ ] **4.1 Moth walk** (bank2:192) → `CellSolid`.
      **Check:** `test_enemy_movement.py` + scripted sim scenario: moth never
      enters a solid cell across a full run.
- [ ] **4.2 Probe callers** (tentacle/derives via PHM — likely free after 2.1;
      change only what the 0.1 table shows remains).
      **Check:** battery + Stella: tentacle/moth patrol clean.

## Phase 5 — Bombs (decision gate D1)

- [ ] **5.0 User decision D1** (from 0.3a): hole persistence across room
      leave —
      **(A)** new representation (punched-col bitmap; ~3-5 ZP bytes, none
      currently free → needs a storage decision), or
      **(B)** holes reset on room leave/re-enter (behavior change, ~zero
      cost, no ZP).
      Present exact costs; user picks.
- [ ] **5.1 `BombMarkWalls` punch** → cell-based (punch PF bits at blast
      cells, reuse `ClearPFColumn`); `BombMaskBit`/`rect.w b7`/rect-index
      WallMask deleted or shrunk per D1.
      **Check:** `sim_bomb_fuse` + `test_laser_wall` + Stella: bomb through
      wall, hole visible, laser through hole.
- [ ] **5.2 `EnterRoom` restore** per D1 + delete rect-cache load if nothing
      needs it (hot may still — 0.3b).
      **Check:** leave/re-enter room → hole state matches D1; battery + sims.

## Phase 6 — Hot rocks

- [ ] **6.1 Hot check** (`HotOverlapFlag`/`HotOverlapBody`) → cell-based.
      PF bits don't encode hot — spec from 0.3b: small hot-tile list in ROM
      (x,y pairs; counts are small) or a hot mask row buffer if ZP allows.
      **Check:** py65 parity test (hot cells ⟺ death) + Stella hot-rock
      touch/death + battery.

## Phase 7 — Cleanup & room freedom

- [ ] **7.1 Data pipeline.** Stop emitting solid rects from
      `convert_room`/models_data (keep hot only if 6.1 kept lists); remove or
      re-scope the interim `check_model_rects` ≤5 guard (may become: no
      constraint at all, or only a hot-count one).
      **Check:** models 5/6 untouched → build green → A1 verified end-to-end.
- [ ] **7.2 Docs.** AGENTS Phase-3 notes, `docs/zp_layout_skill.md` rect-cache
      rows, S6 walk-cycle lessons (`.RectLoop` gone — restate around cells),
      close this plan with outcome notes.
      **Check:** grep shows no stale `RcW1`/5-rect claims; final battery +
      both sims + clean Stella session of level_003.

## Sequencing note

Phases 1-2 alone fix the reported bug (A1); bombs/hot/laser keep using rects
meanwhile (they only misbehave for >5 models, same as today). Phases 3-7 lift
the limit everywhere. Steps 2.1 and 5.1 are the riskiest — each gets its own
Stella gate. Estimated ~14 steps, each independently committable.
