"""Headless door test: drive PlayerHitsMap with a staged door room.

Uses the LIVE banks (src/bank0.bin etc.), not the frozen copies, so it exercises
the current kernel. Staging:
  Model 14 (the user's door room): band 1 = '#####.....', walls elsewhere at the
  strip column; a side-0 LOCKED_DOOR at col 2 -> M1X = 87 + 8*2 = 103.
RoomX is chosen so the player's box spans the strip.
"""
import json
import sys
from pathlib import Path

from py65.devices.mpu6502 import MPU

ROOT = Path("/home/iuri/Desenvolvimento/atari_2600/ai_savior")
SRC = ROOT
sys.path.insert(0, str(ROOT / "tools"))
import convert_room as CR  # noqa: E402

RTS = 0x0101


def load_labels():
    """Zero-page + code symbols from the CURRENT listing."""
    import re
    out = {}
    code = re.compile(r"^\s*\d+\s+([0-9a-f]{4})\s+(\w+)\s*$")
    zp = re.compile(r"^\s*\d+\s+U([0-9a-f]{4})\s+.*?(\w+)\s+byte")
    eq = re.compile(r"(\w+)\s*=\s*\$([0-9a-fA-F]{2,4})\s*$")
    for line in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
        core = line.split(";")[0].rstrip()
        if not core:
            continue
        m = code.match(core)
        if m:
            out[m.group(2)] = int(m.group(1), 16)
            continue
        m = zp.match(core)
        if m:
            out[m.group(2)] = int(m.group(1), 16)
            continue
        m = eq.search(core)
        if m:
            out.setdefault(m.group(1), int(m.group(2), 16))
    return out


L = load_labels()


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.banks = [bytearray((SRC / f"bank{i}.bin").read_bytes())
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


ROWS = ["#####.....",   # band 0: wall at the strip column (envelope)
        "#####.....",   # band 1: the door row (open at col 2..4)
        "#####....."]    # band 2
COL = 2
M1X = 87 + 8 * COL


def run(right_side: bool, key_held: bool, room_x: int, room_y: int = 74,
        verbose: bool = False):
    mem = Mem()
    mpu = MPU(memory=mem)
    # PHM returns through the asym overlay (ReturnPad) - give it a small
    # stack of identical sentinels so a stray extra rts still lands on one.
    mpu.sp = 0xFB
    for a in (0x1FF, 0x1FD):
        mem[a] = RTS & 0xFF
    for a in (0x1FE, 0x1FC):
        mem[a] = RTS >> 8

    def z(name, val):
        mem[L[name] & 0x7F] = val & 0xFF

    for band, row in enumerate(ROWS):
        pf0, pf1, pf2 = CR.pf_values(row)
        mem.ram[(L["PF0Buf"] + band) & 0x7F] = pf0
        mem.ram[(L["PF1Buf"] + band) & 0x7F] = pf1
        mem.ram[(L["PF2Buf"] + band) & 0x7F] = pf2

    col = COL if right_side else 7
    m1x = (87 + 8 * col) if right_side else (7 + 8 * col)
    meta_a = ((col + 1) << 4) | 0x08 | (0x01 if right_side else 0x00)
    z("RoomPF0Lo", meta_a)
    z("RoomPF0Hi", 0x00 if not right_side else 0x80)
    z("LineCount", 0x08)
    z("EnemyDeadMask", 0x00)
    z("LevelStartRoom", 0x80 if key_held else 0x00)
    z("PlayerDir", 1)
    z("RoomX", room_x)
    z("RoomY", room_y)

    trace = []
    mpu.pc = L["PlayerHitsMap"]
    for _ in range(200000):
        trace.append((mpu.pc, mem.bank))
        mpu.step()
        if mpu.pc == RTS:
            break
    else:
        tail = " ".join(f"${pc:04X}/{b}" for pc, b in trace[-12:])
        return None, f"runaway; tail: {tail}"

    if verbose:
        print(f"    M1X={m1x} RoomX={room_x} C={mpu.p & 1} "
              f"steps={len(trace)}")
    return mpu.p & 1, None


def main() -> int:
    print("player box must span the strip column")
    for right in (False, True):
        side = "right(side0)" if right else "left (side1)"
        m1x = (87 + 8 * COL) if right else (7 + 8 * 7)
        for rx in (m1x - 6, m1x - 4, m1x - 1, m1x):
            c, err = run(right_side=right, key_held=False, room_x=rx,
                         verbose=True)
            state = "BLOCKED" if c == 1 else ("passable" if c == 0 else "??")
            print(f"  {side} M1X={m1x} RoomX={rx:3d} -> {state}"
                  f"{'  ' + err if err else ''}")
        c, err = run(right_side=right, key_held=True, room_x=m1x - 4)
        print(f"  {side} with key            -> "
              f"{'BLOCKED' if c == 1 else 'passable'}{'  ' + err if err else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
