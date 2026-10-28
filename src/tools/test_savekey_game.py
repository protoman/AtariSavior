#!/usr/bin/env python3
"""SaveKey wired into the real game (docs/savekey_design.md, user 2026-10-28).

Boots the frozen ROM in py65 with a bit-level 24LC256 (tools/eeprom24lc256.py)
on SWCHA/SWACNT and walks the whole flow:

  A. a save on the chip: the TITLE comes up on the saved stage; RESET on it
     resumes with the saved lives and points;
  B. SELECT to another stage, RESET: a fresh run (3 lives, 0 points);
  C. no key at all: the title and a game start behave as before;
  D. a stage advance (the real tally done path) checkpoints
     {Level, lives, score} and refreshes the high score;
  E. game over (LoseLife with no lives left) erases the save, keeps the high
     score and RESTARTS at the title with 3 lives / 0 points;
  F. clearing the last stage ends the run the same way.
The stack must stay inside the 8-byte mirror ($F8-$FF) while bank4 runs.

Frozen banks + labels (src/tests/frozen/) only - never the live build.
Run: /home/iuri/python3/bin/python3 tools/test_savekey_game.py
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from py65.devices.mpu6502 import MPU  # noqa: E402
from test_cell_map import parse_labels  # noqa: E402
from eeprom24lc256 import Eeprom24LC256  # noqa: E402

FROZEN = Path(os.environ.get("TEST_FROZEN") or ROOT / "tests" / "frozen")
BANKS = [(FROZEN / f"bank{i}.bin").read_bytes() for i in range(8)]

# ZP indexes (addr & $7F)
ROOMX, ROOMY = 0x00, 0x01
DROPT = 0x0A
ROOMNO = 0x18
LEVEL = 0x23
MINERROOM = 0x24
MINERX, MINERY = 0x25, 0x26
LIVES = 0x2C
BAR = 0x2E
BOMBS = 0x70
TALLY = 0x72
SC_TH, SC_HU, SC_TE = 0x73, 0x74, 0x75
BASE = 0x7FE0
REL, RST, SEL = 0xFF, 0xFE, 0xFD

L0 = parse_labels(FROZEN / "bank0.lst", {"StartFrame", "LoseLife"})
L4 = parse_labels(FROZEN / "bank4.lst", {"SkService"})
for need in ("StartFrame", "LoseLife"):
    if need not in L0:
        sys.exit(f"label {need} not found in frozen bank0.lst")
if "SkService" not in L4:
    sys.exit("frozen bank4 has no SkService")
PC_STARTFRAME = L0["StartFrame"]


GAMES = []


class Game:
    def __init__(self, chip_present=True, chip_mem=None):
        GAMES.append(self)
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF
        self.swchb = REL
        self.inpt4 = 0x40
        self.mpu = None
        self.base = 0
        self.chip = Eeprom24LC256(clock=lambda: self.mpu.processorCycles,
                                  present=chip_present)
        if chip_mem is not None:
            self.chip.mem[BASE:BASE + 12] = chip_mem
        self.mpu = MPU(memory=self)
        self.frame = -1
        self.min_sp_sk = 0xFF         # lowest SP while bank4 runs
        self.sk_calls = 0

    # ---- bus ---------------------------------------------------------------
    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:                          # high nibble: the stick; low: the key
            return (self.swcha & 0xF0) | (self.chip.read_swcha() & 0x0F)
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
        if a == 0x0280:
            self.chip.write_swcha(v & 0x0C)      # only pins 3/4 reach the key
            return
        if a == 0x0281:
            self.chip.write_swacnt(v)
            return
        if a in (0x0294, 0x0296, 0x0297):
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            self.tia[a & 0x3F] = v

    # ---- driving -----------------------------------------------------------
    def step(self):
        prev_bank = self.bank
        self.mpu.step()
        if self.bank == 4:
            self.min_sp_sk = min(self.min_sp_sk, self.mpu.sp)
            if prev_bank != 4:
                self.sk_calls += 1

    def next_frame(self, sw=REL, limit=3_000_000):
        n = 0
        while True:
            self.step()
            n += 1
            if n > limit:
                sys.exit(f"frame stalled at f{self.frame} "
                         f"(pc=${self.mpu.pc:04X} bank {self.bank})")
            if self.bank == 0 and self.mpu.pc == PC_STARTFRAME:
                self.frame += 1
                self.swchb = sw
                return

    def run(self, n, sw=REL):
        for _ in range(n):
            self.next_frame(sw)

    def until(self, pred, max_frames, what, sw=REL):
        for _ in range(max_frames):
            self.next_frame(sw)
            if pred():
                return
        sys.exit(f"timeout waiting for {what} (f{self.frame}, "
                 f"DropTarget=${self.ram[DROPT]:02X})")

    # ---- readers -----------------------------------------------------------
    def score(self):
        def bcd(b):
            return (b >> 4) * 10 + (b & 15)
        return (bcd(self.ram[SC_TH]) * 10000 + bcd(self.ram[SC_HU]) * 100
                + bcd(self.ram[SC_TE]))

    def title_shown(self):
        return self.ram[DROPT] == 0xFF

    def record(self):
        return bytes(self.chip.mem[BASE:BASE + 12])


def bcd3(n):
    return bytes(int(f"{n:06d}"[i:i + 2], 16) for i in (0, 2, 4))


def make_record(state, level, lives, score, high):
    rec = bytes([0x53, 0x01, state, level, lives]) + bcd3(score) + bcd3(high)
    c = 0xA5
    for b in rec:
        c ^= b
    return rec + bytes([c])


def boot(g, frames=3):
    g.next_frame()
    g.run(frames)
    assert g.title_shown(), f"boot must land on the title, DROPT=${g.ram[DROPT]:02X}"


def start_game(g):
    g.next_frame(RST)
    g.until(lambda: g.ram[DROPT] == 0, 400, "the drop-in to land")


def stage_pickup(g, bar=60, bombs=2, lives=3):
    """Same staging as tools/test_tally.py: the miner is under the player."""
    r = g.ram
    r[0x33] = 0                    # EnemyCount: nothing may kill the player
    r[BAR] = bar
    r[BOMBS] = bombs
    r[LIVES] = lives
    r[MINERROOM] = r[ROOMNO]
    r[0x27] = 0x10                 # only this miner is left to rescue
    r[MINERX] = r[ROOMX]
    r[MINERY] = r[ROOMY]


def finish_tally(g, level_after):
    """Run until the tally's done path has advanced Level (or restarted)."""
    g.swcha = 0x7F
    for _ in range(700):
        g.next_frame()
        if g.ram[LEVEL] == level_after or g.title_shown():
            g.swcha = 0xFF
            return
    sys.exit(f"tally never finished (Level={g.ram[LEVEL]}, f{g.frame})")


