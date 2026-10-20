#!/usr/bin/env python3
"""Guard the merged title screen: logo + credits over the live stage (2026-10-19).

Design: one title state (DropTarget = $FF).  Band 0 is drawn by the REAL cave
kernel (stage PF + COLUPF from the room buffers, player via PlayerColTable /
Grp0Ptr), so the title does not duplicate the band rendering.  The bank0
row-advance tail diverts to bank1's TitleBand right where band 1 would start;
TitleBand writes band 1's stage row + the S.A.V.I.O.R. logo + the credit
footer, then band 2's row + 48 lines, then the HUD band (jmp MenuMain), so the
score shows level+1 while the title is up.  No object is drawn: DropArm
.DATitle clears EnemyCount/LevelMinerRoom on every title LoadLevel, so
SelectActiveObject parks GRP1.  SELECT cycles the level, RESET starts the
game; the theme plays on $FF.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
SOURCES = ("kernel.asm", "bank1.asm", "bank2.asm", "bank3.asm")


def section(source: str, start: str, end: str) -> str:
    first = source.index(start)
    last = source.index(end, first)
    return source[first:last]


for name in SOURCES:
    source = (SRC / name).read_text()
    assert "Demo" not in source, f"intro demo code remains in {name}"

kernel = (SRC / "kernel.asm").read_text()
bank1 = (SRC / "bank1.asm").read_text()
bank2 = (SRC / "bank2.asm").read_text()

# --- one $FF title state: boot, DropStep and the return path ---------------
assert "TitleIntro:" not in kernel, "retired splash handler came back"
for dead in ("TitleSequenceFold:", "FooterFold:", "TitlePlayerFold:"):
    assert dead not in kernel, f"dead fold {dead} came back"
drop = section(kernel, "DropStep:", ".DSfall:")
assert "cmp #$FF\n    beq TitleWork" in drop, \
    "DropStep must route $FF to TitleWork (merged title)"
ret = section(kernel, "RefreshEnemyY:", ".REYRts:")
assert "lda #$FF" in ret and "sta DropTarget" in ret, \
    "gameplay return-to-title must use the $FF sentinel"
assert "lda #$FF\n    sta DropTarget" in kernel

# --- no duplicated title kernel: KernelInit runs the cave for $FF too -----
init = section(kernel, "KernelInit:", "DropSpeedTable")
assert ".TkPath" not in init and "TitleKernel" not in init, \
    "KernelInit must NOT branch to a title kernel (band 0 is the cave's)"
assert "sta RowIdx" in init and "sbc RoomY" in init

# --- the row-advance tail hook: band 0 -> TitleBand on $FF ----------------
adv = section(kernel, "Advance to next tile row", ".GrpSkip")
assert "lda DropTarget" in adv and "cmp #$FF" in adv, \
    "row advance must test the title sentinel"
assert "jmp CallPad_TitleBand" in adv, \
    "row advance must divert $FF to bank1 TitleBand (band 1)"
assert "bne .Row" in adv, "gameplay must still advance to .Row"

# --- band 0 is the CAVE kernel: player sprite via Grp0Ptr -----------------
cave = section(kernel, "CaveKernelRow:", ".Grp1")
assert "lda (Grp0Ptr),Y" in cave and "sta GRP0" in cave, \
    "band 0 must draw the player from the cave kernel"

# --- TitleBand: band 1 + band 2 from the stage buffers, logo, footer, HUD -
title = section(bank1, "TitleBand:", "TitleFont:")
for row in ("PF0Buf+1", "PF1Buf+1", "ColupfBuf+1", "PF2Buf+1", "BandTab+1",
            "PF0Buf+2", "PF1Buf+2", "ColupfBuf+2", "PF2Buf+2", "BandTab+2"):
    assert f"lda {row}" in title, f"TitleBand must draw the stage from {row}"
assert "lda PF0Buf\n" not in title and "PF0Buf+0" not in title, \
    "band 0 belongs to the cave kernel — TitleBand must not redraw it"
assert "lda (Grp0Ptr),Y" not in title and "PlayerWalk" not in bank1, \
    "the title player is the cave kernel's (no bank1 player copy)"
assert "jsr SetObjectXPos_b1" in title and "sta HMOVE" in title
assert "lda #<(TitleFont+40)" in title and "sta TPtr6" in title, \
    "6 logo slots"
assert ".TkLoop:" in title, "logo draw loop"
assert "jsr FooterBand" in title, "credit footer over the stage"
assert "jmp MenuMain" in title, "HUD band follows the title (score = level+1)"
assert ".LDigitLoop" not in title, "digits band was retired with the black screen"

# --- the title pad reuses the old slot (same 6 bytes, retargeted) ---------
for src, name in ((kernel, "kernel"), (bank1, "bank1")):
    assert "CallPad_TitleBand:" in src, f"{name} missing CallPad_TitleBand"
    assert "CallPad_TitleKernel:" not in src, \
        f"{name} still carries the retired TitleKernel pad"
assert ".ds $FC55 - *, 0" in kernel and "jmp $F080" in kernel

# --- no object on the title: DropArm .DATitle hides the GRP1 slots --------
title_arm = section(kernel, ".DATitle:", "DropStep:")
assert "sta EnemyCount" in title_arm and "sta LevelMinerRoom" in title_arm, \
    "title LoadLevel must clear the object slots (no enemy on the title)"
assert "sta LaserState" in title_arm, "title must clear the laser gate"

# --- retired machinery stays retired ---------------------------------------
for dead in ("TitlePlayerBand", "TitleBandPrep", "TitleJetColors",
             "TitleBombSprite", "TitleBlinkColors"):
    assert f"{dead}:" not in bank1, f"{dead} should be gone (merged title)"
assert "TitleSequence:" not in bank2, "intro movie must be gone"

# --- logo font + credit font ----------------------------------------------
font = section(bank1, "TitleFont:", "FooterBand:")
assert font.count(".byte") == 48, "TitleFont must stay 6 slots x 8 rows"
assert "FooterFont:" in bank1
footer = section(bank1, "FooterBand:", "FooterFont:")
assert "ldx #13" in footer and "lda #<(FooterFont+70)" in footer

# --- music still ticks on title frames ------------------------------------
tail = section(kernel, "TitleTailAudio:", ".TWwait:")
assert "cmp #$FF" in tail and "jsr CallPad_MusicTick" in tail, \
    "music must tick on $FF title frames"
assert "MusicTick:" in bank1 and "MusicMel:" in bank1

# --- PickPlayerFrame moved to bank0 (repack chunk 1) ----------------------
assert "TitleJetSprite:" not in bank2, "bank2 art twin must be gone"
assert "PickPlayerFrame:" in kernel, "frame picker body must live in bank0"

print("test_title_demo: OK (cave band 0 + TitleBand logo/credits/HUD)")
