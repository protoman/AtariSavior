    processor 6502
; ==============================================================================
; bank1 — HUD rendering + 6-digit score (F6 bankswitch, $F000-$FFFF)
; ==============================================================================
; Follows HERO/comparison pattern exactly:
; - GRP0/GRP1 for indicator sprites (lives, bombs)
; - 48-pixel sprite technique for score (NUSIZ copies + VDELP cross-buffer)
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
PlayerLives = $AC
BarLevel = $AE
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

; ZP variables for score rendering (48-pixel sprite technique)
scorePtr1   = $E0       ; pointer to digit 1 font data (hundred-thousands)
scorePtr2   = $E2       ; pointer to digit 2 font data (ten-thousands)
scorePtr3   = $E4       ; pointer to digit 3 font data (thousands)
scorePtr4   = $E6       ; pointer to digit 4 font data (hundreds)
scorePtr5   = $E8       ; pointer to digit 5 font data (tens)
scorePtr6   = $EA       ; pointer to digit 6 font data (ones)
scbrdCnt    = $EC       ; score render loop counter (7..0)
scbrdTmp    = $ED       ; mid-scanline temp cache
Temp        = $AD       ; scratch variable
ScoreTh     = $BF       ; score thousands digit (must match bank0)
ScoreHu     = $C0       ; score hundreds digit
ScoreTe     = $C1       ; score tens+ones packed BCD
ScoreOn     = $C2       ; score ones digit (unused by game, available)

INPT4       = $0C       ; fire button (active low, bit 7)

    ; --- Top gap: 4 scanlines (lower HUD elements) ---
    ldx #4
.TopGap:
    sta WSYNC
    dex
    bne .TopGap

    ; ====================================================================
    ; Ball position at yellow/red boundary (RESPBL/HMBL via X=4)
    ; SetObjectXPos: HMP0+4=$24=HMBL, RESP0+4=$14=RESPBL
    ; +2 scanlines (SetObjectXPos WSYNC + HMOVE) → pad 11→9
    ; ====================================================================
    ldy BarLevel
    lda BallXTable,Y
    ldx #4
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    lda #1              ; ENABL D0=1 (ball on)
    sta ENABL

    ; ====================================================================
    ; Line 1: Timer bar — PF body, mid-scanline COLUPF yellow→red
    ; PF0=$E0 margins (bit4 leftmost OFF), PF1/PF2=$FF. Each line: yellow,
    ; delay(BarLevel), red. A=table[B]; B=0 → all red; B=16 → tiny red right.
    ; Clear PF on the gap line (after WSYNC) so line 3 is not truncated.
    ; ====================================================================

    lda #0
    sta GRP0            ; clear cave player sprite
    sta NUSIZ0
    lda BarLevel        ; CTRLPF: reflect + priority + ball size = BarLevel&3
    and #3              ;   0→1clk, 1→2, 2→4, 3→8 (D4-D5)
    asl
    asl
    asl
    asl
    ora #$05            ; D0 reflect + D2 priority
    sta CTRLPF
    lda #$1C            ; pre-set yellow (setup line must not keep wall color)
    sta COLUPF
    lda #$E0            ; margins (bit 4 = leftmost 4 clocks OFF)
    sta PF0
    lda #$FF
    sta PF1
    sta PF2

    ldx #3
.TimerLoop:
    sta WSYNC
    lda #$1C            ; yellow (hue 1, luma 6)
    sta COLUPF
    ldy BarLevel        ; 0-16
    lda BarDelayTable,Y ; delay iterations A (0..10)
    beq .BarRed         ; A=0 → immediate red (all red)
    tay
.BarDelay:
    dey                 ; 2c
    bne .BarDelay       ; 3c taken / 2c last → 5A-1
    ; red@ = 16 + (5A-1) + 5 = 5A+20; total ≤75 (A=10)
.BarRed:
    lda #$44            ; red (hue 4, luma 2)
    sta COLUPF
    dex
    bne .TimerLoop

    ; --- gap: end bar line 3, clear PF + ball during gap HBLANK ---
    sta WSYNC
    lda #0
    sta PF0
    sta PF1
    sta PF2
    sta ENABL           ; ball off after bar

    ; ====================================================================
    ; Line 2: Lives — green squares, count based on PlayerLives
    ; P0 with NUSIZ based on lives: $03=3 copies, $01=2, $00=1
    ; ====================================================================
    lda PlayerLives
    beq .NoLives                ; 0 lives = skip
    cmp #3
    bne .LivesNot3
    lda #$03                    ; 3 copies close
    jmp .LivesSetNusiz