def main() -> int:
    # ---- A. a save on the chip: title preselects it, RESET resumes ------------
    g = Game(chip_mem=make_record(1, 6, 2, 3400, 5000))
    boot(g)
    assert g.ram[LEVEL] == 6, f"title must come up on the saved stage, Level={g.ram[LEVEL]}"
    assert g.ram[SC_TE] == 7 and g.ram[SC_HU] == 0, "title must show stage 7"
    g.run(10)
    assert g.title_shown() and g.ram[LEVEL] == 6
    start_game(g)
    assert g.ram[LEVEL] == 6 and g.ram[LIVES] == 2, (
        f"RESET on the saved stage must resume the lives: {g.ram[LIVES]}")
    assert g.score() == 3400, f"RESET on the saved stage must resume the score: {g.score()}"
    assert g.sk_calls >= 2, "BOOT and RESUME must both have reached bank4"

    # ---- B. another stage picked with SELECT starts fresh ---------------------
    g = Game(chip_mem=make_record(1, 6, 2, 3400, 5000))
    boot(g)
    g.next_frame(SEL)
    g.run(4)
    assert g.ram[LEVEL] == 7 and g.title_shown()
    start_game(g)
    assert g.ram[LIVES] == 3 and g.score() == 0, (
        f"another stage must start fresh: lives {g.ram[LIVES]} score {g.score()}")

    # ---- C. no key: nothing changes -------------------------------------------
    g = Game(chip_present=False)
    boot(g)
    assert g.ram[LEVEL] == 0 and g.ram[SC_TE] == 1
    start_game(g)
    assert g.ram[LIVES] == 3 and g.score() == 0 and not g.chip.writes

    # ---- D. a stage advance checkpoints; E. game over erases -----------------
    g = Game()                                   # a blank chip
    boot(g)
    start_game(g)
    g.run(6)
    stage_pickup(g, bar=60, bombs=2, lives=3)
    g.until(lambda: g.ram[DROPT] == 0xFE, 60, "the tally to arm")
    finish_tally(g, 1)
    assert g.ram[LEVEL] == 1, f"Level {g.ram[LEVEL]}"
    score = g.score()
    assert score == 1900, f"tally score {score}"
    assert g.record() == make_record(1, 1, 3, 1900, 1900), (
        f"stage advance must checkpoint {{level 1, lives 3, score 1900, high 1900}}: "
        f"{g.record().hex()}")
    # the chip survives a power cycle: BOOT selects stage 2 (index 1)
    h = Game(chip_mem=g.record())
    boot(h)
    assert h.ram[LEVEL] == 1, "a checkpoint must come back as the title stage"

    g.until(lambda: g.ram[DROPT] == 0, 240, "the next stage's drop-in")
    # game over: LoseLife with no lives left (entered like a death)
    g.ram[LIVES] = 0
    g.next_frame()
    g.mpu.pc = L0["LoseLife"]
    g.mpu.sp = 0xFD
    g.ram[0x7F], g.ram[0x7E] = 0x01, 0x00        # a harmless return address
    g.until(lambda: g.title_shown() and g.bank == 0, 120, "the restart at the title")
    assert g.record() == make_record(0, 0, 3, 0, 1900), (
        f"game over must erase the save and keep the high score: {g.record().hex()}")
    # (the title shows the stage number in the score window: 1)
    assert g.ram[LEVEL] == 0 and g.ram[LIVES] == 3 and g.score() == 1, (
        "game over must restart the run at the title on stage 1 with 3 lives")

    # ---- F. the last stage cleared ends the run the same way ------------------
    g = Game(chip_mem=make_record(1, 19, 4, 90000, 90000))
    boot(g)
    assert g.ram[LEVEL] == 19
    start_game(g)
    assert g.ram[LIVES] == 4 and g.score() == 90000
    g.run(6)
    stage_pickup(g, bar=60, bombs=2, lives=4)
    g.until(lambda: g.ram[DROPT] == 0xFE, 60, "the last tally to arm")
    finish_tally(g, 20)
    g.until(lambda: g.title_shown() and g.bank == 0, 120, "the restart after the last stage")
    won = g.record()
    assert won[2] == 0, f"the run is over: no save may remain: {won.hex()}"
    ticks = 20 + (60 + 3) // 6 + 2 + 4 * 2     # miner + time + bombs + 2 per life
    assert won[8:11] == bcd3(90000 + 50 * ticks), (
        f"the winner's score must become the high score: {won.hex()}")
    assert g.ram[LEVEL] == 0 and g.ram[LIVES] == 3 and g.score() == 1

    # ---- the stack stays inside the mirror while bank4 runs --------------------
    low = min(game.min_sp_sk for game in GAMES)
    assert low >= 0xF7, (
        f"bank4 reached SP ${low:02X} (< $F7 clobbers BombTimer/BombX)")

    print("test_savekey_game: OK (title preselects the saved stage; RESET resumes "
          "lives+score; SELECT elsewhere starts fresh; no key = unchanged; stage "
          "advance checkpoints; game over and the last stage erase the save, keep "
          f"the high score and restart at the title; min SP in bank4 ${low:02X})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
