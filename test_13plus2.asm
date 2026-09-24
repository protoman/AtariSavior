; test_13plus2.asm - Exact 13_plus2 demo rendering
; Uses the proven mainTextLoop approach from the demo

    processor 6502
    include "comparison/lo-a-rad-dragon/vcs.h"

    seg.u Variables
    org $80
textptr   byte
savesp    byte
line      byte

; Font data pointers (ZP)
chars equ $a7

    seg code
    org $f000

Reset:
    sei
    cld
    ldx #$ff
    txs
    lda #0
.clear:
    sta 0,x
    dex
    bne .clear

    lda #$00
    sta COLUBK
    lda #$0e
    sta COLUP0
    sta COLUP1

MainLoop:
    lda #2
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #0
    sta VSYNC

    lda #43
    sta TIM64T
.waitVB:
    lda INTIM
    bne .waitVB

    ; Setup (from demo's Picture routine)
    lda #$0e
    sta COLUP0
    sta COLUP1
    lda #$00
    sta COLUBK

    ; Position sprites (from demo)
    lda #$01
    sta RESP0
    sta RESP1
    ldx #$f0
    stx HMP0
    ldx #$e0
    stx HMP1
    sta HMOVE

    lda #$03
    sta NUSIZ0
    sta NUSIZ1
    lda #$01
    sta VDELP0
    sta VDELP1

    ; Initialize text
    lda #0
    sta textptr
    tsx
    stx savesp

    ; Wait for VBLANK to end
    lda INTIM
    bne *-1

    sta WSYNC
    lda #$80
    sta VBLANK

    ; SLEEP 45 (from demo)
    SLEEP 45

    jmp mainTextLoop

    org $fc00
    align 256
mainTextLoop:
    ; Build stack with font data (simplified - use fixed data)
    ldx #chars
    txs
    ldy textptr
    ldx text,y
    beq .done
    iny

    ; Push font data for first char
    lda fontlo,x
    pha
    lda fontlo+1,x
    pha
    lda fontlo+2,x
    pha
    lda fontlo+3,x
    pha
    lda fontlo+4,x
    pha

    ; Push font data for pairs
    ldx text,y
    lda text1,y
    iny
    sty textptr
    tay

    lda fonthi,x
    ora fontlo,y
    pha
    lda fonthi+1,x
    ora fontlo+1,y
    pha
    lda fonthi+2,x
    ora fontlo+2,y
    pha
    lda fonthi+3,x
    ora fontlo+3,y
    pha
    lda fonthi+4,x
    ora fontlo+4,y
    pha

    ; Render 5 rows
    TEXTDISP 0
    TEXTDISP 1
    TEXTDISP 2
    TEXTDISP 3
    TEXTDISP 4

    ; Clear sprites
    lda #0
    sta GRP0
    sta GRP1
    sta GRP0
    sta ENAM0
    sta ENAM1
    sta ENABL

    SLEEP 66
    jmp mainTextLoop

.done:
    ; Restore stack
    ldx savesp
    txs

    ; Clear screen
    ldx #11
.scanloop:
    sta WSYNC
    dex
    bne .scanloop

    lda #2
    sta VBLANK
    lda #35
    sta TIM64T
.waitOS:
    lda INTIM
    bne .waitOS
    jmp MainLoop

; Text data
text:
    byte t,h,i,r,t,e,e,n,c,h,a,r,s,plus,_2,0
    byte 0
text1:
    byte t,h,i,r,t,e,e,n,c,h,a,r,s,plus,_2,0

; Include the 13_plus2 font data from the demo
    include "generated/menu_13plus2.asm"

    org $fffc
    .word Reset
    .word Reset
