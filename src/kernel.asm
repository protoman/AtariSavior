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
PlayerDir       byte            ; sprite eye facing: FACING_RIGHT (0) or FACING_LEFT
Scanline        byte            ; current scanline counter (0-191)
LineCount       byte            ; scanlines remaining in current tile row
TileRow         byte            ; current tile row (0-11)
Grp0Ptr         byte            ; pointer to player sprite data (lo)
Grp0PtrHi       byte            ; pointer to player sprite data (hi)
Temp            byte            ; general scratch

; Collision ZP variables (from comparison/lo-a-rad-dragon/bank0.asm)
MapPtrLo        byte            ; pointer into rectangle list (low)
MapPtrHi        byte            ; pointer into rectangle list (high)
CollisionX      byte            ; scratch for mirror calc
CollisionCellX  byte            ; player max tile column
CollisionCellY  byte            ; player top tile row
CollisionEndX   byte            ; player min tile column
CollisionEndY   byte            ; player bottom tile row
RoomRectsLo     byte            ; pointer to room rectangle data (low)
RoomRectsHi     byte            ; pointer to room rectangle data (high)
RectCount       byte            ; rectangle loop counter

; Jetpack ZP variables
vyLo            byte            ; Y velocity low byte (subpixel; signed 16-bit, + = down)
vyHi            byte            ; Y velocity high byte (whole pixels per frame, signed)
PlayerYSub      byte            ; subpixel accumulator for Y velocity integration
JetPower        byte            ; jet thrust 0..JET_MAX; ramps +1/frame while Up is held
StepsLeft       byte            ; per-frame Y pixel steps remaining (vertical physics loop)

; Room management ZP variables
RoomNo          byte            ; current room index (0-based)
RoomPF0Lo       byte            ; pointer to current room's TilePF0 (low)
RoomPF0Hi       byte            ; pointer to current room's TilePF0 (high)
RoomPF1Lo       byte            ; pointer to current room's TilePF1 (low)
RoomPF1Hi       byte            ; pointer to current room's TilePF1 (high)
RoomPF2Lo       byte            ; pointer to current room's TilePF2 (low)
RoomPF2Hi       byte            ; pointer to current room's TilePF2 (high)
LevelPFDataLo   byte            ; pointer to level's RoomDataTable (low)
LevelPFDataHi   byte            ; pointer to level's RoomDataTable (high)
LevelConnLo     byte            ; pointer to level's RoomConnections (low)
LevelConnHi     byte            ; pointer to level's RoomConnections (high)

; Score ZP variables (shared with bank1 HUD — addresses MUST match)
ScoreTh         = $F0           ; score thousands digit (0-9) — moved to avoid PF1Buf overlap
ScoreHu         = $F1           ; score hundreds digit (0-9)
ScoreTe         = $F2           ; score tens digit (0-9)
ScoreOn         = $F3           ; score ones digit (0-9)
PF0ScoreBuf     = $B3           ; 5 bytes: PF0 values for score rows 0-4
PF1ScoreBuf     = $B8           ; 5 bytes: PF1 values for score rows 0-4
PF2ScoreBuf     = $C6           ; 5 bytes: PF2 values for score rows 0-4

; ==============================================================================
; Constants
; ==============================================================================
PLAYER_HEIGHT   = 8             ; sprite height in scanlines
PLAYER_WIDTH    = 4             ; sprite width in pixels
TILE_COLUMNS    = 20            ; columns per half (reflected playfield)
TILE_ROWS       = 12            ; number of playable tile rows
LINES_PER_TILE  = 12            ; scanlines per tile row
HUD_ROWS        = 4             ; HUD tile rows (48 scanlines)
CAVE_LINES      = 144           ; TILE_ROWS × LINES_PER_TILE
VISIBLE_LINES   = 192           ; CAVE_LINES + (HUD_ROWS × LINES_PER_TILE)

; Player bounds (must stay inside cave walls)
PLAYER_MIN_X    = 4             ; sprite flush with left edge (HERO)
PLAYER_MAX_X    = 163           ; sprite flush with right edge (HERO)
PLAYER_MIN_Y    = 0
PLAYER_MAX_Y    = 136           ; CAVE_LINES - PLAYER_HEIGHT + 1

