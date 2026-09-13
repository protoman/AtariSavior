#!/usr/bin/env python3
"""Relocate tutorial 13_plus2 source into F6 bank1 menu address space."""

from pathlib import Path
import sys


SOURCE = Path("docs/tutorial/13_plus2.asm")


def port() -> str:
    source = SOURCE.read_text()
    source = source.replace(
        "        processor 6502\n        include vcs.h",
        "        include \"comparison/lo-a-rad-dragon/vcs.h\"\n"
        "        include \"comparison/lo-a-rad-dragon/macro.h\"",
        1,
    )
    source = source.replace("        org $F000", "        org $F540", 1)
    source = source.replace("Start\n", "MenuMain\n", 1)
    text_start = source.index("  MAC TEXT\n")
    text_end = source.index("  ENDM\n", text_start) + len("  ENDM\n")
    text_rows = [
        ["eq"] * 13 + ["_", "_"],
        ["_", "s", "a", "v", "i", "o", "r", "_", "_2", "_6", "_0", "_0", "_", "_", "_"],
        ["eq"] * 13 + ["_", "_"],
        ["_"] * 15,
        ["_", "_", "lp", "c", "rp", "_", "_2", "_0", "_2", "_6", "_", "_", "_", "_", "_"],
        ["_", "_", "u", "p", "p", "e", "r", "l", "a", "n", "d", "_", "_", "_", "_"],
        ["_", "_", "_", "s", "t", "u", "d", "i", "o", "s", "_", "_", "_", "_", "_"],
        ["_"] * 15,
        ["_"] * 15,
        ["_"] * 15,
        ["_"] * 15,
        ["_", "p", "r", "e", "s", "s", "_", "f", "i", "r", "e", "_", "_", "_", "_"],
        ["_", "_", "t", "o", "_", "s", "t", "a", "r", "t", "_", "_", "_", "_", "_"],
    ]
    text_lines = ["  MAC TEXT"]
    for row in text_rows:
        text_lines.append("\tTEXT{1} " + ",".join(row + ["0"]))
    text_lines.append("  ENDM\n")
    source = source[:text_start] + "\n".join(text_lines) + source[text_end:]
    source = source.replace(
        "        sta ENABL\n\n\n        SLEEP 66        ; 15+23+12",
        "        sta ENABL\n\n"
        "        dec line\n"
        "        lda line\n"
        "        cmp #12\n"
        "        bne KeepOrange\n"
        "        lda #$0e\n"
        "        sta COLUP0\n"
        "        sta COLUP1\n"
        "        jmp ColorDone\n"
        "KeepOrange\n"
        "        SLEEP 10\n"
        "ColorDone\n"
        "        SLEEP 43        ; preserve original 66-cycle inter-line delay",
        1,
    )
    source = source.replace(
        "ast\n        byte %10100000\n        byte %01000000\n        byte %11100000\n        byte %01000000\n        byte %10100000\neq",
        "ast\n        byte %10100000\n        byte %01000000\n        byte %11100000\n        byte %01000000\n        byte %10100000\nlp\n        byte %01000000\n        byte %10000000\n        byte %10000000\n        byte %10000000\n        byte %01000000\nrp\n        byte %01000000\n        byte %00100000\n        byte %00100000\n        byte %00100000\n        byte %01000000\neq",
        1,
    )
    source = source.replace(
        ";ast\n        byte %00001010\n        byte %00000100\n        byte %00001110\n        byte %00000100\n        byte %00001010\n;eq",
        ";ast\n        byte %00001010\n        byte %00000100\n        byte %00001110\n        byte %00000100\n        byte %00001010\n;lp\n        byte %00000100\n        byte %00001000\n        byte %00001000\n        byte %00001000\n        byte %00000100\n;rp\n        byte %00000100\n        byte %00000010\n        byte %00000010\n        byte %00000010\n        byte %00000100\n;eq",
        1,
    )
    source = source.replace(
        "        align 256\nmainTextLoop",
        "        org $f640\nmainTextLoop",
        1,
    )
    source = source.replace(
        "\talign 256\n\nmainTextLoop",
        "        org $f640\nmainTextLoop",
        1,
    )
    source = source.replace(
        "   byte {16},{3},{5},{7},{9},{11},{13},{15}",
        "   byte <{16},<{3},<{5},<{7},<{9},<{11},<{13},<{15}",
        1,
    )
    source = source.replace(
        "   byte {1},{2},{4},{6},{8},{10},{12},{14}",
        "   byte <{1},<{2},<{4},<{6},<{8},<{10},<{12},<{14}",
        1,
    )
    source = source.replace("text__example1", "text__example1", 1)

    old_overscan = """        lda #$02
        sta VBLANK

        rts     ; overscan
"""
    new_overscan = """WaitOverscan
        lda INTIM
        bne WaitOverscan

        lda INPT4
        bmi NoFire
        lda #1
        sta GameMode
        jmp ToGameStub
NoFire
        lda #$02
        sta VBLANK
        rts
"""
    if old_overscan not in source:
        raise RuntimeError("13_plus2 overscan block changed")
    source = source.replace(old_overscan, new_overscan, 1)

    old_vectors = """        org $FFFC
        .word Start
        .word Start
"""
    new_vectors = """        org $fc68
ToMenuStub
        lda #1
        sta $1FF7
        jmp MenuMain

        org $fc70
ToGameStub
        lda #0
        sta $1FF6
        jmp GameStart

        org $fffc
        .word MenuMain
        .word MenuMain
"""
    if old_vectors not in source:
        raise RuntimeError("13_plus2 vector block changed")
    source = source.replace(old_vectors, new_vectors, 1)
    return source


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: port_13plus2.py OUTPUT", file=sys.stderr)
        return 2
    output = Path(sys.argv[1])
    output.write_text(port())
    print(f"ported 13_plus2 -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
