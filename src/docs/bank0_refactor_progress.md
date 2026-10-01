# Bank0 Refactor — Progress Report

Investigation: `src/docs/bank0_simplification_investigation.md`
Method: one step = edit → `./build.sh` (verify_build + sim_bomb_fuse) →
targeted tests → checkbox update → commit. Revert any step with
`git revert <sha>`.

Baseline (before step 1): bank0 3768B emitted, pre-pad ends $FC67,
verify_build OK (1 WARN: headroom 1B), sim_bomb_fuse OK.

## Phase 1 — pure duplication (no contracts touched)

- [ ] S1.1 `LoseLife` unification — 5 life-loss copies + zero-physics blocks
- [ ] S1.2 `LoadLevel` 14 unrolled folds → loop + dest table
- [ ] S1.3 `ExitRoomUp/Down/Left/Right` → one direction-parameterised routine
- [ ] S1.4 share `EnemyData*` staging across one overscan pass
- [ ] S1.5 mechanical: unused EQUs (`LASER_PREV`, `LASER_HP`, `PF2ScoreBuf`),
      unreferenced labels (`UE_SnakeLeft`, `UpdateP0Vertical`), inline
      `LoadRoomBottomColor` (`lda`/`rts` behind `jsr`)
- [ ] S1.6 dead `YToCellRow` subroutine removal + `test_enemy_movement.py`
      anchor update (deferred: test text-slices on the label)

## Phase 2 — cycles (no format change)

- [ ] S2.1 `BuildColupF` dirty-flag rebuild (VBL headroom; worst 1311c/1472c)

## Phase 3 — ZP re-plan (atomic, high risk)

- [ ] S3.1 shrink PF/Colup buffers 12→3 rows, contiguous rect cache
- [ ] S3.2 single rect-copy loop; delete `.Stage3`, window switch, ABW tables
- [ ] S3.3 hot rects into ZP cache → fold-free `HotOverlapFlag` (−2 SP levels)
- [ ] S3.4 private `EnemyRamY` → delete `LoadPF0Only` + alias guards
- [ ] S3.5 rewrite `docs/zp_layout_skill.md`, re-measure min SP

## Phase 4 — data format

- [ ] S4.1 enemy stride 6→4 (drop dead `range_min/range_max`)
- [ ] S4.2 PF table stride 12→3 (data only)
- [ ] S4.3 hot-rect parent-mask removal (needs gameplay OK)
- [ ] S4.4 room wall-mask nibble pack → per-room byte (needs gameplay OK)

## Phase 5 — offload leaves to bank1/bank2 (~2.6KB / ~3.4KB free)

- [ ] S5.1 `BuildColupF` (176B)
- [ ] S5.2 `BombMarkWalls` (124B)
- [ ] S5.3 `HotOverlapFlag` (117B, tail-call contract via CallPad)
- [ ] S5.4 `LaserHitTest` (90B)

## Phase 6 — gameplay cuts (optional, one at a time, user test each)

- [ ] laser sweep phases off
- [ ] jet inertia ramp off
- [ ] fixed flicker order (no modulo rotation)
- [ ] single-frame player sprite

## Log

| Step | Change | bank0 Δ bytes | Tests | Commit |
|------|--------|---------------|-------|--------|
| 0 | investigation + report committed | — | build OK | (this) |
