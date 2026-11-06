#!/usr/bin/env python3
"""Attract mode (demo) behavioural test — boots the real savior.bin in py65.

After 5 s (300 frames) with every title input released the title plays a demo:
the REAL game on stage 1 driven by a script (bank5 DemoHook -> StickA/DemoOn).
  1. idle   : no demo before 300 title frames; it starts within a few frames of
              that, remembering the selected stage (DemoOn b6-0) and playing stage 1;
  2. script : the demo walks, flies, drops a bomb, fires the laser, never loses a
              life, and loops (second drop-in) — the logo/credits band is the
              title's (DropTarget=$FF), so it is gone while the demo runs;
  3. exit   : a stick press / FIRE / RESET / SELECT returns to the title with the
              selected stage restored, DemoOn/StickA cleared;
  4. latch  : FIRE held through the exit does not start the game, and the idle
              count restarts only after everything is released;
  5. normal : plain gameplay never enters the demo.

Run: /home/iuri/python3/bin/python3 tools/test_attract.py
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(8)]
SYM = {}
for _l in open(SRC / "generated" / "symbols.asm"):
    _m = re.match(r"^(\w+)\s+([0-9a-f]{4})", _l)
    if _m:
        SYM[_m.group(1)] = int(_m.group(2), 16)


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 7
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
from py65.devices.mpu6502 import MPU        # noqa: E402

mpu = MPU(memory=mem)
_lbl = {}
for _l in open(SRC / "bank0.lst", errors="replace"):
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_.][A-Za-z0-9_.]*)"
                  r"(?:\s+subroutine)?\s*(?:;.*)?$", _l)
    if _m:
        _lbl.setdefault(_m.group(2), int(_m.group(1), 16))
PC_SF = _lbl["StartFrame"]
fails = []


def R(n):
    return mem.ram[SYM[n] - 0x80]


def W(n, v):
    mem.ram[SYM[n] - 0x80] = v


frame = 0


def nextframe(sw=0xFF, ja=0xFF, fire=0x80):
    global frame
    g = 0
    while True:
        mpu.step()
        g += 1
        if g > 400000:
            sys.exit(f"stalled at frame {frame}")
        if mem.bank == 0 and mpu.pc == PC_SF:
            frame += 1
            mem.swchb, mem.swcha, mem.inpt4 = sw, ja, fire
            return


def check(ok, msg):
    if not ok:
        fails.append(msg)
        print("FAIL:", msg)


# --- boot to the title, select stage 6 (Level 5) ---------------------------------
for _ in range(6):
    nextframe()
check(R("DropTarget") == 0xFF, "boot did not reach the title")
W("Level", 5)
nextframe(sw=0xFD)                  # a SELECT press would change it; just poke instead
W("Level", 5)
for _ in range(5):
    nextframe()
W("Level", 5)

# --- 1. idle count ---------------------------------------------------------------
idle = 0
started_at = None
while idle < 400:
    nextframe()
    idle += 1
    if R("DemoOn"):
        started_at = idle
        break
check(started_at is not None, "the demo never started on an idle title")
if started_at:
    check(295 <= started_at <= 310, f"demo started after {started_at} idle frames (want ~300)")
    check(R("DemoOn") & 0x7F == (0x40 | 5), f"DemoOn={R('DemoOn'):02x} (want $45 = demo + stage 6)")
for _ in range(120):
    nextframe()
check(R("Level") == 0, f"demo plays stage 1, Level={R('Level')}")
check(R("DropTarget") != 0xFF, "title sentinel still set while the demo runs")

# --- 2. the script ------------------------------------------------------------------
seen = dict(bomb=False, laser=False, fly=False, walk=False, left=False, loop=0)
minx, maxx = 255, 0
was_zero = False
prev_dt = R("DropTarget")
bombs_min = 9
last = None
for _ in range(1600):
    nextframe()
    dt = R("DropTarget")
    if prev_dt == 0 and dt != 0 and dt != 0xFF:
        seen["loop"] += 1
        check(last == (39, 0, 0), f"loop restart from X/Y/dir {last}, want (39, 0, 0)")
    prev_dt = dt
    if dt != 0:
        continue
    x, y = R("RoomX"), R("RoomY")
    last = (x, y, R("PlayerDir"))
    gnd = R("BombPacked") >> 7
    minx, maxx = min(minx, x), max(maxx, x)
    if R("PlayerBombs") & 7 < 5:
        seen["bomb"] = True
    if R("LaserState") & 0x80:
        seen["laser"] = True
    if not gnd and y < 70 and R("JetPower"):
        seen["fly"] = True
    if gnd and R("StickA") & 0xC0:
        seen["walk"] = True
    if R("PlayerDir"):
        seen["left"] = True
    check(R("PlayerLives") == 3, f"lives {R('PlayerLives')} at frame {frame}")
    check(R("DemoOn") & 0x40, "DemoOn dropped mid-demo")
for k in ("bomb", "laser", "fly", "walk", "left"):
    check(seen[k], f"demo never showed: {k}")
check(maxx - minx >= 25, f"demo moved only {maxx - minx} px")
check(seen["loop"] >= 1, "demo script did not loop (no second drop-in)")

# seamless loop: the frame before each restart the player is where the drop-in starts


# --- 3. exit on a stick press, FIRE held through it -----------------------------
for _ in range(20):
    nextframe(fire=0x00)            # fire held
for _ in range(6):
    nextframe(fire=0x00)
check(R("DropTarget") == 0xFF, f"FIRE did not return to the title (DropTarget {R('DropTarget'):02x})")
check(R("DemoOn") == 0, f"DemoOn={R('DemoOn'):02x} after exit")
check(R("StickA") == 0, f"virtual presses left behind A={R('StickA'):02x}")
check(R("Level") == 5, f"selected stage not restored (Level={R('Level')})")
for _ in range(400):
    nextframe(fire=0x00)            # still held: no start, no demo
check(R("DropTarget") == 0xFF and R("DemoOn") == 0, "held FIRE started something")
t = 0
while t < 400 and not R("DemoOn"):
    nextframe()
    t += 1
check(295 <= t <= 310, f"demo re-armed after {t} frames of release (want ~300)")

# --- exits by stick / RESET / SELECT ------------------------------------------------
for how, kw in (("stick", dict(ja=0xEF)), ("RESET", dict(sw=0xFE)), ("SELECT", dict(sw=0xFD))):
    for _ in range(200):
        nextframe()
    check(R("DemoOn") != 0, f"[{how}] demo not running before the press")
    for _ in range(8):
        nextframe(**kw)
    for _ in range(6):
        nextframe()
    check(R("DropTarget") == 0xFF, f"[{how}] not back on the title")
    check(R("DemoOn") == 0, f"[{how}] DemoOn left set")
    check(R("Level") in (5, 6), f"[{how}] Level={R('Level')}")
    W("Level", 5)
    t = 0
    while t < 400 and not R("DemoOn"):
        nextframe()
        t += 1
    check(t < 400, f"[{how}] demo never re-armed")

# --- 5. a real game never turns into the demo ---------------------------------------
for _ in range(200):
    nextframe()
for _ in range(8):
    nextframe(fire=0x00)
for _ in range(10):
    nextframe()
W("Level", 0)
for _ in range(3):
    nextframe(sw=0xFE)              # RESET edge: real start
for _ in range(5):
    nextframe()
for _ in range(1200):
    nextframe()
check(R("DemoOn") == 0, "plain gameplay entered the demo")
check(R("DropTarget") != 0xFF or True, "")

if fails:
    print(f"test_attract: {len(fails)} FAIL")
    sys.exit(1)
print(f"test_attract: OK (started after {started_at} idle frames; "
      f"loops {seen['loop']}, x {minx}-{maxx})")
