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


## Bank3 move, next design (tail-call, zero stack) — 2026-10-19 second attempt

The two-pass symbol export WORKED (build + verify green), but `sim_bomb_fuse`
died: the HOV/crunch chain pushed SP to $F7 (BombTimer) and then wrapped. The
new `jsr ReadB3` frames inside `EnterRoomB2`/`StageBandTab` added stack levels
to a chain that already sits on the floor. Two lessons:

1. **Never add a `jsr` to the room-load or VBL chain** — both are at the
   measured stack floor. Use the project's tail-call/tramp pattern instead
   (`sta $1FFx` + `jmp`, return via `$FBF8`/`$FBEE`), which pushes nothing.
2. A bank3 read stub that must RETURN to bank2 costs one jsr level; a bank3
   body that FINISHES the job can be tail-entered for free.

Redesign (all zero-push):
- **EnterRoomB2 stays in bank2** for everything that reads bank2 (room table,
  RoomEnemies, enemy records). Reorder it so the BLOCK work (rect unpack +
  9-byte PF copy) is LAST, then `sta $1FF9 / jmp B3RoomBlocks`.
  `B3RoomBlocks` (bank3) unpacks rects into `RcBase/RcW1` and copies PF into
  `PF0Buf`, then `jmp $FBF8` (ReturnPad -> bank0). Must preserve X
  (EnemyCount is EnterRoom's return contract) — use Y + a ZP scratch for the
  cache index instead.
- **StageBandTab moves to bank3 entirely** (it only reads the block meta).
  `BuildColupF`'s tail becomes `sta $1FF9 / jmp B3StageBand` (tail, twin jmp
  image in bank3); the body ends `jmp $FBF8`. Bonus: ~150 B leave bank2.
- **Moth/LaserHitTest records stay in bank2** (only blocks move), so no
  reader changes there; the VBL band-color read is already gone.
- Tramp/twin addresses must be free in BOTH banks; the measured free pairs
  are `$FC3E-$FC48`, `$FCDF-$FCEF`, `$F800-$F87F` (bank2) and
  `$F800-$F87F`, `$FCDF-$FD7A` (bank3).
- Two-pass label export (`--sync-bank3-labels`) stays as implemented.

Then, and only then, the ~10-15 ROM-byte tests that read block bytes must
switch to `BANKS[3]` + `bank3.lst`.
