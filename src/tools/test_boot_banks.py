#!/usr/bin/env python3
"""F4 power-up guard: any of the EIGHT banks can be the first one executed.

The bank latch is undefined at power-up on real hardware (Stella only randomises it
when developer settings are on), so a cart that assumes "we always boot in bank N"
hangs 1-in-8. This drives each bank's RESET vector in py65 from an initial bank of
0..7, asserts the CPU lands in BANK0 at GameStart ($F008) and that the game then
reaches its first frame (StartFrame). History: banks 5 and 6 had no boot stub after
the F4 move (bank5 even had the version string at $F000), a 2-in-8 chance of a dead
boot on real hardware (user, 2026-10-28); this test only covered banks 0-3.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem, parse_labels  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"
BANKS = {}
for i in range(8):
    p = FROZEN / f"bank{i}.bin"
    if p.exists() and p.stat().st_size == 4096:
        BANKS[i] = p.read_bytes()
if len(BANKS) < 8:
    sys.exit("frozen bank images missing")


def reset_vector(d):
    return d[0xFFFC - 0xF000] | (d[0xFFFD - 0xF000] << 8)


PC_STARTFRAME = parse_labels(FROZEN / "bank0.lst", {"StartFrame"})["StartFrame"]


def first_frame(bank):
    mem = Mem()
    mem.bank = bank
    mpu = MPU(memory=mem)
    mpu.pc = reset_vector(BANKS[bank])
    mpu.sp = 0xFD
    for _ in range(400000):
        mpu.step()
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            return True
    return False


def boot(bank):
    mem = Mem()
    mem.bank = bank
    mpu = MPU(memory=mem)
    mpu.pc = reset_vector(BANKS[bank])
    mpu.sp = 0xFD
    for _ in range(200):
        if mpu.pc == 0xF008 and mem.bank == 0:
            return True
        mpu.step()
    return False


def main() -> int:
    for bank in range(8):
        assert first_frame(bank), (
            f"booting in bank{bank} never reached the first frame (StartFrame)")
        assert boot(bank), (
            f"booting in bank{bank} never reached bank0's GameStart at $F008 "
            f"(RESET=${reset_vector(BANKS[bank]):04X}) — the F6 latch powers up "
            "in an undefined bank, so every bank must select bank0 itself")
    print("test_boot_banks: OK (power-up in any of the 8 banks lands in bank0 at "
          "$F008 GameStart and reaches the first frame)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
