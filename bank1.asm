    processor 6502
    include "defines.asm"

    ORG $F000

; Bank 1 - spare data bank
; If CPU boots here (bankrandom), switch to bank 3 and restart
StartBank1:
    sta BANK3
    jmp $F010           ; trampoline in bank 3

; Pad to fill 4K
    ORG $FFFC
    .word StartBank1
    .word StartBank1
