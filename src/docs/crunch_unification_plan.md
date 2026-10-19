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

## STATE SNAPSHOT — 2026-10-19, end of chunk A2 (commit `78d996b`)

Everything below is measured, not estimated. Tree green: build + both sims +
42-test battery + title demo; frozen banks re-frozen.

### Actual sizes

| bank | code | data | used | free | largest contiguous hole |
|---|---|---|---|---|---|
| bank0 | 3180 | 360 | 3540 | 556 | — (1 B pre-pad headroom; byte-frozen) |
| bank1 | 2628 | 554 | 3182 | 914 | fragmented |
| bank2 | 2513 | 748 | 3261 | 835 | **192 B** `$F404-$F4C3` |
| bank3 | 1019 | 74 | 1093 | 3003 | **1102 B** `$F3B2-…`, 587 B `$F161-…`, 300 B |
| **total** | **9340** | **1736** | **11076** | **5308** | |

level data (in bank2 spill slots `$F700-$F800` 256 B, `$F901-$F970` 111 B,
`$F9D9-$FB84` 427 B): index 56 + tables 334 + models 166 = **556 B**.

Fill/pad tax inside the 16K (pinned tramps, `.ds` slots, byte-identical twin
images): **4571 B** — bank0 554, bank1 552, bank2 813, bank3 2652. This is why
every 150 B feature costs a reshuffle: the free space is 100 B holes.

### Capacity answer (asked 2026-10-19)

- **Code in bank0+bank1 only: impossible.** Code alone is 9340 B vs 8192 B
  available (-1148 B), before the 1736 B of data and 556 B of level data.
- **bank0+bank1 + half of bank2: not reachable today.** 11076 B used vs 10240 B.
  Short 836 B *and* bank0 is 1 byte from its pre-pad limit; it would need
  ~800-1000 B of content deleted plus a full repack.
- **Reachable target: code in bank0 + bank1 + a *part* of bank2, bank3 = the
  data/content bank.** After A3 bank2 falls to ~2100-2500 B (51-61%) and bank3
  carries the level data plus ~3.3 KB of contiguous free space.

### What the chunks actually bought (honest accounting)

- C1 -10 B, **A1 -22 B** (bank2), **A2 -170 B** (bank2). A1/A2 were
  *prerequisites*, not the payoff: they removed the `(RoomPF0Lo),Y` block reads
  so the VBL chain could leave bank2. Net so far: **bank2 3453 → 3261 used,
  free 643 → 835, biggest hole 99 → 192 B**.
- **A3 (level-data move) is the payoff** and the next real gain: -556 B of data
  from bank2 plus ~600 B of block readers that must follow it to bank3
  (PhaseBlink, BuildColupF's hot-rect walk, HotOverlapBody, EnterRoom's tail).
  That is the whole-layout rebuild (convert split + two-pass build + test
  migration), not a hole-hunt.
- C2/C3 after A3 are cheap (-150…-200) and need no hole arithmetic.

### Standing rules learned here (do not relearn)

1. A bank2↔bank3 pad is ADDRESS-sensitive: the twin is the first byte fetched
   post-switch, i.e. at **sta+3**; the pin must be `.ds <addr>` placed BEFORE
   the block label (inside the block it is a BRK in the fall-through path).
2. `sim_bomb_fuse` runs BEFORE the ROM is concatenated, so it validates the
   *previous* savior.bin — after a chain change, `cat bank*.bin > savior.bin`
   by hand before trusting a sim result.
3. PhaseBlink must run AFTER SBT's band/ball staging and BEFORE the pack
   (`VcrShutter` overwrites Temp/BandTab for the shutter cell).


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


## Chunk A1 — room meta staged at entry (`RoomMetaA/B`), 2026-10-19

**Why first:** the level-data move's real blocker is not the data — it is
that bank2 READS block bytes in 12 places (StageBandTab ×6, LaserWallClamp,
PHMOverlay, M1StripBlast, PhaseBlink, HOVFeatPre, PhHcrPre, OvShutBand,
OvShutScan). A block moved to bank3 turns every one of those into a garbage
read. Staging the two meta bytes at room entry removes the whole class:

- `EnterRoomB2` already copies the 9 PF bytes through `FetchPtr`; the copy
  loop leaves **Y = 9**, so MetaA/MetaB are the next two `(FetchPtr),Y`
  reads — 8 bytes, no `ldy`, and they land in the now-dead pointer pair
  `$99/$9A` (`RoomMetaA/B`). The block pointer itself is dead after that
  (nothing else reads it).
- Every meta reader becomes `lda RoomMetaA/B` (3 B instead of
  `ldy #n / lda (RoomPF0Lo),Y`, 5 B). This is what makes StageBandTab
  ZP-only — the prerequisite for moving it (and later the data) to bank3.
- Two bytes were freed in EnterRoomB2 to pay for the staging: the redundant
  `lda #0` before the bomb reset, and the enemy-record read turned into a
  3-byte loop over the contiguous `EnemyDataLo/Hi/Count` ($B1-$B3).
- `MothRoutine` moved `$F100 → $F110` (its region had slack) so the body
  fits; the `$FEF0` moth tramp operand was updated in **both** banks.

