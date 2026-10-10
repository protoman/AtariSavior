#!/usr/bin/env python3
"""bugs.md #10 — bomb on the L1-room2 thin wall must clear BOTH cols.

User (2026-10-10, screenshots/bugs/sync_wall_half_destroyed.png): bomb
on the symmetric thin wall of level 1 room 2 leaves a 1-col sliver
"half of it". Measured from the PNG: rect (12,1,2,1) cols 12-13 punch
clean, but col 14 (mirror 25) renders wall — PF2 row1 bit2, which is
NOT in the ROM data ($03 = bits0,1 only) and cannot be set by an
AND-punch. This probe boots the real game, hand-loads room 1
(room_id 1), forces the bomb fuse 1->2 edge over the wall, and
snapshots EVERY write to PF0/1/2Buf ($C3-$CB) with (pc, bank, old,
new) so the mystery writer names itself.

Contract (exit 1): PF2 row1 must end $00 (both rect cols cleared,
col14 bit clear). The write trace is printed either way.

Run: /home/iuri/python3/bin/python3 tools/test_bomb_half_wall.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [bytearray(open(SRC / f"bank{i}.bin", "rb").read()) for i in range(4)]

# Zero M0/M1 hot counts (player stands in the blast band).
for _name in ("M0RoomRects", "M1RoomRects"):
    for _l in (SRC / "bank2.lst").read_text(errors="replace").splitlines():
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+" + _name + r"\s*$", _l)
        if _m:
            _a = int(_m.group(1), 16) - 0xF000
            BANKS[2][_a + 1 + 2 * BANKS[2][_a]] = 0
            break
    else:
        sys.exit(f"{_name} label missing in bank2.lst")


def lst_labels(path):
    out = {}
    for _l in Path(path).read_text(errors="replace").splitlines():
        _m = re.match(r"^\s+\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", _l)
        if _m:
            out[_m.group(2)] = int(_m.group(1), 16)
    return out


L0 = lst_labels(SRC / "bank0.lst")
L1 = lst_labels(SRC / "bank1.lst")
L2 = lst_labels(SRC / "bank2.lst")
PC_STARTFRAME = L0["StartFrame"]
PC_BMW = L1["BombMarkWalls"]

I_ROOMX, I_ROOMY, I_DIR = 0x00, 0x01, 0x02
I_VYLO, I_VYHI = 0x13, 0x14
I_RCBASE = 0x09
I_RRLO, I_RRHI = 0x10, 0x11
I_PF0LO, I_PF0HI = 0x19, 0x1A
I_ENCOUNT = 0x33
I_BOMBP = 0x35                # $B5 state b0-1 + DownPrev b2 + mask b3-6
I_DEAD = 0x3A
I_DROPT = 0x0A                # $8A DropTarget (0 = normal play)
I_BOMBX = 0x76                # $F6
I_BOMBT = 0x77                # $F7 BombTimer
I_BOMBSND = 0x71              # $F1
RECTS0 = 0x4C
PF_ROWS = range(0xC3, 0xCC)   # PF0/1/2 rows 0-2 (reported addrs)
PF_IDX = [a & 0x7F for a in PF_ROWS]   # bytearray indices

MODEL = {1: ("M1TilePF0", "M1RoomRects")}

# Editor-proof frozen copy of level-1 room-2 (model1) staging data,
# captured 2026-10-10 from bank2.bin (M1TilePF0 9 PF bytes, M1RoomRects
# packed list). src/rooms/*.txt is user-editable WIP — the test stages
# THESE literals into RAM and hard-fails if the ROM drifted, so room
# edits can never silently change what this test proves.
FIXTURE_PF = bytes.fromhex("f0 30 f0 ff 00 ff 3f 03 ff")   # rows: PF0|PF1|PF2
FIXTURE_RR = bytes.fromhex("04 00 49 01 09 31 09 02 51")   # 4 rects


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF
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

frame = 0
writes = []
watch = False
snap = [mem.ram[a] for a in PF_IDX]


def step():
    global watch, frame
    mpu.step()
    if watch:
        for i, a in enumerate(PF_IDX):
            v = mem.ram[a]
            if v != snap[i]:
                snap[i] = v
                writes.append((frame, mpu.pc, mem.bank,
                               PF_ROWS[i], v))
    if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
        frame += 1


def load_room(room):
    """Hand-EnterRoom: pointers + PF buffers + real rect cache (same
    unpack as bank2 EnterRoomB2) — staged from the FROZEN fixture, with
    a ROM-equality gate so a room edit fails loudly here instead of
    drifting the contract."""
    pf0, rr = MODEL[room]
    a_pf0, a_rr = L2[pf0], L2[rr]
    rom_pf = bytes(BANKS[2][a_pf0 - 0xF000 + i] for i in range(9))
    rom_rr = bytes(BANKS[2][a_rr - 0xF000 + i] for i in range(9))
    if rom_pf != FIXTURE_PF or rom_rr != FIXTURE_RR:
        sys.exit("fixture drift: room model changed since 2026-10-10 — "
                 "re-freeze FIXTURE_PF/FIXTURE_RR in this test")
    mem.ram[I_PF0LO] = a_pf0 & 0xFF
    mem.ram[I_PF0HI] = a_pf0 >> 8
    mem.ram[I_RRLO] = a_rr & 0xFF
    mem.ram[I_RRHI] = a_rr >> 8
    for i in range(3):
        for row in range(3):
            mem.ram[(0xC3 + i * 3 + row) & 0x7F] = FIXTURE_PF[i * 3 + row]
    count = FIXTURE_RR[0]
    mem.ram[I_RCBASE] = min(count, 5)
    for i in range(min(count, 5)):
        p0 = FIXTURE_RR[1 + 2 * i]
        p1 = FIXTURE_RR[2 + 2 * i]
        mem.ram[RECTS0 + 4 * i + 0] = p0 >> 2
        mem.ram[RECTS0 + 4 * i + 1] = p0 & 3
        mem.ram[RECTS0 + 4 * i + 2] = p1 >> 2
        mem.ram[RECTS0 + 4 * i + 3] = p1 & 3


def pin(y=70):
    mem.ram[I_VYLO] = 0
    mem.ram[I_VYHI] = 0
    mem.ram[I_ROOMY] = y
    mem.ram[I_ENCOUNT] = 0
    mem.ram[I_DROPT] = 0
    mem.swcha = 0xFF
    mem.inpt4 = 0x80


def run_case(tag, bombx, roomx, y=70):
    """Reload room 1 fresh, drop a bomb on bombx, watch PF writes.
    Returns (bmw_seen_frame_or_None, writes_since_call, initial_rows)."""
    load_room(1)
    initial = {a: mem.ram[a & 0x7F] for a in PF_ROWS}
    mem.ram[I_BOMBX] = bombx
    mem.ram[I_ROOMX] = roomx
    mem.ram[I_ROOMY] = y
    mem.ram[I_BOMBSND] = 0
    mem.ram[I_BOMBP] = 0x01        # state 1 (fuse), WallMask clear
    mem.ram[I_BOMBT] = 2           # two ticks to the 1->2 edge (BMW)
    global watch, snap
    watch = True
    snap = [mem.ram[a] for a in PF_IDX]
    start = len(writes)
    bmw_seen = None
    limit = start_frame + 8          # timer=2 -> edge within ~2 frames
    while bmw_seen is None and frame < limit:
        pin(y)
        step()
        if mem.bank == 1 and mpu.pc == PC_BMW:
            bmw_seen = frame
    if bmw_seen is None:
        watch = False
        return None, writes[start:], initial
    end = bmw_seen + 3               # a few state2 frames past the punch
    while frame < end:
        pin(y)
        step()
    watch = False
    return bmw_seen, writes[start:], initial


def report(tag, bmw_seen, wts, initial):
    print(f"[{tag}] BMW seen: "
          f"{'f'+str(bmw_seen) if bmw_seen else 'NOT REACHED'}")
    print(f"[{tag}] PF writes ({len(wts)}):")
    for f, pc, bank, addr, val in wts:
        print(f"  f{f} ${pc:04X} bank{bank} ${addr:02X} -> ${val:02X}")
    # contract: punch clears rect (12,1,2,1) = PF2 row1 cols12-13 (bits0,1);
    # every other row/byte keeps its ROM value.
    want = dict(initial)
    want[0xCA] = initial[0xCA] & 0xFC
    bad = []
    for a in sorted(PF_ROWS):
        v = mem.ram[a & 0x7F]
        mark = "" if v == want[a] else f"  != ${want[a]:02X}  <<"
        if v != want[a]:
            bad.append((a, v, want[a]))
        print(f"  ${a:02X} = ${v:02X}{mark}")
    return bad


def main():
    global watch, start_frame
    # ---- boot to landed (RESET f2/f5, title drop-in) ----
    guard = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        guard += 1
        if guard > 400000:
            sys.exit(f"never reached StartFrame (pc=${mpu.pc:04X})")
    landed = None
    while frame < 400:
        step()
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            mem.swchb = 0xFE if frame in (2, 5) else 0xFF
            if mem.ram[I_BOMBP] & 0x80:
                landed = frame
                break
    if landed is None:
        sys.exit("player never landed (BombPacked OnGround)")
    mem.ram[I_DEAD] = 0xFF
    print(f"landed f{landed}")

    # Room 1 (level 1 room 2): thin wall rect (12,1,2,1) = display cols
    # 12-13 direct, 26-27 mirrored. Bomb visible-left = (BombX-7)>>2 (>=15).
    # Case A: left wall — BombX=56 -> visible col 12 (user: removes fully).
    # Case B: right wall — BombX=115 -> visible col 27 -> fold to 12
    #         (user: removes only HALF). Player col must dodge
    #         BombPlayerBlast (|RoomX/4 - BombX/4| < 2 kills -> ReloadLevel
    #         would refill the hole).
    # Case C: right-wall STAND drop — BombX=104 -> col 24 -> fold 15,
    #         blast window [13,17]; rect span is [12,13]. A rect.x-only
    #         window match misses (span overlap SHOULD hit at col 13) =
    #         2026-10-10 "right wall: nothing happens" (sweep: fold 15
    #         = bombx 104-107 = natural flush drop beside the mirror
    #         instance, cols 26-27).
    # Case D: same fold 15 on the left side (BombX=68) — proves the bug
    #         is the window edge, not the mirror.
    results = []
    for tag, bombx, roomx in (("A left", 56, 64), ("B right", 115, 96),
                              ("C stand-right", 104, 116),
                              ("D stand-left", 68, 96)):
        start_frame = frame
        bmw_seen, wts, initial = run_case(tag, bombx, roomx)
        results.append((tag, bmw_seen, report(tag, bmw_seen, wts, initial)))
        print()

    fail = False
    for tag, seen, bad in results:
        if seen is None:
            print(f"FAIL [{tag}]: BombMarkWalls never ran")
            fail = True
        elif bad:
            rows = ", ".join(f"${a:02X}=${v:02X}(want ${w:02X})"
                             for a, v, w in bad)
            print(f"FAIL [{tag}]: sliver left behind: {rows}")
            fail = True
    if fail:
        sys.exit("FAIL: bomb half-wall repro (bugs.md #10)")
    print("test_bomb_half_wall: OK (both walls fully cleared)")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
