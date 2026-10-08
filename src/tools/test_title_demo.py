#!/usr/bin/env python3
"""Guard the title's animated game-sprite flight and fixed line budget."""

from pathlib import Path
import re


SRC = Path(__file__).resolve().parent.parent
SOURCES = ("kernel.asm", "bank2.asm", "bank3.asm")


def section(source, start, end):
    first = source.index(start)
    last = source.index(end, first)
    return source[first:last]


for name in SOURCES:
    source = (SRC / name).read_text()
    assert "Demo" not in source, f"intro demo code remains in {name}"

kernel = (SRC / "kernel.asm").read_text()
assert "TitleKernel:" in kernel
assert "FooterFold:" in kernel
assert "TitleIntro:" in kernel
assert "jsr DropArm" in kernel

title = kernel[kernel.index("TitleKernel:"):kernel.index("TitleFont:")]
assert "ldx #105" in title
assert "cpx #40" in title
assert "ldx #38" in title
assert ".TkPostFooterPad:" in title
assert title.count("jsr SetObjectXPos") == 4
assert "sta NUSIZ0" in title
player = section((SRC / "bank2.asm").read_text(),
                 "TitlePlayerBand:", "TitleJetSprite:")
bank2 = (SRC / "bank2.asm").read_text()
assert "lda EnemyRamP\n    and #4" in player
assert "lda (Grp0Ptr),Y" in player
assert "sta Grp0Ptr\n    sty Grp0PtrHi" in player
assert "lda TitleJetSprite,X" not in player
assert "lda TitleJetColors,Y" in player
assert "ldx #60" in player
assert "ldy #0\n    sta WSYNC" in player
assert "lda LineCount\n    beq .TitleJetDraw" in player
assert "cpy #12" in player
assert "sta VDELP0\n    sta VDELP1" in player
assert player.count("sta GRP0") == 7
assert player.count("sta GRP1") == 4
assert "sta WSYNC\n    jmp $FBF8" in player
assert "sta HMP1" in title
assert "bne .TkFooterPad" in title
assert "lda #60\n    ldx #0\n    jsr SetObjectXPos" in title
assert "lda #20\n    sta RoomX" in kernel
assert "lda #0\n    sta RoomY" in kernel

intro = section(kernel, "TitleIntro:", "FooterFold:")
assert "lda LevelStartX\n    sta RoomX" in intro
assert "lda LevelStartY\n    sta RoomY" in intro

game_frame_a = section(kernel, "PlayerSpriteA:", "PlayerSpriteB:")
game_frame_b = section(kernel, "PlayerSpriteB:", "PlayerColTable:")
jet_copy = section(bank2, "TitleJetSprite:", "TitleJetColors:")
copied_frames = re.findall(r"%[01]{8}", jet_copy)
game_frames = re.findall(r"%[01]{8}", game_frame_a + game_frame_b)
assert len(copied_frames) == 24
assert copied_frames == game_frames
game_colors = section(kernel, "PlayerColTable:", "; --- Level data")
title_colors = section(bank2, "TitleJetColors:", ".ds $F970 - *, 0")
color_values = {
    name: int(value, 16)
    for name, value in re.findall(
        r"^(COLOR_P_[A-Z]+)\s*=\s*\$([0-9A-Fa-f]+)", kernel, re.MULTILINE
    )
}
game_color_names = re.findall(r"COLOR_P_[A-Z]+", game_colors)
copied_color_values = [
    int(value, 16)
    for value in re.findall(r"\$([0-9A-Fa-f]{2})", title_colors)
]
assert copied_color_values == [color_values[name] for name in game_color_names]

positions = []
x, y = 20, 0
for _ in range(200):
    positions.append((x, y))
    if x < 140:
        x += 1
    elif y < 48:
        y += 1
assert positions[0] == (20, 0)
assert positions[120] == (140, 0)
assert positions[168] == (140, 48)
assert positions[199] == (140, 48)
assert {frame & 4 for frame in range(16)} == {0, 4}

kernel_pad = section(kernel, "TitlePlayerFold:", ".ds $FBF8 - *, 0")
bank2_pad = section(bank2, ".ds $FBE8 - *, 0", ".ds $FBF8 - *, 0")
assert "sta $1FF8\n    jmp $F880" in kernel_pad
assert "sta $1FF8\n    jmp TitlePlayerBand" in bank2_pad

print("Title player sprite and fixed line-budget guards passed.")
