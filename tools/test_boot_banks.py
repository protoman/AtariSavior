#!/usr/bin/env python3
"""F6 power-up guard: any of the four banks can be the first one executed.

The F6 bank latch is undefined at power-up on real hardware (Stella only
randomises it when developer settings are on), so a cart that assumes "we always
boot in bank N" hangs 1-in-4. This drives each bank's RESET vector in py65 from
an initial bank of 0..3 and asserts the CPU lands in BANK0 at GameStart ($F008).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import Mem  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "src" / "tests" / "frozen"
BANKS = {}
for i in range(4):
    p = FROZEN / f"bank{i}.bin"
    if p.exists() and p.stat().st_size == 4096:
        BANKS[i] = p.read_bytes()
if len(BANKS) < 4:
    sys.exit("frozen bank images missing")


def reset_vector(d):
    return d[0xFFFC - 0xF000] | (d[0xFFFD - 0xF000] << 8)


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
    for bank in range(4):
        assert boot(bank), (
            f"booting in bank{bank} never reached bank0's GameStart at $F008 "
            f"(RESET=${reset_vector(BANKS[bank]):04X}) — the F6 latch powers up "
            "in an undefined bank, so every bank must select bank0 itself")
    print("test_boot_banks: OK (power-up in bank 0/1/2/3 all lands in bank0 at "
          "$F008 GameStart)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
