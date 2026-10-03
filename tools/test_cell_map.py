#!/usr/bin/env python3
"""PlayerHitsMap cell-walk parity vs room geometry (cell_collision_plan 1.1+2.1).

Drives bank0 PlayerHitsMap headless (py65) for every model: RoomX 4..159 x
representative RoomY (one per distinct top/bottom row pair) x both facing
directions. C flag after the routine must equal "box overlaps a solid cell"
computed from model geometry through the SAME prologue math (visible-left,
endpoint mirror, min/max swap, YToRow rows).

Hit path runs the real bank2 HotOverlapBody (Mem emulates the F6 $1FF8
switch, RoomRects pointed at a known hot-count-0 stream) — so the C=1
tail contract is exercised too.

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
    for line in path.read_text(errors="replace").splitlines():
        for rx in (rx_code, rx_zp):
            m = rx.match(line)
            if m and m.group(2) in names and m.group(2) not in out:
                out[m.group(2)] = int(m.group(1), 16)
                break
    return out


need0 = {"PlayerHitsMap", "RoomX", "RoomY", "PlayerDir", "BombPacked",
         "RoomRectsLo", "RoomRectsHi"}
L0 = parse_labels(SRC / "bank0.lst", need0)
missing = need0 - L0.keys()
if missing:
    sys.exit(f"bank0.lst labels missing: {sorted(missing)}")
PHM = L0["PlayerHitsMap"]

need2 = {"M5RoomRects"}
L2 = parse_labels(SRC / "bank2.lst", need2)
if not need2 <= L2.keys():
    sys.exit("bank2.lst: M5RoomRects missing")

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


def expected_hit(rows: list[str], rx: int, rd: int, ry: int) -> bool:
    lo, hi = visible_range(rx, rd)
    top, bot = row_range(ry)
    assert 0 <= lo <= hi <= 19, f"col range {lo}..{hi} out of spec (X={rx} d={rd})"
    assert 0 <= top <= bot <= 2, f"row range {top}..{bot} out of spec (Y={ry})"
    return any(rows[r][c] in "#H" for r in range(top, bot + 1)
               for c in range(lo, hi + 1))


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
    for name, rows in cases:
        assert len(rows) == 3 and all(len(r) == 20 for r in rows), name
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
    print(f"test_cell_map: OK ({checks} PHM boxes, {len(cases)} geometries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
