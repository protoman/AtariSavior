    processor 6502
    seg code
    org $F000
; ==============================================================================
; Bank7 — POWER-UP BANK for F4 (32K, 8 banks)
; ==============================================================================
; F4 reads the reset vector from the LAST bank, so the entry stub lives here:
; EXACTLY five bytes — `lda #0 / sta $1FF4` — because after that write the next
; fetch at $F005 comes from bank0, whose pad is byte-identical there
; ($F005: jmp GameStart). Anything longer would land mid-instruction in bank0.
; Guard: tools/verify_build.py check_boot_banks.
; Hotspot for this bank: $1FFB.
; ==============================================================================
    lda #0
    sta $1FF4                       ; select bank0 — the fetch at $F005 is its

    .ds $FFFA - *, 0
    .word $F000                     ; NMI (never used: sei)
    .word $F000                     ; RESET -> this bank's stub
    .word $F000                     ; IRQ (never used)
