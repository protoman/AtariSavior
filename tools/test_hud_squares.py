#!/usr/bin/env python3
"""HUD squares (2026-10-26): lives/bombs/miners squares sit 8 px apart.

User request: "decrease by half the spacing between the squares (lives and
bombs)" and "purple squares ... right aligned in the bombs row". The HUD draws
them with QUAD-size players (NUSIZ $07: one GRP bit = 4 px), so squares on every
other bit are 8 px apart (the old NUSIZ copies were 16 px apart). The 5th bomb is
a 4 px missile (NUSIZ0 $27). The miners-left row is P1 (quad) with the squares
packed to the RIGHT end of the sprite.

Checks the frozen bank1 tables (SquarePat / MinerPat) against that contract. The
on-screen result was measured in Stella (squares 8 px wide in the 320 px snap,
16 px pitch = 8 TIA px; purple row ending at x=151).
Run: /home/iuri/python3/bin/python3 tools/test_hud_squares.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import BANK1, parse_labels, FROZEN  # noqa: E402

L = parse_labels(FROZEN / "bank1.lst", {"SquarePat", "MinerPat"})
assert {"SquarePat", "MinerPat"} <= L.keys(), "frozen bank1.lst lacks the tables"
sq = BANK1[L["SquarePat"] - 0xF000:][:6]
mp = BANK1[L["MinerPat"] - 0xF000:][:8]


def squares(pat):
    """-> left edge (in 4 px units) of every lit square; adjacent bits = one
    wide block, which would read as a bar, not squares."""
    bits = [i for i in range(8) if pat & (0x80 >> i)]
    assert all(b - a >= 2 for a, b in zip(bits, bits[1:])), \
        f"pattern ${pat:02X} has touching squares"
    return bits


for n in range(5):
    assert len(squares(sq[n])) == n, f"SquarePat[{n}]=${sq[n]:02X}"
    s = squares(sq[n])
    assert all(b - a == 2 for a, b in zip(s, s[1:])), \
        f"SquarePat[{n}] pitch != 8 px (2 bits of 4 px)"
    assert not s or s[0] == 0, f"SquarePat[{n}] must start at the left edge"
assert sq[5] == sq[4], "5 bombs: the 5th square is missile 0, P0 stays at 4"

for mask in range(8):
    want = bin(mask).count("1")
    s = squares(mp[mask])
    assert len(s) == want, f"MinerPat[{mask}]=${mp[mask]:02X}: {len(s)} != {want}"
    assert all(b - a == 2 for a, b in zip(s, s[1:])), "miner pitch != 8 px"
    if want:
        assert s[-1] == 7, f"MinerPat[{mask}]: last square must be on bit 0 " \
                           "(right aligned)"
print("test_hud_squares: OK (8 px pitch, 5th bomb = missile, miners right aligned)")
