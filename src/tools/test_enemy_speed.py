#!/usr/bin/env python3
"""Enemy speed multiplier: x1 / x1.5 / x2 / x2.5 / x3 every 5 levels (2026-10-26).

User request: "each 5 levels the speed of the enemies increases (x1.5, x2, x2.5,
x3 ...)". Levels 1-5 stay x1 (0-based Level 0-4), 6-10 are x1.5, 11-15 x2, 16-20
x2.5, 21+ x3.

Design: every enemy motion is gated by / derived from a clock. The old gates read
EnemyRamP (bat, spider, tentacle and moth bobs, the moth's patrol) or TickCounter
(snake, tentacle chase) - clocks that also drive the player's walk cycle, the
water tide, the hcrunch band and the laser tone, so they cannot be sped up. The
enemies now read their OWN clock, EnemyClk ($CC). UpdateEnemies runs one PASS per
clock tick: EnemySpd ($CD) = 2 + Level / 5 half-units per frame; an accumulator
(EnemyFrac $CE) turns that into 1, 2, 1, 2 ... passes (x1.5) etc., and each pass
does `inc EnemyClk` and the whole enemy update. The passes are `jmp`s (prologue at
the entry, epilogue at UE_Exit), never a nested jsr - the stack floor cannot take
one more level.

Drives the real frozen banks. Run: /home/iuri/python3/bin/python3 tools/test_enemy_speed.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import test_cell_map as CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

SRC = ROOT
FROZEN = SRC / "tests" / "frozen"


def labels(bank, names):
    got = parse_labels(FROZEN / f"bank{bank}.lst", set(names))
    miss = set(names) - got.keys()
    if miss:
        sys.exit(f"frozen bank{bank}.lst labels missing: {sorted(miss)}")
    return got


L0 = labels(0, ["UpdateEnemies", "EnemyClk", "EnemySpd", "EnemyFrac", "EnemyCount",
                "EnemyDataLo", "EnemyDataHi", "EnemyDeadMask", "EnemyRamX",
                "EnemyRamY", "TickCounter"])
L2 = labels(2, ["LoadLevelB2", "LF_TailSwap", "LevelDataTable", "Level",
                "EnemySpd"])

bank2 = bytearray(CM.BANK2)
REC = 0xFFD0


def poke(mem, lab, name, val):
    mem.ram[lab[name] - 0x80] = val & 0xFF


def peek(mem, lab, name):
    return mem.ram[lab[name] - 0x80]


def run(mem, bank, pc, stop, steps=60000):
    mem.bank = bank
    mpu = MPU(memory=mem)
    mpu.pc, mpu.a, mpu.x, mpu.y = pc, 0, 0, 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(steps):
        mpu.step()
        if mpu.pc == stop or mpu.pc == RTS_SENTINEL:
            return
    sys.exit(f"never reached ${stop:04X} (pc=${mpu.pc:04X}, bank={mem.bank})")


# --- 1. LoadLevel seeds the half-unit speed: 2 + Level / 5 -----------------------
for level, want in ((0, 2), (4, 2), (5, 3), (9, 3), (10, 4), (14, 4), (15, 5),
                    (19, 5)):
    mem = CM.Mem()
    poke(mem, L2, "Level", level)
    poke(mem, L2, "DropTarget", 0) if "DropTarget" in L2 else None
    run(mem, 2, L2["LoadLevelB2"], L2["LF_TailSwap"])
    got = peek(mem, L2, "EnemySpd")
    assert got == want, (f"Level {level}: EnemySpd={got}, want {want} "
                         f"(x{want / 2:g})")

# --- 2. passes per frame: the clock advances EnemySpd / 2 per frame ----------------
# One BAT record (type 1: UEDispatch gives it no X motion) so the body runs.
bank2[REC - 0xF000:REC - 0xF000 + 3] = bytes([1, 60, 60])
CM.BANK2 = bytes(bank2)
FRAMES = 20


class TimedMem(CM.Mem):
    """INTIM ($0284) reads `intim`: UEEpilogue lets an EXTRA pass start only
    while the overscan timer has UE_MIN_INTIM units left (2026-10-28)."""
    intim = 44

    def __getitem__(self, a):
        if (a & 0xFFFF) == 0x0284:
            return self.intim
        return super().__getitem__(a)


for spd, want in ((2, 20), (3, 30), (4, 40), (5, 50), (6, 60)):
    mem = TimedMem()
    poke(mem, L0, "EnemyCount", 1)
    poke(mem, L0, "EnemyDataLo", REC & 0xFF)
    poke(mem, L0, "EnemyDataHi", REC >> 8)
    poke(mem, L0, "EnemyDeadMask", 0)
    poke(mem, L0, "EnemySpd", spd)
    poke(mem, L0, "EnemyFrac", 0)
    poke(mem, L0, "EnemyClk", 0)
    total = 0
    for _ in range(FRAMES):
        before = peek(mem, L0, "EnemyClk")
        run(mem, 0, L0["UpdateEnemies"], RTS_SENTINEL)
        total += (peek(mem, L0, "EnemyClk") - before) & 0xFF
    assert total == want, (f"EnemySpd={spd}: the enemy clock advanced {total} ticks "
                           f"in {FRAMES} frames, want {want} (x{spd / 2:g})")

# --- 2b. the overscan governor: with the timer nearly spent only the FIRST pass runs
for spd in (2, 5):
    mem = TimedMem()
    mem.intim = 0
    poke(mem, L0, "EnemyCount", 1)
    poke(mem, L0, "EnemyDataLo", REC & 0xFF)
    poke(mem, L0, "EnemyDataHi", REC >> 8)
    poke(mem, L0, "EnemyDeadMask", 0)
    poke(mem, L0, "EnemySpd", spd)
    poke(mem, L0, "EnemyFrac", 0)
    poke(mem, L0, "EnemyClk", 0)
    total = 0
    for _ in range(FRAMES):
        before = peek(mem, L0, "EnemyClk")
        run(mem, 0, L0["UpdateEnemies"], RTS_SENTINEL)
        total += (peek(mem, L0, "EnemyClk") - before) & 0xFF
    assert total == FRAMES, (f"EnemySpd={spd}, INTIM=0: {total} ticks in {FRAMES} "
                             f"frames, want {FRAMES} (extra passes dropped, first kept)")

# --- 3. no enemy motion still reads a shared clock ---------------------------------
K = (SRC / "kernel.asm").read_text()
B1 = (SRC / "bank1.asm").read_text()
B2 = (SRC / "bank2.asm").read_text()


def body(text, start, end):
    seg = text[text.index(start):text.index(end, text.index(start))]
    return "\n".join(ln.split(";")[0] for ln in seg.splitlines())


derive = body(K, "\nDeriveEnemyY:", "\n; ====")
assert "EnemyRamP" not in derive and "TickCounter" not in derive, \
    "DeriveEnemyY must read EnemyClk (bat / tentacle / spider bobs)"
assert "EnemyClk" in derive
snake = body(K, "\nUE_SnakeBody:", "\nUE_Next:")
assert "EnemyClk" in snake and "TickCounter" not in snake, \
    "the snake's patrol gate must be the enemy clock"
tent = body(K, "\nUE_Tentacle:", "\n.TentOut:")
assert "EnemyClk" in tent and "TickCounter" not in tent, \
    "the tentacle's chase gate must be the enemy clock"
moth = body(B2, "\nMothRoutine:", "\n.MothRun:")
assert "EnemyClk" in moth and "EnemyRamP" not in moth, \
    "the moth's patrol gate must be the enemy clock"
my = body(B1, "\nMothYDerive:", "\n    rts")
assert "EnemyClk" in my and "EnemyRamP" not in my, \
    "the moth's Y bob must read the enemy clock"

print("test_enemy_speed: OK (x1/1.5/2/2.5/3 by level, passes per frame, own clock)")
