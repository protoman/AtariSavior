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
    assert "sta EnemyRamY,X" in body, "RefreshEnemyY must write EnemyRamY"
    # E1: refresh delegates live-Y to DeriveEnemyY (bat is derived, not stored)
    assert "jsr DeriveEnemyY" in body, \
        "RefreshEnemyY must call DeriveEnemyY (E1: no stored movement state)"
    assert "ldy EnemyOffTable,X" not in body.split("rts")[0], \
        "refresh no longer copies ROM y directly (DeriveEnemyY does)"

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

    # --- E1/E-gates: derives read the free-running clock EnemyRamP ---------
    dey = KERNEL.split("DeriveEnemyY:")[1].split("GetConnIdx:")[0]
    assert "cmp #ENEMY_BAT" in dey, "DeriveEnemyY must special-case the bat"
    assert "sta Temp" in dey and "adc Temp" in dey, \
        "bat delta must be added to ROM spawn y"
    assert "lda EnemyRamP" in dey and "jsr FoldIndirect" in dey, \
        "bat path needs ROM spawn y (via P3.1 fold) and the clock (EnemyRamP)"
    assert "lda TickCounter" not in dey, \
        "TickCounter wraps every 60 frames — derives must use EnemyRamP"
    # clock advances once per frame in RefreshEnemyY
    rey_body = KERNEL.split("RefreshEnemyY:")[1].split("HotOverlapFlag —")[0]
    assert "inc EnemyRamP" in rey_body, \
        "RefreshEnemyY must advance the EnemyRamP frame clock"
    # triangle 0,1,2,1: phase&3 with 3 mapped to 1
    assert re.search(r"and\s+#3", dey), "bat gate: phase & 3"
    assert re.search(r"cmp\s+#3\s*\n\s*bne.*\n\s*lda\s+#1", dey), \
        "bat triangle must map phase 3 -> 1"
    # bat half speed: clock >> 1 before the shared triangle (gate fix)
    bat = dey.split(".DEYTickNoShift:")[1].split(".DEYTickShift:")[0]
    assert re.search(r"lsr", bat), "bat must halve the clock (1 px / 2 frames)"
    # bat must NOT also move in UpdateEnemies (would double-apply)
    ue = KERNEL.split("UpdateEnemies:")[1].split("UE_Next:")[0]
    assert "ENEMY_BAT" not in ue, \
        "UpdateEnemies must not move the bat (movement is derived in refresh)"
    # first screen must spawn at least one enemy (spawner sanity for Stella)
    import json
    lvl = json.loads((ROOT / "src" / "rooms" / "level_001.json")
                     .read_text(encoding="utf-8"))
    first = lvl["level"]["rooms"][0]["enemies"]
    assert len(first) >= 1, \
        "level_001 room0 spawns no enemy (Stella spawner gate)"

    # --- E2: spider derived as spawn + triangle24, dwell at top ------------
    assert "cmp #ENEMY_SPIDER" in dey, "DeriveEnemyY must dispatch the spider"
    spider = dey.split(".DEYSpiderTick:")[1]
    assert ".DEYSUp:" in spider, "spider derive path missing"
    assert re.search(r"lsr[^\n]*\n\s*lsr", spider), \
        "spider gate must be clock >> 2 (1 px per 4 frames)"
    assert "and #$3F" in spider, "spider step index must mask to 0..63"
    assert "cmp #48" in spider and "lda #0" in spider, \
        "spider must dwell (delta 0) for phase >= 48 so the 256-wrap never " \
        "teleports the sprite"
    assert "sbc #48" not in spider, \
        "old mod-48 wrap is gone (it caused the count-down teleport)"
    assert "cmp #25" in spider, "spider triangle turns at step 24 (cmp #25)"
    assert "sbc #$CF" in spider, "spider up half must compute 48-p"
    assert "adc Temp" in dey, "shared tail must add delta to ROM spawn y"
    # all paths (bat/spider) must pass through the shared spawn add
    assert dey.count("rts") == 2, \
        "DeriveEnemyY: only static and shared-tail may rts (bat/spider jmp tail)"
    assert "ENEMY_SPIDER" not in ue, \
        "UpdateEnemies must not move the spider (movement is derived)"

    # --- space fix: YToCellRow uses the 48-entry (A>>2) table -------------
    ytc = KERNEL.split("YToCellRow subroutine")[1].split("PlayerHitsMap:")[0]
    assert re.search(r"lsr[^\n]*\n\s*lsr[^\n]*\n\s*tay", ytc), \
        "YToCellRow must index by scanline>>2"
    table = ytc.split("YToRowTable:")[1]
    operands = []
    for byte_line in re.findall(r"\.byte ([\d,]+)", table):
        operands += [int(v) for v in byte_line.split(",") if v.strip()]
    assert len(operands) == 48 and operands == sorted(operands), \
        f"YToRowTable must be 48 ascending entries, got {len(operands)}"

    # --- E3: tentacle Y derived (÷8 bob), X chases via swap+PlayerHitsMap --
    assert "cmp #ENEMY_TENTACLE" in dey, \
        "DeriveEnemyY must dispatch the tentacle"
    tent_tick = dey.split(".DEYTickShift:")[1].split(".DEYBobTick:")[0]
    assert re.search(r"lsr[^\n]*\n\s*lsr[^\n]*\n\s*lsr", tent_tick), \
        "tentacle bob gate must be clock >> 3"
    tent = KERNEL.split("UE_Tentacle:")[1].split(".TentOut:")[0]
    assert "and #3" in tent, "tentacle X gate must be TickCounter & 3 (÷4)"
    assert len(re.findall(r"\bpha\b", tent)) == 3 \
        and len(re.findall(r"\bpla\b", tent)) == 3, \
        "probe must save/restore player RoomX+RoomY AND slot X in pairs"
    phm = tent.index("jsr PlayerHitsMap")
    # slot X must be pushed before the probe and popped right after it:
    # PlayerHitsMap->YToCellRow does `tax` (X = bottom row), so without the
    # save the commit wrote EnemyRamX[row] — tentacle X froze (E-gate bug).
    save_x = tent.rindex("txa", 0, phm)
    load_x = tent.index("tax", phm)
    assert save_x < phm < load_x, \
        "slot X must be saved before / restored after PlayerHitsMap"
    restore = tent.rindex("sta RoomX")           # player restore AFTER probe
    commit = tent.index("sta EnemyRamX,X")
    assert phm < load_x < restore < commit, \
        "probe order must be: PHM -> restore X -> restore player -> commit"
    assert "jmp UE_Next" not in tent, \
        "UE_Tentacle is a subroutine — must return via .TentOut, not UE_Next"
    ue = KERNEL.split("UpdateEnemies:")[1].split("UE_Exit:")[0]
    assert "jsr UE_Tentacle" in ue, "dispatch must call the tentacle subroutine"
    assert ue.index("cmp #ENEMY_TENTACLE") < ue.index("cmp #ENEMY_SNAKE"), \
        "tentacle check must come first (keeps snake branches in range)"

    # --- water strip: bottom 1/4 of the bottom band, split pass ------------
    assert ".WaterRow:" in KERNEL, "water strip pass missing"
    adv = KERNEL.split("Advance to next tile row")[1].split(".AfterRows:")[0]
    assert "beq .WaterRow" in adv, "row 2 must hand off to .WaterRow"
    assert "beq .AfterRows" in adv, "water pass must exit to .AfterRows"
    row2 = KERNEL.split("Scanlines this pass")[1].split("sta WSYNC")[0]
    assert "#LINES_PER_TILE-12" in row2, \
        "row 2 body count must drop to 36 (12 lines move to the strip)"
    wr = KERNEL.split(".WaterRow:")[1].split(".GrpZero:")[0]
    assert re.search(r"lda\s+#11\b", wr), \
        "strip pass: setup line + 11 bodies = 12-line strip"
    assert "jsr LoadRoomBottomColor" in wr and "sta COLUBK" in wr, \
        "strip must paint the band color (blink-off path)"
    assert wr.rstrip().endswith("jmp .Line"), \
        "strip must continue into the shared .Line loop"
    # death check + respawn follow the strip (bottom_band_plan rules 2/4)
    cbt = KERNEL.split("CheckBandTouch:")[1].split(".CBTdone:")[0]
    assert "cmp #125" in cbt, "band touch threshold must be RoomY >= 125"
    llb = KERNEL.split("LoseLifeBand:")[1].split("BuildColupF —")[0]
    assert re.search(r"sbc\s+#12\b", llb), \
        "band respawn must shift RoomY up by 12 (not the whole 48-line band)"
    # bank1's fold-pad return address must track Overscan's new address
    b1 = (ROOT / "src" / "bank1.asm").read_text(encoding="utf-8")
    ov = re.search(r"^\s*(\d+)\s+([0-9a-f]{4})\s+\S*\s*Overscan\b",
                   (ROOT / "src" / "bank0.lst").read_text(encoding="utf-8"),
                   re.M)
    assert ov, "Overscan label not found in bank0.lst"
    addr = f"${ov.group(2).upper()}"
    assert f"jmp {addr}" in b1, \
        f"bank1 ToGameStub must jmp {addr} (Overscan moved)"

    print("test_enemy_movement: all asserts passed")


if __name__ == "__main__":
    main()
    sys.exit(0)
