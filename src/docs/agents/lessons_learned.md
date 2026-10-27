# Lessons learned (bug post-mortems)

_Dated post-mortems: stack/ZP collisions, hotspot mirror zone, positioning timing, WSYNC overruns, ..._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

### Lessons Learned

**ZP bytes are a PHASE resource — share them by lifetime, and reset at the
handover (2026-10-22).** The title melody held `$9D`/`$9E` (`MelPtr`/
`MelTimer`) even though it only runs on title frames, which blocked the
per-type object height (the cave kernel needs two bytes on BOTH title and
gameplay frames, because the title previews the stage with real objects). Fix:
the melody moved to `$F6`/`$F7` = `BombX`/`BombTimer`, which are dead on title
frames (`DropTarget != 0` → `DropStep` skips the bomb block), and the
`SELECT+RESET` title entry clears them so the theme restarts instead of reading
`MusicMel` with a stale gameplay index. Rule + the audit checklist in
`docs/zp_layout_skill.md` rule 7. **The room-change case obeys the same law**:
every per-room byte (`EnemyDataLo/Hi`, `EnemyCount`, `EnemyRamX/Y/D/P`,
`RoomRectsLo/Hi`, `RoomMetaA/B`, `LevelConnSpare`) is re-derived by
`EnterRoomB2`; a new per-room byte must be staged on that path or it carries
the previous room's value.

**Room entry must refresh the joystick shadow `Temp` (2026-10-20, user
report: the eye snapped right on every transition + a 1 px twitch):** bank0's
overscan input block stages `SWCHA>>4` into `Temp` and keeps reading it for
the rest of the frame. `EnterRoomB2` reuses `Temp` for room/record scratch, so
the stale byte faked a held direction after every exit (room index 0..7 has
bit3 clear = "RIGHT pressed"), flipping `PlayerDir` and walking a pixel.
`bank2.EBLER_Done` therefore re-reads `SWCHA` into `Temp` before `ReturnPad`
(14 B, zero per-frame cost; SWCHA is stable within a frame). **Any future
writer of `Temp` inside the room-load chain must not run after that refresh**,
and any new exit path must return through `EBLER_Done`. Guard:
`tools/test_room_input.py` (stubbed port, three patterns).

