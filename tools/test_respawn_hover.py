#!/usr/bin/env python3
"""Respawn hover guard (bugs.md #1).

After a respawn the player hovers for a GRACE WINDOW (HOVER_FRAMES = 1.5 s):
holding Up spins the jet up while Y is pinned; once thrust beats gravity
(JetPower >= GRAVITY+1) the hover clears and he lifts off. The grace then
EXPIRES on its own — no Up input (or only sideways input) must start the fall
after ~1-2 s (user report 2026-10-21: the player could stay afloat forever by
moving sideways).

Two checks:
  1. asm structure — DropStep arms Hover, UpdateP0Vertical pins vy while
     Hover, DropArm clears it, DropSpeedTable moved out of post-pad.
  2. a white-box simulation of the physics loop asserting no-fall.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
K = (SRC / "kernel.asm").read_text()
# C2 (2026-10-20): LoadLevel's body lives in bank2 (LoadLevelB2); kernel.asm
# keeps only the pad + the drop-in tail (LF_B0Tail).
B2 = (SRC / "bank2.asm").read_text()

B1 = (SRC / "bank1.asm").read_text()
GRAVITY = int(re.search(r"^GRAVITY\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)
JET_MAX = int(re.search(r"^JET_MAX\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)

# --- 1. asm structure -------------------------------------------------------
HOVER_FRAMES = int(re.search(r"^HOVER_FRAMES\s*=\s*(\d+)", B1, re.M).group(1))
# LoseLife ARMS the hover ($FF = waiting for the first input; user rule: an
# untouched player must not start falling after a death)
ll = K[K.index("LoseLife:"):K.index(".LLStay:")]
assert re.search(r"lda #\$FF\s*\n\s*sta Hover", ll), \
    "LoseLife must arm Hover = $FF (waiting for input)"
# LoadLevel clears Hover (stage entry lands normally): the body moved to bank2
# (C2), the bank0 half must stay a pad-only entry so the drop-in tail runs.
assert re.search(r"\nLoadLevel:\n\s+sta \$1FF8", K), \
    "bank0 LoadLevel must stay the $FC20 entry pad ($1FF8 -> bank2 body)"
loadlvl = B2[B2.index("\nLoadLevelB2:"):]
loadlvl = loadlvl[:loadlvl.index("\n    jmp LF_TailSwap")]
assert re.search(r"sta Hover", loadlvl), "LoadLevelB2 must clear Hover"
# UpdateP0Vertical checks Hover + pins vy (at .Integrate, all paths reach it)
up = K[K.index("UpdateP0Vertical:"):K.index(".DoInt:")]
assert "lda Hover" in up and "sta Hover" in up, "physics must read+clear Hover"
# ...and the bank1 HUD band ticks the grace once per gameplay frame
assert re.search(r"^Hover\s*=\s*\$9C", B1, re.M), "bank1 must map Hover ($9C)"
tick = B1[B1.index("Respawn hover (user rule 2026-10-21)"):]
tick = tick[:tick.index("dec Hover")]
assert re.search(r"lda DropTarget\s*\n\s*bne \.HoverDone", tick), \
    "tick must freeze while a drop-in/title/tally owns the player"
loop = B1[B1.index(".TopGap:"):B1.index(".TGskip:")]
assert "Respawn hover (user rule 2026-10-21)" in loop, \
    "tick must run inside the TopGap padding (the next WSYNC absorbs it)"
assert "cpx #6" in loop, "tick must run on ONE TopGap line only"
assert re.search(r"cmp #GRAVITY \+ 1", up), "lift threshold must be GRAVITY+1"
assert up.index(".Integrate:") < up.index("lda Hover"), \
    "Hover check must sit at .Integrate (clamp jmps there)"
# DropSpeedTable is pre-pad (before the $FBD0 EnterRoom-tramp pin; the old
# $FB00/$FB37 pins died with the overlay move, chunk 4), read abs,Y
tbl = K.index("DropSpeedTable:")
assert tbl < K.index("    .ds $FBD0 - *, 0"), "DropSpeedTable must be pre-pad"

# --- 2. physics simulation (mirrors UpdateP0Vertical's arithmetic) ----------
def simulate(up_held, frames, first_input=None):
    """first_input = frame index of the first direction/fire press (None =
    untouched). Hover = $FF waits for it; the press starts HOVER_FRAMES."""
    vyLo = vyHi = sub = jp = 0
    hover = 0xFF
    roomy = 48
    for f in range(frames):
        if hover == 0xFF and first_input is not None and f >= first_input:
            hover = HOVER_FRAMES           # the press arms the grace
        elif 0 < hover < 0xFF:
            hover -= 1                     # grace ticks down once per frame
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

# untouched player: hovers FOREVER (no fall even after 300 frames)
assert simulate(False, 300) == 48, \
    "an untouched player must not start falling after a death"
# sideways input (no Up): pinned until the press, then during the grace, then
# FALLS on its own
assert simulate(False, 60, first_input=10) == 48, \
    "input must start the grace (still pinned)"
y = simulate(False, 10 + HOVER_FRAMES + 90, first_input=10)
assert y > 48 + 20, f"after the grace the player must fall (got RoomY {y})"
# Up held: never falls, and lifts above the spawn altitude
y = simulate(True, 240)
assert y <= 48, f"holding Up must never fall (got RoomY {y})"
assert y < 48, f"holding Up must lift off (got RoomY {y})"

print("respawn hover OK (GRAVITY=%d JET_MAX=%d; idle pins Y; Up lifts)" % (GRAVITY, JET_MAX))