; Jetpack physics constants (HERO-style)
GRAVITY         = $0008         ; gravity per frame (signed 16-bit, + = down)
JET_MAX         = $20           ; max jet thrust accumulator
MAX_FALL        = $0200         ; max fall speed (positive = down)



; Facing direction of the player sprite's eye
FACING_RIGHT    = 0
FACING_LEFT     = 1

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
    lda #L1_START_X
    sta RoomX
    lda #L1_START_Y
    sta RoomY

    ; --- Initialize room management pointers ---
    lda #<L1_RoomDataTable
    sta LevelPFDataLo
    lda #>L1_RoomDataTable
    sta LevelPFDataHi
    lda #<L1_RoomConnections
    sta LevelConnLo
    lda #>L1_RoomConnections
    sta LevelConnHi

    ; --- Load starting room ---
    lda #L1_START_ROOM
    jsr EnterRoom

    ; --- Set player color ---
    lda #COLOR_PLAYER
    sta COLUP0

    ; --- Set playfield to reflected mode + priority ---
    ; D0=1 = reflect (left half mirrors to right)
    ; D2=1 = playfield priority (player drawn BEHIND walls, like HERO)
    lda #$05
    sta CTRLPF

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
    lda L1_M1TilePF0,X
    sta PF0
    lda L1_M1TilePF1,X
    sta PF1
    lda L1_M1TilePF2,X
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
; Uses 13+2 sprite technique via bank1 (fold-pad trampoline)
; ==============================================================================

    ; --- Call bank1 for 13+2 HUD rendering via fold-pad at $FC68 ---
    ; The fold-pad at $FC68 has identical bytes in bank0 and bank1:
    ;   $FC68: lda #1 / sta $1FF7 / jmp $F540
    ; After sta $1FF7, CPU reads next instruction from bank1 at $FC6D.
    ; Bank1's $FC6D has the same jmp $F540 → seamless bank switch.
    jmp $FC68                   ; jump to fold-pad (switches to bank1, runs MenuMain)
    ; Bank1's MenuMain returns to bank0 via: lda #0 / sta $1FF6 / jmp $F0AC

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

; ------------------------------------------------------------------------------
; Vertical movement — HERO-style jetpack physics
; ------------------------------------------------------------------------------
; Gravity pulls down, holding Up fires jetpack (JetPower ramps with inertia).
; Velocity is integrated through PlayerYSub and walked pixel-by-pixel via
; StepDown/StepUp so collision stops flush at walls/doorways.
; ------------------------------------------------------------------------------
UpdateP0Vertical:
; --- Jet thrust accumulator: +1/frame while Up is held (cap JET_MAX),
;     -1/frame otherwise. The ramp gives the jet its initial inertia. ---
    lda #%00000001              ; test D0 (up, after 4x LSR)
    bit Temp
    bne .JetDecay
    lda #FACING_LEFT            ; facing up = left eye
    sta PlayerDir
    lda JetPower
    cmp #JET_MAX
    bcs .JetCapped
    clc
    adc #1
    jmp .JetSet
.JetCapped:
    lda #JET_MAX
.JetSet:
    sta JetPower
    jmp .Gravity
.JetDecay:
    lda JetPower
    beq .Gravity
    dec JetPower

; --- Physics: vy += GRAVITY (gravity), vy -= JetPower (jet thrust). ---
.Gravity:
    clc
    lda vyLo
    adc #<GRAVITY
    sta vyLo
    lda vyHi
    adc #>GRAVITY
    sta vyHi
    sec
    lda vyLo
    sbc JetPower
    sta vyLo
    lda vyHi
    sbc #0
    sta vyHi

; --- Clamp fall speed: down at MAX_FALL, up at -$0100. ---
    lda vyHi
    bmi .RiseClamp
    cmp #>MAX_FALL
    bcc .Integrate
    lda #>MAX_FALL
    sta vyHi
    lda #<MAX_FALL
    sta vyLo
    jmp .Integrate
