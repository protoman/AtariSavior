# Bank0 Space Optimization — Findings

Status: living document. Section 1 = measured findings (2026-09-30).
Section 2 = Q&A — each question's findings/answer appended here as asked.

## 1. How bank0 filled up (measured)

**Question (user):** we refactored to move level data out of bank0 — how is it
still almost 4K? Was it just the cost of handling data in another bank?

### Method

- Snapshots assembled in `/tmp/opencode` via `git archive <commit>` + bare
  `dasm kernel.asm -f3` (generated level files are tracked → old trees build).
- "Used" = sum of byte-columns in `bank0.lst`. Caveats found:
  - raw `bank0.bin` size is useless: vectors at $FFFA force 4096 always.
  - DASM truncates byte display on huge `.ds` lines (`00 00 00 00*`) — only
    padding truncates, so the count ≈ used code+data, free space not counted.
- `bank0_base.bin/.lst` (project root, Sep 14) = **old prototype**, NOT this
  kernel (different label vocabulary: Main/LoopVBlank/UpdateP0Vertical vs
  current Overscan/StepDown). Current `kernel.asm` history starts 2026-09-16.

### Timeline (bank0 used bytes)

| date | snapshot | bank0 used | Δ |
|---|---|---|---|
| Sep 21 | rooms system (`a8b1069`) | 891 | — |
| Sep 23 18:26 | enemies S1 (`34360c6`) | 1989 | +1098 |
| Sep 23 22:08 | bombs S0–S7 (`336be3c`) | 2511 | +522 |
| Sep 24 | score 48px + rewards (`e08b385`) | 3307 | +796 |
| Sep 26 | laser S1 (`0ebd985`) | 3474 | +167 |
| Sep 27 | pre-move (`52664de`) | 3800 | +326 |
| **Sep 27 21:43** | **level data → bank2 (`542acc5`)** | **3712** | **−88** |
| Sep 30 | now (HEAD) | 3904 | +192 |

### Findings

1. **The +1784 B growth happened BEFORE the data move.** Enemies (+1098),
   bombs (+522), score (+796), laser (+167), rooms/tentacle/water (+326+)
   all landed while level data still sat in bank0. Bank0 was near-full —
   that's *why* the move happened.
2. **The move itself nearly balanced to zero:**
   - removed ≈ 350 B: `M0–M3 RoomRects/TilePF0/1/2`, `LEVEL1/2_RoomDataTable`,
     `RoomConnections`, `EnemyDataTable`, `RoomEnemies`, `LevelDataTable`
   - added ≈ 260 B: fold routing (staging + fold calls + pads)
   - **net −88 B** → ~76% of the data savings was immediately consumed by
     the machinery that handles data living in another bank. (User's
     intuition correct for the move operation itself.)
3. **After the move: +192 B** — rect-cache walk (P3.4/P3.6), bomb flicker
   fixes, moth dispatch/tramp. Not "major", but the 25 B gap was the last
   usable slack; E4's `MothYDerive` leaf consumes it exactly.
4. **Cross-bank machinery total today ≈ 180 B** (4.5% of the bank):
   - 18 stage points × 8 B (`lda/sta FetchPtr` pair) = 144 B
   - `FoldIndirect` routine = 9 B
   - byte-identical pads/tramps = 28 B (ToMenuStub 8 + ToGameStub 8 +
     MothExitPad 6 + UE_MothTramp 6)
   - 60 × `jsr FoldIndirect` = byte-neutral (each replaces a 3 B local read)
5. The other ~95% of fullness is plain game code: 6502 logic doesn't compress;
   every system costs hundreds of bytes of unrolled code + tables.

### Current free-space map (bank0, Sep 30)

| region | status |
|---|---|
| main before `.ds $FC49` pin | **0 B slack** (MothExitPad pinned; growth = build error) |
| `$FC4F–$FC67` gap | **25 B** — only usable gap; E4 leaf goes here (25 B exact) |
| `$FC68`/`$FC70` fold pads | fixed (bank1-synced, cannot move) |
| post-pad `$FC78–$FEEF` | contiguous full |
| `$FEF0` tramp, `$FEF6` FoldIndirect, `$FF00` fineAdjust, `$FF10` SetObjectXPos, `$FF20–$FFF1` laser | fixed/pinned, full |
| `$FFF2–$FFF9` | reserved (F6 hotspot mirror zone — no fetched byte ever) |
| bank1 | HUD (in-frame tramp) |
| bank2 | level data + moth routine |
| **bank3** | **empty (~4 K)** — power-up stub only; pressure valve |

