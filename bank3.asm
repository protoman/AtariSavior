    processor 6502
    include "defines.asm"

    ORG $F000

; Bank 3 - startup + reset vectors
; Selected by default at power-on

Startup:
    sei
    cld
    ldx #$FF
    txs
    sta BANK0
; After sta BANK0, bank 0 is selected.
; CPU continues fetching from bank 0 at the same address ($F008).
; Bank 0 must have matching code at this address.

; Trampoline for banks 1/2 — they sta BANK3 then jmp here
    ORG $F010
TrampolineToBank3:
    jmp Startup

; Vectors at $FFFC
    ORG $FFFC
    .word Startup
    .word Startup
