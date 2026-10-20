# Bank layout & kernel map (Savior, F6 16K)

Reference for "where does X live / where should new content go". Addresses are
from the current build (`bank*.lst`); they move with data edits — treat the
**roles** as stable, the numbers as a snapshot (2026-10-16).

## ROM: 4 × 4K banks (F6 bankswitch)

`STA $1FF6`→bank0, `$1FF7`→bank1, `$1FF8`→bank2, `$1FF9`→bank3. Power-up =
bank3 (its reset vector at `$FFFC` points to the 5-byte stub → bank0).

```
   $F000 ............... $FFFF   (each bank is a full 4K window)
   ┌─────────────────────────────┐
   │ bank0  MAIN GAME CODE       │  cave kernel + gameplay + title kernel + sprites/colors
   ├─────────────────────────────┤
   │ bank1  HUD + helpers        │  MenuMain HUD band + power bar + score + call pads
   ├─────────────────────────────┤
   │ bank2  DATA + start-of-bank │  levels/enemies/fonts/folds + EnterRoomB2/Moth/BuildColupF
   ├─────────────────────────────┤
   │ bank3  POWER-UP + crunch    │  5B stub + Phase-4 shutter bodies (mostly code)
   └─────────────────────────────┘
   TARGET (user 2026-10-16): code only in bank0/bank1 (+maybe bank2-start);
   bank3 data-only + the mandatory stub.
```

## Kernels (this is the important part — there are FOUR display kernels)

| kernel | bank | entry | renders | when |
|---|---|---|---|---|
| **Main cave kernel** | bank0 | `KernelInit` `$F9E1` → `CaveKernelRow` `$F0F3` (.Row/.Line `$F134`); `RowSlice` `$FB84` = vcrunch shutter sub-band | the 144-line cave | gameplay |
| **Title kernel** | bank0 | `KernelInit .TkPath` → `TitleKernel` `$F9FB` (.TkLoop/.TkPlayer) | S.A.V.I.O.R. 48px text + player band + footer | intro/title only (COLD) |
| **HUD band** | **bank1** | bank0 `jmp $FC68` fold (after the cave kernel) → `MenuMain` `$F540` | 48-line HUD: score/lives/bombs/timer bar | gameplay |
| **VBL / dispatch** | bank0 | `StartFrame` `$F041` → `VBLTimer` `$F055` → `KernelInit` | (setup, no pixels) | every frame |
| **Overscan** | bank0 | `Overscan` `$F1BB` → `OverscanAudio` `$F336` | (input/AI/collision) | every frame |

Title-kernel note: the title is a **separate cold kernel**, not the cave kernel.
Its helpers + fonts live in bank2 (`TitlePlayerBand` `$F880`, `TitleBandPrep`
`$F3xx`, `FooterBand` `$F700`, `FooterFont`), reached by bank0 fold stubs
(`TitlePlayerFold` `$FBE8`, `FooterFold` `$FBE0`). **The title machinery is
bank0↔bank2 twin-coupled:** `TitleBandPrep` sets `Grp0Ptr` to `PlayerWalkA/B`
and `TitleJetSprite`, and `TitlePlayerBand` reads the sprite from **bank2's
byte-twins at bank0's sprite addresses** (`$F8DD`, `$FDE7`). So the title
kernel's correct home is **bank2** (with its helpers/fonts/twins), NOT bank1 —
moving it to bank1 would require bank1 to hold twins at bank0's sprite
addresses, which is impossible. Only the small flip-animation sprites are the
shared twins; the kernel+`TitleFont` are the movable part.

## bank0 — main game code (`$F000`–`$FFFF`)

- **Frame/handlers:** `GameStart` `$F008`, `StartFrame` `$F041`, `VBLTimer`
  `$F055`, `Overscan` `$F1BB`, `OverscanAudio` `$F336`.
- **Main cave kernel:** `CaveKernelRow`/`.Row` `$F0F3`, `.Line` `$F134`,
  `RowSlice` `$FB84`.
- **Gameplay (overscan):** `UpdateP0Vertical`/`Gravity`, `CheckP0Left/Right`,
  `StepDown/Up`, `PlayerHitsMap` `$F926` (rect-cache walk), `UpdateEnemies`,
  `CheckEnemyHit` `$F71C`, `DeriveEnemyY`, `BombTick` `$F9xx`, `LaserInput`
  `$FF33`, `SelectActiveObject` `$F629`, `LoadLevel` `$F56B`.
- **Title kernel:** `TitleKernel` `$F9FB`, `.TkLoop`, `.TkPlayer`; `TitleFont`
  `$FB00`; `TitleSelect` `$FB30`, `TitleIntro` `$FB4D`; folds `$FBD0`/`$FBD6`/
  `$FBE0`/`$FBE8`.
