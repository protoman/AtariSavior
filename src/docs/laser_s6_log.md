# Laser S6 — wall clamp (mid-wall stop) — session log 2026-10-02

## Room-data read ledger

| date | file | why | result |
|------|------|-----|--------|
| 2026-10-02 | (none) | S6 implemented entirely from code + runtime rect cache | **0 reads** |

S6 needs no room data: the clamp reads the runtime uniform rect cache
(`RcBase=$89`, `RcW1=$CC`) that `EnterRoom` already built. Room `.txt` /
`generated/` files were not opened this session (the build regenerating
`generated/*.asm` is the normal build pipeline, not a read by the agent).
Any future direct read must be appended to this table FIRST.

## What was wrong before (S6 context)

Held-laser sweep steps 8 px/phase; a phase jump can put the whole 8 px
window `[lo, lo+7]` past a nearby wall, so `LaserHitTest` killed enemies
straight through it. Prior attempts (rolled back by `962721d`, back at
`a6b94f4`; see `docs/bank0_refactor_progress.md`) failed by rewriting
NUSIZ/width (`LaserBeamOn` packing, floor-pow2 width — draw out of
position/size away from walls too) and by misreading rect fields
(`rect.y` vs `rect.x`, px vs tile-col). Do not repeat.

## What S6 does (locked design — baby step 1: clamp only)

- **One shared value:** `CollisionX` itself is clamped, so the drawn M0
  (`SetObjectXPos` arg) and the kill interval are always the same value.
  No width/NUSIZ/`BeamMask` change — beam stays 8 px, `LaserBeamOn=$02`.
- **Direction-aware first-wall tip** (`bank2 LaserWallClamp`, $F25A):
  - bank0 `LaserInput` stages the sweep-path cols BEFORE `jsr LaserHitTest`
    (`CollisionEndX`=c0 .. `CollisionCellX`=c1, px>>2):
    right = `[eye, lo+7]`, left = `[lo, eye+7]`, eye = `RoomX±4`.
  - LWC walks the rect cache once (beam rows `band(RoomY+2)..band(RoomY+3)`
    = exact LHT kill window; both screen spans of each rect incl. mirror
    `[40-x-w, 39-x]`; destroyed rects skipped via `BombPacked` b3-6).
  - right: first col = `max(span_lo, c0)` → `lo := min(lo, col*4-5)` (floor 0)
  - left: first col = `min(span_hi, c1)` → `lo := max(lo, col*4+2)`
  - tip lands 2 px inside the wall (mid-wall stop, user-accepted), so the
    kill window can never touch `face+4` / `face-1` = far side survives;
    near-side/inside-wall enemies still die.
- **Stack:** entered/left by `jmp` chains only (`LaserHitTestBody` →
  `jmp LaserWallClamp` … `jmp LaserClampDone`) — depth unchanged
  ($FB inside LWC). `LaserInput` result survives positioning via
  `pha` … `pla` (PLA sets Z from the value) before dispatch.
- **Placement:** LWC in bank2 free zone after `MothRowTable`, before
  `org $F9D9` (Origin Reverse-indexed = build fails on overflow). bank0
  pre-pad headroom is 1 B — nothing added there; `LaserInput` growth only
  shifted `SweepOff`/`BeamMask` within `$FFxx` (BeamMask page guard green).

## Verification (all green 2026-10-02)

- `./build.sh` — 4×4096, `verify_build: OK (1 warning = pre-pad 1B, pre-existing)`,
  `sim_bomb_fuse: OK` (stack guard).
- `tools/test_laser_s4.py` — source contracts incl. new S6 asserts
  (entry jmp, `LaserClampDone`, c0/c1 staging, pha/pla dispatch).
- `tools/test_laser_wall.py` — rewritten to the S6 reference; py65 sweep,
  both facings, X=4..155, 4 phases: **1216 frames, 419 clamped,
  `LaserBeamOn=$02` throughout, CollisionX == reference every frame.**
- Full battery: enemy_movement, laser_sound, level_bank, phm_walk — all PASS.

py65 caveat (AGENTS lesson): its F6 mapper peeks pure ROM — mirror-zone
bank flips are invisible to it. LWC/code addresses were checked by hand:
no fetch at `$xFFF6-$FFF9` (`LaserWallClamp` $F25A-, `LaserClampDone`
$FF03, `.LWpC` $FFA6).

## Not done (user next)

- **Stella test (user):** fire near walls both facings; laser must stop at
  the wall (mid-wall tip) and not kill enemies behind it; away from walls
  the beam must look/position exactly as before.
- Later baby steps (only if wanted): tighten tip (K), lamp/wall interplay,
  sound cue at wall stop.

---

