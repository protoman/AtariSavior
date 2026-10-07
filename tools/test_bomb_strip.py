#!/usr/bin/env python3
"""Bomb-vs-strip blast (user 2026-10-04: 'blasting the strip must work').

Three halves of the fix, driven against the real routines:

1. bank1 BombMarkWalls: with LineCount packed (strip at right_col 2 ->
   pL=24), a bomb whose ±2-col blast covers the strip sets
   EnemyDeadMask b3 and returns count+1 (+75 via the caller). Frames:
   BMW computes blast cols in LEFT-half space (bomb col mirrored), the
   strip pL is RIGHT-half space — StripBlastCheck mirrors the window
   in-body (39-x). Controls: sym run, non-overlapping bomb, no double
   count on a second blast.

2. bank2 M1StripBlast (Phase 4 M1 twin): the left strip's dcols [2ℓ,
   2ℓ+1] share the window's LEFT-half frame — a LEFT-side bomb covering
   them sets EnemyDeadMask b4 (+1 count) via the $F9AC shared pad
   (bank1→bank2 `sta $1FF8`, byte-identical both banks); a RIGHT-side
   bomb's window is mirror-space so the original screen col (RectCount,
   BMW prologue stash) >= 20 skips the test; M1X=0 meta and a pre-set
   b4 are no-ops. Pad identity + both crossing literals are asserted.

3. bank2 StageBandTab: b3 (ball strip dead) blanks BandTab; b4 (M1
   dead) stages M1X=0 and clears the packed b3 presence flag. Expectations
   are DERIVED from the model meta in bank2.bin (BallX/Band0-2/M1X) so
   they track models.json edits.

Both deaths are room-scoped: EnterRoom zeroes EnemyDeadMask.

Run: /home/iuri/python3/bin/python3 tools/test_bomb_strip.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

from test_cell_map import Mem as Mem02, RTS_SENTINEL, parse_labels  # noqa: E402

BANKS = [bytearray(open(SRC / f"bank{i}.bin", "rb").read()) for i in range(4)]


class Mem1:
    """Bank-aware RAM for the bank1 BMW drive (hotspots $1FF6-$1FF9)."""

    def __init__(self):
        self.ram = bytearray(128)
        self.bank = 1

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0284:
            return 0
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return 0
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


def parse_equ(path: Path, names: set) -> dict:
    """bank2.lst EQU lines: `addr  bytes  Name = $vv` (no U prefix)."""
    out = {}
    rx = re.compile(r"^\s*\d+\s+U?[0-9a-f]{4}\s+(?:[0-9a-f]{2}\s+)+"
                    r"([A-Za-z_][A-Za-z0-9_]*)\s+=\s+\$([0-9a-fA-F]+)")
    for line in path.read_text(errors="replace").splitlines():
        m = rx.match(line)
        if m and m.group(1) in names and m.group(1) not in out:
            out[m.group(1)] = int(m.group(2), 16)
    return out


L1 = parse_labels(SRC / "bank1.lst", {"BombMarkWalls", "StripBlastCheck",
                                      "M1ToBank2", "M1ToBank1"})
L0 = parse_labels(SRC / "bank0.lst", {"BombX", "LineCount", "RcBase",
                                "EnemyDeadMask", "CollisionX"})
L2 = parse_labels(SRC / "bank2.lst", {"StageBandTab", "M0TilePF0",
                                      "M3TilePF0", "M1StripBlast"})
L2.update(parse_equ(SRC / "bank2.lst",
                    {"BandTab", "CollisionEndY", "CollisionEndX",
                     "RoomPF0Lo"}))
need = ({"BombMarkWalls", "StripBlastCheck", "M1ToBank2", "M1ToBank1"}
        - L1.keys()) | \
       ({"BombX", "LineCount", "RcBase", "EnemyDeadMask", "CollisionX"}
        - L0.keys()) | \
       ({"StageBandTab", "M0TilePF0", "M3TilePF0", "M1StripBlast",
         "BandTab", "CollisionEndY", "CollisionEndX",
         "RoomPF0Lo"} - L2.keys())
if need:
    sys.exit(f"labels missing: {sorted(need)}")

# Shared cross-bank pad: bank1 .BMWDone jumps here; the 12 bytes must be
# IDENTICAL in both banks (after `sta $1FFx` the next opcode fetch comes
# from the newly selected bank at pc+3 — F6 pad rule).
PAD = 0xF9AC
PAD_BYTES = bytes.fromhex("8df81f4c70f9"    # sta $1FF8 / jmp $F970 (→bank2)
                          "8df71f4c37f9")   # sta $1FF7 / jmp $F937 (→bank1)
for i in (1, 2):
    got = bytes(BANKS[i][PAD - 0xF000:PAD + 12 - 0xF000])
    assert got == PAD_BYTES, (
        f"bank{i} pad @${PAD:04X} = {got.hex()} != {PAD_BYTES.hex()}")
assert L1["M1ToBank2"] == PAD and L1["M1ToBank1"] == PAD + 6, (
    f"bank1 pad labels {L1['M1ToBank2']:04X}/{L1['M1ToBank1']:04X} != "
    f"{PAD:04X}/{PAD + 6:04X}")
assert L1["StripBlastCheck"] == 0xF937, (
    f"StripBlastCheck ${L1['StripBlastCheck']:04X} != $F937 (pin drift)")
assert L2["M1StripBlast"] == 0xF970, (
    f"M1StripBlast ${L2['M1StripBlast']:04X} != $F970 (pin drift)")

# Model 0 meta (bank2 ROM): BallX+10, Band0-2+11..13, M1X+14 — expectations
# below are derived from these so the test tracks models.json edits.
M0 = L2["M0TilePF0"]
_M0OFF = M0 - 0xF000
BALLX = BANKS[2][_M0OFF + 10]
BANDS = tuple(BANKS[2][_M0OFF + 11 + i] for i in range(3))
BAND_MASK = sum(1 << i for i, b in enumerate(BANDS) if b & 0x80)
M1X = BANKS[2][_M0OFF + 14]


def run_bmw(mem: Mem1, bomb_x: int, line_count: int,
            meta: int = None) -> int:
    """Drive BombMarkWalls; return the count A (walls newly broken).

    meta = TilePF0 address staged into RoomPF0Lo (M1X read target);
    defaults to model 0."""
    r = mem.ram
    meta = M0 if meta is None else meta
    r[L2["RoomPF0Lo"] - 0x80] = meta & 0xFF
    r[L2["RoomPF0Lo"] + 1 - 0x80] = meta >> 8
    r[L0["BombX"] - 0x80] = bomb_x
    r[L0["LineCount"] - 0x80] = line_count
    r[L0["RcBase"] - 0x80] = 0           # no rects: strip check only
    r[L0["EnemyDeadMask"] - 0x80] = 0
    mem.bank = 1
    mpu = MPU(memory=mem)
    mpu.pc = L1["BombMarkWalls"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return mpu.a
    sys.exit(f"BMW(bombX={bomb_x}) never returned "
             f"(pc=${mpu.pc:04X}, bank={mem.bank})")


def stage(deadmask: int) -> tuple[tuple, int, int]:
    """Drive StageBandTab; return (BandTab0..2, packed byte, staged M1X)."""
    mem = Mem02()
    r = mem.ram
    r[L2["RoomPF0Lo"] - 0x80] = M0 & 0xFF
    r[(L2["RoomPF0Lo"] + 1) - 0x80] = M0 >> 8
    r[L0["EnemyDeadMask"] - 0x80] = deadmask
    mem.bank = 2
    mpu = MPU(memory=mem)
    mpu.pc = L2["StageBandTab"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            bands = (r[L2["BandTab"] - 0x80], r[L2["BandTab"] + 1 - 0x80],
                     r[L2["BandTab"] + 2 - 0x80])
            packed = r[L2["CollisionEndY"] - 0x80]
            m1x = r[L2["CollisionEndX"] - 0x80]
            return bands, packed, m1x
    sys.exit("StageBandTab never returned")


def main() -> int:
    # packed: right_col 2 -> n=3 -> pL=24; all bands active (mask 7)
    packed = (2 + 1) << 4 | 0x07

    # 1. bomb at display col 25 (BombX=107 -> vl=100 -> col25 -> mirrored
    #    left-col 14 -> blast [12,16] covers the strip's mirror {14,15}).
    #    RIGHT-side bomb (orig col 25 >= 20) → M1StripBlast skips, so the
    #    count stays 1 and only b3 is set.
    mem = Mem1()
    got = run_bmw(mem, 107, packed)
    mask = mem.ram[L0["EnemyDeadMask"] - 0x80]
    assert got == 1 and mask & 0x08 and not mask & 0x10, (
        f"strip blast must break (count={got}, deadmask=${mask:02X})")

    # 2. no double count: bit already set
    def rerun_preserve(bomb_x, line_count, deadmask_pre):
        r = mem.ram
        r[L0["EnemyDeadMask"] - 0x80] = deadmask_pre
        r[L0["BombX"] - 0x80] = bomb_x
        r[L0["LineCount"] - 0x80] = line_count
        r[L0["RcBase"] - 0x80] = 0
        mem.bank = 1
        mpu = MPU(memory=mem)
        mpu.pc = L1["BombMarkWalls"]
        mpu.a = mpu.x = mpu.y = 0
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(5000):
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                return mpu.a
        sys.exit("BMW rerun never returned")

    got2 = rerun_preserve(107, packed, 0x08)
    assert got2 == 0, f"second blast must not count (got {got2})"

    # 3. no ball strip packed: right-side bomb → M1 side gate skips too
    mems = Mem1()
    got3 = run_bmw(mems, 107, 0)
    assert got3 == 0 and not mems.ram[L0["EnemyDeadMask"] - 0x80], (
        f"right-bomb control must not break the M1 strip (count={got3})")

    # 4. bomb far from the strip (col 10 -> blast [8,12]; strip mirror
    #    {14,15} untouched)
    memf = Mem1()
    got4 = run_bmw(memf, 40, packed)
    assert got4 == 0 and not memf.ram[L0["EnemyDeadMask"] - 0x80], (
        f"far bomb must not break the strip (count={got4})")

    # --- M1 (left) strip: BombX=71 -> vl=64 -> screen col 16 (<20 = left)
    #     -> blast [14,18] covers the strip's dcols {16,17} (ℓ=8, M1X=71) --
    if M1X != 71:
        sys.exit(f"model 0 M1X=${M1X:02X} != $47 (ℓ=8) — fixture stale")
    memb = Mem1()
    got5 = run_bmw(memb, 71, 0)
    mask5 = memb.ram[L0["EnemyDeadMask"] - 0x80]
    assert got5 == 1 and mask5 & 0x10, (
        f"left bomb must break the M1 strip (count={got5}, "
        f"deadmask=${mask5:02X})")
    # no double count on the M1 bit either
    r = memb.ram
    r[L0["BombX"] - 0x80] = 71
    r[L0["LineCount"] - 0x80] = 0
    memb.bank = 1
    mpu = MPU(memory=memb)
    mpu.pc = L1["BombMarkWalls"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    memb[0x1FF] = 0x01
    memb[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            break
    assert mpu.a == 0, f"second M1 blast must not count (got {mpu.a})"

    # left bomb far from the strip (col 11 -> blast [9,13] < 16)
    meml = Mem1()
    got6 = run_bmw(meml, 51, 0)
    assert got6 == 0 and not meml.ram[L0["EnemyDeadMask"] - 0x80], (
        f"far left bomb must not break the M1 strip (count={got6})")

    # b4 already set → no double score even under the strip
    memd = Mem1()
    r = memd.ram
    r[L0["EnemyDeadMask"] - 0x80] = 0x10
    r[L2["RoomPF0Lo"] - 0x80] = M0 & 0xFF
    r[L2["RoomPF0Lo"] + 1 - 0x80] = M0 >> 8
    r[L0["BombX"] - 0x80] = 71
    r[L0["LineCount"] - 0x80] = 0
    r[L0["RcBase"] - 0x80] = 0
    memd.bank = 1
    mpu = MPU(memory=memd)
    mpu.pc = L1["BombMarkWalls"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    memd[0x1FF] = 0x01
    memd[0x1FE] = 0x00
    for _ in range(5000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            break
    assert mpu.a == 0, f"pre-set b4 must not count again (got {mpu.a})"

    # meta with M1X=0 (model 3, ball-only): left bomb → no M1 effect
    memz = Mem1()
    gotz = run_bmw(memz, 71, 0, meta=L2["M3TilePF0"])
    assert gotz == 0 and not memz.ram[L0["EnemyDeadMask"] - 0x80], (
        f"M1X=0 meta must skip the M1 test (count={gotz})")

    # --- staging: expectations derived from model 0's meta ---------------
    # 5. ball strip dead (b3) → BandTab blanked
    bands, pack_b, m1_b = stage(0x08)
    assert bands == (0, 0, 0), f"dead ball strip stages blank ({bands})"

    # 6. alive → model's own bands + ball band mask + M1 presence flag
    bands, pack_b, m1_b = stage(0x00)
    assert bands == BANDS, f"live bands {bands} != meta {BANDS}"
    assert pack_b & 0x07 == BAND_MASK, (
        f"packed ball mask ${pack_b & 7:02X} != meta ${BAND_MASK:02X}")
    assert bool(pack_b & 0x08) == bool(M1X), (
        f"packed b3={pack_b & 0x08:02X} != M1X ${M1X:02X} presence")
    assert m1_b == M1X, f"staged M1X ${m1_b:02X} != meta ${M1X:02X}"

    # 7. M1 strip dead (b4) → M1X stages 0, packed b3 clears (ball intact)
    bands, pack_b, m1_b = stage(0x10)
    assert m1_b == 0, f"dead M1 strip must stage M1X=0 (got ${m1_b:02X})"
    assert not pack_b & 0x08, (
        f"dead M1 strip must clear packed b3 (packed=${pack_b:02X})")
    assert bands == BANDS and pack_b & 0x07 == BAND_MASK, (
        f"b4 must not touch the ball strip (bands={bands}, "
        f"mask=${pack_b & 7:02X})")

    print("test_bomb_strip: OK (ball+M1 blast hit/controls, no double "
          "count, staging alive/dead, pad identity)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
