#!/usr/bin/env python3
"""No-input fall through a vertical link must NOT kill or stall the player.

User report 2026-10-24 (level 6, room 1 -> room 2, hands off the controller):
"when I appear on next screen, it stops falling, I have to keep moving him
until I start falling again".

Reproduced with this harness: the frame the room loaded, the player at
RoomY 0 / RoomX 32 overlapped an enemy staged at (31, 0) — the generator put it
on the band-0 APERTURE, i.e. exactly the columns a vertical link drops him on
with no input yet. CheckEnemyHit took a life on arrival (lives 3 -> 2), then the
respawn hover ($FF, cleared only by an UP press) plus a phantom float pinned him
at the top: the reported "stuck".

The generator now keeps band-0 enemies off the aperture (moved a band down, or
dropped when the room has no safe cell). This test boots the ROM, pokes
Level 6 at LoadLevel, presses NOTHING and asserts:
  1. a life is never lost,
  2. he actually enters room 1 (the link fires),
  3. he never hangs un-grounded: no 40-frame run of the same RoomY while off
     the ground (that is the stuck signature).

LIVE data (sanctioned exception, same family as test_band_restage): this is a
GENERATOR-OUTPUT guard, so it reads the live ROM + stage.json. If level 6 no
longer stacks rooms 0/1 it SKIPS instead of failing — that is an authoring
change, not a regression.

Run: /home/iuri/python3/bin/python3 src/tools/test_arrival_fall.py
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
for _need in ('LoadLevel', 'Overscan', 'StepDown'):
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
        if 0x1FF4 <= a <= 0x1FF7:
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


# --- run: RESET first (the sim's recipe), then NOTHING -----------------------
frame = 0
prev_room = 0
hang = 0
last_y = None
lost_life_at = None
entered_room_one_at = None
while frame < FRAMES:
    step()
    if not (mem.bank == 0 and mpu.pc == PC_SAMPLE):
        continue
    frame += 1
    mem.swchb = 0xFE if frame in (1, 4) else 0xFF     # RESET pulse
    r = mem.ram
    if frame == 8:
        # The level start is RoomX 39 (cell 4) since 2026-10-28; this guard needs the
        # fall through the cell-3 aperture of level 6 room 1 (the column it was
        # written for, RoomX 32): put him back there, still falling, no input.
        r[Z_X - 0x80] = 32
    room, y = r[Z_ROOM - 0x80], r[Z_Y - 0x80]
    lives = r[Z_LIVES - 0x80]
    ground = bool(r[Z_BOMB - 0x80] & ON_GROUND)
    if lives < 3 and lost_life_at is None:
        lost_life_at = (frame, room, y)
    if room == 1 and entered_room_one_at is None:
        entered_room_one_at = frame
    if ground or y != last_y:
        hang = 0
    else:
        hang += 1
    if hang == HANG_LIMIT:
        print(f'FAIL: hanging at RoomY={y} in room {room} for {HANG_LIMIT} '
              f'frames without ground contact (frame {frame}, X={r[Z_X-0x80]}, '
              f'lives {lives}) — the "stops falling" report')
        sys.exit(1)
    last_y = y

fails = 0
if lost_life_at:
    print(f'FAIL: lost a life at frame {lost_life_at[0]} in room '
          f'{lost_life_at[1]} (Y={lost_life_at[2]}) while pressing NOTHING — '
          'an object sits on the arrival point')
    fails += 1
if entered_room_one_at is None:
    print('FAIL: the vertical link never fired (level 6 room 1 -> room 2)')
    fails += 1
if fails:
    sys.exit(1)
print(f'test_arrival_fall: OK (level 6, no input: room 1 entered at frame '
      f'{entered_room_one_at}, no life lost, no hang)')
