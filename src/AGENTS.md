# Savior Kernel — Architecture

## Key Principle: Always Follow HERO First

**The Activision developers who created HERO are smarter than both of us combined. When in doubt, do NOT come up with "better" ideas. Just follow their path.** Look at what they did, understand why, and replicate it. Every time we tried to invent our own approach (inline bank-switching, NUSIZ copies for HUD elements, custom positioning), it failed or produced poor results. Every time we followed HERO's patterns (fold-pad bank switching, PF-based HUD rendering, SetObjectXPos), it worked.

**When implementing any feature, ALWAYS look at how HERO does it first and follow that approach.** HERO is the reference architecture. If there are multiple ways to implement something, HERO's way is the default choice. Only deviate from HERO's approach if there is a clear technical reason documented in this file. This applies to: rendering, HUD elements, sprite techniques, positioning, collision, sound, and every other aspect of the game.

**When something works in HERO, do NOT tell the user that following that idea will not work.** If HERO uses a technique for a specific feature (e.g., 3 lives, 5 bombs), and it works, then implement it the same way. Do not suggest alternatives or claim the approach has limitations. The fact that HERO does it proves it works.

**Before claiming how HERO implements something, ALWAYS look at the actual code first.** Do not suppose or assume based on partial understanding. Check hero_bank1.asm, the comparison code, and data tables (especially lookup tables like LFF3E for NUSIZ values, LFF6D for positioning, LFF96 for sprite data). If the code contradicts your assumption, the code wins — update your understanding and tell the user what you found, not what you thought.

**Why this rule exists:** In this session, the agent was told HERO uses NUSIZ copies for lives/bombs but kept insisting it was wrong and suggested 13+2 instead. Later found LFF3E=$30,$30,$20,$20 proving HERO uses NUSIZ. The agent was also told HERO uses PF for score but kept suggesting sprites. The pattern: the agent reads a PART of the code, forms an assumption, then defends it instead of reading more. The fix: read the FULL relevant section, trace the data flow, and verify against the actual disassembly before responding.

**What we already use from HERO (keep these, do NOT replace):**
- Reflected playfield (CTRLPF D0=1) — symmetric cave design
- PF registers written ONCE per tile row (TIA persists across scanlines)
- Fixed-time kernel with unconditional inner loop (no per-scanline branches)
- Andrew Davie's session-24 horizontal positioning (SetObjectXPos with div15 loop + page-aligned fineAdjustTable)
- HMOVE applied during HBLANK after RESP0/HMP0 are set
- Joystick read from SWCHA with 4× LSR to shift bits to D0-D3
- Frame timing: 3 VSYNC + 37 VBLANK + 192 kernel + 30 overscan = 262 scanlines
- F6 bankswitching (16K, 4 banks × 4K)

**What we have NOT yet implemented from HERO (implement these next):**
- 13+2 sprite technique for HUD text/indicators (P0×3 + P1×3 + ball = 13 character columns)
- Per-scanline PF lookup tables for cave patterns (HERO uses 8-entry tables at $DC6A/$DC6C/$DC77)
- Second kernel for HUD rendering (HERO calls JSR $DE00 after cave kernel)
- VDELP0/VDELP1 vertical delay pipeline for multi-sprite text
- Font data loaded into zero-page RAM during VBLANK for fast (zp),Y access
- Ball (ENABL) for HUD indicators

## Critical Rule: NEVER Delete Files Without User Permission

**Deleting files (rm, git rm, moving files to /dev/null, or any operation that removes a tracked or untracked source file) is FORBIDDEN without explicit user approval.** This includes:
- Source files (.asm, .py, .cpp, .hpp, .json, .txt, .sh, etc.)
- Generated files (if they are part of the build pipeline and re-creatable, ask first)
- Config files, build scripts, tool scripts

**What to do instead:** When a file needs to be removed or replaced, tell the user what you want to delete and why. Wait for explicit confirmation. If you accidentally created a file that shouldn't exist, explain which file and ask to delete it.

