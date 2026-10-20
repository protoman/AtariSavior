# Compaction findings — 2026-10-19

Post-merged-title baseline (`fbfe84e`). Everything below is measured from
`src/bank*.lst` / `src/bank*.bin` / `tools/rom_size_report.py`, and HERO from
`src/hero/hero.bin` plus the earlier verified HERO notes in `docs/hero_*`.
Estimates are marked **est.**; do not promote them to facts.

Question asked: (1) find more wins of the title-merge class, (2) check whether
the features we blamed for our size (ferry/raft, hcrunch, …) are actually
cheaper in HERO.

---

## 0. Baseline

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3080 | 360 | 654 | 3440 | 656 |
| bank1 | 2513 | 502 | 719 | 3015 | 1081 |
| bank2 | 1444 | 361 | 2269 | 1805 | 2291 |
| bank3 | 1676 | 426 | 1386 | 2102 | 1994 |
| **total** | **8713** | **1649** | **5028** | **10362** | **6022** |

level data 548 B (index 48 + tables/blocks 334 + models 166).

Key constraint, not total ROM: **bank0 pre-pad has 1 byte**. Total free
(6022 B) is irrelevant to adding features because bank0 is pinned. Any bank0
addition still requires moving something out first. The title merge freed
bank1/bank2, not bank0.

---

## 1. Why the title merge paid 593 B (the generalizable test)

It deleted a **whole rendering mode**: a second kernel (270 B then), its
state machine (`TitleSequence` 267 B), its staging and its art. The merged
screen reuses the *game's own frame* (live stage PF + player + HUD) and only
overlays the logo/credits/music.

The test for another win of this class: **does this code exist only to render
a mode that could reuse the game frame?** Modes that survive: drop-in (needs
its own motion), tally (needs its own frame content), crunch (mutates the
live frame — not a mode), title (already merged). The only remaining
mode-like code is the **tally screen** and the **LV001 banner** (see §5).

---

## 2. Feature inventory (code+data, measured spans)

| cluster | bytes | notes |
|---|---|---|
| crunch (vcrunch + hcrunch + staging + overlays) | **1521** | VCS3 273, HOVFeatEntry 180, HcrPush 144, B3StageBand 132, VcrShutter 129, OvM1Block 116, PhRec 113, PhHcrEntry 110, PhaseBlink 77, HOVafterGate 68, OvShutBand 63, HcrClock 61, SBT_B 55 |
| enemies + object dispatch | 1056 | SelectActiveObject 289, MothDoWalk 216, DeriveEnemyY 98, UE_Tentacle 84, CEH 154, art/tables |
| HUD band | 923 | MenuMain 696 (bar cycle paths included), SetupScorePointers 123, DigitGfx 104 |
| title (current) | 899 | TitleKernel 342, FooterBand 101, music 197, fonts 132, state 103, art 24 |
| bomb + tally | 462 | BombMarkWalls 214, TallyEntry 99, BombEnemyBlast 86, TallyWork 63 |
| laser | 404 | LaserInput 173, LaserWallClamp 143, ClampDone 79 |
| raft / ferry | 318 | RaftBody 252, playfield probe tables 60, pad 6 |

Cross-bank tax (measured from the pad opcodes in every listing):

- 75 pad instances (`sta $1FFx` + `jmp`/`rts`), 37 distinct addresses,
  **450 B of pad bytes** (67 jmp pads + 8 rts pads).
- **34 addresses are shared by 2+ banks → 228 B are twins** (the same 6 bytes
  duplicated at the same address in the other bank; F6 requires that for the
  jmp operand fetch).
- 78 switch sites total; the rest are inline `sta $1FFx` (3 B each).
- Hot targets: sound leaves ($F9C0/$F9CF/$FA00/$FA13/$FAA4), AddScore,
  IsRoomDark/SetRoomDark, MenuMain, TitleKernel, RaftBody, the M1/overlay
  entries.

This is 4.3% of used ROM. Cheaper than it looks, given the 4-bank split.

---

## 3. HERO's structure, measured from the ROM

Facts:

- 8K, **F8** (`docs/bankswitch_sizes.txt`: `H.E.R.O. AZ-036-04 R 8 F8`).
- The image is linked with **bank A at $D000 and bank B at $F000** — the two
  4K halves are the same physical 4K window through the 6507 mirror, so a
  $Dxxx and the matching $Fxxx address are the same bus address.
- Evidence of the design consequence: the kernel block at `$D230-$D2BE` and
  `$F230-$F2BE` is the **same instruction sequence**, with branch/jump operands
  relocated between the two bases; bank B even jumps to a `$Dxxx` mirror
  target. Shared routines therefore live at the **same offset in both banks**.
- Bank switching is essentially absent: one `STA $FFF9` (`8D F9 FF`, offset
  0x1001) and three `BIT $FFF9` reads in the whole 8K. No trampoline table,
  no per-call switch: a `jsr $Dxxx`/`jsr $Fxxx` into the mirrored offset lands
  on the same routine whichever bank is selected, because the routine is
  duplicated there.
- HUD: the cave-band loop `$DC00` is **54 B** (per-scanline PF tables
  `$DC6A/$DC6C/$DC77` + digit tables ~100 B). Score is sprite/PF-table data,
  not runtime glyph math.
- No object rotation: HERO reuses one GRP1 across slots inside the frame
  (verified in `docs/hero_flicker.md`), so it has no `SelectActiveObject`-style
  rotation cost and no flicker.
- Data: HERO bakes per-screen pictures. **Caveat:** the repo's "~1.9 KB code /
  ~6.3 KB data" split (crunch plan §why-the-ROM-is-this-big) is a **lower
  bound on code / upper bound on data**: the bank-A dump left most of that
  bank as a `.byte` blob, including kernel code. Do not quote 6.3 KB as
  verified data.

Consequence for the argument "ours is bigger because of features": the
architectural delta is the opposite of what the suspicion assumes —

- HERO pays for zero trampolines with **duplicated shared code in both
  banks** (a whole extra copy of the kernel/helpers), and with **baked
  per-screen graphics data**.
- We pay 450 B of pads/twins and 1.65 KB of data, and keep one copy of each
  routine. In bytes per *unique* routine we are the cheaper design; in total
  content we are bigger because the game has more content (7 enemy types vs
  4, 18 live rooms vs baked screens, 4 levels, raft, two shutter machines,
  dark rooms, doors/M1, music, merged title).

So the honest answer on the ferry/crunch: they are not the reason a
trampoline-free HERO fits in 8K. HERO's 8K is full because it duplicates code
and bakes pictures.

---

## 4. Ferry and crunch vs HERO — what is verified, what is not

