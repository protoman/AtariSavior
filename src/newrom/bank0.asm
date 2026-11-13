; ==============================================================================
; NEW ROM (docs/agents/banks.md) - bank 0: GENERAL CODE
; main loop, input, physics, collision, sound, positioning, the fold pads. Byte-frozen in the old ROM; copied FIRST.
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
    jmp $F008                       ; $F005: the landing pad every other bank's stub fetches
GameStartNew:                       ; $F008: placeholder until GameStart is copied in
    jmp GameStartNew

    .ds $FFFA - *, 0
    .word $F000                     ; NMI (never used)
    .word $F008                     ; RESET -> this bank's stub (bank0: straight to GameStart)
    .word $F000                     ; IRQ (never used)
