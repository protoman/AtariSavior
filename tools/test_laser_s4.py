#!/usr/bin/env python3
"""Laser contact-missile reference checks (assert-based, no framework).

Contract (redesign 2026-10-08 — single travelling missile, no sweep):

  travel: LaserX +/-4 px per held frame from the eye toward the facing
          (eye = right min(RoomX+4,159) / left RoomX-4), capped at the
          old S3 sweep extent (right <= RoomX+20, left >= max(RoomX-20,0));
          past the cap OR the unsigned `cmp #160` wrap restarts at the eye
          (triangle-loop parity — user: beam "moved way beyond the limit");
          press edge (b7 held / b6 prev) re-anchors.
  vertical:  (RoomY - eY) + 3 < 9     <=> eY in [RoomY-5, RoomY+3]
             (kill rows RoomY+2..3 vs enemy [eY, eY+7]; draw = row 2 only)
  horizontal: (eLo - lo) + 7 < 15     <=> |eLo - lo| <= 7
             (both boxes right-anchored [arg-7, arg] — proven by
             CheckEnemyHit/kill_window: beam [lo-7,lo] vs enemy [eLo-7,eLo])
  wall: bank2 tip-cell test returns A=2 (CollisionX never modified) —
        incl. the M1 patch strip (tip px in [M1X-7, M1X], kill-aware b4);
        kill/lamp/wall/cap all reset LaserX = eye in bank0 LaserInput.
  gate: kernel .Line ENAM0 = BeamMask & LaserState (b1 armed, mirror of
        b7 held) — LaserBeamOn byte retired, $83 holds LaserX now.
  dead mask: bit-per-enemy set/test/clear, no cross-enemy revival

Mirrors the source of LaserHitTest formulas (src/bank2.asm —
LaserHitTestBody) and LaserInput (src/kernel.asm) so drift fails.

Run: /home/iuri/python3/bin/python3 tools/test_laser_s4.py
"""
import re
import sys
from pathlib import Path

MISSILE_W = 8   # NUSIZ0=$30 -> 8-clock M0
ENEMY_W = 8     # kernel.asm ENEMY_WIDTH
BEAM_ROWS = (2, 3)  # kill window rows (bank2 hard-coded RoomY+2..3);
                    # the DRAW is row 2 only — BeamMask {0,0,2,0,...}
