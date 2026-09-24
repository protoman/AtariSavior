# Plan: HERO-Style Kernel Refactor (Zero-Conditional Rendering)

## Problem
The kernel `.Line` worst case is 80 cycles (4 over 76 budget). The GRP0 conditional check (25 cycles) is the main bottleneck. Phased kernel attempt failed (84 cycles — overhead offset savings). Flicker on player+enemy overlap scanlines is NOT acceptable.

## Goal
Rewrite the kernel to have ZERO conditional branches for GRP0/GRP1/ENAM0, achieving a fixed ~60-65 cycles per scanline (well under 76). All rendering data pre-computed during VBLANK into ZP buffers, kernel reads via `(zp),Y` indirect indexed.

## Memory Constraint
- 2600 has 128 bytes of RAM ($80-$FF), mirrored at $0100-$01FF
- Currently ~64 bytes used during kernel (game vars + PF buffers)
- HERO-style needs: 192 bytes per buffer × 3 (GRP0 + GRP1 + ENAM0) = 576 bytes — **impossible**
- **Solution:** Only pre-compute GRP0 (192 bytes). GRP1 and ENAM0 stay conditional but are cheap (22c and 17c worst case). The GRP0 savings (19 cycles) bring worst case from 80 to ~61 cycles.

## ZP Budget Analysis

### Currently used during kernel (~64 bytes)
| Region | Bytes | Variables | Needed? |
|--------|-------|-----------|---------|
| $80-$8B | 12 | RoomX/Y, PlayerDir, vy, JetPower, StepsLeft, Scanline, LineCount, MapPtr | Yes |
| $8C-$90 | 5 | Grp0Ptr, ObjTop, ObjBot, LaserScanline | Yes |
| $A7 | 1 | Scanline | Yes |
| $D2-$FF | 46 | PF0Buf, PF1Buf, PF2Buf, ColupfBuf | Yes |

### Currently free during kernel (~64 bytes)
| Region | Bytes | Variables | Can reuse? |
|--------|-------|-----------|------------|
| $91-$95 | 5 | RoomPFData, RoomRects, RoomNo | Yes (only used during room load) |
| $96-$A6 | 17 | Level data, miner, enemies | Yes (only used during VBLANK) |
| $A8-$B1 | 10 | Game state (minus Scanline) | Yes (only used during VBLANK/overscan) |
| $B3-$BC | 10 | FontP0/P1 | Yes (only used by level sprites, reusable after level render) |
| $C2-$CF | 14 | ScoreTh/Hu/Te/On, score digits | Yes (only used by bank2 HUD) |

**Total available: ~56 bytes.** Need 192 for GRP0 buffer. **Gap: 136 bytes.**

### Space freed by PF score rendering
- ScoreDigit2/3 removed: 10 bytes
- ScoreSpriteFont removed: ~80 bytes ROM (not ZP)
- Net ZP savings: ~10 bytes (ScoreDigit2/3 area can be reused)

## Approach: Pre-compute GRP0 Only (Not Full HERO)

Since 192 bytes for GRP0 + 192 for GRP1 + 192 for ENAM0 is impossible, we pre-compute **only GRP0** (the main flicker source at 25 cycles). GRP1 (22c) and ENAM0 (17c) stay conditional but are cheap enough.

**Result:** GRP0 becomes 6 cycles (load from ZP + store). Worst case drops from 80 to **~61 cycles**.

### GRP0 Buffer Location
Need 192 bytes for GRP0 buffer. Options:

**Option A: Split across ZP + stack page mirrors**
- Store GRP0 for player scanlines (8 bytes) in ZP
- For other 184 scanlines, GRP0 = 0 (no buffer needed)
- Conditional check remains but is simplified

**Option B: Reuse PF buffers during kernel**
- PF buffers ($D2-$FF, 48 bytes) are written during VBLANK and read during kernel
- After kernel reads them, they're free — but kernel needs them throughout
- Not feasible

**Option C: Store GRP0 buffer in unused ZP region**
- During kernel, $91-$CF is unused (56 bytes)
- Need 192 bytes — still 136 short
- Could compress: store only non-zero entries + scanline positions

**Option D: Pre-compute into game logic variables that aren't needed during kernel**
- Move game variables to use fewer ZP bytes
- Reuse freed ZP for GRP0 buffer
- Requires refactoring game code

## Recommended Path: Option A (Simplified Pre-compute)

Since a full 192-byte buffer is impossible, use a **simplified approach**:

1. During VBLANK, compute the 8 GRP0 values for the player's scanlines
2. Store them in ZP (8 bytes at $96-$9D, reusing Level vars)
3. Store PlayerY in a ZP variable
4. In kernel: check if Scanline is in range [PlayerY, PlayerY+8)
5. If yes: load from ZP buffer (4 cycles)
6. If no: load #0 (2 cycles)

This is essentially what the current code does, but with the player data pre-loaded into ZP. The savings: `lda PlayerGrp0,X` (4c) vs `lda (Grp0Ptr),Y` (5c) = 1 cycle per player-visible scanline.

**Not enough.** The conditional check still costs 25 cycles.

## Revised Approach: True Pre-computation (192-byte buffer)

The ONLY way to eliminate the conditional is a 192-byte GRP0 buffer. To get 192 bytes:

### Step 1: Free ZP space by refactoring game code
- [ ] Move collision variables ($8C-$90) to use fewer bytes
- [ ] Combine LevelWallColor/LevelWallColor2 into one byte with lookup
- [ ] Eliminate redundant game state variables
- [ ] Move score data ($C2-$CF) to be computed on-demand in bank2
- [ ] Target: free ~136 additional bytes in ZP

### Step 2: Allocate GRP0 buffer
- [ ] Use freed ZP region ($91-$CF, ~56 bytes) + stack page region
- [ ] GRP0 buffer: 192 bytes at $0100-$01BF (mirrors $80-$3F... wait, that's TIA)

Actually, the stack page mirrors $80-$FF, so $0100-$01BF mirrors $80-$3F. TIA is at $00-$3F. So $0100-$01BF mirrors TIA registers! Can't use that.

Let me reconsider. The only usable RAM is $80-$FF (128 bytes). The stack page mirrors this exact range. There is NO additional RAM.

**Fundamental constraint: 2600 has only 128 bytes of RAM. Period.**

To store a 192-byte GRP0 buffer, we need to either:
1. Reduce the buffer to fit in available ZP (~56 bytes)
2. Accept that we can't have a full 192-byte buffer
3. Use a different rendering approach entirely

## Revised Plan: Optimize Within Constraints

Since a full HERO-style pre-computation is impossible with 128 bytes of RAM, here's a practical plan:

### Phase 1: Free ZP Space
- [ ] Remove ScoreDigit2/3 from ZP (already done — 10 bytes freed)
- [ ] Remove ScoreTh/Hu/Te/On from ZP — compute on-demand in bank2 from ROM (4 bytes)
- [ ] Remove FontP0/P1 from ZP — level sprites can use ROM pointers directly (10 bytes)
- [ ] Combine LevelConnLo/Hi into a single pointer (save 0 bytes, but cleaner)
- [ ] **Total freed: ~24 bytes**

### Phase 2: Optimize GRP0 Check
- [ ] Pre-load player graphic data into ZP ($96-$9D, 8 bytes) during VBLANK
- [ ] Use `lda PlayerGrp0,X` (4c) instead of `lda (Grp0Ptr),Y` (5c)
- [ ] Save 1 cycle per player-visible scanline
- [ ] **Total savings: 1 cycle per player scanline (8 scanlines × 1c = 8c/frame)**

### Phase 3: Optimize GRP1 Check
- [ ] Pre-load enemy graphic data into ZP during VBLANK
- [ ] Use `lda EnemyGrp1,X` (4c) instead of `lda #$f0` + BIT skip
- [ ] Save ~2 cycles per enemy-visible scanline
- [ ] **Total savings: 2 cycles per enemy scanline**

### Phase 4: Optimize ENAM0 Check
- [ ] Pre-compute laser state during VBLANK
- [ ] Store laser active flag in ZP
- [ ] Use `lda LaserActive` (3c) + conditional branch (2c) = 5c instead of 17c
- [ ] **Total savings: 12 cycles when laser is active**

### Expected Result
- GRP0: 25c → 24c (1 cycle saved)
- GRP1: 22c → 20c (2 cycles saved)
- ENAM0: 17c → 5c (12 cycles saved when active)
- **Worst case: 24 + 20 + 16 + 5 = 65 cycles** (under 76!)

## Risk
- ENAM0 optimization only helps when laser is active (rare)
- GRP1 optimization requires enemy graphic data in ZP (8 bytes)
- Total ZP needed for optimizations: ~16 bytes (8 for player + 8 for enemy)
- Available ZP after Phase 1: ~80 bytes (plenty)

## Verification
- [ ] Build succeeds
- [ ] Player sprite renders correctly
- [ ] Enemy/object renders correctly
- [ ] Laser renders correctly
- [ ] Flicker eliminated on overlap scanlines
- [ ] Frame timing stable (262 scanlines)
