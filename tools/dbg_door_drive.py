"""Drive the staged door ROM in py65 and watch the player walk into the door.

Stage: level 1 room 1 is a door room (side-1 LOCKED_DOOR at col 5 -> strip at
x = 7 + 8*5 = 47); the level start x is 32, so holding RIGHT walks into it.
Boot needs the title's RESET press (frames 1-2), like the sims.
"""
import sys
from pathlib import Path

from py65.devices.mpu6502 import MPU

ROM = Path("/tmp/opencode/savior_door.bin")
data = ROM.read_bytes()
BANKS = [bytearray(data[i * 4096:(i + 1) * 4096]) for i in range(8)]

ROOMX = 0x00     # $80
SWCHA = 0x280
SWCHB = 0x282


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.bank = 7                       # F4 powers up in bank 7
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.frames = 0
        self.lines = 0

    def __getitem__(self, a):
        if a < 0x80:
            return 0
        if a < 0x100:
            return self.ram[a & 0x7F]
        if a == SWCHA:
            return self.swcha
        if a == SWCHB:
            return self.swchb
        if 0x280 <= a <= 0x28F:
            return 0xFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        return 0

    def __setitem__(self, a, v):
        v &= 0xFF
        if a < 0x80:
            if a == 0x02:                    # WSYNC write = one scanline
                self.lines += 1
            return
        if a < 0x100:
            self.ram[a & 0x7F] = v
            return
        if 0x1FF4 <= a <= 0x1FFB:
            self.bank = a - 0x1FF4
            return
        if a >= 0xF000:
            BANKS[self.bank][a - 0xF000] = v


def main() -> int:
    mem = Mem()
    mpu = MPU(memory=mem)
    mpu.sp = 0xFF
    mem.bank = 7
    vec = BANKS[7][0xFFC] | (BANKS[7][0xFFD] << 8)
    mpu.pc = vec
    print(f"reset vector ${vec:04X} (bank 7)")

    roomx = []
    last_frame = 0
    steps = 0
    while mem.frames < 200:
        steps += 1
        if steps > 30_000_000:
            print("runaway after", mem.frames, "frames")
            return 1
        mpu.step()
        mem.frames = mem.lines // 262
        if mem.frames != last_frame:
            last_frame = mem.frames
            f = mem.frames
            mem.swchb = 0xFE if f in (2, 3) else 0xFF
            mem.swcha = 0x7F if f >= 8 else 0xFF     # hold RIGHT
            roomx.append(mem.ram[ROOMX])

    tail = roomx[-30:]
    print("RoomX per frame (last 30):", tail)
    peak = max(roomx)
    print("peak RoomX:", peak, "(door strip at x=47)")
    if peak >= 48:
        print("VERDICT: CROSSED the door column -> door did NOT block")
        return 1
    if peak >= 44:
        print("VERDICT: STOPPED at the door -> door BLOCKED")
        return 0
    print("VERDICT: never reached the door (setup problem)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
