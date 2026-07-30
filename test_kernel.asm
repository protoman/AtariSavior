    processor 6502
    include "defines.asm"

    ORG $F000

; Zero-page
playerY = $81

    sei
    cld
    ldx #$FF
    txs
    jmp Init

Init:
    lda #0
    ldx #$2D
.ClearTIA:
    sta 0,x
    dex
    bpl .ClearTIA

    ldx #$7F
.ClearRAM:
    sta $80,x
    dex
    bpl .ClearRAM

    lda #$1E
    sta COLUPF
    lda #$00
    sta COLUBK
    lda #$9C
    sta COLUP0

    lda #$00
    sta CTRLPF
    sta NUSIZ0
    sta HMCLR

    lda #88
    sta playerY

MainLoop:
    sta WSYNC
    lda #%00000010
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #0
    sta VSYNC

    lda #%01000010
    sta VBLANK

    lda #43
    sta TIM64T

    sta WSYNC
    lda #80
    sec
.DivLoop:
    sbc #15
    bcs .DivLoop
    eor #7
    asl
    asl
    asl
    asl
    sta HMP0
    sta RESP0

.WaitVBlank:
    lda INTIM
    bne .WaitVBlank

    sta WSYNC
    sta HMOVE
    lda #0
    sta VBLANK

    ldx #0
    jmp .KernelBody

.KernelLoop:
    sta WSYNC

.KernelBody:
    txa
    cmp #8
    bcc .SolidBorder
    cmp #184
    bcs .SolidBorder

    lda #$F0
    sta PF0
    lda #$00
    sta PF1
    sta PF2
    jmp .DrawPlayer

.SolidBorder:
    lda #$F0
    sta PF0
    lda #$FF
    sta PF1
    sta PF2

.DrawPlayer:
    txa
    sec
    sbc playerY
    cmp #8
    bcs .Blank
    tay
    lda PlayerSprite,y
    sta GRP0
    jmp .Next
.Blank:
    lda #0
    sta GRP0
.Next:
    inx
    cpx #192
    bcc .KernelLoop

    lda #%01000010
    sta VBLANK
    lda #35
    sta TIM64T
    sta HMCLR

.WaitOverscan:
    lda INTIM
    bne .WaitOverscan

    jmp MainLoop

PlayerSprite:
    .byte %00111100
    .byte %01111110
    .byte %11011011
    .byte %11111111
    .byte %11011011
    .byte %01111110
    .byte %00111100
    .byte %00000000

    ORG $FFFC
    .word Init
    .word Init
