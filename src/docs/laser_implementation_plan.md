# Laser Implementation Plan

Status: **S1 COMPLETE (user-validated 2026-09-26). S2.1 COMPLETE
(user-validated 2026-09-26). S2.2 COMPLETE (round-2 fixes validated
2026-09-26, commit `1b1d11c`). S2.3 implemented + build green — awaiting
full-S2 user gate.**

Use one Missile 0 (`M0`), 8×2 pixels, moving 8 pixels per frame across a 24-pixel span and back while fire is held. CRT/phosphor persistence supplies visual trail. Keep P1 free for enemies and objects. INPT4 is active-low at `$0C`; bank0 currently disables M0/M1/ball in cave and does not otherwise position missiles. Bank1 uses ball later in HUD, after cave rendering.

Laser scanline starts at player `RoomY+2`, yellow face row. Release fire disables beam. Collision must cover missile's swept interval each frame, so fast movement cannot skip enemies. Laser kill must persist independently for each enemy; current `DeadEnemyIdx` tracks only one enemy, so extend dead tracking before adding score.

Every step ends at a user validation gate. Build ROM, report exact check, then stop and wait for Stella feedback before starting next step.

## Steps

### S0 — Known-good baseline ✅

- [x] Laser-free ROM restored; user confirmed map collision and snake behavior good.
- [x] Baseline commit: `f84161d`.

### S1 — Fire input and M0 state; no visible beam

- [x] Confirm fire reads from TIA `INPT4=$0C`, pressed low, released high.
  - HERO raw bytes use `BIT $0C` / `BMI` (fires on D7=0); bank1.asm already had
    `INPT4 = $0C`; kernel.asm's `INPT4 = $028C` was wrong (RIOT timer mirror,
    unused) — fixed to `$0C`; assembles as `LDA $0C` zp (`a5 0c`).
- [x] Add M0 press/hold/release state and a 24-pixel sweep phase. Audit shared zero-page first; do not add a byte without checking every bank.
  - Audit: the whole ZP is allocated, and a laser byte must survive the full
    frame loop (overscan → VBLANK → kernel → HUD → overscan), so `Temp`,
    PF/Colupf buffers, score digits, lives, bomb bytes, and `CollisionX`
    were all rejected (each is written mid-cycle by VBLANK/HUD/overscan).
  - Freed **`$C0`** by shrinking `EnemyRamX` to 3 slots ($BD-$BF): editor
    already caps rooms at 3 elements; `convert_level.MAX_ENEMIES` 4→3 and
    `verify_build` enemies+lamps 4→3 enforce it (actual data max = 2, so no
    level changed). `EnemyRamX[3]` would otherwise collide with `$C0`.
  - `LaserState = $C0`: b7 held now, b6 held last frame, b1-0 sweep phase
    (0..3 → M0 offsets 0/8/16/8 px). Updated by `LaserInput` — a post-pad
    leaf (`jsr` from overscan after bomb input, like AddScore/UpdateBombSound
    because pre-pad headroom was only 7 bytes). A+X only; Temp/joystick
    untouched; no TIA writes — M0 stays disabled (kernel still zeros ENAM0).
- [x] Build and run `verify_build.py` — green: banks 4×4096, fold pads
      byte-identical, Overscan still `$F169` (bank1 jmp sync), ToMenuStub
      `$FC68`/ToGameStub `$FC70`, LaserInput `$FE9D`, pre-pad ends `$FC64`
      (4 bytes free, WARN). **Note for S2:** pre-pad has only 4 bytes left —
      VBLANK M0 setup + kernel `.Line` edits will need more leaf relocations
      past the fold pads first.
- [ ] **User validation:** with laser still disabled, check player wall collision, snake movement, bombs, and frame stability remain unchanged. Confirm fire press/release state through Stella debugger if available.
  - Debugger: `breakLabel $F1C0` (the `jsr LaserInput`), watch `$C0`:
    idle `$00`; press frame `$81`; holding cycles `$C2,$C3,$C0,$C1,…`;
    release frame `$40` → `$00` next frame.
