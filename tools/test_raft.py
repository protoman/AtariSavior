#!/usr/bin/env python3
"""Raft guard (enemy type 7): the moving, rideable platform.

Drives bank1's real `RaftBody` (the bank0 CallPad target at $F822) in py65, so
the whole body is under the battery: the fixed float line, the 1.5 px/frame
parity step, the playfield-derived turn-around (all three PF arms + the mirrored
right half), the rails, and the ride (carry + Y pin + vy reset) — including the
invariant that matters most: a rider is held well above the 125 water-kill line.

Frozen banks + labels (src/tests/frozen/) only — never the live build.
Run: /home/iuri/python3/bin/python3 tools/test_raft.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "src" / "tests" / "frozen"
L0 = parse_labels(FROZEN / "bank0.lst", {
    "EnemyRamX", "EnemyRamY", "EnemyRamD", "EnemyRamP", "RoomX", "RoomY",
    "vyLo", "vyHi", "Temp"})
L1 = parse_labels(FROZEN / "bank1.lst", {"RaftBody"})
missing = ({"EnemyRamX", "EnemyRamY", "EnemyRamD", "EnemyRamP", "RoomX",
            "RoomY", "vyLo", "vyHi"} - L0.keys()) | ({"RaftBody"} - L1.keys())
if missing:
    sys.exit(f"frozen labels missing: {sorted(missing)}")

RAFT = L1["RaftBody"]
# ZP indices as plain names (bank-independent RAM)
X = {k: v & 0x7F for k, v in L0.items() if 0x80 <= v <= 0xFF}
PF0_R2, PF1_R2, PF2_R2 = 0xC5 - 0x80, 0xC8 - 0x80, 0xCB - 0x80
RAFTER_Y, RAFT_MIN_X, RAFT_MAX_X = 130, 8, 148
PIN_FIT = 12                       # PLAYER_SPRITE_H
KILL_LINE = 125                    # CheckBandTouch: RoomY >= 125 is water


def run(x, dir_right=True, parity=0, lead=0, room_x=None, room_y=None,
        vyhi=0, pf0=0, pf1=0, pf2=0, slot=0):
    """One RaftBody frame. `lead` seeds the elements ahead of the raft."""
    mem = Mem()
    mem.bank = 1                   # RaftBody lives in bank1 (CallPad target)
    r = mem.ram
    r[X["EnemyRamX"] + slot] = x
    r[X["EnemyRamY"] + slot] = 0x00        # junk: RaftBody must overwrite it
    r[X["EnemyRamD"]] = (1 << slot) if dir_right else 0
    r[X["EnemyRamP"]] = parity
    r[X["RoomX"]] = room_x if room_x is not None else 0
    r[X["RoomY"]] = room_y if room_y is not None else 0
    r[X["vyLo"]] = 0
    r[X["vyHi"]] = vyhi
    r[PF0_R2], r[PF1_R2], r[PF2_R2] = pf0, pf1, pf2
    mpu = MPU(memory=mem)
    mpu.pc = RAFT
    mpu.a = 0
    mpu.x = slot
    mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(20000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            break
    else:
        raise AssertionError(f"RaftBody never returned (x={x})")
    return dict(
        x=r[X["EnemyRamX"] + slot], y=r[X["EnemyRamY"] + slot],
        right=bool(r[X["EnemyRamD"]] & (1 << slot)),
        room_x=r[X["RoomX"]], room_y=r[X["RoomY"]],
        vyhi=r[X["vyHi"]], lead=lead)


def main() -> int:
    # 1. it always floats on the water line, not on the authored y
    s = run(80, pf1=0xFF)
    assert s["y"] == RAFTER_Y, f"raft must float at RAFTER_Y: {s}"

    # 2. 1.5 px/frame = 1 px even frames, 2 px odd frames (open water ahead)
    assert run(80, parity=0)["x"] == 81, "even frame must move 1 px"
    assert run(80, parity=1)["x"] == 82, "odd frame must move 2 px"
    assert run(80, dir_right=False, parity=0)["x"] == 79, "left even = -1"
    assert run(80, dir_right=False, parity=1, pf0=0)["x"] == 78, "left odd = -2"

    # 3. turn-around from the PLAYFIELD, one case per PF register, plus the
    #    mirrored right half (display col >= 20 is source 39-col):
    #    PF0 arm: x=12 left -> candidate 11 -> col 0      -> PF0 bit 4
    s = run(12, dir_right=False, pf0=0x10)
    assert (s["x"], s["right"]) == (12, True), f"PF0 ledge must turn it: {s}"
    #    PF1 arm: x=40 left -> candidate 39 -> (39-8)>>2 = col 7 -> PF1 bit 4
    s = run(40, dir_right=False, pf1=0x10)
    assert (s["x"], s["right"]) == (40, True), f"PF1 ledge must turn it: {s}"
    #    PF2 arm + mirror: x=100 left -> candidate 99 -> col 22 -> source 17
    #    -> PF2 bit 5
    s = run(100, dir_right=False, pf2=0x20)
    assert (s["x"], s["right"]) == (100, True), f"mirrored ledge: {s}"
    #    the same PF2 bit must NOT turn a raft merely passing it on the right:
    s = run(60, dir_right=False, pf2=0x20)
    assert s["x"] == 59, f"mirror column misread (turned early?): {s}"
    #    water (open) is what keeps it moving
    s = run(40, dir_right=False, pf1=0x00)
    assert (s["x"], s["right"]) == (39, False), f"open water = keep going: {s}"

    # 4. rails: the right edge stops it, the left edge stops it
    s = run(RAFT_MAX_X - 1, parity=1, pf1=0xFF)
    assert (s["x"], s["right"]) == (RAFT_MAX_X - 1, False), f"right rail: {s}"
    s = run(RAFT_MIN_X, dir_right=False, parity=1, pf0=0xFF)
    assert (s["x"], s["right"]) == (RAFT_MIN_X, True), f"left rail: {s}"

    # 5. the ride: overlapping the raft's upper rows pins the player onto it,
    #    kills the fall speed and carries him by the raft's own step
    s = run(80, parity=1, room_x=77, room_y=RAFTER_Y + 2)
    assert s["room_y"] == RAFTER_Y - PIN_FIT, f"feet must land on the raft: {s}"
    assert s["room_y"] < KILL_LINE, f"rider inside the water line!: {s}"
    assert s["vyhi"] == 0, f"landing must zero the fall speed: {s}"
    assert s["room_x"] == 79, f"rider must be carried by the step: {s}"
    #    ... and the rider keeps riding on later frames (the pin re-applies)
    s = run(82, parity=0, room_x=79, room_y=RAFTER_Y - PIN_FIT, pf1=0xFF)
    assert (s["room_y"], s["room_x"]) == (RAFTER_Y - PIN_FIT, 80), f"re-pin: {s}"

    # 6. thrust escapes: while rising (vyHi < 0) the pin is skipped
    s = run(80, parity=0, room_x=77, room_y=RAFTER_Y + 2, vyhi=0xFF,
            pf1=0xFF)
    assert s["room_y"] == RAFTER_Y + 2, f"rising must not be pinned: {s}"

    # 7. an empty raft is left alone: no carry, no pin
    s = run(80, parity=0, room_x=0x20, room_y=0x40, pf1=0xFF)
    assert (s["room_x"], s["room_y"]) == (0x20, 0x40), f"no rider, no touch: {s}"

    print("test_raft: OK (floats on the water line; 1.5 px/frame parity; turns "
          "at PF0/PF1/PF2 ledges incl. the mirrored half; rails hold; a rider "
          f"is pinned to RoomY {RAFTER_Y - PIN_FIT} < {KILL_LINE} and carried)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
