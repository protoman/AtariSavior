    processor 6502
; ==============================================================================
; Bank2 stub — selects bank0, jumps to GameStart
; ==============================================================================
    seg code
    org $F000

FetchPtr = $E0                   ; must match kernel.asm (operand baked in)

    ; --- 5-byte stub ---
    lda #0
    sta $1FF6                       ; select bank0
    jmp $F005                       ; GameStart in bank0

    ; --- Level data (frozen addresses — pointer values must match bank0's
    ;     original layout, level_bank_plan P2.1: $F9D9-$FB1E = 326B) ---
    org $F9D9
    include "generated/levels_data.asm"
    include "generated/levels.asm"

; ------------------------------------------------------------------------------
; FoldIndirect — byte-identical copy of kernel.asm's block (same $FEF6
; address). bank0 executes bytes 1-4 (`sta $1FF8,X`) then fetches bytes 5-9
; here (data bank active); `sta $1FF6` switches back, rts fetched from bank0.
; Guard: verify_build compares bank0/bank2 regions byte-for-byte.
; ------------------------------------------------------------------------------
    .ds $FEF6 - *, 0
FoldIndirect:
    sta $1FF8,X
    lda (FetchPtr),Y
    sta $1FF6
    rts

    ; Pad to vectors at $FFFA
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
