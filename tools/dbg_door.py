"""Door (LOCKED_DOOR) collision, driven through PlayerHitsMap.

A door is a 1-px async strip (M1) whose playfield cell is OPEN in its band and
wall in every other band (the wall-hide envelope). PlayerHitsMap's cell walk
misses that open cell (the strip is not a PF wall), so the asym overlay has to
block it — that is the code under test.

The room is authored here (no live stage): 10-column half, door at col 7 in
band 1, walls everywhere else at that column, open cells on both sides of the
door (the "a door must lead somewhere" rule).

Cases:
  1. LEFT door (side 1, x = 7 + 8*col), no key  -> blocked (C=1)
  2. LEFT door, KeyHeld                         -> passable (C=0) + b4 set
  3. RIGHT door (side 0, x = 87 + 8*col), no key -> blocked (C=1)
"""
import re
import sys
from pathlib import Path

from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "src" / "tests" / "frozen"
sys.path.insert(0, str(ROOT / "tools"))
import convert_room  # noqa: E402

CODE_LABEL = re.compile(r"^\s*\d+\s+([0-9a-f]{4})\s+(\w+)\s*$")
ZP_LABEL = re.compile(r"^\s*\d+\s+U([0-9a-f]{4})\s+.*?(\w+)\s+byte")
EQUATE = re.compile(r"(\w+)\s*=\s*\$([0-9a-fA-F]{2,4})\s*$")


def labels(path: Path) -> dict:
    out = {}
    for line in path.read_text(errors="replace").splitlines():
        core = line.split(";")[0].rstrip()
        if not core:
            continue
        for pat in (CODE_LABEL, ZP_LABEL):
            m = pat.match(core)
            if m:
                out[m.group(2)] = int(m.group(1), 16)
                break
        else:
            m = EQUATE.search(core)
            if m:
                out.setdefault(m.group(1), int(m.group(2), 16))
    return out


L = labels(FROZEN / "bank0.lst")
NEED = ("PlayerHitsMap", "EnemyDeadMask", "RoomPF0Lo", "RoomPF0Hi",
        "LevelStartRoom", "LineCount", "RoomX", "RoomY",
        "PF0Buf", "PF1Buf", "PF2Buf")
missing = [n for n in NEED if n not in L]
if missing:
    sys.exit(f"labels missing from frozen bank0.lst: {missing}")

RTS_SENTINEL = 0x0101

# door room: walls everywhere except the door column, which is open in band 1
ROWS = ["##########",
        "#####.....",
        "##########"]
DOOR_COL = 7

L_M1X = 7 + 8 * DOOR_COL            # side 1: left half
R_M1X = 87 + 8 * DOOR_COL           # side 0: right half (display col 17)


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


def run(right_side: bool, key_held: bool, player_x: int, room_y: int = 60):
    mem = Mem()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFD
    mem[0x1FF] = RTS_SENTINEL & 0xFF
    mem[0x1FE] = RTS_SENTINEL >> 8

    def z(name, val):
        mem[L[name] & 0x7F] = val

    # playfield: 3 band rows
    for band, row in enumerate(ROWS):
        pf0, pf1, pf2 = convert_room.pf_values(row)
        mem.ram[(L["PF0Buf"] + band) & 0x7F] = pf0
        mem.ram[(L["PF1Buf"] + band) & 0x7F] = pf1
        mem.ram[(L["PF2Buf"] + band) & 0x7F] = pf2

    # staged async metas: m1_col+1 = 8, door bit (b3), +m1_right (b0)
    z("RoomPF0Lo", (8 << 4) | 0x08 | (0x01 if right_side else 0x00))
    z("RoomPF0Hi", 0x80)            # b7 = async door, no ball column
    z("LineCount", 0x08)            # packed: b3 = M1 present, ball col 0
    z("EnemyDeadMask", 0x00)
    z("LevelStartRoom", 0x80 if key_held else 0x00)
    z("RoomX", player_x)
    z("RoomY", room_y)

    trace = []
    mpu.pc = L["PlayerHitsMap"]
    for _ in range(60000):
        trace.append((mpu.pc, mem.bank))
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            break
    else:
        tail = " ".join(f"${pc:04X}/{b}" for pc, b in trace[-16:])
        sys.exit(f"PlayerHitsMap never returned; tail: {tail}")
    return mpu.p & 0x01, mem.ram[L["EnemyDeadMask"] & 0x7F], trace


def main() -> int:
    fails = []

    c, dead, tr = run(right_side=False, key_held=False, player_x=L_M1X - 4)
    if c != 1:
        fails.append(f"LEFT door: not blocked without the key (C={c})")
    if dead & 0x10:
        fails.append(f"LEFT door: marked destroyed while locked (${dead:02X})")

    c2, dead2, _ = run(right_side=False, key_held=True, player_x=L_M1X - 4)
    if c2 != 0:
        fails.append(f"LEFT door + key: still blocked (C={c2})")
    if not dead2 & 0x10:
        fails.append(f"LEFT door + key: strip not destroyed (${dead2:02X})")

    c3, _, _ = run(right_side=True, key_held=False, player_x=R_M1X - 4)
    if c3 != 1:
        fails.append(f"RIGHT door: not blocked without the key (C={c3})")

    if fails:
        print("FAIL: door collision")
        for f in fails:
            print("  -", f)
        print("  trace head:",
              " ".join(f"${pc:04X}/{b}" for pc, b in tr[:20]))
        return 1
    print("OK: door blocks when locked (both sides), opens with the key")
    return 0


if __name__ == "__main__":
    sys.exit(main())
