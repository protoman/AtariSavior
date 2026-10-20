#!/usr/bin/env python3
"""Room entry must restore the joystick shadow (user report 2026-10-20).

Symptom: on every room transition the player's eye snapped to face right and
the sprite twitched a pixel. EnterRoom clobbers `Temp` ($88) with room/record
scratch, but bank0's overscan input block keeps reading the shifted joystick
bits from `Temp` for the rest of that frame — so the stale byte faked a held
direction (and the first input check rewrote PlayerDir).

Fix (`bank2.EBLER_Done`): re-read SWCHA into `Temp` (4x LSR, same encoding the
input block stages) before returning to bank0. SWCHA is stable inside a frame.

Drives the real `EBLER_Done` tail on frozen banks with a stubbed joystick port
and asserts the staged value for two port patterns (incl. "nothing pressed",
the case that used to fake RIGHT).

Run: /home/iuri/python3/bin/python3 tools/test_room_input.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from py65.devices.mpu6502 import MPU  # noqa: E402

import test_cell_map as _CM  # noqa: E402
from test_cell_map import RTS_SENTINEL, parse_labels  # noqa: E402

SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"

L2 = parse_labels(FROZEN / "bank2.lst", {"EBLER_Done", "Temp"})
if {"EBLER_Done", "Temp"} - set(L2):
    sys.exit(f"bank2.lst missing labels: {sorted({'EBLER_Done', 'Temp'} - set(L2))}")

TEMP = L2["Temp"]
SWCHA = 0x0280


class MemJoystick(_CM.Mem):
    """Mem with a readable TIA joystick port (SWCHA)."""

    def __init__(self, swcha: int):
        super().__init__()
        self.swcha = swcha & 0xFF

    def __getitem__(self, a):
        if (a & 0xFFFF) == SWCHA:
            return self.swcha
        return super().__getitem__(a)


def enter_tail(swcha: int) -> tuple[int, int]:
    """Run bank2.EBLER_Done; return (Temp, bank)."""
    mem = MemJoystick(swcha)
    mem.bank = 2
    mpu = MPU(memory=mem)
    mpu.pc = L2["EBLER_Done"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    mem[0x1FF] = 0x01
    mem[0x1FE] = 0x00
    for _ in range(200):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return mem.ram[TEMP - 0x80], mem.bank
    sys.exit(f"EBLER_Done never returned (pc=${mpu.pc:04X}, bank={mem.bank})")


def main() -> int:
    # Nothing pressed (all joystick bits high) -> $F. The stale Temp used to be
    # the room index (0 for the first room = LEFT/RIGHT "pressed" after the
    # shifted-bit encoding: bit3 = 0 = RIGHT).
    temp, bank = enter_tail(0xF0)
    assert bank == 0, f"EBLER_Done must return through ReturnPad (bank={bank})"
    assert temp == 0x0F, (
        f"nothing pressed: Temp=${temp:02X} want $0F — the joystick shadow was "
        "not refreshed by EnterRoom (stale room scratch fakes a direction)")

    # Left + fire-ish pressed: D6=0 -> after >>4 bit2 = 0, others 1 -> $B.
    temp, _ = enter_tail(0xB0)
    assert temp == 0x0B, f"left held: Temp=${temp:02X} want $0B"

    # All four directions pressed -> 0.
    temp, _ = enter_tail(0x00)
    assert temp == 0x00, f"all pressed: Temp=${temp:02X} want $00"

    print("test_room_input: OK (3 port patterns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
