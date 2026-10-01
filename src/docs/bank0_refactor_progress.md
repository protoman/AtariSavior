# Bank0 Refactor — Progress Report

Investigation: `src/docs/bank0_simplification_investigation.md`
Method: one step = edit → `./build.sh` (verify_build + sim_bomb_fuse) →
targeted tests → checkbox update → commit. Revert any step with
`git revert <sha>`.

Baseline (before step 1): bank0 3769 B emitted (lst-span method), pre-pad ends $FC67,
verify_build OK (1 WARN: headroom 1B), sim_bomb_fuse OK.

> **STATUS 2026-10-01: BACKLOG COMPLETE.** All executable steps done;
> Phase 6 + S4.3 + S4.4 explicitly skipped by user (no space pressure —
> gameplay-fidelity trades not worth it). bank0 **−632B vs baseline**
> (3769 → 3137, doc scale), bank2 −65B walk code (S3.2) and −118B ROM
> data (S4.1+S4.2), min SP improved to $F9. Guards that paid off this session: `check_equ_sync`
> (NEW — caught the bank1 `TickCounter=$AC` bug + the tentacle stomp-zone
> violation), frozen-addr (caught both `LEVEL_DATA_ADDR` shifts), plus
> NEW HOF/LHT tramp byte-identity checks and the updated fold operand.

## Phase 1 — pure duplication (no contracts touched)

- [x] S1.1 `LoseLife` unification — 5 life-loss copies + zero-physics blocks
      → done: −93 B (main −74, post-pad −19). Timer path also dropped a
      redundant `TickCounter` reload (already 60 on entry). C-flag contract:
      C=1 exhausted (ReloadLevel done), C=0 stay (physics zeroed).
- [ ] S1.2 `LoadLevel` 14 unrolled folds → loop + dest table
      → **deferred to Phase 3**: dest vars are NOT contiguous in source
      order (131-134, 137-145, 151-152) and `bank1.asm:108` hardcodes
      `LevelConnLo = $A1` — a safe loop needs the ZP decl reorder first
      (contiguous dests, then ≈ −75 B with no ROM table).
- [ ] S1.3 `ExitRoomUp/Down/Left/Right` → one direction-parameterised routine
      → **verified no-win, skipped**: direction must survive
      `CallPad_GetConnIdx` (which sets X=0), so a unified body needs a ZP
      temp (none free: Temp/LineCount/Collision*/MapPtr all live or
      contract-bound) or a table dispatch that costs ≥ the 4× edge
      sequences it saves (best-safe merge ≈ 78B vs current 79B).
- [ ] S1.4 share `EnemyData*` staging across one overscan pass
      → **skipped**: violates the stage-FetchPtr-immediately-before-batch
      contract (`$E0/$E1` alias family, test enforces ≥22 stage lines).
- [x] S1.5 mechanical: inline `LoadRoomBottomColor` (2 sites), drop
      write-only `ObjBot` stores + dead `clc/adc`, dead EQUs
      (`LASER_PREV`, `LASER_HP`, `PF2ScoreBuf`) → done: −12 B.
      Overscan moved $F183→$F182 (inline was BEFORE it) → bank1 ToGameStub
      `jmp` synced + landmark comment updated.
- [x] S1.6 dead `YToCellRow` subroutine removal + `test_enemy_movement.py`
      → done: −8 B. Test anchor switched from the sub label to the inlined
      lookup at `PlayerHitsMap:`; kernel comments updated (PHM clobbers X
      via rect walk, not the dead `tax`).

## Phase 2 — cycles (no format change)

- [ ] S2.1 `BuildColupF` dirty-flag rebuild (VBL headroom; worst 1311c/1472c)
      → **CLOSED: permanently blocked under the current ZP (verified after
      Phase 3).** Two independent proofs:
      1. bank1 HUD writes `scorePtr4+1`/`scorePtr5` = **$E7/$E8/$E9 every
         frame** → stomps ColupfBuf rows 0-2 (the only rows read) → the
         VBL rebuild is structural stomp repair; a dirty flag is always
         dirty.
      2. Post-Phase-3 byte budget: the persistent-below-$E0 region
         `$C3-$DF` is **exactly full** (PF0 3 + PF1 3 + PF2 3 + rect
         cache 20 = 29/29); band `$BC`, bombs `$F0-$F2`, stack excluded.
         Colupf needs 3 persistent non-stomp-zone bytes — none exist.
         Relocating bank1's ptrs instead is circular (they need the same
         nonexistent bytes; zone spares `$E0/$E1` = only 2).
      Only theoretical unblock: bank1 HUD surgery — all 6 score-ptr HI
      bytes are the constant `$FD`; collapsing them out of ZP would free
      $E1/$E3/$E5/$E7/$E9/$EB… (separate project, not worth ~200-300c).

