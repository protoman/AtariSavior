; game_4k.asm - baby-step Atari 2600 kernel
; Milestone 3: room walls with four wide door openings.
; Game logic and sprites will be added only after this kernel is verified.
    processor 6502
    include "defines.asm"

    ORG $F000

; Zero-page game state
playerX     = $80
playerY     = $81
enemyX      = $82
enemyY      = $83
roomX       = $84
roomY       = $85
joyBits     = $86
nextGRP0    = $87
nextGRP1    = $88

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

    lda #80
    sta playerX
    lda #96
    sta playerY
    lda #1
    sta roomX
    sta roomY

    lda #$2A            ; orange hue, medium brightness
    sta COLUPF
    lda #$00
    sta COLUBK
    lda #$C2
    sta COLUP0
    lda #$00
    sta COLUP1

    lda #$01            ; D0 reflects the left playfield into the right half
    sta CTRLPF
    lda #0
    sta NUSIZ0
    sta NUSIZ1
    sta HMCLR

MainLoop:
; VSYNC - three scanlines
    sta WSYNC
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

; Read joystick 0 and update the player once per frame.
    jsr ReadJoystick
    jsr MovePlayer
    jsr PositionPlayer

.WaitVBlank:
    lda INTIM
    bne .WaitVBlank

; Enter the visible kernel. This milestone still has no sprites.
    sta WSYNC
    sta HMOVE
    lda #0
    sta VBLANK

    sta GRP0
    sta GRP1
    sta ENAM0
    sta ENAM1
    ldx #0
.KernelLine:
; PF0=$F0 makes the side walls in reflected mode. PF2=$0F leaves a
; centered gap in the top and bottom walls.
    txa
    cmp #8
    bcc .HorizontalWall
    cmp #88
    bcc .SideWall
    cmp #104
    bcc .DoorLine
    cmp #184
    bcc .SideWall

.HorizontalWall:
    lda #$F0
    sta PF0
    lda #$FF
    sta PF1
    lda #$0F
    sta PF2
    jmp .FinishLine

.SideWall:
    lda #$F0
    sta PF0
    lda #$00
    sta PF1
    sta PF2
    jmp .FinishLine

.DoorLine:
    lda #$00
    sta PF0
    sta PF1
    sta PF2

.FinishLine:
; Draw a four-scanline green player square at the fixed test position.
    txa
    sec
    sbc playerY
    cmp #4
    bcs .PlayerOff
    lda #$F0
    sta GRP0
    jmp .WaitLine
.PlayerOff:
    lda #0
    sta GRP0

.WaitLine:
    sta WSYNC
    inx
    cpx #192
    bcc .KernelLine

.KernelDone:
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

PositionPlayer:
    sta WSYNC
    lda playerX
    sec
.PositionDelay:
    sbc #15
    bcs .PositionDelay
    eor #7
    asl
    asl
    asl
    asl
    sta HMP0
    sta RESP0
    rts

; A = %0000RLDU for joystick 0, with active-low direction bits.
ReadJoystick:
    lda SWCHA
    lsr
    lsr
    lsr
    lsr
    sta joyBits
    rts

MovePlayer:
; Up
    lda joyBits
    and #%00000001
    bne .NoUp
    lda playerY
    cmp #8
    beq .NoUp
    dec playerY
.NoUp:

; Down
    lda joyBits
    and #%00000010
    bne .NoDown
    lda playerY
    cmp #187
    beq .NoDown
    inc playerY
.NoDown:

; Left
    lda joyBits
    and #%00000100
    bne .NoLeft
    lda playerX
    cmp #4
    beq .NoLeft
    dec playerX
.NoLeft:

; Right
    lda joyBits
    and #%00001000
    bne .NoRight
    lda playerX
    cmp #155
    beq .NoRight
    inc playerX
.NoRight:
.Done:
    rts

SelectEnemy:
; Room index = roomY * 3 + roomX.
    lda roomY
    asl
    clc
    adc roomY
    clc
    adc roomX
    tax
    lda EnemyXTable,x
    sta enemyX
    lda EnemyYTable,x
    sta enemyY
    rts

PositionSprites:
; The simple 15-color-clock loop is adequate while the objects are dots.
    sta WSYNC
    lda playerX
    sec
.PlayerDelay:
    sbc #15
    bcs .PlayerDelay
    eor #7
    asl
    asl
    asl
    asl
    sta HMP0
    sta RESP0

    sta WSYNC
    lda enemyX
    sec
.EnemyDelay:
    sbc #15
    bcs .EnemyDelay
    eor #7
    asl
    asl
    asl
    asl
    sta HMP1
    sta RESP1
    rts

; Fixed enemy locations make room transitions easy to see while testing.
EnemyXTable:
    .byte 32, 120, 72
    .byte 120, 40, 136
    .byte 72, 24, 112

EnemyYTable:
    .byte 32, 48, 144
    .byte 152, 64, 104
    .byte 40, 128, 168

    ORG $FFFC
    .word Init
    .word Init
