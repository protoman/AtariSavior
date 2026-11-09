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
BASE_P0 = {"A": 0, "B": PAD + H0 + 1}
BASE_P1 = {"D0": 0, "D1": PAD + H1 + 1, "D2": 0}


def cycles(ins):
    op, _, arg = ins.partition(" ")
    arg = arg.strip()
    if op in ("sec", "clc", "inx", "iny", "dex", "tax", "nop", "beq", "bne"):
        return 2                          # branches: not-taken cost (taken is set by hand)
    if op in ("lda", "ldx", "ldy", "sbc", "adc", "and", "cmp", "ora"):
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


def prep1(top, h, u, late=0):
    """late=1 for P0: its fetch on the update line still uses the OLD pointer (y=36), so
    the old segment must also cover a sprite that starts one line after it."""
    imm = (h - 1 - u) & 255
    return ["clc", f"lda {top}", f"adc #{imm}", "sta T", f"cmp #{BAND + late + h}",
            "lda #0", "sbc #0", "sta M"]


def prep2(h, base, nxt):
    return [f"lda #{PAD + h}", "sec", "sbc T", "and M", "clc", f"adc {base}", f"sta {nxt}"]


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


def line(s, window):
    def build(start):
        tl = Timeline(start)
        core(tl, s, window)
        return tl.text(), tl.size
    return guarded(build)


def loop_unit(k, last_window):
    """entry pad -> LoopBody (27 lines) -> L35 (entered at c4 on the not-taken bne)."""
    def build(start):
        tl = Timeline(start)
        pad = Timeline(start)
        pad.at(5, "nop") if False else None
        # pad to c5
        gap = 5 - start
        txt = ""
        sz = 0
        if gap == 5:
            txt += "    nop\n    bit Tmp\n"
            sz += 3
        else:
            assert gap == 2
            txt += "    nop\n"
            sz += 1
        tl = Timeline(5)
        core(tl, 0, lambda t, c: None)
        txt += f"LoopBody{k}:\n" + tl.text() + "    dex\n" + f"    bne LoopBody{k}\n"
        sz += tl.size + 3
        t2 = Timeline(4)
        core(t2, -1, last_window)
        txt += t2.text()
        sz += t2.size
        return txt, sz
    return guarded(build)


def band(k):
    out = [f"; ---- band {k} ----\n"]
    u_next = BAND * (k + 1) + UPD

    # L0: PF0 / PF1 / COLUPF (left half old, right half new)
    def w0(tl, c):
        tl.at(c, f"lda PF0B+{k}")
        tl.at(c + 3, "sta PF0")                 # write c32 (>= c29)
        tl.at(c + 8, f"lda PF1B+{k}")
        tl.at(c + 11, "sta PF1")                # write c40 (>= c39)
        tl.at(c + 14, f"lda CPFB+{k}")
        tl.at(c + 20, "sta COLUPF")             # write c49 (>= c49)
    out.append(line(0, w0))
    # L1: PF2 + ball gate
    out.append(line(0, seqwin([f"lda PF2B+{k}", "sta PF2", f"lda BandTab+{k}", "sta ENABL"])))
    # L2: segment update
    out.append(line(0, seqwin(["lda NextS0", "sta G0", "sta C0", "lda NextS1", "sta G1",
                               "sta C1", "ldy #0"])))
    if k < 3:
        out.append(line(0, seqwin(prep1("P0Top", H0, u_next, 1))))
        out.append(line(0, seqwin(prep2(H0, "P0Base", "NextS0"))))
        out.append(line(0, seqwin(prep1("P1Top", H1, u_next))))
        out.append(line(0, seqwin(prep2(H1, "P1Base", "NextS1"))))
        out.append(line(0, seqwin([f"lda CPFB+{k + 1}", "and DoorAnd", "ora DoorOr",
                                   "sta BandColNext", "ldx #27"])))
    else:
        for _ in range(4):
            out.append(line(0, seqwin([])))
        out.append(line(0, seqwin(["ldx #27"])))
    last = seqwin(["lda BandColNext", "sta BandCol"]) if k < 3 else (lambda t, c: None)
    out.append(loop_unit(k, last))
    return "".join(out)


def kernel():
    return "".join(band(k) for k in range(4))


def prologue():
    """VBL code: initial segment (u=0) into the pointers, NextS for u=UPD, line-0 prime."""
    def steps(top, h, base, nxt, u, late=0):
        return "".join(f"    {i}\n" for i in prep1(top, h, u, late) + prep2(h, base, nxt))
    s = steps("P0Top", H0, "P0Base", "NextS0", 0, 1) + steps("P1Top", H1, "P1Base", "NextS1", 0)
    s += """    lda NextS0
    sta G0
    sta C0
    lda NextS1
    sta G1
    sta C1
    lda P0GHi
    sta G0+1
    lda P0CHi
    sta C0+1
    lda P1GHi
    sta G1+1
    lda P1CHi
    sta C1+1
"""
    s += steps("P0Top", H0, "P0Base", "NextS0", UPD, 1) + steps("P1Top", H1, "P1Base", "NextS1", UPD)
    s += """    lda CPFB+0
    and DoorAnd
    ora DoorOr
    sta BandCol
    sta COLUP1
    ; prime line 0: its rows are fetched on the line before the kernel (index S-1)
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
    # colour: the colour of row r is read at the gfx index of row r+1  => shift +1
    out += blk("P0C", 0xFB00, page([(BASE_P0["A"], p0c), (BASE_P0["B"], p0c)], 1))
    out += blk("P1G0", 0xFC00, page([(BASE_P1["D0"], p1g["D0"]), (BASE_P1["D1"], p1g["D1"])]))
    out += blk("P1G1", 0xFD00, page([(BASE_P1["D2"], p1g["D2"])]))
    out += blk("P1C0", 0xFE00, page([(BASE_P1["D0"], p1c), (BASE_P1["D1"], p1c)]))
    out += blk("P1C1", 0xFF00, page([(BASE_P1["D2"], p1c)])[:0xFA])
    return out


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "kernel_gen.inc").write_text(kernel())
    (out / "prologue_gen.inc").write_text(prologue())
    (out / "tables_gen.inc").write_text(tables())


if __name__ == "__main__":
    main()
