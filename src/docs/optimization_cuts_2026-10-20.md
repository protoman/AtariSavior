# Optimization cuts — 2026-10-20 (applied, measured)

Chunk log for the four low-risk cuts of
`docs/optimization_audit_2026-10-20.md` (rows 2, 1, 3, 8 of its ranked plan,
taken in the order the brief gave: level-data C1, dead bank-switch halves,
ObjColorTab, PF row pool). One commit per item; every commit is green:
`./build.sh` (verify + both sims), `tools/freeze_test_banks.sh`, the full
`tools/test_*.py` battery + `src/tools/test_title_demo.py`.

Baseline (HEAD fe40beb): total **9321** used / 7063 free —
bank0 3373, bank1 2887, bank2 1760, bank3 1301; level data 548 B.

## Size ledger

| after | bank0 | bank1 | bank2 | bank3 | total | level data |
|---|---|---|---|---|---|---|
| baseline fe40beb | 3373 | 2887 | 1760 | 1301 | **9321** | 548 |
| C1 shared room blocks | 3373 | 2887 | 1760 | 1263 | **9283** | 510 |

## 1. Level-data C1 — share byte-identical room blocks (38 B)

`tools/convert_level.py`: new `dedupe_room_blocks()` post-pass in `--levels`
mode (it can only run there — the duplicates live in *different* levels'
`*_blocks.asm`). Identity = the emitted byte directives with the
`L<level>R<room>` prefix and comments stripped, so it compares what the ROM
actually stores. The first copy survives; every duplicate's block text is
replaced by a machine-readable note

```
; L3R1 block SHARED with L1R1 (byte-identical dedupe)
```

and its `LEVEL{n}_RoomDataTable` entry is repointed at the survivor's labels,
so no asm change and no bank0/bank2 cost. Cross-level sharing is safe for the
same reason the model blocks already share: the block address is a bank3
absolute and the meta sits at `TilePF0+9/+10` of the same bytes.

`tools/verify_build.py`: the "room owns async but no block emitted" gate now
follows the note and re-runs `block_checks` against the SURVIVOR's text using
the duplicate room's expected meta/right values (identical bytes must satisfy
both rooms' expectations, so a stale note cannot hide a mismatch).

Live stage: `L3R1 -> L1R1`, `L4R1 -> L1R1` (38 B). Frozen test stage:
`L3R1 -> L1R1`, `L4R1 -> L1R1`, `L4R2 -> L3R2` (its level-4 room 2 is a copy
of level-3 room 2 there) — the general rule, not a hardcoded pair.
Re-frozen: `src/tests/frozen/bank{2,3}.{bin,lst}`,
`src/tests/generated/level_00{3,4}_{blocks,rooms}.asm`.