### Where next space comes from

1. **bank3 leaf relocation** — proven pattern: bank2-style tramp pair
   (`sta $1FF9` / byte-identical pad / `sta $1FF6`), `jsr`-safe leaves only.
   ~4 K available.
2. Table floor-nesting compression (freed 144 B once: `YToRowTable`
   192 B → 48 B reindexed by `A>>2`, `floor(floor(A/4)/12)==floor(A/48)`).
3. Shared probe helper extraction (`UE_ProbeStep`: tentacle+moth swap+PHM
   dedup ≈ 40 B) — only if both stay bank0.
4. Main-side refactors already banked into E4: `LoadEnemyRAM` X×6 →
   `ldy EnemyOffTable,X` (−6 B), `RefreshEnemyY` countdown loop (−3/−4 B).

## 2. Q&A

### Q1 (2026-09-30): HERO fits a more complex game in 2×4K. Is it code
### optimization, or are we doing things in a much more complex way?

**Scope:** bank0 code vs HERO's code. (Level data size is not the point —
HERO bakes its cave into tables, ours is generated, both are "data".)

#### Method + a trap

- HERO sources: `docs/hero/hero_bank1.asm` (DiStella of $F000 half, parses
  cleanly) and `/tmp/opencode/hero_bankA_flow.asm` (execution-flow sweep of
  the $D000 half — 1440 instructions).
- **TRAP: `docs/hero/hero_bank0.asm` (DiStella of the $D000 half) MISPARSES
  the kernel region as data after $D02A** (documented in
  `hero_asymmetric_rooms.md:74`). Any HERO code-size taken from that file is
  wrong — a first pass of this analysis read "HERO total code = 1779 B" from
  it and is hereby retracted. The $D000 half alone executes ~2771 B of code.
- Per-half sizes from assembled `h0.bin`/`h1.bin` (both build clean, 4096 B
  each); classification = code bytes from byte columns, data = `$xx` operand
  count on `.byte` lines (byte columns truncate at `*`).

#### Measured

| | code | data | total |
|---|---|---|---|
| HERO half A ($D000: main loop, kernel, HUD renderer, VSYNC/timing) | ≈2771 | ≈1325 | 4096 |
| HERO half B ($F000: game logic + tables: score PF $FA00-$FD00, NUSIZ/pos/sprite) | 1731 | 2365 | 4096 |
| **HERO whole game** | **≈4500** | **≈3700** | **8192** |
| OURS bank0 (kernel + all overscan logic) | ≈3815 | ≈150–300 | ≈3950 |
| OURS bank1 (HUD) | 890 | 98 | 988 |
| OURS bank2 (moth/tramp code + level data) | 69 | ≈300 | — |
| OURS bank3 | — | — | **empty** |
| **OURS whole game** | **≈4770** | **≈550** | **≈5320 / 16384** |

Landmarks (HERO, from `hero_asymmetric_rooms.md`): $D079 main, $D100
kernel entry, $D12C row loop, $D17A line loop, $D6F2 VSYNC+TIM64T, $D9DF
frame end → `JMP $DFF2` thunk, $DC00 HUD renderer (`JSR $DC00` from
half B), $DC6A cave PF tables.

#### Answer

**Not instruction-level fat — our code is not wasteful per byte. It is
architecture + distribution.** Four findings:

1. **Corrected comparison: we are at PARITY, not 2×.** Our whole-game code
   ≈4770 vs HERO ≈4500 (+6%). Our bank0 alone (3815) ≈ 85% of HERO's *entire*
   code. The "2.1×" reading was an artifact of the misparsed $D000 half.

2. **HERO and we have inverted center of gravity.** HERO spends
   ~2771 B on the *kernel side* (per-scanline double PF writes for asymmetric
   halves, HUD sprite renderer, timing) and only ~1731 B on game logic.
   We do the opposite: kernel+VBLANK ≈379 B (write PF once per row — the
   cheap way, as designed), logic ≈3400 B. HERO renders precision from
   **tables**; we compute **systems** at runtime.