- [x] Stop and ask user before S2.

### S1 addendum — regression found in user test & fixed (2026-09-26)

**Symptom (screenshots/laser_issues.png):** spider jumped from right side to the
left edge inside a wall; player visual collision shifted right ~tiles; thin
wall visually passable.

**Root cause (from my diff only):** the `jsr LaserInput` (+3 pre-pad bytes)
pushed `SetObjectXPos` from `$F8F7` to `$F8FA`, moving `bcs .Div15Loop`
($F8FC → $F8FF) across the $F8/$F9 page: next-PC `$F901` vs target `$F8FD`
= branch page-cross → **4c instead of 3c = 6c per /15 iteration (contract:
5c)**. RESP0 then fired 3 color-clocks late per 15-px coarse step → every
sprite drifted right ≈ 3×(X/15) px (player ≈ +3 tiles → looked like broken
collision / thin-wall pass-through), and the right-side spider (X≈140)
overflowed the 160-px window and its position counter wrapped → drawn at the
left edge. Kernel `.Line` budgets were unaffected (verified PlayerSpriteA/B
` (zp),Y`, PlayerColTable `abs,Y`, ObjSprites `abs,X` page math unchanged).

**Checked prior-session hypothesis (CollisionCellX → ActiveObjectX):** not
applicable — my diff reads/writes only `$0C` (INPT4) and `$C0` (LaserState);
no CollisionCellX/ActiveObjectX involvement (git diff kernel.asm).

**Fix:** relocated `SetObjectXPos` (byte-identical, address-only) into the
unused `$FF10-$FF1F` gap between the fineAdjust table and `org $FF20` —
entirely inside one page, so the 5c contract is structurally safe.
`.Div15Loop=$FF12`, `bcs=$FF14` → same page → 3c ✓. Also freed pre-pad
headroom 4 → 20 bytes.

**Guards added to verify_build.py (fail the build):**
1. `bcs .Div15Loop` must share a page with `.Div15Loop` (5c contract).
2. `.Div15Loop` must sit in `$FF12-$FF1B` (the $FF10-$FF1F gap).
3. `ObjSprites+71` must stay in-page (kernel `lda ObjSprites,X` = 4c).

**Lesson (added to my workflow):** inserting ANY code before a cycle-tuned
routine can flip a branch's page — always re-check page contracts from
`bank0.lst` after size changes; verify_build now enforces the two critical ones.

- [x] **User re-validation (2026-09-26): CONFIRMED WORKING** — spider renders
      on the right side again; player stops at walls/thin wall correctly;
      fire state updates at `$C0`. Root cause + guards recorded in
      `AGENTS.md` → Lessons Learned ("Branch page-cross in a cycle-tuned loop").

### S2 — Static M0 pulse at eye row (split into S2.1/S2.2/S2.3)

#### S2.1 — M0 at RoomX, width 8, fire-gated, FULL HEIGHT ✅ (user-validated 2026-09-26)

- [x] Position M0 via `SetObjectXPos` selector 2 (`sta RESP0,X`→`RESM0`,
      `sta HMP0,X`→`HMM0` with X=2). Logic lives in `LaserInput` (post-pad,
      now relocated past `org $FF20` after `SetObjReflection` — the pre-$FF00
      region is 100% full, ObjSprites + zero pad), called every overscan:
      RESP/HMP set during overscan persist into the next frame; VBLANK's
      single `sta HMOVE` applies the fine offset.
- [x] Missile width 8: kernel entry `lda #$00→#$30` for NUSIZ0 (bits4-5 =
      M0 width, copy bits0-2 stay 0 = single-copy P0). Restored every frame
      (bank1 HUD NUSIZ0 writes undone by kernel entry).
- [x] Fire gating: `LaserInput` beam section — held → position + `ENAM0=2`;
      released → `ENAM0=0`. Kernel entry **no longer clears ENAM0**
      (`sta ENAM0` removed — LaserInput owns it every overscan).
