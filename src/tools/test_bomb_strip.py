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

2. bank1 M1StripBlast (Phase 4 M1 twin, moved from bank2 2026-10-20): the
   left strip's dcols [2ℓ, 2ℓ+1] share the window's LEFT-half frame — a
   LEFT-side bomb covering them sets EnemyDeadMask b4 (+1 count); a
   RIGHT-side bomb's window is mirror-space so the original screen col
   (RectCount, BMW prologue stash) >= 20 skips the test; M1X=0 meta and a
   pre-set b4 are no-ops. The whole chain .BMWDone -> M1StripBlast ->
   StripBlastCheck is same-bank (the $F9AC hop pad is gone).

3. bank2 StageBandTab: b3 (ball strip dead) blanks BandTab; b4 (M1
   dead) stages M1X=0 and clears the packed b3 presence flag. Expectations
   are DERIVED from the model meta in bank2.bin (MetaA/MetaB packed) so
   they track models.json edits.

Both deaths are room-scoped: EnterRoom zeroes EnemyDeadMask.

Run: /home/iuri/python3/bin/python3 tools/test_bomb_strip.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "tests" / "frozen"
SRC = ROOT
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

from test_cell_map import Mem as Mem02, RTS_SENTINEL, parse_labels  # noqa: E402

BANKS = [bytearray(open(FROZEN / f"bank{i}.bin", "rb").read()) for i in range(8)]


class Mem1:
    """Bank-aware RAM for the bank1 BMW drive (hotspots $1FF4-$1FF7)."""

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
        if 0x1FF4 <= a <= 0x1FFB:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return 0
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


L1 = parse_labels(FROZEN / "bank1.lst", {"BombMarkWalls", "StripBlastCheck",
                                      "M1StripBlast"})
L0 = parse_labels(FROZEN / "bank0.lst", {"BombX", "LineCount",
                                "EnemyDeadMask", "CollisionX",
                                "BombPacked", "PF0Buf", "PF1Buf",
                                "PF2Buf"})
L2 = {}
# C7 (2026-10-20): the stage/band walker and the shape blocks + extras
# streams live in bank3 again; bank2 keeps the room/enemy tables.
L3 = parse_labels(FROZEN / "bank3.lst", {"B3StageBand", "M0Rows",
                                      "M3Rows", "LEVEL1_AsyncExtras"})
L2.update({k: L3[k] for k in ("M0Rows", "M3Rows",
                              "LEVEL1_AsyncExtras")})
L2.update(parse_equ(FROZEN / "bank2.lst",
                    {"BandTab", "CollisionEndY", "CollisionEndX",
                     "RoomPF0Lo", "RoomRectsLo"}))
need = ({"BombMarkWalls", "StripBlastCheck", "M1StripBlast"} - L1.keys()) | \
       ({"BombX", "LineCount", "EnemyDeadMask", "CollisionX",
         "BombPacked", "PF0Buf", "PF1Buf", "PF2Buf"}
        - L0.keys()) | \
       ({"M0Rows", "M3Rows", "LEVEL1_AsyncExtras",
         "BandTab", "CollisionEndY", "CollisionEndX",
         "RoomPF0Lo", "RoomRectsLo"} - L2.keys()) | ({"B3StageBand"} - L3.keys())
if need:
    sys.exit(f"labels missing: {sorted(need)}")

# Repack chunk 2 (2026-10-20): M1StripBlast lives in bank1 ($F41F fill) and
# the .BMWDone -> M1StripBlast -> StripBlastCheck chain is same-bank, so the
# old 12 B hop pad at $F9AC and bank2's copy of the body must be gone.
# Audit round 2 (2026-10-20): the $F937 / $F9AC pins are deleted too — the
# body is reached by label, so it floats. Pin the INVARIANTS instead of an
# absolute: chain order, the $F41F placement, and "no hand-coded $F937/$F9AC
# literal survives in any bank" (a stale absolute is what the old pin kept).
assert "M1StripBlast" not in L2, "bank2 must not carry M1StripBlast any more"
assert L1["M1StripBlast"] == 0xF41F, (
    f"M1StripBlast ${L1['M1StripBlast']:04X} != $F41F (placement drift)")
