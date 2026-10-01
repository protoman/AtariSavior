#!/usr/bin/env python3
"""Post-build verifier for savior F6 banks — run by build.sh BEFORE concat.

Any ERROR exits 1; build.sh (set -e) aborts and no savior.bin is written.
WARNs print but do not fail the build.

Checks:
  ROM   - 4x4096 banks, fold pads byte-identical ($FC68/$FC70),
          fold jmp target == real Overscan, non-zero reset vectors,
          pre-pad headroom from bank0.lst.
  Fold  - FoldIndirect ($FEF6): byte-identical block in bank0/bank2,
          expected opcodes, 1B zero margin before the $FF00 anchor,
          label address in both listings (level_bank_plan §0.1).
  Level - rooms <=4 (IsRoomDark mask), <=3 enemies+lamps (silent converter
          truncation; slot 3 would collide with LaserState at $C0),
          room_id/grid/start/miner validity, enemy bounds/types,
          model_id exists, generated room .txt shape.
  EQU   - cross-bank `Name = $XX` sync vs kernel authority (S3.0); allows
          documented aliases (ZP_ALLOW: bank1 Temp = $AD).
  Frozen - LEVEL_DATA_ADDR literal == bank2.lst LevelDataTable (models_data
           regeneration shifts bank2 labels; stale literal = empty rect cache).

Usage: verify_build.py [src_dir]
"""
import json
import re
import sys
from pathlib import Path

ERRORS: list[str] = []
WARNS: list[str] = []


def err(msg: str) -> None:
    ERRORS.append(msg)


def warn(msg: str) -> None:
    WARNS.append(msg)


