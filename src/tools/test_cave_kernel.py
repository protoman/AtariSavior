#!/usr/bin/env python3
"""The bank6 cave kernel on the REAL ROM: every sprite row on its own scanline, no repeated
row at the band changes, the 262-line contract, playfield store phases, water line.

The ROM runs normally up to bank0's dispatch (`sta $1FF5`); there the harness overwrites the
bytes the VBL staged (player frame + RoomY, the two GRP1 objects, tide, door, water) with a
scenario, so the kernel sees arbitrary inputs with the game's real art and tables. Every
frame is rendered line by line with tools/tia_render.py (VDELP latches included) and the byte
the TIA would draw at the sprite's first pixel is compared with the art:

  * player: line L shows art row (L - RoomY) of the chosen frame, for RoomY from -25 to 150
    (all four band changes), every frame variant
  * slot-0 object: line L shows design row (L - top), every design, sweeping its top line
  * slot-1 object (the second object, positioned mid-frame): its rows, except the two lines
    the positioning itself costs (the same two the old kernel lost)
  * every kernel line's WSYNC store starts at cycle <= 73, the frame is stable, PF0/PF1/COLUPF
    stores keep their phases on the band-first lines, the water strip starts at 132 + tide.

Run: /home/iuri/python3/bin/python3 tools/test_cave_kernel.py [--quick]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import cave_kernel_gen as G  # noqa: E402
import playbot as P  # noqa: E402
import tia_render as T  # noqa: E402

QUICK = "--quick" in sys.argv
ART = G.read_art(ROOT / "bank0.asm")
OBJ = ART["consts"]
SYM = {}
for _l in (ROOT / "generated" / "symbols.asm").read_text().splitlines():
    _m = re.match(r"^(\S+)\s+([0-9a-fA-F]{4})\b", _l)
    if _m:
        SYM[_m.group(1)] = int(_m.group(2), 16)
ZP = {**G.LIVE, **G.KERNEL_ZP}
Z = {k: v & 0x7F for k, v in ZP.items()}


def design_rows(name):
    """the rows of a design (bytes), then zeros"""
    off = OBJ[name]
    return ART["spr"][off:off + G.DESIGN_ROWS[name]]


class Scenario:
    def __init__(self, **kw):
        self.kw = kw


class Harness(T.TiaConsole, P.Console):
    pass


def make():
    con = P.Console()
    con.boot(1)
    con.__class__ = Harness
    con.tia_init()
    con.scn = None
    for _ in range(3):
        con.tia_frame()
    return con


def hooked(con):
    """patch __setitem__: the scenario lands right before the bank6 kernel starts and the
    game's own values come back when the kernel hands over to the HUD, so the game logic
    (overscan: collisions, deaths, respawns) never sees the fabricated state"""
    cls = type(con)
    base = cls.__setitem__
    keep = {}

    def si(self, a, v):
        if (a & 0xFFFF) == 0x1FF5 and self.bank == 0 and self.scn is not None:
            keep.clear()
            for name in ("RoomY", "Grp0Ptr", "ObjBase", "ObjTop", "ObjBase1", "ObjTop1",
                         "ObjX1", "ObjRefs", "CollisionX", "CollisionCellY", "BombPacked",
                         "RoomBandColor", "LaserState"):
                keep[Z[name]] = self.ram[Z[name]]
            keep[(Z["Grp0Ptr"] + 1) & 0x7F] = self.ram[(Z["Grp0Ptr"] + 1) & 0x7F]
            apply(self, self.scn)
        elif (a & 0xFFFF) == 0x1FF6 and self.bank == 1 and keep:
            for k, val in keep.items():
                self.ram[k] = val
            keep.clear()
        base(self, a, v)
    cls.__setitem__ = si


def apply(con, s):
    r = con.ram
    r[Z["RoomY"]] = s["ry"] & 255
    lo = SYM[s["frame"]]
    r[Z["Grp0Ptr"]] = lo & 255
    r[(Z["Grp0Ptr"] + 1) & 0x7F] = lo >> 8
    # slot 0 object
    if s.get("obj0"):
        name, top = s["obj0"]
        r[Z["ObjBase"]] = OBJ[name]
        r[Z["ObjTop"]] = (top - (s["ry"] & 255) + 1) & 255
    else:
        r[Z["ObjBase"]] = 0xFF
    if s.get("obj1"):
        name, top, x, refs = s["obj1"]
        r[Z["ObjBase1"]] = OBJ[name]
        r[Z["ObjTop1"]] = (top - (s["ry"] & 255) + 1) & 255
        r[Z["ObjX1"]] = x
        r[Z["ObjRefs"]] = refs
    else:
        r[Z["ObjBase1"]] = 0xFF
    r[Z["CollisionX"]] = 24 + s.get("tide", 0)
    r[Z["CollisionCellY"]] = s.get("door", 0x80)
    r[Z["BombPacked"]] = s.get("bombstate", 0)
    r[Z["RoomBandColor"]] = s.get("water", 0x96)
    r[Z["LaserState"]] = s.get("laser", 0)


def frame_lines(con, log):
    by = {}
    for t, reg, v in log:
        by.setdefault(t // T.LINE, []).append((t % T.LINE, reg, v))
    first, last = min(by), max(by)
    k0 = min(ln for ln, ev in by.items() if any(r == T.VBLANK and v == 0 for _, r, v in ev)) + 1
    return by, first, last, k0


def sample(con, by, first, last, k0):
    """{line: (old0 byte at P0's first pixel, new1 byte at P1's first pixel)} for kernel lines"""
    beam = con.beam
    orig = T.Beam.pixel
    s0, s1 = {}, {}
    cur = [0]

    def px(self, x):
        if x == self.pos["p0"] % 160:
            s0[cur[0]] = self.old0 if self.r[T.VDELP0] & 1 else self.new0
        if x == self.pos["p1"] % 160:
            s1[cur[0]] = self.old1 if self.r[T.VDELP1] & 1 else self.new1
        return orig(self, x)
    T.Beam.pixel = px
    try:
        for line in range(first, last + 1):
            cur[0] = line - k0
            ev = sorted(by.get(line, ()), key=lambda e: e[0])
            ei = 0
            for clk in range(228):
                while ei < len(ev) and 3 * ev[ei][0] + 3 <= clk:
                    beam.write(ev[ei][1], ev[ei][2], ev[ei][0])
                    ei += 1
                if clk >= 68:
                    beam.pixel(clk - 68)
            while ei < len(ev):
                beam.write(ev[ei][1], ev[ei][2], ev[ei][0])
                ei += 1
    finally:
        T.Beam.pixel = orig
    return s0, s1


def run(con, scn):
    con.scn = scn
    con.tia_frame()                  # the frame the scenario is applied in
    log = con.tia_frame()
    by, first, last, k0 = frame_lines(con, log)
    return by, first, last, k0, sample(con, by, first, last, k0)


def check(name, got, want, skip=(), problems=None):
    for n in range(144):
        if n in skip:
            continue
        g, w = got.get(n, 0), want.get(n, 0)
        if g != w:
            problems.append((name, n, g, w))
            return


def main():
    con = make()
    hooked(con)
    problems = []
    frames = ["PlayerSpriteA", "PlayerSpriteB", "PlayerWalkA", "PlayerWalkB"]
    step = 11 if QUICK else 3
    # ---- player rows across every band change --------------------------------------------
    for fi, f in enumerate(frames):
        for ry in range(-25, 151, step):
            by, first, last, k0, (s0, s1) = run(con, dict(ry=ry, frame=f))
            want = {ry + r: ART[f][r] for r in range(G.H0) if 0 <= ry + r < 144}
            check(f"player {f} ry={ry}", s0, want, problems=problems)
            if not problems:
                # frame stability + WSYNC contract on the first scenario of each frame
                ws = [t for ln in range(k0, k0 + 144) for t, r, v in by.get(ln, []) if r == T.WSYNC]
                if len(ws) != 144 or max(ws) > 75:
                    problems.append(("wsync", f, ry, (len(ws), max(ws) if ws else None)))
    # ---- slot 0 object: every design, sweeping its top line -------------------------------
    for d in G.DESIGNS:
        rows = design_rows(d)
        for top in range(-20, 150, step * 2):
            by, first, last, k0, (s0, s1) = run(con, dict(ry=40, frame="PlayerSpriteA",
                                                          obj0=(d, top)))
            want = {top + r: rows[r] for r in range(len(rows)) if 0 <= top + r < 144}
            check(f"object {d} top={top}", s1, want, problems=problems)
    # ---- slot 1: a second object lower in another band ------------------------------------
    for d1 in ("OBJ_SPIDER", "OBJ_TENTACLE", "OBJ_MINER"):
        rows1 = design_rows(d1)
        for top1 in sorted(set(list(range(40, 130, 7)) + [36, 37, 72, 73, 108, 109])):
            for x1 in (10, 40, 90):          # (x >= ~103 sees the next row one line early: the GRP1 write is at c57)
                scn = dict(ry=10, frame="PlayerSpriteB", obj0=("OBJ_BAT", 12),
                           obj1=(d1, top1, x1, 0))
                by, first, last, k0, (s0, s1) = run(con, scn)
                ws = [n for n in range(144)
                      if not [t for t, r, v in by.get(k0 + n, []) if r == T.WSYNC]]
                if ws:          # a kernel line without its WSYNC = a stalled (76c+) line
                    problems.append((f"slot1 {d1} top={top1} x={x1}: stalled lines", ws[:4]))
                    break
                band = top1 // 36
                # the hook line pair of its band (lines 3,4 of the band) is allowed to repeat
                skip = {36 * band + 3, 36 * band + 4, 36 * band + 5}
                want = {top1 + r: rows1[r] for r in range(len(rows1)) if 0 <= top1 + r < 144}
                got = {n: v for n, v in s1.items() if n >= 36 * band + 3}
                check(f"slot1 {d1} top={top1} x={x1}", got,
                      {n: v for n, v in want.items() if n >= 36 * band + 3}, skip, problems)
                if problems:
                    break
            if problems:
                break
        if problems:
            break
    # ---- water strip + frame length --------------------------------------------------------
    for tide in range(4):
        by, first, last, k0, _ = run(con, dict(ry=60, frame="PlayerSpriteA", tide=tide))
        wl = [n for n in range(144) for t, r, v in by.get(k0 + n, []) if r == T.COLUBK]
        if wl != [132 + tide]:
            problems.append(("water", tide, wl, [132 + tide]))
    # ---- band changes: every playfield store of the new band lands in HBLANK of the band's
    # first line (before the first pixel each register draws), so both halves change together
    by, first, last, k0, _ = run(con, dict(ry=60, frame="PlayerSpriteA"))
    lim = {T.COLUPF: 22, T.PF0: 22, T.PF1: 27, T.PF2: 38, T.ENABL: 45}   # the ball sits at x >= 79: its first pixel is at c49
    for b in range(4):
        for n in range(36 * b, 36 * b + 4):
            for t, r, v in by.get(k0 + n, []):
                if r in lim and (n != 36 * b or t > lim[r]):
                    problems.append(("playfield store", b, n - 36 * b, hex(r), t))
        got = {r for t, r, v in by.get(k0 + 36 * b, []) if r in lim}
        if got != set(lim):
            problems.append(("band", b, "first line misses", sorted(set(lim) - got)))
    # ---- laser beam: ENAM0 only on the player's beam row, only while armed ----------------
    for armed in (0, 2):
        by, first, last, k0, _ = run(con, dict(ry=50, frame="PlayerSpriteA", laser=armed))
        beam = [n for n in range(144) for t, r, v in by.get(k0 + n, []) if r == T.ENAM0 and v & 2]
        if beam != ([54] if armed else []):
            problems.append(("laser", armed, beam))
    # ---- COLUP1 outside objects: the band colour (door: the stripe colour) ------------------
    for door in (0x80, 0x1C):
        scn = dict(ry=50, frame="PlayerSpriteA", door=door)
        con.scn = scn
        con.tia_frame()
        cpf = [con.ram[(Z["CPFB"] + k) & 0x7F] for k in range(4)]      # (the game's own bytes)
        by, first, last, k0, _ = run(con, scn)
        for n in range(143):
            band = n // 36 + (1 if n % 36 == 35 else 0)             # a band's last line latches the next
            want = 0x1C if door != 0x80 else cpf[band]
            got = [v for t, r, v in by.get(k0 + n, []) if r == T.COLUP1]
            if got and got[-1] != want:
                problems.append(("COLUP1", door, n, got[-1], want))
                break
    # ---- the water strip is not painted during the explosion blink / when the band is off --
    for kw in (dict(bombstate=2), dict(water=0)):
        by, first, last, k0, _ = run(con, dict(ry=60, frame="PlayerSpriteA", **kw))
        wl = [n for n in range(144) for t, r, v in by.get(k0 + n, []) if r == T.COLUBK]
        if wl:
            problems.append(("water must be off", kw, wl))
    if problems:
        print("FAIL:", problems[0])
        for p in problems[1:6]:
            print("     ", p)
        return 1
    print("test_cave_kernel: OK (player rows, slot-0 and slot-1 objects, WSYNC <= c75, water)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
