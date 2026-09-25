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
AUDC0   = $15
AUDC1   = $16
AUDF0   = $17
AUDF1   = $18
AUDV0   = $19
AUDV1   = $1A

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
BombY           byte            ; bomb drop Y (was dead TileRow; scanline snapshot)
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

; Level/miner ZP variables
Level           byte            ; current level index (0-based)
LevelMinerRoom  byte            ; room index holding the miner for current level
MinerX          byte            ; miner X position (room pixel coords)
MinerY          byte            ; miner Y position (room pixel coords)
LevelStartRoom  byte            ; level origin room (spawn + enemy-hit teleport)
LevelStartX     byte            ; level origin X
LevelStartY     byte            ; level origin Y
LevelWallColor  byte            ; wall color 1 (rows 0-3, 8-11)
LevelWallColor2 byte            ; wall color 2 (rows 4-7)
PlayerLives     byte            ; lives remaining (0 = game over, reset)
TickCounter     byte            ; frame counter (60 frames = 1 bar step = 1s)
BarLevel        byte            ; timer bar level (120=full, 0=empty)

; Enemy ZP variables
LevelEnemyLo    byte            ; pointer to level's RoomEnemies table (low)
LevelEnemyHi    byte            ; pointer to level's RoomEnemies table (high)
EnemyDataLo     byte            ; pointer to current room enemy data (low)
EnemyDataHi     byte            ; pointer to current room enemy data (high)
EnemyCount      byte            ; number of enemies in current room
FlickerFrame    byte            ; GRP1 slot index for flicker
BombPacked      byte            ; bomb state at $B5 (was ephemeral ObjectCount):
                                ;   b0-1 state 0=none,1=fuse,2=explode
                                ;   b2 DownPrev edge, b3-6 WallMask, b7 OnGround
ActiveObjectOn  byte            ; 1 when current object is active this frame
ActiveObjectX   byte            ; active object X (room pixel coords)
ActiveObjectY   byte            ; active object Y (scanline coords)
EnemyIndex      byte            ; current enemy index in room enemy list
DeadEnemyIdx    byte            ; index of killed enemy ($FF = none)

; Object rendering ZP (set by SelectActiveObject during VBLANK)
ObjTop          byte            ; top scanline of active object (for GRP1 visibility)
ObjBot          byte            ; bottom scanline of active object (ObjTop + PLAYER_HEIGHT)

; Bomb X/Y/timer live at $F6/$F7 + BombY=$85 (see top of ZP map)
BombX           = $F6           ; bomb drop X (RoomX snapshot; bank1 does not write $F6)
BombTimer       = $F7           ; fuse/explode countdown (frames)
PlayerBombs     = $F0           ; bombs left 0..5 (never written by VBLANK/bank1 score)
BOMBS_MAX       = 5             ; starting / reload bomb count
BombSnd         = $F1           ; frames of bomb audio left (0=silent; bank1 must not write)
RoomWallMask    = $F2           ; packed destroyed-wall mask, until stage leave:
                                ;   bits0-3 room0 rects, bits4-7 room1 rects
                                ;   (BombPacked b3-6 saved here on EnterRoom)

; Score ZP variables (shared with bank1 HUD — addresses MUST match bank1)
; $F3-$F5 live score only — $F6 is BombX (bank1 ScoreOn is unused).
ScoreTh         = $F3           ; score thousands digit (0-9)
ScoreHu         = $F4           ; score hundreds digit (0-9)
ScoreTe         = $F5           ; score tens digit (0-9)
PF0ScoreBuf     = $B3           ; 5 bytes: PF0 values for score rows 0-4
PF1ScoreBuf     = $B8           ; 5 bytes: PF1 values for score rows 0-4
PF2ScoreBuf     = $C6           ; 5 bytes: PF2 values for score rows 0-4

; PF cave buffers (copied from ROM during VBLANK, read by kernel via absolute indexed)
; These share ZP space with bank1's HUD variables — safe because bank1
; runs AFTER the cave kernel. Bank1 overwrites them during HUD band;
; VBLANK re-populates them before the next kernel frame.
PF0Buf          = $C3           ; 12 bytes: TilePF0 values per row
PF1Buf          = $CF           ; 12 bytes: TilePF1 values per row
PF2Buf          = $DB           ; 12 bytes: TilePF2 values per row ($DB-$E6)
                                ; $E7-$F2 = ColupfBuf (12) — overlaps bombs
                                ; $F0-$F2: saved to CollisionCellY/EndX/EndY
                                ; during VBLANK+kernel, restored before HUD.
ColupfBuf       = $E7           ; 12 bytes: final COLUPF per tile row (stripe+hot)

; Player sprite ZP buffer (copied from ROM during VBLANK, read by kernel)
PlayerGrp0      = $F8           ; 8 bytes: player sprite rows (computed per frame)

; Enemy RAM shadow — live X/(packed flags). ROM records are read-only.
; Sequential vars end at $BC; free ZP is $BD-$C2 (6) used by EnemyRam*.
; Score lives at $F3-$F5 only ($F6/$F7 = BombX/BombTimer). SelectActiveObject/
; CheckEnemyHit read Y from ROM (enemy Y is static until S5 spider).
EnemyRamX       = $BD           ; 4 bytes: live X per enemy ($BD-$C0)
EnemyRamD       = $C1           ; dir bits 0-3 = enemy 0-3 (1=right, 0=left)
EnemyRamP       = $C2           ; bits0-3 moth phase; bits4-7 spider vdir (1=down)

; ==============================================================================
; Constants
; ==============================================================================
PLAYER_HEIGHT   = 8             ; sprite height in scanlines
PLAYER_WIDTH    = 4             ; sprite width in pixels
ENEMY_WIDTH     = 4             ; snake GRP1 width ($f0 = 4 px) — flush-out span
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
JET_AUD_BASE    = $0F           ; engine AUDF base: freq = base - JetPower/8 - sputter
JET_AUD_VOL     = $08           ; engine volume while Up is held



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

; Dark room (lamp crashed): medium grey objects, black PF; fuse PF dark grey
COLOR_DARK_OBJ  = $0A           ; hue 0 luma 5 = medium grey (lamp + enemies)
COLOR_DARK_PF   = $04           ; hue 0 luma 2 = very dark grey (bomb fuse walls)

; Explosion blink COLUBK cycle (BombState=2): black → yellow → red
COLOR_BLINK_Y   = $1C           ; hue 1 luma 6 = yellow (power bar)
COLOR_BLINK_R   = $44           ; hue 4 luma 2 = red (power bar)

; Hot rock pulse (COLUPF yellow ↔ red), phase from TickCounter bit 4
COLOR_HOT_Y     = COLOR_BLINK_Y
COLOR_HOT_R     = COLOR_BLINK_R

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
    lda #0
    sta Level
    lda #3
    sta PlayerLives
    lda #BOMBS_MAX
    sta PlayerBombs
    lda #$FF
    sta DeadEnemyIdx
    ; Initialize timer: 60 frames/step × 120 = 7200 = 120.0s
    lda #60
    sta TickCounter
    lda #120
    sta BarLevel                ; bar starts full

    ; --- Load first level ---
    jsr LoadLevel

    ; --- Set player color ---
    lda #COLOR_PLAYER
    sta COLUP0

    ; --- Set playfield to reflected mode + priority ---
    ; D0=1 = reflect (left half mirrors to right)
    ; D2=1 = playfield priority (player drawn BEHIND walls, like HERO)
    lda #$05                      ; CTRLPF: reflect + priority (cave mode)
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

    ; --- No sprite copy needed — kernel reads directly from ROM ---
    ; Do NOT HMOVE here: wait until P1 is positioned too. An early HMOVE
    ; applied stale bank1 HMP1 (score), and a second HMOVE after SelectActiveObject
    ; applied HMP0 twice → player fine-adjust doubled (visual teleport/jitter).

    ; --- Refresh PF buffers (bank1 corrupts them during HUD band) ---
    jsr LoadPFBuffer
    jsr ApplyBombWalls          ; S6.1: re-apply thin-wall holes every frame
    jsr BuildColupF            ; stripe+hot COLUPF bytes into ColupfBuf ($E7-$F2)

    ; --- Select which object GRP1 draws this frame (miner or enemy) ---
    jsr SelectActiveObject

    ; --- Cave COLUBK for this frame → Temp (free until overscan) ---
    ; state=2: blink (60-BombTimer)%3 → black/yellow/red; else COLOR_CAVE_BG
    ; Dark room: black except the existing explosion blink (state=2).
    lda BombPacked
    and #%00000011
    cmp #2
    beq .BgBlink
    jsr IsRoomDark
    beq .BgIdle                 ; lit room → COLOR_CAVE_BG
    lda #COLOR_CAVE_BG          ; dark → black
    jmp .BgStore
.BgBlink:
    lda #60
    sec
    sbc BombTimer
