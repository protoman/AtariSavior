    processor 6502

; ==============================================================================
; savior kernel — HERO-style fixed-time rendering kernel
; ==============================================================================
; A from-scratch Atari 2600 kernel modeled after Activision's HERO.
;
; Architecture:
;   - 4K ROM at $F000-$FFFF (no bankswitching)
;   - Kernel renders 192 visible scanlines: 144 cave + 48 HUD
;   - Cave: 12 tile rows × 12 scanlines each
;   - Reflected playfield (CTRLPF D0=1) — symmetric cave
;   - GRP0 = player (square sprite), GRP1 = future objects
;   - Per-scanline kernel with WSYNC for stable timing
;   - PF registers written ONCE per tile row (TIA persists)
;   - Overscan: input handling + game logic
;
; Frame timing (262 scanlines @ 60Hz NTSC):
;   VSYNC     3 lines
;   VBLANK   37 lines  (game logic + positioning)
;   Kernel  192 lines  (144 cave + 48 HUD)
;   Overscan  30 lines (input + movement)
;   Total   262 lines
;
; Key difference from naive kernels:
;   The inner .Line loop is UNCONDITIONAL — no per-scanline branches for
;   sprite visibility. The player check uses a compare+branch that costs
;   16c (off-screen) or 19c (on-screen), both well within the 76-cycle
;   budget. PF registers are written once per tile row, not per scanline.
; ==============================================================================

; --- TIA write addresses ---
VSYNC   = $00
VBLANK  = $01
WSYNC   = $02
NUSIZ0  = $04
NUSIZ1  = $05
COLUP0  = $06
COLUP1  = $07
COLUPF  = $08
COLUBK  = $09
CTRLPF  = $0A
REFP0   = $0B
REFP1   = $0C
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
HMM0    = $22
HMM1    = $23
HMBL    = $24
VDELP0  = $25
VDELP1  = $26
HMOVE   = $2A
HMCLR   = $2B
CXCLR   = $2C

; --- TIA read addresses ---
SWCHA   = $0280
SWCHB   = $0282
INPT4   = $028C

; --- RIOT addresses ---
TIM64T  = $0296
INTIM   = $0284

; ==============================================================================
; Zero-page variables ($80-$FF)
; ==============================================================================
    seg.u Variables
    org $80

RoomX           byte            ; player X position (0-159)
RoomY           byte            ; player Y position (0-191)
Scanline        byte            ; current scanline counter (0-191)
LineCount       byte            ; scanlines remaining in current tile row
TileRow         byte            ; current tile row (0-11)
Grp0Ptr         byte            ; pointer to player sprite data (lo)
Grp0PtrHi       byte            ; pointer to player sprite data (hi)
Temp            byte            ; general scratch

; ==============================================================================
; Constants
; ==============================================================================
PLAYER_HEIGHT   = 8             ; sprite height in scanlines
TILE_ROWS       = 12            ; number of playable tile rows
LINES_PER_TILE  = 12            ; scanlines per tile row
HUD_ROWS        = 4             ; HUD tile rows (48 scanlines)
CAVE_LINES      = 144           ; TILE_ROWS × LINES_PER_TILE
VISIBLE_LINES   = 192           ; CAVE_LINES + (HUD_ROWS × LINES_PER_TILE)

; Player bounds (must stay inside cave walls)
PLAYER_MIN_X    = 32            ; inside left wall (wall ends at pixel 15)
PLAYER_MAX_X    = 120           ; inside right wall (wall starts at pixel 144)
PLAYER_MIN_Y    = 0
PLAYER_MAX_Y    = 135           ; CAVE_LINES - PLAYER_HEIGHT

; Colors (emulator-aware: hue<<4 | luma<<1)
COLOR_PLAYER    = $1E           ; hue 1 luma 7 = bright yellow
COLOR_CAVE_BG   = $00           ; black interior
COLOR_CAVE_WALL = $84           ; hue 8 luma 2 = dark grey-blue
COLOR_HUD_BG    = $06           ; hue 0 luma 3 = grey
COLOR_TIMER     = $1E           ; hue 1 luma 7 = yellow
COLOR_LIVES     = $C6           ; hue 12 luma 3 = green
COLOR_BOMBS     = $46           ; hue 4 luma 3 = red
COLOR_SCORE     = $0E           ; hue 0 luma 7 = white

