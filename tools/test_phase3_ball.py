#!/usr/bin/env python3
"""Phase 3 CHECK probe (py65): asymmetric ball path with every model's
packed meta poked directly in the ROM image (MetaA = band mask $07,
MetaB = 2 -> staged BallX = 8*2+79 = 95) — the poke simulates
resolve_asym_patches output so the probe does not depend on
models.json having asymmetric content yet.

Assertions (frames >= 2, after the RESET-pulse title -> game start):
  * bank0 ENABL ($1f) writes are only $00 or $ff;
  * >= 3 bank0 $ff ENABL writes per frame (one per band gate: row0/1/2);
  * >= 1 bank0 RESPBL ($14) AND >= 1 HMBL ($24) write per frame — proves
    bank2 StageBandTab staged a non-zero BallX into Temp and the VBL ball
    block ran SetObjectXPos selector 4 (the Phase 3 staging path);
  * Temp ($88) at every bank0 RESPBL write == 95 (8*2+79) — pins the
    staged-BallX constant to the calibrated arg / PHMOverlay math;
  * frame line count constant across frames >= 3 and in {266, 267} (the
    asym VBL growth must not add a scanline; 265 = 262 NTSC + 3 since the
    2026-10-11 VSYNC re-anchor fix for bugs.md #29 Class C);
  * min SP (frames >= 2) >= $F7 (documented whole-run stack guard).

Second run (partial mask, case-1 stacked blocks): MetaA band-mask bit1
cleared (mask $05) while bits0/2 stay set -> the per-band gate must emit
exactly 2 ENABL $ff-writes per frame (band1 skipped).

Run: /home/iuri/python3/bin/python3 tools/test_phase3_ball.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import py65.devices.mpu6502 as m

from test_phase2_ball import Mem, LABELS
import frozen_rom  # noqa: E402

SRC = Path(__file__).resolve().parent.parent / "src"
FROZEN = SRC / "tests" / "frozen"   # test-owned banks+labels
FRAMES = 60
META_B_POKE = 2                   # ball_col+1 -> staged BallX = 8*2+79 = 95
                                  # (calibrated SetObjectXPos arg; must equal
                                  # PHMOverlay's independent 8n+79 math — a
                                  # #86 constant drew the stripe one cell
                                  # right of its collision, 2026-10-12)
ENABL, RESBL, HMBL = 0x1F, 0x14, 0x24

PC_START = LABELS["StartFrame"]

# C5 (2026-10-20): the boot room (level 1 room 0, model 0) is ASYNC, so its
# MetaA/MetaB live in level 1's AsyncExtras record — ordinal 1, so the pair
# sits at LEVEL1_AsyncExtras+1/+2 (header = flags, MetaA, MetaB).
_pat = re.compile(r"^\s*\d+\s+([0-9a-f]{4})\s+LEVEL1_AsyncExtras\s*$")
EXTRAS = None
for _l in (FROZEN / "bank3.lst").read_text(errors="replace").splitlines():
    _m = _pat.match(_l)
    if _m:
        EXTRAS = int(_m.group(1), 16)
        break
if EXTRAS is None:
    sys.exit("LEVEL1_AsyncExtras label not found in bank3.lst")


def run(rom: Path, band1: int = 0xFF) -> dict:
    blob = rom.read_bytes()
    assert len(blob) == 16384, f"{rom} is {len(blob)} bytes, want 16K"
    banks = [bytearray(blob[4096 * i:4096 * (i + 1)]) for i in range(4)]
    # MetaA band mask: band1 parameterized for the partial-mask run
    mask = 0x07 if band1 else 0x05
    banks[3][(EXTRAS + 1) & 0xFFF] = mask          # MetaA
    banks[3][(EXTRAS + 2) & 0xFFF] = META_B_POKE   # MetaB (ball col)
    # C5: the loader ALSO derives the band gates from the SIDE-0 patch bytes
    # (row b7-6 | side b4 | col b3-0) and ORs them into MetaA, so the patch
    # rows must agree with the poked mask (row 0 + row 1 for the full run,
    # rows 0 + 2 for the band-1-partial run).
    prow = (0, 1) if band1 else (0, 2)
    banks[3][(EXTRAS + 3) & 0xFFF] = prow[0] << 6
    banks[3][(EXTRAS + 4) & 0xFFF] = prow[1] << 6
    respbl_temp = []

    class ProbeMem(Mem):
        def __setitem__(self, a, v):
            if (a & 0xFFFF) == RESBL and self.bank == 0:
                respbl_temp.append((self.frame, self.ram[0x08]))
            super().__setitem__(a, v)

    mem = ProbeMem(banks)
    mpu = m.MPU(memory=mem)
    prev = 0
    per_frame = {}
    min_sp = 0xFF

    def step():
        nonlocal prev
        mpu.step()
        c = mpu.processorCycles - prev
        prev = mpu.processorCycles
        mem.wall += c
        if mem.wsync_seen:
            w = mem.wall
            mem.wall = (w // 76 + 1) * 76 if w % 76 else w
            mem.wsync_seen = False
            return True
        return False

    frame = -1
    steps = 0
    prev_wall = 0
    while frame < FRAMES:
        hit = step()
        steps += 1
        if steps > 6_000_000:
            sys.exit(f"{rom.name}: runaway (frame {frame})")
        if hit and frame >= 2 and mpu.sp < min_sp:
            min_sp = mpu.sp
        pc, bk = mpu.pc, mem.bank
        if bk == 0 and pc == PC_START:
            if frame >= 0:
                # wall-model frame lines (76c lines): scanlines where the
                # poll loops burn cycles without a WSYNC write still count
                # as TV lines — count wall delta, not WSYNC events.
                per_frame[frame] = round((mem.wall - prev_wall) / 76)
            prev_wall = mem.wall
            frame += 1
            mem.frame = frame
            mem.swchb = 0xFE if frame in (1, 2) else 0xFF

    enabl = [(f, v) for f, b, a, v in mem.log
             if f >= 2 and b == 0 and a == ENABL]
    respbl = {f for f, b, a, v in mem.log
              if f >= 2 and b == 0 and a == RESBL}
    hmbll = {f for f, b, a, v in mem.log if f >= 2 and b == 0 and a == HMBL}
    ff_per_frame = {}
    for f, v in enabl:
        if v == 0xFF:
            ff_per_frame[f] = ff_per_frame.get(f, 0) + 1
    return dict(
        enabl_vals=sorted({v for _, v in enabl}),
        ff_per_frame=ff_per_frame,
        respbl=respbl,
        hmbll=hmbll,
        respbl_temp=respbl_temp,
        per_frame=per_frame,
        min_sp=min_sp,
        frames=frame,
    )


def main() -> int:
    r = run(frozen_rom.path())
    fails = []

    bad = [f"${v:02X}" for v in r["enabl_vals"] if v not in (0x00, 0xFF)]
    if bad:
        fails.append(f"bank0 ENABL values outside {{00,ff}}: {bad}")
    if 0xFF not in r["enabl_vals"]:
        fails.append("no bank0 ENABL $ff writes (band gate never fired)")

    gate_frames = sorted(f for f, n in r["ff_per_frame"].items() if f >= 3)
    weak = [f for f in gate_frames if r["ff_per_frame"][f] < 3]
    if weak:
        fails.append(f"frames with <3 ENABL $ff writes: {weak[:6]}")

    no_resp = [f for f in range(3, r["frames"]) if f not in r["respbl"]]
    no_hmb = [f for f in range(3, r["frames"]) if f not in r["hmbll"]]
    if no_resp:
        fails.append(f"frames without bank0 RESPBL (ball block): {no_resp[:6]}")
    if no_hmb:
        fails.append(f"frames without bank0 HMBL: {no_hmb[:6]}")

    # staged-BallX constant: Temp at the RESPBL write must be the
    # calibrated arg 8*MetaB+79 (MetaB poke = 2 -> 95). Catches the
    # #86 regression that drew the stripe one cell right of collision.
    want_temp = 8 * META_B_POKE + 79
    bad_temp = sorted({t for f, t in r["respbl_temp"]
                       if f >= 2 and t != want_temp})
    if bad_temp:
        fails.append(
            f"Temp at bank0 RESPBL = "
            f"{[f'${t:02X}' for t in bad_temp]}, want ${want_temp:02X}")

    lens = sorted({r["per_frame"].get(f) for f in range(3, r["frames"])})
    if len(lens) != 1 or lens[0] not in (266, 267):
        fails.append(f"frame line counts (f>=3) = {lens}, want one of [266,267]")

    if r["min_sp"] < 0xF7:
        fails.append(f"min SP (f>=2) = ${r['min_sp']:02X}, want >= $F7")

    # partial mask (case-1 stacked blocks: bands 0+2 painted, band1 mirror):
    # the band gate must skip band1 -> exactly 2 ENABL $ff writes per frame.
    if not fails:
        rp = run(frozen_rom.path(), band1=0x00)
        weak2 = [f for f in range(3, rp["frames"])
                 if rp["ff_per_frame"].get(f, 0) != 2]
        if weak2:
            got = sorted({rp["ff_per_frame"].get(f, 0) for f in weak2})
            fails.append(
                f"partial mask band1=0: frames with !=2 ENABL $ff writes "
                f"{weak2[:6]} (counts {got})")

    if fails:
        for f in fails:
            print(f"FAIL: {f}")
        return 1
    print(f"test_phase3_ball: OK ({r['frames']} frames, "
          f"lines={lens[0]}, ENABL {{00,ff}} with >=3 ff/frame, "
          f"partial mask band1=0 -> 2 ff/frame, "
          f"RESPBL+HMBL every frame (Temp=${want_temp:02X} at RESPBL), "
          f"min SP ${r['min_sp']:02X}, "
          f"poked extras meta + patch rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
