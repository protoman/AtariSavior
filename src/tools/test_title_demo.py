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
assert "ldx #103" in title
assert "cpx #40" in title
assert "ldx #37" in title
assert ".TkPostFooterPad:" in title
assert title.count("jsr SetObjectXPos") == 6
assert "sta NUSIZ0" in title
bank2 = (SRC / "bank2.asm").read_text()
player = section(bank2, "TitlePlayerBand:", "TitleJetSprite:")
prep = section(bank2, "TitleBandPrep:", "    .ds $F700")
# frame pick / mirror / bomb colors live in TitleBandPrep (band calls it)
assert "jsr TitleBandPrep" in player
assert "lda EnemyRamP\n    and #4" in prep          # jet flutter gate
assert "lda #<PlayerWalkA" in prep and "lda #<PlayerWalkB" in prep
assert "sta Grp0Ptr\n    sty Grp0PtrHi" in prep
assert prep.count("    asl") == 3 and "sta REFP0" in prep  # bit3 mirror
assert "cmp #8" in prep and "beq .TBpJet" in prep     # climb uses flutter frames
assert "sta COLUP1" in prep and "sta COLUBK" in prep  # fuse / explosion
assert "TitleBlinkColors" in prep
assert prep.rstrip().endswith("rts")
assert "lda (Grp0Ptr),Y" in player
assert "lda TitleJetSprite,X" not in player
assert "lda TitleJetColors,Y" in player
assert "ldx #60" in player
assert "ldy #0\n    sta WSYNC" in player
assert "lda LineCount\n    beq .TitleJetDraw" in player
assert "cpy #12" in player
assert "lda TitleBombSprite,Y" in player
assert "sta COLUBK" in player and "sta REFP0" in player  # tail restore
assert "sta VDELP0\n    sta VDELP1" in player
assert player.count("sta GRP0") == 7
assert player.count("sta GRP1") == 5   # 4 clears + bomb row
assert "sta WSYNC\n    jmp $FBF8" in player
assert "sta HMP1" not in title
assert "sta NUSIZ1" in title
assert "bne .TkFooterPad" in title
assert "lda #60\n    ldx #0\n    jsr SetObjectXPos" in title
assert "lda #20\n    sta RoomX" in kernel    # TitleIntro spawn init
assert "lda #0\n    sta RoomY" in kernel
bomb_rows = [int(v, 16) for v in re.findall(
    r"\$([0-9A-Fa-f]{2})", section(bank2, "TitleBombSprite:", "TitleBlinkColors:"))]
assert bomb_rows[-8:] == [0x10, 0x20, 0x20, 0x60, 0xF0, 0xF0, 0xF0, 0x60]
blink = re.findall(
    r"COLOR_[A-Z_]+", section(bank2, "TitleBlinkColors:", ".ds $F880"))
assert blink == ["COLOR_CAVE_BG", "COLOR_HOT_Y", "COLOR_HOT_R", "COLOR_HOT_Y"]

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

# --- TitleSequence contract sim (mirrors bank2.asm TitleSequence) ---
# fly 20->140 / drop 0->48 / face left / arm fuse 180 / walk ->76 /
# wait fuse+explode (machine-owned, BombTick gated off on titles) /
# walk ->20 / own the 240-frame pause / reset loop.
def simulate(frames=1600):
    roomx, roomy, player_dir = 20, 0, 0
    ticks = 0
    packed = 0          # bits 0-1 = bomb state
    timer = 0
    bombx = 68
    seen = []
    for _ in range(frames):
        st = packed & 3
        if st == 1:
            timer -= 1
            if timer == 0:
                packed = (packed & 0xFC) | 2
                timer = 60
        elif st == 2:
            timer -= 1
            if timer == 0:
                packed &= 0xFC
                timer = 0
        if (packed & 3) == 0:
            bombx = 68
        if ticks == 0:
            if roomx < 140:
                roomx += 1
            else:
                ticks += 1
        elif ticks == 1:
            if roomy < 48:
                roomy += 1
            else:
                ticks += 1
        elif ticks == 2:
            player_dir = 1
            ticks += 1
        elif ticks == 3:
            packed |= 1
            bombx = 140
            timer = 180
            ticks += 1
        elif ticks == 4:
            if roomx < 77:
                player_dir = 0       # at center: wait facing RIGHT
                ticks += 1
            else:
                roomx -= 1
        elif ticks == 5:
            if (packed & 3) == 0:
                player_dir = 1       # blast gone: walk home facing LEFT
                ticks += 1
        elif ticks == 6:
            if roomx < 21:
                timer = 240
                player_dir = 0       # home: pause facing RIGHT
                ticks += 1
            else:
                roomx -= 1
        elif ticks == 7:  # machine-owned pause (dir already 0)
            timer -= 1
            if timer == 0:
                ticks += 1
        else:               # ticks == 8: climb back to Y=0, then restart
            if roomy == 0:
                roomx, ticks = 20, 0
            else:
                roomy -= 1
        seen.append((roomx, roomy, ticks, packed & 3, player_dir, bombx))
    return seen


