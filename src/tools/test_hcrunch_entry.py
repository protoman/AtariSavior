#!/usr/bin/env python3
"""hcrunch must already be MOVING when the player arrives (user 2026-10-25).

User report: "it should move before the player is on the same band, so the
player can see it moving beforehand."  The hcrunch prefix is driven by the
free-running frame clock EnemyRamP (HcrClock: 4 buckets of home dwell, then
grow, then retract), and EnemyRamP is never touched by a room change - so the
phase a player meets is whatever the clock happened to be: ~1 entry in 4
lands in the 64-frame home dwell, the band looks dead for the whole fall into
band 1 and the crush starts under him.

Contract: loading a room that carries a hcrunch feature record (class kind
b7 = prefix) restarts the clock at the START of the grow phase (EnemyRamP =
$40, bucket 4), so the prefix is visibly advancing from the first frames. A
room WITHOUT a hcrunch record must not touch the clock (enemy bob / phase
blink keep their phase).

Drives the real frozen ExtrasLoad (bank3) for frozen level 3, whose room 2 is
a full-prefix hcrunch room (src/tests/rooms/level_003.json).
Run: /home/iuri/python3/bin/python3 tools/test_hcrunch_entry.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"
NEED = {"ExtrasLoad", "LevelConnSpare", "Level", "EnemyRamP", "PF0Buf"}
L = parse_labels(FROZEN / "bank3.lst", NEED)
missing = NEED - L.keys()
if missing:
    sys.exit(f"frozen labels missing: {sorted(missing)}")

SENTINEL_P = 0xAA
LEVEL_IDX = 2                      # frozen level 3 (0-based 2)


LAST = [0, 0]                      # PF2 row 1 / row 2 after the last load


def load(ordinal: int):
    mem = Mem()
    r = mem.ram
    r[L["Level"] - 0x80] = LEVEL_IDX
    r[L["LevelConnSpare"] - 0x80] = ordinal
    r[L["EnemyRamP"] - 0x80] = SENTINEL_P
    mem.bank = 3
    mpu = MPU(memory=mem)
    mpu.pc = L["ExtrasLoad"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(20000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            # full prefix on band 2 (row 1) or band 3 (row 2, 2026-10-28)
            pf2_row = r[L["PF0Buf"] - 0x80 + 8 + 1]
            LAST[:] = [pf2_row, r[L["PF0Buf"] - 0x80 + 8 + 2]]
            if pf2_row != 0xFF:
                pf2_row = r[L["PF0Buf"] - 0x80 + 8 + 2]
            return r[L["EnemyRamP"] - 0x80], pf2_row
    sys.exit(f"ExtrasLoad(ordinal {ordinal}) never returned")


# Only the ordinals the frozen level 3 really owns: past its last record the
# loader would read whatever bytes follow in the bank (they move with every
# data change), which is not a room.
N_ROOMS = sum(1 for _l in (ROOT / "tests" / "generated"
                           / "level_003_extras.asm").read_text().splitlines()
              if _l.lstrip().startswith(".byte") and "; room " in _l)
assert N_ROOMS >= 2, N_ROOMS
hc = [(o, p) for o in range(1, N_ROOMS + 1) for p, pf2 in [load(o)] if pf2 == 0xFF]
assert hc, "no frozen level-3 room staged a full hcrunch prefix (fixture drift)"
for o, p in hc:
    assert p == 0x40, (f"hcrunch room (extras ordinal {o}) left the clock at "
                       f"${p:02X}: the prefix can sit in its home dwell while "
                       "the player arrives (want $40 = start of the grow phase)")
for o in range(1, N_ROOMS + 1):
    p, pf2 = load(o)
    if pf2 != 0xFF:
        assert p == SENTINEL_P, (f"room without hcrunch (ordinal {o}) changed "
                                 f"the frame clock to ${p:02X}")
# Band 3 crunch (user 2026-10-28): extras feature byte b4 = row 2. Patch the
# fixture's `$89` (hcrunch, col 9) to `$99` in the private bank image: the
# static prefix must land on row 2 and leave row 1 alone.
import test_cell_map as _TC  # noqa: E402
_img = bytearray(_TC.BANK3)
_at = bytes(_img).find(bytes([0x04, 0x00, 0x00, 0x89, 0x01, 0x82]))
assert _at >= 0, "fixture extras record moved"
_img[_at + 3] = 0x99
_TC.BANK3 = _img
_p, _row = load(2)
assert _p == 0x40, _p
assert LAST == [0x00, 0xFF], f"row-2 crunch: PF2 rows 1/2 = {LAST}, want [0, $FF]"
print("test_hcrunch_entry: OK (hcrunch rooms restart the clock at the grow phase)")
