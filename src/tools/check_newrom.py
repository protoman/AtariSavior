#!/usr/bin/env python3
"""Checks of the NEW ROM layout (docs/agents/banks.md): every bank is 4 KB and carries the boot stub
and vectors (verify_build.check_boot_banks, the same check the old ROM passes), and a zone table of how
much of each bank is filled. Usage: check_newrom.py <dir with bank0.bin..bank7.bin>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_build as V  # noqa: E402

ZONES = ["general", "cave", "gameplay", "gameplay+HUD", "other+models", "levels A", "levels B", "levels C"]


def main() -> int:
    d = Path(sys.argv[1])
    V.ERRORS.clear()
    V.check_boot_banks(d)
    for i in range(8):
        data = (d / f"bank{i}.bin").read_bytes()
        used = sum(1 for k, x in enumerate(data[:0xFFA - 0x0]) if x and not (k < 5))
        print(f"  newrom bank{i} [{ZONES[i]:13s}] real bytes (non-zero, after the stub): {used}")
    if V.ERRORS:
        for e in V.ERRORS:
            print("FAIL:", e)
        return 1
    print("check_newrom: OK (8 banks, boot stub + vectors in every bank)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
