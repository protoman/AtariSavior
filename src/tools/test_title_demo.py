#!/usr/bin/env python3
"""Guard the merged title screen: logo + credits over the live stage (2026-10-19).

Design: one title state (DropTarget = $FF).  The TitleKernel draws the stage
itself — the room's three PF rows from the buffers EnterRoom staged, plus the
player — and overlays the S.A.V.I.O.R. logo and the credit footer.  The HUD
band follows (jmp MenuMain), so the score shows level+1 while the title is up.
SELECT cycles the level, RESET starts the game; the theme plays on $FF.
"""
from pathlib import Path
import re

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
init = section(kernel, "KernelInit:", "CallPad_TitleKernel")
assert "cmp #$FF\n    beq .TkPath" in init, "KernelInit must divert $FF to TitleKernel"
ret = section(kernel, "RefreshEnemyY:", ".REYRts:")
assert "lda #$FF" in ret and "sta DropTarget" in ret, \
    "gameplay return-to-title must use the $FF sentinel"
assert "lda #$FF\n    sta DropTarget" in kernel

# --- TitleKernel: stage PF rows + player + logo + credits + HUD -----------
title = section(bank1, "TitleKernel:", "TitleFont:")
for row in ("PF0Buf", "PF1Buf", "ColupfBuf", "PF2Buf", "BandTab"):
    assert f"lda {row}" in title, f"title must draw the stage from {row}"
assert "PF0Buf+1" in title and "PF0Buf+2" in title, "all three stage rows"
assert "lda #<PlayerWalkA" in title and "lda (Grp0Ptr),Y" in title, \
    "title must draw the player over the stage"
assert "jsr SetObjectXPos_b1" in title and "sta HMOVE" in title
assert "lda #<TitleFont" in title and "sta TPtr6" in title, "6 logo slots"
assert ".TkLoop:" in title, "logo draw loop"
assert "jsr FooterBand" in title, "credit footer over the stage"
assert "jmp MenuMain" in title, "HUD band follows the title (score = level+1)"
assert ".LDigitLoop" not in title, "digits band was retired with the black screen"

# --- retired machinery stays retired ---------------------------------------
for dead in ("TitlePlayerBand", "TitleBandPrep", "TitleJetColors",
             "TitleBombSprite", "TitleBlinkColors"):
    assert f"{dead}:" not in bank1, f"{dead} should be gone (merged title)"
assert "TitleSequence:" not in bank2, "intro movie must be gone"
# LV001 HUD banner removed 2026-10-19 (merged title shows the level in the
# score): no arming in LoadLevel, no banner branch / L,V glyphs in bank1.
assert "LevelShowTimer" not in kernel and "LevelShowTimer" not in bank1, \
    "retired LV001 banner came back (LevelShowTimer still referenced)"
assert "LV_SHOW_FRAMES" not in kernel, "retired LV001 banner constant came back"

# --- logo font + credit font + bank1 player art ---------------------------
font = section(bank1, "TitleFont:", "FooterBand:")
assert font.count(".byte") == 48, "TitleFont must stay 6 slots x 8 rows"
assert "FooterFont:" in bank1
footer = section(bank1, "FooterBand:", "FooterFont:")
assert "ldx #13" in footer and "lda #<FooterFont+70" in footer
art = section(bank1, "PlayerWalkA:", ".ds $F080")
assert art.count(".byte") == 24, "bank1 player art (walk A/B) must be present"

# --- music still ticks on title frames ------------------------------------
tail = section(kernel, "TitleTailAudio:", ".TWwait:")
assert "cmp #$FF" in tail and "jsr CallPad_MusicTick" in tail, \
    "music must tick on $FF title frames"
assert "MusicTick:" in bank1 and "MusicMel:" in bank1

# --- bank2 keeps the PlayerSpriteA twin (PickPlayerFrame reads it) --------
assert "TitleJetSprite:" in bank2, "bank2 art twin must stay"
sprite = section(bank2, "TitleJetSprite:", "; --- Level-data spill 2")
assert sprite.count(".byte") == 6, "twin art is 24 B (6 rows x 4)"

print("test_title_demo: OK (merged title: stage + logo + credits + HUD score)")
