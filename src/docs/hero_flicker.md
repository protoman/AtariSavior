# HERO Sprite Flicker Prevention — Investigation (2026-09-30)

**Q: Does HERO avoid flicker by rotating objects between frames (draw object
A only every 3rd frame), or does it draw everything every frame?**

**A: HERO does NOT frame-rotate. Every visible object is drawn EVERY frame.**
Flicker is avoided by multiplexing hardware slots *within* one frame
(mid-frame reposition, VDEL pipelines, NUSIZ copies) — never by dropping
objects on alternating frames.

## Evidence

### 1. Static-scene frames are byte-identical

At boot, gameplay logic is gated off (`$BA=$FF`, see
`hero_death_points.md` §state gating), so the scene is completely static.
Consecutive frames produced **byte-identical TIA write sequences** — full
signature sets (GRP0, GRP1, ENAM1, ENABL, NUSIZ, RESP, colors, PF) had zero
diff across frames 44/45/46 (idle) and 46/48/50/60/62 (joystick perturbed).

Frame-based rotation is time-driven: it would flicker even a frozen scene —
odd frames would show object A, even frames object B. Zero diff on a static
scene therefore rules rotation out. (Write counts confirm: 1468 writes/frame
steady, no periodic every-Nth-frame drop.)

### 2. With gameplay enabled, counts vary smoothly

Clearing the gate (`ram[$BA]=ram[$AD]=0` at frame 30, `ram[$F7..$F9]=$13` to
block instant hero re-death) lets the enemy/hero update loop run: hero moves
under joystick (`$9B` +2/frame right, `$9F` −4/frame). Write totals then drift
1467 → 1465 → 1457 → 1444 → 1442 across frames 30–65 — smooth, never a
sawtooth drop-and-recover pattern that rotation would produce. All 17
consecutive frame pairs (40–57) show per-scanline diffs (80–85 lines each) —
the render reacts to movement every frame instead of waiting a rotation slot.

### 3. Screenshot shows ≥6 elements in one frame

`screenshots/HERO.png`: hero sprite, enemy spark, 3 life icons, 5 bomb
icons, POWER bar, score digits — all simultaneously visible. That exceeds
what time-slicing across frames could produce.

## How HERO fits it all without rotation

- **GRP1 triple-write per scanline** (phases 18/24/28) = VDEL-based pipeline;
  NUSIZ1 written with value `$30` at frame prep.
- **P0 repositioned multiple times per frame**: RESP events at lines
  57/78/96/117/135/156 (values `$A9`/`$00` alternating), feeding 12-line
  GRP0 bands at ~80–91, 119–130, 158–169 — a 39-line cadence matching the
  giant cave rows. One physical player register is reused across Y bands
  *within the same frame* (vertical multiplexing), not across frames.
- **HUD = 13+2 technique**: `JSR $DC00` called at `$D44B`/`$D463`, 11 scanlines
  with Y=`$0A..0`, PF data from `$DC6A/$DC6C/$DC77` tables, VDEL cross-buffer
  between P0/P1, mixed NUSIZ (values `$31`, `$30`, `$83`, `$03` observed).
- **ENAM1 written per line** during the cave band (missile used as extra
  object, no sprite slot needed).

## Caveats (honest scope)

- Boot state: `ram[$BA]=$FF` written at frame 0, `ram[$AD]=$FF` at frame 5 —
  until `$BA` is cleared by us (the game itself clears it only deep in the
  death-sequence path), `D72A → D774 → D9DF` skips ALL gameplay logic every
  frame. Kernel still runs and renders (1468 writes/frame), so rendering
  traces are valid; gameplay-motion claims above come from the
  gate-cleared runs.
- The gate-cleared run armed `$F7,X=$13` in ZP `$F8/$F9` — those bytes are
  stack-page mirrors; fine for a 70-frame probe, do not copy blindly.
- NUSIZ bit-decode of observed values (`$30`, `$83`) was not re-verified
  against the hardware manual this session — quoted as raw values only.

## Consequence for our kernel

Do not rotate objects across frames. HERO's recipe:

1. Every object renders every frame it exists.
2. Same register reused for multiple objects only via mid-frame
   `RESP`/`HMOVE` repositioning (different Y bands) — costs cycles but never
   flickers.
3. Extra width comes from NUSIZ copies and VDEL, extra objects from
   missiles/ball — both frame-stable.
4. Our current `SelectActiveObject` rotation is exactly what HERO avoids;
   if objects flicker in our build, this is the first thing to revisit.

Related but separate: our documented flicker class (263-line frames from VBL
elapsed-counter overruns, AGENTS "Lessons Learned" 2026-09-29) is a
scanline-budget bug, not object rotation — both can coexist as failure
modes; check frame length first, rotation second.
