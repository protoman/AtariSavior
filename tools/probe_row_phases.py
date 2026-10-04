#!/usr/bin/env python3
"""Phase 0 probe (asymmetric_pf_plan): dump our kernel's .Row setup-line
write phases on a real gameplay frame.

Answers: (1) CPU phase of PF0/PF1/PF2/COLUPF/COLUBK stores on each cave
setup line (plan expects PF0 c34, PF1 c41, COLUPF c48, COLUBK c54, PF2 c61),
(2) the free window between the last PF store and the line's WSYNC (how many
cycles a late right-trio block could use), (3) proof that cave body lines
carry no PF writes.

Run:  /home/iuri/python3/bin/python3 tools/probe_row_phases.py
Self-contained (pattern: src/sim_frame_budget.py, docs/hero_asymmetric_rooms.md).
"""
import os
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(4)]

LABELS = {}
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$", _l)
    if _m:
        LABELS.setdefault(_m.group(2), int(_m.group(1), 16))
for _need in ("StartFrame", "EnterRoom", "LoadLevel"):
    if _need not in LABELS:
        sys.exit(f"label {_need} not found in bank0.lst")
PC_START = LABELS["StartFrame"]
PC_ENTER = LABELS["EnterRoom"]
PC_LOADLEVEL = LABELS["LoadLevel"]
IDX_LEVEL = 0x23          # $A3 Level

# DropTarget ZP index (decl walk, same as sim_frame_budget)
DROP_IDX = None
_addr = None
for _line in (SRC / "kernel.asm").read_text(errors="replace").splitlines():
    if re.match(r"\s*org\s+\$80\b", _line):
        _addr = 0x80
        continue
    if _addr is None:
        continue
    if re.match(r"^DropTarget\s+byte\b", _line):
        DROP_IDX = _addr - 0x80
        break
    if re.match(r"^[A-Za-z_][A-Za-z_0-9]*\s+byte\b", _line):
        _addr += 1
if DROP_IDX is None:
    sys.exit("DropTarget ZP decl not found")


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3                 # F6 power-up
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x00             # fire held (laser path active)
        self.wall = 0
        self.wsync_seen = False
        self.deadline = {}
        self.writes = []              # [(wall, addr, val)] TIA stores only

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
            dl = self.deadline.get(0x296, 0)
            if self.wall >= dl:
                return 0
            return min(0xFF, max(1, (dl - self.wall + 63) // 64))
        if a == 0x000C:
            return self.inpt4
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
            mult = {0x0294: 1024, 0x0296: 64, 0x0297: 8}[a]
            self.deadline[a] = self.wall + v * mult
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            self.writes.append((self.wall, a & 0x3F, v))
            if (a & 0x3F) == 2:
                self.wsync_seen = True
            self.tia[a & 0x3F] = v


mem = Mem()
from py65.devices.mpu6502 import MPU
mpu = MPU(memory=mem)

prev_cycles = 0


def step():
    global prev_cycles
    mpu.step()
    c = mpu.processorCycles - prev_cycles
    prev_cycles = mpu.processorCycles
    mem.wall += c
    if mem.wsync_seen:
        w = mem.wall
        mem.wall = (w // 76 + 1) * 76 if w % 76 else w
        mem.wsync_seen = False
    return c


# ---- boot poke: level (same as sim_frame_budget) ----
poked_level = poked_room = False
steps = 0
while not poked_level:
    step()
    steps += 1
    pc, bk = mpu.pc, mem.bank
    if bk == 0 and pc == PC_LOADLEVEL:
        mem.ram[IDX_LEVEL] = 1
        poked_level = True
    if steps > 4_000_000:
        sys.exit("never reached boot poke (LoadLevel)")

# ---- run: console-RESET pulse on title (sim frames 1-2), room poke at the
# ---- gameplay EnterRoom, capture frame CAPTURE_FRAME until the next StartFrame
CAPTURE_FRAME = int(os.environ.get("PROBE_FRAME", "30"))
NAMES = {0x0D: "PF0", 0x0E: "PF1", 0x0F: "PF2", 0x08: "COLUPF",
         0x09: "COLUBK", 0x0A: "CTRLPF"}
PF_REGS = {0x0D, 0x0E, 0x0F}

frame = -1
armed = False
frame_wall = None
start_capture = False

while True:
    step()
    pc, bk = mpu.pc, mem.bank
    if bk == 0 and frame >= 0:
        mem.swchb = 0xFE if frame in (1, 2) else 0xFF
        if (not poked_room and pc == PC_ENTER
                and mem.ram[DROP_IDX] != 0xFF):
            mpu.a = 1                  # RoomNo
            poked_room = True
    if bk == 0 and pc == PC_START:
        if armed:
            frame += 1
            if start_capture:
                break                # frame CAPTURE_FRAME finished
            if frame == CAPTURE_FRAME:
                frame_wall = mem.wall
                mem.writes.clear()
                start_capture = True
        armed = True
        if frame >= 400:
            sys.exit("never reached capture frame")

wall0 = frame_wall - (frame_wall % 76)   # snap to scanline boundary (WSYNC
                                         # aligns wall to multiples of 76)
writes = [(w - wall0, a, v) for w, a, v in mem.writes]

# group TIA writes by scanline (wall//76 relative to frame start)
from collections import defaultdict
by_line = defaultdict(list)
for rel, a, v in writes:
    by_line[rel // 76].append((rel % 76, a, v))

print(f"capture frame {CAPTURE_FRAME}: {len(writes)} TIA writes, "
      f"lines 0..{max(by_line) if by_line else 0}")

# cave band: find lines carrying PF writes, report phases + free window
pf_lines = sorted(ln for ln, ws in by_line.items()
                  if any(a in PF_REGS for _, a, _ in ws))
print("\nsetup lines (any PF write):")
for ln in pf_lines:
    ws = sorted(by_line[ln])
    stores = []
    last_pf = None
    for ph, a, v in ws:
        if a in NAMES:
            stores.append(f"{NAMES[a]}@{ph}={v:02X}")
            if a in PF_REGS:
                last_pf = ph
    wsyncs = [ph for ph, a, _ in ws if a == 2]
    free = None
    if last_pf is not None and wsyncs:
        after = [w for w in wsyncs if w > last_pf]
        free = after[0] - last_pf if after else None
    tag = ""
    if free is not None:
        tag = f"  free(lastPF->WSYNC)={free}c"
    print(f"  line {ln:3d}: {' '.join(stores)}{tag}")

# body check: PF writes outside setup lines + COLUPF/COLUBK activity in cave
cave_pf = [(ln, ph, NAMES[a], v) for ln, ws in by_line.items()
           if 40 <= ln <= 180 for ph, a, v in ws if a in PF_REGS]
print(f"\nPF writes in lines 40..180: {len(cave_pf)}")
