# E4 Moth Implementation Plan (saved 2026-09-30)

Status: research complete, approved for execution pending user go-ahead.
Spec source: `docs/enemy_movement_plan.md` E4 section + user answers (±6 px
sine = 1 tile total travel; range = spawn ±48 patrol; X ÷2 gate, phase ÷2).

## Findings that shaped the design

1. **LaserHitTest reads `EnemyRamY,X`** (kernel.asm:3575) and runs at
   overscan line ~819, BEFORE `UpdateEnemies` (~970).
   → Y sine **must** be written by `DeriveEnemyY` (bank0, called from
   `RefreshEnemyY` at ~768), NOT by the bank2 moth routine. Otherwise laser
   collision sees stale/static Y while the sprite draws sine Y (±6 px error).
   Readers all consistent if DeriveEnemyY owns Y: refresh(768) →
   LaserInput(819) → UpdateEnemies(970) → CheckEnemyHit(976) → next VBLANK draw.

2. **Latent FetchPtr bug (E3, dormant)**: `PlayerHitsMap` restages `FetchPtr`
   to rect window `RcW1=$C7` and never restores (`.NoHit` = `clc/rts`;
   hit path `jmp HotOverlapFlag` restages to RoomRects — also not the record).
   `UE_Tentacle` doesn't restage after `jsr PlayerHitsMap`, so the NEXT live
   enemy in `UE_Loop` reads type from rect-cache garbage.
   **Dormant today**: level scan shows tentacle is always last/only enemy in
   its room (level_002 room 1 = [bat(type0), tentacle(3)] — tentacle slot 1
   last; next iteration = `UE_Exit`). Flag only; fix deferred (needs the same
   scarce main-space budget). E4 moth restages before exit → adds no instances.

3. **Level data already contains a moth**: level_001 room 0, type 4,
   x=34.0, y=5.0, dir=-1 (editor enum == kernel enum: 0 bat, 1 spider,
   2 snake, 3 tentacle, 4 moth, 5 lamp). Currently renders static.
   E4 = make it move. **No editor changes needed** (record already carries
   x/y/range_min/range_max/dir; we use spawn±48 constants like snake).

4. **EnemyRamP writer audit (E4 checklist item) — DONE**: seed in
   `LoadEnemyRAM` (`#$F0`), single `inc` in `RefreshEnemyY`. No other writers.
   Stateless reads safe.

## Bank0 space (the hard constraint)

Measured from `bank0.lst`:

- Main code ends **exactly** at pin `.ds $FC49 - *, 0` (MothExitPad $FC49-$FC4E,
  `.REYDone` rts at $FC48) → **0 B slack**. Any main growth = loud
  `Origin Reverse-indexed` build error.
- Only free code space: gap **$FC4F-$FC67 = 25 B** (between exit pad and
  `org $FC68` ToMenuStub fold pad, which is bank1-synced and cannot move).
- Post-pad ($FC70-$FEF0): contiguous full (UE_FlipDir, ClearPFColumn,
  UpdateJetSound, AddScore, ReloadLevel, HotOverlapFlag, LoseLifeHot,
  IsRoomDark/SetRoomDark, CheckBandTouch/LoseLife, BuildColupF,
  UpdateBombSound, ObjSprites $FEA5-$FEED, UE_MothTramp $FEF0).
- $FF00 fineAdjust, $FF10 SetObjectXPos, $FF20-$FFF1 laser/SetObjReflection,
  $FFF2-$FFF9 fill (F6 mirror zone), $FFFA vectors. Full.

### Space solution

- **Y arm leaf `MothYDerive` in the 25 B gap — 25 B EXACT:**

```
MothYDerive:            ; in: Y=record+0, X=slot preserved; out: A=live Y
    lda EnemyRamP       ; 2
    lsr                 ; 1   ÷2: phase advances once per moth tick
    and #15             ; 2   p = 0..15
    cmp #8              ; 2
    bcc .mUp            ; 2
    eor #15             ; 2   mirror: tri = p<8 ? p : 15-p  (0..7)
.mUp:
    cmp #7              ; 2
    bcc .mOk            ; 2
    lda #6              ; 2   clamp tri ≤ 6 → delta exact ±6
.mOk:
    asl                 ; 1   0..12  (C=0 guaranteed, bit7 clear)
    adc #$FA            ; 2   ×2−6 → delta −6..+6 (C=0 → A-6 mod 256)
    jmp DEYDelta        ; 3   shared tail: sta Temp/iny iny/fold/clc/adc/rts
                        ; = 25 B — exact fit; 26 B trips org $FC68 reverse-index
```

  Continuous at phase wrap (p15→−6 → p0→−6). Period 16 divides the 256 clock
  exactly (spider lesson — no teleport). Y untouched → `.DEYDelta`'s
  `iny iny` still reads record+2 (spawn y). X untouched (caller needs it).
  Stack: jumps only, `rts` pops DeriveEnemyY's caller return — stack depth
  unchanged.