.BgMod3:
    cmp #3
    bcc .BgModDone
    sec
    sbc #3
    bne .BgMod3                 ; A=0 exits via bcc, not this
.BgModDone:
    tay
    lda BombBlinkColors,Y
    jmp .BgStore
.BgIdle:
    lda #COLOR_CAVE_BG
.BgStore:
    sta Temp

    ; --- Single HMOVE: apply P0 (player) + P1 (enemy) fine motion once ---
    sta WSYNC
    sta HMOVE

    ; --- Copy player sprite to ZP (AFTER JSR calls to avoid stack overwrite) ---
    lda PlayerDir
    bne .CopyLeft
    lda #<PlayerSpriteRight
    ldy #>PlayerSpriteRight
    jmp .DoCopySprite
.CopyLeft:
    lda #<PlayerSpriteLeft
    ldy #>PlayerSpriteLeft
.DoCopySprite:
    sta Grp0Ptr
    sty Grp0PtrHi
    ldy #7
.CopySpriteLoop:
    lda (Grp0Ptr),Y
    sta PlayerGrp0,Y
    dey
    bpl .CopySpriteLoop

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
    lda #$00                      ; NUSIZ0 = single copy, no missile
    sta NUSIZ0
    lda #$00                      ; NUSIZ1 = single copy
    sta NUSIZ1
    lda #COLOR_PLAYER             ; restore player color (was green for HUD lives)
    sta COLUP0
    lda #0                        ; clear VDELP0/VDELP1 (bank1 HUD sets them to 1)
    sta VDELP0
    sta VDELP1
    sta ENAM0                     ; disable missile 0
    sta ENAM1                     ; disable missile 1
    sta ENABL                     ; disable ball

    lda #0
    sta Scanline
    ldx #0                      ; tile row counter (0-11)

