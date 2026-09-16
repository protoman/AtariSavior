    processor 6502
; ==============================================================================
; Bank1 stub — selects bank0, jumps to GameStart
; ==============================================================================
    seg code
    org $F000

    ; --- 5-byte stub ---
    lda #0
    sta $1FF6                       ; select bank0
    jmp $F005                       ; GameStart in bank0

    ; Pad to vectors at $FFFA
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
