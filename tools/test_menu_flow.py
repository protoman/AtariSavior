#!/usr/bin/env python3
"""Menu flow behavioral test — bugs.md #13 (self-test, no Stella needed).

Boots the real savior.bin in py65 and walks the full console-switch flow
against DropTarget ($8A) / Level ($A3) / score state:

  1. boot    — intro sentinel $FD shows; first RESET edge exits to old
               title $FF (never returns to $FD for the whole run);
  2. title   — idle holds $FF (no auto-advance); SELECT held 3 frames
               increments Level exactly ONCE (edge, not level-triggered);
  3. select  — LEVEL_COUNT presses cycle Level 0..N-1 and wrap to 0
               (display level = Level+1, so wrap 000004 -> 000001 with
               the current LEVEL_COUNT=4), title state kept ($FF);
  4. start   — title RESET edge: score forced 000000, drop-in arms
               (DROPT = fall Y), lands at DROPT==0 = gameplay;
  5. gate    — SELECT held mid-fall never bounces to title (idle gate:
               DROPT==0 exactly); released before landing, the game
               completes the drop (documented residual: a switch held
               PAST landing re-fires — that hold is what the user must
               release; this test keeps the supported window);
  6. return  — landed + idle: SELECT edge returns to old title $FF;
               a second title RESET starts the game again (repeatable).

Entry #13's "swallow-first SELECT flag $F2" is stale — swallow removed
2026-10-07 (bugs.md 8b); code wins: every edge does level+1.

Run: /home/iuri/python3/bin/python3 tools/test_menu_flow.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(4)]

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
intro_seen = False
intro_exited = False
title_bounced_to_intro = False


def step():
    mpu.step()


def next_frame(sw=REL):
    """Advance to the next frame boundary; arm SWCHB for that frame."""
    global frame, intro_seen, intro_exited, title_bounced_to_intro
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
            if d == 0xFD:
                intro_seen = True
            elif intro_seen and not intro_exited:
                intro_exited = True
            if intro_exited and d == 0xFD:
                title_bounced_to_intro = True
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


# ---- 1. boot -> intro -> first RESET edge -> old title ---------------
guard = 0
while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
    step()
    guard += 1
    if guard > 300000:
        sys.exit("never reached StartFrame")
frame = 0

run(2)                       # f1, f2 with released switches
check(mem.ram[DROPT] == 0xFD, f"boot should show intro $FD, got ${mem.ram[DROPT]:02X}")
next_frame(RST)              # f3: single-frame RESET pulse
run(4)
check(mem.ram[DROPT] == 0xFF,
      f"intro RESET edge -> old title $FF, got ${mem.ram[DROPT]:02X} at f{frame}")
check(intro_exited, "intro was never seen")

# ---- 2. title idle + SELECT edge-once-while-held ---------------------
run(8)
check(mem.ram[DROPT] == 0xFF, f"title must hold $FF while idle, got ${mem.ram[DROPT]:02X}")
lvl0 = mem.ram[LEVEL]
for _ in range(3):           # held 3 frames -> exactly one edge
    next_frame(SEL)
run(3)
check(mem.ram[LEVEL] == (lvl0 + 1) % LEVEL_COUNT,
      f"SELECT held 3f must inc Level once: {lvl0} -> {mem.ram[LEVEL]}, "
      f"want {(lvl0 + 1) % LEVEL_COUNT}")
check(mem.ram[DROPT] == 0xFF, f"SELECT must keep old title $FF, got ${mem.ram[DROPT]:02X}")

# ---- 3. full SELECT cycle: LEVEL_COUNT edges -> exact wrap ------------
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

# ---- 4. title RESET -> game (score zeroed, drop-in lands) -------------
run(4)
next_frame(RST)
run(2)
check(score() == 0, f"title RESET must zero the score, got {score()}")
check(mem.ram[DROPT] not in (0xFD, 0xFF),
      f"title RESET must leave title, DROPT=${mem.ram[DROPT]:02X}")
landed = None
for _ in range(400):
    next_frame(REL)
    if mem.ram[DROPT] == 0:
        landed = frame
        break
check(landed is not None, "drop-in never landed (DROPT stuck)")
run(6)
check(mem.ram[DROPT] == 0, f"gameplay must stay idle, DROPT=${mem.ram[DROPT]:02X}")

# ---- 5. bounce gate: SELECT mid-fall never returns to title ----------
# Restart the game from idle first (SELECT -> title), then start again and
# hold SELECT strictly during the fall window.
next_frame(SEL)
run(4)
check(mem.ram[DROPT] == 0xFF, f"idle SELECT -> title, got ${mem.ram[DROPT]:02X}")
next_frame(RST)
# wait for the fall to arm (DROPT = fall Y, a small nonzero non-sentinel)
for _ in range(60):
    next_frame(REL)
    if mem.ram[DROPT] not in (0xFD, 0xFF, 0xFE, 0):
        break
else:
    check(False, "fall never armed after second title RESET")
fall_seen = mem.ram[DROPT]
held = 0
while mem.ram[DROPT] not in (0, 0xFF) and held < 40:
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

# ---- 6. gameplay -> title -> game again (repeatable) -----------------
run(5)
next_frame(SEL)
run(4)
check(mem.ram[DROPT] == 0xFF, f"landed SELECT -> old title, got ${mem.ram[DROPT]:02X}")
next_frame(RST)
for _ in range(400):
    next_frame(REL)
    if mem.ram[DROPT] == 0:
        break
check(mem.ram[DROPT] == 0, f"second game start never landed, DROPT=${mem.ram[DROPT]:02X}")

# ---- global: intro never reappears -----------------------------------
check(not title_bounced_to_intro, "intro $FD reappeared after the first exit")

if fails:
    print(f"FAIL: {len(fails)} menu-flow violations:")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print(f"test_menu_flow: OK (intro->title->select x{LEVEL_COUNT} wrap->game->"
      f"bounce-gate->title->game, {frame} frames, intro shown once)")
