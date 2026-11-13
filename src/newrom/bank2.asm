; ==============================================================================
; NEW ROM (docs/agents/banks.md) - bank 2: GAMEPLAY CODE
; enemy movement, laser clamp/hit, bomb blast, stage slot staging, exit scan/pending, raft, bomb wall marks, strip blast.
; EMPTY SKELETON: only the boot stub and the vectors. Content is copied in from the
; old ROM in zone order (bank0 first); until then this bank is padding.
; ==============================================================================
    processor 6502
    seg code
    org $F000
; Boot stub (EVERY bank has it: F4 powers up in an undefined bank). `lda #0 / sta $1FF4`
; selects bank0, whose $F005 is `jmp $F008`.
    lda #0
    sta $1FF4

    .ds $FFFA - *, 0
    .word $F000                     ; NMI (never used)
    .word $F000                     ; RESET -> this bank's stub (bank0: straight to GameStart)
    .word $F000                     ; IRQ (never used)
