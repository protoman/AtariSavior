#!/usr/bin/env python3
"""Phase 5 key pickup guard (docs/feature_tiles_plan.md).

Contract under test (kernel.asm):
  * CheckEnemyHit routes type 6 (KEY) to CEH_Key BEFORE the kill path — the
    key is collected, never fatal.
  * CEH_Key latches KeyHeld (LevelStartRoom $A7 b7) and marks the key slot
    dead in EnemyDeadMask (so it vanishes); it contains NO LoseLife.
  * SelectActiveObject skips a type-6 render while KeyHeld (never reappears).
  * Data: ObjColorTab slot 0 is the yellow key colour (the per-row table
    overrides the frame colour, so slot 0 must be $1C, not the old blank $00);
    EnemyColorTable[6]/ObjSpriteOffTable[6] map the type.

Two checks: (1) asm structure; (2) a py65 run of CEH_Key asserting the two
RAM writes.  Run: /home/iuri/python3/bin/python3 tools/test_key_pickup.py
"""
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SRC = TOOLS.parent / "src"
sys.path.insert(0, str(TOOLS))

from test_cell_map import (  # noqa: E402
    Mem, RTS_SENTINEL, parse_labels, BANK0,
)

K = (SRC / "kernel.asm").read_text()

# --- 1. asm structure -------------------------------------------------------
ceh = K[K.index("\nCheckEnemyHit:"):K.index("\nBombTick")]
assert "cmp #KEY" in ceh and "jmp CEH_Key" in ceh, \
    "CheckEnemyHit must dispatch type 6 to CEH_Key"
assert ceh.index("jmp CEH_Key") < ceh.index("jmp LoseLife"), \
    "the type-6 dispatch must precede the kill path"
assert "cmp #KEY" in ceh.split("jmp LoseLife")[0], \
    "the key branch must be before the enemy-kill tail"

body = K[K.index("\nCEH_Key:"):]
body = body[: body.index("rts") + 3]
assert "sta LevelStartRoom" in body and "ora #$80" in body, \
    "CEH_Key must latch KeyHeld = $A7 b7"
assert "sta EnemyDeadMask" in body, "CEH_Key must mark the key slot dead"
assert "ora #$18" not in body, "CEH_Key must NOT auto-open doors"
assert "LoseLife" not in body, "CEH_Key must not kill the player"

B2 = (SRC / "bank2.asm").read_text()
assert "LevelStartRoom = $A7" in B2, "bank2 must hand-copy LevelStartRoom"
# Touch-to-open: the M1 (left door) strip opens only when the player's box
# overlaps it AND KeyHeld (not by merely holding the key).
ov = B2[B2.index(".OvM1block:"):B2.index(".OvM1no:")]
assert "lda LevelStartRoom" in ov and "ora #$10" in ov, \
    "OvM1Block must key-unlock the left door (b4) on touch"

so = K[K.index("\nSelectActiveObject:"):K.index("\nEnemyColorTable:")]
assert "cpx #KEY" in so and "bmi .SOEnemySkip" in so, \
    "SelectActiveObject must skip a type-6 render while KeyHeld"
# The parked "off" object must compensate RoomY (a constant 144 wrapped into
# view for RoomY >= 112 and leaked ObjSprites[row+$FF] = slot 0 = the key art).
noobj = K[K.index(".SONoObj:"):]
noobj = noobj[:noobj.index("rts")]
assert "sbc RoomY" in noobj, \
    "off-object ObjTop must be RoomY-compensated (never wraps into view)"

assert re.search(r"\.byte\s+\$1c,\$1c,\$1c,\$1c", K), \
    "ObjColorTab slot 0 must be $1C (yellow) — per-row table overrides frame"

# --- 2. py65 run of CEH_Key -------------------------------------------------
want = {"CEH_Key", "EnemyBitTable", "EnemyDeadMask", "LevelStartRoom"}
L0 = parse_labels(SRC / "bank0.lst", want)
missing = want - L0.keys()
if missing:
    sys.exit(f"bank0.lst labels missing: {sorted(missing)}")

KEY = 6
idx = 2
bit = BANK0[L0["EnemyBitTable"] - 0xF000 + idx]

mem = Mem()
r = mem.ram
r[L0["LevelStartRoom"] - 0x80] = 0x02      # start room, KeyHeld (b7) clear
r[L0["EnemyDeadMask"] - 0x80] = 0x01       # another enemy already dead
mem.bank = 0
from py65.devices.mpu6502 import MPU  # noqa: E402
mpu = MPU(memory=mem)
mpu.pc = L0["CEH_Key"]
mpu.a = 0
mpu.x = idx
mpu.y = 0
mpu.sp = 0xFD
mem[0x1FF] = 0x01
mem[0x1FE] = 0x00
for _ in range(400):
    mpu.step()
    if mpu.pc == RTS_SENTINEL:
        break
else:
    sys.exit(f"CEH_Key never returned (pc=${mpu.pc:04X})")

got_lsr = r[L0["LevelStartRoom"] - 0x80]
got_dm = r[L0["EnemyDeadMask"] - 0x80]
assert got_lsr == 0x82, f"KeyHeld not latched: LevelStartRoom=${got_lsr:02X} want $82"
assert got_dm == (0x01 | bit), \
    f"key slot not marked dead: EnemyDeadMask=${got_dm:02X} want ${0x01|bit:02X}"

print(f"test_key_pickup: OK (type 6 -> CEH_Key before kill; KeyHeld $A7 b7 "
      f"latched; slot {idx} dead-bit set; render skipped while held; "
      f"ObjColorTab[0]=$1C)")
