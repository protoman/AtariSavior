#!/usr/bin/env python3
"""Guard the merged title screen (2026-10-19).

One screen replaces the old two-step flow (intro splash $FD -> old title $FF):
the TitleKernel draws the SAVIOR logo, a two-digit level-number band, the
credit footer line, and the theme plays there.  SELECT cycles the level,
RESET starts the game.  This test pins that design and the retired machinery
(no movie, no player band, no second title sentinel).
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

# --- merged routing: ONE $FD title sentinel, TitleWork owns SELECT/RESET ----
assert "TitleIntro:" not in kernel, "retired splash handler came back"
for dead in ("TitleSequenceFold:", "FooterFold:", "TitlePlayerFold:"):
    assert dead not in kernel, f"dead fold {dead} came back"
drop = section(kernel, "DropStep:", ".DSfall:")
assert "cmp #$FD\n    beq TitleWork" in drop, \
    "DropStep must route $FD to TitleWork (merged title)"
assert "$FF" not in drop
ret = section(kernel, "RefreshEnemyY:", ".REYRts:")
assert "lda #$FD" in ret and "sta DropTarget" in ret, \
    "gameplay return-to-title must use the $FD sentinel"
assert "lda #$FF\n    sta DropTarget" not in kernel, \
    "old $FF title sentinel still written"

# --- TitleKernel: logo + level digits + credits on the fixed line budget ----
title = section(bank1, "TitleKernel:", "TitleFont:")
assert title.count("jsr SetObjectXPos_b1") == 6, \
    "entry logo pair + digits pair + footer pair"
assert "lda #<TitleFont" in title and "sta TPtr6" in title, "6 logo slots"
assert "lda Level\n    clc\n    adc #1" in title, "level number must be 1-based"
assert "sta TPtr2" in title and "sta TPtr1" in title
assert "lda #>DigitGfx" in title and ".LDigitLoop:" in title
assert "dey\n    bpl .LDigitLoop" in title, "8-row digit loop"
assert "ldx #157" in title, "line budget: logo+pad (player band retired)"
assert "ldx #31" in title and ".TkPostFooterPad:" in title
assert "jsr FooterBand" in title and "jmp CallPad_Overscan" in title
assert "bne .TkFooterPad" in title

# --- retired machinery stays retired ---------------------------------------
for dead in ("TitlePlayerBand", "TitleBandPrep", "TitleJetColors",
             "TitleBombSprite", "TitleBlinkColors"):
    assert f"{dead}:" not in bank1, f"{dead} should be gone (merged title)"
    assert f"jsr {dead}" not in bank1 and f"jmp {dead}" not in bank1
assert "TitleSequenceFold:" not in kernel, "intro fold came back"
assert "TitleSequence:" not in bank2, "intro movie came back"

# --- logo font (6 x 8) + credits footer ------------------------------------
font = section(bank1, "TitleFont:", "FooterBand:")
assert font.count(".byte") == 48, "TitleFont must stay 6 slots x 8 rows"
assert "FooterFont:" in bank1, "credit font must stay"
footer = section(bank1, "FooterBand:", "FooterFont:")
assert "ldx #13" in footer, "13-row footer loop"
assert "lda #<FooterFont+70" in footer, "6 footer slots x 14 B"

# --- music still plays on the merged title ---------------------------------
tail = section(kernel, "TitleTailAudio:", ".TWwait:")
assert "cmp #$FD" in tail and "jsr CallPad_MusicTick" in tail, \
    "music must tick on $FD title frames"
assert "MusicTick:" in bank1 and "MusicMel:" in bank1

# --- bank2 keeps the PlayerSpriteA twin (PickPlayerFrame reads it) ---------
assert "TitleJetSprite:" in bank2, "bank2 art twin must stay"
sprite = section(bank2, "TitleJetSprite:", "; --- Level-data spill 2")
assert sprite.count(".byte") == 6, "twin art is 24 B (6 rows x 4)"

print("test_title_demo: OK (merged title: logo + level digits + credits + music)")
