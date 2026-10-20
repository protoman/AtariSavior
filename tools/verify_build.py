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
  Models - solid-rect count <= 5 per model (ZP rect cache; EnterRoom copies
          5 but RcBase keeps the raw count -> walker reads $E0+ garbage).
  EQU   - cross-bank `Name = $XX` sync vs kernel authority (S3.0); allows
          documented aliases (ZP_ALLOW: bank1 Temp = $AD).
  Frozen - LEVEL_DATA_ADDR literal == bank2.lst LevelDataTable (models_data
           regeneration shifts bank2 labels; stale literal = empty rect cache).
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
# Tally entry tramp — same pattern: `sta $1FF8` at $FFE6 (after BeamMask,
# fetch at $FFE9 from bank2 = `jmp TallyEntry`). Ends $FFEB so $FFF2-$FFF9
# (F6 hotspot mirrors) stay fill.
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
    for idx in (0, 2, 3):
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

    # HOF tramp ($FFEC, A3) — bank0 runs `sta $1FF9`, the opcode+operand are
    # fetched from BANK3's image at +3 ($FFEF).
    hoff = HOF_ENTRY - 0xF000
    g0 = banks[0][hoff:hoff + 6]
    g3 = banks[3][hoff + 3:hoff + 6]
    if g0[:3] != bytes([0x8D, 0xF9, 0x1F]):
        err(f"bank0 HOF entry ${HOF_ENTRY:04X} = {g0.hex()} "
            "(expected 8df91f + jmp)")
    if len(g3) != 3 or g3[0] != 0x4C:
        err(f"bank3 HOF image ${HOF_ENTRY + 3:04X} = {g3.hex()} "
            "(expected jmp image)")
    labels3, _ = parse_lst((src / "bank3.lst").read_text(
        errors="replace").splitlines())
    hof = labels3.get("HotOverlapBody")
    hof_tgt = (g3[1] | (g3[2] << 8)) if len(g3) == 3 else None
    if hof is None:
        err("HotOverlapBody label not found in bank3.lst")
    elif hof_tgt != hof:
        err(f"HOF entry jmp ${hof_tgt if hof_tgt is not None else 0:04X} != "
            f"bank3 HotOverlapBody ${hof:04X} (tramp operand stale)")
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
    # bank0/bank2 + operand == bank2 TallyEntry + label pin (kernel jsrs).
    yoff = TALLY_ENTRY - 0xF000
    y0 = banks[0][yoff:yoff + 6]
    y2 = banks[2][yoff:yoff + 6]
    if y0[:3] != MOTH_STA18:
        err(f"bank0 tally entry ${TALLY_ENTRY:04X} = {y0.hex()} "
            f"(expected {MOTH_STA18.hex()} + jmp)")
    if y0 != y2:
        err(f"tally entry bank0[${TALLY_ENTRY:04X}] {y0.hex()} != bank2 "
            f"{y2.hex()} (byte-identity broken)")
    tally = labels2.get("TallyEntry")
    tally_tgt = (y0[4] | (y0[5] << 8)) if len(y0) == 6 else None
    if tally is None:
        err("TallyEntry label not found in bank2.lst")
    elif tally_tgt != tally:
        err(f"tally entry jmp ${tally_tgt if tally_tgt is not None else 0:04X} "
            f"!= bank2 TallyEntry ${tally:04X} (tramp operand stale)")
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


# Cross-bank call pads (leaf_move_plan): ReturnPad + CallPads must be
# byte-identical in bank0/bank1 (first 5 bytes fetched pre-switch, jmp/pla/
# rts post-switch), and every CallPad jmp literal must equal the bank1 label.
PAD_LO, PAD_HI = 0xFBF8, 0xFC49   # inclusive start, exclusive end (FC48 last)



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


