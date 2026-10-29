#!/usr/bin/env python3
"""SaveKey leaf (bank4 `SkService`): stage checkpoint, high score, resume.

Drives the REAL bank4 image against a bit-level 24LC256 model
(tools/eeprom24lc256.py) wired to SWCHA/SWACNT exactly like the SaveKey. The
design is docs/savekey_design.md; the ops are
  0 BOOT        title power-on: Level := the saved stage
  1 RESUME      RESET on the saved stage: lives + score := the saved ones
  2 CHECKPOINT  stage advance: save {Level, lives, score}, high = max
  3 GAMEOVER    erase the save, high = max(high, score), restart at the title
  4 TITLE       every title frame (no I2C): stage number <-> high score in the
                HUD score window
All return C=0 when they did something, C=1 when there was nothing to do (no
key, no/invalid data, wrong stage).

Frozen banks + labels (src/tests/frozen/) only - never the live build.
Run: /home/iuri/python3/bin/python3 tools/test_savekey.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402
from eeprom24lc256 import Eeprom24LC256  # noqa: E402

FROZEN = Path(os.environ.get("TEST_FROZEN") or ROOT / "tests" / "frozen")
L4 = parse_labels(FROZEN / "bank4.lst", {"SkService"})
if "SkService" not in L4:
    sys.exit("frozen bank4 has no SkService yet (red)")
SERVICE = L4["SkService"]

# game variables the ops touch (kernel.asm ZP; hand copies live in bank4.asm)
LEVEL, LIVES = 0xA3, 0xAC
SC_TH, SC_HU, SC_TE = 0xF3, 0xF4, 0xF5
BASE = 0x7FE0                       # record block in the chip
OP_BOOT, OP_RESUME, OP_CHECKPOINT, OP_GAMEOVER, OP_TITLE = 0, 1, 2, 3, 4
ENEMY_RAMP, SK_HI = 0xC2, 0x93        # frame clock; vyLo/vyHi/PlayerYSub = the high score
FRAME_CYCLES = 19912                # 262 lines x 76 cycles
LEVEL_COUNT = 20
RESTART_PC = 0xF005                 # bank0's `jmp GameStart` after the power-up pad


class KeyMem(Mem):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.bank = 4

    def __getitem__(self, a):
        if (a & 0xFFFF) == 0x0280:
            return self.bus.read_swcha()
        return super().__getitem__(a)

    def __setitem__(self, a, v):
        a &= 0xFFFF
        if a == 0x0280:
            self.bus.write_swcha(v)
        elif a == 0x0281:
            self.bus.write_swacnt(v)
        else:
            super().__setitem__(a, v)


class Console:
    """One RAM + one chip; `power_cycle()` clears RAM, keeps the chip."""

    def __init__(self, present=True):
        self.base = 0                       # cycles of the earlier power-ons
        self.mpu = None
        self.chip = Eeprom24LC256(clock=lambda: self.base + self.mpu.processorCycles,
                                  present=present)
        self.power_cycle()

    def power_cycle(self):
        """RAM is lost, the chip (and its clock) is not."""
        if self.mpu is not None:
            self.base += self.mpu.processorCycles
        self.mem = KeyMem(self.chip)
        self.mpu = MPU(memory=self.mem)

    def set(self, level=0, lives=3, score=0):
        r = self.mem.ram
        r[LEVEL & 0x7F], r[LIVES & 0x7F] = level, lives
        r[SC_TH & 0x7F] = int(f"{score:06d}"[0:2], 16)
        r[SC_HU & 0x7F] = int(f"{score:06d}"[2:4], 16)
        r[SC_TE & 0x7F] = int(f"{score:06d}"[4:6], 16)

    def get(self):
        r = self.mem.ram
        score = int(f"{r[SC_TH & 0x7F]:02x}{r[SC_HU & 0x7F]:02x}"
                    f"{r[SC_TE & 0x7F]:02x}")
        return dict(level=r[LEVEL & 0x7F], lives=r[LIVES & 0x7F], score=score)

    def op(self, op):
        """Run SkService(op); returns (carry, cycles)."""
        m = self.mpu
        self.mem.bank = 4
        m.pc = SERVICE
        m.a, m.x, m.y = op, 0, 0
        m.sp = 0xFD
        self.mem[0x1FF] = 0x01
        self.mem[0x1FE] = 0x00
        c0 = m.processorCycles
        low = m.sp
        self.restarted = False
        for _ in range(400000):
            m.step()
            low = min(low, m.sp)
            if m.pc == RTS_SENTINEL:
                break
            if self.mem.bank == 0 and m.pc == RESTART_PC:
                self.restarted = True          # bank0 `jmp GameStart` is next
                break
        else:
            raise AssertionError(f"op {op} never returned (pc=${m.pc:04X})")
        # The stack mirror is 8 bytes ($F8-$FF) and the caller + its pad already
        # use up to 4 of them: the op may nest at most 4 bytes deep (two jsr).
        assert low >= 0xF9, f"op {op} nested {0xFD - low} stack bytes (max 4)"
        assert not self.chip.violations, self.chip.violations
        assert self.chip.swacnt == 0, "bus not released after the op"
        # a restart op does not return: report C=1 ("nothing for the caller")
        return (True if self.restarted else bool(m.p & 1)), m.processorCycles - c0

    def record(self):
        return bytes(self.chip.mem[BASE:BASE + 12])


def chk(rec):
    c = 0xA5
    for b in rec[:11]:
        c ^= b
    return c


def bcd(n):
    return bytes(int(f"{n:06d}"[i:i + 2], 16) for i in (0, 2, 4))


def expect_record(rec, state, level, lives, score, high):
    want = bytes([0x53, 0x01, state, level, lives]) + bcd(score) + bcd(high)
    want += bytes([chk(want + b"\0")])
    assert rec == want, f"record {rec.hex()} != {want.hex()}"


def main() -> int:
    worst = 0

    # 1. no key: every op is a quick no-op, nothing is written or changed
    c = Console(present=False)
    c.set(level=5, lives=2, score=1234)
    before = c.get()
    for op in (OP_BOOT, OP_RESUME, OP_CHECKPOINT, OP_GAMEOVER):
        carry, cyc = c.op(op)
        assert carry, f"op {op}: no key must report C=1"
        assert c.restarted == (op == OP_GAMEOVER), (
            f"op {op}: only game over restarts, even with no key")
        assert c.get() == before, f"op {op} changed the game with no key"
        assert cyc < 2500, f"op {op}: no key cost {cyc} cycles (abort at the NACK)"
    assert not c.chip.writes

    # 2. a blank chip (all $FF): nothing to boot/resume; checkpoint writes
    c = Console()
    c.set(level=0, lives=3, score=0)
    assert c.op(OP_BOOT)[0] and c.op(OP_RESUME)[0], "blank chip must not load"
    c.set(level=4, lives=3, score=1250)
    carry, cyc = c.op(OP_CHECKPOINT)
    worst = max(worst, cyc)
    assert not carry, "checkpoint on a blank chip must save"
    expect_record(c.record(), 1, 4, 3, 1250, 1250)
    assert len(c.chip.writes) == 1 and c.chip.writes[0][0] == BASE \
        and len(c.chip.writes[0][1]) == 12, c.chip.writes

    # 3. power-on: the saved stage is selected; RESET on it resumes
    c.power_cycle()
    c.set(level=0, lives=3, score=0)
    carry, cyc = c.op(OP_BOOT)
    worst = max(worst, cyc)
    assert not carry and c.get()["level"] == 4, c.get()
    carry, cyc = c.op(OP_RESUME)
    worst = max(worst, cyc)
    assert not carry and c.get() == dict(level=4, lives=3, score=1250), c.get()
    # ... but another stage picked with SELECT starts fresh
    c.power_cycle()
    c.set(level=6, lives=3, score=0)
    assert c.op(OP_RESUME)[0], "a different stage must not resume"
    assert c.get() == dict(level=6, lives=3, score=0)

    # 4. checkpoints overwrite the save; the high score only goes up
    c.set(level=5, lives=2, score=900)
    assert not c.op(OP_CHECKPOINT)[0]
    expect_record(c.record(), 1, 5, 2, 900, 1250)
    c.set(level=6, lives=4, score=3400)
    assert not c.op(OP_CHECKPOINT)[0]
    expect_record(c.record(), 1, 6, 4, 3400, 3400)

    # 5. game over: the save is gone, the high score stays
    c.set(level=7, lives=0, score=2000)
    carry, cyc = c.op(OP_GAMEOVER)
    worst = max(worst, cyc)
    assert c.restarted, "game over must restart the run at the title"
    rec = c.record()
    assert rec[2] == 0, "game over must clear the save state"
    expect_record(rec, 0, 0, 3, 0, 3400)
    c.power_cycle()
    c.set(level=0, lives=3, score=0)
    assert c.op(OP_BOOT)[0] and c.op(OP_RESUME)[0], "nothing to load after game over"
    c.set(level=9, lives=1, score=5000)
    c.op(OP_GAMEOVER)
    expect_record(c.record(), 0, 0, 3, 0, 5000)

    # 5b. the last stage cleared (the caller already did `inc Level`): same as a
    # game over, and with the CHECKPOINT op
    c.set(level=LEVEL_COUNT, lives=2, score=7000)
    c.op(OP_CHECKPOINT)
    assert c.restarted, "clearing the last stage must restart the run"
    expect_record(c.record(), 0, 0, 3, 0, 7000)

    # 6. damaged / foreign / impossible data is ignored, then repaired
    for label, damage in (
            ("bit flip", lambda b: b.__setitem__(BASE + 4, b[BASE + 4] ^ 0x10)),
            ("foreign data", lambda b: b.__setitem__(slice(BASE, BASE + 12),
                                                     bytes(range(12)))),
            ("wrong magic", lambda b: b.__setitem__(BASE, 0x54))):
        c = Console()
        c.set(level=3, lives=3, score=100)
        c.op(OP_CHECKPOINT)
        damage(c.chip.mem)
        c.power_cycle()
        c.set(level=0, lives=3, score=0)
        assert c.op(OP_BOOT)[0], f"{label}: boot must ignore it"
        assert c.op(OP_RESUME)[0], f"{label}: resume must ignore it"
        assert c.get() == dict(level=0, lives=3, score=0)
        c.set(level=1, lives=3, score=700)
        assert not c.op(OP_CHECKPOINT)[0], f"{label}: checkpoint must repair"
        expect_record(c.record(), 1, 1, 3, 700, 700)

    def forge(c, state, level, lives):
        rec = bytes([0x53, 0x01, state, level, lives]) + bcd(800) + bcd(800)
        rec += bytes([chk(rec + b"\0")])
        c.chip.mem[BASE:BASE + 12] = rec

    c = Console()
    forge(c, 1, LEVEL_COUNT, 3)                 # level out of range
    c.set(level=2, lives=3, score=0)
    assert c.op(OP_BOOT)[0] and c.get()["level"] == 2
    forge(c, 1, 2, 9)                           # more lives than the game has
    assert c.op(OP_RESUME)[0] and c.get()["lives"] == 3
    forge(c, 1, 2, 0)                           # zero lives is a valid last life
    assert not c.op(OP_RESUME)[0] and c.get()["lives"] == 0

    # 6b. BOOT leaves the high score for the title; TITLE alternates it with the
    # stage number (only clock $80-$BF shows the high score)
    c = Console()
    c.set(level=6, lives=2, score=3400)
    c.op(OP_CHECKPOINT)
    c.set(level=9, lives=3, score=4000)
    c.op(OP_CHECKPOINT)                       # high = 4000
    c.power_cycle()
    c.set(level=0, lives=3, score=0)
    assert not c.op(OP_BOOT)[0]
    r = c.mem.ram
    assert bytes(r[SK_HI & 0x7F:(SK_HI & 0x7F) + 3]) == bcd(4000), "BOOT must hand over the high score"
    for lvl in range(LEVEL_COUNT):
        c.set(level=lvl, lives=3, score=0)
        r[ENEMY_RAMP & 0x7F] = 0x10
        carry, cyc = c.op(OP_TITLE)
        assert cyc < 400, f"title op took {cyc} cycles (runs every title frame)"
        assert c.get()["score"] == lvl + 1, (
            f"title shows stage {lvl + 1} as packed BCD, got {c.get()}")
        r[ENEMY_RAMP & 0x7F] = 0x90
        c.op(OP_TITLE)
        assert c.get()["score"] == 4000, f"2nd half must show the high score: {c.get()}"
    c.power_cycle()                            # no high score yet: never shown
    c.set(level=3, lives=3, score=0)
    c.mem.ram[ENEMY_RAMP & 0x7F] = 0x90
    c.op(OP_TITLE)
    assert c.get()["score"] == 4, "no high score: the stage number only"
    r = c.mem.ram
    c.power_cycle()
    c.set(level=2, lives=3, score=0)
    for clk in (0x00, 0x7F, 0xC0, 0xFF):
        c.mem.ram[SK_HI & 0x7F] = 0x12
        c.mem.ram[ENEMY_RAMP & 0x7F] = clk
        c.op(OP_TITLE)
        assert c.get()["score"] == 3, f"clock ${clk:02X} must show the stage number"

    # 7. cost: every op fits in ONE frame (the level-change hiccup budget)
    assert worst <= FRAME_CYCLES - 2000, (
        f"slowest op took {worst} cycles; budget {FRAME_CYCLES - 2000}")

    print(f"test_savekey: OK (no key, blank, checkpoint, boot, resume, high "
          f"score, game over, damaged data; slowest op {worst} cycles = "
          f"{worst * 100 // FRAME_CYCLES}% of a frame)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