## Phase 3 — ZP re-plan (sliced execution — atomicity traded for the S3.0 guard)

Execution order: S3.0 → S3.0b → S3.4 → S3.1/S3.2 → S2.1 → S3.5.
Each slice: edit → `./build.sh` + 4 tests → commit → (address movers also
get a Stella checkpoint before the next slice).

- [x] S3.0 cross-bank EQU sync guard (`check_equ_sync` in verify_build;
      kernel authority = sequential `Name byte` walk + `Name = $XX`; hex
      only; allowlist for documented aliases e.g. bank1 `Temp=$AD`)
      → done: caught a LIVE bug on day one — bank1 `TickCounter = $AC`
      read **PlayerLives** in the jet-sound wobble (`bank1.asm:770`,
      `and #1` parity) → fixed `$AC`→`$AD` (30 Hz sputter now works).
      Also deleted dead legacy EQUs `PF0ScoreBuf`/`PF1ScoreBuf` (decl-only,
      zero references — 48px sprite score never used PF buffers).
      Negative-tested (corrupt EQU → guard fails).
- [x] S3.0b dead-path deletions: bomb save/restore — **audit: zero writers
      between VBL save and .AfterRows restore** (BCF writes rows 0-2 only,
      never `$F0-$F2`; vestigial from the 12-row era) → both deleted
      (kernel restore −12B, bank2 save −12B); dead `ObjBot byte` decl
      removed (was last sequential decl → no address shift, `$BC` free).
      Follow-on: `Overscan` moved `$F182→$F176` → bank1 ToGameStub pad
      literal + kernel landmark comment synced (pad byte-identity guard
      caught it on the spot). Headroom warning stays 1B — structural
      (`.ds $FC4F` pin absorbs main-region deltas, not a growth signal).
- [x] S3.1 shrink PF buffers 12→3 rows, contiguous rect cache
      → done: PF0 `$C3-$C5`, PF1 `$C6-$C8`, PF2 `$C9-$CB` (packed rows
      0-2 — kernel reads X=0..2 only); cache **count+rects0-3 contiguous
      at `$CC-$DC`** (`RcBase=$CC`, `RcW1=$CD`); rect4 deliberately SPLIT
      (x,y at `$89/$8A` — sequential decls, moving them shifts the whole
      ZP block; w,h at `$DE/$DF`) → `.Stage3` survives into S3.2;
      `RcW2 ≡ RcW1` (window jump now provably no-op → S3.2 deletes it);
      `RoomBandColor` `$D2→$BC` (own byte, alias class gone);
      ABW tables **EQU-derived** (`.byte RcW1, RcW1+4, …`) in bank0+bank1
      — cannot go stale; EnterRoom copy: 2 windows → 1 loop (Y=1..16);
      ColupfBuf stays `$E7` (moves only with S2.1).
      equ-sync guard verified all hand-copied EQUs (bank1 PF1/PF2/RcBase/
      RcW1, bank2 Rc*) — negative-tested with a stale bank1 RcBase.
      bank0 −11B. **Stella: wall collision + bomb blast + room entry.**
