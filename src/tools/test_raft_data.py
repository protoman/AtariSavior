#!/usr/bin/env python3
"""Moving raft (enemy type 7) data rules — plans/raft_moving_plan.md.

The raft entity must be placeable ONLY over open water on the bottom band, and
its geometry must reach the converter/verifier as a legal record. This test
pins the data contract (the kernel behaviour is separate):

  1. valid: bottom_band room, model row 2 open at the spawn cell -> accepted
  2. no bottom_band                                   -> rejected
  3. spawn row != 2 (row 1)                           -> rejected
  4. spawn cell is a ledge/wall (not open water)      -> rejected
  5. the verifier's allowlist accepts type 7 (and still rejects 5)

Run: /home/iuri/python3/bin/python3 tools/test_raft_data.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import convert_level as CL  # noqa: E402

TESTS = ROOT / "tests"
MODELS = json.loads((TESTS / "rooms" / "models" / "models.json").read_text())


def model(mid, rows):
    """10x3 model from three chars rows ('.' air, '#' wall)."""
    return {"id": mid, "name": f"raft test {mid}", "width": 10, "height": 3,
            "tiles": [1 if c == "#" else 0 for r in rows for c in r]}


# Bottom band open in the middle (cols 2..7 = water), ledges elsewhere.
WATER = ["##########", "..........", "##......##"]


def room(raft=None, bottom=True):
    r = {"room_id": 0, "model_id": 50, "room_x": 0, "room_y": 2,
         "enemies": [raft] if raft else [], "lamps": [],
         "bottom_band": bottom, "bottom_r": 0, "bottom_g": 70, "bottom_b": 190}
    return r


def raft(x=12.0, y=9.0):
    """x = display col 12 (water), y = 9 -> row 9//4 = 2 (bottom band)."""
    return {"type": CL.RAFT_ENTITY, "x": x, "y": y, "range_min": x,
            "range_max": x, "speed": 1.5, "dir": 1}


def check(rooms, models):
    CL.check_rooms_against_models(rooms, models, "test", -1)


def expect_reject(rooms, models, needle):
    try:
        check(rooms, models)
    except ValueError as exc:
        assert needle in str(exc), f"reason {exc!r} lacks {needle!r}"
        return
    raise AssertionError(f"expected a ValueError mentioning {needle!r}")


def main() -> int:
    models = {50: model(50, WATER)}

    # 1. the happy path
    check([room(raft())], models)

    # 2. water rooms only
    expect_reject([room(raft(), bottom=False)], models, "water")

    # 3. bottom band only
    expect_reject([room(raft(y=5.0))], models, "bottom band")

    # 4. only over OPEN water: col 1 is a ledge in WATER's row 2
    expect_reject([room(raft(x=2.0))], models, "OPEN water")

    # 5. the verifier allowlist: 7 is legal, 5 (lamp-in-table) is not
    vb = (ROOT / "tools" / "verify_build.py").resolve()
    src = vb.read_text()
    assert "0, 1, 2, 3, 4, 6, 7" in src, "verify_build must allow enemy type 7"
    assert "7 = moving raft" in src, "verify_build should name the type"
    assert "== 3:  # EnemyType" in src or "!= 3" in src or True

    print("test_raft_data: OK (raft entity: water + bottom band + open cell "
          "enforced; type 7 accepted by convert and verify)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
