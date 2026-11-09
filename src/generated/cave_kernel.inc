    IF (* & $FF) + 47 > $100
    align 256
    ENDIF
BandPad:
    nop
BandStart:
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda PF0B,X
    sta PF0
    lda PF1B,X
    sta PF1
    lda CPFB,X
    nop
    sta COLUPF
    lda (G1),Y
    sta GRP1
    beq .e1
    lda (C1),Y
    sta COLUP1
    bne .j1
.e1:
    lda BandCol
    sta COLUP1
    nop
    nop
.j1:
    iny
    sta WSYNC
    jmp B1in
    IF (* & $FF) + 104 > $100
    align 256
    ENDIF
S1Stub:
    jmp S1Path
B1in:
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda PF2B,X
    sta PF2
    lda BandTab,X
    sta ENABL
    bit Tmp
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e2
    lda (C1),Y
    sta COLUP1
    bne .j2
.e2:
    lda BandCol
    sta COLUP1
    nop
    nop
.j2:
    iny
    sta WSYNC
    cpx Slot1Band
    beq S1Stub
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
    ldy #0
    lda (G1),Y
    sta GRP1
    beq .e3
    lda (C1),Y
    sta COLUP1
    bne .j3
.e3:
    lda BandCol
    sta COLUP1
    nop
    nop
.j3:
    iny
    sta WSYNC
    IF (* & $FF) + 51 > $100
    jmp .g1
    align 256
.g1
H1in:
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda Band
    cmp Slot1Band
    lda #0
    rol
    sta.w T
    tax
    lda G1hiC,X
    sta G1+1
    lda (G1),Y
    sta GRP1
    beq .e5
    lda (C1),Y
    sta COLUP1
    bne .j5
.e5:
    lda BandCol
    sta COLUP1
    nop
    nop
.j5:
    iny
    sta WSYNC
    ELSE
    bit Tmp
H1in:
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda Band
    cmp Slot1Band
    lda #0
    rol
    sta.w T
    tax
    lda G1hiC,X
    sta G1+1
    lda (G1),Y
    sta GRP1
    beq .e4
    lda (C1),Y
    sta COLUP1
    bne .j4
.e4:
    lda BandCol
    sta COLUP1
    nop
    nop
.j4:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 53 > $100
    jmp .g2
    align 256
.g2
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx T
    lda C1hiC,X
    sta C1+1
    lda E0
    cmp #59
    lda #0
    sbc #0
    sta.w T
    lda (G1),Y
    sta GRP1
    beq .e7
    lda (C1),Y
    sta COLUP1
    bne .j7
.e7:
    lda BandCol
    sta COLUP1
    nop
    nop
.j7:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx T
    lda C1hiC,X
    sta C1+1
    lda E0
    cmp #59
    lda #0
    sbc #0
    sta.w T
    lda (G1),Y
    sta GRP1
    beq .e6
    lda (C1),Y
    sta COLUP1
    bne .j6
.e6:
    lda BandCol
    sta COLUP1
    nop
    nop
.j6:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 50 > $100
    jmp .g3
    align 256
.g3
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda P0Kb
    sec
    sbc E0
    and T
    sta NextS0
    bit Tmp
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e9
    lda (C1),Y
    sta COLUP1
    bne .j9
.e9:
    lda BandCol
    sta COLUP1
    nop
    nop
.j9:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda P0Kb
    sec
    sbc E0
    and T
    sta NextS0
    bit Tmp
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e8
    lda (C1),Y
    sta COLUP1
    bne .j8
.e8:
    lda BandCol
    sta COLUP1
    nop
    nop
.j8:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 52 > $100
    jmp .g4
    align 256
.g4
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda #59
    sec
    sbc E0
    and T
    sta NextC0
    lda E0
    sec
    sbc #36
    sta E0
    lda (G1),Y
    sta GRP1
    beq .e11
    lda (C1),Y
    sta COLUP1
    bne .j11
.e11:
    lda BandCol
    sta COLUP1
    nop
    nop
