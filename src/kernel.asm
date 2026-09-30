    processor 6502

; ==============================================================================
; savior kernel — HERO-style fixed-time rendering kernel
; ==============================================================================
; A from-scratch Atari 2600 kernel modeled after Activision's HERO.
;
; Architecture:
;   - 4K ROM at $F000-$FFFF (no bankswitching)
;   - Kernel renders 192 visible scanlines: 144 cave + 48 HUD
;   - Cave: 3 tile rows × 48 scanlines each
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
INPT4   = $0C                    ; fire button, D7: 0=pressed, 1=released
                                 ; (HERO reads BIT $0C; must match bank1 EQU)

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
LaserBeamOn     byte            ; S2.2r2: $02 while fire held else $00 —
                                ; .Line beam gate (reuses dead Scanline byte)
LineCount       byte            ; scanlines remaining in current tile row
BombY           byte            ; bomb drop Y (was dead TileRow; scanline snapshot)
Grp0Ptr         byte            ; pointer to player sprite data (lo)
Grp0PtrHi       byte            ; pointer to player sprite data (hi)
Temp            byte            ; general scratch

; Collision ZP variables (from comparison/lo-a-rad-dragon/bank0.asm)
MapPtrLo        byte            ; rect cache slot: rect4.x (P3.4 — EnterRoom copies;
                                ; was RETIRED by P3.6 fold; addresses frozen)
MapPtrHi        byte            ; rect cache slot: rect4.y (P3.4 — see MapPtrLo)
CollisionX      byte            ; scratch for mirror calc
CollisionCellX  byte            ; player max tile column
CollisionCellY  byte            ; player top tile row
CollisionEndX   byte            ; player min tile column
CollisionEndY   byte            ; player bottom tile row
RoomRectsLo     byte            ; pointer to room rectangle data (low)
RoomRectsHi     byte            ; pointer to room rectangle data (high)
RectCount       byte            ; rectangle loop counter (kernel also uses it as
                                ; RowIdx — tile-row counter, re-init at kernel entry)
RowIdx          = $92           ; kernel tile-row counter; aliases RectCount.
                                ; RectCount users all run post-kernel (overscan)
                                ; and store before their own loops, so no conflict.

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
LevelMinerRoom  byte            ; room index; b7 means miner faces right
MinerX          byte            ; miner X position (room pixel coords)
MinerY          byte            ; miner Y position (room pixel coords)
LevelStartRoom  byte            ; level origin room (spawn + enemy-hit teleport)
LevelStartX     byte            ; level origin X
LevelStartY     byte            ; level origin Y
LevelWallColor  byte            ; wall color 1 (bands 0 and 2)
LevelWallColor2 byte            ; wall color 2 (band 1)
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
ObjBase         byte            ; GRP1 sprite base offset into ObjSprites (0 = off)
ActiveObjectX   byte            ; active object X (room pixel coords)
ActiveObjectY   byte            ; active object Y (scanline coords)
EnemyIndex      byte            ; current enemy index in room enemy list
EnemyDeadMask   byte            ; per-enemy dead bits b0-2 (0 = alive; was DeadEnemyIdx)

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
PF2ScoreBuf     = $C6           ; 5 bytes: PF2 values for score rows 0-4 (legacy; no users)

; P3.4 rect cache — solid rect list copied once per EnterRoom, walked directly
; by PlayerHitsMap with NO bank2 fold (fold mid-function switched the EXECUTION
; bank; only byte-identical pad code may span a switch). Windows (Y is the
; global rect offset: count read first, rect0 base Y=0):
;   $C6      count        (RcBase+0; also RcBase)
;   $C7-$CE  rect0, rect1 (window1: FetchPtr=$C7, Y=0..7)
;   $D3-$DA  rect2, rect3 (window2: FetchPtr=$CB, Y=8..15)
;   $89/$8A  rect4.x/y    (MapPtrLo/MapPtrHi; .Stage3 fixed addresses)
;   $DE/$DF  rect4.w/h    (PF2Buf rows 3-4, fill-only)
; All four targets are fill-only/retired — see docs/zp_layout_skill.md alias
; rule: LoadPFBuffer writes rows 0-2 only, kernel .Row reads X=0..2, bank1
; touches $E0-$EF only, MapPtr* has no other user.
RcBase          = $C6           ; rect cache count + window1 base marker
RcW1            = $C7           ; window1 FetchPtr lo (rect0 x at Y=0)
RcW2            = $CB           ; FetchPtr lo for window2 ($CB + Y=8 = $D3)
Rc4W            = $DE           ; rect4.w cache (PF2Buf+3)
Rc4H            = $DF           ; rect4.h cache (PF2Buf+4)

; PF cave buffers (copied from ROM during VBLANK, read by kernel via absolute indexed)
; These share ZP space with bank1's HUD variables — safe because bank1
; runs AFTER the cave kernel. Bank1 overwrites them during HUD band;
; VBLANK re-populates them before the next kernel frame.
PF0Buf          = $C3           ; 12 bytes: TilePF0 values per row
                                ; (rows 0-2 alias EnemyRamY — see contract)
PF1Buf          = $CF           ; 12 bytes: TilePF1 values per row
                                ; (only rows 0-2 are ever read: kernel .Row
                                ; X=0..2 and ClearPFColumn rows 0..2)
RoomBandColor   = $D2           ; ALIAS PF1Buf[3] (dead fill row) — band-color
                                ; cache (level_bank_plan P2.5). FIX 2026-09-28:
                                ; was $D1 = PF1Buf[2], which collided with the
                                ; kernel's `lda PF1Buf,X` (X=2) — the band
                                ; color (room 0 = $00) overwrote the bottom
                                ; band's PF1 wall pattern every frame
                                ; (phase_1 dumps: $D1=00 vs model $ff →
                                ; mid-wall gap + cell-map collision mismatch).
                                ; Rows 3-11 of PF1Buf are fill-only: nothing
                                ; reads them (bank1 has no $D2 EQU). Writer:
                                ; VBLANK stage AFTER LoadPFBuffer/BuildColupF
                                ; (fold from LevelEnemy+RoomNo*4+3). Readers:
                                ; kernel .WaterRow (via LoadRoomBottomColor) +
                                ; overscan CheckBandTouch. Window: written
                                ; post-buffers → survives VBLANK, kernel,
                                ; bank1 HUD ($E0-$EF only); overscan physics
                                ; never touches $D2; next VBLANK restages.
PF2Buf          = $DB           ; 12 bytes: TilePF2 values per row ($DB-$E6)
                                ; $E7-$F2 = ColupfBuf (12) — overlaps bombs
                                ; $F0-$F2: saved to CollisionCellY/EndX/EndY
                                ; during VBLANK+kernel, restored before HUD.
ColupfBuf       = $E7           ; 12 bytes: final COLUPF per tile row (stripe+hot)
FetchPtr        = $E0           ; fold-indirect pointer ($E0 lo, $E1 hi) —
                                ; ALIAS over PF2Buf rows 5-6. Contract (fold
                                ; wins): stage addr immediately before a
                                ; FoldIndirect batch; no foreign writer in
                                ; the VBLANK/overscan stage→use window
                                ; (bank1 scorePtr1 rebuilds in HUD band,
                                ; after both windows).

; Enemy RAM shadow — live X/Y + packed flags. ROM records are read-only.
; Sequential vars end at $BC; EnemyRam occupies $BD-$BF + $C1-$C2 (5);
; $C0 = LaserState (the one free byte — see docs/zp_layout_skill.md).
; Score lives at $F3-$F5 only ($F6/$F7 = BombX/BombTimer).
; EnemyRamY ($C3, 3B) ALIASES PF0Buf rows 0-2 — E0/E1 contract:
;   writers: RefreshEnemyY via DeriveEnemyY (overscan entry, EVERY frame —
;            VBLANK LoadPF0Only clobbers $C3 each frame; bat Y is derived
;            from ROM spawn + TickCounter, no stored movement state) +
;            LoadEnemyRam (EnterRoom init);
;   readers: SelectActiveObject (VBLANK — MUST run BEFORE LoadPF0Only),
;            CheckEnemyHit + LaserHitTest (overscan, after the refresh).
;   Ordering guards live in verify_build.py (VBLANK + EnterRoom + bank1).
;   PF1/PF2 rows 0-2 have NO per-frame stomp → full LoadPFBuffer runs only
;   on EnterRoom; VBLANK does the 3-fold PF0 repair (LoadPF0Only).
EnemyRamX       = $BD           ; 3 bytes: live X per enemy ($BD-$BF, slots 0-2
                                ; only — enemies+lamps capped at 3 by editor
                                ; kMaxRoomElements, convert_level MAX_ENEMIES,
                                ; verify_build; slot 3 would collide with $C0)
LaserState      = $C0           ; laser (S1): b7 fire held this frame,
                                ;   b6 fire held last frame, b5-4 spare,
                                ;   b1-0 sweep phase (0..3 = 0/8/16/8 px)
EnemyRamD       = $C1           ; dir bits 0-3 = enemy 0-3 (1=right, 0=left)
EnemyRamP       = $C2           ; bits0-3 moth phase (shared/sync); bits4-7
                                ;   vdir for spider/bat/tentacle (1=down)
EnemyRamY       = $C3           ; 3 bytes: live Y per enemy — ALIAS over
                                ;   PF0Buf[0..2]; see contract above

; ==============================================================================
; Constants
; ==============================================================================
PLAYER_HEIGHT   = 8             ; GRP1 object (enemy/miner) height; player uses PLAYER_SPRITE_H
PLAYER_SPRITE_H = 12            ; player sprite height in scanlines (8x12)
PLAYER_WIDTH    = 7             ; lit player sprite spans 7 pixels; REFP0 shift handled
ENEMY_WIDTH     = 8             ; snake GRP1 width ($ff = 8 px) — flush-out span
LAMP_WIDTH      = 4             ; OBJ_LAMP uses GRP1's leftmost 4 lit pixels
MINER_WIDTH     = 4             ; OBJ_MINER spans 4 lit GRP1 pixels
SNAKE_PATROL    = 4             ; patrol half-span from spawn X (was ENEMY_WIDTH)
TILE_COLUMNS    = 20            ; columns per half (reflected playfield)
TILE_ROWS       = 3             ; number of playable color bands
LINES_PER_TILE  = 48            ; scanlines per tile row
HUD_ROWS        = 1             ; HUD band (48 scanlines)
CAVE_LINES      = 144           ; TILE_ROWS × LINES_PER_TILE
VISIBLE_LINES   = 192           ; CAVE_LINES + (HUD_ROWS × LINES_PER_TILE)

; GRP1 sprite design offsets into ObjSprites (8 bytes each; 0 = blank/off)
OBJ_NONE        = 0
OBJ_MOTH        = 8
OBJ_SPIDER      = 16
OBJ_LAMP        = 24
OBJ_TENTACLE    = 32
OBJ_BAT         = 40
OBJ_SNAKE       = 48
OBJ_MINER       = 56
OBJ_BOMB        = 64

; Player bounds (must stay inside cave walls)
PLAYER_MIN_X    = 4             ; sprite flush with left edge (HERO)
PLAYER_MAX_X    = 159           ; horizontal logical-position clamp
PLAYER_MIN_Y    = 0
PLAYER_MAX_Y    = 132           ; CAVE_LINES - PLAYER_SPRITE_H

; Jetpack physics constants (HERO-style)
GRAVITY         = $0008         ; gravity per frame (signed 16-bit, + = down)
JET_MAX         = $20           ; max jet thrust accumulator
MAX_FALL        = $0200         ; max fall speed (positive = down)
JET_AUD_BASE    = $0F           ; engine AUDF base: freq = base - JetPower/8 - sputter
JET_AUD_VOL     = $08           ; engine volume while Up is held



