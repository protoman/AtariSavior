#!/usr/bin/env python3
"""PlayerHitsMap / moth rect-walk contract (assert-based, no framework).

P3.4 regression guard (exit-Y discipline): the rect walk advances Y+4 FROM
THE RECT BASE, but the check sequences leave Y at base (mask/col-x exits),
base+2 (col-end exits), or base+1 (row exits). Without normalizing, one late
exit skews every later rect read — reads drift into adjacent ZP bytes and
collision becomes "from another stage" (thin walls passable, phantom gaps).

Symptom class: any rect walker whose advance reads (base+delta)+4.

S3.2 uniform-stride contract (both walkers, kernel + bank2 moth):
  - cache $CD-$E0 holds count+rects0-4 contiguously; stride 4 walks ALL
    FIVE rects — no window jumps (RcW2 deleted), no .Stage3/.MwStage3
    fixed-address rect4 special case;
  - mask index = Y>>2 covers index 4 via a $00 table entry (rect4 is
    never masked — WallMask b3-6 = rects0-3 only).

Run: python3 tools/test_phm_walk.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = (ROOT / "src" / "kernel.asm").read_text(encoding="utf-8")
BANK2 = (ROOT / "src" / "bank2.asm").read_text(encoding="utf-8")


def phm_block() -> str:
    m = re.search(r"^PlayerHitsMap:.*?^EnemyOffTable", KERNEL, re.S | re.M)
    assert m, "PlayerHitsMap block not found"
    return m.group(0)


def moth_block() -> str:
    m = re.search(r"^MothRoutine:.*?^MothBitTable", BANK2, re.S | re.M)
    assert m, "MothRoutine block not found"
    return m.group(0)


def main() -> None:
    blk = phm_block()

    # --- exits that leave Y = base must target .nextRect directly ---
    assert re.search(r"bne\s+\.nextRect", blk), \
        "mask exit must advance from base (target .nextRect)"
    assert re.search(r"bcs\s+\.nextRect", blk), \
        "col-x exit must advance from base (target .nextRect)"

    # --- col-end exits leave Y = base+2 -> .nrmCol (two dey) ---
    col = re.search(
        r"cmp CollisionEndX.*?beq\s+(\.\w+).*?bcc\s+(\.\w+)", blk, re.S)
    assert col, "col-end exits not found"
    assert col.group(1) == col.group(2) == ".nrmCol", \
        f"col-end exits must target .nrmCol, got {col.groups()}"

    # --- row exits leave Y = base+1 -> .nrmRow (one dey) ---
    row = re.search(
        r"cmp CollisionCellY.*?beq\s+(\.\w+).*?bcc\s+(\.\w+)", blk, re.S)
    assert row, "row y+h exits not found"
    assert row.group(1) == row.group(2) == ".nrmRow", \
        f"row y+h exits must target .nrmRow, got {row.groups()}"
    assert re.search(r"cmp CollisionEndY.*?bcs\s+\.nrmRow", blk, re.S), \
        "row y>bottom exit must target .nrmRow"

    # --- trampolines exist and normalize to base ---
    ncol = re.search(r"\.nrmCol:\s*\n\s*dey\s*\n\s*dey[^\n]*\n\.nextRect:",
                     blk)
    assert ncol, ".nrmCol must be two dey falling into .nextRect"
    nrow = re.search(r"\.nrmRow:\s*\n\s*dey[^\n]*\n\s*bpl\s+\.nextRect", blk)
    assert nrow, ".nrmRow must be one dey then always-taken bpl .nextRect"

    # --- advance stays Y+4 (from normalized base) ---
    assert re.search(r"adc #4\s+;[^\n]*next rect base", blk), \
        "advance must be Y+4 from rect base"

    # --- S3.2 uniform stride: window machinery and .Stage3 are GONE ---
    assert not re.search(r"^\.Stage3:", blk, re.M), \
        ".Stage3 label reappeared — rect4 must walk via the uniform stride"
    assert "RcW2" not in blk and "lda #RcW2" not in blk, \
        "window jump (RcW2) reappeared — stride is uniform since S3.2"
    assert not re.search(r"cpy\s+#16|cpy\s+#8", blk), \
        "window/stage boundary tests must be gone (uniform stride)"
    mb = re.search(r"^BombMaskBit:\s*\n\s*\.byte([^\n]+)", KERNEL, re.M)
    assert mb and len(mb.group(1).split(",")) == 5, \
        "BombMaskBit needs 5 entries (index 4 = \$00, rect4 never masked)"
    assert mb.group(1).split(",")[-1].strip() == "$00", \
        "BombMaskBit[4] must be \$00 (rect4 not in WallMask)"

    # --- same contract in the bank2 moth walk ---
    mblk = moth_block()
    assert not re.search(r"^\.MwStage3:", mblk, re.M), \
        "moth .MwStage3 label must be gone (S3.2)"
    assert "lda #RcW2" not in mblk, "moth window jump must be gone (S3.2)"
    assert re.search(r"adc #4", mblk), "moth advance must be stride 4"
    mm = re.search(r"^MothMaskBit:\s*\n\s*\.byte([^\n]+)", BANK2, re.M)
    assert mm and mm.group(1).split(",")[-1].strip() == "$00", \
        "MothMaskBit[4] must be \$00 (rect4 not masked)"

    print("test_phm_walk: OK")


if __name__ == "__main__":
    sys.exit(main())
