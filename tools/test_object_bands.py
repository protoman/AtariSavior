#!/usr/bin/env python3
"""Object separation: two objects must never share a band or a display column.

ONE GRP1 draws every cave object. `StageSlot1` (bank2) pairs two objects only
when they sit in DIFFERENT bands, so a same-band pair keeps the 30 Hz rotation
and both blink. Different bands are not enough either: objects move inside
their band (moth/bat/snake patrol rows), so a shared display column means they
periodically land on the same scanlines and the pairing drops for those frames.

User report 2026-10-25: level 5 room 2, "still lots of flicker" — both enemies
sat at display column 19 (rows 7 and 10). The generator now runs a final
separation pass (DataSerializer.cpp) and convert_level enforces the same rule
as a BUILD ERROR (BAND_RULE_HARD = True), so the stage can never ship a pair
again.

Run: /home/iuri/python3/bin/python3 tools/test_object_bands.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import convert_level as C  # noqa: E402

# 4-band model: band = y_row // units_per_band = row // 3.
MODEL = {"id": 1, "width": 10, "height": 4,
         "tiles": [0] * 40, "mid_band_type": 0}
MODELS = {1: MODEL}


def fails(room, why):
    try:
        C.check_rooms_against_models([room], MODELS, "test")
    except ValueError as exc:
        msg = str(exc)
        assert why in msg, f"raised the WRONG error for {why}: {msg}"
        return
    raise AssertionError(f"NOT REJECTED: {why}")


def passes(room, why):
    try:
        C.check_rooms_against_models([room], MODELS, "test")
    except ValueError as exc:
        raise AssertionError(f"wrongly rejected ({why}): {exc}") from None


def enemy(x, y):
    return {"type": 0, "x": float(x), "y": float(y), "dir": 1}


def lamp(x, y):
    return {"x": float(x), "y": float(y)}


base = {"model_id": 1, "enemies": [], "lamps": []}

# 1) the reported case: two enemies, one band, one column
fails(dict(base, enemies=[enemy(19, 7), enemy(19, 10)]), "share display column")
# 2) same band, different columns: one GRP1 cannot draw both at all
fails(dict(base, enemies=[enemy(4, 7), enemy(14, 8)]), "objects in band 2")
# 3) different bands, columns 3 apart: legal (the generator's minimum)
passes(dict(base, enemies=[enemy(16, 7), enemy(19, 10)]), "3 columns apart")
# 4) different bands, 2 columns apart: the flare the rule exists for
fails(dict(base, enemies=[enemy(17, 7), enemy(19, 10)]), "share display column")
# 5) a lamp is an object too
fails(dict(base, enemies=[enemy(19, 7)], lamps=[lamp(19, 10)]),
      "share display column")
# 6) one object, no pair: always fine
passes(dict(base, enemies=[enemy(19, 7)]), "single object")

print("test_object_bands: OK (same band, same column, lamp pairs rejected; "
      ">=3 columns apart accepted)")
