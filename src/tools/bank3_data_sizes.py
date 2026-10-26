#!/usr/bin/env python3
"""Bank3 level-data split report (shape window vs extras window).

C12 (2026-10-21): the two halves live in separate windows —
  extras -> $F010-$F44F (1088 B), shapes -> $F5CC-$F8B6 (747 B).
This prints each half against its slot, and (optionally) how many shapes
another 8-byte block would fit, so a generator shape budget comes from
measured bytes.

Run: /home/iuri/python3/bin/python3 tools/bank3_data_sizes.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "generated"

EXTRAS_SLOT = 0xF450 - 0xF010
SHAPES_SLOT = 0xF8B7 - 0xF5CC


def main() -> int:
    models = GEN / "models_data.asm"
    if not models.exists():
        sys.exit("models_data.asm missing (run ./build.sh first)")

    def payload(p: Path) -> int:
        total = 0
        for line in p.read_text(errors="replace").splitlines():
            body = line.split(";", 1)[0]
            m = re.search(r"\.byte\s+(.*)$", body)
            if m:
                total += len([v for v in m.group(1).split(",") if v.strip()])
            m = re.search(r"\.word\s+(.*)$", body)
            if m:
                total += 2 * len([v for v in m.group(1).split(",") if v.strip()])
        return total

    shape_bytes = payload(models)
    shapes = len(re.findall(r"^\s*M\d+Shape:", models.read_text(
        errors="replace"), re.M))
    extras_files = sorted(GEN.glob("level_*_extras.asm")) + \
        [GEN / "levels_extras.asm"]
    extras_bytes = sum(payload(p) for p in extras_files if p.exists())
    print(f"bank3 extras slot: {EXTRAS_SLOT} B ($F010-$F44F)")
    print(f"  extras + base tbl : {extras_bytes} B "
          f"({EXTRAS_SLOT - extras_bytes} B slack)")
    print(f"bank3 shapes slot: {SHAPES_SLOT} B ($F5CC-$F8B6)")
    print(f"  shapes + row pool : {shape_bytes} B for {shapes} shapes "
          f"({SHAPES_SLOT - shape_bytes} B slack)")
    if shapes:
        per = shape_bytes / shapes
        print(f"  ~{per:.2f} B/shape -> room for ~{int(SHAPES_SLOT / per)} "
              "shapes at this average")
    return 0


if __name__ == "__main__":
    sys.exit(main())