- **Data structures:**

  | label | size | purpose |
  |---|---|---|
  | `EnemyBitTable` | 4 | enemy index → dead bit (b0-2) for `EnemyDeadMask` |
  | `EnemyColorTable` | 6 | enemy type → `COLUP1` (hue<<4\|luma<<1) |
  | `ObjSpriteOffTable` | 6 | object type (0-6) → `ObjSprites` design offset |
  | `BombBlinkColors` | 4 | explosion blink `COLUBK`: `(60-BombTimer)%3` (blk/yel/red/yel) |
  | `PlayerSpriteA/B` | 12 ea | 8×12 jet frames (bank2 byte-twins at `$F8DD`) |
  | `PlayerWalkA/B` | 12 ea | ground-walk frames (stride / passing) |
  | `PlayerColTable` | 12 | per-row player `COLUP0` (red/yellow/gray/black) |
  | `YToRowTable` | 37 | `(A>>2)` → tile band row (floor-nested `A/48`) |
  | `EnemyOffTable` | 3 | enemy index → record offset (X×4) |
  | `TitleFont` | 48 | title "S.A.V.I.O.R." 6 slots × 8 rows |
  | `SBmask` / `SBod` | 5 ea | vcrunch shutter sub-band: VcrState bit / bodies per slice |
  | `DropSpeedTable` | 9 | drop-in 8.8 px/frame per `Y>>4` tier |
  | `ColOff` / `ColMask` | 20 / 12 | cell-walk: left-half col 0-19 → PF-reg offset (0/3/6) / bit |
  | `ObjColorTab` | 72 | per-scanline GRP1 color (9 slots × 8 rows) |
  | `ObjSprites` | 72 | GRP1 art (9 designs × 8 rows) |
  | `BeamMask` | 12 | laser beam graphic (b1 shared with `LASER_ARMED`) |
  | `StepDelta` | 2 | laser travel step per `PlayerDir` (0=+4, 1=−4) |
  | `fineAdjustBegin` | 15 | `SetObjectXPos` fine-adjust, page-aligned `$FF00` |
  - ZP buffers (not ROM): `PF0Buf` `$C3` (9B band rows), `ColupfBuf` `$E7`
    (12B), `EnemyRamX/Y/D/P`, `RectCount`/`RcW1` rect cache `$89/$CC`.
- **Pins/twins:** `$F8DD` (sprite twin), `$F9B8` (overlay tramp), `$FB00`
  (TitleFont page-align), `$FBFC-$FC47` **CallPads**, `$FC49` MothExitPad,
  `$FC68`/`$FC70` **fold pads**, `$FDE1` (frame tramp twin), `$FE00`/`$FE48`
  (color/sprite twins), `$FE90`/`$FE96` (HOF/LHT tramps), `$FEF0`/`$FEF6`
  (fold block), `$FF00` fineAdjust (page-aligned), `$FF0F` `SetObjectXPos`,
  `$FFE6` TallyTramp.

## bank1 — HUD + helpers

