#!/usr/bin/env python3
"""Generates kernel_gen.inc + tables_gen.inc for the HERO-style kernel prototype.

Every scanline is a Timeline: instructions are placed at exact cycle targets (padding
with nop / bit), so the store phases are asserted at generation time, not hoped for.

Per-line sprite work (branch-free; X = P0 row counter, Y = P1 row counter, both start
each band at a value computed from the sprite's top line, tables are zero padded):

  c8   lda P0Col0,X   P0 colour/beam byte (table base is page+0, data at +1 => row-1)
  c12  sta COLUP0
  c15  and LaserState / sta ENAM0
  c21  lda P0Gfx,X / sta GRP0    (fetched one line ahead, latched by the GRP1 store: VDELP0)
  c28  inx
  c30..c55  free window (playfield stores, next-band counter prep)
  c55  lda P1Gfx,Y / sta GRP1 (c59, write c61)     c62 lda P1Col,Y / sta COLUP1
  c69  iny      c71 sta WSYNC
"""
import sys
from pathlib import Path

PAD = 36
H0, H1 = 22, 16
BAND = 36
BASE_P0 = {"A": 0, "B": 59}
BASE_P1 = {"D0": 0, "D1": 53}


def cycles(ins):
    op, _, arg = ins.partition(" ")
    arg = arg.strip()
    if op in ("sec", "clc", "inx", "iny", "tax", "nop"):
        return 2
    if op in ("lda", "ldx", "ldy", "sbc", "adc", "and", "cmp"):
        if arg.startswith("#"):
            return 2
        if arg.endswith(",X") or arg.endswith(",Y"):
            return 4
        return 3
    if op in ("sta", "stx", "sty", "bit"):
        return 3
    if op == "dec":
        return 5
    raise ValueError(ins)


