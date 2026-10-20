# Audit round 2 — 2026-10-20 (read-only, measured at 809dd4a)

Scope: fresh measurement of the CURRENT layout after the four cuts
(`optimization_cuts_2026-10-20.md`) and the five repack chunks
(`repack_plan_2026-10-20.md`). Supersedes the numbers in
`optimization_audit_2026-10-20.md` where they disagree.

HEAD `809dd4a` ("cuts 4: split the 11 corridor CallPads"). Measured with
`tools/rom_size_report.py --md` (authoritative totals), the four `bank*.lst`
(byte occupancy by address, label spans), `convert_level._gen_data_size` over
`generated/`, and a 12-byte duplicate scan over the four `bank*.bin`.
"est." marks a projection; everything else is read off the tree.

## Size ledger (measured)

| bank | code | data | used | free (report) | usable windows (listing) |
|---|---|---|---|---|---|
| bank0 | 3214 | 358 | 3572 | 524 | 495 |
| bank1 | 2517 | 431 | 2948 | 1148 | 881 |
| bank2 | 934 | 235 | 1169 | 2927 | 2914 |
| bank3 | 958 | 327 | 1285 | 2811 | 2800 |
| **total** | **7623** | **1351** | **8974** | **7410** | **7090** |

Level data **434 B** = index 36 + per-room tables 132 + room blocks 100 +
models 166. The last two audits moved **−350 B used** (9321 → 8974); 434 of
that was level data, the rest code/pads.

Two accounting notes, both measured:
- The report's `free` is `4096 − (code+data)` and counts a few emitted-but-inert
  rows; the "windows" column counts only addresses with no emitted byte
  (`.ds` fill + `org` gaps). They differ by 21/8/13/11 B per bank. Use the
  report for totals, the windows for placement.
- **Capacity is not the constraint** (7410 B free, and bank2 alone has a
  1064 B contiguous window). Ranking below is by fragility removed and
  per-room/per-frame cost, not by bytes squeezed.

---

## A. Tables now — 917 B of non-level data

Table sizes are `next label − this label` from the listings (cross-checked
against `.byte` counts in source); "readers" is the fetch site class, not a
reference count.

| bank | label | B | purpose | reader |
|---|---|---|---|---|
| 0 | ObjColorTab | 72 | 9 object types × 8 row colors | kernel `.Grp1` `lda ObjColorTab,X` 4c ($F131) |
| 0 | ObjSprites | 72 | 9 designs × 8 rows | kernel `.Grp1` 4c, same X |
| 0 | YToRowTable | 37 | scanline→band row, indexed `A>>2` | `YToRow` (3 walks/frame) |
| 0 | PlayerSpriteA/B, PlayerWalkA/B | 48 | jet + walk art | kernel `(Grp0Ptr),Y`; VBL frame pick |
| 0 | ColOff + ColMask | 40 | cell walk: col→PF offset / mask | `PlayerHitsMap`, LWC path |
| 0 | fineAdjustBegin | 15 | HMOVE fine, **page-pinned** | `SetObjectXPos` |
| 0 | BeamMask | 12 | per-row ENAM0 | kernel `.Line` 4c no-cross |
| 0 | PlayerColTable | 12 | player row colors | kernel 4c |
| 0 | DropSpeedTable | 9 | drop-in ramp | DropArm |
| 0 | EnemyColorTable, ObjSpriteOffTable | 16 | type→color / design offset | SelectActiveObject + VBL |
| 0 | EnemyBitTable, BombBlinkColors, OvHead/Tail, M1OffTab, StepDelta, EnemyOffTable | 21 | small mask/step tables | overscan |
| 1 | DigitGfx | 104 | 13 glyphs × 8 rows, page-pinned `$FD00` | bank1 score kernel `(ptr),Y` |
| 1 | FooterFont | 84 | title footer 6 × 14 | FooterBand `(ptr),Y` |
| 1 | MusicMel + MelDur | 55 | 51 steps, 1 B each + 4 durations | MusicTick (already packed) |
| 1 | TitleFont | 48 | "S.A.V.I.O.R." 6 × 8 | TitleBand |
| 1 | RaftCellMasks | 20 | PF bit per source col 0-19 (reflect) | RaftBody (bank1) |
| 1 | BombClearMask | 20 | PF clear mask per col 0-19 | BombMarkWalls ×3, PartyGone |
| 1 | ABWX/W/Y/H | 20 | rect-cache ZP addrs (`RcW1+4i(+k)`) | BombMarkWalls ×6 |
| 1 | fineAdjustBegin_b1 | 15 | HMOVE copy (page-pinned) | bank1 SOXP |
| 1 | BarDelayTable, BarFineTable | 30 | power-bar timing | MenuMain |
| 1 | LaserFreqTable, BitMaskTable | 16 | laser pitch / bit masks | sound + walls |
| 1 | BombMaskBit, RaftBitTab | 9 | WallMask bit / raft col bit | BMW, RaftBody |
| 2 | ColOff + ColMask | 40 | same tables, bank2 walkers | PHM/LWC/LHT in-bank |
| 2 | EnemyBitTable, EnemyOffTable, MothBitTable | 16 | blast/LHT/moth masks | bank2 |
| 2 | OvHead/OvTail, M1OffTab | 8 | overlay masks | moth patch, LWC |
| 3 | CrPfx0/1/2 | 33 | hcrunch PF prefix rows (n = 1..10) | PhHcrEntry |
| 3 | PhMaskTab, BCFDarkMask | 18 | phase-open masks / dark-room | PhaseBlink, BCFDarkRun |
| 3 | M1OffTab | 2 | M1 patch offset | B3StageBand |

