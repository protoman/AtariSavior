#!/usr/bin/env python3
"""The bank6 cave kernel's zero page contract (tools/cave_kernel_gen.py LIVE / KERNEL_ZP).

  * every LIVE name (a byte the kernel READS from the rest of the game) must sit at the address
    bank0's symbol dump says (a ZP move in kernel.asm would silently break the kernel);
  * every kernel-local byte must be one that is free while the cave runs: VBL/overscan scratch
    that is restaged before use (names whitelisted below), bank1-only HUD bytes ($E0-$EF, the HUD
    rewrites them before reading), the EnemyRamY window ($E2-$E4: written at overscan entry,
    read before the next stomp) and the stack bytes $F8-$FF (bank6 never calls; the deepest call
    chain is checked by sim_bomb_fuse at >= $F8);
  * no two kernel-local names share a byte (apart from the documented aliases).

Run: /home/iuri/python3/bin/python3 tools/test_cave_zp.py   (needs a built tree: generated/symbols.asm)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import cave_kernel_gen as G  # noqa: E402

sym = {}
for line in (ROOT / "generated" / "symbols.asm").read_text().splitlines():
    m = re.match(r"^(\S+)\s+([0-9a-fA-F]{4})\b", line)
    if m:
        sym[m.group(1)] = int(m.group(2), 16)

# bank0 names that may share a byte with a kernel-local name, and why (all restaged before use)
SYMNAME = {"PF0B": "PF0Buf", "PF1B": "PF1Buf", "PF2B": "PF2Buf", "CPFB": "ColupfBuf"}
SCRATCH = {
    "EnemyRamY": "$E2-$E4: written at overscan entry, every read comes before the next HUD stomp",
    "FetchPtr": "staged-only (stage -> read inside one VBL/overscan batch)",
    "LineCount": "VBL scratch (bank3 StageBandTab / old kernel counter)",
    "Grp0Ptr": "read by the prologue first, then reused",
    "Grp0PtrHi": "restaged by PickPlayerFrame every VBL",
    "Temp": "VBL scratch",
    "CollisionCellX": "overscan scratch",
    "CollisionCellY": "door colour: read by the prologue first",
    "CollisionEndX": "overscan scratch (M1X is consumed in the VBL)",
    "CollisionEndY": "overscan scratch",
    "RectCount": "RowIdx: old-kernel counter / hot-record loop counter after the kernel",
    "RowIdx": "alias of RectCount",
    "ObjX1": "repacked into S1Pos by the prologue (bank2 restages it every VBL)",
}


def main():
    bad = []
    for name, addr in G.LIVE.items():
        real = SYMNAME.get(name, name)
        if sym.get(real) != addr:
            bad.append(f"LIVE {name}: generator ${addr:02X}, kernel.asm {sym.get(real)}")
    owners = {}
    for name, addr in G.KERNEL_ZP.items():
        size = 2 if name in ("G0", "C0", "G1", "C1", "G1hiC", "C1hiC", "KbC", "EC") else 1
        for k in range(size):
            owners.setdefault(addr + k, []).append(name)
    for addr, names in sorted(owners.items()):
        if len(names) > 1 and set(names) not in ({"S1Pos", "ObjX1"}, {"S1Adj", "CtxNext"}):
            bad.append(f"${addr:02X} claimed twice: {names}")
        live = [n for n, a in sym.items() if a == addr and not n.startswith(("0.", "NC_", "COLOR_"))
                and "." not in n and 0x80 <= a <= 0xFF]
        for n in live:
            ok = (n in SCRATCH or 0xE0 <= addr <= 0xEF and n.startswith(("scorePtr", "scbrd", "Delay", "Fine"))
                  or addr >= 0xF8)
            if not ok and n not in G.KERNEL_ZP:
                # stack-area / HUD-only names are not in bank0's dump; anything else is state
                bad.append(f"${addr:02X} ({names}) overlays bank0 state {n}")
    # bank1-only HUD bytes and the EnemyRamY window are not bank0 symbols: pin them here
    for addr in (0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xED, 0xEE, 0xEF):
        assert addr in owners, f"${addr:02X} expected to be used"
    if bad:
        print("FAIL:")
        for b in bad:
            print("  ", b)
        return 1
    print(f"test_cave_zp: OK ({len(G.LIVE)} live names pinned, {len(owners)} kernel-local bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