TRAVEL = 4      # px per held frame (contact missile)


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
    b2 = (Path(__file__).resolve().parents[1] / "src" / "bank2.asm")
    text2 = b2.read_text(encoding="utf-8")
    assert re.search(r"ENEMY_WIDTH\s*=\s*8\b", text), "ENEMY_WIDTH != 8"

    # --- LaserInput: travel machine (no sweep residue) --------------------
    assert ".byte 0,8,16,8" not in text, "SweepOff triangle resurrected"
    assert "LASER_PHASE" not in text, "sweep phase bits resurrected"
    assert re.search(r"LASER_ON\s*=\s*%10000010", text), \
        "LASER_ON must arm b7 held + b1 gate in one ora"
    lw = text.split("LaserInput:")[1].split(".ds $FFE6")[0]
    lw = "\n".join(l.split(";")[0] for l in lw.splitlines())  # ignore comments
    assert "adc #4" in lw and "sbc #4" in lw, "travel +/-4px missing"
    assert "cmp #160" in lw, "unsigned edge/wrap guard missing"
    assert "adc #20" in lw and "sbc #20" in lw, \
        "old-sweep-extent cap (RoomX+20 / max(RoomX-20,0)) missing"
    assert "sta RectCount" in lw, "travel candidate staging (RectCount) missing"
    assert re.search(r"sta\s+LaserX\s*\n\s*jmp\s+\.LaserGo", lw), \
        "keep path must commit the candidate and skip the eye restart"
    assert "ora #LASER_ON" in lw, "held+armed store missing"
    assert lw.count("jsr .LaserEye") >= 2, \
        "eye reset must run on press edge AND on contact/wrap"
    assert "lda #159" in lw, "right eye clamp (TIA past 159 unverified)"
    # CollisionX staged immediately before the hit test; dispatch runs on
    # the returned A BEFORE positioning (reset then draws at the eye).
    assert re.search(r"sta CollisionX[^\n]*\n(?:[^\n]*\n)*?\s*jsr\s+LaserHitTest",
                     lw), "CollisionX must be stored before jsr LaserHitTest"
    assert re.search(r"jsr\s+LaserHitTest[^\n]*\n\s*beq\s+\.\w+", lw), \
        "LaserInput must dispatch on the result (0 = keep travelling)"
    assert "cmp #2" in lw, "wall-contact result (A=2) not dispatched"
    assert "jsr CallPad_SetRoomDark" in text and "jsr CallPad_AddScore" in text, \
        "kill/lamp actions must run in bank0 LaserInput"
    # position AFTER dispatch: contact frame draws at the eye
    assert re.search(r"jsr\s+SetObjectXPos[^\n]*\n\s*rts\b", lw), \
        "position must be the tail (post-dispatch reset value)"
    assert "sta HMM0" in lw, "release must clear the stale fine offset"

    # --- kernel gate: ENAM0 = BeamMask & LaserState (b1) ------------------
    assert re.search(r"lda BeamMask,Y[^\n]*\n\s*and LaserState", text), \
        ".Line beam gate must AND LaserState (b1 armed)"
    assert re.search(r"BeamMask:\s*\n\s*\.byte 0,0,2,0,0,0,0,0,0,0,0,0", text), \
        "beam = single yellow row 2 (red row-3 strip removed 2026-10-08)"
    assert "and LaserBeamOn" not in text, "old LaserBeamOn gate still present"
    assert re.search(r"LaserX\s+byte", text), "LaserX ZP decl missing"
    assert re.search(r"LaserState\s*=\s*\$C0", text), "LaserState moved"

    # --- bank2 body: tip-cell wall + own-body kill window ------------------
    hit = text2.split("LaserHitTestBody:")[1].split("EnemyOffTable:")
    hit = hit[0] if isinstance(hit, list) else hit  # keep str slice
    hit = "\n".join(l.split(";")[0] for l in hit.splitlines())  # ignore comments
    assert "adc #3" in hit and "cmp #9" in hit, "vertical window changed"
    # kill == drawn overlap (beam [A-7,A] x enemy [eX-7,eX] — the arg-box
    # convention CheckEnemyHit proves) -> eX in [A-7, A+7] = adc #7.
    assert "adc #7" in hit and "cmp #15" in hit, "horizontal window changed"
    assert "adc #14" not in hit, "S6b left-shifted kill window still present"
    assert "ora EnemyBitTable,X" in hit and "sta EnemyDeadMask" in hit, \
        "kill path changed"
    assert "cmp #LAMP" in hit and ".LHLamp" in hit, \
        "lamp crash path changed"
    # result protocol: 0 / $50 / 1 lamp / 2 wall through ReturnPad
    assert "lda #$50" in hit and "lda #0" in hit and "jmp $FBF8" in hit, \
        "body must return its result through ReturnPad"
    assert "jmp LaserWallClamp" in hit, \
        "body must tail-jmp LaserWallClamp (tip wall test) first"
    assert "LaserClampDone:" in hit, "LWC return label missing in body"
    assert "LaserWallClamp:" in text2, "LaserWallClamp definition missing"
    # LWC slice = LaserWallClamp..MothGate (MothGate uses CollisionX as its
    # OWN scratch — must stay outside the slice or the no-clamp assert
    # false-positives).
    lwc = text2.split("LaserWallClamp:")[1].split("MothGate:")[0]
    lwc = "\n".join(l.split(";")[0] for l in lwc.splitlines())  # ignore comments
    assert "lda #2" in lwc, "wall contact must return A=2"
    assert "sta CollisionX" not in lwc, \
        "clamp store resurrected (contact must not move CollisionX)"
    # M1 patch strip = solid at the tip (the mirror walk alone passes the
    # patched cell — envelope open — and the beam used to sail through)
    assert "ldy #14" in lwc and "(RoomPF0Lo),Y" in lwc, \
        "M1X must be read from room data at offset 14"
    assert "sbc RectCount" in lwc and "cmp #8" in lwc, \
        "M1 tip window must be px [M1X-7, M1X]"
    assert "and #$10" in lwc, "M1 contact must be kill-aware (dead b4)"
    assert "jmp LWpSetup" in lwc, "M1 miss must fall to the ball-strip test"

    # --- travel coverage: 4px steps, capped at the old sweep extent ------
    # right: eye=RoomX+4..cap=RoomX+20 (hit cap/wrap -> eye, loops);
    # left:  eye=RoomX-4..floor=max(RoomX-20,0) (underflow/floor -> eye).
    # Coverage = 8px boxes at every reachable tip must be gap-free inside
    # the cap AND bounded by it (the regression: beam past the limit).
    def travel_seq(eye, cap, step, frames=80):
        seq = [eye]
        t = eye
        for _ in range(frames):
            nt = (t + step) & 0xFF
            if nt >= 160 or (step > 0 and nt > cap) \
                    or (step < 0 and nt < cap):
                nt = eye
            t = nt
            seq.append(t)
        return seq

    for roomx in (4, 12, 60, 120, 140, 155):
        # right facing
        eye = min(roomx + 4, 159)
        cap = roomx + 20
        seq = travel_seq(eye, cap, TRAVEL)
        hi = min(cap, 159)
        assert max(seq) <= hi and min(seq) >= eye, (
            f"right travel escaped [eye,cap]: RoomX={roomx} "
            f"eye={eye} cap={cap} range=[{min(seq)},{max(seq)}]")
        covered = set()
        for t in seq:
            covered |= set(range(t - 7, t + 1))
        max_tip = eye + ((hi - eye) // TRAVEL) * TRAVEL  # lattice <= hi
        want = set(range(eye - 7, max_tip + 1))
        assert want <= covered, (
            f"right travel gaps RoomX={roomx}: {sorted(want - covered)}")
        assert eye in seq[1:], "right travel must loop back to the eye"
        # left facing
        eye = roomx - 4
        cap = max(roomx - 20, 0)
        seq = travel_seq(eye, cap, -TRAVEL)
        assert max(seq) <= eye and min(seq) >= cap, (
            f"left travel escaped [cap,eye]: RoomX={roomx} "
            f"eye={eye} cap={cap} range=[{min(seq)},{max(seq)}]")
        covered = set()
        for t in seq:
            covered |= set(range(t - 7, t + 1))
        lo = eye - ((eye - cap) // TRAVEL) * TRAVEL      # lattice >= cap
        want = set(range(max(lo - 7, 0), eye + 1))
        assert want <= covered, (
            f"left travel gaps RoomX={roomx}: {sorted(want - covered)}")
        assert eye in seq[1:], "left travel must loop back to the eye"

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
    for lo2 in (14, 40, 151, 159):
        for dx in range(-30, 31):
            # both boxes right-anchored [x-7, x] (kill_window convention)
            want = overlap_reference(lo2 - 7, lo2,
                                     lo2 + dx - 7, lo2 + dx)
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