; Facing direction of the player sprite's eye
FACING_RIGHT    = 0
FACING_LEFT     = 1

; LaserState bits (laser_implementation_plan S1)
LASER_HELD      = %10000000     ; b7: fire pressed this frame (INPT4 D7=0)
LASER_PREV      = %01000000     ; b6: fire pressed last frame
LASER_PHASE     = %00000011     ; b1-0: sweep phase 0..3 -> M0 offsets 0/8/16/8 px
LASER_HP        = %11000000     ; held + prev (state while fire stays held)

; Colors (emulator-aware: hue<<4 | luma<<1)
COLOR_PLAYER    = $48           ; red = sprite row0: stale VBLANK color on the
                                ; line before the sprite must match row0 or a
                                ; gold fringe shows above the sprite
; Player sprite per-row colors (PlayerColTable)
COLOR_P_RED     = $48           ; hue 4 luma 4 = red body
COLOR_P_YELLOW  = $1E           ; hue 1 luma 7 = yellow face
COLOR_P_GRAY    = $08           ; hue 0 luma 4 = grey pack + boots
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
                                    ; (NOT deletable: $F008 = GameStart is a
                                    ;  hardcoded cross-bank entry — bank1
                                    ;  stub `jmp $F008`; this jmp also keeps
                                    ;  $F183 Overscan + F0xx landmarks fixed)

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
    lda #$00
    sta EnemyDeadMask
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

    ; --- Set TIM64T for VBLANK ---
    ; P3.4 measured: VBLANK work worst 1311c (mean 1235c) after the rect
    ; cache (enter-copy + direct walk). #23 = 1472c = 161c headroom.
    ; Frame budget: V(#23) + O(#50) = 73 TIM64T units → 3 + 19.4 + 197.5 +
    ; 42.1 = 262 lines. (#75 was the pre-trim 293-line frame.)
    lda #23
    sta TIM64T

    ; --- Position player sprite horizontally ---
    lda RoomX
    sec
    sbc PlayerDir              ; counter REFP0's one-pixel shift when reflected
    ldx #0                      ; X=0 = player0
    jsr SetObjectXPos

    ; --- No sprite copy needed — kernel reads directly from ROM ---
    ; Do NOT HMOVE here: wait until P1 is positioned too. An early HMOVE
    ; applied stale bank1 HMP1 (score), and a second HMOVE after SelectActiveObject
    ; applied HMP0 twice → player fine-adjust doubled (visual teleport/jitter).

    ; --- Select which object GRP1 draws this frame (miner or enemy) ---
    ; MUST run before LoadPF0Only: reads EnemyRamY ($C3 = PF0Buf rows 0-2).
    jsr SelectActiveObject

    ; --- PF0 repair (the ONLY per-frame refresh; 3 folds ≈ 130c vs 384c) ---
    ; $C3-$C5 (PF0 rows 0-2) are stomped every frame by EnemyRamY; PF1/PF2
    ; rows 0-2 have NO per-frame writer (bank1 touches $E0-$EF only; rect
    ; caches + RoomBandColor live in dead rows 3-11) — full 9-fold rebuild
    ; only needed on EnterRoom.
    jsr LoadPF0Only
    jsr ApplyBombWalls          ; S6.1: re-apply thin-wall holes every frame
    jsr BuildColupF            ; stripe+hot COLUPF bytes into ColupfBuf ($E7-$F2)

    ; --- Band-color cache → RoomBandColor ($D2) for kernel+overscan (P2.5) ---
    ; ROM now lives in bank2: kernel-time fold is cycle-impossible on the
    ; .WaterRow line, so fold HERE (VBLANK, timer-paced) and hand the kernel
    ; a plain zp load. Stage FetchPtr immediately before the fold.
    lda RoomNo
    asl
    asl
    ora #3                      ; Y = RoomNo*4+3 (RoomNo*4 low bits are 0)
    tay
    lda LevelEnemyLo
    sta FetchPtr
    lda LevelEnemyHi
    sta FetchPtr+1
    ldx #0
    jsr FoldIndirect
    sta RoomBandColor

    ; --- Cave COLUBK for this frame → Temp (free until overscan) ---
    ; state=2: blink (60-BombTimer)&3 → black/yellow/red/yellow; else COLOR_CAVE_BG
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
    ; Constant-time phase: the old %3 subtract loop ran (elapsed)/3 iterations
    ; (up to 19 × 9c ≈ 171c) and GREW every frame for 60 frames — with a thin
    ; wall punched (ApplyBombWalls +224c) it blew the #23 VBL window late in
    ; state2 → 263-line frames → explosion flicker (2026-09-29). &3 = 4-phase,
    ; 60 frames = exact 15 cycles, starts black at explosion.
    lda #60
    sec
    sbc BombTimer
    and #3
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

    ; --- Facing: mirror sprite in hardware via REFP0 bit3 ---
    ; bank1 HUD writes REFP0=0 during the HUD band, so rewrite it every frame.
    lda PlayerDir
    asl
    asl
    asl                         ; FACING_LEFT(1) -> $08, FACING_RIGHT(0) -> $00
    sta REFP0

    ; --- Sprite frame: legs flutter at 15 Hz while the jet burns ---
    lda JetPower
    beq .FrameA
    lda TickCounter
    and #%00000100
    beq .FrameA
    lda #<PlayerSpriteB
    ldy #>PlayerSpriteB
    jmp .SetGrpPtr
.FrameA:
    lda #<PlayerSpriteA
    ldy #>PlayerSpriteA
.SetGrpPtr:
    sta Grp0Ptr
    sty Grp0PtrHi

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
;   .Row (×3): set PF registers once per color band, init scanline counter
;   .Line (×48): render one scanline — sprite check + loop control
;
; PF registers persist in TIA, so writing once per tile row is sufficient.
; The inner .Line loop has NO PF writes — only sprite rendering.
; ==============================================================================

    ; --- Reset TIA state for cave rendering ---
    ; HUD may have changed NUSIZ0/1, COLUP0/1 — must restore
    lda #$30                      ; NUSIZ0 = single copy P0 + M0 width 8 (laser S2.1)
    sta NUSIZ0
    lda #$00                      ; NUSIZ1 = single copy
    sta NUSIZ1
    lda #COLOR_PLAYER             ; restore player color (was green for HUD lives)
    sta COLUP0
    lda #0                        ; clear VDELP0/VDELP1 (bank1 HUD sets them to 1)
    sta VDELP0
    sta VDELP1
    ; ENAM0 NOT cleared here: kernel .Line owns it (BeamMask AND LaserBeamOn
    ; per in-window line; LaserBeamOn boots $00 via .ClearZP = beam off
    ; until first fire press)
    sta ENAM1                     ; disable missile 1
    sta ENABL                     ; disable ball

    lda #0
    sta RowIdx                  ; tile-row counter (0-2); object section clobbers X
                                ; (Scanline no longer maintained — S2.2 removed
                                ;  its only reader in .Line)
    sec
    sbc RoomY                   ; A = -RoomY = A0 at scanline 0
    tay                         ; running-Y: Y = A0 for the next .Line (10c/line
                                ; cheaper than recomputing Scanline-RoomY each line)
    ldx #0                      ; tile row counter (0-2)

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
    ; --- Scanlines this pass: rows 0/1 = 48; row 2 = 36 bodies. The bottom
    ; water strip (last ~12 lines, bottom_band_plan rule 2) renders in
    ; .WaterRow after this pass — its own setup line + 11 bodies keeps the
    ; row-2 total at 49 lines (setup+48) exactly as before the split.
    cpx #TILE_ROWS-1
    bne .RowLines48
    lda #LINES_PER_TILE-12       ; row 2: 36 bodies
    bne .RowLinesLC              ; always (36 != 0)
.RowLines48:
    lda #LINES_PER_TILE
.RowLinesLC:
    sta LineCount

    ; --- Sync to next scanline ---
    sta WSYNC

.Line:
    ; --- Player sprite: color for THIS line, graphics byte for NEXT line ---
    ; GRP0 written on line S displays on line S+1 (latched at the sprite's
    ; window start after the write) — index graphics with A0+1 ($ff wraps
    ; to 0 = row0 on the line before the sprite).
    ; Running-Y: Y = A0 = Scanline - RoomY is computed ONCE at kernel entry
    ; (sec/sbc RoomY/tay); .Line's iny advances it (Y = A0+1 after the
    ; graphics write = A0 of the next line). Nothing between rows may touch
    ; Y — the water-strip jsr (.WaterRow LoadRoomBottomColor clobbers Y)
    ; pushes/pops it.
    ; Cycle budget from .Line (body starts c8, dec/bne already paid), recounted
    ; from bank0.lst (worst = in-window color/beam/GRP0 + object in-range):
    ;   color+beam+GRP0 (cpy..sta GRP0 incl BeamMask+gate) = 37c
    ;   object (tya..sta GRP1) = 24c
    ;   worst = 61c -> sta WSYNC at c69 (write c71) — 2c margin vs c73. FITS.
    ; ObjSprites+71 must stay in the $FExx page (else lda ObjSprites,X
    ; page-crosses, +1c on the GRP1 fetch) — verify_build enforces this.
    ; Branch targets all same-page (3c taken) and BeamMask operand in $FFxx
    ; (5c fetch budgeted) — both enforced by verify_build (S2.2 guards).
    ; GRP1 object section clobbers X (ObjSprites index) — row counter lives in
    ; RowIdx and X is reloaded after bne. Row-advance +6c on the .Row setup
    ; scanline (segment 63c -> 69c <= 76c): frame length unchanged.
    ; The old Scanline/sec/sbc/tay prefix cost 10c more (body 66c -> WSYNC
    ; write on cycle 76 = one cycle late): WSYNC stalled a full line per
    ; overlapping scanline — stretched cave row, HUD pushed down, and with
    ; GRP1 flicker rotation the frame length alternated (one-tile oscillation).
    ; Keep the hot path at <= ~68c: an overrun duplicates the scanline.
    cpy #PLAYER_SPRITE_H
    bcs .GrpSkip                ; A0 >= 12 (incl $ff): no color this line
    lda PlayerColTable,Y        ; 4c — per-row color from ROM
    sta COLUP0                  ; COLUP0 has no latch: applies to this line
    ; --- Laser S2.2: ENAM0 = beam mask for THIS line (in-window only) ---
    ; BeamMask = {0,0,2,2,0,...} → ENAM0 on exactly RoomY+2..RoomY+3.
    ; In-window path is the only safe place (Y<12 guaranteed); outside the
    ; window ENAM0 keeps its last in-window write ($00 at A0=11) — no HUD
    ; artifact. Table lives in $FFxx (cross = deterministic 5c): +8c/line.
    lda BeamMask,Y              ; 5c (cross $F1→$FF) — table MUST stay $FFxx
    and LaserBeamOn             ; 3c — S2.2r2 gate: $02 only while fire held
    sta ENAM0                   ; 3c (bar showed without fire before this)
.GrpSkip:
    iny                         ; Y = A0+1 ($ff wraps to 0 = sprite row 0)
    cpy #PLAYER_SPRITE_H
    bcs .GrpZero                ; Y >= 12: blank (row11 shows via line10)
    lda (Grp0Ptr),Y             ; 5c — byte for the NEXT scanline
    sta GRP0
.Grp1:

    ; --- GRP1 SECOND (object/enemy sprite): one design row per scanline ---
    ; ObjTop..ObjTop+7 window → row byte from ObjSprites[ObjBase + offset].
    ; Object off: ObjBase=0 → blank rows. S2.2: ObjTop is RoomY-relative;
    ; Y here = A0+1 = next line's A0, so `Y - ObjTopRel` = Scanline - ObjTop
    ; (mod 256, exact). In-object iff result 0..7 → `cmp #8/bcs` (C=0 in
    ; range → adc adds exact ObjBase). Replaces `lda Scanline/sec/sbc/bcc`
    ; (−6c in-range) and the `inc Scanline` (−5c) — Scanline now unused.
    tya
    sec
    sbc ObjTop                  ; A = Y - ObjTopRel (= Scanline - ObjTop, mod 256)
    cmp #PLAYER_HEIGHT
    bcs .ObjZero                ; above (negative mod ≥65) or at/below bottom
    adc ObjBase
    tax
    lda ObjSprites,X
    sta GRP1
.AfterObj:

    ; --- Loop control ---
    sta WSYNC                   ; wait for end of this scanline
    dec LineCount               ; decrement scanlines remaining in row
    bne .Line                   ; loop if more scanlines in this row

    ; --- Advance to next tile row (X clobbered by object section: reload) ---
    ldx RowIdx
    inx
    stx RowIdx
    cpx #TILE_ROWS
    beq .WaterRow                ; row 2 done -> water strip pass
    cpx #TILE_ROWS+1
    beq .AfterRows               ; water pass done (RowIdx wrapped to 4)
    jmp .Row
.WaterRow:
    ; PF0/1/2 + COLUPF + COLUBK(Temp) from row 2's setup persist — the strip
    ; overlays the same cells, so only the band color + 11 lines are needed.
    ; Band color: blink (BombPacked state=2) keeps Temp; 0 = band off.
    lda BombPacked
    and #%00000011
    cmp #2
    beq .WRSkip
    jsr LoadRoomBottomColor     ; cache read — A only, Y preserved (was saved:
                                ; old ROM body clobbered Y)
    beq .WRRestore              ; band off (0): keep Temp, no store
    sta COLUBK
.WRRestore:
.WRSkip:
    lda #11                     ; bodies: setup line + 11 = 12-line strip
    sta LineCount
    sta WSYNC
    jmp .Line
.GrpZero:                       ; dead space: entered only by bcs from .Line
    lda #0                      ; (nothing falls through `jmp .Row`)
    sta GRP0
    jmp .Grp1
.ObjZero:
    lda #0
    sta GRP1
    jmp .AfterObj
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

    ; --- Set TIM64T for overscan ---
    ; P3.4: overscan work worst 2104c (heavy, enemy room, rect cache in) →
    ; #50 = 3200c = 1096c headroom (was #35 = 2240c = 136c — positive but
    ; too tight for transition frames). V(#23)+O(#50) = 73 units = 262 lines.
    lda #50
    sta TIM64T

    ; --- Rewrite EnemyRamY ($C3 alias was clobbered by VBLANK PF refresh) ---
    jsr RefreshEnemyY

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

    ; --- Laser (S1+S2.1): fire state + M0 beam position (body after fold pads) ---
    jsr LaserInput             ; state + RESM0/HMM0/ENAM0; Temp (joystick) untouched

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

    ; --- Bottom band touch (RoomY in row 2 + band color on) → lose life ---
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
    lda #$00
    sta EnemyDeadMask
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
; LoadPF0Only (VBLANK, every frame): PF0 phase only — 3 folds ≈ 130c.
;   Repairs the per-frame EnemyRamY stomp of $C3-$C5 (PF0 rows 0-2).
; LoadPFBuffer (EnterRoom only): full 3-phase rebuild, 9 folds ≈ 384c.
;   PF1/PF2 rows 0-2 have no per-frame writer, so they only need rebuilding
;   once per room (bank1 touches $E0-$EF only; rect caches + RoomBandColor
;   live in dead rows 3-11).
; Uses RoomPF0Lo/Hi, RoomPF1Lo/Hi, RoomPF2Lo/Hi (set by EnterRoom).
; ------------------------------------------------------------------------------
; P3.3: per-phase fold reads (level data lives in bank2). Stage FetchPtr
; immediately before each batch.
; Fill = 3 bytes per register (rows 0-2): the kernel .Row reads X=0..2 and
; ClearPFColumn walks rows 0..2 — buffer bytes 3-11 are fill-only dead weight
; (every generated model has 00 there; bank1 score uses its own $B3/$C6 bufs).
; Cut 2026-09-28 with the $D2 band-color fix: saves ~27 folds ≈ 850c of VBLANK
; setup (the #75 timer had only ~273c headroom → variable setup blew it and
; the expired-timer garbage wait scattered frame lengths) and stops the fill
; from clobbering RoomBandColor = $D2 (PF1Buf[3]).
; Split 2026-09-29: VBLANK calls LoadPF0Only instead of LoadPFBuffer
; (-254c/frame) — level-1 object rooms + wall mask blew the #23 window
; (worst 1539c, -67 → constant 263-line frames ≈ 1s after blast).
LoadPF0Only:
    ; --- Phase 0: PF0 → $C3-$C5 — stage once ---
    lda RoomPF0Lo
    sta FetchPtr
    lda RoomPF0Hi
    sta FetchPtr+1
    ldy #0
.LPB_PF0:
    jsr FoldIndirect
    sta PF0Buf,Y
    iny
    cpy #3
    bne .LPB_PF0
    rts

LoadPFBuffer:               ; EnterRoom only — full rebuild (all 3 phases)
    ; --- Phase 1: PF1 → $CF-$D1 — stage once ---
    lda RoomPF1Lo
    sta FetchPtr
    lda RoomPF1Hi
    sta FetchPtr+1
    ldy #0
.LPB_PF1:
    jsr FoldIndirect
    sta PF1Buf,Y
    iny
    cpy #3
    bne .LPB_PF1

    ; --- Phase 2: PF2 → $DB-$DD — stage once (rows 0-2 never touch $E0/$E1,
    ;     so the P3.3 per-row re-stage is dead too) ---
    lda RoomPF2Lo
    sta FetchPtr
    lda RoomPF2Hi
    sta FetchPtr+1
    ldy #0
.LPB_PF2:
    jsr FoldIndirect
    sta PF2Buf,Y
    iny
    cpy #3
    bne .LPB_PF2
    jmp LoadPF0Only           ; tail: PF0 phase + rts — jsr here would cost
                              ; +1 stack level (EnterRoom path hit SP $F5,
                              ; stomping BombTimer $F7; sim_bomb_fuse gate)

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
    asl
    asl
    tay
    ; --- Fold batch (P2.6): room pointers live in bank2's RoomDataTable.
    ; Stage FetchPtr = LevelPFData immediately before the batch (P3.1: fold
    ; bank select is absolute — X is untouched by FoldIndirect). ---
    lda LevelPFDataLo
    sta FetchPtr
    lda LevelPFDataHi
    sta FetchPtr+1
    ldx #0
    ; Load PF0 data pointer (first .word)
    jsr FoldIndirect
    sta RoomPF0Lo
    iny
    jsr FoldIndirect
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
    jsr FoldIndirect
    sta RoomRectsLo
    iny
    jsr FoldIndirect
    sta RoomRectsHi

    ; --- P3.4: copy solid rect list → ZP cache (21 bytes always; rooms with
    ; count<5 leave garbage in unused tail slots — the walk stops at count).
    ; Runs per room change only (cheap). Source order: count, x,y,w,h × 5. ---
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    jsr FoldIndirect            ; count
    sta RcBase
    iny                         ; Y=1, first rect byte
.rcW1: jsr FoldIndirect
    sta RcBase,Y                ; $C7-$CE (Y=1..8 = rect0, rect1)
    iny
    cpy #9
    bne .rcW1
.rcW2: jsr FoldIndirect
    sta RcBase+4,Y              ; $D3-$DA (Y=9..16 = rect2, rect3)
    iny
    cpy #17
    bne .rcW2
.rcW3: jsr FoldIndirect
    sta $78,Y                   ; $89-$8A (Y=17..18 = rect4 x,y) = MapPtr*
    iny
    cpy #19
    bne .rcW3
.rcW4: jsr FoldIndirect
    sta $CB,Y                   ; $DE-$DF (Y=19..20 = rect4 w,h)
    iny
    cpy #21
    bne .rcW4

    ; Load enemy data for this room from LevelEnemyLo/Hi table
    ; Per-room record: ptr_lo, ptr_hi, count, pad (4 bytes per room)
    lda RoomNo
    asl                         ; room * 4
    asl
    tay
    ; --- Fold batch (P2.6): re-stage FetchPtr = LevelEnemy for this batch ---
    lda LevelEnemyLo
    sta FetchPtr
    lda LevelEnemyHi
    sta FetchPtr+1
    ldx #0
    jsr FoldIndirect            ; enemy data pointer lo
    sta EnemyDataLo
    iny
    jsr FoldIndirect            ; enemy data pointer hi
    sta EnemyDataHi
    iny
    jsr FoldIndirect            ; enemy count
    sta EnemyCount
    lda #$00
    sta EnemyDeadMask            ; no dead enemies in new room

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

    jsr LoadPFBuffer
    jsr ApplyBombWalls          ; re-punch holes from restored mask
    jsr LoadEnemyRam            ; LAST: writes EnemyRamY ($C3 alias) — must
    rts                         ; follow the PF refresh, not precede it

; ------------------------------------------------------------------------------
; LoadEnemyRam — copy each ROM enemy's x,dir into the RAM shadow.
; ROM stride 6: type(+0), x(+1), y(+2), range_min(+3), range_max(+4), dir(+5).
; Y is NOT shadowed (stays in ROM until S5) — $F3-$F6 is bank1 score.
; dir ROM: +1 / $FF. Packed: EnemyRamD bit=1 right, 0 left.
; EnemyRamP = free-running frame clock — seed value here is arbitrary.
; ------------------------------------------------------------------------------
LoadEnemyRam:
    lda EnemyRamD
    and #$F0                    ; preserve RoomDarkMask bits 4-7 (rooms 0-3)
    sta EnemyRamD
    lda #$F0                    ; EnemyRamP clock seed (arbitrary phase)
    sta EnemyRamP
    ; --- Fold batch (P3.1): room enemy records live in bank2. Stage FetchPtr
    ; immediately before the reads; absolute-fold preserves X and Y. ---
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
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
    jsr FoldIndirect
    sta EnemyRamX,X
    iny                         ; +2 = y
    jsr FoldIndirect
    sta EnemyRamY,X
    iny                         ; +3 range_min
    iny                         ; +4 range_max
    iny                         ; +5 dir
    jsr FoldIndirect
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
; E0: loop runs EVERY frame; each type carries its own speed gate (snake
; ÷4 here; bat ungated, spider ÷8, tentacle ÷2/÷8, moth ÷2 in E1-E4).
; Snake patrol: bounds relative to ROM spawn X ± SNAKE_PATROL (6 px, was
; ± ENEMY_WIDTH = overshoot), side chosen by ROM dir (initial facing). Ignores editor range_* per user
; 2026-09-23. First move = facing (live dir from LoadEnemyRam). No wall collision.
; ------------------------------------------------------------------------------
UpdateEnemies:
    lda EnemyCount
    bne UE_Start
    rts
UE_Start:
    ; --- Fold batch (P3.1): enemy record — staged once, every UE read this
    ; frame (type + snake spawn/dir) folds against it; loop writes no FetchPtr.
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    ldx #0
UE_Loop:
    cpx EnemyCount
    bcc UE_Alive                ; P3.1 stage/folds pushed UE_Exit >127B away
    jmp UE_Exit
UE_Alive:
    lda EnemyDeadMask
    and EnemyBitTable,X
    bne UE_Next                  ; dead enemy does not move
    ldy EnemyOffTable,X          ; Y = X*6 = type offset
    jsr FoldIndirect             ; type
    cmp #ENEMY_TENTACLE
    bne .UENotTent
    jsr UE_Tentacle              ; far target — subroutine avoids branch range
    jmp UE_Next
.UENotTent:
    cmp #ENEMY_SNAKE
    bne UE_Next                  ; other types: no X motion (Y is derived)
    lda TickCounter              ; snake: 1 px / 4 frames (was the global gate)
    and #3
    bne UE_Next
    ; live dir bit: 1 = right, 0 = left
    lda EnemyBitTable,X
    and EnemyRamD
    bne UE_SnakeRight
UE_SnakeLeft:
    dec EnemyRamX,X
    iny                          ; +1 = ROM spawn X
    jsr FoldIndirect
    sta Temp
    iny
    iny
    iny
    iny                          ; +5 = ROM dir
    jsr FoldIndirect
    bmi UE_LeftInitL             ; initial face left → rmin = spawn - 6
    lda Temp                     ; initial face right → rmin = spawn
    jmp UE_LeftChk
UE_LeftInitL:
    sec
    lda Temp
    sbc #SNAKE_PATROL
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
    jsr FoldIndirect
    sta Temp
    iny
    iny
    iny
    iny                          ; +5 = ROM dir
    jsr FoldIndirect
    bmi UE_RightInitL            ; initial face left → rmax = spawn
    clc
    lda Temp                     ; initial face right → rmax = spawn + 6
    adc #SNAKE_PATROL
    jmp UE_RightChk
UE_RightInitL:
    lda Temp
UE_RightChk:
    sta Temp
    lda EnemyRamX,X
    cmp Temp
    bcc UE_Next                  ; X < rmax OK
    lda Temp
    sta EnemyRamX,X              ; clamp to exact bound
    jsr UE_FlipDir               ; at or past max → turn left
UE_Next:
    inx
    jmp UE_Loop
UE_Exit:
    rts

; ------------------------------------------------------------------------------
; UE_Tentacle — chase RoomX: 1 px toward the player every 4th frame, gated by
; a wall probe. Probe reuses PlayerHitsMap via RoomX/RoomY swap (plan spec):
; save player xy on stack, put candidate X + live tentacle Y, call, restore
; ALWAYS (PLA/PLA do not disturb C), commit only when C=0 (clear).
; Slot X is ALSO saved (PHM clobbers X via YToCellRow's `tax` — E3 gate bug:
; the commit wrote to EnemyRamX[row] instead of EnemyRamX[slot] → frozen X).
; Candidate >= 160 (incl. wrap 255) rejected before probe — room edge hold.
; In: X = enemy slot. Clobbers A/Y/Temp/X (X restored around the probe).
; Returns via .TentOut on every path.
; ------------------------------------------------------------------------------
UE_Tentacle:
    lda TickCounter
    and #3                       ; ÷4 gate: 1 px / 4 frames (half of E-gate r1)
    bne .TentOut
    lda EnemyRamX,X
    cmp RoomX
    beq .TentOut                 ; aligned with player X → hold
    bcc .TentRight
    sec
    sbc #1                       ; step left
    jmp .TentProbe
.TentRight:
    clc
    adc #1                       ; step right
.TentProbe:
    cmp #160                     ; 160..255 = off right edge or wrap → hold
    bcs .TentOut
    sta Temp                     ; Temp = candidate X (free in overscan)
    ; Same-column cull: committed X is always probe-clear, so a candidate in
    ; the same 4px column covers the same collision cells → result is known
    ; (C=0) and the full PlayerHitsMap swap/probe can be skipped.
    lda Temp
    eor EnemyRamX,X
    and #$FC
    beq .TentCommit
    lda RoomX
    pha                          ; save player position across the probe
    lda RoomY
    pha
    lda Temp
    sta RoomX                    ; probe as the tentacle (candidate x)
    lda EnemyRamY,X
    sta RoomY                    ; live tentacle y (refreshed this overscan)
    txa                          ; save slot: PlayerHitsMap->YToCellRow does
    pha                          ; `tax` (X = bottom row) — slot was lost here
    jsr PlayerHitsMap
    pla
    tax                          ; X = slot again (PLA/tax preserve C)
    pla
    sta RoomY                    ; restore player Y (C survives PLA)
    pla
    sta RoomX                    ; restore player X
    bcs .TentOut                 ; wall → hold position
.TentCommit:
    lda Temp
    sta EnemyRamX,X              ; clear → commit candidate step
.TentOut:
    rts

; ------------------------------------------------------------------------------
; DeriveEnemyY — live Y for enemy slot X. Moving types are DERIVED, not stored:
; the EnemyRamY alias ($C3) is clobbered by every VBLANK's LoadPFBuffer, and
; there is no free ZP byte to persist movement state, so the formula is
; re-evaluated from ROM spawn + the EnemyRamP frame clock at each refresh.
; Bat:     spawn..spawn+2, 1 px / 2 frames, triangle(EnemyRamP>>1 & 3).
; Tentacle: spawn..spawn+2, 1 px / 8 frames, triangle(EnemyRamP>>3 & 3).
; Spider:  spawn..spawn+24, 1 px / 4 frames, p=(EnemyRamP>>2)&63,
;          down first with dwell at top: delta = p<25 ? p : (p<48 ? 48-p : 0).
;          Gate ÷4 (not spec ÷8): phase period must divide the 256-step clock
;          wrap — 48-step÷8 phases never align (teleport), 64-step÷4 does.
;          Dwell absorbs the 256 mod 64 leftover (wrap lands in dwell zone).
; Clock:   EnemyRamP, inc'd once per frame in RefreshEnemyY (TickCounter is
;          the 60-frame game timer — gates from it wrap every second).
; Other types: straight ROM y (their movement stages come later).
; In: X = enemy slot. Out: A = live Y. Clobbers A/Y.
; ------------------------------------------------------------------------------
DeriveEnemyY:
    ; --- Fold batch (P3.1): enemy records live in bank2; stage per entry so
    ; any caller works. Stage is A/X-only — caller's slot in X survives. ---
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    ldy EnemyOffTable,X
    jsr FoldIndirect            ; type
    cmp #ENEMY_BAT
    beq .DEYTickNoShift
    cmp #ENEMY_TENTACLE
    beq .DEYTickShift
    cmp #ENEMY_SPIDER
    beq .DEYSpiderTick
    iny
    iny
    jsr FoldIndirect            ; static types: ROM y
    rts
