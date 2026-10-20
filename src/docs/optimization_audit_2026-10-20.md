# Optimization audit — 2026-10-20 (read-only, measured)

Baseline named in the brief: HEAD 3ea97e5, 9452 used / 6932 free.
**Measured on the live tree at 91475ca (tally A+C reverted): 9452 used / 6932 free.**
bank0 3376 (the brief says 3377 — 1 B drift), bank1 3015, bank2 1760, bank3 1301.
The in-flight tally variant (`9b03714`) measured 9466 (+14: bank0 −11, bank2 +25);
the delta is small enough that every table size below is unchanged either way.
Level data 548 B. Numbers come from `bank*.lst`, `generated/*.asm` and
`tools/rom_size_report.py`; "est." marks a projection.

Reality check before the tables: **capacity is not the constraint** (6932 B free).
The value of shrinking is (a) fewer fragile pins/twins, (b) level-data growth
headroom, (c) less duplicated code across banks. Contiguous free windows
(measured from the listings, largest first) — these are the real placement
targets, not the aggregate "free" number:

| bank | usable windows (fill bounded by pins) |
|---|---|
| bank0 | `$FA04-$FAFF` 252, `$FB00-$FB36` 55, `$F830-$F8BF` 144, `$FBD6-$FBF7` 34 |
| bank1 | `$FF0F-$FFF5` 231 (page-clean; `$FFF6-$F9` reserved), `$F41C-$F53F` 292, `$F2B4-$F359` 166, `$F8C6-$F936` 113 |
| bank2 | `$F9D9-$FBCF` 503 (the documented 509 B level-table window), `$F45E-$F5CE` 369, `$FC4C-$FD86` 315, `$FF59-$FFE5` 141 |
| bank3 | `$FC38-$FFEE` 951, `$F658-$F87F` 552, `$FA7F-$FBF7` 377 |

bank0 is *not* "1 byte left" globally: 307 B sit unused between DropSpeedTable
and the `$FB37` pin; the 1-byte ceiling applies only to code flowing into
`$FC68`. New bank0 leaves can be placed explicitly in `$FA04-$FAFF`.

---

## A. Tables (inventory + reduction candidates)

Per-bank data totals (rom_size_report): bank0 350, bank1 502, bank2 361,
bank3 368. Main tables (bytes measured from the listing; purpose from source):

| bank | table | B | purpose | flag |
|---|---|---|---|---|
| 0 | ObjColorTab | 72 | 9 object types × 8 row colors | 8/9 rows uniform → derivable |
| 0 | ObjSprites | 72 | 9 object designs × 8 rows | needed (kernel 4c read) |
| 0 | YToRowTable | 37 | scanline→band row, indexed A>>2 | affine (idx/12) |
| 0 | PlayerSpriteA/B | 24 | jet frames | duplicated in bank2 |
| 0 | PlayerWalkA/B | 24 | walk frames | 3 copies total |
| 0 | ColOff + ColMask | 40 | cell-walk col→PF offset/mask | duplicated in bank2 |
| 0 | BeamMask | 12 | per-row ENAM0 | 1 nonzero entry |
| 0 | PlayerColTable | 12 | player row colors | small |
| 0 | fineAdjustBegin | 15 | HMOVE fine, page-aligned | required |
| 0 | misc (colors/offsets/speed/vectors) | 42 | type→color/offset, drop speed, IRQ | small |
| 1 | DigitGfx | 104 | 13 glyphs × 8 rows, 7-bit wide | no pack (render reads rows) |
| 1 | MusicMel | 102 | 51 (duration,note) pairs | 3 durations, 16 notes → packable |
| 1 | FooterFont | 84 | title footer, 6 × 14 | title-only |
| 1 | TitleFont | 48 | "S.A.V.I.O.R.", 6 × 8 | title-only |
| 1 | BarDelay/BarFine | 30 | power-bar timing (already 121→15 shrank) | fine |
| 1 | ABWX/W/Y/H | 20 | rect-cache addrs, affine base+4i | derivable |
| 1 | PlayerWalkA/B | 24 | title walk | dup of bank0 |
| 1 | BombClearMask | 20 | inverse ColMask per col | = ColMask ^ $FF |
| 1 | BitMaskTable, LaserFreq | 16 | bit masks / laser pitch | small |
| 1 | fineAdjust + misc + vectors | ~54 | HMOVE copy, 4-byte mask copies | required |
| 2 | LevelDataTable + level tables | 244 | index + room/conn/enemy tables | see C |
| 2 | ColOff + ColMask | 40 | cell-walk (bank2 walkers) | dup of bank0 |
| 2 | TitleJetSprite | 24 | jet art for PickPlayerFrame | dup of bank0 art |
| 2 | walk-frame twin | 24 | PickPlayerFrame walk art | dup of bank0 art |
| 2 | OvHead, EnemyOff, EnemyBit, MothBit | 13 | overlay/derive masks | small |
| 2 | tramp twins + vectors | ~16 | see B | structural |
| 3 | level data (models + per-room blocks) | 304 | see C | 3 identical blocks |
| 3 | CrPfx0-2 | 33 | copyright glyphs | title-only |
| 3 | BCFDarkMask + PhMaskTab | 18 | dark-room / phase masks | small |
| 3 | vectors | 6 | IRQ/NMI/RESET | required |

