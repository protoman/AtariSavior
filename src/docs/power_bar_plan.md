# Power Bar Implementation Plan

HERO-style timer bar: starts full yellow, red grows from right edge toward
left until bar is all red (time up). Verified against
`screenshots/hero_001.png`..`hero_007.png` (bar region x=242..702, y=444..464)
and `docs/hero/hero_bank0.asm`.

## Visual Behavior (measured)

| Screenshot | Yellow px | Red px | % Yellow | Boundary x |
|------------|-----------|--------|----------|------------|
| hero_001   | 450       | 0      | 100%     | none (full)|
| hero_002   | 443       | 13     | 97%      | 687        |
| hero_003   | 366       | 89     | 80%      | 611        |
| hero_004   | 284       | 170    | 62%      | 529        |
| hero_005   | 220       | 236    | 48%      | 465        |
| hero_006   | 167       | 287    | 37%      | 412        |
| hero_007   | 15        | 440    | 3%       | 260        |

- Single continuous bar (NOT mirrored). Yellow left, red right.
- Orange separator (ball sprite) at boundary.
- Margins at screen edges (grey background).
- Bar height: 3 scanlines.

## Technique (HERO Method 2: playfield + ball)

1. **Playfield** draws chunky bar body (4-color-clock PF blocks).
2. **Mid-scanline COLUPF change** (early shutoff): starts yellow, changes to
   red at the BarLevel-derived cycle position.
3. **Ball sprite** at boundary for sub-block precision (step 2).
4. **Reflect mode** (CTRLPF=$05) + PF0=$70 (bit 4 OFF) gives margins at both
   screen edges.

## Colors (kPalette, `(hue<<4)|(luma<<1)`)

- Yellow: hue 1 luma 6 = **$1C** → RGB(232,232,92)
- Red: hue 4 luma 2 = **$44** → RGB(176,60,60)
- Grey margin: $06 (existing COLUBK)

---

## Steps

### Step 1: Playfield-only two-color bar (no ball)

- [x] **1a.** Replace timer bar section in `src/bank1.asm` (lines 96-148):
      remove player-sprite loop (NUSIZ0/GRP0), keep CTRLPF=$05.
- [x] **1b.** Set PF0=$70, PF1=$FF, PF2=$FF (bar shape with edge margins).
- [x] **1c.** Per scanline (×3): WSYNC → COLUPF=#$1C (yellow) →
      delay loop keyed to BarLevel → STA COLUPF (red).
      - BarLevel 16 = delay past bar end = all yellow.
      - BarLevel 0 = immediate red = all red.
      - B>=11 skips red write (delay would overrun 76c line).
      - Verified: boot all-yellow; after timer = yellow left / red right.
- [x] **1d.** After bar: clear PF0/PF1/PF2, restore COLUPF for HUD.
- [x] **1e.** Remove unused `BarPF*Table` lookups (lines 595-647).
      Deleted 4 tables (56 lines), 0 references. Fold-pads OK.
- [x] **1f.** Scanline budget: bar 6→3 lines (saves 3, HUD band ≤48).
      Pad ldx #11; both lives paths = 48.
- [x] **1g.** Build + Stella screenshot (`power_bar_1a.png`): yellow 3-line
      bar with margins, cave/map/HUD intact. visual_check PASS.

### Step 2: Ball at boundary

- [x] **2a.** CTRLPF ball bits: $05 → $35 (add ball 8 clocks, keep
      reflect+priority) or match HERO's $34 (reflect OFF for ball section).
- [x] **2b.** Enable ENABL, position ball at boundary via RESPBL/HMPBL.
      BallXTable after fold-pads (data, not in MenuMain path).
      SetObjectXPos X=4 → HMBL/RESPBL. Pad 11→9. visual_check PASS.
- [x] **2c.** Ball color = orange (kPalette hue 2/3).
      COLUPF #\$2A (hue2 luma5) stripe after delay, then red. Ball shares
      COLUPF. visual_check PASS on power_bar_2c.png (orange 60px @ boundary).
- [x] **2d.** Ball width = BarLevel mod 4 (1/2/4/8 clocks).
      CTRLPF = ((BarLevel&3)<<4) | \$05. DASM: bare \`asl\` (not \`asl a\`).
      visual_check PASS on power_bar_2d.png.
- [x] **2e.** Build, user tests: smooth sub-block edge at boundary.
      Automated: t12 all-yellow, t25 Y/O/R split, boundary moves with
      BarLevel, orange stripe 60px (accepted in 2c), ball width = BarLevel&3.
      Screenshots: power_bar_2e_t12.png, power_bar_2e_t25.png.

### Step 3: Timer speed

- [x] **3a.** `src/kernel.asm` line 625: `lda #28` → `lda #255`.
      Also lines 254, 645, 984 (all TickCounter reloads) so timer
      stays ~68 s after life loss / level change.
- [x] **3b.** Result: 16 × 255 = 4080 frames ≈ 68 seconds
      (single-byte approximation accepted).
- [x] **3c.** Build, user tests: timer expires ≈68 s → loses a life.
      Verified: near@66s bar 12% yellow; exp@71s bar full (reset) and
      lives green px 90→60 (one life lost). Screenshots:
      power_bar_3c_near/exp/post.png.

---

## Constraints

- **Scanline budget**: HUD band = 48 lines (144-191). Every WSYNC = 1 line.
- **ZP budget**: 128 bytes ($80-$FF). BarLevel=$AE, TickCounter=$AD already
  allocated. No new ZP needed for step 1.
- **Build**: `./build.sh` from repo root. `rm -f bank1.lst` before rebuild
  if listing looks stale.
- **Fold-pad**: bank1 fold-pad at $FC70 must stay byte-identical. Code
  address changes require re-checking fold-pad + `jmp` targets.
- **Baby steps**: one checkbox at a time. Build + user test after each step.

## Not in This Plan

- Ball separator smoothing → Step 2.
- Exact 120-second timer (needs 2-byte counter) → skipped per user.