- [x] S3.2 single rect-copy loop; delete `.Stage3`, window switch, ABW tables
      → done (supersedes S3.1's split-rect4 note): **uniform stride** —
      cache now `$CC-$E0` (count + rects0-4), rect4 x,y,w,h IN the cache
      (`$DD-$E0`); `FetchPtr` moved `$E0→$E5` to free `$E0` (frees the
      +1-byte gap that forced the split). Deleted: kernel `.Stage3`,
      window2 jumps in PHM + bank2 moth, moth `.MwStage3`, copy loops
      `.rcW3/.rcW4` (EnterRoom copy = ONE Y=1..20 loop); `RcW2/Rc4W/Rc4H/
      MapPtrLo/Hi` EQUs retired (sequential `$89/$8A` kept as pads —
      moving them shifts the whole ZP block). Mask tables +`$00` 5th
      entry (index4 = rect4, never in WallMask — BombMaskBit + MothMaskBit;
      kernel and moth walks otherwise read it uniformly).
      `FOLD_BYTES` const updated `B1 E0→B1 E5` (byte-identity guard
      re-verified, negative-tested). `test_phm_walk` rewritten: keeps the
      exit-Y discipline asserts (nrmCol/nrmRow — still required!) + adds
      uniform-stride asserts (no `.Stage3`, no `RcW2`, 5-entry masks) for
      BOTH walkers (kernel + moth).
      bank0 −77B (3220→3143), bank2 −65B (1128→1063).
      **Stella: wall collision + bomb + moth wall-turn + room entry.**
      → **S3.2 bug found by user (Stella): tentacle walked inside walls.**
      Root cause: rect4.h landed on `$E0` = bank1 `scorePtr1` lo (leading
      zero) → HUD zeroed it every frame → rect4 probes passed through.
      Fix: count moved onto the `$89` pad (`RcBase` = sequential decl at
      the old MapPtrLo slot), rects shifted to `$CC-$DF` (last byte ≤
      `$DF`, clear of the stomp zone). **New guard** in `check_equ_sync`:
      persistent names (`RcBase/RcW1/PF*/RoomBandColor/BombX/BombTimer`)
      must be < `$E0`, cache span `RcW1+19 ≤ $DF` — negative-tested.
      → **Known (user-accepted, 2026-10-01):** tentacle STILL enters walls
      slightly **on the left**. Residual is probe-box geometry, not the
      cache: PHM's entry derives the column range with PLAYER origin rules
      (`RoomX-PlayerDir`, then −4/−7, PLAYER_WIDTH) while the tentacle is
      an 8px GRP1 sprite whose draw origin sits ~5/7px left of A — same
      family as the documented moth "sat ~7 px inside a wall" issue
      (e4_moth_plan). Fix = per-enemy origin offset on the candidate in
      UE_Tentacle before the RoomX swap — deferred, low severity.
- [x] S3.3 hot rects into ZP cache → fold-free `HotOverlapFlag` (−2 SP levels)
      → **obsolete: S5.1/S5.3 delivered it differently** — HOF body now
      lives in bank2 reading level ROM directly (fold-free, bank2-local);
      bank2 BuildColupF same. No ZP hot cache needed.
- [x] S3.4 private `EnemyRamY` → delete `LoadPF0Only` + alias guards
      → done: `EnemyRamY` `$C3→$E2-$E4` (inside bank1's HUD stomp zone,
      ordering-safe: every write is overscan-post-stomp, every read is
      pre-next-stomp — window diagram in kernel ZP contract). Effect:
      - `$C3-$C5` pure PF0 → VBL `jsr LoadPF0Only` (3 folds ≈130c/frame)
        deleted; routine KEPT as `LoadPFBuffer`'s tail jump (EnterRoom
        full rebuild still needs the PF0 phase).
      - `check_enemy_alias` guard deleted; `test_enemy_movement` re-pinned
        to `$E2`; bank2 EQU synced — **negative-tested with the S3.0
        equ-sync guard** (stale `$C3` in bank2.asm → caught).
      - Overscan `$F176→$F173` (jsr removal) → bank1 pad + landmark synced.
      bank0 −3B (jsr), −130c/frame VBL.
- [x] S3.5 rewrite `docs/zp_layout_skill.md`, re-measure min SP
      → done: doc refreshed (2026-10-01): stomp-zone rule as Critical
      Rule 6, sequential-block/`$BC` rules corrected, cache/count/FetchPtr/
      EnemyRamY rows final, Bank2 section rewritten (level data + offload
      bodies, not "legacy HUD trampoline"), 5-entry mask note, bomb-save
      obsolescence. min SP re-measured: **gameplay `$F9` (guard ≥$F8,
      +1 vs historical boundary)**, whole-run `$F7` — recorded in the doc's
      new "Stack depth" section. NOTE: `AGENTS.md` still documents the
      old EnemyRamY `$C3` alias + `check_enemy_alias` — user file, needs
      an update pass (listed for user).

## Phase 4 — data format

- [x] S4.1 enemy stride 6→4 (drop dead `range_min/range_max`)
      → done: `ENEMY_STRIDE 6→4` in convert_level (ROM = `type,x,y,dir`;
      editor JSON keeps range fields — check_levels still validates them);
      `EnemyOffTable 0,6,12→0,4,8` (kernel + bank2); LoadEnemyRam dir read
      `+5→+3` (−2 iny), snake ROM-dir reads `+5→+3` ×2 (−4 iny); all "*6"
      comments updated; `LEVEL_DATA_ADDR $FB04→$FAFA` — **caught by
      check_frozen_addrs on first build** (rooms_data shrank → LevelDataTable
      moved). −6B bank0 + 2B/enemy ROM (5 enemies → −10B data).
      bank0 3143→3137 (doc scale).
