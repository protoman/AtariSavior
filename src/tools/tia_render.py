#!/usr/bin/env python3
"""A small TIA + RIOT-timer model that turns the real ROM's frames into PNG pictures.

Stella cannot be driven from a script, so screenshots of the game come from the
simulation (py65) instead: the ROM runs exactly as on the console, with

  * virtual time: CPU cycles plus the stalls of `sta WSYNC` (the CPU halts until the
    next 76-cycle line) and a RIOT interval timer (TIM1T/8T/64T/T1024T, INTIM), so the
    kernel's timer waits and scanline counts are the real ones (262 lines a frame);
  * a log of every TIA write with its cycle;
  * a beam model: RESxx strobes park an object at colour clock 3k-68+8 (k = the write
    cycle; during HBLANK at column 3), HMOVE shifts it by the signed top nibble of
    HMxx (fitted on the real SetObjectXPos, see tools/test_hud_positions.py), then
    playfield (reflect/priority/score mode), P0/P1 (NUSIZ copies and sizes, REFP,
    VDELP), M0/M1 and the ball are drawn per colour clock with the NTSC palette of the
    level editor.

It is a picture model, not a cycle-exact TIA: write latencies are one colour clock
or so, no collisions, no RESMP, no late-HMOVE quirks. Good enough to show what the
kernel puts on screen.

  from tia_render import attach, palette_rgb
  con = attach(playbot.Console())              # on a running playbot.Console
  img = con.snapshot(frames=3)                  # PIL image, 160x192 scaled 4x2
"""
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LINE = 76
VSYNC, VBLANK = 0x00, 0x01
NUSIZ0, NUSIZ1, COLUP0, COLUP1, COLUPF, COLUBK, CTRLPF = 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A
REFP0, REFP1, PF0, PF1, PF2 = 0x0B, 0x0C, 0x0D, 0x0E, 0x0F
RESP0, RESP1, RESM0, RESM1, RESBL = 0x10, 0x11, 0x12, 0x13, 0x14
GRP0, GRP1, ENAM0, ENAM1, ENABL = 0x1B, 0x1C, 0x1D, 0x1E, 0x1F
HMP0, HMP1, HMM0, HMM1, HMBL = 0x20, 0x21, 0x22, 0x23, 0x24
VDELP0, VDELP1, HMOVE, HMCLR = 0x25, 0x26, 0x2A, 0x2B
WSYNC = 0x02
OBJ = {RESP0: ("p0", HMP0), RESP1: ("p1", HMP1), RESM0: ("m0", HMM0),
       RESM1: ("m1", HMM1), RESBL: ("bl", HMBL)}
COPIES = {0: (0,), 1: (0, 16), 2: (0, 32), 3: (0, 16, 32), 4: (0, 64), 5: (0,),
          6: (0, 32, 64), 7: (0,)}


def _load_palette():
    """The editor's NTSC table: kPalette[hue][luma] (AtariPalette.cpp)."""
    src = (ROOT / "tools" / "editor" / "src" / "AtariPalette.cpp").read_text()
    body = src[src.index("kPalette[kHues][kLumas]"):src.index("kHueNames")]
    vals = [int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]{6})", body)]
    assert len(vals) == 128, len(vals)
    return [[((v >> 16) & 255, (v >> 8) & 255, v & 255)
             for v in vals[h * 8:h * 8 + 8]] for h in range(16)]


PALETTE = _load_palette()


def palette_rgb(c):
    """TIA colour byte (hue in bits 7-4, luma in bits 3-1) -> (r, g, b)."""
    return PALETTE[(c >> 4) & 15][(c >> 1) & 7]


def signed4(hm):
    n = (hm >> 4) & 15
    return n - 16 if n >= 8 else n


class Beam:
    """Register file + object positions, advanced by the logged writes."""

    def __init__(self):
        self.r = [0] * 0x40
        self.pos = {"p0": 0, "p1": 0, "m0": 0, "m1": 0, "bl": 0}
        self.new0 = self.old0 = self.new1 = self.old1 = 0
        self.blank8 = False

    def write(self, reg, val, k):
        r = self.r
        if reg in OBJ:
            name, _hm = OBJ[reg]
            self.pos[name] = 3 if 3 * k < 68 else (3 * k - 68 + 8) % 160
        elif reg == HMOVE:
            for name, hm in (("p0", HMP0), ("p1", HMP1), ("m0", HMM0),
                             ("m1", HMM1), ("bl", HMBL)):
                self.pos[name] = (self.pos[name] - signed4(r[hm])) % 160
            if 3 * k < 68 + 12:
                self.blank8 = True                 # the HMOVE comb: 8 black pixels
        elif reg == HMCLR:
            for hm in (HMP0, HMP1, HMM0, HMM1, HMBL):
                r[hm] = 0
        elif reg == GRP0:
            self.new0, self.old1 = val, self.new1
        elif reg == GRP1:
            self.new1, self.old0 = val, self.new0
        else:
            r[reg] = val

    def pixel(self, x):
        """Colour byte at visible column x (0..159)."""
        r, pos = self.r, self.pos
        ctrl = r[CTRLPF]
        # playfield
        col = x // 4
        if col >= 20:
            col = 19 - (col - 20) if ctrl & 1 else col - 20
        if col < 4:
            pf = r[PF0] & (0x10 << col)
        elif col < 12:
            pf = r[PF1] & (0x80 >> (col - 4))
        else:
            pf = r[PF2] & (1 << (col - 12))
        pf = bool(pf)
        # ball
        bl = False
        if r[ENABL] & 2:
            bl = (x - pos["bl"]) % 160 < (1 << ((ctrl >> 4) & 3))
        # players
        def player(name, nusiz, grp, refl):
            n = nusiz & 7
            scale = 2 if n == 5 else 4 if n == 7 else 1
            for off in COPIES[n]:
                d = (x - pos[name] - off) % 160
                if d < 8 * scale:
                    bit = d // scale
                    if refl & 8:
                        bit = 7 - bit
                    if grp & (0x80 >> bit):
                        return True
            return False

        def missile(name, nusiz, en):
            if not en & 2:
                return False
            size = 1 << ((nusiz >> 4) & 3)
            for off in COPIES[nusiz & 7]:
                if (x - pos[name] - off) % 160 < size:
                    return True
            return False

        g0 = self.old0 if r[VDELP0] & 1 else self.new0
        g1 = self.old1 if r[VDELP1] & 1 else self.new1
        p0 = player("p0", r[NUSIZ0], g0, r[REFP0]) or missile("m0", r[NUSIZ0], r[ENAM0])
        p1 = player("p1", r[NUSIZ1], g1, r[REFP1]) or missile("m1", r[NUSIZ1], r[ENAM1])
        pfc = r[COLUPF]
        if ctrl & 2:                                  # score mode
            pfc = r[COLUP0] if x < 80 else r[COLUP1]
        if ctrl & 4:                                  # playfield priority
            if pf or bl:
                return pfc
            if p0:
                return r[COLUP0]
            if p1:
                return r[COLUP1]
        else:
            if p0:
                return r[COLUP0]
            if p1:
                return r[COLUP1]
            if pf or bl:
                return pfc
        return r[COLUBK]


