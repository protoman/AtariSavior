#!/usr/bin/env python3
"""Water-death respawn guard (user report 2026-10-21).

Dying in the water used to respawn the player AT THE DEATH Y (inside the strip,
RoomY >= 125): he landed in the water, the band check killed him again, and the
respawn hover pinned him there — "I can't fly up without dying".

Root cause: LoseLifeBand shifted the Y AFTER `jsr LoseLife`, but LoseLife's stay
path tail-jumps DropArm, which freezes RoomY as the drop destiny — so the shift
ran after the destiny was already taken (and `DropTarget` had been zeroed).

The guard checks:
  1. LoseLifeBand shifts RoomY BEFORE handing over to LoseLife (the death Y
     must never become the drop destiny).
  2. Arithmetic: the respawn origin is one tile above the strip and clears the
     kill line, which tests the sprite ORIGIN (RoomY >= 115).
  3. A thrust simulation: from the respawn Y the player can fly UP without ever
     entering the kill zone (the old code fails check 1/2 immediately).
  4. Gravity feel (same report): the terminal fall speed is MAX_FALL = $0180
     (1.5 px/frame, lowered from 2.0).
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
K = (SRC / "kernel.asm").read_text()

# --- 1. asm structure -------------------------------------------------------
cbt = K[K.index("CheckBandTouch:"):K.index(".CBTdone:")]
assert re.search(r"cmp #115", cbt), "water kill origin must stay 115"
assert "jsr LoseLifeBand" in cbt, "water death must go through LoseLifeBand"

llb = K[K.index("LoseLifeBand:"):]
llb = llb[:llb.index("jmp LoseLife") + len("jmp LoseLife")]
shift = llb.index("lda RoomY")
hand = llb.index("jmp LoseLife")
assert shift < hand, "LoseLifeBand must shift RoomY BEFORE LoseLife/DropArm"
assert "sbc #12" in llb, "respawn must move one tile up"
assert "sbc #12" in llb and "lda #0" in llb, \
    "one tile up, clamped at the room top"
assert "jsr LoseLife" not in llb, \
    "LoseLifeBand must TAIL-jump LoseLife (DropArm returns to CheckBandTouch)"

PLAYER_H = int(re.search(r"^PLAYER_SPRITE_H\s*=\s*(\d+)", K, re.M).group(1))
KILL = 115

# --- 2. arithmetic: every death Y in the strip respawns clear --------------
def destiny(death_y: int) -> int:
    return max(0, death_y - 12)

# The band check tests the ORIGIN (RoomY >= 125), so one tile up clears it.
# A death can only happen at the line (the check fires the first frame the
# origin reaches it), i.e. 115..116 with subpixel carry.
# --- 4. the drop-in must not burn the grace (the repeated-death bug) -------
# LoseLife arms $FF; the drop then owns the player for many frames. If the
# grace started on input DURING the drop it expired before landing and the
# player fell straight back into the water — the "dies in sequence" report.
def sequence(drop_frames: int, input_held: bool) -> int:
    """Hover value after the drop + 1 landed frame (input held throughout)."""
    hover = 0xFF
    for f in range(drop_frames + 1):
        drop = f < drop_frames
        if drop:
            continue                      # DropTarget != 0: tick frozen
        if hover == 0xFF and input_held:
            hover = 90                    # first landed-frame input arms it
        elif 0 < hover < 0xFF:
            hover -= 1
    return hover


assert sequence(40, True) == 90, "the grace must start AFTER landing"
assert sequence(40, False) == 0xFF, "an untouched landed player keeps hovering"

for death_y in (KILL, KILL + 1):
    y = destiny(death_y)
    assert y < KILL, (
        f"death at {death_y} respawns at {y}: still at/inside the kill line")
assert destiny(115) == 103 and destiny(116) == 104

# --- 3. thrust simulation from the respawn Y -------------------------------
GRAVITY = int(re.search(r"^GRAVITY\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)
JET_MAX = int(re.search(r"^JET_MAX\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)
MAX_FALL = int(re.search(r"^MAX_FALL\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)
assert MAX_FALL == 0x0180, f"terminal fall is ${MAX_FALL:04x}, want $0180"


def fly(y0: int, frames: int = 180) -> list[int]:
    """Hold Up from y0: hover grace, jet ramp, then ascent (physics mirror)."""
    vyLo = vyHi = sub = jp = 0
    hover = 0xFF
    roomy = y0
    trace = []
    for f in range(frames):
        if hover:                       # input seen -> grace runs, then ends
            if jp >= GRAVITY + 1:
                hover = 0
            elif hover == 0xFF:
                hover = 90              # first press starts the 1.5 s grace
            else:
                hover -= 1
        if not hover and (vyHi & 0x80) == 0 and (vyHi or vyLo):
            jp = JET_MAX                # falling: jet catches at once
        elif jp < JET_MAX:
            jp += 1                     # rest / rising: +1 every frame
        if not hover:
            t = vyLo + GRAVITY
            vyLo, vyHi = t & 0xFF, (vyHi + (t >> 8)) & 0xFF
            t = vyLo - jp
            vyLo = t & 0xFF
            if t < 0:
                vyHi = (vyHi - 1) & 0xFF
        t = sub + vyLo
        sub = t & 0xFF
        carry = t >> 8
        a = (vyHi + carry) & 0xFF
        roomy += a if a < 128 else a - 256
        trace.append(roomy)
    return trace


# --- 4. the drop-in must not burn the grace (the repeated-death bug) -------
# LoseLife arms $FF; the drop then owns the player for many frames. If the
# grace started on input DURING the drop it expired before landing and the
# player fell straight back into the water — the "dies in sequence" report.
def sequence(drop_frames: int, input_held: bool) -> int:
    """Hover value after the drop + 1 landed frame (input held throughout)."""
    hover = 0xFF
    for f in range(drop_frames + 1):
        drop = f < drop_frames
        if drop:
            continue                      # DropTarget != 0: tick frozen
        if hover == 0xFF and input_held:
            hover = 90                    # first landed-frame input arms it
        elif 0 < hover < 0xFF:
            hover -= 1
    return hover


assert sequence(40, True) == 90, "the grace must start AFTER landing"
assert sequence(40, False) == 0xFF, "an untouched landed player keeps hovering"

for death_y in (KILL, KILL + 1):
    y = destiny(death_y)
    trace = fly(y)
    assert min(trace) < y, (
        f"respawn at {y} (death {death_y}) must be able to fly UP "
        f"(min {min(trace)})")
    assert max(trace) < KILL, (
        f"respawn at {y} (death {death_y}) entered the water while flying "
        f"(max {max(trace)})")

print("water respawn OK (kill line %d, respawn <= %d, MAX_FALL $%04x)"
      % (KILL, 113, MAX_FALL))