- **Raft/ferry (318 B)**: HERO has a horizontally patrolling sprite object
  (clamps `$0C..$93`, motion table `$F900`, docs/hero_async.md). Its identity
  was explicitly left **OPEN** by that investigation ("name it only after a
  runtime trace; do NOT guess"), and the doc's RAM map conflicts with
  docs/hero_flicker.md on `$9B` (25-byte room table vs hero X). Therefore:
  no verified HERO ferry implementation, no verified size. Do not claim
  either "HERO has it cheaper" or "HERO lacks it". Next step in §6.
- **Crunch (1521 B)**: no HERO analogue identified in the ROM notes. HERO's
  destructible walls are room-map edits; no shutter machine was found. This
  is our own mechanic and is our **single largest subsystem** — 15% of used
  ROM for a room feature, bigger than the whole title. It deserves the
  compaction effort on its own merits, independent of HERO.
- **Title/music**: HERO's boot screen is the game frame + Activision logo
  (visible in `src/hero/screenshots/s_Hero_1.png`), i.e. exactly the
  "logo over the live stage" design we just adopted. Our merge is closer to
  HERO than the deleted black title was. No separate title kernel exists in
  HERO's verified notes.

---

## 5. Same-class opportunities (ranked by bytes / risk)

1. **Crunch unification — 200–300 B (est.), medium risk.**
   The existing plan (`docs/crunch_unification_plan.md`, C1/C2/C3) is the
   right next chunk. The two machines share the clock, the kill latch and the
   staging; the current split is bank3 bodies + bank2 staging + bank3
   overlays. Do it before any reorg.
2. **TitleKernel band reuse — 100–150 B (est.), medium risk.**
   The cave kernel already renders band 0/2 from the same `PF*Buf`
   (`TitleKernel` re-writes them). If the cave kernel renders the stage and a
   small title band renders only the logo/footer, `TitleKernel` loses the
   band-0/2 setup, the player block and the entry cleanup. Conditions:
   (a) the cave kernel draws the active object (a miner/enemy would appear on
   the title — needs suppression or acceptance), (b) the title player becomes
   multi-colour (game palette) instead of `$0E`. Needs a visual OK.
3. **LV001 banner removal — ~78 B, needs user approval.**
   `SetupScorePointers`' banner branch (~55 B, incl. the /10 loop) + the
   kernel arming (~7 B) + L/V glyphs (16 B). The merged title's score now
   shows the level, so the banner is redundant. Product decision.
4. **Pad co-location — 60–90 B (est.), low risk.**
   34 shared twin slots. Moving a leaf to the bank that calls it removes the
   pad (and possibly a twin). Best candidates: the sound leaves called from
   both bank0 and bank1, and AddScore. Blocked by bank0's 1 B headroom for
   the bank0 side; bank1/bank2 pairs are free to move.
5. **Boot room-load + `.DATitle` bundle — ~36 B, low risk but sim-coupled.**
   Requires moving `sim_bomb_fuse`'s hook from the boot `jsr LoadLevel` to the
   RESET load. Do last (test-harness work, not ROM work).
6. **Duplicate tables — ≤44 B, case-by-case.**
   The audit's list (row math, band masks, M1 offset, clock tables). Several
   are cross-bank copies that cannot merge (bank locality); only same-bank
   pairs are free. Verify before budgeting.
7. **Tally screen — ~160 B, product decision.**
   `TallyEntry` 99 + `TallyWork` 63 + MenuMain tally branches. Its purpose is
   the level-exit bonus. Removing it is a gameplay change; ask first.

Strategic (not this session, listed so it is not lost):

- **Rotation → HERO-style multiplexing** would delete `SelectActiveObject`
  (289 B) and the `FlickerFrame` machinery and remove flicker, at the cost of
  a kernel rewrite (fixed-time GRP1 pipeline). Biggest quality+size win, but
  it is a kernel project with sim/Stella oracle work.
- **HUD band → PF-table HUD** (HERO's 54 B loop): would shrink `MenuMain`
  (696 B) but add data and change the 48-line band contract. High risk for a
  data-for-code trade we do not need (we are data-poor, not code-rich).

---

Duplicate-byte scan (12-byte windows across banks, fill excluded): 164 hits,
all explained — the mandated twins (`TitleJetSprite`, pads), one reused
12-byte `FetchPtr` idiom, and the shared `EnemyRamP` phase math. No mergeable
copy-pasted routine found. Dead-code scan: no confirmed dead label; every
candidate was a fall-through body or a table reached through pads/pointers.

## 6. Next probe (only open question left from the user's list)

To settle the HERO ferry question without guessing:

1. Run `../tools/probe_hero_overlay.py` extended to snapshot `$80-$FF` per
   frame for ~600 frames with `default_input` (starts the game at f40).
2. Find bytes that move ±1 with direction reversals inside a bounded range
   (platform X/Y) rather than counting down (timers) or toggling (animation).
3. Set a write-PC trap on each candidate; map the writer to the ROM offset.
4. If the writer sits in the `$F144`/`$F240` patrol block, its code span is
   the HERO platform's cost; compare with `RaftBody` 252 + 60 tables.

Until that trace is done, any HERO-vs-raft byte claim is a guess and is
excluded from the estimates above.

---

## 7. What I would do next, in order

1. C1/C2/C3 crunch unification (planned; biggest measured subsystem).
2. Ask the user about the LV001 banner (78 B) and the tally (160 B).
3. TitleKernel band reuse if the visual conditions are acceptable.
4. Pad co-location pass (measure per target, move same-bank leaves first).
5. Boot bundle + sim hook last (it is test-harness work).

---

## 8. HERO raft code — FOUND (screenshots raft_002..raft_004, trapWrite $9B)

HERO's raft is **not an entity**. It is a collision test + a forced walk, in bank 1:

```
$F0E0-$F11C  shared gates: sprite ptr $D8==$97, death timer $AD==0,
             room $9C>=11, BIT $07 = CXPPMM (player<P>P1 collision)
$F11E-$F125  LDA $EC / AND #$7F / CLC / ADC #$18 / STA $BB   ; raft X
$F127-$F12E  LDA $9B / SEC / SBC $BB / CMP #$09 / BCS      ; <9 px?
$F130-$F13E  $E6=$40, $AC=$40, $B0 = (bit7 of $EC) ? 0 : 8 ; ride direction
$F140-$F149  $BD=$FF, $9B = $BB + $04                       ; pin to raft
```

- The raft is drawn as **P1 (GRP1), sprite pointer $97**. Ride detection is the
  hardware **CXPPMM** collision plus a <9 px X test — no playfield probe.
- Its X comes from one byte: `raftX = ($EC & $7F) + $18`; `$EC` is written only
  by the room init at `$F663-$F66D` (`$80`/`$60`: bit7 = direction).
- The motion reuses the **ordinary walk step** at `$F240-$F256`: with
  `$B0 = 0/8`, `$9B += 1` (or −1) per frame. Confirmed live: standing still on
  the raft, `$9B` went `2D -> 41` over 20 frames (exactly 1 px/frame), `$9F`
  unchanged, `$A8` in lockstep (`$A8` is the object that chases `$9B` at
  `$F513-$F52B`, not the raft).
- Size: raft-specific ≈ **44 B** (`$F11E-$F149`) + ~11 B room init; the rest of
  the block is shared sprite/death/input logic. Total ≈ **55-70 B**.
- Ours: `RaftBody` 252 + probe tables 60 + pad 6 = **318 B**.

So the suspicion is confirmed: HERO's ferry is a fixed platform + auto-walk,
about 5× smaller than ours. The difference is **behaviour**, not technique:
ours is an entity with ferry gating, inertia, playfield turn-around and tide
alignment. Copying HERO's model would mean deleting those behaviours, not
refactoring the body.

## 9. HERO hcrunch — FOUND (hcrunch.png + hcrunch_002.png)

The red band is a **PF byte override**, not a machine. Bank 1:

```
$F2F1-$F2F4  LDA $FC00,Y / STA $C3        ; band PF byte from the room table
$F355-$F372  LDA $C3 / CMP #$7F / BNE
             LDA $C0 / CMP #$FF / BNE
             LDA $F5 / CMP #$0D / BCC
             LDA $FD / LSR A / LSR A / LSR A
             AND #$07 / TAX
             LDA $FFB8,X / STA $C3        ; 0F 1F 3F 7F FF 7F 3F 1F
```

- The gap is the `$FFB8` triangle applied to the staged PF byte `$C3`; phase =
  `($FD >> 3) & 7`. The clean band data (`$C3=$7F`, `$C0=$FF`) is the room
  table; the override only runs for that band (`$F5 >= $0D`).
- The red pixels are the hazard (HERO's generic PF-touch death); the moving gap
  is the safe passage. There is no close-kill test, no push, no solidity, no
  latch, no per-frame hit box.
- Cost: ~24 B code + 8 B table = **~32 B**.
- Ours: 1521 B (`VCS3`/`HOVFeatEntry`/`HcrPush`/`VcrShutter`/staging/overlays).

Measured verdict on the whole suspicion: HERO's raft ≈ **55-70 B** vs our 318 B;
HERO's hcrunch ≈ **32 B** vs our 1521 B. The gap is behaviour (moving entity,
kill timing, push, tide) and a mask-vs-subsystem design, not sloppy code.

## 10. Chunk 1 — vcrunch (tile 11) removed

User decision 2026-10-19: the vertical-crunch feature is deleted. No stage
room used it (`V` never appears in `src/rooms` or `src/tests/rooms`), so no
data migration. Removed: the bank0 slice hook + RowSlice/SBmask/SBod, bank3
VcrShutter/PFOffTab/VcrStateTab/VCS3 + the `$81` PhaseBlink/HOV arms, bank2
OvShutScan + the `$FD80` tramp, the Vcr* ZP EQUs, converter/editor/gate
support. `tools/test_vcr_shutter.py` now proves the converter + CLI reject
tile 11; `test_phase_kill_frame.py` proves a stale `$81` record is inert.

Size ledger after chunk 1:

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3027 | 350 | 717 | 3377 | 719 |
| bank1 | 2513 | 502 | 719 | 3015 | 1081 |
| bank2 | 1399 | 361 | 2314 | 1760 | 2336 |
| bank3 | 1211 | 371 | 1718 | 1582 | 2514 |
| **total** | **8150** | **1584** | **5468** | **9734** | **6650** |

level data 548 B (index 48 + tables/blocks 334 + models 166).

Delta vs the section-0 table: bank0 −$3F used, bank2 −$2D, bank3 −$208
(free +$208). Kernel main-region code shrank 27 B (Overscan $F19F→$F184),
but the fixed `$F8C0` pin absorbs it (fill grew 0x75→0x90), so the first
growable pin (`$FC49`) still has 11 B free — usable headroom gained: 0 B.

## 11. Chunk 2 — hcrunch simplified (fixed band 1, always hot, no push/latch)

User decision 2026-10-19. New contract: the crunch band is ALWAYS band 1,
ALWAYS hot (touch kills at any phase/extent), and ALWAYS the fixed 10-cell
prefix (half playfield width). Removed: the cold "closing only" kill rule,
HcrPush + HcrBandLo + its call, the one-kill-per-visit latch (EnemyDeadMask
b7 is no longer written by the crunch path), and all per-record x/band/w/h
reads (the `$82` class byte + 5-byte stride stay so the walker is
untouched). Kept: the 16f/step clock animation (`HcrClock`, now always
full=10) and the touch kill through the shared HOV path. `PhHcrEntry` now
stores `P(n)` straight into PF band1; the HOV `$82` handler tests band 1 +
`2n` covered 4px cols (no record reads). `tools/test_hcrunch.py` rewritten
(13 cases, including patched record y/w proving they are ignored).

Size ledger after chunk 2:

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3027 | 350 | 717 | 3377 | 719 |
| bank1 | 2513 | 502 | 719 | 3015 | 1081 |
| bank2 | 1399 | 361 | 2314 | 1760 | 2336 |
| bank3 | 933 | 368 | 1761 | 1301 | 2795 |
| **total** | **7872** | **1581** | **5511** | **9453** | **6931** |

level data 548 B (index 48 + tables/blocks 334 + models 166).

Delta vs chunk 1: bank3 −278 code (−$116 used, free +$116). bank0/bank2
unchanged (only the auto-synced CallPad literals moved: BuildColupF
$F50B→$F507, HotOverlapBody $F5C7→$F5C3).

Note (2026-10-19, after the banner revert): `tools/rom_size_report.py` was fixed
to stop counting `NAME = value` rows inside positive-length `.ds` fills as code
(the fills are now reported as fill). That moves the reported total by 1 B
(9453 -> 9452); it is an accounting fix, not a ROM change. The banner removal
commit `348c342` was reverted per user decision — the LV001 banner stays.

## Chunk: title reuses the cave kernel (band 0) — 2026-10-20

`TitleKernel` in bank1 duplicated the whole frame (its own band-0 stage +
player + band-1 logo/footer + band-2 + HUD). Band 0 is now the REAL cave
kernel, so the two can never drift:

- `KernelInit` no longer dispatches on `DropTarget` (the `$FF` title path,
  its `pla/pla` unwinding and the ENAM0 clear are gone): every frame runs
  `CaveKernelRow`, which draws the live stage PF/COLUPF from the room buffers
  and the player through `PlayerColTable`/`Grp0Ptr`/`PickPlayerFrame`.
- The row-advance tail diverts **only** on `$FF`:
  `lda DropTarget / cmp #$FF / bne .Row / jmp CallPad_TitleBand`. Cost: +5c on
  the row1/row2 setup lines of gameplay frames; the wall model did NOT move
  (sim: cave 267.0 constant, title frame 265, WSYNC counts 195/193), measured
  before retargeting anything.
- `CallPad_TitleKernel` ($FC55) is retargeted, not added: the same 6-byte pad
  is now `CallPad_TitleBand` (byte-identical in bank0/bank1, `jmp $F080`).
- `TitleBand` (bank1, still pinned at `$F080`) starts at band 1: band-1 PF +
  COLUPF + ENABL from `PF*Buf+1`/`ColupfBuf+1`/`BandTab+1` (same store order as
  the cave `.Row`), the 48px logo (`TitleFont`, NUSIZ 6 + VDEL, unchanged),
  the credit footer (`FooterBand`), the band-1 tail, then band 2
  (`PF*Buf+2`), its 48 lines, and `jmp MenuMain`.
- Object/beam suppression needs NO new code: `LoadLevel` tail-jumps `DropArm`,
  whose `.DATitle` (taken because `DropTarget=$FF`) clears
  `EnemyCount`/`LevelMinerRoom`, so `SelectActiveObject` parks GRP1; the same
  `.DATitle` now also clears the laser held/gate bits (`and #LASER_KEEP` —
  band 0 is the cave `.Line`, which would otherwise re-enable ENAM0 from
  `BeamMask & LaserState`), keeping `b0` + the rooms 4-7 dark mask.
- The cave band 0 leaves the missiles latched (`.AfterRows` is skipped on the
  title), and the 48px footer sets NUSIZ=3: `TitleBand` clears `ENAM0/ENAM1`
  on entry, otherwise two 1-clock vertical lines ran through bands 1/2.
- Bank1's `PlayerWalkA/B` art (24 B) and the manual player draw are deleted;
  the inlined `#<FooterFont+N` / `#<TitleFont+N` literals are parenthesized
  (`#<(FooterFont+N)`) — DASM bound `<` to the label only, so moving the font
  across a page boundary turned them into out-of-range values.

Guards: `src/tools/test_title_demo.py` rewritten for the new architecture
(cave band 0 + TitleBand bands 1/2, pad retarget, no bank1 player art,
`.DATitle` suppression); `src/sim_frame_budget.py` classifies title frames at
the new pad (`CallPad_TitleBand`, PH_KER) instead of the retired label.

Size ledger after the chunk:

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3023 | 350 | 720 | 3373 | 723 |
| bank1 | 2409 | 478 | 847 | 2887 | 1209 |
| bank2 | 1399 | 361 | 2314 | 1760 | 2336 |
| bank3 | 933 | 368 | 1761 | 1301 | 2795 |
| **total** | **7764** | **1557** | **5642** | **9321** | **7063** |

level data: index 48 + tables/blocks 334 + models 166 = **548 B**.

Delta vs the tally-revert baseline (9452 used / 6932 free): **−131 B used**
(bank0 −4, bank1 −128: code −104, data −24). Bank0's pre-pad pin still ends at
`$FC67` (the `.ds` pins absorb the shrink); bank1's freed space is fill until
the next feature.

---

# Post-repack optimization cuts — 2026-10-20 (audit rows 4, 5, 1)

The five `repack` commits (`91f1996..9a7f3f4`) moved the level-data/code
addresses the audit's ranked plan had marked "dep"; the remaining measured
rows are taken here, one commit each. Baseline = HEAD **9a7f3f4, 9173 used /
7211 free** (bank0 3642, bank1 3049, bank2 1222, bank3 1260; level data
510 B). Each chunk re-measured before starting, as the audit's numbers predate
the repack.

| after | bank0 | bank1 | bank2 | bank3 | total | level data |
|---|---|---|---|---|---|---|
| baseline 9a7f3f4 | 3642 | 3049 | 1222 | 1260 | **9173** | 510 |
| 1. packed title theme | 3642 | 2993 | 1222 | 1260 | **9117** | 510 |
| 2. level-data C2+C3+C4 | 3620 | 3000 | 1175 | 1285 | **9080** | 434 |
| 3. tail pads split | 3605 | 2985 | 1175 | 1285 | **9050** | 434 |
| 4. corridor pads split | 3572 | 2948 | 1169 | 1285 | **8974** | 434 |

## 1. Title theme packed 1 byte/step (−56 B, audit row 4)

`MusicMel` was 51 `(duration, note)` pairs = 102 B, walked one pair per note by
`bank1.MusicTick` (duration at `X`, note at `X+1`, `MelPtr += 2`). Measured data
shape: **3 real durations** ($1E=30, $3C=60, $78=120) + the loop step's 0, and
**14 pitches** ($07..$1F) + rest $FE + loop $FF. So one byte per step is exact:

```
byte = note_code * 4 + duration_code
note_code     = AUDF; $3E = rest; $3F = loop   (all pitches fit 6 bits)
duration_code -> MelDur = $1E,$3C,$78,$00
```

`MusicTick` decodes with `lsr/lsr` (note) and `and #3 / tay / lda MelDur,Y`
(duration). New cost **55 B of data** (51 packed + the 4-byte `MelDur`) and
**−9 B of code** (two `cmp`-chains collapse into the shared `MelApply`
subroutine; `MelPtr` advances by 1). bank1 data 478 → 431, code 2571 → 2562.

- `art/intro_theme.asm` is now GENERATED by **`tools/gen_intro_theme.py`**,
  which keeps the readable `(duration, note)` pairs and has a `--check` mode
  that re-expands the emitted file and asserts it reproduces them. Never edit
  the asm by hand.
- Melody equality proof: the title frame timeline (`AUDC0`, `AUDF0`, `AUDV0`,
  `AUDV1` at `StartFrame`, 2460 frames) is **byte-identical** before/after.
  This matters because the paired player re-asserted the *next* pair's note
  (`MusicMel+1,X` with `X` already advanced), so `$FF` next = "hold the tone",
  `$FE` next = "mute now". `MelApply` keeps both arms ($3F hold, $3E mute) —
  do not "fix" the one-step-ahead re-assert, it is the shipped melody.
- `MelApply` is a `jsr` from both paths (+1 stack level on the title/VBL path);
  `sim_bomb_fuse` min-SP gate unchanged (still ≥ $F8 gameplay / $F7 run).
- The freed bytes land at bank1 `$F3E3-$F41E`, kept as explicit fill
  (`.ds $F41F - *`) so `M1StripBlast` stays at `$F41F` and bank1's
  `TallyEntry` at `$F44F` — both addresses are hand-copied into `kernel.asm`'s
  `TallyEntry` EQU and pinned by `tools/test_bomb_strip.py`; new bank1 leaves
  can use that hole.
- Guards updated: `tools/test_intro_music.py` now also asserts the ROM's
  `MusicMel`/`MelDur` bytes equal `gen_intro_theme.pack(THEME)`/`MELDUR`
  (it used to be a pitch-count smoke test only); `src/tools/test_title_demo.py`
  follows the theme into the include instead of matching `MusicMel:` inline.

## 2. Level-data C2 + C3 + C4 (−76 B data, net −37 B; audit row 5)

Re-measured on the post-repack tree: 16 rooms (L1 2, L2 2, L3 6, L4 6) and 4
levels, so the audit's 32/32/12 split holds. **The audit did not count the
reader code**; that is where most of the win goes. `docs/handoff_2026-10-19_next.md`
§S2 records an earlier attempt at C2 alone as "TRIED + REVERTED: +36 B decode →
net +12 B worse" — that version kept a running prefix sum. This one removes the
sum entirely by packing the record index instead.

New per-level block (`n` = the level's room count, all offsets from ONE base):

```
base + 0    RoomDataTable    2 B/room  (RoomRects ptr only — C3)
base + 2n   RoomConnections  2 B/room
base + 4n   RoomEnemies      2 B/room  ((count<<5 | first record), band)
base + 6n   EnemyDataTable   4 B/record
```

- **C3**: `TilePF0` always sits `rects + 2 + 2*nrect` inside the same block
  (count byte + the always-zero hot-count byte), so the second word was
  redundant. The derivation happens in `bank3.B3RoomBlocks`, which already
  reads the count, using the RAW count (the ZP rect cache clamps to 5).
- **C2**: the per-room record was `(ptr_lo, ptr_hi, count, band)`. The records
  are contiguous in room order, so `ptr` is `EnemyDataTable + 4*record_index`;
  `record_index` fits 5 bits (≤ 31 records) and `count` 3 bits. `EnterRoomB2`
  reads the base from the level entry (base+4n), then derives the enemy record
  pointer (base+6n + 4*index). **No prefix-sum loop at room load**: the packed
  field is the sum, computed once by the converter.
- **C4**: the level entry is `6 scalars + base word + room count` = **9 B**
  (was 12: three word pointers). `kernel.LoadLevel` computes `Level*9` and reads
  one word + the count; `bank1.GetConnIdx` derives `+2n`, `EnterRoomB2` derives
  `+4n`/`+6n`.
- ZP: `$A1` is now `LevelRoomN`; `$A2`, `$AF`, `$B0` are documented FREE (the
  bytes stay allocated so the hand-copied blocks do not shift —
  `docs/zp_layout_skill.md` updated, `check_equ_sync` still green).

Measured: data −76 (level data 510 → 434; bank2 data 311 → 235), code +39
(bank2 +29 = the two derived pointers, bank3 +25 = the TilePF0 derivation,
bank1 +7 = GetConnIdx), bank0 **−22** (`LoadLevel` lost 4 fold reads and the
`*12` ladder). Net ROM **−37 B**, and bank0 — the bank with a 1-byte pre-pad
ceiling — gains 22 B of headroom.

Gates: `tools/test_band_restage.py` drives the REAL `EnterRoom` for every live
room and now asserts (a) `RoomBandColor`, (b) `EnemyCount`, (c) the **enemy
record base** equals `EnemyDataTable + 4*prefix`, and (d) the **PF cache** (9 B)
equals the block's PF triple at the derived `rects + 2 + 2*nrect` — so the two
new derivations are checked against ROM bytes, not against a restatement of the
formula. `tools/test_level_bank.py` pins the stride (9), the emission ORDER
(RoomData → Conn → RoomEnemies → EnemyData, which IS the reader contract) and
the packed index contiguity; `tools/test_water_band.py` / `test_water_respawn.py`
stage base+count instead of the old pointers; `test_water_respawn`'s band poke
follows the 2-byte record. `tools/freeze_test_banks.sh` now also refreshes
`src/tests/generated/` from the staged conversion — a converter format change
had left those snapshots stale (test_editor_roundtrip caught it).

## 3. Tail-pad reclaim — split the 3 live pads, delete CallPad_Overscan (−15 B/bank)

`docs/optimization_cuts_2026-10-20.md` §2 designed this and skipped it. The
guard rewrite turned out to be smaller than feared, because the fears were
misplaced: `check_callpads`' byte-identity comparison covers only the corridor
`$FBF8-$FC48` (`PAD_HI = $FC49`), so the tail pads were never in it. What the
tail pads DID have was their target check, via the `CallPad_x: sta / jmp $lit`
parse of **kernel.asm** — and that is exactly what the packing removes, so the
guard would have silently stopped covering them.

F6 contract used: a bank0 caller runs `sta $1FF7` at A; the opcode fetch at
A+3 already comes from bank1. So each pad needs one live half per bank:

| pad | bank0 (A) | bank1 (A+3) |
|---|---|---|
| `CallPad_TitleSelect` | `$FC4F` `sta $1FF7` | `$FC52` `jmp TitleSelect` |
| `CallPad_TitleBand` | `$FC52` `sta $1FF7` | `$FC55` `jmp $F080` |
| `CallPad_MusicTick` | `$FC55` `sta $1FF7` | `$FC58` `jmp MusicTick` |

`CallPad_Overscan` (12 B) had **no caller in any bank** and is deleted, along
with its patch loop in `verify_build.sync_overscan` (the `$FC70` ToGameStub twin
still tracks bank0's `Overscan`).

Measured: bank0 pre-pad headroom **1 → 16 B** (flow now ends `$FC58`), bank0
used 3620 → 3605; bank1 2985 (its `sta` halves and the Overscan pad were dead
there too, −15). Total 9080 → **9050**.

Replacement guard (`verify_build.check_callpads`), byte-level, not textual:
for each of the three pads it pins the address, asserts
`bank0[A..A+2] == 8D F7 1F`, and asserts `bank1[A+3..A+5] == 4C <label lo hi>`
with the label resolved from **bank1.lst** — i.e. the same operand-equals-label
contract as before, but read from the ROM where the fetch actually happens. It
also fails if a tail pad regains a kernel `jmp`, if `CallPad_Overscan` comes
back, or if any `CallPad_*` is neither a corridor pad nor a declared tail pad
(so a new pad cannot escape the guard). Runtime proof: `test_intro_music`
(MusicTick pad), `test_menu_flow` (SELECT/TitleSelect pad) and
`sim_frame_budget`'s title-frame classification (TitleBand pad) all drive the
real paths.

## 4. Corridor pads split — every pad is one live half per bank (−76 B)

Audit row (section B) proposed an **RTS-dispatch gateway** for the 11 corridor
CallPads ("132 → ~61 B, ~53 net, +~8c/call"). Re-measured before building it:
the gateway cannot beat the chips it costs, and one cheaper scheme gets more.

**Why the gateway loses.** Its 11 pads collapse into 1 pad/bank + dispatch +
an 11-word table, but the routine id has to come from somewhere:
- id in A/X at the call site = +2 B × 27 `jsr` sites (**+54 B**, and A holds a
  live argument at several sites: `AddScore` takes the amount in A);
- inline id byte = +1 B × 27 (**+27 B**) plus a return-address rewrite;
- RTS dispatch then costs `asl/tay/lda/pha/lda/pha/rts` ≈ **+21c per call**
  over today's `jsr + sta + jmp` (13c), and the overscan margin at the
  fly+laser baseline is only ~20-220c. That is the measured net *below* the
  task's 25 B floor, with a timing risk on top.

**What was done instead: extend the proven tail-pad split to the corridor.**
Same F6 contract as commit 1abf83e, no new machinery: a bank0 caller executes
`sta $1FFx` at A, so the opcode fetch at A+3 already comes from the TARGET
bank. Nothing outside bank0 calls a pad (re-measured: 0 hits in all three
other banks; they only `jmp ReturnPad`), so bank0 needs the `sta` half alone
and the target bank the `jmp` half alone. Packing the live halves:

| | before | after |
|---|---|---|
| bank0 corridor | 11 × (`sta`+`jmp`) = 66 + ReturnPad 4 | 11 × `sta` at `$FBFC..$FC1C` = 33 + ReturnPad 4 |
| bank1 corridor | 11 × (`sta`+`jmp`) = 66 + 4 | 10 × `jmp` at `$FBFF..$FC1F` = 30 + `sta $1FF6` 3 |
| bank2 | dead `CallPad_BuildColupF` image (6) + 4 | 4 |
| bank3 | `jmp BuildColupF` at `$FC35` + 4 | same image at `$FC1A` + 4 |

Address map (bank0 A → target A+3): `$FBFC/$FBFF/$FC02/$FC05/$FC08/$FC0B/
$FC0E/$FC11/$FC14` → bank1's `UpdateBombSound`, `UpdateJetSound`,
`BombSndDrop`, `BombSndExplode`, `GetConnIdx`, `AddScore`, `IsRoomDark`,
`SetRoomDark`, `UpdateLaserSound`; `$FC17` `sta $1FF9` → **bank3's**
`jmp BuildColupF` at `$FC1A`; `$FC1A` → bank1's `jmp BombMarkWalls` at
`$FC1D`. Bank3's image moved because its address is the pad's A+3, not a pin.

**bank2's `CallPad_BuildColupF` was deleted, not moved.** It had no caller in
bank2 either; after the split its `+3` would land on bank3 fill, i.e. a trap
that looks live. Its `jmp $F507` was also the last `BuildColupF` literal in
the tree, so `sync_bank3_labels` no longer patches a `CallPad_BuildColupF`
(bank3's own image is `jmp BuildColupF`, a self-healing label).

**Guards (stronger than the byte-identity they replace).** The old
`check_callpads` compared the whole `$FBF8-$FC48` block bank0 == bank1 — with
the split that comparison is exactly what stops being true, and it never
proved the jump operands. New contract, per pad, from ROM bytes:
- `bank0[A] == 8D F6/F7/F8/F9 1F` (the sta half, target bank from the table) and
  `bank0[A+3]` is **not** `4C` (a regained bank0 `jmp` is a dead byte);
- `target_bank[A+3] == 4C <label lo hi>` with `<label>` resolved from that
  bank's own `.lst` (the fetch is bank-side, so a stale literal dies here);
- `ReturnPad == $FBF8` in every bank with `8D F6 1F`, and bank0 adds the `60`
  (rts) — the other banks' `rts` bytes are correctly dead;
- corridor pads must stay below the `$FC49` MothExitPad pin;
- **no `jsr`/`jmp CallPad_*` in bank1/bank2/bank3** (that is the invariant the
  split rests on — a non-bank0 caller would have no `sta` half to come back);
- every `CallPad_*` in kernel.asm must be declared in `SPLIT_PADS` or
  `TWIN_PADS` (the pinned `RaftBody`/`MothYDerive` tramps keep both halves and
  their own identity guards), and `CallPad_Overscan` must stay gone.

Nothing timing-critical moved: `sta` costs the same, the pad block is still
0 push / 0 cycles, and no kernel/VBL/Overscan instruction changed. Runtime
proof: `sim_frame_budget` (VBL's `CallPad_BuildColupF` → bank3 every frame) and
`sim_bomb_fuse` (overscan sound pads + `AddScore` + `BombMarkWalls`) plus the
full battery, all green.

Measured: bank0 3605 → **3572**, bank1 2985 → **2948**, bank2 1175 → **1169**,
bank3 1285 (image relocated into fill), total 9050 → **8974 = −76 B**.
bank0's pre-pad headroom stays 16 B (the flow still ends at the `$FC58` tail
pad); the reclaimed bank0 space is fill between `$FC1D` and the `$FC48`
MothExitPad pin — 44 B, usable by an `org`'d leaf helper, not by sequential
flow. That is the same trade the tail-pad split made.

---

# Audit round 2 implementation — 2026-10-20 (HEAD bc63451)

`docs/audit_round2_2026-10-20.md` top three, one commit each. Baseline measured
at `bc63451`: bank0 3572 / bank1 2948 / bank2 1169 / bank3 1285 = **8974 used**,
7410 free, level data **434 B**.

## 1. `tools/test_water_respawn.py` fixed (0 ROM)

The test could not fail: the band poke landed at **f3**, after
`LoadLevel → EnterRoom` (frames 0-1) had already staged `RoomBandColor` from
`RoomEnemies[room]+1`, so the byte stayed `$00`, `CheckBandTouch` never fired
and the player rested at `RoomY=131` in a room with no water. The gate
(`loop_deaths = len(deaths)-1`) was 0 for both "no loop" and "no death".

Fixed per the audit's §E:

- **Hook `EnterRoom` ($FBD0, bank0), not a `StartFrame`.** That is the only
  point where the level block base (`$9F/$A0`), the room count (`$A1`) and the
  target room (in **A** — every caller passes the room index: exits pass the
  connection nibble, `LoadLevel` passes `LevelStartRoom`) are final and bank2
  has not read the band byte yet. It fires twice (boot load + the RESET pulse)
  and again on every respawn — 2 pokes in the run, no extra state.
- **Exact address: `base + 4n + 2*room + 1`.** The old
  `base + 4*LevelRoomN + 1` is only right for room 0.
- **Drop-in gate for the `RoomY=131` staging**: forced only once the poke is in
  and `DropTarget == 0`. Forcing it mid drop-in (`DropTarget=$18`) was the
  second half of the old defect.
- **Positive gate, three ways**: `pokes > 0`, `RoomBandColor == $1C`, and
  `len(deaths) >= 1` with `min_lives <= 2`. Any of them missing = FAIL.

Measured on HEAD: `band byte @ $F741 forced at f0` (+f2 from the RESET pulse),
`RoomY->131 at f76`, `f77: DEATH (lives=2, RoomY=0)`, then the player falls to
`Y=119` (the room floor, 6 px above the 125 water line) and stays — 1 death,
0 loop deaths, `PASS`.

Proof the fixed test can fail: with the hook reverted to the old StartFrame
poke (temporary mutation, not committed) the same file reports
`band pokes=1, RoomBandColor=$00, total deaths=0` and exits **1**
(`FAIL: RoomBandColor=$00, expected $1C (the band poke landed after the room
load)`).

Room 0 only: L2's start room is the one the scenario enters; the layout for
every other room stays pinned by `test_band_restage` / `test_level_bank`.

ROM: 0 B. Battery + freeze green.

## 2. Dead pins removed — 7 directives, 0 ROM bytes (audit 2, item 2)

Each pin was verified before deletion: the source line is a bare
`.ds $ADDR - *, 0`, no label/byte sits at the address, no `$ADDR` literal
appears in any bank's code (only in comments), and no guard asserts the
absolute (except `test_bomb_strip:126`, rewritten below).

| pin | bank | what it was | verdict |
|---|---|---|---|
| `$F3C4` | 2 | PickPlayerFrame body entry (chunk 1) | **deleted** — nothing followed it until the `$F450` pad |
| `$F4C4` | 2 | TitleSequenceFold jmp operand | **deleted** — TitleSequence retired 2026-10-19 |
| `$F5CF` | 2 | "TitleSequence retired" | **deleted** — ColOff is a label read, it floats |
| `$F970` | 2 | M1StripBlast body entry (chunk 2) | **KEPT** — the address is the `spill_F901` data-slot END (`convert_level._SPILL_SLOTS` + `verify_build.bank2_data_slots` read the `.ds` line); deleting it silently widens the slot and desyncs the converter's capacity table |
| `$F9B8` | 2 | overlay tramp twin (chunk 4) | **deleted** — the twin lives in bank0 |
| `$FDE1` | 2 | PickPlayerFrame tramp mirror | **deleted** — body moved to bank0 (chunk 1) |
| `$F9AC` | 1 | shared 12 B M1 hop pad | **deleted** — chain is same-bank since chunk 2 |
| `$F937` | 1 | bank2 M1StripBlast back-jmp operand | **deleted** — `StripBlastCheck` is reached by label |
| `$F9B8` | 0 | overlay tramp address sharing | **SKIPPED** — `OverlayTramp` is LIVE at that address; removing the pin shifts `EnemyOffTable`+`OverlayTramp`+`PositionBallM1`+`KernelInit`+`DropSpeedTable`+`PickPlayerFrame` and every later label by 3 B for **0 B gained**, across cycle/page contracts. The audit's entry is about the *sharing* being unnecessary, which is already true; the pin also anchors live code. |

Two things MOVED as a result (both label-reached, both re-verified by the
battery):

- bank2 `ColOff`/`ColMask`: `$F5CF` → `$F45E` (right after the ERBlocks return
  tail). The `$F600` pin still holds `LWpSetup`/`LWpSolid`/`LWpNotPatch`.
- bank1 `StripBlastCheck`: `$F937` → `$F8C6` (right after the raft tramp twin),
  ends before the `$F9AC`-anchored sound leaves.

**Window bytes opened: 0 net.** A `.ds` pin emits no byte, so the window
measurement already counted its address as free — deleting pins cannot create
free space, it removes a *growth cap*. Measured with the listing-row method
(after = this commit, before = the audit's §B table):

| bank | window | before | after |
|---|---|---|---|
| 2 | after the ERBlocks tail | `$F45E-$F5CE` 369 + `$F5F8-$F5FF` 8 | `$F486-$F5FF` **378** (+9, merged; ColOff moved in) |
| 2 | `$F307-$F44F` | 329 | 329 (cap lifted 186 B) |
| 2 | `$F7A8-$FBCF` | 1064 | 1064 (cap lifted 72 B at `$F9B8`) |
| 2 | `$FDDE-$FE95` | 184 | 184 (cap lifted 3 B at `$FDE1`) |
| 1 | strip/sound gap | `$F8C6-$F936` 113 + `$F995-$F9BF` 43 | `$F924-$F9BF` **156** (one run; body moved in, cap lifted 113 B) |
| 1 | `$F9AC-$F9BF` | 20 (merged above) | — |

ROM totals unchanged (8974 used / 7410 free, level data 434 B) — verified.
`test_bomb_strip` now pins the invariants instead of one absolute:
`M1StripBlast == $F41F`, chain order, `$F8C6 <= StripBlastCheck < $F9AC`, and
**no `$F937`/`$F9AC` literal in any bank's CODE** (comments may mention them).

## 3. Level-data micro-pack — 2 of the 4 sub-items, 24 B data (audit 2, item 3)

Converter-side only; `src/rooms` untouched; the `TilePF0+9/+10` meta contract
is unchanged (none of the emitted blocks changed shape). Baseline 434 B.

**Done (d): index constants — 8 B.** `start_room` (0 in all 4 levels) and
`miner_y` (84 px = 7 rows in all 4) left the per-level entry, exactly like
`start_x/y` did on 2026-10-19. Entry 9 → **7 B**:
`miner_room, miner_x, wall, wall2, base word, room count`. `LoadLevel` computes
`Level*7` (`asl×3 / sec / sbc`, −2 B), writes `LevelStartRoom = 0` and
`MinerY = 84` as constants (−2 B), and drops two `jsr FoldIndirect` reads.
The converter now **hard-fails** on any other value instead of silently
dropping it.

**Done (a): sparse band — 16 B (audit projected 14).** The per-room
`bottom_color` byte is gone. `RoomEnemies` is **1 B/room**:

```
bit 7-6  enemy count (0..3)
bit 5-1  first enemy-record index (0..31)
bit 0    bottom-band FLAG
```

The COLOR is one game-wide `BAND_COLOR`, emitted as `generated/levels_equ.asm`
(`BAND_COLOR = $80`, 0 ROM bytes) and included by **bank2.asm before
`EnterRoomB2`** (which does `lda #BAND_COLOR` when the flag is set).
`convert_level` **hard-fails** when two bottom-band rooms resolve to different
colors ("extend the format first"). That is the trade the audit's own
"(room, color) pair for L2R1" also makes (one band setup per level); this
costs 0 bytes instead of 2.

Consequence: the block's enemy-record base moved `+6n` → **+5n** (1 B/room
instead of 2). Updated in `EnterRoomB2` (one `adc` dropped), the kernel/bank1
comments, `docs/zp_layout_skill.md`, `test_band_restage` (it asserts the record
base per room), `test_level_bank` (stride/format), `test_water_band` (stride),
and `test_water_respawn` (the band poke is the FLAG bit at
`base + 4n + room`, and the expected staged color is the emitted `BAND_COLOR`
— `$80` live, not the old `$1C` debug value).

Measured ROM −24 B, and it is all level data (bank0 code −4, bank2 code +4):

| after | bank0 | bank1 | bank2 | bank3 | total | level data |
|---|---|---|---|---|---|---|
| baseline bc63451 | 3572 | 2948 | 1169 | 1285 | **8974** | 434 |
| item 2 (pins) | 3572 | 2948 | 1169 | 1285 | **8974** | 434 |
| item 3 (micro-pack) | 3568 | 2948 | 1149 | 1285 | **8950** | **410** |

### Skipped, with the re-measurement

- **(b) hot-flag bit (`nrect` b7) — 11 B data, ~6 B code, net ~5 B.**
  The count byte only disappears for the 11 hot-less blocks if the hot area
  moves to a derivable offset; making `TilePF0` = `rects+1+2*nrect` costs
  `and #$7F` in the `B3RoomBlocks` cache clamp (+2) and a `bpl` gate in BOTH
  hot-prefix walkers (`PhaseBlink`, `BuildColupF`; +2 each). Under the line.
- **(c) 3-byte enemy records — 9 B data, ~4 B code, net ~5 B.** The only
  reader of the ROM `dir` byte is `EBLER`; packing dir into byte0's b7 costs
  the reload/`eor #$80` dance (+4 B). Also the audit's bit budget is wrong:
  `y` reaches 132 px (row 11 × 12), so it needs **8** bits, not 7 — 3 B works
  only with 3+1+8+8 = 20 of 24 bits. Skipped: ~5 B net plus a 10-file test
  restage (every py65 test that fabricates a 4-byte record).
- **(b') share one hot prefix** (L4R2 is the only block with hot records):
  0 B, it is already one block.

---

## C1 — `SelectActiveObject` → bank2 (2026-10-20, audit round 3 #C1)

The renderer moved out of bank0's mid-flow into bank2's `$F486-$F5FF` fill
window; the helpers (fineAdjust/SOXP/reflection/tables) live in the `$F800`
fill, and bank0 keeps only a 3 B corridor pad.

### Size (measured, `tools/rom_size_report.py --md`)

| | bank0 | bank1 | bank2 | bank3 | total | level data |
|---|---|---|---|---|---|---|
| before (05ea633) | 3568 | 2948 | 1149 | 1285 | **8950** | 410 |
| after | **3266** | 2948 | **1537** | 1285 | **9036** | 410 |
| delta | **−302** | 0 | +388 | 0 | +86 | 0 |

bank0 = −289 body −16 type tables +3 pad. bank2 = +314 (body, vs 289 in
bank0: inline dark test + two `jmp ReturnPad` tails) +17 SOXP +18 reflection
+15 fineAdjust +24 tables +3 pad half. The +86 total is the price of the local
variants. Where the freed bytes landed (emitted-byte occupancy from the new
`bank0.lst`): the `$F6EB-$F8BF` fill block grew to **469 B contiguous**
(org-able; it was ~167 B), while `$FB08-$FBCF` stays 200 B, `$FC20-$FC48` 41 B
and the appended-flow tail stays 16 B (the `$FC55` MusicTick pad still bounds
it — the flow end did not move). So bank0's insertable capacity went from
258 B (audit: 200 + 44 + 14) to ~726 B in the same class of windows.

### Cycles (measured, `sim_frame_budget`)

−46c on every scenario's worst VBL frame, wall model unchanged:

| scenario | VBL max before | after |
|---|---|---|
| default gate | 1059c (f121) | **1013c** (f121) |
| `SIM_FLY=Y` | 1124c (f211) | **1078c** (f211) |
| `SIM_FLY=X` | 1098c (f114) | **1052c** (f114) |
| `SIM_FLY=M` | 1097c (f50) | **1051c** (f50) |

Savings: the per-object `FoldIndirect` (25c) and the `FetchPtr` staging (12c)
are now one `lda (EnemyDataLo),Y` (5c), and `CallPad_IsRoomDark` (~21c of
pad overhead) is an inline test. Cost: pad entry `sta $1FF8`+`jmp` (7c) and
exit `jmp ReturnPad`+`sta $1FF6` vs `rts` (7c). Net −46c, still 161c+ of the
#23 window free.

### Guards added / changed

- `verify_build.CORRIDOR_PADS += ("CallPad_SelectObject", $FC1D, bank2,
  "SelectActiveObject")` — both halves byte-checked (bank0 `sta $1FF8`, bank2
  `jmp` operand from bank2.lst), and bank0's `$FC20` may not hold a `jmp`.
- NEW `verify_build.check_bank2_xpos`: bank2's fineAdjust base is page-aligned
  AND (begin−241) sits in the previous page (guaranteed 5c table read), and
  `bcs .Div15Loop` + the whole routine stay inside one page — the same
  contract the `$FF0F` copy is pinned to.
- `test_raft.tally_gate` now drives the REAL path (pad → body → ReturnPad,
  asserting the return lands in bank0) instead of entering the body.
- `test_room_dark.check_select_object_dark` (new): drives the pad for rooms
  0-9 and asserts the inline mask matches bank1's IsRoomDark split for
  EnemyRamD b4-7, LaserState b2-5 and the rooms-8+ lit guard.
- `test_key_pickup`: slices the bank2 body; the `LevelStartRoom = $A7` copy is
  live again (the renderer reads it) — the guard now requires it; its py65 run
  reads FROZEN labels (was mixing live *.lst with frozen *.bin — exposed by
  this move).
- `test_bomb_render_x`: watches `SetObjectXPos_b2` in bank 2 (was `$FF0F`).
- `test_enemy_movement`: draw-path Y assertions read bank2; `test_level_bank`:
  fold sites 20 → 18, `sta FetchPtr` 10 → 8.

### Deviation from the audit

The audit listed "remove the IsRoomDark pad". It cannot be removed: the VBL's
band-color path (`COLOR_CAVE_BG` on bomb states) still calls it every frame,
and the pad is a byte-identity-pinned corridor slot. Only the per-object call
left (the reason it was removable in the plan).

## C2 — `LoadLevel` → bank2 (2026-10-20, audit round 3 #C2)

Audit said "−26 B flow (32 body, +6 pad)". **The measured body was 124 B**
(`$F535-$F5B0` in the pre-change `bank0.lst`, = the whole "level mgmt" cluster
row of the audit's own composition table), so the move is 4.8x bigger than
the ranking table claimed. Re-measured before touching anything.

| used | before (f53b99f) | after | Δ |
|---|---|---|---|
| bank0 | 3266 | **3170** | **−96** |
| bank1 | 2948 | 2948 | 0 |
| bank2 | 1537 | **1650** | +113 |
| bank3 | 1285 | 1285 | 0 |
| total | 9036 | 9053 | +17 |

- bank0 = **−124 B of flow** (`CheckMinerPickup` moved `$F5B1` → `$F535`) plus
  +22 code (`sta $1FF8` pad 3 + `LF_B0Tail` stub 19) and +6 data (the two
  `.byte 0,0,0` dead halves), all landing in the corridor fill → used −96.
- bank2 = +113 used (code +110, data +3): the 102 B body at `$F640-$F6A5`
  (`.ds $F700` pin intact, so `LevelDataTable` stays frozen at `$F700`), the
  6 B pad halves at `$FC23`/`$FC26` and the 3 B dead half.

### Shape: one dual pad, zero pushes

`LoadLevel` used to tail into `DropArm` and had 5 call sites (boot `$F02E`,
`ReloadLevel` tail, two title paths, tally done). Keeping that drop-in tail in
bank0 is what makes the move stack-neutral:

```
A=$FC20  bank0: sta $1FF8        bank2: (dead)          <- entry, bank0 runs
A+3=$FC23 bank0: .byte 0,0,0     bank2: jmp LoadLevelB2
$FC26    bank0: .byte 0,0,0      bank2: sta $1FF6       <- return, bank2 runs
$FC29    bank0: jmp LF_B0Tail    bank2: .byte 0,0,0
$FC2C    bank0: LF_B0Tail: lda LevelStartRoom / jsr EnterRoom /
         lda LevelStartX / sta RoomX / lda LevelStartY / sta RoomY / jmp DropArm
```

So both directions are "caller `sta $1FFx` + target-bank `jmp` at A+3" (F6
discipline), and neither direction pushes: boot/RESET SP depth is unchanged
(gated by `sim_bomb_fuse` + `test_tally`). The `EnterRoom` call, the level-start
placement and `DropArm` stay in bank0 — that is the reason no local
`rts`-tail `EnterRoom` variant was needed (the audit assumed one; a bank2
`jsr EnterRoomB2` cannot work because its tail is `sta $1FF6 / rts`, i.e. it
always pops a BANK0 frame).

### Cycles: −140c cold path

7 `jsr FoldIndirect` → 7 `lda (FetchPtr),Y` (25c → 5c each). Same bank for the
reader and `LevelDataTable`, so no switch at all; the two pad entries add 7c
each (entry + return). Net **−140c** on level load / death reload / tally
advance. Cold path only, no frame-budget impact (`sim_frame_budget` unchanged).

### Guards added / changed

- `verify_build.CORRIDOR_PADS += ("CallPad_LoadLevel", $FC20, bank2,
  "LoadLevelB2")` — entry half byte-checked, operand resolved from `bank2.lst`.
- NEW `verify_build.check_loadlevel_tramp`: pins the inverted return half
  (`bank2 $FC26 = sta $1FF6`, `bank0 $FC29 = jmp LF_B0Tail`), `bank0.lst
  LoadLevel == $FC20`, bank2 has the body label, bank0 has none, and the
  `LF_B0Tail` instruction shape (`lda LevelStartRoom / jsr EnterRoom /
  lda LevelStartX / sta RoomX / lda LevelStartY / sta RoomY / jmp DropArm`) —
  a silent relocation of the tail back into bank2 would grow the stack depth.
- `test_respawn_hover`: reads `LoadLevelB2` in bank2 for the `sta Hover` clear
  and asserts bank0's `LoadLevel` is still the `$1FF8` pad.
- `test_room_dark`: the `LaserState` dark-bit clear assertion now reads
  bank2.asm.
- `test_level_bank`: fold sites 18 → 12, `sta FetchPtr` 8 → 6 (the 7 level
  reads left the flow).
- `sim_bomb_fuse` / `sim_frame_budget` hooks needed no edit: both resolve
  `LoadLevel` from `bank0.lst` and match the `jsr` opcode+operand, which now
  points at the `$FC20` pad — the poke still lands before the body reads
  `Level` (the sim prints the pad PC).

## C3 — room-exit handlers → bank2 (2026-10-20, audit round 3 #C3)

Re-measured first: the four handlers were `$F4DB-$F535` = **90 B** (the audit's
figure), and the audit's "needs 3 local call variants" was right in spirit but
one of them turned out to be unnecessary — see the A-register trick below.

| used | before (9a9a3f8, after C2) | after | Δ |
|---|---|---|---|
| bank0 | 3170 | **3092** | **−78** |
| bank1 | 2948 | **2924** | **−24** |
| bank2 | 1650 | **1770** | +120 |
| bank3 | 1285 | 1285 | 0 |
| total | 9053 | 9071 | +18 |

- bank0: −90 B of flow (`CheckMinerPickup` moved `$F535` → `$F4DB`) + 12 B of
  entry pads in the `$FBD9-$FBE4` fill.
- bank1: −24 (GetConnIdx body 15 B + its `jmp` half 3 B + 3 B fill + alignment).
- bank2: +120 — `LevelConnB2` 20 B at `$FC4F`, the four handler bodies to
  `$FCB7` (105 B total), four `jmp` halves at `$FBDC-$FBE7` (12 B), 3 B dead.

### Local variants: two of the three the audit listed, the third avoided

- **conn-index read** → `LevelConnB2` (in-bank `FetchPtr = level base + 2n`,
  `Y = RoomNo*2`; same math as bank1's GetConnIdx, carry trick included).
- **fold** → direct `lda (FetchPtr),Y`.
- **`EnterRoom` local `rts` tail** → **not needed.** The old tail was
  `jsr EnterRoom` *then* `lda #edge / sta RoomY`. `EnterRoomB2` + bank3's
  `B3RoomBlocks` read NEITHER RoomX nor RoomY (grepped before the edit), so
  the edge store can happen BEFORE the call and the handler then
  `jmp EnterRoomB2`, whose own `jmp ReturnPad` pops the original bank0
  `jsr ExitRoomXxx` frame. 0 pushes, 0 extra jsr levels, no ghost pad.
  The one trap: the store must not clobber A, because `EnterRoomB2` starts
  with `sta RoomNo` — so the edge goes through Y (`ldy #PLAYER_MIN_Y /
  sty RoomY`), never `lda #… / sta RoomY` (that would pass 0/4/132/159 as the
  room number). `verify_build.check_exit_handlers` pins exactly this, plus
  "placement before the EnterRoomB2 tail" and "no-exit path ends in ReturnPad".

### Pads retired: `CallPad_GetConnIdx`

C3 removed its last caller, so the pad and its body are gone: bank0 `$FC08`
(the `sta $1FF7` half) and bank1's `$FC0B` `jmp GetConnIdx` half became fill,
and bank1's 15 B `GetConnIdx` body was deleted. `verify_build` now rejects a
returning `CallPad_GetConnIdx` (same class as the `CallPad_Overscan` guard).
The corridor stays packed 3 B apart — the removed slot is `$FC08` only; every
other pad and its twin kept its address (`AddScore` still at `$FC0B`).

### Cycles

Cold path (a room crossing once per transition): each exit pays `jsr
LevelConnB2` (6c) + the direct read (5c) instead of `CallPad_GetConnIdx`
(~12c + 8c of pad) + `jsr FoldIndirect` (25c), and the crossing then enters
`EnterRoomB2` (already in-bank). Net ≈ **−30c per crossing**; the audit
expected +8-11c, i.e. dropping the fold hop paid for the rest. No frame-budget
effect: `sim_frame_budget`'s down-crossing scenario (EXIT='down') drives this
exact path and stayed green.

### Guards added / changed

- `verify_build.EXIT_PADS` (4 entries) folded into `SPLIT_PADS`: bank0
  `sta $1FF8` at `$FBD9/$FBDC/$FBDF/$FBE2`, target-bank `jmp` operand resolved
  from `bank2.lst`.
- NEW `verify_build.check_exit_handlers`: per body, `jsr LevelConnB2` first,
  `ldy #<edge>` + `sty RoomY/RoomX` (never `lda`), `beq ExitNoneB2`,
  `jmp EnterRoomB2` as the last instruction, shared `ExitNoneB2: jmp ReturnPad`,
  and no handler label left in kernel.asm.
- `verify_build.CORRIDOR_PADS` lost the `GetConnIdx` entry; the
  "CallPad_GetConnIdx is back" anti-regression check was added.
- `test_enemy_movement`: the `DeriveEnemyY` slice terminator moved from
  `ExitRoomDown:` (which is now a pad at `$FBD9`, far below) to
  `CheckMinerPickup:` — the first routine after the derive cluster in source
  order.
- `test_level_bank`: fold sites 12 → 8 (4 exit-handler folds gone).

---

## Campaign summary — 2026-10-20

Starting point (post merged-title, `fbfe84e`): 10362 used / 6022 free.
Earlier peak reference (pre-title work): 11076 used.

| step | total used | note |
|---|---|---|
| vcrunch removal + hcrunch simplification | 9453 | −909 |
| (banner removed then reverted) | 9452 | parser fix only |
| title kernel band reuse | 9321 | −131 |
| level-data C1 (shared blocks) | 9283 | −38 |
| repack moves 1-5 (PickPlayerFrame, M1StripBlast, PHM/M1 overlay, Tally, B3StageBand) | 9173 | −110, bank2 −538 |
| music pack + C2/C3/C4 + tail pads | 9050 | −123 |
| CallPad corridor split | 8974 | −76 |
| water_respawn gate fix + dead pins + data micro-pack | 8950 | −24, level data 410 |
| C1 SelectActiveObject → bank2 | 9036 | +86 total, **bank0 −302**, VBL −46c |
| C2 LoadLevel → bank2, C3 exits → bank2 | 9071 | +35 total, **bank0 −214 more** |

Final measured state: **9071 used / 7313 free**; bank0 3092, bank1 2924,
bank2 1770, bank3 1285; level data 410 B; bank0 has a **680 B contiguous
org-able block** at `$F618-$F8BF` plus 197 B at `$FB0B` and the tail slots.

Why total went up at the end: the last two chunks trade ~121 B of total ROM for
~516 B of bank0 flow. Bank0 was the only binding resource; total ROM is not.

Gates at the end: `./build.sh` (verify + sim_bomb_fuse + sim_frame_budget),
`freeze_test_banks.sh`, 43/43 battery incl. `src/tools/test_title_demo.py`.
Wall model unchanged (cave 267.0, title 265.0). Min stack SP improved
`$F7`→`$F9`. Three pre-existing `verify_build` warnings remain: models 5/6
declare 6 wall rects > the 5-rect cache (documented cell-swap requirement).

### Measured leftovers, not done (and why)

- PF row pool: 13 B net straight, 26 B only by breaking the `TilePF0+9/+10`
  meta contract. Not worth the contract risk.
- Hot-flag bit (5 B net), 3-byte enemy records (5 B net): both below the
  value floor and both touch walked formats.
- Dead pad halves: 40 B exist but 0 are insertable (each sits between a pin
  and the mandatory live `jmp` at A+3).
- LWC move: costs +16 B.
- HUD PF-table: rejected — only lives+bombs are PF-able (~139 B net), the
  display changes, and bar/score are already at parity.
- Rotation → multiplexing: rejected — `.Grp1` is 69c of a 72c window; indexed
  slots cost +2-3c/line and 2 lines per reposition, and flicker survives
  because `DeriveEnemyY` overlaps Y windows.
- Laser clamp move: +16 B, 2 switches/beam frame.

### What the campaign actually bought

1. +680 B of bank0 leaf space (was 1 B append / 16 B tail) — new bank0
   content is now possible without a repack.
2. Level data 548 → 410 B (−25%), with converter-side ownership and honest
   readers.
3. Bank2 1399 → ~1515 code after gaining SO/LoadLevel/exits; bank3's
   level-data window +193 B, still used 410 B.
4. 43/43 tests, and `test_water_respawn` can actually fail again.
5. Total ROM −1291 B vs the campaign start despite the last +121 B trade.

---

## A1 (2026-10-20): SelectActiveObject back to bank0 — C1 reverted

C1 bought ~86 B of ROM by moving the GRP1 renderer into bank2, paying with a
cross-bank pad and a duplicated SetObjectXPos/fineAdjust/reflection helper
set. Bank0 is no longer the binding resource (680 B contiguous at
`$F615-$F8BF`), so A1 reverses the trade: the body goes back into that
window, bank2 gets ~360 B of contiguous slack for the bank3 evacuation, and
the ROM shrinks.

| | before (C1) | after (A1) | delta |
|---|---|---|---|
| bank0 used | 3092 | 3397 | **+305** (body 289 @ `$F615` + tables 16 @ `$F736`; fill left 378 B to the `$F8C0` pin) |
| bank1 used | 2924 | 2924 | 0 |
| bank2 used | 1770 | 1382 | **−388** (body+helpers+tables+pad half) |
| bank3 used | 1285 | 1285 | 0 |
| **total ROM** | 9071 | **8988** | **−83** |
| VBL worst (sim) | 1013c | **1057c** | **+44c** (1472c `#23` window → 415c margin) |
| wall model | cave 267.0 / title 265.0 | unchanged | 0 |

Placement: the body + `EnemyColorTable`/`ObjSpriteOffTable` sit in the
`$F8C0` fill (nothing ahead of them moves address), so **no fold pad, no twin
and no branch page-cross audit was needed**: caller and body are both bank0.

What came back with the body: `jsr FoldIndirect` for the enemy type (level
data lives in bank2/bank3) and `jsr CallPad_IsRoomDark` (bank1), i.e. the
per-draw 2 switches C1 had removed. Bank2 loses `SelectActiveObject`, its
`SetObjectXPos_b2`/`fineAdjustBegin_b2`/`SetObjReflection_b2` copies, the two
type tables, `BitMaskTab`, and the `$FC20 jmp SelectActiveObject` pad half.

Corridor pads: `CallPad_SelectObject` ($FC1D) is retired, but its **3 bytes
stay as dead fill** — `CallPad_LoadLevel` must keep its $FC20 pin, because
bank2's $FC23/$FC26 halves are addressed from there.

Guards/tests retargeted (all watch bank0 again, no stale bank2 watches):
- `verify_build.check_bank2_xpos` **deleted** (its subject left the bank);
  bank0's pinned SetObjectXPos page contract guard is unchanged.
- `verify_build.CORRIDOR_PADS` loses the `CallPad_SelectObject` entry.
- `test_bomb_render_x` watches `$FF0F` in bank 0.
- `test_room_dark.check_select_object_dark` now drives the real cross-bank
  dark path (bank0 body → `CallPad_IsRoomDark` → bank1 `IsRoomDark` →
  `ReturnPad`) instead of the deleted inline mask, and its FoldIndirect type
  read is exercised too.
- `test_key_pickup`, `test_enemy_movement`, `test_raft.tally_gate` read/slice
  the bank0 body; `test_level_bank` fold/stage lower bounds go back up
  (9 live fold sites, 8 `sta FetchPtr` lines).

Gates: `./build.sh` green (verify_build OK, `sim_bomb_fuse` OK,
`sim_frame_budget` OK — VBL max 1057c), banks re-frozen, 43/43 battery incl.
`src/tools/test_title_demo.py`. Same three pre-existing verify warnings
(pre-pad headroom 16 B, models 5/6 rect counts).

---

## C1 (2026-10-20) — grid-position connections, `LEVEL_FORMAT = 2`

The generator stored exits as a 2 B **nibble room-index** pack (`$F` = none),
which hard-capped a level at **15 rooms** — the blocker for the 20-rooms-per-
level goal of `docs/level_format_plan_2026-10-20.md`. C1 replaces it with
**1 B per room holding the room's grid position**, and exits are *derived* at
room load by scanning that column. Nothing about the stage changes: the
positions come from `room_x`/`room_y`, which the editor already authors.

### Record + encoding

```
level base + 0    RoomDataTable   2 B/room (shape word, unchanged)
level base + 2n   RoomPositions   1 B/room  (x<<4 | y, level-origin normalised)
level base + 3n   RoomEnemies     1 B/room  (was +4n)
level base + 4n   EnemyDataTable  4 B/record (was +5n)
```

* Position nibbles are **0..14**; **nibble 15 is the off-grid sentinel**. That
  is the whole boundary guard: stepping a neighbour position with plain byte
  arithmetic (`$FF` up / `$01` down / `$F0` left / `$10` right) off the grid
  always lands a nibble at 15, which no room may own, so the scan reports "no
  exit" with **zero guard code**. Cost: the cell space is **15×15 = 225**, not
  the plan's 256 — irrelevant at 20 rooms/level, and cheap insurance against a
  silently wrong connection (`tests/grid_conn` pins the property).
* Normalising per level (`min_x`/`min_y`) keeps adjacency intact and lets a
  stage sit anywhere in the editor grid (level 4 currently uses `room_x = -1`).
  A level spanning >15 cells on either axis is rejected by the converter with
  the measured span in the message.
* Duplicate positions are rejected (the scan would silently pick the first).

### Runtime (bank2, cold path only)

`ExitUpB2`/`ExitDownB2`/`ExitLeftB2`/`ExitRightB2` are now 3-byte stubs that
load a direction index and tail-jmp one shared body (`ExitDirB2`): stage
`FetchPtr = base + 2n`, read the room's own position, `adc ExitDeltaTab,X`,
`jsr ExitScanB2` (linear scan, ≤ `LevelRoomN` iterations, returns the room
index + carry), then the same opposite-edge placement and `jmp EnterRoomB2`
with the room index still in A. `LevelConnB2` is gone (the staging is inline:
one push fewer). The scan's target byte lives in `LevelConnSpare` (`$A2`),
the ZP byte freed when `LevelConnHi` died — new hand copy in bank2, paired by
`check_equ_sync`.

**Frame cost: zero.** No kernel/VBL/overscan code changed — `sim_frame_budget`
and `sim_bomb_fuse` are green unchanged (cave 267.0 / title 265.0).

### Size

| | before | after | delta |
|---|---|---|---|
| room tables (16 rooms) | 5 B/room = 80 B | **4 B/room = 64 B** | **−16 B (−1 B/room)** |
| enemy records (9) | 36 B | 36 B | 0 |
| level index (4 levels × 7) | 28 B | 28 B | 0 |
| **level data total** | **410 B** | **394 B** | **−16 B** |
| bank2 code | 2096 | 2077 | **−19** (EnterRoomB2 −2, exit block net −17) |
| bank2 used / free | 2632 / 1464 | **2605 / 1491** | **+27 free** |

Marginal room (shared model, no enemies): **4 B** (was 5). Level data numbers
are `tools/rom_size_report.py --md` at this HEAD; the code delta is the `.lst`
code-column difference (the exit block still fits the pinned `$FC4F-$FCB7`
105 B window — it now ends at `$FCAE`, 9 B slack).

### Versioning + guards

* `convert_level.LEVEL_FORMAT = 2` is emitted as `LEVEL_FORMAT = $02` into
  `generated/levels_index.asm`; `kernel.asm` and `bank1.asm` carry hand copies
  (bank1's is paired with kernel by the existing `check_equ_sync`).
* `verify_build.check_level_format` (new): generated == kernel == bank1 == 2,
  every generated level file has exactly 1 B of positions and 1 B of RoomEnemies
  per room, positions unique-by-construction are re-checked, and **no position
  may use nibble 15**. A stale `generated/` tree (format 1) fails here instead
  of being misread by the `+2n/+3n/+4n` offsets.
* `verify_build.check_exit_handlers` rewritten for the new bodies: direction
  stubs must load the index matching their direction, `ExitDirB2` must stage
  `+2n`, `adc ExitDeltaTab,X`, `jsr ExitScanB2`, branch on carry, `sty RoomY/X`
  before `jmp EnterRoomB2`, and the two tables must keep the
  up/down/left/right order. `bank2.asm` may not mention `RoomConnections`.
* `test_level_bank`: block order/offsets, 1 B position + 1 B enemy per room,
  unique positions, `LEVEL_FORMAT` in all three places, 225-cell cap.
* `test_grid_conn` (**new**): converts a test-owned **20-room** level (15-wide
  row + 5-room second row, built in a temp dir from `src/tests/rooms` models)
  and drives the **frozen bank2 handlers** for every (room, direction): 46 real
  exits land on the JSON-adjacent room with the right edge placement, 34
  no-exits stay put, and each of the 18 off-grid steps is proved to land in the
  nibble-15 sentinel.
* `test_band_restage` / `test_water_band` / `test_water_respawn`: offset
  comments + the respawn band poke moved `base + 3n`.
* Frozen banks + frozen `src/tests/generated/` re-frozen (they carry the new
  table layout); `test_editor_roundtrip` regenerates against the frozen copies.

### Cap proof

`tools/test_grid_conn.py` converts and resolves a 20-room level end-to-end;
20 > the retired 15-room nibble cap, and the encoding's own ceiling is 225 rooms
(15×15 cells, one unique position each) — comfortably above the 20/level goal,
so the *next* cap a 20-level game hits is ROM size (plan §2), not connections.

Gates: `./build.sh` green (verify_build OK, `sim_bomb_fuse` OK,
`sim_frame_budget` OK), banks re-frozen, 43/43 `tools/test_*.py` +
`src/tools/test_title_demo.py` green.

---

## C2 (2026-10-20) — 3 B shape-index room records, `LEVEL_FORMAT = 3`

The per-room block word is gone. A room is now **three 1 B columns** (a 3 B
record spread over three arrays — SoA, not AoS) and the block address is a
6-bit **shape index** into one global word table:

```
base + 0    RoomShapes     1 B/room   idx b5-0 | band b6 | owns-extras b7
base + n    RoomPositions  1 B/room   (x<<4|y — C1, unchanged)
base + 2n   RoomCounts     1 B/room   count<<6 | extras index (b5-0)
base + 3n   EnemyDataTable 4 B/record (contiguous in room order)
```

`LEVEL_ShapeTable` (in `levels_index.asm`) holds one `.word <block>RoomRects`
per distinct block; `SHAPE_<label> = n` EQUs let the room tables stay symbolic,
so `dedupe_room_blocks()` keeps working without rewriting room lines (the
duplicate's EQU resolves to the surviving block's ordinal).

### Why SoA instead of the plan's literal `+0/+1/+2`

An interleaved record would have made the **exit scan** step 3 bytes, which
needs a scan limit (`3n+1`) — a new ZP byte, a divide-by-3 on the hit path, and
~30 B inside the pinned `$FC4F-$FCB7` window (9 B slack). Column layout keeps
`ExitScanB2` byte-identical (`base + n`, `Y` = room, `cpy LevelRoomN`) and keeps
the derived enemy index a stride-1 sum. Total record width is still exactly
3 B/room, as specified.

### Runtime (cold path only)

* `EnterRoomB2`: shape byte → `LEVEL_ShapeTable` word → `RoomRectsLo/Hi`
  (replaces the 2 B word read); band b6 staged to `RoomBandColor` **before**
  the block reader (only writer, unchanged address); count byte → `EnemyCount`;
  first record index = sum of the count bytes of rooms `0..room-1`
  (`LevelConnSpare` is the accumulator — the exit scan has already returned),
  records base = `base + 3n`, `+4*index`.
* `ExitDirB2`: stages `base + n` (was `+2n`). One instruction fewer.
* `B3RoomBlocks` / `StageBandTab` / `B3StageBand` / `PhaseBlink`: unchanged —
  they read `RoomRectsLo/Hi`, `PF0Buf` and the staged `RoomMetaA/B`.
* Caps removed: **31 enemy records/level** (the packed index field) and the
  4 B room row. New cap: **64 distinct blocks** (6-bit shape index), which is
  the C2 form of the plan's "≤63 shapes per level" — global here because the
  model blocks are shared across levels.

### Size

| | before | after | delta |
|---|---|---|---|
| room rows (16 rooms) | 4 B/room = 64 B | **3 B/room = 48 B** | **−16 B (−1 B/room)** |
| shape address table (12 blocks) | — | 24 B (2 B/block) | **+24 B** |
| enemy records (9) | 36 B | 36 B | 0 |
| level index | 28 B | 28 B | 0 |
| **level data total** | **394 B** | **402 B** | **+8 B** |
| bank2 code | 2077 | 2107 | +30 |
| bank2 used / free | 2605 / 1491 | 2643 / 1453 | −38 B free |

**Marginal room = 3 B + 2 B per NEW block + 4 B/enemy.** C2 does **not** shrink
level data at this stage's density (16 rooms, **12 distinct blocks** — models 1-8
+ one surviving async block per shape class): the plan's −1 B/room holds only
when rooms outnumber shapes 2:1, i.e. `R·1 B − S·2 B > 0` → `R > 2S`. Today
`16 < 24`. At the plan's 210-room density (105 shapes, 2 rooms/shape) C2 is
−210 B; at 400 rooms/200 shapes it is −400 B. The 8 B gap is the price of
addressing blocks from 6 bits; the only zero-table alternative is a
length-walk over the block stream, which would cap the whole game at 64 shapes
**and** contradict the plan's own 105-shape target, so it was rejected.

### C5 (async extras) NOT folded

C2 is correct without the extras stream: an async room keeps its own block and
the shape table routes to it (asserted per live async room in
`test_band_restage`). Folding C5 now would be **wrong, not just early**: an
async room's block contains its own **solid rect list** (patch cells change
solidity, e.g. L1R1 has 3 rects with different bounds than model 0), and
rebuilding rects at load needs C4's cell collision (`cell_collision_plan`
5.1b/7.1) — the plan's "4-6 B extras rebuilt from the model + patches" is only
true once the rect cache is gone. The record's b7 / extras-index bits are
therefore **reserved 0** and hard-failed by guards if anything sets them.

### Versioning + guards

* `convert_level.LEVEL_FORMAT = 3` (C1 was 2); `kernel.asm` + `bank1.asm` hand
  copies bumped (paired by `check_equ_sync`).
* `verify_build.check_level_format` rewritten for format 3: format byte in all
  three places; per level exactly 1 B of shapes + 1 B positions + 1 B counts
  per room, in that order; every shape label has an EQU **inside**
  `LEVEL_ShapeTable`; `LEVEL_SHAPE_COUNT == table words <= 64`; every table
  entry referenced; no `RoomDataTable`/`RoomEnemies` label survives (stale
  block word); count bytes must have a **zero extras index** and count ≤ 3;
  shape bytes may only set b6 (b7 reserved); positions keep the nibble-15
  off-grid sentinel rule.
* `check_exit_handlers`: `ExitDirB2` must stage `base + n` (was `+2n`).
* `test_level_bank`: new record shape, shape registry/table pair, counts sum ==
  enemy records, extras-index rule.
* `test_grid_conn`: 3 B/room contract; base+n staging for the exit handlers.
* `test_band_restage`: symbol set → `LEVELn_RoomShapes`/`LEVELn_RoomCounts`;
  derived enemy base checked per room; **new assertion** that an async room's
  loaded block is not the shared model block.
* `test_raft` / `test_water_band` / `test_water_respawn`: label rename; the
  respawn poke now sets b6 of the shape byte (`base + room`).

Gates: `./build.sh` green (verify_build OK, `sim_bomb_fuse` OK,
`sim_frame_budget` OK — no kernel/VBL/overscan change), banks re-frozen,
44/44 `tools/test_*.py` + `src/tools/test_title_demo.py` green.

---

## C3 (2026-10-20) — row dictionary: MEASURED, **not implemented** (under the gate)

Task gate: "if the measured saving is <40 B or the reader change costs more than
it saves, stop and report". Measured **36 B of level data** (net **+30 B** after
the reader), so the chunk was stopped before any edit. `src/`, `tools/` and the
frozen banks are untouched.

### The measurement (live HEAD 00caed2, all emitted blocks)

Every emitted block's PF triple was extracted from `generated/models_data.asm`
(8 shared `M<id>` blocks) + `generated/level_*_blocks.asm` (4 per-room blocks —
`L1R1`, `L4R2`, `L4R5`, `L4R6`), i.e. the 12 rows of `LEVEL_ShapeTable`:

```
12 blocks x 3 bands = 36 band slots -> 12 DISTINCT (PF0,PF1,PF2) rows
raw   9 B/block x 12 = 108 B
after 3 B/block     x 12 =  36 B  (row indices)
    + 3 B/row       x 12 =  36 B  (pool)
                            =  72 B            -> -36 B (-3 B/block)
```

Level data **402 B -> 366 B** (the plan's own pool line, §3.2, agrees: saving
= `6·S − 3·U`, S = shapes, U = unique rows). The chunk's "~70-106 B" estimate
double-counted: 108 -> 72 is 36 B, not ~72 B.

### Reader cost (assembled with dasm, not estimated)

The block layout keeps the reader's arithmetic: rows sit at
`block + 2 + 2·nrect` — **the same address as today's `TilePF0` base** — so only
the copy loop and the meta offset change (meta moves Y=9/10 -> 3/4):

| variant | bytes |
|---|---|
| today: `lda (FetchPtr),Y` 9-byte copy + meta (incl. the 10 B pointer copy) | 29 |
| pool expansion, pointer copy kept | 45 (**+16**) |
| pool expansion, `nrect` math folded into `FetchPtr` (drops the 10 B copy) | **35 (+6)** |

So the honest total is **-36 B data + 6 B code = net +30 B**, and the pool is a
*scaling* investment, not a today win. Per new model: +6 B when its 3 bands are
already pooled, +3 at one new row, 0 at two, **-3 when all 3 bands are new**
(break-even = 2 shared bands).

### What the numbers say about ordering

* Today's saving is small because there are only 12 blocks. At the plan's
  targets it is `6·S − 3·U`: **~540 B at 105 shapes** (U=30), **~1 065 B at 200
  shapes** (U=45), minus the 6 B reader.
* C5 *shrinks* C3's today value (the 4 per-room blocks disappear -> only 8
  blocks left -> 12 B), so C3 should land **after** C6/C7 grow the shape pool,
  or be bundled with C4 (the always-emitted hot-count byte is 12 B of the same
  per-block class).
* C4 alone is **-62 B today** and independent — better next chunk.

### Design kept for the retry (files, layout, guards)

* Block: `[count][2 B/rect][0 = hot count][row0,row1,row2][MetaA][MetaB]`;
  pool emitted in `levels_index.asm` as **3 SoA columns** (`LEVEL_RowPoolPF0/1/2`,
  1 B/row) so the reader needs no second pointer: `lda PoolPF0,X / sta PF0Buf,Y /
  sta +3,+6` over `Y = 2..0`, `X = (FetchPtr),Y`.
* Converter: `convert_room.lines()` gains the pool (global dedupe keyed by the
  3-byte triple, across models **and** per-room blocks), `write_levels_index()`
  emits `LEVEL_ROW_COUNT` + the columns; `_gen_data_size` unchanged.
* `verify_build`: `LEVEL_ROW_COUNT` == emitted rows (<=256), every index < count,
  every row referenced, no `TilePF*` label left in any block, rows base ==
  `block + 2 + 2·nrect`.
* PF parity: the pool holds the *same* triples, so parity is structural —
  assert it in the converter (expanded bytes == the pre-C3 triple) **and** keep
  `test_band_restage`'s PF-cache assertions (they read the loaded `PF0Buf`).
* Zero kernel/VBL/overscan impact (room load only), no ZP change, no `src/rooms`
  edit: the format stays fully derived from the JSON.

Gates for the retry: `./build.sh`, freeze, full battery, ledger — the same
checklist as C2, plus `test_cell_map`'s pure-PF parity.
