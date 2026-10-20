# Audit round 3 — 2026-10-20 (read-only, measured at d9aa22d)

Scope: the three items the brief names (HUD band, object dispatch, bank0
headroom) plus the round-2 leftovers. Nothing was edited except this file.
Every number below is either read off the tree (listing/frozen source) or
marked **est.** (projection); the two HERO-premise facts are cited to the
session that measured them, not re-derived here.

Method: `tools/rom_size_report.py --md` (authoritative totals), `bank*.lst`
(label spans = `next label − this label`, emitted-byte occupancy for windows),
`kernel.asm`/`bank1.asm` cycle comments (whose provenance is the sims, not
this audit), `generated/*.asm` for level data.

## Size ledger (measured, HEAD d9aa22d)

| bank | code | data | used | free |
|---|---|---|---|---|
| bank0 | 3210 | 358 | 3568 | 528 |
| bank1 | 2517 | 431 | 2948 | 1148 |
| bank2 | 938 | 211 | 1149 | 2947 |
| bank3 | 958 | 327 | 1285 | 2811 |
| **total** | **7623** | **1327** | **8950** | **7434** |

Level data **410 B** = index 28 + tables/blocks 216 + models 166.

**bank0 insertable capacity, measured from emitted-byte occupancy — this is
not 16 B:**

| window | B | note |
|---|---|---|
| `$FB08-$FBCF` | **200** | contiguous fill between the overlay cluster and the live `$FBD0` pin |
| `$FC1D-$FC48` | **44** | org-able, last slot before the `$FC49` MothExitPad pin |
| `$FC5A-$FC67` | **14** | appended-flow tail (last emitted byte `$FC59`; round 2 said 16) |
| total | **258** | |

So the binding figure is *flow* growth = 14 B. Anything that fits a window can
be `org`'d at `$FB08` or `$FC1D` today. Growth pressure applies only to code
that appends to the single stream, which ends at `$FC59`.

Bank0 flow composition (label spans; a row may include fill where noted —
the remainder of the 3210 code is post-pad leaves, fold/call pads and the
`$FE00` kernel tables):

| cluster | addr | B |
|---|---|---|
| frame loop + VBLANK | `$F039-$F0D2` | 153 |
| kernel (`.Row`/`.Line`/HUD call) | `$F0D2-$F18A` | 184 |
| overscan + input + laser/bomb/vertical | `$F18A-$F3B2` | 552 |
| room mgmt (`UpdateEnemies`, `DeriveEnemyY`, `UE_*`) | `$F3B2-$F4DB` | 297 |
| exit handlers (4) | `$F4DB-$F535` | 90 |
| level mgmt (`LoadLevel` + pre-roll) | `$F535-$F5B1` | 124 |
| `CheckMinerPickup` | `$F5B1-$F5D5` | 36 |
| `SelectActiveObject` | `$F5D5-$F6F6` | **289** |
| `EnemyColorTable` + `ObjSpriteOffTable` | `$F6F6-$F706` | 16 |
| `CheckEnemyHit` | `$F706-$F7E8` | **226** |
| misc tables (`BombBlinkColors`, masks) + `UEDispatch` + raft pad + jet art + `PlayerColTable` | `$F7E8-$F901` | 281 (incl. ~188 B fill) |
| `YToRowTable` | `$F901-$F926` | 37 |
| `PlayerHitsMap` | `$F926-$F9B5` | 143 |
| pads + overlay cluster (moved in) | `$F9B5-$FC58` | 275 live + 200 fill |

Cycle headroom used throughout this audit (from the source's own measured
notes): **VBL worst 1311c of TIM64T #23 = 1472c → 161c**; **overscan worst
2104c of #50 = 3200c → 1096c**. One bank round trip (pad `sta` + target `jmp`
+ `ReturnPad` `sta`/`rts`) ≈ **8-11c**.

---

## A. HUD band — PF-table HUD feasibility

### Measured: where MenuMain's 696 B go

`MenuMain` = `$F540-$F7F8` = **696 B**. Supporting code/data it needs:
`DigitGfx` 104 (`$FD00-$FD68`, page-pinned), `SetupScorePointers` **123**
(`$FD68-$FDE3`: 6 score pointer sets + `#18 LV001` banner),
`BarDelayTable`+`BarFineTable` 30, `SetObjectXPos_b1` 46 (`$F7F8-$F826`,
shared with the title), `fineAdjustTable_b1` 15.

