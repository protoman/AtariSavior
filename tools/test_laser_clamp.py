#!/usr/bin/env python3
"""Laser wall regression — CONSUME contract (pass-through guard).

Stages a synthetic thin wall (one D7 cell = 2 display cols) into the PF
buffers at the beam's two band rows (buffers persist across frames —
the kernel only rebuilds them on EnterRoom), holds the fire button from
a fixed RoomX facing the wall, and asserts the contact-missile law
(AGENTS "The Laser Is a Dumb Contact Missile"):

  1. no pass-through: the CANDIDATE tip (CollisionX / CollisionX-7,
     the position LaserHitTest actually tested) is never strictly
     past the wall cell;
  2. wall contact CONSUMES the missile: LaserX == eye on that frame;
  3. beam stays ARMED (b1) — contact never blanks the beam (#9's
     suppress is dead), and the restart is observed at least once.

History: this test was first written (2026-10-10) against the
pass-through bug of the 2026-10-08 contact-missile build — travel kept
stepping +-4px, the tip left the thin wall into air, b1 re-armed and
the bolt was drawn through the wall. A wall-center HOLD clamp was built
to fix it and caused a frame lockup + uncapped travel (AGENTS critical
rule); it was abandoned. The shippable contract is CONSUME: contact
resets LaserX to the eye the same frame — no hold, no clamp, no state.

Run: /home/iuri/python3/bin/python3 tools/test_laser_clamp.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [bytearray(open(SRC / f"bank{i}.bin", "rb").read()) for i in range(4)]

# Model 0 meta/hot zeroing (same as test_laser_wall): strip/hot contacts
# must never masquerade as wall hits in this deterministic probe.
_L2 = {}
for _l in (SRC / "bank2.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+(L1R1(?:MetaA|MetaB))\s*$", _l)
    if _m:
        _L2[_m.group(2)] = int(_m.group(1), 16)
assert len(_L2) == 2, f"bank2 L1R1 meta labels missing: {sorted(_L2)}"
for _n in ("L1R1MetaA", "L1R1MetaB"):
    BANKS[2][_L2[_n] - 0xF000] = 0
for _l in (SRC / "bank2.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+L1R1RoomRects\s*$", _l)
    if _m:
        _a = int(_m.group(1), 16) - 0xF000
        BANKS[2][_a + 1 + 2 * BANKS[2][_a]] = 0   # hot count = 0
        break
else:
    sys.exit("L1R1RoomRects label missing in bank2.lst")

# bank0 labels (addresses move every commit)
LABELS = {}
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$",
                  _l)
    if _m and _m.group(2) not in LABELS:
        LABELS[_m.group(2)] = int(_m.group(1), 16)
PC_STARTFRAME = LABELS["StartFrame"]

# bank2 MothRowTable (LWC maps (RoomY+2)>>2 / (RoomY+3)>>2 through it)
MOTHROW = None
for _l in (SRC / "bank2.lst").read_text(errors="replace").splitlines():
    _l = _l.split(";")[0]
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+MothRowTable\s*$", _l)
    if _m:
        MOTHROW = int(_m.group(1), 16)
        break
if MOTHROW is None:
    sys.exit("bank2 MothRowTable label missing")

# ZP indices (addr & 0x7F)
I_ROOMX, I_ROOMY, I_DIR, I_LASERX = 0x00, 0x01, 0x02, 0x03
I_BOMBP, I_DEADMASK, I_LSTATE = 0x35, 0x3A, 0x40
I_COLLX = 0x0B                     # $8B CollisionX (tested candidate)
I_VYLO, I_VYHI = 0x13, 0x14
PF0BUF, PF1BUF, PF2BUF = 0x43, 0x46, 0x49     # $C3/$C6/$C9 & 0x7F

RANGE_LO = LABELS["LaserInput"]
RANGE_HI = LABELS.get("TallyTramp", 0xFFF0)
rts_pcs = set()
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+(?:[0-9a-f]{2}[ \t]+)+rts\b", _l)
    if _m:
        a = int(_m.group(1), 16)
        if RANGE_LO <= a < RANGE_HI:
            rts_pcs.add(a)
assert rts_pcs, "no LaserInput rts found in bank0.lst"


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x00          # fire held from boot

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            return 0
        if a == 0x000C:
            return self.inpt4
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF6 <= a <= 0x1FF9:
            self.bank = a - 0x1FF6
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return


mem = Mem()
from py65.devices.mpu6502 import MPU  # noqa: E402
mpu = MPU(memory=mem)


def rom2(addr):
    return BANKS[2][addr - 0xF000]


def src_bit(src_col):
    """(buffer index, bit) for a source col 0-19 (LWC's ColOff/ColMask)."""
    if src_col < 4:
        return PF0BUF, 0x10 >> src_col
    if src_col < 12:
        return PF1BUF, 0x80 >> (src_col - 4)
    return PF2BUF, 0x01 << (src_col - 12)


def stage_wall(cols, rows):
    """Clear the beam rows, then one thin cell (2 display cols) solid."""
    for row in rows:
        mem.ram[PF0BUF + row] = 0
        mem.ram[PF1BUF + row] = 0
        mem.ram[PF2BUF + row] = 0
    for col in cols:
        src = col if col < 20 else 39 - col     # right half mirrors
        buf, bit = src_bit(src)
        for row in rows:
            mem.ram[buf + row] |= bit


def run_frame(x, roomy, facing):
    """Pin the world, keep the staged wall alive, run one full frame.

    Returns (LaserX, LaserState, CollisionX) captured at LaserInput's
    rts — CollisionX = the candidate LHT tested (LWC does not modify
    it), LaserX = post-contact state (eye when consumed)."""
    mem.ram[I_ROOMX] = x
    mem.ram[I_ROOMY] = roomy
    mem.ram[I_DIR] = facing
    mem.ram[I_VYLO] = 0
    mem.ram[I_VYHI] = 0
    cap = None
    while True:
        mpu.step()
        if mpu.pc in rts_pcs:
            cap = (mem.ram[I_LASERX], mem.ram[I_LSTATE],
                   mem.ram[I_COLLX])
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            break
    return cap


def main() -> None:
    # ---- boot to the main frame loop ----
    guard = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        mpu.step()
        guard += 1
        if guard > 400000:
            sys.exit("never reached StartFrame")
    frame = 0
    landed = None
    while frame < 400:
        mpu.step()
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            frame += 1
            mem.swchb = 0xFE if frame in (2, 5) else 0xFF
            if mem.ram[I_BOMBP] & 0x80:
                landed = frame
                break
    if landed is None:
        sys.exit("player never landed (BombPacked OnGround)")
    mem.ram[I_DEADMASK] = 0xFF                 # kill all enemies
    y0 = mem.ram[I_ROOMY]
    rows = sorted({rom2(MOTHROW + ((y0 + d) >> 2)) for d in (2, 3)})
    print(f"landed f{landed}: RoomY={y0} beam band rows={rows}")

    # (facing, wall pair display cols, player X, label)
    #   right 24,25: mirror of source cell 7 — cell px 96..103
    #   left   8,9: source cell 4       — cell px 32..39
    cases = [
        (0, (24, 25), 90, "right"),
        (1, (8, 9), 55, "left"),
    ]
    failures = []
    for facing, pair, x, tag in cases:
        pair_lo_px, pair_hi_px = pair[0] * 4, pair[1] * 4 + 3
        eye = min(x + 4, 159) if facing == 0 else x - 4
        stage_wall(pair, rows)
        for _ in range(40):                     # travel until it cycles
            stage_wall(pair, rows)
            run_frame(x, y0, facing)
        trace = []
        consumed = 0
        for f in range(16):
            stage_wall(pair, rows)
            lx, ls, cx = run_frame(x, y0, facing)
            trace.append((lx, ls))
            tip = cx if facing == 0 else cx - 7   # candidate LHT tested
            past = tip > pair_hi_px if facing == 0 else tip < pair_lo_px
            in_pair = pair_lo_px <= tip <= pair_hi_px
            if not (ls & 0x02):
                failures.append(
                    f"{tag} f{f}: beam blanked (LaserState=${ls:02X}, b1 "
                    f"clear) — contact must never suppress the beam")
            if past:
                failures.append(
                    f"{tag} f{f}: candidate tip {tip} PAST the wall cell "
                    f"({pair_lo_px}..{pair_hi_px}) — pass-through")
            if in_pair:
                if lx != eye:
                    failures.append(
                        f"{tag} f{f}: tip {tip} in wall but LaserX={lx} "
                        f"!= eye {eye} — missile not consumed")
                else:
                    consumed += 1
            else:
                if lx not in (cx, eye):
                    failures.append(
                        f"{tag} f{f}: clear candidate {cx} but LaserX={lx} "
                        f"not in ({cx},{eye})")
        if consumed == 0:
            failures.append(
                f"{tag}: no wall contact observed in 16 frames — probe "
                f"geometry broken (consumed=0)")
        print(f"  {tag}: eye={eye} cell={pair_lo_px}..{pair_hi_px} "
              f"consumed={consumed}/16 LX=" +
              ",".join(str(lx) for lx, _ in trace) +
              " b1=" + "".join("1" if ls & 2 else "0" for _, ls in trace))
    if failures:
        print(f"\nFAIL: {len(failures)} assertion(s) — laser must be a "
              f"dumb contact missile (consumed by walls, AGENTS rule):")
        for fmsg in failures[:12]:
            print("  " + fmsg)
        if len(failures) > 12:
            print(f"  ... and {len(failures) - 12} more")
        sys.exit(1)
    print("test_laser_clamp: OK (wall consumes the missile: no "
          "pass-through, restart at eye, beam stays armed)")


if __name__ == "__main__":
    main()
