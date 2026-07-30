    processor 6502
    include "defines.asm"

    ORG $F000

; Bank 3 - Reset vectors and startup
; Power-on starts here (bank 3 selected by default)

Startup:
    sei
    cld
    ldx #$FF
    txs

    lda #0
    ldx #$2D
.InitTIA:
    sta 0,x
    dex
    bpl .InitTIA

    ldx #$7F
.InitRAM:
    sta $80,x
    dex
    bpl .InitRAM

    lda #78
    sta $80
    lda #80
    sta $81

    lda #$1E
    sta COLUPF
    lda #$00
    sta COLUBK
    lda #$9C
    sta COLUP0
    lda #$01
    sta CTRLPF

    lda #$1FF6 & $FF
    sta BANK0

    jmp $F000

    ORG $FFFC
    .word Startup
    .word Startup
