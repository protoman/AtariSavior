"""WIP: door (M1 left door) collision harness — NOT a battery test (dbg_ prefix).

STATUS 2026-10-23: calling OverlayTramp directly reproduces the real path up to
the bank2 overlay crossing, but bank2's overlay body then loops: the caller
state it needs (RectCount / CollisionCellX / CollisionEndX / FetchPtr staging)
is produced by PlayerHitsMap's prologue, so this must enter through
PlayerHitsMap with a fully staged room instead of poking the overlay entry.
Kept because the state recipe below is right and the assertions are the ones
the door needs; rename to test_door.py once it drives the real caller.

Door (M1 left door) collision, driven through the real overlay entry.

No frame loop: the overlay is a pure function of staged ZP + the PF buffers, so
the test pokes the state a real door room produces and calls `OverlayTramp`
(the same entry `PlayerHitsMap` uses), then reads the returned carry:
C=1 blocked, C=0 passable.

State poked (all from the live encoding):
  LineCount     = $08  packed overlay byte: b3 = M1 present, no ball column
  RoomPF0Lo     = $78  MetaA: m1_col+1 = 7 (col 6) + b3 door + b0 left half
  RoomPF0Hi     = $00  MetaB: cold, no ball
  PF1Buf[1]     &= ~$20  the door cell (row 1, col 6) OPEN in the playfield
  EnemyDeadMask = 0    strip intact
  LevelStartRoom: 0 = no key, $80 = key held
"""
import re
import sys
from pathlib import Path

from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "src" / "tests" / "frozen"

CODE_LABEL = re.compile(r"^\s*\d+\s+([0-9a-f]{4})\s+(\w+)\s*$")
ZP_LABEL = re.compile(r"^\s*\d+\s+U([0-9a-f]{4})\s+.*?(\w+)\s+byte")
EQUATE = re.compile(r"(\w+)\s*=\s*\$([0-9a-fA-F]{2,4})\s*$")


def labels(path: Path) -> dict:
    """Symbols from a DASM listing: code labels + zero-page declarations."""
    out = {}
    for line in path.read_text(errors="replace").splitlines():
        core = line.split(";")[0].rstrip()
        if not core:
            continue
        m = CODE_LABEL.match(core)
        if m:
            out[m.group(2)] = int(m.group(1), 16)
            continue
        m = ZP_LABEL.match(core)
        if m:
            out[m.group(2)] = int(m.group(1), 16)
            continue
        m = EQUATE.search(core)
        if m:
            out.setdefault(m.group(1), int(m.group(2), 16))
    return out


L = labels(FROZEN / "bank0.lst")
NEED = ("OverlayTramp", "PHMOverlay", "EnemyDeadMask", "RoomPF0Lo",
        "RoomPF0Hi", "LevelStartRoom", "LineCount", "CollisionX",
        "CollisionCellY", "CollisionEndY", "CollisionEndX", "PF1Buf")
missing = [n for n in NEED if n not in L]
if missing:
    sys.exit(f"labels missing from frozen bank0.lst: {missing}")

RTS_SENTINEL = 0x0101


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.banks = [bytearray((FROZEN / f"bank{i}.bin").read_bytes())
                      for i in range(8)]
        self.bank = 0

    def __getitem__(self, a):
        if a < 0x80:
            return 0
        if a < 0x100:
            return self.ram[a & 0x7F]
        if 0x280 <= a <= 0x28F:
            return 0xFF
        if a >= 0xF000:
            return self.banks[self.bank][a - 0xF000]
        return 0

    def __setitem__(self, a, v):
        v &= 0xFF
        if a < 0x80:
            return
        if a < 0x100:
            self.ram[a & 0x7F] = v
            return
        if 0x1FF4 <= a <= 0x1FFB:
            self.bank = a - 0x1FF4
            return
        if a >= 0xF000:
            self.banks[self.bank][a - 0xF000] = v


def run(key_held: bool, door_cell_open: bool = True):
    mem = Mem()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x1FF] = RTS_SENTINEL & 0xFF
    mem[0x1FE] = RTS_SENTINEL >> 8

    def z(name, val):
        mem[L[name] & 0x7F] = val

    z("LineCount", 0x08)          # b3 = M1 present, no ball column
    z("RoomPF0Lo", 0x78)          # MetaA: m1_col+1 = 7, door bit, left half
    z("RoomPF0Hi", 0x00)          # MetaB: cold, no ball
    z("EnemyDeadMask", 0x00)
    z("LevelStartRoom", 0x80 if key_held else 0x00)
    z("CollisionX", 50)           # player's visible left edge, just left of 55
    z("CollisionCellY", 1)        # door band
    z("CollisionEndY", 1)
    z("CollisionEndX", 58)        # player's right edge, past the strip at 55

    row1 = (L["PF1Buf"] + 1) & 0x7F
    if door_cell_open:
        mem.ram[row1] &= ~0x20 & 0xFF      # col 6 = PF1 bit 5 → cell open
    else:
        mem.ram[row1] |= 0x20

    trace = []
    mpu.pc = L["OverlayTramp"]
    for _ in range(20000):
        trace.append((mpu.pc, mem.bank))
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            break
    else:
        pcs = " ".join(f"${pc:04X}/{b}" for pc, b in trace[-24:])
        sys.exit("overlay never returned (runaway); tail: " + pcs)
    return mpu.p & 0x01, mem.ram[L["EnemyDeadMask"] & 0x7F], trace


def main() -> int:
    fails = []

    c, dead, trace = run(key_held=False)
    if c != 1:
        fails.append(f"locked door did NOT block (C={c}): the player walks "
                     "through it")
    if dead & 0x10:
        fails.append(f"locked door marked destroyed (EnemyDeadMask ${dead:02X})")

    c2, dead2, _ = run(key_held=True)
    if c2 != 0:
        fails.append(f"door with the key still blocks (C={c2})")
    if not dead2 & 0x10:
        fails.append("door with the key did not mark b4 "
                     f"(EnemyDeadMask ${dead2:02X})")

    c3, _, _ = run(key_held=False, door_cell_open=False)
    if c3 != 0:
        fails.append(f"a CLOSED (wall) cell must not be treated as a door "
                     f"(C={c3})")

    if fails:
        print("FAIL: door (M1 left door) collision")
        for f in fails:
            print("  -", f)
        pcs = " ".join(f"${pc:04X}/{b}" for pc, b in trace[:26])
        print("  overlay trace head:", pcs)
        return 1
    print("OK: door blocks without the key, opens with it, wall cell unaffected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