; ==============================================================================
; ROM start — F6 bankswitch (16K, 4 banks × 4K)
; ==============================================================================
; Bank3 is the power-up bank. Its stub does:
;   lda #0 / sta $1FF6 → selects bank0
; Bank0 pad at $F000-$F004 ensures the jump into GameStart works.
; ==============================================================================
    seg code
    org $F000

    ; --- 5-byte bankswitching pad ---
    ; After bank3's stub selects us, CPU arrives here.
    ; We jump over the pad into the real init code.
    lda #0
    sta $1FF6                       ; ensure bank0 selected (idempotent)
    jmp GameStart                   ; jump over pad to init code

GameStart:
    sei                         ; disable interrupts
    cld                         ; clear decimal mode
    ldx #$FF
    txs                         ; stack pointer = $FF

    ; --- Clear zero-page RAM ---
    lda #0
    ldx #$80
.ClearZP:
    sta $00,X
    inx
    bne .ClearZP

    ; --- Initialize game state ---
    lda #100
    sta RoomX                   ; player starts in open area
    lda #64
    sta RoomY                   ; player starts near center

    ; --- Set player color ---
    lda #COLOR_PLAYER
    sta COLUP0

    ; --- Set playfield to reflected mode ---
    lda #$01
    sta CTRLPF                  ; D0=1 = reflect (left half mirrors to right)

; ==============================================================================
; Frame loop
; ==============================================================================
StartFrame:

; ------------------------------------------------------------------------------
; VSYNC (3 scanlines)
; ------------------------------------------------------------------------------
    lda #2
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #0
    sta VSYNC

; ------------------------------------------------------------------------------
; VBLANK (37 scanlines)
; ------------------------------------------------------------------------------
    lda #2
    sta VBLANK                  ; turn on VBLANK

    ; --- Set TIM64T for 37 scanlines of VBLANK ---
    ; 37 lines × 76 cycles/line ÷ 64 cycles/tick ≈ 44
    lda #43
    sta TIM64T

    ; --- Position player sprite horizontally ---
    lda RoomX
    ldx #0                      ; X=0 = player0
    jsr SetObjectXPos

    ; --- Apply horizontal motion during VBLANK ---
    sta WSYNC                   ; sync to next scanline (still in VBLANK)
    sta HMOVE                   ; latch fine motion — takes effect when VBLANK ends

    ; --- Wait for VBLANK timer ---
.WaitVBLANK:
    lda INTIM
    bne .WaitVBLANK

    ; --- Turn off VBLANK ---
    lda #0
    sta VBLANK

; ==============================================================================
; Kernel: 192 visible scanlines
; ==============================================================================
; Structure:
;   .Row (×12): set PF registers once per tile row, init scanline counter
;   .Line (×12): render one scanline — sprite check + loop control
;
; PF registers persist in TIA, so writing once per tile row is sufficient.
; The inner .Line loop has NO PF writes — only sprite rendering.
; ==============================================================================

    ; --- Reset TIA state for cave rendering ---
    ; HUD may have changed NUSIZ0/1, COLUP0/1 — must restore
    lda #$10                      ; NUSIZ0 = single copy (was 3 for HUD lives)
    sta NUSIZ0
    lda #$00                      ; NUSIZ1 = single copy (was 3 for HUD bombs)
    sta NUSIZ1
    lda #COLOR_PLAYER             ; restore player color (was green for HUD lives)
    sta COLUP0

    lda #0
    sta Scanline
    ldx #0                      ; tile row counter (0-11)

.Row:
    ; --- Set PF registers for this tile row (TIA persists) ---
    lda CavePF0,X
    sta PF0
    lda CavePF1,X
    sta PF1
    lda CavePF2,X
    sta PF2

    ; --- Set tile row colors ---
    lda #COLOR_CAVE_BG
    sta COLUBK
    lda #COLOR_CAVE_WALL
    sta COLUPF

    ; --- Init scanline counter for this row ---
    lda #LINES_PER_TILE
    sta LineCount

    ; --- Sync to next scanline ---
    sta WSYNC

.Line:
    ; --- Player sprite (GRP0) ---
    ; Check if current scanline is within player's 8-pixel range.
    ; off-screen: 16 cycles | on-screen: 19 cycles
    ; Both well within 76-cycle budget.
    lda Scanline
    sec
    sbc RoomY                   ; A = Scanline - RoomY
    cmp #PLAYER_HEIGHT
    bcs .NoSprite               ; branch if A >= PLAYER_HEIGHT (not visible)
    tay                         ; Y = sprite row index (0-7)
    lda PlayerSprite,Y          ; 4c — ZP indexed read
    jmp .WriteGrp0
.NoSprite:
    lda #0
.WriteGrp0:
    sta GRP0

    ; --- Loop control ---
    inc Scanline                ; advance scanline counter
    sta WSYNC                   ; wait for end of this scanline
    dec LineCount               ; decrement scanlines remaining in row
    bne .Line                   ; loop if more scanlines in this row

    ; --- Advance to next tile row ---
    inx
    cpx #TILE_ROWS
    bne .Row

