# Kernel and ROM architecture

_ROM layout, F4 banks, frame timing, zero-page map rules, TIA notes, the cave kernel and its cycle budget._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

## Overview

A from-scratch Atari 2600 game kernel modeled after Activision's HERO (1984). Built
in `src/` as a standalone project with no dependencies on the older prototype.

## ROM Layout

- **32K ROM** — F4 bankswitch (8 banks × 4K each)
- Bank0: `kernel.asm` — main game code, cave kernel, player logic
- Bank1-3: stubs (switch to bank0, ready for future expansion)
- Output: `savior.bin` (32K)

**Standing rule (2026-10-14): do NOT add new data or features to bank0.**
Bank0 pre-pad headroom is ~1 byte (build warning `ends $FC67, limit $FC68`)
and the fold pads are pinned — every addition forces a reshuffle or a cut.
New ROM content goes to bank2's table slots ($F307/$F453/$F8B7/$F9D9/$FCB8/
$FF59/$FE9C/$F700, `_SPILL_SLOTS`) or bank3's free tail; a smaller leaf helper
can also go after bank0's pads. If a change seems to need bank0 space, move a
leaf helper after
the pads or into bank2 first; only touch bank0 for in-place edits to existing
code. This is why we keep extracting routines out of bank0 every time it fills.

*Reinforced 2026-10-16:* bank0 is now **100% allocated AND byte-identity-frozen**
(pre-pad 1B; post-pad pinned at `$F8DD`/`$FDDA`/`$FDE1`/`$FC68`/`$FF00`).
Adding even 2 bytes breaks `verify_build`'s twin pins. A modest feature (the
Phase 8 respawn hover, ~20B) could not be added at all. **Default answer to
"needs bank0 space" is now: move a chunk OUT first.** Survey + §
"Movable chunks" in `plans/bank0_space_plan.md` (title subsystem ~390B cold →
bank2 is the prime target). Cross-bank catch: bank0 cannot read bank1/bank2
data by `abs` — moving a table requires moving its reader (or a fold) too.

### F4 Bankswitching

| Bank | Address Range | Power-up | Contents |
|------|--------------|----------|----------|
| Bank0 | $F000-$FFFF | — | Game code + cave kernel |
| Bank1 | $F000-$FFFF | — | HUD band, title, sound, fonts, raft body, bomb punch |
| Bank2 | $F000-$FFFF | — | Room half of the level data (entries, room tables, enemy records) + its walkers, moth, LWC/LHT, blast, exits, `LoadLevelB2`, 8 table slots |
| Bank7 | $F000-$FFFF | Yes | Shape half (shape blocks, row pool, shape table, extras streams) + its walkers, boot stub + reset vector |

Bank select (F4): `STA $1FF4` (bank0), `$1FF5` (bank1), `$1FF6` (bank2),
`$1FF7` (bank3), `$1FF8` (bank4), `$1FF9` (bank5), `$1FFA` (bank6),
`$1FFB` (bank7). Power-up bank is **bank7** (F4 reads the reset vector from
the LAST bank); its 5-byte stub is `lda #0 / sta $1FF4` and the fetch after
it comes from bank0, whose $F005 is `jmp GameStart` (byte-identical hand-off).
banks 4-6 are empty 4K windows (`src/bank4..6.asm`); bank7 holds the stub +
vectors. F4's hotspot-mirror zone is **$FFF4-$FFFB** — $FFF4-$FFF9 stay fill;
$FFFA/$FFFB carry the NMI vector and are never read (no interrupts).

## Frame Timing (262 scanlines @ 60Hz NTSC)

| Section    | Scanlines | Notes |
|------------|-----------|-------|
| VSYNC      | 3         | Sync pulse |
| VBLANK     | 37        | Game logic + sprite positioning |
| Kernel     | 192       | 144 cave (4 bands × 36) + 48 HUD band |
| Overscan   | 30        | Input + movement |
| **Total**  | **262**   | NTSC standard |

## Memory Map

### Zero-page ($80-$FF, 128 bytes)

**Authoritative map: `docs/zp_layout_skill.md`** (machine-checked every build
by `verify_build.check_equ_sync` — cross-bank hand-copy drift + stomp-zone
rule). Do NOT copy address tables from this file; it holds only the
load-bearing invariants:

- Sequential `byte` block runs `$80-$BB`; `$BD+` are explicit EQUs.
  **No free sequential byte** — inserting one shifts everything after it
  (bank1/bank2 hand-copied EQUs break silently without the guard).
- **Stomp-zone rule:** bank1 HUD writes `$E0-$EF` every frame; persistent
  bank0 state must live below `$E0` (exceptions: `ColupfBuf` `$E7` rebuilt
  every VBL, `EnemyRamY` `$E2` window-ordered; staged bytes like `FetchPtr`
  `$E5` OK). Violation symptom: field zeroed/changed every HUD frame.
- `$F8-$FF`: stack mirror only — never a buffer (pushes write down into it;
  measured gameplay min SP `$F9`, guard ≥`$F8`).
