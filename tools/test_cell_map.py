#!/usr/bin/env python3
"""PlayerHitsMap + moth-walk cell parity vs room geometry (plan 1.1+2.1+4.1).

Drives bank0 PlayerHitsMap headless (py65) for every model: RoomX 4..159 x
representative RoomY (one per distinct top/bottom row pair) x both facing
directions. C flag after the routine must equal "box overlaps a solid cell"
computed from model geometry through the SAME prologue math (visible-left,
endpoint mirror, min/max swap, YToRow rows).

Hit path runs the real bank3 HotOverlapBody (Mem emulates the F6 $1FF7
switch, RoomRects pointed at a known hot-count-0 stream) — so the C=1
tail contract is exercised too.

Moth side (plan 4.1): drives bank2's moth cell walk directly at
.MothColsOk (post-prologue = walk entry) for EVERY valid box (all col
pairs x row pairs) and asserts the wiring contract: HIT flips EnemyRamD
and does NOT commit Temp; MISS commits Temp to EnemyRamX[0] and leaves
the dir bit — both paths exit via MothExitPad -> bank0 UE_Next.

Also asserts generated M*TilePF0/1/2 bytes == pf_values(geometry) so the
generator can't drift from collision truth.

Run: /home/iuri/python3/bin/python3 tools/test_cell_map.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from convert_level import rows_from_json  # noqa: E402
from convert_room import find_rectangles, pf_values  # noqa: E402

SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"   # test-owned banks+labels (never live src/)
TESTS = SRC / "tests"          # frozen stage copies (AGENTS test-data rule)
BANK0 = (FROZEN / "bank0.bin").read_bytes()
BANK1 = (FROZEN / "bank1.bin").read_bytes()
BANK2 = (FROZEN / "bank2.bin").read_bytes()
BANK3 = (FROZEN / "bank3.bin").read_bytes()
BANK4 = (FROZEN / "bank4.bin").read_bytes()
BANK5 = (FROZEN / "bank5.bin").read_bytes()
BANK6 = (FROZEN / "bank6.bin").read_bytes()
BANK7 = (FROZEN / "bank7.bin").read_bytes()


def parse_labels(path: Path, names: set[str]) -> dict[str, int]:
    out = {}
    rx_code = re.compile(
        r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_.][A-Za-z0-9_.]*)"
        r"(?:\s+subroutine)?\s*(?:;.*)?$")
    rx_zp = re.compile(
        r"^\s*\d+\s+U([0-9a-f]{4})\s+[0-9a-f]{2}+\s+"
        r"([A-Za-z_.][A-Za-z0-9_.]*)\s+byte")
    # EQU decls anchor on the PREVIOUS cell (U00bc) — value is after '=';
    # the U-line shows both anchor and value bytes ("00 bd"), hence the
    # repeated hex pair before the name. bank2 top-of-file EQUs emit the
    # address as a plain `f000` (no U prefix) — both forms accepted.
    rx_equ = re.compile(
        r"^\s*\d+\s+U?[0-9a-fA-F]{4}\s+(?:[0-9a-f]{2}\s+)+"
        r"([A-Za-z_.][A-Za-z0-9_.]*)\s+=\s+\$([0-9a-fA-F]+)")
    for line in path.read_text(errors="replace").splitlines():
        m = rx_equ.match(line)
        if m and m.group(1) in names and m.group(1) not in out:
            out[m.group(1)] = int(m.group(2), 16)
            continue
        for rx in (rx_code, rx_zp):
            m = rx.match(line)
            if m and m.group(2) in names and m.group(2) not in out:
                out[m.group(2)] = int(m.group(1), 16)
                break
    return out


need0 = {"PlayerHitsMap", "RoomX", "RoomY", "PlayerDir", "BombPacked",
         "RoomRectsLo", "RoomRectsHi", "Temp", "CollisionCellX",
         "CollisionCellY", "CollisionEndX", "CollisionEndY",
         "EnemyDataLo", "EnemyDataHi", "EnemyIndex", "EnemyRamX",
         "EnemyRamD", "UE_Next", "LineCount", "FetchPtr",
         "EnemyDeadMask"}
L0 = parse_labels(FROZEN / "bank0.lst", need0)
missing = need0 - L0.keys()
if missing:
    sys.exit(f"bank0.lst labels missing: {sorted(missing)}")
PHM = L0["PlayerHitsMap"]

need2 = {".MothColsOk", "RoomPF0Lo"}
# C2 (2026-10-20): the level/model BLOCKS moved into bank2, so the code
# labels and the block labels come from ONE listing now (bank3 is the boot
# stub only). C3: a shape block ends in `<tag>Rows` (3 row-pool indices).
# C7 (2026-10-20): the SHAPE half (model blocks, the row pool and the async
# extras streams) moved back to bank3 with the walkers that read them; bank2
# keeps the room/enemy tables. Code labels still come from bank2.lst, block
# data labels from bank3.lst.
blk = {"M5Shape", "M0Shape", "M0Rows",
       "LEVEL1_AsyncExtras", "RoomNoStream", "RoomMetaB", "RoomM1Hot"}
L2 = parse_labels(FROZEN / "bank2.lst", need2 | blk)
L3 = parse_labels(FROZEN / "bank3.lst", blk)
if not need2 <= L2.keys():
    sys.exit(f"bank2 labels missing: {sorted(need2 - L2.keys())}")
if not blk <= L3.keys():
    sys.exit(f"bank3 labels missing: {sorted(blk - L3.keys())}")

PF0_BUF = 0xC3
YTOROW = [min(i // 12, 2) for i in range(48)]  # kernel YToRowTable: 36
                              # entries + idx36 tentacle-bob clamp = 2
                              # (bugs.md #13; box past cave bottom → row 2)
Z_FLAG = 0x02
C_FLAG = 0x01
RTS_SENTINEL = 0x0101


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.bank = 0

    def __getitem__(self, a):
        a &= 0xFFFF
        if 0xF000 <= a <= 0xFFFF:
            return {0: BANK0, 1: BANK1, 2: BANK2, 3: BANK3,
                                      4: BANK4, 5: BANK5, 6: BANK6, 7: BANK7}.get(self.bank, BANK0)[a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        if a == 0x1FF4:
            self.bank = 0
        elif a == 0x1FF5:
            self.bank = 1
        elif a == 0x1FF6:
            self.bank = 2
        elif a == 0x1FF7:
            self.bank = 3
        elif a == 0x1FF8:
            self.bank = 4
        elif a == 0x1FF9:
            self.bank = 5
        elif a == 0x1FFA:
            self.bank = 6
        elif a == 0x1FFB:
            self.bank = 7
        elif 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v & 0xFF
        # other hotspots ignored


from py65.devices.mpu6502 import MPU  # noqa: E402


def run_phm(mem: Mem, room_x: int, room_y: int, player_dir: int) -> bool:
    """Drive PlayerHitsMap; return C (True = blocked)."""
    mem.bank = 0
    mpu = MPU(memory=mem)
    mpu.pc = PHM
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(900):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return bool(mpu.p & C_FLAG)
    sys.exit(f"PHM(X={room_x}, Y={room_y}, dir={player_dir}) never returned "
             f"(pc=${mpu.pc:04X}, bank={mem.bank})")


def visible_range(room_x: int, player_dir: int) -> tuple[int, int]:
    """Replicate PHM prologue column math (8-bit), returns (min, max) src col."""
    a = (room_x - player_dir) & 0xFF
    if a >= 15:
        a = (a - 7) & 0xFF
    else:
        a = (a - 4) & 0xFF
    a = (a + player_dir) & 0xFF            # .gotVL: clc adc PlayerDir
    endx = a >> 2
    if endx >= 20:
        endx = (39 - endx) & 0xFF          # mirror (sta CollisionX / 39-a)
    a = (a + 6) & 0xFF                     # PLAYER_WIDTH-1
    cellx = a >> 2
    if cellx >= 20:
        cellx = (39 - cellx) & 0xFF
    if endx > cellx:
        endx, cellx = cellx, endx          # .colsOk swap
    return endx, cellx


PLAYER_SPRITE_H = int(re.search(r"^PLAYER_SPRITE_H\s*=\s*(\d+)",
                                 (Path(__file__).resolve().parents[1] /
                                  "src" / "kernel.asm").read_text(), re.M).group(1))


def row_range(room_y: int) -> tuple[int, int]:
    """Player box rows: PHM's bottom row = RoomY + PLAYER_SPRITE_H - 1."""
    return (YTOROW[(room_y >> 2) & 0x3F],
            YTOROW[((room_y + PLAYER_SPRITE_H - 1) >> 2) & 0x3F])


