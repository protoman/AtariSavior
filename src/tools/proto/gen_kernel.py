#!/usr/bin/env python3
"""Generates kernel_gen.inc, prologue_gen.inc and tables_gen.inc for the HERO-style kernel
prototype v2 (see plans/hero_style_kernel_progress.md).

Every scanline is a Timeline: instructions are placed at exact cycle targets (padding with
nop / bit), so the store phases are asserted at generation time.

Sprite fetch (branch free): ONE shared Y = line counter inside a segment, four zero page
pointers G0/C0 (player gfx/colour) and G1/C1 (object gfx/colour). A pointer's HI byte is a
per-frame constant (page of the frame/design), its LO byte S is the start offset inside the
padded block and is rewritten once per 36-line segment (line 2 of every band, `ldy #0`).

  c5   lda (C0),Y / sta COLUP0 / and LaserState / sta ENAM0     (colour of THIS line)
  c19  lda (G0),Y / sta GRP0                                    (row for the NEXT line)
  c27..c50  free window (playfield stores, segment update, next-segment arithmetic)
  c50  lda (G1),Y / sta GRP1 (write c57, latches P0 via VDELP0)
  c58  beq: gfx==0 -> COLUP1 = BandCol (M1/door strip shares COLUP1), else (C1),Y; 13c both
  c71  iny / c73 sta WSYNC
"""
import sys
from pathlib import Path

PAD = 37                     # zero bytes before/after the rows: the P0 fetch on the update
                             # line still uses the OLD pointer at y=36, so reads span y=0..36
H0, H1 = 22, 16
BAND = 36
UPD = 2                      # line of the band where the pointers are rewritten
STRIDE1 = PAD + H1 + 1       # object block stride (rows slot 16, +1 spare zero)
NSUM = 22                    # loop A + loop B lines of a band (36 - 11 specials - water - B+ - L35)
BASE_P0 = {"A": 0, "B": PAD + H0 + 1}          # frame block offsets (page = 37 zeros first)
BASE_P1 = {"D0": 0, "D1": PAD + H1 + 1, "D2": 0}


def cycles(ins):
    op, _, arg = ins.partition(" ")
    arg = arg.strip()
    if op in ("sec", "clc", "inx", "iny", "dex", "tax", "nop", "beq", "bne"):
        return 2                          # branches: not-taken cost (taken is set by hand)
    if op in ("lda", "ldx", "ldy", "sbc", "adc", "and", "cmp", "cpx", "ora"):
        if arg.startswith("#"):
            return 2
        if arg.endswith("),Y"):
            return 5
        if arg.endswith(",X") or arg.endswith(",Y"):
            return 4
        return 3
    if op in ("sta", "stx", "sty", "bit"):
        return 3
    if op == "dec" or op == "inc":
        return 5
    raise ValueError(ins)


def size(ins):
    op, _, arg = ins.partition(" ")
    if op in ("sec", "clc", "inx", "iny", "dex", "tax", "nop"):
        return 1
    return 2                      # imm / zp / (zp),Y / relative branch (no abs in the kernel)


