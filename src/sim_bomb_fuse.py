#!/home/iuri/python3/bin/python3
"""Headless bomb-fuse test: runs the real savior.bin banks in a py65 6502
simulator, forces Level=2, scripts a joystick Down press (bomb drop), and
asserts the whole bomb lifecycle + a stack-depth guard.

ASSERTIONS (exit 1 on any failure):
  1. drop       — fuse loaded ($B4=180) after landing
  2. fuse_zero  — BombTimer ($F7) counts 180 -> $00 (no stomp keeps it alive)
  3. explode    — BombPacked state (B5&3) reaches 2 (blast), then 0 (idle)
  4. min_sp     — stack guard, two thresholds:
                  * gameplay (frame >= 1): deepest SP >= $F8 (margin)
                  * whole run (incl. init): deepest SP >= $F7 — a push
                    writes AT the current SP then decrements, so SP $F7
                    means the lowest byte written was $F8 = the documented
                    stack-owned zone. SP $F6 = wrote $F7 = BombTimer/BombX
                    physically stomped by return bytes (the 2026-09-28 bug,
                    invisible to any byte-audit of instruction operands).

TIA/RIOT stubs: INTIM always reads 0 (all `lda INTIM` waits exit at once),
WSYNC/TIM64T writes ignored, SWCHA scripted, INPT4 = released ($40).
F6 banking: writes to $1FF6-$1FF9 select the 4K bank at $F000-$FFFF.

NOTE: PC labels in the diagnostic output come from bank0.lst — after moving
bank0 code, re-check addresses there (assertions do NOT depend on PCs).
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
BANKS = [open(SRC / f'bank{i}.bin', 'rb').read() for i in range(4)]

class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3                     # F6 power-up bank
        self.swcha = 0xFF                 # nothing pressed
        self.swchb = 0xFF
        self.inpt4 = 0x40                 # fire released
        self.pc_obj = None                # set to mpu for pc of executing instr
        self.mirror_stomps = []           # stack-page writes onto bomb ZP ($F6/$F7)
    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.banks_[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280: return self.swcha
        if a == 0x0282: return self.swchb
        if a == 0x0284: return 0          # INTIM: expired -> waits pass
        if a == 0x000C: return self.inpt4 # INPT4
        if 0x1FF6 <= a <= 0x1FF9: return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0
    def __setitem__(self, a, v):
        a &= 0xFFFF; v &= 0xFF
        if 0x1FF6 <= a <= 0x1FF9:
            self.bank = a - 0x1FF6        # F6 hotspot
            return
        if a >= 0xF000:
            return                        # no ROM writes expected
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            if 0x180 <= a <= 0x1FF and (a & 0x7F) in (0x76, 0x77):
                # stack push physically landed on BombX/BombTimer mirror
                self.mirror_stomps.append((a & 0x7F, self.pc_obj.pc))
            return
        if a in (0x0294, 0x0296, 0x0297): return  # WSYNC/TIM64T
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            self.tia[a & 0x3F] = v
        # RIOT writes ignored

mem = Mem()
mem.banks_ = BANKS

from py65.devices.mpu6502 import MPU
mpu = MPU(memory=mem)
mem.pc_obj = mpu

PC_STARTFRAME = 0xF039
PC_INIT_LOAD  = 0xF02E     # jsr LoadLevel in GameStart
IDX_F7, IDX_B5, IDX_F0, IDX_A3 = 0x77, 0x35, 0x70, 0x23

# ---- dynamic call chain + min-SP tracking ----
frame = -1
min_sp = 0xFF
min_sp_pc = None
min_sp_calls = []
min_sp_frame = None
min_sp_game = 0xFF                       # gameplay only (frame >= 0, post-init)
min_sp_gpc = min_sp_gframe = None
min_sp_gcalls = []
calls = []                  # dynamic jsr chain: [(pc, ret)]

def step():
    global prev_pc, min_sp, min_sp_pc, min_sp_calls, min_sp_frame, \
        min_sp_game, min_sp_gpc, min_sp_gframe, min_sp_gcalls
    prev_pc = mpu.pc
    op = mem[mpu.pc]
    mpu.step()
    if op == 0x20:                          # JSR: entered a subroutine
        calls.append(prev_pc)
    elif op in (0x60, 0x40):                # RTS / RTI: left one
        if calls: calls.pop()
    if mpu.sp < min_sp:
        min_sp, min_sp_pc, min_sp_frame = mpu.sp, prev_pc, frame
        min_sp_calls = list(calls)
    if frame >= 1 and mpu.sp < min_sp_game:   # f0 includes level load (jsr LoadLevel chain)
        min_sp_game = mpu.sp
        min_sp_gpc, min_sp_gframe = prev_pc, frame
        min_sp_gcalls = list(calls)

def chain_str(chain):
    return ' <- '.join(f'${c:04X}' for c in reversed(chain)) or '(none)'

# ---- reach init LoadLevel, force Level = 2 ----
guard = 0
while mpu.pc != PC_INIT_LOAD:
    step(); guard += 1
    if guard > 200000: sys.exit(f'never reached init LoadLevel (pc=${mpu.pc:04X})')
mem.ram[IDX_A3] = 1                      # Level = 1 (second level)
print(f'Level forced to 2 before jsr LoadLevel at ${PC_INIT_LOAD:04X}')

# ---- frame loop: press Down only AFTER the player has landed (OnGround b7) ----
f7_log, b5_log = [], []                  # (frame, writer_pc, old, new, tag)
prev_f7, prev_b5 = mem.ram[IDX_F7], mem.ram[IDX_B5]
frame = 0
landed_frame = None
press_done = False
drop_frame = None
states_seen = []                         # (frame, B5&3) sampled per frame
saw_fuse_zero = False
snapshots = []

while frame < 420:
    step()
    n_stomp = len(mem.mirror_stomps)
    if mem.ram[IDX_F7] != prev_f7:
        tag = 'STACK' if n_stomp else 'bomb'
        if tag == 'STACK':
            addr, ppc = mem.mirror_stomps[-1]
            print(f'*** STACK STOMP f{frame}: pc=${ppc:04X} writes ${addr:02X} '
                  f'{prev_f7:02X} -> {mem.ram[IDX_F7]:02X}  depth={0xFF - mpu.sp}B')
        f7_log.append((frame, prev_pc, prev_f7, mem.ram[IDX_F7], tag))
        prev_f7 = mem.ram[IDX_F7]
        if prev_f7 == 0x00 and drop_frame is not None:
            saw_fuse_zero = True
    mem.mirror_stomps.clear()
    if mem.ram[IDX_B5] != prev_b5:
        b5_log.append((frame, prev_pc, prev_b5, mem.ram[IDX_B5]))
        prev_b5 = mem.ram[IDX_B5]
    if mpu.pc == PC_STARTFRAME:
        frame += 1
        st = mem.ram[IDX_B5] & 3
        states_seen.append((frame, st))
        if drop_frame is None and mem.ram[IDX_F0] < 5:
            drop_frame = frame
            print(f'drop detected f{frame}: bombs={mem.ram[IDX_F0]} '
                  f'F7=${mem.ram[IDX_F7]:02X} B5=${mem.ram[IDX_B5]:02X}')
        # input: land-detect then hold Down 4 frames
        if landed_frame is None and (mem.ram[IDX_B5] & 0x80):
            landed_frame = frame
        if landed_frame and not press_done:
            mem.swcha = 0xDF               # Down pressed
            if frame >= landed_frame + 4:
                press_done = True
        else:
            mem.swcha = 0xFF
        if frame % 40 == 0 or (landed_frame and landed_frame <= frame <= landed_frame + 8):
            snapshots.append((frame, mem.ram[IDX_F7], mem.ram[IDX_B5], mem.ram[IDX_F0]))

# ---- report ----
print(f'\nlanded f{landed_frame}; drop f{drop_frame}; '
      f'min SP whole-run=${min_sp:02X} (f{min_sp_frame}, pc=${min_sp_pc:04X}), '
      f'min SP gameplay=${min_sp_game:02X}')
if min_sp < 0xF8 or min_sp_game < 0xF8:
    print(f'  deepest chain (whole): {chain_str(min_sp_calls)}')
    print(f'  deepest chain (gameplay): f{min_sp_gframe} pc=${min_sp_gpc:04X} '
          f'{chain_str(min_sp_gcalls)}')

print('\n== frame snapshots (frame, $F7, $B5, bombs) ==')
for fr, f7, b5, fb in snapshots:
    print(f'  f{fr:3d}: F7={f7:02X} B5={b5:02X} bombs={fb}')

def rle(events, name):
    print(f'\n== {name} writes (consecutive same-pc grouped) ==')
    if not events:
        print('  NONE'); return
    runs = []
    for fr, pc, old, new, *rest in events:
        tag = rest[0] if rest else ''
        if runs and runs[-1][1] == pc and runs[-1][5] == tag and runs[-1][3] + 1 == old and new == old + 1:
            runs[-1][3] = new; runs[-1][4] += 1
        elif runs and runs[-1][1] == pc and runs[-1][5] == tag and runs[-1][2] - 1 == old and new == old - 1:
            runs[-1][2] = new; runs[-1][4] += 1
        else:
            runs.append([fr, pc, old, new, 1, tag])
    for fr, pc, hi, lo, n, tag in runs[:12]:
        print(f'  f{fr:3d} pc=${pc:04X} [{tag:5s}] {hi:02X} -> {lo:02X}  ({n}x)')
    if len(runs) > 12:
        print(f'  ... {len(runs) - 12} more runs')

rle(f7_log, '$F7 BombTimer')
rle(b5_log, '$B5 BombPacked')
stack_hits = [e for e in f7_log if e[4] == 'STACK']
print(f'\nstack stomps on $F7: {len(stack_hits)}; bomb-code writes: {len(f7_log) - len(stack_hits)}')

states = [s for _, s in states_seen]
saw_drop = drop_frame is not None
saw_explode = 2 in states
saw_idle_after = saw_explode and states[states.index(2):].count(0) > 0

# ---- assertions ----
checks = [
    ('drop (bombs 5->4, fuse loaded)', saw_drop and drop_frame is not None),
    ('fuse counts 180 -> $00', saw_fuse_zero),
    ('explosion reached (B5 state=2)', saw_explode),
    ('returned to idle (state=0 after blast)', saw_idle_after),
    (f'min SP gameplay >= $F8 (actual ${min_sp_game:02X})', min_sp_game >= 0xF8),
    (f'min SP whole-run >= $F7 (actual ${min_sp:02X})', min_sp >= 0xF7),
]
print('\n== assertions ==')
ok = True
for name, cond in checks:
    print(f'  [{"PASS" if cond else "FAIL"}] {name}')
    ok = ok and cond
print(f'\n{"SIM OK" if ok else "SIM FAILED"}')
sys.exit(0 if ok else 1)