.RiseClamp:
    cmp #$ff                  ; vyHi == $ff -> |vy| <= $0100, keep it
    bcs .Integrate
    lda #$ff
    sta vyHi
    lda #$00
    sta vyLo                  ; vy = -$0100

; --- Signed whole-pixel displacement this frame = carry + vyHi. ---
.Integrate:
    clc
    lda PlayerYSub
    adc vyLo
    sta PlayerYSub
    lda #0
    adc vyHi
    beq .NoVMove
    bmi .UpSteps
    sta StepsLeft             ; positive = falling (down)
.JFalling:
    jsr StepDown
    dec StepsLeft
    bne .JFalling
    jmp .NoVMove
.UpSteps:
    eor #$ff
    clc
    adc #1                    ; magnitude of upward displacement
    sta StepsLeft
.JRising:
    jsr StepUp
    dec StepsLeft
    bne .JRising
.NoVMove:
    jmp CheckP0Left

; ------------------------------------------------------------------------------
; Horizontal movement (left/right) — 1 px/frame + collision
; ------------------------------------------------------------------------------
CheckP0Left:
    lda #%00000100              ; test D2 (left)
    bit Temp
    bne CheckP0Right
    lda #FACING_LEFT
    sta PlayerDir               ; turn the eye left, even if the move is blocked
    lda RoomX
    cmp #PLAYER_MIN_X
    beq .ExitLeft               ; at left edge -> room exit
    dec RoomX
    jsr PlayerHitsMap
    bcc .LeftDone
    inc RoomX                   ; collision -> undo
.LeftDone:
    jmp CheckP0Right
.ExitLeft:
    jsr ExitRoomLeft
    jmp CheckP0Right

CheckP0Right:
    lda #%00001000              ; test D3 (right)
    bit Temp
    bne EndInputCheck
    lda #FACING_RIGHT
    sta PlayerDir               ; turn the eye right, even if the move is blocked
    lda RoomX
    cmp #PLAYER_MAX_X
    beq .ExitRight              ; at right edge -> room exit
    inc RoomX
    jsr PlayerHitsMap
    bcc .RightDone
    dec RoomX                   ; collision -> undo
.RightDone:
    jmp EndInputCheck
.ExitRight:
    jsr ExitRoomRight

EndInputCheck:

    ; --- Wait for overscan timer ---
.WaitOverscan:
    lda INTIM
    bne .WaitOverscan

    jmp StartFrame

; ------------------------------------------------------------------------------
; StepDown: try one pixel of downward movement (called per pixel of vy).
; A pixel is rejected when the footprint enters a solid tile (player lands
; and vy is zeroed). At PLAYER_MAX_Y the room's down connection is followed.
; ------------------------------------------------------------------------------
StepDown subroutine
    lda RoomY
    cmp #PLAYER_MAX_Y
    bcs .SDBottom
    inc RoomY
    jsr PlayerHitsMap
    bcc .SDDone
    dec RoomY
    lda #0
    sta vyLo
    sta vyHi
.SDDone:
    rts
.SDBottom:
    jsr ExitRoomDown
    rts

; ------------------------------------------------------------------------------
; StepUp: one pixel of upward movement. Solid tile above stops the sprite
; and zeroes vy. At the top edge the room's up connection is followed.
; ------------------------------------------------------------------------------
StepUp subroutine
    lda RoomY
    beq .SUTop
    dec RoomY
    jsr PlayerHitsMap
    bcc .SUDone
    inc RoomY
    lda #0
    sta vyLo
    sta vyHi
.SUDone:
    rts
.SUTop:
    jsr ExitRoomUp
    rts

