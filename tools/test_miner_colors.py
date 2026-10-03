"""ObjColorTab + bank2 hand-copied symbol guards (miner 3-color feature).

Covers the two silent-drift risks of the per-row GRP1 color feature:
1. ROM bytes: the MINER slot of ObjColorTab must be exactly the miner.png
   colors converted to nearest NTSC ($54 purple / $4A pink / $08 grey).
   Wrong values = wrong colors with NO build error.
2. bank2 hand copies: PickPlayerFrame's body lives in bank2 and references
   bank0-only symbols (PlayerSprite*/PlayerWalk*/Grp0Ptr/SWCHA) via EQU
   hand copies — a stale address compiles fine and renders garbage sprites.

Run: python3 tools/test_miner_colors.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

MINER_COLORS = [0x54, 0x54, 0x4A, 0x54, 0x54, 0x08, 0x54, 0x54]


def lst_labels(path: Path) -> dict[str, int]:
    labels = {}
    for line in path.read_text(errors="replace").splitlines():
        m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", line)
        if m:
            labels[m.group(2)] = int(m.group(1), 16)
    return labels


def main() -> None:
    labels0 = lst_labels(SRC / "bank0.lst")
    rom0 = (SRC / "bank0.bin").read_bytes()
    kernel = (SRC / "kernel.asm").read_text(encoding="utf-8")
    bank2 = (SRC / "bank2.asm").read_text(encoding="utf-8")

    # --- 1) color table bytes -------------------------------------------
    tab = labels0["ObjColorTab"]
    off = tab - 0xF000
    miner = list(rom0[off + 56: off + 64])
    assert miner == MINER_COLORS, f"miner color slot = {[hex(v) for v in miner]}"
    # slot colors must match EnemyColorTable / frame colors for non-miner types
    assert rom0[off + 8] == 0x22 and rom0[off + 40] == 0xF2, \
        "moth/bat slot colors drifted from EnemyColorTable"
    assert rom0[off + 64] == 0x46, "bomb slot != COLOR_BOMBS ($46)"
    # kernel reads it with the sprite index
    assert re.search(r"lda\s+ObjColorTab,X\s*;[^\n]*", kernel), \
        "kernel .Grp1 does not read ObjColorTab,X"
    assert "sta COLUP1" in kernel, "no COLUP1 write in kernel"

    # --- 2) bank2 hand copies vs bank0 labels ---------------------------
    want = {k: labels0[k] for k in
            ("PlayerSpriteA", "PlayerSpriteB", "PlayerWalkA", "PlayerWalkB")}
    for name, addr in want.items():
        m = re.search(rf"^{name}\s*=\s*\$([0-9a-fA-F]+)", bank2, re.M)
        assert m, f"bank2 EQU {name} missing"
        got = int(m.group(1), 16)
        assert got == addr, f"bank2 {name} = ${got:04X}, bank0 = ${addr:04X}"
    for name, addr in (("Grp0Ptr", 0x86), ("Grp0PtrHi", 0x87), ("SWCHA", 0x0280)):
        m = re.search(rf"^{name}\s*=\s*\$([0-9a-fA-F]+)", bank2, re.M)
        assert m, f"bank2 EQU {name} missing"
        assert int(m.group(1), 16) == addr, f"bank2 {name} wrong"

    # --- 3) layout pins (4c fetches + tramp operand) ---------------------
    obj = labels0["ObjSprites"]
    assert (obj & 0xFF) + 71 <= 0xFF and (obj >> 8) == ((obj + 71) >> 8), \
        f"ObjSprites ${obj:04X} page-crosses (+71)"
    assert (tab >> 8) == ((tab + 71) >> 8), f"ObjColorTab ${tab:04X} page-crosses"
    labels2 = lst_labels(SRC / "bank2.lst")
    tramp = labels0["PickPlayerFrame"]
    tgt = rom0[tramp - 0xF000 + 4] | (rom0[tramp - 0xF000 + 5] << 8)
    assert tgt == labels2["PickPlayerFrame"], "tramp operand != bank2 body"

    print("test_miner_colors: OK "
          f"(tab ${tab:04X}, sprites ${obj:04X}, tramp ${tramp:04X} -> ${tgt:04X})")


if __name__ == "__main__":
    sys.exit(main())