3. **Where our extra logic goes (bank0 spans from label map):**

   | system | ≈bytes | HERO equivalent |
   |---|---|---|
   | room system: EnterRoom 328 (incl. LoadEnemyRAM 95) + exits 92 + LoadLevel 146 + LoadPF 90 + band/dark/bottom ≈150 | **≈700** | fixed baked cave — no connection/transition machinery found; level = tables |
   | enemies: UpdateEnemies 219 + UE_Tentacle 173 + DeriveEnemyY 90 + SelectActiveObject 202 + CEH 135 + LoadEnemyRAM (above) | **≈650** | fewer/simpler types; flicker exists but selection simpler; motion simpler tables |
   | bombs: BombTick→ApplyBombWalls + sounds | **≈420** | HERO has bombs too (5, blast walls) — ours adds WallMask system, blink colors, dual sound, per-room mask |
   | collision: PlayerHitsMap 236 + HotOverlapFlag 111 | **≈350** | method not verified in HERO (needs disasm proof before claiming TIA regs) |
   | laser: LaserInput→LaserHitTest | ≈173 | comparable (hero shoots) |
   | runtime color/PF compute: BuildColupF 149 + LoadPF 90 + ClearPFColumn 49 | **≈290** | baked into per-scanline tables ($DC6A gradients) |
   | F6 banking tax: staging 144 + FoldIndirect 9 + pads/tramps 34 (Section 1) | **≈190** | **flat 8K — both halves visible, `JSR $DC00` direct, zero machinery** |
   | sound: jet 45 + bomb 47 | ≈90 | comparable |

4. **Distribution is the bank0 overflow, not total size.** HERO spreads
   kernel across half A and logic across half B. We put kernel + ALL logic
   in bank0; bank1 only does HUD (890), bank2 is ~data, **bank3 is empty
   (4 K)**. We are out of bank0 while 4 K of our own ROM sits unused.

#### Which ones to simplify (ranked, realistic relief)

