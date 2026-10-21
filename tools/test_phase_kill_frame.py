#!/usr/bin/env python3
"""Tile 11 removal at full-frame scale — a $81 record cannot kill (py65).

Tile 11 (VCRUNCH) was removed 2026-10-19. This test still stages the
frozen model2 fixture (test-owned, carries a retired $81 bbox record +
MetaB $80) because it must prove the RETIRED path is inert in a real
game frame:

  * boot, land, stage model2 (PF + meta + rect/hot stream),
  * pin the player at the OLD kill spot (x127/y48, clock 64 = the old
    "closing" phase) and hold RIGHT so PlayerHitsMap/hot-overlap runs
    every frame,
  * the HOV feature dispatcher must reach the record (feat > 0) and
    pass it (unknown class), so NO life is lost and EnemyDeadMask b7
    (the retired crunch latch) is never set;
  * bank2's $FE57 entry image is no longer `jmp $FD80` (VCS3 gone).

Run: /home/iuri/python3/bin/python3 tools/test_phase_kill_frame.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [bytearray(open(SRC / f"bank{i}.bin", "rb").read()) for i in range(4)]


def lst_labels(path):
    out = {}
    for _l in Path(path).read_text(errors="replace").splitlines():
        _m = re.match(
            r"^\s+\d+\s+([0-9a-f]{4})\s+([.]?[A-Za-z_][A-Za-z0-9_]*)", _l)
        if _m:
            out[_m.group(2)] = int(_m.group(1), 16)
    return out


L0 = lst_labels(SRC / "bank0.lst")
L1 = lst_labels(SRC / "bank1.lst")
L2 = lst_labels(SRC / "bank2.lst")
L3 = lst_labels(SRC / "bank3.lst")   # C7: shape blocks + HOV walker (bank3)

import test_fixtures as FX  # noqa: E402
PC_STARTFRAME = L0["StartFrame"]
PC_PHM = L0["PlayerHitsMap"]
PC_HOF = L0["HotOverlapFlag"]
PC_OVERLAY = L0["OverlayTramp"]
PC_STEPD = L0["StepDown"]
PC_STEPS = L0["StepUp"]
PC_HOV = L3["HotOverlapBody"]
PC_BUMPCHK = 0xF303         # bank0: lda Temp / bpl .NoHotBump (overscan)
PC_LOSECALL = L0["LoseLife"]  # entry — kill rides the KERNEL hot-bump
                              # (Temp b7 -> jsr LoseLife), not F305
PC_HOV_FEAT = L3[".HOVfeature"]
# C11: a shape block carries no record stream, so the fixture stages the
# feature stream in test-owned ZP ($CC-$DF are free since C4).
STREAM_ADDR = 0xCC


def _b3_pc(pattern: str) -> int:
    """PC of the first bank3.lst row whose source matches `pattern`."""
    for _l in (SRC / "bank3.lst").read_text(errors="replace").splitlines():
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+", _l)
        if _m and re.search(pattern, _l):
            return int(_m.group(1), 16)
    raise SystemExit(f"bank2.lst: no row matching {pattern!r}")


PC_HOV_BEQCNT = _b3_pc(r"beq\s+\.HOVdone")      # hot count==0 -> skip
# C11: non-feature records are skipped with `bpl HOVnext`; the feature
# path is a tail jmp, so pin that instead of the old bmi.
PC_HOV_BMI = _b3_pc(r"jmp\s+\.HOVfeature")
PC_HOV_JMP = _b3_pc(r"jmp\s+HOVafterGate")
PC_HOV_ORA = _b3_pc(r"ora\s+#%10000000")

STREAM_ADDR = 0xA0         # C11: synthetic record stream (test-owned RAM)

I_ROOMX, I_ROOMY = 0x00, 0x01
I_VYLO, I_VYHI = 0x13, 0x14
I_DROPT = 0x0A
I_BOMBP = 0x35
I_ENCOUNT = 0x33
I_DEAD = 0x3A            # EnemyDeadMask
I_RP = 0x42              # EnemyRamP ($C2)
I_LIVES = 0x2C           # PlayerLives ($AC)
I_CCX, I_CCY = 0x0C, 0x0D  # CollisionCellX / CollisionCellY ($8C/$8D)
I_CEX, I_CEFY = 0x0E, 0x0F  # CollisionEndX / CollisionEndY ($8E/$8F)
I_TEMP = 0x08            # Temp ($88)
I_RRLO, I_RRHI = 0x10, 0x11  # RoomRectsLo/Hi
I_PF0LO, I_PF0HI = 0x19, 0x1A  # RoomPF0Lo/Hi (StageBandTab MetaA/MetaB)
I_PF1BAND1 = 0x47          # PF1Buf band1 row1 ($C7) — V punch lives here

CELL_X, CELL_Y = 127, 48   # inside the containment window (frozen fixture
                           # BallX=127: lit [x-6,x] within block [120,127]
                           # iff x in {126,127}; 125 is a side brush now),
                           # y48 = crunched BELOW the [66,79) aperture
                           # (Rule 1 2026-10-14: cold kills only while
                           # CLOSING and not totally closed)
CLOCK = 64                 # $1B CLOSING (sc=16 < 32) — the kill phase;
                           # 100 = $1F (closed) is a wall now, no kill
ARM_FRAME = 90            # frames to run after arming
RESPAWN_FRAME = 150       # frames to let DropArm respawn settle


def load_room_m2():
    """Stage model2 (the retired vcrunch room: $81 bbox record + MetaB $80)
    after boot — start_room-agnostic.

    C11 (2026-10-21): a shape block is 3 row-pool indices and carries NO
    record stream, so the fixture stages the frozen $81 stream as synthetic
    RAM data (test-owned) and points RoomRects at it. The meta pair still
    comes from test_fixtures' frozen constants."""
    a_rr = STREAM_ADDR
    mem.ram[I_PF0LO] = FX.METAX[2][0]
    mem.ram[I_PF0HI] = FX.METAX[2][1]
    mem.ram[I_RRLO] = a_rr & 0xFF
    mem.ram[I_RRHI] = a_rr >> 8
    FX.stage_stream(mem.ram, a_rr, FX.M2_STREAM)
    for i, dst in enumerate((0xC3, 0xC6, 0xC9)):
        for row in range(3):
            mem.ram[(dst + row) & 0x7F] = FX.PFX[2][i * 3 + row]


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
hits = []       # (frame, ccx, ccy, cex, cefy, dead, roomx, roomy)
hovs = []       # (frame, b5, dead, ccx, ccy, temp)
loses = []
counts = {"phm": 0, "miss": 0, "stepd": 0, "stepu": 0, "bumpchk": 0,
          "losecall": 0, "tempb7": 0, "beqdone": 0, "bmi": 0,
          "feat": 0, "jmpag": 0, "ora": 0}
