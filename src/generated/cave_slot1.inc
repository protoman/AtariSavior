    IF (* & $FF) + 123 > $100
    align 256
    ENDIF
S1Path:
    lda G1hiC+1
    sta G1+1
    lda C1hiC+1
    sta C1+1
    lda #0
    sta HMP0
    sta HMM0
    sta HMBL
    lda ObjRefs
    asl
    sta REFP1
    iny
    sta WSYNC
    lda S1Pos
    sta HMP1
    and #$0F
    tax
S1Delay:
    dex
    bne S1Delay
    nop
    nop
    sta RESP1
    iny
    sta WSYNC
    sta HMOVE
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda NextS0
    sta G0
    lda NextC0
    sta C0
    lda NextS1
    sta G1
    sta C1
    ldy #2
    lda (G1),Y
    sta GRP1
    beq .e34
    lda (C1),Y
    sta COLUP1
    bne .j34
.e34:
    lda BandCol
    sta COLUP1
    nop
    nop
.j34:
    iny
    sta WSYNC
    jmp H1in
