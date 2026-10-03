#!/usr/bin/env python3
"""PlayerHitsMap cell-walk + moth rect-walk contract (assert-based, no framework).

PHM side (cell_collision_plan 2.1): the walk tests PF0/1/2Buf cell bits —
the ZP rect cache is gone from PlayerHitsMap. Guards:
  - cell core present (ColOff/ColMask indexing, PF0Buf read);
  - table contents == plan 0.2 bit spec (PF0 4+col, PF1 MSB-first,
    PF2 LSB-first, group offsets 0/3/6);
  - hit tail still `jmp HotOverlapFlag` (C=1 contract);
  - miss exit = clc/rts; no RcBase/FetchPtr/rect stride left in PHM.

Moth side: still the verbatim rect walk (converts at plan phase 4.1) — the
P3.4 exit-Y discipline + S3.2 uniform stride + S6.4 destroyed-flag asserts
keep guarding THAT walker until then.

Run: /home/iuri/python3/bin/python3 tools/test_phm_walk.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = (ROOT / "src" / "kernel.asm").read_text(encoding="utf-8")
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


def parse_tables() -> None:
    mo = re.search(r"^ColOff:\s+\.byte([^\n]+)", KERNEL, re.M)
    mm = re.search(r"^ColMask:\s+\.byte([^\n]+)\s*\n\s*\.byte([^\n]+)",
                   KERNEL, re.M)
    assert mo and mm, "ColOff/ColMask tables not found"
    off = [int(b.strip()) for b in mo.group(1).split(",")]
    mask = ([int(b.strip().lstrip("$"), 16)
             for b in mm.group(1).split(",")]
            + [int(b.strip().lstrip("$"), 16)
               for b in mm.group(2).split(",")])
    assert off == OFF_SPEC, f"ColOff {off} != spec {OFF_SPEC}"
    assert mask == MASK_SPEC, f"ColMask {mask} != spec {MASK_SPEC}"


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
    assert re.search(r"^\.CWNoHit:\s*\n\s*clc\s*\n\s*rts", blk, re.M), \
        "miss exit must be clc/rts"
    assert "RcBase" not in blk, \
        "PHM must not consult the rect cache count (cache retired here)"
    assert "FetchPtr" not in blk, \
        "PHM must not walk rect cache bytes (cache retired here)"
    assert "adc #4" not in blk, \
        "rect stride must be gone from PHM (cell loop instead)"
    parse_tables()

    # --- same table spec must feed the walk: col range space = left-half --
    assert re.search(r"cmp\s+#TILE_COLUMNS\s*\n\s*bcc\s+\.firstOk", blk), \
        "prologue must mirror right-half cols (walk sees 0-19 only)"

    # --- moth: still the rect walk (converts at phase 4.1) ----------------
    mblk = moth_block()
    assert not re.search(r"^\.MwStage3:", mblk, re.M), \
        "moth .MwStage3 label must be gone (S3.2)"
    assert "lda #RcW2" not in mblk, "moth window jump must be gone (S3.2)"
    assert re.search(r"adc #4", mblk), "moth advance must be stride 4"
    assert re.search(
        r"lda \(FetchPtr\),Y\s*\n\s*bmi\s+\.MwNrmCol", mblk), \
        "moth w-read must bmi to .MwNrmCol on b7 (S6.4, Y=base+2)"
    assert "lda MothMaskBit" not in mblk, \
        "moth walk must not scan MothMaskBit (S6.4: flag in rect.w b7)"
    mm = re.search(r"^MothMaskBit:\s*\n\s*\.byte([^\n]+)", BANK2, re.M)
    assert mm and mm.group(1).split(",")[-1].strip() == "$00", \
        "MothMaskBit[4] must be $00 (rect4 not masked)"

    # --- bomb machinery still owns the cache while moth/LWC need it ------
    mb = re.search(r"^BombMaskBit:\s*\n\s*\.byte([^\n]+)", KERNEL, re.M)
    assert mb and len(mb.group(1).split(",")) == 5, \
        "BombMaskBit needs 5 entries (index 4 = $00, rect4 never masked)"
    assert mb.group(1).split(",")[-1].strip() == "$00", \
        "BombMaskBit[4] must be $00 (rect4 not in WallMask)"

    print("test_phm_walk: OK (PHM cell contract + moth rect contract)")


if __name__ == "__main__":
    sys.exit(main())