; ==============================================================================
; HUD band: 48 scanlines (144-191)
; Layout: timer bar (8) + lives (8) + bombs (8) + score (8) + spacer (16)
; ==============================================================================

    ; --- Clear sprites and set background ---
    lda #0
    sta GRP0
    sta GRP1
    lda #COLOR_HUD_BG
    sta COLUBK

    ; ========================================================================
    ; Timer bar: 8 scanlines, ~70% width yellow PF bar
    ; ========================================================================
    lda #COLOR_TIMER
    sta COLUPF
    ldx #8
.HudTimer:
    lda #$00
    sta PF0
    lda #$3F
    sta PF1
    lda #$FF
    sta PF2
    sta WSYNC
    dex
    bne .HudTimer

    ; ========================================================================
    ; Spacer: 2 scanlines
    ; ========================================================================
    lda #COLOR_HUD_BG
    sta COLUBK
    lda #$00
    sta PF0
    sta PF1
    sta PF2
    ldx #2
.HudSpacer1:
    sta WSYNC
    dex
    bne .HudSpacer1

    ; ========================================================================
    ; Lives: 8 scanlines, 3 green squares (NUSIZ0 = 3 copies close)
    ; ========================================================================
    lda #COLOR_LIVES
    sta COLUP0
    lda #COLOR_HUD_BG
    sta COLUBK
    lda #$00
    sta PF0
    sta PF1
    sta PF2
    lda #$03                      ; NUSIZ0 = 3 copies close
    sta NUSIZ0
    lda #$00
    sta REFP0
    lda #$F0                      ; HMP0 = left 7
    sta HMP0
    sta WSYNC
    sta RESP0
    sta HMOVE
    ldx #8
.LivesSprite:
    lda #$F0                      ; 4-pixel-wide sprite
    sta GRP0
    sta WSYNC
    dex
    bne .LivesSprite
    lda #0
    sta GRP0

    ; ========================================================================
    ; Spacer: 2 scanlines
    ; ========================================================================
    ldx #2
.HudSpacer2:
    sta WSYNC
    dex
    bne .HudSpacer2

    ; ========================================================================
    ; Bombs: 8 scanlines, 5 red squares
    ; Pass 1 (4 lines): NUSIZ1 = 3 copies close → 3 squares
    ; Pass 2 (4 lines): NUSIZ1 = 2 copies close → 2 more squares
    ; ========================================================================
    lda #COLOR_BOMBS
    sta COLUP1
    lda #COLOR_HUD_BG
    sta COLUBK
    ; --- Pass 1: 3 copies close ---
    lda #$03                      ; NUSIZ1 = 3 copies close
    sta NUSIZ1
    lda #$10                      ; HMP1 = right 1
    sta HMP1
    sta WSYNC
    sta RESP1
    sta HMOVE
    ldx #4
.BombsPass1:
    lda #$F0
    sta GRP1
    sta WSYNC
    dex
    bne .BombsPass1
    ; --- Pass 2: 2 copies close for remaining 2 squares ---
    lda #$01                      ; NUSIZ1 = 2 copies close
    sta NUSIZ1
    lda #$C0                      ; HMP1 = right 4
    sta HMP1
    sta WSYNC
    sta RESP1
    sta HMOVE
    ldx #4
.BombsPass2:
    lda #$F0
    sta GRP1
    sta WSYNC
    dex
    bne .BombsPass2
    lda #0
    sta GRP1

    ; ========================================================================
    ; Spacer: 2 scanlines
    ; ========================================================================
    ldx #2
.HudSpacer3:
    sta WSYNC
    dex
    bne .HudSpacer3

    ; ========================================================================
    ; Score: 8 scanlines, "0000" via PF registers (5-line font, centered)
    ; ========================================================================
    lda #COLOR_SCORE
    sta COLUPF
    lda #COLOR_HUD_BG
    sta COLUBK
    ldy #0
    ldx #8
.HudScore:
    cpy #5
    bcs .HudScoreBlank
    lda ScoreFontPF0,Y
    sta PF0
    lda ScoreFontPF1,Y
    sta PF1
    lda ScoreFontPF2,Y
    sta PF2
    jmp .HudScoreDone
.HudScoreBlank:
    lda #$00
    sta PF0
    sta PF1
    sta PF2
