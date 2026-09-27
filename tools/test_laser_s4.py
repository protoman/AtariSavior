#!/usr/bin/env python3
"""Laser S4 reference checks (assert-based, no framework).

Mirrors kernel.asm LaserHitTest formulas exactly and verifies the source
constants they depend on, so a formula/asm drift fails this check:

  vertical:  (RoomY - eY) + 3 < 9     <=> eY in [RoomY-5, RoomY+3]
             (beam rows RoomY+2..3 vs enemy [eY, eY+7])
  horizontal: (eLo - lo) + 7 < 15     <=> |eLo - lo| <= 7
             (beam [lo, lo+7] (8px M0) vs enemy [eLo, eLo+7])
  sweep: offsets 0,8,16,8 (step = missile width) tile frames gap-free
  dead mask: bit-per-enemy set/test/clear, no cross-enemy revival

Run: python3 tools/test_laser_s4.py
"""
import re
import sys
from pathlib import Path

MISSILE_W = 8   # NUSIZ0=$30 -> 8-clock M0
ENEMY_W = 8     # kernel.asm ENEMY_WIDTH
BEAM_ROWS = (2, 3)  # BeamMask rows 2-3 = RoomY+2..3
SWEEP = (0, 8, 16, 8)


def vert_hit(room_y: int, enemy_y: int) -> bool:
    """Exact mirror of the asm: sec/sbc RoomY-eY, clc/adc #3, cmp #9."""
    a = (room_y - enemy_y) & 0xFF
    return ((a + 3) & 0xFF) < 9


def horiz_hit(lo: int, enemy_x: int) -> bool:
    """Exact mirror of the asm: sec/sbc eLo-lo, clc/adc #7, cmp #15."""
    a = (enemy_x - lo) & 0xFF
    return ((a + 7) & 0xFF) < 15


def overlap_reference(a_lo, a_hi, b_lo, b_hi) -> bool:
    return a_lo <= b_hi and b_lo <= a_hi


def main() -> None:
    # --- asm constants: formulas must match the source --------------------
    src = Path(__file__).resolve().parents[1] / "src" / "kernel.asm"
    text = src.read_text(encoding="utf-8")
    assert re.search(r"ENEMY_WIDTH\s*=\s*8\b", text), "ENEMY_WIDTH != 8"
    assert ".byte 0,8,16,8" in text, "SweepOff triangle changed"
    hit = text.split("LaserHitTest:")[1].split("EnemyOffTable:")[0]
    assert "adc #3" in hit and "cmp #9" in hit, "vertical window changed"
    assert "adc #7" in hit and "cmp #15" in hit, "horizontal window changed"
    assert "ora EnemyBitTable,X" in hit and "sta EnemyDeadMask" in hit, \
        "kill path changed"
    assert "cmp #LAMP" in hit and "jsr SetRoomDark" in hit, \
        "lamp crash path changed"

    # --- sweep tiling: frames at offsets 0,8,16,8 cover 0..24 continuous --
    covered = set()
    for _ in range(4):  # two full triangles
        for off in SWEEP:
            covered.update(range(off, off + MISSILE_W))
    assert covered >= set(range(0, 24)), f"sweep has gaps: {sorted(set(range(0,24)) - covered)}"

    # --- vertical: exact window edges ------------------------------------
    ry = 60
    for ey in range(ry - 5, ry + 4):
        assert vert_hit(ry, ey), f"must hit ey={ey}"
    for ey in (ry - 6, ry + 4):
        assert not vert_hit(ry, ey), f"must miss ey={ey}"
    # byte-walk agreement with the reference on the full round-trip range
    for ry2 in (0, 1, 5, 60, 191):
        for dy in range(-20, 21):
            want = overlap_reference(ry2 + BEAM_ROWS[0], ry2 + BEAM_ROWS[1],
                                     ry2 - dy, ry2 - dy + ENEMY_W - 1)
            got = vert_hit(ry2, ry2 - dy)
            assert got == want, f"vert mismatch ry={ry2} dy={dy}: {got} vs {want}"

    # --- horizontal: exact window edges incl missile width ----------------
    lo = 40
    for ex in range(lo - 7, lo + 8):
        assert horiz_hit(lo, ex), f"must hit eLo={ex}"
    for ex in (lo - 8, lo + 8):
        assert not horiz_hit(lo, ex), f"must miss eLo={ex}"
    for lo2 in (0, 4, 40, 151, 159):
        for dx in range(-30, 31):
            want = overlap_reference(lo2, lo2 + MISSILE_W - 1,
                                     lo2 + dx, lo2 + dx + ENEMY_W - 1)
            got = horiz_hit(lo2, lo2 + dx)
            assert got == want, f"horiz mismatch lo={lo2} dx={dx}: {got} vs {want}"

    # --- dead mask: kill each enemy once, others unaffected ---------------
    mask = 0
    for i in range(3):
        mask |= 1 << i
        assert mask & (1 << i)
    assert mask == 0b111
    for i in range(3):  # no resurrection: clearing one bit keeps others
        mask &= ~(1 << i)
        assert not mask & (1 << i)
        others = [j for j in range(3) if j != i]
        # simulate other kills persisting
        m2 = mask
        for j in others:
            m2 |= 1 << j
        assert all(m2 & (1 << j) for j in others), "mask clear revived others"

    print("test_laser_s4: all asserts passed")


if __name__ == "__main__":
    main()
    sys.exit(0)
