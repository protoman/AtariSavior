#!/usr/bin/env python3
"""Laser kill-window parity: LaserHitTestBody vs the drawn beam (regression).

Bug (user screenshot screenshots/laser_collision_tip_bug.png): the beam
tip touched an enemy and nothing died.

Convention (proven by the WORKING CheckEnemyHit): both the beam arg A and
the enemy arg EnemyRamX anchor an 8px box at [arg-7, arg] (SetObjectXPos
model: lit-left = arg-7). Overlap therefore needs EnemyRamX in
[A-7, A+7]  <=>  (eX-A)+7 in [0..14]  = adc #7 / cmp #15 — the same
formula CheckEnemyHit uses with RoomX.

S6b (bd9b17d) replaced that with adc #14 (eX in [A-14, A]): a 7px-LEFT
shift that kills in empty space left of the beam and misses every enemy
whose box overlaps the tip from the right — exactly the reported bug.

Drives the real bank2 body (LaserWallClamp with an empty rect cache ->
no clamp, then the enemy loop) and asserts the kill interval in X and Y:

  X: kill iff eX in [A-7, A+7]      (beam [A-7,A] x enemy [eX-7,eX])
  Y: kill iff eY in [RoomY-5, RoomY+3] (beam rows RoomY+2..3 x enemy 8px)

Run: /home/iuri/python3/bin/python3 tools/test_laser_kill_window.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402

SRC = ROOT / "src"

need0 = {"EnemyCount", "EnemyDeadMask", "EnemyRamX", "EnemyRamY", "RoomY",
         "CollisionX", "CollisionEndX", "CollisionCellX", "RcBase",
         "EnemyDataLo", "EnemyDataHi", "PlayerDir", "LineCount",
         "RoomPF0Lo"}
L0 = parse_labels(SRC / "bank0.lst", need0)
need2 = {"LaserHitTestBody", "LEVEL1_EnemyDataTable"}
L2 = parse_labels(SRC / "bank2.lst", need2)
missing = (need0 - L0.keys()) | (need2 - L2.keys())
if missing:
    sys.exit(f"labels missing: {sorted(missing)}")

A = 80                      # clamped beam arg -> drawn [73, 80]
BEAM_Y = 80                 # RoomY -> beam rows 82..83


def fire(mem: Mem, e_x: int, e_y: int) -> tuple[bool, int]:
    """Run one held-frame hit test; return (killed, result A)."""
    r = mem.ram
    r[L0["EnemyCount"] - 0x80] = 1
    r[L0["EnemyDeadMask"] - 0x80] = 0
    r[L0["EnemyDataLo"] - 0x80] = L2["LEVEL1_EnemyDataTable"] & 0xFF
    r[L0["EnemyDataHi"] - 0x80] = L2["LEVEL1_EnemyDataTable"] >> 8
    r[L0["RoomY"] - 0x80] = BEAM_Y
    r[L0["EnemyRamY"] - 0x80] = e_y
    r[L0["EnemyRamX"] - 0x80] = e_x
    r[L0["CollisionX"] - 0x80] = A
    r[L0["CollisionEndX"] - 0x80] = A >> 2      # path cols (no walls anyway)
    r[L0["CollisionCellX"] - 0x80] = A >> 2
    r[L0["RcBase"] - 0x80] = 0                  # empty rect cache -> no clamp
    r[L0["PlayerDir"] - 0x80] = 0
    mem.bank = 2
    mpu = MPU(memory=mem)
    mpu.pc = L2["LaserHitTestBody"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            killed = r[L0["EnemyDeadMask"] - 0x80] == 0x01
            return killed, mpu.a
    sys.exit(f"LHT(eX={e_x}, eY={e_y}) never returned "
             f"(pc=${mpu.pc:04X}, bank={mem.bank})")


def main() -> int:
    mem = Mem()
    # --- X sweep: kill interval must be [A-7, A+7] -----------------------
    kill_x = []
    for e_x in range(A - 20, A + 21):
        killed, result = fire(mem, e_x, BEAM_Y)
        if killed:
            assert result == 0x50, f"kill result A=${result:02X} != $50"
            kill_x.append(e_x)
    want_x = list(range(A - 7, A + 8))
    assert kill_x == want_x, (
        f"kill X window {kill_x} != drawn-overlap {want_x} "
        f"(beam [A-7,A]=[73,80], enemy [eX-7,eX])")

    # --- Y sweep: beam rows RoomY+2..3 vs enemy [eY, eY+7] ---------------
    kill_y = []
    for e_y in range(BEAM_Y - 10, BEAM_Y + 8):
        killed, _ = fire(mem, A, e_y)
        if killed:
            kill_y.append(e_y)
    want_y = list(range(BEAM_Y - 5, BEAM_Y + 4))
    assert kill_y == want_y, (
        f"kill Y window {kill_y} != beam-row overlap {want_y}")

    # --- LWC contact contract (redesign 2026-10-08): the tip test returns
    # A=2 through ReturnPad and NEVER moves CollisionX (the old mid-wall
    # clamp retired with the sweep). Ball strip via LWpSetup marker, M1
    # patch strip via (RoomPF0Lo)+14 px window, mirror walk for the rest.
    def lwc_run(packed: int, tip: int, m1x: int = 0, dead: int = 0
                ) -> tuple[int, int]:
        r = mem.ram
        r[L0["EnemyCount"] - 0x80] = 0          # no enemies -> clean exit
        r[L0["LineCount"] - 0x80] = packed
        r[L0["RoomY"] - 0x80] = BEAM_Y          # beam rows -> band 1
        r[L0["CollisionX"] - 0x80] = tip
        r[L0["CollisionEndX"] - 0x80] = 20      # path cols: full right half
        r[L0["CollisionCellX"] - 0x80] = 39
        r[L0["RcBase"] - 0x80] = 0              # empty cache: buffer = map
        r[L0["PlayerDir"] - 0x80] = 0           # right: tip = CollisionX
        r[L0["EnemyDeadMask"] - 0x80] = dead
        # M1X via the room-data pointer: body reads (RoomPF0Lo),Y=Y=14.
        # Stash at $01EE (mirror of ZP $6E): outside the $01FE/$01FF RTS
        # sentinel aliases ($7E/$7F); body pushes nothing, never writes $6E.
        # ptr 0 => reads $000E = 0 => M1X = 0.
        if m1x:
            r[L0["RoomPF0Lo"] - 0x80] = 0xE0
            r[L0["RoomPF0Lo"] + 1 - 0x80] = 0x01
            r[0x6E] = m1x
        else:
            r[L0["RoomPF0Lo"] - 0x80] = 0
            r[L0["RoomPF0Lo"] + 1 - 0x80] = 0
        mem.bank = 2
        mpu = MPU(memory=mem)
        mpu.pc = L2["LaserHitTestBody"]
        mpu.a = mpu.x = mpu.y = 0
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(5000):
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                return mpu.a, r[L0["CollisionX"] - 0x80]
        sys.exit("LWC run never returned")

    # packed: (right_col+1)<<4 | band mask; band 1 active only
    active = (9 + 1) << 4 | 0x02
    inactive = (9 + 1) << 4 | 0x01
    a, cx = lwc_run(active, 159)
    assert a == 2, f"active strip must return A=2 (got {a})"
    assert cx == 159, f"contact must not move CollisionX (got {cx})"
    a, cx = lwc_run(0, 159)
    assert a == 0, f"sym run must fall to the enemy loop A=0 (got {a})"
    assert cx == 159, f"clear must not move CollisionX (got {cx})"
    a, cx = lwc_run(inactive, 159)
    assert a == 0, f"inactive-band strip must stay transparent (got {a})"

    # --- M1 patch strip: tip px in [M1X-7, M1X] = solid (async block);
    # outside the window / strip destroyed (b4) = transparent -----------
    M1X = 71                                   # models_data M0M1X
    for tip in (M1X - 7, M1X - 4, M1X):        # drawn px window
        a, cx = lwc_run(0, tip, m1x=M1X)
        assert a == 2 and cx == tip, \
            f"M1 tip {tip} must block (A={a}, cx={cx})"
    for tip in (M1X - 8, M1X + 1):             # just outside
        a, _ = lwc_run(0, tip, m1x=M1X)
        assert a == 0, f"tip {tip} outside M1 window must pass (A={a})"
    a, _ = lwc_run(0, M1X, m1x=M1X, dead=0x10)
    assert a == 0, f"destroyed strip must pass (A={a})"
    a, _ = lwc_run(0, M1X, m1x=0)
    assert a == 0, f"no M1 (M1X=0) must pass (A={a})"

    print(f"test_laser_kill_window: OK (X window {kill_x[0]}..{kill_x[-1]} "
          f"= [A-7,A+7], Y window {kill_y[0]}..{kill_y[-1]}, LWC "
          f"strip/M1 contact, CollisionX untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