.DEYTickNoShift:
    lda EnemyRamP
    lsr                         ; ÷2: 1 px / 2 frames (bat half speed, E-gate fix)
    jmp .DEYBobTick
.DEYTickShift:
    lda EnemyRamP
    lsr
    lsr
    lsr                         ; ÷8 gate
.DEYBobTick:                    ; shared bob delta: triangle(p&3) = 0,1,2,1
    and #3
    cmp #3
    bne .DEYDelta
    lda #1                      ; 3 -> 1
                                ; (dead `jmp .DEYDelta` removed — target was
                                ;  the very next instruction)
.DEYDelta:                      ; A = delta, then add ROM spawn y
    sta Temp
    iny
    iny
    jsr FoldIndirect            ; ROM spawn y
    clc
    adc Temp
    rts
.DEYSpiderTick:
    lda EnemyRamP
    lsr
    lsr                         ; ÷4 gate (1 px per 4 frames)
    and #$3F                    ; p = 0..63
    cmp #48
    bcc .DEYSUp
    lda #0                      ; dwell: p 48..63 (clock wrap lands here)
    beq .DEYDelta               ; always
.DEYSUp:
    cmp #25
    bcc .DEYDelta               ; p <= 24: delta = p (down, 0..24)
    eor #$FF
    sec
    sbc #$CF                    ; 48-p = (255-p)-207, up phase (p 25..47)
    jmp .DEYDelta

