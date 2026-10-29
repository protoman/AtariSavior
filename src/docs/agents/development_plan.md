# Development plan (phases 1-10)

_Checklist of what is built and what is not._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

## Development Plan

### Phase 1: Basic Rendering ✅
- [x] VSYNC/VBLANK/Overscan frame timing
- [x] Kernel: 4 bands × 36 scanlines + 48 HUD band (originally 12×12; cut
      to 3×48 on 2026-09-28, then to 4×36 on 2026-10-23 — `TILE_ROWS=4`,
      `LINES_PER_TILE=36`, `CAVE_LINES=144`)
- [x] Cave playfield with reflected mode (CTRLPF D0=1)
- [x] Player sprite (GRP0) — 8×12, per-row colors, 2-frame jet animation, REFP0 mirror
- [x] Joystick movement (up/down/left/right)
- [x] Fix cave shape — room .txt maps + convert_room (per-room walls, not bars)
- [x] Proper wall collision bounds (rect walk — see Phase 3)

### Phase 2: Player Sprite & Positioning
- [x] Horizontal positioning via RESP0/HMP0 (Andrew Davie algorithm;
      SetObjectXPos pinned to the $FF10 gap + page-cross guards)
- [x] Player sprite art (jet animation, 2 frames)
- [x] Smooth movement with proper pixel bounds (PLAYER_MIN/MAX_X clamps)
- [x] Collision box matching visual sprite (PlayerHitsMap cell range)

### Phase 3: Collision Detection
- [x] Player-to-playfield collision — implemented as the **PF cell walk**
      (PlayerHitsMap), NOT TIA CXP0FB: the PF buffers ARE the collision map
      (plan C4 2026-10-20 — the solid rect lists and the ZP rect cache are
      retired; only hot records stay as a data stream)