Verified duplicates (12-byte window scan over all four bank binaries, fill and
pads filtered by label): player walk art at bank0 `$FDE7`, bank1 `$F062`,
bank2 `$FDE7`; jet art at bank0 `$F8DD` and bank2 `$F8DD`; `fineAdjust` 15 B in
bank0/bank1 (structural); ColOff/ColMask 20+20 in bank0/bank2; BombClearMask is
the bit-complement of ColMask; models M1..M8 share no whole block, but 36 PF
row triples collapse to **12 distinct** rows.

| candidate | current | proposed | save | cost | risk |
|---|---|---|---|---|---|
| ObjColorTab → per-type color staged in VBL + 8-row miner table | 72 | 17 + ~8 code | **47** | kernel read shortens (4c→3c) | low |
| MusicMel → 1 byte/pair (4-bit note, 2-bit duration) | 102 | 51 + ~15 code | **51** | player decode | med |
| PF row pool (12 distinct triples) + 1 index byte/row | 135 | 36 + 45 idx + ~12 code | **54** raw / ~39 net | room-load copy into PF0Buf | med |
| ColOff/ColMask arithmetic (col→0/3/6, bit mask) | 80 (both banks) | ~16 code | **64** raw / ~48 net | +cycles in PHM walks | high (bank0 hot path) |
| BombClearMask = ColMask ^ $FF (read ColMask? cross-bank → derive) | 20 | ~6 code | **14** | cold path | low |
| YToRowTable → 2 compares (idx/12) | 37 | ~8 code ×1 inline | **29** | +8c per walk (3/frame) | med |
| ABW 4 tables → base + 4·i | 20 | ~6 code | **14** | cold (bomb) | low |
| Walk/jet art single copy + fold/RAM copy | 120 | 48 + ~20 | **~50** net | VBL/kernel cycle risk, no free RAM | high |

Not recommended: DigitGfx/TitleFont/FooterFont/CrPfx row packing (8-bit rows are
read directly by `(ptr),Y` kernels; a packed format touches three renderers),
BeamMask (page-pinned for a 4c fetch), `fineAdjust` (page alignment is a
contract).

---

## B. Pins and bank switching

Measured: **107 `.ds`/`org` directives** (kernel 30, bank1 22, bank2 40,
bank3 15; includes 4 bank-start `org`s and the ZP `org $80`). By comment class:
tramp/twin pads 22, cross-bank CallPad/fold 22, level-data spill slots 6,
F6-hotspot guards 2, vectors 4, layout pins 9, page/segment align 16, rest fill.

Switch cost: **77 `sta $1FFx` instructions** (bank0 32, bank1 23, bank2 18,
bank3 4) = 231 B, over **4 distinct addresses** (`$1FF6-$1FF9`). **35
same-address switch stubs** exist across banks; of these **14 have a dead `sta`
half** in the target bank (it is swapped out before that byte is fetched):

