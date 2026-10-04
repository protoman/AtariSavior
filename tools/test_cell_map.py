#!/usr/bin/env python3
"""PlayerHitsMap + moth-walk cell parity vs room geometry (plan 1.1+2.1+4.1).

Drives bank0 PlayerHitsMap headless (py65) for every model: RoomX 4..159 x
representative RoomY (one per distinct top/bottom row pair) x both facing
directions. C flag after the routine must equal "box overlaps a solid cell"
computed from model geometry through the SAME prologue math (visible-left,
endpoint mirror, min/max swap, YToRow rows).

Hit path runs the real bank2 HotOverlapBody (Mem emulates the F6 $1FF8
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
from convert_room import pf_values  # noqa: E402

SRC = ROOT / "src"
BANK0 = (SRC / "bank0.bin").read_bytes()
BANK2 = (SRC / "bank2.bin").read_bytes()


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
    # repeated hex pair before the name.
    rx_equ = re.compile(
        r"^\s*\d+\s+U[0-9a-fA-F]{4}\s+(?:[0-9a-f]{2}\s+)+"
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
         "EnemyRamD", "UE_Next", "LineCount"}
L0 = parse_labels(SRC / "bank0.lst", need0)
missing = need0 - L0.keys()
if missing:
    sys.exit(f"bank0.lst labels missing: {sorted(missing)}")
PHM = L0["PlayerHitsMap"]

need2 = {"M5RoomRects", ".MothColsOk"}
L2 = parse_labels(SRC / "bank2.lst", need2)
if not need2 <= L2.keys():
    sys.exit(f"bank2.lst labels missing: {sorted(need2 - L2.keys())}")

PF0_BUF = 0xC3
YTOROW = [i // 12 for i in range(48)]        # kernel YToRowTable (rows 0-3)
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
            return {0: BANK0, 2: BANK2}.get(self.bank, BANK0)[a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        if a == 0x1FF8:
            self.bank = 2
        elif a == 0x1FF6:
            self.bank = 0
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


def row_range(room_y: int) -> tuple[int, int]:
    return (YTOROW[(room_y >> 2) & 0x3F],
            YTOROW[((room_y + 11) >> 2) & 0x3F])


def box_hit(rows: list[str], lo: int, hi: int, top: int, bot: int) -> bool:
    """lo/hi are 4px display cols (0..19, walker space); D7 logical cell =
    col pair, so cell = col >> 1 (bit-pairing in pf_values)."""
    assert 0 <= lo <= hi <= 19, f"col range {lo}..{hi} out of spec"
    assert 0 <= top <= bot <= 2, f"row range {top}..{bot} out of spec"
    return any(rows[r][c >> 1] in "#H" for r in range(top, bot + 1)
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
    if not (vl <= bx and vl + 7 >= bx - 7):
        return False
    top, bot = row_range(ry)
    mask = packed & 7
    return any(mask & (1 << r) for r in range(top, bot + 1))


def asym_checks(rows: list[str]) -> int:
    """Full-X sweep with LineCount packed — exercises the OverlayTramp
    crossing (bank0 $F9B1 -> bank2 PHMOverlay $FE00 -> ReturnPad)."""
    mem = Mem()
    load_case(mem, rows)
    # packed configs: (right_col, band mask); 0 = symmetric control
    configs = [(0, 0), (0, 1), (5, 4), (9, 7), (9, 4)]
    checks = 0
    for rc, mask in configs:
        packed = 0 if rc == 0 and mask == 0 else ((rc + 1) << 4) | mask
        mem.ram[L0["LineCount"] - 0x80] = packed
        for rd in (0, 1):
            for rx in range(4, 160):
                for ry in (0, 60, 120):
                    mem.ram[L0["RoomX"] - 0x80] = rx
                    mem.ram[L0["PlayerDir"] - 0x80] = rd
                    mem.ram[L0["RoomY"] - 0x80] = ry
                    want = expected_hit(rows, rx, rd, ry) \
                        or overlay_hit(rx, rd, ry, packed)
                    got = run_phm(mem, rx, ry, rd)
                    assert got == want, (
                        f"asym packed=${packed:02X} (rc={rc} mask={mask}) "
                        f"X={rx} Y={ry} dir={rd}: PHM C={int(got)} want "
                        f"{int(want)} (base={expected_hit(rows, rx, rd, ry)} "
                        f"ovl={overlay_hit(rx, rd, ry, packed)}, "
                        f"vl={visible_left_px(rx, rd)})")
                    checks += 1
    mem.ram[L0["LineCount"] - 0x80] = 0
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
    mem.ram[L0["RoomRectsLo"] - 0x80] = L2["M5RoomRects"] & 0xFF
    mem.ram[L0["RoomRectsHi"] - 0x80] = L2["M5RoomRects"] >> 8


def main() -> int:
    # --- generator parity: models_data.asm PF bytes == pf_values ----------
    md = json.loads((SRC / "rooms" / "models" / "models.json").read_text())
    ml = md.get("models_file", md).get("models", [])
    by_id = {m.get("id"): m for m in ml}
    mda = (SRC / "generated" / "models_data.asm").read_text()
    cases = []
    for m in ml:
        mid = m.get("id")
        rows = rows_from_json({"model_id": mid}, by_id)
        cases.append((f"model{mid}", rows))
        for reg in ("PF0", "PF1", "PF2"):
            hit = re.search(rf"^M{mid}Tile{reg}:\s*\n\s*\.byte([^\n]+)",
                            mda, re.M)
            if not hit:
                continue                  # unreferenced model: not in ROM
            got = [int(b.strip().lstrip("$"), 16)
                   for b in hit.group(1).split(",")]
            want = [pf_values(r)[int(reg[2])] for r in rows]
            assert got == want, (f"M{mid}Tile{reg}: generated {got} "
                                 f"!= geometry {want}")

    # --- py65: box parity, all models, full X sweep, row-pair reps --------
    # Row pairs realized by the prologue: (0,0) Y0-36, (0,1) Y37-47,
    # (1,1) Y48-84, (1,2) Y85-95, (2,2) Y96-132 — one rep each.
    y_reps = (0, 40, 60, 90, 120)
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
    # --- Phase 4: asym overlay (packed LineCount) — crossing + px/band ---
    asym = asym_checks(cases[0][1])
    print(f"test_cell_map: OK ({checks} PHM boxes, {moth_checks} moth "
          f"boxes, {asym} asym overlay, {len(cases)} geometries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
