    processor 6502
; ==============================================================================
; Bank3 stub — power-up bank. Selects bank0, jumps to GameStart.
; ==============================================================================
    seg code
    org $F000

    ; --- 5-byte stub ---
    lda #0
    sta $1FF6                       ; select bank0
    jmp $F005                       ; GameStart in bank0

    ; Pad to vectors at $FFFA
    .ds $FFFA - *, 0

    ; Interrupt vectors — CPU reads $FFFC on power-up
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector ← power-up entry
    .word $F000                     ; IRQ vector
