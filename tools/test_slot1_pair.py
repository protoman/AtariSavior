#!/usr/bin/env python3
"""Slot-1 pairing + PinSlot0 (the two-band de-flicker) — the cross-bank path.

`StageSlot1` moved to bank2 on 2026-10-22 behind the split pad at $FBE5 (bank0
`sta $1FF8` -> bank2 `jmp StageSlot1B2` -> `jmp ReturnPad`). Unit-reading the
source cannot see a broken pad, so this drives the REAL entry (`jsr StageSlot1`
from bank0) through the bank switch, like tools/test_raft.py does for the raft
tramp.

Cases (fabricated enemy records in RAM, no stage data involved):
  1. two live candidates in DIFFERENT bands -> slot 1 = the higher one and
     PinSlot0 pins slot 0 to the other (FlickerFrame = desired + count - 1,
     because SelectActiveObject does `inc` before the modulo);
  2. same band -> no pair at all (ObjBase1 = $FF) and FlickerFrame untouched:
     one GRP1 cannot draw two objects on the same scanlines, so same-band
     rooms keep the 30 Hz rotation BY DESIGN. The live stage hit this in
     L2 room 2 (miner 87 / enemy 60) and L3 room 3 (miner 87 / enemy 48);
     L4 room 4 (miner 87 / enemy 96) is the case the pin exists for;
  3. the miner owns the top slot when it is the higher candidate.

Run: /home/iuri/python3/bin/python3 tools/test_slot1_pair.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_cell_map import Mem, parse_labels  # noqa: E402

SRC = Path(__file__).resolve().parent.parent / "src"
FROZEN = SRC / "tests" / "frozen"

LAB = parse_labels(FROZEN / "bank0.lst",
                   {"StageSlot1", "SelectActiveObject"})
if "StageSlot1" not in LAB:
    sys.exit("frozen bank0.lst has no StageSlot1 (re-freeze?)")

# ZP hand-copies (strings match src/docs/zp_layout_skill.md; the values are
# the RAM indices, i.e. ZP - $80).
Z = dict(EnemyCount=0x33, EnemyDeadMask=0x3A, EnemyRamY=0x62, EnemyRamX=0x3D,
         EnemyDataLo=0x31, EnemyDataHi=0x32, ObjBase1=0x6A, ObjTop1=0x6B,
         ObjX1=0x6C, FlickerFrame=0x34, DropTarget=0x0A, RoomNo=0x18,
         LevelMinerRoom=0x24, RoomY=0x01, ObjBase=0x36, MinerX=0x25,
         MinerY=0x26, ObjHeight1=0x1E, ObjHeight=0x1D, BombPacked=0x35)
# $EA/$EB/$EC -> RAM $6A/$6B/$6C; $B3/$BA/$BD/$E2/$B1/$B2/$B4/$8A/$98/$A4/$81
# $B6/$A5/$A6 -> the indices above. Assert rather than trust the table:
for name, idx in list(Z.items()):
    if idx is None:
        continue
    assert 0 <= idx < 0x80, name

MOTH, OBJ_MOTH, KEY_BYTE = 4, 16, 6
MOTH_H = 14        # MOTH art height (user design 2026-10-22) = ObjHeightTab[4]
REC = 0x01C0            # fabricated enemy-record base: the Mem model maps
                        # $0100-$01FF onto the 128-byte RAM, so the record
                        # aliases ZP $C0/$C3 — bytes StageSlot1/PinSlot0 never
                        # read (a $0180 base would alias RoomY at $81).


class Watch(Mem):
    """Bank-switching Mem that records which banks actually executed."""

    def __init__(self):
        super().__init__()
        self.banks = set()

    def __getitem__(self, a):
        self.banks.add(self.bank)
        return Mem.__getitem__(self, a)


def call_stage_slot1(*, ys, xs, types, miner=False, miner_y=0, flicker=0):
    mem = Watch()
    r = mem.ram
    n = len(ys)
    for i, (y, x, t) in enumerate(zip(ys, xs, types)):
        r[Z["EnemyRamY"] + i] = y
        r[Z["EnemyRamX"] + i] = x
        r[(REC & 0x7F) + i * 3] = t          # type|dir at record + slot*3
    r[Z["EnemyCount"]] = n
    r[Z["EnemyDeadMask"]] = 0
    r[Z["EnemyDataLo"]] = REC & 0xFF
    r[Z["EnemyDataHi"]] = REC >> 8
    r[Z["FlickerFrame"]] = flicker
    r[Z["DropTarget"]] = 0
    r[Z["RoomNo"]] = 0
    r[Z["LevelMinerRoom"]] = 0 if miner else 0x7F
    r[Z["MinerX"]] = 40
    r[Z["MinerY"]] = miner_y
    r[Z["RoomY"]] = 0
    r[Z["ObjBase"]] = OBJ_MOTH            # PinSlot0 skips only the bomb
    r[Z["ObjBase1"]] = 0xAA               # sentinel: must be rewritten
    mem.bank = 0
    from py65.devices.mpu6502 import MPU  # noqa: E402
    mpu = MPU(memory=mem)
    mpu.pc = LAB["StageSlot1"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01                     # RTS sentinel = $0101
    mem[0x1FE] = 0x00
    for _ in range(6000):
        mpu.step()
        if mpu.pc == 0x0101:
            break
    else:
        sys.exit(f"StageSlot1 never returned (pc=${mpu.pc:04X}, "
                 f"bank={mem.bank}, banks seen={sorted(mem.banks)})")
    assert mem.bank == 0, "the pad must switch back to bank0 (ReturnPad)"
    assert 2 in mem.banks, ("bank2 never executed — the $FBE5 pad / $FBE8 jmp "
                            "half is broken")
    return dict(base1=r[Z["ObjBase1"]], top1=r[Z["ObjTop1"]],
                x1=r[Z["ObjX1"]], flicker=r[Z["FlickerFrame"]],
                height1=r[Z["ObjHeight1"]])


# --- case 1: two enemies, bands 1 and 2 -> pair + pin ------------------------
got = call_stage_slot1(ys=[60, 96], xs=[71, 100], types=[MOTH, MOTH])
assert got["base1"] == OBJ_MOTH, f"slot 1 base ${got['base1']:02X} != 16"
assert got["x1"] == 100, f"slot 1 must be the higher-band enemy, X={got['x1']}"
assert got["top1"] == (96 - 0 + 1) & 0xFF, \
    f"ObjTop1={got['top1']} (must stay RoomY-relative)"
assert got["height1"] == MOTH_H, (
    f"ObjHeight1={got['height1']}, want {MOTH_H} (the MOTH art height): slot 1's "
    "draw window must travel with its design or a taller type would be clipped")
assert got["flicker"] == 1, (
    f"PinSlot0 FlickerFrame={got['flicker']}, want 1 = desired(0) + count(2) "
    "- 1: SelectActiveObject's `inc` must land on 0 next frame")

# --- case 2: same band -> no pair, rotation untouched ----------------------
got = call_stage_slot1(ys=[60, 84], xs=[71, 100], types=[MOTH, MOTH],
                       flicker=7)
assert got["base1"] == 0xFF, (
    f"same-band candidates must NOT pair (base1=${got['base1']:02X}): one GRP1 "
    "cannot draw two objects on the same scanlines")
assert got["flicker"] == 7, (
    f"FlickerFrame={got['flicker']}, want 7 (UNTOUCHED): PinSlot0 runs only on "
    "a real pair, so a same-band room keeps SelectActiveObject's rotation")

# --- case 3: the miner is the higher candidate ----------------------------
got = call_stage_slot1(ys=[60], xs=[71], types=[MOTH],
                       miner=True, miner_y=96)
K = (Path(__file__).resolve().parents[1] / "src" / "kernel.asm").read_text()
OBJ_MINER = int(re.search(r"^OBJ_MINER\s*=\s*(\d+)", K, re.M).group(1))
assert got["base1"] == OBJ_MINER, \
    f"slot 1 base ${got['base1']:02X} != OBJ_MINER {OBJ_MINER}"
assert got["x1"] == 40, f"slot 1 must be the miner, X={got['x1']}"
assert got["top1"] == (96 + 3 - 0 + 1) & 0xFF, (
    f"ObjTop1={got['top1']} — the miner's +3 draw offset must be included")

# --- case 4: a dir-left record (type | $80) must still resolve its design ---
# THE 2026-10-22 bug the user hit ("no tentacle, just a dash"): the record packs
# type|dir in one byte. Slot 1 indexed ObjSpriteOffTable/ObjHeightTab with the
# RAW byte ($80|type), read past the end of both tables and staged
# ObjBase1/ObjHeight1 = 0/0 — an object that can never draw. Mask b7 at the read.
got = call_stage_slot1(ys=[60, 96], xs=[71, 100], types=[MOTH, MOTH | 0x80])
assert got["base1"] == OBJ_MOTH, (
    f"dir-left record staged ObjBase1=${got['base1']:02X}, want ${OBJ_MOTH:02X}: "
    "the type byte's b7 (dir) must be masked before indexing the type tables")
assert got["height1"] == MOTH_H, (
    f"dir-left record staged ObjHeight1={got['height1']}, want {MOTH_H}")
assert got["x1"] == 100 and got["top1"] == (96 + 1) & 0xFF, (
    f"dir-left record staged the wrong slot: x1={got['x1']} top1={got['top1']}")

# --- case 5: the SAME masking in SelectActiveObject (slot 0) ---------------
def call_select_active_object(record_type):
    """One enemy, no miner: run SelectActiveObject, report what it staged."""
    mem = Watch()
    r = mem.ram
    r[Z["EnemyRamY"]] = 96
    r[Z["EnemyRamX"]] = 100
    r[REC & 0x7F] = record_type
    r[Z["EnemyCount"]] = 1
    r[Z["EnemyDeadMask"]] = 0
    r[Z["EnemyDataLo"]] = REC & 0xFF
    r[Z["EnemyDataHi"]] = REC >> 8
    r[Z["FlickerFrame"]] = 0
    r[Z["DropTarget"]] = 0
    r[Z["RoomNo"]] = 0
    r[Z["LevelMinerRoom"]] = 0x7F
    r[Z["BombPacked"]] = 0
    r[Z["ObjBase"]] = 0xAA
    mem.bank = 0
    from py65.devices.mpu6502 import MPU  # noqa: E402
    mpu = MPU(memory=mem)
    mpu.pc = LAB["SelectActiveObject"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(6000):
        mpu.step()
        if mpu.pc == 0x0101:
            break
    else:
        sys.exit(f"SelectActiveObject never returned (pc=${mpu.pc:04X}, "
                 f"bank={mem.bank})")
    return r[Z["ObjBase"]], r[Z["ObjHeight"]]


base, height = call_select_active_object(MOTH)
assert (base, height) == (OBJ_MOTH, MOTH_H), (
    f"plain record staged ObjBase=${base:02X} ObjHeight={height}, want "
    f"${OBJ_MOTH:02X}/{MOTH_H}")
base, height = call_select_active_object(MOTH | 0x80)
assert (base, height) == (OBJ_MOTH, MOTH_H), (
    f"dir-left record staged ObjBase=${base:02X} ObjHeight={height}, want "
    f"${OBJ_MOTH:02X}/{MOTH_H}: SelectActiveObject must mask b7 (dir) before "
    "indexing EnemyColorTable/ObjSpriteOffTable/ObjHeightTab")

# --- the height tables must be byte-identical (bank2 stages slot 1) --------
L2 = parse_labels(FROZEN / "bank2.lst", {"ObjHeightTab"})
L0 = parse_labels(FROZEN / "bank0.lst", {"ObjHeightTab"})
if "ObjHeightTab" not in L0 or "ObjHeightTab" not in L2:
    sys.exit("ObjHeightTab missing from a frozen listing (re-freeze?)")
b0 = (FROZEN / "bank0.bin").read_bytes()
b2 = (FROZEN / "bank2.bin").read_bytes()
t0 = b0[L0["ObjHeightTab"] - 0xF000:][:8]
t2 = b2[L2["ObjHeightTab"] - 0xF000:][:8]
assert t0 == t2, (f"ObjHeightTab twins differ: bank0 {t0.hex()} vs bank2 "
                  f"{t2.hex()} — a stale hand-copy would clip slot 1")
assert set(t0) <= {2, 6, 10, 14, 15, 16}, f"unexpected window rows {sorted(set(t0))}"
# SPIDER graduated to its own (15-row) art height: its declared draw window
# must equal the art block it occupies, or .Line reads into the next design.
assert t0[0] == 15, f"ObjHeightTab[SPIDER]={t0[0]}, want 15 (15-row art)"
_sp = int(re.search(r"^OBJ_LAMP\s*=\s*(\d+)", K, re.M).group(1))
_sp0 = int(re.search(r"^OBJ_SPIDER\s*=\s*(\d+)", K, re.M).group(1))
assert _sp - _sp0 == t0[0], (
    f"SPIDER art block is {_sp - _sp0} B but ObjHeightTab says {t0[0]} rows")

print("OK: slot-1 pairing across banks + PinSlot0 (pair, same-band skip, miner) "
      "+ ObjHeightTab twins identical")


def _checkpage():  # pragma: no cover - documented invariant, checked above
    pass