- **Dispatch in DeriveEnemyY (main, +7 B):**

```
    cmp #ENEMY_MOTH
    bne .DEYStatic
    jmp MothYDerive
.DEYStatic:              ; (static fallthrough gets a label)
    iny iny / jsr FoldIndirect / rts
```

  `beq` can't reach the gap (~1330 B away) → cmp+bne+jmp = 7 B.

- **Free 7+ B in main via 2 surgical refactors (no snake/StartFrame surgery):**
  - `LoadEnemyRAM`: X×6 sequence `txa/asl/sta Temp/asl/clc/adc Temp/tay`
    (9 B) → `ldy EnemyOffTable,X` (3 B) = **−6 B**. Same pattern UE_Loop
    already uses. Also drops a `Temp` write (strictly safer vs bank1's
    score-init Temp flag). Verify no caller reads Temp after LoadEnemyRAM.
  - `RefreshEnemyY`: forward loop (`ldx #0/cpx/bcs/.../inx/jmp`, 20 B) →
    countdown (`ldx EnemyCount/beq/dex/[jsr/sta/dex/bpl]/rts`, ~16 B)
    = **−3/−4 B**. Derive order becomes n-1→0 — harmless (Y derivations
    independent, all readers run after refresh completes).
  - Margin: −10 freed vs −7 needed ≈ 3 B spare. Pin gate catches shortfall.
- **Rename `.DEYDelta` → global `DEYDelta`**: DASM local labels bind to the
  previous global label — the gap leaf cannot jmp a DeriveEnemyY-scoped local.
  Token rename only, zero bytes.

## Bank2 MothRoutine (X handler, ~150 B — bank2 has ~3.5 KB free)

Entry contract (existing, verified): tramp `UE_MothTramp` $FEF0
(`sta $1FF8`/`jmp`) → bank2 `$F100`; X = slot, Y = EnemyOffTable,X = X*6
record offset (survives FoldIndirect), FetchPtr = record base (staged at
`UE_Start`). Exit: `jmp MothExitPad` $FC49 (`sta $1FF6` byte-identical slice
→ fetch $FC4C from bank0 = `jmp UE_Next`). 0 push both ways (stack guard).

Algorithm:

1. **Gate**: `lda EnemyRamP / and #1 / bne out` — 1 px / 2 frames; phase
   `(P>>1)&15` advances exactly once per moving tick (spec "phase ++ per
   moth tick"). (Free-running clock — not TickCounter, per E-gate decision.)
2. **Live dir**: bank2-local `MothBitTable .byte $01,$02,$04` (bank0's
   `EnemyBitTable` unreadable from bank2) + `and EnemyRamD / bne .right`
   (EnemyRamD = RAM ✓; eor with own bit for flip — b0-2 only, RoomDarkMask
   b4-7 untouched ✓).
3. **Step** ±1 into `Temp` (free in overscan: all Temp consumers run before
   `UpdateEnemies`; snake re-writes its own Temp later ✓).
4. **Range check** spawn±48, signed/mod-256 safe (spawn px may be <48):
   `candidate − spawn` → `cmp #49 / bcc ok` (0..48) / `cmp #208 / bcc turn`
   (49..207 = out) / else ok (208..255 = −48..−1). Out → **hold (no commit)
   + flip** (clamping to live = the bound, since step is ±1).
5. **Wall probe** — bank2-local copy of PHM's ZP rect walk (**deviation from
   plan's "swap+PlayerHitsMap"**: bank2 must NEVER jsr bank0; plan E3 already
   named this fallback `EnemyProbe`). Details:
   - rows: live Y (sine already applied this frame — refresh ran first):
     top = Y>>4, bottom = (Y+7)>>4 via 4×`lsr` (no bank0 `YToRowTable` —
     floor(floor(Y/4)/4) = floor(Y/16) exact).
   - cols: `Temp>>2 .. (Temp+7)>>2`, mirror ≥20 → 39−c (CEH raw-X convention;
     ±1 px vs resp0 accepted — plan's documented coarse-probe approximation).
   - inputs into shared scratch `CollisionCellY/EndY/CellX/EndX` — write-
     before-read, PHM (StepDown) already ran this frame; CEH rewrites later.
   - walk: `RcBase` count, windows `RcW1=$C7`/`RcW2=$D3` via FetchPtr,
     rect4 fixed addrs ($89/$8A/$DE/$DF), exit-Y normalization
     (`.nrmCol`/`.nrmRow` discipline verbatim — P3.4 drift lesson).
   - bomb mask: dup `MothMaskBit .byte $08,$10,$20,$40` + read `BombPacked`
     (ZP) — destroyed rects passable for moth (parity with player).
   - HIT → `sec` (NO `jmp HotOverlapFlag` — bank0; moth doesn't need hot flag).
6. **Turn** on wall: `lda MothBitTable,X / eor EnemyRamD / sta EnemyRamD`
   + hold. **Commit** on clear: slot saved in `EnemyIndex` around the walk
   (`tax` conflict, E3 lesson) → `lda Temp / sta EnemyRamX,X`.
7. **Restage FetchPtr** (`EnemyDataLo/Hi`) on ALL exit paths — next UE_Loop
   iteration's type fold needs the record base (no new FetchPtr bugs).
8. `jmp MothExitPad`.

Register discipline: X preserved (slot; saved in EnemyIndex around walk),
Y clobberable (UE_Next re-establishes via EnemyOffTable), FetchPtr restaged,
Temp owns candidate, CollisionX = spawn (read after step; LaserInput's use
is finished this frame).

Cycle budget: walk ≤4 rects ≈ 400 c worst, ÷2 gated. Overscan TIM64T window
has ~1096 c headroom (current worst 2104 c); tentacle probe (÷4 + column
cull) may coincide — worst ≈ +450 c → still under. **Measure at Stage D.**

## Execution stages (build-test-build, user gate per stage)

| Stage | Change | Verify |
|---|---|---|
| 0 | Baseline `./build.sh` + `tools/test_enemy_movement.py` green | record baseline |
| A | Main frees: LoadEnemyRAM `ldy EnemyOffTable,X` + RefreshEnemyY countdown | tests unchanged green; build pin gate |
| B | `MothYDerive` leaf in gap + dispatch `cmp/bne/jmp` + rename `DEYDelta` | `org $FC68` fit gate; test asserts; **user Stella: moth bobs ±6 px, laser kills track bob Y, 262-line frames** |
| C | Full bank2 MothRoutine (gate/range/probe/flip/restage) | test asserts (no bank0 jsr, restage present, exit pad intact); **user gate E4: patrols 6 tiles each way, turns at wall AND range, visible ±6 wave, CEH/laser both axes, no roll** |
| D | Cycle measure (player+tentacle+moth worst frame vs TIM64T), update `docs/enemy_movement_plan.md` checkboxes, note deviations | tests green, no 263-line frames |
| — | Then E5 full regression (separate plan section) | user full Stella pass |

## Risks

- **25 B-exact gap fit** — 1 B over = `Origin Reverse-indexed` at `org $FC68`
  (loud, safe). If it trips: drop `lsr` (phase ÷1, 24 B — spec deviation,
  needs user OK) or reclaim 1 B elsewhere.
- **Main frees under-deliver** — `.ds $FC49` pin errors loudly (safe).
- **RefreshEnemyY loop order change** — covered by existing Y-derive tests.
- **Walk-copy divergence from PHM** — port normalize discipline verbatim;
  add test asserts on the bank2 copy's structure.
- **rect4 alias ($89/$8A = MapPtrLo/Hi cache) staleness during overscan** —
  verify who writes MapPtr after EnterRoom; PHM reads same cache earlier in
  the frame (works) — confirm no writer between PHM and UpdateEnemies.
- **Latent tentacle FetchPtr bug** — dormant (tentacle always last slot);
  documented here; optional fix = +12 B restage after probe (needs main frees).