**F6 hotspot MIRROR zone = $FFF6-$FFF9 — no fetched byte may ever live there
(2026-09-30, E4 moth exit tramp frame-3 crash):** Stella's
`CartridgeEnhanced::peek` (`CartEnh.cxx:157`,
`if(hotspot() >= 0x80 && checkSwitchBank(address & ADDR_MASK, 0) && myRandomHotspots)`,
`ADDR_MASK=$1FFF`, F4 `hotspot()=$1FF4`) calls `checkSwitchBank` on **reads** —
the side effect fires even when `myRandomHotspots` is false (the `&&` already
evaluated it). So ANY instruction fetch at `$FFF4-$FFFB` (the only addresses in
code space with `addr & $1FFF ∈ $1FF4-$1FFB`) switches banks MID-INSTRUCTION.
Real F4 is write-only (reads don't switch), so this bites Stella only — but the
frame died exactly like hardware: the E4 moth exit pad at $FFF2 was
`sta $1FF4 / jmp UE_Next`; the `jmp`'s operand fetches at $FFF6/$FFF7 flipped
bank0→bank1 → operand hi read as $00 → `jmp $007D` → bank1 FF-fill runaway →
HUD ran a 2nd time (+48 lines = 359/360-line frames) → each rogue Overscan
re-entry leaked ~5 stack bytes → SP decayed $FF→$E1 over ~6 passes (~3 frames)
→ `jsr RefreshEnemyY`'s return address (pushed at $01E0/$01E1) was the
FetchPtr mirror, clobbered by DeriveEnemyY staging $FAC5 → `rts` → font data →
SLO/JAM at $FAC9. **py65 could never see this** (its F6 mapper peeks pure ROM).
Fix: exit pad moved to $FC49 (main headroom, `.ds $FC49 - *, 0` pin);
guard `check_moth_tramp` now asserts `$FFF2-$FFF9` = fill in bank0/bank2
(F4: $FFF4-$FFF9 are the hotspot mirrors).
**Rule: treat `$xFFF4-$xFFFB` as reserved; before placing ANY code near
$FFFx, check `addr & $1FFF` against $1FF4-$1FFB.** Recognize this bug family:
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

**Shared-GRP1 positioning (2026-10-16, bomb render):** the bomb, enemies and
miner all draw on GRP1 (one sprite, flicker 1/N frames). P1's hardware X
(RESP1/HMP1 via SetObjectXPos) must be set on EVERY object frame — ac4c3ee
moved the bomb's SOXP out of the VBL to the drop only, so on bomb-draw frames
`SelectActiveObject` set `ActiveObjectX = BombX` but P1 still pointed at the
last enemy/miner X: the bomb rendered pinned near that object (collision was
correct — only the sprite was wrong). **Fix:** one shared SOXP in
`SelectActiveObject`'s `.SODone` tail (`ObjBase != 0`), deduped from the
miner/enemy paths. Test: `tools/test_bomb_render_x.py`.

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

**Timer-quantization phase straddle at kernel entry = whole-screen ±1
jitter (2026-10-11, bugs.md #29 Class C) — WSYNC-count guards are BLIND
to this family:**

- **Symptom:** whole screen (HUD seam rows 144/194, cave top edge) shifts
  ±1 row on ~half the frames under bomb/thrust input; Stella detector
  shows a 62/58 two-class split of an otherwise identical scene. NOT a
  duplicated row (Class A) — a seam flip.
- **Root cause:** `TIM64T` expires on a 64-cycle tick and the `INTIM`
  poll (`.WaitVBLANK` / `.WaitOverscan`) exits up to 63c late. The
  kernel-entry phase = tick remainder + the band-0 `.Row` setup WSYNC
  gap (~75c) — right at the 76c boundary — so the kernel start line
  oscillated ±1 with the tick phase (measured: first `.Line` WSYNC at
  scn 20 ×100 frames / scn 21 ×51 frames). py65 WSYNC counts stayed
  CONSTANT (cave 147 / HUD 48) the whole time: count-based guards and
  `sim_frame_budget`'s WSYNC-count assertion could never see it.
- **Fix (do NOT remove either):** two re-anchor `sta WSYNC`s —
  (1) `StartFrame` before the VSYNC pulse (overscan-end quant → VSYNC
  phase-lock); (2) after `.WaitVBLANK` with VBLANK still on (VBL quant
  → kernel-entry line-lock; blank line, invisible). Each costs +1 line
  (263→265 wall-model); `OVER_ABSOAD` +1c from code-motion page-cross
  is ledgered in sim_frame_budget.py.
- **RULE 1: the kernel entry must stay WSYNC-anchored.** Any edit that
  puts cycle-variable code between the INTIM poll exit and the first
  kernel WSYNC (or deletes either re-anchor) re-opens the straddle.
  The gap between them is cycle-precise (see the 2026-10-06
  VBL-tail lesson above).
- **RULE 2: count-constant ≠ stable.** When a ±1 seam jitter is
  reported, do NOT trust WSYNC-count or per-section cycle sums — they
  were constant across the whole bug. The oracle that found it: Stella
  `logTrace` SCN distribution at a kernel landmark PC (must be a SINGLE
  value across ≥100 gameplay frames) + the pixel row-probe detector
  (seam rows must form ONE signature over ≥120 frames). Re-run both
  after any kernel-entry/VBL/Overscan timing change.
- **RULE 3: frame-line targets move with re-anchors.** Adding a
  re-anchor WSYNC = +1 wall-model line: update `sim_frame_budget`'s
  265.0 target, `test_phase3_ball`'s {264,265} set, and any comment
  citing the total in the SAME change — leaving one stale = red gate.

**When debugging collision misalignment:**
1. First check if SetObjectXPos matches the comparison branch exactly
2. Check if the fineAdjustTable is identical
3. Check if the PF0/PF1/PF2 data matches what the TIA renders
4. Use Stella to measure actual sprite pixel position vs expected
