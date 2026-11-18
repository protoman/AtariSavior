# ROM bank plan

_Which bank holds what, today and as planned: code first, then room models, then levels. Every bank carries the boot stub._

**Status: PLAN (user rule 2026-11-13). Nothing below the "Target layout" heading is implemented yet.**
The current map is measured; the target map is a plan whose sizes are ESTIMATES until the survey
(phase 1 below) has been done. When the layout changes, update this file in the same commit.

## The rules (user, 2026-11-13)

1. **Code first, data last.** Banks are filled in this order, from bank0 up:
   **general code -> cave code -> gameplay code -> HUD code -> other code -> room models -> levels.**
   The LAST banks are for level data, so growing the stage never competes with code.
2. **Every bank has the boot stub**, whatever it holds (see "Boot code" below).
3. **A routine only reads data that is in its own bank** (the F4 switch swaps the whole 4 KB window).
   Anything that reads level or model data runs in the bank that holds that data, or hops to it with the
   pinned-address hop (the shape step in bank7 today is the working example, `docs/agents/level_data_and_generator.md`).
4. **No new feature goes into a full bank** (bank0 is full and byte-frozen): extend the code zone instead.

## Boot code (every bank, no exceptions)

Real hardware powers up with an UNDEFINED bank latch, so any of the 8 banks can be the first one fetched.

- `$F000`: `lda #0` / `sta $1FF4` (5 bytes, `A9 00 8D F4 1F`) selects bank0; the next fetch comes from
  bank0, whose `$F005` is `jmp GameStart`. The bytes after the stub in banks 1-7 can be anything.
- The vectors at `$FFFA-$FFFF` (NMI, RESET, IRQ) all point to `$F000` in every bank.
- Guard: `tools/verify_build.py check_boot_banks` checks all 8 banks. A bank that ships without the stub is
  a 1-in-8 chance of a dead boot on real hardware (bank5 and bank6 had none until 2026-10-28).
- A new bank, or a bank that gets re-organised, keeps the stub at `$F000` and nothing else at `$F000-$F004`.

Bank select hotspots (F4): `$1FF4` bank0, `$1FF5` bank1, `$1FF6` bank2, `$1FF7` bank3, `$1FF8` bank4,
`$1FF9` bank5, `$1FFA` bank6, `$1FFB` bank7.

## Current layout (measured 2026-11-13)

"Used" is the real content (non-padding bytes in the assembler listing); free space is padding, so the
numbers are approximate. The ROM is NOT full: about 14 KB is free, but in the wrong banks.

| Bank | Used | Free | Holds today |
|---|---|---|---|
| 0 | 4.0 KB | 0 | general kernel: main loop, input, physics, collision, sound, positioning, the fold pads (pinned, byte-frozen) |
| 1 | ~3.5 KB | ~0.6 KB | HUD (score, bars), title and level select, raft body, bomb wall marks, strip blast |
| 2 | ~3.5 KB | ~0.6 KB | level ROOM half: room readers/exits/laser/moth/blast code plus the room tables (windows `_SPILL_SLOTS`, 2,019 B) |
| 3 | ~2.3 KB | ~1.7 KB | level EXTRAS half: extras walkers (phase, hcrunch, hot, dark, colours) plus the extras data (window `$F010-$F44F`, 1,088 B) |
| 4 | ~1.6 KB | ~2.4 KB | save-to-cartridge (I2C SaveKey) + the room models: shape step, shape blocks, row pool (window `$F4C0-$FBF7`; moved here from bank7 on 2026-11-14, role `BK_MODELS`) |
| 5 | ~0.5 KB | ~3.6 KB | version header, blank room-transition frame, attract-mode script |
| 6 | ~2.3 KB | ~1.8 KB | the generated gameplay cave kernel |
| 7 | ~1.2 KB | ~2.9 KB | cave kernel start-up code only (the shape window moved to bank4) |

Why it looks like this: banks 0-3 were full, so every new feature got a NEW bank (save in 4, transition and
demo in 5, cave kernel in 6, prologue and shapes in 7). Nobody consolidated afterwards, which is why bank4
(0.7 KB used) has more room than bank7.

### Level data budget (measured with the live generator)

| Stage | Room tables (bank2) | Extras (bank3) | Room models |
|---|---|---|---|
| 20 levels, 211 rooms (today) | 1,418 B of 2,019 B | 866 B of 1,088 B | 121 shapes |
| 32 levels, 529 rooms (planned) | 3,393 B + index | 2,155 B | ~126 shapes |