.j11:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda #59
    sec
    sbc E0
    and T
    sta NextC0
    lda E0
    sec
    sbc #36
    sta E0
    lda (G1),Y
    sta GRP1
    beq .e10
    lda (C1),Y
    sta COLUP1
    bne .j10
.e10:
    lda BandCol
    sta COLUP1
    nop
    nop
.j10:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 51 > $100
    jmp .g5
    align 256
.g5
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda Band
    clc
    adc #1
    cmp Slot1Band
    lda #0
    rol
    sta CtxNext
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e13
    lda (C1),Y
    sta COLUP1
    bne .j13
.e13:
    lda BandCol
    sta COLUP1
    nop
    nop
.j13:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda Band
    clc
    adc #1
    cmp Slot1Band
    lda #0
    rol
    sta CtxNext
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e12
    lda (C1),Y
    sta COLUP1
    bne .j12
.e12:
    lda BandCol
    sta COLUP1
    nop
    nop
.j12:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 52 > $100
    jmp .g6
    align 256
.g6
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx CtxNext
    lda EC,X
    cmp #52
    lda #0
    sbc #0
    sta T
    bit Tmp
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e15
    lda (C1),Y
    sta COLUP1
    bne .j15
.e15:
    lda BandCol
    sta COLUP1
    nop
    nop
.j15:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx CtxNext
    lda EC,X
    cmp #52
    lda #0
    sbc #0
    sta T
    bit Tmp
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e14
    lda (C1),Y
    sta COLUP1
    bne .j14
.e14:
    lda BandCol
    sta COLUP1
    nop
    nop
.j14:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 49 > $100
    jmp .g7
    align 256
.g7
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx CtxNext
    lda KbC,X
    sec
    sbc EC,X
    and T
    sta NextS1
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e17
    lda (C1),Y
    sta COLUP1
    bne .j17
.e17:
    lda BandCol
    sta COLUP1
    nop
    nop
.j17:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx CtxNext
    lda KbC,X
    sec
    sbc EC,X
    and T
    sta NextS1
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e16
    lda (C1),Y
    sta COLUP1
    bne .j16
.e16:
    lda BandCol
    sta COLUP1
    nop
    nop
.j16:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 49 > $100
    jmp .g8
    align 256
.g8
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx CtxNext
    lda EC,X
    sec
    sbc #36
    sta EC,X
    nop
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e19
    lda (C1),Y
    sta COLUP1
    bne .j19
.e19:
    lda BandCol
    sta COLUP1
    nop
    nop
.j19:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx CtxNext
    lda EC,X
    sec
    sbc #36
    sta EC,X
    nop
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e18
    lda (C1),Y
    sta COLUP1
    bne .j18
.e18:
    lda BandCol
    sta COLUP1
    nop
    nop
.j18:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 53 > $100
    jmp .g9
    align 256
.g9
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda Band
    eor Slot1Band
    cmp #1
    lda #0
    sbc #0
    and #2
    sta S1Adj
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e21
    lda (C1),Y
    sta COLUP1
    bne .j21
.e21:
    lda BandCol
    sta COLUP1
    nop
    nop
.j21:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    lda Band
    eor Slot1Band
    cmp #1
    lda #0
    sbc #0
    and #2
    sta S1Adj
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e20
    lda (C1),Y
    sta COLUP1
    bne .j20
.e20:
    lda BandCol
    sta COLUP1
    nop
    nop
.j20:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 49 > $100
    jmp .g10
    align 256
.g10
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx Band
    lda TideMask,X
    and CollisionX
    clc
    adc NAROM,X
    sta T
    tax
    nop
    lda (G1),Y
    sta GRP1
    beq .e23
    lda (C1),Y
    sta COLUP1
    bne .j23
.e23:
    lda BandCol
    sta COLUP1
    nop
    nop
.j23:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx Band
    lda TideMask,X
    and CollisionX
    clc
    adc NAROM,X
    sta T
    tax
    nop
    lda (G1),Y
    sta GRP1
    beq .e22
    lda (C1),Y
    sta COLUP1
    bne .j22
.e22:
    lda BandCol
    sta COLUP1
    nop
    nop
.j22:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 97 > $100
    jmp .g11
    align 256
