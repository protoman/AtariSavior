# Bank0 space plan v2 — verified (2026-10-16)

Supersedes the sequencing in `bank0_space_plan.md`. This one is built from the
**verified** F6 mechanics, not assumptions. Written after three dead-ends
(bank2 SOXP fragmentation, bank1 title move, "just move a chunk").

## Verified constraints (evidence in the codebase)

1. **F6 select = `sta $1FFx`; the NEXT instruction fetch comes from the new
   bank at the same PC.** Same-address **byte-identical twins** are required at
   every post-switch fetch point (fold pads `$FC68/$FC70`, `ReturnPad $FBF8`,
   CallPads `$FBFC-$FC47`, `Bank2ReturnPad $FBEE`, tramp pads).
2. **Cross-bank CALLS work only "downstream":** the callee's `rts` is fetched
   from the *caller's* bank (the `ReturnPad` twin does `sta caller-bank; rts`).
   ⇒ bank0→bank1/2/3 OK (CallPads / folds); **bank1/2/3→bank0 does not exist** —
   verified: **0** `jsr <bank0-only label>` in bank1/bank2/bank3. This is *why*
   moved helpers are all self-contained and everything coupled stays in bank0.
3. **Data is read by its owning bank** (`abs,X/Y`). bank0 cannot read bank1/2/3
   data — a moved table needs its reader moved too, or a fold.
4. **`.ds $X` pins** fix the twin addresses. Removing content *before* a pin
   frees nothing (the fill grows). Freeing = remove content **and shift the
   downstream pins** in every bank.
5. **Free space (2026-10-16):** bank0 ~0; bank1 `$F025-$F53F` 1307B + `$FDE3-$FEFF`
   285B; bank2 fragmented ≤41B; bank3 `$F0A1-$F7FF` 1887B + `$FECC-$FFF9` 302B.
6. **Twin coupling:** the title machinery, the kernel, PHM, SelectActiveObject
   and the HUD all read bank0/bank2 same-address twins (`$F8DD`, `$FDE7`,
   `$FE00`, `$FE48`).

## Path 2 — the bank1→bank0 call gate (the missing primitive)

Verified-sound trampoline (push-a-return-shim); needs NO new ZP byte:

```
; --- bank1 ---
Call_b0:                     ; X = any; clobbers A. Pushes a bank0 shim so the
    lda #>ShamB0             ;   callee's rts returns INTO bank0, then jumps to
    pha                      ;   Target by using rts as an indirect jump.
    lda #<ShamB0
    pha                      ; stack: [caller R1] , ShamB0
    lda #>Target
    pha
    lda #<Target
    pha                      ; stack: [caller R1] , ShamB0 , Target
    sta $1FF6                ; select bank0 ("jmp (Target)" via rts)
    rts                      ; pops Target -> enters Target, bank0
; --- bank0 AND bank1, byte-identical, at ShamB0 ---
ShamB0:
    sta $1FF7                ; select bank1 (the caller's bank)
    rts                      ; fetched bank1-side -> returns to Call_b0's jsr
```
Flow: bank1 `jsr Call_b0` → pushes Target+ShamB0 → bank0 `Target` runs → its
`rts` pops ShamB0 (bank0) → `sta $1FF7` + bank1-side `rts` → back in bank1. ✔

**Twin requirements (bank0 + bank1, same address):**
- the `rts` that ends `Call_b0` (1 byte — bank0 side of the gate tail), and
- `ShamB0` = `sta $1FF7 ; rts` (4 bytes).
⇒ ~5 bytes of bank0+bank1 twin space. bank0 has none today → take it from the
**pre-pad/main is full**, so first carve the bank0 **tail** (`MothYDerive`,
~25B) or reclaim via the first pin shift. (Chicken-and-egg: the gate needs ~5B;
the tail gives it.)

**One gate serves all callees** (`Target` is pushed by the caller, so the gate
is generic) — this is the whole point: it unlocks moving ANY coupled bank0
routine to bank1.

## Path 3 — bank2 compaction (for the title kernel)

The title kernel's only valid homes are bank0/bank2 (twin coupling), and bank2's
free space is fragmented (≤41B). To open a ~200B bank2 run: relocate bank2's
**level data** (`LevelDataTable` + spill slices, ~1.5K) to **bank3** (data-only,
user's target). Caveats (verified needed):
- bank2's `EnterRoomB2` reads the level data **directly** (`(FetchPtr),Y`); if
  the data moves to bank3, EnterRoomB2 must move to bank3 too (or read via a
  fold). Since bank2 calls its own routines freely, **move `EnterRoomB2` +
  dependent readers to bank3 with the data** is the clean form.
- bank0's `LoadLevel` reads level pointers too — check each reader.

This is a second subsystem move; do it AFTER path 2 is proven (path 2's gate is
what lets bank3↔bank0 pieces talk).

## Target layout

| bank | role |
|---|---|
| bank0 | main game code + cave kernel (minimized) |
| bank1 | HUD + title + relocated bank0 routines (via the gate) |
| bank2 | fold bodies/helpers + whatever data/twins must stay same-address |
| bank3 | data-first: level data + relocated data-driven code |

## Feasibility ranking of movable bank0 content (honest)

- **Easy (self-contained, no bank0 callees, data stays):** `SetObjReflection`,
  `PositionBallM1`, small helpers. Individually tiny.
- **Needs the gate (coupled):** `DeriveEnemyY`/`UpdateEnemies`, `CheckMinerPickup`,
  `ExitRoom*`, `LoseLife*`, `DropArm`/`DropStep`, `PlayerHitsMap`, `LaserInput`,
  the title helpers. These are the bulk (~330B event routines).
- **Needs gate + data move:** `SelectActiveObject` (reads ObjColorTab/ObjSprites),
  `PlayerHitsMap` (reads YToRowTable/ColOff/ColMask).
- **Immovable:** the cave kernel (reads ObjSprites/PlayerColTable per-scanline),
  the title kernel (twin-coupled to bank2), the HUD (bank1 already).

## Staged execution (each step: build + battery + Stella, no step left red)

0. **Carve the gate twins.** Move `MothYDerive` (bank0 tail, 25B) into bank1 via
   a CallPad (`DeriveEnemyY` → `jsr CallPad_MothYDerive`); its tail-jmp to
   `DEYDelta` becomes a bank1→bank0 jump through the new gate. This also frees
   25B at bank0's END (real headroom, no pin shift needed yet) — and 25B >
   Phase 8's ~20B, so **Phase 8 unblocks here even if we stop**.
1. **Prove the gate** with that single move (`test_enemy_movement`, sim).
2. **Batch — event routines → bank1** (gate + CallPads for bank0 callers).
3. **Data-coupled** (`SelectActiveObject`, `PlayerHitsMap`) — gate + their tables
   (via a fold or a move-with-reader).
4. **ONE pin shift** of `$FB00…$FC49` down by the total removed → the big win.
5. **Path 3**: level data + EnterRoomB2 → bank3 (frees a bank2 run → title kernel
   → bank2), if we still need the title out of bank0.

**Verify each step:** `./build.sh` (pins/stack/wall), the specific battery tests,
`stella` screenshot. **Never** stack a feature on a red guard.
