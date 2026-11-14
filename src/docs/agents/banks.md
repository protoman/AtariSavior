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

## Open questions (answer in the survey)

- Exact size of the level-data service per bank, and whether the enemy-table readers can all use a RAM copy.
- Whether the cave kernel (generated, `tools/cave_kernel_gen.py`) can move to bank1 without its pinned hops.
- Frame cost of the extra hop on every room load (the load runs in the blank transition frame today).
- Which pinned addresses (`$F453`, `$FC49`...) have to follow their routine and which stay put.
- Where the split points between level banks fall (by bytes, so each level lives wholly in one bank).
