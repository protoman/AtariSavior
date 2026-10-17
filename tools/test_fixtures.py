#!/usr/bin/env python3
"""Frozen stage fixtures — the test-owned copy of game staging data.

User rule (2026-10-14): DO NOT stage tests from live game data (models.json,
generated/, ROM contents at current label addresses). The user keeps editing
stages; live-coupled tests break on every edit. Tests own their copies HERE,
in the tests folder, frozen at authoring time.

`freeze_m0` / `freeze_m2` inject the frozen bytes into a test's PRIVATE
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

# model0 — the bomb half-wall contract room (bugs.md #10), ALSO the
# game's boot room: the real EnterRoom (level-1 room0) restages from the
# M0 labels every time it runs — a fixture parked at M1 gets silently
# overwritten by live M0 bytes (found 2026-10-16 when the user's model
# edit made the live bytes diverge from the fixture and the bomb punch
# stopped seeing its wall). PF: rows PF0|PF1|PF2; row1 PF2 = $0C = the
# (14,1,2,1) thin wall (cols 14-15), the blast-window edge case the
# test proves. Stream: 3 rects (ceiling dropped — the blast row is 1),
# 1+6+1 = 8B = the exact M0RoomRects->M0TilePF0 slot (a 4th rect spills
# the hot count into the PF block — same trap that ate the $81 record
# in the M2 fixture).
M0_PF = bytes.fromhex("f0 30 f0 ff 00 ff 3f 0c ff")
M0_META = bytes.fromhex("00 00")              # MetaA, MetaB (no band/ball)
M0_STREAM = bytes.fromhex(
    "03 01 09 39 09 02 51"                    # count 3 + packed rects:
                                              # (0,1,2,1) border, (14,1,2,1)
                                              # thin wall, (0,2,20,1) floor
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

# model4 — the shipped hcrunch room (level 3 room 2, $82 prefix shutter on
# band1, sweep extent cols 0-19 = the whole left half to screen center).
# Stream = 1+6+1+5 = 13B = the exact M4RoomRects -> M4TilePF0 slot;
# PF+meta = 11B = the exact M4TilePF0 -> M5RoomRects slot.
# Re-frozen 2026-10-16: C cells dropped from static rects (convert_room
# solids "#HPV") — the C+row2 merged rect is now the row2 wall rect
# ($02,$11); record w=4 -> w=20 (full = 10 cells = to the center).
M4_PF = bytes.fromhex("f0 f0 f0 ff ff 3f 3f 00 ff")  # TilePF1 row1 = $FF
                                                  # (C sweep area PF-lit raw;
                                                  # staging trims to P(n))
M4_META = bytes.fromhex("00 00")              # MetaA, MetaB (cold: no b6/b7)
M4_STREAM = bytes.fromhex(
    "03 00 49 02 11 1a 39"                    # count 3 + packed rects:
                                              # (0,0,18,1) ceiling band0,
                                              # (0,2,4,1) row2 wall cols0-1,
                                              # (6,2,14,1) floor
    "01"                                      # hot-record count 1
    "82 00 01 14 01")                         # $82, x=0, y=1 (band1),
                                              # w=20 (4px cols = 10 cells =
                                              # to the center), h=1


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


def freeze_m0(banks, labels):
    """Inject the bomb-contract fixture (stream first, then PF+meta)."""
    bank2 = _as_bank2(banks)
    _freeze(bank2, labels, "M0RoomRects", M0_STREAM)
    _freeze(bank2, labels, "M0TilePF0", M0_PF + M0_META)


def freeze_m2(banks, labels):
    """Inject the vcrunch fixture (stream first, then PF+meta)."""
    bank2 = _as_bank2(banks)
    _freeze(bank2, labels, "M2RoomRects", M2_STREAM)
    _freeze(bank2, labels, "M2TilePF0", M2_PF + M2_META)


def freeze_m4(banks, labels):
    """Inject the hcrunch fixture (stream first, then PF+meta)."""
    bank2 = _as_bank2(banks)
    _freeze(bank2, labels, "M4RoomRects", M4_STREAM)
    _freeze(bank2, labels, "M4TilePF0", M4_PF + M4_META)


def _selfcheck():
    from pathlib import Path
    import re
    src = (Path(__file__).resolve().parents[1] / "src" / "tests" / "frozen")
    # ^ test-owned frozen banks+labels (user rule: never live src/)
    labels = {}
    for line in (src / "bank2.lst").read_text(errors="replace").splitlines():
        m = re.match(r"^\s+\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$",
                     line)
        if m:
            labels[m.group(2)] = int(m.group(1), 16)
    for name in ("M0RoomRects", "M0TilePF0", "M2RoomRects", "M2TilePF0",
                 "M4RoomRects", "M4TilePF0", "M5RoomRects"):
        if name not in labels:
            raise SystemExit(f"selfcheck FAIL: {name} missing in bank2.lst")
    bank = bytearray(open(src / "bank2.bin", "rb").read())
    freeze_m0(bank, labels)
    freeze_m2(bank, labels)
    freeze_m4(bank, labels)
    # Assert the fitting prefix of each block (a stream shorter than the
    # fixture deliberately spills into the next block, which the PF/meta
    # freeze then overwrites — order documented in freeze_m*).
    for label, data, nxt in (
        ("M0RoomRects", M0_STREAM, "M0TilePF0"),
        ("M0TilePF0", M0_PF + M0_META, "M1RoomRects"),
        ("M2RoomRects", M2_STREAM, "M2TilePF0"),
        ("M2TilePF0", M2_PF + M2_META, "M3RoomRects"),
        ("M4RoomRects", M4_STREAM, "M4TilePF0"),
        ("M4TilePF0", M4_PF + M4_META, "M5RoomRects"),
    ):
        off = labels[label] - 0xF000
        fit = min(len(data), labels[nxt] - labels[label])
        assert bytes(bank[off:off + fit]) == data[:fit], label
    # fixtures must be self-consistent with the walk/punch assumptions
    assert M0_STREAM[0] == 3 and len(M0_STREAM) == 1 + 6 + 1
    assert M2_STREAM[0] == 0 and len(M2_STREAM) == 1 + 1 + 5
    assert M4_STREAM[0] == 3 and len(M4_STREAM) == 1 + 6 + 1 + 5
    assert M0_PF[7] == 0x0C and M2_META[1] == 0x80 and M2_STREAM[2] == 0x81
    assert M4_STREAM[7] == 1 and M4_STREAM[8] == 0x82
    assert M4_META == b"\x00\x00" and M4_STREAM[9:13] == bytes([0, 1, 20, 1])
    # both streams must fit their slots with NO spill — an M0 spill puts
    # the hot count inside the PF block; an M2 spill eats the $81 record
    # (an M4 spill has the same trap: hot count / $82 inside the PF block)
    for tag, stream, a, b in (
        ("M0", M0_STREAM, "M0RoomRects", "M0TilePF0"),
        ("M2", M2_STREAM, "M2RoomRects", "M2TilePF0"),
        ("M4", M4_STREAM, "M4RoomRects", "M4TilePF0"),
    ):
        gap = labels[b] - labels[a]
        assert len(stream) <= gap, f"{tag} stream {len(stream)}B > slot {gap}B"
    assert len(M4_PF + M4_META) <= labels["M5RoomRects"] - labels["M4TilePF0"]
    print("test_fixtures: OK (freeze round-trip + fixture self-consistency)")


if __name__ == "__main__":
    _selfcheck()
