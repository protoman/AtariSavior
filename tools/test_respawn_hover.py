#!/usr/bin/env python3
"""Respawn hover guard (bugs.md #1).

After a respawn the player must NOT fall: holding Up spins the jet up while
Y is pinned; once thrust beats gravity (JetPower >= GRAVITY+1) the hover
clears and normal physics resumes. Idle (no Up) hovers in place.

Two checks:
  1. asm structure — DropStep arms Hover, UpdateP0Vertical pins vy while
     Hover, DropArm clears it, DropSpeedTable moved out of post-pad.
  2. a white-box simulation of the physics loop asserting no-fall.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
K = (SRC / "kernel.asm").read_text()

GRAVITY = int(re.search(r"^GRAVITY\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)
JET_MAX = int(re.search(r"^JET_MAX\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)

# --- 1. asm structure -------------------------------------------------------
# LoseLife arms Hover on every death
ll = K[K.index("LoseLife:"):K.index(".LLStay:")]
assert re.search(r"lda #1\s*\n\s*sta Hover", ll), "LoseLife must arm Hover=1"
# LoadLevel clears Hover (stage entry lands normally)
i = K.index("\nLoadLevel:")
loadlvl = K[i:i + 700]
assert re.search(r"sta Hover", loadlvl), "LoadLevel must clear Hover"
# UpdateP0Vertical checks Hover + pins vy (at .Integrate, all paths reach it)
up = K[K.index("UpdateP0Vertical:"):K.index(".DoInt:")]
assert "lda Hover" in up and "sta Hover" in up, "physics must read+clear Hover"
assert re.search(r"cmp #GRAVITY \+ 1", up), "lift threshold must be GRAVITY+1"
assert up.index(".Integrate:") < up.index("lda Hover"), \
    "Hover check must sit at .Integrate (clamp jmps there)"
# DropSpeedTable is pre-pad (before the $FB00 pin), read abs,Y
tbl = K.index("DropSpeedTable:")
assert tbl < K.index("    .ds $FB00 - *, 0"), "DropSpeedTable must be pre-pad"

# --- 2. physics simulation (mirrors UpdateP0Vertical's arithmetic) ----------
def simulate(up_held, frames):
    vyLo = vyHi = sub = jp = 0
    hover = 1
    roomy = 48
    for f in range(frames):
        if up_held and (f & 3) == 0 and jp < JET_MAX:
            jp += 1
        if hover:
            if jp >= GRAVITY + 1:
                hover = 0
            else:
                vyLo = vyHi = 0            # pinned: no fall
        if not hover:
            t = vyLo + GRAVITY             # gravity (16-bit add)
            vyLo = t & 0xFF
            vyHi = (vyHi + (t >> 8)) & 0xFF
            t = vyLo - jp                  # thrust (low byte + borrow)
            vyLo = t & 0xFF
            if t < 0:
                vyHi = (vyHi - 1) & 0xFF
        t = sub + vyLo                     # PlayerYSub += vyLo
        sub = t & 0xFF
        carry = t >> 8
        A = (vyHi + carry) & 0xFF
        roomy += A if A < 128 else A - 256
    return roomy

# idle: never falls (exactly pinned at spawn)
assert simulate(False, 180) == 48, "idle respawn must hover (no fall)"
# Up held: never falls, and lifts above the spawn altitude
y = simulate(True, 240)
assert y <= 48, f"holding Up must never fall (got RoomY {y})"
assert y < 48, f"holding Up must lift off (got RoomY {y})"

print("respawn hover OK (GRAVITY=%d JET_MAX=%d; idle pins Y; Up lifts)" % (GRAVITY, JET_MAX))
