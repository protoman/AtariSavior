#!/usr/bin/env python3
"""Frozen stage fixtures — the test-owned copy of game staging data.

User rule (2026-10-14): DO NOT stage tests from live game data (models.json,
generated/, ROM contents at current label addresses). The user keeps editing
stages; live-coupled tests break on every edit. Tests own their copies HERE,
in the tests folder, frozen at authoring time.

C11 (2026-10-21): a SHAPE block is EXACTLY 3 row-pool indices (band 0/1/2,
band 1's b7 = `mid_band_type`) — there is no hot stream to inject into a
block any more. Hot collision is derived from the PF row 1 the loader
expands, so the harnesses:

  * take the PF and the meta pair from the FROZEN CONSTANTS here
    (`PFX` / `METAX`) and stage them directly into a test's private RAM,
  * point `RoomRectsLo/Hi` at bank3's static `$00` count (`RoomNoStream`)
    when the room has no record stream — never at a shape block,
  * stage a synthetic FEATURE-record stream (`M2_STREAM` / `M4_STREAM`) in
    test-owned RAM when the test drives the feature dispatcher.

Addresses may move with live data; bytes never change until someone
deliberately re-freezes here.

Converter-validation tests (test_cell_map, test_features_data,
test_asym_data, test_editor_roundtrip) are the sanctioned exception —
their job IS to track live data.

Run standalone:
  /home/iuri/python3/bin/python3 tools/test_fixtures.py
"""

# model0 — the bomb half-wall contract room (bugs.md #10), ALSO the
# game's boot room. PF: rows PF0|PF1|PF2; row1 PF2 = $0C = the (14,1,2,1)
# thin wall (cols 14-15), the blast-window edge case the test proves.
M0_PF = bytes.fromhex("f0 30 f0 ff 00 ff 3f 0c ff")
M0_META = bytes.fromhex("00 00")              # MetaA, MetaB (no band/ball)

# model2 — the retired vcrunch room (V at row1 col4, MetaB $80 shutter flag,
# $81 bbox record). C11: the record stream is synthetic RAM data now
# (count 1 + record $81,8,1,2,1); y=1 because specials sit on band 1.
M2_PF = bytes.fromhex("f0 30 30 00 0c ff 00 00 3f")
M2_META = bytes.fromhex("00 80")              # MetaA=0, MetaB b7=shutter
M2_STREAM = bytes.fromhex(
    "01 81 08 01 02 01")                      # count 1 + class,x,y,w,h

# model4 — the shipped hcrunch room (level 3 room 2, $82 prefix shutter on
# band1, sweep extent cols 0-19 = the whole left half to screen center).
M4_PF = bytes.fromhex("f0 f0 f0 ff ff 3f 3f 00 ff")  # TilePF1 row1 = $FF
                                                  # (C sweep area PF-lit raw;
                                                  # staging trims to P(n))
M4_META = bytes.fromhex("00 00")              # MetaA, MetaB (cold: no b6/b7)
M4_STREAM = bytes.fromhex(
    "01"                                      # count 1
    "82 00 01 14 01")                         # $82, x=0, y=1 (band1),
                                              # w=20 (4px cols = 10 cells =
                                              # to the center), h=1

# Test-owned PF triple + staged meta pair per fixture model (C5: the ROM no
# longer carries the meta inside the shape block, and the loader expands the
# row-pool indices — harnesses use these constants instead).
PFX = {0: M0_PF, 2: M2_PF, 4: M4_PF}
METAX = {0: M0_META, 2: M2_META, 4: M4_META}


def stage_stream(ram: bytearray, addr: int, blob: bytes) -> None:
    """Write a synthetic record stream into a test's private ZP RAM image
    and return nothing — the caller stages RoomRectsLo/Hi at `addr`."""
    ram[addr - 0x80:addr - 0x80 + len(blob)] = blob


def check(banks, labels) -> None:
    """Self-consistency: every frozen label the harnesses use must resolve."""
    for label in ("M0Shape", "M2Shape", "M4Shape", "RoomNoStream"):
        if label not in labels:
            raise SystemExit(f"test_fixtures: label {label} missing in "
                             "bank3.lst — re-freeze or retire the fixture")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    from test_cell_map import parse_labels  # noqa: PLC0415
    lab = parse_labels(root / "src" / "tests" / "frozen" / "bank3.lst",
                       {"M0Shape", "M2Shape", "M4Shape", "RoomNoStream"})
    check(None, lab)
    for name, blob in (("M2", M2_STREAM), ("M4", M4_STREAM)):
        count = blob[0]
        assert len(blob) == 1 + 5 * count, f"{name}_STREAM stride != 1+5n"
        assert blob[1] & 0x80, f"{name}_STREAM class must be a feature record"
    assert len(M0_PF) == 9 and len(M2_PF) == 9 and len(M4_PF) == 9
    print("test_fixtures: OK (labels resolve; record streams 1+5n with b7 "
          "feature classes; PF triples 9 B)")
