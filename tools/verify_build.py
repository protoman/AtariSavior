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
  Level - unlimited room count (darkness mask covers rooms 0-7; rooms
  8+ stay lit), <=2 objects/room incl. miner
  (flicker budget kMaxRoomElements=2; silent converter
          truncation; slot 3 would collide with LaserState at $C0),
          room_id/grid/start/miner validity, enemy bounds/types,
          model_id exists, generated room .txt shape.
  Cell   - no model-rect cap: every collision walker tests PF cells, the
          solid rect list and the ZP rect cache are retired (plan C4).
  EQU   - cross-bank `Name = $XX` sync vs kernel authority (S3.0); allows
          documented aliases (ZP_ALLOW: bank1 Temp = $AD).
  Frozen - LEVEL_DATA_ADDR literal == bank2.lst LevelDataTable (models_data
           regeneration shifts bank2 labels; stale literal = empty PF block).
           Build self-heals first: `verify_build.py --sync SRC` patches the
           hand-copied kernel literals (LEVEL_DATA_ADDR, LEVEL_COUNT) from
           fresh sources; the checks below still verify the final ROM.

Usage: verify_build.py [src_dir]
       verify_build.py --sync [src_dir]   (pre-bank0 literal self-heal)
       verify_build.py --precheck [src_dir]  (level-window fit, pre-dasm)