assert L1["M1StripBlast"] < L1["StripBlastCheck"], "strip chain out of order"
# StripBlastCheck floats in bank1's $F8C6-$F9AB gap (raft twin -> sound leaves)
assert 0xF8C6 <= L1["StripBlastCheck"] < 0xF9AC, (
    f"StripBlastCheck ${L1['StripBlastCheck']:04X} outside the $F8C6-$F9AB gap")
for _f in ("kernel.asm", "bank1.asm", "bank2.asm", "bank3.asm"):
    _t = (SRC / _f).read_text(errors="replace")
    # comments may mention the retired pins; only CODE operands break:
    for _n, _line in enumerate(_t.splitlines(), 1):
        _code = _line.split(";")[0]
        assert "$F937" not in _code and "$F9AC" not in _code, (
            f"{_f}:{_n}: stale strip address literal in code: {_line.strip()}")

# Model 0 (level 1 room 0) meta — C5 (2026-10-20): the pair left the shape
# block and lives in the level's async-extras record (ordinal 1 -> +1/+2, the
# record's header is flags, MetaA, MetaB). Expectations below are derived from
# the ROM bytes so the test tracks models.json edits (bugs.md 28 point 1).
M0 = L2["M0Rows"]
_EXOFF = L2["LEVEL1_AsyncExtras"] - 0xF000
# C7 (2026-10-20): the extras records live in BANK3 (the shape half), so the
# bytes come from that image.
META_A = BANKS[3][_EXOFF + 1]
META_B = BANKS[3][_EXOFF + 2]
BALLX = 8 * META_B + 86 if META_B else 0    # 87+8*ball_col
BANDS = tuple(0xFF if META_A & (1 << i) else 0 for i in range(3))
BAND_MASK = META_A & 0x07
_m1n = META_A >> 4
M1X = 8 * _m1n - 1 if _m1n else 0           # 7+8*m1_col


def run_bmw(mem: Mem1, bomb_x: int, line_count: int,
            meta_pair: tuple = None, rects=None, bomb_packed: int = 0) -> int:
    """Drive BombMarkWalls; return the count A (walls newly broken).

    meta_pair = (MetaA, MetaB) staged into RoomMetaA/B (C5: the loader reads
    them from the room extras, so tests pass the pair explicitly); defaults to
    model 0's extras pair. rects = list of (x, y, w, h) — INERT since plan
    5.1b (no rect cache); bomb_packed seeds BombPacked (state bits only —
    WallMask b3-6 retired)."""
    r = mem.ram
    _ma, _mb = (META_A, META_B) if meta_pair is None else meta_pair
    r[L2["RoomPF0Lo"] - 0x80] = _ma       # staged room meta
    r[L2["RoomPF0Lo"] + 1 - 0x80] = _mb
    r[L0["BombX"] - 0x80] = bomb_x
    r[L0["LineCount"] - 0x80] = line_count
    r[L0["EnemyDeadMask"] - 0x80] = 0
    r[L0["BombPacked"] - 0x80] = bomb_packed
    rects = rects or []          # plan 5.1b: cache is inert (no reader)
    for i, (x, y, w, h) in enumerate(rects):
        off = 0xCC - 0x80 + 4 * i
        r[off], r[off + 1], r[off + 2], r[off + 3] = x, y, w, h
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