; ==============================================================================
; Room management
; ==============================================================================
; EnterRoom: load PF data and collision rectangles for room A (0-based index).
; Sets RoomNo, RoomPFDataLo/Hi, and RoomRectsLo/Hi.
; RoomX/RoomY are NOT changed — caller (exit handlers) sets them.
; ------------------------------------------------------------------------------
EnterRoom subroutine
    sta RoomNo
    asl                         ; room * 4 (two .word entries per room)
    asl
    tay
    ; Load PF0 data pointer (first .word)
    lda (LevelPFDataLo),Y
    sta RoomPF0Lo
    iny
    lda (LevelPFDataLo),Y
    sta RoomPF0Hi
    ; Pre-compute PF1 and PF2 pointers (+12 bytes each)
    clc
    lda RoomPF0Lo
    adc #12
    sta RoomPF1Lo
    lda RoomPF0Hi
    adc #0
    sta RoomPF1Hi
    clc
    lda RoomPF1Lo
    adc #12
    sta RoomPF2Lo
    lda RoomPF1Hi
    adc #0
    sta RoomPF2Hi
    iny
    ; Load collision rects pointer (second .word)
    lda (LevelPFDataLo),Y
    sta RoomRectsLo
    iny
    lda (LevelPFDataLo),Y
    sta RoomRectsHi
    rts

; ==============================================================================
; Room exit stubs — reposition player to start (100, 64)
; TODO: implement proper room transitions
; ==============================================================================
ExitRoomUp:
ExitRoomDown:
ExitRoomLeft:
ExitRoomRight:
    lda #100
    sta RoomX
    lda #64
    sta RoomY
    rts

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

; --- Level data ---
; Generated from level JSON via tools/generate_level_asm.py.
; Do not edit by hand — regenerate with build.sh.
    include "generated/level_001.asm"

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
; HERO-style score font — 10 digits × 5 rows, 3 bits wide (bits 0-2)
; Score digit font — 3 pixels wide, 5 rows per digit (PF-based, temporary)
; Will be replaced by 8×8 sprite font when 48-pixel technique is implemented
; ==============================================================================
PFDigitFont:
  .byte %00000111, %00000101, %00000101, %00000101, %00000111  ; 0
  .byte %00000010, %00000110, %00000010, %00000010, %00000111  ; 1
  .byte %00000111, %00000001, %00000111, %00000100, %00000111  ; 2
  .byte %00000111, %00000001, %00000111, %00000001, %00000111  ; 3
  .byte %00000101, %00000101, %00000111, %00000001, %00000001  ; 4
  .byte %00000111, %00000100, %00000111, %00000001, %00000111  ; 5
  .byte %00000111, %00000100, %00000111, %00000101, %00000111  ; 6
  .byte %00000111, %00000001, %00000001, %00000001, %00000001  ; 7
  .byte %00000111, %00000101, %00000111, %00000101, %00000111  ; 8
  .byte %00000111, %00000101, %00000111, %00000001, %00000111  ; 9

DigitTimes5:
  .byte 0, 5, 10, 15, 20, 25, 30, 35, 40, 45

; ==============================================================================
; YToCellRow — convert scanline (0-191) to tile row (0-11)
; ==============================================================================
; Identical to comparison/lo-a-rad-dragon/bank0.asm.
; Input: A = scanline. Output: X = tile row.
YToCellRow subroutine
    ldx #0
.Div:
    cmp #LINES_PER_TILE
    bcc .Done
    sbc #LINES_PER_TILE
    inx
    bne .Div
.Done:
    rts

; ==============================================================================
; PlayerHitsMap — check player bounding box against room rectangle list
; ==============================================================================
; Identical to comparison/lo-a-rad-dragon/bank0.asm.
; Rectangles are in tile coordinates (col 0-19, row 0-11, w/h in tiles).
; The playfield is reflected, so tiles >= 20 mirror via 39-col.
; Returns C=0 if clear, C=1 if blocked.
PlayerHitsMap:
; --- Tile row range (top, bottom) ---
    lda RoomY
    jsr YToCellRow
    stx CollisionCellY          ; top tile row
    clc
    lda RoomY
    adc #PLAYER_HEIGHT - 1
    jsr YToCellRow
    stx CollisionEndY           ; bottom tile row

; --- Visible left pixel -> text column range ---
; RESP0 positions sprite relative to RoomX. Offset varies by coarse bin.
    sec
    lda RoomX
    cmp #15
    bcs .off7
    sbc #4                      ; RoomX < 15: visible left = X - 4
    jmp .gotVL
