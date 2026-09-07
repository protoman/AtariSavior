  processor 6502

; ------------------------------------------------------------------------------
; Bank 1 (F6, window $F000 / physical offset $1000)
; Reserved space for non-kernel game data/logic (enemy tables, sound, etc.).
; Currently unused except for the startup stub, so emulators that power up in
; bank 1 still end up switching to bank0.
; ------------------------------------------------------------------------------

    seg code
    org $f000

Reset:
    lda #0
    sta $1FF6           ; F6: select bank0 (next fetch comes from bank0 at $F005)

    org $fffc
    .word Reset
    .word Reset