# Laser Implementation Plan

Status: **S1 implemented; build.sh + verify_build green — awaiting user Stella validation before S2.**

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

- [ ] **User re-validation:** spider back on the right side; player stops at
      walls/thin wall visually correct in both directions; frame stable;
      fire state still updates at `$C0`.

### S2 — Static M0 pulse at eye row

- [ ] Position M0 from player eye using `SetObjectXPos` selector 2 (`RESM0/HMM0`); set missile width to 8 using NUSIZ0 missile-width bits only.
- [ ] Enable M0 for exactly two scanlines at `RoomY+2`; keep P1 object selection and enemy drawing unchanged.
- [ ] Verify VBLANK/scanline timing; account for `SetObjectXPos` WSYNC cost.
- [ ] Build and run `verify_build.py`.
- [ ] **User validation:** press fire once. Check yellow 8×2 pulse begins at eye, Y matches yellow face row, P1 enemies remain visible, and frame does not roll.
- [ ] Stop and ask user before S3.

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
