# Code repack plan — moving code out of bank2/bank3 (2026-10-20)

**Status: executing (chunk ledger at the bottom).** Baseline: HEAD with `9452 used / 6932 free`
(bank0 3376 = 3026 code + 350 data, bank1 3015 = 2513 + 502, bank2 1760 =
1399 + 361, bank3 1301 = 933 + 368) from `tools/rom_size_report.py`.
Per-label byte counts below are label spans measured from `bank*.lst`
(`next label addr − label addr`, `.ds` fill excluded); cluster sums land
within 8 B of the report (inter-label alignment rows), and the report stays
authoritative for totals.

**Verdict up front:** banks 2/3 hold **3061 B used**, while bank0+bank1 offer
**1801 B free** — so "code-free banks 2/3" is arithmetically impossible, before
any data-coupling argument. The realistic best split moves **639 B of bank2
code** (46 % of its 1399 B) into bank0/bank1 and **0 B out of bank3** (its code
is the level-data walker); bank3's real win is an *intra-bank* relocation that
opens 189 B of data window. Residual code in banks 2/3: **1693 B**.

---

## 1. Inventory (measured)

### bank2 — 1399 B code, 361 B data

| # | cluster | labels (bytes) | code | entry | callers (bank) | data read (bank) |
|---|---|---|---|---|---|---|
| B2-1 | EnterRoom | EnterRoomB2 35, ERBlocksDone 17, .EBrec 44, EBLER_Loop 32/Dir 13/Left 9/Next 4/Done 3 | 157 | twin tramp `$FBD0` (bank0 `sta $1FF8`; bank2 holds the `jmp $F010` image) | bank0 `jsr EnterRoom` ×5 | RoomDataTable/RoomEnemies/enemy recs (**b2**, via ZP ptrs), PF0Buf (ZP) |
| B2-2 | Moth AI | MothRoutine 9, .MothRun 17/.MothR 5/.MothChk 7/.MothChk2 23/.MothRangeOk 3, MothDoWalk 36, .Mvl7a 2/.MvlA 15/.MothC1 14/.Mvl7b 2/.MvlB 16/.MothC2 14/.MothColsOk 38/.MovT2 11/.MwSym 4/.MwRow 4/.MwCol 29/.MwRowDone 10/.MwHit 3/.MothNoHit 9/.MothTurn 9, MothExit 11, MothGate 21/.MothGateWalk 6, MothBitTable 3 | 291+27 | tramp `$FEF0` (bank0 `jmp UE_MothTramp`) | bank0 UE dispatch | enemy record (**b2**), ColOff/ColMask/OvHead/OvTail/MothBit (**b2**), PF0Buf (ZP) |
| B2-3 | Laser wall clamp | LaserWallClamp 33, .LWtipL 10/.LWtipC 37, .LWm1Skip 9/.LWm1Solid 5, LWpNotPatch 11/.LWsrc 5/.LWrow 25/.LWclear 3/LWpSolid 5, LWpSetup 31/.LWpNone 2/.LWpSet 2/LWpTest 12/.LWhit 3 | 193 | same-bank tail `jmp` from LHT body `$FF00` | bank2 LHT | PF0Buf (ZP), ColOff/ColMask/OvHead/OvTail (**b2**) — **no level data** |
| B2-4 | Tally | TallyEntry 43, .TEOne 5/.TEFinal 5/.TEIdle 5/.TEArm 7/.TEDiv 10/.TEDivSum 22, TallySum 23 | 120 | tramp `$FFE6` | bank0 `jsr TallyTramp` ×2 | ZP/TIA only |
| B2-5 | Player frame | PickPlayerFrame 30, .WalkA 7, .Jet 13, .FrameA 4, .SetGrpPtr 7 + art 48 | 61 | tramp `$FDE1` (bank0 VBL `jsr`) | bank0 VBL | art at **b2** `$F8DD`/`$FDE7` (byte-copies of bank0's) |
| B2-6 | M1 overlay | OvM1Block 38, .OvM1T2 17/.OvM1Band 13/.OvM1Row 27/.OvM1block 7/.OvM1unlock 10/.OvM1no 4 | 116 | same-bank `jmp` from PHM `$FE00` / OvShut | bank2 | PF0Buf (ZP), ColOff/ColMask/M1OffTab (**b2**) |
| B2-7 | PHM patch | PHMOverlay 15, .Ov7 2/.OvVL 29/.OvT2 11/.OvClear 3/.OvBand 3 | 63 | tramp `$F9B8` | bank0 `jmp OverlayTramp` | ZP only |
| B2-8 | Shutter | OvShutBand 31, .OSBsolid 4, .OSBm1 3 | 38 | same-bank | bank2 | ZP + OvHead/Tail (**b2**) |
| B2-9 | M1 blast | M1StripBlast 33, .M1SBnone 4/.M1SBdoorR 8/.M1SBout 3 | 48 | pad `$F9AC` (from bank1 `.BMWDone`) | bank1 | ZP only (RoomMetaA/B, RectCount) |
| B2-10 | Blast | BombEnemyBlastBody 14, .BEBLoop 40/.BEBAbsCol 16/.BEBNext 5/.BEBnone 5 | 80 | twin pad `$FDD8` | bank0 `jsr BombEnemyBlast` | enemy recs + EnemyBit/Off (**b2**) |
| B2-11 | LHT | LaserHitTestBody 3, LaserClampDone 10, .LHLoop 35/.LHHit 21/.LHLamp 5/.LHNext 3/.LHTOut 5 | 82 | tramp `$FE96` | bank0 `jsr LaserHitTest` | enemy recs (**b2**) |
| B2-12 | Fold | FoldIndirect 9 (byte-identical twin of bank0's) | 9 | bank0 `jsr` ×4 | bank0 | `(FetchPtr)` → **b2/b3** level data |
| B2-13 | Cell helper | BandRowFromLine 15, .BR1 3/.BR2 3/.BR3 3 | 24 | `jsr` (bank2 moth/LWC/LHT) | bank2 | none |
| B2-14 | Pads/twins | ReturnPad 4, ERBlocksPad 12, return tail 6, CallPad_BuildColupF 6, MothExitPad 3, M1ToBank2 6/M1ToBank1 6, OverlayTramp 10, `$FBD0` 6, `$FDD8` 6, PPF tramp 6, LHT tramp 6, UE_MothTramp 6, TallyTramp 6, HotOverlapFlag 6 | 95 | — | — | — |
| B2-15 | Data | ColOff/ColMask 40, OvHead/OvTail 6, M1OffTab 2, EnemyOff 3, EnemyBit 8, MothBit 3, TitleJetSprite 24, walk art 24, level tables 244 (see §5) | — | — | — | — |

Cluster sum **1407** vs report **1399** (Δ −8 alignment). Three bank2 routines
read **bank2 level data directly** and cannot leave without it: EnterRoom/EBLER
(room + enemy tables), Moth (spawn X), Blast + LHT (enemy type byte).

### bank3 — 933 B code, 368 B data

| # | cluster | labels (bytes) | code | entry | data read (bank) |
|---|---|---|---|---|---|
| B3-1 | Stage band | B3StageBand 20, .SBTb0z 13/.SBTb1z 14/.SBTb2z 16, .SBTstripAlive 17, .M1zero 2/.M1got 12/.M1stage 21, .SBTnoBall 10/.SBTballDone 7, SBT_B 6, .M1nof 28, .SBTp0 6/.SBTp1 6/.SBTp2 4, .SBTPack 3 | 185 | tail `jmp` from BCFDarkRun (BuildColupF chain, entered bank0/bank1 `CallPad_BuildColupF`) | ZP + M1OffTab (**b3** 2 B); `jsr PhaseBlink` (b3) |
| B3-2 | Room blocks | B3RoomBlocks 18, .EBrcCntOk 5/.EBrcW 44/.EBpf 28 | 95 | pad `$F450` (bank2) | per-room block stream (**b3**, via ZP ptrs) |
| B3-3 | Phase blink | PhaseBlink 16, .PhNoDoor 8/.Phm1 6/.Phm2 10/.PhfOff 2/.PhfSt 25, PhRec 22, .PhPhase 28, .PhOffA 30/.PhOff 9, PhNext 5/.PhSkip 7/.PhDone 1 | 169 | `jsr` from B3-1 | rect/phase stream (**b3**), PhMaskTab (**b3**), PF0Buf (ZP) |
| B3-4 | BuildColupF | 2+9+2+18+2+26+23+17+9+3 | 111 | CallPad `$FC32` (bank0 + bank1) | rect stream (**b3**) |
| B3-5 | Dark run | BCFDarkRun 16, .BCFhi 14/.BCFon 12/.BCFFuseGrey 2/.BCFdarkFill 2/.BCFdarkLoop 7/.BCFdarkDone 6 | 59 | tail from B3-4 | ZP + BCFDarkMask (**b3**) |
| B3-6 | Hot overlap | HotOverlapBody 24, .HOVloop 16/.HOVwallGate 4/HOVafterGate 11/.HOVcolOk 26/.HOVrowOk 31/HOVlegHit 11/HOVnext 9/.HOVdone 4/.HOVfeature 13 | 149 | pad `$FFEC` (bank0 **and** bank2) | rect stream (**b3**) |
| B3-7 | Phase crush | PhHcrEntry 32 | `jmp` from B3-3 | FetchPtr (**b3**), CrPfx (**b3**) |
| B3-8 | Crush clock | HcrClock 7, .hcN 14/.hcNd 9/.hcNf 8/.hcOut 11/.hcR 3 | 52 | `jsr` (b3 ×2) | ZP only |
| B3-9 | Feature overlap | HOVFeatEntry 7, .HFnotPhase 9, .HFh_begin 27, .HFmissJ 3/.HFkill 3/.HFmiss 3, .HFphase 11 | 63 | `jmp` from B3-6 | rect stream (**b3**) |
| B3-10 | ReturnPad | 10 | shared pad | — |
| B3-11 | Data | M1OffTab 2, CrPfx0-2 33, BCFDarkMask 8, PhMaskTab 10, models+per-room blocks 304 (window `$F160-$F290`), vectors 6 | — | — | — |

Cluster sum **925** vs report **933** (Δ 8). **740 of 925 B dereference the
bank3 block stream** (`RoomRectsLo/Hi`, `RoomPF0Lo/Hi`); only B3-1 (185) and
B3-5 (59) are data-free, and B3-1 calls B3-3 (data-bound), so B3-1 is not
separable for free.

---

## 2. Classification

| bucket | what | bank2 | bank3 | total |
|---|---|---|---|---|
| **(a) movable now** — reads only ZP/TIA/PF0Buf plus small in-bank tables that travel with it (or already exist in the target bank) | B2-3 LWC 193, B2-4 Tally 120, B2-5 PPF 61 (+48 art), B2-6 116, B2-7 63, B2-8 38, B2-9 M1 blast 48; B3-1 StageBand 185, B3-5 DarkRun 59 (with a PhaseBlink pad) | **639** | **244** | **883** |
| **(b) movable only with its data** | B2-2 moth 321 (its single bank2 read is the authored spawn X at `(FetchPtr),Y`; needs 3 B of RAM or a fold) — *also placement-blocked, see §3* | 297 | 0 | 297 |
| **(c) must stay** — dereferences bank2 tables / bank3 block stream | bank2: B2-1 157, B2-10 80, B2-11 82, B2-12 9, B2-13 24, plus the 95 B of pads (53 of them after the moves); bank3: everything except B3-1/B3-5 | **471** | **681** | **1152** |

(a)+(b)+(c) = 883 + 297 + 1152 = 2332 = bank2 1399 + bank3 933 (cluster sums
carry a ±8 alignment each way). Note (a) is code only: the 48 B of duplicated
art dies with B2-5 and 42 B of pads die with B2-5/B2-9/B2-4.

---

## 3. Placement map

Free windows measured as bytes with no emitted code/data (`.ds` fill = free),
>= 23 B (bank0/bank1). Audit agrees within 10 B.

| bank | window | B | notes |
|---|---|---|---|
| bank0 | `$F9F5-$FBCF` | **475** | one span; the `$FB00`/`$FB37` `.ds` pins inside are **dead** (TitleFont/TitleIntro retired) and must be deleted to use it. `$FBD0` (EnterRoom twin) is live — stop before it. |
| bank0 | `$F836-$F8BF` | 138 | after `$F8DD` PlayerSprite pin |
| bank0 | `$FBD6-$FBF7` | 34 | before ReturnPad pin |
| bank0 | `$F8C6-$F8DC` | 23 | |
| bank1 | `$F41F-$F53F` | **289** | largest contiguous |
| bank1 | `$F24F-$F359` | 267 | |
| bank1 | `$FF0F-$FFF5` | 231 | page-clean; `$FFF6-$FFF9` = F6 hotspot mirrors, keep fill |
| bank1 | `$F8C6-$F936` | 113 | |
| bank1 | `$F85C-$F8BF` | 100 | overlap with bank3 `$F85C-$F87F` = 36 B → usable as a **shared pad address** |
| bank1 | `$FCCB-$FCFF` 53, `$F062-$F07F` 30, `$F9AC-$F9BF` 43 (after chunk 2) | 126 | pad slots |

Rules applied: a pad's `sta $1FFx` is 3 B at address T, and the **next fetch
comes from the target bank at T+3** (F6). Only the leading `sta` is
target-bank-dead; the `jmp` opcode+operand must be byte-identical and at the
same address in both banks. No live pin is moved; pins die only when *both*
halves of a pair die.

| move | to | code B | tables/art to target | pads freed (source) | pads added (target) | net ROM | pins that die |
|---|---|---|---|---|---|---|---|
| B2-5 PPF | bank0 `$F9F5` | 61→59 (`jmp ReturnPad`→`rts`) | 0 (bank0 already has both art sets at `$F8DD`/`$FDE7`) | 6 + 6 (both tramps) + 48 art | 0 | **−62** | `$F3C4`, `$FDE1` ×2, `$F8DD`/`$FDE7` twins |
| B2-9 M1 blast | bank1 `$F41F` | 48 | 0 | 12 (`$F9AC` both banks) | 0 (same-bank caller) | **−24** | `$F970`, `$F9AC` |
| B2-4 Tally | bank1 `$F44F` (120) + pad `$FFE6` | 120 | 0 | 6 (b2 `$FFE6`) | 6 (bank1 `$FFE6`; bank0 operand changes) | 0 | `$F313`, `$F880` |
| B2-6/7/8 overlay | bank0 `$FA30` | 217→216 (3 `rts`) + 5 prologue | OvHead/OvTail 6 + M1OffTab 2 | 10 (b2 `$F9B8`) + 6 (b2 `$FFEC`) + 2 (M1OffTab) | 0 (reuses bank0 `HotOverlapFlag` `$FFEC`) | **−13** | `$FE00`, `$F632`, `$F9B8`(b2), `$FFEC`(b2) |
| B2-3 LWC | bank0 `$FB08` / miss-pad `$F836` | 193→191 (`rts`) | 0 (ColOff/ColMask + OvHead/Tail already in bank0 after the overlay move) | 0 | 6 (+6 b2 twin) | +16 | `$F25A` (b2) → bank0 |
| *(stretch)* B2-2 moth | bank1 split `$F24F`+`$FF0F` | 297 | MothBit 3 + fold 9 | 6 (`$FEF0` entry) | 6 entry + 9 fold twin (b2) | +12 | `$F110` |
| B3-1/B3-5 | **stay in bank3** — relocate `$F0A3`→`$FC38` inside bank3 | 0 | 0 | dead `$F3AC` image 3 | 0 | **−3** | `$F3AC` |

Bank0 budget: 59 (`$F9F5-$FA2F`) + 216 (`$FA30-$FB07`) + 191 (`$FB08-$FBC6`) =
**466 of 475**, 9 B spare (miss-pad in `$F836`). Bank1 budget: 48 + 126 =
**174 of 1081** for the recommended set.

---

## 4. Ordered chunks (each independently buildable + green)

### Chunk 1 — PickPlayerFrame → bank0 (safest, highest value)
- **Files:** `kernel.asm` (place body at `$F9F5`, delete `$FDE1` tramp), `bank2.asm` (delete body `$F3C4-$F400`, `$FDE1` tramp, `TitleJetSprite` `$F8DD`, walk art `$FDE7`), `tools/verify_build.py` (delete `check_frame_tramp`), `tools/test_miner_colors.py` (it currently asserts the bank2 art twins).
- **Why safe:** the bank2 body already emits bank0's art addresses (`#<PlayerSpriteA` = `$F8DD`, `#<PlayerWalkA` = `$FDE7`), so the move is a literal 61 B copy plus `jmp ReturnPad`→`rts`.
- **Net:** bank2 **−115** (61 code + 6 tramp + 48 art), bank0 −6 tramp +59 code = **−62 ROM**, 3 pins gone, VBL saves 2 bank switches (~14 c).
- **Risk:** low (pure VBL leaf; verify with `sim_frame_budget`, `sim_bomb_fuse`).

### Chunk 2 — M1StripBlast → bank1 (kills a 2-hop pad chain)
- **Files:** `bank1.asm` (body into `$F41F`, delete `M1ToBank2`/`M1ToBank1` `$F9AC`), `bank2.asm` (delete body `$F970`, the `$F9AC` twin, `M1ToBank1`), `tools/test_bomb_strip.py` (hard-codes `PAD_BYTES` at `$F9AC`, `M1StripBlast==$F970`).
- **Net:** bank2 **−60** (48 code + 12 pads), bank1 +36 (48 − 12), **−24 ROM**. The bank1 path `BombMarkWalls .BMWDone → M1StripBlast → StripBlastCheck` becomes same-bank (0 switches instead of 2).
- **Risk:** low (`ReturnPad` tail + A contract unchanged; run `test_bomb_strip`, `test_bomb_lamp`, `test_bomb_half_wall`).

### Chunk 3 — Tally → bank1
- **Files:** `bank1.asm` (TallyEntry 97 + TallySum 23 at `$F44F`, pad at `$FFE6`), `bank2.asm` (delete `$F313-$F375`, `TallySum` `$F880`, `$FFE6` tramp), `kernel.asm` (`TallyTramp` `sta $1FF7` + new operand), `verify_build.py` (Tally tramp target check, if any).
- **Net:** bank2 **−126**, bank1 +126, **0 ROM**. Two hard `org`s (`$F313`, `$F880`) disappear. Keep the `$F3C4` pin until chunk 1 lands.
- **Risk:** low (ZP/TIA only; runs on the tally frame where the HUD is bank1 anyway). Run `sim_bomb_fuse` (stack guard) + `sim_frame_budget`.

### Chunk 4 — PHM Overlay + M1 overlay + shutter → bank0
- **Files:** `kernel.asm` (3 bodies at `$FA34`; `OverlayTramp` body→inline prologue; keep `HotOverlapFlag` `$FFEC`), `bank2.asm` (delete `$FE00`, `$F632`, `$FE9C`, `$F9B8`, `$FFEC`, `M1OffTab`), `verify_build.py` (`check_fold_block`/`tramp_targets` literals), `tools/test_cell_map.py` + `test_phm_walk.py` (bank2 label/address assertions).
- **Net:** bank2 **−235**, bank0 +222, **−13 ROM**, 3 pins gone. Overscan saves one round trip (entry+return switch) — the walk already ends in a tail `jmp`, so no stack change.
- **Risk:** medium-low (hot per-frame path, but *fewer* switches). Gate on `sim_frame_budget` + `sim_bomb_fuse`.

### Chunk 5 — LaserWallClamp → bank0 (optional; hot path)
- **Files:** `kernel.asm` (LWC at `$FB0B`, miss-pad `$F836`), `bank2.asm` (`jmp LaserWallClamp`→pad `$FFEC` area; twin at `$F836`), `src/sim_frame_budget.py:460` (landmark `bank2 $F25A`), `tools/test_phm_walk.py` (regex on bank2 `LaserWallClamp:`…`MothGate:`).
- **Net:** bank2 **−181**, bank0 +197, **+16 ROM**, `$F25A` pin moves out of bank2.
- **Risk:** high for its value — 2 extra bank switches per beam frame and it edits the sim's landmark. **Recommend deferring** unless bank2's `$F0AD-$F10F`/`$F6A6-$F6FF` holes are needed.

### Chunk 6 — bank3: relocate B3StageBand inside bank3 (recommended over moving it out)
- **Files:** `bank3.asm` (`org $F0A3` body → `org $FC38`; delete the dead `.byte $4C,<B3StageBand` image at `$F3AC`; `org $F160` → `org $F0A3` for `spill_bank3.asm`), `tools/test_bomb_strip.py` (`$F0A3` literal), re-run `convert_level.py --levels` + `tools/freeze_test_banks.sh`.
- **Net:** 0 cross-bank bytes, −3 ROM, **level-block window +189 B** (588 → 777 B; current use 304 B, slack 284 → 473). No new pads, no switch, VBL chain stays local.
- **Risk:** low-medium (address regeneration shifts every block label; `test_band_restage`, `test_asym_data`, `test_features_data` must be re-run).

### Chunk 7 (stretch, not recommended now) — moth → bank1 with a fold
- Requires a bank1 copy of `FoldIndirect` (9 B) + a byte-identical bank2 twin (9 B) to read the spawn X, the entry pad, and a **split** of the 321 B cluster across two bank1 windows (no window is ≥297 B). bank2 −318, bank1 +351, +12 ROM, +2 switches per moth move.
- **Risk:** high (enemy AI + fold pin + split branches). Only worth it if bank2's level-table window ever runs out — it currently has 503 B unused at `$F9D9-$FBD0`.

---

## 5. Residual

After the recommended chunks (1-4), plus 5 if taken:

| bank | code before | after 1-4 | after +5 | data | note |
|---|---|---|---|---|---|
| bank2 | 1399 | **953** | 760 | 361 → 311 | EnterRoom/EBLER 157, moth 321, LHT 82, blast 80, Fold 9, BandRowFromLine 24, pads ~62, minus the 50 B of art/data that leave |
| bank3 | 933 | **933** | 933 | 368 | 740 B is the room-block walker; StageBand/DarkRun stay (relocated in-bank) |
| **total** | 2332 | **1886** | 1693 | 679 | |

**Why the residual cannot shrink further:**

1. **The data is the anchor.** bank2 holds the level tables at `$F700`
   (`LEVEL_DATA_ADDR` is a kernel literal; `RoomsDataTable`, connections,
   `RoomEnemies`, enemy records) — 244 B — and bank3 holds models + per-room
   blocks — 304 B. A reader can only dereference those bytes while its own bank
   is selected, so **every reader is pinned to the data bank**: EnterRoomB2 +
   EBLER (157), moth (321, one record read), LHT (82), bomb blast (80),
   FoldIndirect (9) in bank2; B3RoomBlocks/PhaseBlink/BuildColupF/HotOverlap +
   crush chain (740) in bank3.
2. **Space is already the binding constraint.** To empty banks 2/3 you would
   have to relocate **3061 B** of code+data into bank0+bank1, which have
   **1801 B** free (720 + 1081) — short by 1260 B before any pad overhead. The
   largest contiguous window anywhere in bank0/bank1 is 475 B.
3. **Placement is fragmented.** bank1's biggest window is 289 B; the moth
   cluster (297 B) does not fit contiguously, and the overlay had to go to
   bank0 precisely because bank1's `$F9C0` slot (where bank0's overlay pad
   lands) is occupied by the leaf-sound block.

**Code-free banks 2/3: not reachable.** Best measured split leaves **953 B of
code in bank2** (760 with the laser clamp) and **933 B in bank3**, i.e. 1886 B
(1693 B) of the 2332 B baseline — 73-81 % stays. The repack's real prize is
structural: 15 pin/`.ds` sites deleted (including both art twins), 4 bank
switches per frame removed, and bank3's level-block window grown by 189 B.

---

## Appendix — measurement notes

- Label spans: `bank2.lst`/`bank3.lst` rows, `next_label_addr − label_addr`,
  `.ds` rows counted as fill (free), EQU rows skipped. Cross-checks:
  bank3 cluster sum = 925 vs `rom_size_report` 933; bank2 sum = 1407 vs 1399.
- Routine bodies were read in `kernel.asm`, `bank1.asm`, `bank2.asm`,
  `bank3.asm` to classify each dependency; all `jsr`/`jmp`/pad targets were
  followed by hand (including the label-less `.byte` twins at `$FBD0`, `$FDD8`,
  `$F45B`, `$F3AC`).
- Data sizes from `generated/*.asm` + `convert_level._gen_data_size`
  (level 548 B = index 48 + tables/blocks 334 + models 166).
- Do **not**: move a pad instead of deleting a pair; give a target bank only
  the `jmp` at T+3 while the source bank keeps a different `sta` (both halves
  must be identical at the same address); reuse a freed bank2 address as a new
  pad without checking `addr & $1FFF ∉ $1FF6-$1FF9`.

---

## 6. Execution ledger (measured after each move)

Re-measured at the start of execution (HEAD `0110bb6`, C1 landed):
`9283 used / 7101 free` — bank0 3373, bank1 2887, bank2 1760, bank3 1263,
level data 510 B. The per-cluster sizes in §1 still hold (±8 B), so the
chunk targets below were kept.

### Chunk 1 — PickPlayerFrame → bank0 ($F9F5) — LANDED

| | before | after | Δ |
|---|---|---|---|
| bank0 | 3373 | 3426 | +53 (59 B body − 6 B tramp) |
| bank1 | 2887 | 2887 | 0 |
| bank2 | 1760 | 1645 | **−115** (61 body + 6 tramp + 48 art) |
| bank3 | 1263 | 1263 | 0 |
| **total** | **9283** | **9221** | **−62** |

Pins killed: `$FDE1` tramp (bank0 + bank2), `$F8DD` jet-art twin, `$FDE7`
walk-art twin. Body tail is `rts` (−2 B) instead of `jmp ReturnPad`: the VBL
`jsr` now resolves in-bank. Bank2's `Grp0Ptr`/`Grp0PtrHi`/`SWCHA`/art EQUs
deleted with the body. `verify_build.check_frame_tramp` now asserts the body
lives in bank0 and that bank2 has no `PickPlayerFrame` label; `test_miner_
colors` section 2 checks the same + the bank0 `lda zp` entry, `test_title_
demo` asserts the twin is gone.

### Chunk 2 — M1StripBlast → bank1 ($F41F) — LANDED

| | before | after | Δ |
|---|---|---|---|
| bank0 | 3426 | 3426 | 0 |
| bank1 | 2887 | 2923 | +36 (48 B body − 12 B pads) |
| bank2 | 1645 | 1585 | **−60** (48 body + 12 pads) |
| bank3 | 1263 | 1263 | 0 |
| **total** | **9221** | **9197** | **−24** |

`BombMarkWalls .BMWDone → M1StripBlast → StripBlastCheck` is now same-bank
(0 switches instead of 2). Pins killed: bank2 `$F970`, the 12 B shared hop pad
at `$F9AC` (both banks). One trap paid for: `Temp` in bank1 is `$AD`
(= bank0 `TickCounter`), so the staging write uses `BMWScratch` (`$88`) —
the bank2 copy's `sty Temp` would have killed the game timer. `RoomMetaA/B`
EQUs hand-copied into bank1. `test_bomb_strip` now asserts the body at
`$F41F`, that bank2 no longer has `M1StripBlast`, and keeps the `$F937`
layout pin.

### Chunk 3 (plan chunk 4) — PHM/M1/shutter overlay → bank0 ($FA30) — LANDED

| | before | after | Δ |
|---|---|---|---|
| bank0 | 3426 | 3642 | +216 |
| bank1 | 2923 | 2923 | 0 |
| bank2 | 1585 | 1348 | **−237** |
| bank3 | 1263 | 1263 | 0 |
| **total** | **9197** | **9176** | **−21** |

*Placement re-derived:* the cluster starts at `$FA30` (right after the
PickPlayerFrame body) and runs through the dead `$FB00`/`$FB37` pins, which
were deleted; it stops before the live `$FBD0` EnterRoom twin. The `$F9B8`
tramp became `lda LineCount / beq / jmp PHMOverlay` (bank0 body), so the
per-miss switch is gone. Exits are `rts` (3 tail-jmps → rts, −3 B); the
`jmp HotOverlapFlag` still rides bank0's own `$FFEC` pad → bank3.

*Deviation from the plan (measured):* **`OvHead`/`OvTail` (6 B) stay in
bank2** — `MothDoWalk`'s patch test and `.LWpSetup` (LWC) read them in-bank
and cross-bank reads are impossible, so bank0 got its own copy. `M1OffTab`
did move (only PHMOverlay read it; bank3 keeps its twin). `LevelStartRoom`
lost its bank2 hand-copy with its last readers.

Pins/twins killed: bank2 `$F9B8` overlay tramp, `$FE00` PHMOverlay pin,
`$FE9C` shutter hole, `$FFEC` HotOverlapFlag pad (sync target list updated),
`M1OffTab`. Guards/tests touched: `verify_build.sync_bank3_labels` now
patches the HOF pad in kernel.asm only; `test_key_pickup` reads the cluster
from kernel.asm and asserts bank2's `LevelStartRoom` copy is gone;
`test_respawn_hover` anchors on the `$FBD0` pin.