- [x] **Zero `.Line` edits, zero pre-pad size change for the laser logic**
      (call site unchanged at 3 bytes). Kernel entry −3 bytes (`sta ENAM0`
      removed) → `Overscan` `$F169→$F167`, bank1 `jmp $F167` synced.
- [x] Build + `verify_build.py` green: 4×4096, fold pads byte-identical,
      pre-pad ends `$FC52` (22 bytes free, WARN), guards pass. Page contracts
      re-checked from `bank0.lst`: `.Line` branches all $F1xx, `.Div15Loop`
      $FF12/bcs $FF14 same page, `ObjSprites=$FE9D` (+71=$FEE2 in-page),
      `PlayerColTable` fetch cross unchanged, `LaserInput=$FF33` (<$FFFA).
- [x] **User validation (2026-09-26): CONFIRMED WORKING** — "Tests all pass,
      even your forecast of some HUD flicker" (HUD flicker = expected at S2.1,
      fixed by S2.2's BeamMask ownership).
- [x] S2.1 complete → S2.2.

#### S2.2 — Restrict beam to 2 scanlines at RoomY+2 (risky `.Line` edit) ✅ (code) / gate pending

- [x] `ObjTop` now stores RoomY-relative value in `.SODone`
      (`ActiveObjectY - RoomY + 1`); `ActiveObjectY` itself unchanged
      (`CheckEnemyHit` reads real scanline coords). `ObjBot` write-only/dead.
- [x] `.Line` object section: `lda Scanline/sec/sbc/bcc` replaced by
      `tya/sec/sbc ObjTop/cmp #PLAYER_HEIGHT/bcs .ObjZero` — Y at `.Grp1`
      = A0+1, so `Y - ObjTopRel` = `Scanline - ObjTop` exactly (mod 256;
      negatives ≥ 8 → `.ObjZero`; C=0 in range → `adc ObjBase` exact).
      `inc Scanline` and init `sta Scanline` removed — **`Scanline` is dead**
      (ZP byte $82 kept, never removed from middle of sequential map).
- [x] Beam enable in `.Line` color path (in-window only, Y = A0):
      `lda BeamMask,Y / sta ENAM0`; `BeamMask` = 12 bytes
      `{0,0,2,2,0,0,0,0,0,0,0,0}` (ON at A0=2,3 = RoomY+2..3), placed at
      `$FF5B` (post-pad `$FF20` region). Outside window ENAM0 keeps last
      in-window write ($00 at A0=11) → no HUD artifact (S2.1 flicker gone).
      `LaserInput` no longer writes ENAM0 (positioning only).
- [x] Full worst-path cycle recount from `bank0.lst`: color+beam+GRP0 = 34c,
      object in-range = 24c → **worst 58c → WSYNC at c66, write c68 ≤ c73
      (5c margin)**; obj-above path write c64; outside-window write c52.
      All `.Line` branches same-page $F1 (`.GrpSkip` $F11D, `.GrpZero` $F148,
      `.ObjZero` $F14F, `bne .Line` $F13A→$F10F).
- [x] **New verify_build guards** (negative-tested, fire on violation):
      (3) every relative branch in `.Line..bne .Line` must share a page with
      its target; (4) `lda BeamMask,Y` operand must be `$FFxx` (5c cross
      budgeted).
- [x] Build green: 4×4096, fold pads byte-identical (`Overscan` `$F167→$F165`,
      bank1 `jmp $F165` synced), pre-pad ends `$FC56` (18 bytes free, WARN).
- [ ] **User validation round 1 (2026-09-26): items 2-4 PASS; item 1 FAIL —**
      bar visible at boot without fire (replicated 4×, blinking), inside
      player rather than in front, follows player Y, slides across whole
      screen after release.
      - "inside player" → **S2.3 by design** (eye + facing), not a bug.
      - "follows player Y" → **by design** (beam at RoomY+2 = eye row).
      - **S2.2r2 fixes (root causes):** (a) `.Line` BeamMask wrote ENAM0
        unconditionally — added `and LaserBeamOn` gate ($83, reuses dead
        Scanline byte; `LaserInput` sets $02 held / $00 released; boots $00
        → invisible until first press); (b) release kept stale `HMM0` fine
        offset → VBLANK HMOVE slid M0 every frame — `LaserInput` released
        path now `sta HMM0`=0. Recount: color+beam+GRP0 37c + object 24c
        = worst 61c → WSYNC write **c71 ≤ c73** (2c margin); `Overscan`
        `$F165→$F167` (and zp +2 bytes), bank1 jmp re-synced; pre-pad
        ends `$FC58` (16 bytes free).
