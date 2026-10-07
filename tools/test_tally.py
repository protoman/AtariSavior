#!/usr/bin/env python3
"""Level-bonus tally behavioral test (user spec 2026-10-02).

Boots the real savior.bin in py65, lands the player, then stages a miner
pickup and asserts the whole count-up flow:
  arm    — TallyArm snapshots the bonus into TallyTicks ($F2):
           20 (miner) + (BarLevel+3)/6 (time, 50% -> 500) + bombs
           + 2*lives; DropTarget ($8A) = $FE.
  freeze — while tallying: joystick RIGHT held, RoomX/RoomY never move,
           BarLevel stays frozen (timer block skipped), TallyTicks decs.
  coin   — AUDV0 goes >0 during the run (coin blip via BombSnd hold).
  score  — exact total at completion = ticks*50
           (BarLevel=60, bombs=2, lives=3 -> 38 ticks -> 1900 =
            miner 1000 + time 500 + bombs 100 + lives 300).
  done   — DropTarget back to 0, Level advanced, BarLevel=120,
           TickCounter=60; a few post-tally frames run clean.
  min_sp — two guards: whole run >= $F7 (covers the done path's
           jsr LoadLevel transition chain = boot class; the old pickup
           tail was 2 bytes deeper), gameplay outside LoadLevel >= $F8
           (includes all live tally frames — the bomb sim never enters
           tally, so this is the only coverage for that path).

Run: /home/iuri/python3/bin/python3 tools/test_tally.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(4)]

# ZP indexes (addr & $7F)
ROOMX, ROOMY = 0x00, 0x01
DROPT = 0x0A
ROOMNO = 0x18
LEVEL = 0x23
MINERROOM = 0x24
MINERX, MINERY = 0x25, 0x26
LIVES = 0x2C
TICKC = 0x2D
BAR = 0x2E
BOMBS = 0x70
BOMBSND = 0x71
TALLY = 0x72
SC_TH, SC_HU, SC_TE = 0x73, 0x74, 0x75
AUDV0 = 0x19              # TIA reg index


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3                     # F6 power-up bank
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x40
        self.pc_obj = None

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
mem.pc_obj = mpu

_LBL = {}
for _l in open(SRC / "bank0.lst", errors="replace"):
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$",
                  _l)
    if _m:
        _LBL.setdefault(_m.group(2), int(_m.group(1), 16))
for _need in ("StartFrame", "LoadLevel"):
    if _need not in _LBL:
        sys.exit(f"label {_need} not found in bank0.lst")
PC_STARTFRAME = _LBL["StartFrame"]
LOADLEVEL = _LBL["LoadLevel"]

frame = -1
in_game = False              # min-SP gate: boot/RESET jsr LoadLevel chain is
                             # documented $F7 depth (sim_bomb_fuse excludes it
                             # the same way via on_title) — count only post-title
min_sp_all = 0xFF            # whole run — contract: >= $F7 (AGENTS: SP $F7 =
                             # lowest byte written $F8 = stack boundary kept)
min_sp_all_pc = min_sp_all_frame = None
min_sp_game = 0xFF           # gameplay outside any LoadLevel chain — contract:
                             # >= $F8 (the transition chain is the boot class)
min_sp_pc = None
min_sp_frame = None
min_sp_calls = []
calls = []                  # dynamic jsr chain: [(jsr_pc, ...)] like sim_bomb_fuse


def in_loadlevel_chain():
    # any active jsr whose target is LoadLevel. Target captured at push time:
    # re-reading mem[pc] later can hit ANOTHER bank (fold/tramp switches
    # $1FF6-$1FF9 mid-chain), giving a bogus operand.
    return any(t == LOADLEVEL for _, t in calls)


def step():
    global frame, min_sp_game, min_sp_pc, min_sp_frame, min_sp_calls
    global min_sp_all, min_sp_all_pc, min_sp_all_frame
    prev_pc = mpu.pc
    op = mem[prev_pc]
    mpu.step()
    if op == 0x20:                          # JSR: entered a subroutine
        calls.append((prev_pc, mem[prev_pc + 1] | (mem[prev_pc + 2] << 8)))
    elif op in (0x60, 0x40):                # RTS / RTI: left one
        if calls:
            calls.pop()
    if frame >= 1 and mpu.sp < min_sp_all:
        min_sp_all, min_sp_all_pc, min_sp_all_frame = mpu.sp, prev_pc, frame
    if (in_game and frame >= 1 and mpu.sp < min_sp_game
            and not in_loadlevel_chain()):
        min_sp_game, min_sp_pc, min_sp_frame = mpu.sp, prev_pc, frame
        min_sp_calls = list(calls)


def at_init_jsr():
    return (mem[mpu.pc] == 0x20
            and mem[mpu.pc + 1] | (mem[mpu.pc + 2] << 8) == LOADLEVEL
            and mpu.pc < PC_STARTFRAME)


def score_total():
    return (mem.ram[SC_TH] * 1000 + mem.ram[SC_HU] * 100
            + (mem.ram[SC_TE] >> 4) * 10 + (mem.ram[SC_TE] & 15))


def run_until(pred, max_frames, what):
    global frame
    f0, steps = frame, 0
    while frame - f0 < max_frames:
        step()
        steps += 1
        if mpu.pc == PC_STARTFRAME:
            frame += 1
            if pred():
                return frame
        if steps > max_frames * 30000:
            sys.exit(f"timeout waiting for {what} (frame {frame})")
    sys.exit(f"timeout waiting for {what} (frame {frame})")


# ---- boot: reach init LoadLevel, pulse RESET, land the player ----
guard = 0
while not at_init_jsr():
    step()
    guard += 1
    if guard > 200000:
        sys.exit(f"never reached init LoadLevel (pc=${mpu.pc:04X})")

seen_play = False
while not (seen_play and mem.ram[DROPT] == 0):
    step()
    if mpu.pc == PC_STARTFRAME:
        frame += 1
        # RESET pulses (intro 2026-10-06): f2 leaves the $FD intro,
        # f5 hits TitleWork RESET -> game start (single-frame pulses)
        mem.swchb = 0xFE if frame in (2, 5) else 0xFF
        if mem.ram[DROPT] not in (0xFF, 0xFD):
            seen_play = True
            in_game = True        # post-title: min-SP guard now counts
        if frame > 600:
            sys.exit(f"never landed (f{frame}, DropTarget=${mem.ram[DROPT]:02X})")
landed = frame
print(f"landed at f{landed}: Level={mem.ram[LEVEL]} RoomNo={mem.ram[ROOMNO]}")

# ---- stage the pickup: bonus inputs + miner under the player ----
mem.ram[0x33] = 0            # EnemyCount ($B3) — level0 room0 spawns a
                             # type-4 enemy that would kill the player the
                             # instant the tally unfreezes (LoseLife ->
                             # DropArm stomps the post-tally asserts)
mem.ram[BAR] = 60            # 50% -> 10 ticks = 500
mem.ram[BOMBS] = 2           # 100
mem.ram[LIVES] = 3           # 300
mem.ram[MINERROOM] = mem.ram[ROOMNO]
mem.ram[MINERX] = mem.ram[ROOMX]
mem.ram[MINERY] = mem.ram[ROOMY]
expected_ticks = 20 + (60 + 3) // 6 + 2 + 3 * 2     # = 38
expected_score = expected_ticks * 50                # = 1900

# ---- arm: next normal frame's CheckMinerPickup must fire ----
f_arm = run_until(lambda: mem.ram[DROPT] == 0xFE, 60, "tally arm")
assert mem.ram[TALLY] == expected_ticks, (
    f"TallyTicks={mem.ram[TALLY]} expected {expected_ticks} "
    f"(20 + (60+3)//6 + bombs 2 + lives*2)")
assert score_total() == 0, f"score before count-up = {score_total()}"
print(f"armed at f{f_arm}: TallyTicks={mem.ram[TALLY]} "
      f"expected {expected_ticks}")

# ---- tally: hold joystick RIGHT, watch freeze + coin + progress ----
# Exit ONLY at a frame boundary after the done path finished: LoadLevel's
# tail jmp DropArm writes DropTarget=$18 mid-done-frame, and `inc Level`
# runs even earlier — a mid-frame exit (on DropTarget or Level) would
# assert before TallyWork's sta BarLevel/sta TickCounter execute (they
# run after DropArm's rts returns to the jsr LoadLevel call site).
mem.swcha = 0x7F             # right held (active low D7=0)
coin_seen = False
frozen_bad = None
tally_frames = 0
tally_steps = 0
done = False
while not done:
    step()
    tally_steps += 1
    if tally_steps > 4000000:
        frozen_bad = f"tally hung mid-frame (f{frame})"
        break
    if mpu.pc == PC_STARTFRAME:
        frame += 1
        tally_frames += 1
        if mem.ram[LEVEL] != 0:
            done = True            # done frame fully completed at this boundary
            break
        if mem.tia[AUDV0] > 0 or mem.ram[BOMBSND] > 0:
            coin_seen = True
        if mem.ram[BAR] != 60:
            frozen_bad = f"BarLevel {mem.ram[BAR]} != 60 (timer not frozen)"
            break
        if mem.ram[ROOMX] != mem.ram[MINERX] or mem.ram[ROOMY] != mem.ram[MINERY]:
            frozen_bad = (f"player moved during tally: "
                          f"({mem.ram[ROOMX]},{mem.ram[ROOMY]}) != "
                          f"({mem.ram[MINERX]},{mem.ram[MINERY]})")
            break
        if tally_frames > 600:
            frozen_bad = f"tally never finished (f{frame})"
            break
assert frozen_bad is None, frozen_bad
assert coin_seen, "no coin blip (AUDV0/BombSnd never nonzero during tally)"

# ---- completion state ----
# done path runs the old pickup tail: level++ / jsr LoadLevel, whose tail
# jmp's DropArm -> re-arms the spawn drop-in (DropTarget = fall Y, was $18
# here), so DropTarget is NOT 0 yet; the drop-in lands a few frames later.
assert mem.ram[DROPT] != 0xFE, f"still in tally mode (DropTarget=$FE)"
assert mem.ram[LEVEL] == 1, f"Level={mem.ram[LEVEL]} expected 1"
assert mem.ram[BAR] == 120, f"BarLevel={mem.ram[BAR]} expected 120"
# TickCounter: done path stores 60, then jmp OverscanAudio's `dec TickCounter`
# (kernel.asm:1055) runs in the same frame -> 59 (the old pickup tail had
# the identical order; bar reload waits for the next 60th frame either way).
assert mem.ram[TICKC] in (59, 60), f"TickCounter={mem.ram[TICKC]} expected 60/59"
assert score_total() == expected_score, (
    f"score {score_total()} expected {expected_score} "
    f"({expected_ticks} ticks x 50)")
print(f"done at f{frame}: tally_frames={tally_frames} score={score_total()} "
      f"DropTarget=${mem.ram[DROPT]:02X} (drop-in fall)")

# drop-in: next level's spawn fall must land, then normal play resumes
run_until(lambda: mem.ram[DROPT] == 0, 240, "next-level drop-in landing")
print(f"landed next level at f{frame}")

# ---- post-tally: game resumes, joystick moves again ----
moved = False
for swcha, name in ((0x7F, "right"), (0xBF, "left")):
    mem.swcha = swcha
    before_x = mem.ram[ROOMX]
    f0 = frame
    while frame - f0 < 120 and not moved:
        step()
        if mpu.pc == PC_STARTFRAME:
            frame += 1
            if mem.ram[ROOMX] != before_x:
                print(f"movement resumed ({name}) at f{frame}: "
                      f"RoomX {before_x} -> {mem.ram[ROOMX]}")
                moved = True
    if moved:
        break
assert moved, "player never moved after tally (input still gated?)"

# Stack guards (AGENTS contract: gameplay >= $F8, whole run incl. LoadLevel
# chains >= $F7 — a push writes AT SP then decrements, so SP $F7 = lowest
# byte written $F8 = stack boundary kept; $F6 = BombX/BombTimer stomped).
# The tally done path jsr LoadLevel bottoms at $F7 = the same transition
# class as boot (and the OLD pickup tail was 2 bytes DEEPER: it also paid
# `jsr CheckMinerPickup` on top — so tally strictly improved this).
print(f"min SP whole run  = ${min_sp_all:02X} at f{min_sp_all_frame} "
      f"pc=${min_sp_all_pc:04X}")
print(f"min SP gameplay   = ${min_sp_game:02X} at f{min_sp_frame} "
      f"pc=${min_sp_pc:04X} chain: "
      f"{' <- '.join(f'${c:04X}' for c, _ in reversed(min_sp_calls)) or '(none)'}")
assert min_sp_all >= 0xF7, (
    f"whole-run min SP ${min_sp_all:02X} < $F7 (stack boundary crossed)")
assert min_sp_game >= 0xF8, (
    f"gameplay min SP ${min_sp_game:02X} < $F8 (tally path too deep)")
print("PASS test_tally")