seq = simulate()
assert seq[0] == (21, 0, 0, 0, 0, 68)                  # first frame flies
assert all(seq[i][0] == 21 + i for i in range(120))     # fly 120 frames
assert seq[119][:3] == (140, 0, 0)
grounded = next(i for i, fr in enumerate(seq) if fr[1] == 48)
assert seq[grounded - 1][1] == 47                       # last air frame
arm = next(i for i, fr in enumerate(seq) if fr[3] == 1) # fuse armed
assert seq[arm - 1][2] == 3 and seq[arm][2] == 4        # phase 3 -> 4
assert seq[arm][5] == 140                               # BombX at drop site
explodes = [i for i, fr in enumerate(seq) if fr[3] == 2]
assert explodes, "bomb must reach state 2"
reset = next(i for i, fr in enumerate(seq)
             if i > 0 and fr[:3] == (20, 0, 0))         # climb done, loop restart
cyc = seq[:reset]                                      # first loop only
walk4 = [fr[0] for fr in cyc if fr[2] == 4]
assert walk4 and walk4[0] == 140 and walk4[-1] == 76    # walk to center
assert all(a - b == 1 for a, b in zip(walk4, walk4[1:]))  # 1 px per frame
assert all(seq[i][3] != 0 for i in range(arm, arm + 240))  # fuse 180 + expl 60
assert seq[arm + 240][3] == 0                             # machine reaped it
assert arm + 240 < reset                                  # reaped before loop end
assert all(fr[3] == 0 for fr in seq[:arm])               # no bomb before arm
wait5 = [i for i, fr in enumerate(cyc) if fr[2] == 5]
assert wait5 and all(cyc[i][3] != 0 for i in wait5)     # bomb covers phase 5
assert any(cyc[i][3] == 2 for i in wait5)               # explosion inside wait
walk6 = [fr[0] for fr in cyc if fr[2] == 6]
assert walk6 and walk6[0] == 76 and walk6[-1] == 20     # walk home
assert all(a - b == 1 for a, b in zip(walk6, walk6[1:]))
pauses = [i for i, fr in enumerate(seq) if fr[2] == 7]
assert len(pauses) >= 239                               # 240-frame pause
climb = [i for i in range(reset) if seq[i][2] == 8]    # first loop only
assert len(climb) == 49                                 # enter + 48 decs
assert seq[climb[0]][1] == 48                           # starts on the ground
assert seq[climb[-1]][1] == 0                           # lands on Y=0
assert reset == climb[-1] + 1                           # restart = next frame
assert reset + 1 < len(seq)
assert seq[reset + 1][0] == 21                          # loop restarted
assert all(fr[4] == 1 for i, fr in enumerate(seq)
           if seq[i][2] in (3, 4, 6))                   # left: arm + walks
assert all(fr[4] == 0 for i, fr in enumerate(seq)
           if seq[i][2] in (0, 1, 5, 7, 8))             # right: fly, waits, pause
assert {frame & 4 for frame in range(16)} == {0, 4}     # flutter bit pattern

kernel_pad = section(kernel, "TitlePlayerFold:", ".ds $FBF8 - *, 0")
bank2_pad = section(bank2, ".ds $FBE8 - *, 0", ".ds $FBF8 - *, 0")
assert "sta $1FF8\n    jmp $F880" in kernel_pad
assert "sta $1FF8\n    jmp TitlePlayerBand" in bank2_pad

# --- TitleSequence cross-bank fold: bank0 jsr target + bank2 mirror ---
assert "TitleSequenceFold:" in kernel
intro = section(kernel, "TitleIntro:", "FooterFold:")
assert "jsr TitleSequenceFold" in intro                # machine runs per frame
fold = section(kernel, "TitleSequenceFold:", "    .ds $FBF8 - *, 0")
assert "sta $1FF8\n    jmp $F471" in fold              # switch to bank2, jump
twin = section(bank2, ".ds $FBD6 - *, 0", ".ds $FBE0")
assert "sta $1FF8\n    jmp $F471" in twin              # same bytes, both banks
assert "TitleSequence:" in bank2
lst = (SRC / "bank2.lst").read_text()
assert re.search(r"f471\s+TitleSequence\s*$", lst, re.M)   # body at $F471
ts = section(bank2, "TitleSequence:", "    .ds $F600")
assert "dec BombTimer" in ts                           # fuse + pause owned here
assert "lda #240\n    sta BombTimer" in ts            # 240-frame pause
assert "lda #68\n    sta BombX" in ts                 # base X when idle
assert "sta PlayerDir\n    jmp .TSAdv" in ts           # transition face sets
assert ts.count("sta PlayerDir") == 4   # phase2 + 4->5(0) + 5->6(1) + 6->7(0)
assert "cmp #8" in ts and "dec RoomY" in ts            # phase 8 climbs to Y=0
assert "sta RoomY" not in ts                           # no teleport reset
assert "jmp $FBF8" in ts                               # ReturnPad exit

print("Title player sprite and fixed line-budget guards passed.")
