    processor 6502
    seg code
    org $F000
; ==============================================================================
; Bank6 — free 4K window in the F4 (32K, 8 banks) layout.
; ==============================================================================
; Nothing lives here yet. The file still assembles to a full 4K image: the tail
; is filled to the vector area, and the vectors are emitted (unused, but every
; bank image must be 4096 B and DASM only writes what is emitted).
; Hotspot for this bank: $1FFA (F4: bank = addr - $1FF4).
; The power-up stub below is mandatory in EVERY bank: F4 powers up in an undefined
; bank, so each one selects bank0 (whose $F005 is `jmp GameStart`) first.
; ==============================================================================
    lda #0
    sta $1FF4                       ; select bank0 - the fetch at $F005 is its

    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
