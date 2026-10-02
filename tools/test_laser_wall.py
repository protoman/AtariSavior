#!/usr/bin/env python3
"""Laser wall-clamp end-to-end probe (py65, assert-based) — S6.

Boots savior.bin headless, waits until the player lands, kills all enemies
(no interference), then for BOTH facings sweeps the player across X (fire
held; RoomY pinned + vy zeroed each frame so inputs are deterministic) and
compares, every frame, two things against an independent reference that
reads the SAME runtime rect cache ($89 count, $CC rects):

  1. CollisionX ($8B) captured at LaserInput's rts = the value
     LaserWallClamp left there (also the value SetObjectXPos used).
  2. LaserBeamOn ($83) stays $02 — the beam is an 8px NUSIZ missile; a
     change here means someone re-introduced the rolled-back width
     rewrite (e24d9de: out-of-position/size draws).

Reference = S6b spec (docs/laser_s6_log.md; mirrors bank2 LaserWallClamp).
PIXEL MODEL: drawn M0 = [A-7, A] (SetObjectXPos arg -> box-left arg-7;
PlayerSpriteA lit cols 0-6; PHM lit-left = arg-7 validated by flush wall
stops). Kill test = same [A-7, A].
  raw A: right = min(RoomX+4+off, 159), left = max(RoomX-4-off, 0)
  path cols: right = [nose_R=RoomX-3, A] >> 2, left = [A-7, nose_L=RoomX-4] >> 2
  rows = band(RoomY+2)..band(RoomY+3) (exact LHT kill window)
  per live rect (BombPacked b3-6 clear), spans = [x, x+w-1] and
  [40-x-w, 39-x]; on-path overlap -> first wall col on travel direction:
    right: col = max(slo, c0), cand = col*4+2, min-apply (drawn tip)
    left:  col = min(shi, c1), cand = col*4+9, max-apply (drawn start)
  PLUS independent invariants (not a mirror): when the first wall W is on
  the path, right A in [4W, 4W+2] (tip touches wall, <=2px inside, never
  past face+2), left A in [4W+9, 4W+10] (start <=2px inside the right
  half); with no wall A must equal raw (no spurious clamp).

Run: /home/iuri/python3/bin/python3 tools/test_laser_wall.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(4)]

# labels from bank0.lst (addresses move every commit)
LABELS = {}
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", _l)
    if _m:
        LABELS[_m.group(2)] = int(_m.group(1), 16)
PC_STARTFRAME = LABELS["StartFrame"]

# ZP indices (addr & 0x7F)
I_ROOMX, I_ROOMY, I_DIR, I_BEAMON = 0x00, 0x01, 0x02, 0x03
I_BOMBP, I_LSTATE, I_RCBASE = 0x35, 0x40, 0x09
I_DEADMASK, I_VYLO, I_VYHI = 0x3A, 0x13, 0x14
I_COLLX = 0x0B                  # $8B
RECTS0 = 0x4C                   # $CC & 0x7F

# LaserInput's own rts sites: capture CollisionX there = post-clamp value
# (between LHT and those rts only SetObjectXPos / AddScore run — neither
# writes CollisionX; enemies are all dead in the probe = miss path).
RANGE_LO = LABELS["LaserInput"]
RANGE_HI = LABELS["BeamMask"]
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
        self.inpt4 = 0x00          # fire HELD from boot (probe wants the beam)

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
            self.tia[a & 0x3F] = v


mem = Mem()
from py65.devices.mpu6502 import MPU
mpu = MPU(memory=mem)


def step():
    mpu.step()


def path_cols(roomx, facing, lo):
    """S6b path cols (nose-anchored), mirroring kernel .LaserPos staging."""
    if facing == 0:                          # right: [nose_R, A]
        return max(0, roomx - 3) >> 2, lo >> 2
    return max(0, lo - 7) >> 2, (roomx - 4) >> 2   # left: [A-7, nose_L]


def first_wall(c0, c1, facing, rects, top, bottom):
    """Independent: first solid col on travel direction within [c0, c1]."""
    cols = range(c0, c1 + 1) if facing == 0 else range(c1, c0 - 1, -1)
    for col in cols:
        for (x, y, w, h) in rects:
            if w <= 0 or h <= 0 or not (y <= bottom and y + h > top):
                continue
            for (slo, shi) in ((x, x + w - 1), (40 - x - w, 39 - x)):
                if slo <= col <= shi:
                    return col
    return None


def spec(roomx, roomy, facing, phase, rects):
    """Expected CollisionX after LaserWallClamp (S6b reference)."""
    off = (0, 8, 16, 8)[phase]
    if facing == 0:                          # right
        lo = min(roomx + 4 + off, 159)
    else:                                    # left
        lo = max(roomx - 4 - off, 0)
    c0, c1 = path_cols(roomx, facing, lo)
    top, bottom = (roomy + 2) // 48, (roomy + 3) // 48
    for (x, y, w, h) in rects:
        if w <= 0 or h <= 0:
            continue
        if not (y <= bottom and y + h > top):
            continue                          # rows: band overlap
        for (slo, shi) in ((x, x + w - 1), (40 - x - w, 39 - x)):
            if not (slo <= c1 and shi >= c0):
                continue                      # span off path
            if facing == 0:
                cand = max(max(slo, c0) * 4 + 2, 0)
                if cand < lo:
                    lo = cand                 # min-apply (drawn tip A)
            else:
                cand = min(shi, c1) * 4 + 9
                if cand > lo:
                    lo = cand                 # max-apply (drawn start A-7)
    return lo


def check_invariant(x, y0, facing, phase, rects, actual):
    """Independent geometry check on the captured CollisionX (S6b)."""
    raw = spec_raw(x, facing, phase)
    c0, c1 = path_cols(x, facing, raw)
    top, bottom = (y0 + 2) // 48, (y0 + 3) // 48
    W = first_wall(c0, c1, facing, rects, top, bottom)
    if W is None:
        if actual != raw:
            return f"spurious clamp (no wall on path): {actual} != {raw}"
        return None
    face = W * 4
    if facing == 0:
        if actual > face + 2:
            return f"PASS: tip {actual} > face+2 {face + 2} (W={W})"
        if actual < face:
            return f"GAP: tip {actual} < face {face} (W={W}, short of wall)"
    else:
        if actual < face + 9:
            return f"PASS: start {actual - 7} past wall (A < face+9)"
        if actual > face + 10:
            return f"GAP: start {actual - 7} > face+3 (overshot, A={actual})"
    return None


def main() -> None:
    # ---- boot to the main frame loop ----
    guard = 0
    while mpu.pc != PC_STARTFRAME:
        step()
        guard += 1
        if guard > 400000:
            sys.exit(f"never reached StartFrame (pc=${mpu.pc:04X})")

    frame = 0
    landed = None
    # ---- wait for landing, then freeze enemies ----
    while frame < 400:
        step()
        if mpu.pc == PC_STARTFRAME:
            frame += 1
            if mem.ram[I_BOMBP] & 0x80:
                landed = frame
                break
    if landed is None:
        sys.exit("player never landed (BombPacked OnGround)")
    mem.ram[I_DEADMASK] = 0xFF                 # kill all enemies (no interference)

    # ---- runtime rect cache = ground truth for the reference ----
    count = mem.ram[I_RCBASE]
    rects = []
    for i in range(count):
        b = RECTS0 + 4 * i
        rects.append((mem.ram[b], mem.ram[b + 1],
                      mem.ram[b + 2], mem.ram[b + 3]))
    y0 = mem.ram[I_ROOMY]
    print(f"landed f{landed}: RoomY={y0} rects(count={count})={rects}")

    # ---- deterministic sweep: pin RoomX/Y, dir, vy; fire held ----
    mismatches = []
    checked = 0
    clamped = 0
    for facing in (0, 1):
        for x in range(4, 156):
            for _ in range(4):                 # 4 frames = full phase cycle
                mem.ram[I_ROOMX] = x
                mem.ram[I_ROOMY] = y0
                mem.ram[I_DIR] = facing
                mem.ram[I_VYLO] = 0
                mem.ram[I_VYHI] = 0
                cap = None
                # run to next frame boundary; capture at LaserInput's rts
                while True:
                    step()
                    if mpu.pc in rts_pcs:
                        cap = (mem.ram[I_COLLX], mem.ram[I_BEAMON])
                    if mpu.pc == PC_STARTFRAME:
                        break
                phase = mem.ram[I_LSTATE] & 3
                expected = spec(x, y0, facing, phase, rects)
                checked += 1
                if cap is None:
                    mismatches.append(f"X={x} dir={facing}: no LaserInput rts")
                    continue
                actual, beam = cap
                if beam != 0x02:
                    mismatches.append(
                        f"X={x} dir={facing} phase={phase}: "
                        f"LaserBeamOn=${beam:02X} != $02 (width rewrite?)")
                if actual != expected:
                    mismatches.append(
                        f"X={x} dir={facing} phase={phase}: "
                        f"CollisionX=${actual:02X} exp=${expected:02X}")
                inv = check_invariant(x, y0, facing, phase, rects, actual)
                if inv:
                    mismatches.append(
                        f"X={x} dir={facing} phase={phase}: {inv}")
                if expected != spec_raw(x, facing, phase):
                    clamped += 1
    if mismatches:
        print(f"FAIL: {len(mismatches)} mismatched frames "
              f"(S6 spec = mid-wall tip clamp):")
        for m in mismatches[:15]:
            print("  " + m)
        if len(mismatches) > 15:
            print(f"  ... and {len(mismatches) - 15} more")
        sys.exit(1)
    print(f"test_laser_wall: OK ({checked} frames, "
          f"{clamped} clamped by walls, BeamOn=$02 throughout)")


def spec_raw(roomx, facing, phase):
    """Unclamped lo — for coverage reporting only."""
    off = (0, 8, 16, 8)[phase]
    if facing == 0:
        return min(roomx + 4 + off, 159)
    return max(roomx - 4 - off, 0)


if __name__ == "__main__":
    main()
