#!/usr/bin/env python3
"""Level-bank fold static checks (level_bank_plan P1; assert-based).

Source-shape contract for the cross-bank fold (HERO fold, write-triggered):

  - FoldIndirect block exists in kernel.asm AND bank2.asm with exactly the
    four contracted instructions in order (sta $1FF8,X / lda (FetchPtr),Y /
    sta $1FF6 / rts) — hand-edited drift in one bank breaks execution at
    the switch point.
  - FetchPtr = $E0 defined in both files (operand is baked per file).
  - kernel.asm: block sits right before `.ds $FF00 - *, 0` (margin directive
    to the $FF00 fineAdjust anchor — an assembler error, not silent growth).
  - bank2.asm: `.ds $FEF6 - *, 0` pins the block to the same address.
  - bank1.asm rebuilds scorePtr1 ($E0/$E1) every HUD frame, so bank0 must
    stage FetchPtr before every fold batch (contract §0.2 — staging is
    enforced when fold call sites land in P2/P3; here we just pin the
    writers that make the alias family real).

Bin-level byte-identity + label addresses are guarded by verify_build.py
(check_fold_block) — run this test after ./build.sh for full coverage.

Run: python3 tools/test_level_bank.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = (ROOT / "src" / "kernel.asm").read_text(encoding="utf-8")
BANK1 = (ROOT / "src" / "bank1.asm").read_text(encoding="utf-8")
BANK2 = (ROOT / "src" / "bank2.asm").read_text(encoding="utf-8")

BLOCK = [
    "sta $1FF8,X",
    "lda (FetchPtr),Y",
    "sta $1FF6",
    "rts",
]


def block_body(src: str, label: str) -> list[str]:
    """Instruction lines from `label:` until a non-instruction line."""
    m = re.search(rf"^{label}:\s*$(.*?)(?=^\S|\Z)", src, re.M | re.S)
    assert m, f"{label} label not found"
    body = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith(".ds"):
            if body:  # block ends at first blank/comment after instructions
                break
            continue
        body.append(line)
    return body


def main() -> None:
    # --- block shape, both banks ------------------------------------------
    for name, src in (("kernel.asm", KERNEL), ("bank2.asm", BANK2)):
        body = block_body(src, "FoldIndirect")
        assert body == BLOCK, \
            f"{name}: FoldIndirect body {body} != contract {BLOCK}"

    # --- FetchPtr operand, both files -------------------------------------
    for name, src in (("kernel.asm", KERNEL), ("bank2.asm", BANK2)):
        m = re.search(r"^FetchPtr\s*=\s*\$E0\b", src, re.M)
        assert m, f"{name}: FetchPtr = $E0 definition missing"

    # --- address pinning ---------------------------------------------------
    assert re.search(r"FoldIndirect:.*?\.ds \$FF00 - \*, 0", KERNEL, re.S), \
        "kernel.asm: block must be followed by the .ds $FF00 margin directive"
    assert re.search(r"\.ds \$FEF6 - \*, 0\s*\nFoldIndirect:", BANK2), \
        "bank2.asm: .ds $FEF6 must pin the block to bank0's address"

    # --- P1.3: $E0/$E1 alias writers (stage-before-batch precondition) ----
    assert "sta scorePtr1+1" in BANK1 and "sta scorePtr1" in BANK1, \
        "bank1 must rebuild scorePtr1 ($E0/$E1) — FetchPtr alias family"
    # kernel must not write $E0 directly (only via FetchPtr staging later)
    assert not re.search(r"sta\s+\$E0\b", KERNEL), \
        "kernel.asm writes $E0 raw — use the FetchPtr EQU for alias clarity"

    # --- P2: no cold (pre-fold) reads of relocated tables ------------------
    for tbl in ("LevelPFDataLo", "LevelEnemyLo", "LevelConnLo"):
        assert not re.search(rf"lda \({tbl}\),Y", KERNEL), \
            f"kernel.asm still reads ({tbl}),Y directly — route via FoldIndirect"
    assert KERNEL.count("jsr FoldIndirect") >= 14, \
        f"expected >=14 fold call sites (LoadLevel 14), " \
        f"got {KERNEL.count('jsr FoldIndirect')}"

    # --- P2.5: band-color cache contract ----------------------------------
    assert re.search(r"^RoomBandColor\s*=\s*\$D1\b", KERNEL, re.M), \
        "RoomBandColor = $D1 (PF1Buf[2] alias) missing"
    m = re.search(r"^LoadRoomBottomColor:\s*\n((?:[ \t].*\n)+)", KERNEL, re.M)
    assert m and "lda RoomBandColor" in m.group(1), \
        "LoadRoomBottomColor must read the VBLANK-staged cache"
    assert "sta RoomBandColor" in KERNEL, \
        "VBLANK stage (sta RoomBandColor) missing"

    # --- LEVEL_COUNT hand-copy stays in sync with generated data -----------
    gen = (ROOT / "src" / "generated" / "levels.asm").read_text(
        encoding="utf-8")
    n_levels = len(re.findall(r"^\s*\.word\s+LEVEL\d+_RoomDataTable",
                              gen, re.M))
    m = re.search(r"^LEVEL_COUNT\s*=\s*(\d+)", KERNEL, re.M)
    assert m and int(m.group(1)) == n_levels, \
        f"LEVEL_COUNT = {m and m.group(1)} != {n_levels} generated levels"

    # --- frozen data address: hand-copy matches bank2 listing --------------
    lst = (ROOT / "src" / "bank2.lst").read_text(encoding="utf-8")
    m = re.search(r"^\s+\d+\s+([0-9a-f]{4})\s+LevelDataTable\b", lst, re.M)
    assert m, "LevelDataTable not found in bank2.lst"
    m2 = re.search(r"^LEVEL_DATA_ADDR\s*=\s*\$([0-9A-Fa-f]{4})", KERNEL, re.M)
    assert m2 and m2.group(1).lower() == m.group(1), \
        f"LEVEL_DATA_ADDR ${m2 and m2.group(1)} != " \
        f"bank2 LevelDataTable ${m.group(1)}"

    print("test_level_bank: all asserts passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
