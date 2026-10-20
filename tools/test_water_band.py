#!/usr/bin/env python3
"""Water/bottom-band guard: the raft's other half (bottom_band_plan rule 4).

A `bottom_band` room's water kills at RoomY >= 125 and re-places the player ONE
TILE ABOVE the strip (RoomY -= 12) — that is what makes a row-2 RAFT tile the
only safe footing in a water room (the platform holds the player at ~84, the
open water below kills). tools/qa_sweep.py proves that in-game; this test puts
the rule itself under the battery (build.sh runs the battery after every ROM).

Cases (driving the real overscan entry CheckBandTouch):
  1. band off            -> nothing happens at any height
  2. band on, RoomY 124  -> 1 px above the strip: still safe (no life lost)
  3. band on, RoomY 125  -> losing one life and the respawn DESTINY (DropTarget)
                            is one tile above the strip (125-12=113), RoomY
                            zeroed for the drop
  4. band on, RoomY 132  -> same, destiny = 120
  5. lives exhausted (PlayerLives=0) -> PlayerLives resets to 3 (the game-over
                            path; today it is a level reload, NOT a screen)

Run: /home/iuri/python3/bin/python3 tools/test_water_band.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, RTS_SENTINEL, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "src" / "tests" / "frozen"
NEED = {"CheckBandTouch", "RoomBandColor", "RoomY", "PlayerLives", "DropTarget",
        "Hover", "DropArm", "LevelPFDataLo", "LevelPFDataHi", "LevelRoomN",
        "RoomNo"}
L0 = parse_labels(FROZEN / "bank0.lst", NEED)
missing = NEED - L0.keys()
if missing:
    sys.exit(f"labels missing: {sorted(missing)}")
L2 = parse_labels(FROZEN / "bank2.lst",
                  {"LEVEL1_RoomDataTable", "LEVEL1_RoomEnemies"})
if not L2:
    sys.exit("bank2 level tables missing (frozen labels)")
# room count n for the level block, from the frozen emitted index (C4: the
# entry carries one base word + the count; 0x = LEVEL_DATA_STRIDE).
_INDEX = FROZEN.parent / "generated" / "levels_index.asm"
assert "LEVEL_DATA_STRIDE = 7" in _INDEX.read_text(), (
    "frozen level index is not the 7-byte layout — re-freeze the banks")
L2["LEVEL1_ROOMS"] = int(re.search(r"^\s*\.byte (\d+) ; LEVEL1 rooms",
                                   _INDEX.read_text(), re.M).group(1))
Z = {k: v & 0x7F for k, v in L0.items() if 0x80 <= v <= 0xFF}
BAND_ON = 0x1C                       # any non-zero staged band color byte
DROP_ARM = L0["DropArm"]


def run(room_y, band, lives=3, stage_level=False, stop_at_drop=0,
        max_steps=40000):
    """Drive CheckBandTouch and sample the state where it matters.

    The lose-a-life chain TAIL-JUMPS (`LoseLifeBand` -> `jmp DropArm` twice), so
    there is no rts to wait for on that path: stop at the Nth DropArm entry
    instead. Set stop_at_drop=0 for the inert paths (they rts normally)."""
    mem = Mem()
    mem.bank = 0
    r = mem.ram
    r[Z["RoomBandColor"]] = band
    r[Z["RoomY"]] = room_y
    r[Z["PlayerLives"]] = lives
    r[Z["DropTarget"]] = 0
    r[Z["Hover"]] = 0
    if stage_level:
        # the exhausted path reaches ReloadLevel, which folds the level tables:
        # point the level pointers at the frozen level-1 data (as
        # test_band_restage does) so the reload is real, not garbage.
        # C4 (2026-10-20): base + room count; RoomPositions/RoomEnemies are
        # the block's +2n/+3n offsets (C1 2026-10-20), derived by the readers.
        r[Z["LevelPFDataLo"]] = L2["LEVEL1_RoomDataTable"] & 0xFF
        r[Z["LevelPFDataHi"]] = L2["LEVEL1_RoomDataTable"] >> 8
        r[Z["LevelRoomN"]] = L2["LEVEL1_ROOMS"]
    mpu = MPU(memory=mem)
    mpu.pc = L0["CheckBandTouch"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    arms = 0
    for _ in range(max_steps):
        mpu.step()
        if mpu.pc == DROP_ARM:
            arms += 1
            if stop_at_drop and arms >= stop_at_drop:
                break
        elif not stop_at_drop and mpu.pc == RTS_SENTINEL:
            break
    return dict(room_y=r[Z["RoomY"]], lives=r[Z["PlayerLives"]],
                drop=r[Z["DropTarget"]], hover=r[Z["Hover"]], arms=arms)


def main() -> int:
    # 1. band off: nothing at any height
    for y in (124, 125, 132):
        s = run(y, 0)
        assert (s["lives"], s["drop"], s["room_y"]) == (3, 0, y), (
            f"band off at y={y} must be inert, got {s}")

    # 2. band on but still above the strip
    s = run(124, BAND_ON)
    assert (s["lives"], s["drop"], s["room_y"]) == (3, 0, 124), (
        f"y=124 is above the strip (>=125 kills): {s}")

    # 3/4. band on inside the strip: a life + the respawn destiny one tile up
    for y, want in ((125, 113), (132, 120)):
        s = run(y, BAND_ON, stop_at_drop=2)
        assert s["lives"] == 2, f"y={y}: expected 1 life lost, got {s}"
        assert s["room_y"] == want, (
            f"y={y}: respawn destiny RoomY {s['room_y']} != {want} (one tile "
            f"above the strip)")
        assert s["hover"], f"y={y}: respawn hover must be armed (bugs.md #1)"

    # 5. lives exhausted: the game-over path (today: reset to 3 + reload)
    s = run(132, BAND_ON, lives=0, stage_level=True, max_steps=60000)
    assert s["lives"] == 3, (
        f"exhausted lives must reset to 3 (the current game-over path), got {s}")

    print("test_water_band: OK (band off inert; >=125 loses a life and "
          "respawns one tile above the strip; exhausted lives reset to 3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
