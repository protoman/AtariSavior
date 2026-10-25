#!/usr/bin/env python3
"""Per-frame kernel probe — frame length, body lines per band, slot-1 hook gaps.

Why this exists: `sim_frame_budget.py` tells you the frame is 271 instead of
270, but not WHICH WSYNC segment stole the line. This runs the real ROM in
py65, pokes Level/RoomNo exactly like the sim does, and reports per frame:

  lines   frame length in scanlines ((vsync - prev_vsync) / 76)
  bodies  WSYNC writes per band (RowIdx), i.e. how many body lines each pass ran
  hook    every WSYNC inside Slot1Hook ($F770-$F7D0) as (pc, cycles since the
          previous WSYNC) — the 2nd/3rd entries are the positioning line and
          the div15 line

A gap > 152c means that segment straddled 2 line boundaries (a stolen line);
> 76c is normal for a band setup (the .Row pass owns the whole line).

Usage:
  probe_kernel.py LEVEL ROOM [FROM] [TO]        # 0-based LEVEL and ROOM
  probe_kernel.py 4 1 20 26                     # level 5, room 2, frames 20-26

Notes / traps learned the hard way (2026-10-25):
  * the ROM boots into the TITLE; the console RESET line (SWCHB b0) must be
    held for a few frames or the game never starts (DropTarget stays $FF) and
    `EnterRoom` is never reached with a real DropTarget;
  * WSYNC modelling needs the flag cleared after each stall, otherwise the
    wall clock inflates;
  * `RowIdx` ($92) aliases RectCount, so it is only a band index inside the
    kernel — read it at the WSYNC, never between frames;
  * hook gaps are stable across rooms (197c + 103c measured), so a room that
    measures 270 while another measures 271 differs somewhere ELSE: use the
    per-pc diff (see docs/handoff_2026-10-25_flicker.md) to find it.
"""
import re
import sys
from collections import Counter
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(8)]

LABELS = {}
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$", _l)
    if _m:
        LABELS.setdefault(_m.group(2), int(_m.group(1), 16))

EQU = {}
for _line in (SRC / "kernel.asm").read_text(errors="replace").splitlines():
    _m = re.match(r"^([A-Za-z_][A-Za-z_0-9]*)\s*=\s*\$([0-9a-fA-F]+)", _line)
    if _m and int(_m.group(2), 16) <= 0xFF:
        EQU[_m.group(1)] = int(_m.group(2), 16)


def zp(name):
    """Zero-page address of `name` (EQU first, then the sequential byte block)."""
    if name in EQU:
        return EQU[name]
    addr = None
    for line in (SRC / "kernel.asm").read_text(errors="replace").splitlines():
        if re.match(r"\s*org\s+\$80\b", line):
            addr = 0x80
            continue
        if addr is None:
            continue
        if re.match(rf"^{re.escape(name)}\s+byte\b", line):
            return addr
        if re.match(r"^[A-Za-z_][A-Za-z_0-9]*\s+byte\b", line):
            addr += 1
    return None


Z = {n: zp(n) for n in ("RoomY", "RoomNo", "LineCount", "RowIdx", "Level",
                        "DropTarget")}