- twin tramps: `$F8C0` raft, `$FBD0` EnterRoom, `$FDD8` blast, `$FDE1`
  PickPlayerFrame, `$FE96` LHT, `$FEF0` moth, `$FFE6` tally, `$FFEC`
  HotOverlap, `$F9BC` overlay, `$F458` ERBlocks return;
- single-caller pads: `$FC4F` TitleSelect, `$FC55` TitleKernel, `$FC5B`
  Overscan, `$FC61` MusicTick (the second bank only needs the `jmp` at +3).

That is **42 B** (14 × 3) of provably dead bytes. The F6 rule is respected: the
post-switch fetch begins at pad+3, so the target bank must keep the identical
`jmp` opcode+operand there; only the leading `sta` is dead. Guards
(`verify_build.check_*_tramp`, `check_raft_tramp`) compare a 6-byte window —
they would become "opcode+operand at +3 equal", which is the actual contract.

Corridor accounting (measured spans): the CallPad strip `$FBF8-$FC67` is
**112 B in bank0 and 112 B in bank1** (94 B of pads: ReturnPad 4 + 11 CallPads
× 6 + 4 title/music pads × 6); the fold stubs `$FC68`/`$FC70` are 16 B per
bank. There are 27 `jsr CallPad_*` sites.

| proposal | bytes | risk | note |
|---|---|---|---|
| Drop the 14 dead `sta` halves | **42** | low | guard change, no runtime | 
| RTS-dispatch gateway: 1 pad/bank + 1-byte inline id + 11-word table | 132 → ~61 | **~53 net** | med-high | replaces 11 pads × 2 banks; +~8c/call; needs a dispatch routine |
| `lda #imm` before `sta $1FFx` in the two fold stubs (`$FC68/$FC70`) | 4 | low | F6 ignores the written value; verify no caller reads A |
| Route bank1's CallPad calls through the bank0 copy | 0 | — | not possible: bank1 must switch to bank0 first (adds `sta`), no win |

The single-gateway scheme must stay F6-legal: the id byte is fetched from the
caller bank *before* the `sta`, and the target bank holds the dispatch table
plus the `jmp (vec)` image at the fixed address. It trades 132 B of duplicated
pads for ~61 B, and removes 22 pins from the two most crowded banks.

**DONE differently 2026-10-20** (`cuts 4` commit) — the gateway row was
measured and **skipped**: the routine id costs +27..54 B at the 27 call sites
and RTS dispatch adds ~21c/call against a ~20-220c overscan margin, i.e. under
the 25 B floor with a timing risk. The same duplication was reclaimed by
extending the proven **split-pad** contract (commit `1abf83e`) to the corridor:
bank0 keeps the `sta` halves packed, the target bank the `jmp` halves at A+3.
Net **−76 B** (bank0 −33, bank1 −37, bank2 −6), zero cycles, zero stack. The
`CallPad_BuildColupF` image moved `$FC35` → `$FC1A` and bank2's dead copy was
deleted (its `+3` would have landed on bank3 fill). Details:
`docs/compaction_findings_2026-10-19.md` §4.

---

## C. Level / room data (548 B)

Measured per level (`tools/rom_size_report.py` + `_gen_data_size`), index
48 = 4 × 12 B; models 166 = M1-M8 (19,19,19,21,25,25,19,19); per-room blocks
138 = L1R1 19, L3R1 19, L4R1 19, L4R2 24, L4R5 17, L4R6 40.

| level | rooms | index | roomdata | conn | enemy recs | roomenemies | blocks | total |
|---|---|---|---|---|---|---|---|---|
| L1 | 2 | 12 | 8 | 4 | 8 (2) | 8 | 19 | 59 |
| L2 | 2 | 12 | 8 | 4 | 4 (1) | 8 | 0 | 36 |
| L3 | 6 | 12 | 24 | 12 | 24 (6) | 24 | 19 | 115 |
| L4 | 6 | 12 | 24 | 12 | 0 (0) | 24 | 100 | 172 |
| models | — | — | — | — | — | — | — | 166 |

