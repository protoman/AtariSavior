#!/usr/bin/env python3
"""Asymmetric-PF encoder fixture (asymmetric_pf_plan Phase 0 / CHECK 0).

Proves D4: right-half register bytes under reflect. The TIA with CTRLPF D0=1
maps right logical cell k to logical cell (WIDTH-1-k); under D7 each logical
cell is a PF bit PAIR (2c, 2c+1), so a right-half pattern B (10 cols, col 0
adjacent to center) renders correctly only if the stored trio =
pf_values(reversed(B)) — pf_values does the pairing.

Pure python, no py65: derives bytes for a hand-checkable pattern and renders
them back through a reflect-mode TIA model, asserting the screen equals B.
Run: /home/iuri/python3/bin/python3 tools/test_asym_encoder.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_room import pf_values, WIDTH


def encode_right(b_cols: str) -> tuple[int, int, int]:
    """Right-half pattern (WIDTH logical cols, '#'=wall, col0 = center-
    adjacent) -> PF trio to store for the late (right-paint) write."""
    assert len(b_cols) == WIDTH
    return pf_values(b_cols[::-1])


def render_cell(pf: tuple[int, int, int], cell: int) -> bool:
    """Register cell 0-19 -> solid? (pf_values bit convention)."""
    pf0, pf1, pf2 = pf
    if cell < 4:
        return bool(pf0 & (0x10 << cell))
    if cell < 12:
        return bool(pf1 & (0x80 >> (cell - 4)))
    return bool(pf2 & (0x01 << (cell - 12)))


def render_right_half(pf: tuple[int, int, int]) -> str:
    """Reflect mode: right logical col k shows logical col (WIDTH-1-k),
    i.e. register pair cells (2*(WIDTH-1-k), 2*(WIDTH-1-k)+1) (equal by
    bit-pairing)."""
    return "".join(
        "#" if render_cell(pf, 2 * (WIDTH - 1 - k)) else "." for k in range(WIDTH))


def main() -> int:
    # Hand-derived fixture: right half all wall except a 2-cell gap at the
    # center-adjacent columns 0-1 (D7: 10 logical cols).
    #   reverse(B) = wall cols 0-7, gap cols 8-9
    #   paired: register cells 0-15 solid, 16-19 open
    #   pf0 = $F0 (cells 0-3), pf1 = $FF (cells 4-11),
    #   pf2 = $0F (cells 12-15 set -> bits 0-3; 16-19 open)
    b = ".." + "#" * 8
    got = encode_right(b)
    expected = (0xF0, 0xFF, 0x0F)
    assert got == expected, f"encode: got ${got[0]:02X},${got[1]:02X},${got[2]:02X}" \
                            f" want ${expected[0]:02X},${expected[1]:02X},${expected[2]:02X}"
    # Render check: reflect-mode right half must reproduce B.
    screen = render_right_half(got)
    assert screen == b, f"render: {screen!r} != {b!r}"

    # Second fixture: off-center shaft — gap at right logical cols 3-4 only.
    #   reverse = wall 0-4, gap 5-6, wall 7-9
    #   paired: cells 0-9 solid, 10-13 open, 14-19 solid
    #   pf0 $F0; pf1 cells4-11 = solid(4-9)+open(10,11) -> bits7-2 set -> $FC;
    #   pf2 cells12-19 = open(12,13)+solid(14-19) -> bits0-1 clear,
    #   bits2-7 set -> $FC
    b2 = "###" + ".." + "#" * 5
    got2 = encode_right(b2)
    assert render_right_half(got2) == b2
    assert got2 == (0xF0, 0xFC, 0xFC), \
        f"encode2: ${got2[0]:02X},${got2[1]:02X},${got2[2]:02X} want $F0,$FC,$FC"

    # Third: symmetric round trip — a left-half row pattern via today's
    # pf_values, mirrored right must render its mirror (baseline unchanged).
    left = "####..####"          # 10 logical cols, any shape
    pf_l = pf_values(left)
    mirrored = "".join(left[WIDTH - 1 - k] for k in range(WIDTH))
    assert render_right_half(pf_l) == mirrored

    print("test_asym_encoder: OK (3 fixtures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
