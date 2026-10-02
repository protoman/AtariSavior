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
  → score DOES use P0×3+P1×3+VDELP (docs/font/48px_score_skill.md); ball/extra columns not yet
- Per-scanline PF lookup tables for cave patterns (HERO uses 8-entry tables at $DC6A/$DC6C/$DC77)
- Second kernel for HUD rendering (HERO calls JSR $DE00 after cave kernel)
  → effectively done: bank1 HUD band runs via the $FC68 fold pad after the cave kernel
- VDELP0/VDELP1 vertical delay pipeline for multi-sprite text → done for score (bank1)
- Font data loaded into zero-page RAM during VBLANK for fast (zp),Y access
  → partial: digit ptrs live in ZP (scorePtr1-6), glyphs stay in ROM ($FD00)
- Ball (ENABL) for HUD indicators

## Critical Rule: NEVER Delete Files Without User Permission

**Deleting files (rm, git rm, moving files to /dev/null, or any operation that removes a tracked or untracked source file) is FORBIDDEN without explicit user approval.** This includes:
- Source files (.asm, .py, .cpp, .hpp, .json, .txt, .sh, etc.)
- Generated files (if they are part of the build pipeline and re-creatable, ask first)
- Config files, build scripts, tool scripts

**What to do instead:** When a file needs to be removed or replaced, tell the user what you want to delete and why. Wait for explicit confirmation. If you accidentally created a file that shouldn't exist, explain which file and ask to delete it.

**Why this rule exists:** On 2026-09-22, the editor source files (MainWindow.hpp, MainWindow.cpp, MapCanvas.hpp, MapCanvas.cpp, LevelData.hpp, DataSerializer.cpp) were lost because they were never added to git, then overwritten without warning. The user's work was destroyed. This must never happen again.

## Critical Rule: NEVER Read or Write TODO.txt

**`src/TODO.txt` is the user's private file. Never open it, grep it, search it, or write it.** Do not use `cat`, `Read`, `Grep`, `Glob` matches, or any tool that would expose its contents. Exclude it from searches. When a commit includes it (user's instruction), `git add TODO.txt` blindly — never inspect contents.

**Data rule:** measurement/debug values come ONLY from screenshots the user provides or from code the agent verified directly. Values that leaked from TODO.txt are forbidden and must be discarded.

**Why this rule exists:** On 2026-09-27 a grep over `src/` surfaced TODO.txt lines containing Stella INTIM readings; those values polluted the timing analysis. The user's TODO file is off-limits — full stop.

## File-Format Changes Require Data Migration

When changing a serialized or generated data format, update all existing project data and its generators in the same change. Preserve compatibility with older files through an explicit version/default migration, or migrate those files before requiring the new format. Verify both legacy loading and new-format round trips; never leave checked-in data behind the code's schema.

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

### Structure (HERO pattern)

```
.Row (×TILE_ROWS=3): PF setup — write PF0/PF1/PF2 ONCE per 48-line band
                   (TIA registers persist — no need to rewrite per scanline)
.Line (×48):      Sprite rendering — the tight inner loop (band 2 runs
                   36 bodies + the 12-line .WaterRow strip)
                   Unconditional: same instruction stream every scanline
```

*(Era note: this was "12 tile rows × 12 scanlines" until the 2026-09-28
band cut — PF buffers shrink to rows 0-2, `LINES_PER_TILE=48`,
`YToRowTable = line/48`. The 3-band structure is current.)*

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

### Phase 1: Basic Rendering ✅
- [x] VSYNC/VBLANK/Overscan frame timing
- [x] Kernel: 3 bands × 48 scanlines + 48 HUD band (originally 12×12; band
      cut 2026-09-28 — `TILE_ROWS=3`, `LINES_PER_TILE=48`)
- [x] Cave playfield with reflected mode (CTRLPF D0=1)
- [x] Player sprite (GRP0) — 8×12, per-row colors, 2-frame jet animation, REFP0 mirror
- [x] Joystick movement (up/down/left/right)
- [x] Fix cave shape — room .txt maps + convert_room (per-room walls, not bars)
- [x] Proper wall collision bounds (rect walk — see Phase 3)