| section | addr | B | lines in the 48-line band |
|---|---|---|---|
| prologue + `CTRLPF`/PF setup + `TopGap` | `$F540-$F583` | 67 | 6 |
| timer bar (3 red paths + `BarGap`) | `$F583-$F686` | **259** | 4 |
| lives (NUSIZ 1-3 copies, P0 @12) | `$F686-$F6D6` | 80 | 8 |
| bombs (P0 @12 + P1 @60) | `$F6D6-$F763` | 141 | 11 |
| score (setup + `.ScoreLoop` 72 + `.HudPad` 8) | `$F763-$F7F8` | 149 | 10 + 9 pad |

The 48-line contract is `6 TopGap + 4 bar + 8 lives + 11 bombs + 10 score +
9 pad` (comment, `bank1.asm:1252-1258`). Every `SetObjectXPos_b1` call is
exactly 1 scanline, so moving an element changes the pad, not the total.

### The HERO premise does not hold

The brief's model ("HERO does the visible HUD with a 54 B loop + per-scanline
PF tables + ~100 B digit tables") is **half wrong, already measured on
2026-10-19** (`docs/handoff_2026-10-19_next.md` §4a, `docs/compaction_findings_2026-10-19.md`):

- The **54 B loop at `$DC00` is the cave/PF band** (per-scanline terrain PF
  tables `$DC6A/$DC6C/$DC77`), not the HUD. We already have that shape.
- HERO's **score is sprite-based**: an 8×8 glyph font at `$DF00` (10 digits ×
  8 B + letters), rendered `lda ($xx),Y` → `GRP0`/`GRP1` with VDELP0/1, and
  HUD setup fills pointer high bytes with `$DF`. That is structurally the same
  technique as our 48px score + `DigitGfx`.
- A PF score cannot show six distinct digits: the playfield is 20 bits over
  80 px (4 px per bit) and is either mirrored or repeated in the right half,
  so 6 digits either become 4 px block glyphs or get duplicated. Layout would
  have to move into one half. That is a design change, not a compaction.

**Verdict up front: REJECT.** There is no HERO-parity gap to close on the
score (we are already sprite-glyph based), the only PF-able elements are
lives+bombs, and the bytes saved land in **bank1, which is not the binding
bank** (1148 free, 343 B largest window).

### Model, per element

| element | now | PF replacement | data added | code after (est.) | display identical? |
|---|---|---|---|---|---|
| prologue + `TopGap` | 67 | n/a — stays | 0 | 67 | yes |
| timer bar | 259 | **already PF** (`PF0=$E0/PF1=PF2=$FF`, mid-line `COLUPF`) — leave alone: cycle-tuned (`.R3` has no `jmp` because a 76c line adds a scanline) | 30 stays | 259 | yes |
| lives | 80 | 1 row from a count→PF table; drops 1 `SetObjectXPos` (−1 line) | 12 (4 states × 3 PF bytes) | ~26 | **no** |
| bombs | 141 | 2 rows (or 1 row, 2 groups); drops 2 `SetObjectXPos` (−2 lines) | 18 (6 states × 3) | ~26 | **no** |
| score | 149 | not reachable (see above) | — | — | — |

Numbers: lives+bombs = **221 B → ~52 B code + 30 B data = ~139 B net saved**,
in bank1. `SetObjectXPos_b1` (46) and `fineAdjustTable_b1` (15) must stay
because the title path uses them too.

**Why the display changes:** the playfield is 20 bits and mirrored/repeated.
Lives are drawn at x12 only; bombs at x12 and x60. With reflection on
(`CTRLPF=$05` in the band) an icon at x12 also appears at x148; with
reflection off the right half repeats the left, so an icon at x12 also appears
at x92. Either way PF icons duplicate, and each PF "pixel" is 4 clocks vs the
current 3-clock sprite squares. Identical output is not achievable without
moving the elements and changing the design.