.HudScoreDone:
    iny
    sta WSYNC
    dex
    bne .HudScore

    ; ========================================================================
    ; Spacer: remaining scanlines
    ; ========================================================================
    lda #COLOR_HUD_BG
    sta COLUBK
    lda #$00
    sta PF0
    sta PF1
    sta PF2
    ldx #10
.HudSpacer4:
    sta WSYNC
    dex
    bne .HudSpacer4

; ==============================================================================
; Overscan (30 scanlines) — input handling + game logic
; ==============================================================================
    lda #2
    sta VBLANK                  ; turn on VBLANK during overscan

    ; --- Set TIM64T for 30 scanlines ---
    ; 30 × 76 ÷ 64 ≈ 35
    lda #35
    sta TIM64T

    ; --- Read joystick ---
    ; SWCHA bits: D4=up, D5=down, D6=left, D7=right (0=pressed)
    ; After 4x LSR: D0=up, D1=down, D2=left, D3=right
    lda SWCHA
    lsr                         ; shift joystick 0 bits to D0-D3
    lsr
    lsr
    lsr
    sta Temp                    ; save shifted joystick bits

    ; --- Move up (D0) ---
    and #$01                    ; test D0 (up)
    bne .NotUp
    lda RoomY
    beq .NotUp
    dec RoomY
.NotUp:

    ; --- Move down (D1) ---
    lda Temp
    and #$02                    ; test D1 (down)
    bne .NotDown
    lda RoomY
    cmp #PLAYER_MAX_Y
    beq .NotDown
    inc RoomY
.NotDown:

    ; --- Move left (D2) ---
    lda Temp
    and #$04                    ; test D2 (left)
    bne .NotLeft
    lda RoomX
    cmp #PLAYER_MIN_X
    beq .NotLeft
    dec RoomX
.NotLeft:

    ; --- Move right (D3) ---
    lda Temp
    and #$08                    ; test D3 (right)
    bne .NotRight
    lda RoomX
    cmp #PLAYER_MAX_X
    beq .NotRight
    inc RoomX
.NotRight:

    ; --- Wait for overscan timer ---
.WaitOverscan:
    lda INTIM
    bne .WaitOverscan

    jmp StartFrame

; ==============================================================================
; SetObjectXPos — horizontal positioning via RESP0/HMP0
; ==============================================================================
; Andrew Davie session-24 routine:
; Rolls the divide-by-15 and the delay loop into one unit.
; The page-aligned fineAdjustTable ($FF00) guarantees every RESP0 write lands
; on the same clock grid, mapping the sprite 1:1 to pixel (0..159).
; Input: A = horizontal position (0-159 color clocks)
;        X = object selector (0 = player0, 1 = player1)
; ==============================================================================
SetObjectXPos subroutine
    sta WSYNC                   ; sync to start of scanline
    sec                         ; ensure carry flag
    jmp .Div15Loop              ; redirect to page $F1 (avoid bcs page-cross)
.Div15Loop:
    sbc #15                     ; coarse delay (15 clocks / 5 cycles per loop)
    bcs .Div15Loop              ; loop until carry clear (remainder in -15..-1)
    tay                         ; Y = remainder in -15..-1
    lda fineAdjustTable,Y       ; 5 cycles (page-cross guaranteed) -> fine offset
    sta HMP0,X                  ; store fine offset
    sta RESP0,X                 ; store coarse offset
    rts

; ==============================================================================
; Data tables
; ==============================================================================

; --- Player sprite: 8×8 square ---
; 4 pixels wide (bits 7-4), 8 rows tall
; Each byte: MSB = leftmost pixel
PlayerSprite:
    .byte %11110000             ; row 0
    .byte %11110000             ; row 1
    .byte %11110000             ; row 2
    .byte %11110000             ; row 3
    .byte %11110000             ; row 4
    .byte %11110000             ; row 5
    .byte %11110000             ; row 6
    .byte %11110000             ; row 7

; --- Cave playfield data ---
; 12 tile rows, reflected (left half only — TIA mirrors the right half)
;
; PF0 bits 7-4 → pixels 0-3 (leftmost)
; PF1 bits 7-0 → pixels 4-11 (reversed: bit7=pixel4, bit0=pixel11)
; PF2 bits 0-7 → pixels 12-19 (reversed: bit0=pixel12, bit7=pixel19)
;
; Cave shape (reflected, each half mirrors):
;   Row 0-3:  ####....................................####  (thick walls)
;   Row 4-7:  ##..........................................##  (thin walls)
;   Row 8-11: ###################....#####################  (bottom passage)