miss_box = []
tempb7_first = []


def step():
    global frame
    mpu.step()
    if mem.bank == 0 and mpu.pc == PC_PHM:
        counts["phm"] += 1
    if mem.bank == 0 and mpu.pc == PC_OVERLAY:
        counts["miss"] += 1
        miss_box.append((frame, mem.ram[I_CCX], mem.ram[I_CCY],
                         mem.ram[I_CEX], mem.ram[I_CEFY]))
    if mem.bank == 0 and mpu.pc == PC_STEPD:
        counts["stepd"] += 1
    if mem.bank == 0 and mpu.pc == PC_STEPS:
        counts["stepu"] += 1
    if mem.bank == 0 and mpu.pc == PC_BUMPCHK:
        counts["bumpchk"] += 1
        if mem.ram[I_TEMP] & 0x80:
            counts["tempb7"] += 1
    if mem.bank == 0 and mpu.pc == PC_LOSECALL:
        counts["losecall"] += 1
        loses.append(frame)
    if mem.bank == 3:      # C7: bank3 owns the hot walker
        if mpu.pc == PC_HOV_BEQCNT:
            counts["beqdone"] += 1
        elif mpu.pc == PC_HOV_BMI:
            counts["bmi"] += 1
        elif mpu.pc == PC_HOV_FEAT:
            counts["feat"] += 1
        elif mpu.pc == PC_HOV_JMP:
            counts["jmpag"] += 1
        elif mpu.pc == PC_HOV_ORA:
            counts["ora"] += 1
    if (mem.ram[I_TEMP] & 0x80) and not tempb7_first:
        tempb7_first.append((frame, mpu.pc, mem.bank))
    if mem.bank == 0 and mpu.pc == PC_HOF:
        hits.append((frame, mem.ram[I_CCX], mem.ram[I_CCY],
                     mem.ram[I_CEX], mem.ram[I_CEFY],
                     mem.ram[I_DEAD], mem.ram[I_ROOMX], mem.ram[I_ROOMY]))
    if mem.bank == 3 and mpu.pc == PC_HOV:
        hovs.append((frame, (mem.ram[I_DEAD] >> 5) & 1, mem.ram[I_DEAD],
                     mem.ram[I_CCX], mem.ram[I_CCY], mem.ram[I_TEMP]))
        if len(hovs) == 1:
            rr = mem.ram[I_RRLO] | (mem.ram[I_RRHI] << 8)
            fp_lo = mem.ram[0x65] | (mem.ram[0x66] << 8)   # FetchPtr $E5/$E6
            print(f"HOV1: RoomRects*=${rr:04X} FetchPtr=${fp_lo:04X} "
                  f"stream[0:11]=" +
                  " ".join(f"{mem[rr + i]:02X}" for i in range(11)))
    if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
        frame += 1


