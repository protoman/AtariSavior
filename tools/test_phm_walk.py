#!/usr/bin/env python3
"""PlayerHitsMap walk exit-Y contract (assert-based, no framework).

P3.4 regression guard: the rect walk advances Y+4 FROM THE RECT BASE, but
the check sequences leave Y at base (mask/col-x exits), base+2 (col-end
exits), or base+1 (row exits). Without normalizing, one late exit skews
every later rect read — reads drift into PF1Buf/PF2Buf bytes and collision
becomes "from another stage" (thin walls passable, phantom gaps).

Symptom class: any rect walker whose advance reads (base+delta)+4.

Run: python3 tools/test_phm_walk.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = (ROOT / "src" / "kernel.asm").read_text(encoding="utf-8")


def phm_block() -> str:
    m = re.search(r"^PlayerHitsMap:.*?^\.Stage3", KERNEL, re.S | re.M)
    assert m, "PlayerHitsMap block not found"
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

    print("test_phm_walk: OK")


if __name__ == "__main__":
    sys.exit(main())