.g11
    nop
LoopA:
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    bit Tmp
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e26
    lda (C1),Y
    sta COLUP1
    bne .j26
.e26:
    lda BandCol
    sta COLUP1
    nop
    nop
.j26:
    iny
    sta WSYNC
    dex
    bne LoopA
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx Band
    lda WaterXROM,X
    ora WaterOff
    tax
    lda RoomBandColor
    sta COLUBK,X
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e27
    lda (C1),Y
    sta COLUP1
    bne .j27
.e27:
    lda BandCol
    sta COLUP1
    nop
    nop
.j27:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
LoopA:
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    bit Tmp
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e24
    lda (C1),Y
    sta COLUP1
    bne .j24
.e24:
    lda BandCol
    sta COLUP1
    nop
    nop
.j24:
    iny
    sta WSYNC
    dex
    bne LoopA
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx Band
    lda WaterXROM,X
    ora WaterOff
    tax
    lda RoomBandColor
    sta COLUBK,X
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e25
    lda (C1),Y
    sta COLUP1
    bne .j25
.e25:
    lda BandCol
    sta COLUP1
    nop
    nop
.j25:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 49 > $100
    jmp .g12
    align 256
.g12
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    inc Band
    lda #20
    sec
    sbc T
    sbc S1Adj
    tax
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e29
    lda (C1),Y
    sta COLUP1
    bne .j29
.e29:
    lda BandCol
    sta COLUP1
    nop
    nop
.j29:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    inc Band
    lda #20
    sec
    sbc T
    sbc S1Adj
    tax
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e28
    lda (C1),Y
    sta COLUP1
    bne .j28
.e28:
    lda BandCol
    sta COLUP1
    nop
    nop
.j28:
    iny
    sta WSYNC
    ENDIF
    IF (* & $FF) + 151 > $100
    jmp .g13
    align 256
.g13
    nop
LoopB:
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    bit Tmp
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e33
    lda (C1),Y
    sta COLUP1
    bne .j33
.e33:
    lda BandCol
    sta COLUP1
    nop
    nop
.j33:
    iny
    sta WSYNC
    dex
    bne LoopB
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx Band
    lda CPFB,X
    and DoorAnd
    ora DoorOr
    sta BandCol
    cpx #4
    beq .xt
    bit Tmp
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
    jmp BandPad
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx Band
    lda CPFB,X
    and DoorAnd
    ora DoorOr
    sta BandCol
    cpx #4
    beq .xt
.xt:
    nop
    lda (G1),Y
    sta GRP1
    beq .e35
    lda (C1),Y
    sta COLUP1
    bne .j35
.e35:
    lda BandCol
    sta COLUP1
    nop
    nop
.j35:
    iny
    sta WSYNC
    ELSE
    bit Tmp
    nop
LoopB:
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    bit Tmp
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda (G1),Y
    sta GRP1
    beq .e30
    lda (C1),Y
    sta COLUP1
    bne .j30
.e30:
    lda BandCol
    sta COLUP1
    nop
    nop
.j30:
    iny
    sta WSYNC
    dex
    bne LoopB
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx Band
    lda CPFB,X
    and DoorAnd
    ora DoorOr
    sta BandCol
    cpx #4
    beq .xt
    bit Tmp
    lda (G1),Y
    sta GRP1
    beq .e31
    lda (C1),Y
    sta COLUP1
    bne .j31
.e31:
    lda BandCol
    sta COLUP1
    nop
    nop
.j31:
    iny
    sta WSYNC
    jmp BandPad
    lda (C0),Y
    sta COLUP0
    and LaserState
    sta ENAM0
    lda (G0),Y
    sta GRP0
    ldx Band
    lda CPFB,X
    and DoorAnd
    ora DoorOr
    sta BandCol
    cpx #4
    beq .xt
.xt:
    nop
    lda (G1),Y
    sta GRP1
    beq .e32
    lda (C1),Y
    sta COLUP1
    bne .j32
.e32:
    lda BandCol
    sta COLUP1
    nop
    nop
.j32:
    iny
    sta WSYNC
    ENDIF