.off7:
    sbc #7                      ; RoomX >= 15: visible left = X - 7
.gotVL:
    ; first block = visible_left / 4 -> text column
    tay                         ; Y = visible_left
    lsr
    lsr
    cmp #TILE_COLUMNS
    bcc .firstOk
    sta CollisionX
    lda #39
    sec
    sbc CollisionX
.firstOk:
    sta CollisionEndX           ; min text column

    ; last block = (visible_left + PLAYER_WIDTH - 1) / 4 -> text column
    tya                         ; A = visible_left
    clc
    adc #PLAYER_WIDTH - 1
    lsr
    lsr
    cmp #TILE_COLUMNS
    bcc .lastOk
    sta CollisionX
    lda #39
    sec
    sbc CollisionX
.lastOk:
    sta CollisionCellX          ; max text column

    ; Ensure min <= max (blocks 20+ reverse the column order)
    lda CollisionEndX
    cmp CollisionCellX
    bcc .colsOk
    ldx CollisionCellX
    stx CollisionEndX
    sta CollisionCellX
.colsOk:

; --- Walk rectangle list ---
    lda RoomRectsLo
    sta MapPtrLo
    lda RoomRectsHi
    sta MapPtrHi
    ldy #0
    lda (MapPtrLo),Y            ; rectangle count
    bne .HasRects
    clc
    rts                         ; no rectangles -> not hit
.HasRects:
    sta RectCount               ; rectangle loop counter
    iny                         ; Y=1, first rect byte

.RectLoop:
    tya
    pha                         ; save rect base offset

; Column overlap: max_col >= rect.x AND min_col < rect.x + rect.w
    lda (MapPtrLo),Y            ; rect.x (Y = base)
    cmp CollisionCellX          ; rect.x > max_col?
    beq .colOk
    bcc .colOk
    jmp .nextRect
.colOk:
    sta CollisionX              ; save rect.x for addition
    iny
    iny                         ; Y = base + 2 (rect.w)
    clc
    lda (MapPtrLo),Y            ; rect.w
    adc CollisionX              ; rect.x + rect.w
    cmp CollisionEndX           ; (rect.x+w) <= min_col?
    beq .nextRect
    bcc .nextRect

; Row overlap: bottom_row >= rect.y AND top_row < rect.y + rect.h
    dey                         ; Y = base + 1 (rect.y)
    lda (MapPtrLo),Y            ; rect.y
    cmp CollisionEndY           ; rect.y > bottom_row?
    beq .rowOk
    bcc .rowOk
    jmp .nextRect
.rowOk:
    iny
    iny                         ; Y = base + 3 (rect.h)
    clc
    lda (MapPtrLo),Y            ; rect.h
    dey
    dey                         ; Y = base + 1 (rect.y)
    adc (MapPtrLo),Y            ; rect.y + rect.h
    cmp CollisionCellY          ; (rect.y+h) <= top_row?
    beq .nextRect
    bcc .nextRect

; HIT — player is blocked
    pla
    sec
    rts

.nextRect:
    pla
    clc
    adc #4                      ; advance past this rect (4 bytes each)
    tay
    dec RectCount
    beq .NoHit
    jmp .RectLoop

.NoHit:
    clc
    rts

; ==============================================================================
; F6 cross-bank fold pads — MUST match bank1's copies at these addresses.
; These go BEFORE the fineAdjustTable so org $FC68 doesn't go backwards.
; ==============================================================================
MenuMain = $F540                   ; bank1's HUD entry (not code in bank0)
    org $FC68
ToMenuStub:
    lda #1
    sta $1FF7                     ; select bank1 (HUD)
    jmp MenuMain                 ; next fetch from bank1: jmp $F540

    org $FC70
ToGameStub:
    lda #0
    sta $1FF6                     ; select bank0 (game)
    jmp $F0B9                     ; return to bank0 after HUD band

; Pad to fineAdjustTable
    .ds $FF00 - *, 0

; ==============================================================================
; Fine-adjust table for SetObjectXPos — MUST be page-aligned ($xx00)
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
