    processor 6502
; ==============================================================================
; bank1 — HUD rendering (F6 bankswitch, $F000-$FFFF)
; ==============================================================================
; Follows HERO/comparison pattern exactly:
; - GRP0/GRP1 for indicator sprites (lives, bombs)
; - PF registers for score digits (pre-computed)
; - SetObjectXPos for precise positioning
; - Returns via fold-pad at $FC70

VBLANK  = $01
WSYNC   = $02
NUSIZ0  = $04
NUSIZ1  = $05
COLUP0  = $06
COLUP1  = $07
COLUPF  = $08
COLUBK  = $09
PF0     = $0D
PF1     = $0E
PF2     = $0F
RESP0   = $10
RESP1   = $11
GRP0    = $1B
GRP1    = $1C
ENAM0   = $1D
ENAM1   = $1E
ENABL   = $1F
HMP0    = $20
HMP1    = $21
HMOVE   = $2A
REFP0   = $0B
REFP1   = $0C
CTRLPF  = $0A
VDELP0  = $25
VDELP1  = $26

    org $F000

    ; Bank0 power-up stub: lda #0 / sta $1FF6 → lands here, jumps to GameStart
    jmp $F008

    org $F540
MenuMain:
    ; ========================================================================
    ; HUD entry point — called from bank0 via fold-pad at $FC68
    ; Follows comparison/lo-a-rad-dragon/bank2.asm pattern exactly
    ; ========================================================================

    ; --- Setup (same as comparison bank2) ---
    lda #0
    sta PF0
    sta PF1
    sta PF2
    lda #$06            ; grey background
    sta COLUBK
    lda #$0e            ; white sprites
    sta COLUP0
    sta COLUP1
    lda #0
    sta NUSIZ0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1
    sta REFP0
    sta REFP1

; ZP variables for score rendering
PF0ScoreBuf = $B3       ; 5 bytes: PF0 values (unused with sprite approach)
PF1ScoreBuf = $B8       ; 5 bytes: PF1 values (unused with sprite approach)
PF2ScoreBuf = $C6       ; 5 bytes: PF2 values (unused with sprite approach)
Temp        = $AD       ; scratch variable
RowCnt      = $AE       ; score render row counter (0-7)
DigitPtr1   = $94       ; pointer to digit 0 font data
DigitPtr2   = $96       ; pointer to digit 1 font data
DigitPtr3   = $98       ; pointer to digit 2 font data
DigitPtr4   = $9A       ; pointer to digit 3 font data
DigitPtr5   = $9C       ; pointer to digit 4 font data
ScoreTh     = $C2       ; score thousands digit
ScoreHu     = $C3       ; score hundreds digit
ScoreTe     = $C4       ; score tens digit
ScoreOn     = $C5       ; score ones digit

    ; --- Top gap: 4 scanlines (lower HUD elements) ---
    ldx #4
.TopGap:
    sta WSYNC
    dex
    bne .TopGap

    ; ====================================================================
    ; Line 1: Timer bar (PF-based, yellow, ~70% centered)
    ; ====================================================================
    lda #$1E            ; yellow
    sta COLUPF

    lda #$00            ; PF0: pixels 0-3 OFF
    sta PF0
    lda #$FF            ; PF1: pixels 4-11 ON
    sta PF1
    lda #$FF            ; PF2: pixels 12-19 ON
    sta PF2

    ldx #6
.TimerLoop:
    sta WSYNC
    dex
    bne .TimerLoop

    lda #0
    sta PF0
    sta PF1
    sta PF2

    ; --- 1 scanline gap ---
    sta WSYNC

    ; ====================================================================
    ; Line 2: Lives — 3 green squares on ONE line
    ; P0 with NUSIZ=$03 (3 copies, 16 clocks apart)
    ; $FF pattern = 8px squares, 8px gaps (one square between)
    ; Squares at X, X+16, X+32
    ; ====================================================================
    lda #$C6            ; green
    sta COLUP0
    lda #$03            ; NUSIZ0 = 3 copies close
    sta NUSIZ0
    lda #12             ; base X: squares at 12, 28, 44
    ldx #0
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    lda #$E0            ; 3-color-clock-wide square pattern
    sta GRP0
    ldy #5              ; 5 scanlines tall
