#!/usr/bin/env python3
"""Level-bank fold static checks (level_bank_plan P1; assert-based).

Source-shape contract for the cross-bank fold (HERO fold, write-triggered):

  - FoldIndirect block exists in kernel.asm AND bank2.asm with exactly the
    four contracted instructions in order (sta $1FF8 / lda (FetchPtr),Y /
    sta $1FF6 / rts) — hand-edited drift in one bank breaks execution at
    the switch point. P3.1: bank select absolute (X preserved; was
    sta $1FF8,X).
  - FetchPtr = $E0 defined in both files (operand is baked per file).
  - kernel.asm: block sits right before `.ds $FF00 - *, 0` (margin directive
    to the $FF00 fineAdjust anchor — an assembler error, not silent growth).
  - bank2.asm: `.ds $FEF6 - *, 0` pins the block to the same address.
  - bank1.asm rebuilds scorePtr1 ($E0/$E1) every HUD frame, so bank0 must
    stage FetchPtr before every fold batch (contract §0.2 — staging is
    enforced when fold call sites land in P2/P3; here we just pin the
    writers that make the alias family real).

Bin-level byte-identity + label addresses are guarded by verify_build.py
(check_fold_block) — run this test after ./build.sh for full coverage.

Run: python3 tools/test_level_bank.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = (ROOT / "src" / "kernel.asm").read_text(encoding="utf-8")
BANK2 = (ROOT / "src" / "bank2.asm").read_text(encoding="utf-8")
BANK1 = (ROOT / "src" / "bank1.asm").read_text(encoding="utf-8")
BANK2 = (ROOT / "src" / "bank2.asm").read_text(encoding="utf-8")

BLOCK = [
    "sta $1FF8",
    "lda (FetchPtr),Y",
    "sta $1FF6",
    "rts",
]


def block_body(src: str, label: str) -> list[str]:
    """Instruction lines from `label:` until a non-instruction line."""
    m = re.search(rf"^{label}:\s*$(.*?)(?=^\S|\Z)", src, re.M | re.S)
    assert m, f"{label} label not found"
    body = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith(".ds"):
            if body:  # block ends at first blank/comment after instructions
                break
            continue
        body.append(line)
    return body


def main() -> None:
    # --- block shape, both banks ------------------------------------------
    for name, src in (("kernel.asm", KERNEL), ("bank2.asm", BANK2)):
        body = block_body(src, "FoldIndirect")
        assert body == BLOCK, \
            f"{name}: FoldIndirect body {body} != contract {BLOCK}"

    # --- FetchPtr operand, both files (moved $E0→$E5 in S3.2) --------------
    for name, src in (("kernel.asm", KERNEL), ("bank2.asm", BANK2)):
        m = re.search(r"^FetchPtr\s*=\s*\$E5\b", src, re.M)
        assert m, f"{name}: FetchPtr = $E5 definition missing"

    # --- address pinning ---------------------------------------------------
    assert re.search(r"FoldIndirect:.*?\.ds \$FF00 - \*, 0", KERNEL, re.S), \
        "kernel.asm: block must be followed by the .ds $FF00 margin directive"
    assert re.search(r"\.ds \$FEF6 - \*, 0\s*\nFoldIndirect:", BANK2), \
        "bank2.asm: .ds $FEF6 must pin the block to bank0's address"

    # --- P1.3: FetchPtr ($E5/$E6) partition + stage-before-batch ----------
    # S3.2: FetchPtr moved $E0→$E5 (frees $E0 = rect4.h in the cache); it
    # now sits under bank1 scorePtr3-hi/scorePtr4-lo — same time partition:
    # bank0 stages only inside VBL/overscan batches, bank1 rebuilds in HUD.
    assert "sta scorePtr3+1" in BANK1 and "sta scorePtr4" in BANK1, \
        "bank1 must rebuild scorePtr3+1/scorePtr4 — FetchPtr partition pair"
    # kernel must not write FetchPtr's bytes raw (only via the EQU) and
    # must not raw-write $E0 (now a rect cache byte — writes go RcBase,Y)
    assert not re.search(r"sta\s+\$E5\b", KERNEL), \
        "kernel.asm writes $E5 raw — use the FetchPtr EQU for alias clarity"
    assert not re.search(r"sta\s+\$E0\b", KERNEL), \
        "kernel.asm writes $E0 raw — rect cache byte, write via RcBase,Y"

    # --- P2/P3.1: no direct reads of relocated tables ----------------------
    for tbl in ("LevelPFDataLo", "LevelEnemyLo", "LevelConnLo", "EnemyDataLo"):
        assert not re.search(rf"lda \({tbl}\),Y", KERNEL), \
            f"kernel.asm still reads ({tbl}),Y directly — route via FoldIndirect"
    # #22: EnterRoom moved to bank2 (direct (ptr),Y reads — it IS the reader),
    # so its 11 fold call sites + 10 stage lines left kernel with it.
    # was 30: the snake's symmetric patrol (2026-10-19) dropped its two ROM-dir
    # reads; then the redundant VBL band-color fold left (EnterRoom stages it),
    # so 27. S4 (2026-10-19) dropped the two start_x/start_y table fields,
    # so 25. C4 (2026-10-20) dropped the two derived pointer words from the
    # per-level entry (4 reads), so 21. The 2026-10-20 micro-pack dropped
    # start_room + miner_y from the entry (2 reads), so 20. C1 (2026-10-20)
    # moved SelectActiveObject to bank2 (2 sites: lit + dark reloads), so 18.
    assert KERNEL.count("jsr FoldIndirect") >= 18, \
        f"expected >=18 fold call sites (conn/LoadLevel + P3.1 enemy " \
        f"derives; EnterRoom + SelectActiveObject folds moved to bank2 " \
        f"direct reads), got {KERNEL.count('jsr FoldIndirect')}"
    # every fold batch stages FetchPtr immediately before its reads
    # C1 (2026-10-20): SelectActiveObject's staging pair (EnemyDataLo/Hi ->
    # FetchPtr) left with the body to bank2, which reads (EnemyDataLo),Y
    # directly: 10 -> 8.
    stages = len(re.findall(r"^\s+sta FetchPtr\+?1?\s*$", KERNEL, re.M))
    assert stages >= 8, \
        f"expected >=8 sta FetchPtr lines, got {stages}"

    # --- P2.5: band-color cache contract ----------------------------------
    # FIX 2026-09-28: was $D1 = PF1Buf[2] — collides with kernel .Row
    # `lda PF1Buf,X` (X=2); band color rendered as the bottom-band PF1 wall
    # pattern (phase_1: $D1=00 vs model $ff → mid-wall gap). $D2 = dead row.
    assert re.search(r"^RoomBandColor\s*=\s*\$BC\b", KERNEL, re.M), \
        "RoomBandColor = $BC (own byte since S3.1; was $D2 = PF1Buf[3] alias)"
    assert not re.search(r"^RoomBandColor\s*=\s*\$D1\b", KERNEL, re.M), \
        "RoomBandColor must not alias PF1Buf[2] ($D1) — kernel reads it"
    assert "lda RoomBandColor" in KERNEL, \
        "kernel/overscan must read the VBLANK-staged cache (inlined)"
    # 2026-10-19: the per-frame VBL re-read of the band color was redundant
    # (EnterRoomB2 restages it on every room entry since the 2026-10-04 fix),
    # so the ONLY writer is the room loader now.
    assert "sta RoomBandColor" not in KERNEL, \
        "kernel.asm must not re-read the band color every VBL (redundant)"
    assert "sta RoomBandColor" in BANK2, \
        "EnterRoomB2 must stage RoomBandColor (the only writer)"
    assert "jsr LoadRoomBottomColor" not in KERNEL, \
        "LoadRoomBottomColor was inlined (S1.5) — reads go direct"

    # --- LEVEL_COUNT hand-copy stays in sync with generated data -----------
    gen = (ROOT / "src" / "generated" / "levels.asm").read_text(
        encoding="utf-8")
    n_levels = len(re.findall(r"^\s*\.word\s+LEVEL\d+_RoomDataTable",
                              gen, re.M))
    m = re.search(r"^LEVEL_COUNT\s*=\s*(\d+)", KERNEL, re.M)
    assert m and int(m.group(1)) == n_levels, \
        f"LEVEL_COUNT = {m and m.group(1)} != {n_levels} generated levels"

    # --- frozen data address: hand-copy matches bank2 listing --------------
    lst = (ROOT / "src" / "bank2.lst").read_text(encoding="utf-8")
    m = re.search(r"^\s+\d+\s+([0-9a-f]{4})\s+LevelDataTable\b", lst, re.M)
    assert m, "LevelDataTable not found in bank2.lst"
    m2 = re.search(r"^LEVEL_DATA_ADDR\s*=\s*\$([0-9A-Fa-f]{4})", KERNEL, re.M)
    assert m2 and m2.group(1).lower() == m.group(1), \
        f"LEVEL_DATA_ADDR ${m2 and m2.group(1)} != " \
        f"bank2 LevelDataTable ${m.group(1)}"

    # --- C2/C3/C4 (2026-10-20) + the 2026-10-20 micro-pack ----------------
    # The readers hardcode the block layout: RoomDataTable (2 B/room),
    # RoomConnections (2 B/room), RoomEnemies (1 B/room), EnemyDataTable
    # (4 B/record). The per-level entry is 4 scalars + base word + room count,
    # and the Connections/RoomEnemies/enemy-record bases are the block's
    # +2n / +4n / +5n offsets, so the emission order IS the contract.
    index = (ROOT / "src" / "generated" / "levels_index.asm").read_text(
        encoding="utf-8")
    assert "LEVEL_DATA_STRIDE = 7" in index, (
        "level index stride is not the 7-byte layout (kernel LoadLevel "
        "computes Level*7; start_room and miner_y are kernel constants)")
    assert "  .word LEVEL" in index and "  .byte " in index
    entries = re.findall(r"^\s*\.byte (LEVEL(\d+)_MINER_ROOM), "
                         r"LEVEL\2_MINER_X, LEVEL\2_WALL_COLOR, "
                         r"LEVEL\2_WALL_COLOR2\n"
                         r"\s*\.word (LEVEL\2_RoomDataTable)\n"
                         r"\s*\.byte (\d+) ;", index, re.M)
    assert len(entries) == n_levels, (
        f"level index has {len(entries)} 7-byte entries, want {n_levels} "
        "(miner room/x + 2 wall colors + base word + room count)")
    assert "LEVEL1_START_ROOM," not in index and "MINER_Y," not in index, (
        "start_room / miner_y must not be emitted into the entry (kernel "
        "constants 0 / 84; convert_level rejects other values)")
    # one bottom-band COLOR for the game — bank2 reads the emitted EQU
    equ = (ROOT / "src" / "generated" / "levels_equ.asm").read_text()
    m = re.search(r"^BAND_COLOR = \$([0-9a-f]{2})", equ, re.M)
    assert m, "generated/levels_equ.asm must define BAND_COLOR"
    assert 'include "generated/levels_equ.asm"' in BANK2, (
        "bank2.asm must include generated/levels_equ.asm (BAND_COLOR) BEFORE "
        "EnterRoomB2 uses it")
    for _ml, n, _rd, rooms in entries:
        rooms = int(rooms)
        text = (ROOT / "src" / "generated" / f"level_{int(n):03d}_rooms.asm"
                ).read_text(encoding="utf-8")
        pos = {k: text.index(f"{k}:") for k in (
            f"LEVEL{n}_RoomDataTable", f"LEVEL{n}_RoomConnections",
            f"LEVEL{n}_RoomEnemies", f"LEVEL{n}_EnemyDataTable")}
        assert (pos[f"LEVEL{n}_RoomDataTable"] < pos[f"LEVEL{n}_RoomConnections"]
                < pos[f"LEVEL{n}_RoomEnemies"]
                < pos[f"LEVEL{n}_EnemyDataTable"]), (
            f"LEVEL{n}: block order must be RoomData/Conn/RoomEnemies/"
            f"EnemyData — the readers use +2n/+4n/+5n offsets")
        chunk = text[pos[f"LEVEL{n}_RoomDataTable"]:pos[f"LEVEL{n}_EnemyDataTable"]]
        assert chunk.count("  .word ") == rooms, (
            f"LEVEL{n}: RoomDataTable must be ONE word per room (C3)")
        # Connections: 2 bytes/room; RoomEnemies: ONE byte/room (2026-10-20)
        assert chunk.count("  .byte ") == 2 * rooms, (
            f"LEVEL{n}: one Connections line (2 B) + one RoomEnemies line "
            f"(1 B) per room — got {chunk.count('  .byte ')} for "
            f"{rooms} rooms")
        enemies = text[pos[f"LEVEL{n}_RoomEnemies"]:
                       pos[f"LEVEL{n}_EnemyDataTable"]]
        goals = re.findall(r"^  \.byte \$([0-9a-f]{2}) ; room (\d+)", enemies, re.M)
        assert len(goals) == rooms, f"LEVEL{n}: RoomEnemies record count"
        prev = 0
        for hexv, room in goals:
            packed = int(hexv, 16)
            count, first = packed >> 6, (packed >> 1) & 0x1F
            assert count <= 3, (
                f"LEVEL{n} room {room}: count {count} > 3 (b7-6)")
            assert first == prev, (
                f"LEVEL{n} room {room}: packed first index {first} != {prev} "
                f"(records must stay contiguous in room order)")
            prev += count
        records = text[pos[f"LEVEL{n}_EnemyDataTable"]:].count("  .byte ")
        assert records == prev, (
            f"LEVEL{n}: EnemyDataTable has {records} records but the packed "
            f"indices account for {prev} (4 B/record)")
        # the bottom-band FLAG is b0 only; the color is the global EQU
        for hexv, _room in goals:
            if int(hexv, 16) & 0x01:
                assert int(hexv, 16) >> 6 <= 3

    print("test_level_bank: all asserts passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