- [x] S4.2 PF table stride 12→3 (data only)
      → done: `TABLE_STRIDE 12→3` in convert_room (both emission paths —
      models + room-local — share the constant; legacy >3-row grids still
      pad to their row count via `max()`); kernel EnterRoom PF1/PF2 pointer
      math `adc #12 → adc #3` (the "+12/+12 bank0 table arithmetic" the
      old padding existed for); `PF0Buf` comment de-staled.
      `LEVEL_DATA_ADDR $FAFA→$FA8E` — **frozen-addr guard fired again**
      (models_data shrank 108B → everything after moved).
      ROM: −108B bank2 data (4 referenced models × 3 tables × 9 bytes);
      bank0 code Δ0 (operand-size neutral). **User Stella ✓** — walls
      render identically (pattern, mirrors, bomb holes, transitions).
- [ ] S4.3 hot-rect parent-mask removal (needs gameplay OK)
      → **SKIPPED (user decision 2026-10-01):** no space pressure (same
      rationale as Phase 6). Both rule options cost gameplay fidelity
      (hot rock never dies = invisible bump in the blast hole; all die =
      other rocks lose danger) for ~10B + 1B/hot rect. Reference:
      investigation F3 — revisit only with a fresh user request.
- [ ] S4.4 room wall-mask nibble pack → per-room byte (needs gameplay OK)
      → **SKIPPED (user decision 2026-10-01):** simplest cut = destroyed
      walls reset on room leave (gameplay change); no-gameplay-change
      variant needs +1 ZP byte (none free). ~60B. Reference:
      investigation F4 — revisit only with a fresh user request.

## Phase 5 — offload leaves to bank1/bank2 (~2.6KB / ~3.4KB free)

- [x] S5.1 `BuildColupF` → **bank2** (not bank1) via `CallPad_BuildColupF`
      → done: −144 B (3656→3512). Findings baked into the step:
      - The shared `$FEF6` fold block ends `sta $1FF6` — once bank2 serves
        the middle bytes, the switch back to bank0 is **frozen**; a fold
        inside any non-bank0 body cannot return home. bank2 bodies read
        rect data directly (`lda (FetchPtr),Y`, moth precedent).
      - `CallPad_*` stubs switch banks **mid-pad**: the pad's `jmp` is
        fetched from the TARGET bank (why bank1 mirrors the whole pad
        block) — bank2 now mirrors the new stub too (fetch at `$FC3B`).
      - `jsr CallPad_IsRoomDark` cannot nest from a pad body (ReturnPad
        switches to bank0) → dark check inlined (4B `BCFDarkMask` table).
      - New first-ever `sta $1FF8` pad: `check_callpads` now looks the
        jmp target up in `bank2.lst` for `$1FF8` pads (bank1 for `$1FF7`).
      - Entry save block (`$F0-$F2` → collision temps) moved as-is —
        still dead (rows 0-2 only, no restore) → follow-up audit.
- [x] S5.2 `BombMarkWalls` → **bank1** via `CallPad_BombMarkWalls` ($FB10)
      → done: −102 B (3512→3410). Constraints handled:
      - Score could not stay inline (`jsr CallPad_AddScore` from a pad body
        = ReturnPad switches to bank0 mid-call) → BMW returns
        **A = #walls newly broken**; the fuse-expiry caller does the +75
        loop (per-wall semantics preserved; AddScore doesn't read
        BombPacked, so post-walk scoring is equivalent same-frame).
      - `Temp` trap: bank1's `Temp` EQU = $AD (HUD scratch, kernel's
        TickCounter) — BMW scratch renamed `BMWScratch = $88` (kernel Temp).
      - `ABWXTab`/`ABWWTab`/`BombMaskBit` duplicated into bank1 (ROM is
        per-bank; the ZP rect cache itself is shared RAM).
