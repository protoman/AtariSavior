#!/usr/bin/env python3
"""Tile 11 (VCRUNCH) removal guard.

Contract (user decision 2026-10-19): the vertical-crunch feature is GONE.
No room in the stage uses it, so there is no data migration — but every
layer must fail loudly if the retired tile shows up again:

  1. converter: convert_level.rows_from_json / convert_room.lines reject a
     model tile 11 and a grid 'V' with "tile 11 (VCRUNCH) removed; use
     PHASE 10";
  2. converter CLI: a temp copy of a TEST-OWNED level (src/tests/rooms —
     never src/rooms) carrying a tile-11 feature cell fails with rc=1 and
     that message;
  3. ROM: no bank source or generated block emits a $81 feature record and
     the retired kernel/bank3 Vcr* state is gone.

Run: /home/iuri/python3/bin/python3 tools/test_vcr_shutter.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SRC = TOOLS.parent / "src"
sys.path.insert(0, str(TOOLS))

import convert_level  # noqa: E402
import convert_room  # noqa: E402

MSG = "tile 11 (VCRUNCH) removed; use PHASE 10"


def expect_reject(fn, tag):
    try:
        fn()
    except ValueError as exc:
        assert MSG in str(exc), f"{tag}: wrong error {exc!r}"
        return
    raise AssertionError(f"{tag}: tile 11 was accepted")


# --- 1. converter layers reject the tile -------------------------------------
tiles = [0] * 30
tiles[10] = 11                      # model grid tile 11 (row 1, col 0)
expect_reject(
    lambda: convert_level.rows_from_json(
        {"model_id": 91}, {91: {"id": 91, "width": 10, "height": 3,
                                "tiles": tiles}}),
    "model grid")
expect_reject(
    lambda: convert_level.room_feature_cells(
        {"room_id": 0, "feature_cells": [[1, 0, 11]]}),
    "room feature cell")
expect_reject(
    lambda: convert_room.lines(["V" + "." * 9, "." * 10, "." * 10],
                               prefix="M91", source="test"),
    "grid char")

# --- 2. CLI over a temp copy of a TEST-OWNED level ---------------------------
src_rooms = SRC / "tests" / "rooms"
level_src = src_rooms / "level_001.json"
assert level_src.exists(), "test-owned level missing: src/tests/rooms"


def run_cli(rooms_dir: Path, out_prefix: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / "convert_level.py"),
         str(rooms_dir / "level_001.json"), str(out_prefix), str(rooms_dir)],
        capture_output=True, text=True)


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    rooms = tmp / "rooms"
    shutil.copytree(src_rooms, rooms)
    models = rooms / "models" / "models.json"
    assert models.exists(), "test-owned models.json missing"
    level = json.loads((rooms / "level_001.json").read_text())
    if "level" in level:            # cereal wrapper
        level = level["level"]
        wrapped = True
    else:
        wrapped = False
    level["rooms"][0]["feature_cells"] = [[1, 0, 11]]
    payload = {"level": level} if wrapped else level
    (rooms / "level_001.json").write_text(json.dumps(payload))
    out = tmp / "generated" / "level_001"
    out.parent.mkdir()
    res = run_cli(rooms, out)
    assert res.returncode == 1, f"CLI accepted tile 11 (rc={res.returncode})"
    assert MSG in (res.stderr + res.stdout), res.stderr[-300:]

    # clean copy converts fine (the fixture itself is not broken)
    shutil.rmtree(rooms)
    shutil.copytree(src_rooms, rooms)
    res = run_cli(rooms, out)
    assert res.returncode == 0, res.stderr[-300:]

# --- 3. no $81 records / retired state in the shipped sources ----------------
# NOTE: only files that can EMIT a record are scanned for the raw $81 byte —
# sprite art rows are hex too and $81 is a legal GRP1 row (BAT row 0, 2026-10-22),
# so scanning kernel.asm for `$81,` is a false positive. Symbols stay global.
for path in list(SRC.glob("generated/*.asm")) + [SRC / "bank3.asm"]:
    text = path.read_text(errors="replace")
    assert not re.search(r"\.byte\s+\$81,", text), \
        f"{path.name}: emits a retired $81 vcrunch record"
for path in (SRC / "kernel.asm", SRC / "bank2.asm", SRC / "bank3.asm"):
    text = path.read_text()
    for token in ("VcrBand", "VcrNext", "VcrState", "VcrShutter", "VCS3",
                  "OvShutScan"):
        assert token not in text, f"{path.name}: retired symbol {token}"

print("test_vcr_shutter: OK (tile 11 rejected at converter + CLI; no $81 "
      "records or retired Vcr* state in the ROM sources)")
