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
    "vyLo", "vyHi", "Temp", "UpdateEnemies", "EnemyCount", "EnemyDataLo",
    "EnemyDataHi", "EnemyDeadMask"})
L1 = parse_labels(FROZEN / "bank1.lst", {"RaftBody"})
missing = ({"EnemyRamX", "EnemyRamY", "EnemyRamD", "EnemyRamP", "RoomX",
            "RoomY", "vyLo", "vyHi"} - L0.keys()) | ({"RaftBody"} - L1.keys())
if missing:
    sys.exit(f"frozen labels missing: {sorted(missing)}")

RAFT = L1["RaftBody"]
# ZP indices as plain names (bank-independent RAM)
X = {k: v & 0x7F for k, v in L0.items() if 0x80 <= v <= 0xFF}
PF0_R2, PF1_R2, PF2_R2 = 0xC5 - 0x80, 0xC8 - 0x80, 0xCB - 0x80
RAFT_MIN_X, RAFT_MAX_X = 8, 148
RAFTER_BASE = 125                  # raft top at tide off=0 (surface 132 - 7:
                                   # the bottom row sits ON the surface line)
PIN_FIT = 12                       # PLAYER_SPRITE_H
KILL_LINE = 125                    # CheckBandTouch: RoomY >= 125 is water


def tide_off(enemy_ram_p):
    """Mirror of the kernel's tide triangle, which the raft body also mirrors:
    p = EnemyRamP >> 4; p0-3 -> 0..3 down, p4-7 -> 3..0 up, p8-15 -> rest."""
    p = (enemy_ram_p & 0xF0) >> 4
    if p == 0 or p >= 8:
        return 0
    return p if p < 4 else 7 - p


def raft_top(enemy_ram_p):
    """The raft's top row: it floats ON the moving water surface."""
    return RAFTER_BASE + tide_off(enemy_ram_p)


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


TRAMP = 0xF8C0                 # CallPad_RaftBody (pinned; verify_build guard)