def parse_lst(lines: list[str]) -> tuple[dict[str, int], list[tuple[int, str]]]:
    """Label-only lines -> {name: addr}; plus (addr, text) rows for headroom."""
    labels: dict[str, int] = {}
    rows: list[tuple[int, str]] = []
    label_re = re.compile(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
    addr_re = re.compile(r"^\s*\d+\s+([0-9a-f]{4})\s*(.*)$")
    for line in lines:
        m = label_re.match(line)
        if m:
            labels[m.group(2)] = int(m.group(1), 16)
            continue
        m = addr_re.match(line)
        if m:
            rows.append((int(m.group(1), 16), m.group(2)))
    return labels, rows


def check_rom(src: Path) -> bytes | None:
    banks: dict[int, bytes] = {}
    for i in range(4):
        p = src / f"bank{i}.bin"
        if not p.exists():
            err(f"bank{i}.bin missing")
            continue
        data = p.read_bytes()
        banks[i] = data
        if len(data) != 4096:
            err(f"bank{i}.bin is {len(data)} bytes, expected 4096")

    pad0 = b""
    if 0 in banks and 1 in banks:
        pad0 = banks[0][0xC68:0xC78]
        pad1 = banks[1][0xC68:0xC78]
        if pad0 != pad1:
            err(f"fold pads $FC68/$FC70 differ:\n"
                f"  bank0 {pad0.hex()}\n  bank1 {pad1.hex()}")
        if pad0 == bytes(16):
            err("bank0 fold pads are all zero")

    for idx in (0, 3):  # bank0 vectors + bank3 power-up vectors
        if idx in banks and banks[idx][0xFFC:0x1000] == bytes(4):
            err(f"bank{idx} reset vector is zero")

    lst_path = src / "bank0.lst"
    if not lst_path.exists():
        err("bank0.lst missing")
        return pad0
    labels, rows = parse_lst(lst_path.read_text(errors="replace").splitlines())

    if labels.get("ToMenuStub") != 0xFC68:
        err(f"ToMenuStub at {labels.get('ToMenuStub')}, expected $FC68")
    if labels.get("ToGameStub") != 0xFC70:
        err(f"ToGameStub at {labels.get('ToGameStub')}, expected $FC70")

    overscan = labels.get("Overscan")
    if overscan is None:
        err("Overscan label not found in bank0.lst")
    elif len(pad0) == 16 and pad0[13] == 0x4C:
        target = pad0[14] | (pad0[15] << 8)
        if target != overscan:
            err(f"fold pad jmp target ${target:04X} != Overscan ${overscan:04X}")

    # Pre-pad headroom: content end = addr on the row before `org $FC68`.
    for i, (addr, text) in enumerate(rows):
        if re.match(r"\s*org\s+\$FC68\b", text) and i > 0:
            end = rows[i - 1][0]
            free = 0xFC68 - end
            if free < 0:
                err(f"pre-pad code overflows $FC68 (ends ${end:04X})")
            elif free < 64:
                warn(f"pre-pad headroom only {free} bytes (ends ${end:04X}, limit $FC68)")
            break
    else:
        err("`org $FC68` directive not found in bank0.lst")

    # Fixed-time kernel / positioning contracts — enforced from bank0.lst
    # (AGENTS rule: never trust cycle counts written in comments).
    # 1) SetObjectXPos .Div15Loop: `bcs .Div15Loop` must share a page with its
    #    target (3c taken = 5c per /15 iteration). A page-cross adds 1c per
    #    iteration, so RESP0 fires 3 color-clocks late per coarse step: every
    #    sprite drifts right ~3*(X/15) px, and positions past 160 wrap to the
    #    left edge (laser S1 bug: spider jumped to the left wall).
    div15 = None
    bcs_at = None
    for addr, text in rows:
        t = text.strip()
        if t == ".Div15Loop":
            div15 = addr
        if (not t.startswith(";")) and "bcs" in t and ".Div15Loop" in t:
            bcs_at = addr
    if div15 is None or bcs_at is None:
        err("SetObjectXPos .Div15Loop/bcs not found in bank0.lst")
    elif (bcs_at + 2) >> 8 != div15 >> 8:
        err(f"SetObjectXPos bcs page-cross: bcs at ${bcs_at:04X} targets "
            f"${div15:04X} (6c/iteration, contract 5c) -> sprite X drift")
    elif not (0xFF12 <= div15 <= 0xFF1B):
        # Routine must sit between the fineAdjust table ($FF00-$FF0E, 15 bytes)
        # and org $FF20: whole routine inside one page = bcs contract safe.
        err(f"SetObjectXPos .Div15Loop at ${div15:04X} outside the "
            f"$FF10-$FF1F gap (expected ${0xFF12:04X}-${0xFF1B:04X})")
    # 2) Kernel GRP1 fetch: `lda ObjSprites,X` (X <= 71) must stay in-page
    #    (4c) or the .Line loop gains 1c on object rows (row-stretch risk).
    obj = labels.get("ObjSprites")
    if obj is None:
        err("ObjSprites label not found in bank0.lst")
    elif (obj + 71) >> 8 != obj >> 8:
        err(f"ObjSprites ${obj:04X}+71 crosses a page -> kernel "
            f"lda ObjSprites,X costs 5c (budget assumes 4c)")
    # 3) Laser S2.2: every relative branch inside the .Line hot loop
    #    (.Line .. bne .Line) must share a page with its target (3c taken
    #    budgeted; a cross costs 4c -> WSYNC one cycle late -> duplicated
    #    scanline / frame-length oscillation).
    line_at = None
    bne_at = None
    for addr, text in rows:
        t = text.strip()
        if t == ".Line":
            line_at = addr
        if (line_at is not None and addr > line_at
                and re.match(r"^(?:[0-9a-f]{2}[ \t])+\s*b[a-z]{2}\s+\.Line\b", t)):
            bne_at = addr
    if line_at is None or bne_at is None:
        err(".Line / bne .Line not found in bank0.lst (branch guard)")
    else:
        for addr, text in rows:
            if not (line_at <= addr <= bne_at):
                continue
            t = text.strip()
            m = re.match(r"^((?:[0-9a-f]{2}[ \t])+)\s*b[a-z]{2}\s", t)
            if not m:
                continue
            bs = m.group(1).split()
            if len(bs) != 2:  # relative branches are exactly 2 bytes
                continue
            off = int(bs[1], 16)
            if off > 127:
                off -= 256
            tgt = (addr + 2 + off) & 0xFFFF
            if (addr + 2) >> 8 != tgt >> 8:
                err(f".Line branch page-cross: {t.split(';')[0].strip()} at "
                    f"${addr:04X} targets ${tgt:04X} (4c, budget 3c) -> "
                    f"WSYNC overrun")
    # 4) Laser S2.2: `lda BeamMask,Y` fetch budgeted at 5c = 4c + cross
    #    ($F1xx kernel -> $FFxx table). Table moved onto the kernel's own
    #    page would make the comment/budget stale; keep it in $FFxx.
    for addr, text in rows:
        t = text.strip()
        if t.startswith(";"):
            continue
        m = re.match(r"^((?:[0-9a-f]{2}[ \t])+)\s*lda\s+BeamMask,Y\b", t)
        if m:
            bs = m.group(1).split()
            if len(bs) != 3 or int(bs[2], 16) != 0xFF:
                err(f"BeamMask fetch operand ${''.join(bs[-2:])} at "
                    f"${addr:04X} not in $FFxx (budget assumes 5c cross)")
            break
    else:
        err("lda BeamMask,Y not found in bank0.lst")
    return pad0


FOLD_ADDR = 0xFEF6
# sta $1FF8 / lda (FetchPtr),Y / sta $1FF6 / rts — plan §0.1, hand-copy
# forbidden: change the block → change these bytes + plan together.
# P3.1: bank select is absolute (was sta $1FF8,X) — see kernel.asm deviation.
FOLD_BYTES = bytes([0x8D, 0xF8, 0x1F, 0xB1, 0xE0, 0x8D, 0xF6, 0x1F, 0x60])


def check_fold_block(src: Path) -> None:
    regions: dict[int, bytes] = {}
    off = FOLD_ADDR - 0xF000
    for idx in (0, 2):
        p = src / f"bank{idx}.bin"
        if not p.exists():
            err(f"bank{idx}.bin missing (fold block check)")
            return
        data = p.read_bytes()
        if len(data) == 4096:
            regions[idx] = data[off:off + 10]
    if len(regions) < 2:
        return
    b0, b2 = regions[0], regions[2]
    if b0[:len(FOLD_BYTES)] != FOLD_BYTES:
        err(f"bank0 fold block {b0[:len(FOLD_BYTES)].hex()} != expected "
            f"{FOLD_BYTES.hex()} (block changed — update verify + plan §0.1)")
    if b0 != b2:
        err(f"fold block bank0[{FOLD_ADDR:04X}] {b0.hex()} != bank2 {b2.hex()} "
            "(byte-identity broken — data bank would execute different code)")
    if len(b0) == 10 and b0[9] != 0:
        err(f"fold margin byte ${FOLD_ADDR + 9:04X} non-zero — block grew "
            "toward the $FF00 fineAdjust anchor")
    for idx in (0, 2):
        lp = src / f"bank{idx}.lst"
        if not lp.exists():
            err(f"bank{idx}.lst missing (FoldIndirect label check)")
            continue
        labels, _ = parse_lst(lp.read_text(errors="replace").splitlines())
        addr = labels.get("FoldIndirect")
        if addr != FOLD_ADDR:
            shown = f"${addr:04X}" if addr is not None else "None"
            err(f"FoldIndirect at {shown}, expected "
                f"${FOLD_ADDR:04X} (bank{idx})")


MOTH_ENTRY = 0xFEF0
MOTH_EXIT = 0xFC49
# sta $1FF8 (entry) / sta $1FF6 (exit) — the switch halves of the E4 tramps.
MOTH_STA18 = bytes([0x8D, 0xF8, 0x1F])
MOTH_STA16 = bytes([0x8D, 0xF6, 0x1F])

# S5.3 HOF entry tramp — same pattern as the moth entry: bank0 executes
# `sta $1FF8` at $FE80, the fetch at $FE83 comes from bank2 = `jmp` target.
HOF_ENTRY = 0xFE80
# S5.4 LaserHitTest entry tramp — same pattern: `sta $1FF8` at $FE86,
# fetch at $FE89 from bank2 = `jmp LaserHitTestBody`.
LHT_ENTRY = 0xFE86


def check_moth_tramp(src: Path) -> None:
    """E4: moth code-fold tramps — byte-identity slices + address pins.

    Entry $FEF0: bank0 runs `sta $1FF8`, bank2 serves `jmp MothRoutine`
    ($FEF3). Exit $FC49: bank2 runs `sta $1FF6`, bank0 serves `jmp UE_Next`
    ($FC4C). Each bank only executes its own half, but both halves are written
    in both sources (FoldIndirect discipline) so a straight byte-compare pins
    the whole block: operand drift (e.g. bank2's MothRoutine moving while
    kernel.asm's literal stays) fails loudly.
    Also asserts $FFF2-$FFF9 stay fill in both banks: $FFF6-$FFF9 are F6
    hotspot mirrors ((addr & $1FFF) in $1FF6-$1FF9) — Stella peek() calls
    checkSwitchBank on reads (CartEnh.cxx:157), so any fetched byte there
    flips banks mid-instruction (the 2026-09-30 frame-3 crash).
    """
    banks: dict[int, bytes] = {}
    for idx in (0, 2):
        p = src / f"bank{idx}.bin"
        if not p.exists():
            err(f"bank{idx}.bin missing (moth tramp check)")
            return
        data = p.read_bytes()
        if len(data) == 4096:
            banks[idx] = data
    if len(banks) < 2:
        return

    lst0_path, lst2_path = src / "bank0.lst", src / "bank2.lst"
    if not lst0_path.exists() or not lst2_path.exists():
        err("bank0.lst/bank2.lst missing (moth tramp check)")
        return
    labels0, _ = parse_lst(lst0_path.read_text(errors="replace").splitlines())
    labels2, _ = parse_lst(lst2_path.read_text(errors="replace").splitlines())

    eoff = MOTH_ENTRY - 0xF000
    e0 = banks[0][eoff:eoff + 6]
    e2 = banks[2][eoff:eoff + 6]
    if e0[:3] != MOTH_STA18:
        err(f"bank0 moth entry ${MOTH_ENTRY:04X} = {e0.hex()} "
            f"(expected {MOTH_STA18.hex()} + jmp)")
    if e0 != e2:
        err(f"moth entry bank0[{MOTH_ENTRY:04X}] {e0.hex()} != bank2 "
            f"{e2.hex()} (byte-identity broken)")
    moth = labels2.get("MothRoutine")
    tgt = (e0[4] | (e0[5] << 8)) if len(e0) == 6 else None
    if moth is None:
        err("MothRoutine label not found in bank2.lst")
    elif tgt != moth:
        err(f"moth entry jmp ${tgt if tgt is not None else 0:04X} != "
            f"bank2 MothRoutine ${moth:04X} (entry pad and routine diverged)")
    tramp = labels0.get("UE_MothTramp")
    if tramp != MOTH_ENTRY:
        shown = f"${tramp:04X}" if tramp is not None else "None"
        err(f"UE_MothTramp at {shown}, expected ${MOTH_ENTRY:04X} "
            "(dispatch jmp target moved off the pad)")

    # S5.3 HOF tramp ($FE80) — same discipline as the moth entry above.
    hoff = HOF_ENTRY - 0xF000
    g0 = banks[0][hoff:hoff + 6]
    g2 = banks[2][hoff:hoff + 6]
    if g0[:3] != MOTH_STA18:
        err(f"bank0 HOF entry ${HOF_ENTRY:04X} = {g0.hex()} "
            f"(expected {MOTH_STA18.hex()} + jmp)")
    if g0 != g2:
        err(f"HOF entry bank0[${HOF_ENTRY:04X}] {g0.hex()} != bank2 "
            f"{g2.hex()} (byte-identity broken)")
    hof = labels2.get("HotOverlapBody")
    hof_tgt = (g0[4] | (g0[5] << 8)) if len(g0) == 6 else None
    if hof is None:
        err("HotOverlapBody label not found in bank2.lst")
    elif hof_tgt != hof:
        err(f"HOF entry jmp ${hof_tgt if hof_tgt is not None else 0:04X} != "
            f"bank2 HotOverlapBody ${hof:04X} (tramp operand stale)")
    hof_tramp = labels0.get("HotOverlapFlag")
    if hof_tramp != HOF_ENTRY:
        shown = f"${hof_tramp:04X}" if hof_tramp is not None else "None"
        err(f"HotOverlapFlag at {shown}, expected ${HOF_ENTRY:04X} "
            "(PlayerHitsMap jmp target moved off the pad)")

    # S5.4 LaserHitTest tramp ($FE86) — same discipline again.
    loff = LHT_ENTRY - 0xF000
    t0 = banks[0][loff:loff + 6]
    t2 = banks[2][loff:loff + 6]
    if t0[:3] != MOTH_STA18:
        err(f"bank0 LHT entry ${LHT_ENTRY:04X} = {t0.hex()} "
            f"(expected {MOTH_STA18.hex()} + jmp)")
    if t0 != t2:
        err(f"LHT entry bank0[${LHT_ENTRY:04X}] {t0.hex()} != bank2 "
            f"{t2.hex()} (byte-identity broken)")
    lht = labels2.get("LaserHitTestBody")
    lht_tgt = (t0[4] | (t0[5] << 8)) if len(t0) == 6 else None
    if lht is None:
        err("LaserHitTestBody label not found in bank2.lst")
    elif lht_tgt != lht:
        err(f"LHT entry jmp ${lht_tgt if lht_tgt is not None else 0:04X} != "
            f"bank2 LaserHitTestBody ${lht:04X} (tramp operand stale)")
    lht_tramp = labels0.get("LaserHitTest")
    if lht_tramp != LHT_ENTRY:
        shown = f"${lht_tramp:04X}" if lht_tramp is not None else "None"
        err(f"LaserHitTest at {shown}, expected ${LHT_ENTRY:04X} "
            "(LaserInput jsr target moved off the pad)")

    xoff = MOTH_EXIT - 0xF000
    x0 = banks[0][xoff:xoff + 3]
    x2 = banks[2][xoff:xoff + 3]
    if x0 != MOTH_STA16 or x2 != MOTH_STA16:
        err(f"moth exit slice bank0 {x0.hex()} / bank2 {x2.hex()} != "
            f"{MOTH_STA16.hex()} (sta $1FF6)")
    if banks[0][xoff + 3] != 0x4C:
        err(f"bank0 ${MOTH_EXIT + 3:04X} is not a jmp (expected jmp UE_Next)")
    else:
        un = labels0.get("UE_Next")
        op = banks[0][xoff + 4] | (banks[0][xoff + 5] << 8)
        if un is None:
            err("UE_Next label not found in bank0.lst")
        elif op != un:
            err(f"moth exit jmp ${op:04X} != UE_Next ${un:04X}")

    # F6 hotspot mirror zone: a fetch of $FFF6-$FFF9 peeks a hotspot
    # (ADDR_MASK=$1FFF) and flips banks mid-instruction (Stella peek side
    # effect). Must stay fill — no code — in every executing bank.
    for idx, data in banks.items():
        zone = data[0xFF2:0xFFA]
        if any(zone):
            err(f"bank{idx} $FFF2-$FFF9 = {zone.hex()} (must be fill: "
                "$FFF6-$FFF9 are F6 hotspot mirrors on peek)")


# Cross-bank call pads (leaf_move_plan): ReturnPad + CallPads must be
# byte-identical in bank0/bank1 (first 5 bytes fetched pre-switch, jmp/pla/
# rts post-switch), and every CallPad jmp literal must equal the bank1 label.
PAD_LO, PAD_HI = 0xFBF8, 0xFC49   # inclusive start, exclusive end (FC48 last)


def check_callpads(src: Path) -> None:
    banks: dict[int, bytes] = {}
    for idx in (0, 1):
        p = src / f"bank{idx}.bin"
        if not p.exists():
            err(f"bank{idx}.bin missing (callpad check)")
            return
        data = p.read_bytes()
        if len(data) == 4096:
            banks[idx] = data
    if len(banks) < 2:
        return
    b0 = banks[0][PAD_LO - 0xF000:PAD_HI - 0xF000]
    b1 = banks[1][PAD_LO - 0xF000:PAD_HI - 0xF000]
    if b0 != b1:
        first = next((i for i, (x, y) in enumerate(zip(b0, b1)) if x != y), 0)
        err(f"callpad block bank0[${PAD_LO + first:04X}] != bank1 "
            "(byte-identity broken — ReturnPad/CallPads must match)")

    labels0: dict[str, int] = {}
    labels1: dict[str, int] = {}
    labels2: dict[str, int] = {}
    for idx, out in ((0, "labels0"), (1, "labels1"), (2, "labels2")):
        lp = src / f"bank{idx}.lst"
        if not lp.exists():
            err(f"bank{idx}.lst missing (callpad label check)")
            return
        labs, _ = parse_lst(lp.read_text(errors="replace").splitlines())
        if idx == 0:
            labels0 = labs
        elif idx == 1:
            labels1 = labs
        else:
            labels2 = labs
    for side, labs in (("bank0", labels0), ("bank1", labels1)):
        rp = labs.get("ReturnPad")
        if rp != PAD_LO:
            err(f"{side} ReturnPad ${rp if rp is not None else -1:04X} "
                f"!= ${PAD_LO:04X} (bank1 body tails jmp literal $FBF8)")

    ksrc = (src / "kernel.asm").read_text(errors="replace")
    # ReturnPad must switch back WITHOUT touching A/flags/stack:
    # `sta $1FF6 / rts` (F6 hotspot ignores the written value).
    rp = banks[0][PAD_LO - 0xF000:PAD_LO - 0xF000 + 4]
    if rp != bytes([0x8D, 0xF6, 0x1F, 0x60]):
        err(f"ReturnPad bytes {rp.hex()} != sta $1FF6/rts "
            "(any A-clobbering sequence breaks pad arg/flag pass-through)")
    pads = re.findall(
        r"^CallPad_(\w+):\s*\n((?:[^\n]*\n){1,3}?)\s*jmp \$([0-9A-Fa-f]{4})",
        ksrc, re.M)
    if not pads:
        err("no CallPad_* definitions found in kernel.asm")
        return
    for name, body, hexv in pads:
        if re.search(r"\b(lda|tax|tay|txa|tya|pha|pla)\b", body):
            err(f"CallPad_{name}: pad body clobbers A/X/Y/stack — pads must "
                "be `sta $1FFx / jmp` only (value ignored by F6 hotspot)")
        want = int(hexv, 16)
        # `sta $1FF8` pads jump to a bank2 body (e.g. BuildColupF: the hot-rect
        # stream lives in bank2); `sta $1FF7` pads jump to bank1.
        if "sta $1FF8" in body:
            tgt_labs, tgt_side = labels2, "bank2"
        else:
            tgt_labs, tgt_side = labels1, "bank1"
        got = tgt_labs.get(name)
        if got is None:
            err(f"CallPad_{name}: jmp ${want:04X} but {name} not in "
                f"{tgt_side}.lst")
        elif got != want:
            err(f"CallPad_{name}: jmp ${want:04X} != {tgt_side} {name} "
                f"${got:04X} (stale literal — pads must be byte-identical)")


# S3.0: cross-bank EQU sync --------------------------------------------------
# kernel.asm is the authority: sequential `Name byte` walk (seg.u, org $80)
# plus every explicit `Name = $XX` hex literal. bank1/bank2 hand-copy the
# shared names; a stale copy silently reads/writes the WRONG byte with no
# assembler error (found live this session: bank1 TickCounter = $AC read
# PlayerLives in the jet-sound wobble at bank1.asm:770).
# Hex assignments only — decimal constants may legitimately differ per bank.
ZP_ALLOW: dict[tuple[str, str], str] = {
    ("bank1", "Temp"):
        "AGENTS cross-bank Temp: bank1's score-init flag lives in kernel "
        "TickCounter's slot ($AD); kernel Temp is $88 — different bytes "
        "on purpose (documented conflict, see AGENTS.md)",
}


def kernel_equ_authority(kernel: str) -> dict[str, int]:
    """name -> value. Sequential `Name byte` allocates +1 from org $80
    (decls confined to the seg.u block, verified: no `Name byte` outside
    lines 85-175); every `Name = $XX` recorded, first definition wins."""
    names: dict[str, int] = {}
    addr: int | None = None
    for line in kernel.splitlines():
        if re.match(r"\s*org\s+\$80\b", line):
            addr = 0x80
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s+byte\b", line)
        if m and addr is not None:
            names.setdefault(m.group(1), addr)
            addr += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\$([0-9A-Fa-f]+)\b",
                     line)
        if m:
            names.setdefault(m.group(1), int(m.group(2), 16))
    return names


