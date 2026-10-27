# HERO reference

_Activision HERO patterns we follow, differences from HERO, and the HERO power-bar analysis._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

## HERO Architecture Reference

### Key Patterns to Follow

1. **Reflected Playfield**: CTRLPF D0=1 — left half mirrors to right.
   Cave design is symmetric about center seam.

2. **PF Persistence**: Write PF0/PF1/PF2 ONCE per tile row. TIA persists
   values across all 12 scanlines of that row. Saves 36 cycles/scanline.

3. **Fixed-Time Kernel**: Same instruction stream every scanline. No
   conditional branches that change cycle count. Sprite data from
   pre-computed buffers. PF data from lookup tables.

4. **Horizontal Positioning**: RESP0 for coarse (every 15 color clocks),
   HMP0 for fine (-8 to +7). HMOVE applied during HBLANK.

   **CRITICAL: SetObjectXPos must match the comparison branch EXACTLY.**
   A `jmp .Div15Loop` before the div15 loop added 3 cycles (1 pixel) to
   RESP0 timing, causing collision misalignment. This took 2 days to find.
   NEVER add timing-changing instructions to SetObjectXPos without
   verifying pixel-perfect alignment with the comparison branch.

5. **CRITICAL: ZP Address Conflicts Between Banks** — All banks share the
   same 128 bytes of zero-page RAM ($80-$FF). Writing to a ZP address in
   one bank corrupts the value for ALL banks. Before defining new ZP
   variables in any bank, ALWAYS check that the addresses don't conflict
   with variables used by other banks. The ZP map in kernel.asm shows
   bank0's usage; bank1 must use addresses that don't overlap. Known
   safe unused ranges: check kernel.asm ZP allocation before adding new
   variables. Example: $E0-$EB was used by bank0's level data pointers,
   causing crashes when bank1 wrote digit pointers there.

 6. **CRITICAL: ZP Stack Collision ($F8-$FF)** — The2600's128-byte RAM
   mirrors at $0100-$01FF (stack page). The stack pointer starts at $FF
   and grows downward. Any ZP buffer at $F8-$FF shares
   physical RAM with the stack. **JSR pushes return addresses to $FF-$FE,
   overwriting data at those ZP addresses.** If you copy data to a ZP
   buffer and then call JSR, the return address overwrites the buffer.
   Rule: do NOT put buffers at $F8-$FF at all — the stack owns it.
   (Historical: the old PlayerGrp0 buffer sat there and JSRs overwrote
   sprite rows 6-7; removed 2026-09-24 — kernel now reads ROM via
   `Grp0Ptr` with no ZP copy.)
   **The real boundary is the MEASURED deepest SP, not $F8** (2026-09-28):
   nested jsr chains (frame → StepDown → PlayerHitsMap → rect-walk →
   FoldIndirect = 5 levels) drive SP down to **$F6**, stomping $F6/$F7.
   Any new jsr level in a deep path moves the line down by 2 bytes.
   Guard (build gate, `sim_bomb_fuse.py` via `build.sh`): gameplay min
   SP ≥ $F8, whole-run ≥ $F7 (a push writes AT SP then decrements — SP $F7
   = lowest byte written $F8 = boundary kept; SP $F6 = $F7 stomped).
   Never assume "$F6 is free" — check the measured depth first.

7. **Incremental Development** — When making big changes, ALWAYS divide
   the work into small steps and test after each one. Each step should
   add only one piece of functionality. This makes it much easier to
   catch and fix issues early, before the full code is in place. If a
   step breaks something, you know exactly which change caused it.
   Example: building the 48px score renderer required 10+ incremental
   steps (registers → color → positioning → pointers → render loop)
   rather than writing the whole thing at once.
7. **Build-Test-Build** — When implementing a feature, write the plan
   as small, testable pieces. After EACH piece, ask the user to test
   in Stella before moving to the next piece. Do NOT implement the
   entire feature at once — a bug buried in 500 lines is 10x harder
   to find than a bug in 20 lines. Pattern: implement → build → user
   tests → fix if needed → next piece. This is MANDATORY for any
   feature touching the kernel, movement, collision, or room system.

5. **Vertical Positioning**: Kernel scanline counter matches player Y.
   Sprite rendered when scanline falls within player's 8-line range.

6. **Collision**: TIA hardware collision registers (CXP0FB, CXPPMM, etc.)
   checked in VBLANK/Overscan after frame renders.

### Hero's Cave Structure

```
Row 0-3:   ####....................................####   (thick walls)
Row 4-7:   ##..........................................##   (thin walls)
Row 8-11:  ###################....#####################   (bottom passage)
```

The cave is 20 logical columns wide. With reflection, each half mirrors.
PF0/PF1/PF2 define the left half; TIA mirrors the right.

### Playfield Register Layout (Left Half)

| Register | Bits    | Pixels (color clocks) |
|----------|---------|----------------------|
| PF0      | 7-4     | 0-3 (leftmost)       |
| PF1      | 7-0     | 4-11                 |
| PF2      | 0-7     | 12-19 (reversed)     |

## Differences from HERO

