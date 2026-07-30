    processor 6502
    include "defines.asm"

    ORG $F000

; Bank 1 - spare data bank
; Graphics and level data can go here later
    .byte 0

; Pad to fill 4K
    ORG $FFFE
    .byte $FF, $FF
