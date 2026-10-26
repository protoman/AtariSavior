#!/usr/bin/env python3
"""A miner faces the way the level / editor says he does (hardware mirror, per slot).

History: until 2026-10-22 the cave kernel drove REFP1 from the active object, so
the miner (and the editor's facing arrow) worked. That was removed because REFP1
is ONE register for GRP1 while a frame can draw TWO objects (slot 0 + the
band-paired slot 1): every other frame the miner took the other object's side.
The art was stored mirrored (facing right) and the facing died. User request
2026-10-26 ("I put him facing left, but the sprite is facing right ... why can't
we just flip him?"): bring it back PER SLOT.

Contract under test (the art faces RIGHT; the mirror is needed when he faces left):
  * StageSlot1B2 (bank2) ends in `S1Fin`: it asks MinerRef whether the miner of
    this room faces left, writes REFP1 for SLOT 0 right there (the VBL value the
    kernel starts the frame with) and leaves slot 1's flag in ObjRefs ($89) bit 2.
      - the level's own miner: LevelMinerRoom b7 = faces RIGHT (clear = mirror);
      - an extra miner (record type 15): record b7 = LEFT (set = mirror).
    Only OBJ_MINER ever mirrors: any other object leaves REFP1 = 0.
  * Slot1Hook (bank0) writes REFP1 from ObjRefs (bit 2 -> bit 3) while the band
    swap happens, BEFORE its aligning WSYNC (cycle-neutral: that part of the hook
    has ~30c of slack, 197 of 228c used).

Drives the real frozen routines. Run: /home/iuri/python3/bin/python3 tools/test_miner_facing.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from py65.devices.mpu6502 import MPU  # noqa: E402
from test_cell_map import Mem, parse_labels  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"
K = (SRC / "kernel.asm").read_text()
OBJ_MINER = int(re.search(r"^OBJ_MINER\s*=\s*(\d+)", K, re.M).group(1))
OBJ_MOTH = int(re.search(r"^OBJ_MOTH\s*=\s*(\d+)", K, re.M).group(1))
REFP1 = 0x0C
MINER2, MOTH = 15, 4

L0 = parse_labels(FROZEN / "bank0.lst",
                  {"StageSlot1", "Slot1Hook", "CaveLine", "ZPSpare89",
                   "BandStart", "RoomY", "ObjBase1", "ObjTop1", "ObjX1",
                   "ObjHeight1", "ObjBase", "ObjHeight", "ObjTop", "LineCount",
                   "CollisionX", "ActiveObjectX", "EnemyCount", "EnemyDeadMask",
                   "EnemyRamY", "EnemyRamX", "EnemyDataLo", "EnemyDataHi",
                   "FlickerFrame", "DropTarget", "RoomNo", "LevelMinerRoom",
                   "MinerX", "MinerY", "BombPacked"})
need = {"StageSlot1", "Slot1Hook", "CaveLine", "ZPSpare89"}
miss = need - L0.keys()
if miss:
    sys.exit(f"frozen bank0.lst labels missing: {sorted(miss)}")
Z = {n: L0[n] - 0x80 for n in L0 if L0[n] < 0x100}
REF = Z["ZPSpare89"]                  # ObjRefs lives on the freed $89 slot
REC = 0x01C0                          # enemy records: the Mem model maps $0100-$01FF to RAM


class Tia(Mem):
    """Mem that also logs every REFP1 write."""

    def __init__(self):
        super().__init__()
        self.refp1 = []

    def __setitem__(self, a, v):
        if (a & 0xFFFF) == REFP1:
            self.refp1.append(v & 0xFF)
        Mem.__setitem__(self, a, v)


def stage_slot1(*, ys, types, miner=None, miner_y=0, obj_base=OBJ_MOTH):
    """miner: None = no level miner here, 'L' / 'R' = faces left / right."""
    mem = Tia()
    r = mem.ram
    for i, (y, t) in enumerate(zip(ys, types)):
        r[Z["EnemyRamY"] + i] = y
        r[Z["EnemyRamX"] + i] = 71
        r[(REC & 0x7F) + i * 3] = t
    r[Z["EnemyCount"]] = len(ys)
    r[Z["EnemyDataLo"]] = REC & 0xFF
    r[Z["EnemyDataHi"]] = REC >> 8
    r[Z["RoomNo"]] = 0
    if miner is None:
        r[Z["LevelMinerRoom"]] = 0x7F
    else:
        r[Z["LevelMinerRoom"]] = 0 | (0x80 if miner == "R" else 0)
    r[Z["MinerX"]] = 40
    r[Z["MinerY"]] = miner_y
    r[Z["ObjBase"]] = obj_base            # what SelectActiveObject drew in slot 0
    r[Z["ObjBase1"]] = 0xAA
    r[REF] = 0x55                         # sentinel
    mem.bank = 0
    mpu = MPU(memory=mem)
    mpu.pc = L0["StageSlot1"]
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(8000):
        mpu.step()
        if mpu.pc == 0x0101:
            break
    else:
        sys.exit("StageSlot1 never returned")
    return mem


def slot0_mirror(mem):
    return mem.refp1[-1] if mem.refp1 else None


# --- slot 0 -------------------------------------------------------------------
m = stage_slot1(ys=[], types=[], miner="L", miner_y=96, obj_base=OBJ_MINER)
assert slot0_mirror(m) == 0x08, (
    f"level miner facing LEFT in slot 0: REFP1 writes {m.refp1} - the art faces "
    "right, so the mirror bit ($08) must be written")
m = stage_slot1(ys=[], types=[], miner="R", miner_y=96, obj_base=OBJ_MINER)
assert slot0_mirror(m) == 0x00, f"miner facing right must not mirror: {m.refp1}"
m = stage_slot1(ys=[], types=[], miner="L", miner_y=96, obj_base=OBJ_MOTH)
assert slot0_mirror(m) == 0x00, (
    f"a MOTH in slot 0 must never be mirrored (only the miner art): {m.refp1}")
# an extra miner (record type 15, b7 = left) as the slot-0 object
m = stage_slot1(ys=[63], types=[MINER2 | 0x80], obj_base=OBJ_MINER)
assert slot0_mirror(m) == 0x08, f"extra miner facing left (slot 0): {m.refp1}"
m = stage_slot1(ys=[63], types=[MINER2], obj_base=OBJ_MINER)
assert slot0_mirror(m) == 0x00, f"extra miner facing right (slot 0): {m.refp1}"

# --- slot 1 (left in ObjRefs bit 2 for the hook) -------------------------------
m = stage_slot1(ys=[60], types=[MOTH], miner="L", miner_y=96)
assert m.ram[REF] & 0x04, (
    f"the level miner faces LEFT in slot 1: ObjRefs=${m.ram[REF]:02X} lacks bit 2")
assert slot0_mirror(m) == 0x00, "slot 0 (the moth) must stay unmirrored"
m = stage_slot1(ys=[60], types=[MOTH], miner="R", miner_y=96)
assert not m.ram[REF] & 0x04, f"miner facing right: ObjRefs=${m.ram[REF]:02X}"
m = stage_slot1(ys=[60, 99], types=[MOTH, MINER2 | 0x80])
assert m.ram[REF] & 0x04, f"extra miner left in slot 1: ObjRefs=${m.ram[REF]:02X}"
m = stage_slot1(ys=[60, 99], types=[MOTH, MINER2])
assert not m.ram[REF] & 0x04, f"extra miner right in slot 1: ObjRefs=${m.ram[REF]:02X}"
# the higher-band extra miner listed FIRST (the PinSlot0 case)
m = stage_slot1(ys=[99, 60], types=[MINER2 | 0x80, MOTH])
assert m.ram[REF] & 0x04, f"extra miner record 0 in slot 1: ObjRefs=${m.ram[REF]:02X}"

# --- the hook: ObjRefs bit 2 -> REFP1 bit 3 at the band swap -------------------
for refs, want in ((0x04, 0x08), (0x00, 0x00)):
    mem = Tia()
    r = mem.ram
    r[Z["RoomY"]] = 0
    r[Z["ObjBase1"]] = OBJ_MINER
    r[Z["ObjTop1"]] = 50                  # absolute y 49 -> band 1 (36..71)
    r[Z["ObjX1"]] = 80
    r[Z["ObjHeight1"]] = 16
    r[REF] = refs
    mem.bank = 0
    mpu = MPU(memory=mem)
    mpu.pc = L0["Slot1Hook"]
    mpu.x = 1                             # RowIdx = band 1
    mpu.y = 3
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(4000):
        mpu.step()
        if mpu.pc == L0["CaveLine"]:
            break
    else:
        sys.exit(f"Slot1Hook never reached CaveLine (pc=${mpu.pc:04X})")
    got = mem.refp1[-1] if mem.refp1 else None
    assert got == want, (f"Slot1Hook with ObjRefs=${refs:02X}: REFP1 writes "
                         f"{mem.refp1}, want ${want:02X}")

# --- the write sits BEFORE the aligning WSYNC (cycle-neutral) ------------------
hook = K.split("Slot1Hook:")[1].split(".SHout:")[0]
hook = "\n".join(ln for ln in hook.splitlines() if not ln.lstrip().startswith(";"))
assert hook.index("sta REFP1") < hook.index("sta WSYNC"), (
    "the REFP1 write must come before the hook's aligning `sta WSYNC`: after it "
    "the positioning line has no cycles to spare at far-right X")

print("test_miner_facing: OK (per-slot REFP1: level + extra miners, slot 0 and 1, hook)")
