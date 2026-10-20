#!/usr/bin/env python3
"""Frozen stage fixtures — the test-owned copy of game staging data.

User rule (2026-10-14): DO NOT stage tests from live game data (models.json,
generated/, ROM contents at current label addresses). The user keeps editing
stages; live-coupled tests break on every edit. Tests own their copies HERE,
in the tests folder, frozen at authoring time.

`freeze_m0` / `freeze_m2` / `freeze_m4` inject the frozen STREAM bytes into
a test's PRIVATE bank*.bin copy (a bytearray the test already owns) at the
CURRENT label addresses parsed from bank*.lst, so the game's hot-stream walk
sees the fixture while label moves stay harmless.

C5 (2026-10-20): a shape block is `hot stream | PF triple` — the MetaA/MetaB
pair moved to the room extras and `TilePF0+9/+10` is retired. Test harnesses
therefore take the PF and the meta pair from the FROZEN CONSTANTS here
(`PFX` / `METAX`) instead of reading them out of ROM: the fixture block only
has to hold the (small) stream, which fits inside the live 10 B shape.

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
# 1+6+1 = 8B = the exact L1R1RoomRects->L1R1TilePF0 slot (a 4th rect spills
# the hot count into the PF block — same trap that ate the $81 record
# in the M2 fixture).
M0_PF = bytes.fromhex("f0 30 f0 ff 00 ff 3f 0c ff")
M0_META = bytes.fromhex("00 00")              # MetaA, MetaB (no band/ball)
M0_STREAM = bytes.fromhex(
    "00")                                      # C4 2026-10-20: hot count ONLY
                                              # — the solid rect list is
                                              # retired (cell collision), so
                                              # the block is hot | PF | meta

# model2 — the shipped vcrunch room (V at row1 col4, MetaB $80 shutter
# flag, hot $81 bbox record) — kill rides the overlay miss path.
# Count 0 (player pinned — no wall rects needed) so the stream fits the
# live 8-byte M2RoomRects slot: with 4 rects the 15-byte stream spilled
# into M2TilePF0 and the PF/meta freeze clobbered the $81 record (found
# 2026-10-14 once the no-op list-freeze was fixed and the arm went red).
M2_PF = bytes.fromhex("f0 30 30 00 0c ff 00 00 3f")
M2_META = bytes.fromhex("00 80")              # MetaA=0, MetaB b7=shutter
M2_STREAM = bytes.fromhex(
    "01 81 08 01 02 01")                      # C4 2026-10-20: hot count 1
                                              # + record $81,8,1,2,1 (y=1:
                                              # specials sit on the middle band)

# model4 — the shipped hcrunch room (level 3 room 2, $82 prefix shutter on
# band1, sweep extent cols 0-19 = the whole left half to screen center).
# Stream = 1+6+1+5 = 13B = the exact L3R2RoomRects -> L3R2TilePF0 slot;
# PF+meta = 11B = the exact L3R2TilePF0 -> M5RoomRects slot.
# Re-frozen 2026-10-16: C cells dropped from static rects (convert_room
# solids "#HPV") — the C+row2 merged rect is now the row2 wall rect
# ($02,$11); record w=4 -> w=20 (full = 10 cells = to the center).
M4_PF = bytes.fromhex("f0 f0 f0 ff ff 3f 3f 00 ff")  # TilePF1 row1 = $FF
                                                  # (C sweep area PF-lit raw;
                                                  # staging trims to P(n))
M4_META = bytes.fromhex("00 00")              # MetaA, MetaB (cold: no b6/b7)
M4_STREAM = bytes.fromhex(
    "01"                                      # C4 2026-10-20: hot count 1
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
    # C2 (2026-10-20): the level/model BLOCKS moved from bank3 into bank2.
    # Tests hand us their BANKS list of 4 banks; inject into bank2's image and
    # pass labels parsed from bank2.lst. (A list passed straight to _freeze
    # would slice-assign on the LIST — a silent no-op at offset 0x9FF —
    # caught 2026-10-14.)
    return banks[2] if isinstance(banks, (list, tuple)) else banks


# Test-owned PF triple + staged meta pair per fixture model (C5: the ROM no
# longer carries the meta inside the shape block, and the fixture stream may
# overwrite PF bytes — harnesses use these constants instead).
PFX = {0: M0_PF, 2: M2_PF, 4: M4_PF}
METAX = {0: M0_META, 2: M2_META, 4: M4_META}


def freeze_m0(banks, labels):
    """Inject the bomb-contract stream at the shared model-0 shape."""
    bank2 = _as_bank2(banks)
    _freeze(bank2, labels, "M0RoomRects", M0_STREAM)


def freeze_m2(banks, labels):
    """Inject the (inert) $81 stream at the shared model-2 shape."""
    bank2 = _as_bank2(banks)
    _freeze(bank2, labels, "M2RoomRects", M2_STREAM)


def freeze_m4(banks, labels):
    """Inject the hcrunch $82 stream at the shared model-4 shape."""
    bank2 = _as_bank2(banks)
    _freeze(bank2, labels, "M4RoomRects", M4_STREAM)


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
                 "M4RoomRects", "M4TilePF0"):
        if name not in labels:
            raise SystemExit(f"selfcheck FAIL: {name} missing in bank2.lst")
    bank = bytearray(open(src / "bank2.bin", "rb").read())
    freeze_m0(bank, labels)
    freeze_m2(bank, labels)
    freeze_m4(bank, labels)
    # Streams land at the block base and must fit BETWEEN base and TilePF0
    # (C4: TilePF0 = block + 1 + 5*hot). M0's stream is a single count byte;
    # the synthetic $81/$82 streams overwrite the first PF bytes, which the
    # harnesses never read (PFX is test-owned).
    for tag, stream, base, pf in (
        ("M0", M0_STREAM, "M0RoomRects", "M0TilePF0"),
        ("M2", M2_STREAM, "M2RoomRects", "M2TilePF0"),
        ("M4", M4_STREAM, "M4RoomRects", "M4TilePF0"),
    ):
        off = labels[base] - 0xF000
        fit = min(len(stream), labels[pf] - labels[base])
        assert bytes(bank[off:off + fit]) == stream[:fit], tag
    # fixtures must be self-consistent with the walk/punch assumptions
    assert M0_STREAM[0] == 0 and len(M0_STREAM) == 1      # hot count only
    assert M2_STREAM[0] == 1 and len(M2_STREAM) == 1 + 5
    assert M4_STREAM[0] == 1 and len(M4_STREAM) == 1 + 5
    assert M0_PF[7] == 0x0C and M2_META[1] == 0x80 and M2_STREAM[1] == 0x81
    assert M4_STREAM[1] == 0x82
    assert M4_META == b"\x00\x00" and M4_STREAM[2:6] == bytes([0, 1, 20, 1])
    # C5: no fixture block carries a meta tail any more (TilePF0+9/+10 gone)
    assert len(M0_PF) == 9 and len(M2_PF) == 9 and len(M4_PF) == 9
    assert all(len(v) == 2 for v in METAX.values())
    print("test_fixtures: OK (freeze round-trip + fixture self-consistency)")


if __name__ == "__main__":
    _selfcheck()
