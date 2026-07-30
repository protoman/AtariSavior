    processor 6502
    include "defines.asm"

    ORG $F000

; Bank 2 - spare data bank
    ORG $F000 + $0FFE
    .byte $FF, $FF
