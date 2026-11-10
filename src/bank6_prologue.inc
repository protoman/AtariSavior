; ==============================================================================
; Cave kernel PROLOGUE (VBL time) - shared by bank6.asm and tools/proto/main.asm.
; Reads the state the bank0 VBL staged (player frame pointer, the two GRP1 objects, door,
; tide, water) and fills the kernel's zero page: pointer pages, K values, the object
; contexts [slot 0, slot 1] and Slot1Band; then the generated core (cave_prologue.inc)
; computes the first segment. Needs: cave_zp.inc, cave_luts.inc, CaveFrameLo, CaveFineTab.
; Registers are free; no jsr (the stack bytes $F8-$FF double as kernel arrays).
; ==============================================================================
    MAC FINDDESIGN                  ; A = ObjBase-style offset -> X = design index (a table lookup)
    tax
    lda CaveDesignIdx,X
    tax
    ENDM

    ; the VBL-tail inits the live kernel did right before its timer poll
    lda #1
    sta VDELP0
    lda #0
    sta VDELP1
    sta ENABL

    ; ---- player frame: Grp0Ptr lo -> frame -> table page + K ----
    lda Grp0Ptr
    ldx #3
.frame:
    cmp CaveFrameLo,X
    beq .frameok
    dex
    bpl .frame
    inx                             ; unknown pointer: frame 0
.frameok:
    lda CaveFrameGHi,X
    sta G0+1
    lda CaveFrameKb,X
    sta P0Kb
    lda #CAVE_P0CHI
    sta C0+1

    ; ---- slot 0 object: ObjBase -> design -> pages + K; EC[0] = line of its row 0 ----
    lda ObjBase
    cmp #$FF
    beq .none0
    FINDDESIGN 0
    lda ObjTop
    clc
    adc RoomY
    sec
    sbc #1                          ; ObjTop = line of row 0 - RoomY + 1
    jmp .set0
.none0:
    ldx #0
    lda #200                        ; parked: far outside every segment
.set0:
    sta EC
    lda CaveDesignGHi,X
    sta G1hiC
    lda CaveDesignCHi,X
    sta C1hiC
    lda CaveDesignKb,X
    sta KbC

    ; ---- slot 1 object (bank2 StageSlot1: ObjBase1 = $FF when there is none) ----
    lda ObjBase1
    cmp #$FF
    beq .none1
    FINDDESIGN 1
    lda ObjTop1
    clc
    adc RoomY
    sec
    sbc #1
    cmp #CAVE_LINES                 ; line of row 0 outside the cave: no hook
    bcs .none1
    sta EC+1
    ldy #$FF
    sec
.band:
    iny
    sbc #BAND_LINES
    bcs .band
    sty Slot1Band                   ; = line / 36
    lda CaveDesignGHi,X
    sta G1hiC+1
    lda CaveDesignCHi,X
    sta C1hiC+1
    lda CaveDesignKb,X
    sta KbC+1
    ; S1Pos = HMP1 fine value (b7-4) | N (b3-0): the delay iterations SetObjectXPos would run
    lda ObjX1
    sec
    ldx #0
.div15:
    inx
    sbc #15
    bcs .div15
    clc
    adc #15                         ; A = x mod 15
    tay
    lda CaveFineTab,Y
    and #$F0
    sta T
    txa
    ora T
    sta S1Pos
    jmp .s1done
.none1:
    lda #$FF
    sta Slot1Band
    lda #200
    sta EC+1
    lda #0
    sta G1hiC+1                     ; (never selected: ctx 1 is only used from Slot1Band on)
    sta C1hiC+1
    sta KbC+1
.s1done:

    ; ---- door stripe: BandCol = (ColupfBuf & DoorAnd) | DoorOr ----
    lda CollisionCellY
    bmi .nodoor
    sta DoorOr
    lda #0
    sta DoorAnd
    beq .doordone
.nodoor:
    lda #$FF
    sta DoorAnd
    lda #0
    sta DoorOr
.doordone:

    ; ---- water: the strip is painted unless the explosion blink owns COLUBK / band off ----
    lda BombPacked
    and #%00000011
    cmp #2
    beq .nowater
    lda RoomBandColor
    beq .nowater
    lda #0
    sta WaterOff
    beq .waterdone
.nowater:
    lda #$30                        ; the water store goes to a dead TIA address
    sta WaterOff
.waterdone:

    include "cave_prologue.inc"     ; pointers, segments 0/1, line-0 prime, Band = 0