- `$81` RoomY, `$88` Temp, `$B5` BombPacked, `$F6/$F7` BombX/BombTimer —
  the crash-prone names referenced throughout the lessons below.

### TIA Registers (write-only at $00-$2F)

Key registers used:
- `$1B` GRP0 — Player sprite graphics
- `$1C` GRP1 — Object sprite graphics
- `$0D/$0E/$0F` PF0/PF1/PF2 — Playfield registers (persist across scanlines)
- `$08` COLUPF — Playfield color
- `$09` COLUBK — Background color

### TIA Read (active-low joystick at $0280)

- D4 = Up, D5 = Down, D6 = Left, D7 = Right (0 = pressed)

## Kernel Architecture

### Key Principle: Fixed-Time Inner Loop

The kernel's `.Line` loop must execute exactly the same number of cycles on
every scanline to avoid flicker. The2600 TV frame is 262 scanlines at 60Hz;
each scanline is 76 CPU cycles. If the loop exceeds 76 cycles on any
scanline, WSYNC stalls until the NEXT scanline, making the frame longer.

### MANDATORY: Budget scanlines BEFORE writing code

**Every `sta WSYNC` in the HUD band costs exactly 1 scanline.** The HUD band is 48 scanlines (144-191). Before writing any HUD code, write out the full scanline budget:

```
; Example budget (must sum to 48):
; Timer bar:     6 scanlines
; Gap:           1 scanline
; Lives (3):     9 scanlines (3 per icon)
; Gap:           1 scanline
; Bombs (5):    15 scanlines (3 per icon)
; Gap:           1 scanline
; Score:         5 scanlines
; Pad:           9 scanlines
; TOTAL:        48 scanlines
```

**If the budget exceeds 48, reduce BEFORE coding — not after.** The frame will crash with a grey screen if the HUD band overflows. Each icon rendered on its own scanline (for RESP positioning) costs 3 scanlines: 1 WSYNC in SetObjectXPos + 2 WSYNCs in RenderLifeIcon. Multiply by icon count and add gaps.

### MANDATORY: Keep the kernel entry WSYNC-anchored (bugs.md #29 Class C)

**Two re-anchor `sta WSYNC`s hold the picture still — never delete them, never add cycle-variable code around them:**
1. `StartFrame`: `sta WSYNC` BEFORE `lda #2 / sta VSYNC` (overscan-end tick quant → VSYNC phase-lock).
2. `.WaitVBLANK` exit: `sta WSYNC` while VBLANK is still ON, before `sta VBLANK` off (VBL tick quant → kernel-entry line-lock; blank line, invisible).

**Why:** `TIM64T` ticks every 64 cycles; the `INTIM` poll exits up to 63c late; the band-0 `.Row` setup WSYNC gap is ~75c — without the anchors the kernel start line straddles the 76c boundary and oscillates ±1 with tick phase = whole-screen jitter (62/58 two-class split, 2026-10-11). **WSYNC-count guards cannot see this family** — counts stayed constant through the whole bug. Oracle: Stella `logTrace` SCN at the first kernel WSYNC must be a SINGLE value across ≥100 frames, and the pixel detector's seam rows must form ONE signature across ≥120 frames (`tools/measure_bar_cycles.py` + `stella_shots` row-probe recipe).

**Each anchor costs +1 wall-model line** — when adding one, update `sim_frame_budget`'s 265.0 target, `test_phase3_ball`'s {264,265} set, and any comment citing the frame total in the SAME change. Full lesson: **Timer-quantization phase straddle** in Lessons Learned below.

### Structure (HERO pattern)

```
.Row (×TILE_ROWS=4): PF setup — write PF0/PF1/PF2 ONCE per 36-line band
                   (TIA registers persist — no need to rewrite per scanline)
.Line (×36):      Sprite rendering — the tight inner loop (the bottom band
                   runs 24 bodies + the 12-line .WaterRow strip)
                   Unconditional: same instruction stream every scanline
```

*(Era note: "12 tile rows × 12 scanlines" became 3 bands × 48 lines on
2026-09-28 (`LINES_PER_TILE=48`, `YToRowTable = line/48`) and 4 bands × 36
lines on 2026-10-23 (`CAVE_LINES = 144`, `YToRowTable = line/36`). Band
geometry, the 4-band PF stride (`$CC-$DF`), `BandTab` and the extra TIA x
values live in `plans/band4_plan.md`; the data format is `LEVEL_FORMAT = 7`
with one shape row per drawn band.)*

### Per-scanline cycle budget (76 max)

Our `.Line` loop worst-case:

| Section        | Cycles (off-screen) | Cycles (on-screen) |
|----------------|--------------------|--------------------|
| GRP0 check     | 16                 | 19                 |
| Loop control   | 16                 | 16                 |
| **Total**      | **32**             | **35**             |

Both well within 76-cycle limit. No flicker.

### PF Write Strategy

PF registers (PF0/PF1/PF2) are written ONCE per band in `.Row`.
The TIA persists these values across all 48 scanlines of the band.
This saves three abs-stores per scanline for the whole cave
(144 lines × 12c ≈ 1.7Kc of VBL/kernel time).