def integration() -> None:
    """The REAL cross-bank path: UpdateEnemies -> UEDispatch ->
    CallPad_RaftBody (bank0 $F8C0) -> bank1 RaftBody ($FDE3) -> ReturnPad.

    The enemy record is faked by pointing EnemyDataLo/Hi at a frozen bank2 byte
    that reads 7 in the TYPE slot (the key record's y byte), so the dispatch
    takes the raft arm for real. This is the case that catches a misplaced or
    mistwinned tramp: the unit cases above enter RaftBody directly and cannot
    see it (a $F82C tramp with no bank1 twin jumped into the body's own bytes).
    """
    b0 = (FROZEN / "bank0.bin").read_bytes()
    b1 = (FROZEN / "bank1.bin").read_bytes()
    a = b0[TRAMP - 0xF000:TRAMP - 0xF000 + 6]
    b = b1[TRAMP - 0xF000:TRAMP - 0xF000 + 6]
    assert a == b and a[:3] == bytes([0x8D, 0xF7, 0x1F]), (
        f"raft tramp ${TRAMP:04X} not twinned: bank0 {a.hex()} bank1 {b.hex()} "
        "(the jmp is fetched from bank1 after sta $1FF7)")
    assert a[3:6] == bytes([0x4C, RAFT & 0xFF, RAFT >> 8]), (
        f"raft tramp target {a[3:6].hex()} != bank1 RaftBody ${RAFT:04X}")

    L2 = parse_labels(FROZEN / "bank2.lst", {"LEVEL1_RoomDataTable"})
    assert "LEVEL1_RoomDataTable" in L2, "frozen bank2 level table label"
    b2 = (FROZEN / "bank2.bin").read_bytes()
    # RaftBody reads NO record field (it lives off EnemyRam*/the playfield), so
    # any bank2 byte that reads 7 in the type slot stages a raft for real. Prefer
    # a hit inside the level-data area so the fake record looks like data.
    base = L2["LEVEL1_RoomDataTable"] & 0xFFF0
    off = next((i for i in range(base - 0xF000, 0xF000)
                if b2[i] == 7), None)
    assert off is not None, "no bank2 byte reads 7 to stage a raft type"

    mem = Mem()
    mem.bank = 0                       # UpdateEnemies lives in bank0
    r = mem.ram
    r[X["RoomX"]] = 0
    r[X["RoomY"]] = 0
    r[X["EnemyRamX"]] = 80
    r[X["EnemyRamY"]] = 0
    r[X["EnemyRamD"]] = 0x01           # slot 0 faces right
    r[X["EnemyRamP"]] = 0              # even frame -> 1 px
    r[X["EnemyDeadMask"]] = 0
    r[X["EnemyCount"]] = 1
    r[X["EnemyDataLo"]] = off & 0xFF
    r[X["EnemyDataHi"]] = (off >> 8) + 0xF0
    r[PF0_R2] = r[PF1_R2] = r[PF2_R2] = 0      # open water ahead
    mpu = MPU(memory=mem)
    mpu.pc = L0["UpdateEnemies"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(40000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            break
    else:
        raise AssertionError("UpdateEnemies never returned (raft dispatch hung)")
    assert r[X["EnemyRamY"]] == raft_top(0), (
        "the dispatch did not reach the raft body (EnemyRamY not floated) — "
        "check the CallPad twin at $F8C0 and the $FDE3 target")
    assert r[X["EnemyRamX"]] == 81, (
        f"the raft did not move through UpdateEnemies: x={r[X['EnemyRamX']]}")
    assert mem.bank == 0, "the raft path must come back to bank0 (ReturnPad)"


def main() -> int:
    integration()

    # 1. it floats on the water SURFACE, not on the authored y
    s = run(80, pf1=0xFF)
    assert s["y"] == raft_top(0), f"raft must float on the surface: {s}"

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

    # 4b. RIDES THE TIDE: the water surface drifts 0-3 lines (the kernel draws
    # the strip as the band's last 12-off lines -> surface 132+off), so the
    # raft's top must be 125+off at EVERY phase: its bottom row stays on the
    # moving surface instead of a hard-coded line.
    for ramp, off in ((0x00, 0), (0x10, 1), (0x20, 2), (0x30, 3), (0x40, 3),
                      (0x50, 2), (0x60, 1), (0x70, 0), (0x80, 0), (0xF0, 0)):
        s = run(80, parity=ramp, pf1=0xFF)
        assert s["y"] == raft_top(ramp) == RAFTER_BASE + off, (
            f"tide p={ramp >> 4}: raft top {s['y']} != surface-7 "
            f"{RAFTER_BASE + off}")

    # 4c. worst-case tide for the rider: off=3 puts the pin at 116, still well
    # clear of the 125 kill line (the pin follows the raft, not a constant)
    s = run(80, parity=0x30, room_x=77, room_y=raft_top(0x30) + 2)
    assert s["room_y"] == raft_top(0x30) - PIN_FIT, f"tide pin wrong: {s}"
    assert s["room_y"] < KILL_LINE, (
        f"rider at the tide's extreme is in the water: {s}")

    # 5. the ride: overlapping the raft's upper rows pins the player onto it,
    #    kills the fall speed and carries him by the raft's own step
    s = run(80, parity=1, room_x=77, room_y=raft_top(1) + 2)
    assert s["room_y"] == raft_top(1) - PIN_FIT, f"feet must land on the raft: {s}"
    assert s["room_y"] < KILL_LINE, f"rider inside the water line!: {s}"
    assert s["vyhi"] == 0, f"landing must zero the fall speed: {s}"
    assert s["room_x"] == 79, f"rider must be carried by the step: {s}"
    #    ... and the rider keeps riding on later frames (the pin re-applies)
    s = run(82, parity=0, room_x=79, room_y=raft_top(0) - PIN_FIT, pf1=0xFF)
    assert (s["room_y"], s["room_x"]) == (raft_top(0) - PIN_FIT, 80), f"re-pin: {s}"

    # 6. thrust escapes: while rising (vyHi < 0) the pin is skipped
    s = run(80, parity=0, room_x=77, room_y=raft_top(0) + 2, vyhi=0xFF,
            pf1=0xFF)
    assert s["room_y"] == raft_top(0) + 2, f"rising must not be pinned: {s}"

    # 7. an empty raft is left alone: no carry, no pin
    s = run(80, parity=0, room_x=0x20, room_y=0x40, pf1=0xFF)
    assert (s["room_x"], s["room_y"]) == (0x20, 0x40), f"no rider, no touch: {s}"

    print("test_raft: OK (dispatch->tramp->body cross-bank path; floats ON the "
          "tide-driven water surface (0-3 line drift, both directions); 1.5 "
          "px/frame parity; turns at PF0/PF1/PF2 ledges incl. the mirrored "
          "half; rails hold; a rider is pinned to the raft's top (113+off, "
          f"worst case {raft_top(0x30) - PIN_FIT}) < {KILL_LINE} and carried)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