32 levels overflow the current windows (rooms at level 22-26, extras earlier). The fix is not "more ROM", it is
moving level data to the last three banks.

## Target layout (plan)

Code in the first banks, in the order the user gave; models after the code; levels last.

| Bank | Zone | Holds | Est. size |
|---|---|---|---|
| 0 | **General code** | main loop, input, physics, collision, sound, positioning, fold pads. Byte-frozen: stays as it is | 4.0 KB |
| 1 | **Cave code** | the generated cave kernel (now bank6) plus its VBL prologue (now bank7) | ~3.5 KB |
| 2 | **Gameplay code** | enemy movement (moth walk, UpdateEnemies helpers), laser clamp/hit, bomb blast, stage slot staging, exit scan/pending, raft, bomb wall marks, strip blast | ~4.0 KB |
| 3 | **Gameplay code (cont.) + HUD code** | phase/hcrunch/hot/dark/colour walkers (now bank3), HUD bars and score, title and level select (now bank1) | ~3.1 KB |
| 4 | **Other code + room models** | save-to-cartridge (I2C), version header, blank transition frame, attract-mode script (~1.2 KB), then the shape blocks, row pool and shape table (now the bank7 window, ~0.9 KB used today, cap 128 shapes ~1-1.3 KB). The ~1.5 KB left is code growth buffer | ~2.5 KB (+1.5 KB spare) |
| 5 | **Levels A** | levels 1-N: boot stub, level-data service, room tables, extras | see below |
| 6 | **Levels B** | levels N+1-M (same layout and same service addresses as bank5) | see below |
| 7 | **Levels C** | levels M+1-32 (same again) | see below |

(Other code and the room models share bank4, which frees a third level bank: user rule 2026-11-13.)

Sizes of code zones are estimates (sum ~15.8 KB of code into banks 0-4, with models); the survey fixes the real assignment.

### The level banks

- Each level bank (5, 6, 7) holds the boot stub, a small **level-data service** at FIXED addresses (identical in
  all three level banks), then data. The room loader chooses the bank by `Level` (a three-way split of the
  levels) and hops to the service, the way `EnterRoomB2` hops to the shape step today.
- The service does everything that touches level data: copy the room record (shape index, position, enemy count,
  the enemy records), find the extras record, and hop on to the model bank for the shape step, which ends in
  the usual return pad (the model bank is bank4 now, one hop). Code that needs level data later reads the RAM copy, not ROM.
- Budget: rooms 3.4 KB + extras 2.2 KB + index 0.2 KB = ~5.8 KB for 32 levels, plus three service copies
  (target <= 0.8 KB each = 2.4 KB): fits in 12 KB with ~3.8 KB left for more or bigger levels. The
  converter fills bank5 first, then bank6, then bank7.
- Today's readers of level data that must move behind the service or switch to RAM copies:
  `EnterRoomB2`, `ExitScanB2`/`ExitDirB2` (room positions), `LoadLevelB2` (level start), `MothRoutine` and
  the spawn-X reads through `FoldIndirect` (enemy table), `LaserWallClamp`/`LaserHitTestBody`,
  `BombEnemyBlastBody`, `ExtrasLoad`/`B3Meta`/`B3RoomBlocks` (extras), `ShapeStep7` (models).

## Method: build a NEW EMPTY ROM and fill it (user rule 2026-11-13)

Moving routines around inside the existing 32 KB image means shuffling pinned addresses in a ROM that is
packed and byte-frozen. If that is what the organisation needs, do NOT do it in place: **create a new, empty
ROM layout and fill it**, taking pieces from the old one.

- The new layout is a second set of bank sources (for example `src/banks/` or `bankN_new.asm`), built by a
  separate script, so the old ROM keeps building and keeps passing the battery until the switch.
- It starts EMPTY: 8 banks, each with only the boot stub and vectors (it already passes `check_boot_banks`).
- It is filled in the zone order of the target table: bank0 first, then 1, 2 ... Each routine is brought over
  with its own data and pinned addresses chosen fresh for the new layout, instead of being squeezed into
  whatever gap the old ROM had.