class TiaConsole:
    """Mixed into a playbot.Console: `attach(con)` re-classes a live console."""

    def tia_init(self):
        self.log = []
        self.stall = 0
        self.t_start = 0
        self.t_len = 1
        self.timer = None
        self.beam = Beam()
        self.pending_wsync = None

    # ---- virtual time ------------------------------------------------------
    def vtime(self):
        return self.mpu.processorCycles + self.stall

    def _now(self):
        return self.t_start + self.t_len - 1

    def _intim(self):
        if self.timer is None:
            return 0
        t0, interval, v = self.timer
        el = max(0, self._now() - t0)
        if el < v * interval:
            return v - el // interval
        if el < (v + 1) * interval:
            return 0
        return (-(el - (v + 1) * interval) - 1) & 0xFF

    # ---- bus ---------------------------------------------------------------
    def __getitem__(self, a):
        if (a & 0xFFFF) == 0x0284:
            return self._intim()
        return super(TiaConsole, self).__getitem__(a)

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if a < 0x80 or 0x100 <= a < 0x180:                # the TIA (and its mirror)
            reg = a & 0x3F
            t = self._now()
            self.log.append((t, reg, v))
            if reg == WSYNC:
                self.pending_wsync = t
            return
        if 0x294 <= a <= 0x297:
            self.timer = (self._now() + 1, (1, 8, 64, 1024)[a - 0x294], v)
            return
        super(TiaConsole, self).__setitem__(a, v)

    def tia_step(self):
        op = self[self.mpu.pc]
        self.t_start = self.vtime()
        self.t_len = self.mpu.cycletime[op]
        self.mpu.step()
        if self.pending_wsync is not None:
            t = self.pending_wsync
            self.pending_wsync = None
            boundary = (t // LINE + 1) * LINE
            self.stall += max(0, boundary - (self.t_start + self.t_len))

    def tia_frame(self, swcha=0xFF, fire=False):
        """Run one frame (StartFrame to StartFrame); returns the TIA write log."""
        self.swcha = swcha
        self.inpt4 = 0x00 if fire else 0x80
        self.log = []
        self.tia_step()
        while not (self.bank == 0 and self.mpu.pc == self.pc_frame):
            self.tia_step()
        self.frames += 1
        return self.log

    # ---- rendering ---------------------------------------------------------
    def render(self, log):
        """-> the visible rows (lists of 160 colour bytes) of this frame's log."""
        if not log:
            return []
        by_line = {}
        for t, reg, v in log:
            by_line.setdefault(t // LINE, []).append((t % LINE, reg, v))
        first, last = min(by_line), max(by_line)
        rows = []
        beam = self.beam
        for line in range(first, last + 1):
            ev = sorted(by_line.get(line, ()), key=lambda e: e[0])
            beam.blank8 = False
            row = []
            ei = 0
            for clk in range(0, 228):
                while ei < len(ev) and 3 * ev[ei][0] + 3 <= clk:
                    beam.write(ev[ei][1], ev[ei][2], ev[ei][0])
                    ei += 1
                if clk < 68:
                    continue
                x = clk - 68
                if beam.r[VBLANK] & 2 or (beam.blank8 and x < 8):
                    row.append(0)
                else:
                    row.append(beam.pixel(x))
            while ei < len(ev):
                beam.write(ev[ei][1], ev[ei][2], ev[ei][0])
                ei += 1
            if not beam.r[VBLANK] & 2:
                rows.append(row)
        return rows            # the kernel draws ~200 lines (not 192): keep them all

    def snapshot(self, frames=3, swcha=0xFF, fire=False, scale=(4, 2)):
        """Run `frames` frames and return the last one as a PIL image."""
        rows = []
        for _ in range(frames):
            rows = self.render(self.tia_frame(swcha, fire))
        return rows_to_image(rows, scale)


def rows_to_image(rows, scale=(4, 2)):
    img = Image.new("RGB", (160, max(len(rows), 1)))
    px = img.load()
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            px[x, y] = palette_rgb(c)
    return img.resize((160 * scale[0], len(rows) * scale[1]), Image.NEAREST)


def attach(con):
    """Turn a running playbot.Console into one that models time and the TIA."""
    cls = type("TiaShotConsole", (TiaConsole, type(con)), {})
    con.__class__ = cls
    con.tia_init()
    return con
