# Fix Flicker: Frame Timing & Kernel Overruns

## Problem
Kernel `.Line` loop exceeds 76 cycles on some scanlines, causing per-scanline flicker.

## Root Causes Identified

### 1. `_scan` pseudo-register broken in Stella 7.0 (FIXED)
- `watch _scan` → BAD WATCH; `print _scan` → resolves to address $00 (CXM0P)
- All `breakif {_scan == N}` commands were unreliable
- **Fix:** Use `breakLabel` for bankswitch-safe breakpoints (NOT `break` — see lesson below)

### 2. `.Row` WSYNC adds +13 scanlines — CANNOT FIX
- Each tile row has a `sta WSYNC` after PF setup, making cave kernel 157 scanlines instead of 144
- **Why we can't fix it:** PF writes (38c) + first `.Line` rendering (50-69c) = 88-107c, exceeding 76c budget. Removing the WSYNC just shifts the extra scanline to a different location.
- Full kernel rewrite (HERO-style per-scanline PF lookup) would be needed — deferred.

### 3. Bank2 HUD takes ~58 scanlines — CORRECT, NOT A PROBLEM
- **Correct measurement (via `breakLabel`):** `breakLabel f177` → Scn 190, `breakLabel fc80` → Scn 248. Bank2 = 58 scanlines.
- **Previous 88-scanline measurement was WRONG** — caused by cross-bank breakpoint contamination. Regular `break f067` fires at address $f067 in BOTH bank0 (`lda ActiveObjectOn` in VBLANK) and bank2 (score font loading), mixing bank0 and bank2 scanline readings.
- **Lesson:** ALWAYS use `breakLabel` (not `break`) for F6 bankswitch debugging. Regular `break` fires at the physical ROM address regardless of which bank is active.

### 4. Kernel `.Line` worst-case = 80 cycles (4 over 76) — THE FLICKER SOURCE
- GRP1 (22c) + GRP0 (25c) + ENAM0 (17c) + loop (16c) = 80
- Causes flicker on scanlines where player + enemy overlap
- **Fix:** Pre-compute GRP0/GRP1/ENAM0 during VBLANK, read from buffer in kernel (no conditional branches)

## Frame Budget (measured)

| Section | Scanlines | Notes |
|---------|-----------|-------|
| VSYNC | 3 | |
| VBLANK (setup + wait) | ~35 | |
| Cave kernel (.Row+.Line) | 157 | 12 rows × 13 scanlines (PF setup + 12 lines) |
| Bank2 HUD | 58 | Measured via `breakLabel f177`/`breakLabel fc80` |
| Overscan | ~30 | |
| **Total** | **~283** | ~21 over NTSC 262 target |

The .Row WSYNC (+13 per row) means the cave kernel alone is 157 scanlines.
The absolute minimum frame is: 3 + VBLANK + 157 + 58 + 30 = ~253+.
Frame is ~283 (21 over NTSC 262), causing possible screen jitter/roll.

## Plan

### Phase 1: Fix debugging infrastructure — DONE
- Address breakpoints work with `breakLabel` (NOT `break`)
- AGENTS.md updated with corrected documentation
- Discovered cross-bank breakpoint contamination

### Phase 2: Fix kernel cycle overruns (THE ACTUAL FLICKER)
- Pre-compute GRP0, GRP1, ENAM0 into ZP buffers during VBLANK
- Kernel reads `LDA Grp0Buf,Y / STA GRP0` — fixed cycle count
- Reduces worst-case from 80 to ~70 cycles (eliminates flicker on overlap scanlines)
- ENAM0 buffer eliminates the 3-branch color stripe check

**Approach:** Use `(zp),Y` indirect indexed addressing like HERO does.
Pre-load font/object pointers into ZP during VBLANK, then read via
`(pointer),Y` in the kernel. This avoids both stack overflow and ZP overflow.

### Phase 3: Recalibrate VBLANK wait loop (if needed)
- After Phase 2: measure frame with `breakLabel`
- Adjust wait loop to hit target frame length
- Target: minimize frame length while staying ≤262

## Execution Order
1. ~~Phase 1~~ → DONE
2. Phase 2 → fix kernel overruns (pre-compute GRP0/GRP1/ENAM0)
3. Phase 3 → recalibrate wait loop
4. Verify: measure frame, check flicker

## Verification Steps
1. Build: `./build_game_f6.sh`
2. Measure frame: `stella savior.bin` → debugger → `clearbreaks` → `breakLabel f177` → `run` → note Scn value
3. Measure bank2: `breakLabel fc80` → `run` → note Scn value → subtract from previous
4. Check flicker: visual inspection in Stella

## Debugging Lessons Learned

### Cross-bank breakpoint contamination
Regular `break <addr>` fires at the physical ROM address in ALL banks.
With F6 bankswitching, the same address (e.g., $f067) has different code in
different banks. The breakpoint fires in BOTH banks, mixing scanline readings.

**Solution:** Always use `breakLabel` for bankswitch-safe breakpoints.
`breakLabel` fires at the address in all banks but avoids mirror issues.

### Stella "Scn Ln" display format
The debugger shows two numbers: `Scn / Ln`
- **Scn** = frame scanline (0 to 261+ for NTSC, counts VSYNC+VBLANK+kernel+overscan)
- **Ln** = visible scanline (resets to 0 when VBLANK turns off, counts up during visible area)

Example: `190 / 43` means frame scanline 190, visible scanline 43.

### Measurement technique (PROVEN)
1. `clearbreaks` first
2. `breakLabel <addr>` — set breakpoint at specific address
3. `run` → stops at breakpoint → read Scn value from "Scn Ln" field
4. Repeat at different addresses to map the full frame
5. **ALWAYS use `breakLabel`, NEVER use `break`** for F6 bankswitch ROMs
