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
    sta BK_GENERAL                       ; select bank0 — the fetch at $F005 is its

    include "colors.inc"
    include "banks.inc"             ; BK_* bank selectors by role (docs/agents/banks.md)
    include "generated/bank6_equs.inc"
    include "generated/cave_zp.inc"
    include "generated/cave_luts.inc"
CaveFrameLo:    .byte <PlayerSpriteA,<PlayerSpriteB,<PlayerWalkA,<PlayerWalkB

; ---- the cave kernel's PROLOGUE (bank6 has no room for it) ------------------------------
; Entered from bank6: `sta $1FFB` at Kernel6Entry, then the byte at +3 is the jmp below.
; Leaves with `sta $1FFA` at Kernel6Entry+6 (bank6 continues at +9, `Kernel6Back`).
Kernel6Entry = Kernel6Pad + 3
    org Kernel6Entry + 3
    jmp Prologue7
    org Kernel6Entry + 6
    sta BK_CAVE
    org $F100
Prologue7:
    include "bank6_prologue.inc"
    jmp Kernel6Entry + 6


    .ds $FFFA - *, 0
    .word $F000                     ; NMI (never used: sei)
    .word $F000                     ; RESET -> this bank's stub
    .word $F000                     ; IRQ (never used)