**Why this rule exists:** On 2026-09-22, the editor source files (MainWindow.hpp, MainWindow.cpp, MapCanvas.hpp, MapCanvas.cpp, LevelData.hpp, DataSerializer.cpp) were lost because they were never added to git, then overwritten without warning. The user's work was destroyed. This must never happen again.

## Overview

A from-scratch Atari 2600 game kernel modeled after Activision's HERO (1984). Built
in `src/` as a standalone project with no dependencies on the older prototype.

## ROM Layout

- **16K ROM** — F6 bankswitch (4 banks × 4K each)
- Bank0: `kernel.asm` — main game code, cave kernel, player logic
- Bank1-3: stubs (switch to bank0, ready for future expansion)
- Output: `savior.bin` (16K)

### F6 Bankswitching

| Bank | Address Range | Power-up | Contents |
|------|--------------|----------|----------|
| Bank0 | $F000-$FFFF | — | Game code + cave kernel |
| Bank1 | $F000-$FFFF | — | Stub → bank0 |
| Bank2 | $F000-$FFFF | — | Stub → bank0 |
| Bank3 | $F000-$FFFF | Yes | Stub → bank0 + reset vector |

Bank select: `STA $1FF6` (bank0), `$1FF7` (bank1), `$1FF8` (bank2), `$1FF9` (bank3).
Power-up bank is bank3; its reset vector at $FFFC points to the stub which switches to bank0.

## Frame Timing (262 scanlines @ 60Hz NTSC)

| Section    | Scanlines | Notes |
|------------|-----------|-------|
| VSYNC      | 3         | Sync pulse |
| VBLANK     | 37        | Game logic + sprite positioning |
| Kernel     | 192       | 144 cave + 48 HUD band |
| Overscan   | 30        | Input + movement |
| **Total**  | **262**   | NTSC standard |

## Memory Map

### Zero-page ($80-$FF, 128 bytes)

| Address | Name       | Purpose |
|---------|------------|---------|
| $80     | RoomX      | Player X position (0-159) |
| $81     | RoomY      | Player Y position (0-191) |
| $82     | Scanline   | Current scanline counter |
| $83     | LineCount  | Scanlines remaining in tile row |
| $84     | TileRow    | Current tile row (0-11) |
| $85-$86 | Grp0Ptr    | Player sprite pointer (unused yet) |
| $87     | Temp       | Scratch |

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

### Structure (HERO pattern)

```
.Row (×12):       PF setup — write PF0/PF1/PF2 ONCE per tile row
                   (TIA registers persist — no need to rewrite per scanline)
.Line (×12):      Sprite rendering — the tight inner loop
                   Unconditional: same instruction stream every scanline
```

### Per-scanline cycle budget (76 max)

Our `.Line` loop worst-case:

| Section        | Cycles (off-screen) | Cycles (on-screen) |
|----------------|--------------------|--------------------|
| GRP0 check     | 16                 | 19                 |
| Loop control   | 16                 | 16                 |
| **Total**      | **32**             | **35**             |

Both well within 76-cycle limit. No flicker.

### PF Write Strategy

PF registers (PF0/PF1/PF2) are written ONCE per tile row in `.Row`.
The TIA persists these values across all 12 scanlines of the row.
This saves 36 cycles per scanline (3 writes × 12 cycles each).

## Build

```bash
./build.sh          # builds savior.bin (16K, F6)
```

Requires: `dasm` (6502 cross-assembler)

### DASM Assembly Gotchas

- **`=` definitions MUST start at column 1** — DASM treats indented `=` as
  unknown mnemonics and silently fails. Example: `    Temp = $AD` fails but
  `Temp = $AD` works. This caused bank1 to silently use stale .bin files.
- **ALWAYS verify bank1.bin is actually rebuilt** — if DASM fails but the
  build script catches the error (via `|| echo`), the old .bin is reused.
  Check file timestamps after building.