# S6b — Stella symptoms diagnosed + fixed (2026-10-02)

## User Stella report (level 0 room 0, fire held while walking into wall)

1. Small gap (1-3 px) between beam tip and wall.
2. Beam slides back / shows partially behind the player on approach.
3. Beam passes the wall and kills enemies behind it (asked: both crossed
   AND died).

## Pixel-model calibration (the missing ground truth)

- `SetObjectXPos` arg A → object box-left = **A-7** (calibrated from
  battle-tested `PlayerHitsMap` `vl = arg-(4|7)` flush wall stops +
  real walks: R→col17 stops X=68 for face-68 wall).
- `PlayerSpriteA` ($F953): col0 lit, col7 never lit → sprite lit =
  `[X-7, X-1]` both directions; nose (face art col4/col3) = `X-3`/`X-4`.
- **drawn M0 = `[A-7, A]`** (8 px, NUSIZ0=$30 unchanged — e24d9de rule).
- `CTRLPF=$05` (reflect + priority): PF over M0 → beam px inside wall
  hidden → visible tip flush at face-1 when A ≥ face.

## Root causes (all three symptoms)

1. **Kill window ≠ drawn window:** asm kill = `[A, A+7]` (adc #7 cmp #15)
   while beam drawn = `[A-7, A]` → kill reached 7 px BEYOND the visible
   tip = invisible through-wall kills (also the original pre-S6 bug).
2. **Clamp target tuned for the wrong window:** right `face-5` /
   left `face+2` (S6a, drawn window assumed `[lo, lo+7]`) → with the
   real drawn window the tip lands 5 px short of the face = **gap**,
   and the drawn start sticks out left of the sprite = **behind-player
   stub**.
3. **Path anchored at the eye (`X+4`), not the nose:** at max approach
   (walk stops X=68, wall face 68) the eye col 18 > wall col 17 →
   wall never on the path → **no clamp at all** → beam spawns past the
   wall and kills through.

## S6b edits (3 coupled — applied, build green)

1. `kernel.asm` `.LaserPos` staging — nose-anchored path cols:
   - right: `c0 = (RoomX-3)>>2`, `c1 = CollisionX>>2` (no `adc #7`)
   - left:  `c0 = max(0, CollisionX-7)>>2`, `c1 = (RoomX-4)>>2`
2. `bank2.asm` `LaserWallClamp` cands (drawn-window targets):
   - right: `face-5` → `**face+2**` (min-apply; floor dropped — face+2
     ≥ 2 always)
   - left:  `face+2` → `**face+9**` (max-apply)
   - resulting drawn: right `[face-5, face+2]` (starts under sprite,
     visible tip flush, ≤2 px inside), left `[face+2, face+9]`.
3. `bank2.asm` kill test: `adc #7` → `**adc #14**` (window = drawn
   `[A-14+7..]` ⇔ `[A-7, A]` — kill == visible beam exactly).

Invariant: clamped right `A ∈ [4W, 4W+2]`, left `A ∈ [4W+9, 4W+10]`
(wall on path, sprite valid); never past face+2/far side — enemies
beyond survive; no-wall frames = raw (no spurious clamp).

## Answers to user questions

- **"Just shrink the beam?"** — possible (`NUSIZ0 $30→$20` + kill
  constants + clamp retune) but unnecessary: the root causes are window
  mismatches, not width. After S6b the beam is flush at every wall.
- **"Rebuild the whole thing?"** — NO. S1-S5 all validated; the fault
  was ~40 lines of S6 clamp/staging.

## Verification (all green 2026-10-02, S6b)

- `./build.sh` — 4×4096, verify_build OK (1 pre-existing warning),
  sim_bomb_fuse OK (stack guard ≥$F8).
- Battery 6/6: enemy_movement, laser_s4 (updated S6b contracts incl.
  nose anchors + `adc #14` + comment-strip), laser_sound, laser_wall
  (S6b spec + independent per-col invariant), level_bank, phm_walk.
- `test_laser_wall`: 1216 frames (X=4..155 × 2 facings × 4 phases),
  419 clamped, CollisionX == reference every frame, BeamOn=$02.
- Independent invariant probe (`/tmp/opencode/laser_invariant.py`,
  per-col first-wall + validity gate sprite lit cols free):
  **4576 valid frames / 5152 invalid poses skipped / 3024 no-wall /
  0 violations** (PASS/GAP/BEHIND/no-spurious-clamp).
- Room-data reads this session: **0**.

## Not done (user next)

- **Stella re-test (user):** level 0 room 0, fire while walking into
  the wall both facings: tip must touch the wall (no gap), no
  behind-player stub, enemies behind the wall survive; away from walls
  beam positions unchanged.