class Timeline:
    def __init__(self, start=0):
        self.cur = start
        self.out = []

    def at(self, c, ins):
        gap = c - self.cur
        assert gap >= 0, f"{ins!r}: wanted c{c}, already at c{self.cur}"
        assert gap != 1, f"{ins!r}: 1-cycle gap before c{c}"
        if gap % 2:
            self.out.append("    bit Tmp\n")
            gap -= 3
        self.out.extend(["    nop\n"] * (gap // 2))
        self.out.append(f"    {ins}\n")
        self.cur = c + cycles(ins)

    def seq(self, c, instrs):
        for i in instrs:
            self.at(self.cur if self.cur >= c else c, i)

    def text(self):
        return "".join(self.out)


def body(tl, shift, window, last_reload=False):
    d = shift
    tl.at(8 + d, "lda P0Col0,X")
    tl.at(12 + d, "sta COLUP0")
    tl.at(15 + d, "and LaserState")
    tl.at(18 + d, "sta ENAM0")
    tl.at(21 + d, "lda P0Gfx,X")
    tl.at(25 + d, "sta GRP0")
    tl.at(28 + d, "inx")
    window(tl, 30 + d)
    tl.at(55 + d, "lda P1Gfx,Y")
    tl.at(59 + d, "sta GRP1")
    tl.at(62 + d, "lda P1Col,Y")
    tl.at(66 + d, "sta COLUP1")
    if last_reload:
        tl.at(69 + d, "ldy NextY")
    else:
        tl.at(69 + d, "iny")
    tl.at(max(tl.cur, 71 + d), "sta WSYNC")
    # the WSYNC store lands on its 3rd cycle
    assert tl.cur - 1 <= 75


def prep_a(top, table, tmp, b0n):
    return [f"stx SavX", f"lda {top}", "sec", f"sbc #{b0n}", "tax", f"lda {table},X",
            f"sta {tmp}", "ldx SavX"]


def prep_b(base, tmp, dst):
    return [f"lda {tmp}", "clc", f"adc {base}", f"sta {dst}"]


def emit_band(k):
    s = []
    b0n = BAND * (k + 1)
    prep = k < 3

    def straight(prelude, window):
        tl = Timeline(0)
        for c, i in prelude:
            tl.at(c, i)
        body(tl, 0, window)
        return tl.text()

    s.append(f"; ---- band {k} ----\n")
    # L0: PF0 / PF1 / COLUPF (the old left-half-old / right-half-new transition line)
    def w0(tl, c):
        tl.at(c, f"lda PF0B+{k}")
        tl.at(c + 3, "sta PF0")          # write c35 (>= c29)
        tl.at(c + 6, f"lda PF1B+{k}")
        tl.at(c + 9, "sta PF1")          # write c41 (>= c39)
        tl.at(c + 12, f"lda CPFB+{k}")
        tl.at(c + 17, "sta COLUPF")      # write c49 (>= c49)
    s.append(straight([(0, "lda #31"), (2, "sta LineCnt")], w0))

    def seqwin(instrs):
        def w(tl, c):
            for i in instrs:
                tl.at(max(tl.cur, c), i)
            assert tl.cur <= 55 + (0), tl.cur
        return w

    pf2 = [(0, f"lda PF2B+{k}"), (3, "sta PF2")]
    s.append(straight(pf2, seqwin(prep_a("P0Top", "SMap0", "T0", b0n) if prep else [])))
    s.append(straight([], seqwin(prep_a("P1Top", "SMap1", "T1", b0n) if prep else [])))
    s.append(straight([], seqwin((prep_b("P0Base", "T0", "NextX") + prep_b("P1Base", "T1", "NextY")) if prep else [])))
    s.append("    nop\n    nop\n    nop\n    nop\n")  # the loop's 8-cycle prelude (dec/bne)
    # loop body
    tl = Timeline(8)
    body(tl, 0, lambda t, c: None)
    s.append(f"LoopBody{k}:\n" + tl.text())
    s.append("    dec LineCnt\n")
    s.append(f"    bne LoopBody{k}\n")
    # L35: entered from the not-taken bne at c7
    tl = Timeline(7)
    body(tl, -1, (lambda t, c: t.at(c, "ldx NextX")) if prep else (lambda t, c: None), last_reload=prep)
    s.append(tl.text())
    return "".join(s)


def tables():
    def rows(tag, n, base_idx, arr):
        for r in range(n):
            arr[base_idx + r] = tag | r
    p0 = [0] * 256
    rows(0x80, H0, 36, p0)
    rows(0xC0, H0, 95, p0)
    c0 = [0] * 256
    for r in range(H0):
        c0[36 + r] = 0x40 + 2 * r
        c0[95 + r] = 0x60 + 2 * r
    p1 = [0] * 256
    rows(0x80, H1, 36, p1)
    rows(0xC0, H1, 89, p1)
    c1 = [0] * 256
    for r in range(H1):
        c1[36 + r] = 0x20 + 2 * r
        c1[89 + r] = 0x30 + 2 * r
    sm0, sm1 = [], []
    for d in range(256):
        sm0.append((37 - d) & 255 if d <= 36 or d >= 256 - (H0 - 1) else 0)
        sm1.append((37 - d) & 255 if d <= 36 or d >= 256 - (H1 - 1) else 0)

    def blk(name, org, data):
        lines = [f"    ORG ${org:04X}\n{name}:\n"]
        for i in range(0, 256, 16):
            lines.append("    .byte " + ",".join(f"${v:02X}" for v in data[i:i + 16]) + "\n")
        return "".join(lines)
    out = blk("SMap0", 0xF800, sm0) + blk("SMap1", 0xF900, sm1) + blk("P0Gfx", 0xFA00, p0)
    # P0Col0 = page base; data starts at +1 so that P0Col0,X reads colour[X-1]
    out += "    ORG $FB00\nP0Col0:\n    .byte 0\n"
    for i in range(0, 255, 15):
        out += "    .byte " + ",".join(f"${v:02X}" for v in c0[i:min(i + 15, 255)]) + "\n"
    out += blk("P1Gfx", 0xFC00, p1) + blk("P1Col", 0xFD00, c1)
    return out


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "kernel_gen.inc").write_text("".join(emit_band(k) for k in range(4)))
    (out / "tables_gen.inc").write_text(tables())


if __name__ == "__main__":
    main()
