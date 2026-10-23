#!/usr/bin/env python3
"""Cave VDEL contract (Phase 4, 2026-10-22).

The cave enables VDELP0 and leaves VDELP1 off. That is NOT the HUD's 13+2
cross-buffer usage — it is the only way this kernel can render the player's
per-row colours on the same scanline as the art, and it is x-dependent, so the
exact bits and the latching contract are load-bearing:

1. VDEL is not a plain one-line delay. Stella (`Player::grp`,
   `Player::updatePattern`, `Player::shufflePatterns`): a GRP write lands in
   `myPatternNew` and renders immediately; with VDEL the live pattern is
   `myPatternOld`, which is latched when the OTHER player is written. So the
   cave's landing point for GRP0 moves from GRP0's own store (measured c35 by
   `tools/cycle_ledger.py`, correct art only for X < 44 px) to the GRP1 store
   (c58 → X < 113 px) — and PlayerColTable[row] then lands on the same
   scanline as the art row, because COLUP0 is stored at c19, before every
   sprite pixel.

2. That ONLY works while `.Line` writes GRP1 on every path: the in-window
   path (.Grp1) and the blank path (.ObjNoRes). If a path ever returns to
   .Line without a GRP1 store, P0's latch stalls and the player freezes at the
   last latched row — a silent renderer hang, so it is asserted here.

3. P1 must stay immediate: with VDELP1=1 its latch would be GRP0's c35 store
   (a WORSE split than its own c58) while its colour stays at c65.

Reads the FROZEN bank images + kernel.asm (source-level contract).
Run: /home/iuri/python3/bin/python3 tools/test_vdel_cave.py
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
FROZEN = SRC / "tests" / "frozen"

# lda #1 / sta VDELP0 / lda #0 / sta VDELP1 / sta ENABL  (cave VBL init)
WANT = bytes([0xA9, 0x01, 0x85, 0x25, 0xA9, 0x00, 0x85, 0x26, 0x85, 0x1F])


def fail(msg):
    sys.exit(f"FAIL: {msg}")


bank0 = (FROZEN / "bank0.bin").read_bytes()
if len(bank0) != 4096:
    fail(f"frozen/bank0.bin is {len(bank0)} B, expected 4096")

hits = [i for i in range(len(bank0)) if bank0.startswith(WANT, i)]
if len(hits) != 1:
    fail(f"cave VDEL init (VDELP0=1 / VDELP1=0) found {len(hits)}x in "
         f"frozen/bank0.bin, expected exactly 1 — the cave must enable P0 "
         "VDEL and keep P1 immediate (see the .Line comment)")

K = (SRC / "kernel.asm").read_text(errors="replace")

# --- every .Line path must store GRP1 (P0's latch driver) --------------------
body = K.split(".Grp1:")[1].split(".AfterObj:")[0]
if "sta GRP1" not in body:
    fail(".Grp1 in-window path lost its `sta GRP1` — P0's VDEL latch would "
         "stall and the player would freeze at the last latched row")
blank = K.split(".ObjNoRes:")[1].split(".AfterRows:")[0]
if "sta GRP1" not in blank:
    fail(".ObjNoRes (out-of-window blank) lost its `sta GRP1` — same stall")

# --- the player colour must be stored before the graphics ------------------
line_body = K.split(".Line:", 1)[1].split(".AfterObj:")[0]
i_col = line_body.find("sta COLUP0")
i_grp = line_body.find("sta GRP0")
if i_col < 0 or i_grp < 0:
    fail(".Line must store COLUP0 and GRP0")
if i_col > i_grp:
    fail("COLUP0 is stored after GRP0 — the per-row colour would land on the "
         "wrong scanline for every sprite (measured c19 vs c35)")

# --- the HUD's own VDEL usage stays untouched -----------------------------
b1 = (SRC / "bank1.asm").read_text(errors="replace")
if "VDELP1" not in b1 or b1.count("sta VDELP1") < 2:
    fail("bank1's HUD VDELP1 usage disappeared — the 48px score pipeline "
         "needs it and it is independent of the cave's P0 bit")

# --- the line ABOVE the sprite must write art row 0 -----------------------
# With VDELP0 the pattern displayed on the sprite's first line is the one
# written on the scanline before it, so `.GrpSkip` must fetch row 0 on the
# A0=$ff line instead of blanking. Blanking it ate the art's top row (user
# report 2026-10-22: the helmet's narrow first row never appeared).
kern = (SRC / "kernel.asm").read_text(errors="replace")
skip = kern.split(".GrpSkip:")[1].split(".GrpZero:")[0]
if "lda (Grp0Ptr),Y" not in skip:
    fail(".GrpSkip does not write art row 0 on the A0=$ff line — the player's "
         "top row would be blanked and the sprite would draw one row short")
if "bne .GrpZero" not in skip:
    fail(".GrpSkip must still blank every skipped line except the one above "
         "the sprite (bne .GrpZero)")

print("OK: cave VDELP0=1 / VDELP1=0, GRP1 stored on every .Line path, "
      "COLUP0 ahead of GRP0, HUD VDELP1 intact, art row 0 on the line above "
      "the sprite")
