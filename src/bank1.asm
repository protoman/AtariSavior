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
DigitPtr1   = $89       ; pointer to digit 0 font data
DigitPtr2   = $8B       ; pointer to digit 1 font data
DigitPtr3   = $8D       ; pointer to digit 2 font data
DigitPtr4   = $8F       ; pointer to digit 3 font data
DigitPtr5   = $91       ; pointer to digit 4 font data
DigitPtr6   = $93       ; pointer to digit 5 font data
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
    ; EXACT match to score48pix.asm setup timing
    ; ====================================================================
    sta WSYNC            ; sync to start of scanline
    lda #0
    sta REFP0
    sta REFP1
    lda #$01
    sta CTRLPF
    lda #$0E            ; white
    sta COLUP0
    sta COLUP1
    lda #$10            ; HMP0 = -1
    sta HMP0
    lda #$20            ; HMP1 = -2
    sta HMP1
    lda #$03            ; NUSIZ = 3 copies close
    sta NUSIZ0
    sta NUSIZ1
    sta RESP0            ; RESP0 at cycle 40
    sta RESP1            ; RESP1 at cycle 43
    sta VDELP0           ; vertical delay ON
    sta VDELP1
    sta WSYNC
    sta HMOVE

    ; Set up digit pointers
    lda #>DigitGfx
    sta DigitPtr1+1
    sta DigitPtr2+1
    sta DigitPtr3+1
    sta DigitPtr4+1
    sta DigitPtr5+1
    sta DigitPtr6+1
    lda #<(DigitGfx + (0*8))
    sta DigitPtr1
    lda #<(DigitGfx + (1*8))
    sta DigitPtr2
    lda #<(DigitGfx + (2*8))
    sta DigitPtr3
    lda #<(DigitGfx + (3*8))
    sta DigitPtr4
    lda #<(DigitGfx + (4*8))
    sta DigitPtr5
    lda #<(DigitGfx + (0*8))
    sta DigitPtr6

    ; Clear sprites before loop
    lda #0
    sta GRP0
    sta GRP1
    sta WSYNC           ; sync before render loop

    ; Render loop — 48-pixel sprite technique
    ldy #7
    sty RowCnt
.ScoreLoop:
    ldy RowCnt             ; 3c
    lda (DigitPtr6),Y      ; 5c — Load digit 5 (blank)
    tax                    ; 2c — X = blank
    sta WSYNC              ; 3c — start of scanline
    lda (DigitPtr1),Y      ; 5c — Load digit 0
    sta.w GRP0             ; 4c — Buffer digit 0
    lda (DigitPtr2),Y      ; 5c — Load digit 1
    sta GRP1               ; 3c — Buffer digit 1
    lda (DigitPtr3),Y      ; 5c — Load digit 2
    sta GRP0               ; 3c — Buffer digit 2
    lda (DigitPtr4),Y      ; 5c — Load digit 3
    sta Temp               ; 3c — Cache digit 3
    lda (DigitPtr5),Y      ; 5c — Load digit 4
    ldy Temp               ; 3c — Y = digit 3
    stx GRP1               ; 3c — Buffer blank (digit 5)
    sty GRP0               ; 3c — Buffer digit 3
    sta GRP1               ; 3c — Buffer digit 4
    sta GRP0               ; 3c — Final push
    dec RowCnt             ; 5c
    ldy RowCnt             ; 3c
    bpl .ScoreLoop         ; 2c

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
