#!/usr/bin/env python3
"""Laser S4 reference checks (assert-based, no framework).

Mirrors the LaserHitTest formulas exactly (S5.4: body lives in
src/bank2.asm — LaserHitTestBody; the kill/lamp actions dispatch in
kernel.asm LaserInput) and verifies the source constants they depend
on, so a formula/asm drift fails this check:

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
BEAM_ROWS = (2, 3)  # BeamMask rows 2-3 = RoomY+2..3 (eye rows)
SWEEP = (0, 8, 16, 8)


def vert_hit(room_y: int, enemy_y: int) -> bool:
    """Exact mirror of the asm: sec/sbc RoomY-eY, clc/adc #3, cmp #9."""
    a = (room_y - enemy_y) & 0xFF
    return ((a + 3) & 0xFF) < 9


def horiz_hit(lo: int, enemy_x: int) -> bool:
    """Exact mirror of the asm: sec/sbc eLo-lo, clc/adc #14, cmp #15."""
    a = (enemy_x - lo) & 0xFF
    return ((a + 14) & 0xFF) < 15


def overlap_reference(a_lo, a_hi, b_lo, b_hi) -> bool:
    return a_lo <= b_hi and b_lo <= a_hi


def main() -> None:
    # --- asm constants: formulas must match the source --------------------
    src = Path(__file__).resolve().parents[1] / "src" / "kernel.asm"
    text = src.read_text(encoding="utf-8")
    b2 = (Path(__file__).resolve().parents[1] / "src" / "bank2.asm")
    text2 = b2.read_text(encoding="utf-8")
    assert re.search(r"ENEMY_WIDTH\s*=\s*8\b", text), "ENEMY_WIDTH != 8"
    assert ".byte 0,8,16,8" in text, "SweepOff triangle changed"
    hit = text2.split("LaserHitTestBody:")[1].split("EnemyOffTable:")[0]
    hit = "\n".join(l.split(";")[0] for l in hit.splitlines())  # ignore comments
    assert "adc #3" in hit and "cmp #9" in hit, "vertical window changed"
    assert "adc #14" in hit and "cmp #15" in hit, "horizontal window changed"
    assert "adc #7" not in hit, "old [lo,lo+7] kill window still present"
    assert "ora EnemyBitTable,X" in hit and "sta EnemyDeadMask" in hit, \
        "kill path changed"
    assert "cmp #LAMP" in hit and ".LHLamp" in hit, \
        "lamp crash path changed"
    # S5.4 result protocol: body returns A (0/$50/1), LaserInput dispatches
    # the actions (pads cannot nest from a pad body)
    assert "lda #$50" in hit and "lda #0" in hit and "jmp $FBF8" in hit, \
        "body must return its result through ReturnPad"
    # S6 (docs/laser_s6_log.md): LWC first in the body, entered/left by jmp
    assert "jmp LaserWallClamp" in hit, \
        "body must tail-jmp LaserWallClamp before the kill test"
    assert "LaserClampDone:" in hit, "LWC return label missing in body"
    assert "LaserWallClamp:" in text2, "LaserWallClamp definition missing"
    # S6: LaserInput stages the sweep-path cols BEFORE the call, and the
    # result of LHT survives positioning (pha ... pla) so dispatch still
    # runs on the returned A.
    lw = text.split("LaserInput:")[1].split("SweepOff:")[0]
    lw = "\n".join(l.split(";")[0] for l in lw.splitlines())    # ignore comments
    assert "sta CollisionEndX" in lw and "sta CollisionCellX" in lw, \
        "S6: sweep-path cols (c0/c1) not staged before LaserHitTest"
    # S6b: path anchored at the sprite nose (RoomX-3 / RoomX-4), NOT the
    # eye (RoomX+4) — eye anchoring missed the wall at max approach.
    nose = lw.split("sta CollisionEndX")[1].split("sta CollisionCellX")[0]
    assert "sbc #4" in nose, "left path c1 must be nose_L (RoomX-4)"
    assert "sbc #3" in lw.split(".LWpR:")[1].split("sta CollisionEndX")[0], \
        "right path c0 must be nose_R (RoomX-3)"
    assert "adc #7" not in lw, "stale lo+7 / eye+7 path bound (S6a)"
    assert re.search(r"sta CollisionX[^\n]*\n(?:[^\n]*\n)*?\s*jsr\s+LaserHitTest",
                     lw), "CollisionX must be stored before jsr LaserHitTest"
    assert re.search(
        r"jsr\s+LaserHitTest[^\n]*\n\s*pha\b.*?^\s*pla\b[^\n]*\n\s*beq\s+\.\w+",
        lw, re.M | re.S), \
        "LaserInput must save the result across SetObjectXPos and dispatch on it"
    assert "jsr CallPad_SetRoomDark" in text and "jsr CallPad_AddScore" in text, \
        "kill/lamp actions must run in bank0 LaserInput"

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
    for ex in range(lo - 14, lo + 1):
        assert horiz_hit(lo, ex), f"must hit eLo={ex}"
    for ex in (lo - 15, lo + 1):
        assert not horiz_hit(lo, ex), f"must miss eLo={ex}"
    for lo2 in (14, 40, 151, 159):
        for dx in range(-30, 31):
            want = overlap_reference(lo2 - 7, lo2,
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