- [x] S5.3 `HotOverlapFlag` (117B, tail-call contract via CallPad)
      → done: −107 B (3410→3303, same lst-span delta measured HEAD vs now).
      NOT a CallPad: the $FBF8-$FC48
      pad window is full (5 B left, stub needs 6 B) → moth-pattern entry
      tramp pinned $FE80 instead. Body moved to bank2.asm `HotOverlapBody`
      at $FCF0, fold-free (7 `jsr FoldIndirect` → direct `lda (FetchPtr),Y`
      — RoomRects level data lives in bank2; +1 fewer push level on the hot
      path). Exits `sec / jmp $FBF8` (ReturnPad) keep the tail-call C=1
      contract (sta touches neither A nor flags). `check_moth_tramp` extended:
      $FE80 byte-identity bank0/bank2 + jmp operand == bank2.lst
      `HotOverlapBody` + bank0 `HotOverlapFlag` label pin.
- [x] S5.4 `LaserHitTest` (90B) → **bank2** at $FF00 via $FE86 tramp
      → done: −57 B (3303→3246, lst-span delta measured HEAD vs now).
      Constraints handled:
      - Kill/lamp ACTIONS cannot run from a bank2 body (`CallPad_AddScore`/
        `CallPad_SetRoomDark` are bank0→bank1 only — pads cannot nest from
        a pad body, S5.2 lesson) → body returns a RESULT CODE in A through
        ReturnPad (sta/rts preserve A/Z/C): 0 miss / #$50 kill / 1 lamp;
        LaserInput tail does `beq / cmp #$50 / jsr CallPad_*`.
      - Enemy type read: fold → direct `lda (FetchPtr),Y` (records are
        bank2 level data); `EnemyBitTable`/`EnemyOffTable` copied into
        bank2 (bank0 ROM invisible; same labels keep test anchors).
      - Tramp pinned $FE86 (free $FE86-$FEEF hole in BOTH banks, same
        pattern as the S5.3 HOF tramp); `check_moth_tramp` extended with
        the same 4 checks (byte-identity, sta prefix, operand == bank2
        label, bank0 label pin) — negative-tested.
      - `test_enemy_movement` + `test_laser_s4` re-anchored to bank2 body;
        `test_laser_s4`'s stale `jsr SetRoomDark` assert (broken since the
        bank1 leaf move — pre-existing) fixed to the CallPad form.

## Phase 6 — gameplay cuts: **REMOVED from plan (user decision 2026-10-01)**

Space pressure is gone (bank0 −267B this session); the §5 cuts table in
`bank0_simplification_investigation.md` stays as reference only — do not
execute without a fresh, explicit user request tied to a real need
(title screen / music / win screen / VBL margin).

## Bugfixes

- **Laser passed through walls** (user, 2026-10-01) — labeled **S6** in
  code/comments (investigation §S6 "staging noise" is unrelated).
  Two symptoms fixed by ONE mechanism — wall-clamped visible width:
  1. *visual*: beam reappeared beyond thin walls (CTRLPF=$05 priority only
     hides the OVERLAP pixels) and sweep bursts jumped the eye→burst gap;
  2. *gameplay*: `LaserHitTest` killed through walls (interval was fixed
     `[lo, lo+7]`).
  Design: `LaserWallClamp` (post-pad leaf — the $FFxx page is full) walks
  the rect cache over the path `[min(eye,lo) .. max(eye,lo+7)]`, clamps
  `bestEnd` to the first wall, returns width→ `bound=floor-pow2(W)+7`
  staged in `RectCount` (LHT: `cmp RectCount`) and packed into
  `LaserBeamOn = $02 | bound<<4` → VBL `and #$30 / sta NUSIZ0` picks the
  M0 width code (1/2/4/8 px; floor so the sprite never overruns), fully
  blocked = `LaserBeamOn=$00` + skip LHT. HERO has no laser code —
  original design. Scratch: ActiveObjectX/Y + RectCount (window-safe:
  every later reader writes first). Overscan +~500c, VBL +2c.
  **First attempt (same session) failed: the walk compared PIXEL path
  coords against column-unit rects** (rect cache = text columns 0-19 +
  band rows — that's why large walls hid via CTRLPF priority but thin
  walls + kills sailed through). Fix: path px → `>>2` real columns, test
  BOTH spans per rect (left-half `[x,x+w-1]` + mirror `[39-(x+w-1),39-x]` —
  reflected playfield means every wall exists twice), `bestCol*4 - lo` for
  the pixel width (sign also handles eye-gap/blocked). White-box sim in the
  commit validated: flush thin wall → W=4/bound11, gap burst → 0,
  mirror cases → correct, open → 8; `test_laser_s4` now asserts the
  column conversion + mirror-span presence.
  Overscan moved `$F173→$F175` (VBL +2B) → bank1 pad synced (4th time —
  AGENTS lesson updated). Post-pad slack 316→142B (`LaserWallClamp` lives
  at $FCD4). `test_laser_s4` extended (bound contract, NUSIZ/VBL chain,
  blocked path).