.LivesLoop:
    sta WSYNC
    dey
    bne .LivesLoop
    lda #0
    sta GRP0
    sta NUSIZ0

    ; --- 1 scanline gap ---
    sta WSYNC

    ; ====================================================================
    ; Line 3: Bombs — 5 red squares on ONE line
    ; P0 (3 copies) + P1 (2 copies), all 16 clocks apart
    ; Squares at 12, 28, 44 (P0) + 60, 76 (P1)
    ; ====================================================================
    lda #$46            ; red
    sta COLUP0
    sta COLUP1
    lda #$03            ; NUSIZ0 = 3 copies
    sta NUSIZ0
    lda #$01            ; NUSIZ1 = 2 copies
    sta NUSIZ1
    lda #12             ; P0 at 12: copies at 12, 28, 44
    ldx #0
    jsr SetObjectXPos_b1
    lda #60             ; P1 at 60: copies at 60, 76
    ldx #1
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    lda #$E0            ; 3-color-clock-wide square pattern
    sta GRP0
    sta GRP1
    ldy #5
.BombsLoop:
    sta WSYNC
    dey
    bne .BombsLoop
    lda #0
    sta GRP0
    sta GRP1
    sta NUSIZ0
    sta NUSIZ1

    ; --- 3 scanline gap (moved score down to avoid bomb collision) ---
    sta WSYNC
    sta WSYNC
    sta WSYNC

    ; ====================================================================
    ; Line 4: Score — 48-pixel sprite technique
    ; Using burger8e.asm setup (known working in a complete game)
    ; NUSIZ0=3 (3 copies) + NUSIZ1=1 (2 copies) = 5 slots
    ; Digit 0 = blank (we only show 4 digits: 1,2,3,4)
    ; ====================================================================
    ldx #1
    stx VDELP0           ; vertical delay ON
    stx VDELP1
    ldx #0
    stx GRP0             ; clear player0
    stx GRP1             ; clear player1
    stx REFP0            ; no reflection
    stx REFP1
    ldx #3               ; 3 copies close
    stx NUSIZ0
    stx RESP0            ; player0 at pixel 54
    ldx #1               ; 2 copies close
    stx NUSIZ1
    stx RESP1            ; player1 at pixel 78
    ldx #$E0             ; HMP0 = +2 left
    stx HMP0
    ldx #0               ; HMP1 = 0
    stx HMP1
    lda #$0E             ; white
    sta COLUP0
    sta COLUP1
    sta WSYNC
    sta HMOVE

    ; Set up digit pointers — hardcoded low bytes for reliability
    lda #$FD             ; high byte of DigitGfx ($FD00)
    sta DigitPtr1+1
    sta DigitPtr2+1
    sta DigitPtr3+1
    sta DigitPtr4+1
    sta DigitPtr5+1
    lda #$00             ; DigitGfx+0 = $FD00 (digit 0 = blank row)
    sta DigitPtr1
    lda #$08             ; DigitGfx+8 = $FD08 (digit "1")
    sta DigitPtr2
    lda #$10             ; DigitGfx+16 = $FD10 (digit "2")
    sta DigitPtr3
    lda #$18             ; DigitGfx+24 = $FD18 (digit "3")
    sta DigitPtr4
    lda #$20             ; DigitGfx+32 = $FD20 (digit "4")
    sta DigitPtr5

    ; Clear sprites before loop
    lda #0
    sta GRP0
    sta GRP1

    ; Render loop — exact copy of burger8e.asm ScoreLoop
    ; 5 digit pointers: DigitPtr1=blank, DigitPtr2=1, DigitPtr3=2, DigitPtr4=3, DigitPtr5=4
    ldy #7
    sty RowCnt
.ScoreLoop:
    sta WSYNC
    lda (DigitPtr1),Y      ; load digit 0 (blank)
    sta GRP0               ; blank -> GRP0
    sta GRP1               ; blank -> GRP1, blank -> GRP0A
    lda (DigitPtr2),Y      ; load digit 1 ("1")
    sta GRP0               ; "1" -> GRP0, blank -> GRP1A
    lda (DigitPtr3),Y      ; load digit 2 ("2")
    tax                    ; X = "2"
    lda (DigitPtr4),Y      ; load digit 3 ("3")
    sta Temp               ; Temp = "3"
    lda (DigitPtr5),Y      ; load digit 4 ("4")
    ldy Temp               ; Y = "3"
    stx GRP1               ; "2" -> GRP1, "1" -> GRP0A
    sty GRP0               ; "3" -> GRP0, "2" -> GRP1A
    sta GRP1               ; "4" -> GRP1, "3" -> GRP0A
    sta GRP0               ; "4" -> GRP0 (final push)
    dec RowCnt
    ldy RowCnt
    bpl .ScoreLoop

    ; Clear sprites after score
    lda #0
    sta GRP0
    sta GRP1
    sta VDELP0
    sta VDELP1
    sta NUSIZ0
    sta NUSIZ1

    ; --- Restore cave kernel settings ---
    lda #$05            ; CTRLPF: reflect + priority (cave mode)
    sta CTRLPF
    lda #$10
    sta NUSIZ0
    lda #0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1

    ; ====================================================================
    ; Pad remaining scanlines to reach exactly 48 total
    ; Budget:
    ;   Top gap:  4 scanlines
    ;   Timer:    6 scanlines
    ;   Gap:      1
    ;   Lives:    7 (SetObjectXPos 1 + HMOVE 1 + render 5)
    ;   Gap:      1
    ;   Bombs:    8 (SetObjectXPos×2 2 + HMOVE 1 + render 5)
    ;   Gap:      3
    ;   Score:    12 (SetObjectXPos×2 2 + HMOVE 1 + sync 1 + render 8)
    ;   TOTAL:    4+6+1+7+1+8+3+12 = 42
    ;   Pad:      48 - 42 = 6
    ; ====================================================================
    ldx #6