.LivesNot3:
    cmp #2
    bne .LivesNot2
    lda #$01                    ; 2 copies close
    jmp .LivesSetNusiz
.LivesNot2:
    lda #$00                    ; 1 copy
.LivesSetNusiz:
    sta NUSIZ0
    lda #$C6                    ; green
    sta COLUP0
    lda #12                     ; base X
    ldx #0
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    lda #$E0                    ; 3-color-clock-wide square pattern
    sta GRP0
    ldy #5                      ; 5 scanlines tall
.LivesLoop:
    sta WSYNC
    dey
    bne .LivesLoop
    lda #0
    sta GRP0
    sta NUSIZ0
    jmp .LivesDone
.NoLives:
    lda #0
    sta GRP0
    sta NUSIZ0
    ldy #5
.LivesBlankLoop:
    sta WSYNC
    dey
    bne .LivesBlankLoop
    sta WSYNC            ; match lives path: SetObjectXPos + HMOVE
    sta WSYNC
.LivesDone:

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
    ; Line 4: Score — 6-digit test ("012389") — 48-pixel sprite technique
    ; NUSIZ0=3 (3 copies close) + NUSIZ1=3 (3 copies close)
    ; Interleaved: P0c1 P1c1 P0c2 P1c2 P0c3 P1c3 = 6 digit slots
    ; VDELP0=1, VDELP1=1 for cross-buffer pipeline
    ; ====================================================================

    ; --- Setup sprites ---
    lda #$0E             ; white
    sta COLUP0
    sta COLUP1
    lda #3               ; NUSIZ = 3 copies close
    sta NUSIZ0
    sta NUSIZ1
    lda #1               ; VDELP = ON (cross-buffer active)
    sta VDELP0
    sta VDELP1
    ; Flush both VDELP buffers + live registers to 0.
    ; Without this, stale buffer data from previous frame shows as
    ; white ghost copies during the positioning scanlines.
    lda #0
    sta GRP0             ; GRP0A (buffer) = 0
    sta GRP1             ; GRP1A (buffer) = 0, GRP0 live = GRP0A = 0
    sta GRP0             ; GRP1 live = GRP1A = 0
    sta REFP0
    sta REFP1

    ; --- Position P0 and P1 for interleaved 6-digit layout ---
    ; P0 at pixel 60, P1 at pixel 68 (shifted 4px right to fix pipeline timing)
    lda #60
    ldx #0
    jsr SetObjectXPos_b1
    lda #68
    ldx #1
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE

    ; --- Initialize score to 0 on first frame ---
    lda Temp
    bne .scoreInitDone
    inc Temp
    lda #0
    sta ScoreTh
    sta ScoreHu
    lda #$00
    sta ScoreTe
.scoreInitDone:

    ; --- Fire button: +50 BCD (same logic as bank0 collision code) ---
    lda INPT4
    bmi .noFire
    lda ScoreTe
    clc
    adc #$50              ; add 50 BCD
    cmp #$a0              ; overflow past 99?
    bcc .scoreDone        ; no → store and done
    sbc #$a0              ; wrap ScoreTe
    inc ScoreHu           ; carry to hundreds
    lda ScoreHu
    cmp #$a0              ; overflow past 99?
    bcc .scoreDone        ; no → store and done
    sbc #$a0              ; wrap ScoreHu
    inc ScoreTh           ; carry to thousands
.scoreDone:
    sta ScoreTe