| action | bank0 relief | risk |
|---|---|---|
| move runtime compute → tables in bank2/3 (room colors, bottom colors, band — HERO's way) | −150…−250 | low (data, not behavior) |
| relocate leaf helpers to bank3 via proven bank2-style tramp (AddScore, ReloadLevel, sounds, IsRoomDark…) | −100…−200 | low (leaves only) |
| enemy compaction: dedupe snake left/right, shared probe helper, table-driven dispatch | −80…−150 | medium (kernel-adjacent) |
| review SelectActiveObject (202) + CEH (135) for shared loops | −50…−100 | medium |
| **realistic total** | **−350…−600** | |

**Do NOT:** delete the room system (it is the game's design, and HERO
"not having it" is not an optimization we can copy); chase instruction
micro-opts (kernel/logic already tight — fixed-time loops, no redundant
loads); touch the rect collision without a full misalignment plan
(2026-09-21 lesson); expect F6 tax to disappear (16K is required for
editor levels — 190 B is the price).

**Bottom line (Q1):** HERO is not "more optimized" — it is *more static*.
It converts everything it can into ROM tables and keeps a fixed layout; we
chose dynamic rooms + 5 enemy types + F6 banking, and pay with logic bytes.
Our total code already ≈ HERO's total code; the fix for bank0 is (a) push
compute into tables where HERO has tables, and (b) use the empty bank3.

### Q2 (2026-09-30): How much free space in bank1 (HUD)?

**≈2819 B of 4096 = 69% free.** Measured from `bank1.bin` fills (lst byte
columns truncate on `.byte` dumps — do NOT count from lst; `FF` = DASM
org-gap fill, `00` = `.ds` pad, both = free):

| region | size | fill | origin |
|---|---|---|---|
| $F003–$F53F | 1341 | FF | org gap after entry stub `jmp $F008` ($F000–$F002) |
| $F9C0–$FC67 | 680 | 00 | `.ds $FC68-*,0` pad; HUD content ends $F9BF |
| $FC78–$FCFF | 136 | FF | org gap before font |
| $FD50–$FEFF | 432 | FF | org gap after DigitGfx ($FD00, 80 B) |
| $FF10–$FFF5 | 230 | 00 | pad to vectors; **$FFF6–$FFF9 reserved** (F6 mirror) |
| **total free** | **2819** | | |

Used ≈1277 B: entry stub 3 + MenuMain/HUD $F540–$F9BF (1152: power bar,
score, lives; tramp stubs $FC68/$FC70 FIXED by bank0 contract) + DigitGfx 80
+ fineAdjust $FF00 16 + vectors 6.

Placement constraints for future content:
- $F003–$F53F = biggest contiguous chunk, no alignment constraints
- $FD50–$FEFF shares font page — safe while DigitGfx pointer stays $FD00
- fineAdjust at $FF00 must not move (positioning math); $FF10+ OK
- keep entry stub $F000, tramp stubs $FC68/$FC70, vectors, $FFF6–$FFF9

**Verdict:** bank1 can absorb ≈2.8 K of relocated tables/code — plenty for
the "spread data between banks" direction. Note: HUD-related data
(DigitGfx, fineAdjust) already lives here; bank1 executes only during the
HUD band via tramp, so relocated content must be reachable from bank1 code
or be passive data read from bank0/bank1 contexts.

### Q3 (2026-09-30): What can move bank0 → bank1 (data preferred, HUD
### first)? Is a jump to bank1 as costly as the level folds?

#### HUD-first audit (bombs, lives, power timer, score)

| item | where it lives now | move needed? |
|---|---|---|
| state: PlayerLives $AC, PlayerBombs $F0, BarLevel $AE, TickCounter $AD, ScoreTh/Hu/Te $F3-$F5 | ZP RAM — shared by ALL banks, written bank0, read bank1 (and vice versa) | **no — RAM moves are free, already shared** |
| power bar draw + BarDelayTable/BarFineTable/BallXTable (121×3 = 363 B) | bank1 | already there |
| score glyphs DigitGfx (80 B, 8×8, page-aligned $FD00) | bank1 | already there |
| HUD icon rendering (lives/bombs NUSIZ logic) | bank1 code | already there |
| **dead old PF score system in bank0: ScoreFontPF0/1/2 (15 B) + PFDigitFont (50 B) + DigitTimes5 (10 B)** | bank0 $FAB1–$FAFB | **delete — zero readers project-wide** |

Dead-block proof: `grep -rn "ScoreFontPF\|PFDigitFont\|DigitTimes5"
--include=*.asm` → ONLY the 5 definition lines in kernel.asm. The source
comment self-documents it: *"PF-based, temporary — Will be replaced by
8×8 sprite font when 48-pixel technique is implemented"* — implemented
(48px skill doc; git `bb97c3e 2026-09-18 Revert: hardcoded score buffers
in bank1, remove bank0 pre-comp`). Orphaned then. Also 3 dead ZP decls:
`PF0ScoreBuf $B3`, `PF1ScoreBuf $B8`, `PF2ScoreBuf $C6` (zero code users;
comment says bank1 owns its own $B3/$C6 bufs). **Net if deleted: −75 B
bank0, 0 cost, no folds, no jumps.**

**STATUS 2026-09-30: DELETED.** Block removed from kernel.asm; build green
(4×4096, verify_build incl. ObjSprites-page + Div15Loop guards, sim_bomb_fuse,
test_enemy_movement, test_level_bank all pass). Label shift verified exactly
−75: `RefreshEnemyY` $FC37→$FBEC, `PlayerHitsMap` $FB34→$FAE9.
Pre-pad slack before the `MothExitPad` pin grew by 75 B (the 25 B gap
$FC4F–$FC67 after the pin is unchanged — still E4's). ZP decls left in
place (zero cost, pre-existing).

#### Why most bank0 data CANNOT go to bank1 (regardless of cost)

| data | size | reader context | verdict |
|---|---|---|---|
| ObjSprites | 73 | cave kernel, `lda ObjSprites,X` per scanline (bank0 context) | **pinned** |
| PlayerSpriteA/B + PlayerColTable | ~36 | cave kernel per scanline (`PlayerColTable,Y` has a page-cross guard, AGENTS) | **pinned** |
| fineAdjust | 15 | $FF00 page + positioning math, both banks keep own copy | **pinned/duplicated** |
| laser beam tables | 16 | laser logic (overscan) | movable (fold) |

A fold read costs ~19 c (`sta hotspot` 4 + `lda (zp),Y` 5 + `sta hotspot`
4 + rts 6). Kernel lines run with ~10 c margin in a 76 c budget →
**per-scanline folds are physically impossible, not just costly.**
Overscan/VBLANK phases have hundreds of spare cycles → folds fine there.

#### Cost model — "like the levels?"

The level folds were expensive for a specific structural reason, not
because bank switching itself is costly:

| pattern | mechanism | cost | notes |
|---|---|---|---|
| **level folds (what we fear)** | 60 read sites share ONE `FetchPtr` → 18 staging points × 8 B = 144 B + FoldIndirect 9 B + pads ≈ **190 B** | staging *discipline* + alias bugs (PHM restages FetchPtr → E3 latent; bank1 digit pointers stomped $E0–$EB) | sharing across ALL phases = the real cost |
| **single-consumer table fold** | one routine stages ptr once (`lda #<T/sta FetchPtr/...` = 8 B) + `jsr` (3 B, net 0 vs direct `lda abs,Y`) + shared `FoldB1` variant (`sta $1FF7/lda (FetchPtr),Y/sta $1FF6/rts` = 9 B) | **≈ +17 B, +19 c per read** | cheap when 1 consumer, 1 phase |
| **whole-routine jump (proven HUD pattern)** | fixed byte-identical pads (8 B × 2 banks per direction — execution crosses the hotspot mid-stub, so bytes after `sta $1FF7` must exist in the OTHER bank at the same address) + `jmp` call/return (3+3 B) | **≈ bank0 19 B, bank1 16 B per pair, ~12 c per transition, once/frame, ZERO staging** | can carry its OWN private tables along = no folds at all |
| kernel-scanline read | — | **impossible** (76 c line, ~10 c margin) | never |

#### Candidates ranked (bank0 relief)

| action | bank0 net | cost class |
|---|---|---|
| **delete dead score fossil** (75 B, + 3 dead ZP decls) | **−75** | none — needs user OK (dead code rule) |
| move YToRowTable (48 B) to bank1 via fold (1–2 overscan sites) | ≈ −30 | small fold, but timing-sensitive (overscan TIM64T history) |
| move bomb/blink tables (32 B) + EnemyColor/ObjSpriteOff (18 B) via folds | ≈ −15 | small folds, marginal |
| move whole overscan subsystem + private tables via tramp pair: BuildColupF (~149 B) or SelectActiveObject (~202 B + its 18 B tables) | ≈ −130 / −190 | tramp 19 B bank0 (pad space needed!) — cheapest per byte |
| kernel data (ObjSprites etc.) | 0 | impossible |

**Constraints discovered:**
- bank0 has only ONE free pad home right now: the 25 B gap ($FC4F–$FC67),
  which E4's `MothYDerive` consumes exactly → tramp pads need bank0 space
  that appears only after the dead-block deletion (pad can sit at fixed
  $FAC0 inside the freed $FAB1–$FAFB run, which is ALSO free in bank1's
  680 B gap $F9C0–$FC67 ✓) or another explicit free.
- bank1 can only EXECUTE content during contexts we tramp into (HUD band
  today); data in bank1 read from bank0 costs folds as above.

#### Verdict

1. **HUD four: nothing left to move** — state = shared RAM, render+tables
   already bank1. The only bank0 HUD item is the DEAD 75 B PF-score fossil
   → deletion beats relocation.
2. **Jumps are NOT inherently level-expensive.** Levels cost 190 B +
   bug history because 60 sites shared one staged pointer across all
   phases. A routine-jump (HUD tramp pattern) = fixed pads + jmps ≈ 19 B,
   no staging, no aliasing. A single-consumer table fold ≈ 17 B.
3. **Real bank0 hugs are kernel-pinned** (ObjSprites+sprites ≈110 B can
   never fold). Bigger relief comes from overscan-subsystem jumps
   (−130…−190 B each) — code, not data, but safe and cheap.

### Q4 (2026-09-30): Good code-move candidates, or optimize in place?

#### Call-graph audit (jsr-dependency scan of every routine >25 B)

**Big subsystem moves FAIL — dependency-entangled:**

| candidate | calls | verdict |
|---|---|---|
| SelectActiveObject (202) | `SetObjectXPos` (kernel-tuned, shared), `FoldIndirect`, `IsRoomDark`, `SetObjReflection` | ✗ chain explodes |
| BuildColupF (149) | `FoldIndirect`×4, `IsRoomDark` | ✗ same |
| HotOverlapFlag (111) | `FoldIndirect` | ✗ |
| UE_* / PlayerHitsMap / laser | `SetObjectXPos`, fold chains | ✗ kernel-tuned deps |
| LoseLifeHot → ReloadLevel → LoadLevel(146)+… | deep chain | ✗ too entangled |

**Leaf set — CLOSED, movable (all overscan-phase, zero outgoing jsr
except each other):**

| routine | bytes | callers (all overscan) |
|---|---|---|
| AddScore | 38 | CEH, BombEnemyBlast, BombMarkWalls |
| UpdateJetSound | 45 | overscan loop |
| UpdateBombSound + BombSndDrop + BombSndExplode | 62 | BombTick |
| IsRoomDark + SetRoomDark + LoadRoomBottomColor | ≈99 | UE, SelectActiveObject, BuildColupF, ReloadLevel |
| ClearPFColumn | 49 | CEH area |
| GetConnIdx | 16 | exit handlers |
| **total** | **≈309** | |

Mechanism: shared ReturnPad (`lda #0/sta $1FF6/rts`, byte-identical both
banks) 8 B + per-target CallPad (`lda #1/sta $1FF7/jmp Target`) 8 B each;
bank0 call sites become `jsr CallPadX` (3 B = same as direct jsr, net 0).
≈16 + 8×N fixed bank0 cost (N≈8–10) ≈ 96 B → **net ≈ −213 B**.
**Destination: bank1** — bank3 is RESERVED for levels (user, 2026-09-30).
Capacity: leaves ≈309 B + pads ≈16 B ≈ 325 B of bank1's 2819 B free,
leaving ≈2494 B for HUD growth (13+2 technique). All reads/writes are
shared ZP; no FetchPtr use; phases have spare cycles.

#### In-place optimization — realistic ceiling is LOW

| target | possible | risk |
|---|---|---|
| snake L/R near-duplicate paths (UE_SnakeLeft 45 / UE_SnakeRight 45) | −30…−40 | medium (live enemy logic) |
| EnterRoom/CEH/LoadEnemyRAM | already loop-compact (LER_Loop, CEH_Loop) | little left |
| kernel `.Line` / VBLANK | **do not touch** — cycle-tuned, AGENTS history (stale comment budgets shipped 2 bugs; VBL overrun lesson) | unacceptable |
| realistic in-place total | **−30…−60** | |

#### Answer

**Move, don't optimize** — for this codebase:
1. Leaf-set move to bank1 ≈ **−213 B** at low risk (leaves, overscan,
   no cycle-tuned code, pad byte-identity can be guarded in verify_build).
   bank1 capacity check: 325 B of 2819 free, HUD keeps ≈2494 B.
2. In-place only buys −30…−60 B at medium risk; kernel/VBL untouchable.
3. Do NOT chase SelectActiveObject/BuildColupF — dependency audit says
   each would drag SetObjectXPos/FoldIndirect chains behind it.
4. Order: E4 (planned, uses the 25 B gap) → leaf move → snake dedup only
   if still short. One step per build, Stella test between (AGENTS
   build-test-build).
5. **bank3 is RESERVED for levels** (user directive 2026-09-30) — the
   earlier "empty bank3 = pressure valve" idea (Q1) is superseded: future
   level growth goes there, not code.

**STATUS 2026-09-30: leaf move EXECUTED — see `leaf_move_plan.md`.**
9 routines + 2 tables moved bank0→bank1 (batches A+B), CallPad/ReturnPad
mechanism, all gates green incl. `check_callpads()` guard. bank0 free
measured **249 B** (was ~0; better than the −213 B estimate). bank1 free
after moves = **~547 B** (the pre-move "2819 B free" figure never matched
the binary — budget HUD growth against 547 B).