- A piece is "moved" only when the new ROM runs it correctly (the sims and the playbot run on BOTH ROMs while
  the two coexist); then the old copy is dead code and goes at the switch-over (deleting needs the user's OK).
- The switch-over is one commit: build.sh points at the new layout, the frozen test banks are re-frozen,
  the old sources stay in git history.

## How to get there (phases; each one builds, passes `verify_build` and the battery, and is committed alone)

0. **Done:** bank selectors by role (`banks.inc`, `BK_*`; the old ROM stayed byte-identical), the empty `newrom/` skeleton, and the room models moved to bank4 (`BK_MODELS`, 2026-11-14; playbot 20/20, tests green).
1. **Survey (no code).** For every routine: bank, size, callers, the data it reads, pinned addresses. Fill the
   assignment table in this file. Output: the final bank map and the real zone sizes.
2. **New empty ROM skeleton** (see "Method"): 8 boot-stub banks, a build script, `check_boot_banks` green.
   Then **level-data service**, first thing filled:  Build the service and the multi-window extras (bank3 has ~1.7 KB
   free: the extras base table already holds 16-bit pointers, so a level's stream can sit in any window) and give
   the room tables a second home, so 32 levels fit. Gate: 20-level stage byte-for-byte equal in behaviour,
   `test_level_bank`, playbot 20/20.
3. **Models next to the other code** (bank4) in the new ROM.
4. **Fill the new ROM in zone order** (general, cave, gameplay, HUD, other, models, levels). Every piece
   brings its own `sta $1FF4+n` pads, the pinned addresses checked by `verify_build`, the `bank*.lst` readers
   in tools and tests, the frozen test banks (`tools/freeze_test_banks.sh`) and the PAL/PAL60 variants.
   Then the switch-over commit.
5. **Generator.** `kStageLevels` -> 32, the room-count and level-bank split in `convert_level.py`, new
   `test_generator` budgets (per bank), and the usage audit the generator already prints.
6. **Release gate** (`tools/release.py --tag`) on the final layout.

## Finding 2026-11-14: why the level-data service is not "just move the data"

Measured while preparing step 2 (levels 21-32 do not fit bank2's windows: rooms 3,393 B needed vs 2,019 B):

- Eleven bank0 pads reach level data: `EnterRoom`, `ExitRoomDown/Up/Left/Right`, `StageSlot1`, `LoadLevel`,
  `BombEnemyBlast`, `LaserHitTest`, `UE_MothTramp` and `FoldIndirect`. Each is a fixed `sta BK_ROOMS` (3 bytes);
  bank0 has ~4 spare bytes, so no pad can pick a bank by level.
- Nearly every bank2 body reads enemy or room records through `FetchPtr`/`EnemyDataLo` IN bank2, and
  `FoldIndirect` (bank0, spawn-X reads of snake/moth/tentacle) is hard-wired to bank2. RAM has no room to copy
  the records out.
- So a level bank cannot be a data-only bank: it has to be a **twin of bank2** (same code at the same addresses,
  other data) with a way to get into it.

Design that fits (not built): bank5 becomes "bank2B" (identical code, data of levels 21-32). Each of the nine
level-reading pads keeps its `sta BK_ROOMS`; bank2's `jmp body` at pad+3 becomes `jmp Stub_i`, a ~10-byte stub
in bank2 that tests ONE spare zero-page bit with `bit zp` / `bpl` (no register is touched, so A/X/Y stay as the
pad contract needs), then `sta BK_ROOMS_B`; bank2B has `jmp body_i` at the byte after that `sta`. Open points: one
free ZP bit "level >= 21"; the `FoldIndirect` spawn-X readers (twin them through a second fold or move the spawn X
into the RAM enemy record); bank5's current content (version, transition, demo, ~0.5 KB) moves to bank4 (2.4 KB
spare); extras for levels 21+ go to bank3's free windows (`$F5CC-$F8B6`, ~0.75 KB, plus gaps). Capacity: bank2B
data windows ~2 KB, just enough for the rooms of levels 21-32 (1,975 B) - no margin; compressing the enemy
records (3 B each) is the lever if the levels grow.

## Decision 2026-11-14 (user): route 3 - the new ROM is designed so code reaches level data by level

The twin-of-bank2 patch (above) is NOT the plan. The new ROM is empty, so bank0 is laid out for this from day one:

- **Level banks carry their own readers.** Banks 5, 6, 7 each hold the level-reading code (the FetchPtr/EnemyDataLo
  readers and the bodies that use them, today's bank2) plus a share of the level data; a level lives wholly in one
  bank. Code is duplicated x3 (~2 KB each), data fills the other ~2 KB per bank.
- **Pads pick the bank.** The eleven level pads in bank0 select the bank with a flags-only test, no register touched:
  `bit LevelRoomN` (b7 = N, b6 = V) then `bmi`/`bvs` to one of three `sta BK_L5/6/7`. Cost ~12-15 B per pad.
- **The selector byte is LevelRoomN b7/b6** (no free ZP byte exists, but LevelRoomN is only read in bank2 and a level
  has <= 63 rooms): readers mask it with `and #$3F`, LoadLevel writes it. Nothing else changes in RAM.
- **FoldIndirect spawn reads** go through the same selector (a fold pad per level bank) or the spawn X moves into the
  RAM enemy record; decide in the survey.
- Extras (the bank3 half) move into the level banks too, so bank3's data windows disappear.

## Layout v2 (2026-11-14, awaiting user approval; supersedes "Target layout" and the route-3 sketch above)

Measured from the 2026-11-14 build (`bank2.lst`/`bank3.lst`, label spans; code = non-data bytes):

| Quantity | Bytes |
|---|---|
| bank2 total used / of which room data (20 levels) | 3,312 / 1,558 -> code ~1,750 |
| bank3 total used / of which extras data (20 levels) | 2,305 / ~900 -> code ~1,400 |
| 32-level data: rooms + index + extras | 3,393 + ~230 + 2,155 = ~5,780 |

**Why "copy all of bank2 into each level bank" does NOT work:** reader code ~1,750 + extras reader ~330 = ~2,080 B
per level bank leaves ~1,900 B of data room per bank, 5,700 B for three banks, against 5,780 B needed. No margin
and whole-level granularity wastes more. Rejected.

**What works: a THIN level service in each level bank, everything else reads through a fold.**

- *Level service* (identical code in banks 5, 6, 7, at the same addresses, each with its share of the data):
  `EnterRoomB2` (+`EBLER` loops), `LoadLevelB2`, the exit scan (`ExitScanB2`/`ExitDirB2`/`ExitFind`/`ExitPendingB2`,
  `SetRoomExits`), `ExtrasLoad`/`B3Meta`/`B3RoomBlocks`, and a read fold. Estimate ~1,000 B (sum of the label spans
  above: 230 + 130 + ~300 + ~330), + boot stub, vectors, ReturnPad ~100 B. Data room per level bank ~3.0 KB,
  9.0 KB for three, against 5.8 KB needed: **~3 KB margin** (even after whole-level granularity, ~0.3 KB per bank).
- *Entering the service:* the level pads in bank0 pick the bank by `bit LevelRoomN` (b7/b6) + `bmi`/`bvs`
  (flags only, A/X/Y untouched), ~12-15 B per pad.
- *Reading enemy/room bytes from gameplay code* (moth walk, laser tip/clamp, blast, stage slot staging, miner):
  these stop reading ROM with `lda (FetchPtr),Y` and use a read fold: pad in the code bank does the same bit-test,
  `sta BK_L5/6/7`; the level bank holds `lda (FetchPtr),Y / sta BK_<caller> / rts` at the next address. One fold
  per caller bank (bank0 already has `FoldIndirect`). Cost ~40 cycles per byte; the moth walk keeps its INTIM gate.
- *Everything else* moves to the code zone in the order the user gave:

| Bank | Zone | Holds | Est. used |
|---|---|---|---|
| 0 | general | main loop, input, physics, collision, sound, positioning, fold pads, level pads | 4.0 KB (full) |
| 1 | cave | cave kernel (now bank6) + VBL prologue (now bank7) | 3.5 KB |
| 2 | gameplay | moth, laser, blast, stage slot, miner, raft, bomb wall marks, strip blast, phase/hcrunch/hot/dark/colour walkers | ~3.3 KB |
| 3 | HUD | HUD, score, bars, title, level select | ~2.5 KB |
| 4 | other + models | save-to-cartridge, version, transition, attract, then shape blocks/row pool | ~2.4 KB (1.6 KB spare) |
| 5, 6, 7 | levels | boot stub + level service + data; converter fills 5, then 6, then 7 | ~3.0 KB data each |

Sizes of banks 2/3 are sums of today's label spans (code only); the ~14 KB of code plus ~1 KB of models fit in
banks 0-4 (20 KB) with ~4.8 KB spare.

**Three gates that decide whether this holds (each is cheap; build the 3-level-bank service last):**
1. *Reader inventory:* list every `FetchPtr`/`EnemyDataLo`/table read in bank2/bank3 code (94 lines in bank2) and
   mark it "in the service" or "needs the read fold". Fixes the service size (target <= 1.2 KB).
2. *Frame cost:* count fold reads per frame in the heaviest rooms (`test_frame_all_rooms` gate, 280 lines).
3. *Spare-bit check:* `LevelRoomN` readers all mask `#$3F` (readers are bank2-only; grep proves it).

## Bank0 budget survey (2026-11-14, user rule: keep >= 200 B free in bank0)

Measured: bank0 holds 4,050 B in 4,096 B (~46 B free). Level pads with the bit-test select would cost ~18 B each x 11
= ~200 B more, so the v2 sketch above (pads pick the bank) does NOT fit bank0. Corrected design:

- **Bank0 pads stay exactly as they are** (`sta BK_ROOMS`, 3 B). Bank2 becomes the **router/gameplay bank**: the
  `jmp body` it serves at pad+3 becomes `jmp Router_i`, a ~10 B stub in bank2 (`bit LevelRoomN` / `bmi` / `bvs` /
  `sta BK_L5|L6|L7`, flags only) and each level bank serves `jmp body_i` at the byte after its `sta`. Bank0 growth: 0 B.
  Cost: ~15 cycles per pad entry; `FoldIndirect` (7+ per frame) gets ~20 cycles more each - this is gate 2 (frame cost).
- **Stubs live in the gameplay bank (2)**, so bank2 no longer holds level data; its data windows become code room.
- **Reaching the 200 B reserve needs ~155 B moved out of bank0.** Candidates, with what the survey found:
  - `SelectActiveObject` (308 B) and `LaserInput` (173 B): single callers but tightly bound to bank0 (they call
    `SetObjectXPos`, `FoldIndirect`, `CallPad_*`, `LaserHitTest`; `SelectActiveObject` was moved out and REVERTED in
    A1 2026-10-20 for cycle cost). NOT clean candidates.
  - `TallyWork` (54 B, `TallyEntry` 66 B already trampolined) calls `CallPad_AddScore`, `PickupSnd`, `StartFrame`: needs
    return pads, ~20 B kept in bank0. Net ~35 B.
  - Other single-caller routines (`DropStep` 47, `CEH_KeyDisp` 44, `RefreshEnemyY` 59, `DeriveEnemyY` 63, `StepDown` 57,
    `Slot1Hook` 96, `PHMOverlay` 63, `OvShutBand` 51) are UNVERIFIED: each needs a caller/cycle/pinned-address check.
  - Conclusion: ~155 B is probably reachable by moving 3-4 of the small ones, but it is not yet proven. If it is not
    found, the reserve rule (user) stands and the plan changes, not the reserve.
- **New build guard:** the new ROM's `verify_build` fails if bank0 has < 200 B of padding.

## Gate results 2026-11-14 (`tools/measure_level_reads.py`, all 211 rooms, fire held and released, steady frames)

- **Reads that would become folds** (`lda (FetchPtr),Y` / `lda (EnemyDataLo),Y` executed in bank2 or bank3):
  worst frame 9 in bank3 (extras walkers; L6-L8 room 4), 12 in bank2 (moth/laser/blast/stage slot; L18 room 17),
  plus 8 bank0 `FoldIndirect` calls (L4 room 2, L18 room 17). Worst combined: 22 in L18 room 17.
- **Cost:** a fold is ~40 c against ~5 c for the direct read, so +35 c per read: worst room ~+500-700 c per frame.
  The VBL window is 2,880 c and the worst room uses 2,491 c (L7 room 6), i.e. **389 c of slack** (rule: >= 150 c).
  The extras walkers and `SelectActiveObject` run in the VBL. **Gate 2 FAILS: gameplay code cannot read level data
  through per-read folds.** (The bank0 pad stays; the problem is the readers, not the entry.)
- **Consequence for layout v2:** the code that reads level data every frame must live NEXT TO the data or read a RAM
  copy. Putting the walkers (~1,100 B) in the level banks makes the service ~2.1 KB: 3 banks x ~1.9 KB = 5.7 KB
  against 5.78 KB needed, i.e. it does not fit. Open options: (a) per-room RAM copy of the enemy records + extras
  (needs ~30-40 B of RAM that does not exist today), (b) four level banks, (c) a smaller extras format.
- **Bank0 reserve:** the closed cluster `PHMOverlay` + `OvShutBand` + `OvM1Block` (~227 B, calls only itself and
  `DoorLocked`) can move out; it was moved INTO bank0 in 2026-10-20 for cycles, so it costs a hop x3 per frame
  (check with `test_frame_stability`). `PickPlayerFrame` (49 B) calls nothing.

## Layout v3 (2026-11-14, after the gate results; supersedes v2)

Gate 2 killed v2's idea of folding every read. Capacity kills "readers x3". What is left is the cheapest shape that
keeps every per-frame reader next to its data: **two identical room banks (A, B) plus one extras bank**.

- **Rooms A / B (banks 6, 7), twins:** each holds ALL of today's bank2 code (~1,750 B: room entry, level load, exit scan,
  moth, laser, blast, stage slot, miner) + stubs/boot/vectors/ReturnPad (~250 B) = ~2.0 KB, and ~2.1 KB of room data
  (shapes, positions, counts, enemy records, level index). A holds levels 1..K, B holds K+1..32; K is chosen by bytes by
  the converter, the engine knows it as one equate. Room data needed 3,393 B + ~230 B index = ~3.6 KB against
  4.2 KB: **~0.6 KB margin** (before whole-level rounding, ~0.2 KB per bank).
- **Entering:** the bank0 pads keep `sta BK_ROOMS` (= A); A's `jmp body` at pad+3 becomes `jmp Stub_i` (~10 B, flags
  only): `bit LevelRoomN` (b7 = level >= K) / `bpl` to the body / `sta BK_ROOMS_B`; B serves `jmp body_i` after that
  `sta`. Bank0 growth: 0 B. `FoldIndirect` gets the same stub (+~15 c x 8 per frame = ~120 c of the 389 c VBL slack).
- **Extras bank (5): walkers + all extras data** for the 32 levels: the bank3 code that reads extras every frame
  (hot overlap, phase, hcrunch, `ExtrasLoad`, ~1.4 KB) + 2,155 B of extras = ~3.6 KB; the non-extras bank3 code
  (stage band, colour build, ~0.6 KB) moves to a code bank to widen the margin to ~0.9 KB.
- **Code zone (banks 0-4):** 0 general (>= 200 B free), 1 cave, 2 HUD + title, 3 raft/bomb marks/strip blast + stage-band
  and colour code, 4 save + version + transition + attract + models. ~13 KB of ~16 KB used.

| Bank | Zone | Holds |
|---|---|---|
| 0 | general code | as today, level pads unchanged, >= 200 B free |
| 1 | cave code | kernel (now bank6) + prologue (now bank7) |
| 2 | HUD code | HUD, score, bars, title, level select (now bank1 minus raft etc.) |
| 3 | gameplay code | raft, bomb wall marks, strip blast, stage band, colour build |
| 4 | other code + models | save, version, transition, attract, shape blocks, row pool |
| 5 | levels: extras | extras walkers + extras data, 32 levels |
| 6 | levels: rooms A | room code (twin) + room data, levels 1..K |
| 7 | levels: rooms B | the same code + room data, levels K+1..32 |

Levels stay last (banks 5-7), code first, every bank has the boot stub. Gates for v3: (1) stub + FoldIndirect cost
measured in the old ROM (`test_frame_all_rooms`, VBL slack >= 150 c); (2) A/B code identical except data (guard in
`verify_build`); (3) bank0 cluster `PHMOverlay`+`OvShutBand`+`OvM1Block` moved out, hop cost measured; (4) the converter
splits levels by bytes between A and B and reports the margin.

## Progress log

- **2026-11-14: bank5 emptied.** The blank transition frame, the attract script and the version header moved to
  bank4 (`trans.inc`, version at `$FC70`; twin pads `$FBD0/$FC08/$FC20/$FC58-$FC64`); `BKI_TRANS = 4`. Bank5 is now
  boot stub + vectors only, reserved for levels. The shape window cap dropped to `$FBD0` (`_BANK3_SHAPES_SLOT`).
  `verify_build` follows the roles (`_CODE_BANKS`, `TRANS_PADS`). Battery 93/93 after fixing `test_room_transition`
  and `test_tally` (they hard-coded bank 5). Next: physical order (cave to 1, HUD to 3, extras to 5, rooms to 6)
- **2026-11-14: 32 levels run (layout v3 built in the OLD bank order).** Room banks A (bank2) and B (bank5 = `bank2.asm`
  assembled with `ROOMS_B = 1`) hold levels 1-23 / 24-32 (the converter picks the largest prefix that fits A; the rest
  must fit B). Every bank0 pad is unchanged (`sta BK_ROOMS`); A's slot at pad+3 is `jmp Stub_x` (`RSTUB` macro; `bit
  RoomExits` b7 picks the bank, set by LoadLevel / SetRoomExits). `FoldIndirect` reads through `Stub_Fold`. Extras of all
  32 levels sit in five bank3 windows (first-fit). Guards: `check_room_banks`, stub-aware pad checks (`_bank_bytes`).
  **Capacity is the limit:** the room tables pack only up to 20 rooms per level (22 does not fit: fragmentation of the
  eight windows at ~93% fill), so the generator caps levels at 20 rooms. More rooms need more window space (smaller
  records, one more room bank after merging the cave prologue, or code moved out of A/B). Frame budget: heavy rooms
  have ~0-1 timer units of overscan left; fixes in kernel.asm: `UEEpilogue` drops the extra pass on a wrapped INTIM,
  `.WaitOverscan` leaves at once when the timer already expired (the 7-cycle poll could skip the zero and spin
  256-cycle laps = 304-line frames), `UE_MIN_INTIM` 16. The generator never puts a moth AND a snake in a room with two
  async strips. Not done: the physical bank ORDER of the target table (cave to bank1, HUD after gameplay, levels in
  5-7) - the roles still sit in the old banks (rooms 2 + 5, extras 3, cave 6, prologue 7); bank0 still has only ~45 B
  free (the >= 200 B reserve needs the `PHMOverlay` cluster moved out, ~227 B).
  Results: battery 93/93, playbot 32/32 levels, `test_frame_all_rooms` 902 runs OK.

  and the room-bank twin (bank 7).

## Lesson: survey the READERS before planning where data lives

2026-11-14: the plan said "levels last, banks 5-7" without tracing which code reads the level data. Data can only be
read by code that runs in the same bank, so placement of data and placement of its readers must be planned together.
Every future "move X to bank N" step starts with a reader/caller survey of X.

## Open questions (answer in the survey)

- Exact size of the level-data service per bank, and whether the enemy-table readers can all use a RAM copy.
- Whether the cave kernel (generated, `tools/cave_kernel_gen.py`) can move to bank1 without its pinned hops.
- Frame cost of the extra hop on every room load (the load runs in the blank transition frame today).
- Which pinned addresses (`$F453`, `$FC49`...) have to follow their routine and which stay put.
- Where the split points between level banks fall (by bytes, so each level lives wholly in one bank).

- **2026-11-14 (restart in `newrom/`): bank 0 and bank 1 filled.** The reorg is done by FILLING `newrom/` in plan order (the
  original ROM is not touched; `tools/build_newrom.sh`, role map in `newrom/banks.inc`). Bank 0 = `kernel.asm` without the
  overlay cluster (316 B free, 227 in one run at `$FAED`); `OverlayTramp` hops with `sta BK_OVERLAY`, the cluster is placed
  when its bank is filled. Bank 1 = the cave kernel (old bank6, generated into `newrom/generated`). **Finding:** cave + prologue
  do NOT share a bank (8 table pages = 2 KB pinned to `$F8-$FF` + ~1.7 KB of kernel code; the plan's ~3.5 KB was wrong), so
  the prologue (~0.6 KB with its tables) goes to the gameplay code bank 3 (`BKI_PROLOGUE = 3`).
- **2026-11-14 (newrom): banks 2 and 3 filled.** Bank 2 = HUD, title, level select, score, sound, tally, music (old bank1 minus the
  gameplay set; 2,398 B). Bank 3 = the prologue (old bank7) + raft, strip blasts, `ClearPFColumn`, `BombMarkWalls` (cut out of old
  bank1; the pads of bank0 use `BK_GAMEPLAY`; pinned addresses kept: RaftBody `$FDE3`, BombMarkWalls `$FB10`, ReturnPad `$FBF8`).
  **Finding:** the stage band and the colour build do NOT go to bank 3 yet: `BuildColupF -> B3StageBand -> jsr PhaseBlink`, and
  `PhaseBlink` walks the extras streams, so they stay with the extras walkers (bank 5) unless PhaseBlink is reworked.
- **2026-11-14 (newrom): banks 4-7 placed, all 8 banks assemble.** Bank 4 = the old bank4 + the overlay cluster (hop `jmp PHMOverlay` at
  `$F9BF`, `HotOverlapFlag` twin at `$FFEC`, shape window cap `$F9BF`); bank 5 = extras walkers + data (old bank3, unchanged);
  bank 6 / 7 = room bank A / B (old bank2 assembled with `ROOMS_B = 0 / 1`). Bank0 of the new ROM has 316 B free (227 contiguous).
  The new ROM boots and `tools/playbot.py --rom-dir newrom` finishes levels 1-3. Left: the switch-over (build.sh -> newrom,
  verify_build / tests / frozen banks follow the role map), then more rooms per level.
- **2026-11-14: SWITCH-OVER done.** `newrom/` is the ROM now: `bankN.asm` at the `src/` root IS physical bank N (roles in `banks.inc`),
  the old `kernel.asm` / `bank1-7.asm` / `banks.inc` live in `oldrom/` (history kept via `git mv`, nothing deleted). `build.sh` assembles
  banks 5, 6 (level data), syncs the literals (`--sync-hof`, `--sync`: `LEVEL_DATA_ADDR` from `bank6.lst`, `LEVEL_COUNT` into banks
  0/2/4), then bank 0, `--sync-overscan` (bank 2's fold pad), the generated cave bank 1, then 2, 3, 4, 7. `verify_build.py` and the tools
  follow the role map (`B_HUD`, `B_GAME`, `B_ROOMS`, ... = `banksym.bank_index`). `tests/frozen/` is re-frozen on the new layout
  (`tools/freeze_test_banks.sh`); tests that share `test_cell_map` still call the OLD role names `BANK1..BANK7` (BANK1 = HUD ...),
  `Mem.bank` is the PHYSICAL bank. Bug caught on the way: the bank 4 copy of `ColMask` had only 12 of its 20 entries.
- **2026-11-15: rooms per level 20 -> 23 on the new structure.** `convert_level._pack_exact` (big-first first-fit, then a bounded
  depth-first search) packs the room tables into the window slots of banks 6/7 and the extras into bank 5; with it level n has
  min(n, 23) rooms (484 rooms, was 451). **Capacity finding:** 24 rooms/level does NOT pack even with exact packing: the
  windows of one room bank hold at most ~8 level tables of >=150 B (window sizes 329/429/340/290/199/207/141/71 minus the
  level index), so the limit is window fragmentation + total (~4.0 KB for both banks), not the packer. Going further needs
  bigger contiguous windows (move the pinned code in `bank6.asm` so `$F453-$F600`, `$F700-$F854` merge, i.e. rework of
  the room-bank code layout) or a smaller enemy-record encoding (enemy records are ~55% of the table bytes). The generator keeps
  the knob `SAVIOR_GEN_ROOMS_CAP`. `tools/playbot.py` re-plans when a wide ceiling/floor link drops it into a room off the route
  (level 22 needed this).
- **2026-11-15: bomb wall punch spread over 3 frames.** Sweeping `sim_frame_budget` over rooms of the 23-room stage found level 20
  room 18 with a 285.8-line blast frame (overscan 3543c): `BombMarkWalls` scanned the whole +-2 col window (up to 3 cells) in the
  edge frame, on top of a heavy room. `BombTick` now calls it at BombTimer 60 (edge: first cell + the M1/ball strip checks),
  58 and 57 (one cell each); timer 59 stays the enemy/player/sound frame. `BMWJ` (bank 3) derives the slice from BombTimer, so
  no new ZP; any other BombTimer (tests) keeps the old all-cells call. `tools/test_bomb_stagger.py` guards it. `sim_frame_budget` now
  starts the cave phase at bank 1 `BandStart` (the `.Row` address there is a sprite-fetch `jmp`), has a tally-frame class
  (DropTarget $FE bypasses the overscan: 1 line short) and its default scenario is level 2 room 1.
