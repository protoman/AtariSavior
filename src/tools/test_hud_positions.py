#!/usr/bin/env python3
"""HUD lives row + key: WHERE the squares really are on the scanline.

test_hud_lives.py / test_hud_key.py pin the TIA write COUNTS, values and colours;
nothing pinned the horizontal PIXEL positions, which is what the user sees when a
square is one clock off or the 5th-8th lives drift from the 8-px pitch (commit
4b96b62 moved P1 for exactly that). This test measures them.

Method: the real bank1 HUD band (`MenuMain`) runs in py65 and every TIA write is
logged with its CPU cycle inside the scanline (WSYNC restarts the line at cycle 0).
A small beam model turns the strobes into pixel columns:

    left edge = 3 * k - 68 + D - hm        k = cycle of the RESxx write (a strobe
                                           in HBLANK parks at a fixed column C),
                                           hm = signed top nibble of HMxx at HMOVE

D and C are NOT assumed: they are FITTED on the real `SetObjectXPos_b1` for every X 0..159 and
must come out one constant for the players and one for the ball, against the rule the
rest of the project already relies on (PlayerHitsMap: a player's visible left edge is
X-4 below X=15 and X-7 from there; the ball's is X-7, the async strip window
[BallX-7, BallX]). So the model is pinned by ground truth, then the HUD is measured:

  * lives 1..8: the squares are 4 px wide on an exact 8-px pitch from x=8 (P0 holds
    the first four, P1 starts at x=40: no gap and no overlap at the 4/5 boundary);
  * lives 0: nothing on the row;
  * key held: an 8-px ball at x=125..132, clear of the squares; no key: no ball;
  * every GRP/ENABL write lands BEFORE the beam reaches its object (a late write
    drops the square for that line).

Frozen banks + labels (src/tests/frozen/) only - never the live build.
Run: /home/iuri/python3/bin/python3 tools/test_hud_positions.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = Path(os.environ.get("TEST_FROZEN") or ROOT / "tests" / "frozen")
L1 = parse_labels(FROZEN / "bank1.lst", {"MenuMain", "SetObjectXPos_b1"})
L0 = parse_labels(FROZEN / "bank0.lst",
                  {"PlayerLives", "PlayerBombs", "LevelStartRoom", "LineCount",
                   "BombX", "Level", "TickCounter", "BarLevel"})
Z = {k: v & 0x7F for k, v in {**L0, **L1}.items() if 0x80 <= v <= 0xFF}

WSYNC, NUSIZ0, NUSIZ1 = 0x02, 0x04, 0x05
RESP0, RESP1, RESBL = 0x10, 0x11, 0x14
GRP0, GRP1, ENABL = 0x1B, 0x1C, 0x1F
HMP0, HMP1, HMBL, HMOVE = 0x20, 0x21, 0x24, 0x2A
SPRITE = {RESP0: HMP0, RESP1: HMP1, RESBL: HMBL}

EXPECT_P0_X = 8             # base X 12 -> left edge 12 - 4
PITCH = 8
EXPECT_BALL_X = 125         # base X 132 -> left edge 132 - 7


class TimedMem(Mem):
    """Logs every TIA write as (line, cycle in the line, register, value)."""

    def __init__(self):
        super().__init__()
        self.log = []
        self.line = 0
        self.origin = 0
        self.start = 0           # processorCycles at the start of this instruction
        self.length = 0          # its cycle count
        self.after_wsync = False

    def __setitem__(self, addr, value):
        a = addr & 0xFFFF
        if a < 0x40:
            cyc = self.start + self.length - 1 - self.origin   # the write cycle
            self.log.append((self.line, cyc, a, value & 0xFF))
            if a == WSYNC:
                self.line += 1
                self.after_wsync = True
        super().__setitem__(addr, value)


def run(pc, regs, until, mem=None, steps=200000):
    mem = mem or TimedMem()
    mpu = MPU(memory=mem)
    mpu.pc, mpu.sp = pc, 0xFD
    mpu.a, mpu.x, mpu.y = regs
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(steps):
        op = mem[mpu.pc]
        mem.start, mem.length = mpu.processorCycles, mpu.cycletime[op]
        mpu.step()
        if mem.after_wsync:                  # the CPU resumes at cycle 0 of the next line
            mem.origin = mpu.processorCycles
            mem.after_wsync = False
        if until(mpu):
            return mem, mpu
    sys.exit(f"never reached the end (pc=${mpu.pc:04X})")


def signed_nibble(hm):
    n = hm >> 4
    return n - 16 if n >= 8 else n


def coarse(cyc, d, c_hblank):
    """Left edge BEFORE the fine motion for a strobe at CPU cycle `cyc` of the line:
    during HBLANK (colour clock < 68) the TIA parks the object at a fixed column."""
    return c_hblank if 3 * cyc < 68 else 3 * cyc - 68 + d


def fit_offsets():
    """-> ((D, C) players, D ball): fitted on the real `SetObjectXPos_b1`, so the
    beam model agrees with the rule the project already relies on (PlayerHitsMap:
    a player's visible left edge is X-4 below X=15, X-7 from there; the ball's is
    X-7, the async strip window [BallX-7, BallX])."""
    fitted = {}
    for sel, xs in ((0, range(160)), (4, range(15, 160))):
        ds, cs = set(), set()
        for x in xs:
            mem = TimedMem()
            mem.bank = 1
            run(L1["SetObjectXPos_b1"], (x, sel, 0),
                lambda m: m.pc == RTS_SENTINEL, mem)
            res = next((e for e in mem.log if e[2] == RESP0 + sel), None)
            hm = next((e for e in mem.log if e[2] == HMP0 + sel), None)
            assert res and hm, f"X={x}: no RES/HM strobes"
            left = x - 4 if (sel == 0 and x < 15) else x - 7
            base = left + signed_nibble(hm[3])          # the coarse column
            if 3 * res[1] < 68:
                cs.add(base)
            else:
                ds.add(base - (3 * res[1] - 68))
        assert len(ds) == 1 and len(cs) <= 1, (
            f"sel {sel}: the beam model does not fit the SetObjectXPos left-edge "
            f"rule (visible-strobe offsets {sorted(ds)}, hblank columns {sorted(cs)})")
        fitted[sel] = (ds.pop(), cs.pop() if cs else None)
    return fitted[0], fitted[4][0]


D_PLAYER = D_BALL = None      # fitted in main(): D_PLAYER = (D, hblank column)


def run_band(lives, key):
    mem = TimedMem()
    r = mem.ram
    r[Z["PlayerLives"]] = lives
    r[Z["PlayerBombs"]] = 5
    r[Z["LevelStartRoom"]] = 0x80 if key else 0
    r[Z["BarLevel"]] = 40
    r[Z["LineCount"]] = 0
    r[Z["BombX"]] = 0
    r[Z["Level"]] = 0
    r[Z["TickCounter"]] = 30
    mem.bank = 1
    run(L1["MenuMain"], (0, 0, 0), lambda m: m.pc == 0xFC70, mem)
    return mem.log


def lives_row(log):
    """Positions + patterns on the lives row (the line after the ball's RESBL)."""
    hm = {}
    pos = {}
    ball_line = next(l for l, _c, a, _v in log if a == RESBL)
    row = ball_line + 1
    on = {}
    writes = {}
    for line, cyc, a, v in log:
        if line > row:
            break
        if a in SPRITE:
            if a == RESBL:
                assert 3 * cyc >= 68, "the ball is strobed in HBLANK: not fitted"
                pos[a] = coarse(cyc, D_BALL, None)
            else:
                pos[a] = coarse(cyc, D_PLAYER[0], D_PLAYER[1])
        elif a in (HMP0, HMP1, HMBL):
            hm[a] = v
        elif a == HMOVE:
            for res, h in SPRITE.items():
                if h in hm and res in pos:
                    pos[res] -= signed_nibble(hm[h])
                    del hm[h]
        elif a in (GRP0, GRP1, ENABL) and line == row:
            writes.setdefault(a, []).append((cyc, v))
            if a == ENABL:
                on["ENABL"] = v
    return pos, writes, on


def lit_pixels(pos, writes):
    """-> (squares, ball): the lit pixel columns of P0/P1 (QUAD, 4 px per GRP bit)
    and of the ball, from the FIRST write of each register on the lives line."""
    px = set()
    for res, grp in ((RESP0, GRP0), (RESP1, GRP1)):
        if grp not in writes:
            continue
        pat = writes[grp][0][1]
        for bit in range(8):
            if pat & (0x80 >> bit):
                px.update(range(pos[res] + 4 * bit, pos[res] + 4 * bit + 4))
    ball = set()
    if ENABL in writes and writes[ENABL][0][1] & 2:
        ball = set(range(pos[RESBL], pos[RESBL] + 8))
    return px, ball


def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        sys.exit(1)


def main() -> int:
    global D_PLAYER, D_BALL
    D_PLAYER, D_BALL = fit_offsets()
    for key in (False, True):
        for lives in range(9):
            who = f"lives={lives} key={key}"
            log = run_band(lives, key)
            pos, writes, _on = lives_row(log)
            check(pos.get(RESP0) is not None and pos.get(RESP1) is not None
                  and pos.get(RESBL) is not None, f"{who}: an object was never positioned")
            # the squares themselves
            squares, ball = lit_pixels(pos, writes)
            want = set()
            for i in range(lives):
                want.update(range(EXPECT_P0_X + PITCH * i, EXPECT_P0_X + PITCH * i + 4))
            check(squares == want,
                  f"{who}: lit columns {sorted(squares)}, want squares of 4 px at "
                  f"x={[EXPECT_P0_X + PITCH * i for i in range(lives)]} "
                  f"(P0 at {pos[RESP0]}, P1 at {pos[RESP1]})")
            check(pos[RESP0] == EXPECT_P0_X and pos[RESP1] == EXPECT_P0_X + 4 * PITCH,
                  f"{who}: P0/P1 left edges {pos[RESP0]}/{pos[RESP1]}, want "
                  f"{EXPECT_P0_X}/{EXPECT_P0_X + 4 * PITCH} (P1 flush right of P0's 4 "
                  "squares)")
            # the key ball
            if key:
                check(ball == set(range(EXPECT_BALL_X, EXPECT_BALL_X + 8)),
                      f"{who}: ball columns {sorted(ball)}, want {EXPECT_BALL_X}..{EXPECT_BALL_X + 7}")
                check(not (ball & squares), f"{who}: the key overlaps a life square")
            else:
                check(not ball, f"{who}: a ball is lit without the key")
            # every GRP/ENABL write must land before the beam reaches its object
            for res, grp in ((RESP0, GRP0), (RESP1, GRP1), (RESBL, ENABL)):
                if grp in writes and (grp != ENABL or key):
                    cyc = writes[grp][0][0]
                    check(3 * cyc <= 68 + pos[res],
                          f"{who}: first write of ${grp:02X} at cycle {cyc} (colour clock "
                          f"{3 * cyc}) is after the beam reaches x={pos[res]} (clock "
                          f"{68 + pos[res]}): the first line of the object would be lost")
    print(f"test_hud_positions: OK (beam model fitted: players D={D_PLAYER[0]} "
          f"hblank column {D_PLAYER[1]}, ball D={D_BALL}; 0..8 lives = squares of 4 px on an 8-px pitch from x={EXPECT_P0_X}, "
          f"P1 from x={EXPECT_P0_X + 4 * PITCH}, key ball at x={EXPECT_BALL_X})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