def check_tramp_targets(src: Path) -> None:
    """Generic: every `sta $1FFx` + `jmp $Fxxx` pair must land on a
    destination-bank listing row start (label/instruction/data start).

    Catches the stale-operand class generally: a 1-byte-wrong jmp operand
    lands between rows, like 2026-10-10 ($FD6B vs BombEnemyBlastBody
    $FD6A). Comment text is stripped first so prose mentioning tramps
    (e.g. bank1's $F937 pin comments) cannot false-positive. bank3.lst
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
    labels3: dict[str, int] = {}
    for idx, out in ((0, "labels0"), (1, "labels1"), (2, "labels2"),
                     (3, "labels3")):
        lp = src / f"bank{idx}.lst"
        if not lp.exists():
            err(f"bank{idx}.lst missing (callpad label check)")
            return
        labs, _ = parse_lst(lp.read_text(errors="replace").splitlines())
        if idx == 0:
            labels0 = labs
        elif idx == 1:
            labels1 = labs
        elif idx == 2:
            labels2 = labs
        else:
            labels3 = labs
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
        # stream lives in bank2); `sta $1FF7` pads jump to bank1; `sta $1FF6`
        # pads are bank1->bank0 tail exits (e.g. CallPad_Overscan -> Overscan).
        if "sta $1FF8" in body:
            tgt_labs, tgt_side = labels2, "bank2"
        elif "sta $1FF9" in body:
            tgt_labs, tgt_side = labels3, "bank3"   # A3: level-data walkers
        elif "sta $1FF6" in body:
            tgt_labs, tgt_side = labels0, "bank0"
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
    # Stomp-zone rule: bank1 HUD writes $E0-$EF every frame (score ptrs +
    # bar temps). Bank0 state that is written ONCE and read across frames
    # must live BELOW $E0 — the S3.2 tentacle bug: rect4.h landed on $E0,
    # scorePtr1's leading-zero lo byte zeroed it every HUD frame, and
    # probes walked through rect4 walls. ColupfBuf ($E7, VBL rebuild) and
    # EnemyRamY ($E2, window-ordered) are the two documented exceptions.
    PERSIST_BELOW_E0 = ("RcBase", "RcW1", "PF0Buf", "PF1Buf", "PF2Buf",
                        "RoomBandColor", "BombX", "BombTimer")
    for name in PERSIST_BELOW_E0:
        v = auth.get(name)
        if v is None:
            err(f"equ-sync: kernel lost persistent var {name} "
                f"(rename/move? update PERSIST_BELOW_E0)")
        elif 0xE0 <= v <= 0xEF:
            err(f"equ-sync: {name} = ${v:02X} is inside bank1's $E0-$EF "
                f"stomp zone — HUD will corrupt it every frame")
    rw1 = auth.get("RcW1")
    if rw1 is not None and rw1 + 20 > 0xE0:   # exclusive end ≤ $E0 → last byte ≤ $DF
        err(f"equ-sync: rect cache RcW1=${rw1:02X} spans to "
            f"${rw1 + 19:02X} — rect bytes would sit in the "
            f"bank1 stomp zone (tentacle-wall bug family)")

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

    # Async-meta guards (2026-10-17): async lives on the ROOM, so every MODEL
    # block is static (MetaA $00, MetaB $00 | $40 hot) and each room that owns
    # async has its own L<level>R<room> block. Both are cross-checked against
    # the SAME envelope convert uses (independent gate at verify time): meta
    # bytes at TilePF0+9/+10, right rows stride 3, ball x = 87+8*right_col,
    # right-rect budget. The block's own text is passed in, so the model and
    # per-room paths cannot diverge.
    block_checks = None
    if models:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from convert_level import (resolve_asym_patches, rows_from_json,  # noqa: PLC0415
                                   room_feature_cells, room_m1_door_flag)
        from convert_room import pf_values  # noqa: PLC0415
        gen_dir = src / "generated"

        def meta_byte(text: str, tag: str, label: str):
            hit = re.search(
                rf"^{re.escape(tag + label)}:\s*\n\s*\.byte\s+\$?([0-9a-fA-F]+)",
                text, re.M)
            return int(hit.group(1), 16) if hit else None

        def block_checks(tag: str, text: str, model: dict, room: dict,
                         left: list[str], who: str) -> None:
            """Meta + right-half cross-check for one emitted block."""
            try:
                res = resolve_asym_patches(model, room, left)
            except ValueError as exc:
                err(f"{who}: {exc}")
                return
            asym, ball_x, m1_x, _door, m1_right = (
                res if res else (None, 0, 0, False, False))
            band_mask = 0
            if asym is not None:
                for bidx in range(3):
                    if asym[bidx] != left[bidx][::-1]:
                        band_mask |= 1 << bidx
            m1n = ((m1_x - 7) >> 3) + 1 if m1_x else 0
            want_a = (m1n << 4) | band_mask
            if room_m1_door_flag(room):
                want_a |= 0x08
            if m1_right:
                want_a |= 0x01
            got_a = meta_byte(text, tag, "MetaA")
            if got_a is None:
                err(f"{who}: {tag}MetaA missing (must sit at TilePF0+9)")
            elif got_a != want_a:
                err(f"{who}: MetaA=${got_a:02X}, want ${want_a:02X} "
                    f"((m1_col+1)<<4 | band_mask=${band_mask:02X}"
                    f"{' | $08 door' if room_m1_door_flag(room) else ''})")
            ball_n = ((ball_x - 87) >> 3) + 1 if ball_x else 0
            if model.get("mid_band_type"):
                ball_n |= 0x40            # hot band (touch-kill semantics)
            got_b = meta_byte(text, tag, "MetaB")
            if got_b is None:
                err(f"{who}: {tag}MetaB missing (must sit at TilePF0+10)")
            elif got_b != ball_n:
                err(f"{who}: MetaB=${got_b:02X}, want ${ball_n:02X} "
                    "(ball_col+1 | $80 door | $40 hot, 0 = no ball)")
            if asym is None:
                if re.search(rf"^{re.escape(tag)}RightPF\d:", text, re.M):
                    err(f"{who}: symmetric but RightPF block emitted")
                return
            if f"{tag}RightPF0:" not in text:
                err(f"{who}: asym block missing RightPF")
                return
            for reg in range(3):
                label = f"{tag}RightPF{reg}"
                hit = re.search(
                    rf"^{re.escape(label)}:\s*\n\s*\.byte([^\n]+)", text, re.M)
                if not hit:
                    err(f"{who}: {label} missing")
                    continue
                got = [int(b.strip().lstrip("$"), 16)
                       for b in hit.group(1).split(",")]
                want = [pf_values(r[::-1])[reg] for r in asym]
                if got != want:
                    err(f"{who}: {label} = {got}, want {want} (stride 3)")
            hit = re.search(
                rf"^{re.escape(tag)}RightRects:\s*\n\s*\.byte\s+(\d+)", text, re.M)
            if not hit:
                err(f"{who}: {tag}RightRects missing")
            elif int(hit.group(1)) > 4:
                err(f"{who}: {hit.group(1)} right rects > WallMask budget 4")

        mda = (gen_dir / "models_data.asm").read_text() \
            if (gen_dir / "models_data.asm").exists() else ""
        for mid, model in sorted(models.items()):
            tag = f"M{mid}"
            if f"{tag}TilePF0:" not in mda:
                continue                      # model not referenced by any room
            try:
                left = rows_from_json({"model_id": mid}, models)
            except (ValueError, KeyError, TypeError) as exc:
                err(f"models.json model {mid}: {exc}")
                continue
            block_checks(tag, mda, model, {}, left, f"models.json model {mid}")

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
            if block_checks is not None:
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

            # A room that owns async must have its own emitted block, and its
            # meta/right rows are cross-checked here (paths relative to src/).
            if block_checks is not None and mid is not None \
                    and models and mid in models:
                try:
                    has_async = bool(r.get("asym_patches")
                                     or r.get("feature_cells"))
                except AttributeError:
                    has_async = False
                if has_async:
                    rid = r.get("room_id", 0)
                    # A3: per-room blocks are emitted into level_00N_blocks.asm
                    # (included from bank3); the table file keeps only tables.
                    asm = src / "generated" / f"level_{level_n:03d}_blocks.asm"
                    text = asm.read_text() if asm.exists() else ""
                    tag = f"L{level_n}R{rid + 1}"
                    if f"{tag}TilePF0:" not in text:
                        # C1 (2026-10-20): a byte-identical block owned by
                        # another level's room is emitted ONCE; the duplicate
                        # carries a note and its table points at the survivor.
                        # Cross-check the survivor's bytes against THIS room's
                        # expected meta/right rows — same bytes, so a stale
                        # note cannot hide a mismatch.
                        hit = re.search(
                            rf"^;\s*({re.escape(tag)}) block SHARED with "
                            rf"(L\d+R\d+)\b", text, re.M)
                        shared_text = None
                        if hit:
                            for other in sorted(
                                    (src / "generated").glob(
                                        "level_[0-9][0-9][0-9]_blocks.asm")):
                                body = other.read_text()
                                if f"{hit.group(2)}TilePF0:" in body:
                                    shared_text = body
                                    break
                        if not hit:
                            err(f"{label}: room owns async but no {tag} block "
                                f"was emitted ({asm.name})")
                        elif shared_text is None:
                            err(f"{label}: {tag} claims to share "
                                f"{hit.group(2)} but no such block exists")
                        else:
                            try:
                                left = rows_from_json(r, models)
                            except (ValueError, KeyError, TypeError) as exc:
                                err(f"{label}: {exc}")
                            else:
                                block_checks(hit.group(2), shared_text,
                                             models[mid], r, left, label)
                    else:
                        try:
                            left = rows_from_json(r, models)
                        except (ValueError, KeyError, TypeError) as exc:
                            err(f"{label}: {exc}")
                        else:
                            block_checks(tag, text, models[mid], r, left, label)

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


def check_model_rects(src: Path) -> None:
    """Every model's solid-rect count must fit the game's ZP rect cache.

    The cache is 5 uniform slots ($CC-$DF, walk Y=0..19). EnterRoom copies
    exactly 5 rects but stores the RAW count in RcBase — a 6-rect model
    loses its last rect (no collision under it) AND the walker's 6th
    iteration reads $E0+ (bank1 scorePtr garbage) as a phantom rect.
    Seen 2026-10-02: level_003 room 3 / model 6 needed 6 rects for its
    geometry; the player fell through the bottom band.
    """
    mp = src / "rooms" / "models" / "models.json"
    if not mp.exists():
        return
    try:
        md = json.loads(mp.read_text())
    except ValueError as exc:
        err(f"models.json: {exc}")
        return
    ml = md.get("models_file", md).get("models", [])
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from convert_level import rows_from_json          # noqa: PLC0415
    from convert_room import find_rectangles          # noqa: PLC0415
    by_id = {m.get("id"): m for m in ml}
    for m in ml:
        try:
            rows = rows_from_json({"model_id": m.get("id")}, by_id)
        except (KeyError, TypeError, ValueError) as exc:
            err(f"model {m.get('id')}: {exc}")
            continue
        rects = find_rectangles(rows, solids="#")
        if len(rects) > 5:
            # Transition (cell_collision_plan): >5 rects only SAFE once every
            # cache walker is cell-based (PHM 2.1, LWC 3.1, moth 4.1, bombs 5.x).
            # During the swap this stays a WARN so sims/battery can gate each
            # step; the whole check dies at phase 7.1 (rect cache retired).
            warn(f"model {m.get('id')}: {len(rects)} wall rects > 5 — "
                 f"cell-swap must cover all cache walkers before release; "
                 f"rects={rects}")


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
    # The CallPad twin block is byte-identical in bank0 and bank1: patch both
    # pads' CallPad_Overscan operand (every byte before the pad moves with
    # bank0 code, and the two pads must point at the same address).
    for label, path in (("kernel", src / "kernel.asm"),
                        ("bank1", bank1_p)):
        if not path.exists():
            print(f"sync: {path.name} missing", file=sys.stderr)
            return 1
        txt = path.read_text(encoding="utf-8")
        pm = re.search(r"(CallPad_Overscan:\s*\n\s*sta \$1FF6\s*\n\s*jmp \$)"
                       r"([0-9A-Fa-f]{4})", txt)
        if not pm:
            print(f"sync: {label} CallPad_Overscan literal not found",
                  file=sys.stderr)
            return 1
        pold = int(pm.group(2), 16)
        if pold != got:
            txt = txt[:pm.start(2)] + f"{got:04X}" + txt[pm.end(2):]
            path.write_text(txt, encoding="utf-8")
            print(f"sync: {label} CallPad_Overscan ${pold:04X} -> ${got:04X}")
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
    `.ds $ADDR - *, 0`. Returns [{pad, files, org}] where org is the
    nearest literal `org $X` above the block (exact start) or None."""
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
            mo = re.match(r"org\s+\$([0-9A-Fa-f]+)", s)
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