Duplicates/derivables **already taken** (do not re-propose):
`ObjColorTab` miner rows are the only non-uniform slot (verified byte table);
walk/jet art is now a single copy per bank-role (chunk 1 removed bank2's
`TitleJetSprite`/walk twins); `MusicMel` is **already 1 byte/step** (51 B) —
the earlier audit's "102 → 51" line is stale; the C1 block dedupe removed 3
identical room blocks; the corridor `sta`/`jmp` halves are split, not twinned.

Duplicate scan (12-byte windows, fill filtered, cross-bank and intra-bank):
the only remaining duplicate **code** run is
`bank0 $F089-$F0A5` == `bank1 $FDE3-$FDFF` (**29 B**), which is the raft tide
triangle the VBL and `RaftBody` both compute. Everything else the scan reports
is fill, the pad corridor (structural), or `fineAdjust` (page contract).
**No intra-bank duplicate block ≥ 12 B exists.**

Remaining reduction candidates, ranked by bytes/risk (all previously deferred;
re-checked against THIS layout):

| candidate | now | proposed | save | cost | risk |
|---|---|---|---|---|---|
| YToRowTable → `cmp/cmp` inline | 37 | ~8 code | **29** | +8c × 3 walks/frame | med |
| PF row pool, 4-bit indices | 108 | 36 pool + 18 idx + ~28 code | **~26 net** | room load + nibble unpack; meta moves `+9`→`+3` | med |
| ColOff/ColMask arithmetic (b0+b2) | 80 | ~32 code | **48 raw** | +cycles in PHM/LWC/LHT hot walks | high |
| BombClearMask arithmetic (bank1) | 20 | ~12 code | **8** | bank1 has no ColMask — must derive, cold path | low |
| RaftCellMasks → column math in RaftBody | 20 | ~10 code | **10** | cold (leading edge only), `test_raft` pins it | low-med |
| PF row pool, straight 12×3 | 108 | 72 + ~23 code | **13 net** | below the chunk line | med |
| ObjColorTab → staged color | 72 | 17 + ~40 stage | 47 raw | see "do not do" | — |
| ABW 4 tables → affine | 20 | ~26 code | **−6** | negative, see "do not do" | — |

Re-check of the two deferred items, as asked:

- **ObjColorTab**: unchanged by the repack, and the reason is now measurable in
  numbers rather than prose. The `.Grp1` section's own comment records the
  worst path at **69c work / 72c start-to-start** with `sta WSYNC` required
  ≤ c73, i.e. **4c of margin**. Any per-row discriminator (`lda ObjBase`,
  `cmp`, `bne` = 7-8c worst) breaks the kernel line budget, and staging the
  color needs a write at each of the 8 `sta ObjBase` sites (~40 B), eating
  most of the 47 B. Still deferred — the new layout changed nothing here.