class Timeline:
    def __init__(self, start=0):
        self.cur = start
        self.out = []
        self.size = 0

    def at(self, c, ins):
        gap = c - self.cur
        assert gap >= 0, f"{ins!r}: wanted c{c}, already at c{self.cur}"
        assert gap != 1, f"{ins!r}: 1-cycle gap before c{c}"
        if gap % 2:
            self.out.append("    bit Tmp\n")
            self.size += 2
            gap -= 3
        self.out.extend(["    nop\n"] * (gap // 2))
        self.size += gap // 2
        self.out.append(f"    {ins}\n")
        self.size += size(ins)
        self.cur = c + cycles(ins)

    def text(self):
        return "".join(self.out)


_n = [0]


def core(tl, s, window):
    """One sprite line starting at c5+s. `window(tl, start)` fills c27+s .. c50+s."""
    _n[0] += 1
    n = _n[0]
    tl.at(5 + s, "lda (C0),Y")
    tl.at(10 + s, "sta COLUP0")
    tl.at(13 + s, "and LaserState")
    tl.at(16 + s, "sta ENAM0")
    tl.at(19 + s, "lda (G0),Y")
    tl.at(24 + s, "sta GRP0")
    window(tl, 27 + s)
    assert tl.cur <= 50 + s, f"window overruns c{50 + s}: c{tl.cur}"
    tl.at(50 + s, "lda (G1),Y")
    tl.at(55 + s, "sta GRP1")
    tl.at(58 + s, f"beq .e{n}")
    tl.at(60 + s, "lda (C1),Y")
    tl.at(65 + s, "sta COLUP1")
    tl.at(68 + s, f"bne .j{n}")
    # zero-gfx path: beq taken = 3c  -> c61+s
    tl.cur = 61 + s
    tl.out.append(f".e{n}:\n")
    tl.at(61 + s, "lda BandCol")
    tl.at(64 + s, "sta COLUP1")
    tl.at(67 + s, "nop")
    tl.at(69 + s, "nop")
    assert tl.cur == 71 + s
    tl.out.append(f".j{n}:\n")
    tl.at(71 + s, "iny")
    tl.at(73 + s, "sta WSYNC")
    assert tl.cur - 1 <= 75


def seqwin(instrs):
    def w(tl, c):
        for i in instrs:
            tl.at(max(tl.cur, c), i)
    return w


_g = [0]


def guarded(build):
    """Wrap a block so it never straddles a page (a taken branch across a page costs +1c).
    build(start) -> (text, size) assembled assuming the line is entered at cycle `start`.
    Normal entry: start 0 (right after a WSYNC). Straddling case: `jmp` (3c) to an aligned
    copy that starts at c3."""
    _g[0] += 1
    ta, sa = build(0)
    tb, _ = build(3)
    return (f"    IF (* & $FF) + {sa} > $100\n    jmp .g{_g[0]}\n    align 256\n.g{_g[0]}\n"
            f"{tb}    ELSE\n{ta}    ENDIF\n")


def line(window, label=None):
    def build(start):
        tl = Timeline(start)
        core(tl, 0, window)
        return (f"{label}:\n" if label else "") + tl.text(), tl.size
    return guarded(build)


def loop_unit(name, setup, tail):
    """entry pad -> loop body -> tail line (entered at c4 on the not-taken bne)."""
    def build(start):
        gap = 5 - start
        assert gap in (5, 2)
        txt = "    nop\n    bit Tmp\n" if gap == 5 else "    nop\n"
        sz = 3 if gap == 5 else 1
        tl = Timeline(5)
        core(tl, 0, lambda t, c: None)
        txt += f"{name}:\n" + tl.text() + "    dex\n" + f"    bne {name}\n"
        sz += tl.size + 3
        t2 = Timeline(4)
        core(t2, -1, tail)
        txt += t2.text()
        sz += t2.size
        return txt, sz
    return guarded(build)


# -- next-segment arithmetic (A only) ---------------------------------------------------
# e = Top + (H-1) - u ; in range iff e < BAND + late + H ; S = ((K - e) & mask)
def step_e(h, late, e):
    """T = e, M = in-range mask. `e` is the ZP byte holding e for the NEXT update line."""
    return [f"lda {e}", "sta T", f"cmp #{BAND + late + h}", "lda #0", "sbc #0", "sta M"]


def step_s(k, dst):
    return [f"lda {k}", "sec", "sbc T", "and M", f"sta {dst}"]


def step_dec(e):
    return [f"lda {e}", "sec", f"sbc #{BAND}", f"sta {e}"]


def tail_text():
    """The last line of a band (entered at c4 after LoopB): latch the next band's colour,
    advance Band; on the last band take the exit path. Both paths cost the same up to the
    P1 section; the loop-back is `jmp BandPad` (3c) + the pad's `nop` (2c) = c5."""
    res = []
    for exit_path in (False, True):
        tl = Timeline(4)

        def w(t, c, exit_path=exit_path):
            for i in ("lda BandColNext", "sta BandCol", "inc Band", "ldx Band", "cpx #4"):
                t.at(max(t.cur, c), i)
            t.at(42, "beq .xt")                       # taken (3c) / not taken (2c)
            if exit_path:
                t.cur = 42 + 3
                t.out.append(".xt:\n")
                t.at(45, "nop")
                t.at(47, "nop")                       # 7c after the branch in both paths
            else:
                t.at(44, "bit Tmp")
                t.at(47, "nop")
        core(tl, -1, w)
        res.append(tl)
    cont, ex = res
    return cont.text() + "    jmp BandPad\n" + ex.text(), cont.size + 3 + ex.size


def kernel():
    """The same band code runs 4 times; X = band index in the special lines."""
    out = []
    # B0: PF0 / PF1 / COLUPF (left half old, right half new)
    def w0(tl, c):
        tl.at(c, "lda PF0B,X")
        tl.at(c + 4, "sta PF0")                 # write c33 (>= c29)
        tl.at(c + 7, "lda PF1B,X")
        tl.at(c + 11, "sta PF1")                # write c40 (>= c39)
        tl.at(c + 14, "lda CPFB,X")
        tl.at(c + 20, "sta COLUPF")             # write c49 (>= c49)
    def build0(start):
        # entered ONLY by `jmp BandPad` (c0-c3) + this nop = c5 (the VBL jumps too)
        tl = Timeline(5)
        core(tl, 0, w0)
        return "BandPad:\n    nop\nBandStart:\n" + tl.text(), tl.size + 1
    ta, sa = build0(0)
    _g[0] += 1
    out.append(f"    IF (* & $FF) + {sa} > $100\n    align 256\n    ENDIF\n{ta}")
    out.append(line(seqwin(["lda PF2B,X", "sta PF2", "lda BandTab,X", "sta ENABL"])))
    out.append(line(seqwin(["lda NextS0", "sta G0", "lda NextC0", "sta C0", "lda NextS1",
                            "sta G1", "sta C1", "ldy #0"])))
    out.append(line(seqwin(step_e(H0, 1, "E0"))))
    out.append(line(seqwin(step_s("#" + str(PAD + H0), "NextC0"))))
    out.append(line(seqwin(step_s("P0Kb", "NextS0"))))
    out.append(line(seqwin(step_e(H1, 0, "E1"))))
    out.append(line(seqwin(step_s("P1Kb", "NextS1"))))
    out.append(line(seqwin(step_dec("E0") + step_dec("E1"))))
    out.append(line(seqwin(["lda CPFB+1,X", "and DoorAnd", "ora DoorOr", "sta BandColNext"])))
    # loop A count: NA = NAROM[band] + (TideMask[band] & TideOff); X = NA
    out.append(line(seqwin(["lda TideMask,X", "and TideOff", "clc", "adc NAROM,X", "sta T",
                            "tax"])))
    out.append(loop_unit("LoopA", seqwin([]), seqwin([
        "ldx Band", "lda WaterXROM,X", "ora WaterOff", "tax", "lda WaterCol",
        "sta COLUBK,X"])))
    # after the water line: X = NB = NSUM - NA
    out.append(line(seqwin([f"lda #{NSUM}", "sec", "sbc T", "tax"])))
    # LoopB; its tail is the band's last line
    def buildB(start):
        gap = 5 - start
        assert gap in (5, 2)
        txt = "    nop\n    bit Tmp\n" if gap == 5 else "    nop\n"
        sz = 3 if gap == 5 else 1
        tl = Timeline(5)
        core(tl, 0, lambda t, c: None)
        txt += "LoopB:\n" + tl.text() + "    dex\n" + "    bne LoopB\n"
        sz += tl.size + 3
        tt, ts = tail_text()
        return txt + tt, sz + ts
    out.append(guarded(buildB))
    return "".join(out)


def prologue():
    """VBL code: initial pointers (u=0), NextS for the update line u=UPD, E for the first
    prep (u=UPD+36), line-0 prime, band colour."""
    def ins(lst):
        return "".join(f"    {i}\n" for i in lst)

    def sub(e, n):
        return ins([f"lda {e}", "sec", f"sbc #{n}", f"sta {e}"])
    s = ins(["lda P0Top", "clc", f"adc #{H0 - 1}", "sta E0", "lda P1Top", "clc",
             f"adc #{H1 - 1}", "sta E1"])
    # u = 0
    s += ins(step_e(H0, 1, "E0") + step_s(f"#{PAD + H0}", "NextC0") + step_s("P0Kb", "NextS0"))
    s += ins(step_e(H1, 0, "E1") + step_s("P1Kb", "NextS1"))
    s += ins(["lda NextC0", "sta C0", "lda NextS0", "sta G0", "lda NextS1", "sta G1", "sta C1",
              "lda P0GHi", "sta G0+1", "lda P0CHi", "sta C0+1", "lda P1GHi", "sta G1+1",
              "lda P1CHi", "sta C1+1"])
    # u = UPD
    s += sub("E0", UPD) + sub("E1", UPD)
    s += ins(step_e(H0, 1, "E0") + step_s(f"#{PAD + H0}", "NextC0") + step_s("P0Kb", "NextS0"))
    s += ins(step_e(H1, 0, "E1") + step_s("P1Kb", "NextS1"))
    s += sub("E0", BAND) + sub("E1", BAND)               # e for the first prep (u = UPD + 36)
    s += ins(["lda CPFB+0", "and DoorAnd", "ora DoorOr", "sta BandCol", "sta COLUP1",
              "lda #0", "sta Band"])
    s += """    ; prime line 0: its rows are fetched on the line before the kernel (index S-1)
    ldy #0
    dec G0
    lda (G0),Y
    sta GRP0
    inc G0
    dec G1
    lda (G1),Y
    sta GRP1
    inc G1
    ldy #0
    ldx #0
"""
    return s


def tables():
    def blk(name, org, data):
        lines = [f"    ORG ${org:04X}\n{name}:\n"]
        for i in range(0, len(data), 16):
            lines.append("    .byte " + ",".join(f"${v:02X}" for v in data[i:i + 16]) + "\n")
        return "".join(lines)

    def page(blocks, shift=0):
        d = [0] * 256
        for base, rows in blocks:
            for r, v in enumerate(rows):
                d[base + PAD + r + shift] = v
        return d
    p0g = {"A": [0x80 | r for r in range(H0)], "B": [0xC0 | r for r in range(H0)]}
    p0c = [0x40 + 2 * r for r in range(H0)]
    p1g = {"D0": [0x80 | r for r in range(H1)], "D1": [0xC0 | r for r in range(H1)],
           "D2": [0xA0 | r for r in range(H1)]}
    p1c = [0x20 + 2 * r for r in range(H1)]
    out = blk("P0G", 0xFA00, page([(BASE_P0["A"], p0g["A"]), (BASE_P0["B"], p0g["B"])]))
    # ONE colour block (all frames share the colours), base 0; the colour of row r is read at
    # the gfx index of row r+1  => shift +1
    out += blk("P0C", 0xFB00, page([(0, p0c)], 1))
    out += blk("P1G0", 0xFC00, page([(BASE_P1["D0"], p1g["D0"]), (BASE_P1["D1"], p1g["D1"])]))
    out += blk("P1G1", 0xFD00, page([(BASE_P1["D2"], p1g["D2"])]))
    out += blk("P1C0", 0xFE00, page([(BASE_P1["D0"], p1c), (BASE_P1["D1"], p1c)]))
    out += blk("P1C1", 0xFF00, page([(BASE_P1["D2"], p1c)])[:0xFA])
    small = """NAROM:       .byte 10,10,10,13
TideMask:    .byte 0,0,0,$FF
WaterXROM:   .byte $30,$30,$30,0
"""
    return small + out


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "kernel_gen.inc").write_text(kernel())
    (out / "prologue_gen.inc").write_text(prologue())
    (out / "tables_gen.inc").write_text(tables())


if __name__ == "__main__":
    main()
