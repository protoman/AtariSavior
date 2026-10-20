#!/usr/bin/env python3
"""bugs.md #10 probe — reproduce the USER'S exact sequence (2026-10-10
screenshots half_wall_001..005) and trace every write to PF buffers.

Sequence (one room session, no reload between bombs):
  1. bomb @ BombX=104 (RoomX=104, visible col 24 -> mirror 15, window 13..17)
  2. bomb @ BombX=63  (RoomX=64,  visible col 14, window 12..16)
  3. bomb @ BombX=63  again

Screenshots show PF2 row1 ($CA) = 03 -> 05 -> 06 across blasts, i.e.
bit-sets an AND-punch cannot make. This probe either (a) reproduces a
bit-set and names the writer (pc+bank in the trace), or (b) proves the
current build only ever AND-clears (then the screenshots came from a
different ROM image than src/savior.bin built 14:15).

Contract (exit 1 on violation): no write to $C3-$CB may set a bit that
was clear before the write (new & ~old) != 0.

Run: /home/iuri/python3/bin/python3 tools/test_bomb_user_sequence.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [bytearray(open(SRC / f"bank{i}.bin", "rb").read()) for i in range(4)]

for _name in ("M0RoomRects",):   # level 1 room 0 = model 0 (C5: shape)
                                   # L1R2 block was removed with it)
    for _l in (SRC / "bank2.lst").read_text(errors="replace").splitlines():
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+" + _name + r"\s*$", _l)
        if _m:
            _a = int(_m.group(1), 16) - 0xF000
            BANKS[2][_a] = 0      # hot count (C4: block starts with it)
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


L0 = lst_labels(SRC / "bank0.lst")
L1 = lst_labels(SRC / "bank1.lst")
L2 = lst_labels(SRC / "bank2.lst")
L3 = lst_labels(SRC / "bank2.lst")   # A3: level/model blocks
PC_STARTFRAME = L0["StartFrame"]
PC_BMW = L1["BombMarkWalls"]

I_ROOMX, I_ROOMY = 0x00, 0x01
I_VYLO, I_VYHI = 0x13, 0x14
I_RCBASE = 0x09
I_RRLO, I_RRHI = 0x10, 0x11
I_PF0LO, I_PF0HI = 0x19, 0x1A
I_ENCOUNT = 0x33
I_BOMBP = 0x35
I_DEAD = 0x3A
I_DROPT = 0x0A
I_BOMBX = 0x76
I_BOMBT = 0x77
I_BOMBSND = 0x71
I_COLLX = 0x0B            # CollisionX = walls-broken count (BMW out)
RECTS0 = 0x4C
PF_ROWS = range(0xC3, 0xCC)
PF_IDX = [a & 0x7F for a in PF_ROWS]

MODEL = {1: 0}   # room index -> fixture MODEL id (level 1 room 0 = M0)


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x80

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

frame = 0
writes = []
watch = False
snap = [mem.ram[a] for a in PF_IDX]
illegal = []


def step():
    global watch, frame
    mpu.step()
    if watch:
        for i, a in enumerate(PF_IDX):
            v = mem.ram[a]
            if v != snap[i]:
                old = snap[i]
                snap[i] = v
                writes.append((frame, mpu.pc, mem.bank, PF_ROWS[i], old, v))
                if v & ~old:
                    illegal.append((frame, mpu.pc, mem.bank,
                                    PF_ROWS[i], old, v))
    if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
        frame += 1


def shape_pf(model):
    """The 9 PF bytes of model `model`'s shape: C3 row-pool expansion.

    A shape block is `hot count | 5 B/record | 3 row indices`; the loader
    (bank2 B3RoomBlocks) expands the indices through RowPoolPF0/1/2 into
    PF0Buf, so this reads the SAME bytes via the label addresses."""
    at = L3[f"M{model}Rows"] - 0xF000
    idx = BANKS[2][at:at + 3]
    out = bytearray()
    for col in ("RowPoolPF0", "RowPoolPF1", "RowPoolPF2"):
        base = L3[col] - 0xF000
        out += bytes(BANKS[2][base + i] for i in idx)
    return bytes(out)


def load_room(room):
    model = MODEL[room]
    pf9, a_rr = shape_pf(model), L3[f"M{model}RoomRects"]
    # C5: the meta pair comes from the room's extras record (level 1 room 0 =
    # model 0 is the async room, ordinal 1 -> +1/+2). C4: no rect cache.
    mem.ram[I_PF0LO] = BANKS[2][(L3["LEVEL1_AsyncExtras"] + 1 - 0xF000)]
    mem.ram[I_PF0HI] = BANKS[2][(L3["LEVEL1_AsyncExtras"] + 2 - 0xF000)]
    mem.ram[I_RRLO] = a_rr & 0xFF
    mem.ram[I_RRHI] = a_rr >> 8
    for i, dst in enumerate((0xC3, 0xC6, 0xC9)):
        for row in range(3):
            mem.ram[(dst + row) & 0x7F] = pf9[i * 3 + row]


def pin(y=70):
    mem.ram[I_VYLO] = 0
    mem.ram[I_VYHI] = 0
    mem.ram[I_ROOMY] = y
    mem.ram[I_ENCOUNT] = 0
    mem.ram[I_DROPT] = 0
    mem.swcha = 0xFF
    mem.inpt4 = 0x80


def rows():
    return {a: mem.ram[a & 0x7F] for a in PF_ROWS}


def drop_bomb(tag, bombx, roomx, y=70):
    """Arm a real fuse (timer ~180 -> let the 1->2 edge fire BMW),
    keep player alive, watch PF writes until 3 frames past BMW."""
    global watch, snap
    mem.ram[I_ROOMX] = roomx
    mem.ram[I_BOMBX] = bombx
    mem.ram[I_BOMBSND] = 0
    bp = mem.ram[I_BOMBP]
    mem.ram[I_BOMBP] = (bp & ~0x83) | 0x01   # OnGround clear + state1 fuse
    mem.ram[I_BOMBT] = 3                      # ~3 frames to the edge
    watch = True
    snap = [mem.ram[a] for a in PF_IDX]
    start = len(writes)
    bmw = None
    limit = frame + 40
    while bmw is None and frame < limit:
        pin(y)
        step()
        if mem.bank == 1 and mpu.pc == PC_BMW:
            bmw = frame
    if bmw is None:
        watch = False
        print(f"[{tag}] BMW NEVER RAN (BombX={bombx}, RoomX={roomx})")
        return None
    while frame < bmw + 3:
        pin(y)
        step()
    watch = False
    wts = writes[start:]
    print(f"[{tag}] bombX={bombx} roomX={roomx} BMW f{bmw} "
          f"CollisionX(count)={mem.ram[I_COLLX]}")
    print(f"[{tag}] PF writes ({len(wts)}):")
    for f, pc, bank, addr, old, v in wts:
        print(f"  f{f} ${pc:04X} bank{bank} ${addr:02X} ${old:02X} -> ${v:02X}")
    if not wts:
        print(f"  (none — window missed every rect)")
    return bmw


def main():
    global watch
    guard = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        guard += 1
        if guard > 400000:
            sys.exit(f"never reached StartFrame (pc=${mpu.pc:04X})")
    landed = None
    while frame < 400:
        step()
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            mem.swchb = 0xFE if frame in (2, 5) else 0xFF
            if mem.ram[I_BOMBP] & 0x80:
                landed = frame
                break
    if landed is None:
        sys.exit("player never landed (BombPacked OnGround)")
    mem.ram[I_DEAD] = 0xFF
    print(f"landed f{landed}")

    load_room(1)
    print("initial rows: " + " ".join(
        f"${a:02X}=${mem.ram[a & 0x7F]:02X}" for a in PF_ROWS))

    # user sequence: right wall @104, then left @63, then @63 again
    seq = (("bomb1 @104", 104, 64), ("bomb2 @63", 63, 64),
           ("bomb3 @63", 63, 64))
    for tag, bx, rx in seq:
        drop_bomb(tag, bx, rx)
        print(f"[{tag}] rows: " + " ".join(
            f"${a:02X}=${mem.ram[a & 0x7F]:02X}" for a in PF_ROWS))
        print(f"[{tag}] BombPacked=${mem.ram[I_BOMBP]:02X} "
              f"CollisionX={mem.ram[I_COLLX]:02X}")
        print()
        # rearm for next bomb: state back to fuse, keep mask
        mem.ram[I_BOMBP] |= 0x01
        mem.ram[I_BOMBT] = 3

    if illegal:
        print("BIT-SET WRITES FOUND:")
        for f, pc, bank, addr, old, v in illegal:
            print(f"  f{f} ${pc:04X} bank{bank} ${addr:02X} ${old:02X} -> ${v:02X}")
        sys.exit("FAIL: writer that SETS bits (mystery writer named)")
    print("test_bomb_user_sequence: OK (all PF writes are AND-clears only)")


if __name__ == "__main__":
    main()
