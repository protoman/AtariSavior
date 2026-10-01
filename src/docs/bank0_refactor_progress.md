# Bank0 Refactor — Progress Report

Investigation: `src/docs/bank0_simplification_investigation.md`
Method: one step = edit → `./build.sh` (verify_build + sim_bomb_fuse) →
targeted tests → checkbox update → commit. Revert any step with
`git revert <sha>`.

Baseline (before step 1): bank0 3769 B emitted (lst-span method), pre-pad ends $FC67,
verify_build OK (1 WARN: headroom 1B), sim_bomb_fuse OK.

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
      → **blocked on Phase 3 (verified this session):** bank1 HUD writes
      `scorePtr4+1`/`scorePtr5` = **$E7/$E8/$E9 every frame** (score pointer
      setup is unconditional in the HUD band), i.e. it stomps ColupfBuf rows
      0-2 — the ONLY rows the kernel reads (TILE_ROWS=3). The per-frame
      VBLANK rebuild is the structural stomp repair (zp_layout_skill.md
      line "VBLANK rebuilds"); a dirty flag would evaluate dirty EVERY
      frame and skip nothing. A "cheap 3-byte repair" variant would win
      ~200-300c but needs 3 bytes of cache ZP — none free pre-Phase-3.
      Re-enable ONLY after S3.1 moves ColupfBuf rows 0-2 out of bank1's
      $E0-$EF stomp zone.

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
- [ ] S3.0b dead-path deletions: bomb save/restore audit (BCF writes rows
      0-2 only, never `$F0-$F2` → save/restore likely vestigial), dead
      `ObjBot byte` decl (last sequential → no shift, frees `$BC`)
- [ ] S3.1 shrink PF/Colup buffers 12→3 rows, contiguous rect cache
- [ ] S3.2 single rect-copy loop; delete `.Stage3`, window switch, ABW tables
- [x] S3.3 hot rects into ZP cache → fold-free `HotOverlapFlag` (−2 SP levels)
      → **obsolete: S5.1/S5.3 delivered it differently** — HOF body now
      lives in bank2 reading level ROM directly (fold-free, bank2-local);
      bank2 BuildColupF same. No ZP hot cache needed.
- [ ] S3.4 private `EnemyRamY` → delete `LoadPF0Only` + alias guards
      (target `$E2-$E4` — timing-verified: all Y reads land between the
      overscan write and the next HUD stomp)
- [ ] S3.5 rewrite `docs/zp_layout_skill.md`, re-measure min SP

## Phase 4 — data format

- [ ] S4.1 enemy stride 6→4 (drop dead `range_min/range_max`)
- [ ] S4.2 PF table stride 12→3 (data only)
- [ ] S4.3 hot-rect parent-mask removal (needs gameplay OK)
- [ ] S4.4 room wall-mask nibble pack → per-room byte (needs gameplay OK)

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

## Phase 6 — gameplay cuts (optional, one at a time, user test each)

- [ ] laser sweep phases off
- [ ] jet inertia ramp off
- [ ] fixed flicker order (no modulo rotation)
- [ ] single-frame player sprite

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

## Verified no-win / deferred (Phase 1 findings)

- S1.2 deferred to Phase 3 (needs contiguous dests = ZP reorder).
- S1.3 skipped: 6502 scratch cost ≥ duplication (79B → best-safe 78B).
- S1.4 skipped: stage-before-batch contract is load-bearing.
- Snake left/right mirror dedup (investigation D-finding, not a checkbox):
  shared fetch saves ≈13 B but needs php/plp + face/movement flag dance —
  same bug family as the php/pla lesson. **Not worth ≈9 B net.**
- Unreferenced labels (`UE_SnakeLeft`, `UpdateP0Vertical`): 0 B (code is
  fall-through reachable; label text costs nothing) — left alone.