- [x] Wall collision prevention (don't walk through walls)
- [x] Room boundary checks (don't leave room edges — exit handlers)
- [x] Collision response (stop + hot-rock bump)

### Phase 4: Room System
- [x] Room data format (rooms/*.txt → convert_level → PF + hot stream in ROM)
- [x] Room connections (up/down/left/right exits — LevelConn*)
- [x] Room transitions (load new room on exit — EnterRoom)
- [x] Multiple rooms per level (2 levels, LEVEL_COUNT guarded)
- [x] Room-specific enemy placement (JSON enemies + editor 3-slot cap)

### Phase 5: Enemies (GRP1)
- [x] Enemy sprite rendering (GRP1, ObjSprites bank0)
- [x] Enemy positioning (RESP1/HMP1 via SetObjectXPos selector 1)
- [x] Basic enemy AI (patrol/chase — moth walk, tentacle probe, derives)
- [x] Enemy-player collision (CheckEnemyHit)
- [x] Multiple enemy types (moth/spider/tentacle/bat/snake/lamp/miner/raft)

### Phase 6: HUD Display
**HERO's HUD per disassembly (corrected — see the "read the FULL section"
rule at the top):** NUSIZ copies for icon rows (`LFF3E = $30,$30,$20,$20`
= lives/bombs), 13+2 (P0×3 + P1×3 + ball) for TEXT rows. An earlier
version of this section claimed HERO used 13+2 for *everything* — that
was the disproven claim.
- [x] Score display (6 digits — bank1, 48px technique: NUSIZ×3 P0/P1 +
      VDELP cross-buffer, `docs/font/48px_score_skill.md`)
- [x] Lives display (bank1 "Line 2", NUSIZ icons)
- [x] Bombs display (bank1 "Line 3", red squares, count = PlayerBombs)
- [x] Timer bar (power bar, bank1 — BarDelay/BarFine/BallX tables)
- [x] Level indicator
- [x] HUD rendering in the 48-line band (bank1 via the $FC68 fold pad)

**Score rendering notes (from HERO disassembly + bumbershootsoft):**

**HERO's actual architecture (follow this):**
- HERO uses **per-scanline PF lookup tables** — NOT a font array + runtime computation
- Each scanline gets its own complete PF0/PF1/PF2 value from ROM tables (LFA00/LFB00/LFC00/LFD00)
- Font data is **baked directly into the PF register values** — there is no separate PFDigitFont
- The score kernel loads ONE source byte per scanline, then ANDs it with per-scanline masks ($BF for PF1, $C2 for PF2) to extract each PF register's portion
- Masks vary per scanline because different rows need different bits masked off
- This eliminates serialization overhead — each scanline's PF values are loaded directly from ROM
- The PF values encode both the digit shape AND the pixel positioning in the PF register bit layout
- Score is 4 scanlines tall (not 5), using 2-pixel-wide digits (not 3)
- The key trick: one source byte encodes PF0 raw, PF1 via AND mask, PF2 via AND mask — saves ROM space and simplifies the kernel

**Why this matters:** HERO's digits look small because the PF lookup tables pre-compute the exact pixel pattern for every scanline. Our approach of computing PF values at runtime from a font array introduces overhead and makes digits wider. To match HERO's look, we should use the same PF-table approach.

**What we currently use (48px sprite score, `docs/font/48px_score_skill.md`):**
- Score is rendered by **bank1** in the HUD band: NUSIZ0/1 = 3 (P0×3 +
  P1×3 = 6 digit slots), VDELP0/1 cross-buffer pipeline
- `scorePtr1-6` ($E0-$EB) → `DigitGfx` ROM font at $FD00, read
  `lda (scorePtrN),Y` per scanline
- The old bumbershootsoft PF-compute approach (CTRLPF SCORE mode +
  `PFDigitFont` + runtime PF values) is **gone** — no `PFDigitFont`
  reference survives anywhere
- HERO's per-scanline PF-table trick (bullets above) remains the
  aspirational reference for pixel-small digits

### Phase 7: Gameplay
- [x] Laser/weapon system (missile 0) — LaserInput/ENAM0/BeamMask/LaserHitTest
- [x] Bomb system (bomb sprite + fuse timer, NOT the ball — BombPacked state machine)
- [x] Wall destruction (BombMarkWalls cell punch: a thin wall = one solid
      D7 cell whose neighbours are empty; the PF buffer is the double-score
      guard — WallMask/ApplyBombWalls retired by C4)
- [x] Item collection (CheckMinerPickup → next level)
- [x] Level progression (inc Level, wraps at LEVEL_COUNT)

### Phase 8: Jetpack Physics
- [x] Gravity (constant downward force — vyLo/vyHi integration)
- [x] Thrust (upward force when button held — JetPower; **HERO feel 2026-10-22**: while
      FALLING a held jet jumps straight to JET_MAX ($30) and stops a terminal
      1.5 px/frame fall in ~10 frames; from rest / while rising it still ramps
      +1/frame so take-off eases in. The old `EnemyRamP & 3` gate + JET_MAX=$14
      needed ~80 frames to beat gravity = a room height of extra falling, bugs #31
      superseded — do not re-add the ÷4 gate to the falling case.)
      **The velocity clamp must compare the low byte** when `vyHi == >MAX_FALL`
      (2026-10-22): the old high-byte-only `cmp` rewrote every speed in
      `$0100..$017F` to exactly `$0180`, so thrust was computed and thrown away
      every frame and no jet could slow a fall. Guard: `tools/test_jet_clamp.py`
      (ROM-level — model-based tests use a proper `>` compare and cannot see it).
- [x] Inertia (momentum — subpixel accumulator PlayerYSub)
- [x] Vertical collision with ceiling (StepUp stops flush)

### Phase 9: Polish
- [x] Sound effects (engine buzz, bomb drop/explode, laser — test_laser_sound.py)
- [x] Color schemes per level (LevelWallColor/LevelWallColor2 from level data)
- [x] Title screen (level select: DROP-IN sentinel, SELECT/RESET console switches)
- [x] Extra life every 50,000 points, max 8 lives, score to 999,999 (2026-10-27)

### Phase 10: Levels & Content
- [x] 20 generated levels (`Build20LevelStage`), enemy speed x1..x2.5 every 5 levels

### Remaining for 1.0 (user ruling 2026-10-27)
Music, screen transitions, game over screen, difficulty settings, bosses,
secret rooms and level-specific enemy patterns are CUT from scope.
- [x] SaveKey support (Atari 2600 save-key / AtariVox EEPROM): save the game
      and the high score. DONE 2026-10-28 (docs/savekey_design.md; verified in Stella
      by the user). Original note: Needs a design pass first (I2C bit-bang on SWCHA,
      ROM/zero-page budget in bank1, test with a py65 EEPROM model).

- [x] Playthrough bot for the generated stage (tools/playbot.py, 2026-10-28): all 20
      levels finish on the real ROM; see docs/agents/testing_and_build.md.
- [x] Horizontal-position test for the lives row and the key ball
      (tools/test_hud_positions.py, 2026-10-28): a beam model fitted on the real
      SetObjectXPos measures the lit pixel columns; squares of 4 px on an 8-px pitch
      from x=8 (P1 from x=40), key ball at x=125..132, every GRP/ENABL write before
      the beam. Red-proofed by moving P1 and the ball one pixel.
