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
    ; Line 2: Lives — 3 green squares, each on its own scanline
    ; Individual RESP positioning for 4px gaps (HERO approach)
    ; ====================================================================
    lda #$C6            ; green
    sta COLUP0
    lda #$00            ; single copy
    sta NUSIZ0
    lda #$F0            ; 4-pixel-wide block pattern

    ; Life 1 at pixel 10
    ldx #10
    stx LifeX
    jsr RenderLifeIcon

    ; Life 2 at pixel 18 (10 + 4px block + 4px gap)
    ldx #18
    stx LifeX
    jsr RenderLifeIcon

    ; Life 3 at pixel 26 (18 + 8)
    ldx #26
    stx LifeX
    jsr RenderLifeIcon

    ; Clear sprites
    sta WSYNC
    lda #0
    sta GRP0

    ; --- 1 scanline gap ---
    sta WSYNC

    ; ====================================================================
    ; Line 3: Bombs — 5 red squares, each on its own scanline
    ; ====================================================================
    lda #$46            ; red
    sta COLUP0
    lda #$00            ; single copy
    sta NUSIZ0
    lda #$F0            ; 4-pixel-wide block pattern

    ; Bomb 1 at pixel 10
    ldx #10
    stx LifeX
    jsr RenderLifeIcon

    ; Bomb 2 at pixel 18
    ldx #18
    stx LifeX
    jsr RenderLifeIcon

    ; Bomb 3 at pixel 26
    ldx #26
    stx LifeX
    jsr RenderLifeIcon

    ; Bomb 4 at pixel 34
    ldx #34
    stx LifeX
    jsr RenderLifeIcon

    ; Bomb 5 at pixel 42
    ldx #42
    stx LifeX
    jsr RenderLifeIcon

    ; Clear sprites
    sta WSYNC
    lda #0
    sta GRP0

    ; --- 1 scanline gap ---
    sta WSYNC

    ; ====================================================================
    ; Line 4: Score "0000" — PF-based from pre-computed buffers
    ; (simplified: just render PF digits directly)
    ; ====================================================================
    lda #$0E            ; white
    sta COLUPF

    ldy #0
.ScoreRender:
    ; PF0 = ScoreTh digit pattern << 4
    ldx ScoreTh
    lda PFDigitFontPF0,X
    sta PF0
    ; PF1 = ScoreHu digit pattern << 5
    ldx ScoreHu
    lda PFDigitFontPF1,X
    sta PF1
    ; PF2 = ScoreTe | (ScoreOn << 4)
    ldx ScoreTe
    lda PFDigitFontPF2,X
    ldx ScoreOn
    ora PFDigitFontPF2Shifted,X
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

    ; ====================================================================
    ; Pad remaining scanlines (48 total: 7top+6bar+1gap+9lives+1gap+15bombs+1gap+5score+6pad)
    ; Lives: 3 icons × 3 scanlines = 9
    ; Bombs: 5 icons × 3 scanlines = 15
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
; RenderLifeIcon — render a single 4px-wide, 4px-tall icon
; LifeX = pixel position for this icon
; A = pattern ($F0 for blocks)
; ========================================================================
LifeX = $A8

RenderLifeIcon:
    ldx LifeX
    ldy #0
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    ; Render 3 scanlines
    ldy #3
.RenderLoop:
    sta WSYNC
    sta GRP0
    dey
    bne .RenderLoop
    rts

; ========================================================================
; Score digit font — PF-based (from comparison bank2)
; PFDigitFontPF0: digit pattern << 4 (for PF0 bits 4-7)
; PFDigitFontPF1: digit pattern << 5 (for PF1 bits)
; PFDigitFontPF2: digit pattern (for PF2 bits)
; PFDigitFontPF2Shifted: digit pattern << 4 (for second PF2 digit)
; ========================================================================
PFDigitFontPF0:
  .byte $70, $50, $70, $70, $50, $70, $70, $70, $70, $70  ; 0-9 << 4

PFDigitFontPF1:
  .byte $E0, $C0, $A0, $C0, $A0, $E0, $E0, $C0, $E0, $E0  ; 0-9 << 5

PFDigitFontPF2:
  .byte $07, $02, $07, $07, $05, $07, $07, $03, $07, $07  ; 0-9

PFDigitFontPF2Shifted:
  .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $00  ; 0-9 << 4

; Score ZP variables
ScoreTh = $C2
ScoreHu = $C3
ScoreTe = $C4
ScoreOn = $C5

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
