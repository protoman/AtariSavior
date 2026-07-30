    processor 6502
    include "defines.asm"

    ORG $F000

; Bank 2 - spare data bank
    .byte 0

; Pad to fill 4K
    ORG $FFFE
    .byte $FF, $FF