def check_equ_sync(src: Path) -> None:
    """S3.0: every bank1/bank2 `Name = $XX` must equal kernel's value."""
    kernel = (src / "kernel.asm").read_text(encoding="utf-8")
    auth = kernel_equ_authority(kernel)
    if auth.get("TickCounter") is None or auth.get("Temp") is None:
        err("equ-sync: kernel authority walk lost Temp/TickCounter "
            "(seg.u/org $80 block moved? re-verify kernel_equ_authority)")
        return
    for bank in ("bank1.asm", "bank2.asm"):
        p = src / bank
        if not p.exists():
            err(f"{bank} missing (equ-sync)")
            continue
        side = bank.split(".")[0]
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(
                r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\$([0-9A-Fa-f]+)\b", line)
            if not m:
                continue
            name, val = m.group(1), int(m.group(2), 16)
            if (side, name) in ZP_ALLOW:
                continue
            if name in auth and auth[name] != val:
                err(f"equ-sync: {side} {name} = ${val:02X} != kernel "
                    f"${auth[name]:02X} (stale hand-copy — reads/writes the "
                    f"wrong byte)")


def check_frozen_addrs(src: Path) -> None:
    """Frozen cross-bank addresses must track the regenerated layout.

    models_data growth shifts every bank2 label after it; LEVEL_DATA_ADDR
    is a hardcoded literal in kernel.asm and silently reads shifted records
    (empty rect cache, RoomX=0) when it goes stale.
    """
    kernel = src / "kernel.asm"
    lst2 = src / "bank2.lst"
    if not kernel.exists() or not lst2.exists():
        err("kernel.asm/bank2.lst missing (frozen addr check)")
        return
    m = re.search(r"^LEVEL_DATA_ADDR\s*=\s*\$([0-9A-Fa-f]{4})",
                  kernel.read_text(encoding="utf-8"), re.M)
    if not m:
        err("LEVEL_DATA_ADDR not found in kernel.asm")
        return
    want = int(m.group(1), 16)
    labels2, _ = parse_lst(lst2.read_text(encoding="utf-8").splitlines())
    got = labels2.get("LevelDataTable")
    if got is None:
        err("LevelDataTable label not found in bank2.lst")
    elif got != want:
        err(f"LEVEL_DATA_ADDR=${want:04X} but bank2 LevelDataTable=${got:04X} "
            f"(bank2 layout shifted — update the frozen literal)")


def check_room_txt(path: Path, label: str) -> None:
    if not path.exists():
        err(f"{label}: generated room txt missing ({path.name})")
        return
    rows = [r for r in path.read_text().split("\n") if r]
    if len(rows) != 3:
        err(f"{label}: room txt has {len(rows)} rows, expected 3")
    for li, row in enumerate(rows):
        if len(row) != 20:
            err(f"{label}: row {li} is {len(row)} chars, expected 20")
        bad = set(row) - set(".,#H")
        if bad:
            err(f"{label}: row {li} has invalid chars {sorted(bad)}")


def check_levels(src: Path) -> None:
    rooms_dir = src / "rooms"
    models: dict = {}
    mp = rooms_dir / "models" / "models.json"
    if mp.exists():
        try:
            md = json.loads(mp.read_text())
            ml = md.get("models_file", md).get("models", [])
            models = {m["id"]: m for m in ml}
            for model in ml:
                if model.get("width") != 20 or model.get("height") != 3:
                    err(f"models.json model {model.get('id')}: expected 20x3 geometry")
                if len(model.get("tiles", [])) != 60:
                    err(f"models.json model {model.get('id')}: expected 60 band tiles")
        except Exception as exc:  # noqa: BLE001 - report, don't crash verifier
            err(f"models.json: {exc}")

    level_files = sorted(rooms_dir.glob("level_[0-9][0-9][0-9].json"))
    if not level_files:
        err("no level_XXX.json files found in rooms/")
        return

    for jp in level_files:
        name = jp.name
        try:
            doc = json.loads(jp.read_text())
        except Exception as exc:  # noqa: BLE001
            err(f"{name}: invalid JSON ({exc})")
            continue
        lvl = doc.get("level", doc)
        if lvl.get("cereal_class_version") != 1:
            err(f"{name}: expected migrated cereal_class_version 1")
        if lvl.get("miner_dir") not in (-1, 1):
            err(f"{name}: miner_dir must be -1 or 1")
        rooms = lvl.get("rooms", [])
        n = len(rooms)
        if n == 0:
            err(f"{name}: level has no rooms")
            continue
        if n > 4:
            err(f"{name}: {n} rooms > 4 (IsRoomDark darkness mask covers rooms 0-3 only)")

        ids = [r.get("room_id") for r in rooms]
        if sorted(ids) != list(range(n)):
            err(f"{name}: room_ids {ids} must be 0..{n - 1}")

        seen: dict[tuple, object] = {}
        for r in rooms:
            pos = (r.get("room_x"), r.get("room_y"))
            if pos in seen:
                err(f"{name}: rooms {seen[pos]} and {r.get('room_id')} share grid {pos}")
            seen[pos] = r.get("room_id")

        for key in ("start_room", "miner_room"):
            v = lvl.get(key)
            if not isinstance(v, int) or not 0 <= v < n:
                err(f"{name}: {key}={v!r} out of [0,{n})")

        try:
            if not 0 <= float(lvl.get("miner_x", -1)) < 20:
                err(f"{name}: miner_x={lvl.get('miner_x')} out of tile columns 0..19")
            if not 0 <= float(lvl.get("miner_y", -1)) <= 11:
                err(f"{name}: miner_y={lvl.get('miner_y')} out of tile rows 0..11")
            if lvl.get("miner_dir", -1) not in (-1, 1):
                err(f"{name}: miner_dir={lvl.get('miner_dir')} must be -1 or 1")
        except (TypeError, ValueError):
            err(f"{name}: miner_x/miner_y not numeric")

        level_n = int(re.search(r"level_(\d+)", jp.stem).group(1))
        for r in rooms:
            rid = r.get("room_id")
            label = f"{name} room {rid}"
            mid = r.get("model_id")
            if mid is not None and models and mid not in models:
                err(f"{label}: model_id {mid} not in models.json")

            enemies = r.get("enemies") or []
            lamps = r.get("lamps") or []
            if len(enemies) + len(lamps) > 3:
                err(f"{label}: {len(enemies)} enemies + {len(lamps)} lamps > 3 "
                    f"(MAX_ENEMIES=3, converter truncates silently; slot 3 "
                    f"would collide with LaserState at $C0)")

            for i, e in enumerate(enemies):
                el = f"{label} enemy {i}"
                t = e.get("type", 0)
                if not isinstance(t, int) or not 0 <= t <= 4:
                    err(f"{el}: type={t!r} out of 0..4")
                try:
                    if not 0 <= float(e.get("x", -1)) <= 39:
                        err(f"{el}: x={e.get('x')} out of display columns 0..39")
                    if not 0 <= float(e.get("y", -1)) <= 11:
                        err(f"{el}: y={e.get('y')} out of tile rows 0..11")
                    for k in ("range_min", "range_max"):
                        if not 0 <= float(e.get(k, 0)) <= 39:
                            err(f"{el}: {k}={e.get(k)} out of 0..39")
                except (TypeError, ValueError):
                    err(f"{el}: non-numeric coordinate")
                if e.get("dir") not in (-1, 1):
                    err(f"{el}: dir={e.get('dir')!r} must be -1 or 1")

            for i, lamp in enumerate(lamps):
                ll = f"{label} lamp {i}"
                try:
                    if not 0 <= float(lamp.get("x", -1)) <= 39:
                        err(f"{ll}: x={lamp.get('x')} out of 0..39")
                    if not 0 <= float(lamp.get("y", -1)) <= 11:
                        err(f"{ll}: y={lamp.get('y')} out of 0..11")
                except (TypeError, ValueError):
                    err(f"{ll}: non-numeric coordinate")

            for k in ("bottom_r", "bottom_g", "bottom_b"):
                v = r.get(k, 0)
                if not isinstance(v, int) or not 0 <= v <= 255:
                    err(f"{label}: {k}={v!r} out of 0..255")

            check_room_txt(
                rooms_dir / f"level_{level_n:03d}_room_{rid + 1:03d}.txt", label)


def main() -> int:
    src = (Path(sys.argv[1]) if len(sys.argv) > 1
           else Path(__file__).resolve().parent.parent / "src")
    check_rom(src)
    check_fold_block(src)
    check_moth_tramp(src)
    check_callpads(src)
    check_levels(src)
    check_equ_sync(src)
    check_frozen_addrs(src)

    for w in WARNS:
        print(f"  WARN: {w}")
    for e in ERRORS:
        print(f"  ERROR: {e}")
    if ERRORS:
        print(f"verify_build: FAILED ({len(ERRORS)} error(s))")
        return 1
    print(f"verify_build: OK ({len(WARNS)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
