  processor 6502

; ------------------------------------------------------------------------------
; Bank 2 (F6, window $F000 / physical offset $2000)
; Simplified HUD rendering.  Called from bank0's kernel via a fold-pad
; trampoline at $fc78.  Returns to bank0 via $fc80.
; ------------------------------------------------------------------------------

    include "comparison/lo-a-rad-dragon/vcs.h"
    include "comparison/lo-a-rad-dragon/macro.h"

HUD_COLOR = $06

; ZP variable addresses (must match bank0's declarations exactly)
Level           = $96
FontP0          = $b3
FontP1          = $b8
Temp            = $ad
ScoreTh         = $c2
ScoreHu         = $c3
ScoreTe         = $c4
ScoreOn         = $c5
ScoreDigit2     = $c6
ScoreDigit3     = $cb

    seg code
    org $f000

Reset:
    lda #0
    sta $1FF6           ; F6: select bank0

    org $f010
Bank2HudEntry:
; ============================================================================
; Simplified HUD: "LVnn" line + "nnnn" score line, 48 scanlines.
; Layout: 8 (LV+digits) + 8 (score) + 32 (pad) = 48
;
; Font order: ScoreSpriteFont stores row 0 = TOP of glyph.
; Render loop writes GRP BEFORE WSYNC so TIA latches for current scanline.
; ============================================================================

; --- Setup ---
    lda #0
    sta PF0
    sta PF1
    sta PF2
    lda #HUD_COLOR
    sta COLUBK
    lda #$0e              ; white
    sta COLUP0
    sta COLUP1
    lda #0
    sta NUSIZ0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1
    sta REFP0
    sta REFP1

; ============================================================================
; Line 1: "LV 01" — all 4 characters on ONE line.
; P0 = packed "LV" (L in bits 7-5, V in bits 2-0), P1 = packed "01" (tens, ones).
; Layout matches score: P0 at px10, P1 at px28.
; ============================================================================

    ; --- Compute Level+1 tens and ones ---
    lda Level
    clc
    adc #1
    ldx #0
.Div10:
    cmp #10
    bcc .GotLevel
    sbc #10
    inx
    jmp .Div10
.GotLevel:
    ; A = ones, X = tens
    pha
    txa
    asl
    asl
    asl                     ; *8
    tax
    ldy #0
.LoadTensDigit:
    lda ScoreSpriteFont,X
    sta ScoreDigit2,Y       ; tens digit rows
    inx
    iny
    cpy #5
    bne .LoadTensDigit

    pla                     ; A = ones
    asl
    asl
    asl
    tax
    ldy #0
.LoadOnesDigit:
    lda ScoreSpriteFont,X
    sta ScoreDigit3,Y       ; ones digit rows
    inx
    iny
    cpy #5
    bne .LoadOnesDigit

    ; --- Pack "LV" into FontP0, "01" into FontP1 ---
    ldy #0
.PackLoop:
    ; P0 = FontL | (FontV >> 5)  →  "LV"
    lda FontV,Y
    lsr
    lsr
    lsr
    lsr
    lsr                     ; V in bits 2-0
    sta Temp
    lda FontL,Y
    ora Temp
    sta FontP0,Y

    ; P1 = tens | (ones >> 5)  →  "01"
    lda ScoreDigit3,Y
    lsr
    lsr
    lsr
    lsr
    lsr                     ; ones in bits 2-0
    sta Temp
    lda ScoreDigit2,Y
    ora Temp
    sta FontP1,Y

    iny
    cpy #5
    bne .PackLoop

    ; --- Position and render (matches score layout) ---
    lda #10
    ldx #0
    jsr SetObjectXPos_b2
    lda #28
    ldx #1
    jsr SetObjectXPos_b2
    sta WSYNC
    sta HMOVE

    ; Render 5 scanlines
    lda FontP0
    ldy #1
    sta WSYNC
    sta GRP0
    lda FontP1
    sta GRP1
.LVRender:
    sta WSYNC
    lda FontP0,Y
    sta GRP0
    lda FontP1,Y
    sta GRP1
    iny
    cpy #5
    bne .LVRender

    ; Clear sprites
    sta WSYNC
    lda #0
    sta GRP0
    sta GRP1

; ============================================================================
; Line 3: Score "nnnn" — left-aligned
; ============================================================================
    ; Load all 4 digits, compose packed pairs
    ; Digit 0 (thousands) -> FontP0
    lda ScoreTh
    asl
    asl
    asl
    tax
    ldy #0
.LoadD0:
    lda ScoreSpriteFont,X
    sta FontP0,Y
    inx
    iny
    cpy #5
    bne .LoadD0

    ; Digit 1 (hundreds) -> FontP1
    lda ScoreHu
    asl
    asl
    asl
    tax
    ldy #0
.LoadD1:
    lda ScoreSpriteFont,X
    sta FontP1,Y
    inx
    iny
    cpy #5
    bne .LoadD1

    ; Digit 2 (tens) -> ScoreDigit2
    lda ScoreTe
    asl
    asl
    asl
    tax
    ldy #0
.LoadD2:
    lda ScoreSpriteFont,X
    sta ScoreDigit2,Y
    inx
    iny
    cpy #5
    bne .LoadD2

    ; Digit 3 (ones) -> ScoreDigit3
    lda ScoreOn
    asl
    asl
    asl
    tax
    ldy #0
.LoadD3:
    lda ScoreSpriteFont,X
    sta ScoreDigit3,Y
    inx
    iny
    cpy #5
    bne .LoadD3

    ; Compose packed pairs:
    ;   FontP0[row] = FontP0[row] | (FontP1[row] >> 5)  -> "12"
    ;   FontP1[row] = ScoreDigit2[row] | (ScoreDigit3[row] >> 5) -> "34"
    ldy #0
.Compose:
    lda FontP1,Y
    lsr
    lsr
    lsr
    lsr
    lsr                 ; >> 5
    sta Temp
    lda FontP0,Y
    ora Temp
    sta FontP0,Y

    lda ScoreDigit3,Y
    lsr
    lsr
    lsr
    lsr
    lsr                 ; >> 5
    ora ScoreDigit2,Y
    sta FontP1,Y

    iny
    cpy #5
    bne .Compose

    ; Position P0 at px10, P1 at px28 (left-aligned)
    lda #10
    ldx #0
    jsr SetObjectXPos_b2
    lda #28
    ldx #1
    jsr SetObjectXPos_b2
    sta WSYNC
    sta HMOVE

    ; Render 5 scanlines — write GRP BEFORE WSYNC
    lda FontP0            ; row 0
    ldy #1
    sta WSYNC
    sta GRP0
    lda FontP1
    sta GRP1
.ScoreRender:
    sta WSYNC
    lda FontP0,Y
    sta GRP0
    lda FontP1,Y
    sta GRP1
    iny
    cpy #5
    bne .ScoreRender

    ; Clear sprites
    sta WSYNC
    lda #0
    sta GRP0
    sta GRP1

; ============================================================================
; Padding: fill remaining scanlines to reach 48 total
; Used: 8 (LV+packed) + 8 (score) = 16.  Need 32 more.
; ============================================================================
    ldx #32
.HudPad:
    sta WSYNC
    dex
    bne .HudPad

; ============================================================================
; Return to bank0
; ============================================================================
    jmp ToBank0Return

; ============================================================================
; Subroutines
; ============================================================================

SetObjectXPos_b2:
    sta WSYNC
    sec
.Div15Loop:
    sbc #15
    bcs .Div15Loop
    tay
    lda fineAdjustTable_b2,Y
    sta HMP0,X
    sta RESP0,X
    rts

; ============================================================================
; Font data — row 0 = TOP of glyph
; ============================================================================

FontL:
    .byte $80, $80, $80, $80, $e0   ; bottom-to-top: #.. #.. #.. #.. ###
FontV:
    .byte $a0, $a0, $a0, $a0, $40   ; top-to-bottom: #.# #.# #.# #.# .#.

ScoreSpriteFont:
  .byte  $e0, $a0, $a0, $a0, $e0, $00, $00, $00  ; 0
  .byte  $40, $c0, $40, $40, $e0, $00, $00, $00  ; 1
  .byte  $e0, $20, $e0, $80, $e0, $00, $00, $00  ; 2
  .byte  $e0, $20, $e0, $20, $e0, $00, $00, $00  ; 3
  .byte  $a0, $a0, $e0, $20, $20, $00, $00, $00  ; 4
  .byte  $e0, $80, $e0, $20, $e0, $00, $00, $00  ; 5
  .byte  $e0, $80, $e0, $a0, $e0, $00, $00, $00  ; 6
  .byte  $e0, $20, $40, $40, $40, $00, $00, $00  ; 7
  .byte  $e0, $a0, $e0, $a0, $e0, $00, $00, $00  ; 8
  .byte  $e0, $a0, $e0, $20, $e0, $00, $00, $00  ; 9

; ============================================================================
; Fold pads (byte-identical in bank0 and bank2)
; ============================================================================

    org $fc78
    lda #2
    sta $1FF8
    jmp Bank2HudEntry

    org $fc80
ToBank0Return:
    lda #0
    sta $1FF6
    rts

; ============================================================================
; Fine-adjust table (page-aligned)
; ============================================================================
    org $ff00
fineAdjustBegin_b2:
  .byte %01110000
  .byte %01100000
  .byte %01010000
  .byte %01000000
  .byte %00110000
  .byte %00100000
  .byte %00010000
  .byte %00000000
  .byte %11110000
  .byte %11100000
  .byte %11010000
  .byte %11000000
  .byte %10110000
  .byte %10100000
  .byte %10010000
fineAdjustTable_b2 EQU fineAdjustBegin_b2 - %11110001

    org $fffc
    .word Reset
    .word Reset
