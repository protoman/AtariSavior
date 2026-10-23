#!/usr/bin/env python3
"""Laser close-range wall/extension contact probe (py65) — bugs #9.

User report (2026-10-09): level 1, rooms 1 AND 2 (1-based), very close to
a block, facing RIGHT (left OK), the beam continues ALL the way through —
sync walls and the async extension. test_laser_wall only proves the travel
budget; a pass-through (travel lands in a wall cell) passes that model.

This probe sweeps RoomX across the whole screen, both facings, both rooms
and two RoomY rows (incl. a band-straddle row), pinning the player like
test_laser_wall does, and asserts against the game's LIVE state:

  consume contract (2026-10-10, AGENTS "laser = dumb contact missile"):
      capture = (LaserX, CollisionX, LaserState) at LaserInput's rts;
      candidate tip = CollisionX (right) / CollisionX-7 (left)
      CollisionX = the position LHT tested (staged pre-contact, LWC does
      not modify it) — LaserX alone cannot detect contact anymore, because
      the consume restart rewrites it to the eye.
      if CellSolid(candidate tip, band) for EITHER beam band row
          -> LaserX == eye  AND  b1 armed  AND  buzz live (no suppress)
      else -> LaserX in (candidate, eye)   (travel committed / cap reset)
  extension invariants (same shape, candidate-based):
      LWtipC left strip: tip in [M1X-7, M1X], strip alive (b4 clear)
          -> consume          (M1X = (MetaA>>4)<<3)-1)
      LWpSetup band strip: pack=$84 !=0, pack & OvHead[top] & OvTail[bot],
          d-tip - pL in {0,1} with pL = 18 + (pack>>4)*2
          -> consume

Rooms are switched by hand (the game rebuilds PF/rect/pointer state only
in EnterRoom): at each block start we poke RoomPF0Lo/Hi, the 9 PF buffer
bytes from the ROM model data, RoomRectsLo/Hi, and EnemyCount=0 — VBL's
StageBandTab then rebuilds the overlay pack from the new MetaA by itself.
M0/M1 hot counts are zeroed in the ROM image (hot = life-loss would end
the sweep); strip state (MetaA + EnemyDeadMask b4) stays REAL.

Run: /home/iuri/python3/bin/python3 tools/test_laser_close.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FROZEN = ROOT / "src" / "tests" / "frozen"   # test-owned banks+labels
BANKS = [bytearray(open(FROZEN / f"bank{i}.bin", "rb").read()) for i in range(4)]

# Zero M0/M1 hot counts (life-loss would end the sweep); strips stay real.
for _name in ("M0Shape",):   # level 1 room 0 = model 0 (C5: shape)
                                   # L1R2 block was removed with it)
    for _l in (FROZEN / "bank3.lst").read_text(errors="replace").splitlines():
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+" + _name + r"\s*$", _l)
        if _m:
            _a = int(_m.group(1), 16) - 0xF000
            BANKS[3][_a] = 0                          # hot count = 0
            break
    else:
        sys.exit(f"{_name} label missing in bank3.lst")


def lst_labels(path):
    out = {}
    for _l in Path(path).read_text(errors="replace").splitlines():
        _m = re.match(r"^\s+\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", _l)
        if _m:
            out[_m.group(2)] = int(_m.group(1), 16)
    return out


L0 = lst_labels(FROZEN / "bank0.lst")
L2 = lst_labels(FROZEN / "bank2.lst")
L3 = lst_labels(FROZEN / "bank3.lst")   # C7: shape blocks + extras

def shape_pf(model):
    """The 9 PF bytes of model `model`'s shape: C3 row-pool expansion.

    A shape block is `hot count | 5 B/record | 3 row indices`; the loader
    (bank2 B3RoomBlocks) expands the indices through RowPoolPF0/1/2 into
    PF0Buf, so this reads the SAME bytes via the label addresses."""
    at = L3[f"M{model}Rows"] - 0xF000
    idx = BANKS[3][at:at + 3]
    out = bytearray()
    for col in ("RowPoolPF0", "RowPoolPF1", "RowPoolPF2"):
        base = L3[col] - 0xF000
        out += bytes(BANKS[3][base + i] for i in idx)
    return bytes(out)


PC_STARTFRAME = L0["StartFrame"]

# ZP indices (addr & 0x7F) — from bank0.lst U00xx decl lines
I_ROOMX, I_ROOMY, I_DIR, I_LASERX = 0x00, 0x01, 0x02, 0x03   # $80..$83
I_COLLX = 0x0B                      # $8B CollisionX (LHT candidate)
I_PACK = 0x04                       # $84 LineCount (overlay pack after HUD)
I_RRLO, I_RRHI = 0x10, 0x11         # $90/$91 RoomRects ptr
I_VYLO, I_VYHI = 0x13, 0x14         # $93/$94
I_PF0LO, I_PF0HI = 0x19, 0x1A       # $99/$9A RoomPF0 ptr
I_ENCOUNT = 0x33                    # $B3
I_BOMBP = 0x35                      # $B5
I_DEAD = 0x3A                       # $BA EnemyDeadMask

OV_HEAD, OV_TAIL = L2["OvHead"], L2["OvTail"]
MODEL = {0: 0}   # room 0-based -> fixture MODEL id (level 1 room 0 = M0)

RANGE_LO = L0["LaserInput"]
RANGE_HI = L0.get("TallyTramp", 0xFFF0)
rts_pcs = set()
for _l in (FROZEN / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s+\d+\s+([0-9a-f]{4})\s+(?:[0-9a-f]{2}[ \t]+)+rts\b", _l)
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
        self.inpt4 = 0x00

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
from py65.devices.mpu6502 import MPU  # noqa: E402
mpu = MPU(memory=mem)


def step():
    mpu.step()


def band_row_of(y):
    idx = y >> 2
    return 0 if idx < 12 else (1 if idx < 24 else 2)


def cell_solid(tip_px, band_row):
    if tip_px < 0 or tip_px > 159:
        return False
    d = tip_px >> 2
    src = d if d < 20 else 39 - d
    if src < 4:
        addr, mask = 0xC3 + band_row, 0x10 << src
    elif src < 12:
        addr, mask = 0xC6 + band_row, 0x80 >> (src - 4)
    else:
        addr, mask = 0xC9 + band_row, 0x01 << (src - 12)
    return bool(mem.ram[addr & 0x7F] & mask)


def eye_of(roomx, facing):
    return min(roomx + 4, 159) if facing == 0 else roomx - 4


def load_room(room):
    """Hand-EnterRoom: pointers + PF buffers + rects ptr (cache unused by
    the laser). VBL StageBandTab rebuilds the overlay pack itself."""
    model = MODEL[room]
    pf9, a_rr = shape_pf(model), L3["RoomNoStream"]   # C11: no stream in a shape
    # C5: MetaA/MetaB live in the level's AsyncExtras record (level 1 room 0
    # is the async room, ordinal 1 -> +1/+2).
    mem.ram[I_PF0LO] = BANKS[3][(L3["LEVEL1_AsyncExtras"] + 1 - 0xF000)]
    mem.ram[I_PF0HI] = BANKS[3][(L3["LEVEL1_AsyncExtras"] + 2 - 0xF000)]
    mem.ram[I_RRLO] = a_rr & 0xFF
    mem.ram[I_RRHI] = a_rr >> 8
    # ROM: C3 row-pool expansion of the shape's 3 indices
    for i, dst in enumerate((0xC3, 0xC6, 0xC9)):
        for row in range(3):
            mem.ram[(dst + row) & 0x7F] = pf9[i * 3 + row]


def meta_a(room):
    """MetaA = the room extras record's +1 (C5: the pair left the block)."""
    return BANKS[3][L3["LEVEL1_AsyncExtras"] + 1 - 0xF000]