def pin():
    mem.ram[I_VYLO] = 0
    mem.ram[I_VYHI] = 0
    mem.ram[I_ROOMX] = CELL_X
    mem.ram[I_ROOMY] = CELL_Y
    mem.ram[I_ENCOUNT] = 0
    mem.ram[I_DROPT] = 0
    mem.ram[I_RP] = CLOCK          # frame clock -> VcrCoveredState = $1F
    mem.swcha = 0x7F          # hold RIGHT (D7=0): PHM proposes every
                              # frame -> punched-cell MISS -> OvShutBand
    mem.inpt4 = 0x80


def main():
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
    print(f"landed f{landed}")

    load_room_m2()
    loses_boot = len(loses)
    mem.ram[I_DEAD] = 0x00
    mem.ram[I_RP] = CLOCK
    lives0 = mem.ram[I_LIVES]
    print(f"start: lives={lives0} dead=${mem.ram[I_DEAD]:02X}")

    arm_f0 = frame
    while frame < arm_f0 + ARM_FRAME:
        pin()
        step()

    dead_now = mem.ram[I_DEAD]
    loses_now = len(loses) - loses_boot
    print(f"after {frame - arm_f0} frames: lives={mem.ram[I_LIVES]} "
          f"dead=${dead_now:02X} loses={loses_now} counts={counts}")

    # ---- retired path is inert: no kill, no latch, but the record was met
    if mem.ram[I_LIVES] != lives0:
        sys.exit(f"FAIL: tile 11 killed the player — lives {lives0} -> "
                 f"{mem.ram[I_LIVES]}")
    if loses_now != 0:
        sys.exit(f"FAIL: LoseLife fired {loses_now} time(s) for a $81 record")
    if dead_now & 0x80:
        sys.exit(f"FAIL: retired b7 crunch latch set — dead=${dead_now:02X}")
    if counts["feat"] == 0:
        sys.exit("FAIL: the $81 record never reached HOVFeatEntry "
                 "(staging broken — test proves nothing)")

    # ---- ROM: the VCS3 entry image is gone ------------------------------
    img = BANKS[2][0xE57:0xE5A]
    if img == bytes((0x4C, 0x80, 0xFD)):
        sys.exit("FAIL: bank2 $FE57 still holds jmp $FD80 (VCS3 tramp)")

    print("test_phase_kill_frame: OK ($81 record reaches the dispatcher and "
          "is inert; no kill, no latch; VCS3 tramp gone)")


if __name__ == "__main__":
    main()