.HudPad:
    sta WSYNC
    dex
    bne .HudPad

    ; --- Return to bank0 via fold-pad ---
    jmp $FC70

; ========================================================================
; SetObjectXPos — Andrew Davie algorithm (page-aligned table)
; X=0 positions P0, X=1 positions P1
; A = pixel position (0-159)
; ========================================================================
SetObjectXPos_b1:
    sta WSYNC
    sec
.Div15Loop:
    sbc #15
    bcs .Div15Loop
    tay
    lda fineAdjustTable_b1,Y
    sta HMP0,X
    sta RESP0,X
    rts

; ========================================================================
; Fold-pad stubs (byte-identical to bank0)
; ========================================================================
    .ds $FC68 - *, 0
    lda #1
    sta $1FF7
    jmp $F540

    .ds $FC70 - *, 0
    lda #0
    sta $1FF6
    jmp $F0A4

; ========================================================================
; Score digit font — 8x8 pixels, page-aligned for fast (zp),Y addressing
; 10 digits (0-9), 8 bytes each = 80 bytes
; MSB-first: bit7 = leftmost pixel
; ========================================================================
    org $FD00
DigitGfx:
    ; Digit 0
    .byte %0
    .byte %01111100
    .byte %11000110
    .byte %11000110
    .byte %11000110
    .byte %11000110
    .byte %11000110
    .byte %01111100

    ; Digit 1
    .byte %0
    .byte %00011000
    .byte %00011000
    .byte %00011000
    .byte %00011000
    .byte %01011000
    .byte %00111000
    .byte %00011000

    ; Digit 2
    .byte %0
    .byte %11111110
    .byte %11000000
    .byte %01100000
    .byte %00011000
    .byte %00000110
    .byte %11000110
    .byte %01111100

    ; Digit 3
    .byte %0
    .byte %11111100
    .byte %00000110
    .byte %00000110
    .byte %00111100
    .byte %00000110
    .byte %00000110
    .byte %11111100

    ; Digit 4
    .byte %0
    .byte %00001100
    .byte %00001100
    .byte %11111110
    .byte %11001100
    .byte %11001100
    .byte %11001100
    .byte %11000000

    ; Digit 5
    .byte %0
    .byte %11111100
    .byte %00000110
    .byte %00000110
    .byte %11111100
    .byte %11000000
    .byte %11000000
    .byte %11111110

    ; Digit 6
    .byte %0
    .byte %01111100
    .byte %11000110
    .byte %11000110
    .byte %11111100
    .byte %11000000
    .byte %11000010
    .byte %01111100

    ; Digit 7
    .byte %0
    .byte %01100000
    .byte %00110000
    .byte %00011000
    .byte %00001100
    .byte %00000110
    .byte %00000110
    .byte %11111110

    ; Digit 8
    .byte %0
    .byte %01111100
    .byte %11000110
    .byte %11000110
    .byte %01111100
    .byte %11000110
    .byte %11000110
    .byte %01111100

    ; Digit 9
    .byte %0
    .byte %01111100
    .byte %10000110
    .byte %00000110
    .byte %01111110
    .byte %11000110
    .byte %11000110
    .byte %01111100

; ========================================================================
; Fine-adjust table (page-aligned at $FF00)
; ========================================================================
    org $FF00
fineAdjustBegin_b1:
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
fineAdjustTable_b1 EQU fineAdjustBegin_b1 - %11110001

; ========================================================================
; Interrupt vectors
; ========================================================================
    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
