#!/usr/bin/env python3
"""Frozen stage fixtures — the test-owned copy of game staging data.

User rule (2026-10-14): DO NOT stage tests from live game data (models.json,
generated/, ROM contents at current label addresses). The user keeps editing
stages; live-coupled tests break on every edit. Tests own their copies HERE,
in the tests folder, frozen at authoring time.

`freeze_m1` / `freeze_m2` inject the frozen bytes into a test's PRIVATE
bank*.bin copy (a bytearray the test already owns) at the CURRENT label
addresses parsed from bank*.lst — so the game's pointer-based reads
(StageBandTab MetaA/MetaB, the rect/hot stream walk) see the fixture,
while label moves stay harmless. Fixture blocks are written stream-first
then PF+meta so a shrunken live block's spill is overwritten by the
fixture itself.

Addresses may move with live data; bytes never change until someone
deliberately re-freezes here.

Converter-validation tests (test_cell_map, test_features_data,
test_asym_data, test_editor_roundtrip) are the sanctioned exception —
their job IS to track live data.

Run standalone:
  /home/iuri/python3/bin/python3 tools/test_fixtures.py
"""

# model1 — the bomb half-wall contract room (bugs.md #10).
# PF: rows PF0|PF1|PF2; row1 PF2 = $0C = the (14,1,2,1) thin wall
# (cols 14-15), the blast-window edge case the test proves.
M1_PF = bytes.fromhex("f0 30 f0 ff 00 ff 3f 0c ff")
M1_META = bytes.fromhex("00 00")              # MetaA, MetaB (no band/ball)
M1_STREAM = bytes.fromhex(
    "04 00 49 01 09 39 09 02 51"              # count 4 + packed rects
    "00")                                      # hot-record count 0

# model2 — the shipped vcrunch room (V at row1 col4, MetaB $80 shutter
# flag, hot $81 bbox record) — kill rides the overlay miss path.
# Count 0 (player pinned — no wall rects needed) so the stream fits the
# live 8-byte M2RoomRects slot: with 4 rects the 15-byte stream spilled
# into M2TilePF0 and the PF/meta freeze clobbered the $81 record (found
# 2026-10-14 once the no-op list-freeze was fixed and the arm went red).
M2_PF = bytes.fromhex("f0 30 30 00 0c ff 00 00 3f")
M2_META = bytes.fromhex("00 80")              # MetaA=0, MetaB b7=shutter
M2_STREAM = bytes.fromhex(
    "00 01 81 08 01 02 01")                   # 0 rects + 1 hot record:
                                              # $81,8,1,2,1 (y=1 — specials
                                              # sit on the middle band)


def _freeze(bank, labels, label, data):
    if label not in labels:
        raise SystemExit(f"test_fixtures: label {label} missing — "
                         "model block deleted; re-freeze or retire fixture")
    off = labels[label] - 0xF000
    bank[off:off + len(data)] = data


def _as_bank2(banks):
    # Tests hand us their W.BANKS/BANKS list of 4 banks; take bank2.
    # (A list passed straight to _freeze would slice-assign on the LIST —
    # a silent no-op at offset 0x9FF — caught 2026-10-14.)
    return banks[2] if isinstance(banks, (list, tuple)) else banks


def freeze_m1(banks, labels):
    """Inject the bomb-contract fixture (stream first, then PF+meta)."""
    bank2 = _as_bank2(banks)
    _freeze(bank2, labels, "M1RoomRects", M1_STREAM)
    _freeze(bank2, labels, "M1TilePF0", M1_PF + M1_META)


def freeze_m2(banks, labels):
    """Inject the vcrunch fixture (stream first, then PF+meta)."""
    bank2 = _as_bank2(banks)
    _freeze(bank2, labels, "M2RoomRects", M2_STREAM)
    _freeze(bank2, labels, "M2TilePF0", M2_PF + M2_META)


def _selfcheck():
    from pathlib import Path
    import re
    src = Path(__file__).resolve().parents[1] / "src"
    labels = {}
    for line in (src / "bank2.lst").read_text(errors="replace").splitlines():
        m = re.match(r"^\s+\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$",
                     line)
        if m:
            labels[m.group(2)] = int(m.group(1), 16)
    for name in ("M1RoomRects", "M1TilePF0", "M2RoomRects", "M2TilePF0"):
        if name not in labels:
            raise SystemExit(f"selfcheck FAIL: {name} missing in bank2.lst")
    bank = bytearray(open(src / "bank2.bin", "rb").read())
    freeze_m1(bank, labels)
    freeze_m2(bank, labels)
    # Assert the fitting prefix of each block (a stream shorter than the
    # fixture deliberately spills into the next block, which the PF/meta
    # freeze then overwrites — order documented in freeze_m*).
    for label, data, nxt in (
        ("M1RoomRects", M1_STREAM, "M1TilePF0"),
        ("M1TilePF0", M1_PF + M1_META, "M2RoomRects"),
        ("M2RoomRects", M2_STREAM, "M2TilePF0"),
        ("M2TilePF0", M2_PF + M2_META, "M3RoomRects"),
    ):
        off = labels[label] - 0xF000
        fit = min(len(data), labels[nxt] - labels[label])
        assert bytes(bank[off:off + fit]) == data[:fit], label
    # fixtures must be self-consistent with the walk/punch assumptions
    assert M1_STREAM[0] == 4 and len(M1_STREAM) == 1 + 8 + 1
    assert M2_STREAM[0] == 0 and len(M2_STREAM) == 1 + 1 + 5
    assert M1_PF[7] == 0x0C and M2_META[1] == 0x80 and M2_STREAM[2] == 0x81
    # the M2 stream must fit its slot with NO spill — a spill lands in
    # M2TilePF0 and the PF/meta freeze silently eats the $81 record
    m2gap = labels["M2TilePF0"] - labels["M2RoomRects"]
    assert len(M2_STREAM) <= m2gap, f"M2 stream {len(M2_STREAM)}B > slot {m2gap}B"
    print("test_fixtures: OK (freeze round-trip + fixture self-consistency)")


if __name__ == "__main__":
    _selfcheck()
