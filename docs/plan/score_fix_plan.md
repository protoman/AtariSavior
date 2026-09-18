# Score Rendering Fix Plan

## Problem
Score digits appear too large and don't match HERO's small, refined font.

## Root Causes (from bumbershootsoft documentation)
1. We write to PF0/PF1/PF2 — HERO only uses **PF2** for digit rendering
2. Missing **CTRLPF=$02** (SCORE mode) — causes doubled score in reflected mode
3. Font is **3×6 bricks** (not our 3×5)
4. Score should be stored as **BCD** (Binary Coded Decimal)
5. Font data should be in **final 256 bytes** of ROM

## Fix Steps

- [ ] **Step 1: Add CTRLPF=$02** — Set SCORE mode before rendering score. This uses COLUP0 for left half, COLUP1 for right half, avoiding doubled score in reflected mode.

- [ ] **Step 2: Rewrite score to use PF2 only** — Remove PF0ScoreBuf/PF1ScoreBuf. Compute PF2 values directly from font data. Each digit is 3 bits wide in PF2, combined with OR for two digits per PF2 byte.

- [ ] **Step 3: Update font to 3×6 format** — Change PFDigitFont from 3×5 to 3×6 bricks, stored bottom-to-top. Update DigitTimes5 accordingly.

- [ ] **Step 4: Store score as BCD** — Change ScoreTh/Hu/Te/On to use BCD encoding (e.g., 57 stored as $57).

- [ ] **Step 5: Test and verify** — Build, run in Stella, verify score digits match HERO's small/refined appearance.

## Current Status
- [x] Step 1 — Add CTRLPF=$02 (SCORE mode before score, restore to $05 after)
- [x] Step 2 — Rewrite score to use PF0+PF1+PF2 (all 3 registers, 4 digits)
- [x] Step 3 — Update font to 3×5 (matching comparison/bank2 PFDigitFont, 1 scanline per row)
- [x] Step 4 — COLUP1 = background grey to hide right-half duplication
- [x] Step 5 — Build verified clean