Room-data layout facts that bound the options: `RoomDataTable` is 2 words/room
(PF0 ptr + rects ptr) read at `bank2.asm:150-163`; `RoomEnemies` is 4 B/room
(ptr_lo, ptr_hi, count, bottom_color) read at `bank2.asm:168-179`; both blocks
(PF+meta) and models are emitted rects-first, PF0/1/2, MetaA, MetaB (meta at
`TilePF0+9/+10` by contract); every rect list has **0 hot rects**.

| change (converter-side unless noted) | save | risk | note |
|---|---|---|---|
| C1 share the 3 byte-identical blocks (L1R1/L3R1/L4R1) | **38** | low | converter hash; room tables point at one label; no asm change |
| C2 RoomEnemies 4 B → 2 B (count+color; ptr = running count at room load) | **32** | med | 16 rooms × 2; loader accumulates ≤16 counts (~80c at EnterRoom) |
| C3 RoomData 2 words → 1 word (PF0 = rects + 2 + 2·nrect, hot=0) | **32** | med | bank2 `EnterRoomB2` ptr math; breaks if hot rects return |
| C4 LevelDataTable 12 → 9 B (one base + room count; conn/enemy offsets = 4n/2n) | **12** | med | index reader only; assumes uniform per-level layout |
| C5 Enemy record 4 → 3 B (type 3b + dir 1b packed with x,y) | **15** | med | 15 records; 3 readers (load, derive, tests) |
| C6 Drop the always-zero hot-count byte (14 rect lists) | **14** | med | format change; models.json has no hot rects today |
| C7 MetaB: emit only when nonzero (13/14 blocks are 0) | 13 | high | meta offset is a fixed +10 read; needs a per-block flag |
| C8 PF row pool over level data | 39 net | med | see A; room-load copy into `PF0Buf` |

Fully zero-asm: **C1 (38 B)**. With the small reader edits, **C1 + C5 + C6 = 67 B**.
All of C is regeneration from `src/rooms` — the room files themselves
are never touched, so no user-content edit is required. Any change here
invalidates the frozen test banks (`tools/freeze_test_banks.sh`).

---

## D. Ranked plan

"dep" = conflicts with the pending bank2/bank3 code repack (moves the same
addresses); "indep" = bank0/bank1-only or converter-only.

| # | change | est. B | risk | files | dep |
|---|---|---|---|---|---|
| 1 | Drop 14 dead twin `sta` halves in target banks | 42 | low | kernel/bank1/bank2/bank3.asm, verify_build | yes (bank2 pins) |
| 2 | C1 share identical per-room blocks | 38 | low | tools/convert_level.py, generated/ | no |
| 3 | ObjColorTab → staged type color + miner row table | 47 | low | kernel.asm, bank1/bank2 (color staging) | no |
| 4 | MusicMel 1 byte/pair | 51 | med | bank1.asm, art/intro_theme.asm | no |
| 5 | C2+C3+C4 level-table compaction (readers in bank2) | 76 | med | convert_level.py, bank2.asm | yes |
| 6 | C5+C6 enemy/hot-byte packing | 29 | med | convert_level.py, bank2/bank3 readers, verify | yes |
| 7 | BombClearMask from bit math + ABW affine | 28 | low | bank1.asm | no |
| 8 | PF row pool over models/blocks | 39 | med | convert_level.py, bank3/bank2 room load | yes |
| 9 | YToRowTable → compares | 29 | med | kernel.asm (PHM inline) | no |
| 10 | RTS-dispatch gateway for 11 CallPads | 53 | med-high | kernel/bank1/bank2.asm, verify_build | yes |
| 11 | ColOff/ColMask arithmetic (both banks) | 48 | high | kernel.asm, bank2.asm (PHM/LWC hot paths) | yes |
| 12 | Art dedupe (walk ×3, jet ×2) | ~50 | high | bank0-2 art, VBL frame select | yes |

Sum of rows 1-9 (the low/medium band): **~380 B**, none of it a gameplay
change. Rows 1-2 are safe to take first: 80 B with no runtime effect and no
dependency on the repack beyond re-freezing fixtures.

Sequencing note: rows 5, 6, 8, 10, 11 all move bank2/bank3 addresses, so they
must land after (or as part of) the in-flight repack; rows 1-4, 7, 9 are
independent and can proceed now. Re-run `tools/rom_size_report.py --md` and
update the ledger in the same commit as each row.