**Risk if it were done anyway:** the band is a WSYNC count contract — freed
positioning lines must be re-added to `.HudPad` in the same change or the band
becomes 47/49 lines; `sim_frame_budget`, `test_phase3_ball` and the HUD-band
pixel detectors read it. The bar must not be touched (the `.BarRedFull`
paths are 71-73c of a 76c line and its tables are generated by
`tools/gen_bar_tables.py`).

**Verdict: reject with numbers.** 139 B saved, +30 B data, in the bank with
1148 B free, at the price of a visible redesign and a 48-line-band re-timing.

---

## B. Object dispatch — rotation → in-frame multiplexing

### What exists (measured)

`SelectActiveObject` = `$F5D5-$F6F6` = **289 B**, called once per frame from the
VBL (`kernel.asm:556`). It rotates one GRP1 slot per frame using
`FlickerFrame` (1 ZP byte `$B4`) and produces `ObjBase` / `ObjTop` /
`ActiveObjectX/Y` / `COLUP1` for the kernel. Per frame it also pays up to one
`CallPad_IsRoomDark` (bank1, 38 B there) and one `FoldIndirect`
(10 B, 19c + `jsr` = 25c, **2 bank switches**) per object drawn.

Kernel side (`.Grp1`, `$F121`): per line `tya/sec/sbc ObjTop/cmp #8/bcs` then
`adc ObjBase / tax / lda ObjSprites,X / sta GRP1 / lda ObjColorTab,X / sta
COLUP1` — 30c in-window, and the section's own comment records the worst line
at **69c work / 72c start-to-start with `sta WSYNC` required ≤ c73** → **4c
of margin**.

### What multiplexing would cost

1. **Per-line slot state.** In-frame multiplexing reads the *current slot's*
   ObjTop/base from indexed ZP (`lda SlotTop,X`) instead of a fixed byte:
   +1c per access, ×2-3 accesses = **+2..3c/line against a 4c budget**. That
   alone leaves no room for the slot-boundary test.
2. **Reposition cost is a whole scanline, twice.** `RESP1` needs the div15
   loop (~5c/iteration, up to 10) which does not fit the 68-clock HBLANK, so
   each slot boundary is `sta WSYNC` + loop + an `HMOVE` line ⇒ **2 lines per
   extra slot**. With 2 extra slots that is **+4 lines/frame**. The frame is
   fixed: the only donors are the cave bands (breaks `YToRowTable`, the water
   strip and the RoomY geometry) or the HUD band, where only the **9 pad
   lines** are free (the 1- and 3-line element gaps are visible spacing) —
   and the band is a pinned 48-line contract either way.
3. **It does not remove flicker anyway.** Multiplexing only works when slot Y
   windows are disjoint. `DeriveEnemyY` derives Y **every frame from
   `EnemyRamP`** for bat / tentacle / spider / moth (`kernel.asm` `DEYBobTick`
   family), so two enemies routinely occupy overlapping Y; those frames still
   need rotation. Flicker becomes rarer, not gone — and the platform (miner)
   plus a moving enemy overlap too.

### Byte model (est.)

| item | B |
|---|---|
| delete `SelectActiveObject` | −289 |
| delete tally/frozen-scene gate branches (inside SO) | (in the 289) |
| add VBL slot fill + Y-sort | +24 |
| add kernel indexed slot select / boundary dispatch | +30 |
| add 2 reposition sequences | +16 |
| add per-slot color/restore bookkeeping | +14 |
| add ZP slot table (3 slots × top/base/X/Y) | 0 ROM, **+12 B RAM** (ZP map change — sequential block is full) |
| **net bank0** | **≈ −205** |

Plus the frame-geometry change (4 lines), a new per-kernel WSYNC count, a
`sim_frame_budget` landmark, the `{264,265}` frame set, and a Stella SCN
single-value oracle run — i.e. the "kernel project" the 2026-10-19 findings
already classified it as.

**Verdict: reject.** Best case ≈ −205 B in bank0 (the one bank that needs it)
for a fixed-time kernel rewrite that must donate 4 scanlines, and the stated
quality goal (no flicker) is not delivered for Y-overlapping objects. If
flicker is the actual goal, the lever is authoring (the editor's ≤2 objects /
≤1 per row cap) and the rotation cadence — not a kernel rewrite.