CavePF0:
    ; Row 0:    $F0 = pixels 0-3 ON (solid ceiling)
    ; Row 1-3:  $F0 = pixels 0-3 ON (4px wall)
    ; Row 4-7:  $30 = pixels 0-1 ON (2px wall, PF0 reversed: bit4=px0,bit5=px1)
    ; Row 8-11: $F0 = pixels 0-3 ON (19px wall)
    .byte $F0                       ; Row 0: solid
    .byte $F0, $F0, $F0             ; Row 1-3: 4px wall
    .byte $30, $30, $30, $30       ; Row 4-7: 2px wall
    .byte $F0, $F0, $F0, $F0       ; Row 8-11: 19px wall

CavePF1:
    ; Row 0:    $FF = all ON (solid ceiling)
    ; Row 1-3:  $00 = all OFF
    ; Row 4-7:  $00 = all OFF
    ; Row 8-11: $FF = all ON (19px wall)
    .byte $FF                       ; Row 0: solid
    .byte $00, $00, $00             ; Row 1-3: open
    .byte $00, $00, $00, $00       ; Row 4-7: open
    .byte $FF, $FF, $FF, $FF       ; Row 8-11: wall

CavePF2:
    ; Row 0:    $FF = all ON (solid ceiling)
    ; Row 1-3:  $00 = all OFF
    ; Row 4-7:  $00 = all OFF
    ; Row 8-11: $7F = pixels 12-18 ON (19px wall, pixel19 OFF for gap)
    .byte $FF                       ; Row 0: solid
    .byte $00, $00, $00             ; Row 1-3: open
    .byte $00, $00, $00, $00       ; Row 4-7: open
    .byte $3F, $3F, $3F, $3F       ; Row 8-11: wall (2px gap at center)

; ==============================================================================
; Score font data: "0000" rendered as 5-line PF patterns
; Each digit is 4px wide with 1px gaps between digits:
;   Line 0: ####.####.####.####.  (top)
;   Line 1: #..#.#..#.#..#.#..#.  (sides)
;   Line 2: #..#.#..#.#..#.#..#.  (sides)
;   Line 3: #..#.#..#.#..#.#..#.  (sides)
;   Line 4: ####.####.####.####.  (bottom)
; ==============================================================================
ScoreFontPF0:
    .byte $F0                       ; Line 0: pixels 0-3 ON
    .byte $90                       ; Line 1: pixels 0,3 ON
    .byte $90                       ; Line 2: pixels 0,3 ON
    .byte $90                       ; Line 3: pixels 0,3 ON
    .byte $F0                       ; Line 4: pixels 0-3 ON

ScoreFontPF1:
    .byte $7B                       ; Line 0: pixels 5-8 ON, 10-11 ON
    .byte $4A                       ; Line 1: pixels 5,8,10 ON
    .byte $4A                       ; Line 2: pixels 5,8,10 ON
    .byte $4A                       ; Line 3: pixels 5,8,10 ON
    .byte $7B                       ; Line 4: pixels 5-8 ON, 10-11 ON

ScoreFontPF2:
    .byte $7D                       ; Line 0: pixels 12-13,15-18 ON
    .byte $4C                       ; Line 1: pixels 13,15,18 ON
    .byte $4C                       ; Line 2: pixels 13,15,18 ON
    .byte $4C                       ; Line 3: pixels 13,15,18 ON
    .byte $7D                       ; Line 4: pixels 12-13,15-18 ON

; ==============================================================================
; Fine-adjust table for SetObjectXPos — MUST be page-aligned ($xx00)
; ==============================================================================
; The indexed load `lda fineAdjustTable,Y` must always cross a page boundary
; to guarantee 5-cycle timing. Placed at $FF00 (top of last page).
; Y = remainder from div15 loop (-15..-1), maps to HMP0 value.
; ==============================================================================
    org $FF00
fineAdjustBegin:
    .byte %01110000               ; left 7
    .byte %01100000               ; left 6
    .byte %01010000               ; left 5
    .byte %01000000               ; left 4
    .byte %00110000               ; left 3
    .byte %00100000               ; left 2
    .byte %00010000               ; left 1
    .byte %00000000               ; no movement
    .byte %11110000               ; right 1
    .byte %11100000               ; right 2
    .byte %11010000               ; right 3
    .byte %11000000               ; right 4
    .byte %10110000               ; right 5
    .byte %10100000               ; right 6
    .byte %10010000               ; right 7
fineAdjustTable EQU fineAdjustBegin - %11110001   ; = fineAdjustBegin - 241

; ==============================================================================
; Interrupt vectors
; ==============================================================================
    .ds $FFFA - *, 0               ; pad to vectors at $FFFA

    .word GameStart                 ; NMI vector
    .word GameStart                 ; RESET vector
    .word GameStart                 ; IRQ vector