- **HUD band:** `MenuMain` `$F540` (entered via the `$FC68` fold).
- **Positioning:** `SetObjectXPos_b1` `$F7F2` + `fineAdjustBegin_b1` `$FF00`
  (page-aligned; separate from bank0's — used by the HUD bar, free for reuse).
- **Helpers / call targets:** `UpdateBombSound`, `UpdateJetSound`, `BombSndDrop`,
  `BombSndExplode`, `GetConnIdx`, `ClearPFColumn`, `AddScore`, `IsRoomDark`,
  `SetRoomDark`, `UpdateLaserSound`, `StripBlastCheck` `$F937`.
- **Data structures:**

  | label | size | purpose |
  |---|---|---|
  | `BombMaskBit` | 5 | wall rect index → `WallMask` bit |
  | `BarDelayTable` | 121 | power-bar mid-scanline color delay (B=0..120) |
  | `BarFineTable` | 121 | power-bar fine split (F∈{0,1,2,3,4}) |
  | `BombClearMask` | 20 | AND-mask to clear col 0-19's PF bit (inverse of `convert_room.pf_values`) |
  | `LaserFreqTable` | 8 | laser sound frequency per state |
  | `BitMaskTable` | 8 | enemy bit masks (b0-2 used) |
  | `DigitGfx` | 104 | HUD 13+2 score font (6 digits) |
  | `fineAdjustBegin_b1` | 15 | bank1 `SetObjectXPos` fine table, page-aligned `$FF00` |
  | `ABWXTab`/`ABWWTab`/`ABWYTab`/`ABWHTab` | 5 ea | ABW rect field offsets (EQU-derived from `RcW1`) |
- **Pads:** `ReturnPad` `$FBF8`, CallPad block `$FBFC-$FC47` (byte-identical
  with bank0), `$FC68`/`$FC70` fold pads.
- Free: **`$F025–$F53F` (1307B)**, plus `$FDE3–$FEFF` (285B), `$FF10–$FFF9`.

## bank2 — data + start-of-bank code

- **Start-of-bank code:** `EnterRoomB2` `$F010`, `MothRoutine` `$F100`.
- **Code (moved from bank0):** `TallyEntry` `$F313`, `PickPlayerFrame` `$F3C4`,
  `TitleSequence` `$F4C4`, `BuildColupF` `$FC4F`, `LaserHitTestBody` `$FF00`,
  `FooterBand` `$F700`, `TitlePlayerBand` `$F880`.
- **Data structures:**

  | label | size | purpose |
  |---|---|---|
  | `LevelDataTable` (+ per-level) | — | level start/miner/colors + `RoomDataTable`/`RoomPositions`/`RoomEnemies` (LEVEL_FORMAT 2); generated `spill_*.asm` |
  | `MothBitTable` / `MothRowTable` | 3 / 48 | moth enemy turn bits / row lookup |
  | `BCFDarkMask` | 8 | `BuildColupF` dark-room mask per room |
  | `ColOff` / `ColMask` | 20 / 12 | cell-walk copies (bank2-side walkers) |
  | `FooterFont` | 84 | title footer font (6 × 14) |
  | `TitleBombSprite` | 12 | title bomb sprite (bottom-aligned) |
  | `TitleBlinkColors` | 4 | title blink colors (black/yellow/red/yellow) |
  | `TitleJetSprite` | 24 | title jet A/B sprite (byte-twin of bank0 `$F8DD`) |
  | `TitleJetColors` | 12 | title jet per-row colors |
  | `PhMaskTab` | 10 | PhaseBlink blink-cell pair idx → PF bit pair |
  | `PFOffTab` | 10 | pair idx → PF reg offset (0/3/6) |
  | `OvHead` / `OvTail` | 3 ea | overlay patch-strip row markers |
  | `VcrStateTab` | 32 | vcrunch slice state: `sc(clock>>2) → $00/$11/$1B/$1F` |
  | `EnemyOffTable` / `EnemyBitTable` | 3 / 4 | enemy copies (bank2 walkers) |
- **Pads/twins:** `$F9B8` overlay-tramp twin, `$FBD0`/`$FBD6`/`$FBE0`/`$FBE8`
  fold twins, `Bank2ReturnPad` `$FBEE`, `ReturnPad` `$FBF8`, `$FDE1`
  PickPlayerFrame twin, `$FE90`/`$FE96` tramp twins, `$FEF6` fold twin,
  `$FFE6` TallyTramp twin.
- Free: fragmented — largest `$FBA7–$FBCF` (41B), else 20–27B.

## bank3 — power-up + Phase-4 crunch bodies

- **Stub (mandatory):** `$F000` 5B → `sta $1FF6` + `jmp` bank0 (RESET vector
  target). This is the only *unavoidable* bank3 code.
- **Phase-4 crunch bodies (movable target for R2):** `PhVcrEntry` `$F800`,
  `PhHcrEntry` `$F880`, `CrunchClock` `$F900`, `HcrClock` `$F9FE`,
  `HOVFeatEntry` `$FA40`, `HOVvcrunch` `$FA82`, `HOVhcrunch` `$FACB`,
  `VCS3` `$FD80` + tramp-image pads.
- **Data structures:**

  | label | size | purpose |
  |---|---|---|
  | `CrPfx0` / `CrPfx1` / `CrPfx2` | 11 ea | prefix masks `P(n)`, n=0..10 (crunch PF staging) |
  | `HcrBandLo` | 3 | band → `band*48` (HcrPush vertical gate) |
  | `.OSgapHi` / `.OSgapLo` | 2 ea | VCS3 cold-kill aperture bounds ([79,88) / [66,57)) |
  - crunch tramp-image pads (`.byte $4C,…`) — same-address twins for the
    bank2↔bank3 dispatch.
- Free: `$F0A1–$F7FF` (~1887B), `$FECC–$FFF9` (~302B), plus several 20–155B.

## Cross-bank mechanism (why "just move it" is hard)

- bank0↔bank1/bank2/3 calls go through **same-address byte-identical twins**:
  a `sta $1FFx` executes in the caller's bank, then the following `jmp`/`rts`
  opcode bytes are fetched from the other bank at the **same PC** (fold pads
  `$FC68`/`$FC70`, CallPads `$FBFC-$FC47`, `ReturnPad` `$FBF8`, fold twins).
- bank0 **cannot** read bank1/bank2 data with `abs,X/Y` — a moved table needs
  its reader moved too (or a fold).
- **`.ds $X` pins** keep these twin addresses fixed **and** fill the gap up to
  `$X`. Removing content *before* a pin **grows that fill — which is usable
  code/data space in the same bank.** So removal DOES free space; it just does
  not move the "pre-pad headroom" number (which measures only the gap before
  `org $FC68`). A pin shift is needed only to *merge* scattered fills into one
  contiguous run. **CORRECTED 2026-10-16** — the old "removing before a pin
  frees nothing" claim was wrong. See `docs/refactor_v4_plan.md` §0.

## "Where does new content go?" (decision guide)

1. Gameplay code / cave kernel → **bank0** — use the **225B free run at
   `$F7FC–$F8DC`** (verified; before the `$F8DD` sprite pin).
2. HUD / display / other kernels → **bank1** — use **`$F042–$F53F` (~1278B)**.
3. Level/enemy/font/model data → **bank2/3** — bank3 has **`$F0A3–$F7FF` (~1885B)**.
4. Crunch/tally bodies → move out of bank3 (data-only target).
5. There is already **~3400B free** across banks; the constraint is cross-bank
   coupling, not total bytes. See `docs/refactor_v4_plan.md` (verified).
