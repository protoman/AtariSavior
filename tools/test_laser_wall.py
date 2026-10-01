#!/usr/bin/env python3
"""Laser wall-clamp end-to-end probe (py65, assert-based).

Boots savior.bin headless, waits until the player lands, kills all enemies
(no interference), then for BOTH facings sweeps the player across X (fire
held; RoomY pinned + vy zeroed each frame so inputs are deterministic) and
compares the asm's LaserBeamOn every frame against an independent
column-space reference that reads the SAME runtime rect cache ($89 count,
$CC rects).

Reference = intended behavior (S6 spec):
  path = [min(eye, lo) .. max(eye, lo+7)] in px, converted to real columns
  (rect cache = text columns 0-19 + band rows; both the left-half span and
  the mirrored span of each rect are tested), bestCol = first occluding
  column, raw width = bestCol*4 - lo (<=0 => beam blocked), width clamped
  to 8 then floor-pow2 (NUSIZ 1/2/4/8 px), END-FLUSH draw position
  (beam touches the wall: drawLo = wallPx - width when a wall was found),
  bound = width + 7 packed into LaserBeamOn = $02 | bound<<4
  (bits5-4 = NUSIZ M0 width code consumed by the VBL restore).

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
I_RECTCOUNT = 0x12              # $92
I_COLLX = 0x0B                  # $8B
I_AOX, I_AOY = 0x37, 0x38       # ActiveObjectX/Y = $B7/$B8
RECTS0 = 0x4C                   # $CC & 0x7F


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


def band(line: int) -> int:
    return line // 48 if line < 192 else 3


def spec(roomx, roomy, facing, phase, count, rects):
    """Return packed LaserBeamOn (0 = blocked/off). Mirrors the S6 spec."""
    off = (0, 8, 16, 8)[phase]
    if facing == 0:                          # right
        eye = roomx + 4
        lo = eye + off
        if lo >= 160:
            lo = 159
    else:                                    # left
        eye = roomx - 4
        lo = eye - off
        if lo < 0:
            lo = 0
    path_lo = min(eye, lo)
    path_hi = max(eye, lo + 7)
    if path_lo > 159:
        path_lo = 159
    if path_hi > 159:
        path_hi = 159
    plo, phi = path_lo >> 2, path_hi >> 2
    best = phi + 1
    b1, b2 = band(roomy + 2), band(roomy + 3)
    for (x, y, w, h) in rects:
        if w <= 0 or h <= 0:
            continue
        if not (y <= b2 and y + h > b1):
            continue                          # rows: band overlap
        s_lo = x
        if s_lo <= phi:                       # left-half span
            if x + w - 1 >= plo and s_lo < best:
                best = s_lo
        m_hi = 39 - x                         # mirrored right-half span
        if m_hi >= plo:
            m_lo = m_hi - w + 1
            if m_lo <= phi and m_lo < best:
                best = m_lo
    raw = best * 4 - lo
    if raw <= 0:
        return 0, lo, 0, 0                    # fully blocked
    if raw > 8:
        raw = 8
    fw = (1, 2, 2, 4, 4, 4, 4, 8)[raw - 1]    # floor-pow2 (NUSIZ)
    found = best != phi + 1
    if found:
        lo = best * 4 - fw                    # end-flush: beam touches wall
    bound = fw + 7
    return 0x02 | (bound << 4), lo, fw, bound


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
    # sub return points: the two `rts` inside LaserWallClamp (state snapshot)
    rts_pcs = set()
    lc = LABELS["LaserWallClamp"]
    for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+(?:[0-9a-f]{2}[ \t]+)+rts\b",
                      _l)
        if _m:
            a = int(_m.group(1), 16)
            if lc <= a < lc + 0x140:
                rts_pcs.add(a)
    sub_out = None                # captured at the sub's rts

    mismatches = []
    checked = 0
    for facing in (0, 1):
        for x in range(4, 156):
            for _ in range(4):                 # 4 frames = full phase cycle
                mem.ram[I_ROOMX] = x
                mem.ram[I_ROOMY] = y0
                mem.ram[I_DIR] = facing
                mem.ram[I_VYLO] = 0
                mem.ram[I_VYHI] = 0
                sub_out = None
                # run to next frame boundary (LaserInput has run this frame)
                while True:
                    step()
                    if mpu.pc in rts_pcs:
                        sub_out = (mpu.a,                       # packed / 0
                                   mem.ram[I_RECTCOUNT],        # bound/bestCol
                                   mem.ram[I_AOX], mem.ram[I_AOY],  # pLo/pHi cols
                                   mem.ram[I_COLLX])            # lo at entry
                    if mpu.pc == PC_STARTFRAME:
                        break
                phase = mem.ram[I_LSTATE] & 3      # advanced before pos = used
                expected, draw_lo, fw, bound = spec(
                    x, y0, facing, phase, count, rects)
                actual = mem.ram[I_BEAMON]
                checked += 1
                if actual != expected:
                    mismatches.append(
                        f"X={x} dir={facing} phase={phase}: "
                        f"BeamOn=${actual:02X} exp=${expected:02X} "
                        f"(sub: A=${sub_out[0]:02X} RectCount={sub_out[1]} "
                        f"pLo={sub_out[2]} pHi={sub_out[3]} "
                        f"lo={sub_out[4]}) exp_lo={draw_lo} fw={fw}")
    if mismatches:
        print(f"FAIL: {len(mismatches)}/{checked} frames mismatched "
              f"(spec = column-space clamp + end-flush):")
        for m in mismatches[:15]:
            print("  " + m)
        if len(mismatches) > 15:
            print(f"  ... and {len(mismatches) - 15} more")
        sys.exit(1)
    print(f"test_laser_wall: OK ({checked} frames, "
          f"{2 * 152 * 4} pos/dir/phase samples)")


if __name__ == "__main__":
    main()
