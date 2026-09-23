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
BAR_MAX = 120            ; full bar (60 frames/step × 120 = 120s)
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
DelayCnt    = $EE       ; bar delay A preloaded once per frame (bank1; ColupfBuf+7)
FineCnt     = $EF       ; bar fine delay cycles 0/2/3/4 (H3; bank1 only)
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
    ; PF0=$E0 margins (bit4 leftmost OFF), PF1/PF2=$FF.
    ; Full (BarLevel=BAR_MAX): pure yellow, no red write (no stripes).
    ; H3c: dual path — Fine=0 slim (no dispatch, ≤67c) / Fine≠0 (≤72c).
    ; red@ = 15*A + 3*Fine - 15; BallX = red@ (aligned, no desync).
    ; Clear PF on the gap line (after WSYNC) so line 3 is not truncated.
    ; ====================================================================

    lda #0
    sta GRP0            ; clear cave player sprite
    sta NUSIZ0
    lda #$05            ; CTRLPF: reflect + priority + 1-clock ball.
    sta CTRLPF          ;   ($00 had D0=0 → no reflect: right half REPEATS
                        ;    → center notch; also no PF priority)
    lda #$1C            ; pre-set yellow (setup line must not keep wall color)
    sta COLUPF
    lda #$E0            ; margins (bit 4 = leftmost 4 clocks OFF)
    sta PF0
    lda #$FF
    sta PF1
    sta PF2

    ldy BarLevel
    cpy #BAR_MAX
    bne .BarRedPath     ; not full → skips YellowOnly + pad (0 extra cycles)

.BarYellowOnly:         ; full bar: pure yellow, ~20c/line (no overrun)
    ldx #3
.YLoop:
    sta WSYNC
    lda #$1C
    sta COLUPF
    dex
    bne .YLoop
    jmp .BarGap

    ; H3b: +25B never-executed pad (bne already jumps over it). Shifts
    ; line-2 beq .R2 (f5f8+f5fc → f60c) off the F5→F6 page boundary
    ; (+1c taken = 3 clocks late red on middle bar line = horizontal
    ; stripes). Must NOT be a jmp in the taken path — that pushed setup
    ; to 78c (>76). +6 over .ds 19: branch+2 must reach f600.
    .ds 25

.BarRedPath:
    ; H3c: preload A + Fine; Y := red for sty (3c vs lda+sta 5c).
    lda BarDelayTable,Y
    sta DelayCnt
    lda BarFineTable,Y
    sta FineCnt
    ldy #$44            ; red (hue 4, luma 2) for sty COLUPF
    lda FineCnt
    bne .NotF0          ; F≠0 → check F=1
    ; --- Fine=0: slim, no pad (≤67c @A=11) ---
.BarRedF0:
    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF1
.BF1:
    dex
    bne .BF1
.RF1:
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF2
.BF2:
    dex
    bne .BF2
.RF2:
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF3
.BF3:
    dex
    bne .BF3
.RF3:
    sty COLUPF
    jmp .BarGap

.NotF0:
    cmp #1
    bne .BarRedFull     ; F=2,3,4 → dispatch
    ; --- Fine=1: slim + 2c nop/line (fills 3px gaps) ---
.BarRedF1:
    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF1n
.BF1n:
    dex
    bne .BF1n
.RF1n:
    nop                 ; +2c → +6 clocks vs F=0
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF2n
.BF2n:
    dex
    bne .BF2n
.RF2n:
    nop
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF3n
.BF3n:
    dex
    bne .BF3n
.RF3n:
    nop
    sty COLUPF
    jmp .BarGap

    ; --- Fine ∈ {2,3,4}: full dispatch, content ≤71c ---
.BarRedFull:
    sta WSYNC
    lda #$1C            ; yellow (hue 1, luma 6)
    sta COLUPF
    ldx DelayCnt        ; 3c, Z if A=0
    beq .Fine1          ; A=0 → fine only