; ==============================================================================
; Room exit handlers — check connection table, switch rooms, reposition player
; ==============================================================================
; Connection table: 4 bytes per room (up, down, left, right), $FF = no exit.
; After transition: player is placed at the OPPOSITE edge of the new room.
; Jetpack velocity carries over (matches comparison/hero pattern).
; ------------------------------------------------------------------------------
GetConnIdx:                 ; A/Y = RoomNo * 4 (exit handlers add dir offset)
    lda RoomNo
    asl
    asl
    tay
    ; --- Fold batch (P2.7): conn table lives in bank2. Stage FetchPtr here
    ; so all four direction handlers fold with Y set by their iny path.
    ; P3.1: fold bank select is absolute — X untouched across FoldIndirect. ---
    lda LevelConnLo
    sta FetchPtr
    lda LevelConnHi
    sta FetchPtr+1
    ldx #0
    rts

ExitRoomDown:
    jsr GetConnIdx
    iny                     ; +1 = down direction
    jsr FoldIndirect
    cmp #$ff
    beq .NoDown
    jsr EnterRoom
    lda #PLAYER_MIN_Y
    sta RoomY               ; enter at the top edge
.NoDown:
    rts

ExitRoomUp:
    jsr GetConnIdx          ; +0 = up direction
    jsr FoldIndirect
    cmp #$ff
    beq .NoUp
    jsr EnterRoom
    lda #PLAYER_MAX_Y
    sta RoomY               ; enter at the bottom edge
.NoUp:
    rts

ExitRoomLeft:
    jsr GetConnIdx
    iny
    iny                     ; +2 = left direction
    jsr FoldIndirect
    cmp #$ff
    beq .NoLeft
    jsr EnterRoom
    lda #PLAYER_MAX_X
    sta RoomX               ; enter at the right edge
.NoLeft:
    rts

ExitRoomRight:
    jsr GetConnIdx
    iny
    iny
    iny                     ; +3 = right direction
    jsr FoldIndirect
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
; LevelDataTable stride: 14 bytes
;   +0..+2: start_room, start_x, start_y
;   +3..+5: miner_room (b7 = faces right), miner_x, miner_y
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

    ; --- Fold batch (P2.7): LevelDataTable lives in bank2 at the frozen
    ; address. Stage FetchPtr immediately before the batch; FoldIndirect
    ; preserves X and Y (iny flow below unchanged), returns the byte in A.
    ; The ldx #0 is kept for callers that expect X clear on entry. ---
    lda #<LEVEL_DATA_ADDR
    sta FetchPtr
    lda #>LEVEL_DATA_ADDR
    sta FetchPtr+1
    ldx #0

    ; +0..+2: start room, x, y
    jsr FoldIndirect
    sta LevelStartRoom
    iny
    jsr FoldIndirect
    sta LevelStartX
    iny
    jsr FoldIndirect
    sta LevelStartY
    iny
    ; +3..+5: miner room, x, y
    jsr FoldIndirect
    sta LevelMinerRoom
    iny
    jsr FoldIndirect
    sta MinerX
    iny
    jsr FoldIndirect
    sta MinerY
    iny
    ; +6..+7: wall colors
    jsr FoldIndirect
    sta LevelWallColor
    iny
    jsr FoldIndirect
    sta LevelWallColor2
    iny
    ; +8..+9: pfdata ptr
    jsr FoldIndirect
    sta LevelPFDataLo
    iny
    jsr FoldIndirect
    sta LevelPFDataHi
    iny
    ; +10..+11: conn ptr
    jsr FoldIndirect
    sta LevelConnLo
    iny
    jsr FoldIndirect
    sta LevelConnHi
    iny
    ; +12..+13: enemy ptr
    jsr FoldIndirect
    sta LevelEnemyLo
    iny
    jsr FoldIndirect
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
    lda LevelMinerRoom
    and #$7f
    cmp RoomNo
    bne .CMPDone                ; not in miner's room
    ; X overlap: player [RoomX, +6] vs 4px miner.
    ; Accept iff RoomX - MinerX in [-6, +3].
    lda RoomX
    sec
    sbc MinerX
    clc
    adc #PLAYER_WIDTH - 1
    cmp #PLAYER_WIDTH + MINER_WIDTH - 1
    bcs .CMPDone                ; no X overlap
    ; Y overlap: player [RoomY, +11] vs miner [MinerY, +7]
    ; accept iff RoomY - MinerY in [-11, +7]  (add 11, compare 19)
    lda RoomY
    sec
    sbc MinerY
    clc
    adc #PLAYER_SPRITE_H - 1
    cmp #PLAYER_SPRITE_H + PLAYER_HEIGHT - 1
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
; Sets ObjBase, ActiveObjectX, ActiveObjectY, ObjTop, ObjBot, COLUP1.
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
    lda #OBJ_BOMB               ; bomb design offset into ObjSprites
    sta ObjBase
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
    lda LevelMinerRoom
    and #$7f
    cmp RoomNo
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
    lda Temp
    cmp EnemyCount
    beq .SOEnemy               ; no miner slot in this room
    ; This slot is the miner
    lda #OBJ_MINER              ; miner design offset into ObjSprites
    sta ObjBase
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
    ldx FlickerFrame
    lda Temp
    cmp EnemyCount
    beq .SOEnemyNoMinerOffset
    dex                         ; skip miner slot
