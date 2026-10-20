#!/home/iuri/python3/bin/python3
"""Auto-repro bugs.md #1: water death -> respawn -> hold Up.

Boots the real savior.bin, forces Level=1 (second level), turns the entered
room into a water room (pokes the level's band byte AT THE ROOM LOAD), lets the
band kill the player, then holds Up+Right and watches whether he survives the
respawn or falls back into the band (death loop).

The band byte is poked on the EnterRoom ($FBD0) trampoline: that is the only
point where (a) the level base/count and the target room are all final in ZP
and (b) bank2 has not yet read RoomEnemies[room]+1 (EnterRoomB2 stages
RoomBandColor once per room). Poking at a StartFrame instead lands AFTER the
room load, so RoomBandColor stays $00 and the water never exists — the old
version of this test did exactly that and passed with zero deaths.

Exit 0 = the water killed him and he did NOT loop; 1 = no death at all (the
scenario never ran — fail loudly) or a post-respawn death loop.
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
BANKS = [bytearray(open(SRC / f"bank{i}.bin", "rb").read()) for i in range(4)]


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x40

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            return 0
        if a == 0x000C:
            return self.inpt4
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF6 <= a <= 0x1FF9:
            self.bank = a - 0x1FF6
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            self.tia[a & 0x3F] = v


mem = Mem()
from py65.devices.mpu6502 import MPU  # noqa: E402
mpu = MPU(memory=mem)

_LBL = {}
for _l in open(SRC / "bank0.lst", errors="replace"):
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$", _l)
    if _m:
        _LBL.setdefault(_m.group(2), int(_m.group(1), 16))
PC_STARTFRAME = _LBL["StartFrame"]
LOADLEVEL = _LBL["LoadLevel"]
ENTERROOM = _LBL["EnterRoom"]          # $FBD0: bank0 half of the tramp
# ZP index = address - $80 (the Mem view maps $80-$FF onto ram[0..127]).
I_ROOMY, I_LPF, I_ROOMN = 0x01, 0x1F, 0x21        # $81 $9F $A1
I_LIVES, I_DROP, I_HOVER = 0x2C, 0x0A, 0x1C       # $AC $8A $9C
I_BAND = 0x3C                                     # $BC RoomBandColor
# The staged color comes from the ROM: one bottom-band color per game, emitted
# by convert_level into generated/levels_equ.asm (2026-10-20 pack).
_BAND_EQU = SRC / "generated" / "levels_equ.asm"
_m = re.search(r"^BAND_COLOR = \$([0-9a-fA-F]{2})", _BAND_EQU.read_text(),
               re.M) if _BAND_EQU.exists() else None
BAND_COLOR = int(_m.group(1), 16) if _m else 0


def at_init_jsr():
    return (mem[mpu.pc] == 0x20
            and mem[mpu.pc + 1] | (mem[mpu.pc + 2] << 8) == LOADLEVEL
            and mpu.pc < PC_STARTFRAME)


guard = 0
while not at_init_jsr():
    mpu.step()
    guard += 1
    if guard > 200000:
        sys.exit(f"never reached init LoadLevel (pc=${mpu.pc:04X})")
mem.ram[0x23] = 1        # second level

frame = 0
pokes = 0
armed = None             # frame the player was placed in the water
dropped = False          # RoomY forced once, after the drop-in finishes
deaths = []              # frames where a life was lost
last_lives = 3
log = []

while frame < 520:
    mpu.step()
    if mem.bank == 0 and mpu.pc == ENTERROOM:
        # A = target room index (all callers: exits pass the room index the
        # position scan found, LoadLevel passes LevelStartRoom). ZP holds the
        # level block base + the room count; the room's band FLAG is b6 of its
        # ONE-byte RoomShapes record (C2 2026-10-20: base + room).
        room = mpu.a
        n = mem.ram[I_ROOMN]
        base = mem.ram[I_LPF] | (mem.ram[I_LPF + 1] << 8)
        rec = base + room
        if 0xF000 <= rec <= 0xFFFF:
            BANKS[2][rec - 0xF000] |= 0x40     # bottom-band flag
            pokes += 1
            print(f"band flag @ ${rec:04X} forced at f{frame} "
                  f"(room {room}, n={n})")
        else:
            sys.exit(f"band record ${rec:04X} outside bank2 (room {room})")
    elif mem.bank == 0 and mpu.pc == PC_STARTFRAME:
        frame += 1
        mem.swchb = 0xFE if frame in (2, 5) else 0xFF
        # Place him IN the band only after (a) the water room was loaded with
        # the poked band byte and (b) the drop-in finished ($8A==0); forcing
        # RoomY mid drop-in fought DropArm.
        if pokes and not dropped and mem.ram[I_DROP] == 0:
            mem.ram[I_ROOMY] = 131
            dropped = True
            armed = frame
            print(f"RoomY->131 (in the band) at f{frame}, "
                  f"RoomBandColor=${mem.ram[I_BAND]:02X}")
        if dropped and armed is not None and frame > armed:
            y, lv, hv = mem.ram[I_ROOMY], mem.ram[I_LIVES], mem.ram[I_HOVER]
            mem.swcha = 0x6F            # hold Up + Right
            if lv < last_lives:
                last_lives = lv
                deaths.append(frame)
                print(f"  f{frame}: DEATH (lives={lv}, RoomY={y})")
            log.append((frame, y, lv, hv))
            if frame % 10 == 0 and frame >= armed:
                print(f"  f{frame}: Y={y} vy={mem.ram[0x14]:02X}{mem.ram[0x13]:02X} "
                      f"JP={mem.ram[0x16]:02X} Hover={hv}")

band_live = mem.ram[I_BAND]
min_lives = min((lv for _, _, lv, _ in log), default=3)
loop_deaths = max(0, len(deaths) - 1)
tail = [y for (f, y, lv, hv) in log if f >= log[-1][0] - 100] if log else []
print(f"\nband pokes={pokes}, RoomBandColor=${band_live:02X}, "
      f"total deaths={len(deaths)} (lives lost {3 - min_lives}); "
      f"loop deaths after respawn={loop_deaths}")
print("last 100 frames RoomY min/max:", (min(tail), max(tail)) if tail else None,
      "(band starts at 125)")

if not pokes:
    print("FAIL: EnterRoom was never hooked — scenario did not run")
    sys.exit(1)
if not BAND_COLOR or band_live != BAND_COLOR:
    print(f"FAIL: RoomBandColor=${band_live:02X}, expected ${BAND_COLOR:02X} "
          "(the band flag poke landed after the room load, or levels_equ.asm "
          "is stale)")
    sys.exit(1)
if len(deaths) < 1 or min_lives > 2:
    print("FAIL: the water never killed him — the gate cannot be trusted")
    sys.exit(1)
if loop_deaths == 0:
    print("PASS: water killed him once, no death loop after respawn")
    sys.exit(0)
print("FAIL: water death loop")
sys.exit(1)
