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
ENABL   = $1F
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
P0Kb    = $82       ; PAD + H0 + frame block offset (K of the gfx pointer arithmetic)
P1Kb    = $83
P0GHi   = $84       ; page of the player gfx / colour block
P0CHi   = $85
P1GHi   = $86
P1CHi   = $87
P0X     = $88
P1X     = $89
LaserState = $8A
DoorAnd = $8B
DoorOr  = $8C
NextS0  = $8D
NextS1  = $8E
T       = $8F
M       = $A8
BandCol = $A9
BandColNext = $AA
Tmp     = $AB
E0      = $AC
E1      = $AD
NextC0  = $AE
Band    = $AF
TideOff = $B4
WaterOff = $B5
WaterCol = $B6
PF0B    = $90       ; 4 bytes per register: one per band
PF1B    = $94
PF2B    = $98
CPFB    = $9C
BandTab = $B0
G0      = $A0       ; zero page pointers (lo = segment offset, hi = page)
C0      = $A2
G1      = $A4
C1      = $A6

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
    include "prologue_gen.inc"

.wait:
    lda INTIM
    bne .wait
    sta WSYNC
    lda #0
    sta VBLANK
    sta WSYNC               ; kernel line 0 starts on the line after this one

    jmp BandPad
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
