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
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "src" / "tests" / "frozen"
L0 = parse_labels(FROZEN / "bank0.lst", {
    "EnemyRamX", "EnemyRamY", "EnemyRamD", "EnemyRamP", "RoomX", "RoomY",
    "vyLo", "vyHi", "Temp", "PlayerBombs", "UpdateEnemies", "EnemyCount",
    "EnemyDataLo", "EnemyDataHi", "EnemyDeadMask", "UEDispatch", "UE_Next"})
OBJ_RAFT_TYPE = 7
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
RAFTER_BASE = 131                  # raft top at tide off=0 (surface 132 - 1:
                                   # the 2-row plank's bottom sits ON the line)
PIN_FIT = 22                       # PLAYER_SPRITE_H (22-row art)
KILL_LINE = 115                    # CheckBandTouch: RoomY >= 115 is water


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
        vyhi=0, pf0=0, pf1=0, pf2=0, slot=0, bombs=0):
    """One RaftBody frame. `lead` seeds the elements ahead of the raft."""
    mem = Mem()
    mem.bank = 1                   # RaftBody lives in bank1 (CallPad target)
    r = mem.ram
    r[X["EnemyRamX"] + slot] = x
    r[X["EnemyRamY"] + slot] = 0x00        # junk: RaftBody must overwrite it
    r[X["EnemyRamD"]] = (1 << slot) if dir_right else 0
    r[X["EnemyRamP"]] = parity
    r[X["PlayerBombs"]] = bombs        # b2-0 bombs, b7 flag, b6-3 ramp level
    # default: a rider is over the raft (the ferry only moves when he is);
    # pass room_x/room_y to place him elsewhere and check the parked case
    if room_x is None:
        room_x = x
    if room_y is None:
        room_y = raft_top(parity) + 2
    r[X["RoomX"]] = room_x
    r[X["RoomY"]] = room_y
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
        vyhi=r[X["vyHi"]], lead=lead, bombs_after=r[X["PlayerBombs"]])


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

    L2 = parse_labels(FROZEN / "bank2.lst", {"LEVEL1_RoomShapes"})
    assert "LEVEL1_RoomShapes" in L2, "frozen bank2 level table label"
    b2 = (FROZEN / "bank2.bin").read_bytes()
    # RaftBody reads NO record field (it lives off EnemyRam*/the playfield), so
    # any bank2 byte that reads 7 in the type slot stages a raft for real. Prefer
    # a hit inside the level-data area so the fake record looks like data.
    base = L2["LEVEL1_RoomShapes"] & 0xFFF0
    off = next((i for i in range(base - 0xF000, 0xF000)
                if b2[i] == 7), None)
    assert off is not None, "no bank2 byte reads 7 to stage a raft type"

    mem = Mem()
    mem.bank = 0                       # UpdateEnemies lives in bank0
    r = mem.ram
    # the raft is a ferry: it only moves while the rider is over it, so the
    # integration case puts him on top (the dispatch proof is the floated Y;
    # the step proves motion still happens through the real path)
    r[X["RoomX"]] = 80
    r[X["RoomY"]] = raft_top(0) + 2
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