def stage(deadmask: int, metas=None) -> tuple[tuple, int, int]:
    """Drive B3StageBand (bank3); return (BandTab0..2, packed byte, staged M1X)."""
    mem = Mem1()
    r = mem.ram
    ma, mb = metas if metas else (META_A, META_B)
    r[L2["RoomPF0Lo"] - 0x80] = ma              # staged meta (room entry)
    r[(L2["RoomPF0Lo"] + 1) - 0x80] = mb
    r[L0["EnemyDeadMask"] - 0x80] = deadmask
    mem.bank = 3            # C7: the band walker lives in bank3
    mpu = MPU(memory=mem)
    mpu.pc = L3["B3StageBand"]
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
    gotz = run_bmw(memz, 71, 0, meta_pair=(0, 0))   # M3: symmetric
    assert gotz == 0 and not memz.ram[L0["EnemyDeadMask"] - 0x80], (
        f"M1X=0 meta must skip the M1 test (count={gotz})")

    # --- staging: expectations derived from model 0's meta ---------------
    # 5. ball strip dead (b3) → BandTab blanked
    bands, pack_b, m1_b = stage(0x08)
    assert bands == (0, 0, 0), f"dead ball strip stages blank ({bands})"
    # 2026-10-25 (user, level 7 room 1): the strip vanished but still blocked.
    # The collision pack (read by PHMOverlay/OvShutBand) was rebuilt from the
    # metas and ignored b3, so the dead strip kept its ball-column nibble and
    # band gates. Only the M1-present flag (b3) may survive a ball-strip kill.
    # The model-0 fixture has no ball column, so use a ball room: band 1 gate
    # (MetaA b1) + ball_col+1 = 3 (MetaB), exactly level 7 room 1's shape.
    _, live, _ = stage(0x00, (0x02, 0x03))
    assert live & 0xF0 == 0x30 and live & 0x02, (
        f"fixture: live ball room must pack col+gate (packed=${live:02X})")
    _, dead, _ = stage(0x08, (0x02, 0x03))
    assert dead & 0xF7 == 0, (
        f"dead ball strip must pack no ball column/gates (packed=${dead:02X}) "
        "- the strip vanished but still blocked (level 7 room 1)")

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

    # --- #7(i): walk covers rect4; PairGone guards its double-score ------
    # left bomb col 11 -> blast [9,13] (far from the strip mirror {14,15},
    # cf. case 6). Thin rect (10,0,2,1) staged at cache idx4 = the slot the
    # old X=3..0 walk never reached. Pair cols 10,11 = PF1 bits $02|$01.
    r5 = [(0, 0, 4, 1), (2, 0, 4, 1), (4, 0, 4, 1), (6, 0, 4, 1),
          (10, 0, 2, 1)]
    memr = Mem1()
    r = memr.ram
    r[L0["PF1Buf"] - 0x80] = 0x03
    # plan 5.1b (2026-10-20): NO rect cache — the punch reads the PF buffers.
    # Cell 5 (cols 10-11) is thin: neighbours (cols 8-9 / 12-13) are clear.
    # The buffer IS the double-score guard (the punch empties the pair), and
    # WallMask (BombPacked b3-6) is retired — it must stay untouched.
    gotr = run_bmw(memr, 51, 0, rects=r5)
    assert gotr == 1, f"thin cell must break (count={gotr})"
    assert not r[L0["PF1Buf"] - 0x80] & 0x03, "punch must clear both cols"
    assert not r[L0["BombPacked"] - 0x80] & 0x78, (
        f"punch must not set WallMask (packed=${r[L0['BombPacked'] - 0x80]:02X})")
    gotr2 = run_bmw(memr, 51, 0, rects=r5)   # pair now clear in PF1Buf
    assert gotr2 == 0, f"re-blast must not count (count={gotr2})"

    # parity (the reason the cache could go): a cell that joins a wider run
    # is a THICK wall — never breakable, exactly like the old w==2 rect test.
    memq = Mem1()
    r = memq.ram
    r[L0["PF1Buf"] - 0x80] = 0x0F    # cols 8-11 solid: cell5 has a neighbour
    gotq = run_bmw(memq, 51, 0)
    assert gotq == 0, f"thick wall must not break (count={gotq})"
    assert r[L0["PF1Buf"] - 0x80] == 0x0F, "thick wall must stay solid"

    # --- P2b doors (key-only, bomb-immune) ------------------------------
    def door_run(meta_a, meta_b, bomb_x, line_count):
        mem = Mem1()
        r = mem.ram
        got = run_bmw(mem, bomb_x, line_count, meta_pair=(meta_a, meta_b))
        return got, r[L0["EnemyDeadMask"] - 0x80]

    # 8a. RIGHT door: MetaB b7 set, same strip geometry as case 1
    #     (ball_col+1=3 → pL=24; bomb 107 → blast covers it) — bomb must
    #     NOT set b3 nor count.
    got, mask = door_run(0x90, 0x83, 107, (2 + 1) << 4 | 0x07)
    assert got == 0 and not mask & 0x08, (
        f"right door must be bomb-immune (count={got}, deadmask=${mask:02X})")
    # 8b. same meta WITHOUT b7 → the old kill still works (control)
    got, mask = door_run(0x90, 0x03, 107, (2 + 1) << 4 | 0x07)
    assert got == 1 and mask & 0x08, (
        f"plain strip control must still die (count={got}, mask=${mask:02X})")

    # 9a. LEFT door: MetaA = m1n9 | band | b3 ($98). M1 dcol = 16; a
    #     left bomb at col 16 (BombX=71 → blast [14,18]) must NOT set b4.
    got, mask = door_run(0x98, 0x00, 71, 0)
    assert got == 0 and not mask & 0x10, (
        f"left door must be bomb-immune (count={got}, deadmask=${mask:02X})")
    # 9b. same MetaA without b3 ($90, model 0's own) → b4 sets (control)
    got, mask = door_run(0x90, 0x00, 71, 0)
    assert got == 1 and mask & 0x10, (
        f"plain M1 control must still die (count={got}, mask=${mask:02X})")

    # 10. NUSIZ1 staging: constant $30 for door AND plain (user rejected
    #     the 4clk door sizing 2026-10-12 — doors look like plain async).
    class MemTIA(Mem1):
        def __init__(self):
            super().__init__()
            self.tia_writes = {}

        def __setitem__(self, a, v):
            a &= 0xFFFF
            if a <= 0x3F or 0x100 <= a <= 0x13F:
                self.tia_writes[a & 0x3F] = v & 0xFF
            super().__setitem__(a, v)

    def stage_n1(meta_a):
        mem = MemTIA()
        r = mem.ram
        r[L2["RoomPF0Lo"] - 0x80] = meta_a         # staged MetaA
        r[L2["RoomPF0Lo"] + 1 - 0x80] = 0x00
        r[L0["EnemyDeadMask"] - 0x80] = 0
        mem.bank = 3            # C7: the band walker lives in bank3
        mpu = MPU(memory=mem)
        mpu.pc = L3["B3StageBand"]
        mpu.a = mpu.x = mpu.y = 0
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(5000):
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                return (mem.tia_writes.get(0x05),
                        r[0x8D - 0x80])          # NUSIZ1, door color
        sys.exit("StageBandTab (NUSIZ1 probe) never returned")

    n1, color = stage_n1(0x98)
    assert n1 == 0x30 and color == 0x1C, (
        f"door: NUSIZ1=${n1:02X} color=${color:02X}, want $30/$1C yellow")
    n1, color = stage_n1(0x90)
    assert n1 == 0x30 and color == 0x80, (
        f"plain: NUSIZ1=${n1:02X} color=${color:02X}, want $30/$80")

    # 11. Ball gate off for a NO-BALL model even when MetaA bit0 is set.
    #     A RIGHT-half door reuses MetaA bit0 as its "M1 strip on the RIGHT
    #     half" flag (band mask $00 — a door has no ball), and that bit is
    #     ALSO the band-0 ENABL gate: decoded blindly it enabled the ball in
    #     band0, painting a wall-coloured (COLUPF) 8px bar over the room's
    #     band-0 opening — the stray brown tile in
    #     screenshots/bugs/door_right.png (user report 2026-10-17).
    #     MetaA=$29 = live model 1: (m1_col+1=2)<<4 | $08 door | $01 right.
    def band_gate(meta_a, meta_b):
        mem = Mem1()
        r = mem.ram
        r[L2["RoomPF0Lo"] - 0x80] = meta_a        # staged MetaA
        r[L2["RoomPF0Lo"] + 1 - 0x80] = meta_b    # staged MetaB
        r[L0["EnemyDeadMask"] - 0x80] = 0
        mem.bank = 3            # C7: the band walker lives in bank3
        mpu = MPU(memory=mem)
        mpu.pc = L3["B3StageBand"]
        mpu.a = mpu.x = mpu.y = 0
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(8000):
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                return (r[L2["BandTab"] - 0x80], r[L2["BandTab"] + 1 - 0x80],
                        r[L2["BandTab"] + 2 - 0x80],
                        r[L2["CollisionEndY"] - 0x80],
                        r[L2["CollisionEndX"] - 0x80])
        sys.exit("StageBandTab (band gate probe) never returned")

    b0, b1, b2, packed, m1x = band_gate(0x29, 0x00)
    assert (b0, b1, b2) == (0, 0, 0), (
        f"door (no ball, MetaA bit0 = right-half flag) must blank the band "
        f"gates, got {(b0, b1, b2)}")
    assert m1x == 0x5F, f"right door M1X ${m1x:02X} != $5F (87+8*1)"
    assert packed == 0x08, (
        f"door pack ${packed:02X} != $08 (M1 present, no ball bits)")
    # control: the SAME bit0 with a real ball is still the band-0 gate
    b0, b1, b2, packed, m1x = band_gate(0x91, 0x03)
    assert (b0, b1, b2) == (0xFF, 0, 0), (
        f"ball model band-0 mask must still enable band0, got {(b0, b1, b2)}")
    assert packed & 0x07 == 0x01, (
        f"ball model pack mask ${packed & 7:02X} != $01")

    # --- Phase 3: phase-cell blink ---------------------------------------
    # Synthetic hot stream at $A0: solid count 0, hot count 1, record
    # $80, 2c=4 (pair idx 2 → PF1 bits7,6 = $C0), row 1 (PF1Buf row1 =
    # $C8). mod-90 clock (2026-10-13): phase <45 = ON half (b5 armed,
    # bits set); phase >=45 = OFF half (bits cleared).
    def stage_phase(clock):
        mem = Mem1()
        r = mem.ram
        r[0xA0 - 0x80:0xA0 - 0x80 + 6] = bytes([1, 0x80, 4, 1, 2, 1])
        r[L2["RoomRectsLo"] - 0x80] = 0xA0
        r[L2["RoomRectsLo"] + 1 - 0x80] = 0x00
        r[L2["RoomPF0Lo"] - 0x80] = 0x90   # staged MetaA: plain M1 (no door)
        r[L2["RoomPF0Lo"] + 1 - 0x80] = 0x00   # staged MetaB
        r[L0["EnemyDeadMask"] - 0x80] = 0
        r[0xC2 - 0x80] = clock             # EnemyRamP
        r[0xC8 - 0x80] = 0xC0              # PF1Buf row1 (N=4: $C7+1) ON
        mem.bank = 3            # C7: the band walker lives in bank3
        mpu = MPU(memory=mem)
        mpu.pc = L3["B3StageBand"]
        mpu.a = mpu.x = mpu.y = 0
        mpu.sp = 0xFD
        mem[0x1FF] = 0x01
        mem[0x1FE] = 0x00
        for _ in range(8000):              # walk + jsr depth
            mpu.step()
            if mpu.pc == RTS_SENTINEL:
                return r[0xC8 - 0x80]
        sys.exit("StageBandTab (phase probe) never returned")

    assert stage_phase(0x2D) == 0x00, (
        f"phase OFF half (phase 45) must clear PF1Buf row1 bits7,6 "
        f"(got ${stage_phase(0x2D):02X})")
    assert stage_phase(0x00) == 0xC0, (
        f"phase ON half (phase 0) must set PF1Buf row1 bits7,6 "
        f"(got ${stage_phase(0x00):02X})")
    # mod-90 two-pass normalize: clock 200 → 200-90-90 = 20 <45 = ON
    assert stage_phase(0xC8) == 0xC0, (
        f"mod-90 clock 200 must land in the ON half "
        f"(got ${stage_phase(0xC8):02X})")

    print("test_bomb_strip: OK (ball+M1 blast hit/controls, no double "
          "count, staging alive/dead, pad identity, rect4 walk + guard, "
          "P2b doors bomb-immune + NUSIZ1, Phase 3 blink + door color, "
          "no-ball band gate off)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
