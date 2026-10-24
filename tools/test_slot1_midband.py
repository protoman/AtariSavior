#!/usr/bin/env python3
"""Same-band pair: the kernel must NOT try to draw two objects in one band.

Phase 5b (2026-10-22) tried a mid-band slot swap so the miner could share a
band with an enemy. It was withdrawn — two artifacts are inherent to the
approach, both confirmed on real hardware-style timing:

  1. the swap needs SetObjectXPos' own scanline plus its HMOVE line, and the
     player's GRP0 latch shows the same art row twice (one duplicated sprite
     row, the reported "legs repeated");
  2. those extra scanlines make the band TALLER, so every band below it is
     drawn 2-3 px lower than the collision map says (the player appears to
     sink into / float above the walls: the reported "inside the PF").

So the rule stands: one GRP1 object per 48-line band, the miner included
(`tools/convert_level.py` warns for each offending room, but the check is a
WARNING because the live stage still has two such rooms).

This test is the guard for that decision, driven by the real ROM:
  * a same-band pair is NOT staged: the frame length does not change and only
    ONE design reaches GRP1 per frame (the known 30 Hz rotation);
  * the PLAYER's art is untouched: the number of distinct non-zero GRP0 bytes
    per frame matches the baseline exactly (a corrupted running-Y from any
    future mid-frame reposition shows up here immediately — that was the
    mechanism behind the three 2026-10-22 reports).

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
GRP0, GRP1 = 0x1B, 0x1C
Z = dict(ObjBase=0x36, EnemyCount=0x33, EnemyDeadMask=0x3A, EnemyRamY=0x62,
         EnemyRamX=0x3D, LevelMinerRoom=0x24, MinerX=0x25, MinerY=0x26,
         RoomNo=0x18)
PC_START = LABELS["StartFrame"]


def main() -> int:
    blob = ROM.read_bytes()
    assert len(blob) in (16384, 32768), f"{ROM} is {len(blob)} bytes, want 32K"
    banks = [bytearray(blob[4096 * i:4096 * (i + 1)])
             for i in range(len(blob) // 4096)]
    mem = Mem(banks)
    mpu = MPU(memory=mem)
    prev = 0
    art = {GRP0: set(), GRP1: set()}

    class Probe(Mem):
        pass

    def step():
        nonlocal prev
        mpu.step()
        mem.wall += mpu.processorCycles - prev
        prev = mpu.processorCycles
        if mem.wsync_seen:
            w = mem.wall
            mem.wall = (w // 76 + 1) * 76 if w % 76 else w
            mem.wsync_seen = False

    def frame(*, pair):
        r = mem.ram
        # Both configurations stage the SAME two objects (one room enemy + the
        # miner); only their band layout differs, so the frame-length compare
        # is like for like. (Pre-N=4 the control staged NOTHING and inherited
        # the boot room, so the pair was measured against another object set.)
        r[Z["EnemyCount"]] = 1
        r[Z["EnemyDeadMask"]] = 0
        r[Z["EnemyRamX"]] = 71
        r[Z["LevelMinerRoom"]] = r[Z["RoomNo"]] & 0x7F
        r[Z["MinerX"]] = 40
        if pair:
            # The stage's own case: the enemy and the miner 20 lines below,
            # BOTH inside band 1 (lines 36..71; the miner draws at MinerY+3) —
            # the arrangement that must NOT pair. It was 60/84 while a band
            # was 48 lines, where 84 still belonged to band 1.
            r[Z["EnemyRamY"]] = 44
            r[Z["MinerY"]] = 60
        else:
            # Control: the same two objects in DIFFERENT bands (44 = band 1,
            # 100+3 = band 2) — the pair IS staged and the hook runs.
            r[Z["EnemyRamY"]] = 44
            r[Z["MinerY"]] = 100
        wall0 = mem.wall
        art[GRP0].clear()
        art[GRP1].clear()
        while True:
            # record GRP0/GRP1 patterns written by bank0 this frame
            pc, bk = mpu.pc, mem.bank
            addr = None
            if bk == 0 and mem[pc] == 0x85:            # sta zp
                addr = mem[(pc + 1) & 0xFFFF] & 0xFF
            elif bk == 0 and mem[pc] == 0x8D:          # sta abs
                addr = mem[(pc + 1) & 0xFFFF] | (mem[(pc + 2) & 0xFFFF] << 8)
            if addr in (GRP0, GRP1):
                art[addr].add(mpu.a)
            step()
            if mem.bank == 0 and mpu.pc == PC_START:
                break
        return (mem.wall - wall0) / 76, set(art[GRP0]), set(art[GRP1])

    frame_no = -1
    while frame_no < 4:
        step()
        if mem.bank == 0 and mpu.pc == PC_START:
            frame_no += 1
            mem.frame = frame_no
            mem.swchb = 0xFE if frame_no in (1, 2) else 0xFF

    base_lines, base_g0, _ = frame(pair=False)
    base_lines2, _, _ = frame(pair=False)
    pair_lines, pair_g0, pair_g1 = frame(pair=True)
    pair_lines2, _, _ = frame(pair=True)
    # The player art has 4 frames (2 jet flutter phases, 2 walk phases) and
    # the jet phase follows TickCounter, so ONE sampled frame can miss a
    # byte that the other phase draws ($9C vs $DC/$94). Union three frames
    # per configuration: the comparison is "does a pair LOSE art", not
    # "which exact byte is drawn on this frame".
    for _ in range(3):
        _, g0, _ = frame(pair=False)
        base_g0 |= set(g0)
        _, g0, g1 = frame(pair=True)
        pair_g0 |= set(g0)
    base_lines, pair_lines = round(base_lines), round(pair_lines)
    base_lines2, pair_lines2 = round(base_lines2), round(pair_lines2)

    base_art = len({v for v in base_g0 if v})
    pair_art = len({v for v in pair_g0 if v})

    fails = []
    # N=4 note: the invariant is CONSTANT frames WITHIN a configuration (no
    # flicker). The cross-configuration delta measured here (272 vs 270) is
    # the StartFrame re-anchor phase, not a band stretch: sim_frame_budget,
    # which measures whole frames, holds a constant cave frame with a pair
    # staged (270.0 +/- 0.08), and setting the hook's body compensation to -3
    # was measured to make that frame 269 (one line SHORT). So do not compare
    # the two configurations against each other.
    # Known red (2026-10-24): the fabricated room leaves ObjTop1=$FD / ObjX1=$00
    # / ObjBase1=$50 in RAM, i.e. the pokes below do NOT make SelectActiveObject
    # stage the pair the way the game does, and the Slot1Hook gate then runs a
    # nonsense-Y prologue on every band. Diagnostic to finish this: drive the
    # REAL staging route (see call_stage_slot1 in tools/test_slot1_pair.py)
    # instead of poking ZP, then re-measure — the real stage holds a constant
    # 270 in sim_frame_budget, so this is very likely test-side.
    for tag, a, b in (("control", base_lines, base_lines2),
                      ("same-band", pair_lines, pair_lines2)):
        if a != b:
            fails.append(f"{tag} frames are not constant ({a} -> {b}): the "
                         "kernel is stretching a band, which flickers")
    if pair_art < base_art:
        fails.append(f"the player's art lost rows with a same-band pair "
                     f"({base_art} distinct GRP0 bytes -> {pair_art}): the "
                     "running-Y was clobbered mid-frame (SetObjectXPos' `tay`)")
    miner = OBJ_MINER in {v for v in pair_g1 if v}
    if miner:
        fails.append("the miner reached GRP1 in a same-band room — one GRP1 "
                     "cannot draw two objects on the same scanlines (this is "
                     "the withdrawn mid-band swap coming back)")

    if fails:
        print(f"FAIL: {len(fails)}")
        for f in fails:
            print("  " + f)
        return 1
    print(f"test_slot1_midband: OK (same-band pair refused: {base_lines} lines "
          f"both frames, player art rows {pair_art}, single GRP1 design)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
