    processor 6502
; ==============================================================================
; bank1 — HUD rendering (F6 bankswitch)
; ==============================================================================
; Simple HUD: PF timer bar + sprite copies for lives/bombs + 13+2 score text

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
VDELP0  = $25
VDELP1  = $26
HMOVE   = $2A

; ZP for 13+2 score rendering
charp   = $80
chara   = $85
charb   = $8A
charc   = $8F
chard   = $94
chare   = $99
charf   = $9E
charg   = $A3

; 13+2 TEXTDISP macro
   MAC TEXTDISP
    lda #11
    sta NUSIZ1
    sta VDELP1
    lda charg+{1}
    sta ENAM0
    lsr
    sta ENAM1
    lsr
    sta ENABL
    lda charf+{1}
    sta GRP0
    lda chare+{1}
    sta GRP1
    nop
    lda chard+{1}
    sta GRP0
    lda charc+{1}
    ldy charb+{1}
    ldx chara+{1}
    sta GRP1
    sty GRP0
    stx GRP1
    sta VDELP1
    lda #4
    sta NUSIZ1
    lda charp+{1}
    sta GRP1
   ENDM

    org $F000

    .ds $F540 - *, 0

MenuMain:
    ; --- Grey background for HUD band ---
    lda #$06
    sta COLUBK

    ; --- Clear playfield ---
    lda #0
    sta PF0
    sta PF1
    sta PF2

    ; --- Clear all sprites ---
    sta GRP0
    sta GRP1

    ; ========================================
    ; LINE 1: Timer bar (PF-based, 6 scanlines)
    ; Centered yellow bar (~70% width)
    ; ========================================
    lda #$1E        ; yellow
    sta COLUPF

    ; In reflected mode: PF0 bits4-7=pixels0-3, PF1=pixels4-11, PF2=pixels12-19
    ; Mirror gives pixels20-27=PF2, 28-35=PF1, 36-39=PF0
    ; PF0=$00: outer 4px each side OFF
    ; PF1=$FF: pixels4-11 ON, mirrored 28-35 ON
    ; PF2=$FF: pixels12-19 ON, mirrored 20-27 ON
    ; Result: solid bar from pixel4 to pixel35 (~70% centered)
    lda #$00
    sta PF0
    lda #$FF
    sta PF1
    sta PF2

    ldx #6
.TimerLoop:
    sta WSYNC
    dex
    bne .TimerLoop

    ; Clear PF after bar
    lda #0
    sta PF0
    sta PF1
    sta PF2

    ; 2 scanline gap
    sta WSYNC
    sta WSYNC

    ; ========================================
    ; LINE 2: Lives — 3 green blocks (5 scanlines)
    ; ========================================
    lda #$C6        ; green
    sta COLUP0
    lda #$FF
    sta GRP0         ; solid block pattern

    ; NUSIZ0 = 3 copies close
    lda #$03
    sta NUSIZ0

    ; Position P0 using WSYNC + delay for coarse position
    ; Want 3 copies spread: ~32, ~48, ~64 color clocks from left
    ; RESP0 during HBLANK at cycle ~8 = color clock ~24
    sta WSYNC
    lda #$00        ; fine motion = 0
    sta HMP0
    ldx #8
.Resp0Delay:
    dex
    bne .Resp0Delay
    sta RESP0        ; coarse position ~24 color clocks
    sta WSYNC
    sta HMOVE

    ; 5 scanlines of green blocks
    ldx #5
.LivesLoop:
    sta WSYNC
    dex
    bne .LivesLoop

    ; Clear
    lda #0
    sta GRP0
    sta NUSIZ0

    ; 2 scanline gap
    sta WSYNC
    sta WSYNC

    ; ========================================
    ; LINE 3: Bombs — 3 red blocks (5 scanlines)
    ; ========================================
    lda #$46        ; red
    sta COLUP1
    lda #$FF
    sta GRP1         ; solid block pattern

    ; NUSIZ1 = 3 copies close
    lda #$03
    sta NUSIZ1

    ; Position P1 to the right of P0 lives
    sta WSYNC
    lda #$00
    sta HMP1
    ldx #8
.Resp1Delay:
    dex
    bne .Resp1Delay
    sta RESP1
    sta WSYNC
    sta HMOVE

    ; 5 scanlines of red blocks
    ldx #5
.BombLoop:
    sta WSYNC
    dex
    bne .BombLoop

    ; Clear
    lda #0
    sta GRP1
    sta NUSIZ1

    ; 2 scanline gap
    sta WSYNC
    sta WSYNC

    ; ========================================
    ; LINE 4: Skip score for now — just pad
    ; ========================================
    ldx #10
.ScorePad:
    sta WSYNC
    dex
    bne .ScorePad

    ; --- Clear sprites ---
    lda #0
    sta GRP0
    sta GRP1
    sta GRP0
    sta ENAM0
    sta ENAM1
    sta ENABL

    ; --- Restore cave kernel settings ---
    lda #$10
    sta NUSIZ0
    lda #0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1

    ; --- Pad remaining HUD scanlines ---
    ; Timer(6)+gap(2)+Lives(5)+gap(2)+Bombs(5)+gap(2)+Skip(10) = 32
    ; 48 - 32 = 16 remaining
    ldx #16
.PadLoop:
    sta WSYNC
    dex
    bne .PadLoop

    ; --- Return to bank0 via fold-pad at $FC70 ---
    jmp $FC70

; ==============================================================================
; Fold-pad stubs (byte-identical to bank0)
; ==============================================================================
    .ds $FC68 - *, 0
    lda #1
    sta $1FF7
    jmp $F540

    .ds $FC70 - *, 0
    lda #0
    sta $1FF6
    jmp $F0A4

; ==============================================================================
; Score slot data — "0000" pre-computed
; ==============================================================================
HudSlots_Score:
    .byte $00, $00, $00, $00, $00, $40, $A0, $A0
    .byte $A0, $40, $44, $AA, $AA, $AA, $44, $46
    .byte $A0, $A0, $A0, $40, $04, $0A, $0A, $0A
    .byte $04, $CE, $A8, $CC, $A8, $AE, $64, $8A
    .byte $8A, $8A, $64, $06, $08, $04, $02, $0C

; ==============================================================================
    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
