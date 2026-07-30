    processor 6502
    include "defines.asm"

    ORG $F000

; Zero-page variables
playerX     = $80
playerY     = $81
playerYSub  = $82
vyLo        = $83
vyHi        = $84
jetPower    = $85
scanline    = $86
temp        = $87

; Matching header for bank 3 startup (must be identical bytes at $F000-$F009)
    sei
    cld
    ldx #$FF
    txs
    sta BANK0       ; safe no-op when already in bank 0
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

    lda #$00
    sta CTRLPF
    sta NUSIZ0

    sta HMCLR

MainLoop:

; VSYNC - 3 scanlines
    sta WSYNC           ; align to start of scanline
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

; Read joystick 0 (bits 4-7 of SWCHA: bit4=up, bit5=down, bit6=left, bit7=right; 0=pressed)
    lda SWCHA
    lsr
    lsr
    lsr
    lsr             ; A = %0000RLDU (bit3=right, bit2=left, bit1=down, bit0=up)

; Check Up (bit 0) - jet thrust
    lsr             ; carry = up (since bit0 shifted out)
    bcs .NoJet      ; carry=1 means up NOT pressed (active low)

    lda jetPower
    clc
    adc #$01
    cmp #$20
    bcc .SetJet
    lda #$20
.SetJet:
    sta jetPower
    jmp .AfterUp

.NoJet:
    lda jetPower
    sec
    sbc #$01
    bpl .SetJet2
    lda #0
.SetJet2:
    sta jetPower

.AfterUp:
; Check Down (bit 1) - advance LSR, not used directly (gravity handles it)
    lsr             ; carry = down
    ; not used

; Check Left (bit 2) - move left
    lsr             ; carry = left
    bcs .NotLeft
    dec playerX
    lda playerX
    cmp #4
    bcs .NotLeft
    lda #4
    sta playerX
.NotLeft:

; Check Right (bit 3) - move right
    lsr             ; carry = right
    bcs .NotRight
    inc playerX
    lda playerX
    cmp #152
    bcc .NotRight
    lda #152
    sta playerX
.NotRight:

; Gravity: vy += $0010 per frame
    lda vyLo
    clc
    adc #$10
    sta vyLo
    lda vyHi
    adc #$00
    sta vyHi

; Jet: vy -= jetPower (upward thrust)
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

; Clamp Y within playfield border
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
    sta WSYNC       ; align to scanline start BEFORE PosPlayer
    lda playerX
    jsr PosPlayer

; Wait for VBLANK timer
.WaitVBlank:
    lda INTIM
    bne .WaitVBlank

; Enter kernel - first visible scanline
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

; OVERSCAN
    lda #%01000010
    sta VBLANK
    lda #35
    sta TIM64T

    sta HMCLR

.WaitOverscan:
    lda INTIM
    bne .WaitOverscan

    jmp MainLoop

; Player positioning subroutine
PosPlayer:
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
    rts

; Player sprite data (8 pixels wide, 8 pixels tall)
PlayerSprite:
    .byte %00111100
    .byte %01111110
    .byte %11011011
    .byte %11111111
    .byte %11011011
    .byte %01111110
    .byte %00111100
    .byte %00000000

; Pad to fill 4K  
    ORG $FFFC
    .word Init
    .word Init