def tentacle_ink_cells(cand: int) -> tuple[int, int] | None:
    """Tentacle ink cells (walker space): 4 px at vl = cand-5/-7 (bank2
    .Mvl convention — SetObjectXPos draws the sprite 5/7 px left of A),
    mirrored >=20 like the PHM prologue. None = fully off-screen left."""
    vl = cand - (5 if cand < 15 else 7)
    if vl + 3 < 0:
        return None
    lo = max(0, vl) >> 2
    hi = (max(0, vl) + 3) >> 2
    if lo >= 20:
        lo = (39 - lo) & 0xFF
    if hi >= 20:
        hi = (39 - hi) & 0xFF
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def box_hit(rows: list[str], lo: int, hi: int, top: int, bot: int) -> bool:
    """lo/hi are 4px display cols (0..19, walker space); D7 logical cell =
    col pair, so cell = col >> 1 (bit-pairing in pf_values)."""
    assert 0 <= lo <= hi <= 19, f"col range {lo}..{hi} out of spec"
    assert 0 <= top <= bot <= 2, f"row range {top}..{bot} out of spec"
    return any(rows[r][c >> 1] in "#HPVC" for r in range(top, bot + 1)
               for c in range(lo, hi + 1))


def run_moth(mem: Mem, lo: int, hi: int, top: int, bot: int,
             temp: int) -> bool:
    """Drive bank2's moth cell walk at .MothColsOk (post-prologue = walk
    entry); return True = HIT. Asserts the exit wiring contract: HIT flips
    EnemyRamD ($00->$01, MothBitTable[0]) and must NOT commit Temp;
    MISS commits Temp to EnemyRamX[0] and leaves the dir bit."""
    mem.bank = 2
    r = mem.ram
    r[L0["CollisionEndX"] - 0x80] = lo
    r[L0["CollisionCellX"] - 0x80] = hi
    r[L0["CollisionCellY"] - 0x80] = top
    r[L0["CollisionEndY"] - 0x80] = bot
    r[L0["Temp"] - 0x80] = temp
    r[L0["EnemyIndex"] - 0x80] = 0
    r[L0["EnemyRamX"] - 0x80] = 0xAA        # untouched sentinel
    r[L0["EnemyRamD"] - 0x80] = 0x00
    r[L0["EnemyDataLo"] - 0x80] = 0x00      # restage-only on exit
    r[L0["EnemyDataHi"] - 0x80] = 0x00
    mpu = MPU(memory=mem)
    mpu.pc = L2[".MothColsOk"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    for _ in range(5000):
        mpu.step()
        if mem.bank == 0 and mpu.pc == L0["UE_Next"]:
            break
    else:
        sys.exit(f"moth walk(box {lo}..{hi},{top}..{bot}) never exited "
                 f"(pc=${mpu.pc:04X}, bank={mem.bank})")
    hit = r[L0["EnemyRamD"] - 0x80] == 0x01
    committed = r[L0["EnemyRamX"] - 0x80] == temp
    assert (hit and not committed) or (not hit and committed), (
        f"moth wiring: box {lo}..{hi},{top}..{bot}: "
        f"EnemyRamD={r[L0['EnemyRamD'] - 0x80]:02X} "
        f"EnemyRamX={r[L0['EnemyRamX'] - 0x80]:02X} temp={temp:02X}")
    return hit


def expected_hit(rows: list[str], rx: int, rd: int, ry: int) -> bool:
    lo, hi = visible_range(rx, rd)
    top, bot = row_range(ry)
    return box_hit(rows, lo, hi, top, bot)


def visible_left_px(rx: int, rd: int) -> int:
    """PHMOverlay's visible_left (same 8-bit math as the prologue)."""
    a = (rx - rd) & 0xFF
    a = a - 7 if a >= 15 else a - 4
    return (a + rd) & 0xFF


def overlay_hit(rx: int, rd: int, ry: int, packed: int) -> bool:
    """Spec of bank2 PHMOverlay: packed = (right_col+1)<<4 | band mask."""
    if packed == 0 or (packed >> 4) == 0:
        return False
    vl = visible_left_px(rx, rd)
    bx = 79 + 8 * (packed >> 4)          # BallX = 87+8*rc (patch right edge)
    if not (vl <= bx and vl + 6 >= bx - 7):   # lit span = 7px [vl, vl+6]
        return False
    top, bot = row_range(ry)
    mask = packed & 7
    return any(mask & (1 << r) for r in range(top, bot + 1))


def m1_overlay_hit(rx: int, rd: int, ry: int, rows: list[str],
                   m1x: int, dead: int) -> bool:
    """Spec of bank0 OvM1Block (Phase 4 M1 strip overlay).

    Reached only when the tramp crossed (packed != 0 — checked by the
    caller). Kill-aware (EnemyDeadMask b4). The door is a solid 8 px block
    [M1X-7, M1X] and the player box is 7 lit px [vl, vl+6], so it blocks as
    soon as the boxes TOUCH: vl in [M1X-13, M1X]. Symmetric by construction
    (a left-wall door is approached from its right, a right-wall one from
    its left). Cell = M1X>>2, mirrored to 39-cell on the right half (the
    same reflect mapping as visible_range); band test = any player row with
    the PF cell open (wall-hide envelope: open ⟺ M1-patched). The PF cell
    is 4 px, the model grid above is 8 px (WIDTH 10), so the model index is
    PF_cell >> 1."""
    if dead or m1x == 0:
        return False
    vl = visible_left_px(rx, rd)
    if vl > m1x or vl < m1x - 13:
        return False
    ell = m1x >> 2
    if ell >= 20:
        ell = 39 - ell
    ell >>= 1                      # the model grid is 8 px cells (WIDTH 10)
    top, bot = row_range(ry)
    for r in range(top, bot + 1):
        row = rows[r]
        if len(row) <= ell:
            raise AssertionError(
                f"M1 spec: row {r} has {len(row)} cells, need index {ell} "
                f"(M1X={m1x}); row={row!r}")
        if row[ell] == ".":
            return True
    return False


def asym_checks(rows: list[str]) -> int:
    """Full-X sweep with LineCount packed — exercises the OverlayTramp
    crossing (bank0 $F9B1 -> bank2 PHMOverlay $FE00 -> ReturnPad) for
    BOTH strips: the right ball strip (packed) and the left M1 strip
    (OvM1Block: M1X meta via the RoomPF0Lo pointer + b4 kill knob)."""
    mem = Mem()
    load_case(mem, rows)
    r = mem.ram
    # C5 (2026-10-20): MetaA/MetaB live in the level's AsyncExtras record
    # (level 1 room 0 is an async room; its record is ordinal 1, so the pair
    # is at LEVEL1_AsyncExtras+1/+2). M1X = 8*(m1_col+1)-1, 0 = no M1.
    m1n = BANK3[L3["LEVEL1_AsyncExtras"] - 0xF000 + 1] >> 4
    m1x = 8 * m1n - 1 if m1n else 0
    r[L2["RoomPF0Lo"] - 0x80] = BANK3[L3["LEVEL1_AsyncExtras"] - 0xF000 + 1]
    r[L2["RoomPF0Lo"] + 1 - 0x80] = BANK3[L3["LEVEL1_AsyncExtras"] - 0xF000 + 2]
    r[L0["EnemyDeadMask"] - 0x80] = 0
    # packed configs: (right_col, band mask); 0 = symmetric control
    configs = [(0, 0), (0, 1), (5, 4), (9, 7), (9, 4)]
    checks = 0
    for dead in (0, 0x10):
        for rc, mask in configs:
            packed = 0 if rc == 0 and mask == 0 else ((rc + 1) << 4) | mask
            if dead and packed == 0:
                continue          # kill knob needs one packed≠0 config only
            r[L0["LineCount"] - 0x80] = packed
            r[L0["EnemyDeadMask"] - 0x80] = dead
            for rd in (0, 1):
                for rx in range(4, 160):
                    for ry in (0, 60, 120):
                        mem.ram[L0["RoomX"] - 0x80] = rx
                        mem.ram[L0["PlayerDir"] - 0x80] = rd
                        mem.ram[L0["RoomY"] - 0x80] = ry
                        ball = overlay_hit(rx, rd, ry, packed)
                        # tramp gate: packed==0 → no crossing → no M1 either
                        m1 = packed != 0 and m1_overlay_hit(
                            rx, rd, ry, rows, m1x, dead)
                        want = expected_hit(rows, rx, rd, ry) or ball or m1
                        got = run_phm(mem, rx, ry, rd)
                        assert got == want, (
                            f"asym packed=${packed:02X} (rc={rc} mask={mask} "
                            f"dead=${dead:02X}) X={rx} Y={ry} dir={rd}: PHM "
                            f"C={int(got)} want {int(want)} (base="
                            f"{expected_hit(rows, rx, rd, ry)} ball={ball} "
                            f"m1={m1}, m1x={m1x}, "
                            f"vl={visible_left_px(rx, rd)})")
                        checks += 1
    r[L0["LineCount"] - 0x80] = 0
    r[L0["EnemyDeadMask"] - 0x80] = 0
    return checks


def moth_strip_checks() -> int:
    """Phase 4: moth vs the D6 patch strip (bank2 .MothColsOk overlay).

    run_moth enters at .MothColsOk (post-prologue), so the fixture stashes
    vl into FetchPtr exactly like the prologue's new `sta FetchPtr` would.
    Rows fully open => the mirrored walk always misses; only the overlay
    can turn the moth. Strip: right_col 9 (px 152..159, BallX=159),
    band row 1."""
    mem = Mem()
    load_case(mem, [".........."] * 3)
    top = bot = 1
    packed = (9 + 1) << 4 | 0x02       # right_col+1 in b4-7, band1 bit
    inactive = (9 + 1) << 4 | 0x01     # band0 only -> strip transparent here
    checks = 0

    def probe(temp: int, line_count: int) -> bool:
        r = mem.ram
        r[L0["LineCount"] - 0x80] = line_count
        vl = temp - 5 if temp < 15 else temp - 7   # prologue .MvlA math
        r[L0["FetchPtr"] - 0x80] = vl & 0xFF
        return run_moth(mem, 0, 19, top, bot, temp)

    # in-strip candidate (vl=150 in [145,159]) -> overlay turns
    assert probe(157, packed), "active strip must block the moth at px157"
    checks += 1
    # left of strip (vl=133 < 145) -> mirrored walk (open rows) commits
    assert not probe(140, packed), "moth left of strip must walk through"
    checks += 1
    # symmetric control: no overlay, same candidate -> commits
    assert not probe(157, 0), "sym run must not turn at the strip"
    checks += 1
    # inactive band: strip painted elsewhere -> transparent
    assert not probe(157, inactive), "inactive-band strip must be transparent"
    checks += 1
    mem.ram[L0["LineCount"] - 0x80] = 0
    return checks


HOT_ROWS = [
    "..........",
    "HHHH....##",        # row 1: hot cells cols 0-3, plain wall cols 8-9
    "..........",
]
HOT_M1_COL = 5           # PF-OPEN row-1 cell (the M1 strip paints there)


def hot_death_checks(rows_unused: list[str] | None = None) -> int:
    """C11 (2026-10-21) hot-death sweeps — PF-derived hot, test-owned room.

    Hot cells of a mid_band_type=1 model ARE its solid row-1 PF cells
    (convert promotes every row-1 wall), so HotOverlapBody sweeps the box's
    display columns over PF row 1 whenever MetaB b6 is set. The sweep is
    reached only from a cell-walk hit, so the contract is:

        Temp b7 ⟺ the player bumped something AND the box overlaps a SOLID
        row-1 cell (in a hot room), or the staged hot-band M1 block cell.

    Two passes:
      A. PF sweep (no M1 cell): every X x both facings x row-pair reps.
      B. M1 block cell (PF-open, staged in RoomM1Hot = col+1): strip alive
         (EnemyDeadMask b4 clear) → kill; strip destroyed → pass.
      C. PUNCHED parents: the same hot room with row 1 emptied (= what the
         bomb punch does to the PF cell) must never fire Temp b7, even
         though the box still overlaps row 1 — the bombed hot wall stops
         being hot with no record gate.
    The cold control (MetaB b6 clear) must never fire Temp b7 — normal
    collision is the cell walk's own C=1, not a death.
    """
    punched = [HOT_ROWS[0], "..........", HOT_ROWS[2]]   # row 1 blasted out
    checks = 0
    for rows, hot, m1, dead in (
            (HOT_ROWS, True, False, 0), (HOT_ROWS, True, True, 0),
            (HOT_ROWS, True, True, 0x10), (HOT_ROWS, False, False, 0),
            (punched, True, False, 0)):
        mem = Mem()
        load_case(mem, rows)
        r = mem.ram
        r[L3["RoomMetaB"] - 0x80] = 0x40 if hot else 0
        r[L3["RoomM1Hot"] - 0x80] = HOT_M1_COL + 1 if m1 else 0
        r[L0["EnemyDeadMask"] - 0x80] = dead
        r[L0["BombPacked"] - 0x80] = 0
        r[L0["LineCount"] - 0x80] = 0        # no ball/M1 overlay: entered =
        #                                      the cell walk's own result
        for rd in (0, 1):
            for rx in range(4, 160):
                for ry in (40, 60, 90, 120):   # rows {0,1},{1,1},{1,2},{2,2}
                    r[L0["RoomX"] - 0x80] = rx
                    r[L0["PlayerDir"] - 0x80] = rd
                    r[L0["RoomY"] - 0x80] = ry
                    r[L0["Temp"] - 0x80] = 0x0F    # joystick: nothing pressed
                    lo, hi = visible_range(rx, rd)
                    top, bot = row_range(ry)
                    entered = expected_hit(rows, rx, rd, ry)
                    row1 = top <= 1 <= bot
                    solid = any(rows[1][c >> 1] in "#H"
                                for c in range(lo, hi + 1))
                    m1_cell = (m1 and dead == 0 and row1
                               and 2 * HOT_M1_COL <= hi
                               and 2 * HOT_M1_COL + 2 > lo)
                    want = entered and hot and row1 and (solid or m1_cell)
                    run_phm(mem, rx, ry, rd)
                    got = bool(r[L0["Temp"] - 0x80] & 0x80)
                    assert got == want, (
                        f"hot sweep hot={int(hot)} m1={int(m1)} "
                        f"dead=${dead:02X} X={rx} Y={ry} dir={rd}: "
                        f"Temp.b7={int(got)} want {int(want)} "
                        f"(entered={int(entered)} row1={int(row1)} "
                        f"solid={int(solid)} m1cell={int(m1_cell)} box "
                        f"{lo}..{hi} {top}..{bot})")
                    checks += 1
    return checks


def load_case(mem: Mem, rows: list[str]) -> None:
    for r, row in enumerate(rows):
        pf0, pf1, pf2 = pf_values(row)
        mem.ram[PF0_BUF - 0x80 + r] = pf0
        mem.ram[PF0_BUF - 0x80 + 3 + r] = pf1
        mem.ram[PF0_BUF - 0x80 + 6 + r] = pf2
    mem.ram[L0["RoomX"] - 0x80] = 0
    mem.ram[L0["RoomY"] - 0x80] = 0
    mem.ram[L0["PlayerDir"] - 0x80] = 0
    mem.ram[L0["BombPacked"] - 0x80] = 0
    # C11 (2026-10-21): a shape block carries no record stream any more —
    # point RoomRects at bank3's static $00 count (the "no stream" sentinel).
    mem.ram[L0["RoomRectsLo"] - 0x80] = L3["RoomNoStream"] & 0xFF
    mem.ram[L0["RoomRectsHi"] - 0x80] = L3["RoomNoStream"] >> 8
    mem.ram[L3["RoomMetaB"] - 0x80] = 0        # cold room (no hot sweep)
    mem.ram[L3["RoomM1Hot"] - 0x80] = 0        # no hot-band M1 block cell


def main() -> int:
    # --- generator parity: the ROW POOL + shape indices == pf_values ------
    # C3 (2026-10-20): a shape block carries 3 one-byte row-pool indices, not
    # the 9 PF bytes, so parity is `pool[idx]` per band.
    md = json.loads(
        (TESTS / "rooms" / "models" / "models.json").read_text())
    ml = md.get("models_file", md).get("models", [])
    by_id = {m.get("id"): m for m in ml}
    mda = (TESTS / "generated" / "models_data.asm").read_text()
    pool: dict[str, list[int]] = {}
    for name in ("RowPoolPF0", "RowPoolPF1", "RowPoolPF2"):
        hit = re.search(rf"^{name}:\s*\n\s*\.byte([^\n]+)", mda, re.M)
        assert hit, f"generated models_data.asm has no {name} (C3 row pool)"
        pool[name] = [int(b.strip().lstrip("$"), 16)
                      for b in hit.group(1).split(",")]
    row_count = int(re.search(r"^LEVEL_ROW_COUNT = (\d+)$", mda, re.M).group(1))
    assert all(len(v) == row_count for v in pool.values()), (
        f"pool columns {[(k, len(v)) for k, v in pool.items()]} vs "
        f"LEVEL_ROW_COUNT {row_count}")
    cases = []
    for m in ml:
        mid = m.get("id")
        rows = rows_from_json({"model_id": mid}, by_id)
        cases.append((f"model{mid}", rows))
        hit = re.search(rf"^M{mid}Rows:\s*\n\s*\.byte([^\n]+)", mda, re.M)
        if not hit:
            continue                      # unreferenced model: not in ROM
        idx = [int(b.strip().lstrip("$"), 16)
               for b in hit.group(1).split(";")[0].split(",")]
        assert len(idx) == 3, f"M{mid}Rows: {len(idx)} indices, want 3"
        # C11: band 1's index byte b7 = mid_band_type (the hot flag).
        want_hot = 0x80 if m.get("mid_band_type") else 0
        assert (idx[1] & 0x80) == want_hot, (
            "M%sRows band1 $%02x: b7 must be $%02x (mid_band_type=%d)"
            % (mid, idx[1], want_hot, 1 if want_hot else 0))
        assert not ((idx[0] | idx[2]) & 0x80), "M%dRows: b7 outside band 1" % mid
        idx = [i & 0x7F for i in idx]
        for reg, name in enumerate(("RowPoolPF0", "RowPoolPF1", "RowPoolPF2")):
            got = [pool[name][i] for i in idx]
            want = [pf_values(r)[reg] for r in rows]
            assert got == want, (f"M{mid}Rows -> {name}: generated {got} "
                                 f"!= geometry {want}")
        for band, i in enumerate(idx):
            assert i < row_count, f"M{mid}Rows band {band}: {i} >= {row_count}"

    # --- py65: box parity, all models, full X sweep, row-pair reps --------
    # Row pairs realized by the prologue: (0,0) Y0-11, (0,1) Y12-23,
    # (1,1) Y24-59, (1,2) Y60-71, (2,2) Y72-122 — one rep each. The LAST
    # rep is PLAYER_MAX_Y (122): the bottom row is (Y+PLAYER_SPRITE_H-1)>>2
    # and must stay inside YToRowTable (idx <= 36 = the clamp entry), so a
    # Y above the reachable range reads past the table and is not a case.
    y_reps = (0, 40, 60, 90, 120, 122)
    checks = 0
    moth_checks = 0
    temp = 0x42                        # candidate != sentinel 0xAA
    for name, rows in cases:
        assert len(rows) == 3 and all(len(r) == 10 for r in rows), name
        mem = Mem()
        load_case(mem, rows)
        for rd in (0, 1):                 # FACING_RIGHT / FACING_LEFT
            for rx in range(4, 160):      # PLAYER_MIN_X..PLAYER_MAX_X
                mem.ram[L0["RoomX"] - 0x80] = rx
                mem.ram[L0["PlayerDir"] - 0x80] = rd
                for ry in y_reps:
                    mem.ram[L0["RoomY"] - 0x80] = ry
                    want = expected_hit(rows, rx, rd, ry)
                    got = run_phm(mem, rx, ry, rd)
                    assert got == want, (
                        f"{name} X={rx} Y={ry} dir={rd}: "
                        f"PHM C={int(got)} want {int(want)} "
                        f"(box cols {visible_range(rx, rd)} rows "
                        f"{row_range(ry)})")
                    checks += 1
        # --- moth walk: every valid box (plan 4.1), wiring asserted ------
        # lo/hi stay display cols (walker space, 0..19); box_hit maps to
        # D7 logical cells via col >> 1.
        for lo in range(20):
            for hi in range(lo, 20):
                for top in range(3):
                    for bot in range(top, 3):
                        want = box_hit(rows, lo, hi, top, bot)
                        got = run_moth(mem, lo, hi, top, bot, temp)
                        assert got == want, (
                            f"{name} moth box cols {lo}..{hi} rows "
                            f"{top}..{bot}: HIT={got} want {want}")
                        moth_checks += 1
    # --- C4 regression (2026-10-20): a model with >5 wall rects (the old
    # ZP-cache limit; stage models 5/6 carry 6) must be solid EXACTLY where
    # its PF triple says solid. The solid rect list is retired, so this is
    # the whole collision contract: one cell box (lo=2c, hi=2c+1) per cell,
    # driven through the real moth cell walk.
    six = [(nm, rows) for nm, rows in cases
           if len(find_rectangles(rows, solids="#")) > 5]
    assert six, "stage has no >5-rect model — the 6-rect regression is moot"
    six_checks = 0
    for name, rows in six:
        mem6 = Mem()
        load_case(mem6, rows)
        triples = [pf_values(r) for r in rows]
        for row in range(3):
            for col in range(10):                  # left-half D7 cells
                lo, hi = 2 * col, 2 * col + 1      # one cell = 2 display cols
                want = box_hit(rows, lo, hi, row, row)
                got = run_moth(mem6, lo, hi, row, row, temp)
                assert got == want, (
                    f"{name} 6-rect cell (row {row}, col {col}): "
                    f"HIT={got} want {want} (PF={triples[row]})")
                six_checks += 1
    print(f"C4 6-rect solidity: {len(six)} models x 30 cells = "
          f"{six_checks} cells match the PF map")

    # --- Phase 4: asym overlay (packed LineCount) — crossing + px/band ---
    asym = asym_checks(cases[0][1])
    strip = moth_strip_checks()
    # C11 (2026-10-21): hot death is PF-derived, so the sweep no longer needs
    # a live hot model — it authors its own hot room in this file
    # (HOT_ROWS) and covers the PF sweep, the bomb-punched parent and the
    # hot-band M1 block cell (strip alive/destroyed) plus the cold control.
    hot = hot_death_checks()
    # --- #4 tentacle probe origin (UE_Tentacle RoomX = cand-1) -------------
    # Column-set inclusion, geometry-free: PHM's row range (Y..Y+11) always
    # covers the tentacle ink rows (Y+1..Y+8), so cols-coverage implies the
    # probe HITs whenever ink touches a wall cell, for every geometry.
    # Kernel guard: cand<=4 probes RoomX=cand (no offset) — RoomX<=3 wraps
    # PHM's negative visible-left to 255 (ColOff OOB walk).
    tent_checks = 0
    for rd in (0, 1):
        for cand in range(4, 160):
            ink = tentacle_ink_cells(cand)
            if ink is None:
                continue
            r_room = cand - 1 if cand >= 5 else cand
            lo, hi = visible_range(r_room, rd)
            assert ink[0] >= lo and ink[1] <= hi, (
                f"tentacle cand={cand} dir={rd}: ink cells {ink[0]}..{ink[1]} "
                f"outside probe box {lo}..{hi} (RoomX={r_room})")
            tent_checks += 1
    # Sensitivity: the pre-fix RoomX=cand box must MISS the ink cell at
    # cand 8/12 (the bugs.md #4 1-px wall overlap) — proves this sweep
    # would catch a regression that drops the origin offset.
    for rd in (0, 1):
        for cand in (8, 12):
            ink = tentacle_ink_cells(cand)
            lo, hi = visible_range(cand, rd)
            assert not (ink[0] >= lo and ink[1] <= hi), (
                f"tentacle sensitivity cand={cand} dir={rd}: pre-fix box "
                f"{lo}..{hi} unexpectedly covers ink {ink[0]}..{ink[1]}")
            tent_checks += 1
    print(f"test_cell_map: OK ({checks} PHM boxes, {moth_checks} moth "
          f"boxes, {tent_checks} tentacle-probe, {asym} asym overlay, "
          f"{strip} moth-strip, {hot} hot-death, "
          f"{len(cases)} geometries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
