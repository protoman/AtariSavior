#!/usr/bin/env python3
"""Enemy-movement E0 reference checks (assert-based, no framework).

Verifies the EnemyRamY alias contract and E0 dispatch/gate facts directly
against the sources, so a drift fails this check:

  - EnemyRamY declared at $C3 (alias over PF0Buf rows 0-2)
  - VBLANK order: SelectActiveObject before LoadPFBuffer (draw reads Y first)
  - EnterRoom order: LoadEnemyRam after LoadPFBuffer (PF refresh first)
  - LoadEnemyRAM copies ROM y into EnemyRamY for every slot
  - RefreshEnemyY runs at overscan entry, before LaserInput/CEH (the VBLANK
    LoadPFBuffer clobbers $C3 every frame — without this, enemies render
    one frame then vanish)
  - all three Y readers use EnemyRamY (draw, CheckEnemyHit, LaserHitTest)
  - UpdateEnemies: loop ungated, snake carries its own TickCounter & 3 gate
  - speeds per plan: snake &3 (1px/4f); others added in E1-E4

Run: python3 tools/test_enemy_movement.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = (ROOT / "src" / "kernel.asm").read_text(encoding="utf-8")


def line_no(pattern: str, flags: int = 0) -> int:
    for i, ln in enumerate(KERNEL.splitlines()):
        if re.search(pattern, ln, flags):
            return i + 1
    raise AssertionError(f"not found in kernel.asm: {pattern}")


def main() -> None:
    # --- declarations -----------------------------------------------------
    m = re.search(r"EnemyRamY\s*=\s*\$C3\b", KERNEL)
    assert m, "EnemyRamY must be $C3 (PF0Buf rows 0-2 alias)"
    assert re.search(r"PF0Buf\s*=\s*\$C3\b", KERNEL), \
        "PF0Buf must stay $C3 (alias base moved — redo E0 contract)"

    # --- ordering ---------------------------------------------------------
    sel = line_no(r"^\s*jsr\s+SelectActiveObject\b")
    lpfs = [i + 1 for i, ln in enumerate(KERNEL.splitlines())
            if re.match(r"\s*jsr\s+LoadPFBuffer\b", ln)]
    ler = line_no(r"^\s*jsr\s+LoadEnemyRam\b")
    assert lpfs, "no jsr LoadPFBuffer"
    assert sel < min(lpfs), \
        f"VBLANK order broken: Select@{sel} must precede LoadPF@{min(lpfs)}"
    assert ler > max(lpfs), \
        f"EnterRoom order broken: LoadEnemyRam@{ler} must follow LoadPF@{max(lpfs)}"

    # --- per-frame refresh (VBLANK LoadPF clobbers the $C3 alias) ---------
    rey = line_no(r"^\s*jsr\s+RefreshEnemyY\b")
    laser = line_no(r"^\s*jsr\s+LaserInput\b")
    ceh = line_no(r"^CheckEnemyHit:")
    assert rey < laser < ceh, \
        f"RefreshEnemyY@{rey} must run before LaserInput@{laser} and CEH@{ceh}"
    body = KERNEL.split("RefreshEnemyY:")[1].split("HotOverlapFlag —")[0]
    assert "sta EnemyRamY,X" in body and "jsr" not in body.split("rts")[0], \
        "RefreshEnemyY must be a jsr-free leaf loop writing EnemyRamY"

    # --- LoadEnemyRAM copies y -------------------------------------------
    ler_body = KERNEL.split("LoadEnemyRam:")[1].split("EnemyBitTable:")[0]
    assert "sta EnemyRamX,X" in ler_body and "sta EnemyRamY,X" in ler_body, \
        "LoadEnemyRam must shadow both x and y"

    # --- Y readers (no ROM y reads left in draw/CEH/laser vertical) -------
    draw = KERNEL.split(".SOEnemyColorDone:")[1].split(".SOEnemySkip:")[0]
    assert "lda EnemyRamY,X" in draw, "draw must read EnemyRamY"
    assert "lda (EnemyDataLo),Y" not in draw, "draw still reads ROM y"
    ceh = KERNEL.split("CheckEnemyHit:")[1].split("CEH_Loop:")[0]
    ceh_body = KERNEL.split("CEH_HasMore:")[1].split("CEHNext:")[0]
    assert "lda EnemyRamY,Y" in ceh_body, "CheckEnemyHit must read EnemyRamY"
    assert "sta ActiveObjectY" in ceh_body
    laser = KERNEL.split("LaserHitTest:")[1].split("EnemyOffTable:")[0]
    assert "sbc EnemyRamY,X" in laser, "LaserHitTest must read EnemyRamY"
    assert "(EnemyDataLo),Y" not in laser.split(".LHHit")[0], \
        "LaserHitTest vertical test still reads ROM y"

    # --- dispatch + snake gate -------------------------------------------
    ue = KERNEL.split("UpdateEnemies:")[1].split("UE_Next:")[0]
    assert "cmp #ENEMY_SNAKE" in ue, "dispatch must test snake"
    assert "and #3" in ue, "snake keeps its 1px/4f gate inside the handler"
    gate_pos = ue.index("and #3")
    cmp_pos = ue.index("cmp #ENEMY_SNAKE")
    assert cmp_pos < gate_pos, "snake gate must come AFTER the type dispatch"
    head = ue.split("UE_Loop:")[0]
    assert "and #3" not in head, "global tick gate must be removed (E0)"

    # --- no accidental ROM-y reads left where live Y matters --------------
    # CEH lamp/type reads stay on ROM (type only).
    assert "sta EnemyDeadMask" in KERNEL, "dead-mask kill path intact"

    print("test_enemy_movement: all asserts passed")


if __name__ == "__main__":
    main()
    sys.exit(0)
