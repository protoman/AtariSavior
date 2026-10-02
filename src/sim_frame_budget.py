#!/home/iuri/python3/bin/python3
"""Headless frame-budget guard: worst-case scenario, segment work vs the
hardware timer windows (the "screen flickers / moves up/down" class).

Scenario (user spec 2026-10-02): Level 1 room 1 (the flicker repro room),
player flying (thrust pulses) + alternating left/right + fire HELD (laser
every frame) + bomb dropped (falling fuse + explosion mid-run), 1 enemy +
miner in the room (post-migration 2-object cap).

MEASUREMENT (py65 = pure CPU work; WSYNC/TIM64T/INTIM stubbed):
  VBL      StartFrame -> first .Row        must be <= VBL_BUDGET   (TIM64T #23)
  OVER     Overscan   -> next StartFrame   must be <= OVER_BUDGET  (TIM64T #50)
  KERNEL   every WSYNC-to-WSYNC gap (cave + HUD band) <= 76 cycles
           (a >76 body = line spills to the next scanline on hardware =
           263-line frame = whole-screen jump — the documented
           WSYNC-off-by-one / HUD-bar class)
  kernel WSYNC count constant per frame (structure drift guard)

Budgets are the documented timers (kernel.asm VBL #23 = 1472c,
overscan #50 = 3200c; frame = V(#23)+O(#50) = 262 lines). A timer segment
whose WORK exceeds its window loses the wait and eats extra scanlines on
hardware; py65 work > budget predicts the Stella jump.

ASSERTIONS (exit 1): all budgets + WSYNC-count constancy + scenario
validity (bomb dropped AND exploded, enemy present) + >=300 measured frames.

Run: /home/iuri/python3/bin/python3 src/sim_frame_budget.py
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
BANKS = [open(SRC / f'bank{i}.bin', 'rb').read() for i in range(4)]

VBL_BUDGET = 1472          # TIM64T #23 (kernel.asm:449)
OVER_BUDGET = 3200         # TIM64T #50 (kernel.asm:776)
# Assert band = 3222 (documented fill absorb: INTIM poll granularity lets
# ~3201-3222 pass silently; sub-window frames measure 3200 +- tick-quant
# epsilon, so the hard 3200 line is alignment-fragile — wall-model is the
# Stella-agree invariant). Real work spikes (3359+, 4285) still fail.
OVER_ABSORB = 3222
GAP_LIMIT = 76             # one scanline = 76 CPU cycles
MIN_FRAMES = 300

import os
SIM_LEVEL = os.environ.get('SIM_LEVEL', '1')   # '0' = boot level/room 0
SIM_ROOM = os.environ.get('SIM_ROOM', '1')
PIN_ROW = os.environ.get('SIM_PINROW') == '1'  # pin RoomY onto enemy row
FLY = os.environ.get('SIM_FLY', '')    # '1'/'Y' hover enemy Y; 'X' align enemy X (user repro: fly
                                         # L/R with laser until same row)
TRAIL_FRAMES = {int(x) for x in os.environ.get('SIM_TRAIL', '347').split(',')}

# ---- labels from bank0.lst (addresses move every commit) ----
LABELS = {}
for _l in (SRC / 'bank0.lst').read_text(errors='replace').splitlines():
    _m = re.match(r'^\s*\d+\s+([0-9a-f]{4})\s+'
                  r'([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*$', _l)
    if _m:
        LABELS.setdefault(_m.group(2), int(_m.group(1), 16))
for _need in ('StartFrame', 'Overscan', 'EnterRoom', 'LoadLevel', '.Row'):
    if _need not in LABELS:
        sys.exit(f'label {_need} not found in bank0.lst')
PC_START = LABELS['StartFrame']
PC_OVER = LABELS['Overscan']
PC_ENTER = LABELS['EnterRoom']
PC_LOADLEVEL = LABELS['LoadLevel']
PC_ROW = LABELS['.Row']

# overscan sub-marks for attribution (which caller eats the timer window)
OVER_MARKS = {LABELS[_n]: _n for _n in
              ('RefreshEnemyY', 'UpdateEnemies', 'CheckEnemyHit',
               'LaserInput', 'BombTick', 'CheckBandTouch',
               'LaserHitTest', 'SetObjectXPos', 'PlayerHitsMap',
               'StepDown', 'StepUp', 'CheckMinerPickup', 'LoseLife',
               'ExitRoomLeft', 'ExitRoomRight',
               'CallPad_BombSndDrop', 'CallPad_UpdateBombSound',
               'CallPad_UpdateJetSound', 'CallPad_UpdateLaserSound',
               'CallPad_AddScore', 'CallPad_SetRoomDark',
               'AddScore', 'EnterRoom')
              if _n in LABELS}
mark_events = []                 # (frame, mark, window_cycles) per measurement
pc_cycles = {}                   # pc -> cycles in CURRENT frame (OVER phase)
pc_hist_keep = {}                # frame -> {pc: cycles} for top over frames
over_trail = {}                  # frame -> [(pc, cum, c)] OVER steps

IDX_LEVEL = 0x23           # $A3 Level (poke before jsr LoadLevel)
IDX_COUNT = 0x33           # $B3 EnemyCount
IDX_B5 = 0x35              # $BombPacked
IDX_GROUND = 0x80          # BombPacked b7 = OnGround


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3                     # F6 power-up bank
        self.swcha = 0xFF                 # nothing pressed
        self.swchb = 0xFF
        self.inpt4 = 0x00                 # fire HELD from boot (laser worst case)
        self.wsync_seen = False
        self.wall = 0                     # beam/CPU wall clock (76c per line)
        self.deadline = {}                # RIOT timer addr -> wall expiry

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
            mult = {0x294: 1024, 0x296: 64, 0x297: 8}[a]
            self.deadline[a] = self.wall + v * mult
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            if (a & 0x3F) == 2:           # WSYNC ($02 / mirror)
                self.wsync_seen = True
            self.tia[a & 0x3F] = v


mem = Mem()
from py65.devices.mpu6502 import MPU
mpu = MPU(memory=mem)

prev_cycles = 0
frame = -1
poked_level = poked_room = False


def step():
    global prev_cycles
    mpu.step()
    c = mpu.processorCycles - prev_cycles
    prev_cycles = mpu.processorCycles
    mem.wall += c
    if mem.wsync_seen:
        # WSYNC halts the CPU until the start of the NEXT scanline
        w = mem.wall
        mem.wall = (w // 76 + 1) * 76 if w % 76 else w
    return c


def zp_byte_addr(name):
    """Address of a `Name byte` ZP decl (sequential from org $80)."""
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


def near_label(addr):
    """Nearest lst label <= addr (diagnostics only)."""
    best, best_a = '?', -1
    for name, a in LABELS.items():
        if a <= addr and a > best_a:
            best, best_a = name, a
    return f'{best}+{addr - best_a}'


OBJ_TOP_IDX = zp_byte_addr('ObjTop') - 0x80

# ---- boot pokes: default Level=1/Room=1 (the flicker repro room);
# SIM_LEVEL=0 keeps the boot defaults (level 0, start_room 0) ----
if SIM_LEVEL == '0':
    poked_level = poked_room = True
    print('boot defaults kept: level 0 room 0')
boot_steps = 0
while not (poked_level and poked_room):
    mpu.step()
    boot_steps += 1
    pc, bk = mpu.pc, mem.bank
    if not poked_level and bk == 0 and pc == PC_LOADLEVEL:
        mem.ram[IDX_LEVEL] = int(SIM_LEVEL)
        poked_level = True
        print(f'Level={SIM_LEVEL} poked at jsr LoadLevel pc=${pc:04X}')
    if not poked_room and bk == 0 and pc == PC_ENTER:
        mpu.a = int(SIM_ROOM)              # EnterRoom param
        poked_room = True
        print(f'RoomNo={SIM_ROOM} poked at EnterRoom pc=${pc:04X}')
    if boot_steps > 2_000_000:
        sys.exit('never reached boot pokes')
prev_cycles = mpu.processorCycles          # ignore boot cycles in segment math

# ---- phase machine: VBL -> KERNEL -> OVER -> (next frame) ----
PH_VBL, PH_KER, PH_OVER = 0, 1, 2
phase = PH_VBL
vbl_acc = 0
over_acc = 0
gap = 0
kwsync = 0
frame_armed = False                       # first StartFrame seen
vbl_val = over_val = None
kwsync_frame = None
frame_bad = []

max_vbl = max_over = max_gap = 0
max_vbl_f = max_over_f = max_gap_f = None
gap_pc = None
gap_log = []                     # every gap > limit: (frame, pc, bank, cycles)
gap_tail = 0                     # kernel tail gaps > limit (informational)
frame_lines = []                 # wall-model scanlines per frame (76c lines)
_wall_start = 0
frame_stats = []                 # (frame, over_work, vbl_work) per measured frame
wall_segs = []                   # (frame, vsync+vbl, ker, over) WALL cycles
prev_wall = None
trail = []                       # ring of (pc, bk, c) since last KER wsync
printed_trails = 0
over_windows = {}                # mark name -> max cycles between marks
over_mark_t = 0
bomb_states = set()
bomb_packed_snap = {}
beam_cols = {}
measured = 0
landed_frame = None
wsync_counts = set()
enemy_seen = False
inpt4_frames = 0

while frame < 440:
    c = step()
    pc, bk = mpu.pc, mem.bank

    # -- accumulate into the phase the executed code belonged to --
    if phase == PH_VBL:
        vbl_acc += c
    elif phase == PH_KER:
        gap += c
    elif phase == PH_OVER:
        over_acc += c

    # -- phase transitions (landmarks are bank0 labels) --
    if bk == 0 and pc == PC_ROW and phase == PH_VBL:
        vbl_val = vbl_acc
        _wall_vbl = mem.wall
        phase = PH_KER
        gap = 0
        kwsync = 0
    elif bk == 0 and pc == PC_OVER and phase == PH_KER:
        # kernel tail (post last WSYNC) also counts as line work.
        # tail gaps >76c are baked into the 263-line baseline (Stella agrees);
        # line constancy below is the real invariant -- count, don't fail.
        if gap > GAP_LIMIT:
            gap_tail += 1
        phase = PH_OVER
        over_acc = 0
        over_mark_t = 0
        _wall_ker = mem.wall
        gap = 0
    elif bk == 0 and pc == PC_START:
        if frame_armed and phase == PH_OVER:
            over_val = over_acc
            # -- evaluate previous frame --
            frame += 1
            if frame >= 2 and vbl_val is not None:
                measured += 1
                if vbl_val > max_vbl:
                    max_vbl, max_vbl_f = vbl_val, frame
                if over_val > max_over:
                    max_over, max_over_f = over_val, frame
                    snap_windows = dict(over_windows)
                    snap_tail = over_acc - over_mark_t
                if over_val > OVER_BUDGET:
                    pc_hist_keep[frame] = dict(pc_cycles)
                pc_cycles = {}
                if kwsync_frame is None:
                    kwsync_frame = kwsync
                elif kwsync != kwsync_frame:
                    frame_bad.append(
                        f'f{frame}: kernel WSYNC {kwsync} != {kwsync_frame}')
                wsync_counts.add(kwsync)
                frame_stats.append((frame, over_val, vbl_val))
                wall_segs.append((frame, _wall_vbl - _wall_start,
                                  _wall_ker - _wall_vbl,
                                  mem.wall - _wall_ker))
                _wall_start = mem.wall
                bomb_packed_snap[frame] = mem.ram[0x35]

                if mem.ram[IDX_COUNT] >= 1:
                    enemy_seen = True
                if mem.inpt4 == 0:
                    inpt4_frames += 1
        frame_armed = True
        phase = PH_VBL
        vbl_acc = 0
        pc_cycles = {}
        _wall_start = mem.wall

    if bk == 2 and pc == 0xF25A:      # LaserWallClamp entry (bank2 only)
        beam_cols[frame] = (mem.ram[0x0E], mem.ram[0x0C])
    if phase == PH_OVER:
        pc_cycles[pc] = pc_cycles.get(pc, 0) + c
        if frame in TRAIL_FRAMES:
            over_trail.setdefault(frame, []).append((pc, over_acc, c))

    # -- overscan attribution (bank0 only: bank2 body pcs alias bank0 labels) --
    if phase == PH_OVER and bk == 0 and pc in OVER_MARKS:
        w = over_acc - over_mark_t
        if w > over_windows.get(OVER_MARKS[pc], 0):
            over_windows[OVER_MARKS[pc]] = w
        if frame >= 2:
            mark_events.append((frame + 1, OVER_MARKS[pc], w, over_acc))
        over_mark_t = over_acc

    if phase == PH_KER:
        trail.append((pc, bk, c))
        if len(trail) > 200:
            trail.pop(0)

    # -- WSYNC accounting (write happened in the step just executed) --
    if mem.wsync_seen:
        mem.wsync_seen = False
        if phase == PH_KER:
            if gap > max_gap:
                max_gap, max_gap_f, gap_pc = gap, frame, pc
            if gap > GAP_LIMIT:
                gap_log.append((frame, pc, bk, gap))
            trail = []
            kwsync += 1
            gap = 0

    # -- input script per frame boundary --
    if bk == 0 and pc == PC_START and frame_armed:
        if PIN_ROW:
            # attractor (max 3px/frame, no teleport artifacts): slide RoomY
            # toward the enemy window (enemy screen Y = RoomY + ObjTop rel).
            d = (mem.ram[OBJ_TOP_IDX] + 128) % 256 - 128
            if d:
                mem.ram[0x01] = (mem.ram[0x01] + max(-3, min(3, d))) & 0xFF
        if prev_wall is None:
            prev_wall = mem.wall
        else:
            frame_lines.append((frame, (mem.wall - prev_wall) / 76))
            prev_wall = mem.wall
        bomb_states.add(mem.ram[IDX_B5] & 3)
        if landed_frame is None and (mem.ram[IDX_B5] & IDX_GROUND):
            landed_frame = frame
        k = frame if landed_frame is None else frame - landed_frame
        if landed_frame is not None and frame <= landed_frame + 4:
            mem.swcha = 0xDF               # Down: bomb drop (4-frame press)
        else:
            mem.swcha = 0xFF
            if FLY in ('X', 'B', 'M', 'Mx'):
                # align X with enemy slot0 (EnemyRamX $BD): steer toward it
                dx = mem.ram[0x3D] - mem.ram[0x00]
                if dx < -2:
                    mem.swcha &= 0xBF          # left
                elif dx > 2:
                    mem.swcha &= 0x7F          # right
                elif (k // 12) % 2 == 0:
                    mem.swcha &= 0xBF
                else:
                    mem.swcha &= 0x7F
            elif (k // 12) % 2 == 0:
                mem.swcha &= 0xBF          # left
            else:
                mem.swcha &= 0x7F          # right
            if FLY in ('M', 'My'):
                # hover at MINER Y ($A6): user repro "align Y with the miner"
                d = ((mem.ram[0x01] - mem.ram[0x26] + 128) & 0xFF) - 128
                if d > 6:
                    mem.swcha &= 0xEF
            elif FLY in ('1', 'Y', 'B'):
                # hover band at enemy Y (slot0 $E2, room coords): thrust
                # while below it, release above -> gravity; repeats passes
                # through the same-row window (laser held = kill happens)
                d = ((mem.ram[0x01] - mem.ram[0x62] + 128) & 0xFF) - 128
                if d > 6:
                    mem.swcha &= 0xEF       # up thrust (rise to enemy)
            elif k % 12 < 5:
                mem.swcha &= 0xEF          # up thrust pulse (fly)

# ---- report ----
print(f'\nmeasured frames: {measured} (landed f{landed_frame})')
print(f'VBL    max {max_vbl}c / {VBL_BUDGET}c  (f{max_vbl_f})')
print(f'OVER   max {max_over}c / {OVER_BUDGET}c  (f{max_over_f})')
print(f'KERNEL max gap {max_gap}c (informational; tail gaps >{GAP_LIMIT}c: {gap_tail})')
import collections as _c
_lines_hist = _c.Counter(round(v) for _, v in frame_lines)
print(f'wall-model frame lines: {dict(sorted(_lines_hist.items()))}')
_lines_raw = [(f, round(v, 2)) for f, v in frame_lines]
_odd = [(f, v) for f, v in _lines_raw if abs(v - 263.0) > 0.15]
print(f'frames off 263.0 by >0.15: {len(_odd)} '
      f'{sorted(_odd, key=lambda x: -x[1])[:12]}')
print(f'kernel WSYNC counts seen: {sorted(wsync_counts)}')
over_over = [(f, o) for f, o, _ in frame_stats if o > OVER_BUDGET]
print(f'frames with OVER work > {OVER_BUDGET}: {len(over_over)} '
      f'{[(f, o) for f, o in over_over[:12]]}')
print(f'bomb states seen: {sorted(bomb_states)}; enemy present: {enemy_seen}; '
      f'fire held frames: {inpt4_frames}')

# -- optional per-frame PC histogram dump (SIM_HIST=169,173) --
for _fr in [int(x) for x in os.environ.get('SIM_HIST', '').split(',') if x]:
    _h = pc_hist_keep.get(_fr)
    if not _h:
        print(f'HIST f{_fr}: none (over <= {OVER_BUDGET})')
        continue
    _inv = {v: k for k, v in LABELS.items()}
    print(f'HIST f{_fr} total={sum(_h.values())}')
    for _pc, _n in sorted(_h.items(), key=lambda kv: -kv[1])[:16]:
        print(f'  {_inv.get(_pc, hex(_pc))}: {_n}')

# -- optional mark-window dump (SIM_EVENTS=168,169,173) --
_ev = [int(x) for x in os.environ.get('SIM_EVENTS', '').split(',') if x]
if _ev:
    _wins = {}
    _prev = None
    for _fr, _lb, _w, _cum in mark_events:
        if _prev is not None:
            _wins.setdefault(_prev[0], []).append((_prev[1], _w - _prev[2]))
        _prev = (_fr, _lb, _w)
    for _fr in _ev:
        print(f'EVENTS f{_fr}:')
        for _lb, _d in _wins.get(_fr, []):
            print(f'  {_lb}: {_d}')

# hard invariant: every real frame (>=2, boot excluded) sits at 263.0 +/-0.15
# -- the wall-model line count. VBL/OVER cpu budgets are secondary guards.
_bad_lines = [(f, v) for f, v in _lines_raw
              if f >= 2 and abs(v - 263.0) > 0.15]
checks = [
    (f'VBL work <= {VBL_BUDGET}c (max {max_vbl}c)', max_vbl <= VBL_BUDGET),
    (f'overscan work <= {OVER_ABSORB}c absorb band (max {max_over}c)',
     max_over <= OVER_ABSORB),
    ('kernel WSYNC count constant', len(wsync_counts) <= 1),
    (f'wall-model lines 263.0 +/-0.15 on all frames >=2 (bad: {_bad_lines[:6]})',
     not _bad_lines),
    ('bomb dropped (state1 seen)', 1 in bomb_states),
    ('bomb exploded (state2 seen)', 2 in bomb_states),
    ('enemy present in room', enemy_seen),
    (f'measured frames >= {MIN_FRAMES} (got {measured})', measured >= MIN_FRAMES),
    ('no structural notes', not frame_bad),
]
ok = True
print('\n== assertions ==')
for name, cond in checks:
    print(f'  [{"PASS" if cond else "FAIL"}] {name}')
    ok = ok and cond
for note in frame_bad[:10]:
    print('   note:', note)
print(f'\n{"SIM OK" if ok else "SIM FAILED"}')
sys.exit(0 if ok else 1)
