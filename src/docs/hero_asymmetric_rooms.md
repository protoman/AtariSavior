# HERO Asymmetric Rooms — Investigation (2026-09-30)

**Q: How can HERO's cave be asymmetric left/right when the TIA playfield is
mirrored?**

**A: HERO writes the PF registers TWICE per scanline.** Writes landing in the
first half of the line paint the LEFT playfield half; writes landing in the
second half paint the RIGHT half (the TIA re-scans PF0/PF1/PF2 for the right
half at color clock 148). The right half still mirrors the register values
(cave uses reflect), but the values at that moment are different from the left
half's — so the two halves can show different patterns, and the room is
asymmetric.

## Timing model (verified in py65 trace)

1 scanline = 76 CPU cycles = 228 color clocks (1 CPU cycle = 3 color clocks).

| Region | Color clocks | CPU phase |
|---|---|---|
| HBLANK | 0–67 | 0 – 22.7 |
| Left playfield half | 68–147 | 22.7 – 49.0 |
| Right playfield half | 148–227 | 49.3 – 75.7 |

A PF store with CPU phase ≤ ~44 lands before clock 147 → left half is
already painted with it. A PF store with phase ≥ 50 lands after clock 147 →
only the right half sees it. The row-boundary pattern we traced:

- line N, phase 70: `STA PF1` → right half of line N
- line N+1, phase 6: `STA PF0`, phase 37: `STA PF2` → left half of line N+1
- phase 44: `STA CTRLPF` = `$35` (reflect ON, priority ON)

Different values per half + reflect = asymmetric room. One write per row with
a single value set can never do this: the TIA always re-scans the same
registers for the right half (reflect only flips bit order).

## Pixel-level proof

`screenshots/HERO.png` (894×594, visible x7–891, scale 5.525 px per TIA-x),
platform row y=350:

- wall x7–373, gap x379–472, wall x475–891
- gap center = 425.5 vs screen center 449 → off-center
- left portion of the gap ≈ 3 PF pixels, right portion ≈ 1 PF pixel

A single value set + reflect gives equal portions on both sides of center —
rejected. Two different half values + mirror gives 3 px left / 1 px right —
matches.

## Trace structure (gameplay frame, relative lines from VSYNC)

- 0–43: VBLANK
- 44–49: prep (RESP1 line 45, NUSIZ1, CTRLPF=$35 at line 44/61)
- 50–53: PF row setup (COLUPF 2A/28/26/24 vertical gradient, PF0 00/60/F0/F0)
- 54–175: cave band; PF row cadence ≈ 39–40 lines (HERO's tile rows are
  giant, ~39 TIA lines tall — matches screenshot block sizes); row boundaries
  at 54/55, 93/94, 132/133 with the late/early PF pattern above
- 172–175: floor (PF0=FF, PF1=FF, PF2=3F)
- 176–235: HUD band; CTRLPF switches to `$30`/`$34` (reflect OFF) at lines
  176/184/223; true mid-line double PF writes (e.g. line 179–183: PF1@6,
  PF2@30 left; PF0@45, PF1@51, PF2@56, PF0@59 right; COLUPF@64) + text
  rendering (13+2, `JSR $DC00` HUD renderer, NUSIZ/RESP/GRP activity)

## Code/ROM references

- `hero.bin` model: **flat 8K, both halves visible simultaneously** —
  `ROM[0:4096]` = `$D000-$DFFF` (kernel, "bank A"), `ROM[4096:8192]` =
  `$F000-$FFFF` (logic, "bank B"); reset vector `$FFFC → $F000`. Kernel code
  at `$D079` (main) executes fine under this model. AGENTS's "HERO = F8
  bankswitch" claim is NOT verified from this dump — treat with caution.
- Bank A landmarks: `$D079` main, `$D100` kernel entry, `$D12C` row loop
  (X counter), `$D17A` line loop, `$D6F2/D717` VSYNC+TIM64T, `$D9DF` frame
  end (`JMP $DFF2` → bank B thunk).
- CTRLPF: cave `$35`, HUD `$30`/`$34`.
- Code: `docs/hero/hero_bank0.asm` (DiStella of first half — kernel region
  is MISPARSED as data after `$D02A`, do not trust), `docs/hero/hero_bank1.asm`
  (second half — logic source), `/tmp/opencode/hero_bankA_flow.asm` (linear
  sweep disassembly, 1440 instructions, covers observed execution paths).

## Trace harness (reproducible)

py65, `/tmp/opencode/trace2.py` pattern:

- cycle count = `mpu.processorCycles` delta per `step()`
- `WSYNC` write (`$0002`) aligns virtual clock `v` up to next multiple of 76
  (py65 has no halt)
- `TIM64T` write sets `tim_dead = v + v*64`; `INTIM` read returns
  `(tim_dead - v) / 64` — without both, write positions are garbage
- frame = VSYNC (`$0000` bit2) rising edges; measured frame = 19988 cycles ≈
  262×76 = 19912 ✓
- per-line dump classifies each write as left/right by phase×3 vs clock 147/148

## Consequence for our kernel

We write PF once per tile row → both halves always equal (symmetric, by
design for our mirrored cave). If we ever want asymmetric rooms, one write
per row cannot work: we must write PF between the two half-scans (early =
left, late = right), exactly HERO's method — and budget the extra cycles
per line. Reflect stays ON for the right-half order flip if we keep mirrored
bit ordering.