### Phase 2: Player Sprite & Positioning
- [x] Horizontal positioning via RESP0/HMP0 (Andrew Davie algorithm;
      SetObjectXPos pinned to the $FF10 gap + page-cross guards)
- [x] Player sprite art (jet animation, 2 frames)
- [x] Smooth movement with proper pixel bounds (PLAYER_MIN/MAX_X clamps)
- [x] Collision box matching visual sprite (PlayerHitsMap cell range)

### Phase 3: Collision Detection
- [x] Player-to-playfield collision — implemented as the **rect-cache walk**
      (PlayerHitsMap), NOT TIA CXP0FB: rooms ship x/y/w/h rect lists
- [x] Wall collision prevention (don't walk through walls)
- [x] Room boundary checks (don't leave room edges — exit handlers)
- [x] Collision response (stop + hot-rock bump)

### Phase 4: Room System
- [x] Room data format (rooms/*.txt → convert_level → PF + rect lists in ROM)
- [x] Room connections (up/down/left/right exits — LevelConn*)
- [x] Room transitions (load new room on exit — EnterRoom)
- [x] Multiple rooms per level (2 levels, LEVEL_COUNT guarded)
- [x] Room-specific enemy placement (JSON enemies + editor 3-slot cap)

### Phase 5: Enemies (GRP1)
- [x] Enemy sprite rendering (GRP1, ObjSprites bank0)
- [x] Enemy positioning (RESP1/HMP1 via SetObjectXPos selector 1)
- [x] Basic enemy AI (patrol/chase — moth walk, tentacle probe, derives)
- [x] Enemy-player collision (CheckEnemyHit)
- [x] Multiple enemy types (moth/spider/tentacle/bat/snake/lamp + miner)

### Phase 6: HUD Display
**HERO's HUD per disassembly (corrected — see the "read the FULL section"
rule at the top):** NUSIZ copies for icon rows (`LFF3E = $30,$30,$20,$20`
= lives/bombs), 13+2 (P0×3 + P1×3 + ball) for TEXT rows. An earlier
version of this section claimed HERO used 13+2 for *everything* — that
was the disproven claim.
- [x] Score display (6 digits — bank1, 48px technique: NUSIZ×3 P0/P1 +
      VDELP cross-buffer, `docs/font/48px_score_skill.md`)
- [x] Lives display (bank1 "Line 2", NUSIZ icons)
- [x] Bombs display (bank1 "Line 3", red squares, count = PlayerBombs)
- [x] Timer bar (power bar, bank1 — BarDelay/BarFine/BallX tables)
- [ ] Level indicator
- [x] HUD rendering in the 48-line band (bank1 via the $FC68 fold pad)

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

**What we currently use (48px sprite score, `docs/font/48px_score_skill.md`):**
- Score is rendered by **bank1** in the HUD band: NUSIZ0/1 = 3 (P0×3 +
  P1×3 = 6 digit slots), VDELP0/1 cross-buffer pipeline
- `scorePtr1-6` ($E0-$EB) → `DigitGfx` ROM font at $FD00, read
  `lda (scorePtrN),Y` per scanline
- The old bumbershootsoft PF-compute approach (CTRLPF SCORE mode +
  `PFDigitFont` + runtime PF values) is **gone** — no `PFDigitFont`
  reference survives anywhere
- HERO's per-scanline PF-table trick (bullets above) remains the
  aspirational reference for pixel-small digits

### Phase 7: Gameplay
- [x] Laser/weapon system (missile 0) — LaserInput/ENAM0/BeamMask/LaserHitTest
- [x] Bomb system (bomb sprite + fuse timer, NOT the ball — BombPacked state machine)
- [x] Wall destruction (BombMarkWalls/ApplyBombWalls, WallMask b3-6)
- [x] Item collection (CheckMinerPickup → next level)
- [x] Level progression (inc Level, wraps at LEVEL_COUNT)
- [ ] Win/lose conditions — lose (0 lives → game over) exists; no win screen (levels wrap)

### Phase 8: Jetpack Physics
- [x] Gravity (constant downward force — vyLo/vyHi integration)
- [x] Thrust (upward force when button held — JetPower ramp)
- [x] Inertia (momentum — subpixel accumulator PlayerYSub)
- [ ] Fuel management (no fuel system; the power bar is the game TIMER)
- [x] Vertical collision with ceiling (StepUp stops flush)

### Phase 9: Polish
- [x] Sound effects (engine buzz, bomb drop/explode, laser — test_laser_sound.py)
- [ ] Music (background theme)
- [x] Color schemes per level (LevelWallColor/LevelWallColor2 from level data)
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
| PF writes | Per-scanline (ROM tables) | Per-band (3 × 48 lines, written once in `.Row`) |
| Sprite data | `(zp),Y` from ROM | `(zp),Y` from ROM (`(Grp0Ptr),Y`, frame picked in VBLANK) |
| VDEL | Used for sprite pipeline | Used by bank1 score (48px technique); cave kernel no |
| Enemies | Yes (miner + enemies) | Yes — moth/spider/tentacle/bat/snake/lamp + miner |
| Rooms | Multiple connected rooms | Yes — multi-room levels, exit handlers + connections |
| HUD | Score/lives/time text | Yes — bank1 band via fold pad (score/lives/bombs/bar) |
| Jetpack | Physics with gravity | Yes — gravity/thrust/inertia (vyLo/vyHi/JetPower) |

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

**py65 PC traces MUST filter the execution bank (2026-09-29):** bank0/bank1
share the $F000-$FFFF address space — a raw PC counter sees bank1 HUD code at
the SAME address as a bank0 routine (tentacle's `beq .TentCommit` at $F5A5 =
bank1's `lda BarDelayTable,Y`), silently mixing them: counts came out ~5× too
high and the "probe path" PCs were bar-red delay instructions. Rule: pair
every `(pc, ...)` count with `mem.bank` (measure's `hpc[(pc,bank)]` does);
a lone hex PC is ambiguous.

**`print *$XX` DEREFERENCES — it is NOT a raw byte read (2026-09-28):**
`*` is Stella's pointer operator: `print *$B5` uses the byte AT `$B5` as an
address and shows THAT cell (observed: `print *$B5` → `ram_81` because
`[$B5]=$81`; `print *$F7` → `CXBLPF|$30(R)` because `[$F7]=$35` pointed at
the TIA collision register at `$35`). Reading a ZP variable raw:
- `watch $XX` — prints the raw byte before every prompt (preferred), or
- `ram` — full ZP dump, or
- click the `00xx` RIOT grid cell (row = high nibble, col = low nibble).
Symptom of having used `*` by accident: output names a *different* address
(TIA register or `ram_XX`) than the one you typed.

### Scn Ln fields (TIA info panel) — source: Stella `TiaInfoWidget.cxx`

The row labeled `Scanline` (short form **`Scn Ln`**) holds TWO value boxes
(comment line 32: "current and the last-frame scanline counts, which share a
row"). Box order is fixed by reflow (line 199-200: `{myScanlineCount,
myScanlineCountLast}`) — **left box first, right box second:**

| Box | Widget | Source | Meaning (tooltip) |
|-----|--------|--------|-------------------|
| **LEFT** | `myScanlineCount` | `tia.scanlines()` = `myCurrentFrameTotalLines` | "Current scanline of this frame" — 0 at frame start, +1 per scanline |
| **RIGHT** | `myScanlineCountLast` | `tia.scanlinesLastFrame()` = `myCurrentFrameFinalLines` | "Number of scanlines of last frame" — frozen; updates ONLY at frame boundary |

- Frame boundary = `notifyFrameComplete()` (AbstractFrameManager.cxx:91) →
  RIGHT = totalLines at that instant, LEFT resets to 0. Fired by: VSYNC
  falling edge (≥2-line pulse), or timeout paths (`myVsyncLineCount > 50`).
- So `Scn 45|301` = line 45 of the CURRENT frame; last completed frame was
  301 lines long.
- Cross-checks: `Frame Cycles` ≈ LEFT×76 + Scn Cycle (tooltip: "CPU cycles
  executed this frame"); `Frame` = boundary counter.
- NEVER conclude "frame is N lines" from LEFT — LEFT is a position, not a
  total. Only RIGHT is a frame total, and only right after a boundary it
  actually belongs to.

### Pseudo-registers (Stella 7.0)

- `_scan` does NOT work — resolves to $00 (CXM0P)
- `breakif {_scan == N}` is UNRELIABLE
- Use `breakLabel` + Scn field instead

### Lessons Learned

**F6 hotspot MIRROR zone = $FFF6-$FFF9 — no fetched byte may ever live there
(2026-09-30, E4 moth exit tramp frame-3 crash):** Stella's
`CartridgeEnhanced::peek` (`CartEnh.cxx:157`,
`if(hotspot() >= 0x80 && checkSwitchBank(address & ADDR_MASK, 0) && myRandomHotspots)`,
`ADDR_MASK=$1FFF`, F6 `hotspot()=$1FF6`) calls `checkSwitchBank` on **reads** —
the side effect fires even when `myRandomHotspots` is false (the `&&` already
evaluated it). So ANY instruction fetch at `$FFF6-$FFF9` (the only addresses in
code space with `addr & $1FFF ∈ $1FF6-$1FF9`) switches banks MID-INSTRUCTION.
Real F6 is write-only (reads don't switch), so this bites Stella only — but the
frame died exactly like hardware: the E4 moth exit pad at $FFF2 was
`sta $1FF6 / jmp UE_Next`; the `jmp`'s operand fetches at $FFF6/$FFF7 flipped
bank0→bank1 → operand hi read as $00 → `jmp $007D` → bank1 FF-fill runaway →
HUD ran a 2nd time (+48 lines = 359/360-line frames) → each rogue Overscan
re-entry leaked ~5 stack bytes → SP decayed $FF→$E1 over ~6 passes (~3 frames)
→ `jsr RefreshEnemyY`'s return address (pushed at $01E0/$01E1) was the
FetchPtr mirror, clobbered by DeriveEnemyY staging $FAC5 → `rts` → font data →
SLO/JAM at $FAC9. **py65 could never see this** (its F6 mapper peeks pure ROM).
Fix: exit pad moved to $FC49 (main headroom, `.ds $FC49 - *, 0` pin);
guard `check_moth_tramp` now asserts `$FFF2-$FFF9` = fill in bank0/bank2.
**Rule: treat `$xFFF6-$xFFF9` as reserved; before placing ANY code near
$FFFx, check `addr & $1FFF` against $1FF6-$1FF9.** Recognize this bug family:
sprite/enemy "teleports" + wall pass-through + odd frame lengths + a counter
that decays in steps then never completes → look for a hidden bank flip, then
for stack decay from mid-frame re-entries.

**Tagged Stella trace recipe (needed to SEE addresses):** the pc column only
prints when `disasm.list` has a tag ≥ pc; that list loads when the debugger
prompt first shows (`loadListFile` from `PromptWidget::_firstTime`), which also
runs the ROM-dir script. **The two trace scripts are kept RENAMED to
`*.tracebak` by default** — `src/savior.script.tracebak` and
`~/.config/stella/autoexec.script.tracebak` (both = `logTrace` + `run`); while
active they trace EVERY instruction (millions of lines) and make the game
crawl. To trace: `mv` both back to their exact names (`savior.script` /
`autoexec.script`), run `timeout --signal=KILL 10 stella -debug -loglevel 2
-logtoconsole 1 savior.bin`, then rename them to `*.tracebak` again.
**Stella 7 persists settings in `~/.config/stella/stella.sqlite3` (table
`settings`, no .ini)** — `logTrace` writes `dbg.logtrace=1` there and it
survives sessions, so plain runs keep tracing after a trace session. Reset
after any trace (python sqlite UPDATE): `dbg.logtrace=0`, `logtoconsole=0`,
`loglevel=0`. Symptom of a dirty db: `stella savior.bin` prints a `trace` line
per instruction (game crawls).
— do NOT add `-dbg.logtrace 1` on the CLI (with `-debug` it produced zero trace
lines). Health check WITHOUT addresses (no scripts, no debugger):
`timeout 10 stella -loglevel 2 -logtoconsole 1 -dbg.logtrace 1 savior.bin` —
gives frame/scn/A/X/Y/SP only. Bytes/disasm columns come from the stale
`src/savior.lst` (Sep 16) — trust only
the address + bank columns (bank = `getBank(pc)` at trace time; during the HUD
band, `1/f57d` = the score loop, not the dispatch). Health check: per-frame max
scn must be 262 and min SP ≥ $F9 after boot.

**Explosion flicker = VBL overrun from elapsed-counter loops + per-frame full
PF rebuild (2026-09-29):** the bomb explosion flickered (263-line frames) only
late in state2's 60 frames. Three costs compounded: (1) old `.BgBlink` was an
elapsed/3 subtract loop whose iteration count grew 0→~19 (≈171c) as the
animation aged; (2) `ApplyBombWalls` thin-wall punch +224c per blast; (3) a
full `LoadPFBuffer` (9 folds ≈384c) ran EVERY frame. Worst VBL 1539c >
`TIM64T #23` = 1472c window → VBL ended after the timer → 263-line frame →
flicker. Fixes: constant-time blink `and #3 / tay / lda BombBlinkColors,Y`
(60 frames = 15 exact phase cycles — iteration count fixed forever);
`LoadPFBuffer` split so VBL calls `LoadPF0Only` (3 folds ≈130c, −254c/frame)
and the full rebuild runs only on `EnterRoom` (tail-jmp keeps the stack
guard). Worst VBL 1539→1235c, margin +237c.
*[Postscript S3.4: the VBL `LoadPF0Only` call is now GONE entirely —
`EnemyRamY` moved to `$E2`, so `$C3-$C5` are never stomped and VBL does no
PF rebuild at all (EnterRoom only). The routine survives as
`LoadPFBuffer`'s tail jump. Lesson stands.]*
**Rule:** budget VBL at the
worst path × the LATEST-in-animation iteration count, not the first frame;
elapsed-counter/subtract loops are forbidden in VBL (they age) — use a table
index gated by frame phase. Recount from `bank0.lst` after any VBL growth.

**Stack pushes are INVISIBLE to byte-audits — audit stack DEPTH, not operand
bytes (2026-09-28, bomb never explodes in level 2):** BombTimer ($F7) went
down then bounced back up forever ($33↔$3B), fuse never reached 0, state
stuck at 1, bomb consumed but never exploded. Root cause: the CPU stack page
$0100-$01FF **mirrors** ZP $80-$FF, and the deep call chain
`frame → StepDown → PlayerHitsMap → rect-walk → jsr FoldIndirect` (5 levels)
drove SP to **$F6** — so JSR return-address bytes ($3B = PCL) were pushed
onto $01F7/$01F6 = physically BombTimer/BombX. The fuse `dec` dragged the
byte down, the next frame's stomp shoved it back → the exact bounce the grid
watch showed. **A byte-audit can NEVER find this**: JSR pushes are hardware
writes to $01xx, not instructions with $F7 in their operands. And repeated
pushes of the SAME value (same call site → same PCL) look like no-ops, which
is why the watch showed "unchanging" bytes for a while. The P3.6 fold
refactor added one jsr level per fold — each level moves the danger line
down 2 bytes; the old inline `lda (MapPtrLo),Y` walks had zero extra stack.
**Rule:** any ZP variable at or above the MEASURED deepest SP is unsafe —
measure min-SP in a headless sim (`sim_bomb_fuse.py` write-tracking +
push-trace), never infer safety from "no instruction writes that address".
Symptom signature: a counter/modulo that counts down, then JUMPS back up in
a stable bounce band, while related state machines never complete.

**`TickCounter` is the 60-frame GAME timer — never derive periodic motion from
it beyond `& 7` (2026-09-27, E-gate: spider teleport):** it decrements 60→1
and reloads, so any `>>3` gate only ever sees 0..7 and counts DOWN (0→7 wrap =
sprite jumps to the bottom once per second). Symptom signature: sprite descends
N pixels then **instantly teleports** back to spawn, forever. Fix: free-running
frame clock — `inc EnemyRamP` ($C2, was reserved for moth flags) once per
frame in `RefreshEnemyY`; all derive gates index off it. Alignment rule: the
motion phase period must divide 256 (the clock's wrap) or the wrap shows as a
jump — 48-step phases are impossible; 64-step (gate ÷4) works, and a **dwell
zone** (delta 0 at the wrap landing) hides it entirely. Bat gate = `clock>>1`
(1 px/2f), tentacle bob = `clock>>3`, spider = `clock>>2` + dwell.

**`PlayerHitsMap` clobbers X — save/restore the caller's X around it
(2026-09-27, E-gate: tentacle X frozen):** PHM calls `YToCellRow`, which does
`tax` (X = bottom tile row). `UE_Tentacle` documented "X preserved" and used
X after the probe: `sta EnemyRamX,X` wrote the candidate into
`EnemyRamX[row]` (out of the slot), so the tentacle's real X never changed —
sprite bobs vertically (Y is derived) but never moves horizontally, with NO
error and no crash. Symptom signature: one axis works, the other silently
does nothing after a `jsr` collision helper. Rule: any routine that calls
`PlayerHitsMap`/`YToCellRow` must push/pop X (`txa/pha ... pla/tax` — PLA
does not disturb C, so probe carry survives) unless it provably does not use
X after the call. Static PHM simulation (rect walk at the spawn box) showed
CLEAR — the position math was fine; the register was the bug.

**Kernel row splits must preserve per-pass line totals exactly (2026-09-27,
water strip):** each `.Row` pass costs 1 setup line (ends `sta WSYNC`) + N
`.Line` bodies. Splitting row 2's 48 bodies into 36 + a `.WaterRow` pass
(setup + 11) keeps `1+48 = (1+36) + (1+11)` — frame length unchanged. Adding
a pass with 12 bodies would add one scanline/frame (roll risk). When editing
kernel structure, count WSYNC executions before/after; comment cycle counts
are stale the moment code changes.

**Bank0 space discipline (2026-09-27, E1-E3): main ends ≤ `$FC68`, post-pad
is full — compress DATA before building fold machinery:** `DeriveEnemyY` +
tentacle arm overflowed main (over by 34B). Cheapest fix = compress lookup
tables with **floor-nesting**: `YToRowTable` was 192B indexed by A (A/48);
reindexed by `A>>2` = 48B table — `floor(floor(A/4)/12) == floor(A/48)`, cost
+4c/call. Freed 144B (headroom 4→106B) with zero behavior change. When a
growing dispatch hits the assembler's 127-byte branch limit, do NOT pad
branches — extract a `jsr` subroutine (`UE_Tentacle` after `UE_Exit`, jsr is
absolute) and put the NEW type check FIRST in the dispatch so existing
branches keep their original (short) ranges. E4 moth needs ~95B vs ~33B free:
space options (fold machinery vs more compression vs shared probe helper)
must be decided with the user. Also verified: all overscan `Temp` consumers
(input/hot-bump) run BEFORE `jsr UpdateEnemies`, so UE's probe may own Temp.

**ZP alias lifetime — an alias over a per-frame-refreshed buffer needs its
OWN writer in your read window (2026-09-26, enemy Y at $C3; mechanism
retired S3.4 but the rule is permanent):** `EnemyRamY` was aliased over
`PF0Buf` rows 0-2. The E0 design listed overscan as the
writer and VBLANK as a reader, but `LoadPFBuffer` ALSO writes $C3 every
VBLANK — so after the first frame, draw read PF garbage: **symptom = object
renders for one frame, then vanishes forever** (not a draw/collision bug).
Fix was `RefreshEnemyY` rewriting the alias at overscan entry every frame;
**permanent fix landed in S3.4**: the alias was deleted (Y got private
bytes `$E2-$E4`) and the `$F0-$F2` bomb-save ↔ ColupfBuf save/restore pair
was deleted too (S3.0b — it had been a no-op since the 12-row era).
**Rule before choosing an alias address:** map EVERY writer to those bytes
across the whole frame (including periodic refreshers like
the bank1 HUD), then make sure one of YOUR writers runs after the last
foreign writer and before your next read — every frame, not just at init.
Encode the ordering in verify_build/test (guards exist for exactly this),
and remember the blanket form of this rule: the **stomp-zone rule**
(`check_equ_sync` enforces it — persistent state below `$E0`, see
docs/zp_layout_skill.md Critical Rule 6). The tentacle-inside-walls bug
(2026-10-01) was exactly this family: rect4.h landed on `$E0`, bank1's
scorePtr1 zeroed it every HUD frame.

**Collision misalignment (2026-09-21):** A `jmp .Div15Loop` in SetObjectXPos
added 3 cycles (1 pixel) to RESP0 timing, shifting the sprite's pixel position
right while the collision code expected it left. This caused the player to stop
1+ pixels away from walls. **Fix:** Remove any extra instructions before the
div15 loop — the comparison branch's SetObjectXPos is the reference.

**Branch page-cross in a cycle-tuned loop (2026-09-26, laser S1) — recurrence
of the 2026-09-21 family, via a different mechanism:** a 3-byte `jsr LaserInput`
inserted before SetObjectXPos moved it `$F8F7→$F8FA`, pushing
`bcs .Div15Loop` across the $F8/$F9 page. A taken branch costs 4c across a page
vs 3c within one, so the div15 loop ran at **6c per iteration instead of the
5c contract** — each "15 color-clock" coarse step burned 18, and RESP0 fired
3 color-clocks late **per step** (amplified by the loop, up to ~10 iterations).
- **Symptom signature (recognize BEFORE hunting logic):** sprites render right
  of their logical X by ~3×(X/15) px — drift **grows with X**; far-right
  objects (X≈140) overflow the 160-px window and the position counter wraps
  to the **left edge** (looks like an enemy "teleported across the map");
  player visually ghosts through walls although logical (RoomX) collision is
  intact. "Enemy on wrong side of screen + wall pass-through" = positioning
  TIMING, not collision/enemy code.
- **Rule: ANY size change (even one `jsr`) placed before cycle-tuned code can
  flip a taken branch's page.** After adding/removing bytes in bank0 pre-pad
  code, recheck page contracts from `bank0.lst` — never from comments (the
  ObjSprites comment had already gone stale). Kernel `.Line` fetches to recheck:
  `lda ObjSprites,X` (abs,X), `lda PlayerColTable,Y` (abs,Y),
  `lda (Grp0Ptr),Y` (zp,Y), plus SetObjectXPos's `bcs`.
- **Fix:** SetObjectXPos relocated (byte-identical, address-only) into the
  single-page `$FF10-$FF1F` gap (between the 15-byte fineAdjust table at $FF00
  and `org $FF20`) — the 5c contract is now structural. Note the post-pad
  region was already at 100% capacity (ObjSprites ended exactly at $FF00), so
  that gap was the only free code space.
- **Guards (verify_build.py fails the build):** (1) `bcs .Div15Loop` must
  share a page with `.Div15Loop`; (2) `.Div15Loop` must be in `$FF12-$FF1B`;
  (3) `ObjSprites+71` must stay in-page. Do not weaken these.

**PF0 bit order (2026-09-21):** TIA PF0 has bit 4 = leftmost pixel, NOT bit 7.
The mapping `0x10 << col` is correct. Do NOT "fix" this — it was verified
empirically and matches the comparison branch.

**WSYNC off-by-one overrun — RECURRENCE (2026-09-25):** This exact bug class
has bitten us multiple times (see the `.Line` comment history: "jmp on the hot
path" double-height sprite, and now this). One-cycle-late `sta WSYNC` in the
kernel `.Line` loop stalls a FULL scanline per affected line.

- **Symptom → cause map:** player on same row as enemy/snake → that cave row
  stretches down, HUD pushed down, enemy renders 2× tall (duplicated scanlines);
  GRP1 object flicker (`SelectActiveObject` rotation) makes the overlap
  present only on SOME frames → frame length alternates 262/274 → screen
  oscillates up/down by ~12 lines (one tile) until the object disappears
  (e.g. bomb explodes). If you see these, suspect cycle overrun FIRST.
- **Root cause:** worst path (player sprite in-range + GRP1 object in-range)
  body was 66c, but the `.Line` budget comment claimed 60c — `sta WSYNC`
  started at c74 and its write landed on cycle 76 = one cycle late. The
  comment had an off-by-one; nobody recounted after the sprite code grew.
- **Fix:** running-Y — seed `Y = A0 = Scanline - RoomY` ONCE at kernel entry
  (`sec/sbc RoomY/tay`), let `.Line`'s `iny` advance it (Y after the graphics
  write = next line's A0). Drops the per-line `lda Scanline/sec/sbc/tay`
  (−10c): worst path 66c → 56c, WSYNC write ≈ c66 (10c margin). Row-11 band
  jsr clobbers Y → `tya/pha ... pla/tay` around it (stack balanced).
- **RULE: never trust cycle counts written in comments.** After ANY change to
  `.Line`/kernel, recount the worst path from `bank0.lst` (instruction
  addresses, include branch page-cross) and keep the WSYNC write ≤ c73.
  Comment budget that is stale by 6 cycles = bug shipped twice.
- **Recurrence #3 (2026-09-29, bank1 HUD +1 line → 263-line frames):**
  `.BarRedFull` (power-bar Fine∈{2,3,4}) line-3 tail = 76c → `.BarGap`
  WSYNC started at c76 = full-line stall → HUD band 51→52 lines →
  frame 262→263 on ~48% of frames (only bar-red frames). Killed by deleting
  `.R3`'s `jmp .BarGap` (jumped to the NEXT instruction, after the red
  boundary write). Bisect method that found it: per-frame landmarks
  k1=`.Row` / k2=`jmp $FC68` pad target / k3=`Overscan` + WSYNC-site
  PCs + cycle gaps per WSYNC index — integer segment sums isolate WHICH
  band grew; WSYNC-count constant ⇒ line SKIP (overrun), not structure.
  **Addresses drift with every code change** (Overscan was $F18A then
  $F182/$F176/$F173 through the S3.x refactors) — resolve each landmark
  from `bank0.lst` at use time, never from this file.
  **Bar rule: content AFTER `sty COLUPF` (post-boundary) is
  table-independent (trim freely); content BEFORE it is table-coupled
  (BarDelay/BarFine/BallX regeneration required).**

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
as existing `AddScore` / `ReloadLevel` (S5.x moved `HotOverlapFlag` to
bank2 instead). `jsr` is absolute, so post-pad placement is fine. Never
move `Overscan` without syncing bank1's `jmp $Fxxx` (ToGameStub at
`$FC70` must match) — this fired 3× in the S3.x refactors alone
($F182→$F176→$F173); the fold-pad byte-identity guard catches it, but
sync the literal by hand.

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
- Score display is 6 digits, right-aligned: `0 0 ScoreTh ScoreHu tens ones` → "000075" for 75 points.
  ptrs 1-2 = leading zero; ptrs 3-6 = value. Max 9999 → "009999".

### Editor flicker budget (2026-09-23)

`MapCanvas`: **max 3 elements/room** (`kMaxRoomElements`) and **max 1 element
per row** (miner/enemy/lamp share a row budget). Warnings via `QMessageBox`.
Rationale: GRP1 is one sprite — more simultaneous objects → more flicker
(rotating `SelectActiveObject`). Restrict at authoring time.

### Open items (refresh 2026-10-01)

- **BombEnemyBlast can kill lamps** (type 5): pre-existing bug — no type
  check in the blast loop. Last seen 2026-09-23, still unverified/fixed.
- **Cross-bank Temp conflict (documented, allowlisted):** bank1 `Temp` =
  `$AD` = bank0's `TickCounter` slot (NOT bank0's `Temp` at `$88`) —
  bank1 uses it as its score-init first-frame flag (`inc` once). Deliberate;
  `check_equ_sync.ZP_ALLOW` records it. Fragile if either side's frame
  phase changes.
- **Tentacle residual (user-accepted):** probe still lets it enter walls
  slightly on the left — PHM's entry uses PLAYER origin/width for the
  candidate box; fix = per-enemy origin offset in `UE_Tentacle`. Details:
  `docs/bank0_refactor_progress.md` (S3.2 entry).

## Skill References

- `docs/zp_layout_skill.md` — Complete zero-page memory map for all banks (bank0/bank1/bank2), with conflict detection rules and historical crash lessons
- `docs/font/48px_score_skill.md` — 48-pixel sprite score technique (NUSIZ copies + VDELP cross-buffer), known bugs, and implementation guide
