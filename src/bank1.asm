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
PF2ScoreBuf = $C6       ; 5 bytes: PF2 values for each scanline row (3x5 font)
    Temp        = $AD       ; scratch variable
ScoreTh     = $C2       ; score thousands digit
ScoreHu     = $C3       ; score hundreds digit
ScoreTe     = $C4       ; score tens digit
ScoreOn     = $C5       ; score ones digit

    ; --- Score PF buffers (3×5 font, temporary until 48px sprite implementation) ---
    ; PF0: digit1 << 4 (reversed bits), PF1: (digit2 << 5) | (digit3 << 1), PF2: digit4 reversed
    ; Digit 1=1, Digit 2=2, Digit 3=3, Digit 4=4

    ; PF0 (digit1 reversed <<4): %010→$20, %011→$30, %010→$20, %010→$20, %111→$70
    lda #$20
    sta PF0ScoreBuf+0
    lda #$30
    sta PF0ScoreBuf+1
    lda #$20
    sta PF0ScoreBuf+2
    lda #$20
    sta PF0ScoreBuf+3
    lda #$70
    sta PF0ScoreBuf+4

    ; PF1 (digit2<<5 | digit3<<1): $EE,$22,$EE,$82,$EE
    lda #$EE
    sta PF1ScoreBuf+0
    lda #$22
    sta PF1ScoreBuf+1
    lda #$EE
    sta PF1ScoreBuf+2
    lda #$82
    sta PF1ScoreBuf+3
    lda #$EE
    sta PF1ScoreBuf+4

    ; PF2 (digit4 reversed): %101→$05, %101→$05, %111→$07, %100→$04, %100→$04
    lda #$05
    sta PF2ScoreBuf+0
    lda #$05
    sta PF2ScoreBuf+1
    lda #$07
    sta PF2ScoreBuf+2
    lda #$04
    sta PF2ScoreBuf+3
    lda #$04
    sta PF2ScoreBuf+4

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
    ; Line 4: Score — PF0+PF1+PF2 for "1234" (bumbershootsoft method)
    ; CTRLPF=$02: SCORE mode — left half uses COLUP0, right half uses COLUP1
    ; COLUP1 = background color to hide right-half duplicate
    ; ====================================================================
    ; Setup CTRLPF/COLUP during current scanline (after gap WSYNC)
    ; Then WSYNC so PF writes land at start of NEXT scanline (during HBLANK)
    lda #$02            ; SCORE mode (avoids doubled score in reflected mode)
    sta CTRLPF
    lda #$0E            ; white for left half (COLUP0)
    sta COLUP0
    lda #$06            ; grey for right half (COLUP1 = background, hides duplicate)
    sta COLUP1
    sta WSYNC           ; sync — PF writes below land at start of next scanline

    ; PF writes must happen during HBLANK (first ~22 cycles) for clean rendering
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
    cpy #5              ; 5 rows for 3×5 font
    bne .ScoreRender
    ; Clear PF after last row
    lda #0
    sta PF0
    sta PF1
    sta PF2
    sta WSYNC

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
    ;   Lives:    7 (SetObjectXPos 1 + setup 1 + render 5)
    ;   Gap:      1
    ;   Bombs:    8 (SetObjectXPos×2 2 + setup 1 + render 5)
    ;   Gap:      1
    ;   Score:    5 render + 1 clear = 6
    ;   TOTAL:    4+6+1+7+1+8+1+6 = 34
    ;   Pad:      48 - 34 = 14
    ; ====================================================================
    ldx #11
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