## Log

| Step | Change | bank0 Δ bytes | Tests | Commit |
|------|--------|---------------|-------|--------|
| 0 | investigation + report committed | — | build OK | 6f61a20 |
| 1 | S1.1 LoseLife unification | −93 (3769→3676) | build+sim+3 tests OK | f41800d |
| 2 | S1.5 inline helper + ObjBot + dead EQUs | −12 (3676→3664) | build+sim+3 tests OK | 02b991c |
| 3 | S1.6 dead YToCellRow sub + test anchor | −8 (3664→3656) | build+sim+3 tests OK | a2158f8 |
| 4 | S5.1 BuildColupF → bank2 via CallPad ($1FF8) | −144 (3656→3512) | build+sim+3 tests OK | 5103f6a |
| 5 | S5.2 BombMarkWalls → bank1, count-return + caller score loop | −102 (3512→3410) | build+sim+3 tests OK | (this) |
| 6 | S5.3 HotOverlapFlag → bank2 ($FE80 tramp, fold-free, ReturnPad exit) | −107 (3410→3303) | build+sim+3 tests OK + guard negative-test | (this) |
| 7 | S5.4 LaserHitTest → bank2 ($FE86 tramp, A-result protocol) | −57 (3303→3246) | build+sim+4 tests OK + guard negative-test | (this) |
| 8 | S3.0 cross-bank EQU guard + bank1 TickCounter fix + dead score EQUs | 0 B (bank1 operand swap) | build+sim+4 tests OK + guard negative-test | (this) |
| 9 | S3.0b bomb save/restore + ObjBot decl deleted; Overscan $F182→$F176 | −12 (3246→3234; bank2 −12) | build+sim+4 tests OK | (this) |
| 10 | S3.4 EnemyRamY $C3→$E2, VBL LoadPF0Only repair deleted | −3 (3234→3231) | build+sim+4 tests OK + equ-sync negative-test | (this) |
| 11 | S3.1 packed PF buffers + contiguous rect cache $CC-$DC, band→$BC, EQU-derived ABW tables | −11 (3231→3220) | build+sim+4 tests OK + equ-sync negative-test | (this) |
| 12 | S3.2 uniform stride: rect4 into cache, FetchPtr $E0→$E5, .Stage3 + window jumps deleted (kernel+moth) | −77 (3220→3143; bank2 −65) | build+sim+4 tests OK + fold-guard negative-test | (this) |
| 13 | S3.2-fix: rect cache out of bank1 stomp zone (count→$89, rects→$CC-$DF) + stomp-zone guard | 0 B (address fix) | build+sim+4 tests OK + zone-guard negative-test | (this) |
| 14 | S2.1 closed (permanently blocked — byte budget) + S3.5 zp doc rewrite + min SP re-measured ($F9/$F7) | 0 B (docs) | build+sim+4 tests OK | (this) |
| 15 | S4.1 enemy stride 6→4 (drop range slots), EnemyOffTable 0/4/8, LEVEL_DATA_ADDR sync | −6 (3143→3137) + −10B ROM | build+sim+4 tests OK (frozen-addr guard fired first) | (this) |
| 16 | S4.2 PF table stride 12→3 (convert_room + EnterRoom +3 pointers) | 0 B code; −108B bank2 ROM data | build+sim+4 tests OK (frozen-addr guard fired again) | (this) |
| 17 | Bugfix: laser wall occlusion (`LaserWallClamp` + bound-staged LHT + NUSIZ width) | +174B post-pad (slack 316→142) | build+sim+4 tests OK | (this) |

## Verified no-win / deferred (Phase 1 findings)

- S1.2 deferred to Phase 3 (needs contiguous dests = ZP reorder).
- S1.3 skipped: 6502 scratch cost ≥ duplication (79B → best-safe 78B).
- S1.4 skipped: stage-before-batch contract is load-bearing.
- Snake left/right mirror dedup (investigation D-finding, not a checkbox):
  shared fetch saves ≈13 B but needs php/plp + face/movement flag dance —
  same bug family as the php/pla lesson. **Not worth ≈9 B net.**
- Unreferenced labels (`UE_SnakeLeft`, `UpdateP0Vertical`): 0 B (code is
  fall-through reachable; label text costs nothing) — left alone.
