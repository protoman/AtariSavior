    lda P0Top
    clc
    adc #21
    sta E0
    lda P1Top
    clc
    adc #15
    sta E1
    lda E0
    sta T
    cmp #59
    lda #0
    sbc #0
    sta M
    lda #59
    sec
    sbc T
    and M
    sta NextC0
    lda P0Kb
    sec
    sbc T
    and M
    sta NextS0
    lda E1
    sta T
    cmp #52
    lda #0
    sbc #0
    sta M
    lda P1Kb
    sec
    sbc T
    and M
    sta NextS1
    lda NextC0
    sta C0
    lda NextS0
    sta G0
    lda NextS1
    sta G1
    sta C1
    lda E0
    sec
    sbc #2
    sta E0
    lda E1
    sec
    sbc #2
    sta E1
    lda E0
    sta T
    cmp #59
    lda #0
    sbc #0
    sta M
    lda #59
    sec
    sbc T
    and M
    sta NextC0
    lda P0Kb
    sec
    sbc T
    and M
    sta NextS0
    lda E1
    sta T
    cmp #52
    lda #0
    sbc #0
    sta M
    lda P1Kb
    sec
    sbc T
    and M
    sta NextS1
    lda E0
    sec
    sbc #36
    sta E0
    lda E1
    sec
    sbc #36
    sta E1
    lda CPFB+0
    and DoorAnd
    ora DoorOr
    sta BandCol
    sta COLUP1
    lda #0
    sta Band
    ; prime line 0: its rows are fetched on the line before the kernel (index S-1)
    ldy #0
    dec G0
    lda (G0),Y
    sta GRP0
    inc G0
    dec G1
    lda (G1),Y
    sta GRP1
    inc G1
    ldy #0
    ldx #0
