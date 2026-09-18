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

; ZP variables for score rendering (HERO pattern)
PF0ScoreBuf = $B3       ; 5 bytes: PF0 values for each scanline row
PF1ScoreBuf = $B8       ; 5 bytes: PF1 values for each scanline row
PF2ScoreBuf = $C6       ; 5 bytes: PF2 values for each scanline row
Temp        = $AD       ; scratch variable
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

    ; --- Initialize score buffers for "1234" ---
    ; Hardcoded PFDigitFont row data for digits 1-4
    ; Digit 1: %00000010,%00000110,%00000010,%00000010,%00000111
    ; Digit 2: %00000111,%00000001,%00000111,%00000100,%00000111
    ; Digit 3: %00000111,%00000001,%00000111,%00000001,%00000111
    ; Digit 4: %00000101,%00000101,%00000111,%00000001,%00000001

    ; Digit 1 rows (for PF0 << 4)
    lda #%00100000     ; row 0: %00000010 << 4
    sta PF0ScoreBuf+0
    lda #%01100000     ; row 1: %00000110 << 4
    sta PF0ScoreBuf+1
    lda #%00100000     ; row 2
    sta PF0ScoreBuf+2
    lda #%00100000     ; row 3
    sta PF0ScoreBuf+3
    lda #%01110000     ; row 4: %00000111 << 4
    sta PF0ScoreBuf+4

    ; Digit 2 rows (for PF1 << 5)
    lda #%11100000     ; row 0: %00000111 << 5
    sta PF1ScoreBuf+0
    lda #%00100000     ; row 1: %00000001 << 5
    sta PF1ScoreBuf+1
    lda #%11100000     ; row 2
    sta PF1ScoreBuf+2
    lda #%10000000     ; row 3: %00000100 << 5
    sta PF1ScoreBuf+3
    lda #%11100000     ; row 4
    sta PF1ScoreBuf+4

    ; Digit 3 rows (for PF2 digit 3) | Digit 4 rows (for PF2 digit 4 << 4)
    ; Digit 3: %00000111, %00000001, %00000111, %00000001, %00000111
    ; Digit 4: %00000101, %00000101, %00000111, %00000001, %00000001
    ; PF2 = digit3 | (digit4 << 4)
    lda #$07|$50        ; row 0: $07 | ($05<<4) = $07|$50
    sta PF2ScoreBuf+0
    lda #$01|$50        ; row 1: $01 | ($05<<4) = $01|$50
    sta PF2ScoreBuf+1
    lda #$07|$70        ; row 2: $07 | ($07<<4) = $07|$70
    sta PF2ScoreBuf+2
    lda #$01|$10        ; row 3: $01 | ($01<<4) = $01|$10
    sta PF2ScoreBuf+3
    lda #$07|$10        ; row 4: $07 | ($01<<4) = $07|$10
    sta PF2ScoreBuf+4

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

    ; --- 1 scanline gap ---
    sta WSYNC

    ; ====================================================================
    ; Line 4: Score — PF-based from pre-computed buffers
    ; ====================================================================
    lda #$0E            ; white
    sta COLUPF

    ldy #0
.ScoreRender:
    lda PF0ScoreBuf,Y
    sta PF0
    lda PF1ScoreBuf,Y
    sta PF1
    lda PF2ScoreBuf,Y
    sta PF2
    sta WSYNC
    iny
    cpy #5
    bne .ScoreRender

    ; Clear PF
    sta WSYNC
    lda #0
    sta PF0
    sta PF1
    sta PF2

    ; --- Restore cave kernel settings ---
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
    ;   Lives:    7 (SetObjectXPos 1 + setup 1 + render 5)
    ;   Gap:      1
    ;   Bombs:    8 (SetObjectXPos×2 2 + setup 1 + render 5)
    ;   Gap:      1
    ;   Score:    5 render + 1 clear = 6
    ;   TOTAL:    4+6+1+7+1+8+1+6 = 34
    ;   Pad:      48 - 34 = 14
    ; ====================================================================
    ldx #14
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
; Score digit font — from bank0 (PFDigitFont + DigitTimes5)
; Pre-computed PF0ScoreBuf/PF1ScoreBuf/PF2ScoreBuf in ZP at $B3/$B8/$C6
; ========================================================================

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
