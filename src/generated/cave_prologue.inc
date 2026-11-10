    lda P0Top
    clc
    adc #21
    sta E0
    lda EC
    clc
    adc #15
    sta EC
    lda EC+1
    clc
    adc #15
    sta EC+1
    ; segment u = 0 (slot 0 object)
    lda E0
    cmp #59
    lda #0
    sbc #0
    sta T
    lda #59
    sec
    sbc E0
    and T
    sta NextC0
    lda P0Kb
    sec
    sbc E0
    and T
    sta NextS0
    lda EC
    cmp #52
    lda #0
    sbc #0
    sta T
    lda KbC
    sec
    sbc EC
    and T
    sta NextS1
    lda NextC0
    sta C0
    lda NextS0
    sta G0
    lda NextS1
    sta G1
    sta C1
    lda G1hiC
    sta G1+1
    lda C1hiC
    sta C1+1
    ; segment u = 2: P0, and the context band 0 uses (slot 1 only when Slot1Band == 0)
    lda E0
    sec
    sbc #2
    sta E0
    cmp #59
    lda #0
    sbc #0
    sta T
    lda #59
    sec
    sbc E0
    and T
    sta NextC0
    lda P0Kb
    sec
    sbc E0
    and T
    sta NextS0
    ldx #0
    lda Slot1Band
    bne .ctx0
    inx
.ctx0:
    lda EC,X
    sec
    sbc #2
    sta S1Adj
    cmp #52
    lda #0
    sbc #0
    sta T
    lda KbC,X
    sec
    sbc S1Adj
    and T
    sta NextS1
    ; E for the first prep (u = 38): P0 and the slot-0 context ...
    lda E0
    sec
    sbc #36
    sta E0
    lda EC
    sec
    sbc #38
    sta EC
    ; ... and the slot-1 context: first used by the prep of band Slot1Band-1 (u = 36 *
    ; Slot1Band + 2), or by band 0's prep (u = 38) when Slot1Band = 0
    lda EC+1
    sec
    sbc #2
    ldx Slot1Band
    cpx #4
    bcs .e1done
    bne .e1loop
    inx
.e1loop:
    sec
    sbc #36
    dex
    bne .e1loop
.e1done:
    sta EC+1
    ; band 0 colour, the band counter, the line-0 prime (its rows are fetched on the line
    ; before the kernel: index S-1)
    lda CPFB
    and DoorAnd
    ora DoorOr
    sta BandCol
    sta COLUP1
    lda #0
    sta Band
    ldx #0