def tally_gate() -> None:
    """During the points tally (DropTarget = $FE) the GRP1 slot must draw the
    MINER only — no enemy, no raft, no bomb. That frame bypasses the overscan,
    so RefreshEnemyY never runs while bank1's HUD writes $E0-$EF: EnemyRamY
    ($E2-$E4) is left holding score-pointer bytes, and whatever enemy is drawn
    then appears at a garbage Y (user report 2026-10-18: the raft "moved up to
    the middle of the screen" when the counting started).

    A1 2026-10-20: the body is back in bank0 (C1's bank2 copy is gone), so the
    gate is entered directly again — no pad, no bank switch.
    """
    need = {"SelectActiveObject", "DropTarget", "LevelMinerRoom", "RoomNo",
            "MinerX", "MinerY", "ObjBase", "ActiveObjectX", "ActiveObjectY",
            "FlickerFrame", "BombPacked"}
    L = parse_labels(FROZEN / "bank0.lst", need)
    assert not (need - L.keys()), f"labels missing: {sorted(need - L.keys())}"
    Z = {k: v & 0x7F for k, v in L.items() if 0x80 <= v <= 0xFF}
    km = re.search(r"^OBJ_MINER\s*=\s*(\d+)",
                   (ROOT / "src" / "kernel.asm").read_text(), re.M)
    assert km, "OBJ_MINER EQU not found"
    OBJ_MINER = int(km.group(1))

    def one(miner_room, room_no):
        mem = Mem()
        mem.bank = 0
        r = mem.ram
        r[Z["DropTarget"]] = 0xFE          # the tally / frozen scene
        r[Z["LevelMinerRoom"]] = miner_room
        r[Z["RoomNo"]] = room_no
        r[Z["MinerX"]] = 80
        r[Z["MinerY"]] = 84
        r[Z["FlickerFrame"]] = 40          # the gate must zero it
        r[Z["BombPacked"]] = 0
        r[Z["ObjBase"]] = 0xAA             # sentinel: must be rewritten
        mpu = MPU(memory=mem)
        mpu.pc = L["SelectActiveObject"]
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(4000):
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                break
        else:
            raise AssertionError("SelectActiveObject never returned")
        return r[Z["ObjBase"]], r[Z["FlickerFrame"]]

    obj, flick = one(miner_room=3, room_no=3)
    assert obj == OBJ_MINER, f"the tally must draw the MINER, got ObjBase={obj}"
    obj, flick = one(miner_room=1, room_no=3)
    assert obj == 0xFF, (
        f"the tally must stage NOTHING when the miner is elsewhere, got "
        f"ObjBase={obj} ($FF is the only 'no object' sentinel — 0 is the KEY "
        "design and .SODone would park/stage from a stale Y)")
    assert flick == 0, f"the tally must zero FlickerFrame, got {flick}"


