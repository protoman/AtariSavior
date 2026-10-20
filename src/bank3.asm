    processor 6502
; ==============================================================================
; Bank3 — boot stub ONLY (C3 2026-10-20: the payload moved to bank2)
; ==============================================================================
; Power-up bank (F6: the latch is undefined at power-up, so ANY bank can be the
; first fetched). This bank now holds nothing but the 5-byte "select bank0"
; prefix and the three vectors — 11 emitted bytes total:
;
;   $F000  lda #0 / sta $1FF6     ; selects bank0 (the write is what switches)
;   $F005  (no byte needed)       ; the fetch AFTER the sta is read from BANK0,
;                                 ;   where $F005 is `jmp GameStart` — so the
;                                 ;   old dead `jmp $F005` filler is gone
;   $FFFA  NMI / RESET / IRQ      ; all three point at $F000
;
; History: 2026-10-13 put the Phase-4 crunch/stage bodies here (bank0 had 1 B
; of pre-pad headroom), and A3 2026-10-19 added the level-data blocks + their
; walkers. C1-C3 2026-10-20 evacuated all of it into bank2 (see the slot map in
; bank2.asm), so no pad switches here at run time.
;
; Keep this a VALID 4K image: the F6 vectors must exist, the $F000 prefix must
; stay `lda #0 / sta $1FF6` (verify_build.check_boot_banks), and $FFF2-$FFF9
; must stay fill — $FFF6-$FFF9 decode as F6 hotspot mirrors on PEEK (Stella
; calls checkSwitchBank from peek; see kernel.asm MothExitPad's comment).
; ==============================================================================
    seg code
    org $F000

    ; --- 5-byte stub: select bank0, then the fetch at $F005 is bank0's ---
    lda #0
    sta $1FF6                       ; select bank0

    .ds $FFF2 - *, 0                ; $FFF2-$FFF9 stay fill (F6 hotspot mirrors)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector ← power-up entry
    .word $F000                     ; IRQ vector
