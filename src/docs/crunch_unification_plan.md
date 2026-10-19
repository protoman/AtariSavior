# Crunch unification — plan + size ledger

Status: **in progress** (started 2026-10-19). Goal: shrink the vcrunch/hcrunch
subsystem (~1.5 KB between bank3 bodies and bank2 staging) without changing what
the player sees. Every chunk lands as its own commit, build + both sims + full
battery green, and the ledger below is updated in the same commit — that is the
tripwire if a later chunk misbehaves: diff the ledger, find the chunk.

## Behaviour that must NOT change (user rulings)

- vcrunch: sprite-slice shutter over the middle band; cold kill only while
  closing and only when the player is fully inside closed slices; hot band kills
  on touch; a closed shutter is a SOLID block (no walking through); one kill per
  room visit (b7 latch); side brushes never kill.
- hcrunch: prefix band from col 0; cold kill while closing (sc < 52) at any
  extent; hot exempt; grow-to-center push (HcrPush) keeps a cold shutter from
  sealing the player inside; kill latch once per visit.
- Both: kill test runs on the same clock the kernel rendered (EnemyRamP-1), and
  the record walk stays in PhaseBlink.

## Chunk list

| chunk | content | expected |
|---|---|---|
| C1 | merge `HOVFeatEntry` + `HOVvcrunch` + `HOVhcrunch` into one dispatcher (shared field drain + latch) | ~ -100 B |
| C2 | share the PF staging between `VcrShutter` (bank2) and `PhHcrEntry` (bank3) — needs both in one bank | ~ -80..150 B |
| C3 | fold `HcrPush`/`HcrClock` into the staging path, drop the bank3 tramp + pads | ~ -40 B |
| C4 | drop the retired legacy twin images (`jmp $F800`/`jmp $F880` fill) and re-pin the pads | ~ -6 B |

C2 is the structural one; it may require the level-data move to bank3 first
(bank2 needs the room).

## Size ledger

Measured with `tools/rom_size_report.py --md` (DASM listing-based; code vs data
vs fill, plus generated level-data bytes).

### Baseline (start of crunch work, commit `61fcd15`)

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3180 | 360 | 554 | 3540 | 556 |
| bank1 | 2628 | 554 | 552 | 3182 | 914 |
| bank2 | 2705 | 748 | 617 | 3453 | 643 |
| bank3 | 834 | 69 | 942 | 903 | 3193 |
| **total** | **9347** | **1731** | **2665** | **11078** | **5306** |

level data: index 56 + level tables 334 + models 166 = **556 B**

### C1 — single HOV dispatcher (`HOVFeatEntry` + `HOVvcrunch` + `HOVhcrunch` merged)

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3180 | 360 | 554 | 3540 | 556 |
| bank1 | 2628 | 554 | 552 | 3182 | 914 |
| bank2 | 2705 | 748 | 617 | 3453 | 643 |
| bank3 | 824 | 69 | 952 | 893 | 3203 |
| **total** | **9337** | **1731** | **2675** | **11068** | **5316** |

delta vs baseline: code **-10 B** (bank3), used -10 B. Level data unchanged
556 B. (The merge removed the jsr/rts pair + one drain, but the two arms'
bounds checks and the near-trampolines cost most of it back — C2/C3 carry the
real weight.)

**Trap hit and fixed in C1:** the old `HOVvcrunch`/`HOVhcrunch` were entered
with `jsr`, so their `tsx` field offsets assumed a 2-byte return address on
top. Merging them into the entry removed that word — every offset shifts by
−2 (h=$0101, w=$0102, y=$0103, x=$0104). The first build was "green" only
because the frozen test banks still held the OLD code; `freeze_test_banks.sh`
+ battery exposed 4 failing hcrunch cases. **Lesson: re-freeze before
trusting a battery run after any bank code change.**


## Level-data move to bank3 (started 2026-10-19, reverted to keep green)

Goal: free bank2 for the crunch consolidation. Blocks (model + per-room
PF/meta/rect) move to bank3; the small tables (RoomDataTable, connections,
enemy records, RoomEnemies) stay in bank2.

Done and reverted in the same session (working but not committed):
- convert split: `level_00N_blocks.asm` (blocks) + `spill_bank3.asm` list;
  tables stay in `level_00N_rooms.asm`;
- bank3 stubs at `$F0A3`: `B3Read` ((FetchPtr),Y), `B3ReadPF`
  ((RoomPF0Lo),Y), `B3CopyPF` (9 B -> PF0Buf); all return through `$FBEE`;
  twin `jmp` images at `$FC41/$FCE2/$FCE8`;
- bank2 tramps at `$FC3E` (`ReadPFB3`), `$FCDF` (`ReadB3`), `$FCE5`
  (`CopyPFB3`) — those three addresses are free in BOTH banks;
- `EnterRoomB2` rect unpacking reads through `ReadB3` (pha/pla per byte);
  the PF copy goes through `CopyPFB3`; `StageBandTab` reads MetaA once +
  MetaB through `ReadPFB3` (M1OffTab moved to the `$F3BC` gap).

**Blocker:** each bank is assembled separately, so bank2's level tables
cannot reference block labels defined in bank3's include
(`M5TilePF0`, `L3R1TilePF0`, …) — DASM stops with "Unresolved Symbol".

Two ways forward (both keep 16K):

1. **Two-pass assembly + exported EQUs (recommended).** Assemble bank3
   first, dump its symbols (`-s`), keep only `M<digits>*` / `L<digits>R<digits>*`,
   emit `generated/bank3_labels.asm`, and `include` it in bank2. The table
   `.word`s keep resolving symbolically and — importantly — `bank2.lst`
   still shows those labels as EQU rows, so most tests keep parsing the same
   file. Reorder build.sh: convert → bank3 (pass 1) → bank2 → sync-phrec →
   bank3 (pass 2) → bank0 → bank1.
2. **Literal index/table addresses.** convert computes the bank3 block
   layout itself and emits numeric pointers. No build reorder, but every
   `.word` becomes a literal and `verify_build` needs a label-vs-literal
   cross-check.

Migration after either: ~10-15 ROM-byte tests read block bytes from
`BANKS[2]` (`test_bomb_strip`, `test_bomb_user_sequence`, `test_laser_*`,
`test_hcrunch`, `test_cell_map`, `test_fixtures`, …) and must read `BANKS[3]`
plus labels from `bank3.lst`. `test_editor_roundtrip`/`test_level_bank` are
unaffected (they use generated text, not addresses).

Estimated: two-pass build ~30 lines in build.sh/verify_build; test migration
mechanical but touches 10-15 files.