def main() -> int:
    integration()
    tally_gate()

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

    # 4a. TAKE-OFF RAMP (inertia): the state lives in PlayerBombs' spare high
    # bits. While boarded the raft leaves at 1 px/frame and only reaches the
    # 1/2 parity once the level tops out; stepping off clears both, so an empty
    # raft returns at full speed and the next take-off ramps again.
    RAMP_FULL = 0xF8                   # flag + level 15 = spun up
    s = run(80, parity=1, bombs=0x80)  # just boarded -> still slow on an odd frame
    assert s["x"] == 81, f"ramped raft must do 1 px/frame: {s}"
    s = run(80, parity=1, bombs=RAMP_FULL)
    assert s["x"] == 82, f"spun-up raft must do the full 1/2 parity: {s}"
    # even frame while ridden: level +1 (bombs must survive untouched)
    s = run(80, parity=0, room_x=77, room_y=raft_top(0) + 2, bombs=0x05)
    assert s["bombs_after"] == 0x05 | 0x80 | 0x10, (
        f"ramp must advance the level and keep the bombs: {s}")
    # odd frame while ridden: flag only
    s = run(80, parity=1, room_x=77, room_y=raft_top(0) + 2, bombs=0x05)
    assert s["bombs_after"] == 0x05 | 0x80, (
        f"odd frames only arm the flag: {s}")
    # nobody aboard: flag and level cleared, bombs kept -> full speed next time
    s = run(80, parity=0, room_x=0x20, room_y=0x40, bombs=0xF5)
    assert s["bombs_after"] == 0x05, f"empty raft must clear the ramp: {s}"

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

    # 5b. BOXED-IN raft (user report 2026-10-22, level 4 room 4): the authored
    #     row-2 cells (PF0 $90 / PF1 $80 / PF2 $98 = solid logical cols 0,3,4,
    #     15,16,19) leave the raft's x=12 span inside the ledge, so BOTH probes
    #     hit walls and it turns every frame without moving. The rider must
    #     still be PINNED on those turn frames — otherwise he sank through the
    #     raft into the 125 water line and respawned forever ("position keeps
    #     changing, zig-zags").
    #    (feed a FALLING rider: on a turn frame the old code returned before
    #    the pin, so this is the assertion that used to sink him)
    s = run(12, parity=0, room_x=12, room_y=raft_top(0) + 2, vyhi=1,
            pf0=0x90, pf1=0x80, pf2=0x98)
    assert s["x"] == 12, f"the boxed-in raft must not move: {s}"
    assert s["room_y"] == raft_top(0) - PIN_FIT, (
        f"a turn frame must still pin the rider: {s}")
    assert s["vyhi"] == 0, f"turn frame must zero the fall speed: {s}"
    #    long chain: no frame may let him sink (the bug's symptom)
    x, rx, par, d = 12, 12, 0, True
    for _ in range(40):
        r = run(x, dir_right=d, parity=par, room_x=rx,
                room_y=raft_top(par) + 2, vyhi=1, pf0=0x90, pf1=0x80, pf2=0x98)
        assert r["room_y"] == raft_top(par) - PIN_FIT, (
            f"boxed-in chain lost the pin: {r}")
        x, rx, par, d = r["x"], r["room_x"], (par + 1) & 0xFF, r["right"]

    # 5c. DIR BIT (user bug 2026-10-22): the enemy record packs type|dir in one
    #     byte, so a raft authored dir=right reads $87. UEDispatch must mask b7
    #     before `cmp #ENEMY_RAFT` — without the mask the body never ran (no
    #     tide, no motion, no pin) and the rider fell into the water.
    def dispatches(type_byte):
        mem = Mem()
        mem.bank = 0
        r = mem.ram
        r[X["EnemyRamX"]] = 60
        r[X["EnemyRamD"]] = 0x01
        r[X["EnemyRamP"]] = 0
        r[X["RoomX"]] = 60
        r[X["RoomY"]] = 113
        r[X["vyLo"]] = 0
        r[X["vyHi"]] = 0
        mpu = MPU(memory=mem)
        mpu.pc = L0["UEDispatch"]
        mpu.a = type_byte
        mpu.x = 0
        mpu.y = 0
        mpu.sp = 0xFD
        mem[0x1FF] = RTS_SENTINEL & 0xFF
        mem[0x1FE] = RTS_SENTINEL >> 8
        for _ in range(4000):
            mpu.step()
            if mem.bank == 1 and mpu.pc == RAFT:
                return True
            if mpu.pc == L0["UE_Next"]:
                return False
        return False

    assert dispatches(OBJ_RAFT_TYPE) is True, "plain raft record must dispatch"
    assert dispatches(OBJ_RAFT_TYPE | 0x80) is True, (
        "a raft authored dir=right ($87) must still dispatch — mask b7")

    # 6. thrust escapes: while rising (vyHi < 0) the pin is skipped
    s = run(80, parity=0, room_x=77, room_y=raft_top(0) + 2, vyhi=0xFF,
            pf1=0xFF)
    assert s["room_y"] == raft_top(0) + 2, f"rising must not be pinned: {s}"

    # 7. FERRY: with nobody over it the raft PARKS (no motion at all), and the
    # ramp state is cleared so the next take-off ramps again; a rider is never
    # touched. (Position reset on room entry is LoadEnemyRam's job.)
    s = run(80, parity=1, room_x=0x20, room_y=0x40, pf1=0xFF, bombs=0x85)
    assert s["x"] == 80, f"an empty raft must not move: {s}"
    assert (s["room_x"], s["room_y"]) == (0x20, 0x40), f"no rider, no touch: {s}"
    assert s["bombs_after"] == 0x05, f"parking must clear the ramp: {s}"

    print("test_raft: OK (dispatch->tramp->body cross-bank path; FERRY: moves "
          "only while the rider is over it and parks when he leaves; floats ON "
          "the tide-driven water surface (0-3 line drift); take-off ramp "
          "(1 px/frame -> 1.5, cleared on parking, bombs untouched); turns at "
          "PF0/PF1/PF2 ledges incl. the mirrored half; rails hold; a rider is "
          "pinned to the raft's top (113+off, worst case "
          f"{raft_top(0x30) - PIN_FIT}) < {KILL_LINE} and carried)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