.SOEnemyNoMinerOffset:
    ; A = enemy index in list
    txa
    sta EnemyIndex
    ; Check if index < EnemyCount
    cmp EnemyCount
    bcc .SOEnemyValid
    ; Out of range — no object this slot
    lda #0
    sta ObjBase
    jmp .SODone
.SOEnemyValid:
    ; Skip if this enemy is dead (mask bit = index); A already = EnemyIndex
    tax
    lda EnemyDeadMask
    and EnemyBitTable,X
    bne .SOEnemySkip
    ; Live X from RAM; Y from RAM (EnemyRamY) at .SOEnemyColorDone
    ldx EnemyIndex
    lda EnemyRamX,X
    sta ActiveObjectX
    ldy EnemyOffTable,X         ; Y = EnemyIndex * 6 = type offset
    ; --- Fold batch (P3.1): enemy record staged before IsRoomDark (A-only,
    ; Y and FetchPtr survive the call). ---
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    jsr IsRoomDark              ; clobbers X — Y still = type offset
    beq .SOEnemyLit
    lda #COLOR_DARK_OBJ         ; dark room: lamp + enemies medium grey
    sta COLUP1
    jsr FoldIndirect            ; reload type
    tax
    jmp .SOEnemyPattern
.SOEnemyLit:
    jsr FoldIndirect            ; reload type (X was clobbered by IsRoomDark)
    tax
    lda EnemyColorTable,X
    sta COLUP1
.SOEnemyPattern:
    lda ObjSpriteOffTable,X     ; type → ObjSprites design offset
    sta ObjBase
.SOEnemyColorDone:
    ldx EnemyIndex
    lda EnemyRamY,X             ; live Y (E0: EnemyRamY alias, was ROM +2)
    sta ActiveObjectY
    ; Position GRP1
    lda ActiveObjectX            ; A = X position for SetObjectXPos
    ldx #1                      ; X=1 = player1
    jsr SetObjectXPos
    jmp .SODone

.SOEnemySkip:
    lda #0
    sta ObjBase

.SODone:
    jsr SetObjReflection
    ; Set ObjTop/ObjBot for kernel GRP1 visibility check.
    ; S2.2: ObjTop stored RoomY-relative (ObjTopRel = ActiveObjectY-RoomY+1) so
    ; the kernel compares against running-Y (`tya`) instead of `lda Scanline`
    ; — frees 9c/line (lda Scanline + inc Scanline) for the laser beam write.
    ; Kernel .Grp1 does: tya / sec / sbc ObjTop / cmp #8 / bcs .ObjZero.
    ; ObjBot mirrors ObjTop+8 (write-only; no readers).
    lda ObjBase
    beq .SONoObj
    lda ActiveObjectY
    sec
    sbc RoomY
    clc
    adc #1                      ; A = ActiveObjectY - RoomY + 1 (mod 256)
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
    sta ObjBase
    jmp .SODone

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

; Enemy type → ObjSprites design offset (index = ENEMY_* type)
ObjSpriteOffTable:
    .byte OBJ_SPIDER            ; 0
    .byte OBJ_BAT               ; 1
    .byte OBJ_SNAKE             ; 2
    .byte OBJ_TENTACLE          ; 3
    .byte OBJ_MOTH              ; 4
    .byte OBJ_LAMP              ; 5 (LAMP)

; ==============================================================================
; CheckEnemyHit — player overlaps an enemy → remove enemy, lose life
; ------------------------------------------------------------------------------
CheckEnemyHit:
    ; Walk enemy list, check footprint overlap with each
    lda EnemyCount
    bne CEH_HasEnemies
    jmp CEH_NoHit              ; no enemies
CEH_HasEnemies:
    ; --- Fold batch (P3.1): enemy record staged once — the loop reads type
    ; at CEH_HasMore and writes no FetchPtr. ---
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    ldy #0
CEH_Loop:
    cpy EnemyCount
    bcc CEH_HasMore
    jmp CEH_NoHit              ; walked all enemies, no hit
CEH_HasMore:
    sty EnemyIndex
    ; Skip dead enemies
    lda EnemyDeadMask
    and EnemyBitTable,Y
    bne CEHNext
    ; Live X and Y from RAM shadow (Y = slot here)
    lda EnemyRamX,Y
    sta ActiveObjectX
    lda EnemyRamY,Y
    sta ActiveObjectY
    ; Broad object bounds; lamp gets its 4px lit-width check after Y overlap.
    lda RoomX
    sec
    sbc ActiveObjectX
    clc
    adc #PLAYER_WIDTH - 1
    cmp #PLAYER_WIDTH + ENEMY_WIDTH - 1
    bcs CEHNext                ; no X overlap
    sta CollisionX              ; keep x-overlap span for lamp's narrower box
    ; Y overlap: player [RoomY, +11] vs enemy [ActiveObjectY, +7] — exact
    lda RoomY
    sec
    sbc ActiveObjectY
    clc
    adc #PLAYER_SPRITE_H - 1
    cmp #PLAYER_SPRITE_H + PLAYER_HEIGHT - 1
    bcs CEHNext                ; no Y overlap
        ; Lamp (type 5): crash → RoomDarkMask; lamp stays in rotation (grey), no life
    ldx EnemyIndex
    ldy EnemyOffTable,X         ; Y = EnemyIndex * 6
    jsr FoldIndirect            ; type
    cmp #LAMP
    beq CEH_Lamp
    ; Hit! Mark this enemy dead (bit = index)
    lda EnemyDeadMask
    ora EnemyBitTable,X         ; X = EnemyIndex (set at CEH hit)
    sta EnemyDeadMask
    lda #$50              ; +50 points per kill
    jsr AddScore
    ; Lose a life
    dec PlayerLives
    bpl CEH_Stay
    ; Lives exhausted — reset level (all enemies back, 3 lives)
    lda #$00
    sta EnemyDeadMask            ; clear dead enemy
    lda #3
    sta PlayerLives
    jsr ReloadLevel
    rts
CEH_Lamp:
    ; Broad overlap guarantees lower bound; narrow to lamp's 4 lit pixels.
    lda CollisionX
    cmp #PLAYER_WIDTH + LAMP_WIDTH - 1
    bcs CEHNext
    ; Only fire once (bit already set → no-op); no life loss, not EnemyDeadMask
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
;   → sets dead bit in EnemyDeadMask (per-enemy, shared with CheckEnemyHit
;   and LaserHitTest); first live enemy per blast.
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
    ldx EnemyIndex
    cpx EnemyCount
    bcs .BEBDone
    lda EnemyDeadMask
    and EnemyBitTable,X
    bne .BEBNext                ; already dead
    ; Live X from RAM (no Y needed for X-only check)
    lda EnemyRamX,X
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
    lda EnemyDeadMask
    ora EnemyBitTable,X          ; X = EnemyIndex
    sta EnemyDeadMask            ; kill (first overlapping enemy per blast)
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
    lda #$00
    sta EnemyDeadMask
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

; ------------------------------------------------------------------------------
; BombMarkWalls — on 1→2 edge: walk RoomRects, set WallMask bit for each
;   w==1 rect whose x is in blast cols (bomb left-half col ±2, clamped 0..19).
;   Skip x==0: screen cols 0 and 39 (both = stored col 0 under reflection).
; Bits b3-6 of BombPacked = rect index 0..3 (rooms have ≤4 rects).
; ------------------------------------------------------------------------------
BombMarkWalls:
    ; visible-left mapping identical to PlayerHitsMap: the bomb is drawn from
    ; BombX via SetObjectXPos, so its left edge is BombX-5 / BombX-7, not BombX.
    sec
    lda BombX
    cmp #15
    bcs .BMWoff7
    sbc #4                      ; visible left = BombX - 5 (CMP clears carry)
    jmp .BMWVL
.BMWoff7:
    sbc #7                      ; visible left = BombX - 7
.BMWVL:
    lsr
    lsr                         ; screen col = visible_left/4 (0..39)
    cmp #TILE_COLUMNS
    bcc .BMWCol
    sta Temp
    lda #39
    sec
    sbc Temp                    ; mirror right-half → left-half col
.BMWCol:
    sta Temp                    ; bomb left-half col
    ; blast lo = max(col-2, 0)   (±2: player is 8px wide, so a bomb dropped
    ; blast hi = min(col+2, 19)    flush-left sits 2 cols from the wall)
    lda Temp
    cmp #2
    bcc .BMWLo0
    sec
    sbc #2
    bcs .BMWStoreLo
.BMWLo0:
    lda #0
.BMWStoreLo:
    sta CollisionEndX           ; blast_lo (free: overscan, after movement)
    lda Temp
    cmp #18
    bcs .BMWHi19
    clc
    adc #2
    bcc .BMWStoreHi
.BMWHi19:
    lda #19
.BMWStoreHi:
    sta CollisionCellX          ; blast_hi (loop compares rect.x against it)
    lda RcBase                  ; cached rect count
    beq .BMWDone
    cmp #4
    bcc .BMWCountOk
    lda #4                      ; rooms with >4 rects: only rects 0-3 maskable
.BMWCountOk:
    tax                         ; X = rect count (1..4)
    dex                         ; X = 3..0
.BMWLoop:
    lda ABWXTab,X
    tay
    lda 0,Y                     ; rect.x
    beq .BMWNext                ; x==0 = screen L/R border — never destroy
    cmp CollisionEndX
    bcc .BMWNext                ; x < lo
    cmp CollisionCellX
    beq .BMWCheckW              ; x == hi → in blast
    bcs .BMWNext                ; x > hi
.BMWCheckW:
    lda ABWWTab,X
    tay
    lda 0,Y                     ; rect.w
    cmp #1
    bne .BMWNext
    lda BombMaskBit,X
    and BombPacked              ; already broken?
    bne .BMWNext                ; yes → no double score
    lda BombMaskBit,X
    ora BombPacked
    sta BombPacked               ; set WallMask bit (keeps state+DownPrev)
    lda #$75                    ; +75 points per broken wall
    jsr AddScore
.BMWNext:
    dex
    bpl .BMWLoop
.BMWDone:
    rts