**Trap hit (cost most of the session):** three bank2↔bank3 pads are
ADDRESS-sensitive — bank3 keeps a byte-image at a fixed address while the
bank2 half is `sta $1FF9 / jmp body`. The meta rewrite removed `ldy #10`
from `HOVFeatPre`, `PhHcrPre` and `OvShutScan`, which shifted each pad by 2
bytes; the jmp then landed on bank3 fill (`$00` = BRK → reset vector →
GameStart reset loop). Symptom: crunch tests boot, then the game silently
restarts (DropTarget becomes `$FD`). Fix = `.ds <addr> - *, 0` **before the
block label** (a pad inside the block sits in the fall-through path and is
itself a BRK). Pins now: `$FBFE` HOVFeatPre, `$FC20` PhHcrPre, `$FE4A`
OvShutScan → tramps at `$FC18/$FC31/$FE54`, jmps at `$FC1B/$FC34/$FE57`.
**Rule: any size change in a bank2 block that owns a bank3 twin needs a
re-check of the twin alignment, and the guard should pin the BLOCK start,
not the jmp.**

Tests updated (staging moved from the block pointer to the ZP pair):
`test_bomb_strip`, `test_cell_map`, `test_laser_close`,
`test_laser_kill_window`, `test_laser_walk_wall` (shared `load_room`),
`test_phase_kill_frame`, `test_vcr_shutter`, `test_hcrunch` (MetaB poke),
`test_laser_s4`/`test_phm_walk` (source asserts now look for `RoomMetaA`).

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3180 | 360 | 554 | 3540 | 556 |
| bank1 | 2628 | 554 | 552 | 3182 | 914 |
| bank2 | 2683 | 748 | 643 | 3431 | 665 |
| bank3 | 824 | 69 | 952 | 893 | 3203 |
| **total** | **9315** | **1731** | **2701** | **11046** | **5338** |

delta vs C1: bank2 code **-22 B** (used 3453 → 3431). Bank2's largest
contiguous hole is unchanged (**99 B**, `$FB6D-$FBCF`), so C2 still needs
the StageBandTab move below.

**Next chunk (A2):** move `StageBandTab` (~195 B, now ZP-only) to bank3.
`BuildColupF`'s tail becomes `sta $1FF9 / jmp B3StageBand` (twin jmp in
bank3, same -2/+2 pin discipline). PhaseBlink stays in bank2 (it walks the
rect stream) and is reached from bank3 as a tail ping-pong:
`sta $1FF8 / jmp PhBlink` → bank2 body → `sta $1FF9 / jmp SBT_tail`
(0 pushes, VBL jsr still returns via ReturnPad). That opens a **195 B
contiguous hole at `$F401-$F4C3`**, which is what C2 (PhHcrEntry + HcrPush
+ HcrClock into bank2) needs. Then A3 = the data move itself
(convert `level_00N_blocks.asm` + two-pass build + the remaining rect-walk
readers: PhaseBlink, BuildColupF's hot walk, HotOverlapBody, EnterRoom tail).


## Chunk A2 — `StageBandTab` moved to bank3 (`B3StageBand` @ `$F0A3`), 2026-10-19

The A1 staging paid off: SBT was already ZP-only, so the move needed no read
tramp. What it DID need is ordering — this is the whole subtlety:

- **PhaseBlink must run AFTER SBT's band/ball staging and BEFORE the pack.**
  It is not a "phase cell" pass only: the `$81` path tail-jumps into
  `VcrShutter`, which **overwrites `Temp` (BallX) and `BandTab` for the
  shutter cell**. Calling PhaseBlink first (the obvious "move the jsr to
  BuildColupF" version) let SBT's own staging erase the shutter, and every
  crunch kill stopped latching (`test_vcr_shutter` / `test_phase_kill_frame`
  caught it: "no latch (state=$1B)"). So the body is split at the old jsr:
  part A (band mask, M1X, CTRLPF, BallX, NUSIZ1) → ping-pong → part B (pack).
- **Ping-pong, 0 pushes, both legs pinned:**
  - bank2 `BCFDarkRun` tail `$F3A9`: `sta $1FF9 / jmp $F0A3`
  - bank3 `$F3AC`: `jmp B3StageBand` (byte-image; **sta+3**, not sta+6 — the
    jmp OPCODE is the first byte fetched post-switch)
  - bank3 part A end `$F124`: `jmp $F800` → bank3 `$F800` `sta $1FF8` → bank2
    `$F803` `jmp PhBlinkTail` → `jsr PhaseBlink` → `sta $1FF9` → bank3
    `$F80C` `jmp SBT_B`
  - bank3 `$FBF8` now carries its own `ReturnPad` (`sta $1FF6`; the `rts`
    opcode is fetched bank0-side) — without it the exit executed bank3 fill.
- Test: `test_bomb_strip` drives `B3StageBand` from `bank3.lst` with
  `mem.bank = 3`; it now exercises the real ping-pong (the phase case walks
  PhaseBlink the way the VBL does).

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3180 | 360 | 554 | 3540 | 556 |
| bank1 | 2628 | 554 | 552 | 3182 | 914 |
| bank2 | 2513 | 748 | 813 | 3261 | 835 |
| bank3 | 1019 | 74 | 2652 | 1093 | 3003 |
| **total** | **9340** | **1736** | **4571** | **11076** | **5308** |

delta vs A1: bank2 code **-170 B** (used 3431 → 3261), bank3 code +195 B.
**bank2's largest contiguous hole is now 192 B (`$F404-$F4C3`)** — C2
(PhHcrEntry + HcrPush + HcrClock ≈ 150 B into bank2) is unblocked.

**Next: C2** — move `PhHcrEntry`/`HcrPush`/`HcrClock`/`CrPfx*` from bank3 into
the `$F404-$F4C3` hole and merge the PF staging with bank2 `VcrShutter`.
Keep the tramp/twin discipline: `$FC34` (PhHcrPre → PhHcrEntry) becomes a
local `jmp` once the body is in bank2 (delete the bank3 twin), and the
`$FCC1-$FCDD` return pads collapse to `jmp PhNext`/`jmp HOVnext` in bank2.

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