---

## C. bank0 headroom — what can leave, what must stay

### Must stay (pinned by a 4c fetch, a page contract, or the frame anchors)

| item | B | reason |
|---|---|---|
| kernel `.Row`/`.Line`/`.Grp1`/`.GrpSkip`/`.ObjZero` | 184 | fetched inside the fixed-time loop; its worst path is 69-72c of 73 |
| frame loop + VBL + the two re-anchor WSYNCs + `WaitVBLANK` | 153 | phase-lock contract (bug #29 Class C); no cycle-variable code may enter the INTIM-exit → first kernel WSYNC span |
| kernel-read data: `ObjColorTab` 72, `ObjSprites` 72, jet+walk art 48, `PlayerColTable` 12, `BeamMask` 12, `fineAdjustBegin` 15 | **231** | `lda abs,X` / `(zp),Y` at 4-5c with no page cross; a fold would cost 25c/line |
| `SetObjectXPos` `$FF0F`/`.Div15Loop` `$FF12` + fineAdjust `$FF00` | 33 | page-pinned 5c contract (`verify_build` guards 2 of these) |
| fold pads `$FC68/$FC70`, `ReturnPad` `$FBF8`, `MothExitPad` `$FC49`, twin tramps | ~60 | F6 switch contract (byte-identical halves) |
| overlay cluster `$F9F5-$FB07` + `PickPlayerFrame` | 275 | moved in by repack chunks 1/3 (−83 B total, fewer switches) — moving it back re-opens those chunks |

Remaining bank0 data (127 B: `YToRowTable` 37, `ColOff`+`ColMask` 40,
`EnemyColor/ObjSpriteOff` 16, misc masks 21, `ConnectionTable` 8) travels only
with its reader — it cannot be freed on its own.

### Ranked moves (bank0 → bank2/bank1)

All six targets are mid-flow, so each one **grows the flow tail by its net**
(14 B → 14 + freed). Ranked by (bytes freed) ÷ (risk that the target bank's
`ReturnPad`-to-bank0 semantics break the moved body).

| # | move | net bank0 | target cost | cycles | risk | why it ranks here |
|---|---|---|---|---|---|---|
| 1 | `SelectActiveObject` (`$F5D5`) → **bank2** | **−283** (289 body, +6 pad) | +289 body + ~76 helpers | **−12..−40c** net | **med** | biggest win and the **cleanest dependency profile**: its two cross-bank callees are replaceable *in place* — `FoldIndirect` becomes `lda (EnemyDataLo),Y` (records are in bank2, 1 B each since d9aa22d, 5c instead of 25c) and `IsRoomDark` becomes an inline `RoomNo`/mask test (~10 B; a bank1 copy is unusable, it ends in `jmp ReturnPad` → bank0). Needs `SetObjectXPos` 17 + page-aligned fineAdjust 15, `SetObjReflection` 18, `EnemyColorTable`+`ObjSpriteOffTable` 16 (`EnemyBitTable`/`EnemyOffTable` are already in bank2). bank2 fits it in one window (`$F790`, 1088 B); bank1 does not (largest 343). Removes 2-4 switches per object draw. |
| 2 | `LoadLevel` (`$F535`) → bank2 | **−26** (32 body, +6 pad) | +32 +2 (local `EnterRoom` entry) | **−140c** cold | **low-med** | already pays **7 `jsr FoldIndirect`** (175c) for the 7-byte entry at `$F700`; in-bank = 7 direct reads. Its `jsr EnterRoom` must become the bank2 body with an `rts` tail (+2 B, same trick repack chunk 1 used for `PickPlayerFrame`) because today's `EnterRoom` leaves via `jmp ReturnPad`. Cold path (level load/death). |
| 3 | 4 exit handlers (`$F4DB-$F535`) → bank2 | **−84** (90 body, +6 pad) | +90 +~15 (inline conn read + local fold + `rts`-tail `EnterRoom`) | +8-11c per room crossing | **med** | **not** the easy second step it looks like: each handler does `jsr CallPad_GetConnIdx` (bank1), `jsr FoldIndirect` (bank2) and `jsr EnterRoom` (bank2), then keeps working (`sta RoomY`) — all three return to **bank0**, so a copy in any other bank must replace all three with local variants first. Cold path, so cycles do not matter; the room-transition tests do (`test_band_restage`, `test_respawn_hover`). |
| 4 | `UpdateEnemies` cluster (`$F3B2-$F4DB`) → bank2 | **−291** | +297 + data | ≈ −50c (drops `UE_MothTramp` + folds) | **high** | same data-coupling win as #1, but it is the enemy AI (moth/snake/tentacle/bat Y derivation) with the widest test surface (`test_enemy_movement` asserts against `UEDispatch`). Overscan has 1096c headroom, so the cycles are not the objection — the correctness surface is. |
| 5 | `CheckEnemyHit` (`$F706`) → bank2 | **−220** | +226 | ≈ −70c (3 folds removed) | med-high | kill/life logic; `test_bomb_lamp`, `test_enemy_movement`, `test_bomb_user_sequence` read it. |
| 6 | `PlayerHitsMap` (`$F926`) → bank2 | **−137** | +143 | +16-24c (2 switches × 2-3 calls/frame) | med | `ColOff`/`ColMask` already have bank2 copies, so no data travels; but it is the hottest walk (3 calls/frame) and the tentacle-residual bug lives in its callers. |

Cumulative: **#1 = −283 B flow** (tail 14 → 297 B); **+#2 = −309**
(tail 14 → 323 B); **+#3 = −393** (tail 14 → 407 B). #4-#6 are not needed for
capacity at that point.

### The 44 B org slot

`$FC1D-$FC48` (44 B, ends at the `$FC49` pin) is real and usable for a leaf
today: it is inside the flow but org-able, so placing code there does not move
the tail. Same for `$FB08-$FBCF` (200 B) if a routine is big enough to justify
an `org`. Four pages of new leaf code fit bank0 **without any of the moves
above**; the moves matter only for *appended* growth.

---

## D. Round-2 leftovers — value now

| item | bytes | where | value now | verdict |
|---|---|---|---|---|
| PF row pool, straight 12×3 | 13 net | level data (bank2/bank3) | banks 2/3 hold 2947/2811 free; level data is not scarce | **skip** (under the chunk line) |
| PF row pool, 4-bit indices | ~26 net | level data | same, plus it breaks the `TilePF0+9/+10` meta contract that `bank2.StageBandTab` and six `test_cell_map` reads depend on | **skip** (contract risk for non-scarce bytes) |
| hot-flag: drop the always-zero hot-count byte | **11** (11 of 12 lists; verified `level_004_blocks.asm` still emits it) | level data | non-scarce bank; converter + `verify_build` + re-freeze churn | **skip** |
| enemy-record packing | already done (d9aa22d: 1-byte records) | — | — | **stale item** |
| dead pad halves (7 twin `sta` + MothExitPad b0 + 2 fold stubs) | 40 dead, **0 insertable** | all four banks | each sits between a `.ds` pin and the live `jmp` at A+3, or between two org anchors | **skip** (measured in round 2, re-confirmed) |
| LWC → bank0 | **+16 cost** | bank2 → bank0 | bank2 has 1088 B free; it would *spend* bank0 and add 2 switches per beam frame | **skip** |

Net: **nothing from round 2 is worth doing now.** The remaining level-data
bytes (11 B hot-flag, 13 B table pool) are real but sit in banks with
thousands of bytes free.

---

## Value/risk matrix

| item | bank0 B | bank1/2 B | cycles | risk | display | verdict |
|---|---|---|---|---|---|---|
| A. PF-table HUD (lives+bombs) | 0 | −139 (bank1) | neutral (pad re-balanced) | med-high (48-line band) | **changes** | **reject** |
| A. PF-table score | — | — | — | — | impossible (6 digits / 20 bits) | **reject** |
| B. rotation → multiplexing | ≈ −205 | +82 kernel | +3c/line vs 4c margin; +4 lines | high (kernel rewrite, geometry) | flicker only partly gone | **reject** |
| C1. `SelectActiveObject` → bank2 | **−283** | +365 | −12..−40c/frame | med (VBL, GRP1 select) | none | **do first** |
| C2. `LoadLevel` → bank2 | **−26** | +34 | −140c cold | low-med | none | **do second** |
| C3. exit handlers → bank2 | **−84** | +105 | +8-11c/crossing | med (needs 3 local call variants) | none | **do third** |
| C4-C6. `UpdateEnemies` / `CheckEnemyHit` / `PlayerHitsMap` → bank2 | −291 / −220 / −137 | +297 / +226 / +143 | −50 / −70 / +20c | high / med-high / med | none | **defer** (not needed after C1-C3) |
| D. level-data items | 0 | 11-26 | 0 | med (converter + re-freeze) | none | **skip** |
| use `$FC1D-$FC48` (44) / `$FB08-$FBCF` (200) for new leaves | 0 | 0 | 0 | low | none | **available now** |

## Recommended sequence

1. **Stop** on A and B. A saves bytes in the non-binding bank and changes the
   picture; B costs a kernel rewrite and does not remove flicker for
   Y-overlapping objects (which `DeriveEnemyY` produces every frame).
2. **C1 `SelectActiveObject` → bank2** (−283 B flow; the only move that both
   relieves bank0 and removes switches). Do it as its own chunk: plain-record
   read instead of `FoldIndirect`, inline dark test, `SetObjectXPos` +
   page-aligned fineAdjust, `SetObjReflection` and 2 color/offset tables in
   bank2; the body must not call any CallPad (bank1/bank0 target rule).
   Gate: `sim_frame_budget` (VBL landmark + WSYNC counts), `sim_bomb_fuse`,
   `test_enemy_movement`, `test_miner_colors`, `test_raft`; re-freeze.
3. **C2 `LoadLevel` → bank2** (−26 B flow, −140c, 7 folds → direct reads) with
   the `rts`-tail `EnterRoom` local entry. Gate: `test_level_bank`,
   `test_band_restage`, `test_key_pickup`, `test_tally`.
4. **C3 exits → bank2** (−84 B flow) only after C1/C2 have established the
   local-variant pattern in bank2; it needs three of them (conn-index read,
   fold, `EnterRoom`) and it is a room-transition path.
5. Only if more flow headroom is still needed after that (14 + 283 + 26 + 84 =
   ~407 B): C4-C6, in that order, each with `sim_frame_budget` +
   `sim_bomb_fuse` + the battery.
6. New leaf code goes to `$FC1D-$FC48` (44 B) first, then `$FB08-$FBCF`
   (200 B) via `org`. No move is needed to add a modest feature today.

## Why "16 B" is the wrong headline number

The stream's append point has 14 B left, but bank0 has **258 B of insertable
window** (200 + 44 + 14). A feature that fits a window needs no compaction at
all; only a feature that must be contiguous with the existing flow, or a
re-layout that has to grow past `$FC67`, is blocked. Both audits' "bank0 is
the binding resource" is right about *total* bank0 usage (3568/4096) but the
actionable number for a new feature is the window, not the tail.

## Measurement appendix

- Section boundaries: `bank1.lst` / `bank0.lst` label addresses and the
  section-comment addresses (`MenuMain $F540`, `Line 1: Timer $F583`,
  `Line 2: Lives $F686`, `Line 3: Bombs $F6D6`, `Line 4: Score $F769`,
  `.ScoreLoop $F7A8`, `.HudPad $F7F0`, `SetObjectXPos_b1 $F7F8`).
- Free windows: emitted-byte occupancy from the listings (`.ds` fill counted
  free), same method as round 2; the 200 B `$FB08` and 44 B `$FC1D` windows and
  the 14 B tail were recomputed for this HEAD.
- Cycle margins: quoted from the measured notes in `kernel.asm` (VBL #23
  1311/1472c, overscan #50 2104/3200c) and from the `.Grp1`/`.BarRedFull`
  comments (69c/73c, 71c/76c). Not re-simulated here (read-only audit; a build
  would rewrite `bank*.bin` and `generated/`).
- HERO HUD facts: cited from `docs/handoff_2026-10-19_next.md` §4a and
  `docs/compaction_findings_2026-10-19.md` (disassembly of
  `docs/hero/hero_bank0.asm`), not re-derived.
- Level-data leftovers verified against `generated/level_004_blocks.asm`
  (hot-count byte still emitted; 1-byte enemy records already in place).