| Feature | HERO | This kernel |
|---------|------|-------------|
| ROM size | 8K (F8 bankswitch) | 16K (F6 bankswitch) |
| PF writes | Per-scanline (ROM tables) | Per-band (4 × 36 lines, written once in `.Row`) |
| Sprite data | `(zp),Y` from ROM | `(zp),Y` from ROM (`(Grp0Ptr),Y`, frame picked in VBLANK) |
| VDEL | Used for sprite pipeline | Used by bank1 score (48px technique); cave kernel no |
| Enemies | Yes (miner + enemies) | Yes — moth/spider/tentacle/bat/snake/lamp + miner |
| Rooms | Multiple connected rooms | Yes — multi-room levels, exit handlers + connections |
| HUD | Score/lives/time text | Yes — bank1 band via fold pad (score/lives/bombs/bar) |
| Jetpack | Physics with gravity | Yes — gravity/thrust/inertia (vyLo/vyHi/JetPower) |


### HERO Power Bar Analysis (2026-09-22)

Verified against `docs/hero/hero_bank0.asm` + screenshots `screenshots/hero_001.png`..`hero_007.png`
(bar region x=242..702, y=444..464).

**Visual behavior (measured from screenshots):**
- Single continuous bar, NOT mirrored/symmetric. Yellow (remaining) left,
  red (consumed) right. Red grows right→left as time depletes.
- Orange single-pixel separator at the yellow/red boundary (ball sprite).
- Margins at screen edges (grey background outside the bar).
- Bar height: 3 scanlines (HERO's setup loop runs 3 iterations: X=8→4→0, DEX×4).
- Full→empty progression: hero_001 (100% yellow, 0 red) → hero_007 (3% yellow, 440px red).

**HERO's CTRLPF writes (decoded from raw bytes in hero_bank0.asm):**
- `LDA #$34 / STA CTRLPF` before bar: %00110100 = reflect OFF (D0=0),
  priority ON (D2=1), ball 8 clocks (D4-D5=%11).
- `LDA #$30 / STA CTRLPF` after bar: %00110000 = reflect OFF, priority OFF,
  ball 8 clocks.
- Hero enables ball during bar: `LDA #$90 / STA ENABL` (ball ON) +
  `STA HMM0` (missile/ball horizontal motion).

**Bar setup loop (3 scanlines):**
- `LDA #$D0 / LDX #$08 / SEC`, then per iteration: WSYNC, store A to $87,X,
  SBC #8, store A to $85,X, SBC #8, DEX×4, BPL. Produces values
  $D0,$C8,$C0,$B8,$B0,$A8 in ZP $85-$8F — cycle-count data for the
  mid-scanline COLUPF change (early shutoff technique).

**Color bytes for our bar (kPalette, `(hue<<4)|(luma<<1)`):**
- Yellow: hue 1 luma 6 = **$1C** → RGB(232,232,92) ≈ screenshot (224,224,80).
- Red: hue 4 luma 2 = **$44** → RGB(176,60,60) ≈ screenshot (176,48,48).
- Existing HUD greys/greens unchanged: lives=$C6, bombs=$46, grey BG=$06.

**Our implementation plan (HERO Method 2: playfield + ball):**
- Reflect mode CTRLPF=$05 + PF0=$E0 (bit4 OFF) gives margins at both screen edges.
- PF1=$FF, PF2=$FF for solid bar body.
- Mid-scanline `STA COLUPF` from yellow→red at BarLevel-derived cycle delay.
- Ball (ENABL) at boundary for sub-block smooth edge (step 2).
- BarLevel 0-16, TickCounter max 255 (single byte) ≈ 68 s total (approximation accepted).

**Full plan: `docs/power_bar_plan.md`**

### Power bar: H3c dual-path + H3d yellow-line fix (2026-09-23)

**Architecture (bank1 MenuMain):**
- Setup (PF shape, grey `COLUPF=$06`, GRP0/NUSIZ0, `CTRLPF=$05`) runs **before**
  TopGap — grey-on-grey over the 4 gap lines, so no visible line above the bar.
- After ball `SetObjectXPos` + `sta WSYNC` / `sta HMOVE`: only `lda #1 / sta ENABL`
  + `ldy BarLevel / cpy #BAR_MAX` + path dispatch. **HMOVE-line content ≤51c**
  (must stay ≤76 or the next bar line is skipped → doubled yellow + HUD shift).
- Yellow `COLUPF=$1C` is written **only** on the 3 bar lines. Gap/`BarGap` uses grey.
- Dispatch: `bne .BarRedSetup`; F=0 falls into `.BarRedF0`; `beq .BarRedF1` for F=1;
  `jmp .BarRedFull` for F=2,3,4 (avoid `bne .BarRedFull` page-cross F5→F6).
- Tables: `BarDelayTable` / `BarFineTable` / `BallXTable` (121 entries, B=0..120).
  Fine ∈ {0,1,2,3,4}; BallX = actual body pixel `3*cycles-69` per path.
  **Always regenerate tables from path cycle counts in a script** — hand transcription
  caused 9 mismatches once.

**H3d roots:** (1) yellow `COLUPF`+PF on the HMOVE line = permanent 1px yellow
above bar; (2) red-path setup on that line ≥78c = skipped line = thickness doubles
and HUD rows push down. Fix = move setup before TopGap; keep HMOVE line short.

**Future (user):** smaller px/step + more steps/s (plan **H4**) — redesign tables
under the same ≤73c path budget before changing the tick.