; ------------------------------------------------------------------------------
; ApplyBombWalls — after LoadPFBuffer: for each masked rect, clear its col
;   bit in PF0Buf/PF1Buf/PF2Buf only for rows rect.y .. rect.y+h-1
;   (thin segment only — not into a wider join below/above).
; Early-out when WallMask=0 (common case).
; Reads rect x/y/h directly from ZP rect cache (no FoldIndirect):
;   Rect 0: x=$C7, y=$C8, h=$CA
;   Rect 1: x=$CB, y=$CC, h=$CE
;   Rect 2: x=$D3, y=$D4, h=$D6
;   Rect 3: x=$D7, y=$D8, h=$DA
; ------------------------------------------------------------------------------
ApplyBombWalls:
    lda BombPacked
    and #%01111000              ; WallMask b3-6 only
    beq .ABWDone
    ldx #3                      ; rect index 3..0 (descending)
.ABWLoop:
    lda BombMaskBit,X
    and BombPacked
    beq .ABWNext
    lda ABWXTab,X               ; ZP address of rect.x
    tay
    lda 0,Y                     ; rect.x (direct ZP read via Y pointer)
    sta CollisionX
    lda ABWYTab,X               ; ZP address of rect.y
    tay
    lda 0,Y                     ; rect.y = first row
    sta Temp
    lda ABWHTab,X               ; ZP address of rect.h
    tay
    lda 0,Y                     ; rect.h
    clc
    adc Temp
    sec
    sbc #1
    sta CollisionCellX          ; last row = y+h-1
    txa
    pha                         ; rect index — ClearPFColumn clobbers X
    lda CollisionX              ; col
    jsr ClearPFColumn           ; A=col, Temp=first, CollisionCellX=last
    pla
    tax
.ABWNext:
    dex
    bpl .ABWLoop
.ABWDone:
    rts

; ZP address tables for ApplyBombWalls/BombMarkWalls rect cache (rects 0-3)
ABWXTab: .byte $C7, $CB, $D3, $D7  ; rect.x ZP addresses
ABWYTab: .byte $C8, $CC, $D4, $D8  ; rect.y ZP addresses
ABWWTab: .byte $C9, $CD, $D5, $D9  ; rect.w ZP addresses
ABWHTab: .byte $CA, $CE, $D6, $DA  ; rect.h ZP addresses

; ==============================================================================
; Data tables
; ==============================================================================

; --- Explosion blink COLUBK: index = (60-BombTimer) % 3 ---
BombBlinkColors:
    .byte COLOR_CAVE_BG         ; 0 black
    .byte COLOR_BLINK_Y         ; 1 yellow
    .byte COLOR_BLINK_R         ; 2 red
    .byte COLOR_BLINK_Y         ; 3 yellow (4-phase blink: b/y/r/y)

; WallMask bit for rect index 0-3 (BombPacked b3-6)
BombMaskBit:
    .byte $08, $10, $20, $40

; AND-mask to clear col 0-19's PF bit (inverse of convert_room.pf_values):
;   col 0-3   → PF0 bits 4-7; col 4-11 → PF1 bits 7-0; col 12-19 → PF2 bits 0-7
BombClearMask:
    .byte $EF, $DF, $BF, $7F                    ; col 0-3  (PF0)
    .byte $7F, $BF, $DF, $EF, $F7, $FB, $FD, $FE ; col 4-11 (PF1)
    .byte $FE, $FD, $FB, $F7, $EF, $DF, $BF, $7F ; col 12-19 (PF2)

; --- Player sprites: 8x12, all 8 pixels wide (bit7 = leftmost pixel) ---
; Frame A = normal, frame B = jet legs (rows 7-8 differ; 3 pixels changed).
; Per-row colors in PlayerColTable (RED/RED/YELLOW/RED/GRAY/RED/.../BLACK/BLACK).
PlayerSpriteA:
    .byte %00111100             ; row 0
    .byte %01111110             ; row 1
    .byte %01111000             ; row 2 — yellow face
    .byte %00111100             ; row 3
    .byte %01111100             ; row 4 — grey pack
    .byte %11011110             ; row 5
    .byte %11011110             ; row 6
    .byte %00011100             ; row 7 — frame A
    .byte %00011000             ; row 8 — frame A
    .byte %00011000             ; row 9
    .byte %00011100             ; row 10 — black boots
    .byte %00111100             ; row 11 — black boots

PlayerSpriteB:
    .byte %00111100             ; row 0
    .byte %01111110             ; row 1
    .byte %01111000             ; row 2 — yellow face
    .byte %00111100             ; row 3
    .byte %01111100             ; row 4
    .byte %11011110             ; row 5
    .byte %11011110             ; row 6
    .byte %11011100             ; row 7 — frame B
    .byte %01011000             ; row 8 — frame B
    .byte %00011000             ; row 9
    .byte %00011100             ; row 10
    .byte %00111100             ; row 11

PlayerColTable:
    .byte COLOR_P_RED, COLOR_P_RED, COLOR_P_YELLOW, COLOR_P_RED
    .byte COLOR_P_GRAY, COLOR_P_RED, COLOR_P_RED, COLOR_P_RED
    .byte COLOR_P_RED, COLOR_P_RED, COLOR_P_GRAY, COLOR_P_GRAY

; --- Level data ---
; Generated from level JSON via tools/convert_level.py.
; Do not edit by hand — regenerate with build.sh.
; NOTE: data payload moved to bank2 (level_bank_plan P2, frozen addresses
; $F9D9-$FB1E); pointer values are unchanged. kernel keeps only the EQUs
; it consumes (LEVEL_COUNT) — sync asserted by test_level_bank.py.

; --- Level constants ---
ENEMY_SPIDER   = 0
ENEMY_BAT      = 1
ENEMY_SNAKE    = 2
ENEMY_TENTACLE = 3
ENEMY_MOTH     = 4
LAMP           = 5             ; type-5 enemy record = editor lamp (white square)
ENEMY_DATA_STRIDE = 6
LEVEL_COUNT    = 2             ; hand copy of generated LEVEL_COUNT (cmp in
                                ; LoadLevel advance guard — test asserts sync)
LEVEL_DATA_ADDR = $FB03        ; frozen address of bank2's LevelDataTable
                                ; (test asserts bank2.lst label == this)

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
; YToCellRow — convert scanline (0-191) to 48-line band row (0-3)
; ==============================================================================
; Input: A = scanline. Output: X = tile row.
; Lookup table: constant-time. Subtract loop grew linearly with RoomY and
; made 3× PlayerHitsMap (fall 2 + L/R 1) exceed overscan TIM64T=35 (~2240c)
; in 4-rect rooms → frame >262 lines → vertical roll when strafing while falling.
; Indexed by A>>2 (48-entry table): floor(floor(A/4)/12) = floor(A/48).
; Costs +4c/call vs the 192-entry table, saves 144 ROM bytes.
; Max A = PLAYER_MAX_Y+11 = 143 → index 35 (fits 48 entries).
YToCellRow subroutine
    lsr
    lsr                 ; A = scanline >> 2
    tay
    lda YToRowTable,Y
    tax
    rts

; 48 entries: 12 each of 0,1,2,3 (value = index/12 = scanline/48).
YToRowTable:
    .byte 0,0,0,0,0,0,0,0,0,0,0,0
    .byte 1,1,1,1,1,1,1,1,1,1,1,1
    .byte 2,2,2,2,2,2,2,2,2,2,2,2
    .byte 3,3,3,3,3,3,3,3,3,3,3,3

; ==============================================================================
; PlayerHitsMap — check player bounding box against room rectangle list
; ==============================================================================
; Identical to comparison/lo-a-rad-dragon/bank0.asm.
; Rectangles are in tile coordinates (col 0-19, row 0-2, w/h in bands).
; The playfield is reflected, so tiles >= 20 mirror via 39-col.
; Returns C=0 if clear, C=1 if blocked.
PlayerHitsMap:
; --- Tile row range (top, bottom) ---
; Inlined YToCellRow: saves 2 JSR stack push levels (4B on stack) to keep SP >= $F8
    lda RoomY
    lsr
    lsr                         ; A = scanline >> 2
    tay
    lda YToRowTable,Y
    sta CollisionCellY          ; top tile row
    clc
    lda RoomY
    adc #PLAYER_SPRITE_H - 1
    lsr
    lsr
    tay
    lda YToRowTable,Y
    sta CollisionEndY           ; bottom tile row

; --- Visible left pixel -> text column range ---
; RESP0 target is RoomX-PlayerDir; offset varies by its coarse bin.
    sec
    lda RoomX
    sbc PlayerDir
    cmp #15
    bcs .off7
    sec
    sbc #4                      ; P0 target <15: visible left = X - 4
    jmp .gotVL
.off7:
    sbc #7                      ; P0 target >=15: visible left = X - 7
.gotVL:
    clc
    adc PlayerDir              ; reflected sprite's first lit bit is column 1
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

; --- Walk rectangle list (P3.4: ZP cache, direct reads — NO fold) ---
; A fold mid-function is only safe inside the byte-identical pad block:
; after `sta $1FF8` the NEXT opcode is fetched from the same address in the
; NEW bank. The earlier bank2-once walk fetched bank2's bytes at $FB6B and
; jumped into bank2's entry code (frozen player, 2026-09-29). EnterRoom
; copies the list into the fragmented ZP cache instead; Y = global rect
; offset (rect0 base Y=0, mask index = Y>>2), windows switch at Y=8/Y=16.
    lda RcBase                  ; count (cached; empty room -> clear)
    bne .wrGo
    jmp .NoHit
.wrGo:
    sta RectCount
    lda #RcW1                   ; window1: $C7 + Y0..7 = $C7-$CE
    sta FetchPtr
    lda #$00
    sta FetchPtr+1
    ldy #0

.RectLoop:
; S6.2: skip rects destroyed by a bomb (WallMask bit for this index;
; index = base/4 — rect0..3 only; rect4 = .Stage3 is never masked)
    tya
    lsr
    lsr
    tax
    lda BombMaskBit,X
    and BombPacked
    bne .nextRect               ; destroyed → not solid

; Column overlap: max_col >= rect.x AND min_col < rect.x + rect.w
    lda (FetchPtr),Y            ; rect.x
    cmp CollisionCellX          ; rect.x > max_col?
    beq .colOk
    bcs .nextRect               ; C1&Z0 = x > max (C0 falls to .colOk)
.colOk:
    sta CollisionX              ; save rect.x for addition
    iny
    iny                         ; Y = base + 2 (rect.w)
    clc
    lda (FetchPtr),Y            ; rect.w
    adc CollisionX              ; rect.x + rect.w
    cmp CollisionEndX           ; (rect.x+w) <= min_col?
    beq .nrmCol                 ; Y=base+2 here — normalize before advance
    bcc .nrmCol

; Row overlap: bottom_row >= rect.y AND top_row < rect.y + rect.h
    dey                         ; Y = base + 1 (rect.y)
    lda (FetchPtr),Y            ; rect.y
    cmp CollisionEndY           ; rect.y > bottom_row?
    beq .rowOk
    bcs .nrmRow                 ; Y=base+1 — normalize before advance
.rowOk:
    iny
    iny                         ; Y = base + 3 (rect.h)
    clc
    lda (FetchPtr),Y            ; rect.h
    sta CollisionX
    dey
    dey                         ; Y = base + 1 (rect.y)
    lda (FetchPtr),Y            ; rect.y (re-read for y+h)
    adc CollisionX              ; rect.y + rect.h
    cmp CollisionCellY          ; (rect.y+h) <= top_row?
    beq .nrmRow                 ; Y=base+1 — normalize before advance
    bcc .nrmRow

