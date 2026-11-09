#!/usr/bin/env python3
"""Probe: does the player sprite repeat art rows where the kernel changes band?

Every `sta GRP0` of the kernel is re-tagged with the art row index it fetched (the Y
register), the TIA model (tools/tia_render.py, VDELP latches included) draws the frame,
and the row shown at the sprite's first pixel is read off per scanline. Walking the
player down the room (RoomY 10..169) must show art rows 0,1,2.. on consecutive lines;
a "dup" is a row drawn twice (a stale line), a "gap"/"jump" a skipped one.

  probe_setup_sprite.py [ROMDIR|-]       (default: the live build here)

Result on 1.0.2: dups on lines 70/71, 108/109, 146/147 (+172): the two band-setup
lines (PF stores, then the PF2/Slot1 tail + WSYNC) write neither GRP0 nor GRP1, so the
previous row is shown on both. Measurement only - not a gate.
"""
import sys
sys.path.insert(0,'tools')
import playbot as P, tia_render as T

def make(rom_dir=None, level=1):
    con=P.Console(rom_dir); con.boot(level)
    base=type(con)
    class C(T.TiaConsole, base):
        def __setitem__(self,a,v):
            a&=0xFFFF; v&=0xFF
            if (a<0x80 or 0x100<=a<0x180) and (a&0x3F)==T.GRP0 and v:
                v=0x80|(self.mpu.y&0x1F)          # tag = the art row index fetched
            super().__setitem__(a,v)
    con.__class__=C; con.tia_init()
    for _ in range(4): con.tia_frame()
    return con

def shown(con):
    """{kernel-relative line: art row tag displayed at the player's first pixel}"""
    seen={}
    log=con.tia_frame()
    by={}
    for t,reg,v in log: by.setdefault(t//T.LINE,[]).append((t%T.LINE,reg,v))
    first,last=min(by),max(by)
    beam=con.beam
    orig=T.Beam.pixel
    cur=[0]
    def px(self,x):
        if x==self.pos["p0"]%160 and not self.r[T.VBLANK]&2:
            g0=self.old0 if self.r[T.VDELP0]&1 else self.new0
            if g0 & 0x80 and cur[0] < 195: seen[cur[0]]=g0&0x1F
        return orig(self,x)
    T.Beam.pixel=px
    try:
        for line in range(first,last+1):
            cur[0]=line-first
            ev=sorted(by.get(line,()),key=lambda e:e[0]); ei=0
            for clk in range(228):
                while ei<len(ev) and 3*ev[ei][0]+3<=clk:
                    beam.write(ev[ei][1],ev[ei][2],ev[ei][0]); ei+=1
                if clk>=68: beam.pixel(clk-68)
            while ei<len(ev):
                beam.write(ev[ei][1],ev[ei][2],ev[ei][0]); ei+=1
    finally:
        T.Beam.pixel=orig
    return seen

def verdict(seen):
    """list of problems in the sprite's picture: repeated art row / skipped row."""
    ls=sorted(seen)
    probs=[]
    for a,b in zip(ls,ls[1:]):
        if b==a+1:
            if seen[b]==seen[a]: probs.append(("dup",b,seen[b]))
            elif seen[b]!=seen[a]+1: probs.append(("jump",b,seen[a],seen[b]))
        else: probs.append(("gap",a,b))
    return probs

if __name__=="__main__":
    from collections import Counter
    con=make(sys.argv[1] if len(sys.argv)>1 and sys.argv[1]!="-" else None)
    kinds=Counter(); where=Counter(); nbad=0
    for ry in range(10,170):
        con.w("RoomY",ry)
        for _ in range(2): con.tia_frame()
        p=verdict(shown(con))
        nbad+=bool(p)
        for q in p:
            kinds[q[0]]+=1; where[(q[0],q[1])]+=1
    print("RoomY with problems:",nbad,"of 160", dict(kinds))
    print(sorted(where.items())[:40])
