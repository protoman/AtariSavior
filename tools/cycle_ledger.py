#!/usr/bin/env python3
"""Cycle ledger for the bank0 kernel (`.Line` body + `.Row` setup line).

Source of truth: `src/bank0.lst` (DASM listing: address, bytes, source text).
The walker follows one path through the real instruction stream, so branch
taken/not-taken and page-cross costs are the assembled bytes, not comments.

Run: /home/iuri/python3/bin/python3 tools/cycle_ledger.py

Definitions used in the output (line-relative cycles, 76 per scanline):
  * `.Line` entry sits 8 cycles into a scanline: the previous line's
    `dec LineCount / bne .Line` (5+3) runs right after its WSYNC halt.
  * a WSYNC whose store completes at line cycle C halts the CPU at C and
    resumes at the NEXT line start, so anything after it is rebased.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LST = ROOT / "src" / "bank0.lst"

ROW = re.compile(r"^\s*\d+\s+([0-9a-f]{4})\s*((?:[0-9a-f]{2}\s+)*)\s*(.*)$")

rows: list[tuple[int, list[int], str]] = []
for line in LST.read_text(errors="replace").splitlines():
    m = ROW.match(line)
    if m:
        rows.append((int(m.group(1), 16),
                     [int(x, 16) for x in m.group(2).split()],
                     m.group(3).rstrip()))

labels: dict[str, int] = {}
for addr, bs, text in rows:
    if bs:
        continue
    t = text.split(";")[0].strip()
    if re.fullmatch(r"[A-Za-z_.][A-Za-z0-9_.]*", t):
        labels.setdefault(t, addr)

insns = []
for addr, bs, text in rows:
    if not bs:
        continue
    t = text.strip()
    if not t or t.startswith(";") or re.match(r"^[A-Za-z_.][A-Za-z0-9_.]*\s*=", t):
        continue
    parts = re.split(r"\s+", t, maxsplit=1)
    insns.append({"addr": addr, "bytes": bs, "mn": parts[0].lower(),
                  "op": (parts[1].split(";")[0].strip() if len(parts) > 1 else ""),
                  "n": len(bs), "text": t})
by_addr = {i["addr"]: k for k, i in enumerate(insns)}

BRANCH = {"bcc", "bcs", "beq", "bne", "bmi", "bpl", "bvc", "bvs"}
BASE = {
    ("lda", "imm"): 2, ("lda", "zp"): 3, ("lda", "zpx"): 4, ("lda", "abs"): 4,
    ("lda", "absx"): 4, ("lda", "absy"): 4, ("lda", "izy"): 5,
    ("ldx", "imm"): 2, ("ldx", "zp"): 3, ("ldx", "absy"): 4,
    ("ldy", "imm"): 2, ("ldy", "zp"): 3,
    ("sta", "zp"): 3, ("sta", "zpx"): 4, ("sta", "abs"): 4,
    ("sta", "absx"): 5, ("sta", "absy"): 5, ("sta", "izy"): 6,
    ("stx", "zp"): 3, ("sty", "zp"): 3,
    ("and", "imm"): 2, ("and", "zp"): 3, ("and", "abs"): 4,
    ("ora", "imm"): 2, ("ora", "zp"): 3,
    ("eor", "imm"): 2, ("eor", "zp"): 3,
    ("adc", "imm"): 2, ("adc", "zp"): 3,
    ("sbc", "imm"): 2, ("sbc", "zp"): 3,
    ("cmp", "imm"): 2, ("cmp", "zp"): 3,
    ("cpx", "imm"): 2, ("cpy", "imm"): 2, ("cpy", "zp"): 3, ("bit", "zp"): 3,
    ("asl", "acc"): 2, ("lsr", "acc"): 2, ("rol", "acc"): 2, ("ror", "acc"): 2,
    ("dec", "zp"): 5, ("inc", "zp"): 5,
    ("tax", "imp"): 2, ("tay", "imp"): 2, ("txa", "imp"): 2, ("tya", "imp"): 2,
    ("inx", "imp"): 2, ("iny", "imp"): 2, ("dex", "imp"): 2, ("dey", "imp"): 2,
    ("sec", "imp"): 2, ("clc", "imp"): 2, ("nop", "imp"): 2,
    ("pha", "imp"): 3, ("pla", "imp"): 4, ("rts", "imp"): 6,
    ("jmp", "abs"): 3, ("jsr", "abs"): 6,
    ("bcc", "rel"): 2, ("bcs", "rel"): 2, ("beq", "rel"): 2,
    ("bne", "rel"): 2, ("bmi", "rel"): 2, ("bpl", "rel"): 2,
}
# abs,X / abs,Y / (zp),Y reads pay +1 when the effective page differs from the
# base page. Which rows cross is decided by the table address, reported below.
PAGE_SENSITIVE = {("lda", "absx"), ("lda", "absy"), ("lda", "izy")}


def mode_of(ins):
    mn, op, n = ins["mn"], ins["op"], ins["n"]
    if mn in BRANCH:
        return "rel"
    if not op:
        return "imp"
    if mn in ("asl", "lsr", "rol", "ror") and op.upper() == "A":
        return "acc"
    if op.startswith("#"):
        return "imm"
    if re.fullmatch(r"\(.*\),\s*Y", op, re.I):
        return "izy"
    idx = ""
    m = re.search(r",\s*([XY])$", op, re.I)
    if m:
        idx = m.group(1).lower()
    if n == 2:
        return "zp" + idx
    if n == 3:
        return "abs" + idx
    return "imp"


def operand(ins):
    bs, n = ins["bytes"], ins["n"]
    if n == 2:
        return bs[1]
    if n >= 3:
        return bs[1] | (bs[2] << 8)
    return None


def cycles(ins):
    key = (ins["mn"], mode_of(ins))
    if key not in BASE:
        raise SystemExit(f"no cycle entry for {key} at ${ins['addr']:04x} "
                         f"({ins['text']})")
    return BASE[key]


def target_of(ins):
    off = ins["bytes"][1]
    if off > 127:
        off -= 256
    return (ins["addr"] + 2 + off) & 0xFFFF


def walk(start, decisions, skip=0, limit=400):
    pc, total, skipped = start, 0, 0
    trace, stores = [], []
    for _ in range(limit):
        if pc not in by_addr:
            raise SystemExit(f"walk left the listing at ${pc:04x}")
        ins = insns[by_addr[pc]]
        m = mode_of(ins)
        c, tgt = cycles(ins), None
        if m == "rel":
            tgt = target_of(ins)
            want = decisions.get(pc)
            if want not in ("taken", "not"):
                raise SystemExit(f"no decision for ${pc:04x} {ins['text']}")
            if want == "taken":
                c = 3 if (tgt & 0xFF00) == ((pc + 2) & 0xFF00) else 4
            else:
                tgt = None
        total += c
        trace.append((ins["addr"], ins["text"], c, total, tgt))
        if ins["mn"].startswith("sta"):
            stores.append((ins["op"], total))
        if ins["mn"] == "sta" and ins["op"].upper() == "WSYNC":
            if skipped < skip:
                skipped += 1
                total = 0        # CPU resumes at the next line start
            else:
                return total, trace, stores
        pc = tgt if tgt is not None else (ins["addr"] + ins["n"]) & 0xFFFF
        if ins["mn"] == "jmp":
            pc = operand(ins)
    raise SystemExit("walk did not terminate")


def L(name):
    if name not in labels:
        raise SystemExit(f"label {name} not in listing")
    return labels[name]


def branches_to(*names):
    want = {L(n) for n in names if n in labels}
    return {i["addr"]: None for i in insns
            if mode_of(i) == "rel" and target_of(i) in want}


line0, row0 = L(".Line"), L(".Row")
grp_skip, obj_zero, obj_nores = L(".GrpSkip"), L(".ObjZero"), L(".ObjNoRes")

ply_b = next(i["addr"] for i in insns
             if mode_of(i) == "rel" and target_of(i) == grp_skip)
obj_b = next(i["addr"] for i in insns
             if mode_of(i) == "rel" and target_of(i) == obj_zero)
a8_b = next(i["addr"] for i in insns
            if mode_of(i) == "rel" and target_of(i) == obj_nores)
always = {addr: "taken" for addr in branches_to(".AfterObj")}

PATHS = [
    ("P1 player-in, object-in (worst)",  "not", "in"),
    ("P2 player-in, object-out",         "not", "out"),
    ("P3 player-in, object first-out A==8", "not", "a8"),
    ("P4 player-out, object-in",         "taken", "in"),
    ("P5 player-out, object-out",        "taken", "out"),
    ("P6 player-out, object first-out A==8", "taken", "a8"),
]
print(f"entry: .Line=${line0:04x} .Row=${row0:04x} "
      f"gates: player=${ply_b:04x} object=${obj_b:04x} A==8=${a8_b:04x}")
PATH_TOTALS: dict[str, int] = {}
print("\n| path | cycles from .Line entry | WSYNC store at line cycle |")
print("|---|---|---|")
for name, pl, ob in PATHS:
    dec = dict(always)
    dec[ply_b] = pl
    dec[obj_b] = "taken" if ob in ("out", "a8") else "not"
    if ob == "out":
        dec[a8_b] = "taken"
    if ob == "a8":
        dec[a8_b] = "not"
    total, trace, stores = walk(line0, dec)
    PATH_TOTALS[name] = total
    print(f"| {name} | {total} | {total + 8} |")

worst = max(PATHS, key=lambda p: PATH_TOTALS[p[0]])
dec = dict(always)
dec[ply_b] = worst[1]
dec[obj_b] = "taken" if worst[2] in ("out", "a8") else "not"
if worst[2] == "out":
    dec[a8_b] = "taken"
if worst[2] == "a8":
    dec[a8_b] = "not"
total, trace, stores = walk(line0, dec)
print(f"\nworst path = {worst[0]}; store phases (line-relative):")
for op, at in stores:
    print(f"  {op:<8} c{at + 8}")

print("\n== .Row setup line (gameplay, no door: CollisionCellY b7=1) ==")


def setup(cfg_tide: bool):
    dec = dict(always)
    dec[ply_b], dec[obj_b], dec[a8_b] = "not", "taken", "taken"
    for pc in branches_to(".Line"):
        dec[pc] = "not"          # line count reached 0
    for pc in branches_to(".Row"):
        dec[pc] = "taken"        # gameplay, DropTarget != $FF
    for pc in branches_to(".M1band"):
        dec[pc] = "taken"        # no door -> band colour path
    for pc in branches_to(".WaterRow", ".AfterRows"):
        dec[pc] = "not"
    for pc in branches_to(".RowLinesTide"):
        dec[pc] = "taken" if cfg_tide else "not"
    return walk(line0, dec, skip=1)


for tide in (False, True):
    total, trace, stores = setup(tide)
    print(f"\n  {'row2 (tide)' if tide else 'rows 0/1'}: setup WSYNC store at "
          f"c{total} (window = 2 lines = 152)")
    for op, at in stores:
        if op.upper() != "WSYNC" and at > 30:   # after the .Row label
            print(f"    {op:<8} c{at}")
