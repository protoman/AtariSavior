#!/usr/bin/env python3
"""Menu flow behavioral test — merged title over the live stage (no Stella).

Boots the real savior.bin in py65 and walks the console-switch flow against
DropTarget ($8A) / Level ($A3) / score state.  Since 2026-10-19 there is ONE
title screen ($FF sentinel): the CAVE stage is previewed with the logo and
credits drawn over it, the theme plays, and the HUD score shows level+1.

  1. boot    — title sentinel $FF; stays $FF while idle; score = level+1;
  2. select  — SELECT held 3 frames increments Level exactly ONCE
               (edge, not level-triggered), keeps $FF and refreshes ScoreTe;
  3. cycle   — LEVEL_COUNT presses cycle Level 0..N-1 and wrap to 0;
  4. start   — title RESET edge: score forced 000000, drop-in arms
               (DROPT = fall Y), lands at DROPT==0 = gameplay;
  5. gate    — SELECT held mid-fall never bounces to title (idle gate:
               DROPT==0 exactly);
  6. return  — landed + idle: SELECT returns to the title $FF;
               a second title RESET starts the game again.

Run: /home/iuri/python3/bin/python3 tools/test_menu_flow.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(8)]

DROPT = 0x0A               # DropTarget ($8A)
LEVEL = 0x23               # Level ($A3) 0-based
SC_TH, SC_HU, SC_TE = 0x73, 0x74, 0x75

REL = 0xFF                 # SWCHB: both released (active low)
RST = 0xFE                 # RESET pressed
SEL = 0xFD                 # SELECT pressed

kernel_src = (SRC / "kernel.asm").read_text()
m = re.search(r"^LEVEL_COUNT\s*=\s*(\d+)", kernel_src, re.M)
if not m:
    sys.exit("LEVEL_COUNT not found in kernel.asm")
LEVEL_COUNT = int(m.group(1))


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3                     # F6 power-up bank
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x40

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.banks_[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            return 0                     # INTIM expired -> waits pass
        if a == 0x000C:
            return self.inpt4
        if 0x1FF4 <= a <= 0x1FFB:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF4 <= a <= 0x1FFB:
            self.bank = a - 0x1FF4
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
mem.banks_ = BANKS

from py65.devices.mpu6502 import MPU
mpu = MPU(memory=mem)

_LBL = {}
for _l in open(SRC / "bank0.lst", errors="replace"):
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$",
                  _l)
    if _m:
        _LBL.setdefault(_m.group(2), int(_m.group(1), 16))
if "StartFrame" not in _LBL:
    sys.exit("label StartFrame not found in bank0.lst")
PC_STARTFRAME = _LBL["StartFrame"]

frame = -1
fails = []
title_seen = False
fd_seen = False


def step():
    mpu.step()


def next_frame(sw=REL):
    """Advance to the next frame boundary; arm SWCHB for that frame."""
    global frame, title_seen, fd_seen
    guard = 0
    while True:
        step()
        guard += 1
        if guard > 40000:
            sys.exit(f"frame stalled at f{frame} (no StartFrame?)")
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            frame += 1
            mem.swchb = sw
            d = mem.ram[DROPT]
            if d == 0xFF:
                title_seen = True
            if d == 0xFD:
                fd_seen = True
            return


def run(n, sw=REL):
    for _ in range(n):
        next_frame(sw)


def score():
    return (mem.ram[SC_TH] * 1000 + mem.ram[SC_HU] * 100
            + (mem.ram[SC_TE] >> 4) * 10 + (mem.ram[SC_TE] & 15))


def check(cond, msg):
    if not cond:
        fails.append(msg)


# ---- 1. boot: title over the stage, stays $FF while idle ----------------
guard = 0
while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
    step()
    guard += 1
    if guard > 300000:
        sys.exit("never reached StartFrame")
frame = 0

run(2)
check(mem.ram[DROPT] == 0xFF,
      f"boot should show the merged title $FF, got ${mem.ram[DROPT]:02X}")
check(mem.ram[SC_TE] == 1 and mem.ram[SC_TH] == 0 and mem.ram[SC_HU] == 0,
      f"title score must show level+1 (1): TH/HU/TE="
      f"{mem.ram[SC_TH]}/{mem.ram[SC_HU]}/{mem.ram[SC_TE]}")
run(10)
check(mem.ram[DROPT] == 0xFF,
      f"title must hold $FF while idle, got ${mem.ram[DROPT]:02X}")

# ---- 2. SELECT edge-once-while-held --------------------------------------
lvl0 = mem.ram[LEVEL]
for _ in range(3):           # held 3 frames -> exactly one edge
    next_frame(SEL)
run(3)
check(mem.ram[LEVEL] == (lvl0 + 1) % LEVEL_COUNT,
      f"SELECT held 3f must inc Level once: {lvl0} -> {mem.ram[LEVEL]}, "
      f"want {(lvl0 + 1) % LEVEL_COUNT}")
check(mem.ram[DROPT] == 0xFF,
      f"SELECT must keep the merged title $FF, got ${mem.ram[DROPT]:02X}")
check(mem.ram[SC_TE] == mem.ram[LEVEL] + 1 and mem.ram[SC_HU] == 0,
      f"title score must follow the selected level: TE={mem.ram[SC_TE]} "
      f"level={mem.ram[LEVEL]}")

# ---- 3. full SELECT cycle: LEVEL_COUNT edges -> exact wrap ---------------
start = mem.ram[LEVEL]
seen = [start]
for k in range(LEVEL_COUNT):
    next_frame(SEL)          # one pressed frame
    run(4)                   # release + LoadLevel settle
    check(mem.ram[DROPT] == 0xFF,
          f"SELECT #{k + 1}: title state lost, DROPT=${mem.ram[DROPT]:02X}")
    seen.append(mem.ram[LEVEL])
want = [(start + k) % LEVEL_COUNT for k in range(LEVEL_COUNT + 1)]
check(seen == want, f"SELECT cycle levels {seen}, want {want}")
check(mem.ram[LEVEL] == start, f"wrap not exact: {mem.ram[LEVEL]} != {start}")

# ---- 4. title RESET -> game (score zeroed, drop-in lands) ---------------
run(4)
next_frame(RST)
run(2)
check(score() == 0, f"title RESET must zero the score, got {score()}")
check(mem.ram[DROPT] not in (0xFF, 0xFD),
      f"title RESET must leave title, DROPT=${mem.ram[DROPT]:02X}")
landed = None
for _ in range(400):
    next_frame(REL)
    if mem.ram[DROPT] == 0:
        landed = frame
        break
check(landed is not None, "drop-in never landed (DROPT stuck)")
run(6)
check(mem.ram[DROPT] == 0,
      f"gameplay must stay idle, DROPT=${mem.ram[DROPT]:02X}")

# ---- 5. bounce gate: SELECT mid-fall never returns to title -------------
next_frame(SEL)              # idle SELECT -> merged title
run(4)
check(mem.ram[DROPT] == 0xFF,
      f"idle SELECT -> title $FF, got ${mem.ram[DROPT]:02X}")
next_frame(RST)
# wait for the fall to arm (DROPT = fall Y, a small nonzero non-sentinel)
for _ in range(60):
    next_frame(REL)
    if mem.ram[DROPT] not in (0xFF, 0xFD, 0xFE, 0):
        break
else:
    check(False, "fall never armed after title RESET")
fall_seen = mem.ram[DROPT]
held = 0
while mem.ram[DROPT] != 0 and held < 40:
    next_frame(SEL)          # held during the fall
    held += 1
check(mem.ram[DROPT] != 0xFF,
      f"SELECT mid-fall bounced to title (DROPT=$FF after {held} held frames)")
# release well before landing; the drop must complete
for _ in range(200):
    next_frame(REL)
    if mem.ram[DROPT] == 0:
        break
check(mem.ram[DROPT] == 0,
      f"game never completed after SELECT release (DROPT=${mem.ram[DROPT]:02X}, "
      f"fall was ${fall_seen:02X})")

# ---- 6. gameplay -> title -> game again (repeatable) --------------------
run(5)
next_frame(SEL)
run(4)
check(mem.ram[DROPT] == 0xFF,
      f"landed SELECT -> merged title, got ${mem.ram[DROPT]:02X}")
next_frame(RST)
for _ in range(400):
    next_frame(REL)
    if mem.ram[DROPT] == 0:
        break
check(mem.ram[DROPT] == 0,
      f"second game start never landed, DROPT=${mem.ram[DROPT]:02X}")

# ---- global: the retired $FD sentinel never appears ---------------------
check(title_seen, "merged title $FF never ran")
check(not fd_seen, "retired $FD sentinel appeared")

if fails:
    print(f"FAIL: {len(fails)} menu-flow violations:")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print(f"test_menu_flow: OK (title $FF -> select x{LEVEL_COUNT} wrap -> game -> "
      f"bounce gate -> title -> game, {frame} frames)")
