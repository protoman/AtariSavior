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
HMOVE   = $2B
HMCLR   = $2C
CXCLR   = $2D

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
    lda #80
    sta RoomX                   ; player starts near center
    lda #64
    sta RoomY                   ; player starts near center

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

    ; --- Position player sprite (GRP0) ---
    ; SetObjectXPos: coarse position via RESP0, fine via HMP0
    ; Simplified: just set RESP0 at a fixed position for now
    ldy RoomY
    jsr SetObjectYPos           ; vertical positioning via kernel timing

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
; HUD band: 48 scanlines (192-239) — grey background, no sprites
; ==============================================================================
; The HUD is a simple grey band below the cave. PF is cleared so no
; playfield artifacts appear. GRP0/GRP1 are zeroed.
; ==============================================================================
    lda #0
    sta PF0
    sta PF1
    sta PF2
    sta GRP0
    sta GRP1
    lda #COLOR_HUD_BG
    sta COLUBK

    ldx #48
.HudLoop:
    sta WSYNC
    dex
    bne .HudLoop

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
    ; After 4x LSR: D0=left, D1=right, D2=up, D3=down
    lda SWCHA
    lsr                         ; shift joystick 0 bits to D0-D3
    lsr
    lsr
    lsr
    sta Temp                    ; save shifted joystick bits

    ; --- Move left (D0) ---
    and #$01                    ; test D0 (left)
    bne .NotLeft
    lda RoomX
    cmp #PLAYER_MIN_X
    beq .NotLeft
    dec RoomX
.NotLeft:

    ; --- Move right (D1) ---
    lda Temp
    and #$02                    ; test D1 (right)
    bne .NotRight
    lda RoomX
    cmp #PLAYER_MAX_X
    beq .NotRight
    inc RoomX
.NotRight:

    ; --- Move up (D2) — jetpack ---
    lda Temp
    and #$04                    ; test D2 (up)
    bne .NotUp
    lda RoomY
    beq .NotUp
    dec RoomY
.NotUp:

    ; --- Move down (D3) — gravity ---
    lda Temp
    and #$08                    ; test D3 (down)
    bne .NotDown
    lda RoomY
    cmp #PLAYER_MAX_Y
    beq .NotDown
    inc RoomY
.NotDown:

    ; --- Wait for overscan timer ---
.WaitOverscan:
    lda INTIM
    bne .WaitOverscan

    jmp StartFrame

; ==============================================================================
; SetObjectYPos — vertical positioning for player sprite
; ==============================================================================
; Simplified vertical positioning: waits until the beam reaches RoomY,
; then the kernel's .Line loop picks up rendering from there.
; For now, this is a no-op — vertical position is handled by the kernel's
; scanline counter matching RoomY.
; ==============================================================================
SetObjectYPos:
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
; Interrupt vectors
; ==============================================================================
    .ds $FFFA - *, 0               ; pad to vectors at $FFFA

    .word GameStart                 ; NMI vector
    .word GameStart                 ; RESET vector
    .word GameStart                 ; IRQ vector