.Row:
    ; --- Set PF registers for this tile row (TIA persists) ---
    lda PF0Buf,X
    sta PF0
    lda PF1Buf,X
    sta PF1
    lda PF2Buf,X
    sta PF2

    ; --- Set tile row colors (Temp = this frame's COLUBK, set in VBLANK) ---
    lda Temp
    sta COLUBK
    ; COLUPF precomputed by BuildColupF (stripe + hot pulse) — one ZP load.
    ; Inline stripe+hot test was 84-109c; budget is 76c/scanline.
    lda ColupfBuf,X
    sta COLUPF
    ; --- Bottom band: row 11 only, open PF shows COLUBK band color ---
    ; Blink (BombPacked state=2) keeps Temp; color 0 = band off.
    cpx #TILE_ROWS-1
    bne .RowSkipBand
    lda BombPacked
    and #%00000011
    cmp #2
    beq .RowSkipBand
    jsr LoadRoomBottomColor
    beq .RowSkipBand
    sta COLUBK
.RowSkipBand:

    ; --- Init scanline counter for this row ---
    lda #LINES_PER_TILE
    sta LineCount

    ; --- Sync to next scanline ---
    sta WSYNC

.Line:
    ; --- GRP0 FIRST (must be within HBLANK, ~22 cycles) ---
    lda Scanline
    sec
    sbc RoomY                   ; A = Scanline - RoomY
    cmp #PLAYER_HEIGHT
    bcs .NoSprite               ; branch if A >= PLAYER_HEIGHT (not visible)
    tay                         ; Y = sprite row index (0-7)
    lda PlayerGrp0,Y            ; 4c — ZP indexed read
    jmp .WriteGrp0
.NoSprite:
    lda #0
.WriteGrp0:
    sta GRP0

    ; --- GRP1 SECOND (object/enemy sprite) ---
    lda ActiveObjectOn
    beq .NoObject
    lda Scanline
    cmp ObjTop
    bcc .NoObject
    cmp ObjBot
    bcs .NoObject
    lda #$f0
    jmp .WriteGrp1
.NoObject:
    lda #0
.WriteGrp1:
    sta GRP1

    ; --- Loop control ---
    inc Scanline                ; advance scanline counter
    sta WSYNC                   ; wait for end of this scanline
    dec LineCount               ; decrement scanlines remaining in row
    bne .Line                   ; loop if more scanlines in this row

    ; --- Advance to next tile row ---
    inx
    cpx #TILE_ROWS
    beq .AfterRows
    jmp .Row
.AfterRows:

    ; --- Restore bombs clobbered by ColupfBuf ($F0-$F2) before HUD/overscan ---
    lda CollisionCellY          ; saved PlayerBombs
    sta PlayerBombs
    lda CollisionEndX           ; saved BombSnd
    sta BombSnd
    lda CollisionEndY           ; saved RoomWallMask
    sta RoomWallMask

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
    ; Bank1's MenuMain returns to bank0 via: lda #0 / sta $1FF6 / jmp Overscan

; ==============================================================================
; Overscan (30 scanlines) — input handling + game logic
; ==============================================================================
Overscan:
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

    ; --- Bomb: edge-detect Down (D1, 0=pressed) ---
    lda Temp
    and #%00000010
    beq .BombHeld
    lda BombPacked              ; released: clear DownPrev (b2), keep state/mask
    and #%11111011
    sta BombPacked
    jmp .BombInDone
.BombHeld:
    lda BombPacked
    and #%00000100
    bne .BombInDone             ; held since last frame — no edge
    lda BombPacked
    and #%00000011
    bne .BombMarkDown           ; bomb already active: just set DownPrev
    lda PlayerBombs
    beq .BombMarkDown           ; no bombs left: swallow edge, keep DownPrev
    lda BombPacked
    and #%10000000              ; b7 OnGround — drop only when standing
    beq .BombMarkDown           ; flying/falling: swallow edge, keep DownPrev
    dec PlayerBombs
    lda BombPacked              ; rising edge, state=0 → drop
    ora #%00000101              ; state=1 + DownPrev
    sta BombPacked
    lda RoomX
    sta BombX
    lda RoomY
    sta BombY
    lda #180
    sta BombTimer
    jsr BombSndDrop          ; S10: short blip on place
    jmp .BombInDone
.BombMarkDown:
    lda BombPacked
    ora #%00000100
    sta BombPacked
.BombInDone:

; ------------------------------------------------------------------------------
; Vertical movement — HERO-style jetpack physics
; ------------------------------------------------------------------------------
; Gravity pulls down, holding Up fires jetpack (JetPower ramps with inertia).
; Velocity is integrated through PlayerYSub and walked pixel-by-pixel via
; StepDown/StepUp so collision stops flush at walls/doorways.
; ------------------------------------------------------------------------------
UpdateP0Vertical:
; --- Clear HotBump (Temp b7) — set again only if this frame bumps hot rock ---
    lda Temp
    and #%01111111
    sta Temp

; --- Jet thrust accumulator: +1/frame while Up is held (cap JET_MAX),
;     -1/frame otherwise. The ramp gives the jet its initial inertia. ---
    lda #%00000001              ; test D0 (up, after 4x LSR)
    bit Temp
    bne .JetDecay
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
    ; fall through to CheckP0Left (removed redundant jmp — target was next insn, 3c/frame)

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
    ; fall through to CheckP0Right (removed redundant jmp — target was next insn, 3c)

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

    ; --- Hot rock touch (bump into H cell this frame) → lose life ---
    lda Temp
    bpl .NoHotBump
    jsr LoseLifeHot
.NoHotBump:

    ; --- Bottom band touch (RoomY in row 11 + band color on) → lose life ---
    jsr CheckBandTouch

    ; --- Move live enemies (snake first; other types no-op until S5+) ---
    jsr UpdateEnemies

    ; --- Check miner pickup (advances to next level) ---
    jsr CheckMinerPickup

    ; --- Check enemy collision (lose life on hit) ---
    jsr CheckEnemyHit

    ; --- Bomb fuse/explode tick (frames) ---
    jsr BombTick

    ; --- Bomb audio: hold registers while BombSnd > 0, else silence ---
    jsr UpdateBombSound

    ; --- Jet engine audio (channel 1): buzz while Up is held ---
    jsr UpdateJetSound

    ; --- Decrement game timer (60 frames/step × 120 = 120s) ---
    dec TickCounter
    bne .TimerDone              ; not 1s yet
    lda #60
    sta TickCounter
    dec BarLevel
    beq .TimerExpired           ; bar empty — time's up!
    jmp .TimerDone
.TimerExpired:
    ; Time's up! Lose a life (same as enemy hit)
    dec PlayerLives
    bpl .TimerReset
    ; Lives exhausted — reset level
    lda #3
    sta PlayerLives
    lda #$FF
    sta DeadEnemyIdx
    jsr ReloadLevel
    jmp .TimerDone
.TimerReset:
    ; Reset bar for retry
    lda #120
    sta BarLevel
    lda #60
    sta TickCounter
    ; Zero velocity, stay at current position
    lda #0
    sta vyLo
    sta vyHi
    sta JetPower
    sta PlayerYSub
.TimerDone:

    ; --- Wait for overscan timer ---
.WaitOverscan:
    lda INTIM
    bne .WaitOverscan

    jmp StartFrame

; ------------------------------------------------------------------------------
; StepDown: try one pixel of downward movement (called per pixel of vy).
; A pixel is rejected when the footprint enters a solid tile (player lands
; and vy is zeroed). At PLAYER_MAX_Y the room's down connection is followed.
; Sets BombPacked b7 (OnGround) on land / floor; clears when free-falling.
; ------------------------------------------------------------------------------
StepDown subroutine
    lda RoomY
    cmp #PLAYER_MAX_Y
    bcs .SDBottom
    inc RoomY
    jsr PlayerHitsMap
    bcc .SDAir
    dec RoomY
    lda #0
    sta vyLo
    sta vyHi
    lda BombPacked
    ora #%10000000              ; landed — OnGround
    sta BombPacked
    rts
.SDAir:
    lda BombPacked
    and #%01111111              ; still falling — not ground
    sta BombPacked
    rts
.SDBottom:
    jsr ExitRoomDown
    lda RoomY
    cmp #PLAYER_MAX_Y
    bne .SDDone                  ; changed room (EnterRoom cleared b7)
    lda BombPacked
    ora #%10000000              ; no down exit — standing on floor
    sta BombPacked
    lda #0
    sta vyLo
    sta vyHi
.SDDone:
    rts

; ------------------------------------------------------------------------------
; StepUp: one pixel of upward movement. Solid tile above stops the sprite
; and zeroes vy. At the top edge the room's up connection is followed.
; Clears OnGround (b7) — jet/lift is not standing.
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
    lda BombPacked
    and #%01111111              ; rising/blocked-up — not ground
    sta BombPacked
    rts
.SUTop:
    jsr ExitRoomUp
    lda BombPacked
    and #%01111111              ; ceiling / enter-from-below — not ground
    sta BombPacked
    rts

; ==============================================================================
; Room management
; ==============================================================================
; LoadPFBuffer: copy PF data from ROM to ZP buffers (12 bytes × 3 registers).
; Called every frame during VBLANK because bank1's HUD corrupts the buffers.
; Uses RoomPF0Lo/Hi, RoomPF1Lo/Hi, RoomPF2Lo/Hi (set by EnterRoom).
; ------------------------------------------------------------------------------
LoadPFBuffer:
    ldy #0
.LPB_Loop:
    lda (RoomPF0Lo),Y
    sta PF0Buf,Y
    lda (RoomPF1Lo),Y
    sta PF1Buf,Y
    lda (RoomPF2Lo),Y
    sta PF2Buf,Y
    iny
    cpy #12
    bne .LPB_Loop
    rts

; EnterRoom: load PF data and collision rectangles for room A (0-based index).
; Sets RoomNo, RoomPFDataLo/Hi, and RoomRectsLo/Hi.
; RoomX/RoomY are NOT changed — caller (exit handlers) sets them.
; ------------------------------------------------------------------------------
EnterRoom subroutine
    ; Persist outgoing room WallMask into RoomWallMask (permanent until LoadLevel)
    pha                         ; save new room index
    lda BombPacked
    and #%01111000              ; mask bits only
    lsr
    lsr
    lsr                         ; A = rect nibble (b0-3)
    ldx RoomNo                  ; OLD room (still valid)
    beq .ERSaveR0
    asl
    asl
    asl
    asl                         ; room1: nibble → high
    sta Temp
    lda RoomWallMask
    and #$0F
    ora Temp
    sta RoomWallMask
    jmp .ERGotRoom
.ERSaveR0:
    sta Temp
    lda RoomWallMask
    and #$F0
    ora Temp
    sta RoomWallMask
.ERGotRoom:
    pla                         ; new room
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

    ; Load enemy data for this room from LevelEnemyLo/Hi table
    ; Per-room record: ptr_lo, ptr_hi, count, pad (4 bytes per room)
    lda RoomNo
    asl                         ; room * 4
    asl
    tay
    lda (LevelEnemyLo),Y        ; enemy data pointer lo
    sta EnemyDataLo
    iny
    lda (LevelEnemyLo),Y        ; enemy data pointer hi
    sta EnemyDataHi
    iny
    lda (LevelEnemyLo),Y        ; enemy count
    sta EnemyCount
    lda #$FF
    sta DeadEnemyIdx            ; no dead enemies in new room

    ; Bomb reset: clear state/timer/sound (incl. OnGround b7); RELOAD mask
    ; (destroyed thin walls persist across room leave/re-enter until stage leave)
    lda #0
    sta BombPacked
    sta BombTimer
    sta BombSnd
    sta AUDV0
    ldx RoomNo
    beq .ERLoadR0
    lda RoomWallMask
    and #$F0
    beq .ERMaskDone
    lsr                         ; high nibble → b3-6
    jmp .ERMaskOr
.ERLoadR0:
    lda RoomWallMask
    and #$0F
    beq .ERMaskDone
    asl
    asl
    asl                         ; low nibble → b3-6
.ERMaskOr:
    ora BombPacked
    sta BombPacked
.ERMaskDone:

    jsr LoadEnemyRam            ; copy ROM x/dir → live RAM shadow
    jsr LoadPFBuffer
    jsr ApplyBombWalls          ; re-punch holes from restored mask
    rts

; ------------------------------------------------------------------------------
; LoadEnemyRam — copy each ROM enemy's x,dir into the RAM shadow.
; ROM stride 6: type(+0), x(+1), y(+2), range_min(+3), range_max(+4), dir(+5).
; Y is NOT shadowed (stays in ROM until S5) — $F3-$F6 is bank1 score.
; dir ROM: +1 / $FF. Packed: EnemyRamD bit=1 right, 0 left.
; EnemyRamP bits4-7 init to %1111 (all spiders start moving down).
; ------------------------------------------------------------------------------
LoadEnemyRam:
    lda EnemyRamD
    and #$F0                    ; preserve RoomDarkMask bits 4-7 (rooms 0-3)
    sta EnemyRamD
    lda #$F0                    ; spider vdir bits 4-7 = 1 (down) for slots 0-3
    sta EnemyRamP
    ldx #0
LER_Loop:
    cpx EnemyCount
    bcs LER_Done
    txa                         ; Y = X * 6 (= x2 + x4)
    asl
    sta Temp
    asl
    clc
    adc Temp
    tay
    iny                         ; +1 = x
    lda (EnemyDataLo),Y
    sta EnemyRamX,X
    iny                         ; +2 = y (ROM only — not shadowed)
    iny                         ; +3 range_min
    iny                         ; +4 range_max
    iny                         ; +5 dir
    lda (EnemyDataLo),Y
    bmi LER_Left                ; $FF = face left
    lda EnemyBitTable,X         ; face right → set bit
    ora EnemyRamD
    sta EnemyRamD
    jmp LER_Next
LER_Left:
    lda EnemyBitTable,X         ; face left → clear bit
    eor #$FF
    and EnemyRamD
    sta EnemyRamD
LER_Next:
    inx
    jmp LER_Loop
LER_Done:
    rts

EnemyBitTable:
    .byte $01, $02, $04, $08

; ------------------------------------------------------------------------------
; UpdateEnemies — per-type live motion from RAM shadow (overscan).
; Speed: 1 px / 2 frames (TickCounter parity gate).
; Snake patrol: bounds relative to ROM spawn X ± ENEMY_WIDTH (4 = $f0 sprite),
; side chosen by ROM dir (initial facing). Ignores editor range_* per user
; 2026-09-23. First move = facing (live dir from LoadEnemyRam). No wall collision.
; ------------------------------------------------------------------------------
UpdateEnemies:
    lda EnemyCount
    bne UE_Gate
    rts
UE_Gate:
    lda TickCounter         ; 1 px / 4 frames (half of previous 1/2)
    and #3
    bne UE_Exit
    ldx #0
UE_Loop:
    cpx EnemyCount
    bcs UE_Exit
    cpx DeadEnemyIdx
    beq UE_Next                  ; dead enemy does not move
    ; ROM type at offset X*6
    txa
    asl
    sta Temp
    asl
    clc
    adc Temp
    tay                          ; Y = X*6 = type offset
    lda (EnemyDataLo),Y
    cmp #ENEMY_SNAKE
    bne UE_Next                  ; only snake moves
    ; live dir bit: 1 = right, 0 = left
    lda EnemyBitTable,X
    and EnemyRamD
    bne UE_SnakeRight
UE_SnakeLeft:
    dec EnemyRamX,X
    iny                          ; +1 = ROM spawn X
    lda (EnemyDataLo),Y
    sta Temp
    iny
    iny
    iny
    iny                          ; +5 = ROM dir
    lda (EnemyDataLo),Y
    bmi UE_LeftInitL             ; initial face left → rmin = spawn - 8
    lda Temp                     ; initial face right → rmin = spawn
    jmp UE_LeftChk
UE_LeftInitL:
    sec
    lda Temp
    sbc #ENEMY_WIDTH
UE_LeftChk:
    sta Temp
    lda EnemyRamX,X
    cmp Temp
    bcs UE_Next                  ; X >= rmin OK
    lda Temp
    sta EnemyRamX,X              ; clamp to exact bound
    jsr UE_FlipDir               ; below min → turn right
    jmp UE_Next
UE_SnakeRight:
    inc EnemyRamX,X
    iny                          ; +1 = ROM spawn X
    lda (EnemyDataLo),Y
    sta Temp
    iny
    iny
    iny
    iny                          ; +5 = ROM dir
    lda (EnemyDataLo),Y
    bmi UE_RightInitL            ; initial face left → rmax = spawn
    clc
    lda Temp                     ; initial face right → rmax = spawn + 8
    adc #ENEMY_WIDTH
    jmp UE_RightChk
UE_RightInitL:
    lda Temp
UE_RightChk:
    sta Temp
    lda EnemyRamX,X
    cmp Temp
    bcc UE_Next                  ; X < rmax OK
    beq UE_Next                  ; X == rmax OK
    lda Temp
    sta EnemyRamX,X              ; clamp to exact bound
    jsr UE_FlipDir               ; past max → turn left
UE_Next:
    inx
    jmp UE_Loop
UE_Exit:
    rts

; Flip dir bit for enemy X (right↔left).
UE_FlipDir:
    lda EnemyBitTable,X
    eor EnemyRamD
    sta EnemyRamD
    rts

; ==============================================================================
; Room exit handlers — check connection table, switch rooms, reposition player
; ==============================================================================
; Connection table: 4 bytes per room (up, down, left, right), $FF = no exit.
; After transition: player is placed at the OPPOSITE edge of the new room.
; Jetpack velocity carries over (matches comparison/hero pattern).
; ------------------------------------------------------------------------------
ExitRoomDown:
    lda RoomNo
    asl
    asl                     ; A = RoomNo * 4
    tay
    iny                     ; +1 = down direction
    lda (LevelConnLo),Y
    cmp #$ff
    beq .NoDown
    jsr EnterRoom
    lda #PLAYER_MIN_Y
    sta RoomY               ; enter at the top edge
.NoDown:
    rts

ExitRoomUp:
    lda RoomNo
    asl
    asl                     ; A = RoomNo * 4 + 0 = up direction
    tay
    lda (LevelConnLo),Y
    cmp #$ff
    beq .NoUp
    jsr EnterRoom
    lda #PLAYER_MAX_Y
    sta RoomY               ; enter at the bottom edge
.NoUp:
    rts

ExitRoomLeft:
    lda RoomNo
    asl
    asl
    tay
    iny
    iny                     ; +2 = left direction
    lda (LevelConnLo),Y
    cmp #$ff
    beq .NoLeft
    jsr EnterRoom
    lda #PLAYER_MAX_X
    sta RoomX               ; enter at the right edge
.NoLeft:
    rts

ExitRoomRight:
    lda RoomNo
    asl
    asl
    tay
    iny
    iny
    iny                     ; +3 = right direction
    lda (LevelConnLo),Y
    cmp #$ff
    beq .NoRight
    jsr EnterRoom
    lda #PLAYER_MIN_X
    sta RoomX               ; enter at the left edge
.NoRight:
    rts

; ==============================================================================
; Level management
; ==============================================================================
; LoadLevel: read LevelDataTable entry for current Level, init pointers, enter room.
; LevelDataTable stride: 12 bytes
;   +0..+2: start_room, start_x, start_y
;   +3..+5: miner_room, miner_x, miner_y
;   +6..+7: pfdata ptr (lo, hi)
;   +8..+9: conn ptr (lo, hi)
;  +10..+11: enemy ptr (lo, hi)
; ------------------------------------------------------------------------------
LoadLevel:
    ; Stage leave/reload/advance: walls return + bombs refill to 5
    lda #0
    sta RoomWallMask
    sta BombPacked              ; so EnterRoom's save writes 0, not stale mask
    sta BombTimer
    sta EnemyRamD               ; clear dir + RoomDarkMask (bits 4-7) — level reset
    lda #BOMBS_MAX
    sta PlayerBombs
    ; Compute LevelDataTable pointer: base + Level * 14
    ; Stride 14: start(3) + miner(3) + wall_colors(2) + ptrs(3×2)
    lda Level
    asl                         ; *2
    sta Temp                    ; Temp = L * 2
    asl                         ; *4
    asl                         ; *8
    clc
    adc Temp                    ; *10
    adc Temp                    ; *12
    adc Temp                    ; *14
    tay                         ; Y = Level * 14

    ; +0..+2: start room, x, y
    lda LevelDataTable,Y
    sta LevelStartRoom
    iny
    lda LevelDataTable,Y
    sta LevelStartX
    iny
    lda LevelDataTable,Y
    sta LevelStartY
    iny
    ; +3..+5: miner room, x, y
    lda LevelDataTable,Y
    sta LevelMinerRoom
    iny
    lda LevelDataTable,Y
    sta MinerX
    iny
    lda LevelDataTable,Y
    sta MinerY
    iny
    ; +6..+7: wall colors
    lda LevelDataTable,Y
    sta LevelWallColor
    iny
    lda LevelDataTable,Y
    sta LevelWallColor2
    iny
    ; +8..+9: pfdata ptr
    lda LevelDataTable,Y
    sta LevelPFDataLo
    iny
    lda LevelDataTable,Y
    sta LevelPFDataHi
    iny
    ; +10..+11: conn ptr
    lda LevelDataTable,Y
    sta LevelConnLo
    iny
    lda LevelDataTable,Y
    sta LevelConnHi
    iny
    ; +12..+13: enemy ptr
    lda LevelDataTable,Y
    sta LevelEnemyLo
    iny
    lda LevelDataTable,Y
    sta LevelEnemyHi

    ; Enter the starting room
    lda LevelStartRoom
    jsr EnterRoom

    ; Place player at level start
    lda LevelStartX
    sta RoomX
    lda LevelStartY
    sta RoomY

    ; Zero jetpack state
    lda #0
    sta vyLo
    sta vyHi
    sta JetPower
    sta PlayerYSub
    rts

; ==============================================================================
; Miner pickup — check if player overlaps miner, advance to next level
; ==============================================================================
CheckMinerPickup:
    lda RoomNo
    cmp LevelMinerRoom
    bne .CMPDone                ; not in miner's room
    ; Check X overlap: |RoomX - MinerX| < PLAYER_WIDTH
    lda RoomX
    sec
    sbc MinerX
    bcs .CMPXAbs
    eor #$ff
    clc
    adc #1
.CMPXAbs:
    cmp #PLAYER_WIDTH
    bcs .CMPDone                ; no X overlap
    ; Check Y overlap: |RoomY - MinerY| < PLAYER_HEIGHT
    lda RoomY
    sec
    sbc MinerY
    bcs .CMPYAbs
    eor #$ff
    clc
    adc #1
.CMPYAbs:
    cmp #PLAYER_HEIGHT
    bcs .CMPDone                ; no Y overlap
    ; Pickup! Advance to next level
    inc Level
    lda Level
    cmp #LEVEL_COUNT
    bne .CMPNotWrap
    lda #0                      ; wrap past last level
    sta Level
.CMPNotWrap:
    jsr LoadLevel
    ; Reset timer for new level
    lda #120
    sta BarLevel
    lda #60
    sta TickCounter
.CMPDone:
    rts

; ==============================================================================
; SelectActiveObject — choose the single GRP1 object to draw this frame.
; The TIA has one GRP1 sprite, so objects flicker by rotating slots each frame.
; Sets ActiveObjectOn, ActiveObjectX, ActiveObjectY, ObjTop, ObjBot, COLUP1.
; Slot count (enemies + miner?) lives in Temp for this VBLANK only.
; Bomb fuse (state=1): low-priority — bomb only when (BombTimer&3)==0
; (~15 Hz); other frames normal miner/enemy rotation (FlickerFrame alone).
; One GRP1: cannot draw bomb + entity same frame.
; ------------------------------------------------------------------------------
SelectActiveObject:
    inc FlickerFrame            ; advance every frame (bomb + enemy paths)
    ; --- Bomb fuse (state=1): 1 of 4 frames = bomb (enemies keep priority) ---
    lda BombPacked
    and #%00000011
    cmp #1
    bne .SOCount
    lda BombTimer
    and #3
    bne .SOCount                ; 3 of 4 → miner/enemy
    lda #1
    sta ActiveObjectOn
    lda BombX
    sta ActiveObjectX
    lda BombY
    sta ActiveObjectY
    lda BombX                    ; A = X for SetObjectXPos
    ldx #1
    jsr SetObjectXPos
    lda #COLOR_BOMBS             ; $46 red
    sta COLUP1
    jmp .SODone                  ; ObjTop/Bot from ActiveObjectY
.SOCount:
    ; Count objects: enemies + miner if in miner's room (Temp = count; VBLANK-safe)
    lda EnemyCount
    sta Temp
    lda RoomNo
    cmp LevelMinerRoom
    bne .SONoMiner
    inc Temp                    ; miner counts as a slot
.SONoMiner:
    lda Temp
    bne .SONotNothing
    jmp .SONothing              ; no objects at all
.SONotNothing:
    ; FlickerFrame already advanced at entry — modulo into 0..(slot count-1)
.SOModLoop:
    lda FlickerFrame
    cmp Temp
    bcc .SOModDone
    sec
    sbc Temp
    sta FlickerFrame
    jmp .SOModLoop
.SOModDone:
    ; FlickerFrame is now 0..(slot count-1)
    ; Check if slot 0 is the miner
    lda FlickerFrame
    bne .SOEnemy
    lda RoomNo
    cmp LevelMinerRoom
    bne .SOEnemy
    ; This slot is the miner
    lda #1
    sta ActiveObjectOn
    lda MinerX
    sta ActiveObjectX
    lda MinerY
    sta ActiveObjectY
    lda MinerX                 ; A = X position for SetObjectXPos
    ldx #1
    jsr SetObjectXPos
    lda #$66                    ; purple (hue 6, luma 3)
    sta COLUP1
    jmp .SODone

.SOEnemy:
    ; Walk enemy list: find the (FlickerFrame - (miner_offset))th enemy
    ; If miner room and FlickerFrame > 0, subtract 1 for miner slot
    lda FlickerFrame
    ldx RoomNo
    cpx LevelMinerRoom
    bne .SOEnemyNoMinerOffset
    sec
    sbc #1                      ; skip miner slot
.SOEnemyNoMinerOffset:
    ; A = enemy index in list
    sta EnemyIndex
    ; Check if index < EnemyCount
    cmp EnemyCount
    bcc .SOEnemyValid
    ; Out of range — no object this slot
    lda #0
    sta ActiveObjectOn
    jmp .SODone
.SOEnemyValid:
    ; Skip if this enemy is dead
    lda EnemyIndex
    cmp DeadEnemyIdx
    beq .SOEnemySkip
    ; Live X from RAM; Y from ROM (stride +2) — not shadowed
    ldx EnemyIndex
    lda EnemyRamX,X
    sta ActiveObjectX
    ; Type/Y offset = EnemyIndex * 6
    lda EnemyIndex
    ; multiply by 6: x6 = x2 + x4
    sta Temp                    ; save index
    asl                         ; *2
    sta Temp+1                  ; save *2
    asl                         ; *4
    clc
    adc Temp+1                  ; *6
    tay                         ; Y = byte offset into enemy data
    jsr IsRoomDark              ; clobbers X — Y still = type offset
    beq .SOEnemyLit
    lda #COLOR_DARK_OBJ         ; dark room: lamp + enemies medium grey
    sta COLUP1
    jmp .SOEnemyColorDone
.SOEnemyLit:
    lda (EnemyDataLo),Y         ; reload type (X was clobbered by IsRoomDark)
    tax
    lda EnemyColorTable,X
    sta COLUP1
.SOEnemyColorDone:
    iny
    iny                         ; +2 = y
    lda (EnemyDataLo),Y
    sta ActiveObjectY
    ; Position GRP1
    lda ActiveObjectX            ; A = X position for SetObjectXPos
    ldx #1                      ; X=1 = player1
    jsr SetObjectXPos
    ; Object is visible
    lda #1
    sta ActiveObjectOn
    jmp .SODone

.SOEnemySkip:
    lda #0
    sta ActiveObjectOn

.SODone:
    ; Set ObjTop/ObjBot for kernel GRP1 visibility check
    lda ActiveObjectOn
    beq .SONoObj
    lda ActiveObjectY
    sta ObjTop
    clc
    adc #PLAYER_HEIGHT
    sta ObjBot
    rts
.SONoObj:
    lda #0
    sta ObjTop
    sta ObjBot
    rts

.SONothing:
    lda #0
    sta ActiveObjectOn
    sta ObjTop
    sta ObjBot
    rts

; ==============================================================================
; Enemy color table (emulator-aware: hue<<4 | luma<<1)
; ==============================================================================
EnemyColorTable:
    .byte $14                   ; spider — hue 1 luma 2 = dark yellow
    .byte $f2                   ; bat — hue 15 luma 7 = brown
    .byte $c4                   ; snake — hue 12 luma 2 = green
    .byte $0e                   ; tentacle — hue 0 luma 7 = white
    .byte $22                   ; moth — hue 2 luma 1 = dark orange
    .byte $0e                   ; lamp (type 5) — white; dark rooms override to grey

; ==============================================================================
; CheckEnemyHit — player overlaps an enemy → remove enemy, lose life
; ------------------------------------------------------------------------------
CheckEnemyHit:
    ; Walk enemy list, check footprint overlap with each
    lda EnemyCount
    bne CEH_HasEnemies
    jmp CEH_NoHit              ; no enemies
CEH_HasEnemies:
    ldy #0
CEH_Loop:
    cpy EnemyCount
    bcc CEH_HasMore
    jmp CEH_NoHit              ; walked all enemies, no hit
CEH_HasMore:
    sty EnemyIndex
    ; Skip dead enemies
    cpy DeadEnemyIdx
    beq CEHNext
    ; Live X from RAM; Y from ROM (stride +2) — Y not shadowed
    lda EnemyRamX,Y
    sta ActiveObjectX
    tya                         ; A = enemy index → offset = index*6
    asl
    sta Temp
    asl
    clc
    adc Temp
    tay                         ; Y = byte offset into enemy data
    iny
    iny                         ; +2 = y
    lda (EnemyDataLo),Y
    sta ActiveObjectY
    ldy EnemyIndex              ; restore loop index
    ; Check X overlap: |RoomX - ActiveObjectX| < PLAYER_WIDTH
    lda RoomX
    sec
    sbc ActiveObjectX
    bcs .CEHXAbs
    eor #$ff
    clc
    adc #1
.CEHXAbs:
    cmp #PLAYER_WIDTH
    bcs CEHNext                ; no X overlap
    ; Check Y overlap
    lda RoomY
    sec
    sbc ActiveObjectY
    bcs .CEHYAbs
    eor #$ff
    clc
    adc #1
.CEHYAbs:
    cmp #PLAYER_HEIGHT
    bcs CEHNext                ; no Y overlap
        ; Lamp (type 5): crash → RoomDarkMask; lamp stays in rotation (grey), no life
    ldx EnemyIndex
    txa
    asl
    sta Temp                    ; save index
    asl
    clc
    adc Temp                    ; *6
    tay
    lda (EnemyDataLo),Y         ; type
    cmp #LAMP
    beq CEH_Lamp
    ; Hit! Mark this enemy as dead
    lda EnemyIndex
    sta DeadEnemyIdx
    lda #$50              ; +50 points per kill
    jsr AddScore
    ; Lose a life
    dec PlayerLives
    bpl CEH_Stay
    ; Lives exhausted — reset level (all enemies back, 3 lives)
    lda #$FF
    sta DeadEnemyIdx            ; clear dead enemy
    lda #3
    sta PlayerLives
    jsr ReloadLevel
    rts
CEH_Lamp:
    ; Only fire once (bit already set → no-op); no life loss, not DeadEnemyIdx
    jsr SetRoomDark
    rts
CEH_Stay:
    ; Still have lives — just zero velocity, stay at current position
    lda #0
    sta vyLo
    sta vyHi
    sta JetPower
    sta PlayerYSub
    rts
CEHNext:
    ldy EnemyIndex
    iny
    jmp CEH_Loop
CEH_NoHit:
    rts

; ------------------------------------------------------------------------------
; BombTick — per-frame state machine (overscan).
;   state1 fuse: dec BombTimer, at 0 → state=2 timer=60 (blast = S5/S6/S9)
;   state2: dec BombTimer, at 0 → state=0 (mask stays; saved on EnterRoom)
; ------------------------------------------------------------------------------
BombTick subroutine
    lda BombPacked
    and #%00000011              ; state
    beq .BTDone                 ; none
    cmp #1
    beq .BTFuse
    ; state 2 — exploding
    dec BombTimer
    bne .BTDone
    lda BombPacked              ; clear state bits only (keep mask + DownPrev)
    and #%11111100
    sta BombPacked
    lda #0
    sta BombTimer
    rts
.BTFuse:
    dec BombTimer
    bne .BTDone
    lda BombPacked              ; 1 → 2
    and #%11111100
    ora #%00000010
    sta BombPacked
    lda #60
    sta BombTimer
    jsr BombMarkWalls           ; S6.3: set WallMask for w==1 rects in blast
    jsr BombEnemyBlast          ; S9: kill enemy ±1 col any Y (before player — reload clears)
    jsr BombPlayerBlast         ; S5: player ±1 col any Y → life (may ReloadLevel → clears masks)
    jsr BombSndExplode          ; S10: noise burst
.BTDone:
    rts

; ------------------------------------------------------------------------------
; BombEnemyBlast — on explode, walk live enemies; X-only (±1 col, any Y)
;   → DeadEnemyIdx = index. One kill slot (same as CheckEnemyHit); rooms ≤1 enemy.
; Call after BombMarkWalls, before BombPlayerBlast (ReloadLevel resets dead list).
; ------------------------------------------------------------------------------
BombEnemyBlast:
    lda EnemyCount
    bne .BEB1
    rts
.BEB1:
    lda BombX
    lsr
    lsr
    sta CollisionCellX          ; bomb screen col
    lda #0
    sta EnemyIndex
.BEBLoop:
    lda EnemyIndex
    cmp EnemyCount
    bcs .BEBDone
    cmp DeadEnemyIdx
    beq .BEBNext                ; already dead
    ; Live X from RAM (no Y needed for X-only check)
    ldy EnemyIndex
    lda EnemyRamX,Y
    ; |dcol| < 2 (col = px/4) — ignore Y entirely
    lsr
    lsr
    sec
    sbc CollisionCellX
    bcs .BEBAbsCol
    eor #$ff
    clc
    adc #1
.BEBAbsCol:
    cmp #2
    bcs .BEBNext
    lda EnemyIndex
    sta DeadEnemyIdx            ; kill (single slot — first hit wins)
    lda #$50                    ; +50 points per kill
    jsr AddScore
    rts
.BEBNext:
    inc EnemyIndex
    jmp .BEBLoop
.BEBDone:
    rts

; ------------------------------------------------------------------------------
; BombPlayerBlast — on explode, if player col in ±1 col of bomb col (any Y):
;   lose 1 life (same path as CEH_Stay / timer expiry).
; Cols = px/4 (0..39 screen). Y ignored.
; ------------------------------------------------------------------------------
BombPlayerBlast:
    lda BombX
    lsr
    lsr                         ; bomb col = BombX/4
    sta Temp
    lda RoomX
    lsr
    lsr                         ; player col = RoomX/4
    sec
    sbc Temp
    bcs .BPBColAbs
    eor #$ff
    clc
    adc #1
.BPBColAbs:
    cmp #2                      ; |dcol| < 2 → any Y kills
    bcs .BPBMiss
    ; Hit — same life path as enemy/timer
    dec PlayerLives
    bpl .BPBStay
    lda #3
    sta PlayerLives
    lda #$FF
    sta DeadEnemyIdx
    jsr ReloadLevel              ; LoadLevel → clears RoomWallMask + bomb state
    rts
.BPBStay:
    lda #0
    sta vyLo
    sta vyHi
    sta JetPower
    sta PlayerYSub
.BPBMiss:
    rts

; ------------------------------------------------------------------------------
; Bomb audio (channel 0). BombSnd = frames remaining; UpdateBombSound decs
; each overscan and silences AUDV0 at 0. Drop = square blip; explode = noise.
; ------------------------------------------------------------------------------
BombSndDrop:
    lda #6
    sta BombSnd
    lda #4                      ; square
    sta AUDC0
    lda #10
    sta AUDF0
    lda #8
    sta AUDV0
    rts

BombSndExplode:
    lda #30
    sta BombSnd
    lda #8                      ; noise
    sta AUDC0
    lda #0
    sta AUDF0
    lda #10
    sta AUDV0
    rts

UpdateBombSound:
    lda BombSnd
    beq .UBSSilence
    dec BombSnd
    bne .UBSDone
.UBSSilence:
    lda #0
    sta AUDV0
.UBSDone:
    rts

; ------------------------------------------------------------------------------
; BombMarkWalls — on 1→2 edge: walk RoomRects, set WallMask bit for each
;   w==1 rect whose x is in blast cols (bomb left-half col ±1, clamped 0..19).
;   Skip x==0: screen cols 0 and 39 (both = stored col 0 under reflection).
; Bits b3-6 of BombPacked = rect index 0..3 (rooms have ≤4 rects).
; ------------------------------------------------------------------------------
BombMarkWalls:
    lda BombX
    lsr
    lsr                         ; screen col = BombX/4 (0..39)
    cmp #TILE_COLUMNS
    bcc .BMWCol
    sta Temp
    lda #39
    sec
    sbc Temp                    ; mirror right-half → left-half col
.BMWCol:
    sta Temp                    ; bomb left-half col
    ; blast lo = max(col-1, 0)
    lda Temp
    beq .BMWLo0
    sec
    sbc #1
    bcs .BMWStoreLo
.BMWLo0:
    lda #0
.BMWStoreLo:
    sta CollisionEndX           ; blast_lo (free: overscan, after movement)
    ; blast hi = min(col+1, 19)
    lda Temp
    cmp #19
    bcs .BMWHi19
    clc
    adc #1
    bcc .BMWStoreHi
.BMWHi19:
    lda #19
.BMWStoreHi:
    sta CollisionCellX          ; blast_hi
    lda RoomRectsLo
    sta MapPtrLo
    lda RoomRectsHi
    sta MapPtrHi
    ldy #0
    lda (MapPtrLo),Y            ; rect count
    beq .BMWDone
    sta RectCount
    iny                         ; Y = base of first rect (1)
.BMWLoop:
    tya
    pha                         ; save base
    lda (MapPtrLo),Y            ; rect.x
    beq .BMWNext                ; x==0 = screen L/R border — never destroy
    cmp CollisionEndX
    bcc .BMWNext                ; x < lo
    cmp CollisionCellX
    beq .BMWCheckW              ; x == hi → in blast
    bcs .BMWNext                ; x > hi
.BMWCheckW:
    pla
    pha
    clc
    adc #2
    tay
    lda (MapPtrLo),Y            ; rect.w
    cmp #1
    bne .BMWNext
    pla                         ; base
    pha
    sec
    sbc #1
    lsr
    lsr                         ; index = (base-1)/4
    tax
    cpx #4
    bcs .BMWNext
    lda BombMaskBit,X
    and BombPacked              ; already broken?
    bne .BMWNext                ; yes → no double score
    lda BombMaskBit,X
    ora BombPacked
    sta BombPacked               ; set WallMask bit (keeps state+DownPrev)
    lda #$75                    ; +75 points per broken wall
    jsr AddScore
.BMWNext:
    pla
    clc
    adc #4
    tay
    dec RectCount
    bne .BMWLoop
.BMWDone:
    rts

; ------------------------------------------------------------------------------
; ApplyBombWalls — after LoadPFBuffer: for each masked rect, clear its col
;   bit in PF0Buf/PF1Buf/PF2Buf only for rows rect.y .. rect.y+h-1
;   (thin segment only — not into a wider join below/above).
; Early-out when WallMask=0 (common case).
; ------------------------------------------------------------------------------
ApplyBombWalls:
    lda BombPacked
    and #%01111000              ; WallMask b3-6 only
    beq .ABWDone
    lda RoomRectsLo
    sta MapPtrLo
    lda RoomRectsHi
    sta MapPtrHi
    ldy #0
    lda (MapPtrLo),Y
    beq .ABWDone
    sta RectCount
    iny
.ABWLoop:
    tya
    pha                         ; save base
    tya
    sec
    sbc #1
    lsr
    lsr                         ; index
    tax
    cpx #4
    bcs .ABWAdv
    lda BombMaskBit,X
    and BombPacked
    beq .ABWAdv
    lda (MapPtrLo),Y            ; rect.x
    sta CollisionX              ; col (saved; Y will move)
    iny
    lda (MapPtrLo),Y            ; rect.y → first row
    sta Temp
    iny
    iny                         ; Y → h
    lda (MapPtrLo),Y            ; rect.h
    clc
    adc Temp
    sec
    sbc #1
    sta CollisionCellX          ; last row = y+h-1
    lda CollisionX              ; col
    jsr ClearPFColumn           ; A=col, Temp=first, CollisionCellX=last
.ABWAdv:
    pla
    clc
    adc #4
    tay
    dec RectCount
    bne .ABWLoop
.ABWDone:
    rts

; ------------------------------------------------------------------------------
; ClearPFColumn — A = left-half col 0..19; Temp = first row; CollisionCellX =
;   last row (inclusive). AND-clear that col's PF bit in those rows only.
;   Inverse of convert_room.pf_values. Clobbers A/X/Y/CollisionX. Preserves
;   RectCount/MapPtr (caller restores Y from stack).
; ------------------------------------------------------------------------------
ClearPFColumn:
    tay                         ; Y = col
    lda BombClearMask,Y
    sta CollisionX              ; AND mask (clear bit)
    ldx Temp                    ; first row
.CPCLoop:
    tya                         ; col
    cmp #4
    bcc .CPC0
    cmp #12
    bcc .CPC1
    lda PF2Buf,X
    and CollisionX
    sta PF2Buf,X
    jmp .CPCNext
.CPC0:
    lda PF0Buf,X
    and CollisionX
    sta PF0Buf,X
    jmp .CPCNext
.CPC1:
    lda PF1Buf,X
    and CollisionX
    sta PF1Buf,X
.CPCNext:
    cpx CollisionCellX
    beq .CPCDone
    inx
    bne .CPCLoop               ; rows 0..11; X never wraps here
.CPCDone:
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

; --- Explosion blink COLUBK: index = (60-BombTimer) % 3 ---
BombBlinkColors:
    .byte COLOR_CAVE_BG         ; 0 black
    .byte COLOR_BLINK_Y         ; 1 yellow
    .byte COLOR_BLINK_R         ; 2 red

; WallMask bit for rect index 0-3 (BombPacked b3-6)
BombMaskBit:
    .byte $08, $10, $20, $40

; Bit masks for IsRoomDark/SetRoomDark (indexed 0-7; bits 4-7 used for rooms 0-3)
BitMaskTable:
    .byte $01, $02, $04, $08, $10, $20, $40, $80

; AND-mask to clear col 0-19's PF bit (inverse of convert_room.pf_values):
;   col 0-3   → PF0 bits 4-7; col 4-11 → PF1 bits 7-0; col 12-19 → PF2 bits 0-7
BombClearMask:
    .byte $EF, $DF, $BF, $7F                    ; col 0-3  (PF0)
    .byte $7F, $BF, $DF, $EF, $F7, $FB, $FD, $FE ; col 4-11 (PF1)
    .byte $FE, $FD, $FB, $F7, $EF, $DF, $BF, $7F ; col 12-19 (PF2)

; --- Player sprites: 8×8, 4 pixels wide (bits 7-4) ---
; Row 2 has the "eye" notch to show facing direction.
PlayerSpriteRight:
    .byte %11110000             ; row 0
    .byte %11110000             ; row 1
    .byte %11000000             ; row 2 — eye on right
    .byte %11110000             ; row 3
    .byte %11110000             ; row 4
    .byte %11110000             ; row 5
    .byte %11110000             ; row 6
    .byte %11110000             ; row 7

PlayerSpriteLeft:
    .byte %11110000             ; row 0
    .byte %11110000             ; row 1
    .byte %00110000             ; row 2 — eye on left
    .byte %11110000             ; row 3
    .byte %11110000             ; row 4
    .byte %11110000             ; row 5
    .byte %11110000             ; row 6
    .byte %11110000             ; row 7

; --- Level data ---
; Generated from level JSON via tools/convert_level.py.
; Do not edit by hand — regenerate with build.sh.
    include "generated/levels_data.asm"

; --- Level constants ---
ENEMY_SPIDER   = 0
ENEMY_BAT      = 1
ENEMY_SNAKE    = 2
ENEMY_TENTACLE = 3
ENEMY_MOTH     = 4
LAMP           = 5             ; type-5 enemy record = editor lamp (white square)
ENEMY_DATA_STRIDE = 6

; --- Level table + connections (generated) ---
    include "generated/levels.asm"

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
; Input: A = scanline. Output: X = tile row.
; Lookup table: constant-time. Subtract loop grew linearly with RoomY and
; made 3× PlayerHitsMap (fall 2 + L/R 1) exceed overscan TIM64T=35 (~2240c)
; in 4-rect rooms → frame >262 lines → vertical roll when strafing while falling.
YToCellRow subroutine
    tay
    lda YToRowTable,Y
    tax
    rts

; 192 entries: A/12 for A=0..191 (matches old loop for full scanline range).
YToRowTable:
    .byte 0,0,0,0,0,0,0,0,0,0,0,0
    .byte 1,1,1,1,1,1,1,1,1,1,1,1
    .byte 2,2,2,2,2,2,2,2,2,2,2,2
    .byte 3,3,3,3,3,3,3,3,3,3,3,3
    .byte 4,4,4,4,4,4,4,4,4,4,4,4
    .byte 5,5,5,5,5,5,5,5,5,5,5,5
    .byte 6,6,6,6,6,6,6,6,6,6,6,6
    .byte 7,7,7,7,7,7,7,7,7,7,7,7
    .byte 8,8,8,8,8,8,8,8,8,8,8,8
    .byte 9,9,9,9,9,9,9,9,9,9,9,9
    .byte 10,10,10,10,10,10,10,10,10,10,10,10
    .byte 11,11,11,11,11,11,11,11,11,11,11,11
    .byte 12,12,12,12,12,12,12,12,12,12,12,12
    .byte 13,13,13,13,13,13,13,13,13,13,13,13
    .byte 14,14,14,14,14,14,14,14,14,14,14,14
    .byte 15,15,15,15,15,15,15,15,15,15,15,15

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

; S6.2: skip rects destroyed by a bomb (WallMask bit for this index)
    tya
    sec
    sbc #1
    lsr
    lsr                         ; index = (base-1)/4
    tax
    cpx #4
    bcs .MaskOk                 ; index ≥4 never masked
    lda BombMaskBit,X
    and BombPacked
    bne .nextRect               ; destroyed → not solid
.MaskOk:

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
    jsr HotOverlapFlag          ; set Temp b7 if proposed cells include hot rock
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
    jmp Overscan                 ; return to bank0 after HUD band

; ------------------------------------------------------------------------------
; Jet engine audio (channel 1) — old two-stroke combustion buzz.
; Re-reads SWCHA directly (Temp may be clobbered by overscan subroutines).
; AUDF = JET_AUD_BASE - JetPower/8 - (TickCounter&1):
;   - JetPower/8 (0..4) revs the pitch up as thrust ramps
;   - frame-parity wobble (+0/+1) gives the put-put sputter at 30 Hz
; Channel 0 stays free for bomb blips.
; After fold pads to keep main code under $FC68.
; ------------------------------------------------------------------------------
UpdateJetSound:
    lda SWCHA
    and #%00010000              ; D4 = up (0 = pressed)
    beq .JetOn
    lda #0                      ; throttle off -> mute engine
    sta AUDV1
    rts
.JetOn:
    lda #1                      ; 4-bit poly = raspy engine buzz
    sta AUDC1
    lda JetPower
    lsr
    lsr
    lsr                         ; JetPower/8 = 0..4 (revs with thrust)
    eor #$ff
    clc
    adc #1                      ; A = -(JetPower/8)
    clc
    adc #JET_AUD_BASE           ; A = base - JetPower/8
    tax
    lda TickCounter
    and #1
    beq .JetWob
    dex                         ; parity wobble -1 every other frame (30 Hz sputter)
.JetWob:
    txa
    sta AUDF1
    lda #JET_AUD_VOL
    sta AUDV1
    rts

; ------------------------------------------------------------------------------
; AddScore — add BCD amount in A (e.g. #$50, #$75) to HUD score.
; ScoreTh/ScoreHu = binary digits 0-9; ScoreTe = packed BCD (tens*16+ones).
; Carry: ScoreTe >= $a0 → wrap and inc ScoreHu; ScoreHu >= 10 → wrap and
; inc ScoreTh; ScoreTh >= 10 → cap at 9 (display is 4 digits).
; Clobbers A. After fold pads so $FC68 org stays valid.
; ------------------------------------------------------------------------------
AddScore:
    clc
    adc ScoreTe
    cmp #$a0
    bcc .ASstoreTe
    sbc #$a0
    pha                         ; save wrapped ScoreTe
    inc ScoreHu
    lda ScoreHu
    cmp #10
    bcc .AShuOk
    lda #0
    sta ScoreHu
    inc ScoreTh
    lda ScoreTh
    cmp #10
    bcc .ASthOk
    lda #9
    sta ScoreTh
.ASthOk:
.AShuOk:
    pla
.ASstoreTe:
    sta ScoreTe
    rts

; ------------------------------------------------------------------------------
; ReloadLevel — reset level to initial state (all enemies back, 3 lives).
; Reloads level data from ROM and respawns player at start.
; Score is NOT reset (persists across deaths).
; After fold pads to keep main code under $FC68.
; ------------------------------------------------------------------------------
ReloadLevel:
    lda #3
    sta PlayerLives
    lda #BOMBS_MAX
    sta PlayerBombs
    lda Level
    jsr LoadLevel
    lda #0
    sta vyLo
    sta vyHi
    sta JetPower
    sta PlayerYSub
    rts

; ------------------------------------------------------------------------------
; HotOverlapFlag — if the player's proposed tile range (CollisionCell*) overlaps
;   any hot-only rect, set Temp bit 7 (HotBump). Called from PlayerHitsMap HIT
;   while CollisionCell* still describe the rejected position. Clobbers A/X/Y/
;   MapPtr/RectCount (PlayerHitsMap returns immediately after).
; Hot section: after solid count + N*4 solid bytes → hot count + M*4 hot bytes.
; ------------------------------------------------------------------------------
HotOverlapFlag:
    lda RoomRectsLo
    sta MapPtrLo
    lda RoomRectsHi
    sta MapPtrHi
    ldy #0
    lda (MapPtrLo),Y            ; solid count
    asl
    asl                         ; *4
    clc
    adc #1                      ; +1 count byte → hot count offset
    tay
    lda (MapPtrLo),Y
    beq .HOVdone                ; no hot rects
    sta RectCount
    iny                         ; first hot rect base
.HOVloop:
    tya
    pha
    ; Column overlap (same tests as PlayerHitsMap)
    lda (MapPtrLo),Y            ; rect.x
    cmp CollisionCellX
    beq .HOVcolOk
    bcc .HOVcolOk
    jmp .HOVnext
.HOVcolOk:
    sta CollisionX
    iny
    iny                         ; Y = base+2 (w)
    clc
    lda (MapPtrLo),Y
    adc CollisionX
    cmp CollisionEndX
    beq .HOVnext
    bcc .HOVnext
    ; Row overlap — same dey count as PlayerHitsMap (base+2 → base+1).
    ; Extra deys here read the hot-count byte as rect.y → death zone shifted up.
    dey                         ; Y = base+1 (y)
    lda (MapPtrLo),Y
    cmp CollisionEndY
    beq .HOVrowOk
    bcc .HOVrowOk
    jmp .HOVnext
.HOVrowOk:
    iny
    iny                         ; Y = base+3 (h)
    clc
    lda (MapPtrLo),Y
    dey
    dey                         ; Y = base+1 (y)
    adc (MapPtrLo),Y            ; y+h
    cmp CollisionCellY
    beq .HOVnext
    bcc .HOVnext
    ; Hot hit
    pla
    lda Temp
    ora #%10000000
    sta Temp
    rts
.HOVnext:
    pla
    clc
    adc #4
    tay
    dec RectCount
    bne .HOVloop
.HOVdone:
    rts

; ------------------------------------------------------------------------------
; LoseLifeHot — same life path as enemy/timer hit (Temp b7 already set).
; ------------------------------------------------------------------------------
LoseLifeHot:
    dec PlayerLives
    bpl .LLHstay
    lda #3
    sta PlayerLives
    lda #$FF
    sta DeadEnemyIdx
    jsr ReloadLevel
    rts
.LLHstay:
    lda #0
    sta vyLo
    sta vyHi
    sta JetPower
    sta PlayerYSub
    rts

; ------------------------------------------------------------------------------
; IsRoomDark — Z=1 if current room's dark flag is clear (lit), Z=0 if dark.
; RoomDarkMask lives in EnemyRamD bits 4-7 (bit4=room0 … bit7=room3).
; Clobbers A and X only. Y preserved. Callers must NOT rely on X after return.
; ------------------------------------------------------------------------------
IsRoomDark:
    lda RoomNo
    cmp #4
    bcs .IRDlit                 ; rooms 4+ never dark (mask only covers 0-3)
    clc
    adc #4                      ; bit index = 4 + RoomNo
    tax
    lda BitMaskTable,X
    and EnemyRamD               ; Z=1 → lit (bit clear), Z=0 → dark
    rts
.IRDlit:
    lda #0                      ; Z=1 → lit
    rts

; ------------------------------------------------------------------------------
; SetRoomDark — set dark flag for current RoomNo (bits 4-7 of EnemyRamD).
; Clobbers A/X. Cleared only by LoadLevel (level end/reload).
; ------------------------------------------------------------------------------
SetRoomDark:
    lda RoomNo
    cmp #4
    bcs .SRDdone                ; rooms 4+ unsupported
    clc
    adc #4
    tax
    lda BitMaskTable,X
    ora EnemyRamD
    sta EnemyRamD
.SRDdone:
    rts

; ------------------------------------------------------------------------------
; LoadRoomBottomColor — A = RoomEnemies pad color for RoomNo (0 = band off).
; Clobbers A, Y. ROM record: ptr_lo, ptr_hi, count, bottom_color (4 bytes).
; ------------------------------------------------------------------------------
LoadRoomBottomColor:
    lda RoomNo
    asl                         ; room * 4
    asl
    tay
    iny
    iny
    iny                         ; +3 = bottom_color
    lda (LevelEnemyLo),Y
    rts

; ------------------------------------------------------------------------------
; CheckBandTouch — overscan: if band on and RoomY in bottom tile row → life.
; Bottom row starts at scanline 132; sprite origin RoomY >= 125 enters it
; (125 + PLAYER_HEIGHT - 1 = 132). Same path as hot/enemy: lose life, then
; respawn 12 scanlines up (min 0).
; ------------------------------------------------------------------------------
CheckBandTouch:
    jsr LoadRoomBottomColor
    beq .CBTdone                ; band off
    lda RoomY
    cmp #125
    bcc .CBTdone                ; above band
    jsr LoseLifeBand
.CBTdone:
    rts

; ------------------------------------------------------------------------------
; LoseLifeBand — life path + RoomY -= 12 (min 0). Full reload skips the shift
; (LoadLevel already places the player safely).
; ------------------------------------------------------------------------------
LoseLifeBand:
    dec PlayerLives
    bpl .LLBstay
    lda #3
    sta PlayerLives
    lda #$FF
    sta DeadEnemyIdx
    jsr ReloadLevel
    rts
.LLBstay:
    lda #0
    sta vyLo
    sta vyHi
    sta JetPower
    sta PlayerYSub
    lda RoomY
    sec
    sbc #LINES_PER_TILE
    bcs .LLBstore
    lda #0
.LLBstore:
    sta RoomY
    rts

; ------------------------------------------------------------------------------
; BuildColupF — 12-byte final COLUPF image at ColupfBuf ($E7-$F2).
;   Stripe: rows 0-3,8-11 = LevelWallColor; rows 4-7 = LevelWallColor2.
;   Hot rows overwrite with TickCounter-bit4 pulse (COLOR_HOT_Y/R).
;   $E7-$F2 overlaps PlayerBombs/BombSnd/RoomWallMask ($F0-$F2): save those
;   to collision temps (free until overscan), restore at .AfterRows.
;   Bank1 clobbers $E0-$EF during HUD; VBLANK rebuilds every frame.
; ------------------------------------------------------------------------------
BuildColupF:
    lda PlayerBombs
    sta CollisionCellY          ; save $F0
    lda BombSnd
    sta CollisionEndX           ; save $F1
    lda RoomWallMask
    sta CollisionEndY           ; save $F2
    ; --- stripe fill ---
    ldx #0
.BCFstripe:
    cpx #4
    bcc .BCFc1
    cpx #8
    bcs .BCFc1
    lda LevelWallColor2
    jmp .BCFstore
.BCFc1:
    lda LevelWallColor
.BCFstore:
    sta ColupfBuf,X
    inx
    cpx #TILE_ROWS
    bne .BCFstripe
    ; --- pulse color → Temp (free until .BgStore) ---
    lda TickCounter
    and #$10
    beq .BCFpulseY
    lda #COLOR_HOT_R
    jmp .BCFpulse
.BCFpulseY:
    lda #COLOR_HOT_Y
.BCFpulse:
    sta Temp
    ; --- walk hot rects, overwrite those rows ---
    lda RoomRectsLo
    sta MapPtrLo
    lda RoomRectsHi
    sta MapPtrHi
    ldy #0
    lda (MapPtrLo),Y
    asl
    asl
    clc
    adc #1
    tay                         ; Y → hot count
    lda (MapPtrLo),Y
    beq .BCFdone
    sta RectCount
    iny
.BCFrect:
    tya
    pha
    iny                         ; Y = base+1 (y)
    lda (MapPtrLo),Y
    sta CollisionCellX          ; first row
    iny
    iny                         ; Y = base+3 (h)
    clc
    lda (MapPtrLo),Y
    adc CollisionCellX
    sta CollisionX              ; one-past last row
    ldx CollisionCellX
.BCFrow:
    cpx #TILE_ROWS
    bcs .BCFrectDone
    cpx #12
    bcs .BCFrectDone
    lda Temp
    sta ColupfBuf,X
    inx
    cpx CollisionX
    bne .BCFrow
.BCFrectDone:
    pla
    clc
    adc #4
    tay
    dec RectCount
    bne .BCFrect
.BCFdone:
    ; --- Dark room: walls black; fuse (state=1) walls dark grey ---
    jsr IsRoomDark
    beq .BCFdarkDone            ; lit → keep stripe/hot colors
    lda BombPacked
    and #%00000011
    cmp #1
    bne .BCFdarkBlack
    lda #COLOR_DARK_PF          ; bomb fuse active → dark grey walls
    jmp .BCFdarkFill
.BCFdarkBlack:
    lda #COLOR_CAVE_BG          ; black walls (matches black background)
.BCFdarkFill:
    ldx #0
.BCFdarkLoop:
    sta ColupfBuf,X
    inx
    cpx #TILE_ROWS
    bne .BCFdarkLoop
.BCFdarkDone:
    rts

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
