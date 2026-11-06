#!/usr/bin/env python3
"""Room changes are DEFERRED to a blank transition frame (2026-11).

EnterRoom costs 1000-2000c; run inside the overscan of the frame that crossed
the edge it overran the timer and the frame grew by up to 11 scanlines (the
"glitch on every playfield transition" report). Now bank2's exit handler only
sets LevelConnSpare = room | $80, the frame skips the rest of its overscan, and
bank5 TransBody emits ONE blank frame that runs EnterRoom with a whole frame to
itself. This boots the real ROM on level 6 (the no-input fall through the
room 1 -> room 2 link of test_arrival_fall) and asserts:
  1. the exit frame leaves the pending flag set and RoomNo still the old room,
  2. exactly one blank frame (TransBody entered) follows, it consumes the flag
     and RoomNo is the target afterwards,
  3. (the blank frame's length is gated by sim_frame_budget's wall model, not
     here: this harness never clears its WSYNC latch),
  4. the stack is balanced (SP identical at every Overscan entry).
Same live-data exception as test_arrival_fall (skips when level 6 changes).

Run: /home/iuri/python3/bin/python3 src/tools/test_room_transition.py
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]   # src/
BANKS = [open(SRC / f'bank{i}.bin', 'rb').read() for i in range(8)]
LEVEL = 5                      # 0-based: level 6 (1-based) — the report
FRAMES = 420
HANG_LIMIT = 40                # frames on one RoomY with no ground contact

LABELS = {}
for _l in (SRC / 'bank0.lst').read_text(errors='replace').splitlines():
    _m = re.match(r'^\s*\d+\s+([0-9a-f]{4})\s+'
                  r'([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$', _l)
    if _m:
        LABELS.setdefault(_m.group(2), int(_m.group(1), 16))
for _need in ('LoadLevel', 'Overscan', 'StepDown', 'CallPad_Transition', 'StartFrame'):
    if _need not in LABELS:
        sys.exit(f'label {_need} not found in bank0.lst')
PC_LOADLEVEL = LABELS['LoadLevel']
PC_SAMPLE = LABELS['Overscan']


def zp(name):
    addr = None
    for line in (SRC / 'kernel.asm').read_text(errors='replace').splitlines():
        if re.match(r'\s*org\s+\$80\b', line):
            addr = 0x80
            continue
        if addr is None:
            continue
        if re.match(rf'^{re.escape(name)}\s+byte\b', line):
            return addr
        if re.match(r'^[A-Za-z_][A-Za-z_0-9]*\s+byte\b', line):
            addr += 1
    sys.exit(f'ZP decl {name} not found')


Z_Y, Z_X = zp('RoomY'), zp('RoomX')
Z_ROOM, Z_LIVES = zp('RoomNo'), zp('PlayerLives')
Z_BOMB = zp('BombPacked')
ON_GROUND = 0x80


class Mem:
    """py65 memory: 8 bank images + ZP/stack mirror + the TIA bits the game
    polls (SWCHA/SWCHB/INPT4, WSYNC and the RIOT timers)."""

    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 7                 # F4 power-up bank
        self.swcha = 0xFF             # nothing pressed, ever
        self.swchb = 0xFF
        self.inpt4 = 0x00
        self.wsync_seen = False
        self.wall = 0
        self.deadline = {}

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
        if 0x1FF4 <= a <= 0x1FF7 or a == 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF4 <= a <= 0x1FF7 or a == 0x1FF9:
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
            if (a & 0x3F) == 2:
                self.wsync_seen = True
            self.tia[a & 0x3F] = v


mem = Mem()
from py65.devices.mpu6502 import MPU        # noqa: E402

mpu = MPU(memory=mem)
prev = 0


def step():
    global prev
    mpu.step()
    c = mpu.processorCycles - prev
    prev = mpu.processorCycles
    mem.wall += c
    if mem.wsync_seen:
        w = mem.wall
        mem.wall = (w // 76 + 1) * 76 if w % 76 else w
    return c


# --- the guard only makes sense while level 6 still stacks rooms 0 and 1 ------
import json                       # noqa: E402
_stage = json.loads((SRC / 'rooms' / 'stage.json').read_text())['stage']
_lv = _stage['levels'][LEVEL]
_pos = {(int(r['room_x']), int(r['room_y'])) for r in _lv['rooms']}
if not {(0, 0), (0, 1)} <= _pos:
    print('test_arrival_fall: SKIP (level 6 no longer stacks rooms 1 and 2)')
    sys.exit(0)

# --- boot to the level load, then poke Level 6 -------------------------------
poked = False
boot = 0
while not poked:
    step()
    boot += 1
    if mem.bank == 0 and mpu.pc == PC_LOADLEVEL:
        mem.ram[zp('Level') - 0x80] = LEVEL
        poked = True
    if boot > 3_000_000:
        sys.exit('never reached LoadLevel')



# bank5 TransBody entry (the blank frame) from the listing
PC_TBGO = None
for _l in (SRC / 'bank5.lst').read_text(errors='replace').splitlines():
    _m = re.match(r'^\s*\d+\s+([0-9a-f]{4})\s+\.TBgo\s*$', _l)
    if _m:
        PC_TBGO = int(_m.group(1), 16)
if PC_TBGO is None:
    sys.exit('.TBgo not found in bank5.lst')
Z_LCS = zp('LevelConnSpare')
PC_PAD = LABELS['CallPad_Transition']

frame = 0
pending_seen = []          # (frame, room before, flag)
blank_enter = []           # (frame, wall)
blank_done = []            # (frame, room after, flag, lines)
sps = set()
cur_blank = None
SF = LABELS['StartFrame']
while frame < FRAMES:
    step()
    if mem.bank == 5 and mpu.pc == PC_TBGO:
        cur_blank = mem.wall
        blank_enter.append(frame)
    if mem.bank == 0 and mpu.pc == SF and cur_blank is not None:
        r = mem.ram
        blank_done.append((frame, r[Z_ROOM - 0x80], r[Z_LCS - 0x80],
                           (mem.wall - cur_blank) / 76))
        cur_blank = None
    if mem.bank == 0 and mpu.pc == PC_PAD and mem.ram[Z_LCS - 0x80] & 0x80:
        pending_seen.append((frame, mem.ram[Z_ROOM - 0x80], mem.ram[Z_LCS - 0x80]))
    if not (mem.bank == 0 and mpu.pc == PC_SAMPLE):
        continue
    frame += 1
    mem.swchb = 0xFE if frame in (1, 4) else 0xFF
    r = mem.ram
    sps.add(mpu.sp)
    if frame == 8:
        r[Z_X - 0x80] = 32

fails = []
if not pending_seen:
    fails.append('no exit ever set the pending flag (LevelConnSpare b7)')
if len(blank_enter) != len(blank_done) or not blank_enter:
    fails.append(f'blank frames entered {len(blank_enter)} / finished {len(blank_done)}')
for (pf, proom, pflag), (bf, aroom, aflag, lines) in zip(pending_seen[:1], blank_done[:1]):
    if (pflag & 0x7F) != aroom:
        fails.append(f'target room ${pflag & 0x7F:02X} but RoomNo=${aroom:02X} after the blank frame')
    if aroom == proom:
        fails.append('the room never changed')
    if aflag & 0x80:
        fails.append('the blank frame did not consume the pending flag')
if len(pending_seen) > len(blank_enter) * 6:
    fails.append(f'pending seen on {len(pending_seen)} overscans for {len(blank_enter)} blank frames')
if len(sps) != 1:
    fails.append(f'stack not balanced: SP at Overscan entry took {sorted(hex(x) for x in sps)}')
if fails:
    print('FAIL: ' + '; '.join(fails))
    sys.exit(1)
print(f'test_room_transition: OK ({len(blank_enter)} blank frame(s), '
      f'room ${pending_seen[0][1]:02X} -> ${blank_done[0][1]:02X}, SP ${list(sps)[0]:02X} constant)')
