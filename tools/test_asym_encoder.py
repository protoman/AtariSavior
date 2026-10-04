#!/usr/bin/env python3
"""Asymmetric-PF encoder fixture (asymmetric_pf_plan Phase 0 / CHECK 0).

Proves D4: right-half register bytes under reflect. The TIA with CTRLPF D0=1
maps right screen cell (20+k) to register cell (19-k), so a right-half pattern
B (cols 0-19, col 0 adjacent to center) renders correctly only if the stored
trio = pf_values(reversed(B)).

Pure python, no py65: derives bytes for a hand-checkable pattern and renders
them back through a reflect-mode TIA model, asserting the screen equals B.
Run: /home/iuri/python3/bin/python3 tools/test_asym_encoder.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_room import pf_values, WIDTH


def encode_right(b_cols: str) -> tuple[int, int, int]:
    """Right-half pattern (20 cols, '#'=wall, col0 = center-adjacent) ->
    PF trio to store for the late (right-paint) write."""
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
    """Reflect mode: right screen cell (20+k) shows register cell (19-k)."""
    return "".join("#" if render_cell(pf, 19 - k) else "." for k in range(WIDTH))


def main() -> int:
    # Hand-derived fixture: right half all wall except a 2-cell gap at the
    # center-adjacent columns 0-1 (screen cells 20-21).
    #   reverse(B) = wall cols 0-17, gap cols 18-19
    #   pf0 = $F0 (cols 0-3), pf1 = $FF (cols 4-11), pf2 = $3F (cols 18-19 clear
    #   -> bits 6,7 = 0 in pf_values' bit (col-12) convention)
    b = ".." + "#" * 18
    got = encode_right(b)
    expected = (0xF0, 0xFF, 0x3F)
    assert got == expected, f"encode: got ${got[0]:02X},${got[1]:02X},${got[2]:02X}" \
                            f" want ${expected[0]:02X},${expected[1]:02X},${expected[2]:02X}"
    # Render check: reflect-mode right half must reproduce B.
    screen = render_right_half(got)
    assert screen == b, f"render: {screen!r} != {b!r}"

    # Second fixture: off-center shaft — gap at right cols 3-4 only.
    b2 = "###" + ".." + "#" * 15
    got2 = encode_right(b2)
    assert render_right_half(got2) == b2
    # expected bytes, hand-derived: reverse = wall0-14, gap15-16, wall17-19
    #   pf0 $F0, pf1 $FF, pf2: cols12-19 = w w w w w g g w -> bits0-2=1,
    #   bits3,4=0, bits5-7=1 -> $E7
    assert got2 == (0xF0, 0xFF, 0xE7), \
        f"encode2: ${got2[0]:02X},${got2[1]:02X},${got2[2]:02X} want $F0,$FF,$E7"

    # Third: symmetric round trip — a left-half row pattern via today's
    # pf_values, mirrored right must render its mirror (baseline unchanged).
    left = "####......####......"          # 20 cols, any shape
    pf_l = pf_values(left)
    mirrored = "".join(left[19 - k] for k in range(WIDTH))
    assert render_right_half(pf_l) == mirrored

    print("test_asym_encoder: OK (3 fixtures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
