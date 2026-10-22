#!/usr/bin/env python3
"""Mid-band slot swap (Phase 5b, 2026-10-22) — the user's flicker case, ROM level.

`StageSlot1` pairs two candidates in ONE 48-line band when their drawn windows
are at least OBJ_WINDOW (16) lines apart — the miner sitting while an enemy
walks past. `.Line` then swaps the live GRP1 trio at `ObjSwap` (= ObjTop1-1) and
repositions P1 with SetObjectXPos: the one horizontal reposition this kernel
performs inside the frame.

Drives the real ROM (frozen banks, wall-model timing like
tools/test_phase3_ball.py):
  1. boot into gameplay through the RESET pulse and measure the baseline frame
     length (no pair in the room);
  2. fabricate the stage's case — the room's own enemy at y=60 and the miner
     27 lines below at y=87, SAME band (60//48 == 87//48) — then assert:
       * two DISTINCT designs reach GRP1 in the SAME frame (one is
         OBJ_MINER): the objects share the frame instead of rotating,
       * the paired frame is baseline + 3 scanlines and CONSTANT across
         frames (no oscillation = no flicker).

Run: /home/iuri/python3/bin/python3 tools/test_slot1_midband.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import frozen_rom  # noqa: E402
from test_phase2_ball import Mem, LABELS  # noqa: E402

from py65.devices.mpu6502 import MPU  # noqa: E402

ROM = frozen_rom.path()
OBJ_MINER = 112
SWAP_COST_LINES = 3        # SOXP line + its HMOVE line + the uncounted trigger
Z = dict(ObjBase=0x36, EnemyCount=0x33, EnemyDeadMask=0x3A, EnemyRamY=0x62,
         EnemyRamX=0x3D, LevelMinerRoom=0x24, MinerX=0x25, MinerY=0x26,
         RoomNo=0x18)
PC_START = LABELS["StartFrame"]
PC_KERNEL = LABELS["CaveKernelRow"]     # sample designs only inside the cave
PC_KERNEL_END = LABELS[".AfterRows"]


def main() -> int:
    blob = ROM.read_bytes()
    assert len(blob) == 16384, f"{ROM} is {len(blob)} bytes, want 16K"
    banks = [bytearray(blob[4096 * i:4096 * (i + 1)]) for i in range(4)]
    mem = Mem(banks)
    mpu = MPU(memory=mem)
    prev = 0

    def step():
        nonlocal prev
        mpu.step()
        mem.wall += mpu.processorCycles - prev
        prev = mpu.processorCycles
        if mem.wsync_seen:                      # WSYNC stall = line boundary
            w = mem.wall
            mem.wall = (w // 76 + 1) * 76 if w % 76 else w
            mem.wsync_seen = False

    def frame(*, pair):
        """One frame from StartFrame; returns (lines, designs seen in GRP1)."""
        r = mem.ram
        if pair:
            # enemy at y=60 and the miner at 84 (+3 draw offset = 87): same
            # band 1, windows 27 lines apart -> StageSlot1 pairs them, slot 0 =
            # the enemy (lower), slot 1 = the miner.
            r[Z["EnemyCount"]] = 1
            r[Z["EnemyDeadMask"]] = 0
            r[Z["EnemyRamY"]] = 60
            r[Z["EnemyRamX"]] = 71
            r[Z["LevelMinerRoom"]] = r[Z["RoomNo"]] & 0x7F
            r[Z["MinerX"]] = 40
            r[Z["MinerY"]] = 84
        wall0 = mem.wall
        seen = set()
        while True:
            step()
            if (mem.bank == 0 and PC_KERNEL <= mpu.pc < PC_KERNEL_END):
                # Only lines the cave kernel actually draws: an ObjBase sampled
                # outside it can be a zero/garbage pre-staging value.
                seen.add(r[Z["ObjBase"]])
            if mem.bank == 0 and mpu.pc == PC_START:
                break
        return (mem.wall - wall0) / 76, seen

    # --- boot through the title (RESET pulse on frames 1-2) ------------------
    frame_no = -1
    while frame_no < 4:
        step()
        if mem.bank == 0 and mpu.pc == PC_START:
            frame_no += 1
            mem.frame = frame_no
            mem.swchb = 0xFE if frame_no in (1, 2) else 0xFF
    if mem.ram[0x0A] == 0xFF:
        print("WARN: still on the title screen after the RESET pulse")

    # The wall model rounds each frame independently (±0.07), so compare
    # line counts as integers — the gate is "same value every frame".
    base = [round(frame(pair=False)[0]) for _ in range(3)]
    pair_lines, designs = [], set()
    for _ in range(3):
        n, seen = frame(pair=True)
        pair_lines.append(round(n))
        designs |= seen

    fails = []
    if len(set(base)) != 1:
        fails.append(f"baseline frame length oscillates: {base}")
    if len(set(pair_lines)) != 1:
        fails.append(f"paired frame length oscillates (timing jitter): {pair_lines}")
    elif pair_lines[0] != base[0] + SWAP_COST_LINES:
        fails.append(f"paired frame {pair_lines[0]} lines, expected baseline "
                     f"{base[0]} + {SWAP_COST_LINES} = "
                     f"{base[0] + SWAP_COST_LINES} — the mid-band swap's "
                     "documented cost")
    real = {d for d in designs if d < 0x80}     # a design offset, not stale RAM
    if OBJ_MINER not in real:
        fails.append("the miner's design never reached GRP1 inside the kernel "
                     f"(designs seen: {sorted(hex(d) for d in real)})")
    if len(real) < 2:
        fails.append("only ONE design reached GRP1 inside the kernel in a "
                     f"paired frame ({sorted(hex(d) for d in real)}) — the two "
                     "objects still rotate (the flicker the swap removes)")

    if fails:
        print(f"FAIL: {len(fails)}")
        for f in fails:
            print("  " + f)
        return 1
    print(f"test_slot1_midband: OK ({base[0]} -> {pair_lines[0]} lines, both "
          f"designs in one frame: {sorted(hex(d) for d in real)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
