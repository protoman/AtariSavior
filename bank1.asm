    processor 6502
    include "defines.asm"

    ORG $F000

; Bank 1 - spare data bank
; Graphics and level data can go here later
; For now, just pad to 4K and switch to bank 0

    lda #$FF  ; should never reach here
    sta $FF

; Pad to end of 4K
    ORG $F000 + $0FFE
    .byte $FF, $FF
