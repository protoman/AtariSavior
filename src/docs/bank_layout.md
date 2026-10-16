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
Its helper renders live in bank2 (`TitlePlayerBand` `$F880`, `FooterBand`
`$F700`), reached by bank0 fold stubs (`TitlePlayerFold` `$FBE8`,
`FooterFold` `$FBE0`). This coupling is why relocating the title kernel is a
chain, not a single block.

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
- **Data:** sprites `PlayerSpriteA/B`+`PlayerWalkA/B`+`PlayerColTable` (`$F8DD`
  — byte-twin of bank2), `BombBlinkColors`, `EnemyColorTable`,
  `ObjSpriteOffTable`, `EnemyBitTable`, `YToRowTable` `$F901`,
  `DropSpeedTable`, `ColOff/ColMask`, `ObjColorTab` `$FE00`, `ObjSprites`
  `$FE48`, `BeamMask` `$FEDB`, `StepDelta`.
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
- **Data:** `BarDelayTable`/`BarFineTable` (power bar), `ABWxTab`+`BombMaskBit`,
  HUD font data.
- **Pads:** `ReturnPad` `$FBF8`, CallPad block `$FBFC-$FC47` (byte-identical
  with bank0), `$FC68`/`$FC70` fold pads.
- Free: **`$F025–$F53F` (1307B)**, plus `$FDE3–$FEFF` (285B), `$FF10–$FFF9`.

## bank2 — data + start-of-bank code

- **Start-of-bank code:** `EnterRoomB2` `$F010`, `MothRoutine` `$F100`.
- **Code (moved from bank0):** `TallyEntry` `$F313`, `PickPlayerFrame` `$F3C4`,
  `TitleSequence` `$F4C4`, `BuildColupF` `$FC4F`, `LaserHitTestBody` `$FF00`,
  `FooterBand` `$F700`, `TitlePlayerBand` `$F880`.
- **Data:** `LevelDataTable` `$F767` + per-level rooms/enemies/connections,
  `FooterFont`, `TitleJetColors`/`TitleJetSprite`/`TitleBombSprite` (twins at
  `$F8DD`), `VcrStateTab`, `PhMaskTab`, level spill slots.
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
- **Data:** `CrPfx0/1/2` prefix tables, `.OSgapHi/Lo`.
- Free: `$F0A1–$F7FF` (~1887B), `$FECC–$FFF9` (~302B), plus several 20–155B.

## Cross-bank mechanism (why "just move it" is hard)

- bank0↔bank1/bank2/3 calls go through **same-address byte-identical twins**:
  a `sta $1FFx` executes in the caller's bank, then the following `jmp`/`rts`
  opcode bytes are fetched from the other bank at the **same PC** (fold pads
  `$FC68`/`$FC70`, CallPads `$FBFC-$FC47`, `ReturnPad` `$FBF8`, fold twins).
- bank0 **cannot** read bank1/bank2 data with `abs,X/Y` — a moved table needs
  its reader moved too (or a fold).
- **`.ds $X` pins** keep these twin addresses fixed. Removing content *before*
  a pin frees nothing (the fill grows); freeing space = remove content **and
  shift the downstream pins** (in every bank) — a batched operation.

## "Where does new content go?" (decision guide)

1. Gameplay code / cave kernel → **bank0** (frozen; only via a batched pin shift).
2. HUD / display / leaf helpers → **bank1** (has free space).
3. Level/enemy/font/model data → **bank2**.
4. Crunch/tally bodies → **bank2** if possible (bank3 should trend to data-only).
5. Never add bank0 bytes without removing an equal-or-larger chunk (and doing
   the pin shift) in the same change — see `plans/bank0_space_plan.md`.