wsync_log = []          # (pc, wall, LineCount, RowIdx)
vsync_walls = []        # wall of every VSYNC pulse (frame boundary clock)
frame_no = 0


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 7
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0
        self.wsync_seen = False
        self.wall = 0
        self.deadline = {}
        self.pc = 0

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
        if a == 0x0284:                     # INTIM: derive from TIM64T deadline
            dl = self.deadline.get(0x296, 0)
            if self.wall >= dl:
                return 0
            return min(0xFF, max(1, (dl - self.wall + 63) // 64))
        if a == 0x000C:
            return self.inpt4
        if 0x1FF4 <= a <= 0x1FF7:           # F4 hotspots: reads must not switch
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF4 <= a <= 0x1FF7:
            self.bank = a - 0x1FF4
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            mult = {0x294: 1024, 0x296: 64, 0x297: 8}[a]
            self.deadline[a] = self.wall + v * mult
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            reg = a & 0x3F
            if reg == 0 and v == 2:         # VSYNC on -> frame boundary
                vsync_walls.append(self.wall)
            if reg == 2:                    # WSYNC: record site + gap source
                self.wsync_seen = True
                wsync_log.append((self.pc, self.wall,
                                  self.ram[Z["LineCount"] - 0x80],
                                  self.ram[Z["RowIdx"] - 0x80]))
            self.tia[reg] = v


mem = Mem()
from py65.devices.mpu6502 import MPU        # noqa: E402

mpu = MPU(memory=mem)
prev_cycles = 0


def step():
    global prev_cycles, frame_no
    mpu.step()
    mem.pc = mpu.pc
    c = mpu.processorCycles - prev_cycles
    prev_cycles = mpu.processorCycles
    mem.wall += c
    if mem.wsync_seen:
        w = mem.wall
        mem.wall = (w // 76 + 1) * 76 if w % 76 else w
        mem.wsync_seen = False              # ONE stall per WSYNC write
    if len(vsync_walls) > frame_no:
        frame_no = len(vsync_walls)
        # console RESET: the title screen needs the PRESS EDGE and the RELEASE,
        # so pulse it on two isolated frames — holding it makes the game restart
        # every frame and it never reaches gameplay (this cost an hour once).
        mem.swchb = 0xFE if frame_no in (1, 8) else 0xFF


BODY_LO = LABELS["CaveLine"]
BODY_HI = BODY_LO + 0x80
HOOK_LO = LABELS.get("Slot1Hook", LABELS["CaveLine"]) - 0x10
HOOK_HI = HOOK_LO + 0x80

LEVEL = int(sys.argv[1])
ROOM = int(sys.argv[2])
F0 = int(sys.argv[3]) if len(sys.argv) > 3 else 20
F1 = int(sys.argv[4]) if len(sys.argv) > 4 else F0

printed = -1
poked_level = poked_room = False
while frame_no <= F1:
    step()
    if mem.bank == 0 and not poked_level and mpu.pc == LABELS["LoadLevel"]:
        mem.ram[Z["Level"] - 0x80] = LEVEL
        poked_level = True
    if mem.bank == 0 and poked_level and not poked_room \
            and mpu.pc == LABELS["EnterRoom"] \
            and mem.ram[Z["DropTarget"] - 0x80] not in (0xFF, 0xFD):
        mpu.a = ROOM
        poked_room = True
    if len(vsync_walls) > 1 and frame_no >= F0 and frame_no != printed \
            and mem.ram[Z["RoomNo"] - 0x80] == ROOM:
        # ONE report per frame boundary: the condition stays true for the whole
        # frame, so a missing guard prints (and clears the log) per instruction
        # and every report comes out empty.
        printed = frame_no
        f = frame_no
        lines = (vsync_walls[-1] - vsync_walls[-2]) / 76
        prev_wall = None
        bodies = Counter()
        hook = []
        for (pc, wall, lc, band) in wsync_log:
            gap = 0 if prev_wall is None else wall - prev_wall
            prev_wall = wall
            # body WSYNCs: the .Line loop's tail sits inside CaveLine+$00..$70.
            # Range-based on purpose — hardcoded addresses go stale with every
            # bank0 edit (and a stale $F138 silently reported "no bodies").
            if BODY_LO <= pc <= BODY_HI:
                bodies[band] += 1
            if HOOK_LO <= pc <= HOOK_HI:
                hook.append((pc, gap))
        print(f"f{f:4d} lines {lines:6.2f} "
              f"bodies {dict(sorted(bodies.items()))} "
              f"hook {[(hex(p), g) for p, g in hook]}", flush=True)
        wsync_log.clear()
