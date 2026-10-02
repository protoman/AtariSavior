#!/usr/bin/env python3
"""Laser clamp forensic explorer (temporary tool, not part of the battery).

Random-walks the ROM headless (fire held, RoomY swept for band coverage) and
instruments LaserThinClamp's rts plus a HARD WRITE-WATCH on the rect cache
($89 count, $CC-$DF rects). Every clamp call is checked against an
independent spec; every non-loader write to the cache is reported with the
writing PC/bank/label. Classes:

  W  watched write to RcBase/rect cache (pc, bank, label) — corruption hunt
  A  runtime rects/count DIFFER from the pristine baseline at clamp rts
  B  clamp's best face is not a face of the runtime rects (read-index bug)
  C  asm pack != spec pack (semantic divergence incl. h==0/w<=0 edges)
  D  beam ON while a wall face sits between the eye and C (tunnel state)

Run: /home/iuri/python3/bin/python3 tools/explore_laser.py [frames]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(4)]

LABELS = {}
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_][A-Za-z0-9_]*)(?:\s+subroutine)?\s*$", _l)
    if _m:
        LABELS[_m.group(2)] = int(_m.group(1), 16)
PC_STARTFRAME = LABELS["StartFrame"]
LC = LABELS["LaserThinClamp"]
SOLABELS = sorted((a, n) for n, a in LABELS.items())
ADDR2LAB = {a: n for a, n in SOLABELS}


def label_at(pc):
    if pc in ADDR2LAB:
        return ADDR2LAB[pc]
    lo = None
    for a, n in SOLABELS:
        if a > pc:
            break
        lo = n
    return f"{lo}+{pc - LABELS[lo]:#x}" if lo else "?"


# ZP indices (addr & 0x7F)
I_ROOMX, I_ROOMY, I_DIR, I_BEAMON = 0x00, 0x01, 0x02, 0x03
I_BOMBP, I_RCBASE = 0x35, 0x09
I_LASERSTATE = 0x40            # $C0
I_RECTCOUNT = 0x12             # $92
I_COLLX = 0x0B                 # $8B
I_COLLENDX = 0x0E              # $8E
RECTS0 = 0x4C                  # $CC & 0x7F
WATCH_ADDRS = {0x09} | set(range(0x4C, 0x4C + 20))   # $89, $CC-$DF
SWEEP_OFF = (0, 8, 16, 8)

rt = {"frame": 0, "writes": [], "active": False}


class Mem:
    def __init__(s):
        s.ram = bytearray(128)
        s.tia = bytearray(0x40)
        s.bank = 3
        s.swcha = 0xFF
        s.swchb = 0xFF
        s.inpt4 = 0x00

    def __getitem__(s, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[s.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return s.ram[a & 0x7F]
        if a == 0x0280:
            return s.swcha
        if a == 0x0282:
            return s.swchb
        if a == 0x0284:
            return 0
        if a == 0x000C:
            return s.inpt4
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return s.tia[a & 0x3F]
        return 0

    def __setitem__(s, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF6 <= a <= 0x1FF9:
            s.bank = a - 0x1FF6
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            if rt["active"] and (a & 0x7F) in WATCH_ADDRS:
                if len(rt["writes"]) < 400:
                    rt["writes"].append(
                        (rt["frame"], a & 0x7F, v, mpu.pc, s.bank))
            s.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            s.tia[a & 0x3F] = v


mem = Mem()
from py65.devices.mpu6502 import MPU
mpu = MPU(memory=mem)


def band_of(roomy):
    return min((roomy + 3) // 48, 3)


def visible_faces(rects, band):
    faces = set()
    for (x, y, w, h) in rects:
        if w <= 0 or h <= 0 or not (y <= band < y + h):
            continue
        faces.add(4 * x)
        faces.add(4 * (40 - x - w))
    return faces


def spec(c, roomx, roomy, facing, rects, mask_hits):
    """Probe-style step-1 reference + WallMask skip (mask_hits = skipped)."""
    if facing != 0:
        return 0x32, 15
    band = band_of(roomy)
    face = roomx + 4
    best = c + 8
    blocked = False
    for i, (x, y, w, h) in enumerate(rects):
        if i in mask_hits or w <= 0 or h <= 0:
            continue
        if not (y <= band < y + h):
            continue
        for (a, b) in ((4 * x, 4 * (x + w) - 1),
                       (4 * (40 - x - w), 4 * (39 - x) + 3)):
            if b < c:
                if a > face:
                    blocked = True
            elif a > c + 7:
                pass
            elif a <= c:
                blocked = True
            elif a < best:
                best = a
        if blocked:
            break
    if blocked:
        return 0, None
    w = best - c
    if w >= 8:
        return 0x32, 15
    wcode = 0 if w == 1 else (1 if w <= 3 else 2)
    return 0x02 | (wcode << 4), (8, 9, 11, 15)[wcode]


BOMBMASK = (0x08, 0x10, 0x20, 0x40)   # BombMaskBit for rect idx 0-3 (b3-b6)


def read_rects():
    count = mem.ram[I_RCBASE]
    rects = []
    for i in range(min(count, 5)):
        b = RECTS0 + 4 * i
        rects.append((mem.ram[b], mem.ram[b + 1],
                      mem.ram[b + 2], mem.ram[b + 3]))
    return count, rects


def main():
    NF = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    guard = 0
    while mpu.pc != PC_STARTFRAME:
        mpu.step()
        guard += 1
        if guard > 400000:
            sys.exit("no boot")
    frame = 0
    while frame < 500:
        mpu.step()
        if mpu.pc == PC_STARTFRAME:
            frame += 1
            if mem.ram[I_BOMBP] & 0x80:
                break

    rts_pcs = set()
    for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+(?:[0-9a-f]{2}[ \t]+)+rts\b",
                      _l)
        if _m:
            a = int(_m.group(1), 16)
            if LC <= a < LC + 0x160:
                rts_pcs.add(a)
    if not rts_pcs:
        sys.exit("no rts inside LaserThinClamp")

    rt["active"] = True
    base_count, base_rects = read_rects()
    print(f"baseline: count={base_count} rects={base_rects}")

    cls = {"W": [], "A": [], "B": [], "C": [], "D": []}
    n_clamp = 0
    writes_before = 0
    import random
    rng = random.Random(20261001)
    swcha = 0xFF
    next_input = 0

    for fr in range(NF):
        rt["frame"] = fr
        if fr >= next_input:
            swcha = (0xFF, 0xF7, 0xFB, 0xFD, 0xFE)[rng.randrange(5)]
            next_input = fr + 8 + rng.randrange(12)
        mem.swcha = swcha
        mem.inpt4 = 0x00
        # band coverage: sweep RoomY deterministically, pin vy
        mem.ram[I_ROOMY] = (fr * 7) % 190
        mem.ram[0x13] = 0        # vyLo
        mem.ram[0x14] = 0        # vyHi

        cap = None
        while True:
            mpu.step()
            if mpu.pc in rts_pcs:
                # READ EVERYTHING HERE — $92/$8B/$8E are aliased later
                cap = dict(c=mem.ram[I_COLLX], best=mem.ram[I_COLLENDX],
                           pack=mem.ram[I_BEAMON], rc=mem.ram[I_RECTCOUNT],
                           dr=mem.ram[I_DIR], rx=mem.ram[I_ROOMX],
                           ry=mem.ram[I_ROOMY], bombp=mem.ram[I_BOMBP],
                           phase=mem.ram[I_LASERSTATE] & 3,
                           rects=read_rects())
            if mpu.pc == PC_STARTFRAME:
                break
        if cap:
            n_clamp += 1
            count, rects = cap["rects"]
            c, best, pack = cap["c"], cap["best"], cap["pack"]
            dr, roomx, roomy = cap["dr"], cap["rx"], cap["ry"]
            got_rc, phase, bombp = cap["rc"], cap["phase"], cap["bombp"]
            mask_hits = {i for i in range(4)
                         if (bombp & BOMBMASK[i]) if i < count}
            band = band_of(roomy)

            # A: runtime cache differs from pristine baseline
            if count != base_count or rects != base_rects:
                if len(cls["A"]) < 30:
                    cls["A"].append(
                        f"f{fr} Rx={roomx} Ry={roomy} count={count} "
                        f"rects={rects} base={base_rects}")

            if dr == 0:
                exp, expb = spec(c, roomx, roomy, dr, rects, mask_hits)
                # C: asm pack vs spec (RectCount bound too)
                bad = pack != exp
                if not bad and pack != 0 and got_rc != expb:
                    bad = True
                if bad and len(cls["C"]) < 30:
                    cls["C"].append(
                        f"f{fr} Rx={roomx} Ry={roomy} C={c} pack=${pack:02X} "
                        f"exp=${exp:02X} RC={got_rc} expb={expb} "
                        f"best={best} phase={phase} mask={sorted(mask_hits)} "
                        f"rects={rects}")
                # B: best face must be a runtime face (or sentinel)
                if pack not in (0x00, 0x32) and best != c + 8:
                    if best not in visible_faces(rects, band) \
                            and len(cls["B"]) < 30:
                        cls["B"].append(
                            f"f{fr} Rx={roomx} Ry={roomy} C={c} best={best} "
                            f"band={band} vf={sorted(visible_faces(rects, band))}"
                            f" rects={rects}")
                # D: beam on with a wall face between eye and C (tunnel)
                if pack != 0:
                    eye = roomx + 4
                    for (x, y, w, h) in rects:
                        if h <= 0 or w <= 0 or not (y <= band < y + h):
                            continue
                        for (a, b) in ((4 * x, 4 * (x + w) - 1),
                                       (4 * (40 - x - w), 4 * (39 - x) + 3)):
                            if eye <= a < c and b >= eye:
                                if len(cls["D"]) < 30:
                                    cls["D"].append(
                                        f"f{fr} Rx={roomx} Ry={roomy} "
                                        f"eye={eye} C={c} wall=[{a},{b}] "
                                        f"pack=${pack:02X} phase={phase} "
                                        f"rects={rects}")
                                break
                # eye/C math check (SweepOff triangle)
                exp_c = (roomx + 4 + SWEEP_OFF[phase]) % 256
                if exp_c != c and len(cls.setdefault("E", [])) < 30:
                    cls["E"].append(
                        f"f{fr} Rx={roomx} phase={phase} C={c} exp={exp_c}")

        # new watched writes -> report + re-baseline (loader or corruption)
        ws = rt["writes"][writes_before:]
        writes_before = len(rt["writes"])
        if ws:
            for (f, idx, val, pc, bk) in ws:
                if len(cls["W"]) < 60:
                    cls["W"].append(
                        f"f{f} ${0x80 + idx:02X}<-${val:02X} pc=${pc:04X} "
                        f"bank{bk} {label_at(pc)}")
            base_count, base_rects = read_rects()   # assume loader; A fired
            # note: if it was corruption, baseline is now poisoned too —
            # W entries keep the evidence either way.

    print(f"frames={NF} clamp_calls={n_clamp} watched_writes="
          f"{len(rt['writes'])}")
    for k in ("W", "A", "C", "B", "D", "E"):
        v = cls.get(k, [])
        if v:
            print(f"\n== class {k}: showing {len(v)}")
            for s in v:
                print("  " + s)
        else:
            print(f"class {k}: none")


if __name__ == "__main__":
    main()
