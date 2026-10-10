# Laser wall clamp — beam stops at wall center (no pass-through)

> **SUPERSEDED 2026-10-10 (same day).** The wall-center hold clamp was
> built, caused a frame lockup (cap check read `RectCount`, which
> `LaserWallClamp` clobbers as scratch), and was reverted. The shipped
> contract is **consume-on-contact**: a wall tip-cell (`A=2`) resets
> `LaserX` to the eye the same frame (no hold/clamp/suppress state).
> The flush-hold residual pass-through was then fixed by the b0
> rearm (Option A, `LASER_REARM`) — see `src/bugs.md` item 9 and the
> AGENTS.md "Critical Rule: The Laser Is a Dumb Contact Missile".
> This plan is kept for the root-cause traces only; do NOT implement
> from it.

**User report (2026-10-10):** "The laser is passing through the walls.
The beam should just adjust the max distance it travels to not pass
through the wall. It should stop at max in the center of the wall it is
hitting."

## Root cause (proven with py65 traces, not guessed)

The 2026-10-08 contact-missile redesign made `LaserWallClamp` (bank2,
$F25A) test only the missile TIP cell and return `A=2` (wall). The
bank0 reaction (`kernel.asm .LaserWallOff`, added for #9) only clears
**b1 (armed)** — the beam is blanked for exactly the frames whose tip
sits INSIDE a solid cell. **`LaserX` is never clamped or reset on a wall
hit** (kill/lamp reset to the eye; wall does not — design comment
"contact never moves CollisionX"). But held fire **keeps stepping
LaserX ±4 px every frame** (the cap is `RoomX±20`, far beyond any cave
wall), and b1 is re-armed each held frame (`LASER_ON = b7|b1`).

Trace evidence (test-room model, py65, `/tmp/opencode/laser_lwc_trace.py`):

```
x=137 facing right, fire held (wall = display cols 38-39, the right
mirror of the left border at beam row 1):
 f2  LaserX=153 tip col38 SOLID -> LWpSolid -> b1=off (suppressed)
 f3  LaserX=157 tip col39 SOLID -> LWpSolid -> b1=off (suppressed)
 f4  cand 161 >= 160           -> .LaserInit (eye) -> b1=ON
```

Sequence for a thin wall with air beyond the cap: frames with the tip
in the wall are suppressed, then the tip steps **past the wall's
thickness into air -> LWC reports miss -> b1 stays armed -> the kernel
draws the beam from the eye to a tip BEHIND the wall** = pass-through.
Playfield priority (CTRLPF=$35, D2=1) hides only the segment that
crosses the wall itself, so the bolt visibly re-emerges on the far side
— exactly what the user sees.

So: the bug is not the tip test (it works: LWpSolid fires correctly on
rows `MothRowTable[(RoomY+2)>>2]..[(RoomY+3)>>2]`), it is **travel not
being clamped on contact + suppression being per-inside-cell only**.

## Fix design — idempotent clamp, NO new state bit

The requested behavior: max travel = wall center; beam stays there,
visible, while held.

**Key trick — the clamp is idempotent, so no "clamped" flag is needed.**
A wall hit is one D7 cell = 2 display cols = px `[8k, 8k+7]`. Choose the
clamp so that the NEXT +4 px candidate always lands back inside the
same wall:

| facing | clamp tip px | LaserX | next candidate tip | result |
|--------|-------------|--------|--------------------|--------|
| right  | `8k+3` (pair base `4*(col & $FE)` + 3) | `8k+3` | `8k+7` = last px of the pair = SOLID | contact -> re-clamp to the same `8k+3` (idempotent: `col & $FE` aligns an entered right-col down to the same pair) |
| left   | `8k+4` (exact center) | `8k+11` | `8k+4 - 4 = 8k` = first px = SOLID | contact -> re-clamp to the same `8k+11` |

Every held frame against the wall: travel proposes `clamp+4` -> LWC
tests it -> solid -> clamp overwrites again -> `LaserX` at rts is a
**constant** = wall center. Stable, no oscillation, no state bit, no
travel gate. The beam renders every frame at the clamp (b1 stays armed
— #9's "no beam" semantics are superseded by this user directive).

Right-facing `8k+3` is the deepest safe point (candidate `+4` must stay
in the pair, so the tip cannot reach the exact `8k+4` center without
exiting); left reaches the exact center. With PF priority on, the
rendered beam ends at the wall **face** either way — the center value is
the internal max distance (and the resume point if the wall is later
bombed away). Honest expectation: user sees the beam stop at the wall,
never re-emerge behind it.

### Component 1 — bank2 `LaserWallClamp` (pin $F25A kept)

- Contract change: on solid (`A=2`), **LWC overwrites `CollisionX`
  with the clamp `LaserX` value** (today it promises never to touch it).
  On miss, `CollisionX` untouched.
- Compute at the two solid exits (`LWpSolid`, `.LWm1Solid`), sharing one
  `.LWclamp` tail: `FetchPtr` already holds the display col on the
  PF-walk path (line 602); stage it on the M1 path too (`RectCount` still
  holds the tip px there). Then:
  - right (`PlayerDir=0`): `pair = col & $FE; LaserX = pair*4 + 3`
    (max `38*4+3 = 155` — always a valid SetObjectXPos arg)
  - left: `LaserX = pair*4 + 4 + 7` (guard `>=160 -> 159`, rare
    right-edge case)
  - M1 patch strip (its px span is `[M1X-7, M1X]`, not cell-aligned):
    right `LaserX = M1X-4`, left `LaserX = M1X-3+7` — same stability
    check (candidate lands back inside the strip).
  - Then the existing `lda #2 / jmp $FBF8` return (sta does not touch
    A/Z — flag protocol intact).
- Space: the region right after `LWpSolid` ($F2EF) is **zero slack**
  (S6.5 moth col-gate follows immediately) — the clamp block goes
  **out-of-line** (same pattern as `LWpSetup` @ $F600), entered by `jmp`,
  ending in the same `jmp $FBF8`. Step 0 of implementation = map the
  exact free gap in bank2.lst (candidate: after the LWpSetup block
  ~$F6FC..before the $F767 data slot) and pick one; never consume a
  reserved level-data slot.

### Component 2 — bank0 `LaserInput` (`kernel.asm`)

- `.LaserWallOff` (b1-clear) -> `.LaserWallHold`:
  `lda CollisionX / sta LaserX / jmp .LaserPos` — keeps b1 armed (beam
  drawn at the clamp the same frame), HMM0 positioned by the normal
  `SetObjectXPos` path, buzz continues (b7-gated `UpdateLaserSound`).
  The old suppress block (~9B) is deleted.
- **Reorder the cap check** — required for walls near the cap edge
  (trace case: clamp `155`, candidate `159` > cap `RoomX+20 = 157` ->
  today that eye-resets BEFORE the wall test ever runs). New order:
  1. travel candidate (keep the `>=160` / left-underflow pre-check
     FIRST — LWC must never see col >= 40),
  2. commit + `.LaserGo` (LHT at the candidate),
  3. `A=0` miss -> NOW the cap compare (candidate vs `RoomX±20`) ->
     eye if past, else `.LaserPos`,
  4. `A=2` -> `.LaserWallHold` (clamp), `A=$50`/`A=1` -> kill/lamp ->
     eye (unchanged).
  Cap logic bytes MOVE (not duplicate) into the miss arm; net growth
  expected ~+5..10B.
- Space gate: `LaserInput` ends `$FFE0`, pin `TallyTramp $FFE6` =
  **5B free**. If the net exceeds it, in order: (a) relocate the moved
  cap blocks into the `$FF20`-gap page (same page = short branches
  stay valid), (b) report and stop — do NOT touch `SetObjectXPos`,
  the fold pads, or any pin.

### What we deliberately do NOT do

- No new `LaserState` bit (b3 idea from the first draft — the
  idempotent clamp makes it unnecessary; fewer bits = fewer state bugs).
- No change to `SetObjectXPos`, the kernel `.Line` beam window
  (`BeamMask` on `RoomY+2`), the tip-cell row mapping, enemy kill/lamp
  handling, or CTRLPF (PFP stays on — walls remain opaque).
- No moving of pinned entries (`$F25A`, `$FFE6`, `$FF10` gap).

## Test plan (Build-Test-Build, after every structural edit)

1. **Edit LWC alone** -> `./build.sh` (runs `sim_bomb_fuse` +
   `sim_frame_budget`; LWC entry `$F25A` is keyed by `beam_cols` — keep
   the pin; compare OVER/bad-frame lists before/after).
2. **Edit bank0** -> same sims immediately, before writing tests.
3. `test_laser_close.py`: the wall-contact contract flips —
   `wallish -> b1 clear + HMM0 parked` becomes **`wallish -> b1 STILL
   set + LaserX == clamp + HMM0 positioned (not parked)`**; buzz asserts
   (AUDC0=2/AUDV0=9) unchanged. Rewrite those asserts deliberately, do
   not weaken the buzz ones.
4. `test_laser_wall.py`: extend the travel model with the two new legal
   outcomes — hold frames (`lx == model`, no travel) and first-contact
   frames (`cx == lx` = LWC wrote the clamp) — re-sync model from `lx`
   as today. Anything else still = budget escape.
5. **New pass-through regression assert** (in `test_laser_wall` or a
   small sibling): at a fixed RoomX facing a wall found in PF0/1/2Buf,
   hold fire N frames and assert: `LaserX` converges to the predicted
   pair clamp (`4*(col&$FE)+3` / `+11`), stays constant, `b1` armed
   every frame, and `LaserX` never exceeds the wall pair. This is the
   runnable check for the bug.
6. Full battery (`tools/test_*.py` + title demo) = 23/23 before commit.
7. Stella visual gate (user): beam extends to the wall and holds
   (face-visible, center-clamped), no re-emergence behind walls, buzz
   while held, kill/lamp/reset unchanged, bomb a wall under the held
   beam -> beam resumes from the clamp point.

## Risks / lessons applied

- 6502 flags: `LDX`/`LDY`/`PLA` set Z (bit me in #7(i)) — the clamp
  path sets A last, `sta CollisionX` does not affect flags, `A=2` +
  return protocol re-verified after every edit.
- Cycle budget: clamp math only runs on contact frames (~30-40c);
  bank0 reorder is branch-neutral. Sims are the judge, comments are not.
- Pad discipline: bank2 returns stay on `$FBF8`; no new cross-bank
  jsr; LWC keeps its documented "stack depth unchanged" property (only
  internal jmps, no jsr).
- The `$F25A` / `$FFE6` / fold-pad byte-identity guards stay green —
  if a guard fails, the change is wrong, do not weaken it.

## Steps (execution order)

0. Map exact free space: bank0 `$FF20`-gap content + LaserInput end;
   bank2 gap after LWpSetup. Report numbers before editing.
1. LWC clamp (out-of-line block) + CollisionX contract + docs comment
   rewrite in the LWC header. Build + sims.
2. bank0 `.LaserWallHold` + cap reorder. Build + sims.
3. Fix `test_laser_close` / `test_laser_wall` contracts + add the
   pass-through regression assert. Battery 23/23.
4. bugs.md: new entry (root cause + fix + superseded #9 semantics).
5. Commit (no push). Stella gate for the user.
