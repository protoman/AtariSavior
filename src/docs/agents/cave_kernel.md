# The gameplay cave kernel (bank6, generated)

_Since 1.0.3 development (2026-11). Replaces the bank0 `.Row`/`.Line` kernel for every
gameplay frame; the title still runs the old bank0 kernel for its band 0 (+ bank1's
`TitleBand`). Design record: `plans/hero_style_kernel_plan.md`, progress log
`plans/hero_style_kernel_progress.md`._

## Why
The old kernel spent two scanlines at every band change (PF stores, then PF2/slot-1 tail +
WSYNC) with no sprite fetch, so a sprite crossing a band repeated its previous row on both
(probe: `tools/probe_setup_sprite.py`: 84 of 160 positions). Fitting the fetch in needed the
body to shrink from 64c worst case: HERO's trick (read from `hero/hero.bin`) is a branch-free
fetch from zero-padded tables.

## Shape
* Entry: bank0 VBL tail, `GoKernel6: sta $1FFA` (title branches around it). The byte after
  the `sta` is `jmp Kernel6Entry` in bank6 (address from `generated/bank6_equs.inc`).
* `bank6_prologue.inc` (hand written, VBL time): player frame from `Grp0Ptr`, the two GRP1
  objects from `ObjBase/ObjTop/ObjBase1/ObjTop1/ObjX1`, door, water, then the generated
  core (`cave_prologue.inc`): pointers for the first segment, `NextS*`, `E0/EC`.
* `generated/cave_kernel.inc`: ONE band code run four times (X = band index in the special
  lines). 36 lines per band, no dead lines. Frame stays 272 lines (`CAVE_DEAD_LINES` waits
  before the kernel, VBLANK on).
* Exit: after the last band the kernel falls into `KernelExit` (clears ENABL/ENAM1, padding
  so MenuMain's first PF store keeps landing at cycle 47) and `jmp $FC68` (HUD fold pad, the
  bytes live in table page $FC).

## Line template (cycles from the line start)
```
c5   lda (C0),Y  sta COLUP0  and LaserState  sta ENAM0       colour/beam of THIS line
c19  lda (G0),Y  sta GRP0                                    gfx row for the NEXT line
c27..c50  23-cycle window: playfield stores, segment update, next-segment arithmetic
c50  lda (G1),Y  sta GRP1 (write c57; latches P0 via VDELP0)
c58  beq: gfx == 0 -> COLUP1 = BandCol (the M1/door strip shares COLUP1), else (C1),Y; 13c
c71  iny   c73 sta WSYNC          (start <= 73: the project's stall contract)
```
Loop lines prelude `dex/bne` (5c). Lines after a loop start at c4 (shift -1). Every line is
a `Timeline` in `tools/cave_kernel_gen.py`: each store sits at an asserted cycle.

## Sprite fetch
Shared `Y` = line counter inside a 36-line segment; pointers G0/C0 (player gfx/colour) and
G1/C1 (object gfx/colour): HI = per-frame page, LO = start offset S, rewritten at line 2 of
every band (`ldy #0`). `S = ((K - e) & mask)`, `e = top + (H-1) - u`, in range iff
`e < 36 + late + H`; out of range -> S = 0 (page start = 37 zero bytes). Pages are padded with
`PAD = 37` zeros between blocks (reads span y = 0..36 because the P0 fetch on the update line
still uses the old pointer). Colour of row r is read at the gfx index of row r+1 (table shift).

## Tables / memory map (bank6)
| range | content |
|---|---|
| $F000 | power-up stub (mandatory in every bank) |
| ~$F005-$F0C8 | LUTs (`cave_luts.inc`), `CaveFrameLo`, fine table |
| `Kernel6Pad` | `jmp Kernel6Entry`, prologue, generated kernel, exit, slot-1 path |
| $F800-$FE00 | P1 gfx pages (12 designs, 4 per page) and P1 colour pages |
| $FC00 | player colour block, frame-3 gfx at base 112, HUD pad at $FC68 |
| $FF00 | player frames 0-2 (bases 0/60/120; reads end below index 216), vectors at $FFFA |
`tools/cave_kernel_gen.py --real generated kernel.asm` parses the art from kernel.asm.

## Second object (slot 1)
bank2 `StageSlot1` pairs two objects in different bands. P1's context (pointer pages, K, e)
exists twice (arrays at $F8-$FF indexed by ctx = Band >= Slot1Band). The update line's pad is
the hook (`cpx Slot1Band / beq S1Stub`): partial line (no fetch) + variable positioning line
(RESP1 at the same cycle SetObjectXPos strobes: 5N+15) + HMOVE line (does the update, `ldy #2`).
Cost: two stale sprite lines in that band (the old kernel lost two as well).

## Zero page
Kernel-local bytes are free while the cave runs (VBL/overscan scratch, bank1-only HUD bytes
$E0-$EF, the EnemyRamY window, and the stack bytes $F8-$FF: bank6 never calls). Map and
contract: `tools/cave_kernel_gen.py KERNEL_ZP/LIVE`, guarded by `tools/test_cave_zp.py`.

## Tests
`tools/test_cave_kernel.py` (real ROM + real art: player rows for every frame across all band
changes, all 12 object designs, slot 1, WSYNC <= c75, water strip at 132+tide),
`tools/test_cave_zp.py`, `tools/probe_setup_sprite.py` (repeat-row counter),
`tools/proto/` (the standalone prototypes v1-v3, history).
