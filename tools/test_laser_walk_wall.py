#!/usr/bin/env python3
"""Walk-then-fire laser wall repro (py65) — user report 2026-10-10.

Report: player walks against a 1-tile-width block until collision
stops him, THEN fires. Facing RIGHT the laser passes through the
wall; facing LEFT it works. Every earlier laser test PINNED RoomX —
that is why none of them reproduced it. This one drives real input:

  1. boot to landed (RESET f2/f5), fire RELEASED,
  2. hand-load room (pointer + PF buffers + REAL rect cache, same
     unpack as bank2 EnterRoomB2: count->RcBase, 2B packed -> 4B
     slots at $CC), so PlayerHitsMap collides for real,
  3. place the player 8px short of an INTERIOR wall (borders
     excluded), hold SWCHA until RoomX stops (collision),
  4. press INPT4, run frames, capture (LaserX, CollisionX,
     LaserState, RoomX, PlayerDir) at LaserInput's rts.

Contract failures (= repro) while fire held:
  * LaserX strictly beyond the wall run (beam committed/past), or
  * candidate tip strictly beyond the wall run, or
  * tip inside the wall run but LaserX != eye (hit, not consumed),
  * beam disarmed (LaserState b1 clear).

Setup issues (no wall found, walk blocked, etc.) are WARNINGS —
they do not fail the test. Exit 1 only on contract violations or
when no fire case could run at all.

Run: /home/iuri/python3/bin/python3 tools/test_laser_walk_wall.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"   # test-owned banks+labels
BANKS = [bytearray(open(FROZEN / f"bank{i}.bin", "rb").read()) for i in range(4)]


def lst_labels(path):
    out = {}
    for _l in Path(path).read_text(errors="replace").splitlines():
        _m = re.match(r"^\s+\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", _l)
        if _m:
            out[_m.group(2)] = int(_m.group(1), 16)
    return out


L0 = lst_labels(FROZEN / "bank0.lst")
L2 = lst_labels(FROZEN / "bank2.lst")
PC_STARTFRAME = L0["StartFrame"]

import test_fixtures as FX  # noqa: E402
FX.freeze_m0(BANKS, L2)     # frozen model0: interior wall + hot count 0

# ZP indices (addr & 0x7F) — from bank0.lst decl lines
I_ROOMX, I_ROOMY, I_DIR, I_LASERX = 0x00, 0x01, 0x02, 0x03   # $80..$83
I_COLLX = 0x0B                      # $8B CollisionX (LHT candidate)
I_RCBASE = 0x09                     # $89 rect cache count
I_RRLO, I_RRHI = 0x10, 0x11         # $90/$91 RoomRects ptr
I_VYLO, I_VYHI = 0x13, 0x14         # $93/$94
I_PF0LO, I_PF0HI = 0x19, 0x1A       # $99/$9A RoomPF0 ptr
I_ENCOUNT = 0x33                    # $B3
I_BOMBP = 0x35                      # $B5
I_DEAD = 0x3A                       # $BA EnemyDeadMask
I_LSTATE = 0x40                     # $C0 LaserState
DT_SLOT = 0x0A                      # $8A DropTarget (death/feature gate)
RECTS0 = 0x4C                       # $CC rect cache slots (RcW1)

OV_HEAD = L2["OvHead"]
MODEL = {  # fixture models only (rule 2026-10-14). M0 = this test's
    # probe; M2 kept for test_vcr_shutter, which imports this harness and
    # freeze_m2's its own private copy before load_room(2); M4 kept for
    # test_hcrunch (freeze_m4's its own copy before load_room(4)).
    0: ("L1R1TilePF0", "L1R1RoomRects"),
    2: ("M2TilePF0", "M2RoomRects"),
    4: ("L3R2TilePF0", "L3R2RoomRects"),
}

RANGE_LO = L0["LaserInput"]
RANGE_HI = L0.get("TallyTramp", 0xFFF0)
rts_pcs = set()
for _l in (FROZEN / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s+\d+\s+([0-9a-f]{4})\s+(?:[0-9a-f]{2}[ \t]+)+rts\b", _l)
    if _m:
        a = int(_m.group(1), 16)
        if RANGE_LO <= a < RANGE_HI:
            rts_pcs.add(a)
assert rts_pcs, "no LaserInput rts found in bank0.lst"


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x80               # fire RELEASED from power-on

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


def step():
    mpu.step()


def band_row_of(y):
    idx = y >> 2
    return 0 if idx < 12 else (1 if idx < 24 else 2)


def cell_solid(tip_px, band_row):
    if tip_px < 0 or tip_px > 159:
        return False
    d = tip_px >> 2
    src = d if d < 20 else 39 - d
    if src < 4:
        addr, mask = 0xC3 + band_row, 0x10 << src
    elif src < 12:
        addr, mask = 0xC6 + band_row, 0x80 >> (src - 4)
    else:
        addr, mask = 0xC9 + band_row, 0x01 << (src - 12)
    return bool(mem.ram[addr & 0x7F] & mask)


def eye_of(roomx, facing):
    return min(roomx + 4, 159) if facing == 0 else roomx - 4


def load_room(room):
    """Hand-EnterRoom: pointers + PF buffers + REAL rect cache, same
    unpack as bank2 EnterRoomB2 (packed 2B [x<<2|y, w<<2|h] -> 4B at
    $CC, count -> RcBase clamped to 5). VBL StageBandTab rebuilds the
    overlay pack from the new MetaA by itself."""
    pf0, rr = MODEL[room]
    a_pf0, a_rr = L2[pf0], L2[rr]
    # RoomMetaA/B are staged at room entry (bank2 EnterRoomB2 reads the
    # block's +9/+10 and overwrites the pointer pair) — stage them directly.
    mem.ram[I_PF0LO] = BANKS[2][(a_pf0 + 9 - 0xF000) & 0xFFFF]
    mem.ram[I_PF0HI] = BANKS[2][(a_pf0 + 10 - 0xF000) & 0xFFFF]
    mem.ram[I_RRLO] = a_rr & 0xFF
    mem.ram[I_RRHI] = a_rr >> 8
    # ROM: TilePF0/1/2 = 3 band-row bytes each, in order after the label
    for i, dst in enumerate((0xC3, 0xC6, 0xC9)):
        for row in range(3):
            mem.ram[(dst + row) & 0x7F] = BANKS[2][
                ((a_pf0 + i * 3 + row) - 0xF000) & 0xFFFF]
    # rect cache (EnterRoomB2 .EBrcW): count + unpack 4B/rect slots
    off = (a_rr - 0xF000) & 0xFFFF
    count = BANKS[2][off]
    mem.ram[I_RCBASE] = min(count, 5)
    for i in range(min(count, 5)):
        p0 = BANKS[2][off + 1 + 2 * i]
        p1 = BANKS[2][off + 2 + 2 * i]
        mem.ram[RECTS0 + 4 * i + 0] = p0 >> 2      # x
        mem.ram[RECTS0 + 4 * i + 1] = p0 & 3       # y
        mem.ram[RECTS0 + 4 * i + 2] = p1 >> 2      # w
        mem.ram[RECTS0 + 4 * i + 3] = p1 & 3       # h


def meta_a(room):
    a_pf0 = L2[MODEL[room][0]]
    return BANKS[2][a_pf0 + 9 - 0xF000]


def step_frame(y_pin, capture=True):
    """Run one frame with per-frame pins; return rts capture or None."""
    mem.ram[I_VYLO] = 0
    mem.ram[I_VYHI] = 0
    mem.ram[I_ROOMY] = y_pin
    mem.ram[I_ENCOUNT] = 0
    cap = None
    while True:
        mpu.step()
        if capture and mpu.pc in rts_pcs:
            cap = (mem.ram[I_LASERX], mem.ram[I_COLLX], mem.ram[I_LSTATE],
                   mem.ram[I_ROOMX], mem.ram[I_DIR])
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            break
    return cap


def solid_cols(rows):
    return {d for d in range(40)
            if any(cell_solid(d * 4 + 2, r) for r in rows)}


def find_wall(rows, approach):
    """INTERIOR wall run (borders lo<=3 / hi>=36 excluded).
    approach +1: walk RIGHT into the run's left face; need cols
    lo-1,lo-2 clear (8px start box). approach -1: walk LEFT into the
    right face; need cols hi+1..hi+3 clear. Returns (wl_px, wr_px) or
    None. Prefers narrow runs (1-tile blocks) by scanning runs in
    ascending width order."""
    solid = solid_cols(rows)
    runs = []
    d = 0
    while d < 40:
        if d in solid:
            lo = d
            while d + 1 in solid:
                d += 1
            runs.append((lo, d))
        d += 1
    runs.sort(key=lambda r: (r[1] - r[0], r[0]))      # narrowest first
    for lo, hi in runs:
        if lo <= 3 or hi >= 36:
            continue                                  # screen border
        if approach > 0:
            if (lo - 1) not in solid and (lo - 2) not in solid:
                return lo * 4, hi * 4 + 3
        else:
            if all((hi + k) not in solid for k in (1, 2, 3)):
                return lo * 4, hi * 4 + 3
    return None


def vcrunch_bbox_overlaps(room, rows, wl, wr):
    """True if a hot $81 (vcrunch bbox) record covers the wall run.
    Hot records: after packed count + hot count, 5B each
    [class, x, y, w, h] — x = 4px display col (left half), y = band."""
    _, rr = MODEL[room]
    off = (L2[rr] - 0xF000) & 0xFFFF
    count = BANKS[2][off]
    hot = BANKS[2][off + 1 + 2 * count]
    base = off + 2 + 2 * count
    for i in range(hot):
        cls, x, y, w, h = BANKS[2][base + 5 * i:base + 5 * i + 5]
        if cls != 0x81:
            continue
        if not any(y <= r < y + h for r in rows):
            continue
        bx0, bx1 = x * 4, x * 4 + w * 4 - 1
        if wl <= bx1 and bx0 <= wr:
            return True
    return False


def run_case(room, y_pin, approach, warns, fails, stats):
    rows = (band_row_of(y_pin + 2), band_row_of(y_pin + 3))
    wall = find_wall(rows, approach)
    side = "RIGHT" if approach > 0 else "LEFT"
    tag = f"r{room} y{y_pin} {side}"
    if wall is None:
        warns.append(f"{tag}: no interior wall with clear approach")
        return
    wl, wr = wall
    if vcrunch_bbox_overlaps(room, rows, wl, wr):
        # Shutter cell: VcrShutter punches the bbox OPEN in the PF buffers
        # every VBL (the ball block needs the hole — CTRLPF priority would
        # hide it), and the cell walk IS the PF buffers, so the left half of
        # the bbox is walkable by design (2026-10-13 "no invisible left
        # kill" ruling: kill/block follows the drawn right-half ball only).
        # The wall here is the shutter itself — plain-wall probe geometry
        # not applicable (same skip class as a DropTarget feature tile).
        warns.append(f"{tag}: wall {wl}..{wr} = vcrunch bbox — skipped "
                     f"(punched cell, shutter semantics)")
        return
    if approach > 0:
        start = max(4, wl - 8)
        mem.swcha = 0x7F                    # P0 right pressed (active low D7)
        want_dir = 0
    else:
        start = min(152, wr + 8)
        mem.swcha = 0xBF                    # P0 left pressed (active low D6)
        want_dir = 1
    mem.ram[I_ROOMX] = start
    mem.ram[I_ROOMY] = y_pin
    mem.ram[I_LSTATE] = 0                # clean laser state per case (was
                                         # accumulating b7/held bits across
                                         # the wider model sweep)
    mem.inpt4 = 0x80                        # fire released while walking

    # --- walk until collision stops him -----------------------------------
    prev, streak, final_dir = start, 0, None
    for _ in range(200):
        cap = step_frame(y_pin)
        if cap is None:
            # DropTarget armed (death tile: feature record $80/$81/$82 in
            # the hot stream until Phase 3/4 runtime exists) or LaserInput
            # skipped — geometry not probeable, skip the case.
            warns.append(f"{tag}: DropTarget=${mem.ram[DT_SLOT]:02X} during "
                         f"walk — death/feature tile in geometry")
            return
        rx = cap[3]
        streak = streak + 1 if rx == prev else 0
        prev, final_dir = rx, cap[4]
        if streak >= 8:
            break
    else:
        warns.append(f"{tag}: player never stopped walking (RoomX={prev})")
        return
    final = prev
    if final == start:
        warns.append(f"{tag}: player never moved (RoomX={start}) — walk "
                     f"input ignored")
        return
    if final_dir != want_dir:
        warns.append(f"{tag}: PlayerDir={final_dir} after walking {side} "
                     f"(want {want_dir})")
        return
    if approach > 0:
        gap = wl - (final + 8)
    else:
        gap = final - (wr + 1)
    if gap > 10:
        warns.append(f"{tag}: stopped {gap}px short of wall {wl}..{wr} "
                     f"(RoomX={final}) — not wall collision")
        return

    # --- release, then press fire -----------------------------------------
    mem.inpt4 = 0x80
    for _ in range(8):
        step_frame(y_pin, capture=False)
    mem.inpt4 = 0x00                        # fire pressed (held)
    # travel = +-(4px/frame) capped at RoomX+-20; wall is <=20px away
    # by placement (start 8px short, walk <=8px), keep a generous window
    nframes = max(24, abs((wr if approach > 0 else wl) -
                          (final + 4 if approach > 0 else final - 4)) // 4 + 16)

    contacts = 0
    trace = []
    for f in range(nframes):
        cap = step_frame(y_pin)
        if cap is None:
            fails.append(f"{tag} f{f}: DropTarget=${mem.ram[DT_SLOT]:02X} "
                         f"during fire — LaserInput gated")
            break
        lx, cx, st, rx, _d = cap
        eye = eye_of(rx, 0 if approach > 0 else 1)
        tip = cx if approach > 0 else cx - 7
        trace.append(lx)
        stats["frames"] += 1
        if not (st & 0x02):
            fails.append(f"{tag} f{f}: beam DISARMED while held "
                         f"(LaserState=${st:02X})")
        if approach > 0:
            if lx > wr:
                fails.append(f"{tag} f{f}: PASS-THROUGH: LaserX={lx} beyond "
                             f"wall {wl}..{wr} (RoomX={rx})")
            if tip > wr:
                fails.append(f"{tag} f{f}: candidate tip {tip} tested PAST "
                             f"wall {wl}..{wr}")
            if wl <= tip <= wr:
                contacts += 1
                if lx != eye:
                    fails.append(f"{tag} f{f}: tip {tip} inside wall "
                                 f"{wl}..{wr} but LaserX={lx} != eye {eye} "
                                 f"(not consumed)")
        else:
            if lx < wl:
                fails.append(f"{tag} f{f}: PASS-THROUGH: LaserX={lx} left of "
                             f"wall {wl}..{wr} (RoomX={rx})")
            if tip < wl:
                fails.append(f"{tag} f{f}: candidate tip {tip} tested PAST "
                             f"wall {wl}..{wr}")
            if wl <= tip <= wr:
                contacts += 1
                if lx != eye:
                    fails.append(f"{tag} f{f}: tip {tip} inside wall "
                                 f"{wl}..{wr} but LaserX={lx} != eye {eye} "
                                 f"(not consumed)")
    if contacts == 0:
        fails.append(f"{tag}: no wall contact in {nframes} fire frames "
                     f"(wall {wl}..{wr}, walked to RoomX={final})")
    else:
        stats["cases"] += 1
    print(f"  {tag}: wall {wl}..{wr} start={start} walked-> {final} "
          f"contacts={contacts}/{nframes} LX=" +
          ",".join(str(lx) for lx in trace[:24]))


def main() -> None:
    guard = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        guard += 1
        if guard > 400000:
            sys.exit(f"never reached StartFrame (pc=${mpu.pc:04X})")

    frame = 0
    landed = None
    while frame < 400:
        step()
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            frame += 1
            mem.swchb = 0xFE if frame in (2, 5) else 0xFF
            if mem.ram[I_BOMBP] & 0x80:
                landed = frame
                break
    if landed is None:
        sys.exit("player never landed")
    spawn_y = mem.ram[I_ROOMY]

    warns, fails = [], []
    stats = {"frames": 0, "cases": 0}
    # Frozen fixture only (rule 2026-10-14): the probe geometry is the
    # M0 fixture's interior wall (cols 14-15, band 1). Live models are
    # never scanned — content edits emptied them of qualifying walls
    # (2026-10-16 "no fire case ran"). MODEL also maps M2 for the
    # test_vcr_shutter import; only room 0 is probed here.
    for room in (0,):
        load_room(room)
        for _ in range(2):                 # VBL rebuilds overlay pack
            while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
                step()
        mem.ram[I_DEAD] = 0xEF             # enemies dead, b4 strip ALIVE
        # Band-1 pins only: the fixture wall lives on the middle band.
        for y in (56, 72, 88):
            for approach in (+1, -1):
                run_case(room, y, approach, warns, fails, stats)

    for w in warns:
        print("WARN " + w)
    if fails:
        print(f"\nFAIL: {len(fails)} — laser walk repro "
              f"(right = bug, left = control):")
        for f in fails[:24]:
            print("  " + f)
        if len(fails) > 24:
            print(f"  ... and {len(fails) - 24} more")
        sys.exit(1)
    if stats["cases"] == 0:
        print("FAIL: no fire case ran — probe geometry broken")
        sys.exit(1)
    print(f"test_laser_walk_wall: OK ({stats['cases']} cases, "
          f"{stats['frames']} fire frames — issue NOT reproduced)")


if __name__ == "__main__":
    main()