; HIT — player is blocked
    ; TAIL-CALL (stack depth guard): HotOverlapFlag's exits sec, so its rts
    ; completes PlayerHitsMap with C=1. Replacing jsr+sec+rts with this jmp
    ; removes one push level: deepest chain (StepDown -> PlayerHitsMap ->
    ; -> HotOverlapFlag -> FoldIndirect + pha) was 9 pushes = SP $F6, and
    ; SP $F6/$F7 is physically BombX/BombTimer — stack pushes stomped the
    ; bomb fuse (see AGENTS.md "Stack pushes are INVISIBLE to byte-audits").
    ; Any new caller of HotOverlapFlag MUST account for it returning C=1.
    jmp HotOverlapFlag          ; set Temp b7 if proposed cells include hot rock

; Exit-Y discipline: mask/col-x exits leave Y = rect base (correct); col-end
; exits leave Y = base+2 and row exits base+1. The advance below is Y+4 FROM
; BASE — without normalizing, one late exit skews every later rect read
; (P3.4 regression: rects drifted into PF1Buf/PF2Buf bytes = garbage walls).
.nrmCol:
    dey
    dey                         ; base+2 -> base, fall into advance
.nextRect:
    dec RectCount
    beq .NoHit                  ; last rect done -> clear
    tya
    clc
    adc #4                      ; next rect base (global Y)
    tay
    cpy #16
    beq .Stage3                 ; rect4: fixed-address cache slots
    cpy #8
    bcc .RectLoop               ; Y<8: still window1
    lda #RcW2                   ; window2: $CB + Y8..15 = $D3-$DA
    sta FetchPtr                ; (FetchPtr+1 already $00)
    jmp .RectLoop

.nrmRow:
    dey                         ; base+1 -> base
    bpl .nextRect               ; always taken (Y <= 16 -> N clear)

.Stage3:
; rect4 = last solid rect (M3 rooms only, count=5) — its cache fields are
; not contiguous ($89/$8A = x,y; $DE/$DF = w,h), so compare inline at
; fixed addresses. No mask (index 4 never masked), no Y, no push.
    lda MapPtrLo                ; rect4.x
    cmp CollisionCellX
    beq .s3c
    bcs .NoHit                  ; x > max
.s3c:
    sta CollisionX
    clc
    lda Rc4W                    ; rect4.w
    adc CollisionX
    cmp CollisionEndX
    beq .NoHit
    bcc .NoHit                  ; x+w <= min
    lda MapPtrHi                ; rect4.y
    cmp CollisionEndY
    beq .s3r
    bcs .NoHit                  ; y > bottom
.s3r:
    clc
    lda Rc4H                    ; rect4.h
    adc MapPtrHi                ; y + h
    cmp CollisionCellY
    beq .NoHit
    bcc .NoHit                  ; y+h <= top
    jmp HotOverlapFlag          ; blocked (C set inside)

.NoHit:
    clc
    rts

EnemyOffTable:
    .byte 0,6,12                ; enemy index * 6 (offset into enemy data)

; Bit masks for IsRoomDark/SetRoomDark (indexed 0-7; bits 4-7 used for rooms 0-3)
; (tail of main — P3.1's laser stage pushed the $FF20 region past $FFFA,
; and main has pad slack here.)
BitMaskTable:
    .byte $01, $02, $04, $08, $10, $20, $40, $80

; ------------------------------------------------------------------------------
; RefreshEnemyY — write live Y → EnemyRamY (every slot, live or dead).
; The alias ($C3) is clobbered by VBLANK's LoadPFBuffer every frame, so
; overscan must rewrite it AFTER the HUD band and BEFORE LaserInput /
; CheckEnemyHit / next frame's SelectActiveObject read it.
; E1: moving types (bat) get ROM spawn + TickCounter-derived offset via
; DeriveEnemyY — no persistent movement state exists in RAM.
; Clobbers A/X/Y. End-of-main leaf (moved 2026-09-28: P3.6 rect folds grew
; the post-pad region past the $FEF6 FoldIndirect pin — end of main has
; pad slack, post-pad did not).
; ------------------------------------------------------------------------------
RefreshEnemyY:
    inc EnemyRamP                ; free-running frame clock (wraps 0-255).
                                 ; TickCounter is the 60-frame GAME timer
                                 ; (decrements 60->1, reloads) — gates derived
                                 ; from it wrapped every second (spider
                                 ; "teleported": (TC>>3)&63 only ever saw
                                 ; 0..7 and counted DOWN 0->7 = jump).
    ldx #0
.REYLoop:
    cpx EnemyCount
    bcs .REYDone
    jsr DeriveEnemyY            ; A = live Y (ROM copy, or derived for bat)
    sta EnemyRamY,X
    inx
    jmp .REYLoop
.REYDone:
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

; Flip dir bit for enemy X (right↔left).
; After fold pads to keep main code under $FC68 (leaf, jsr-safe from bank0).
UE_FlipDir:
    lda EnemyBitTable,X
    eor EnemyRamD
    sta EnemyRamD
    rts

; ------------------------------------------------------------------------------
; ClearPFColumn — A = left-half col 0..19; Temp = first row; CollisionCellX =
;   last row (inclusive). AND-clear that col's PF bit in those rows only.
;   Inverse of convert_room.pf_values. Clobbers A/X/Y/CollisionX. Preserves
;   RectCount/FetchPtr (caller restores Y from stack).
; After fold pads to keep main code under $FC68 (leaf, jsr-safe from bank0).
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
    bne .CPCLoop               ; rows 0..2; X never wraps here
.CPCDone:
    rts

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
;   FetchPtr/RectCount (PlayerHitsMap returns immediately after).
; Hot section: after solid count + N*4 solid bytes → hot count + M*4 hot bytes.
; TAIL-CALLED (jmp) from PlayerHitsMap HIT — no jsr level, stack depth guard:
;   the old jsr pushed the deepest chain to 9 (SP $F6) where $F6/$F7 =
;   BombX/BombTimer got stomped by return bytes (fuse never reached 0).
;   Contract: every rts here returns C=1 (sec at both exits).
; ------------------------------------------------------------------------------
HotOverlapFlag:
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    jsr FoldIndirect            ; solid count (P3.6: bank2 fold)
    asl
    asl                         ; *4
    clc
    adc #1                      ; +1 count byte → hot count offset
    tay
    jsr FoldIndirect
    beq .HOVdone                ; no hot rects
    sta RectCount
    iny                         ; first hot rect base
.HOVloop:
    tya
    pha
    ; Column overlap (same tests as PlayerHitsMap)
    jsr FoldIndirect            ; rect.x
    cmp CollisionCellX
    beq .HOVcolOk
    bcc .HOVcolOk
    jmp .HOVnext
.HOVcolOk:
    sta CollisionX
    iny
    iny                         ; Y = base+2 (w)
    clc
    jsr FoldIndirect
    adc CollisionX
    cmp CollisionEndX
    beq .HOVnext
    bcc .HOVnext
    ; Row overlap — same dey count as PlayerHitsMap (base+2 → base+1).
    ; Extra deys here read the hot-count byte as rect.y → death zone shifted up.
    dey                         ; Y = base+1 (y)
    jsr FoldIndirect
    cmp CollisionEndY
    beq .HOVrowOk
    bcc .HOVrowOk
    jmp .HOVnext
.HOVrowOk:
    iny
    iny                         ; Y = base+3 (h)
    clc
    jsr FoldIndirect
    sta CollisionX
    dey
    dey                         ; Y = base+1 (y)
    jsr FoldIndirect
    adc CollisionX              ; y+h
    cmp CollisionCellY
    beq .HOVnext
    bcc .HOVnext
    ; Hot hit
    pla
    lda Temp
    ora #%10000000
    sta Temp
    sec                         ; tail-call contract: return C=1
    rts
.HOVnext:
    pla
    clc
    adc #4
    tay
    dec RectCount
    bne .HOVloop
.HOVdone:
    sec                         ; tail-call contract: return C=1
    rts

; ------------------------------------------------------------------------------
; LoseLifeHot — same life path as enemy/timer hit (Temp b7 already set).
; ------------------------------------------------------------------------------
LoseLifeHot:
    dec PlayerLives
    bpl .LLHstay
    lda #3
    sta PlayerLives
    lda #$00
    sta EnemyDeadMask
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
; LoadRoomBottomColor — A = band color for RoomNo (0 = band off). Reads the
; VBLANK-staged cache (RoomBandColor = $D2, PF1Buf[3] dead-row alias at decl):
; the LevelEnemy ROM record moved to bank2, and a kernel-time fold overruns
; the .WaterRow line (fold body 20c + stage on top of a ~74c line).
; Clobbers A only (Y preserved — .WaterRow no longer needs its save).
; ------------------------------------------------------------------------------
LoadRoomBottomColor:
    lda RoomBandColor
    rts

; ------------------------------------------------------------------------------
; CheckBandTouch — overscan: if band on and sprite touches the water strip →
; life. Strip = bottom ~12 lines of the cave (bottom_band_plan rule 2);
; sprite origin RoomY >= 125 enters it (125 + PLAYER_SPRITE_H - 1 = 136).
; Same path as hot/enemy: lose life, then respawn 12 scanlines up (min 0).
; ------------------------------------------------------------------------------
CheckBandTouch:
    jsr LoadRoomBottomColor
    beq .CBTdone                ; band off
    lda RoomY
    cmp #125
    bcc .CBTdone                ; above strip
    jsr LoseLifeBand
.CBTdone:
    rts

; ------------------------------------------------------------------------------
; LoseLifeBand — life path + RoomY -= 12 (min 0; spec: respawn just above
; the water strip). Full reload skips the shift
; (LoadLevel already places the player safely).
; ------------------------------------------------------------------------------
LoseLifeBand:
    dec PlayerLives
    bpl .LLBstay
    lda #3
    sta PlayerLives
    lda #$00
    sta EnemyDeadMask
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
    sbc #12                     ; clear the strip (spec: -= 12, not whole band)
    bcs .LLBstore
    lda #0
.LLBstore:
    sta RoomY
    rts

; ------------------------------------------------------------------------------
; BuildColupF — 12-byte final COLUPF image at ColupfBuf ($E7-$F2).
;   Stripe: rows 0,2 = LevelWallColor; row 1 = LevelWallColor2.
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
    cpx #1
    bne .BCFc1
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
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    jsr FoldIndirect            ; solid count (P3.6: bank2 fold)
    asl
    asl
    clc
    adc #1
    tay                         ; Y → hot count
    jsr FoldIndirect
    beq .BCFdone
    sta RectCount
    iny
.BCFrect:
    tya
    pha
    iny                         ; Y = base+1 (y)
    jsr FoldIndirect
    sta CollisionCellX          ; first row
    iny
    iny                         ; Y = base+3 (h)
    clc
    jsr FoldIndirect
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
    beq .BCFFuseGrey            ; bomb fuse active → dark grey walls
    lda #COLOR_CAVE_BG          ; black walls (matches black background)
    beq .BCFdarkFill            ; A=$00 (COLOR_CAVE_BG) → always taken
.BCFFuseGrey:
    lda #COLOR_DARK_PF          ; hue 0 luma 2 = very dark grey walls
.BCFdarkFill:
    ldx #0
.BCFdarkLoop:
    sta ColupfBuf,X
    inx
    cpx #TILE_ROWS
    bne .BCFdarkLoop
.BCFdarkDone:
    rts

