#!/usr/bin/env python3
"""Title level display = packed BCD (user report 2026-10-20, level 10+).

The title screen doubles as the level selector: SELECT cycles the start level
and the selected number is shown in the ordinary HUD score field, which the
score renderer reads as PACKED BCD (tens = ScoreTe>>4, ones = ScoreTe&$F).
The title used to store `Level+1` raw, so level 10 wrote $0A → tens 0, ones 10
= the blank glyph.

`kernel.TitleBcd` now converts A (1-based level) to packed BCD; the title path
(`DropArm.DATitle`) calls it with Level+1. This drives the real routine on the
frozen bank image for levels 1..20 and a >LEVEL_COUNT sanity value, and pins
the call site so the conversion cannot silently fall back to raw binary.

Run: /home/iuri/python3/bin/python3 tools/test_title_level.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

import test_cell_map as _CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402

SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"

for _i in range(8):
    setattr(_CM, f"BANK{_i}", (FROZEN / f"bank{_i}.bin").read_bytes())
Mem = _CM.Mem

L0 = parse_labels(FROZEN / "bank0.lst", {"TitleBcd", "ScoreTe"})
if {"TitleBcd", "ScoreTe"} - set(L0):
    sys.exit(f"bank0.lst missing labels: {sorted({'TitleBcd', 'ScoreTe'} - set(L0))}")

KERNEL = (SRC / "kernel.asm").read_text(encoding="utf-8")


def run_bcd(level: int) -> int:
    mem = Mem()
    mem.bank = 0
    mpu = MPU(memory=mem)
    mpu.pc = L0["TitleBcd"]
    mpu.a = level & 0xFF
    mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(500):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return mem.ram[L0["ScoreTe"] - 0x80]
    sys.exit(f"TitleBcd(level={level}) never returned (pc=${mpu.pc:04X})")


def main() -> int:
    # --- call site: the title path must convert, not store raw binary -----
    title = KERNEL.split(".DATitle:")[1].split("DropStep:")[0]
    code = "\n".join(l.split(";")[0] for l in title.splitlines())
    assert "jsr TitleBcd" in code, \
        "DropArm.DATitle must call TitleBcd (raw Level+1 is invalid BCD at 10)"
    assert re.search(r"lda Level\s*\n\s*clc\s*\n\s*adc #1\s*\n\s*jsr TitleBcd",
                     code), "TitleBcd must be called with Level+1 (1-based)"

    # --- routine: every level the game can select -------------------------
    for level in range(1, 21):
        want = (level // 10) * 0x10 | (level % 10)
        got = run_bcd(level)
        assert got == want, (
            f"level {level}: ScoreTe=${got:02X} want ${want:02X} "
            "(packed BCD; the renderer reads >>4 and &$F)")

    # --- 99 (banner's stated ceiling) must still be exact -----------------
    got = run_bcd(99)
    assert got == 0x99, f"level 99: ScoreTe=${got:02X} want $99"

    print("test_title_level: OK (1..20 + 99, call site pinned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