def sync_bank3_labels(src: Path) -> int:
    """Post-bank3-pass1 (build.sh): export block labels + self-heal pads.

    A3 (2026-10-19): the level data (shared model blocks + per-room blocks)
    lives in bank3. bank2's room TABLES still need those labels as plain
    absolute addresses, so pass 1 of bank3 is assembled, its labels are
    exported into generated/bank3_labels.asm (included by bank2), and the
    `jmp` literals of the two pads whose bodies moved to bank3 are patched
    (kernel/bank1/bank2 `CallPad_BuildColupF`, kernel/bank2 `HotOverlapFlag`).
    Size-preserving: only the 4 hex digits change, so pass 2's addresses are
    identical to pass 1's.
    """
    lst3 = src / "bank3.lst"
    if not lst3.exists():
        print("sync-bank3: bank3.lst missing — assemble bank3 pass 1 first",
              file=sys.stderr)
        return 1
    labels, _ = parse_lst(lst3.read_text(errors="replace").splitlines())
    block = re.compile(r"^(M\d+|L\d+R\d+)(TilePF[0-2]|RoomRects|Meta[AB]|"
                       r"RightPF[0-2]|RightRects)$")
    lines = ["; Generated by verify_build.py --sync-bank3-labels. Do not edit.",
             "; bank3 level-data block labels (absolute addresses for bank2's",
             "; room tables)."]
    n = 0
    for name in sorted(labels):
        if block.match(name):
            lines.append(f"{name} = ${labels[name]:04X}")
            n += 1
    if not n:
        print("sync-bank3: no block labels found in bank3.lst", file=sys.stderr)
        return 1
    (src / "generated" / "bank3_labels.asm").write_text("\n".join(lines) + "\n")
    print(f"sync-bank3: exported {n} block labels -> generated/bank3_labels.asm")

    targets = {"CallPad_BuildColupF": ("BuildColupF",
                                        ("kernel.asm", "bank1.asm", "bank2.asm")),
               "HotOverlapFlag": ("HotOverlapBody",
                                  ("kernel.asm", "bank2.asm"))}
    for fname in ("kernel.asm", "bank1.asm", "bank2.asm"):
        p = src / fname
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        orig = text
        for pad, (label, files) in targets.items():
            if fname not in files:
                continue
            addr = labels.get(label)
            if addr is None:
                err(f"bank3.lst: {label} label missing (pad {pad})")
                return 1
            pat = re.compile(
                rf"(^{re.escape(pad)}:\s*\n(?:[^\n]*\n){{0,3}}?\s*jmp \$)"
                rf"([0-9A-Fa-f]{{4}})", re.M)
            def repl(m, addr=addr, pad=pad, fname=fname):
                old = int(m.group(2), 16)
                if old != addr:
                    print(f"sync-bank3: {fname} {pad} ${old:04X} -> "
                          f"${addr:04X}")
                return m.group(1) + f"{addr:04X}"
            text, k = pat.subn(repl, text, count=1)
            if not k:
                err(f"{fname}: {pad} pad not found (sync-bank3)")
                return 1
        if text != orig:
            p.write_text(text, encoding="utf-8")
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
    if argv and argv[0] == "--sync-bank3-labels":
        src = (Path(argv[1]) if len(argv) > 1
               else Path(__file__).resolve().parent.parent / "src")
        return sync_bank3_labels(src)
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
    check_tramp_targets(src)
    check_callpads(src)
    check_levels(src)
    check_model_rects(src)
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
