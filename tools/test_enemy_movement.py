#!/usr/bin/env python3
"""Enemy-movement reference checks (assert-based, no framework).

Verifies the EnemyRamY placement contract and dispatch/gate facts directly
against the sources, so a drift fails this check:

  - EnemyRamY declared at $E2 (private 3B since S3.4; sits inside bank1's
    $E0-$EF HUD stomp zone but every write/read is ordering-safe)
  - VBLANK order: SelectActiveObject before LoadPFBuffer (draw reads Y first)
  - EnterRoom order: LoadEnemyRam after LoadPFBuffer (source-order legacy;
    the bytes are disjoint since S3.4 but the order is kept)
  - LoadEnemyRAM copies ROM y into EnemyRamY for every slot
  - RefreshEnemyY runs at overscan entry, before LaserInput/CEH (writes the
    safe window: after the HUD score-ptr stomp, before every reader —
    without it, enemies render stale/vanish)
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
# S5.4: LaserHitTest body moved to bank2 (entry tramp stays in kernel.asm)
BANK2 = (ROOT / "src" / "bank2.asm").read_text(encoding="utf-8")


def line_no(pattern: str, flags: int = 0) -> int:
    for i, ln in enumerate(KERNEL.splitlines()):
        if re.search(pattern, ln, flags):
            return i + 1
    raise AssertionError(f"not found in kernel.asm: {pattern}")


def main() -> None:
    # --- declarations -----------------------------------------------------
    m = re.search(r"EnemyRamY\s*=\s*\$E2\b", KERNEL)
    assert m, "EnemyRamY must be $E2 (private since S3.4, was $C3 alias)"
    assert re.search(r"PF0Buf\s*=\s*\$C3\b", KERNEL), \
        "PF0Buf must stay $C3 (rows 0-2 pure since S3.4)"

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

    # --- per-frame refresh (safe window: post-HUD-stomp, pre-read) --------
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
    laser = BANK2.split("LaserHitTestBody:")[1].split("EnemyOffTable:")[0]
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
    # end marker: GetConnIdx moved to bank1 (leaf_move_plan); its old label
    # was the slice terminator — ExitRoomDown now sits at that spot.
    dey = KERNEL.split("DeriveEnemyY:")[1].split("ExitRoomDown:")[0]
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

    # --- E4: moth Y arm (MothYDerive in the $FC4F gap, docs/e4_moth_plan) ---
    assert "bpl .REYLoop" not in KERNEL, \
        "refresh loop exit must test X, not the derived-Y sign (bpl ran away)"
    assert re.search(r"txa[^\n]*\n\s*bne \.REYLoop", KERNEL), \
        "RefreshEnemyY countdown must end with txa/bne (flags from X)"
    assert ".DEYDelta" not in KERNEL, \
        "DEYDelta must be a global label (gap leaf cannot jmp a local)"
    assert "cmp #ENEMY_MOTH" in dey and "jmp MothYDerive" in dey, \
        "DeriveEnemyY must dispatch the moth to MothYDerive"
    moth = KERNEL.split("MothYDerive:")[1].split("org $FC68")[0]
    assert "and #15" in moth and "cmp #8" in moth, \
        "moth phase must be (P>>2)&15 with triangle mirror at 8"
    assert moth.count("lsr") >= 2, \
        "vertical tick = P>>2 (half the X tick — user speed tuning)"
    assert "lda #6" in moth, "moth delta must clamp tri <= 6 (exact ±6)"
    assert "adc #$FA" in moth, "moth delta = asl then -6 (x2-6)"
    assert moth.count("jmp DEYDelta") == 1, \
        "moth must jump-tail into the shared delta+spawn-y add"
    assert "sta EnemyRamP" not in moth, "MothYDerive reads the clock only"

    # --- E4 Stage C: bank2 MothRoutine horizontal patrol ---------------------
    b2 = (ROOT / "src" / "bank2.asm").read_text(encoding="utf-8")
    mr = b2.split("MothRoutine:")[1].split("MothBitTable:")[0]
    body = "\n".join(ln.split(";")[0] for ln in mr.splitlines())
    assert "jsr" not in body, \
        "bank2 moth must never jsr (mid-bank2 fold = frozen player)"
    assert "jmp UE_Next" not in body, \
        "exit only via jmp MothExitPad (bank0's pad half serves UE_Next)"
    assert "and #1" in body, "gate = EnemyRamP & 1 (1 px / 2 frames)"
    assert "stx EnemyIndex" in body and "ldx EnemyIndex" in body, \
        "slot must survive the col swap + rect walk (X clobbers, E3 lesson)"
    assert "lda EnemyDataLo" in body and "sta FetchPtr" in body, \
        "every exit must re-stage FetchPtr (MothExit discipline)"
    assert body.rstrip().endswith("jmp MothExitPad"), \
        "tail must jmp MothExitPad"
    assert "sta EnemyRamX,X" in body, "clear path must commit candidate X"
    assert "eor EnemyRamD" in body, "turn must flip the live dir bit"
    assert body.count("(FetchPtr),Y") == 1, \
        "only the spawn record type read stays direct (walk converts to " \
        "cell tests, plan 4.1 — rect reads must be gone)"
    assert "adc ColOff,X" in body and "and ColMask,X" in body \
        and "lda PF0Buf,Y" in body, \
        "moth walk must be the PHM-style cell walk (plan 4.1)"
    assert "RcBase" not in body and "RcW1" not in body, \
        "rect cache must be gone from the moth walk (plan 4.1)"
    assert re.search(r"cmp\s+#160", body), \
        "wrap/off-screen candidate must turn (plan's mod-256 range passes 255)"
    assert re.search(r"cmp\s+#33", body) and re.search(r"cmp\s+#224", body), \
        "range check = spawn ± 8 tiles mod-256 (cmp #33 / cmp #224)"
    assert body.count("sbc #7") >= 2, \
        "cols must start at VISIBLE left (Temp-5/-7 bomb convention), not Temp"
    assert "adc #8" in body and "adc #1" in body, \
        "rows must be visual Y+1..Y+8 (GRP1 ObjTop+1 window)"
    assert body.count("MothRowTable,Y") == 2, \
        "rows must convert via the /48 band table (the old >>4 = /16 gave " \
        "rows 3-4 = below every rect -> probe never hit -> walked into wall)"
    mrt = b2.split("MothRowTable:")[1].split("org")[0]
    mvals = []
    for byte_line in re.findall(r"\.byte ([\d,]+)", mrt):
        mvals += [int(v) for v in byte_line.split(",") if v.strip()]
    assert len(mvals) == 48 and mvals == sorted(mvals), \
        f"MothRowTable must be 48 ascending /48-band entries, got {len(mvals)}"
    assert ".byte $01, $02, $04" in b2, \
        "MothBitTable = per-slot dir bits (bank2-local copy)"
    assert not re.search(r"^MothMaskBit:", b2, re.M), \
        "MothMaskBit orphan must stay deleted (LWC cell swap, plan 3.1)"

    # --- space fix: row lookup uses the (A>>2) table, 36-entry tail ------
    # (the dead YToCellRow jsr wrapper was removed in S1.6; the lookup is
    # inlined at the top of PlayerHitsMap; the row-3 tail was dropped
    # 2026-10-05 to fund the .ObjZero M1 band-color restore — INVARIANT:
    # PHM only runs in-cave, RoomY <= 131 → max index 35)
    ytc = KERNEL.split("\nPlayerHitsMap:")[1].split("CollisionCellY", 1)[0]
    assert re.search(r"lda RoomY\n\s*lsr[^\n]*\n\s*lsr[^\n]*\n\s*tay", ytc), \
        "inlined row lookup must index by scanline>>2"
    table = KERNEL.split("YToRowTable:")[1].split("PlayerHitsMap:")[0]
    operands = []
    for byte_line in re.findall(r"\.byte ([\d,]+)", table):
        operands += [int(v) for v in byte_line.split(",") if v.strip()]
    expect = [0] * 12 + [1] * 12 + [2] * 12
    assert operands == expect, \
        f"YToRowTable must be the 36-entry A>>2 form, got {operands}"

    # --- E3: tentacle Y derived (÷8 bob), X chases via swap+PlayerHitsMap --
    assert "cmp #ENEMY_TENTACLE" in dey, \
        "DeriveEnemyY must dispatch the tentacle"
    tent_tick = dey.split(".DEYTickShift:")[1].split(".DEYBobTick:")[0]
    assert re.search(r"lsr[^\n]*\n\s*lsr[^\n]*\n\s*lsr", tent_tick), \
        "tentacle bob gate must be clock >> 3"
    tent = KERNEL.split("UE_Tentacle:")[1].split(".TentOut:")[0]
    assert "and #3" in tent, "tentacle X gate must be TickCounter & 3 (÷4)"
    # ZP-scratch probe (6140f5a): the old 3-pha path hit min SP $F4 = bomb
    # stomp — pha/pla are banned here; the swap uses ActiveObjectX/Y + EnemyIndex.
    tent_code = "\n".join(l.split(";")[0] for l in tent.splitlines())
    assert not re.search(r"\bpha\b|\bpla\b", tent_code), \
        "probe must use ZP scratch (ActiveObjectX/Y + EnemyIndex), not pha/pla"
    phm = tent.index("jsr PlayerHitsMap")
    # slot X must be saved before the probe and popped right after it:
    # PlayerHitsMap clobbers X (rect walk ldx/dex + txa/tax), so without the
    # save the commit wrote EnemyRamX[row] — tentacle X froze (E-gate bug).
    save_x = tent.rindex("stx EnemyIndex", 0, phm)
    load_x = tent.index("ldx EnemyIndex", phm)
    assert save_x < phm < load_x, \
        "slot X must be saved before / restored after PlayerHitsMap"
    restore = tent.rindex("sta RoomX")           # player restore AFTER probe
    commit = tent.index("sta EnemyRamX,X")
    assert phm < load_x < restore < commit, \
        "probe order must be: PHM -> restore X -> restore player -> commit"
    assert "sta ActiveObjectX" in tent and "sta ActiveObjectY" in tent, \
        "probe must save player RoomX/RoomY into ZP scratch"
    # tail architecture: the ONLY exit is .TentOut -> jmp UE_Next
    tent_out = KERNEL.split(".TentOut:")[1].splitlines()[1]
    assert tent_out.split(";")[0].strip() == "jmp UE_Next", \
        "every path must exit via .TentOut -> jmp UE_Next (tail jmp, no rts)"
    ue = KERNEL.split("UpdateEnemies:")[1].split("UE_Exit:")[0]
    assert "jmp UE_Tentacle" in ue, \
        "dispatch must tail-jmp the tentacle (jsr costs 2 stack bytes)"
    assert ue.index("cmp #ENEMY_TENTACLE") < ue.index("cmp #ENEMY_SNAKE"), \
        "tentacle check must come first (keeps snake branches in range)"
    # --- E4: moth dispatched via the $FEF0 bank2 code-fold tramp ------------
    assert "cmp #ENEMY_MOTH" in ue, "dispatch must test the moth"
    assert "jmp UE_MothTramp" in ue, \
        "moth must tail-jmp the entry tramp (0 push — stack guard)"
    assert (ue.index("cmp #ENEMY_TENTACLE") < ue.index("cmp #ENEMY_MOTH")
            < ue.index("cmp #ENEMY_SNAKE")), \
        "dispatch order must stay tentacle -> moth -> snake"

    # --- water strip: bottom 1/4 of the bottom band, split pass ------------
    assert ".WaterRow:" in KERNEL, "water strip pass missing"
    adv = KERNEL.split("Advance to next tile row")[1].split(".AfterRows:")[0]
    assert "beq .WaterRow" in adv, "row 2 must hand off to .WaterRow"
    assert "bcs .AfterRows" in adv, \
        "water pass must exit .AfterRows (X=4 bcs after cpx #TILE_ROWS)"
    gate = KERNEL.split("Scanlines this pass")[1].split(".Line:")[0]
    assert "lda CollisionX" in gate, \
        "row 2 body count must be the tide value 36+off (CollisionX carrier)"
    # split tail (2026-10-05): rows 0/1 store 48 + WSYNC + `jmp .Line` BEFORE
    # the tide block; row 2 loads CollisionX, WSYNCs, stores its tide count,
    # then falls straight into .Line (row1 setup gap 77->74c = the +1
    # line/frame stall).
    # A1 gap fix (2026-10-05): `sta LineCount` sits AFTER `sta WSYNC` in
    # both paths — -3c from the setup-gap window (A1's `sta Temp` in .Row
    # pushed gaps to 77/79 = +2 lines/frame), +3c to the first body line.
    # Moving either store back before its WSYNC re-opens the stall.
    assert gate.index(".RowLinesTide:") > gate.index("jmp .Line"), \
        "split tail: tide block must come after rows 0/1's WSYNC jmp"
    # strip comments first — the A1 explanation above quotes both mnemonics
    gcode = "\n".join(l.split(";")[0] for l in gate.splitlines())
    assert gcode.index("sta LineCount") > gcode.index("sta WSYNC"), \
        "LineCount store must follow WSYNC (setup-gap A1 fix)"
    assert gcode.rstrip().endswith("sta LineCount"), \
        "row 2 must fall from WSYNC through LineCount straight into .Line"
    wr = KERNEL.split(".WaterRow:")[1].split(".GrpZero:")[0]
    assert re.search(r"lda\s+#47\b", wr) and "sbc CollisionX" in wr, \
        "strip pass: setup line + (47-(36+off)) bodies = 12-off strip"
    assert "lda RoomBandColor" in wr and "sta COLUBK" in wr, \
        "strip must paint the band color (blink-off path, inlined read)"
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
