#!/usr/bin/env python3
"""C1 (2026-10-20): grid-position connections — a 20-room level, exits proved
against the REAL bank2 exit handlers.

LEVEL_FORMAT 2 replaces the 2 B nibble connection pack (`$F` = none, which
capped a level at 15 rooms) with ONE byte per room: `(x<<4 | y)` normalised to
the level origin. Connections are no longer stored — an exit steps its own
position by a direction delta and SCANS the level's position column
(bank2 `ExitDirB2` -> `ExitScanB2`). This test owns its data (a synthetic
20-room level built in a temp dir from the TEST-OWNED `src/tests/rooms`
models.json) and drives the frozen bank2 image, so a converter/reader mismatch
cannot hide behind live stage data.

Gates:
  * the converter emits exactly 4 B/room of room tables (2 B shape word +
    1 B position + 1 B RoomEnemies) for 20 rooms, positions unique with no
    nibble of 15, and 20 > the retired 15-room cap;
  * for EVERY (room, direction) the ROM returns the room index that the JSON
    adjacency implies (or "no exit"), with the opposite-edge placement
    (EnterRoomB2's A = room index contract, RoomY/RoomX staging);
  * the off-grid property is exercised for real: rooms on the grid's last
    column/row report no exit although a wrapped nibble would point at
    another room, because no stored position may use the nibble-15 sentinel.

Run: /home/iuri/python3/bin/python3 tools/test_grid_conn.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"

from py65.devices.mpu6502 import MPU  # noqa: E402

import test_cell_map as _CM  # noqa: E402
from test_cell_map import Mem, parse_labels  # noqa: E402

# ROM-byte reads come from the FROZEN bank images + label set (AGENTS rule:
# never live src/bank*.bin / src/*.lst from a test).
for _i in range(4):
    setattr(_CM, f"BANK{_i}", (FROZEN / f"bank{_i}.bin").read_bytes())
Mem = _CM.Mem

# kernel EQUs (read from the frozen bank2 listing via its hand copies)
Z = parse_labels(FROZEN / "bank2.lst", {
    "LevelPFDataLo", "LevelPFDataHi", "LevelRoomN", "RoomNo", "LevelConnSpare",
    "RoomX", "RoomY"})
L2 = parse_labels(FROZEN / "bank2.lst", {
    "ExitUpB2", "ExitDownB2", "ExitLeftB2", "ExitRightB2", "ExitScanB2",
    "EnterRoomB2", "ReturnPad"})
for need, got, where in (
        ({"ExitUpB2", "ExitDownB2", "ExitLeftB2", "ExitRightB2",
          "EnterRoomB2", "ReturnPad"}, L2, "bank2.lst"),
        ({"LevelPFDataLo", "LevelPFDataHi", "LevelRoomN", "RoomNo",
          "RoomX", "RoomY"}, Z, "bank2.lst")):
    lack = need - set(got)
    if lack:
        sys.exit(f"{where}: missing labels {sorted(lack)}")
if not {"ExitUpB2", "ExitDownB2", "ExitLeftB2", "ExitRightB2",
        "EnterRoomB2", "ReturnPad"} <= set(L2):
    sys.exit(f"frozen bank2.lst is missing exit labels: {sorted(set(L2))}")

PLAYER_MIN_X, PLAYER_MAX_X = 4, 159
PLAYER_MIN_Y, PLAYER_MAX_Y = 0, 132
DIRS = [("ExitUpB2", -1, 0, PLAYER_MAX_Y, "room_y"),
        ("ExitDownB2", 0, 1, PLAYER_MIN_Y, "room_y"),
        ("ExitLeftB2", -1, 0, PLAYER_MAX_X, "room_x"),
        ("ExitRightB2", 1, 0, PLAYER_MIN_X, "room_x")]

# 20 rooms: a 15-wide bottom row + a 5-room second row. Deliberately touches
# BOTH ends of the nibble range (x=0 and x=14, y=0), so the boundary cases the
# old nibble pack could not even express are real coverage.
ROOMS = [(x, 0) for x in range(15)] + [(x, 1) for x in range(5)]


def build_level(tmp: Path) -> Path:
    """Write the synthetic level + copy the test-owned models next to it."""
    (tmp / "models").mkdir(parents=True, exist_ok=True)
    models_src = SRC / "tests" / "rooms" / "models" / "models.json"
    shutil.copy(models_src, tmp / "models" / "models.json")
    rooms = []
    for i, (x, y) in enumerate(ROOMS):
        rooms.append({
            "room_id": i,
            "room_x": x,
            "room_y": y,
            "model_id": 0,
            "enemies": [],
            "lamps": [],
        })
    level = {
        "level": {
            "cereal_class_version": 1,
            "level_id": 20,
            "name": "C1 synthetic 20-room level",
            "wall_r": 28, "wall_g": 56, "wall_b": 144,
            "wall2_r": 80, "wall2_g": 112, "wall2_b": 188,
            "start_room": 0,
            "miner_room": 0,
            "miner_x": 2.0,
            "miner_y": 7.0,
            "miner_dir": 1,
            "rooms": rooms,
        }
    }
    path = tmp / "level_020.json"
    path.write_text(json.dumps(level, indent=1))
    return path


def convert(level_json: Path, tmp: Path) -> str:
    out = tmp / "level_020_rooms.asm"
    res = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "convert_level.py"),
         str(level_json), str(tmp / "level_020"), str(tmp)],
        capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"convert_level failed on the synthetic 20-room level:\n"
                 f"{res.stdout}{res.stderr}")
    return out.read_text()


def parse_generated(text: str) -> tuple[list[int], int, int, int]:
    words = len(re.findall(r"^  \.word ", text, re.M))
    pos = [int(h, 16) for h in re.findall(
        r"^  \.byte \$([0-9a-f]{2}) ; room \d+ \(\d+, \d+\)$", text, re.M)]
    enemies = len(re.findall(
        r"^  \.byte \$[0-9a-f]{2} ; room \d+: ", text, re.M))
    records = len(re.findall(r"^  \.byte \d+, \d+, \d+, \d+$", text, re.M))
    return pos, words, enemies, records


def expected(room: int) -> dict[int, int | None]:
    """JSON adjacency: up/down/left/right -> room index, independently of the
    converter (same rule the editor authors with: one grid cell away)."""
    x, y = ROOMS[room]
    out: dict[int, int | None] = {}
    for d, (dx, dy) in enumerate(((0, -1), (0, 1), (-1, 0), (1, 0))):
        hit = None
        for j, (ox, oy) in enumerate(ROOMS):
            if (ox, oy) == (x + dx, y + dy):
                hit = j
                break
        out[d] = hit
    return out


# The level block base is staged in ZP. The handlers take LevelPFDataLo/Hi as
# the base and add 2n to reach RoomPositions, so the column is laid out at
# base + 2n (exactly where the converter puts it). $A3 + 40 = $CB keeps all
# 20 bytes inside RAM and clear of every ZP var the handlers touch.
BASE = 0xA3
POS_AT = BASE + 2 * len(ROOMS)


def _zp(mem: Mem, name: str, value: int) -> None:
    mem.ram[Z[name] - 0x80] = value


def run_exit(mem: Mem, handler: str, room: int, positions: list[int],
             room_y: int = 99, room_x: int = 77) -> dict:
    assert POS_AT + len(positions) <= 0x100, "staged column must fit RAM"
    for i, pos in enumerate(positions):
        mem[POS_AT + i] = pos
    _zp(mem, "LevelPFDataLo", BASE & 0xFF)
    _zp(mem, "LevelPFDataHi", BASE >> 8)
    _zp(mem, "LevelRoomN", len(positions))
    _zp(mem, "RoomNo", room)
    _zp(mem, "RoomY", room_y)
    _zp(mem, "RoomX", room_x)
    mem.bank = 2
    mpu = MPU(memory=mem)
    mpu.pc = L2[handler]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(4000):
        mpu.step()
        if mpu.pc == L2["EnterRoomB2"]:
            return dict(moved=True, room=mpu.a,
                        room_y=mem.ram[Z["RoomY"] - 0x80],
                        room_x=mem.ram[Z["RoomX"] - 0x80])
        if mpu.pc == L2["ReturnPad"]:
            return dict(moved=False, room=None,
                        room_y=mem.ram[Z["RoomY"] - 0x80],
                        room_x=mem.ram[Z["RoomX"] - 0x80])
    sys.exit(f"{handler} from room {room} never reached EnterRoomB2/ReturnPad "
             f"(pc=${mpu.pc:04X}, bank={mem.bank})")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="gridconn_", dir="/tmp/opencode"))
    try:
        text = convert(build_level(tmp), tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    positions, words, enemies, records = parse_generated(text)

    # --- converter: table shape + the 20-room cap ---------------------------
    n = len(ROOMS)
    assert n == 20, "synthetic level must hold 20 rooms (the C1 target)"
    assert len(positions) == n, (
        f"RoomPositions: {len(positions)} bytes for {n} rooms")
    assert words == n and enemies == n, (
        f"RoomDataTable {words} words / RoomEnemies {enemies} bytes for {n} "
        "rooms")
    assert len(set(positions)) == n, "grid positions must be unique"
    for i, (x, y) in enumerate(ROOMS):
        assert positions[i] == ((x << 4) | y), (
            f"room {i}: position ${positions[i]:02x} != ({x},{y})")
        assert (positions[i] >> 4) < 15 and (positions[i] & 0x0F) < 15, (
            f"room {i}: nibble 15 is the off-grid sentinel, never emitted")
    # 2 B shape word + 1 B position + 1 B RoomEnemies = 4 B/room (was 5)
    assert words * 2 + len(positions) + enemies == 4 * n, "4 B/room contract"
    print(f"test_grid_conn: converter OK — {n} rooms, "
          f"{words * 2 + len(positions) + enemies} B of room tables "
          f"(4 B/room, {n} > the retired 15-room cap), {records} enemy records")

    # --- runtime: every (room, direction) through the real handlers ---------
    mem = Mem()
    moved = stayed = boundary = 0
    deltas = {0: 0xFF, 1: 0x01, 2: 0xF0, 3: 0x10}
    for room in range(n):
        want = expected(room)
        for d, (handler, _dx, _dy, edge, which) in enumerate(DIRS):
            got = run_exit(mem, handler, room, positions)
            target = want[d]
            if target is None:
                assert not got["moved"], (
                    f"{handler} from room {room} {ROOMS[room]} moved to "
                    f"room {got['room']} — no such neighbour in the JSON")
                assert got["room_y"] == 99 and got["room_x"] == 77, (
                    f"{handler} from room {room}: no-exit path must not move "
                    f"the player (RoomY={got['room_y']}, RoomX={got['room_x']})")
                stayed += 1
                x, y = ROOMS[room]
                # off-grid: the stepped nibble becomes 15 and no stored
                # position may use 15, so the scan can never match — this is
                # what replaces a per-direction boundary guard.
                if ((d == 0 and y == 0) or (d == 1 and y == 14)
                        or (d == 2 and x == 0) or (d == 3 and x == 14)):
                    boundary += 1
                    stepped = (positions[room] + deltas[d]) & 0xFF
                    assert 0xF in (stepped >> 4, stepped & 0x0F), (
                        f"room {room} {ROOMS[room]} dir {d}: stepping off the "
                        f"grid gave ${stepped:02x} with no nibble-15 sentinel")
                    assert stepped not in positions, (
                        f"room {room} {ROOMS[room]} dir {d}: off-grid target "
                        f"${stepped:02x} collides with a real room")
            else:
                assert got["moved"], (
                    f"{handler} from room {room} {ROOMS[room]} reported no "
                    f"exit — JSON says room {target} {ROOMS[target]}")
                assert got["room"] == target, (
                    f"{handler} from room {room} {ROOMS[room]} reached room "
                    f"{got['room']} {ROOMS[got['room']]}, want {target} "
                    f"{ROOMS[target]}")
                assert got[which] == edge, (
                    f"{handler} from room {room}: edge placement "
                    f"{which}={got[which]}, want {edge}")
                moved += 1
    assert boundary >= 4, (
        f"only {boundary} off-grid boundary cases exercised — the synthetic "
        "level must touch the x=0/x=14/y=0 edges")

    print(f"test_grid_conn: {moved} real exits + {stayed} no-exits "
          f"({boundary} off-grid boundary cases, each stepped into the "
          "nibble-15 sentinel) resolved by the frozen bank2 handlers")

    # --- the retired cap itself: 16 rooms could not be expressed before -----
    assert n > 15, "20 rooms is the point of C1"
    print("test_grid_conn: all asserts passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
