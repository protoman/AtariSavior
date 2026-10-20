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
Frozen test stage shares one more pair (`L4R2 -> L3R2`) than the live stage,
because its level-4 room 2 is a copy of level-3 room 2 — the dedupe is by
bytes, not by a hardcoded room list.

## 2. Dead bank-switch halves — SKIPPED (claim does not survive re-measure)

The audit's premise ("14 dead `sta` halves = 42 B") is wrong for 10 of the 14,
and worth only ~15 B for the rest.

Measured facts:
- A pad at address `A` is `sta $1FFx` (3 B) + `jmp $YYYY` (3 B). A caller in
  bank C executes the `sta`; after the switch the *next* fetch is at `A+3`,
  i.e. from the TARGET bank. So in the target bank bytes `A..A+2` are dead and
  `A+3..A+5` are live; in the caller bank the opposite. Both halves are
  address-locked: deleting one half shifts the surviving half off `A+3`,
  which breaks the tramp. **Removing a dead half frees no ROM by itself.**
- `bank1/bank2/bank3` contain **zero** `jsr CallPad_*` sites (grep of all four
  sources: only bank0 calls pads; every other bank only does `jmp ReturnPad`),
  so the dead halves are exactly: target-bank `sta` + caller-bank `jmp`.
- The 10 "twin tramps" the audit lists (`$F8C0`, `$FBD0`, `$FDD8`, `$FDE1`,
  `$FE96`, `$FEF0`, `$FFE6`, `$FFEC`, `$F9BC`, `$F458`) sit between fixed pins
  on both sides — deleting a half only enlarges the fill.
- Real, reclaimable bytes exist only at the **tail of bank0's flow**, where
  the pads end at `$FC67` (limit `$FC68`, headroom 1 B):

| pad | address | bank0 live half | bank1 live half |
|---|---|---|---|
| `CallPad_TitleSelect` | `$FC4F` | `sta $1FF7` (kernel:3109) | `jmp $F041` at `$FC52` |
| `CallPad_TitleBand` | `$FC55` | `sta $1FF7` (kernel:911) | `jmp $F080` at `$FC58` |
| `CallPad_Overscan` | `$FC5B` | **nothing calls it** (dead 6 B) | dead too |
| `CallPad_MusicTick` | `$FC61` | `sta $1FF7` (kernel:3145) | `jmp MusicTick` at `$FC64` |

Design for the 15 B (next session, do not start without a green tree and a
full battery budget): bank0 keeps only the three `sta`s, packed at
`$FC4F/$FC52/$FC55` (flow ends `$FC58` → headroom 1 B → 16 B); bank1 keeps
only the three `jmp`s at `$FC52/$FC55/$FC58`; delete the `CallPad_Overscan`
pair (no caller in any bank) and drop its loop from
`verify_build.sync_overscan`; replace `check_callpads`'s whole-block
`bank0 == bank1` byte-identity test (currently lines 771-776) with a per-pad
contract (bank0 `8D F7 1F` at `A`, target bank `4C lo hi` at `A+3`), because
the two banks intentionally stop being byte-identical there. Guarded by
`test_menu_flow` + `test_title_demo` + both sims (the title path is the only
consumer).

Skipped in this chunk: 15 B for a rewrite of the one guard that protects the
bank-switch corridor (a wrong pad address is a silent wrong-bank jump), with
the bank0 tail pinned on both sides. Recorded above instead.

## 3. ObjColorTab 72 -> 17 — SKIPPED (hot-path cycle cost, not a table win)

`ObjColorTab` (kernel.asm `$FE00-$FE47`) is read in the cycle-exact `.Grp1`
object section as `lda ObjColorTab,X` (4c, same page) with `X = ObjBase + r`,
4 bytes after `lda ObjSprites,X` reuses the same X. The suggested shrink
("staged per-type color + 8-row miner table") needs the per-row color write to
become conditional, because only the MINER has non-uniform rows
(`$54,$54,$4A,$54,$54,$08,$54,$54`; all 8 other types are 8x the same byte).
- A per-row branch (`lda ObjBase/cmp/bne` ≈ 7-8c worst) lands in the section
  whose own comment (kernel.asm:885-887, 916-918) records the worst path at
  69c/72 start-to-start, `sta WSYNC` ≤ c73 — a 1c miss is the documented
  263->264-line flicker class.
- Staging the color needs a write at 8 `sta ObjBase` sites
  (kernel.asm:1916/1924/1945/1972/1994/2024/2062/2071) ≈ 5 B each (~40 B),
  which eats most of the 47 B before any cycle risk is counted.
- `tools/test_miner_colors.py` pins the tab bytes at `$FE00`; the miner rows
  are a user-visible feature (per-row purple/pink/grey), not dead data.

## 4. PF row pool 135 -> 81 — SKIPPED (12 blocks, not 15; net ~13 B)

Re-measured on the live build (after C1): **12 blocks x 3 bands = 36 rows,
108 B, 12 distinct triples** (the audit's 135 B / 45 rows predates the C1
dedupe and the block count). Pool = 12 triples x 3 B = 36 B, plus one index
byte per band = 36 B, i.e. 72 B for what is now 108 B: **36 B raw**.
The reader change (`bank3.B3RoomBlocks`' 9-byte straight copy, currently
`lda (FetchPtr),Y / sta PF0Buf,Y / iny / cpy #9`) becomes an
index->triple expand loop: `asl/clc/adc` for `idx*3` + three `abs,Y` stores
≈ +23 B of bank3 code, and it moves the room meta from `TilePF0+9/+10` to
`+3/+4`, i.e. it breaks the documented block contract and the six hardcoded
`+9` reads in `tools/test_cell_map.py`. Net ≈ **13 B** for a medium-risk
reader + contract change — below the "worth a chunk" line.

## Deviations

- Cut order: C1 first (as briefed). Items 2 and 4 re-measured against the
  post-C1 tree, so their block counts differ from the audit's.
- No item touched `src/rooms/`, `models.json` or `src/generated` by hand:
  `src/generated` changes are converter output from `./build.sh`.