- [x] **User validation round 2 (2026-09-26): ALL PASS** (clean before
      first press, single bar at player, gone+stationary after release,
      items 2-4 held). Committed `1b1d11c`.
- [x] S2.2 complete → S2.3.

#### S2.3 — Fine X: eye pixel + facing sign ✅ (code) / gate pending

- [x] Eye column derived from sprite art (unreflected = facing right, REFP0=0):
      yellow face rows 2-3 = cols 1-4, front/eye = **col 4**; REFP0 mirror
      (facing left) → front col 3, bar extends left 7 px → left edge = eye-7.
      M0 X: right = `RoomX+4` (spans +4..+11), left = `RoomX-4` (spans
      -4..+3, right edge at eye). Sprite visual left = `RoomX` both dirs
      (P0 arg `RoomX-PlayerDir` + REFP0 1-px compensation; collision uses
      `[RoomX, RoomX+6]`).
- [x] No clamps needed: `RoomX` ∈ [`PLAYER_MIN_X`=4, `PLAYER_MAX_X`=159] →
      args ∈ [0,163]; SetObjectXPos div15 remainder always −15..−1 ✓.
      Lives entirely in post-`$FF20` LaserInput — pre-pad/Overscan/folds
      untouched (`Overscan` stays `$F167`).
- [ ] **Full S2 user gate:** yellow 8×2 pulse BEGINS AT THE EYE and extends
      forward (right when facing right, left when facing left); Y matches
      yellow face row (RoomY+2..3); nothing before first press; P1
      enemies/snake visible; no frame roll; wall collision/bombs/map
      unchanged; beam gone on release.
- [ ] STOP → user validates before S3 (8 px/frame sweep).

### S3 — Fast back-and-forth sweep

- [ ] While held, move M0 through positions 0, 8, 16 pixels ahead of eye, then back; repeat. Use facing direction to choose horizontal sign.
- [ ] Disable M0 immediately on fire release. Keep M1, ball, and P1 out of laser rendering.
- [ ] Build and run `verify_build.py`.
- [ ] **User validation:** test both facing directions in Stella with phosphor/trail enabled. Check visible sweep spans about 24 pixels, tracks eye row, stops on release, leaves enemies/snake visible, and does not disturb wall collision or frame timing.
- [ ] Stop and ask user before S4.

### S4 — Swept enemy collision and score

- [ ] Test enemy vertical overlap against the two laser scanlines and horizontal overlap against the full swept interval, including missile width. Handle screen-edge clipping.
- [ ] Replace the single `DeadEnemyIdx` kill slot with per-enemy persistent dead state; all draw, movement, player-hit, and bomb-hit paths must skip laser-killed enemies so later shots cannot revive earlier kills.
- [ ] Call existing `AddScore` with `#$50` exactly once per removed enemy.
- [ ] Add assert-based checks for sweep interval / enemy overlap and dead-state behavior.
- [ ] Build and run `verify_build.py`.
- [ ] **User validation:** hit enemies at both ends and between sweep positions; verify each removed once, +50 per hit, no resurrection after another hit, no lamp side effects, P1/snake continue rendering, and no frame roll.
- [ ] Stop and ask user before S5.

### S5 — Final regression

- [ ] Rebuild editor and ROM; check bank sizes, fold pads, level generation, and zero-page notes.
- [ ] **User validation:** full Stella pass: both directions, wall contact, snake/object visibility, fire release, repeated shots, score, room transitions, and bombs.
- [ ] Mark complete only after user confirms.
