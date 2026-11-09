; HERO-style cave kernel PROTOTYPE (standalone 4K ROM, NTSC).
; Generated pieces: kernel_gen.inc (the 4 bands), tables_gen.inc (padded sprite tables,
; SMap lookup). Purpose: prove that a branch-free sprite fetch (per-band counters in X/Y)
; leaves room for the playfield stores inside normal lines, i.e. no dead lines.
    processor 6502
VSYNC   = $00
VBLANK  = $01
WSYNC   = $02
NUSIZ0  = $04
NUSIZ1  = $05
COLUP0  = $06
COLUP1  = $07
COLUPF  = $08
COLUBK  = $09
CTRLPF  = $0A
PF0     = $0D
PF1     = $0E
PF2     = $0F
RESP0   = $10
RESP1   = $11
GRP0    = $1B
GRP1    = $1C
ENAM0   = $1D
HMP0    = $20
HMP1    = $21
VDELP0  = $25
VDELP1  = $26
HMOVE   = $2A
HMCLR   = $2B
INTIM   = $0284
TIM64T  = $0296

; ---- zero page: the harness pokes the inputs ----
P0Top   = $80       ; kernel line of the player's first row (two's complement)
P1Top   = $81
P0Base  = $82       ; frame base index into the P0 tables (0 / 58)
P1Base  = $83       ; design base index into the P1 tables (0 / 52)
P0X     = $84
P1X     = $85
LaserState = $86
NextX   = $87
NextY   = $88
SavX    = $89
T0      = $8A
T1      = $8B
LineCnt = $8C
Tmp     = $8D
PF0B    = $90       ; 4 bytes per register: one per band
PF1B    = $94
PF2B    = $98
CPFB    = $9C

    ORG $F000
Reset:
    sei
    cld
    ldx #$FF
    txs
    lda #0
    tax
.clr:
    sta $00,x
    inx
    bne .clr
    ldx #$FF
    txs

StartFrame:
    lda #2
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #0
    sta VSYNC
    lda #2
    sta VBLANK
    lda #43
    sta TIM64T

    ; ---- VBL work: TIA init, positions, band-0 counters ----
    lda #1
    sta VDELP0
    lda #0
    sta VDELP1
    sta NUSIZ0
    sta NUSIZ1
    sta COLUBK
    lda #1
    sta $0A                 ; CTRLPF reflect
    lda PF0B
    sta PF0
    lda PF1B
    sta PF1
    lda PF2B
    sta PF2
    lda CPFB
    sta COLUPF
    lda P0X
    ldx #0
    jsr SetX
    lda P1X
    ldx #1
    jsr SetX
    sta WSYNC
    sta HMOVE
    ; band 0 counters: X = P0Base + SMap0[P0Top - 0], Y = P1Base + SMap1[P1Top - 0]
    ldx P0Top
    lda SMap0,x
    clc
    adc P0Base
    sta T0
    ldx P1Top
    lda SMap1,x
    clc
    adc P1Base
    tay
    ldx T0
    ; prime line 0: its row is fetched on the line "before" the kernel
    lda P0Gfx-1,x
    sta GRP0
    lda P1Gfx-1,y
    sta GRP1                ; latches old0 (VDELP0)
    lda P1Col-1,y
    sta COLUP1

.wait:
    lda INTIM
    bne .wait
    sta WSYNC
    lda #0
    sta VBLANK
    sta WSYNC               ; kernel line 0 starts on the line after this one

    include "kernel_gen.inc"

    ; ---- overscan ----
    lda #0
    sta GRP0
    sta GRP1
    sta ENAM0
    sta PF0
    sta PF1
    sta PF2
    lda #2
    sta VBLANK
    ldx #OVERSCAN
.os:
    sta WSYNC
    dex
    bne .os
    jmp StartFrame

SetX:
    sta WSYNC
    sec
.d: sbc #15
    bcs .d
    eor #7
    asl
    asl
    asl
    asl
    sta HMP0,x
    sta RESP0,x
    rts

    include "tables_gen.inc"

    ORG $FFFC
    .word Reset
    .word Reset
