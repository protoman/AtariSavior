    processor 6502
    seg code
    org $F000
; Power-up stub (every bank has it: F4 powers up in an undefined bank): `lda #0 /
; sta $1FF4` selects bank0, whose $F005 is `jmp GameStart`. Guard: verify_build
; check_boot_banks (all 8 banks).
    lda #0
    sta $1FF4
; ==============================================================================
; Bank5 — free 4K window in the F4 (32K, 8 banks) layout.
; ==============================================================================
; Besides the stub, only the version header lives here ($F005: "S.A.V.I.O.R. <VERSION>", 0 - build.sh
; writes version.asm from the VERSION file). The file still assembles to a full 4K
; image: the tail is filled to the vector area, and the vectors are emitted (unused,
; but every bank image must be 4096 B and DASM only writes what is emitted).
; Hotspot for this bank: $1FF9 (F4: bank = addr - $1FF4).
; ==============================================================================
RomVersion:
    include "version.asm"
    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
