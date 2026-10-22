#!/usr/bin/env python3
"""Guard: the slot-1 mid-frame HMOVE must not re-apply the player's fine adjust.

`Slot1Hook` repositions the second object mid-frame, which needs its own HMOVE.
At that point HMP0/HMM0/HMBL still hold the PLAYER's, the laser's and the
ball's fine values written in the VBL, so HMOVE applies them a SECOND time: the
player's fine adjust doubles — his drawn X advances 2 px per 1 px of `RoomX`,
sawing +/-15 px as the fine value cycles. That is the "raft zig-zag" the user
reported on 2026-10-22 (only in rooms where two objects span two bands, e.g.
raft + miner).

HMP1 must stay: it is set just above, for the slot-1 sprite itself.

Run: /home/iuri/python3/bin/python3 tools/test_slot1_hmove.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
K = (ROOT / "src" / "kernel.asm").read_text(encoding="utf-8")

if "Slot1Hook:" not in K or ".SHout:" not in K:
    sys.exit("Slot1Hook / .SHout labels missing from kernel.asm")
hook = K.split("Slot1Hook:")[1].split(".SHout:")[0]
assert "sta HMOVE" in hook, "Slot1Hook must still strobe its own HMOVE"
hmove = hook.index("sta HMOVE")
wsync = hook.rindex("sta WSYNC", 0, hmove)
for reg in ("HMP0", "HMM0", "HMBL"):
    at = hook.find(f"sta {reg}")
    assert at != -1, (
        f"Slot1Hook must clear {reg} before its HMOVE (double fine-adjust)")
    assert at < wsync, (
        f"the {reg} clear must come BEFORE the `sta WSYNC` that precedes HMOVE:"
        " ~14 cycles between WSYNC and HMOVE make it a LATE HMOVE, which gives"
        " up part of slot 1's fine shift (sprite snaps in ~4 px steps)")
assert "sta HMP1" not in hook, (
    "HMP1 belongs to SetObjectXPos for slot 1 — do not clear it here")

print("test_slot1_hmove: OK (mid-frame HMOVE clears HMP0/HMM0/HMBL, keeps HMP1)")
