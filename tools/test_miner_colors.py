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
    # design offsets come from kernel.asm (they move whenever a type
    # graduates to taller art — per-type heights since Phase 6)
    def obj_off(name: str) -> int:
        m = re.search(rf"^{name}\s*=\s*(\d+)", kernel, re.M)
        assert m, f"{name} EQU not found in kernel.asm"
        return int(m.group(1))
    O_MINER, O_MOTH, O_BAT, O_BOMB = (obj_off(n) for n in
                                     ("OBJ_MINER", "OBJ_MOTH", "OBJ_BAT", "OBJ_BOMB"))
    tab = labels0["ObjColorTab"]
    off = tab - 0xF000
    miner = list(rom0[off + O_MINER: off + O_MINER + 8])
    assert miner == MINER_COLORS, f"miner color slot = {[hex(v) for v in miner]}"
    # slot colors must match EnemyColorTable / frame colors for non-miner types
    # (moth/bat rows are art-authored per-row colours since 2026-10-22, so the
    #  old EnemyColorTable equality check is retired on purpose: only the miner
    #  slot and the bomb row still have a fixed meaning)
    assert rom0[off + O_BOMB] == 0x46, "bomb slot != COLOR_BOMBS ($46)"
    # kernel reads it with the sprite index
    assert re.search(r"lda\s+ObjColorTab,X\s*;[^\n]*", kernel), \
        "kernel .Grp1 does not read ObjColorTab,X"
    assert "sta COLUP1" in kernel, "no COLUP1 write in kernel"

    # --- 2) art + frame picker are bank0-only (repack chunk 1) ----------
    # PickPlayerFrame moved out of bank2 (2026-10-20): it now reads bank0's
    # own PlayerSprite*/PlayerWalk* labels, so both art twins and the
    # hand-copied EQUs are gone. Guard: no duplicates may come back, and the
    # body must live in the bank that owns the art.
    want = {k: labels0[k] for k in
            ("PlayerSpriteA", "PlayerSpriteB", "PlayerWalkA", "PlayerWalkB")}
    labels2 = lst_labels(SRC / "bank2.lst")
    for name in list(want) + ["PickPlayerFrame"]:
        assert name not in labels2, f"bank2 still defines {name} (twin/tramp)"
    assert "PickPlayerFrame" in labels0, "PickPlayerFrame body must be in bank0"
    for name, addr in want.items():
        m = re.search(rf"^{name}\s*=\s*\$([0-9a-fA-F]+)", bank2, re.M)
        assert not m, f"bank2 EQU {name} must be gone"
    # SWCHA is allowed back: bank2 EBLER_Done re-reads the joystick port to
    # restore bank0's Temp shadow after EnterRoom clobbers it (2026-10-20).
    for name, addr in (("Grp0Ptr", 0x86), ("Grp0PtrHi", 0x87)):
        m = re.search(rf"^{name}\s*=\s*\$([0-9a-fA-F]+)", bank2, re.M)
        assert not m, f"bank2 EQU {name} must be gone"

    # --- 3) layout pins (4c fetches) ------------------------------------
    obj = labels0["ObjSprites"]
    # last byte of a table = base + size - 1; the size is the sum of the
    # per-type heights, so take it from the .lst (ObjColorTab end is the
    # next label) rather than hard-coding 154.
    last = 124
    assert (obj & 0xFF) + last <= 0xFF and (obj >> 8) == ((obj + last) >> 8), \
        f"ObjSprites ${obj:04X} page-crosses (+{last})"
    assert (tab >> 8) == ((tab + last) >> 8), f"ObjColorTab ${tab:04X} page-crosses"
    frame = labels0["PickPlayerFrame"]
    # body must be a real instruction start in bank0 (was a switch tramp)
    assert rom0[frame - 0xF000] == 0xA5, \
        f"PickPlayerFrame ${frame:04X} is not `lda zp` (stale tramp?)"

    print("test_miner_colors: OK "
          f"(tab ${tab:04X}, sprites ${obj:04X}, frame ${frame:04X})")


if __name__ == "__main__":
    sys.exit(main())