.BD1:
    dex                 ; 2c
    bne .BD1            ; 3c taken / 2c last → 5A-1
.Fine1:
    ldx FineCnt         ; 3c (≠0 here)
    cpx #2              ; 2c
    beq .R1             ; Fine=2
    cpx #3              ; 2c
    beq .F31            ; Fine=3
    nop                 ; Fine=4
    nop
    jmp .R1
.F31:
    bit DelayCnt        ; 3c zp
    jmp .R1
.R1:
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .Fine2
.BD2:
    dex
    bne .BD2
.Fine2:
    ldx FineCnt
    cpx #2
    beq .R2
    cpx #3
    beq .F32
    nop
    nop
    jmp .R2
.F32:
    bit DelayCnt
    jmp .R2
.R2:
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .Fine3
.BD3:
    dex
    bne .BD3
.Fine3:
    ldx FineCnt
    cpx #2
    beq .R3
    cpx #3
    beq .F33
    nop
    nop
    jmp .R3
.F33:
    bit DelayCnt
    jmp .R3
.R3:
    sty COLUPF
    ; fall through to .BarGap

.BarGap:

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

; Bar H3c tables (B=0..120): content ≤71c (WSYNC 3c fits in 76).
; Paths (cycles after WSYNC → sty red): F=0 slim 12+5A; F=1 slim+nop 14+5A;
; F=2 full 20+5A; F=3 full 30+5A; F=4 full 31+5A (A=0 special-cased).
; pixel = 3*cycles-69; BallX = max(4,pixel) so ball == body edge (mono).
BarDelayTable:          ; B=0..120
    .byte 0,0,2,2,2,1,1,1,3,3,3,3,3,3,3,2
    .byte 2,2,0,0,0,0,0,0,4,4,4,1,1,1,1,1
    .byte 1,1,5,5,5,5,5,5,2,2,2,2,2,2,6,6
    .byte 6,6,6,6,6,3,3,3,3,3,3,7,7,7,7,7
    .byte 7,4,4,4,4,4,4,4,8,8,8,8,8,8,5,5
    .byte 5,5,5,5,9,9,9,9,9,9,9,6,6,6,6,6
    .byte 6,10,10,10,10,10,10,7,7,7,7,7,7,11,11,11
    .byte 11,11,11,11,8,8,8,8,8

BarFineTable:           ; B=0..120; ∈{0,1,2,3,4}; path = f(F)
    .byte 0,0,1,1,1,2,2,2,0,0,0,0,1,1,1,2
    .byte 2,2,3,3,3,4,4,4,1,1,1,3,3,3,4,4
    .byte 4,4,0,0,0,1,1,1,3,3,3,4,4,4,0,0
    .byte 0,1,1,1,1,3,3,3,4,4,4,0,0,0,1,1
    .byte 1,3,3,3,4,4,4,4,0,0,0,1,1,1,3,3
    .byte 3,4,4,4,0,0,0,1,1,1,1,3,3,3,4,4
    .byte 4,0,0,0,1,1,1,3,3,3,4,4,4,0,0,0
    .byte 0,1,1,1,3,3,3,4,4

BallXTable:             ; B=0..120; = max(4, actual body red@); mono
    .byte 4,4,4,4,4,6,6,6,12,12,12,12,18,18,18,21
    .byte 21,21,27,27,27,30,30,30,33,33,33,36,36,36,39,39
    .byte 39,39,42,42,42,48,48,48,51,51,51,54,54,54,57,57
    .byte 57,63,63,63,63,66,66,66,69,69,69,72,72,72,78,78
    .byte 78,81,81,81,84,84,84,84,87,87,87,93,93,93,96,96
    .byte 96,99,99,99,102,102,102,108,108,108,108,111,111,111,114,114
    .byte 114,117,117,117,123,123,123,126,126,126,129,129,129,132,132,132
    .byte 132,138,138,138,141,141,141,144,144

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
    jmp $F103           ; Overscan in bank0 (must match bank0 ToGameStub)

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