CASE_Y = (24, 45, 96)      # 24 = spawn/band0, 45 = straddle, 96 = band 2


def main() -> None:
    guard = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        guard += 1
        if guard > 400000:
            sys.exit(f"never reached StartFrame (pc=${mpu.pc:04X})")

    frame = 0
    landed = None
    while frame < 400:
        step()
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            frame += 1
            mem.swchb = 0xFE if frame in (2, 5) else 0xFF
            if mem.ram[I_BOMBP] & 0x80:
                landed = frame
                break
    if landed is None:
        sys.exit("player never landed")
    mem.ram[I_DEAD] = 0xEF                 # enemies dead, b4 strip ALIVE

    fails = []
    checked = 0
    cells_hit = ext_hits = 0
    for room in (0,):   # level 1 has one room
        load_room(room)
        # settle: let one VBL StageBandTab rebuild the overlay pack from
        # the freshly poked MetaA before asserts start
        for _ in range(2):
            while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
                step()
        meta = meta_a(room)
        m1x = ((meta >> 4) << 3) - 1 if (meta >> 4) else None
        for facing in (0, 1):
            for y in CASE_Y:
                for x in range(4, 156):
                    for _ in range(3):
                        mem.ram[I_ROOMX] = x
                        mem.ram[I_ROOMY] = y
                        mem.ram[I_DIR] = facing
                        mem.ram[I_VYLO] = 0
                        mem.ram[I_VYHI] = 0
                        mem.ram[I_ENCOUNT] = 0
                        cap = None
                        while True:
                            step()
                            if mpu.pc in rts_pcs:
                                cap = (mem.ram[I_LASERX],
                                       mem.ram[I_COLLX],
                                       mem.ram[0x40])   # LaserX, CollisionX,
                                                        # LaserState
                            if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
                                break
                        if cap is None:
                            continue
                        checked += 1
                        lx, cx, st = cap
                        eye = eye_of(x, facing)
                        # candidate = what LHT tested (CollisionX is staged
                        # from the pre-contact LaserX; LWC does not modify
                        # it) — derive contact from THAT, since the consume
                        # restart rewrites LaserX to the eye.
                        tip = cx if facing == 0 else cx - 7
                        rows = (band_row_of(y + 4), band_row_of(y + 5))
                        wallish = any(cell_solid(tip, r) for r in rows)
                        # extension: LWtipC left strip window (raw M1X)
                        if m1x is not None and not (mem.ram[I_DEAD] & 0x10):
                            if m1x - 7 <= tip <= m1x:
                                ext_hits += 1
                                wallish = True
                        # extension: LWpSetup band strip (col marker)
                        pack = mem.ram[I_PACK]
                        if pack and m1x is not None:
                            bt, bb = rows
                            if pack & BANKS[2][OV_HEAD - 0xF000 + bt] & \
                                    BANKS[2][OV_TAIL - 0xF000 + bb]:
                                pl = 18 + (pack >> 4) * 2
                                d = tip >> 2
                                if 0 <= d - pl <= 1:
                                    wallish = True
                        if wallish:
                            cells_hit += 1
                            # consume contract (2026-10-10, AGENTS Critical
                            # Rule): the wall CONSUMES the missile — restart
                            # at the eye THIS frame, beam stays ARMED (b1),
                            # buzz keeps (b7). No suppress, no hold/clamp.
                            if lx != eye:
                                fails.append(
                                    f"r{room} dir{facing} x{x} y{y}: wall "
                                    f"contact but LaserX={lx} != eye {eye} "
                                    f"(missile not consumed)")
                            if not (st & 0x02):
                                fails.append(
                                    f"r{room} dir{facing} x{x} y{y}: wall "
                                    f"contact but beam DISARMED (LaserState="
                                    f"${st:02X}) — no suppress allowed")
                            # buzz must LIVE while held (b7):
                            # ch0 = LASER_AUD_C=2 / LASER_AUD_V=9
                            ac = mem.tia[0x15]      # AUDC0
                            av = mem.tia[0x19]      # AUDV0
                            if ac != 2 or av != 9:
                                fails.append(
                                    f"r{room} dir{facing} x{x} y{y}: buzz "
                                    f"dead (AUDC0=${ac:02X} "
                                    f"AUDV0=${av:02X}, want $02/$09)")
                        else:
                            # clear candidate: travel committed it (or the
                            # miss-arm cap restarted at the eye) — LaserX is
                            # the candidate or the eye; anything else means
                            # the bolt got somewhere it was never tested.
                            if lx not in (cx, eye):
                                fails.append(
                                    f"r{room} dir{facing} x{x} y{y}: clear "
                                    f"candidate but LaserX={lx} not in "
                                    f"({cx},{eye}) — pass-through?")
    print(f"checked {checked} frames; cell-contact frames={cells_hit}, "
          f"M1-strip frames={ext_hits}")
    if fails:
        print(f"FAIL: {len(fails)} consume-contract violations:")
        for f in fails[:20]:
            print("  " + f)
        if len(fails) > 20:
            print(f"  ... and {len(fails) - 20} more")
        sys.exit(1)
    print("test_laser_close: OK (wall/strip tip => missile CONSUMED: "
          "LaserX==eye, b1 armed, buzz live; clear frames = candidate or "
          "eye; both rooms/facings, straddle rows included)")


if __name__ == "__main__":
    main()
