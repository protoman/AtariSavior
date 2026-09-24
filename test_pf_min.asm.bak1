    processor 6502
    include "comparison/lo-a-rad-dragon/vcs.h"

; "TESTE" via 3-phase flicker (20fps/char):
;   Phase 0: P0=T@px8,  P1=T@px23  (both T's simultaneously)
;   Phase 1: P0=E@px13, P1=E@px28  (both E's simultaneously)
;   Phase 2: P0=S@px18, P1=off
;
; Pixel formula: px = write_cycle * 3 - 63
; Phase 0: RESP0 write@24→px9,  RESP1 write@29→px24  (HMP $10/$10 → 8/23)
; Phase 1: RESP0 write@25→px12, RESP1 write@30→px27  (HMP $F0/$F0 → 13/28)
; Phase 2: RESP0 write@27→px18, RESP1 (GRP1=0, invisible)

    seg code
    org $f000

frame_phase = $80   ; cycles 0 → 1 → 2 → 0

Start:
    sei
    cld
    ldx #$ff
    txs
    lda #0
    sta frame_phase
.clear:
    sta 0,x
    dex
    bne .clear

    lda #$0e
    sta COLUP0
    sta COLUP1
    lda #0
    sta COLUBK
    sta COLUPF
    sta NUSIZ0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1

MainLoop:
    ;---- VSYNC: 3 lines ----------------------------------------
    lda #2
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #0
    sta VSYNC

    ;---- VBLANK: 37 lines ----------------------------------------
    lda #44
    sta TIM64T

    lda frame_phase
    beq .phase0
    cmp #1
    beq .phase1

    ;-- Phase 2: P0=S@18, P1=off --------------------------------
    ; RESP0 write@27 → px18, HMP0=$00 → px18
    ; RESP1 not needed (GRP1 stays 0)
    lda #$00
    sta HMP0
    sta HMP1
    sta WSYNC
    nop                 ; 2
    nop                 ; 4
    nop                 ; 6
    nop                 ; 8
    nop                 ; 10
    nop                 ; 12
    nop                 ; 14
    nop                 ; 16
    nop                 ; 18
    nop                 ; 20
    nop                 ; 22
    bit $80             ; reads frame_phase (ZP,3cy) → ends@24
    sta RESP0           ; opcode@25 operand@26 write@27 → CC81 → px18 ✓
    jmp .apply_hmove

    ;-- Phase 0: P0=T@8, P1=T@23 --------------------------------
    ; RESP0 write@24 → px9,  HMP0=$10 (left 1) → px8
    ; RESP1 write@29 → px24, HMP1=$10 (left 1) → px23
.phase0:
    lda #$10
    sta HMP0
    sta HMP1
    sta WSYNC
    nop                 ; 2
    nop                 ; 4
    nop                 ; 6
    nop                 ; 8
    nop                 ; 10
    nop                 ; 12
    nop                 ; 14
    nop                 ; 16
    nop                 ; 18
    nop                 ; 20
    nop                 ; 22
    sta RESP0           ; opcode@22 operand@23 write@24 → CC72 → px9
    nop                 ; 25-26
    sta RESP1           ; opcode@27 operand@28 write@29 → CC87 → px24
    jmp .apply_hmove

    ;-- Phase 1: P0=E@13, P1=E@28 -------------------------------
    ; RESP0 write@25 → px12, HMP0=$F0 (right 1) → px13
    ; RESP1 write@30 → px27, HMP1=$F0 (right 1) → px28
.phase1:
    lda #$F0
    sta HMP0
    sta HMP1
    sta WSYNC
    nop                 ; 2
    nop                 ; 4
    nop                 ; 6
    nop                 ; 8
    nop                 ; 10
    nop                 ; 12
    nop                 ; 14
    nop                 ; 16
    nop                 ; 18
    nop                 ; 20 (10 nops done, next@20)
    bit $80             ; ZP,3cy → ends@22
    sta RESP0           ; opcode@23 operand@24 write@25 → CC75 → px12
    nop                 ; 26-27
    sta RESP1           ; opcode@28 operand@29 write@30 → CC90 → px27

.apply_hmove:
    sta WSYNC
    sta HMOVE           ; at CC~6, inside HBLANK ✓

    ; Wait for rest of VBLANK
.vblank:
    lda INTIM
    bne .vblank
    sta WSYNC
    lda #0
    sta VBLANK

    ;---- Kernel: 192 visible scanlines --------------------------
    ; Pre-font: 80 blank lines
    lda #0
    sta GRP0
    sta GRP1            ; GRP1=0 stays for phase 2 (P1 invisible)
    ldy #80
.pre:
    sta WSYNC
    dey
    bne .pre

    ; Font rows: 5 scanlines at rows 80-84
    lda frame_phase
    beq .font_tt
    cmp #1
    beq .font_ee

    ; Phase 2: P0=S, GRP1 stays 0 → P1 invisible
    ldx #0
.font_s:
    sta WSYNC
    lda FontS,x
    sta GRP0
    inx
    cpx #5
    bne .font_s
    jmp PostKernel

    ; Phase 0: P0=T, P1=T (same data → just reuse A after sta GRP0)
.font_tt:
    ldx #0
.font_tt_lp:
    sta WSYNC
    lda FontT,x
    sta GRP0
    sta GRP1            ; A still = FontT[x] ✓
    inx
    cpx #5
    bne .font_tt_lp
    jmp PostKernel

    ; Phase 1: P0=E, P1=E
.font_ee:
    ldx #0
.font_ee_lp:
    sta WSYNC
    lda FontE,x
    sta GRP0
    sta GRP1            ; A still = FontE[x] ✓
    inx
    cpx #5
    bne .font_ee_lp

PostKernel:
    sta WSYNC           ; line after last font row: clear sprites
    lda #0
    sta GRP0
    sta GRP1

    ; 106 trailing lines  (80 + 5 + 1 + 106 = 192) ✓
    ldy #106
.post:
    sta WSYNC
    dey
    bne .post

    ;---- Overscan -----------------------------------------------
    lda #2
    sta VBLANK
    lda #36
    sta TIM64T

    ; Advance phase: 0 → 1 → 2 → 0
    inc frame_phase
    lda frame_phase
    cmp #3
    bne .no_reset
    lda #0
    sta frame_phase
.no_reset:

.waitOS:
    lda INTIM
    bne .waitOS
    sta WSYNC

    jmp MainLoop

;---- Font data: 5 rows, MSB = leftmost pixel --------------------
FontT:  .byte $E0, $40, $40, $40, $40  ; T: ###  _#_  _#_  _#_  _#_
FontE:  .byte $E0, $80, $C0, $80, $E0  ; E: ###  #__  ##_  #__  ###
FontS:  .byte $E0, $80, $E0, $20, $E0  ; S: ###  #__  ###  __#  ###

    org $fffc
    .word Start
    .word Start
