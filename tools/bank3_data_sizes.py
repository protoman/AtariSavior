#!/usr/bin/env python3
"""Bank3 level-data split report (shape half vs extras half).

The bank3 data window is $F010-$F44F (1088 B): shape blocks + row pool +
per-level extras + the extras base table. This prints the two halves so a
two-slot split (shapes -> another gap, extras staying) can be planned from
measured bytes instead of guesses.

Run: /home/iuri/python3/bin/python3 tools/bank3_data_sizes.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "src" / "generated"


def main() -> int:
    models = GEN / "models_data.asm"
    if not models.exists():
        sys.exit("models_data.asm missing (run ./build.sh first)")
    # Count emitted payload bytes directly from the .byte lines (the helper
    # above is line-shape fragile; count values plainly).
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
    extras_files = sorted(GEN.glob("level_*_extras.asm")) + \
        [GEN / "levels_extras.asm"]
    extras_bytes = sum(payload(p) for p in extras_files if p.exists())
    slot = 0xF450 - 0xF010
    print(f"bank3 data slot: {slot} B ($F010-$F44F)")
    print(f"  shapes + row pool : {shape_bytes} B")
    print(f"  extras + base tbl : {extras_bytes} B")
    print(f"  total             : {shape_bytes + extras_bytes} B "
          f"({slot - shape_bytes - extras_bytes} B slack)")
    print("split candidate: shapes -> $F5BF (760 B), "
          f"extras -> $F010 (1088 B; needs <= {slot} B, have {extras_bytes})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
