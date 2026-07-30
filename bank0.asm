    processor 6502
    include "defines.asm"

    ORG $F000

; Zero-page variables
  .align $80
playerX     = $80
playerY     = $81
playerYSub  = $82
vyLo        = $83
vyHi        = $84
jetPower    = $85
scanline    = $86
temp        = $87

Start:
    sei
    cld
    ldx #$FF
    txs

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

    lda #78
    sta playerX
    lda #80
    sta playerY
    lda #0
    sta playerYSub
    sta vyLo
    sta vyHi
    sta jetPower

    lda #$1E
    sta COLUPF
    lda #$00
    sta COLUBK
    lda #$9C
    sta COLUP0

    lda #0
    sta RESMP0
    sta RESMP1

    lda #$01
    sta CTRLPF

    lda #$00
    sta NUSIZ0

    sta HMCLR

MainLoop:

; VSYNC - 3 scanlines
    lda #%00000010
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #0
    sta VSYNC

; VBLANK
    lda #%01000010
    sta VBLANK

    lda #43
    sta TIM64T

; Read joystick 0 (bits 4-7 of SWCHA)
    lda SWCHA
    lsr
    lsr
    lsr
    lsr
    sta temp

; Right (bit 0 active low)
    bit temp
    bvc .NotRight
    inc playerX
    lda playerX
    cmp #152
    bcc .NotRight
    lda #152
    sta playerX
.NotRight:

; Left (bit 1 active low)
    lsr
    bcs .NotLeft
    dec playerX
    lda playerX
    cmp #4
    bcs .NotLeft
    lda #4
    sta playerX
.NotLeft:

; Down (bit 2)
    lsr

; Up (bit 3 active low) - jet thrust with inertia
    lsr
    bcs .NoJet

    lda jetPower
    clc
    adc #$01
    cmp #$20
    bcc .SetJet
    lda #$20
.SetJet:
    sta jetPower
    jmp .JetDone

.NoJet:
    lda jetPower
    sec
    sbc #$01
    bpl .SetJet2
    lda #0
.SetJet2:
    sta jetPower

.JetDone:
; Gravity: vy += $0010 per frame
    lda vyLo
    clc
    adc #$10
    sta vyLo
    lda vyHi
    adc #$00
    sta vyHi

; Jet: vy -= jetPower (upward)
    lda vyLo
    sec
    sbc jetPower
    sta vyLo
    lda vyHi
    sbc #0
    sta vyHi

; Clamp downward vy to $0200
    lda vyHi
    bmi .NoClamp
    cmp #$02
    bmi .NoClamp
    lda #$02
    sta vyHi
    lda #$00
    sta vyLo
.NoClamp:

; Update Y position
    lda playerYSub
    clc
    adc vyLo
    sta playerYSub
    lda playerY
    adc vyHi
    sta playerY

; Clamp Y
    lda playerY
    cmp #8
    bcs .CheckBottom
    lda #8
    sta playerY
    lda #0
    sta vyHi
    sta vyLo
    beq .PosDone
.CheckBottom:
    cmp #176
    bcc .PosDone
    lda #176
    sta playerY
    lda #0
    sta vyHi
    sta vyLo
.PosDone:

; Position player horizontally
    lda playerX
    jsr PosPlayer

; Wait for VBLANK timer
.WaitVBlank:
    lda INTIM
    bne .WaitVBlank

; Last VBLANK scanline - apply HMOVE, turn off VBLANK
    sta WSYNC
    sta HMOVE
    lda #0
    sta VBLANK

; KERNEL - 192 visible scanlines
    ldx #0
.Kernel:
    sta WSYNC

    txa
    cmp #8
    bcc .Solid
    cmp #184
    bcs .Solid

    lda #$F0
    sta PF0
    lda #$00
    sta PF1
    sta PF2
    jmp .DrawPlayer

.Solid:
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
    bcc .Kernel

; OVERSCAN
    lda #%01000010
    sta VBLANK
    lda #35
    sta TIM64T

    sta HMCLR

.WaitOverscan:
    lda INTIM
    bne .WaitOverscan

    lda #0
    sta VBLANK

    jmp MainLoop

PosPlayer:
    sec
    sta WSYNC
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
    rts

PlayerSprite:
    .byte %00111100
    .byte %01111110
    .byte %11011011
    .byte %11111111
    .byte %11011011
    .byte %01111110
    .byte %00111100
    .byte %00000000
