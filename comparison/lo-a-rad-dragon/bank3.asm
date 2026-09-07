  processor 6502

; ------------------------------------------------------------------------------
; Bank 3 (F6, window $F000 / physical offset $3000)
; F6 cartridges power up with bank 3 selected, so the reset vector lives here
; (physical $3FFC). The stub selects bank0; the fetch that follows lands on
; bank0's landing pad (`jmp Main` at window $F005).
; ------------------------------------------------------------------------------

    seg code
    org $f000

Reset:
    lda #0
    sta $1FF6           ; F6: select bank0 (next fetch comes from bank0 at $F005)

    org $fffc
    .word Reset
    .word Reset