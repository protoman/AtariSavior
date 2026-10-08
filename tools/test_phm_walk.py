#!/usr/bin/env python3
"""PlayerHitsMap + LaserWallClamp cell-walk, moth rect-walk contract.

PHM side (cell_collision_plan 2.1): the walk tests PF0/1/2Buf cell bits —
the ZP rect cache is gone from PlayerHitsMap. Guards:
  - cell core present (ColOff/ColMask indexing, PF0Buf read);
  - table contents == plan 0.2 bit spec (PF0 4+col, PF1 MSB-first,
    PF2 LSB-first, group offsets 0/3/6);
  - hit tail still `jmp HotOverlapFlag` (C=1 contract);
  - miss exit = clc/rts; no RcBase/FetchPtr/rect stride left in PHM.

LWC side (cell_collision_plan 3.1): LaserWallClamp scans display cols
[c0..c1] against the same buffers — rect cache + MothMaskBit gone;
entry still pinned (labels only, addresses asserted elsewhere), tail
still `jmp LaserClampDone`; cand constants +9/+2 kept.

Moth side (cell_collision_plan 4.1): same cell walk — HIT tail-jmps
.MothTurn (flip dir, no commit), miss falls to .MothNoHit (commit);
rect cache gone; the S3.2/S6.4 legacy-absence asserts keep guarding
against window/stage resurrects.

Bomb side (cell_collision_plan 5.1/5.2): kernel ApplyBombWalls +
RoomWallMask are gone (D1-B); bank1 BombMarkWalls punches at the match
via jsr ClearPFColumn; BombMaskBit survives bank1-only (bomb walk +
hot parent-mask AND until phase 6).

Run: /home/iuri/python3/bin/python3 tools/test_phm_walk.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = (ROOT / "src" / "kernel.asm").read_text(encoding="utf-8")
BANK1 = (ROOT / "src" / "bank1.asm").read_text(encoding="utf-8")
BANK2 = (ROOT / "src" / "bank2.asm").read_text(encoding="utf-8")

MASK_SPEC = [0x10, 0x20, 0x40, 0x80,
             0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01,
             0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80]
OFF_SPEC = [0, 0, 0, 0, 3, 3, 3, 3, 3, 3, 3, 3, 6, 6, 6, 6, 6, 6, 6, 6]


def phm_block() -> str:
    m = re.search(r"^PlayerHitsMap:.*?^EnemyOffTable", KERNEL, re.S | re.M)
    assert m, "PlayerHitsMap block not found"
    return m.group(0)


def moth_block() -> str:
    m = re.search(r"^MothRoutine:.*?^MothBitTable", BANK2, re.S | re.M)
    assert m, "MothRoutine block not found"
    return m.group(0)


def lwc_block() -> str:
    m = re.search(r"^LaserWallClamp:.*?^MothGate:", BANK2, re.S | re.M)
    assert m, "LaserWallClamp block not found"
    return m.group(0)


def parse_tables(text: str, tag: str) -> None:
    mo = re.search(r"^ColOff:\s+\.byte([^\n]+)", text, re.M)
    mm = re.search(r"^ColMask:\s+\.byte([^\n]+)\s*\n\s*\.byte([^\n]+)",
                   text, re.M)
    assert mo and mm, f"ColOff/ColMask tables not found ({tag})"
    off = [int(b.strip()) for b in mo.group(1).split(",")]
    mask = ([int(b.strip().lstrip("$"), 16)
             for b in mm.group(1).split(",")]
            + [int(b.strip().lstrip("$"), 16)
               for b in mm.group(2).split(",")])
    assert off == OFF_SPEC, f"ColOff {off} != spec {OFF_SPEC} ({tag})"
    assert mask == MASK_SPEC, f"ColMask {mask} != spec {MASK_SPEC} ({tag})"


def main() -> None:
    # --- PHM: cell walk contract ------------------------------------------
    blk = phm_block()
    assert re.search(r"adc\s+ColOff,X", blk), \
        "PHM must index ColOff (cell group offset)"
    assert re.search(r"lda\s+PF0Buf,Y", blk), \
        "PHM must read the PF render buffer"
    assert re.search(r"and\s+ColMask,X", blk), \
        "PHM must mask the cell bit with ColMask"
    assert re.search(r"bne\s+\.CWHit\s*;[^\n]*solid", blk), \
        "solid cell must branch to .CWHit"
    assert re.search(r"^\.CWHit:\s*\n\s*jmp\s+HotOverlapFlag", blk, re.M), \
        "hit must tail-jmp HotOverlapFlag (C=1 contract)"
    assert re.search(r"^\.CWNoHit:", blk, re.M) \
        and re.search(r"jmp\s+OverlayTramp", blk), \
        "miss exit must tail-jmp OverlayTramp (Phase 4 asym gate; the tramp " \
        "returns clc/rts for sym and bank2 PHMOverlay for asym)"
    assert "RcBase" not in blk, \
        "PHM must not consult the rect cache count (cache retired here)"
    assert "FetchPtr" not in blk, \
        "PHM must not walk rect cache bytes (cache retired here)"
    assert "adc #4" not in blk, \
        "rect stride must be gone from PHM (cell loop instead)"
    parse_tables(KERNEL, "kernel")

    # --- same table spec must feed the walk: col range space = left-half --
    assert re.search(r"cmp\s+#TILE_COLUMNS\s*\n\s*bcc\s+\.firstOk", blk), \
        "prologue must mirror right-half cols (walk sees 0-19 only)"

    # --- LWC: contact tip test (redesign 2026-10-08): ONE display col x
    # band rows RoomY+2..3, ball strip first (LWpSetup), M1 patch strip px
    # window, then the mirror row walk; result A=2 via ReturnPad ---------
    lb = lwc_block()
    assert re.search(r"adc\s+ColOff,X", lb), \
        "LWC must index ColOff (cell group offset)"
    assert re.search(r"lda\s+PF0Buf,Y", lb), \
        "LWC must read the PF render buffer"
    assert re.search(r"and\s+ColMask,X", lb), \
        "LWC must mask the cell bit with ColMask"
    assert re.search(r"cmp\s+#20\s*\n\s*bcc\s+\.LWsrc", lb), \
        "LWC must mirror right-half display cols (source = 39-d)"
    assert "adc #2" in lb and "adc #3" in lb, \
        "band rows must be RoomY+2..RoomY+3 (kill-window rows)"
    assert "jmp LWpSetup" in lb, \
        "tip col must go to the ball-strip test (LWpSetup) first"
    assert "ldy #14" in lb and "(RoomPF0Lo),Y" in lb \
        and "sbc RectCount" in lb and "cmp #8" in lb, \
        "M1 patch-strip tip window [M1X-7, M1X] missing"
    assert re.search(r"cmp\s+CollisionEndY[^\n]*\n\s*beq\s+\.LWclear", lb), \
        "row loop must stop after the bottom band row"
    assert re.search(r"^\.LWclear:\s*\n\s*jmp\s+LaserClampDone", lb, re.M), \
        "LWC must tail-jmp LaserClampDone (stack depth unchanged)"
    for gone in ("RcBase", "(FetchPtr),Y", "MothMaskBit", "BombPacked",
                 "sta CollisionX"):
        assert gone not in lb, f"LWC must not touch {gone} (contact contract)"
    parse_tables(BANK2, "bank2")

    # --- moth: cell walk since phase 4.1 (was the PHM rect walk) ----------
    mblk = moth_block()
    assert not re.search(r"^\.MwStage3:", mblk, re.M), \
        "moth .MwStage3 label must be gone (S3.2)"
    assert "lda #RcW2" not in mblk, "moth window jump must be gone (S3.2)"
    assert re.search(r"adc\s+ColOff,X", mblk) \
        and re.search(r"lda\s+PF0Buf,Y", mblk) \
        and re.search(r"and\s+ColMask,X", mblk), \
        "moth walk must index the cell map (ColOff/ColMask/PF0Buf, 4.1)"
    assert re.search(r"^\.MwHit:\s*\n\s*jmp\s+\.MothTurn", mblk, re.M), \
        "moth HIT must tail-jmp .MothTurn (flip dir, no commit)"
    assert re.search(r"beq\s+\.MothNoHit", mblk), \
        "exhausted rows must fall to .MothNoHit (commit candidate)"
    assert "RcBase" not in mblk and "adc #4" not in mblk, \
        "rect cache must be gone from the moth walk (plan 4.1) — the " \
        "single (FetchPtr),Y spawn type read is guarded by " \
        "test_enemy_movement (==1)"
    assert "lda MothMaskBit" not in mblk, \
        "moth walk must not scan MothMaskBit (S6.4: flag in rect.w b7)"
    assert not re.search(r"^MothMaskBit:", BANK2, re.M), \
        "MothMaskBit label must be gone (orphan of LWC cell swap, plan 3.1)"

    # --- plan 5.1/5.2: punch lives in bank1, persistence machinery dead ----
    assert not re.search(r"^ApplyBombWalls:", KERNEL, re.M), \
        "kernel ApplyBombWalls must be gone (plan 5.1: punch in BMW)"
    assert "jsr ApplyBombWalls" not in KERNEL, \
        "no caller may re-punch (VBL re-apply + EnterRoom restore deleted)"
    assert not re.search(r"^RoomWallMask", KERNEL, re.M), \
        "RoomWallMask $F2 must be gone (D1-B: no cross-room hole state)"
    mb = re.search(r"^BombMaskBit:\s*\n\s*\.byte([^\n]+)", BANK1, re.M)
    assert mb and len(mb.group(1).split(",")) == 4, \
        "bank1 BombMaskBit needs 4 entries (rect0-3; bomb walk + hot AND)"
    bmc = re.search(r"^BombMarkWalls:.*?^ABWXTab", BANK1, re.S | re.M)
    assert bmc and "jsr ClearPFColumn" in bmc.group(0), \
        "BMW must punch at the match via jsr ClearPFColumn (plan 5.1)"
    cpc = re.search(r"^\.CPCDone:\s*\n\s*(\S+)", BANK1, re.M)
    assert cpc and cpc.group(1) == "rts", \
        "ClearPFColumn must tail rts, not ReturnPad (same-bank, plan 5.1)"

    print("test_phm_walk: OK (PHM + LWC + moth cell contracts)")


if __name__ == "__main__":
    sys.exit(main())
