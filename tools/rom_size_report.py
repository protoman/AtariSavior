#!/usr/bin/env python3
"""ROM size report — per bank code/data/fill + level-data totals.

Source of truth is the DASM listing (bank*.lst): a listing row that carries
byte columns contributes `next_row_addr - row_addr` bytes (this also handles
DASM's truncated `00 00 00 00*` column form). Rows are classified by the
source text printed on the same line:

  code  = instructions
  data  = .byte / .word / .byte.b  (tables, sprites, generated level data)
  fill  = .ds                     (padding; free for growth)

Level-data totals are measured with convert_level._gen_data_size on the
generated .asm files (index + per-level tables + shared models).

Run: /home/iuri/python3/bin/python3 tools/rom_size_report.py [--md]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT / "tools"))
from convert_level import _gen_data_size  # noqa: E402

BANKS = {0: "kernel.asm", 1: "bank1.asm", 2: "bank2.asm", 3: "bank3.asm"}


def rows(lst: Path) -> list[tuple[int, bool, str]]:
    out = []
    if not lst.exists():
        return out
    for ln in lst.read_text(errors="replace").splitlines():
        m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+((?:[0-9a-f]{2}\s+)+)", ln)
        if m:
            out.append((int(m.group(1), 16), True, ln))
            continue
        m2 = re.match(r"^\s*\d+\s+([0-9a-f]{4})\b", ln)
        if m2:
            out.append((int(m2.group(1), 16), False, ln))
    return out


def classify(line: str) -> str:
    # Text after the byte columns is the original source line.
    body = re.sub(r"^\s*\d+\s+[0-9a-f]{4}\s+(?:[0-9a-f]{2}\s+)+\*?\s*", "", line)
    if not body:
        body = line
    if ".ds" in body:
        return "fill"
    if ".byte" in body or ".word" in body:
        return "data"
    return "code"


def bank_sizes(bank: int) -> dict[str, int]:
    lst = SRC / f"bank{bank}.lst"
    r = rows(lst)
    acc = {"code": 0, "data": 0, "fill": 0}
    for i, (addr, has_bytes, line) in enumerate(r):
        if not has_bytes:
            continue
        # A `NAME = value` row emits no ROM. DASM prints the value in the byte
        # columns and (after a positive-length `.ds`) keeps the preceding
        # address, so counting it steals the `.ds` fill it sits inside
        # (bank1's $FD00 -> $FDE3 pad was reported as code before this).
        if re.match(r"^[A-Za-z_.][A-Za-z0-9_.]*\s*=\s*",
                    re.sub(r"^\s*\d+\s+[0-9a-f]{4}\s+(?:[0-9a-f]{2}\s+)+\*?\s*",
                           "", line)):
            continue
        nxt = r[i + 1][0] if i + 1 < len(r) else addr + 1
        if nxt == addr and ".ds" in line:
            # Truncated `.ds` row: DASM prints the START address, and the rows
            # inside the fill keep it. The fill ends at the next address jump.
            for j in range(i + 1, len(r)):
                if r[j][0] > addr:
                    nxt = r[j][0]
                    break
        size = nxt - addr if nxt > addr else 0
        if not 0xF000 <= addr < 0x10000:
            continue
        acc[classify(line)] += size
    acc["used"] = acc["code"] + acc["data"]
    acc["free"] = 4096 - acc["used"]
    return acc


def level_data_sizes() -> dict[str, int]:
    gen = SRC / "generated"
    idx = gen / "levels_index.asm"
    levels = sorted(gen.glob("level_*_rooms.asm"))
    blocks = sorted(gen.glob("level_*_blocks.asm"))   # A3: bank3 blocks
    models = gen / "models_data.asm"
    return {
        "index": _gen_data_size(idx) if idx.exists() else 0,
        "levels": sum(_gen_data_size(p) for p in levels)
        + sum(_gen_data_size(p) for p in blocks),
        "models": _gen_data_size(models) if models.exists() else 0,
        "total": (_gen_data_size(idx) if idx.exists() else 0)
        + sum(_gen_data_size(p) for p in levels)
        + sum(_gen_data_size(p) for p in blocks)
        + (_gen_data_size(models) if models.exists() else 0),
    }


def main() -> int:
    md = "--md" in sys.argv
    banks = {b: bank_sizes(b) for b in BANKS}
    lv = level_data_sizes()
    if md:
        print("| bank | code | data | fill | used | free |")
        print("|---|---|---|---|---|---|")
        for b in BANKS:
            s = banks[b]
            print(f"| bank{b} | {s['code']} | {s['data']} | {s['fill']} | "
                  f"{s['used']} | {s['free']} |")
        tot_c = sum(s["code"] for s in banks.values())
        tot_d = sum(s["data"] for s in banks.values())
        tot_f = sum(s["fill"] for s in banks.values())
        print(f"| **total** | **{tot_c}** | **{tot_d}** | **{tot_f}** | "
              f"**{tot_c + tot_d}** | **{16384 - tot_c - tot_d}** |")
        print()
        print(f"level data: index {lv['index']} + tables/blocks {lv['levels']} "
              f"+ models {lv['models']} = **{lv['total']} B**")
        return 0
    for b in BANKS:
        s = banks[b]
        print(f"bank{b}: code {s['code']:4d}  data {s['data']:4d}  "
              f"fill {s['fill']:4d}  used {s['used']:4d}  free {s['free']:4d}")
    print(f"level data: index {lv['index']} + tables {lv['levels']} + "
          f"models {lv['models']} = {lv['total']} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