.noFire:

    ; --- Set up 6 digit pointers ---
    ; Font at $FD00, each digit = 8 bytes, offset = digit * 8
    ; ScoreTh/Hu = single digits (0-9), ScoreTe = packed BCD (tens*16+ones)
    ; Display: ScoreTh ScoreHu tens ones blank blank

    ; High bytes first (all $FD)
    lda #>DigitGfx
    sta scorePtr1+1
    sta scorePtr2+1
    sta scorePtr3+1
    sta scorePtr4+1
    sta scorePtr5+1
    sta scorePtr6+1

    ; scorePtr1 = ScoreTh * 8
    lda ScoreTh
    asl
    asl
    asl
    sta scorePtr1

    ; scorePtr2 = ScoreHu * 8
    lda ScoreHu
    asl
    asl
    asl
    sta scorePtr2

    ; scorePtr3 = (ScoreTe >> 4) * 8  (tens digit)
    lda ScoreTe
    lsr
    lsr
    lsr
    lsr                   ; tens digit in low nibble
    asl
    asl
    asl
    sta scorePtr3

    ; scorePtr4 = (ScoreTe & $0F) * 8  (ones digit)
    lda ScoreTe
    and #$0F
    asl
    asl
    asl
    sta scorePtr4

    ; scorePtr5..6 = blank (digit "0", offset $00)
    lda #0
    sta scorePtr5
    sta scorePtr6

    ; --- Clear sprites before loop (3-write pattern for VDELP) ---
    lda #0
    sta GRP0
    sta GRP1
    sta GRP0

    ; ====================================================================
    ; 8-scanline render loop (exactly 71 cycles + WSYNC = 74 per line)
    ; Proven kernel from score48pix.asm
    ; ====================================================================
    ldy #7
    sty scbrdCnt
.ScoreLoop:
    ldy <scbrdCnt          ; 3c
    lda (scorePtr6),Y      ; 5c — pre-load LAST digit (digit 6)
    tax                    ; 2c — cache in X
    sta WSYNC              ; 3c
    lda (scorePtr1),Y      ; 5c — load digit 1
    sta.w GRP0             ; 4c — digit 1 -> GRP0A buffer
    lda (scorePtr2),Y      ; 5c — load digit 2
    sta GRP1               ; 3c — digit 2 -> GRP1A, digit 1 live on P0c1
    lda (scorePtr3),Y      ; 5c — load digit 3
    sta GRP0               ; 3c — digit 3 -> GRP0A, digit 2 live on P1c1
    lda (scorePtr4),Y      ; 5c — load digit 4
    sta <scbrdTmp          ; 3c — cache digit 4
    lda (scorePtr5),Y      ; 5c — load digit 5
    ldy <scbrdTmp          ; 3c — Y = digit 4
    sty GRP1               ; 3c — digit 4 -> GRP1A, digit 3 live on P0c2
    sta GRP0               ; 3c — digit 5 -> GRP0A, digit 4 live on P1c2
    stx GRP1               ; 3c — digit 6 -> GRP1A, digit 5 live on P0c3
    stx GRP0               ; 3c — digit 6 -> GRP0A, digit 6 live on P1c3
    dec <scbrdCnt          ; 5c
    bne .ScoreLoop         ; 3c

    ; --- Cleanup ---
    lda #0
    sta GRP0
    sta GRP1
    sta NUSIZ0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1

    ; --- Restore cave kernel settings ---
    lda #$05            ; CTRLPF: reflect + priority (cave mode)
    sta CTRLPF
    lda #0
    sta NUSIZ0
    lda #0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1

    ; ====================================================================
    ; Pad remaining scanlines to reach exactly 48 total
    ; Path A (PlayerLives > 0) — execution count:
    ;   Top gap:  4
    ;   Ball pos: 1 SetObjectXPos + 1 HMOVE = 2
    ;   Timer:    3 loop + 1 gap = 4
    ;   Lives:    1 SetObjectXPos + 1 HMOVE + 5 render + 1 gap = 8
    ;   Bombs:    2 SetObjectXPos + 1 HMOVE + 5 render + 3 gap = 11
    ;   Score:    2 SetObjectXPos + 1 HMOVE + 7 ScoreLoop = 10
    ;   Subtotal: 4+2+4+8+11+10 = 39
    ;   Pad:      48 - 39 = 9
    ; .NoLives blank path pads +2 WSYNC so both paths total 48.
    ; ====================================================================
    ldx #9
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
    jmp $F107           ; Overscan in bank0 (must match bank0 ToGameStub)

; Bar delay iterations A(B)=round(B*10/16), monotonic 0..10
; red@ = 5A+20 (A>0); total loop ≤75c (A=10). B≥1 always writes red.
; DATA — not in execution path.
BarDelayTable:          ; B=0..16 → A
    .byte 0
    .byte 1,1,2,2,3,4,4,5,6,6,7,8,8,9,9,10

; Ball X at yellow/red boundary: px=(red@-23)*160/53, clamped 4..155
BallXTable:             ; B=0..16
    .byte 4             ; B=0 all red → left edge of body
    .byte 6,6,21,21,36,51,51,66,82,82,97,112,112,127,127,142

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
