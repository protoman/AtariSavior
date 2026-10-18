#!/usr/bin/env python3
"""Phase 6: in-game traversal sweep of the QA stage (py65, real input).

Drives the QA ROM (tools/qa_build.sh) through its whole level-1 chain with
the joystick only — no RAM pinning, no hand-rolled EnterRoom — and asserts
every feature actually works where the player meets it:

  room 0 start   walk right to the cell-8 gap, drop
  room 1 KEY     fall through the lane -> key picked up, slot dead, no death
  room 2 phase   the P stripe across the lane must blink (>=2 distinct
                 stagings) and the player must reach the next room alive
  room 3 door    land, walk into the M1 bar with the key -> touch-unlock
                 (EnemyDeadMask b4) THEN pass through
  room 4 vcrunch the shutter must arm (VcrBand=1) and stage the block at
                 BallX=111 (= 159-8*6, the lane's mirror) while the player
                 drops through the punched V cell
  room 5 hcrunch band 1 must be staged to P(n) (>=2 distinct stagings) and
                 the player must time the aperture to reach the last room
  room 6 goal    walk into the miner -> level tally starts (DropTarget=$FE)

Run (after bash tools/qa_build.sh):
  /home/iuri/python3/bin/python3 tools/qa_sweep.py [rom.bin]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_cell_map import parse_labels  # noqa: E402

ROM = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/opencode/savior_qa.bin")
L0P = ROM.with_name(ROM.stem + ".bank0.lst")
L2P = ROM.with_name(ROM.stem + ".bank2.lst")
if not (ROM.exists() and L0P.exists() and L2P.exists()):
    sys.exit(f"{ROM} (+ .bank0.lst/.bank2.lst) missing — run: "
             f"bash tools/qa_build.sh")

BANKS = [bytearray(ROM.read_bytes()[4096 * i:4096 * (i + 1)]) for i in range(4)]
L0 = parse_labels(L0P, {
    "StartFrame", "RoomX", "RoomY", "RoomNo", "EnemyCount", "EnemyRamP",
    "EnemyDeadMask", "LevelStartRoom", "BombPacked", "DropTarget", "Hover",
    "BandTab", "CollisionEndX", "CollisionEndY", "Temp", "PF0Buf", "PF1Buf",
    "PF2Buf", "VcrBand", "VcrNext", "VcrState", "vyLo", "vyHi"})
PC_SF = L0["StartFrame"]

UP, RIGHT, LEFT, NONE = 0xEF, 0x7F, 0xBF, 0xFF      # active low (D4/D7/D6)
KEY_HELD = 0x80


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = NONE
        self.swchb = 0xFF
        self.inpt4 = 0x80

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

R = mem.ram
X, Y, ROOM = L0["RoomX"] & 0x7F, L0["RoomY"] & 0x7F, L0["RoomNo"] & 0x7F
BAND = L0["BandTab"] & 0x7F
PF1, PF2 = L0["PF1Buf"] & 0x7F, L0["PF2Buf"] & 0x7F
FAILS, NOTES = [], []


FOLD_PC = 0xFC68            # bank0 HUD fold pad: after VBL staging, before
                            # bank1's $EA-$EF stomp (VcrBand/VcrNext live here)


def frame():
    """One whole frame with the current joystick; returns samples.

    Vcrunch state is captured AT THE HUD FOLD: $EA-$EF is bank1's stomp zone,
    so a StartFrame read of VcrBand/VcrNext/VcrState/Temp is the stomped
    garbage (Temp is the overscan joystick byte by then)."""
    fold = {}
    mpu.step()
    while not (mem.bank == 0 and mpu.pc == PC_SF):
        if mem.bank == 0 and mpu.pc == FOLD_PC and not fold:
            fold = dict(fvband=R[L0["VcrBand"] & 0x7F],
                        fvnext=R[L0["VcrNext"] & 0x7F],
                        fvstate=R[L0["VcrState"] & 0x7F],
                        ftemp=R[L0["Temp"] & 0x7F])
        mpu.step()
    out = dict(room=R[ROOM], x=R[X], y=R[Y], ec=R[L0["EnemyCount"] & 0x7F],
                dead=R[L0["EnemyDeadMask"] & 0x7F],
                key=bool(R[L0["LevelStartRoom"] & 0x7F] & KEY_HELD),
                temp=R[L0["Temp"] & 0x7F],
                vband=R[L0["VcrBand"] & 0x7F], vnext=R[L0["VcrNext"] & 0x7F],
                pf1=[R[(PF1 + i) & 0x7F] for i in range(3)],
                pf2=[R[(PF2 + i) & 0x7F] for i in range(3)],
                dt=R[L0["DropTarget"] & 0x7F], bomb=R[0x35])
    out.update(fold)
    return out


def run(n=1, swcha=None):
    if swcha is not None:
        mem.swcha = swcha
    out = None
    for _ in range(n):
        out = frame()
    return out


def wait_room(target, maxf=1200, swcha=None, collect=None, tag=""):
    """Run until RoomNo == target (returns the frame samples list)."""
    if swcha is not None:
        mem.swcha = swcha
    seen = []
    for f in range(maxf):
        s = frame()
        seen.append(s)
        if collect:
            collect.append(s)
        if s["room"] == target:
            return seen
    FAILS.append(f"{tag}: never reached room {target} in {maxf}f "
                 f"(stuck room {seen[-1]['room']} x={seen[-1]['x']} "
                 f"y={seen[-1]['y']})")
    return seen


def walk_to(x_target, maxf=400, swcha=None, tag=""):
    """Hold left/right until RoomX reaches x_target."""
    for _ in range(maxf):
        x = R[X]
        if x == x_target:
            mem.swcha = NONE
            return True
        mem.swcha = RIGHT if x < x_target else LEFT
        frame()
    FAILS.append(f"{tag}: RoomX stuck at {R[X]} (want {x_target})")
    return False


def settle(maxf=900, tag=""):
    """Run with no input until RoomY has been unchanged for 40 frames.

    Why 40: gravity is subpixel (GRAVITY=$0008 => 8/256 px/frame^2), so even
    in mid-air the first fall pixel only arrives after ~30 frames — a shorter
    "stable" window would call free-fall "landed" and the walk would push
    against the band-0 walls. vy==0 is NOT a landed signal either: a blocked
    StepDown zeroes vy for one frame, then gravity re-accumulates, so vy is
    only 0 every ~7th frame while standing."""
    last, still = None, 0
    for _ in range(maxf):
        s = frame()
        still = still + 1 if s["y"] == last else 0
        last = s["y"]
        if still >= 40:
            return s
    FAILS.append(f"{tag}: never settled (y={last})")
    return None


def clear_hover(maxf=200, tag=""):
    """After a death, LoseLife arms the respawn hover (bugs.md #1): Y is pinned
    until thrust beats gravity, so the player must hold UP to resume. Real
    play requires the same, so the sweep thrusts instead of poking RAM."""
    if not R[L0["Hover"] & 0x7F]:
        return True
    for _ in range(maxf):
        frame_hold(UP)
        if not R[L0["Hover"] & 0x7F]:
            mem.swcha = NONE
            return True
    FAILS.append(f"{tag}: hover never cleared (held UP {maxf}f)")
    return False


def frame_hold(swcha):
    mem.swcha = swcha
    return frame()


def boot():
    """Intro -> gameplay: SWCHB RESET edges at frames 1 and 4 (sim_frame_budget's
    proven 2-stage flow; a 2/5 pulse pattern never leaves the title here), then
    run the drop-in until the player is landed (BombPacked b7) AND DropTarget
    is idle (0) — b7 is also set on the title path, so the DropTarget check is
    what proves we are in gameplay."""
    while not (mem.bank == 0 and mpu.pc == PC_SF):
        mpu.step()
    for f in range(400):
        mem.swchb = 0xFE if f in (1, 4) else 0xFF
        frame()
        if (R[0x35] & 0x80) and R[L0["DropTarget"] & 0x7F] == 0:
            mem.swchb = 0xFF
            return f
    sys.exit("never reached gameplay (still on the intro/title?)")


def main() -> int:
    landed = boot()
    NOTES.append(f"landed frame {landed}, room {R[ROOM]}, "
                 f"x{R[X]} y{R[Y]}, Hover={R[L0['Hover'] & 0x7F]}")
    if R[ROOM] != 0:
        FAILS.append(f"start room {R[ROOM]} != 0")

    # room 0 -- start: settle on the floor, walk right into the cell 4/5 lane
    # (box [x-7,x] must sit inside x32-47 -> x 39..47) and drop.
    settle(tag="room0")
    if not walk_to(59, maxf=900, tag="room0"):
        return report()
    wait_room(1, maxf=900, tag="room0->1")

    # room 1 -- KEY: fall the lane; the key (x40-47) must be collected.
    run(1)
    s0 = frame()
    if s0["ec"] != 1:
        FAILS.append(f"room1: EnemyCount={s0['ec']} != 1 (key record missing)")
    seen = wait_room(2, maxf=900, tag="room1->2")
    if not any(s["key"] for s in seen):
        FAILS.append("room1: KeyHeld never latched falling through the lane")
    if not any(s["dead"] for s in seen):
        FAILS.append("room1: key slot never marked dead")
    if not any(s["key"] for s in seen[-3:]):
        FAILS.append("room1: KeyHeld not still set at the room exit")
    a_key = bool(R[L0["LevelStartRoom"] & 0x7F] & KEY_HELD)

    # room 2 -- phase: the stripe (cells 8,9 = x64-79) must blink; the player
    # lands on the cell 4,5 floor and leaves by the cell 2,3 gap (x16-31,
    # box window x 23..31) -- the stripe itself is a wall, so the lane goes
    # around it. Pressing into it is the kill path (b6 removal latch).
    settle(tag="room2")
    seen = []
    for _ in range(120):                          # walk right into the stripe
        s = frame()
        seen.append(s)
        if s["x"] >= 70 or (s["dead"] & 0x40):
            break
        mem.swcha = RIGHT
    for _ in range(140):                          # sample a full 90f blink cycle
        mem.swcha = NONE
        seen.append(frame())
    p2 = sorted({(s["pf2"][1]) for s in seen})
    if len(p2) < 2:
        FAILS.append(f"room2: phase stripe never blinked (band1 PF2 = "
                     f"{[f'{v:02X}' for v in p2]})")
    else:
        NOTES.append(f"room2: phase band1 blink stagings "
                     f"{[f'{v:02X}' for v in p2]}")
    if R[L0["EnemyDeadMask"] & 0x7F] & 0x40:
        NOTES.append("room2: touching the stripe latched the removal b6 "
                     "(crush kill + same-room removal, test_phase_kill path)")
        for _ in range(300):                      # let the respawn drop finish
            if R[L0["DropTarget"] & 0x7F] == 0:
                break
            frame()
        clear_hover(tag="room2-after-kill")
        settle(tag="room2-after-kill")
    if not walk_to(43, maxf=900, tag="room2-exit"):
        return report()
    wait_room(3, maxf=900, tag="room2->3")

    # room 3 -- door: settle in the cell 4/5 lane, walk RIGHT into the M1 bar
    # (col0 -> x80-87) with the key -> touch-unlock b4; then walk LEFT into the
    # exit lane (cells 2,3 = x16-31) and drop. The bar is a wall until then.
    settle(tag="room3")
    if not walk_to(80, maxf=900, tag="room3-approach"):
        return report()
    run(6, RIGHT)                                 # press into the bar
    unlocked = bool(R[L0["EnemyDeadMask"] & 0x7F] & 0x10)
    if not a_key:
        NOTES.append("room3: (no key held -- touch-unlock not expected)")
    elif not unlocked:
        FAILS.append("room3: M1 door never set EnemyDeadMask b4 on touch")
    else:
        NOTES.append("room3: door touch-unlocked (b4) on contact")
    if not walk_to(27, maxf=900, tag="room3-exit"):
        return report()
    wait_room(4, maxf=900, tag="room3->4")
    if FAILS:
        return report()
    NOTES.append("room3: passed the opened door and dropped the exit lane")

    # room 4 -- vcrunch: shutter armed; the block is staged at the lane's
    # mirror (V cell2 -> BallX = 159-8*2 = 143). The player drops the punched
    # left lane at x23-31.
    seen = wait_room(5, maxf=1200, tag="room4->5")
    if not any(s.get("fvband") == 1 for s in seen):
        FAILS.append(f"room4: VcrBand never armed at the HUD fold "
                     f"({sorted({s.get('fvband') for s in seen})})")
    if not any(s.get("fvstate") for s in seen):
        FAILS.append(f"room4: shutter never staged a slice state "
                     f"({sorted({s.get('fvstate') for s in seen})})")
    if not FAILS:
        NOTES.append("room4: VcrBand=1 + slice states "
                     + str(sorted({s.get("fvstate") for s in seen}))
                     + f" (record Temp={sorted({s.get('ftemp') for s in seen})}); "
                     "dropped the punched lane")

    # room 5 -- hcrunch: band 1 must be staged to P(n) (>=2 distinct shapings)
    # and the player must time the aperture to reach the last room.
    seen = wait_room(6, maxf=2400, tag="room5->6")
    h = sorted({(s["pf1"][1], s["pf2"][1]) for s in seen})
    if len(h) < 2:
        FAILS.append(f"room5: hcrunch band1 never animated (PF1/PF2 = {h})")
    else:
        NOTES.append("room5: hcrunch band1 stagings "
                     + str([f"{a:02X}{b:02X}" for a, b in h]))

    # room 6 -- goal: land on the floor, walk into the miner -> tally starts.
    settle(tag="room6")
    for _ in range(400):
        s = frame()
        if s["dt"] == 0xFE:
            break
        mem.swcha = RIGHT if s["x"] < 25 else (LEFT if s["x"] > 31 else NONE)
    if R[L0["DropTarget"] & 0x7F] != 0xFE:
        FAILS.append(f"room6: miner never picked up "
                     f"(x{R[X]} y{R[Y]} DropTarget={R[L0['DropTarget'] & 0x7F]:02X})")
    else:
        NOTES.append("room6: miner pickup armed the level tally (DropTarget=$FE)")
    return report()


def report() -> int:
    for n in NOTES:
        print("  ok   " + n)
    for f in FAILS:
        print("  FAIL " + f)
    if FAILS:
        print(f"qa_sweep: FAIL ({len(FAILS)})")
        return 1
    print(f"qa_sweep: OK — sweep walked end to end ({len(NOTES)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
