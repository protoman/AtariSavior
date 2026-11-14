; ==============================================================================
; Bank 5 - EMPTY since 2026-11-14 (banks plan, docs/agents/banks.md): the blank room-transition frame, the
; attract-mode script and the version header moved to bank4 (trans.inc). This bank only carries the boot
; stub and the vectors; it is reserved for LEVEL DATA (bank order: code first, levels last).
; ==============================================================================
    processor 6502
    seg code
    include "banks.inc"             ; BK_* bank selectors by role
    org $F000
    lda #0
    sta BK_GENERAL                  ; boot stub (every bank): select bank0, whose $F005 is `jmp $F008`

    .ds $FFFA - *, 0
    .word $F000                     ; NMI (never used)
    .word $F000                     ; RESET -> this bank's stub
    .word $F000                     ; IRQ (never used)
