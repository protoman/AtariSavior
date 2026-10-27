# Coding gotchas and open items

_php/pla decimal mode, Origin Reverse-indexed, score rewards, editor flicker budget, open items._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

### php/pla X-preserve sets decimal mode (2026-09-23) — NEVER repeat

**Bug:** To keep `EnemyIndex` in X across `jsr IsRoomDark`, code used
`php / tax / <call> / pla / tax / plp`. After `pla`, X still held the **saved
flags** (from `php`), not the saved X. The following `plp` then restored **X
into the flags**. When X happened to have bit 3 set, **D (decimal mode) was
enabled** — every subsequent `ADC`/`SBC` became BCD math. Symptoms: stuck
player, vertical-rectangle miner, black playfield, garbage collision.

**Fix:** Do **not** preserve X across a call with php/pla/tax/plp. Make the
callee clobber-safe and reload the value in the **caller** instead:
`jsr IsRoomDark` (clobbers A/X only, Y safe) then
`lda (EnemyDataLo),Y / tax` to reload type before `EnemyColorTable,X`.

**Rule:** Never invent stack-preserving register dances. If a routine must
return a value, put it in A (or a documented ZP temp). Callers reload.

### Origin Reverse-indexed: bank0 code must end before $FC68 (2026-09-23)

F6 fold pads live at fixed `org $FC68` / `org $FC70`. DASM errors
`Origin Reverse-indexed` if main code (everything before those orgs) grows
past `$FC68`.

**When adding bank0 routines that push the end over `$FC68`:** move **leaf
helpers** (not the fold pads themselves) **after** `org $FC70` — same pattern
as existing `AddScore` / `ReloadLevel` (S5.x moved `HotOverlapFlag` to
bank2 instead). `jsr` is absolute, so post-pad placement is fine. Never
move `Overscan` without syncing bank1's `jmp $Fxxx` (ToGameStub at
`$FC70` must match) — this fired 3× in the S3.x refactors alone
($F182→$F176→$F173); the fold-pad byte-identity guard catches it, but
sync the literal by hand.

**This session:** `AddScore` alone overflowed (fc68→fc72). Fixed by moving
`AddScore` + `ReloadLevel` after the pads. Build green: 4×4096, folds match,
Overscan still `$F14D`.

### Score rewards (2026-09-23): +50 kill, +75 wall, no fire hack

- **Removed** bank1 fire-button `INPT4` → `+$50` hack (was demo-only).
- **`AddScore`** (after fold pads): A = BCD amount (`#$50`/`#$75`).
  `ScoreTe` packed BCD (`tens*16+ones`), `ScoreTh`/`ScoreHu` binary 0-9.
  Overflow: `$a0` wrap → inc Hu; Hu≥10 → wrap, inc Th; Th≥10 → cap 9.
- **Call sites (bank0 overscan):**
  - `CheckEnemyHit` after `sta DeadEnemyIdx` (non-lamp) → `#$50`
  - `BombEnemyBlast` after kill → `#$50`
  - `BombMarkWalls` only when WallMask bit **was clear** → `#$75`
    (and-ora with existing mask; already-broken → skip score)
- **Score persists** across `ReloadLevel` (not cleared on death).
- Score display is 6 digits, right-aligned: `0 0 ScoreTh ScoreHu tens ones` → "000075" for 75 points.
  ptrs 1-2 = leading zero; ptrs 3-6 = value. Max 9999 → "009999".

### Editor flicker budget (2026-09-23)

`MapCanvas`: **max 2 elements/room** (`kMaxRoomElements`) and **max 1 element
per row** (miner/enemy/lamp share a row budget; same ≤2 cap enforced on data
by `verify_build` objects >2). Warnings via `QMessageBox`.
Rationale: GRP1 is one sprite — more simultaneous objects → more flicker
(rotating `SelectActiveObject`). Restrict at authoring time.

### Open items (refresh 2026-10-01)

- **RESOLVED 2026-10-07** — *BombEnemyBlast can kill lamps* (type 5): the
  blast loop now skips LAMP (`bank2.asm BombEnemyBlastBody`: `cmp #LAMP /
  beq .BEBNext`), so a lamp survives, keeps its dark-room trigger and no
  phantom +50 is awarded. **Guard added 2026-10-18:** `tools/test_bomb_lamp.py`
  (6 cases: enemy dies / lamp survives in either slot order, lamp-only = no
  kill, pre-dead enemy, range gate `|dcol| < 2`, one kill per blast). The
  entry above sat stale for 11 days — when picking up an "open item", verify it
  against the code first.
- **Phase wall = one-time crushable wall (user ruling 2026-10-18).** A
  full-band stripe cannot be crossed in one pass: falling 48 px from a standing
  start takes ~55 frames (subgravity 8/256 px/f²) while PhaseBlink's OFF half is
  45 frames — measured by `tools/qa_sweep.py`. That is INTENDED: taking the
  crush kill latches the removal (`EnemyDeadMask b6`), which force-opens the
  cell until the next `EnterRoom`, so the wall costs one life and is open for
  the rest of the room visit. Do not "fix" the blink into a timing gate without
  a new user ruling.
- **Raft = a row-2 platform cell** (`RAFT` tile 6): `tile_to_char` renders it
  as a solid wall cell, so it is a static platform you can stand on (~RoomY 84)
  while the `bottom_band` water below kills at `RoomY >= 125`. Authored with
  the editor's ADD_RAFT brush (row 2, water room, painted on an AIR cell) and
  enforced by convert (`RAFT` row 2 only; raft models need `bottom_band`). It
  is NOT a moving/rideable object — motion has never been specified; ask the
  user before adding any.

- **Cross-bank Temp conflict (documented, allowlisted):** bank1 `Temp` =
  `$AD` = bank0's `TickCounter` slot (NOT bank0's `Temp` at `$88`) —
  bank1 uses it as its score-init first-frame flag (`inc` once). Deliberate;
  `check_equ_sync.ZP_ALLOW` records it. Fragile if either side's frame
  phase changes.
- **Tentacle residual (user-accepted):** probe still lets it enter walls
  slightly on the left — PHM's entry uses PLAYER origin/width for the
  candidate box; fix = per-enemy origin offset in `UE_Tentacle`. Details:
  `docs/bank0_refactor_progress.md` (S3.2 entry).