; Moved here (after fold pads) to keep pre-pad code under $FC68.
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
; ObjSprites — 4×8 designs, left-aligned bits 7-4 (col0=bit7), 8 rows each.
; Row r displays on scanline RoomY+ObjTop-1+r (ObjTop is RoomY-relative since
; S2.2; .Grp1 checks r = Y-ObjTop where Y = running A0+1). GRP1 write
; latching, same as before.
; Offset = OBJ_* constant; index 0 = blank (object off).
; ------------------------------------------------------------------------------
ObjSprites:
    .byte 0,0,0,0,0,0,0,0          ; OBJ_NONE
    .byte $90,$60,$f0,$f0,$60,$90,$60,$60   ; OBJ_MOTH
    .byte $60,$f0,$f0,$60,$90,$60,$90,$90   ; OBJ_SPIDER
    .byte $f0,$f0,$60,$60,$f0,$f0,$f0,$60   ; OBJ_LAMP
    .byte $60,$90,$80,$60,$30,$30,$30,$30   ; OBJ_TENTACLE
    .byte $90,$60,$f0,$60,$60,$90,$90,$00   ; OBJ_BAT
    .byte $ff,$ff,$ff,$ff,$ff,$ff,$ff,$ff   ; OBJ_SNAKE (8 px)
    .byte $80,$b0,$30,$70,$70,$f0,$f0,$00   ; OBJ_MINER (facing left)
    .byte $10,$20,$20,$60,$f0,$f0,$f0,$60   ; OBJ_BOMB

; ------------------------------------------------------------------------------
; FoldIndirect — cross-bank data fetch (HERO fold, write-triggered;
; level_bank_plan §0.1). Pad lands $FEF6-$FEFF (last byte ≤ $FEFF — $FF00
; stays the fineAdjust anchor). Bytes must be byte-identical in bank2
; (guard: verify_build) — after `sta $1FF8` the CPU fetches the remainder
; from the data bank at the same PC.
; Contract: bank select is ABSOLUTE $1FF8 (bank2) — X/Y both preserved,
; A = junk in, data out (`sta $1FF6` switches back, A preserved).
; P3.1 deviation (plan §0): `sta $1FF8,X` required X=0, but every enemy
; loop keeps the slot in X and has no free temp to swap (DEY/snake hold
; Temp live across the read). All level data is bank2, so X-selection is
; dead weight; bank3 data later needs a second entry `sta $1FF9` pad.
; ------------------------------------------------------------------------------
    .ds $FEF6 - *, 0            ; pin address (main size drift must not move it)
FoldIndirect:
    sta $1FF8
    lda (FetchPtr),Y
    sta $1FF6
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
; SetObjectXPos — horizontal positioning via RESP0/HMP0
; ==============================================================================
; Andrew Davie session-24 routine:
; Rolls the divide-by-15 and the delay loop into one unit.
; The page-aligned fineAdjustTable ($FF00) guarantees every RESP0 write lands
; on the same clock grid, mapping the sprite 1:1 to pixel (0..159).
; Input: A = horizontal position (0-159 color clocks)
;        X = object selector (0 = player0, 1 = player1)
;
; Lives in the $FF10-$FF1F gap (exactly 16 bytes, before org $FF20) — moved
; here 2026-09-26 (laser S1): the `jsr LaserInput` (+3 pre-pad) had pushed
; .Div15Loop across the $F8/$F9 page, turning `bcs .Div15Loop` from 3c into
; 4c = 6c per /15 iteration (contract: 5c). RESP0 then fired 3 color-clocks
; late per coarse step -> sprites drifted right ~3*(X/15) px and wrapped past
; 160 (spider appeared at the left edge). Placement inside ONE page makes the
; 5c contract structurally safe; verify_build asserts the exact range.
; DO NOT move this routine to an address where bcs and .Div15Loop differ in page.
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

    org $FF20

; Set REFP1/NUSIZ1 each frame; bank1 HUD may have changed both registers.
SetObjReflection:
    lda #0
    sta REFP1
    lda ObjBase
    cmp #OBJ_MINER
    bne .SORdone
    lda LevelMinerRoom
    bpl .SORdone
    lda #$08
    sta REFP1
.SORdone:
    rts

; ------------------------------------------------------------------------------
; LaserInput (S1 fire state + S2.1 M0 beam) — runs every overscan.
; ------------------------------------------------------------------------------
; Lives after $FF20: the pre-$FF00 region is 100% full (ObjSprites + zero pad),
; so any addition here must go past SetObjReflection. Pre-pad code size is
; unchanged (call site jsr unchanged) — page contracts in the kernel untouched.
; INPT4 ($0C) D7: 0 = pressed, 1 = released (HERO reads BIT $0C / BMI).
; LaserState ($C0): b7 = held now, b6 = held last frame, b1-0 = sweep phase.
; Every held frame advances phase 0->1->2->3->0 (S3 maps these to M0 offsets
; 0/8/16/8 px ahead of the eye — full triangle covered either starting parity);
; release clears held and resets phase. Temp (joystick) intact.
; S2.1: after state update, positions M0 (selector 2). S2.2: ENAM0 enable
; moved into kernel .Line (BeamMask) — no TIA writes here anymore.
; Overscan: VBLANK on, end waits on TIM64T — SetObjectXPos's WSYNC costs 1
; of 30 lines. Y/X dead until next reload (ldy #0 / ldx RoomNo) — safe.
LaserInput:
    ldx LaserState             ; X = old state (b7 held, b6 prev, b1-0 phase)
    txa
    and #LASER_HELD
    lsr                         ; old held (b7) -> new prev (b6)
    sta LaserState              ; stage prev (phase/held written back below)
    lda INPT4                   ; active-low fire button, D7: 0 = pressed
    bmi .LaserDone              ; released: prev set, held=0, phase=0 -> done
    txa
    and #LASER_PHASE
    clc
    adc #1
    and #LASER_PHASE            ; phase advances every held frame (incl. press)
    ora LaserState              ; + prev
    ora #LASER_HELD             ; + held
    sta LaserState
.LaserDone:
    ; --- S2.1 positioning: M0 X while fire held (S2.2: ENAM0 enable moved
    ; into the kernel .Line via BeamMask — LaserInput sets the gate byte and
    ; RESM0/HMM0 positioning only) ---
    lda LaserState
    and #LASER_HELD
    beq .LaserReleased
    lda #$02
    sta LaserBeamOn             ; .Line BeamMask AND passes rows 2-3
    ; --- S3 sweep: phase 0..3 -> offset 0/8/16/8 px AHEAD of the eye
    ; (triangle: 0->8->16->8->0 each held frame), sign = facing.
    ; Eye: art faces right unreflected (REFP0=0), yellow face rows 2-3
    ; cols 1-4 -> front col 4; REFP0 mirror -> front col 3 (bar extends
    ; left, left edge = RoomX-4). Args clamped to [0,159] — TIA position
    ; past 159 is unverified for SetObjectXPos (wrap vs hide).
    lda PlayerDir
    bne .LaserEyeL
    ; right: X = RoomX + 4 + off
    lda LaserState
    and #LASER_PHASE
    tax
    lda RoomX
    clc
    adc #4
    clc
    adc SweepOff,X
    cmp #160
    bcc .LaserPos
    lda #159                    ; clamp: sweep stops at right screen edge
    jmp .LaserPos
.LaserEyeL:
    ; left: X = RoomX - 4 - off (RoomX>=PLAYER_MIN_X=4 -> base >=0;
    ; off may borrow below 0 -> carry clear -> clamp 0)
    lda LaserState
    and #LASER_PHASE
    tax
    lda RoomX
    sec
    sbc #4
    sec
    sbc SweepOff,X
    bcs .LaserPos
    lda #0                      ; clamp: sweep stops at left screen edge
.LaserPos:
    sta CollisionX              ; S4: cur arg for LaserHitTest (held path only)
    ldx #2                      ; selector 2: RESP0+2=RESM0, HMP0+2=HMM0
    jsr SetObjectXPos           ; HMM0 applies at next frame's VBLANK HMOVE
    jsr LaserHitTest            ; S4: swept kill — needs CollisionX + LaserState
    rts

; SweepOff — M0 offset ahead of the eye per sweep phase (LaserState b1-0).
SweepOff:
    .byte 0,8,16,8
.LaserReleased:
    lda #0
    sta LaserBeamOn             ; beam off (S2.2r2: bar was visible w/o fire)
    sta HMM0                    ; S2.2r2: HMOVE re-applied stale fine offset
                                ; every frame -> bars slid across screen
    rts

; ------------------------------------------------------------------------------
; BeamMask — per-scanline ENAM0 values for the in-window kernel path (S2.2).
; Indexed by Y = A0 = Scanline - RoomY, rows 0-11 only.
; Rows 2-3 = $02 (beam on: RoomY+2..RoomY+3 = eye rows); all others $00.
; MUST live in the $FFxx page: `lda BeamMask,Y` in .Line ($F1xx) relies on
; the deterministic 5c page-cross (4c+1). verify_build enforces the page.
; ------------------------------------------------------------------------------
BeamMask:
    .byte 0,0,2,2,0,0,0,0,0,0,0,0

; ------------------------------------------------------------------------------
; LaserHitTest (S4) — swept laser kill. CollisionX = cur M0 arg, stored by
; LaserInput .LaserPos (held path only). Interval = [cur, cur+7] (8 px
; missile); sweep steps are 8 px = missile width, so consecutive frames tile
; gap-free — no prev-frame storage needed. Vertical: beam rows [RoomY+2,
; RoomY+3] vs enemy [Y,+7] -> (RoomY-Y)+3 in [0..8]. Horizontal (request
; space, same convention as CheckEnemyHit): |eLo-lo| <= 7 via (d+7) in [0..14];
; arg clamped [0,159] by LaserInput = screen-edge clip.
; First live enemy in span: dead bit + #$50 + rts (next frame the mask skips
; it — no resurrection, no double score). Lamp: overlap instead crashes the
; lamp = SetRoomDark (same effect as player-body touch; no kill, no score).
; Does NOT touch Temp (joystick still live at the call site).
; ------------------------------------------------------------------------------
LaserHitTest:
    ; --- Fold batch (P3.1): enemy record staged once — .LHHit reloads type;
    ; loop writes no FetchPtr. ---
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    ldx #0
.LHLoop:
    cpx EnemyCount
    bcs .LHTOut
    lda EnemyDeadMask
    and EnemyBitTable,X
    bne .LHNext
    lda RoomY
    sec
    sbc EnemyRamY,X
    clc
    adc #3                      ; (RoomY-eY)+3 in [0..8] = eY in [RoomY-5, RoomY+3]
    cmp #9                      ; out of beam rows RoomY+2..3
    bcs .LHNext
    lda EnemyRamX,X
    sec
    sbc CollisionX
    clc
    adc #7
    cmp #15                     ; (eLo-lo)+7 <=14 -> |d| <=7 = overlap w/ 8px missile
    bcs .LHNext
.LHHit:
    ldy EnemyOffTable,X         ; re-fetch type (Y advanced for y-offset)
    jsr FoldIndirect
    cmp #LAMP
    beq .LHLamp
    lda EnemyDeadMask
    ora EnemyBitTable,X
    sta EnemyDeadMask
    lda #$50
    jsr AddScore
    rts
.LHLamp:
    jsr SetRoomDark             ; crash lamp = same as player-body touch:
    rts                         ; no kill bit, no score (idempotent no-op)
.LHNext:
    inx
    bne .LHLoop
.LHTOut:
    rts

; ==============================================================================
; Interrupt vectors
; ==============================================================================
    .ds $FFFA - *, 0               ; pad to vectors at $FFFA

    .word GameStart                 ; NMI vector
    .word GameStart                 ; RESET vector
    .word GameStart                 ; IRQ vector