- **PF row pool**: re-measured after C1/C3. 12 blocks (8 models + L1R1, L4R2,
  L4R5, L4R6) × 3 bands = **36 rows, 108 B, 12 distinct triples** (and 12
  distinct individual rows, so triple-pooling and row-pooling are identical
  here). Straight pool = 36 + 36 index = 72 → **13 B net**, still marginal.
  A 4-bit index (12 ≤ 15) is 18 B of indices → **~26 B net** but needs nibble
  unpacking at room load and changes the `TilePF0+9/+10` meta contract that
  six `test_cell_map` reads and `bank2.StageBandTab` depend on.

---

## B. Pins, windows, pads

### Directives

**98 `.ds`/`org` directives** now (was 107): kernel 24, bank1 25, bank2 34,
bank3 15 (includes 4 bank-start `org`s and the ZP `org $80`).

### Fixed pins (address: purpose)

| bank0 | purpose | bank1 | purpose |
|---|---|---|---|
| `$F8C0` | raft CallPad twin address | `$F010` | MothYDerive entry (bank0 pad target) |
| `$F8DD` | `PlayerSpriteA` art, EQUs in other banks | `$F080` | TitleBand literal target |
| `$F9B8` | overlay tramp address (bank2 twin **deleted**) | `$F35A` | retired title movie art |
| `$FBD0` | EnterRoom tramp (bank2 twin) | `$F41F` | M1StripBlast entry (was bank2's) |
| `$FBF8` | ReturnPad (all four banks) | `$F540` | MenuMain (HUD entry, `jmp` target) |
| `$FC49` | MothExitPad (switch target) | `$F8C0` | raft twin prefix |
| `$FC4F` | tail CallPad slot | `$F937` | `StripBlastCheck` (was bank2's back-jmp) |
| `$FC68`/`$FC70` | fold stubs (HUD/game) | `$F9AC` | sound-leaf block start |
| `$FDD8` | BombEnemyBlast tramp | `$F9C0` | sound EQUs (no bytes) |
| `$FE00` | ObjColorTab/ObjSprites page | `$FB10` | BombMarkWalls body |
| `$FE96` | LHT tramp | `$FBF8`/`$FBFF` | ReturnPad + jmp strip |
| `$FEE7` | CallPad_MothYDerive | `$FC1D` | BombMarkWalls image |
| `$FEF0` | UE_MothTramp | `$FC52/$FC55/$FC58` | tail pad jmp slots |
| `$FEF6` | FoldIndirect (bank2 twin) | `$FD00` | DigitGfx page |
| `$FF00`/`$FF20` | fineAdjust + SOXP gap | `$FDE3` | RaftBody |
| `$FFE6` | TallyTramp | `$FEE7` | MothYDerive twin |
| `$FFEC` | HotOverlapFlag | `$FF00` | fineAdjust copy |
| `$FFF2` | F6 hotspot fill ($FFF6-$FFF9) | `$FFE6` | TallyTramp twin |
| `$FFFA` | vectors | `$FFFA` | vectors |

| bank2 | purpose | bank3 | purpose |
|---|---|---|---|
| `$F010` | EnterRoomB2 body | `$F0A3` | level-data window start |
| `$F110` | MothRoutine (bank0 tramp operand) | `$F3B0` | B3RoomBlocks body |
| `$F25A` | LWClamp entry (sim landmark) | `$F453` | `jmp B3RoomBlocks` image |
| `$F450`/`$F458` | block-reader pad + return tail | `$F880` | PhHcrEntry |
| `$F600` | LWC patch-strip body | `$F980` | CrPfx |
| `$F700` | level tables (kernel literal `LEVEL_DATA_ADDR`) | `$FA40` | HOVFeatEntry |
| `$F800` | StageBandTab ping-pong (`jmp $F800`) | `$FBF8` | B3StageBand exit pad |
| `$F854`/`$F864` | spill slots (unused today) | `$FC1A` | BuildColupF entry image |
| `$F880` | fill (TallySum moved out) | `$FC38` | B3StageBand body |
| `$F8B7` | spill-pool gap | `$FFEF` | HotOverlapFlag entry image |
| `$F9D9` | level-spill org (windows below) | `$FFFA` | vectors |
| `$FBD0` | EnterRoom twin | | |
| `$FBF8` | ReturnPad | | |
| `$FC49` | MothExitPad | | |
| `$FD87` | BombEnemyBlastBody | | |
| `$FDD8`/`$FE96`/`$FEF0`/`$FEF6` | blast/LHT/moth/fold twins | | |
| `$FF00` | LHT body (bank0 tramp operand literal) | | |
| `$FFF2`/`$FFFA` | hotspot fill / vectors | | |

### Insertable windows (measured, ≥ 8 B, current free bytes)

| bank | windows |
|---|---|
| bank0 | `$FB08-$FBCF` **200**, `$F820-$F8BF` **160**, `$FC1D-$FC48` **44** (org-able, last code slot before the `$FC49` pin), `$FBD6-$FBF7` **34**, `$F8C6-$F8DC` **23**, `$FC58-$FC67` **16** (pre-pad headroom), `$FDF6-$FDFF` 10, `$FDD0-$FDD7` 8 |
| bank1 | `$FF0F-$FFE5` **215** (page-clean; `$FFF6-$FFF9` reserved), `$F4C7-$F53F` **121**, `$F8C6-$F936` **113**, `$F85C-$F8BF` **100**, `$F3E7-$F41E` 56, `$FCCB-$FCFF` 53, `$FC20-$FC51` 50, `$F995-$F9BF` 43, `$F062-$F07F` 30, `$FEED-$FEFF` 19, `$FBE6-$FBF7` 18, `$FED9-$FEE6` 14, `$FFEC-$FFF9` 14, `$FC5B-$FC67` 13, `$F005-$F00F` 11, `$FB05-$FB0F` 11 |
| bank2 | `$F7A8-$FBCF` **1064** (level-data spill window; level data uses `$F700-$F7A7`), `$F45E-$F5CE` **369**, `$F307-$F44F` **329**, `$FC4C-$FD86` **315**, `$F632-$F6FF` **206**, `$FDDE-$FE95` 184, `$FF59-$FFF9` 161 (ends at the hotspot fill), `$FE9C-$FEEF` 84, `$FBFC-$FC48` 77, `$F0CA-$F10F` 70, `$FBD6-$FBF7` 34, `$F24E-$F259` 12, `$F5F7-$F5FF` 9 |
| bank3 | `$FCF3-$FFEE` **764**, `$F658-$F87F` **552**, `$F1AD-$F3AF` **515** (level-block window, 781 B total, 266 used), `$FA7F-$FBF7` **377**, `$F8A0-$F97F` 224, `$F008-$F0A2` 155, `$F9D5-$FA3F` 107, `$F422-$F452` 49, `$FBFC-$FC19` 30, `$FC1D-$FC37` 27 |

Some of these are **not** free for code: the 3-byte holes at every pad stride
(`$FC52/$FC55/$FC58` in bank1, the `.ds` between corridor `jmp`s) are
A+3 alignment, not capacity. The bank0 `$FFF2-$FFF9` fill is the F6 hotspot
mirror zone — never code.

### `sta $1FFx` pads (49 instructions = 147 B; was 77 = 231 B)

All four banks share the same 4 hotspot addresses; no pad sits in
`addr & $1FFF ∈ $1FF6-$1FF9`. Callers: **27 `jsr CallPad_*` (all in bank0)**,
plus direct paths for EnterRoom (`jsr`, ×5), BombEnemyBlast, LHT, TallyTramp,
FoldIndirect, RaftBody, OverlayTramp, HotOverlapFlag, MothYDerive.

| pad | addr | from → to | status | callers |
|---|---|---|---|---|
| bank-start stub | `$F002` | each → b0 | 4 live copies (boot/bank3 reset) | boot, error paths |
| CallPad_RaftBody | `$F8C0` | b0 → b1 | **twin**: b1 `sta` dead 3 B | `UEDispatch` (1) |
| EnterRoom | `$FBD0` | b0 → b2 | **twin**: b2 `sta` dead 3 B | LoadLevel + 4 exits |
| BombEnemyBlast | `$FDD8` | b0 → b2 | **twin**: b2 `sta` dead 3 B | BombTick (1) |
| LaserHitTest | `$FE96` | b0 → b2 | **twin**: b2 `sta` dead 3 B | LaserInput (1) |
| CallPad_MothYDerive | `$FEE7` | b0 → b1 | **twin**: b1 `sta` dead 3 B | 1 |
| UE_MothTramp | `$FEF0` | b0 → b2 | **twin**: b2 `sta` dead 3 B | UEDispatch (1) |
| FoldIndirect | `$FEF6` | b0 → b2 → b0 | **structural twin** (both halves live) | 4 |
| TallyTramp | `$FFE6` | b0 → b1 | **twin**: b1 `sta` dead 3 B | 2 |
| HotOverlapFlag | `$FFEC` | b0 → b3 | **split** ✓ (b3 keeps only the `jmp`) | PHM path |
| MothExitPad | `$FC49` | b2 → b0 | split, one dead half in **bank0** (3 B) | MothExit |
| ReturnPad | `$FBF8` | all → b0 (rts served by b0) | 4 `sta` live + b0 `rts` | 43 `jmp ReturnPad` |
| corridor CallPads `$FBFC-$FC1A` | 11 pads | b0 → b1 (×10) / b3 (×1) | **split** ✓ | 27 `jsr` |
| tail pads `$FC4F/$FC52/$FC55` | 3 pads | b0 → b1 | **split** ✓ | 3 (TitleSelect/TitleBand/MusicTick) |
| fold stubs `$FC68`/`$FC70` | 2 | b0 ⇄ b1 | **both copies byte-identical**; b0's `$FC68` live, b1's dead 8 B; b1's `$FC70` live, b0's dead 8 B | 1 `jmp $FC68`, 1 `jmp $FC70` |

**Dead bytes: 40 B in 9 places** (7 twin `sta` halves 21 B + MothExitPad
bank0 half 3 B + the two dead fold stubs 16 B). Measured value of reclaiming
them: **0 usable bytes**. Every twin's dead 3 B sits between a `.ds` pin at A
and the mandatory live `jmp` at A+3, so it can only become fill; the fold
stubs are `org`-anchored at both ends, so deleting one shifts the following
code up and the next `.ds` pin eats the shift (bank0's `$FDD0-$FDD7` fill would
grow 8 → 16 B, still not insertable). This confirms, independently, the
conclusion `optimization_cuts_2026-10-20.md` §2 reached from the other side.

### Dead pins (purpose retired by the last three chunks; 0 B each)

| pin | why dead | note |
|---|---|---|
| bank0 `$F9B8` | bank2's overlay twin was deleted — nothing else shares the address | `OverlayTramp` is bank0-local now |
| bank2 `$F3C4` | PickPlayerFrame entry pin (chunk 1) | sits inside the `$F307-$F44F` window |
| bank2 `$F970` | M1StripBlast entry pin (chunk 2) | inside the `$F7A8-$FBCF` window |
| bank2 `$FDE1` | PPF tramp mirror (chunk 1); `verify_build` asserts it is gone | inside `$FDDE-$FE95` window |
| bank2 `$F4C4` | "TitleSequenceFold jmp operand" — TitleSequence no longer exists | inside `$F45E-$F5CE` |
| bank2 `$F5CF` | "TitleSequence retired" — it is just the address where `ColOff` starts | free to float |
| bank1 `$F9AC` | shared M1-hop pad deleted (chunk 2) | inside `$F995-$F9BF` |
| bank1 `$F937` | M1StripBlast back-jmp operand — the body is same-bank now | still asserted by `test_bomb_strip:126` |

Removing them frees no ROM but each one currently *caps* the growth of the
code block in front of it and keeps a stale literal in a guard. bank2 is the
worst case: it carries 5 of the 8.

---

## C. Code — no duplicate blocks, residual is data-coupled

12-byte duplicate scan over all four binaries (fill and pad patterns
excluded, cross-bank and intra-bank):

- **cross-bank**: `bank0 $F089-$F0A5` == `bank1 $FDE3-$FDFF` (29 B) — the raft
  tide triangle. Every other hit is `fineAdjust` (15 B page contract), the pad
  corridor (required by the F6 switch contract), or fill.
- **intra-bank**: **none** ≥ 12 B at distinct addresses.

That is the whole duplicate-code inventory: the repack already removed the
three art twins (48 B) and the overlay/clamp/tally duplicates.

Movable vs pinned after chunks 1-5 (measured `rom_size_report`:
bank2 code **934**, bank3 code **958**):

| bank2 cluster | B | status |
|---|---|---|
| EnterRoom + EBLER | 157 | **pinned** — reads RoomDataTable/RoomEnemies/enemy recs in-bank |
| Moth (incl. walk + gates) | 318 | **pinned in practice** — reads the authored spawn X from `(FetchPtr),Y`; needs a fold twin to leave |
| LaserWallClamp | 193 | movable (plan chunk 5) but **+16 B and 2 switches/beam frame**; deferred |
| BombEnemyBlastBody | 80 | **pinned** — enemy type byte |
| LaserHitTest body | 82 | **pinned** — enemy records |
| FoldIndirect + BandRowFromLine | 33 | **pinned** (fold must live where the data bank is) |
| pads/return tails | ~50 | structural |
| data (ColOff/ColMask/masks + level 168) | 235 | — |

| bank3 cluster | B | status |
|---|---|---|
| B3RoomBlocks + PhaseBlink + BuildColupF + HotOverlap(+feature) + PhHcr + HcrClock | 671 | **pinned** — every one dereferences the room-block/rect stream |
| B3StageBand | 185 | data-free but calls PhaseBlink; relocated inside bank3 (`$F0A3` → `$FC38`) |
| BCFDarkRun | 59 | data-free, tail of BuildColupF |
| pad/return | 10 | structural |
| data (models/blocks 266 + CrPfx 33 + masks 28) | 327 | — |

**Residual data-coupled minimum: bank2 ≈ 866 B code, bank3 ≈ 915 B code**
(cluster sums; the report's 934/958 include alignment rows). Reaching it means
finishing chunk 5 (LWC) and leaving the moth where it is.

Dead-code candidates after the repack: **none found by reference analysis.**
Every col-1 label in all four banks is referenced somewhere except
`TallyTramp_b1` (address-reached twin), `LWpTest` and `SBT_B` (fall-through
labels carrying documentation only). Feature removals left no orphans:
`vcrunch` apply paths were deleted 2026-10-19 (`PhHcrEntry`/`HcrClock`/`CrPfx`
are still live through `PhaseBlink $82`), the tally moved whole (bank2 `$F880`
is fill again), and the title subsystem is fully live (TitleSelect 63,
TitleBand 238, FooterBand 101, TitleFont 48, FooterFont 84, CrPfx 33 — all
reached from `CallPad_TitleSelect`/`CallPad_TitleBand`). The only *stale*
artefacts are the two `TitleSequence` pins in §B.

---

## D. Level data — 434 B, and where the next 50 B are

Measured per file with `convert_level._gen_data_size`:

| level | index | rooms (RoomData+conn+enemies+records) | room blocks | total |
|---|---|---|---|---|
| L1 (2 rooms) | 9 | 20 (4+4+4+8) | 19 | 48 |
| L2 (2 rooms) | 9 | 16 (4+4+4+4) | 0 | 25 |
| L3 (6 rooms) | 9 | 60 (12+12+12+24) | 0 | 69 |
| L4 (6 rooms) | 9 | 36 (12+12+12+0) | 81 (L4R2 24, L4R5 17, L4R6 40) | 126 |
| models | — | — | 166 (19,19,19,21,25,25,19,19) | 166 |
| **sum** | **36** | **132** | **100** | **434** |

C1-C4 are all in: index stride 9, one `RoomRects` word per room (TilePF0 =
`rects + 2 + 2·nrect`), 2-byte `RoomEnemies`, 3 shared blocks. Block layout is
`nrect, rects (2 B each), hot-count, PF0/1/2, MetaA, MetaB` with meta at
`TilePF0+9/+10`; 11 of 12 lists have `hot-count = 0` (L4R2 has 1, with the
5-byte hcrunch prefix).

Further converter-side reductions (bytes measured from the current files):

| change | save | risk | detail |
|---|---|---|---|
| Sparse band byte: 15 of 16 `RoomEnemies[+1]` are `$00` | **14** | med | keep a 1-byte "band present" flag in the `RoomEnemies` byte (bits are free: count ≤ 3, first-record index ≤ 31 fits 5 bits with count in b5-6) + one (room, color) pair for L2R1 |
| Drop the always-zero hot-count byte (11 of 12 lists) | **11** | med | `nrect` is 1-3, so b7 can be the hot flag; L4R2 keeps its prefix |
| Enemy record 4 B → 3 B (type 3b, dir 1b, x 8b, y 7b) | **9** | med | 9 records; readers: EBLER load, moth spawn-X, blast type, LHT |
| Index: `start_room` is 0 in all 4 levels, `miner_y` is 84 in all 4 | **8** | low | two constants move into the kernel (already fixed at 32/24 for start x/y) |
| PF row pool, 4-bit indices | ~26 net | med-high | see §A; breaks the `+9` meta contract |
| Room blocks: L4R5 vs L4R6 differ only in PF row 1 and MetaA/B | 0 | — | not byte-identical, C1 cannot share them |

Total realistic next step **~42 B** (first four rows, no contract change to the
meta offset), taking the level data to ~392 B. Migration: converter
(`tools/convert_level.py`), the bank2 loader (`EnterRoomB2` band/enemy base
math), `verify_build` block checks, and a re-freeze of
`src/tests/frozen/bank{2,3}.*` + `src/tests/generated/`. Note that level bytes
are *not* scarce right now (bank3 has 515 B of slack in the 781 B block
window, bank2 has 1064 B) — the value is the per-room floor (currently 8 B/room
before enemies) and the smaller emitted set for new content.

---

## E. Test quality — `tools/test_water_respawn.py` (diagnosed, not edited)

Reproduced on the live tree: `total deaths=0 (lives lost 0); loop
deaths after respawn=0` → `PASS`. Two independent defects, both measured with
a py65 probe against `bank0.lst` labels:

1. **The band poke lands after the room load, so the water is never on.**
   `RoomBandColor` (`$BC`) is staged **once per room** by `EnterRoomB2` from
   `RoomEnemies[room]+1` (bank2.asm:202-203). The test pokes the ROM byte at
   the first `StartFrame` where `DropTarget ∈ {0,$FE,$FD}` — that is **frame
   3**, after `LoadLevel → EnterRoom` already ran (frame 0-1). Probe output:

   ```
   f1: Level=1 base=$F738 RoomN=2 RoomNo=0 RoomY=24 BandColor=$00 DropTarget=$FF
   f3: Level=1 base=$F738 RoomN=2 RoomNo=0 RoomY=130 BandColor=$00 DropTarget=$18   <- poke frame
   ```

   `BandColor` stays `$00` for the whole run, so `CheckBandTouch`
   (`lda RoomBandColor / beq .CBTdone`) never fires and the player just rests
   at `RoomY=131` in the strip.
2. **The gate passes when nothing happens.** `loop_deaths =
   max(0, len(deaths)-1)` is 0 for both "no loop" and "no death at all", so a
   scenario that never enters the water is indistinguishable from a fix.
   `RoomY` is also forced on the same frame the poke happens, which is during
   the `DropTarget=$18` drop-in.

**Exact fix** (proposed, not applied):

- Hook the room load instead of a StartFrame: `ENTERROOM = _LBL["EnterRoom"]`
  (= `$FBD0`), and in the step loop
  `if mem.bank == 0 and mpu.pc == ENTERROOM:` poke there — `$9F/$A0`
  (`LevelPFDataLo/Hi`), `$A1` (room count) and `$A2` (`RoomNo`) are already
  valid, and bank2 has not read the byte yet. Verified: with this hook the
  staged value is `$1C` and the death fires (`f7: RoomY=131 → f8: RoomY=0,
  DropTarget=$77, Hover=1`). The hook also re-pokes after the RESET pulse
  (frames 2/5) automatically.
- Address: `base + 4*n + 2*RoomNo + 1`, not `base + 4*RoomN + 1`. The current
  form is only correct for room 0 (it happens to give `$F741` for L2 room 0,
  which is the right byte today, by coincidence of `4n`).
- Gate: require `len(deaths) >= 1` and `mem.ram[0x3C] == 0x1C` (RoomBandColor)
  plus `min_lives <= 2`; print FAIL when no death occurs. That makes the test
  fail loudly on a future regression instead of passing silently.

---

## F. Ranked implementation plan

| # | change | ~B | risk | files | dependency |
|---|---|---|---|---|---|
| 1 | Fix `test_water_respawn` (EnterRoom hook + exact band address + positive gate) | 0 ROM | low | `tools/test_water_respawn.py` | none — highest value/effort in this audit: it currently cannot fail |
| 2 | Delete the 8 dead pins + refresh the 2 stale guard literals | 0–8 | low | kernel/bank1/bank2.asm, `verify_build`, `test_bomb_strip:126` | none; do it before adding code near `$F3C4/$F970/$F9B8/$FC49` |
| 3 | Level-data: sparse band byte + hot-flag bit + 3-byte enemy records + index constants | **~42** | med | `tools/convert_level.py`, bank2 loader, `verify_build`, re-freeze | after 2 (same bank2 tables) |
| 4 | YToRowTable → inline compares | 29 | med | kernel.asm | independent; measure VBL with `sim_frame_budget` |
| 5 | PF row pool with 4-bit indices (level data) | ~26 net | med-high | convert_level, bank3 room load, `test_cell_map` (6 `+9` reads), re-freeze | after 3, same generator |
| 6 | RaftCellMasks → column math in `RaftBody` | 10 | low-med | bank1.asm, `test_raft` | independent |
| 7 | BombClearMask → derive in bank1 (no cross-bank read) | 8 | low | bank1.asm | independent |
| 8 | LWC → bank0 (repack chunk 5) | **−16** (costs) | high | kernel/bank2, `sim_frame_budget:460` landmark | only if bank2 windows are needed |

Rows 1-2 are worth doing now and cost nothing at runtime; row 3 is the only
entry that changes what new content costs per room.

## G. Do not do (measured reasons)

- **ObjColorTab shrink (47 B claim).** `.Grp1` worst path is 69c of a 73c
  WSYNC budget; any per-row discriminator is 7-8c. Staging the color costs
  ~40 B of `sta ObjBase` sites. Net risk >> net bytes.
- **Reclaim the dead twin `sta` halves as ROM.** 40 B of dead bytes, **0**
  insertable: each sits between a `.ds` pin and the live `jmp` at A+3.
- **ABW 4 tables → affine.** Measured **negative**: 6 read sites × (+3 B) +
  6 B helper − 20 B tables = **+4 B**, and it adds 8c per site on the bomb
  path. (The first audit's "+14 B" assumed one site.)
- **BombClearMask from ColMask.** bank1 has no `ColMask`; copying it (20 B)
  cancels the win. Only the arithmetic form (8 B) is positive.
- **Deduplicate the raft tide triangle (29 B).** The shared input is
  `EnemyRamP`; the computed `off` is carried in `CollisionX`, which the input
  rect-walks clobber before `UpdateEnemies`, and there is no free ZP byte
  (sequential block is full, `$E0-$EF` is the bank1 HUD stomp zone,
  `$F8-$FF` is stack). Leave the hand-synced mirror.
- **Pack MusicMel / re-list it as a 51 B saving.** Already packed: 51 B +
  `MelDur` 4 B (source says `note*4 + duration`).
- **Straight 12×3 PF pool.** 13 B net — under the chunk line; use the 4-bit
  variant or skip.
- **Replace BeamMask with compares.** 4c table fetch vs 6-7c of compares in
  the kernel's tightest section.
- **Pack DigitGfx/TitleFont/FooterFont/CrPfx.** All three renderers read rows
  directly with `(ptr),Y`; a packed format touches three kernels for ~0 B of
  real headroom (we have 7410 B free).
- **Single-gateway RTS dispatch for the CallPads.** Already measured and
  skipped in `optimization_audit_2026-10-20.md` §B; still true: 27 call sites
  × id byte + ~21c/call against a ~20-220c overscan margin.
- **Move the moth cluster (318 B) out of bank2.** It reads the authored spawn
  X from `(FetchPtr),Y`; leaving needs a fold twin (+9 B) and splits 297 B
  across two bank1 windows, with +2 switches per moth move — and bank2 has
  1064 B free.