## Testing

Run in Stella:
```bash
stella savior.bin        # normal emulation
stella -debug savior.bin # debugger
```

## Development Plan

### Phase 1: Basic Rendering ✅ (in progress)
- [x] VSYNC/VBLANK/Overscan frame timing
- [x] Kernel: 12 tile rows × 12 scanlines + 48 HUD band
- [x] Cave playfield with reflected mode (CTRLPF D0=1)
- [x] Player sprite (GRP0) — 8×8 square
- [x] Joystick movement (up/down/left/right)
- [ ] Fix cave shape (currently vertical bars — needs proper walls)
- [ ] Proper wall collision bounds

### Phase 2: Player Sprite & Positioning
- [ ] Horizontal positioning via RESP0/HMP0 (Andrew Davie algorithm)
- [ ] Player sprite art (not just a square)
- [ ] Smooth movement with proper pixel bounds
- [ ] Collision box matching visual sprite

### Phase 3: Collision Detection
- [ ] Player-to-playfield collision (CXP0FB)
- [ ] Wall collision prevention (don't walk through walls)
- [ ] Room boundary checks (don't leave room edges)
- [ ] Collision response (bounce/stop)

### Phase 4: Room System
- [ ] Room data format (20×12 tile grids in ROM)
- [ ] Room connections (up/down/left/right exits)
- [ ] Room transitions (load new room on exit)
- [ ] Multiple rooms per level
- [ ] Room-specific enemy placement

### Phase 5: Enemies (GRP1)
- [ ] Enemy sprite rendering (GRP1)
- [ ] Enemy positioning (RESP1/HMP1)
- [ ] Basic enemy AI (patrol, chase)
- [ ] Enemy-player collision
- [ ] Multiple enemy types

### Phase 6: HUD Display
**ALWAYS follow HERO's approach for HUD rendering.** HERO uses the 13+2 sprite technique (P0×3 copies + P1×3 copies + ball) for ALL HUD elements — text, lives, bombs, timer. Simple NUSIZ copies are insufficient for multi-element HUDs (e.g., 5 bombs, 9 lives). The 13+2 technique is the correct solution.
- [ ] Score display (3 digits)
- [ ] Lives display (up to 9)
- [ ] Bombs display (5)
- [ ] Timer bar
- [ ] Level indicator
- [ ] HUD rendering in the 48-line band

**Score rendering notes (from HERO disassembly + bumbershootsoft):**

**HERO's actual architecture (follow this):**
- HERO uses **per-scanline PF lookup tables** — NOT a font array + runtime computation
- Each scanline gets its own complete PF0/PF1/PF2 value from ROM tables (LFA00/LFB00/LFC00/LFD00)
- Font data is **baked directly into the PF register values** — there is no separate PFDigitFont
- The score kernel loads ONE source byte per scanline, then ANDs it with per-scanline masks ($BF for PF1, $C2 for PF2) to extract each PF register's portion
- Masks vary per scanline because different rows need different bits masked off
- This eliminates serialization overhead — each scanline's PF values are loaded directly from ROM
- The PF values encode both the digit shape AND the pixel positioning in the PF register bit layout
- Score is 4 scanlines tall (not 5), using 2-pixel-wide digits (not 3)
- The key trick: one source byte encodes PF0 raw, PF1 via AND mask, PF2 via AND mask — saves ROM space and simplifies the kernel

**Why this matters:** HERO's digits look small because the PF lookup tables pre-compute the exact pixel pattern for every scanline. Our approach of computing PF values at runtime from a font array introduces overhead and makes digits wider. To match HERO's look, we should use the same PF-table approach.

**What we currently use (bumbershootsoft approach, works but wider):**
- CTRLPF=$02 (SCORE mode) — uses COLUP0 for left half, COLUP1 for right half
- Font stored as separate PFDigitFont array (3 pixels wide, 5 rows)
- PF values computed at runtime from font data
- Score render loop: writes PF0/PF1/PF2 per scanline from pre-computed buffers
- The 13+2 technique is used for the 32-char text demo (bank1), but the game HUD uses simpler sprite+PF approach

### Phase 7: Gameplay
- [ ] Laser/weapon system (missile 0)
- [ ] Bomb system (ball)
- [ ] Wall destruction
- [ ] Item collection
- [ ] Level progression
- [ ] Win/lose conditions

### Phase 8: Jetpack Physics
- [ ] Gravity (constant downward force)
- [ ] Thrust (upward force when button held)
- [ ] Inertia (momentum)
- [ ] Fuel management
- [ ] Vertical collision with ceiling

### Phase 9: Polish
- [ ] Sound effects (engine, laser, explosions)
- [ ] Music (background theme)
- [ ] Color schemes per level
- [ ] Screen transitions
- [ ] Title screen
- [ ] Game over screen
- [ ] Difficulty settings

### Phase 10: Levels & Content
- [ ] Design 5+ levels with increasing difficulty
- [ ] Level-specific enemy patterns
- [ ] Boss encounters
- [ ] Secret rooms/areas
- [ ] High score tracking

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
   and grows downward. Any ZP buffer at $F8-$FF (like PlayerGrp0) shares
   physical RAM with the stack. **JSR pushes return addresses to $FF-$FE,
   overwriting data at those ZP addresses.** If you copy data to a ZP
   buffer and then call JSR, the return address overwrites the buffer.
   Rule: copy to ZP buffers at $F8-$FF ONLY AFTER all JSR calls are done,
   just before the code that reads the buffer. Example: player sprite data
   was copied to PlayerGrp0 ($F8-$FF) before LoadPFBuffer/SelectActiveObject
   JSR calls — the return addresses overwrote sprite rows 6-7, causing
   extra rendering artifacts.

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
| PF writes | Per-scanline (ROM tables) | Per-tile-row (simpler) |
| Sprite data | `(zp),Y` from ROM | ZP indexed (`PlayerGrp0,Y`) |
| VDEL | Used for sprite pipeline | Not used (simpler) |
| Enemies | Yes (miner + enemies) | Not yet |
| Rooms | Multiple connected rooms | Single hardcoded room |
| HUD | Score/lives/time text | Grey band only |
| Jetpack | Physics with gravity | Simple up/down |

## Debugging

### Stella Debugger

- `stella -debug savior.bin` — launch with debugger
- Backtick (`) — enter debugger from emulation
- `run` — resume execution
- `breakLabel <addr>` — set bankswitch-safe breakpoint
- `clearbreaks` — clear all breakpoints
- `scanline` — show current scanline

### Timing Measurement

Use `breakLabel` at two addresses, subtract Scn values:

1. `clearbreaks`
2. `breakLabel <start_addr>` → run → note Scn value
3. `clearbreaks`
4. `breakLabel <end_addr>` → run → note Scn value
5. Subtract to get duration in scanlines

**NEVER use `break`** — it fires at the physical ROM address in ALL banks
(causes cross-bank contamination with bankswitched ROMs).

### Pseudo-registers (Stella 7.0)

- `_scan` does NOT work — resolves to $00 (CXM0P)
- `breakif {_scan == N}` is UNRELIABLE
- Use `breakLabel` + Scn field instead

### Lessons Learned

**Collision misalignment (2026-09-21):** A `jmp .Div15Loop` in SetObjectXPos
added 3 cycles (1 pixel) to RESP0 timing, shifting the sprite's pixel position
right while the collision code expected it left. This caused the player to stop
1+ pixels away from walls. **Fix:** Remove any extra instructions before the
div15 loop — the comparison branch's SetObjectXPos is the reference.

**PF0 bit order (2026-09-21):** TIA PF0 has bit 4 = leftmost pixel, NOT bit 7.
The mapping `0x10 << col` is correct. Do NOT "fix" this — it was verified
empirically and matches the comparison branch.

**When debugging collision misalignment:**
1. First check if SetObjectXPos matches the comparison branch exactly
2. Check if the fineAdjustTable is identical
3. Check if the PF0/PF1/PF2 data matches what the TIA renders
4. Use Stella to measure actual sprite pixel position vs expected

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

### php/pla X-preserve sets decimal mode (2026-09-23) — NEVER repeat

**Bug:** To keep `EnemyIndex` in X across `jsr IsRoomDark`, code used
`php / tax / <call> / pla / tax / plp`. After `pla`, X still held the **saved
flags** (from `php`), not the saved X. The following `plp` then restored **X
into the flags**. When X happened to have bit 3 set, **D (decimal mode) was
enabled** — every subsequent `ADC`/`SBC` became BCD math. Symptoms: stuck
player, vertical-rectangle miner, black playfield, garbage collision.

**Fix:** Do **not** preserve X across a call with php/pla/tax/plp. Make the
callee clobber-safe and reload the value in the **caller** instead:
`jsr IsRoomDark` (clobbers A/X only, Y safe) then
`lda (EnemyDataLo),Y / tax` to reload type before `EnemyColorTable,X`.

**Rule:** Never invent stack-preserving register dances. If a routine must
return a value, put it in A (or a documented ZP temp). Callers reload.

### Origin Reverse-indexed: bank0 code must end before $FC68 (2026-09-23)

F6 fold pads live at fixed `org $FC68` / `org $FC70`. DASM errors
`Origin Reverse-indexed` if main code (everything before those orgs) grows
past `$FC68`.

**When adding bank0 routines that push the end over `$FC68`:** move **leaf
helpers** (not the fold pads themselves) **after** `org $FC70` — same pattern
as existing `HotOverlapFlag` / `AddScore` / `ReloadLevel`. `jsr` is absolute,
so post-pad placement is fine. Never move `Overscan` without syncing
bank1's `jmp $Fxxx` (ToGameStub at `$FC70` must match).

**This session:** `AddScore` alone overflowed (fc68→fc72). Fixed by moving
`AddScore` + `ReloadLevel` after the pads. Build green: 4×4096, folds match,
Overscan still `$F14D`.

### Score rewards (2026-09-23): +50 kill, +75 wall, no fire hack

- **Removed** bank1 fire-button `INPT4` → `+$50` hack (was demo-only).
- **`AddScore`** (after fold pads): A = BCD amount (`#$50`/`#$75`).
  `ScoreTe` packed BCD (`tens*16+ones`), `ScoreTh`/`ScoreHu` binary 0-9.
  Overflow: `$a0` wrap → inc Hu; Hu≥10 → wrap, inc Th; Th≥10 → cap 9.
- **Call sites (bank0 overscan):**
  - `CheckEnemyHit` after `sta DeadEnemyIdx` (non-lamp) → `#$50`
  - `BombEnemyBlast` after kill → `#$50`
  - `BombMarkWalls` only when WallMask bit **was clear** → `#$75`
    (and-ora with existing mask; already-broken → skip score)
- **Score persists** across `ReloadLevel` (not cleared on death).
- Score display is 4 meaningful digits (Th Hu tens ones); ptrs 5-6 blank.

### Editor flicker budget (2026-09-23)

`MapCanvas`: **max 3 elements/room** (`kMaxRoomElements`) and **max 1 element
per row** (miner/enemy/lamp share a row budget). Warnings via `QMessageBox`.
Rationale: GRP1 is one sprite — more simultaneous objects → more flicker
(rotating `SelectActiveObject`). Restrict at authoring time.

## Skill References

- `docs/zp_layout_skill.md` — Complete zero-page memory map for all banks (bank0/bank1/bank2), with conflict detection rules and historical crash lessons
- `docs/font/48px_score_skill.md` — 48-pixel sprite score technique (NUSIZ copies + VDELP cross-buffer), known bugs, and implementation guide
