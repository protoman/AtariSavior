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

## 12. Chunk 3 — level-exit tally simplified (award at once, keep the hold)

User decision 2026-10-19 (A+C). The tally screen is kept (frozen miner scene
+ bonus + level advance) but it no longer counts up. Removed: the 4-frame
pacing divider (`TickCounter` in the arm), the +50-per-tick step in
`TallyWork` (`CallPad_AddScore`), the event bits b0/b1, and the coin blip
(`AUDC0/AUDF0/AUDV0/BombSnd` writes). Kept: the arm computation
(`BarLevel/6 + TallySum`), `DropTarget = $FE`, the miner-only frozen draw
(`SelectActiveObject` tally gate untouched) and the advance tail
(level++/`LoadLevel`/`BarLevel=120`/`TickCounter=60`).

New flow: `TallyEntry`'s arm frame computes the SAME tick total and passes it
to **`TallyAward`** (new, bank2, 62 B) — one BCD add of `50*TallyTicks`
(`100*(N/2)` into the hundreds digit + `$50` into `ScoreTe` when odd, binary
normalize with a thousands carry, `$9999` saturation like `AddScore`). Then
`TallyTicks` is reused as a held-frame countdown (`TALLY_HOLD = 36`, ~0.6 s)
and the done path is unchanged. No bonus value/cap change.

Sizes: `TallyEntry` 97 → 60 B, `TallyWork` (bank0) 64 → 53 B, `TallyAward`
new 62 B; bank2's `$F34F-$F38C` sits in the region's existing fill slack
(next pin `$F3C4`, untouched).

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3015 | 350 | 728 | 3365 | 731 |
| bank1 | 2513 | 502 | 719 | 3015 | 1081 |
| bank2 | 1424 | 361 | 2289 | 1785 | 2311 |
| bank3 | 933 | 368 | 1761 | 1301 | 2795 |
| **total** | **7885** | **1581** | **5497** | **9466** | **6918** |

level data 548 B (index 48 + tables/blocks 334 + models 166).

Delta vs the 9452/6932 tree: bank0 free +12 (code −11), bank2 free −25
(`TallyEntry` −37, `TallyAward` +62), total used +14 / free −14.
Tests: `tools/test_tally.py` now asserts the award on the arm frame (exact
`50*ticks`), a 30-45-frame hold with the score/TickCounter/BarLevel frozen,
no coin tone, and five direct `TallyAward` BCD cases (even, odd, tens carry,
thousands carry, `$9999` cap). The miner-only tally gate in
`tools/test_raft.py` is unchanged and still green.
