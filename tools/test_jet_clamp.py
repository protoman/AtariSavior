#!/usr/bin/env python3
"""Jet/thrust guard: the vertical velocity clamp and the thrust integration.

Calls the REAL `UpdateP0Vertical` (bank0) in py65 with a hand-poked airborne
state, so the whole path is under test — the jet ramp/catch, gravity, the
thrust subtraction and the MAX_FALL clamp. No boot, no room data.

Why it exists (bug 2026-10-22): the down clamp compared only the HIGH byte
(`cmp #>MAX_FALL`), so every speed in $0100..$017F was rewritten to exactly
$0180. A falling player's thrust was computed and then thrown away every
frame, so no amount of jet could slow the fall ("he does not stop until
reaching ground", user report). The clamp must compare the low byte when the
high bytes match.

Frozen banks + labels (src/tests/frozen/) only — never the live build.
Run: /home/iuri/python3/bin/python3 tools/test_jet_clamp.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "src" / "tests" / "frozen"
SRC = ROOT / "src"
K = (SRC / "kernel.asm").read_text(encoding="utf-8")

GRAVITY = int(re.search(r"^GRAVITY\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)
JET_MAX = int(re.search(r"^JET_MAX\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)
MAX_FALL = int(re.search(r"^MAX_FALL\s*=\s*\$([0-9A-Fa-f]+)", K, re.M).group(1), 16)
assert MAX_FALL == 0x0180, f"MAX_FALL is ${MAX_FALL:04x}"
assert JET_MAX > GRAVITY, "the jet must out-thrust gravity"

NEED = {"RoomY", "vyLo", "vyHi", "JetPower", "Temp", "Hover", "PlayerYSub",
        "BombPacked", "PF0Buf", "UpdateP0Vertical", "CheckP0Left"}
L0 = parse_labels(FROZEN / "bank0.lst", NEED)
missing = NEED - L0.keys()
if missing:
    sys.exit(f"frozen labels missing: {sorted(missing)}")

BANKS = [(FROZEN / f"bank{i}.bin").read_bytes() for i in range(4)]
Z = {k: v & 0x7F for k, v in L0.items() if 0x80 <= v <= 0xFF}


def vert(vy, jp, up=True, room_y=20, temp=None):
    """One UpdateP0Vertical call; returns the resulting vy."""
    mem = Mem()
    mem.banks_ = BANKS
    mem.bank = 0
    mpu = MPU(memory=mem)
    mem.pc_obj = mpu
    r = mem.ram
    base = L0["PF0Buf"] & 0x7F
    for i in range(9):                       # no walls anywhere
        r[(base + i) & 0x7F] = 0
    r[Z["RoomY"]] = room_y
    r[Z["vyLo"]] = vy & 0xFF
    r[Z["vyHi"]] = (vy >> 8) & 0xFF
    r[Z["JetPower"]] = jp
    r[Z["PlayerYSub"]] = 0
    r[Z["Hover"]] = 0
    r[Z["BombPacked"]] = 0
    # joystick shadow: D0 = Up (0 = pressed)
    r[Z["Temp"]] = (0x0E if up else 0x0F) if temp is None else temp
    # the vertical block is INLINE (falls through into CheckP0Left), so run
    # from its label and stop at the next stage's label
    mpu.pc = L0["UpdateP0Vertical"]
    mpu.sp = 0xFD
    mpu.a = mpu.x = mpu.y = 0
    for _ in range(20000):
        mpu.step()
        if mpu.pc == L0["CheckP0Left"]:
            break
    else:
        sys.exit(f"vertical block never reached CheckP0Left (pc=${mpu.pc:04X})")
    return r[Z["vyLo"]] | (r[Z["vyHi"]] << 8)


# 1. THE BUG: at terminal fall a held jet must actually reduce vy.
#    (Before the fix this came back $0180 — clamped — every frame.)
vy = vert(MAX_FALL, JET_MAX)
want = MAX_FALL + GRAVITY - JET_MAX
assert vy == want, (f"thrust did not slow a terminal fall: vy ${vy:04X}, "
                    f"want ${want:04X} (clamped back to MAX_FALL?)")

# 2. The brake must finish: 10 frames from terminal to rising.
v = MAX_FALL
frames = 0
for _ in range(30):
    v = vert(v, JET_MAX)
    frames += 1
    if v >= 0x8000:                          # rising (two's complement)
        break
assert frames <= 12, f"a held jet needs {frames} frames to arrest a fall"

# 3. The clamp still caps a real overspeed (2.0 px/frame, no thrust).
vy = vert(0x0200, 0, up=False)
assert vy == MAX_FALL, f"fall cap broken: vy ${vy:04X}, want ${MAX_FALL:04X}"

# 4. Under 1 px/frame the clamp must not touch the value.
vy = vert(0x00C0, 0, up=False)
assert vy == 0x00C0 + GRAVITY, f"sub-1px fall mangled: ${vy:04X}"

print(f"test_jet_clamp: OK (GRAVITY={GRAVITY} JET_MAX={JET_MAX} "
      f"MAX_FALL=${MAX_FALL:04X}; terminal fall arrested in {frames} frames; "
      f"overspeed still capped; sub-1px falls untouched)")
