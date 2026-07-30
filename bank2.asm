    processor 6502
    include "defines.asm"

    ORG $F000

; Bank 2 - spare data bank
; If CPU boots here (bankrandom), switch to bank 3 and restart
StartBank2:
    sta BANK3
    jmp $F010           ; trampoline in bank 3

; Pad to fill 4K
    ORG $FFFC
    .word StartBank2
    .word StartBank2
