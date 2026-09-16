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
PF0ScoreBuf     = $b3          ; reused from FontP0 after level rendering
PF1ScoreBuf     = $b8          ; reused from FontP1 after level rendering
PF2ScoreBuf     = $c6          ; reused from ScoreDigit2 (no longer needed)
Temp            = $ad
ScoreTh         = $c2
ScoreHu         = $c3
ScoreTe         = $c4
ScoreOn         = $c5

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

    ; --- Level digits pre-computed in bank0 VBLANK ---
    ; FontP0/FontP1 already contain packed "LV" and level number.

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
; Pre-compute score PF values into buffers (runs during level scanlines,
; before score section). PF registers are free here (level uses GRP0/GRP1).
;
; PF0ScoreBuf[row] = PFDigitFont[ScoreTh*5+Y] << 4
; PF1ScoreBuf[row] = PFDigitFont[ScoreHu*5+Y] << 5
; PF2ScoreBuf[row] = PFDigitFont[ScoreTe*5+Y] | (PFDigitFont[ScoreOn*5+Y] << 4)
; ============================================================================

    ldy #0
.ScorePreComp:
    ; --- PF0 from ScoreTh ---
    ldx ScoreTh               ; 3
    lda DigitTimes5,X         ; 4
    sta Temp                  ; 3
    tya                       ; 2
    clc                       ; 2
    adc Temp                  ; 3
    tax                       ; 2
    lda PFDigitFont,X         ; 4
    asl                       ; 2
    asl                       ; 2
    asl                       ; 2
    asl                       ; 2
    sta PF0ScoreBuf,Y         ; 5

    ; --- PF1 from ScoreHu ---
    ldx ScoreHu               ; 3
    lda DigitTimes5,X         ; 4
    sta Temp                  ; 3
    tya                       ; 2
    clc                       ; 2
    adc Temp                  ; 3
    tax                       ; 2
    lda PFDigitFont,X         ; 4
    asl                       ; 2
    asl                       ; 2
    asl                       ; 2
    asl                       ; 2
    asl                       ; 2
    sta PF1ScoreBuf,Y         ; 5

    ; --- PF2 from ScoreTe + ScoreOn ---
    ; Digit 3 first (no shift)
    ldx ScoreTe               ; 3
    lda DigitTimes5,X         ; 4
    sta Temp                  ; 3
    tya                       ; 2
    clc                       ; 2
    adc Temp                  ; 3
    tax                       ; 2
    lda PFDigitFont,X         ; 4
    pha                       ; 3  save digit3 pattern on stack

    ; Digit 4 (shift left 4)
    ldx ScoreOn               ; 3
    lda DigitTimes5,X         ; 4
    sta Temp                  ; 3
    tya                       ; 2
    clc                       ; 2
    adc Temp                  ; 3
    tax                       ; 2
    lda PFDigitFont,X         ; 4
    asl                       ; 2
    asl                       ; 2
    asl                       ; 2
    asl                       ; 2
    sta Temp                  ; 3  save shifted digit4

    pla                       ; 4  restore digit3 pattern
    ora Temp                  ; 3
    sta PF2ScoreBuf,Y         ; 5

    iny                       ; 2
    cpy #5                    ; 2
    bne .ScorePreComp         ; 3

; ============================================================================
; Line 3: Score "nnnn" — PF-based rendering from pre-computed buffers
; ============================================================================

    ldy #0
.ScoreRender:
    lda PF0ScoreBuf,Y         ; 4
    sta PF0                    ; 3
    lda PF1ScoreBuf,Y         ; 4
    sta PF1                    ; 3
    lda PF2ScoreBuf,Y         ; 4
    sta PF2                    ; 3
    sta WSYNC                  ; 3
    iny                        ; 2
    cpy #5                     ; 2
    bne .ScoreRender           ; 3

    ; Clear PF after score to prevent persistence into padding
    sta WSYNC
    lda #0
    sta PF0
    sta PF1
    sta PF2

; Padding: fill remaining scanlines to reach 48 total
; Used: 8 (LV) + 9 (score: PF render with computation) = 17.
; Need 31 more.
    ldx #26
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
; PF Digit Font — pattern in bits 0-2 (3 pixels wide)
; 10 digits × 5 rows. Each byte has the glyph in bits 0-2.
; Shifted at runtime: PF0 = pattern<<4, PF1 = pattern<<5, PF2 = pattern
; ============================================================================

PFDigitFont:
  .byte %00000111, %00000101, %00000101, %00000101, %00000111  ; 0
  .byte %00000010, %00000110, %00000010, %00000010, %00000111  ; 1
  .byte %00000111, %00000001, %00000111, %00000100, %00000111  ; 2
  .byte %00000111, %00000001, %00000111, %00000001, %00000111  ; 3
  .byte %00000101, %00000101, %00000111, %00000001, %00000001  ; 4
  .byte %00000111, %00000100, %00000111, %00000001, %00000111  ; 5
  .byte %00000111, %00000100, %00000111, %00000101, %00000111  ; 6
  .byte %00000111, %00000001, %00000001, %00000001, %00000001  ; 7
  .byte %00000111, %00000101, %00000111, %00000101, %00000111  ; 8
  .byte %00000111, %00000101, %00000111, %00000001, %00000111  ; 9

; Lookup table: digit × 5 (for PFDigitFont indexing)
DigitTimes5:
  .byte 0, 5, 10, 15, 20, 25, 30, 35, 40, 45

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