"""
import json
import os
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
    # 4) Laser S2.2: `lda BeamMask,Y` fetch budgeted at 4c = no page-cross
    #    (kernel $F1xx -> table $FExx, operand + Y(<=11) must stay in $FExx).
    #    A cross would add 1c to the object-path worst case (WSYNC guard).
    for addr, text in rows:
        t = text.strip()
        if t.startswith(";"):
            continue
        m = re.match(r"^((?:[0-9a-f]{2}[ \t])+)\s*lda\s+BeamMask,Y\b", t)
        if m:
            bs = m.group(1).split()
            if len(bs) != 3 or int(bs[2], 16) != 0xFE or int(bs[1], 16) > 0xF4:
                err(f"BeamMask fetch operand ${''.join(bs[-2:])} at "
                    f"${addr:04X} not no-cross in $FExx (budget assumes 4c)")
            break
    else:
        err("lda BeamMask,Y not found in bank0.lst")
    # 5) Class-A jitter guard (bugs.md #29): the color/beam gate skips A0=11
    #    (`cpy #PLAYER_SPRITE_H - 1`) — line A0=11 inherits row 10's COLUP0
    #    and ENAM0 writes. Requires [10]==[11] in both tables (row 11 render
    #    = row bytes fetched on line A0=10; wrong pair = wrong boot color or
    #    stale beam bit, silent). Removing the -1 gate without recounting
    #    the .Line worst path is also an error (78c stall, +1 scanline).
    if 0 in banks:
        for name in ("PlayerColTable", "BeamMask"):
            a = labels.get(name)
            if a is None:
                err(f"{name} label not found in bank0.lst")
                continue
            tbl = banks[0][a - 0xF000:a - 0xF000 + 12]
            if len(tbl) < 12:
                err(f"{name} at ${a:04X}: only {len(tbl)} bytes in bank0")
            elif tbl[10] != tbl[11]:
                err(f"{name}[10]=${tbl[10]:02X} != [11]=${tbl[11]:02X} — "
                    "A0=11 gate skip inherits row 10 (verify_build #5)")
    if not any(re.search(r"\bcpy\s+#PLAYER_SPRITE_H\s*-\s*1\b", t)
               for _, t in rows):
        err("color gate `cpy #PLAYER_SPRITE_H - 1` not found in bank0.lst "
            "(A0=11 worst-line skip removed — recount the .Line worst path)")
    return pad0


FOLD_ADDR = 0xFEF6
# sta $1FF8 / lda (FetchPtr),Y / sta $1FF6 / rts — plan §0.1, hand-copy
# forbidden: change the block → change these bytes + plan together.
# P3.1: bank select is absolute (was sta $1FF8,X) — see kernel.asm deviation.
FOLD_BYTES = bytes([0x8D, 0xF8, 0x1F, 0xB1, 0xE5, 0x8D, 0xF6, 0x1F, 0x60])
# 0xE5 = FetchPtr (moved $E0→$E5 in S3.2 to free $E0 for rect4.h)


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
# `sta $1FF8` at $FE90, the fetch at $FE93 comes from bank2 = `jmp` target.
# (shifted +$10 from $FE80 when the aligned ObjColorTab/ObjSprites pair
#  took $FE00-$FE8F; mirrors in both banks moved together.)
HOF_ENTRY = 0xFFEC   # A3: moved off $FE90 (bank3 $FE93 = .OSline)
# S5.4 LaserHitTest entry tramp — same pattern: `sta $1FF8` at $FE96,
# fetch at $FE89 from bank2 = `jmp LaserHitTestBody`.
LHT_ENTRY = 0xFE96
# Tally entry tramp — same pattern: `sta $1FF7` at $FFE6 (after BeamMask,
# fetch at $FFE9 from BANK1 = `jmp TallyEntry`, repack chunk 3). Ends $FFEB so
# $FFF2-$FFF9 (F6 hotspot mirrors) stay fill.
TALLY_ENTRY = 0xFFE6


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
    for idx in (0, 1, 2, 3):
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
    labels1, _ = parse_lst((src / "bank1.lst").read_text(
        errors="replace").splitlines())

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

    # HOF tramp ($FFEC) — bank0 runs `sta $1FF8`, the opcode+operand are
    # fetched from BANK2's image at +3 ($FFEF). (C2 2026-10-20: the body moved
    # from bank3 to bank2's $F8B7 cluster with the rest of the record walkers.)
    hoff = HOF_ENTRY - 0xF000
    g0 = banks[0][hoff:hoff + 6]
    g2 = banks[2][hoff + 3:hoff + 6]
    if g0[:3] != MOTH_STA18:
        err(f"bank0 HOF entry ${HOF_ENTRY:04X} = {g0.hex()} "
            f"(expected {MOTH_STA18.hex()} + jmp)")
    if len(g2) != 3 or g2[0] != 0x4C:
        err(f"bank2 HOF image ${HOF_ENTRY + 3:04X} = {g2.hex()} "
            "(expected jmp image)")
    hof = labels2.get("HotOverlapBody")
    hof_tgt = (g2[1] | (g2[2] << 8)) if len(g2) == 3 else None
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
    # $FFF2-$FFF9 must stay fill (hotspot mirrors) — bank0 pad now ends $FFF1.


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

    # Tally entry tramp ($FFE6) — same discipline: byte-identity slice in
    # bank0/BANK1 (repack chunk 3: body moved to bank1) + operand == bank1
    # TallyEntry + label pin (kernel jsrs).
    yoff = TALLY_ENTRY - 0xF000
    y0 = banks[0][yoff:yoff + 6]
    y1 = banks[1][yoff:yoff + 6]
    if y0[:3] != bytes([0x8D, 0xF7, 0x1F]):
        err(f"bank0 tally entry ${TALLY_ENTRY:04X} = {y0.hex()} "
            "(expected 8df71f + jmp — sta $1FF7 to bank1)")
    if y0 != y1:
        err(f"tally entry bank0[${TALLY_ENTRY:04X}] {y0.hex()} != bank1 "
            f"{y1.hex()} (byte-identity broken)")
    tally = labels1.get("TallyEntry")
    tally_tgt = (y0[4] | (y0[5] << 8)) if len(y0) == 6 else None
    if tally is None:
        err("TallyEntry label not found in bank1.lst")
    elif tally_tgt != tally:
        err(f"tally entry jmp ${tally_tgt if tally_tgt is not None else 0:04X} "
            f"!= bank1 TallyEntry ${tally:04X} (tramp operand stale)")
    tally_tramp = labels0.get("TallyTramp")
    if tally_tramp != TALLY_ENTRY:
        shown = f"${tally_tramp:04X}" if tally_tramp is not None else "None"
        err(f"TallyTramp at {shown}, expected ${TALLY_ENTRY:04X} "
            "(CheckMinerPickup/TallyWork jsr target moved off the pad)")

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


# Cross-bank call pads (leaf_move_plan, SPLIT 2026-10-20 chunk 4): each pad is
# ONE live half per bank. A bank0 caller executes `sta $1FFx` at A; the opcode
# fetch at A+3 already comes from the TARGET bank, so the target keeps only the
# `jmp`. Table = (kernel label, A in bank0, target bank, sta operand byte,
# target label in that bank).
PAD_LO, PAD_HI = 0xFBF8, 0xFC49   # inclusive start, exclusive end (FC48 last)
PAD_BANK_BYTE = {0: 0xF6, 1: 0xF7, 2: 0xF8, 3: 0xF9}

CORRIDOR_PADS = (
    ("CallPad_UpdateBombSound", 0xFBFC, 1, "UpdateBombSound"),
    ("CallPad_UpdateJetSound", 0xFBFF, 1, "UpdateJetSound"),
    ("CallPad_BombSndDrop", 0xFC02, 1, "BombSndDrop"),
    ("CallPad_BombSndExplode", 0xFC05, 1, "BombSndExplode"),
    # $FC08 (CallPad_GetConnIdx) RETIRED by C3: the exit handlers read the
    # connection table in bank2 (LevelConnB2), so the pad lost its last caller.
    ("CallPad_AddScore", 0xFC0B, 1, "AddScore"),
    ("CallPad_IsRoomDark", 0xFC0E, 1, "IsRoomDark"),
    ("CallPad_SetRoomDark", 0xFC11, 1, "SetRoomDark"),
    ("CallPad_UpdateLaserSound", 0xFC14, 1, "UpdateLaserSound"),
    ("CallPad_BuildColupF", 0xFC17, 2, "BuildColupF"),
    ("CallPad_BombMarkWalls", 0xFC1A, 1, "BombMarkWalls"),
    # $FC1D (CallPad_SelectObject) RETIRED by A1 2026-10-20:
    # SelectActiveObject is back in bank0, called directly. The 3 bytes
    # stay dead so CallPad_LoadLevel keeps its $FC20 pin.
    ("CallPad_LoadLevel", 0xFC20, 2, "LoadLevelB2"),
)

# C3 (2026-10-20): room-exit entry pads — packed before the $FBF8 ReturnPad.
# bank0 half = `sta $1FF8` at A, bank2 half = `jmp ExitXxxB2` at A+3.
EXIT_PADS = (
    ("CallPad_ExitDown", 0xFBD9, 2, "ExitDownB2"),
    ("CallPad_ExitUp", 0xFBDC, 2, "ExitUpB2"),
    ("CallPad_ExitLeft", 0xFBDF, 2, "ExitLeftB2"),
    ("CallPad_ExitRight", 0xFBE2, 2, "ExitRightB2"),
)

# Tail pads (title/music): same split contract, packed after the $FC49 pin.
TAIL_PADS = (
    ("CallPad_TitleSelect", 0xFC4F, 1, "TitleSelect"),
    ("CallPad_TitleBand", 0xFC52, 1, "TitleBand"),
    ("CallPad_MusicTick", 0xFC55, 1, "MusicTick"),
)
SPLIT_PADS = CORRIDOR_PADS + EXIT_PADS + TAIL_PADS

# Pinned twin tramps: these two keep BOTH halves in bank0 and bank1 (their
# byte-identity is guarded by check_raft_tramp / check_moth_tramp); listed
# here so the "every CallPad_* is declared" test covers them too.
TWIN_PADS = (
    ("CallPad_RaftBody", 0xF8C0, "RaftBody"),
    ("CallPad_MothYDerive", 0xFEE7, "MothYDerive"),
)



def check_live_stage(src: Path) -> None:
    """The live stage must not BE the test stage.

    `tools/freeze_test_banks.sh` and `tools/raft_build.sh` replace src/rooms with
    src/tests/rooms for the duration of a build and restore it afterwards. Before
    2026-10-18 the restore was inline-only (the EXIT trap just deleted the
    backup), so an early exit left the TEST stage in src/rooms — and a blind
    `git add -A src` committed it over the user's own room edit. This makes that
    state impossible to miss: the two trees may never be byte-identical.
    Stands down while a staging script runs (it sets FREEZE_STAGED=1).
    """
    if os.environ.get("FREEZE_STAGED"):
        return
    live, test = src / "rooms", src / "tests" / "rooms"
    if not live.is_dir() or not test.is_dir():
        return
    live_files = sorted(p.relative_to(live) for p in live.rglob("*") if p.is_file())
    test_files = sorted(p.relative_to(test) for p in test.rglob("*") if p.is_file())
    if live_files != test_files:
        return
    for rel in live_files:
        if (live / rel).read_bytes() != (test / rel).read_bytes():
            return
    err("src/rooms is byte-identical to src/tests/rooms — the TEST stage is "
        "sitting in the live slot. A staging script (freeze_test_banks.sh / "
        "raft_build.sh) was interrupted; restore the live stage before "
        "building or committing.")


def check_boot_banks(src: Path) -> None:
    """F6 power-up robustness: the bank latch is UNDEFINED at power-up on real
    hardware, so any of the four banks can be the first one fetched. Every bank
    therefore needs the same 5-byte "select bank0" prefix at $F000
    (`lda #0 / sta $1FF6`), with bank0 holding `jmp GameStart` at $F005 — the
    post-switch fetch reads those three bytes from BANK0, so banks 1-3 can
    leave them as anything. Each bank's RESET vector must lead there (bank0
    jumps straight to GameStart at $F008).

    Regression this exists for: bank1 shipped with a bank-select-less
    `jmp $F008`, i.e. a 1-in-4 chance of booting into zero fill (BRK loop).
    """
    PREFIX = bytes([0xA9, 0x00, 0x8D, 0xF6, 0x1F])   # lda #0 / sta $1FF6
    bins: dict[int, bytes] = {}
    for idx in range(4):
        p = src / f"bank{idx}.bin"
        if p.exists() and p.stat().st_size == 4096:
            bins[idx] = p.read_bytes()
    if len(bins) < 4:
        err("bank images missing (boot-bank check)")
        return
    for idx, d in bins.items():
        off = 0xF000 - 0xF000
        if d[off:off + 5] != PREFIX:
            err(f"bank{idx} $F000 = {d[off:off + 5].hex()} — every bank must "
                "start with `lda #0 / sta $1FF6` (F6 can power up in ANY bank)")
        res = d[0xFFFC - 0xF000] | (d[0xFFFD - 0xF000] << 8)
        want = 0xF008 if idx == 0 else 0xF000
        if res != want:
            err(f"bank{idx} RESET vector = ${res:04X}, expected ${want:04X}")
    b0 = bins[0]
    if b0[0xF005 - 0xF000:0xF008 - 0xF000] != bytes([0x4C, 0x08, 0xF0]):
        err("bank0 $F005 must be `jmp $F008` (the landing pad the other banks "
            "fetch after switching)")


def check_raft_tramp(src: Path) -> None:
    """Raft entry tramp: bank0 executes `sta $1FF7` at $F8C0; the `jmp` opcode
    and operand are FETCHED from bank1's mirror at the same address (CallPad /
    FoldIndirect discipline). So the 6 bytes must be byte-identical in
    bank0/bank1 and the operand must be bank1's RaftBody body label (pinned
    $FDE3 by `.ds`, bank1.asm). Added 2026-10-18 with the raft: without the
    twin the tramp jumps into whatever bank1 happens to hold at that address."""
    TRAMP = 0xF8C0
    bins = {}
    for idx in (0, 1):
        p = src / f"bank{idx}.bin"
        if p.exists() and p.stat().st_size == 4096:
            bins[idx] = p.read_bytes()
    if len(bins) < 2:
        return
    off = TRAMP - 0xF000
    a, b = bins[0][off:off + 6], bins[1][off:off + 6]
    if a != b:
        err(f"raft tramp ${TRAMP:04X}: bank0 {a.hex()} != bank1 {b.hex()} "
            "(must be byte-identical: the post-switch fetch comes from bank1)")
    tgt = None
    lst = src / "bank1.lst"
    if lst.exists():
        for line in lst.read_text(errors="replace").splitlines():
            # DASM label lines: "<lineno> <addr>  <TAB>Label" — comments always
            # carry a ';', so requiring the label to END the line is enough.
            if ";" in line or not re.search(r"\bRaftBody\b", line):
                continue
            m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+RaftBody\s*$", line)
            if m:
                tgt = int(m.group(1), 16)
                break
    if tgt is None:
        err("raft tramp: bank1 RaftBody label not found in bank1.lst")
        return
    if a[3:6] != bytes([0x4C, tgt & 0xFF, tgt >> 8]):
        err(f"raft tramp ${TRAMP:04X}: jmp operand {a[3:6].hex()} != "
            f"bank1 RaftBody ${tgt:04X}")


def check_frame_tramp(src: Path) -> None:
    """PickPlayerFrame lives in bank0 (repack chunk 1, 2026-10-20).

    The VBL `jsr PickPlayerFrame` now resolves in-bank, so bank2 must no
    longer carry the body, the $FDE1 tramp mirror or the $F8DD/$FDE7 art
    twins. Guard the regression: a bank2 PickPlayerFrame label would mean a
    stray twin came back (and a switch bank0 no longer performs).
    """
    l0p, l2p = src / "bank0.lst", src / "bank2.lst"
    if not l0p.exists() or not l2p.exists():
        err("bank0.lst/bank2.lst missing (frame tramp check)")
        return
    labels0, _ = parse_lst(l0p.read_text(errors="replace").splitlines())
    labels2, _ = parse_lst(l2p.read_text(errors="replace").splitlines())
    if "PickPlayerFrame" not in labels0:
        err("PickPlayerFrame body missing from bank0.lst")
    if "PickPlayerFrame" in labels2:
        err("PickPlayerFrame still in bank2.lst (tramp/twin must be gone)")


def check_enterroom_tramp(src: Path) -> None:
    """#22 EnterRoom tramp: bank0/bank2 byte-identity + operand = body.

    bank0 executes `sta $1FF8` at labels0['EnterRoom'] ($FB84); the
    following `jmp` is FETCHED from bank2's twin at the same address, so
    all 6 bytes must match and the operand must equal bank2's EnterRoomB2
    body label (pinned $F010 by .ds).
    """
    bins: dict[int, bytes] = {}
    for idx in (0, 2):
        p = src / f"bank{idx}.bin"
        if not p.exists():
            err(f"bank{idx}.bin missing (enterroom tramp check)")
            return
        d = p.read_bytes()
        if len(d) == 4096:
            bins[idx] = d
    if len(bins) < 2:
        return
    l0p, l2p = src / "bank0.lst", src / "bank2.lst"
    if not l0p.exists() or not l2p.exists():
        err("bank0.lst/bank2.lst missing (enterroom tramp check)")
        return
    labels0, _ = parse_lst(l0p.read_text(errors="replace").splitlines())
    labels2, _ = parse_lst(l2p.read_text(errors="replace").splitlines())
    tramp = labels0.get("EnterRoom")
    body = labels2.get("EnterRoomB2")
    if tramp is None or body is None:
        err("EnterRoom label missing (bank0 tramp / bank2 EnterRoomB2 body)")
        return
    off = tramp - 0xF000
    b0 = bins[0][off:off + 6]
    b2 = bins[2][off:off + 6]
    if len(b0) == 6 and b0[:3] != bytes((0x8D, 0xF8, 0x1F)):
        err(f"bank0 EnterRoom tramp ${tramp:04X} = {b0.hex()} (expected 8df81f + jmp)")
    if b0 != b2:
        err(f"enterroom tramp bank0[${tramp:04X}] {b0.hex()} != bank2 {b2.hex()} "
            f"(byte-identity broken — bank2 twin missing/moved)")
    if len(b0) == 6:
        tgt = b0[4] | (b0[5] << 8)
        if tgt != body:
            err(f"enterroom tramp jmp ${tgt:04X} != bank2 EnterRoomB2 "
                f"${body:04X} (operand stale)")


def check_blast_tramp(src: Path) -> None:
    """BombEnemyBlast tramp: bank0/bank2 byte-identity + operand = body.

    2026-10-10 bug #10: operand was hand-synced to $FD6B while
    BombEnemyBlastBody lives at $FD6A — both copies byte-identical and
    equally wrong, execution entered mid-instruction and `inc $4A,X`
    aliased into $CA (wall bits set with no store that could explain it).
    Byte-identity alone proves nothing; the operand must equal the label.
    """
    bins: dict[int, bytes] = {}
    for idx in (0, 2):
        p = src / f"bank{idx}.bin"
        if not p.exists():
            err(f"bank{idx}.bin missing (blast tramp check)")
            return
        d = p.read_bytes()
        if len(d) == 4096:
            bins[idx] = d
    if len(bins) < 2:
        return
    l0p, l2p = src / "bank0.lst", src / "bank2.lst"
    if not l0p.exists() or not l2p.exists():
        err("bank0.lst/bank2.lst missing (blast tramp check)")
        return
    labels0, _ = parse_lst(l0p.read_text(errors="replace").splitlines())
    labels2, _ = parse_lst(l2p.read_text(errors="replace").splitlines())
    tramp = labels0.get("BombEnemyBlast")
    body = labels2.get("BombEnemyBlastBody")
    if tramp is None or body is None:
        err("BombEnemyBlast/BombEnemyBlastBody label missing (blast tramp)")
        return
    off = tramp - 0xF000
    b0 = bins[0][off:off + 6]
    b2 = bins[2][off:off + 6]
    if len(b0) == 6 and b0[:3] != bytes((0x8D, 0xF8, 0x1F)):
        err(f"bank0 BombEnemyBlast tramp ${tramp:04X} = {b0.hex()} (expected 8df81f + jmp)")
    if b0 != b2:
        err(f"blast tramp bank0[${tramp:04X}] {b0.hex()} != bank2 {b2.hex()} "
            f"(byte-identity broken — bank2 twin missing/moved)")
    if len(b0) == 6:
        tgt = b0[4] | (b0[5] << 8)
        if tgt != body:
            err(f"blast tramp jmp ${tgt:04X} != bank2 BombEnemyBlastBody "
                f"${body:04X} (operand stale)")


def check_loadlevel_tramp(src: Path) -> None:
    """C2 (2026-10-20): LoadLevel lives in bank2; the RETURN half is inverted.

    Entry is an ordinary split pad (SPLIT_PADS: bank0 `sta $1FF8` at $FC20,
    bank2 `jmp LoadLevelB2` at $FC23). The return is the mirror image: the
    bank2 body tail `jmp $FC26` executes BANK2's `sta $1FF6` there, so the
    fetch at $FC29 comes from bank0, which must hold `jmp LF_B0Tail` (the
    drop-in tail: EnterRoom + placement + `jmp DropArm`). Both halves are
    pinned byte-for-byte, and the drop-in tail's shape is pinned too: if it
    ever moves back into bank2 the stack depth of boot/RESET grows by a jsr
    level (sim_bomb_fuse / test_tally measure it), so a silent relocation is
    exactly the failure this guard must catch.
    """
    PAD_ENTRY, PAD_RET = 0xFC20, 0xFC26
    bins: dict[int, bytes] = {}
    for idx in (0, 2):
        p = src / f"bank{idx}.bin"
        if not p.exists():
            err(f"bank{idx}.bin missing (loadlevel tramp check)")
            return
        d = p.read_bytes()
        if len(d) == 4096:
            bins[idx] = d
    if len(bins) < 2:
        return
    l0p, l2p = src / "bank0.lst", src / "bank2.lst"
    if not l0p.exists() or not l2p.exists():
        err("bank0.lst/bank2.lst missing (loadlevel tramp check)")
        return
    labels0, _ = parse_lst(l0p.read_text(errors="replace").splitlines())
    labels2, _ = parse_lst(l2p.read_text(errors="replace").splitlines())

    def at(bank: int, addr: int, n: int) -> bytes:
        return bins[bank][addr - 0xF000:addr - 0xF000 + n]

    if labels0.get("LoadLevel") != PAD_ENTRY:
        err(f"bank0 LoadLevel ${labels0.get('LoadLevel', -1):04X} != "
            f"${PAD_ENTRY:04X} (entry pad)")
    if at(0, PAD_ENTRY, 3) != bytes((0x8D, 0xF8, 0x1F)):
        err(f"bank0 ${PAD_ENTRY:04X} = {at(0, PAD_ENTRY, 3).hex()} != "
            "sta $1FF8 (8d f8 1f)")
    body = labels2.get("LoadLevelB2")
    if body is None:
        err("bank2 LoadLevelB2 label missing")
        return
    got = at(2, PAD_ENTRY + 3, 3)
    if got != bytes((0x4C, body & 0xFF, body >> 8)):
        err(f"bank2 ${PAD_ENTRY + 3:04X} = {got.hex()} != jmp LoadLevelB2 "
            f"${body:04X} (stale operand)")
    if at(2, PAD_RET, 3) != bytes((0x8D, 0xF6, 0x1F)):
        err(f"bank2 ${PAD_RET:04X} = {at(2, PAD_RET, 3).hex()} != sta $1FF6 "
            "(the body tail jmp $FC26 must land on the bank0 switch)")
    tail = labels0.get("LF_B0Tail")
    if tail is None:
        err("bank0 LF_B0Tail label missing (LoadLevel drop-in tail)")
        return
    got = at(0, PAD_RET + 3, 3)
    if got != bytes((0x4C, tail & 0xFF, tail >> 8)):
        err(f"bank0 ${PAD_RET + 3:04X} = {got.hex()} != jmp LF_B0Tail "
            f"${tail:04X} (the post-swap fetch comes from bank0)")
    # The tail must stay in bank0 and keep its three jobs.
    ksrc = (src / "kernel.asm").read_text(errors="replace")
    m = re.search(r"^LF_B0Tail:\n((?:[ \t]+[^\n]*\n)+)", ksrc, re.M)
    if not m:
        err("bank0 LF_B0Tail body not found next to its label")
    else:
        want = ("lda LevelStartRoom", "jsr EnterRoom", "lda LevelStartX",
                "sta RoomX", "lda LevelStartY", "sta RoomY", "jmp DropArm")
        norm = [ln.split(";")[0].strip() for ln in m.group(1).splitlines()]
        norm = [ln for ln in norm if ln]
        if tuple(norm) != want:
            err(f"LF_B0Tail body {norm} != {list(want)} (EnterRoom + level-start "
                "placement + DropArm must stay in bank0)")
    if "LoadLevelB2" in labels0:
        err("bank0.lst has a LoadLevelB2 label (body must live in bank2 only)")


def check_exit_handlers(src: Path) -> None:
    """C1/C3 (2026-10-20): the four room-exit handlers live in bank2.

    LEVEL_FORMAT 2/3: there is no connection table. A room owns ONE
    grid-position byte at level base + n (C2 2026-10-20: the room record is
    three 1 B columns, so the position column still starts one block-of-n in),
    and an exit steps that byte by a direction delta
    ($FF up / $01 down / $F0 left / $10 right) and SCANS the level's position
    column (unconditional, <= LevelRoomN iterations). Invariants that a
    "harmless" edit can silently break:

    1. **A must still hold the room index at the `jmp EnterRoomB2`** — the edge
       placement therefore writes RoomY/RoomX through Y (`ldy ExitEdgeTab,X` /
       `sty ...`). Storing `lda #PLAYER_MIN_Y / sta RoomY` would pass
       0/4/132/159 as the room number (EnterRoomB2 does `sta RoomNo` first).
    2. **the placement must precede EnterRoomB2** — EnterRoomB2 + B3RoomBlocks
       read neither RoomX nor RoomY, so writing them first is equivalent to the
       old post-call store, and it lets the whole tail stay in bank2 (0 extra
       pushes: EnterRoomB2's ReturnPad pops the original bank0 `jsr ExitRoomXxx`).
    3. **the direction stubs must load the table index that matches their
       direction** (ExitDeltaTab/ExitEdgeTab order = up, down, left, right).
       Swapping two stubs would silently connect the wrong neighbours.
    4. **the no-exit path must be a branch to ExitNoneB2** (C from the scan) —
       ExitNoneB2 tail-jmps ReturnPad.
    """
    b2p = src / "bank2.asm"
    if not b2p.exists():
        err("bank2.asm missing (exit handlers check)")
        return
    text = b2p.read_text(errors="replace")

    def body(name: str) -> list[str] | None:
        m = re.search(rf"^{name}:\n(.*?)(?=^[A-Za-z_][A-Za-z0-9_]*:)",
                      text, re.M | re.S)
        if not m:
            err(f"{name} body not found in bank2.asm")
            return None
        code = [ln.split(";")[0].strip() for ln in m.group(1).splitlines()]
        return [ln for ln in code if ln]

    # 3: stub -> direction index (table order up, down, left, right)
    for name, idx in (("ExitUpB2", 0), ("ExitDownB2", 1),
                      ("ExitLeftB2", 2), ("ExitRightB2", 3)):
        b = body(name)
        if b is None:
            continue
        if f"ldx #{idx}" not in b:
            err(f"{name}: must select direction {idx} (`ldx #{idx}`) — "
                "ExitDeltaTab/ExitEdgeTab order is up, down, left, right")
        if "jmp ExitDirB2" not in b and name != "ExitRightB2":
            err(f"{name}: must tail-jmp ExitDirB2 (shared body)")

    # shared body
    b = body("ExitDirB2")
    if b is not None:
        adc_n = sum(1 for ln in b if ln == "adc LevelRoomN")
        if adc_n != 1 or "sta FetchPtr" not in b:
            err(f"ExitDirB2: FetchPtr must stage level base + n "
                f"(RoomPositions, C2 3 B columns) — found {adc_n} "
                "`adc LevelRoomN`")
        if "adc ExitDeltaTab,X" not in b:
            err("ExitDirB2: neighbour position must be `adc ExitDeltaTab,X` "
                "(nibble-wrap = off-grid, no guard code)")
        if "jsr ExitScanB2" not in b:
            err("ExitDirB2: the exit must scan the position column "
                "(jsr ExitScanB2)")
        if "bcs ExitNoneB2" not in b:
            err("ExitDirB2: no-exit path must branch on the scan carry")
        if not any(ln.startswith("sty Room") for ln in b):
            err("ExitDirB2: opposite-edge placement must `sty RoomY/RoomX` "
                "(A must keep the room index for EnterRoomB2)")
        if "jmp EnterRoomB2" not in b:
            err("ExitDirB2: exit must tail-jmp EnterRoomB2 (its ReturnPad pops "
                "the bank0 caller frame — an `rts` here would strand bank2)")
        else:
            pos = len(b) - 1 - b[::-1].index("jmp EnterRoomB2")
            sty = [i for i, ln in enumerate(b) if ln.startswith("sty Room")]
            if not sty or max(sty) > pos:
                err("ExitDirB2: edge store sits AFTER `jmp EnterRoomB2` in the "
                    "list (unreachable code)")
        if not any(ln.startswith("ldy ExitEdgeTab,X") for ln in b):
            err("ExitDirB2: the edge value must come from ExitEdgeTab,X")

    # tables: order IS the direction contract
    m = re.search(r"^ExitDeltaTab:\n\s*\.byte\s*([^\n]+)", text, re.M)
    if not m:
        err("ExitDeltaTab not found in bank2.asm")
    else:
        vals = [v.strip() for v in m.group(1).split(";")[0].split(",")]
        if vals[:4] != ["$FF", "$01", "$F0", "$10"]:
            err(f"ExitDeltaTab must be $FF,$01,$F0,$10 (up,down,left,right) "
                f"— got {vals[:4]}")
    m = re.search(r"^ExitEdgeTab:\n\s*\.byte\s*([^\n]+)", text, re.M)
    if not m:
        err("ExitEdgeTab not found in bank2.asm")
    else:
        want = ["PLAYER_MAX_Y", "PLAYER_MIN_Y", "PLAYER_MAX_X", "PLAYER_MIN_X"]
        got = [v.strip() for v in m.group(1).split(";")[0].split(",")][:4]
        if got != want:
            err(f"ExitEdgeTab must be {want} (up enters at the bottom edge, "
                f"down at the top, left at the right, right at the left) — "
                f"got {got}")

    # scan loop: bounded by the level's room count, returns a room index
    b = body("ExitScanB2")
    if b is not None:
        if not any(ln.startswith("cpy LevelRoomN") for ln in b):
            err("ExitScanB2: the scan must be bounded by `cpy LevelRoomN`")
        if "tya" not in b:
            err("ExitScanB2: a hit must return the ROOM INDEX (tya)")
        if "sec" not in b or "clc" not in b:
            err("ExitScanB2: must return C=0 hit / C=1 none")

    if not re.search(r"^ExitNoneB2:\n\s+jmp ReturnPad", text, re.M):
        err("ExitNoneB2 must tail-jmp ReturnPad (only exit back to bank0)")
    # the retired connection table must be gone from the reader bank
    if "RoomConnections" in text:
        err("bank2.asm still reads RoomConnections — LEVEL_FORMAT 2 uses the "
            "1 B RoomPositions grid byte (C1)")
    # bank1's GetConnIdx must no longer be reachable, and bank0 must not define
    # the handler bodies (they live in bank2 only)
    ksrc = (src / "kernel.asm").read_text(errors="replace")
    if re.search(r"^ExitRoom\w*:\n\s+jsr CallPad_GetConnIdx", ksrc, re.M):
        err("bank0 still runs a GetConnIdx exit handler (C3 moved it)")
    for name in ("ExitUpB2", "ExitDownB2", "ExitLeftB2", "ExitRightB2"):
        if name in re.findall(r"^(\w+):", ksrc, re.M):
            err(f"kernel.asm defines {name} (body must live in bank2 only)")


def check_level_format(src: Path) -> None:
    """C5 (2026-10-20): LEVEL_FORMAT 4 = shape-index records + async extras.

    The generated level index is the converter's truth; kernel.asm and
    bank1.asm carry hand copies (bank1's is also paired by check_equ_sync).
    A stale generated/ tree is exactly the failure this guard exists for:
    format 2 rows carried a 2 B RoomRects word, so bank2's `base + n / +2n /
    +3n` columns would read the wrong bytes and EnterRoom would jump through
    a garbage block pointer. Layout per level (n = room count):

        base +  0   RoomShapes     1 B  (idx b5-0 | band b6 | extras b7)
        base +  n   RoomPositions  1 B  (x<<4|y)
        base + 2n   RoomCounts     1 B  (count<<6 | extras ordinal)
        base + 3n   EnemyDataTable 4 B/record
        ..          LEVELn_AsyncExtras  variable records (C5)

    The block address is `LEVEL_ShapeTable[shape index]` (a 2 B word table in
    levels_index.asm); the MetaA/MetaB pair is no longer inside the block
    (`TilePF0+9/+10` retired) — it lives in the extras record. The counts
    byte's b5-0 is the room's 1-based extras ordinal (0 = none) and MUST
    agree with the shape byte's b7, or the loader would read a record that
    is not there (or ignore one that is).
    """
    idx = src / "generated" / "levels_index.asm"
    if not idx.exists():
        err("generated/levels_index.asm missing (level-format check)")
        return
    idx_text = idx.read_text(errors="replace")
    m = re.search(r"^LEVEL_FORMAT = \$([0-9a-fA-F]{2})\b", idx_text, re.M)
    if not m:
        err("levels_index.asm does not declare LEVEL_FORMAT — rerun ./build.sh "
            "(format 3 = C2 shape-index room records)")
        return
    gen_fmt = int(m.group(1), 16)
    if gen_fmt != 4:
        err(f"generated LEVEL_FORMAT = {gen_fmt}, the bank2 reader implements "
            "4 (shape-index records + async extras) — stale generated tree or "
            "half-done migration")
    for name in ("kernel.asm", "bank1.asm"):
        p = src / name
        if not p.exists():
            continue
        hm = re.search(r"^LEVEL_FORMAT\s*=\s*\$([0-9a-fA-F]{2})\b",
                       p.read_text(errors="replace"), re.M)
        if not hm:
            err(f"{name}: LEVEL_FORMAT hand copy missing (C2)")
        elif int(hm.group(1), 16) != gen_fmt:
            err(f"{name}: LEVEL_FORMAT ${hm.group(1)} != generated "
                f"${gen_fmt:02X} — stale hand copy")

    # --- shape registry + address table -----------------------------------
    shape_equ = {name: int(value) for name, value in re.findall(
        r"^SHAPE_(\w+) = (\d+)$", idx_text, re.M)}
    m = re.search(r"^LEVEL_SHAPE_COUNT = (\d+)$", idx_text, re.M)
    if not m:
        err("levels_index.asm must declare LEVEL_SHAPE_COUNT (C2)")
        shape_count = 0
    else:
        shape_count = int(m.group(1))
        if shape_count > 64:
            err(f"LEVEL_SHAPE_COUNT = {shape_count} > 64 — the room record "
                "shape index is 6 bits (b5-0)")
    table = re.search(r"^LEVEL_ShapeTable:\n((?:  \.word \w+RoomRects\n)+)",
                      idx_text, re.M)
    if not table:
        err("levels_index.asm must emit LEVEL_ShapeTable (C2 word table)")
    else:
        words = len(re.findall(r"^  \.word ", table.group(1), re.M))
        if words != shape_count:
            err(f"LEVEL_ShapeTable has {words} words but LEVEL_SHAPE_COUNT = "
                f"{shape_count}")
    used: set = set()
    for path in sorted((src / "generated").glob("level_*_rooms.asm")):
        text = path.read_text(errors="replace")
        if "RoomDataTable" in text or "RoomEnemies" in text:
            err(f"{path.name}: stale room-table label (RoomDataTable/"
                "RoomEnemies) — LEVEL_FORMAT 3 has no per-room block word")
        shapes = re.findall(
            r"^  \.byte (SHAPE_\w+)(?: \| \$([0-9a-f]{2}))? ; room (\d+) \(",
            text, re.M)
        pos = re.findall(r"^  \.byte \$([0-9a-f]{2}) ; room \d+ \(\d+, \d+\)$",
                         text, re.M)
        counts = re.findall(r"^  \.byte \$([0-9a-f]{2}) ; room \d+: "
                            r"(\d) record", text, re.M)
        if not shapes or not (len(shapes) == len(pos) == len(counts)):
            err(f"{path.name}: {len(shapes)} shape bytes vs {len(pos)} "
                f"positions vs {len(counts)} counts — LEVEL_FORMAT 3 emits "
                "exactly 1 B of each per room")
            continue
        if [int(i) for _n, _b, i in shapes] != list(range(len(shapes))):
            err(f"{path.name}: room indices are not 0..n-1 in order")
        owns_flags: list[bool] = []
        for name, flags_hex, index in shapes:
            shape = name[6:]
            if shape not in shape_equ:
                err(f"{path.name}: room {index} shape {name} has no "
                    "`SHAPE_<label> = n` EQU in levels_index.asm")
                continue
            value = shape_equ[shape]
            if value >= shape_count:
                err(f"{path.name}: room {index} shape {name} = {value} is "
                    f"outside LEVEL_ShapeTable (0..{shape_count - 1})")
            used.add(value)
            flags = int(flags_hex, 16) if flags_hex else 0
            if flags & ~0xC0:
                err(f"{path.name}: room {index} sets unsupported shape-byte "
                    f"bits ${flags:02x} (only b6 = band flag and b7 = "
                    "owns-extras are defined)")
            owns_flags.append(bool(flags & 0x80))
        for hexv in pos:
            b = int(hexv, 16)
            if (b >> 4) == 0xF or (b & 0x0F) == 0xF:
                err(f"{path.name}: position byte ${hexv} has a nibble of 15 — "
                    "reserved as the off-grid sentinel (POSITION_SPAN 15)")
        ordinals: list[int] = []
        for i, (hexv, count) in enumerate(counts):
            b = int(hexv, 16)
            ordinal = b & 0x3F
            owns = owns_flags[i] if i < len(owns_flags) else False
            if bool(ordinal) != owns:
                err(f"{path.name}: room {i} shape b7 owns-extras={int(owns)} "
                    f"but its count byte ${hexv} carries extras ordinal "
                    f"{ordinal} — the loader dispatches on b7 and indexes "
                    "with b5-0, so they must agree")
            if ordinal:
                ordinals.append(ordinal)
            if int(count) > 3:
                err(f"{path.name}: room has {count} enemy records > 3 "
                    "(MAX_ENEMIES)")
        # --- C5 extras stream: one record per owns-extras room, in order ---
        hit = re.search(r"^LEVEL\d+_AsyncExtras:\n((?:  \.byte[^\n]*\n)+)",
                        text, re.M)
        records = hit.group(1).splitlines() if hit else []
        if ordinals != list(range(1, len(ordinals) + 1)):
            err(f"{path.name}: extras ordinals {ordinals} are not 1..N in "
                "room order (the loader walks the stream by ordinal)")
        if len(records) != len(ordinals):
            err(f"{path.name}: {len(records)} AsyncExtras records for "
                f"{len(ordinals)} owns-extras rooms")
        for n, line in enumerate(records):
            payload = line.split(".byte", 1)[1].split(";")[0]
            vals = [int(v.strip().lstrip("$"), 16)
                    for v in payload.split(",")]
            if len(vals) < 3:
                err(f"{path.name}: extras record {n + 1} shorter than the "
                    "flags + MetaA/MetaB header")
                continue
            flags = vals[0]
            npatch, nfeat = flags & 0x03, (flags >> 2) & 0x0F
            want = 3 + npatch + nfeat
            if nfeat:
                hot_at = want
                if len(vals) <= hot_at:
                    err(f"{path.name}: extras record {n + 1} has no hot "
                        "count byte (n_features > 0 requires the room's hot "
                        "stream)")
                    continue
                want += 1 + 5 * vals[hot_at]
            if flags & 0xC0:
                err(f"{path.name}: extras record {n + 1} sets reserved flags "
                    f"${flags:02x} (only b5-0 are n_features/n_patches)")
            if len(vals) != want:
                err(f"{path.name}: extras record {n + 1} is {len(vals)} B, "
                    f"the flags say {want} B (n_patches={npatch}, "
                    f"n_features={nfeat})")
                continue
            if nfeat and vals[2] & 0x80:
                err(f"{path.name}: extras record {n + 1} MetaB sets b7 (the "
                    "retired shutter/door flag) — StageBandTab masks it out "
                    "but the record must stay clean")
    if shape_count and used != set(range(shape_count)):
        err(f"LEVEL_ShapeTable entries {sorted(set(range(shape_count)) - used)} "
            "are unreferenced — the shape stream and the table drifted")


def check_tramp_targets(src: Path) -> None:
    """Generic: every `sta $1FFx` + `jmp $Fxxx` pair must land on a
    destination-bank listing row start (label/instruction/data start).

    Catches the stale-operand class generally: a 1-byte-wrong jmp operand
    lands between rows, like 2026-10-10 ($FD6B vs BombEnemyBlastBody
    $FD6A). Comment text is stripped first so prose mentioning tramps
    (e.g. bank1's retired $F937 pin comments) cannot false-positive. bank3.lst
    is emitted by build.sh (added 2026-10-16 — it was a silent fossil
    before, misdirecting label lookups).
    """
    hot = {"$1FF6": 0, "$1FF7": 1, "$1FF8": 2, "$1FF9": 3}
    starts: dict[int, set[int]] = {}
    for b in range(4):
        p = src / f"bank{b}.lst"
        if not p.exists():
            err(f"bank{b}.lst missing (tramp target check)")
            return
        labels, rows = parse_lst(p.read_text(errors="replace").splitlines())
        starts[b] = {a for a, _ in rows} | set(labels.values())
    sta_re = re.compile(r"sta\s+(\$1FF[6789])(?![0-9A-Fa-f])")
    jmp_re = re.compile(r"jmp\s+\$([0-9a-fA-F]{4})")

    def check(dest: int, tgt: int, where: str) -> None:
        if not 0xF000 <= tgt <= 0xFFFF:
            err(f"{where} tramp jmp ${tgt:04X} outside code space")
        elif tgt not in starts[dest]:
            err(f"{where} tramp -> jmp ${tgt:04X} is NOT a bank{dest} "
                f"listing row start (stale operand)")

    for name in ("kernel.asm", "bank1.asm", "bank2.asm", "bank3.asm"):
        p = src / name
        if not p.exists():
            continue
        lines = p.read_text(errors="replace").splitlines()
        for i, raw in enumerate(lines):
            code = raw.split(";", 1)[0]
            m = sta_re.search(code)
            if not m:
                continue
            dest = hot[m.group(1)]
            where = f"{name}:{i + 1}"
            mj = jmp_re.search(code[m.end():])
            if mj:  # sta + jmp on the same line
                check(dest, int(mj.group(1), 16), where)
                continue
            for j in range(i + 1, min(i + 9, len(lines))):  # next code line only
                nxt = lines[j].split(";", 1)[0].strip()
                if not nxt:
                    continue
                mj = jmp_re.search(nxt)
                if mj and not re.search(r"\bjsr\b|\brts\b|\.byte", nxt):
                    check(dest, int(mj.group(1), 16), f"{where}/{j + 1}")
                break  # first non-comment line decides: jmp pair or not a tramp


def check_callpads(src: Path) -> None:
    """Cross-bank call pads: ONE live half per bank (split, 2026-10-20 chunk 4).

    F6 contract: a bank0 caller executes `sta $1FFx` at A; the bank switch
    happens on that write, so the NEXT opcode fetch (A+3) already comes from
    the TARGET bank. Only bank0 calls pads (checked below), therefore bank0
    needs the `sta` half alone and the target bank needs the `jmp` half alone;
    the mirror halves were dead bytes. Both halves are pinned here in ROM
    bytes and the jump operand is resolved against the target bank's .lst — a
    wrong pad address or a stale operand is a silent wrong-bank jump.
    """
    banks: dict[int, bytes] = {}
    for idx in (0, 1, 2, 3):
        p = src / f"bank{idx}.bin"
        if not p.exists():
            err(f"bank{idx}.bin missing (callpad check)")
            return
        data = p.read_bytes()
        if len(data) == 4096:
            banks[idx] = data
    if len(banks) != 4:
        return
    labels: dict[int, dict[str, int]] = {}
    for idx in (0, 1, 2, 3):
        lp = src / f"bank{idx}.lst"
        if not lp.exists():
            err(f"bank{idx}.lst missing (callpad label check)")
            return
        labels[idx], _ = parse_lst(lp.read_text(errors="replace").splitlines())

    def at(bank: int, addr: int, n: int) -> bytes:
        return banks[bank][addr - 0xF000:addr - 0xF000 + n]

    # --- ReturnPad: every bank that HAS bodies switches to bank0; bank0
    # serves the `rts`. C3 2026-10-20: bank3 is boot-only (no bodies), so it is
    # no longer expected to carry the pad — 0/1/2 are.
    for idx in (0, 1, 2):
        rp = labels[idx].get("ReturnPad")
        if rp is not None and rp != PAD_LO:
            err(f"bank{idx} ReturnPad ${rp:04X} != ${PAD_LO:04X} (every "
                "bank's body tails jmp $FBF8)")
            continue
        if at(idx, PAD_LO, 3) != bytes([0x8D, 0xF6, 0x1F]):
            err(f"bank{idx} ${PAD_LO:04X} = {at(idx, PAD_LO, 3).hex()} != "
                "sta $1FF6 (8d f6 1f) — `sta` is the whole live half there, "
                "and the bodies reach it by the $FBF8 literal")
    # The `rts` is fetched from bank0 after the `sta`: `sta` preserves
    # A/X/Y/flags/stack, which is what the pad argument pass-through needs.
    if at(0, PAD_LO, 4) != bytes([0x8D, 0xF6, 0x1F, 0x60]):
        err(f"bank0 ReturnPad {at(0, PAD_LO, 4).hex()} != sta $1FF6/rts "
            "(the target banks' bodies rely on bank0's rts at $FBFB)")

    # --- split pads: bank0 `sta` at A, target-bank `jmp` at A+3 --------------
    last_corridor = max((a for _n, a, _t, _l in CORRIDOR_PADS), default=0)
    if last_corridor + 6 > PAD_HI:
        err(f"corridor pads run past ${PAD_HI:04X} (last pad ${last_corridor:04X}"
            ") — they must stay below the $FC49 MothExitPad pin")
    for pad, addr, tbank, target in SPLIT_PADS:
        a0 = labels[0].get(pad)
        if a0 != addr:
            err(f"{pad} at ${a0 if a0 is not None else -1:04X}, expected "
                f"${addr:04X} (pads are packed 3 B apart: A+3 is the "
                "target-bank jmp slot)")
            continue
        want = bytes([0x8D, PAD_BANK_BYTE[tbank], 0x1F])
        got = at(0, a0, 3)
        if got != want:
            err(f"{pad} bank0 ${a0:04X} = {got.hex()} != {want.hex()} "
                "(sta $1FFx) — the bank0 half selects the target bank and must "
                "clobber nothing")
        if at(0, a0 + 3, 1) == b"\x4c":
            err(f"{pad}: bank0 ${a0 + 3:04X} holds a `jmp` — the pad's jmp half "
                "must live in the TARGET bank, where the post-switch fetch "
                "lands (a bank0 copy is a dead byte)")
        tgt = labels[tbank].get(target)
        if tgt is None:
            err(f"{pad}: target {target} not in bank{tbank}.lst")
            continue
        got = at(tbank, a0 + 3, 3)
        want_b = bytes([0x4C, tgt & 0xFF, tgt >> 8])
        if got != want_b:
            err(f"{pad} bank{tbank} ${a0 + 3:04X} = {got.hex()} != "
                f"{want_b.hex()} (jmp {target} ${tgt:04X}, fetched from "
                f"bank{tbank} after the $1FF{'6789'[tbank]} write — stale "
                "operand or an overwritten slot)")

    # --- pinned twin tramps keep both halves (identity guarded elsewhere) ---
    for pad, addr, target in TWIN_PADS:
        a0 = labels[0].get(pad)
        if a0 != addr:
            err(f"{pad} at ${a0 if a0 is not None else -1:04X}, expected "
                f"${addr:04X}")
            continue
        if at(0, a0, 3) != bytes([0x8D, 0xF7, 0x1F]):
            err(f"{pad} bank0 ${a0:04X} = {at(0, a0, 3).hex()} != sta $1FF7")
        tgt = labels[1].get(target)
        if tgt is None:
            err(f"{pad}: target {target} not in bank1.lst")
            continue
        got = at(1, a0 + 3, 3)
        want_b = bytes([0x4C, tgt & 0xFF, tgt >> 8])
        if got != want_b:
            err(f"{pad} bank1 ${a0 + 3:04X} = {got.hex()} != {want_b.hex()} "
                f"(jmp {target} ${tgt:04X})")

    # --- nobody but bank0 may call a pad ------------------------------------
    for idx in (1, 2, 3):
        text = (src / f"bank{idx}.asm").read_text(errors="replace")
        for ln, line in enumerate(text.splitlines(), 1):
            code = line.split(";")[0]
            if re.search(r"\b(jsr|jmp)\s+CallPad_\w+", code):
                err(f"bank{idx}.asm:{ln} calls a pad ({code.strip()}) — pads "
                    "are bank0-entry only: the target bank holds just the jmp "
                    "half, so it has no `sta` half to switch back with")

    ksrc = (src / "kernel.asm").read_text(errors="replace")
    if re.search(r"^CallPad_Overscan:", ksrc, re.M):
        err("CallPad_Overscan is back: it has no caller in any bank (deleted "
            "2026-10-20 with the tail-pad packing)")
    if re.search(r"^CallPad_GetConnIdx:", ksrc, re.M):
        err("CallPad_GetConnIdx is back: C3 moved the exit handlers to bank2 "
            "(LevelConnB2 reads the conn table in-bank), so the pad has no "
            "caller")
    known = {n for n, _a, _t, _l in SPLIT_PADS}
    known |= {n for n, _a, _t in TWIN_PADS}
    for name in sorted(set(re.findall(r"^CallPad_(\w+):", ksrc, re.M))):
        if f"CallPad_{name}" not in known:
            err(f"CallPad_{name} is not declared in verify_build's pad table "
                "(SPLIT_PADS for split halves / TWIN_PADS for pinned tramps) "
                "— add it with its bank0 address and target bank")


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
    # Stomp-zone rule: bank1 HUD writes $E0-$EF every frame (score ptrs +
    # bar temps). Bank0 state that is written ONCE and read across frames
    # must live BELOW $E0 — the S3.2 tentacle bug: rect4.h landed on $E0,
    # scorePtr1's leading-zero lo byte zeroed it every HUD frame, and
    # probes walked through rect4 walls. ColupfBuf ($E7, VBL rebuild) and
    # EnemyRamY ($E2, window-ordered) are the two documented exceptions.
    PERSIST_BELOW_E0 = ("PF0Buf", "PF1Buf", "PF2Buf",
                        "RoomBandColor", "BombX", "BombTimer")
    for name in PERSIST_BELOW_E0:
        v = auth.get(name)
        if v is None:
            err(f"equ-sync: kernel lost persistent var {name} "
                f"(rename/move? update PERSIST_BELOW_E0)")
        elif 0xE0 <= v <= 0xEF:
            err(f"equ-sync: {name} = ${v:02X} is inside bank1's $E0-$EF "
                f"stomp zone — HUD will corrupt it every frame")
    # C4 (2026-10-20): the rect cache is retired — RcBase/RcW1 must not come
    # back as code in any bank (they would silently re-introduce a second
    # collision source next to the PF cells).
    for name in ("RcBase", "RcW1"):
        if auth.get(name) is not None:
            err(f"equ-sync: kernel still declares {name} — the rect cache is "
                f"retired (plan C4); keep the address in ZPSpare89 instead")
    rw1 = auth.get("ZPSpare89")
    if rw1 != 0x89:
        err(f"equ-sync: kernel ZPSpare89 = ${rw1 if rw1 is not None else -1:02X}"
            f" != $89 (the freed rect-count slot must stay allocated)")

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
        if len(row) != 10:
            err(f"{label}: row {li} is {len(row)} chars, expected 10")
        bad = set(row) - set(".,#HPVC")
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
                if model.get("width") != 10 or model.get("height") != 3:
                    err(f"models.json model {model.get('id')}: expected 10x3 geometry")
                if len(model.get("tiles", [])) != 30:
                    err(f"models.json model {model.get('id')}: expected 30 band tiles")
                # Async lives on the ROOM (moved 2026-10-17): a model that
                # still carries asym_patches or P/V/C grid tiles is stale
                # data. RAFT stays a model grid object (row 2 only).
                w = model.get("width") or 10
                if model.get("asym_patches"):
                    err(f"models.json model {model.get('id')}: asym_patches is "
                        "stale — async strips live on the ROOM "
                        "(room.asym_patches); run tools/migrate_async_to_rooms.py")
                stale_feat = sorted({t for t in model.get("tiles", [])
                                     if t in (10, 11, 12)})
                if stale_feat:
                    err(f"models.json model {model.get('id')}: feature tiles "
                        f"{stale_feat} in the grid — feature cells live on the "
                        "ROOM (room.feature_cells); run "
                        "tools/migrate_async_to_rooms.py")
                bad = [i // w for i, t in enumerate(model.get("tiles", []))
                       if t == 6 and i // w != 2]
                if bad:
                    err(f"models.json model {model.get('id')}: RAFT at "
                        f"row(s) {sorted(set(bad))} — must sit in row 2 "
                        "(bottom band, the water strip)")
        except Exception as exc:  # noqa: BLE001 - report, don't crash verifier
            err(f"models.json: {exc}")

    # C5 (2026-10-20) shape + extras cross-check. Async lives on the ROOM and
    # now rides the level's AsyncExtras stream; the shared M<id> SHAPE block is
    # the static hot stream + PF triple ONLY. So:
    #   1. no emitted shape carries the retired meta/right sections;
    #   2. every shape's PF triple equals pf_values(model rows);
    #   3. every AsyncExtras record re-derives, byte for byte, from the JSON
    #      through the same envelope convert uses (an independent gate: the
    #      loader stages MetaA/MetaB and the PF feature cells from it).
    if models:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from convert_level import room_extras, rows_from_json  # noqa: PLC0415
        from convert_room import pf_values  # noqa: PLC0415
        gen_dir = src / "generated"

        mda = (gen_dir / "models_data.asm").read_text() \
            if (gen_dir / "models_data.asm").exists() else ""
        for mid, model in sorted(models.items()):
            tag = f"M{mid}"
            if f"{tag}TilePF0:" not in mda:
                continue                      # model not referenced by any room
            if re.search(rf"^{re.escape(tag)}(MetaA|MetaB|RightPF\d|"
                         rf"RightRects):", mda, re.M):
                err(f"models.json model {mid}: shape block still carries a "
                    "retired meta/right section — C5 moved MetaA/MetaB to the "
                    "level extras and dropped RightPF/RightRects")
            try:
                left = rows_from_json({"model_id": mid}, models)
            except (ValueError, KeyError, TypeError) as exc:
                err(f"models.json model {mid}: {exc}")
                continue
            for reg, name in enumerate(("TilePF0", "TilePF1", "TilePF2")):
                hit = re.search(
                    rf"^{re.escape(tag + name)}:\s*\n\s*\.byte([^\n]+)",
                    mda, re.M)
                if not hit:
                    err(f"models.json model {mid}: {tag}{name} missing")
                    continue
                got = [int(b.strip().lstrip("$"), 16)
                       for b in hit.group(1).split(",")]
                want = [pf_values(r)[reg] for r in left]
                if got != want:
                    err(f"models.json model {mid}: {tag}{name} = {got}, want "
                        f"{want} (PF triple must be the model rows)")

        for jp in sorted(rooms_dir.glob("level_[0-9][0-9][0-9].json")):
            level_n = int(re.search(r"(\d+)", jp.stem).group(1))
            try:
                doc = json.loads(jp.read_text())
            except Exception as exc:  # noqa: BLE001
                err(f"{jp.name}: invalid JSON ({exc})")
                continue
            lvl = doc.get("level", doc)
            rooms = sorted(lvl.get("rooms") or [],
                           key=lambda r: r["room_id"])
            gen = gen_dir / f"level_{level_n:03d}_rooms.asm"
            if not gen.exists():
                err(f"{gen.name}: missing (async extras cross-check)")
                continue
            text = gen.read_text(errors="replace")
            hit = re.search(r"^LEVEL\d+_AsyncExtras:\n((?:  \.byte[^\n]*\n)+)",
                            text, re.M)
            lines = hit.group(1).splitlines() if hit else []
            ordinal = 0
            for index, room in enumerate(rooms):
                if not (room.get("asym_patches") or room.get("feature_cells")):
                    continue
                model = models.get(int(room.get("model_id", -1)))
                if model is None:
                    err(f"{jp.name} room {index}: no model_id (C5 needs a "
                        "shared shape)")
                    continue
                who = f"{jp.name} room {index}"
                try:
                    rows = rows_from_json(room, models)
                    want, _nfeat = room_extras(room, model, rows, who)
                except ValueError as exc:
                    err(f"{who}: {exc}")
                    continue
                if ordinal >= len(lines):
                    err(f"{who}: no AsyncExtras record (owns-extras room must "
                        "carry one)")
                    continue
                payload = lines[ordinal].split(".byte", 1)[1].split(";")[0]
                got = bytes(int(v.strip().lstrip("$"), 16)
                            for v in payload.split(","))
                if got != want:
                    err(f"{who}: AsyncExtras record {got.hex()} != the "
                        f"JSON-derived {want.hex()} (meta/patches/features/"
                        "hot stream drifted from the room data)")
                ordinal += 1
            if ordinal != len(lines):
                err(f"{gen.name}: {len(lines)} AsyncExtras records for "
                    f"{ordinal} async rooms")

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
        # Room count is unlimited: the 8-bit RoomDarkMask (EnemyRamD b4-7 +
        # LaserState b5-2) covers rooms 0-7 only; rooms 8+ simply stay lit
        # (IsRoomDark returns lit, SetRoomDark no-ops — never crashes).

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
                err(f"{name}: miner_x={lvl.get('miner_x')} out of display columns 0..19")
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
            objs = len(enemies) + len(lamps)
            if lvl.get("miner_room") == r.get("room_id"):
                objs += 1
            if objs > 2:
                err(f"{label}: {len(enemies)} enemies + {len(lamps)} lamps"
                    f"{' + miner' if lvl.get('miner_room') == r.get('room_id') else ''}"
                    f" = {objs} objects > 2 "
                    f"(flicker budget: editor kMaxRoomElements=2, 2026-10-02; "
                    f"RAM would still hold 3 slots — slot 3 collides with "
                    f"LaserState at $C0)")

            # Special-feature room rules (user rule 2026-10-14): specials
            # are alone per room; hcrunch owns the sprite slot (no objects
            # at all); door allows a single non-key enemy and no lamp/miner;
            # raft models need water rooms (bottom_band).
            specials = []
            door_model = False
            has_raft = False
            if mid is not None and models and mid in models:
                mdef = models[mid]
                has_raft = any(t == 6 for t in mdef.get("tiles", []))
            if models:
                # Special kinds come from the ROOM's async now.
                try:
                    from convert_level import async_kinds  # noqa: PLC0415
                    specials = async_kinds(r)
                except (ValueError, TypeError, KeyError) as exc:
                    err(f"{label}: {exc}")
                door_model = "door" in specials
            if len(specials) > 1:
                err(f"{label}: room mixes special features "
                    f"{specials} — specials are alone per room "
                    "(door XOR phase XOR hcrunch)")
            if "hcrunch" in specials and objs > 0:
                err(f"{label}: room has hcrunch but room has {objs} "
                    "object(s) (enemies+lamps+miner) — the crunch band needs "
                    "the sprite slot")
            if door_model:
                if len(enemies) > 1:
                    err(f"{label}: door room has {len(enemies)} enemies "
                        "— at most ONE enemy per door room")
                if any(e.get("type", 0) == 6 for e in enemies):
                    err(f"{label}: door room has a KEY enemy — door rooms "
                        "allow a single non-key enemy only")
                if len(lamps) > 0 or (
                        lvl.get("miner_room") == r.get("room_id")):
                    err(f"{label}: door room has a lamp/miner — door rooms "
                        "allow a single enemy only")
            if has_raft and not r.get("bottom_band"):
                err(f"{label}: model {mid} has RAFT tiles but the room is "
                    "not water (bottom_band=false)")

            # C5 (2026-10-20): an async room has NO per-room block any more —
            # its record is cross-checked byte-for-byte against the JSON in the
            # block above (check_level_format parses the stream, this function
            # re-derives it). A belt-and-braces guard here: the room must flip
            # the shape byte's b7 and the count byte's ordinal.
            if models and mid is not None and (
                    r.get("asym_patches") or r.get("feature_cells")):
                rid = r.get("room_id", 0)
                asm = (src / "generated" /
                       f"level_{level_n:03d}_rooms.asm")
                text = asm.read_text() if asm.exists() else ""
                if not re.search(rf"^  \.byte \w+(?: \| \$[0-9a-f]{{2}})? "
                                 rf"; room {rid} \(async extras\)$", text, re.M):
                    err(f"{label}: async room's shape byte is not flagged "
                        "owns-extras (C5 extras stream)")

            # Moving raft (type 7): water rooms only, bottom band only, and
            # the spawn cell must be OPEN water — the same contract convert
            # enforces (plans/raft_moving_plan.md).
            for i, e in enumerate(enemies):
                if int(e.get("type", 0)) != 7:
                    continue
                if not r.get("bottom_band"):
                    err(f"{label} enemy {i}: raft in a room without the "
                        "bottom band (water)")
                if int(float(e.get("y", 0))) // 4 != 2:
                    err(f"{label} enemy {i}: raft at y={e.get('y')} — the "
                        "raft lives on the bottom band (model row 2)")

            for i, e in enumerate(enemies):
                el = f"{label} enemy {i}"
                t = e.get("type", 0)
                if not isinstance(t, int) or t not in (0, 1, 2, 3, 4, 6, 7):
                    err(f"{el}: type={t!r} out of 0..4, 6, 7 (5 = lamp in the "
                        f"merged table, 6 = key, 7 = moving raft)")
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
                # Raft/tentacle water rule (user rule 2026-10-14):
                # tentacles live in the water on the bottom band.
                if t == 3:
                    if not r.get("bottom_band"):
                        err(f"{el}: tentacle in a room without the bottom "
                            "band — tentacles live in the water")
                    try:
                        if int(float(e.get("y", 0))) // 4 != 2:
                            err(f"{el}: tentacle at y={e.get('y')} — "
                                "tentacles live on the bottom band "
                                "(display rows 8-11)")
                    except (TypeError, ValueError):
                        pass  # non-numeric y already reported above

            if lamps and int(r.get("room_id", 0)) >= 8:
                warn(f"{label}: room {r.get('room_id')} has {len(lamps)} "
                     "lamp(s) but the darkness mask covers rooms 0-7 only "
                     "— room stays lit")

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


def sync_kernel_literals(src: Path) -> int:
    """Pre-assembly self-heal (build.sh: after level gen + bank2, before bank0).

    Patches kernel.asm hand-copied literals whose values the assembler bakes
    into bank0 immediates and that move whenever level data changes:
      LEVEL_DATA_ADDR <- bank2.lst LevelDataTable
      LEVEL_COUNT     <- generated/levels.asm
    Safety nets stay: check_frozen_addrs + test_level_bank verify afterwards.
    """
    kernel_p = src / "kernel.asm"
    if not kernel_p.exists():
        print("sync: kernel.asm missing", file=sys.stderr)
        return 1
    text = kernel_p.read_text(encoding="utf-8")
    changed: list[str] = []

    lst2 = src / "bank2.lst"
    if not lst2.exists():
        print("sync: bank2.lst missing — assemble bank2 first", file=sys.stderr)
        return 1
    labels2, _ = parse_lst(lst2.read_text(errors="replace").splitlines())
    got = labels2.get("LevelDataTable")
    if got is None:
        print("sync: LevelDataTable label not in bank2.lst", file=sys.stderr)
        return 1
    m = re.search(r"^LEVEL_DATA_ADDR = \$([0-9A-Fa-f]{4})", text, re.M)
    if not m:
        print("sync: LEVEL_DATA_ADDR literal not found in kernel.asm",
              file=sys.stderr)
        return 1
    if int(m.group(1), 16) != got:
        text = text[:m.start()] + f"LEVEL_DATA_ADDR = ${got:04X}" + text[m.end():]
        changed.append(f"LEVEL_DATA_ADDR ${int(m.group(1), 16):04X} -> ${got:04X}")

    levels_asm = src / "generated" / "levels.asm"
    if levels_asm.exists():
        mg = re.search(r"^LEVEL_COUNT = (\d+)",
                       levels_asm.read_text(encoding="utf-8"), re.M)
        mk = re.search(r"^LEVEL_COUNT\s*=\s*(\d+)", text, re.M)
        if mg and mk and int(mg.group(1)) != int(mk.group(1)):
            text = text[:mk.start()] + f"LEVEL_COUNT    = {mg.group(1)}" + text[mk.end():]
            changed.append(f"LEVEL_COUNT {mk.group(1)} -> {mg.group(1)}")

    if changed:
        kernel_p.write_text(text, encoding="utf-8")
        print("sync: " + "; ".join(changed))
    return 0


def sync_overscan_literal(src: Path) -> int:
    """Post-bank0 self-heal (build.sh: after bank0, before bank1).

    bank1's fold pad ends in `jmp $Fxxx` -> Overscan, which moves whenever
    bank0 pre-pad code shifts. Hand-synced at least 3x (and bit again
    2026-10-05); patch it from bank0.lst instead of by hand.
    """
    lst0 = src / "bank0.lst"
    if not lst0.exists():
        print("sync: bank0.lst missing — assemble bank0 first", file=sys.stderr)
        return 1
    labels0, _ = parse_lst(lst0.read_text(errors="replace").splitlines())
    got = labels0.get("Overscan")
    if got is None:
        print("sync: Overscan label not in bank0.lst", file=sys.stderr)
        return 1
    bank1_p = src / "bank1.asm"
    if not bank1_p.exists():
        print("sync: bank1.asm missing", file=sys.stderr)
        return 1
    text = bank1_p.read_text(encoding="utf-8")
    m = re.search(r"^(    jmp \$)([0-9A-Fa-f]{4})(\s*; Overscan in bank0)",
                  text, re.M)
    if not m:
        print("sync: bank1 Overscan jmp literal not found", file=sys.stderr)
        return 1
    old = int(m.group(2), 16)
    if old != got:
        text = text[:m.start(2)] + f"{got:04X}" + text[m.end(2):]
        bank1_p.write_text(text, encoding="utf-8")
        print(f"sync: bank1 jmp Overscan ${old:04X} -> ${got:04X}")
    # (The CallPad_Overscan twin that used to be patched here was deleted
    # 2026-10-20 with the tail-pad packing: it had no caller in any bank.)
    return 0


def sync_phrec_literal(src: Path) -> int:
    """Post-bank2 self-heal (build.sh: before dasm bank3).

    bank3's return-tail tramps `jmp $Fxxx ; .PhRec (vcrunch/hcrunch)` track
    bank2's .PhRec label, which moves whenever the feature-record stream
    (model tiles / level data) shifts. Hand-synced twice on 2026-10-13 and
    stale again after each data edit — same family as bank1's Overscan
    literal; patch from bank2.lst instead of by hand.
    """
    lst2 = src / "bank2.lst"
    if not lst2.exists():
        print("sync: bank2.lst missing — assemble bank2 first", file=sys.stderr)
        return 1
    m = re.search(r"^\s*\d+\s+([0-9a-f]{4})\s+\.PhRec\s*$",
                  lst2.read_text(errors="replace"), re.M)
    if not m:
        print("sync: .PhRec label not in bank2.lst", file=sys.stderr)
        return 1
    got = int(m.group(1), 16)
    bank3_p = src / "bank3.asm"
    if not bank3_p.exists():
        print("sync: bank3.asm missing", file=sys.stderr)
        return 1
    text = bank3_p.read_text(encoding="utf-8")
    pat = re.compile(r"^(    jmp \$)([0-9A-Fa-f]{4})(\s*; \.PhRec)", re.M)
    hits = list(pat.finditer(text))
    if len(hits) != 2:
        print(f"sync: expected 2 bank3 .PhRec jmp literals, found {len(hits)}",
              file=sys.stderr)
        return 1
    new = text
    for hit in reversed(hits):
        old = int(hit.group(2), 16)
        if old != got:
            new = new[:hit.start(2)] + f"{got:04X}" + new[hit.end(2):]
            print(f"sync: bank3 jmp .PhRec ${old:04X} -> ${got:04X}")
    if new != text:
        bank3_p.write_text(new, encoding="utf-8")
    return 0


def data_size(path: Path) -> int:
    """Bytes a generated pure-data .asm contributes (.byte=1B/op, .word=2B/op)."""
    n = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(";")[0].strip()
        if line.startswith(".byte"):
            n += len([o for o in line[5:].split(",") if o.strip()])
        elif line.startswith(".word"):
            n += 2 * len([o for o in line[5:].split(",") if o.strip()])
        elif line.startswith((".ds", ".org", "echo")):
            warn(f"{path.name}: non-data directive {line!r} — size may be off")
    return n


def bank2_data_slots(bank2: str) -> list[dict]:
    """Data slots (bugs.md 27): include-blocks terminated by a pad
    `.ds $ADDR - *, 0`. Returns [{pad, files, org}] where org is the exact
    slot start: the nearest literal `org $X` above the block, or the
    `.ds $X - *, 0` pad that opens it (same semantics — both set PC to X), or
    None (then slot_start falls back to the block's first label)."""
    lines = bank2.splitlines()
    slots = []
    for i, raw in enumerate(lines):
        m = re.match(r"\s*\.ds\s+\$([0-9A-Fa-f]+)\s+-\s+\*\s*,\s*0", raw)
        if not m:
            continue
        files, j = [], i - 1
        while j >= 0:
            s = lines[j].strip()
            if not s or s.startswith(";"):
                j -= 1
                continue
            mi = re.match(r'include\s+"([^"]+)"', s)
            if mi:
                files.insert(0, mi.group(1))
                j -= 1
                continue
            break
        if not files:
            continue
        org = None
        k = j
        while k >= 0:
            s = lines[k].strip()
            if not s or s.startswith(";"):
                k -= 1
                continue
            mo = (re.match(r"org\s+\$([0-9A-Fa-f]+)", s)
                  or re.match(r"\.ds\s+\$([0-9A-Fa-f]+)\s+-\s+\*\s*,\s*0", s))
            if mo:
                org = int(mo.group(1), 16)
            break
        slots.append({"pad": int(m.group(1), 16), "files": files, "org": org})
    return slots


def flatten_includes(files: list[str], src: Path, depth: int = 0) -> list[str]:
    """#27b: spill_*.asm files are include-lists — expand to data files
    (recursive; generated data files never contain includes themselves)."""
    out: list[str] = []
    for f in files:
        p = src / f
        nested: list[str] = []
        if depth < 3 and p.exists():
            for raw in p.read_text(encoding="utf-8").splitlines():
                mi = re.match(r'\s*include\s+"([^"]+)"', raw)
                if mi:
                    nested.append(mi.group(1))
        if nested:
            out += flatten_includes(nested, src, depth + 1)
        else:
            out.append(f)
    return out


def slot_start(slot: dict, labels: dict[str, int], src: Path) -> tuple[int | None, str]:
    if slot["org"] is not None:
        return slot["org"], "org literal"
    p = src / slot["files"][0]
    if not p.exists():
        return None, f"{slot['files'][0]} missing"
    for raw in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", raw.split(";")[0].strip())
        if m:
            addr = labels.get(m.group(1))
            if addr is None:
                return None, f"label {m.group(1)} not in bank2.lst"
            return addr, m.group(1)
    return None, f"no label in {p.name}"


def check_level_window(src: Path) -> None:
    """--precheck (build.sh, before dasm bank2): fit generated level/model
    blocks into bank2's data slots. Fails early with the placement map
    instead of DASM's cryptic `Origin Reverse-indexed` at the pad line.
    Slot starts: `org` literal (exact) or first label of the block in
    bank2.lst (from the last successful build — exact while bank2 code
    is unchanged, which holds for the JSON-only growth that overflows)."""
    bank2_p = src / "bank2.asm"
    if not bank2_p.exists():
        err("bank2.asm not found")
        return
    labels: dict[str, int] = {}
    lst = src / "bank2.lst"
    if lst.exists():
        labels, _ = parse_lst(lst.read_text(errors="replace").splitlines())
    slots = bank2_data_slots(bank2_p.read_text(encoding="utf-8"))
    if not slots:
        err("no include-block data slots found in bank2.asm")
        return
    print("window fit map (bank2 data slots):")
    for s in slots:
        s["files"] = flatten_includes(s["files"], src)   # #27b spill lists
        sizes, missing = [], False
        for f in s["files"]:
            p = src / f
            if not p.exists():
                err(f"slot ${s['pad']:04X}: {f} missing — run convert_level first")
                missing = True
                continue
            sizes.append((f, data_size(p)))
        if missing:
            continue
        used = sum(sz for _, sz in sizes)
        start, how = slot_start(s, labels, src)
        if start is None:
            if used == 0:
                continue                      # #27b empty spill slot — no gate
            warn(f"slot ${s['pad']:04X}: start unknown ({how}) — gate skipped, "
                 f"used {used}B")
            continue
        cap = s["pad"] - start
        slack = cap - used
        detail = ", ".join(f"{Path(f).name} {sz}B" for f, sz in sizes)
        flag = "" if slack >= 0 else "  <-- OVERFLOW"
        print(f"  ${start:04X}..${s['pad']:04X}  used {used}/{cap}B  "
              f"slack {slack}B  [{detail}]{flag}")
        if slack < 0:
            err(f"slot ${s['pad']:04X} overflows: {used}B > {cap}B "
                f"(start ${start:04X} via {how}) — move data to another gap "
                f"or trim; see map above")
        elif slack < 8:
            warn(f"slot ${s['pad']:04X} nearly full: slack {slack}B")


def sync_hof_literal(src: Path) -> int:
    """Post-bank2 self-heal (build.sh: after dasm bank2, before bank0).

    kernel.asm's `HotOverlapFlag` pad ends in `jmp $Fxxx` -> bank2's
    HotOverlapBody. That body moves whenever bank2 code above it shifts, and
    the operand is a hand-copied literal in bank0's last 6 bytes (bank2's own
    $FFEF image is a label, so it self-heals). Patch it from bank2.lst.

    C2 (2026-10-20): replaces --sync-bank3-labels. The block-label export
    (generated/bank3_labels.asm) retired when the level data moved into bank2 —
    bank2 now defines those labels itself; CallPad_BuildColupF's image is a
    label too, so this is the only literal left. Size-preserving: only the 4
    hex digits change, so bank0's addresses are unaffected.
    """
    lst2 = src / "bank2.lst"
    if not lst2.exists():
        print("sync-hof: bank2.lst missing — assemble bank2 first",
              file=sys.stderr)
        return 1
    labels, _ = parse_lst(lst2.read_text(errors="replace").splitlines())
    addr = labels.get("HotOverlapBody")
    if addr is None:
        print("sync-hof: HotOverlapBody label not in bank2.lst",
              file=sys.stderr)
        return 1
    kernel_p = src / "kernel.asm"
    text = kernel_p.read_text(encoding="utf-8")
    pat = re.compile(
        r"(^HotOverlapFlag:\s*\n(?:[^\n]*\n){0,3}?\s*jmp \$)"
        r"([0-9A-Fa-f]{4})", re.M)

    def repl(m):
        old = int(m.group(2), 16)
        if old != addr:
            print(f"sync-hof: kernel.asm HotOverlapFlag ${old:04X} -> "
                  f"${addr:04X}")
        return m.group(1) + f"{addr:04X}"

    text, k = pat.subn(repl, text, count=1)
    if not k:
        print("sync-hof: kernel.asm HotOverlapFlag pad not found",
              file=sys.stderr)
        return 1
    kernel_p.write_text(text, encoding="utf-8")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--sync":
        src = (Path(argv[1]) if len(argv) > 1
               else Path(__file__).resolve().parent.parent / "src")
        return sync_kernel_literals(src)
    if argv and argv[0] == "--sync-overscan":
        src = (Path(argv[1]) if len(argv) > 1
               else Path(__file__).resolve().parent.parent / "src")
        return sync_overscan_literal(src)
    if argv and argv[0] == "--sync-phrec":
        src = (Path(argv[1]) if len(argv) > 1
               else Path(__file__).resolve().parent.parent / "src")
        return sync_phrec_literal(src)
    if argv and argv[0] == "--sync-hof":
        src = (Path(argv[1]) if len(argv) > 1
               else Path(__file__).resolve().parent.parent / "src")
        return sync_hof_literal(src)
    if argv and argv[0] == "--precheck":
        src = (Path(argv[1]) if len(argv) > 1
               else Path(__file__).resolve().parent.parent / "src")
        check_level_window(src)
        for w in WARNS:
            print(f"  WARN: {w}")
        for e in ERRORS:
            print(f"  ERROR: {e}")
        if ERRORS:
            print(f"window precheck: FAILED ({len(ERRORS)} error(s))")
            return 1
        print("window precheck: OK")
        return 0
    src = (Path(argv[0]) if argv
           else Path(__file__).resolve().parent.parent / "src")
    check_rom(src)
    check_fold_block(src)
    check_moth_tramp(src)
    check_frame_tramp(src)
    check_raft_tramp(src)
    check_boot_banks(src)
    check_live_stage(src)
    check_enterroom_tramp(src)
    check_blast_tramp(src)
    check_loadlevel_tramp(src)
    check_exit_handlers(src)
    check_level_format(src)
    check_tramp_targets(src)
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
