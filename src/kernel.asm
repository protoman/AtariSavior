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
RcBase          byte            ; rect cache count ($89 — was MapPtrLo;
                                ; rect4.x moved into the cache S3.2, and the
                                ; count needs a byte OUTSIDE bank1's $E0-$EF
                                ; stomp zone — see cache note below)
DropTarget      byte            ; spawn drop-in target Y (0 = idle); was
                                ; MapPtrPad1/MapPtrHi dead pad — repurposed
                                ; in place, keeps the sequential block from
                                ; shifting (see DropArm below)
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
; ObjBot removed (S3.0b): dead since S1.5 (stores deleted); was the LAST
; sequential decl → removal shifts no other ZP address ($BC is now free).

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
; PF0ScoreBuf/PF1ScoreBuf removed (S3.0): dead legacy EQUs — the 48px
; sprite score never used PF score buffers (decl-only, zero references).

; P3.4 rect cache — solid rect list copied once per EnterRoom, walked directly
; by PlayerHitsMap with NO bank2 fold (fold mid-function switched the EXECUTION
; bank; only byte-identical pad code may span a switch). Layout (S3.2 —
; UNIFORM STRIDE: all 5 rects contiguous, no windows, no .Stage3):
;   $89       count        (RcBase — sequential decl; MUST stay outside
;                           bank1's $E0-$EF stomp zone: the first attempt
;                           had count/rect4.h inside it and scorePtr writes
;                           zeroed rect4.h every HUD frame → probes passed
;                           through rect4 walls = tentacle walked inside
;                           walls. Keep ALL persistent cache bytes < $E0.)
;   $CC-$DF  rect0..rect4 (walk: FetchPtr base RcW1=$CC, Y=0..19, stride 4;
;                          mask index = Y>>2, table has a $00 entry for
;                          index 4 = rect4 never masked)
; rect4 x,y,w,h live IN the cache ($DC-$DF) since S3.2 — the old split
; slots are gone (DropTarget $8A keeps the allocation byte), Rc4W retired.
; Buffers packed: PF0 $C3-$C5, PF1 $C6-$C8, PF2 $C9-$CB (rows 0-2 only).
; ($E0/$E1 are spare/stomp-zone — never persistent bank0 state.)
RcW1            = $CC           ; walk FetchPtr base (rect0 x at Y=0; Y→$DF)
; Rc4W/Rc4H retired (S3.2): rect4.w/h = cache bytes $DE/$DF, reached by
; the uniform stride like every other field. RcBase is the $89 decl above.

; PF cave buffers (copied from ROM during VBLANK, read by kernel via absolute indexed)
; These share ZP space with bank1's HUD variables — safe because bank1
; runs AFTER the cave kernel. Bank1 overwrites them during HUD band;
; VBLANK re-populates them before the next kernel frame.
PF0Buf          = $C3           ; 3 bytes: TilePF0 rows 0-2 (stride-3 data S4.2)
                                ; (rows 0-2 pure since S3.4 — Y moved to $E2)
PF1Buf          = $C6           ; rows 0-2 only (S3.1 packed; was $CF)
RoomBandColor   = $BC           ; band-color cache (level_bank_plan P2.5) —
                                ; own byte since S3.1 (was $D2 = PF1Buf[3];
                                ; history: FIX 2026-09-28 was $D1 = PF1Buf[2]
                                ; collision → mid-wall gap; alias class now
                                ; gone entirely). Writer: VBLANK stage AFTER
                                ; LoadPFBuffer/BuildColupF (fold from
                                ; LevelEnemy+RoomNo*4+3). Readers: kernel
                                ; .WaterRow (direct lda, plain abs = 4c any
                                ; address) + overscan CheckBandTouch. Window:
                                ; VBL write → kernel + overscan read same
                                ; frame ($BC is nobody else's byte) → next
                                ; VBL restages.
PF2Buf          = $C9           ; rows 0-2 only (S3.1 packed; was $DB-$E6)
ColupfBuf       = $E7           ; 12 bytes: final COLUPF per tile row (stripe+hot)
FetchPtr        = $E5           ; fold-indirect pointer ($E5 lo, $E6 hi) —
                                ; MOVED S3.2 to free $E0 for rect4.h (cache
                                ; $CD-$E0 now uniform). Sits in bank1's
                                ; stomp zone (scorePtr3-hi/scorePtr4-lo) —
                                ; time-partitioned: bank0 stages only inside
                                ; VBL/overscan batches, bank1 rebuilds in
                                ; HUD after both windows. Contract (fold
                                ; wins): stage addr immediately before a
                                ; FoldIndirect batch.

; Enemy RAM shadow — live X/Y + packed flags. ROM records are read-only.
; Sequential vars end at $BB (ObjBot removed S3.0b); $BC = RoomBandColor,
; $BD-$BF EnemyRam, $C0 LaserState, $C1-$C2 EnemyRamD/P.
; Score lives at $F3-$F5 only ($F6/$F7 = BombX/BombTimer).
; EnemyRamY ($E2, 3B) — private bytes since S3.4 (was an alias over
; PF0Buf rows 0-2). It deliberately sits INSIDE bank1's HUD stomp zone
; ($E0-$EF score ptrs, written every frame) because every write and every
; read land inside one safe window:
;   [HUD stomp $E2-$E4] → [overscan: RefreshEnemyY/LoadEnemyRam WRITE]
;   → [CEH / Laser / moth READ] → [next VBL: SelectActiveObject READ]
;   → [HUD stomp ...]. No reader ever sits between the stomp and the write.
;   writers: RefreshEnemyY via DeriveEnemyY (overscan entry, EVERY frame —
;            live Y is derived from ROM spawn + EnemyRamP clock, no stored
;            movement state) + LoadEnemyRam (EnterRoom init);
;   readers: SelectActiveObject (VBLANK), CheckEnemyHit + LaserHitTest +
;            moth walk (overscan, after the refresh).
; Effect: $C3-$C5 = pure PF0Buf rows 0-2, never stomped → the per-frame
;   VBL repair (LoadPF0Only, ~130c + 3 folds) is deleted; full
;   LoadPFBuffer runs only on EnterRoom (PF1/PF2 rows 0-2 likewise have
;   no per-frame writer). bank1 owns $E0-$EF during HUD; bank0 never keeps
;   other persistent state there (FetchPtr $E0/$E1 = staged only).
EnemyRamX       = $BD           ; 3 bytes: live X per enemy ($BD-$BF, slots 0-2
                                ; only — enemies+lamps capped at 3 by editor
                                ; kMaxRoomElements, convert_level MAX_ENEMIES,
                                ; verify_build; slot 3 would collide with $C0)
LaserState      = $C0           ; laser (S1): b7 fire held this frame,
                                ;   b6 fire held last frame,
                                ;   b5-2 RoomDarkMask rooms 4-7,
                                ;   b1-0 sweep phase (0..3 = 0/8/16/8 px)
EnemyRamD       = $C1           ; dir bits 0-3 = enemy 0-3 (1=right, 0=left)
EnemyRamP       = $C2           ; bits0-3 moth phase (shared/sync); bits4-7
                                ;   vdir for spider/bat/tentacle (1=down)
EnemyRamY       = $E2           ; 3 bytes: live Y per enemy ($E2-$E4) —
                                ;   private since S3.4; see contract above

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
LASER_AUD_C     = 2             ; laser ch0 control: div-15 tone = low pitch
LASER_AUD_V     = 9             ; laser ch0 volume while fire held



; Facing direction of the player sprite's eye
FACING_RIGHT    = 0
FACING_LEFT     = 1

; LaserState bits (laser_implementation_plan S1)
LASER_HELD      = %10000000     ; b7: fire pressed this frame (INPT4 D7=0)
LASER_PHASE     = %00000011     ; b1-0: sweep phase 0..3 -> M0 offsets 0/8/16/8 px
LASER_DARK      = %00111100     ; b5-2: RoomDarkMask rooms 4-7 (IsRoomDark/SetRoomDark)

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
                                    ;  $F196 Overscan (bank1 stub literal tracks it)
                                    ;  + F0xx landmarks fixed)

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
    ; Initialize timer: 60 frames/step × 120 = 7200 = 120.0s
    lda #60
    sta TickCounter
    lda #120
    sta BarLevel                ; bar starts full
    ; --- Title screen: DropTarget=$FF sentinel (valid fall targets are Y
    ;     ≤ 191, so $FF never reads as a real drop) → boot lands in the
    ;     level-select state until console RESET starts the game. ---
    lda #$FF
    sta DropTarget

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
VBLTimer:                       ; sim: VBL work window starts here (TIM64T)
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
    ; Reads EnemyRamY ($E2) — no VBL writer of $E2 exists (Y writers are
    ; overscan-only, score ptrs are HUD-only), so no ordering constraint.
    jsr SelectActiveObject

    ; --- PF0: NO per-frame refresh since S3.4 — EnemyRamY moved to $E2-$E4,
    ; so $C3-$C5 keep the EnterRoom pattern forever (the old LoadPF0Only
    ; repair = 3 folds ≈ 130c/frame is deleted). PF1/PF2 rows 0-2 likewise
    ; have no per-frame writer; full 9-fold rebuild only on EnterRoom.
    jsr ApplyBombWalls          ; S6.1: re-apply thin-wall holes every frame
    jsr CallPad_BuildColupF    ; stripe+hot COLUPF bytes into ColupfBuf ($E7-$F2)

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
    jsr CallPad_IsRoomDark
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

    ; --- Tide row2 body count → CollisionX (kernel carrier; idle during kernel) ---
    ; Water band surface drifts 0-3 lines down/up. off = triangle(p),
    ; p = EnemyRamP>>4 (free-running clock, 16 frames per pixel = gentle
    ; wave speed): p0-3 = down (0→3), p4-7 = back up (3→0), p8-15 = rest
    ; (~2.1 s at 0). 256-frame period wraps 15→0 with off=0 both sides (no
    ; jump). Stores 36+off; kernel .Row row2 uses it, .WaterRow derives
    ; 47-count. CollisionX is overscan-only elsewhere — this VBL write is
    ; the last before the kernel read (stomp-zone safe, no new ZP byte).
    lda EnemyRamP
    and #$F0
    beq .TideBase            ; p=0 → off 0 (A already 0)
    lsr
    lsr
    lsr
    lsr                      ; A = p (1..15)
    cmp #8
    bcc .TideTri
    lda #0                   ; rest phase p8-15
    beq .TideBase            ; always
.TideTri:
    cmp #4
    bcc .TideBase            ; p 1-3: off = p (A holds it)
    eor #$FF                 ; p 4-7: off = 7-p
    sec
    adc #7                   ; ~p + 7 + 1 = 7-p (mod 256)
.TideBase:
    clc
    adc #36
    sta CollisionX

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
    ; Store ORDER is cycle-critical (thin-yellow-line fix, 2026-10-01): the
    ; stores land mid-visible (advance block then these pairs), so on the
    ; row1→row2 band-transition line the left half must keep the OLD band's
    ; PF+color while the right half may show the NEW band. Write cycles
    ; (cN = CPU cycles on the setup line, x = pixel at 4x, HBLANK ends c22.7):
    ;   PF0 w c34 x136 | PF1 w c41 x222 | COLUPF w c48 x296 |
    ;   COLUBK w c54 (Temp = frame const, invisible) | PF2 w c61 x460
    ; COLUPF 3rd: color flips at x296 = past ALL left ON-pixels (PF1 ends
    ; x187, PF2 cell17 ends x287); cells18-19 (x288-319) are never ON in any
    ; model row (PF2 bits6/7 always 0) so the flip there is invisible (BG =
    ; COLUBK). PF2 LAST: store lands past every right-half PF2 pixel (x449)
    ; → right PF2 keeps OLD band (= BG post-blast = no yellow; pre-blast
    ; cell17 = new pattern's wall = looks new). Old order (PF2 3rd = w c48,
    ; COLUPF last = w c61 x447) painted right PF2 (x350-446) NEW pattern
    ; under OLD hot color = the blinking thin yellow line at y191/192.
    lda PF0Buf,X
    sta PF0
    lda PF1Buf,X
    sta PF1
    ; COLUPF precomputed by BuildColupF (stripe + hot pulse) — one ZP load.
    ; Inline stripe+hot test was 84-109c; budget is 76c/scanline.
    lda ColupfBuf,X
    sta COLUPF

    ; --- Set tile row colors (Temp = this frame's COLUBK, set in VBLANK) ---
    lda Temp
    sta COLUBK
    lda PF2Buf,X
    sta PF2
    ; --- Scanlines this pass: rows 0/1 = 48; row 2 = 36+off (tide, CollisionX).
    ; The bottom water strip (last 12-off lines, bottom_band_plan rule 2)
    ; renders in .WaterRow after this pass — its own setup line + (11-off)
    ; bodies keeps the row-2 total at 49 lines (setup+48) exactly.
    cpx #TILE_ROWS-1
    beq .RowLinesTide        ; row 2: tide count (36+off) from CollisionX
    lda #LINES_PER_TILE
    bne .RowLinesLC          ; always (48 != 0)
.RowLinesTide:
    lda CollisionX           ; 36..39 — VBL tide calc (see VBL comment)
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
    ; Y — the water-strip band-color read is an inlined `lda` (Y untouched).
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
    lda RoomBandColor           ; inlined band-color read (was a jsr helper)
    beq .WRRestore              ; band off (0): keep Temp, no store
    sta COLUBK
.WRRestore:
.WRSkip:
    lda #47                     ; strip bodies = 47 - CollisionX (36+off)
    sec                         ;   = 11-off: total row2 setup+48 unchanged
    sbc CollisionX
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
    ; Bomb save/restore deleted (S3.0b): BuildColupF writes rows 0-2 only
    ; (TILE_ROWS=3) — nothing touched $F0-$F2 between the old save and
    ; restore (window audited: zero writers), so the round trip was a no-op.

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

    ; --- Write live Y → EnemyRamY ($E2-$E4; window-safe since S3.4: this
    ; runs after the HUD score-ptr stomp, before every reader) ---
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

    ; --- Spawn drop-in gate: while falling from the top (DropTarget != 0)
    ;     ALL input/physics/collision is bypassed -> DropStep only. ---
    lda DropTarget
    beq .NormalGame             ; idle -> normal play (adjacent, 3c/2c)
    jmp DropStep                ; tail-jumps back to OverscanAudio
.NormalGame:

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
    jsr CallPad_BombSndDrop          ; S10: short blip on place
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
    jsr LoseLife
.NoHotBump:

    ; --- Bottom band touch (RoomY in row 2 + band color on) → lose life ---
    jsr CheckBandTouch

    ; --- Move live enemies (snake first; other types no-op until S5+) ---
    jsr UpdateEnemies

    ; --- Check miner pickup (advances to next level) ---
    jsr CheckMinerPickup

    ; --- Check enemy collision (lose life on hit) ---
    jsr CheckEnemyHit

OverscanAudio:                  ; rejoin for the spawn drop-in (DropStep tail):
    ;     bomb fuse keeps ticking during the fall — only BombPlayerBlast is
    ;     gated (a mid-fall explosion must not cost a 2nd life/re-drop).
    ; --- Bomb fuse/explode tick (frames) ---
    jsr BombTick

    ; --- Bomb audio: hold registers while BombSnd > 0, else silence ---
    jsr CallPad_UpdateBombSound

    ; --- Jet engine audio (channel 1): buzz while Up is held ---
    jsr CallPad_UpdateJetSound

    ; --- Laser audio (channel 0): low zoom while fire held; ch0 is free ---
    jsr CallPad_UpdateLaserSound

    ; --- Decrement game timer (60 frames/step × 120 = 120s) ---
    dec TickCounter
    bne .TimerDone              ; not 1s yet
    lda #60
    sta TickCounter
    dec BarLevel
    bne .TimerDone              ; not empty yet (bne = was beq+jmp, −3B)
.TimerExpired:
    ; Time's up! Lose a life (shared path). C=1: lives exhausted +
    ; ReloadLevel done. C=0: physics zeroed by LoseLife.
    jsr LoseLife
    bcs .TimerDone
    lda #120
    sta BarLevel             ; reset bar for retry
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
; LoadPF0Only: PF0 phase (3 folds ≈ 130c) — now reached ONLY via
;   LoadPFBuffer's tail jump (EnterRoom full rebuild).
;   History: was also called every VBLANK frame to repair the per-frame
;   EnemyRamY stomp of $C3-$C5; that repair entry + jsr were deleted in
;   S3.4 when EnemyRamY moved to $E2-$E4 (PF0 rows 0-2 are never stomped).
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
    sta LineCount               ; NOT Temp — joystick byte stays live: after
                                ; EnterRoom the caller resumes CheckP0Right /
                                ; .NoVMove and reads Temp as held buttons
    lda RoomWallMask
    and #$0F
    ora LineCount
    sta RoomWallMask
    jmp .ERGotRoom
.ERSaveR0:
    sta LineCount               ; see above — Temp belongs to the input path
    lda RoomWallMask
    and #$F0
    ora LineCount
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
    ; Pre-compute PF1 and PF2 pointers (+3 bytes each — S4.2: tables are
    ; stride 3 now, was +12 in the 12-row era)
    clc
    lda RoomPF0Lo
    adc #3
    sta RoomPF1Lo
    lda RoomPF0Hi
    adc #0
    sta RoomPF1Hi
    clc
    lda RoomPF1Lo
    adc #3
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
    sta RcBase                  ; → $89 (outside the bank1 stomp zone)
    iny                         ; Y=1, first rect byte
.rcW1: jsr FoldIndirect
    sta RcW1-1,Y                ; $CC-$DF (Y=1..20 = rects0-4 — UNIFORM
    iny                         ; stride since S3.2, incl. rect4; was 4 loops)
    cpy #21
    bne .rcW1

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
    jsr LoadEnemyRam            ; writes EnemyRamX/Y/D ($E2 disjoint from PF
    rts                         ; buffers since S3.4 — order now cosmetic)

; ------------------------------------------------------------------------------
; LoadEnemyRam — copy each ROM enemy's x,dir into the RAM shadow.
; ROM stride 4 (S4.1): type(+0), x(+1), y(+2), dir(+3) — the old
; range_min/range_max slots are gone (nothing read them).
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
    ldy EnemyOffTable,X         ; Y = X*4 (table lookup — same as UE_Loop;
                                ; drops the 9 B txa/asl/sta Temp/asl/clc/adc
                                ; sequence, -6 B main. No caller reads Temp
                                ; after this routine.)
    iny                         ; +1 = x
    jsr FoldIndirect
    sta EnemyRamX,X
    iny                         ; +2 = y
    jsr FoldIndirect
    sta EnemyRamY,X
    iny                         ; +3 = dir (S4.1: range slots dropped)
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
    ldy EnemyOffTable,X          ; Y = X*4 = type offset
    jsr FoldIndirect             ; type
    cmp #ENEMY_TENTACLE
    bne .UENotTent
    jmp UE_Tentacle              ; tail jmp: saves 2 push bytes (stack guard)
.UENotTent:
    cmp #ENEMY_MOTH              ; E4: moth body runs in bank2 (code fold)
    bne .UENotMoth
    jmp UE_MothTramp             ; tail jmp: 0 push (stack guard, like tentacle)
.UENotMoth:
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
    iny                          ; +3 = ROM dir (S4.1: range slots dropped)
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
    iny                          ; +3 = ROM dir (S4.1: range slots dropped)
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
; save player xy in ActiveObjectX/Y scratch (NOT the stack — 3 pha drove SP to
; $F4 and jsr return bytes stomped BombTimer $F7 / BombX $F6 every 4th frame,
; so the fuse never reached 0), put candidate X + live tentacle Y, call,
; restore from scratch (lda/sta do not disturb C), commit only when C=0.
; Slot X likewise saved in EnemyIndex (PHM clobbers X in its rect walk
; — E3 gate bug: the commit wrote to EnemyRamX[row] instead of
; EnemyRamX[slot] → frozen X). All three bytes are write-before-read for
; every reader (SelectActiveObject/CheckEnemyHit rewrite before reading).
; Candidate >= 160 (incl. wrap 255) rejected before probe — room edge hold.
; In: X = enemy slot. Clobbers A/Y/Temp/X (X restored around the probe).
; Entered via JMP from the dispatch; every path exits .TentOut → jmp UE_Next.
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
    sta ActiveObjectX            ; save player position in ZP scratch (was pha:
    lda RoomY                    ; the 3-pha path hit min SP $F4 → bomb stomp)
    sta ActiveObjectY
    lda Temp
    sta RoomX                    ; probe as the tentacle (candidate x)
    lda EnemyRamY,X
    sta RoomY                    ; live tentacle y (refreshed this overscan)
    stx EnemyIndex               ; save slot: PlayerHitsMap clobbers X
                                 ; (rect walk ldx/dex/tax) — slot was lost here
    jsr PlayerHitsMap
    ldx EnemyIndex               ; X = slot again (ldx/sta preserve C)
    lda ActiveObjectY
    sta RoomY                    ; restore player Y (lda/sta preserve C)
    lda ActiveObjectX
    sta RoomX                    ; restore player X
    bcs .TentOut                 ; wall → hold position
.TentCommit:
    lda Temp
    sta EnemyRamX,X              ; clear → commit candidate step
.TentOut:
    jmp UE_Next                  ; tail exit (rts would need a dispatch jsr)

; ------------------------------------------------------------------------------
; DeriveEnemyY — live Y for enemy slot X. Moving types are DERIVED, not stored:
; there is no free ZP byte for per-slot movement state (phase/direction live
; in the shared EnemyRamP/EnemyRamD bitfields), so the formula is
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
    cmp #ENEMY_MOTH             ; E4: Y arm lives in the $FC4F gap
    bne .DEYStatic
    jmp MothYDerive
.DEYStatic:
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
    bne DEYDelta
    lda #1                      ; 3 -> 1
                                ; (dead `jmp DEYDelta` removed — target was
                                ;  the very next instruction)
DEYDelta:                      ; A = delta, then add ROM spawn y
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
    beq DEYDelta               ; always
.DEYSUp:
    cmp #25
    bcc DEYDelta               ; p <= 24: delta = p (down, 0..24)
    eor #$FF
    sec
    sbc #$CF                    ; 48-p = (255-p)-207, up phase (p 25..47)
    jmp DEYDelta

; ==============================================================================
; Room exit handlers — check connection table, switch rooms, reposition player
; ==============================================================================
; Connection table: 4 bytes per room (up, down, left, right), $FF = no exit.
; After transition: player is placed at the OPPOSITE edge of the new room.
; Jetpack velocity carries over (matches comparison/hero pattern).
; GetConnIdx moved to bank1 (leaf_move_plan batch B) — CallPad_GetConnIdx.

ExitRoomDown:
    jsr CallPad_GetConnIdx
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
    jsr CallPad_GetConnIdx          ; +0 = up direction
    jsr FoldIndirect
    cmp #$ff
    beq .NoUp
    jsr EnterRoom
    lda #PLAYER_MAX_Y
    sta RoomY               ; enter at the bottom edge
.NoUp:
    rts

ExitRoomLeft:
    jsr CallPad_GetConnIdx
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
    jsr CallPad_GetConnIdx
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
    lda LaserState
    and #%11000111              ; clear RoomDarkMask rooms 4-7 (LaserState b5-2)
    sta LaserState
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

    ; Drop-in from the screen top to the start Y (DropArm also zeroes the
    ; jetpack state + laser — stage start, game over and level advance all
    ; land here).
    jmp DropArm

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
; Sets ObjBase, ActiveObjectX, ActiveObjectY, ObjTop, COLUP1.
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
    ldy EnemyOffTable,X         ; Y = EnemyIndex * 4 = type offset
    ; --- Fold batch (P3.1): enemy record staged before IsRoomDark (A-only,
    ; Y and FetchPtr survive the call). ---
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    jsr CallPad_IsRoomDark              ; clobbers X — Y still = type offset
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
    lda EnemyRamY,X             ; live Y from $E2 (private since S3.4)
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
    ; Set ObjTop for kernel GRP1 visibility check.
    ; S2.2: ObjTop stored RoomY-relative (ObjTopRel = ActiveObjectY-RoomY+1) so
    ; the kernel compares against running-Y (`tya`) instead of `lda Scanline`
    ; — frees 9c/line (lda Scanline + inc Scanline) for the laser beam write.
    ; Kernel .Grp1 does: tya / sec / sbc ObjTop / cmp #8 / bcs .ObjZero.
    ; ObjBot (write-only, no readers): stores removed S1.5, decl removed
    ; S3.0b (was last sequential decl — no address shift).
    lda ObjBase
    beq .SONoObj
    lda ActiveObjectY
    sec
    sbc RoomY
    clc
    adc #1                      ; A = ActiveObjectY - RoomY + 1 (mod 256)
    sta ObjTop
    rts
.SONoObj:
    lda #0
    sta ObjTop
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
    ldy EnemyOffTable,X         ; Y = EnemyIndex * 4
    jsr FoldIndirect            ; type
    cmp #LAMP
    beq CEH_Lamp
    ; Hit! Mark this enemy dead (bit = index)
    lda EnemyDeadMask
    ora EnemyBitTable,X         ; X = EnemyIndex (set at CEH hit)
    sta EnemyDeadMask
    lda #$50              ; +50 points per kill
    jsr CallPad_AddScore
    ; Lose a life (shared path — tail jmp: its rts returns to caller)
    jmp LoseLife
CEH_Lamp:
    ; Broad overlap guarantees lower bound; narrow to lamp's 4 lit pixels.
    lda CollisionX
    cmp #PLAYER_WIDTH + LAMP_WIDTH - 1
    bcs CEHNext
    ; Only fire once (bit already set → no-op); no life loss, not EnemyDeadMask
    jsr CallPad_SetRoomDark
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
    jsr CallPad_BombMarkWalls   ; S6.3: set WallMask; A = #walls newly broken
    tax
    beq .BTNoScore
.BTScore:
    lda #$75                    ; +75 points per broken wall (moved out of
    jsr CallPad_AddScore        ;   BMW — pads cannot nest from a pad body)
    dex
    bne .BTScore
.BTNoScore:
    jsr BombEnemyBlast          ; S9: kill enemy ±1 col any Y (before player — reload clears)
    jsr BombPlayerBlast         ; S5: player ±1 col any Y → life (may ReloadLevel → clears masks)
    jsr CallPad_BombSndExplode          ; S10: noise burst
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
    jsr CallPad_AddScore
    rts
.BEBNext:
    inc EnemyIndex
    jmp .BEBLoop
.BEBDone:
    rts

; ------------------------------------------------------------------------------
; BombPlayerBlast — on explode, if player col in ±1 col of bomb col (any Y):
;   lose 1 life (shared LoseLife path).
; Cols = px/4 (0..39 screen). Y ignored.
; ------------------------------------------------------------------------------
BombPlayerBlast:
    lda DropTarget
    bne .BPBMiss                ; spawn drop-in: falling = invulnerable
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
    jmp LoseLife                ; shared life path (tail: rts to caller)
.BPBMiss:
    rts

; Bomb audio bodies (BombSndDrop/BombSndExplode) moved to bank1
; (leaf_move_plan batch A) — called via CallPad_BombSnd*.

; ------------------------------------------------------------------------------
; BombMarkWalls — MOVED to bank1 (S5.2) — CallPad_BombMarkWalls ($FB10).
;   Returns A = #walls newly broken; the fuse-expiry caller scores +75 each
;   (pads cannot nest: ReturnPad switches to bank0 mid-call). bank1 keeps
;   its own copies of ABWXTab/ABWWTab/BombMaskBit (ROM is per-bank).
; ------------------------------------------------------------------------------

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
    sta LineCount               ; NOT Temp — EnterRoom runs this mid-input and
                                ; CheckP0Left/Right read Temp as held buttons
    lda ABWHTab,X               ; ZP address of rect.h
    tay
    lda 0,Y                     ; rect.h
    clc
    adc LineCount
    sec
    sbc #1
    sta CollisionCellX          ; last row = y+h-1
    txa
    pha                         ; rect index — ClearPFColumn clobbers X
    lda CollisionX              ; col
    jsr CallPad_ClearPFColumn           ; A=col, LineCount=first, CollisionCellX=last
    pla
    tax
    ; S6.4: flag rect.w b7 = destroyed — both walks (bank0 PHM, bank2 moth)
    ; skip at their w-read. Single choke point: every-frame VBL re-punch
    ; + EnterRoom mask-restore run this loop, so b7 tracks WallMask.
    lda ABWWTab,X
    tay
    lda 0,Y
    ora #$80
    sta 0,Y
.ABWNext:
    dex
    bpl .ABWLoop
.ABWDone:
    rts

; ZP address tables for ApplyBombWalls/BombMarkWalls rect cache (rects 0-3)
ABWXTab: .byte RcW1, RcW1+4, RcW1+8, RcW1+12   ; rect.x ZP addrs (EQU-derived
ABWYTab: .byte RcW1+1, RcW1+5, RcW1+9, RcW1+13 ;  since S3.1 — tables can no
ABWWTab: .byte RcW1+2, RcW1+6, RcW1+10, RcW1+14 ; longer go stale vs cache)
ABWHTab: .byte RcW1+3, RcW1+7, RcW1+11, RcW1+15

; ==============================================================================
; Data tables
; ==============================================================================

; --- Explosion blink COLUBK: index = (60-BombTimer) % 3 ---
BombBlinkColors:
    .byte COLOR_CAVE_BG         ; 0 black
    .byte COLOR_BLINK_Y         ; 1 yellow
    .byte COLOR_BLINK_R         ; 2 red
    .byte COLOR_BLINK_Y         ; 3 yellow (4-phase blink: b/y/r/y)

; WallMask bit for rect index 0-3 (BombPacked b3-6); index 4 (rect4) =
; $00 entry (S3.2) → `and BombPacked` = 0 → never skipped.
BombMaskBit:
    .byte $08, $10, $20, $40, $00

; BombClearMask moved to bank1 with ClearPFColumn (leaf_move_plan batch B).

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
LEVEL_COUNT    = 3             ; hand copy of generated LEVEL_COUNT (cmp in
                                ; LoadLevel advance guard — test asserts sync)
LEVEL_DATA_ADDR = $FB6E        ; frozen address of bank2's LevelDataTable
                                ; (S4.1 −$FAFA, S4.2 −$FA8E, 2026-10-02
                                ;  −$FA86 as the ≤2-object room migration
                                ;  shrank the tables; check_frozen_addrs
                                ;  enforces)
                                ; (test asserts bank2.lst label == this)

; ==============================================================================
; YToRowTable — convert scanline (0-191) to 48-line band row (0-3), idx A>>2
; ==============================================================================
; The jsr wrapper that used to live here was dead (PlayerHitsMap inlines the
; lsr/lsr/tay/lda lookup — saves 2 JSR stack push levels to keep SP >= $F8)
; and was removed in S1.6. Table rationale: the old subtract loop grew
; linearly with RoomY and made 3× PlayerHitsMap (fall 2 + L/R 1) exceed
; overscan TIM64T=35 (~2240c) in 4-rect rooms → frame >262 lines → vertical
; roll when strafing while falling.
; Indexed by A>>2 (48-entry table): floor(floor(A/4)/12) = floor(A/48).
; Costs +4c/call vs the 192-entry table, saves 144 ROM bytes.
; Max A = PLAYER_MAX_Y+11 = 143 → index 35 (fits 48 entries).

; 48 entries: 12 each of 0,1,2,3 (value = index/12 = scanline/48).
YToRowTable:
    .byte 0,0,0,0,0,0,0,0,0,0,0,0
    .byte 1,1,1,1,1,1,1,1,1,1,1,1
    .byte 2,2,2,2,2,2,2,2,2,2,2,2
    .byte 3,3,3,3,3,3,3,3,3,3,3,3

; ==============================================================================
; PlayerHitsMap — check player bounding box against the room's PF map
; ==============================================================================
; Boxes are in tile coordinates (col 0-19, row 0-2); the walk tests the
; PF0/1/2Buf cell bits directly (cell_collision_plan 2.1) — no rect cache,
; no rect-count limit. The playfield is reflected, so right-half display
; cols mirror via 39-col IN THE PROLOGUE (walk sees left-half only).
; Returns C=0 if clear, C=1 if blocked.
PlayerHitsMap:
; --- Tile row range (top, bottom) ---
; Inlined row lookup: saves 2 JSR stack push levels (4B on stack) to keep SP >= $F8
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

; --- Cell walk (cell_collision_plan 2.1): test the PF buffers directly ---
; The ZP rect cache ($CC-$DF, 5-slot limit) is gone from THIS walker: the
; render buffers PF0/1/2Buf ARE the map (ApplyBombWalls punches bomb holes
; into them), so room complexity is unbounded and geometry parity is proven
; by tools/test_cell_map.py (box vs geometry, all models/rooms).
; Prologue ranges (all left-half space): CollisionCellY = top row,
; CollisionEndY = bottom row, CollisionEndX = min col, CollisionCellX = max
; col — cols are endpoint-mirrored above, so ALWAYS 0-19 here (no in-loop
; mirror; bank2 display-space walkers add their own when they convert).
; RectCount = running row, CollisionX = running col (both were walk temps
; before — same ZP, no new allocation).
; Exits: HIT -> jmp HotOverlapFlag (tail, C=1 contract preserved);
;        miss -> clc / rts. Stack depth during the walk = old walk exactly
;        (no jsr added — sim_bomb_fuse gameplay min-SP guard stays $F8).
    lda CollisionCellY
    sta RectCount
.CWRow:
    lda CollisionEndX
    sta CollisionX
.CWCol:
    lda CollisionX
    tax
    ldy RectCount
    tya
    clc
    adc ColOff,X            ; PF0/PF1/PF2 group offset (0/3/6)
    tay
    lda PF0Buf,Y            ; $C3+row+off — the byte the kernel renders
    and ColMask,X           ; bit for this source col
    bne .CWHit              ; solid (Z=0)
    lda CollisionX
    cmp CollisionCellX      ; col == max?
    beq .CWRowDone
    inc CollisionX
    bne .CWCol              ; always (col never wraps to 0)
.CWRowDone:
    lda RectCount
    cmp CollisionEndY       ; row == bottom?
    beq .CWNoHit
    inc RectCount
    bne .CWRow              ; always (row never wraps to 0)
.CWHit:
    jmp HotOverlapFlag      ; C=1 contract; hot rects unchanged (ROM stream)
.CWNoHit:
    clc
    rts

EnemyOffTable:
    .byte 0,4,8                 ; enemy index * 4 (stride S4.1; offset into
                                ; enemy data type,x,y,dir)

; BitMaskTable moved to bank1 with IsRoomDark/SetRoomDark (leaf_move_plan).

; ------------------------------------------------------------------------------
; RefreshEnemyY moved post-pad (after TitleWork) — 2026-10-02, so its SELECT
; → title check costs 0 pre-pad bytes (headroom 1B). Pins .ds $FBF8/$FC49
; keep every downstream pre-pad address unchanged.
; ------------------------------------------------------------------------------

; ==============================================================================
; E4 moth exit tramp ($FC49-$FC4E) — bank2 executes `sta $1FF6` at $FC49
; (byte-identical slice, guard: verify_build), then the fetch at $FC4C comes
; from bank0 = `jmp UE_Next` (real label here — no cross-bank address sync).
; bank0's `sta $1FF6` copy never runs; bank2's bytes from $FC4C never run.
;
; MUST stay off $FFF6-$FFF9: those are the ONLY addresses in code space where
; (addr & $1FFF) lands in $1FF6-$1FF9 = F6 hotspot mirrors. Stella's
; CartridgeEnhanced::peek (CartEnh.cxx:157, ADDR_MASK=$1FFF) calls
; checkSwitchBank on READS — the old $FFF2 placement fetched the `jmp`
; operands at $FFF6/$FFF7 and flipped banks mid-instruction (operand hi from
; bank1 = $00 -> jmp $007D -> HUD runaway, 359/360-line frames, 5-byte stack
; leak per rogue Overscan entry -> SP decayed to $E1 -> frame-3 crash where
; jsr RefreshEnemyY's return landed on FetchPtr). Real F6 is write-only, but
; no fetched byte may ever sit in the mirror zone.
; ==============================================================================
; ==============================================================================
; Cross-bank call pads (docs/leaf_move_plan.md) — byte-identical copies live in
; bank1 at the SAME addresses. F6 hotspots switch on ANY write — the written
; value is ignored (proven by FoldIndirect's `sta $1FF6` carrying data bytes) —
; so the pads `sta $1FF7`/`sta $1FF6` with A AS-IS: A/X/Y/flags pass through
; unchanged, making the pad equivalent to the original inlined `jsr`.
; (2026-09-30 bug: `lda #1` before `sta $1FF7` clobbered A — ClearPFColumn
; punched col 1 instead of the bomb's col, AddScore added +1 instead of
; +50/+75. Hole appeared at screen col 1 + mirror col 18 = "second tile from
; each edge"; collision stayed correct because WallMask is separate.)
; `sta` does not touch flags — IsRoomDark's `beq` contract survives the
; return. Carry survives. No stack use.
; ==============================================================================
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF6
    rts
CallPad_UpdateBombSound:
    sta $1FF7
    jmp $F9C0
CallPad_UpdateJetSound:
    sta $1FF7
    jmp $F9CF
CallPad_BombSndDrop:
    sta $1FF7
    jmp $FA00
CallPad_BombSndExplode:
    sta $1FF7
    jmp $FA13
CallPad_GetConnIdx:
    sta $1FF7
    jmp $FA26
CallPad_ClearPFColumn:
    sta $1FF7
    jmp $FA38
CallPad_AddScore:
    sta $1FF7
    jmp $FA7F
CallPad_IsRoomDark:
    sta $1FF7
    jmp $FC78
CallPad_SetRoomDark:
    sta $1FF7
    jmp $FC9E
CallPad_UpdateLaserSound:
    sta $1FF7
    jmp $FAA7
CallPad_BuildColupF:
    sta $1FF8                   ; S5.1: body lives in bank2 (direct rect reads)
    jmp $FC4F
CallPad_BombMarkWalls:
    sta $1FF7                   ; S5.2: body lives in bank1 ($FB10)
    jmp $FB10

    .ds $FC49 - *, 0             ; pin (main growth past $FC49 = build error)
MothExitPad:
    sta $1FF6                   ; select bank0 (executed from bank2's copy)
    jmp UE_Next                 ; resume dispatch loop (bank0 half)

; ------------------------------------------------------------------------------
; MothYDerive — E4 Y arm (docs/e4_moth_plan.md). 25 B EXACT: fills the
; $FC4F-$FC67 gap; 26 B trips org $FC68 reverse-index (loud build error).
; In: Y = record+0 (type offset), X = slot (preserved). Out: A = live Y.
; Y sine ±6 px: tri = clamp(triangle((EnemyRamP>>1)&15), 0..6) → ×2−6.
; Phase period 16 divides the 256 clock exactly (no teleport), continuous
; at the p15→p0 wrap (both −6). Jump-tail into DEYDelta: stack depth of
; DeriveEnemyY's caller unchanged (sta Temp / iny iny / fold y / adc / rts).
; ------------------------------------------------------------------------------
MothYDerive:
    lda EnemyRamP               ; free-running frame clock (RefreshEnemyY incs)
    lsr
    lsr                         ; ÷4: vertical tick = half the X tick (user tuning:
    and #15                     ; sine period 32→64 frames = half vertical speed)
    cmp #8
    bcc .mUp
    eor #15                     ; mirror: tri = p<8 ? p : 15-p (0..7)
.mUp:
    cmp #7
    bcc .mOk
    lda #6                      ; clamp tri ≤ 6 → delta exact ±6
.mOk:
    asl                         ; 0..12 (C=0: bit7 clear)
    adc #$FA                    ; ×2−6 → delta −6..+6 (C=0 → A−6 mod 256)
    jmp DEYDelta                ; shared tail — A = delta, Y = record+0

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

; ClearPFColumn + BombClearMask moved to bank1 (leaf_move_plan batch B).

; UpdateJetSound moved to bank1 (leaf_move_plan batch A) — CallPad_UpdateJetSound.

; AddScore moved to bank1 (leaf_move_plan batch B) — CallPad_AddScore.

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
; HotOverlapFlag — moved to bank2 (S5.3): fold-free body (HotOverlapBody)
;   reads RoomRects directly via (FetchPtr),Y — 7 folds → 7 direct reads
;   (one less push level on the hot path too). Entry tramp pinned $FE80
;   (byte-identical bank0/bank2, moth pattern — the $FBF8-$FC48 pad window
;   is full: 5 B left, a stub needs 6 B). Call sites below keep
;   `jmp HotOverlapFlag` (tail: 0 push) and the C=1 contract: body ends
;   `sec / jmp $FBF8` (ReturnPad), so the pad's rts pops the ORIGINAL
;   caller's return. Full behavior docs moved with the body.
;   Behavior: if the player's proposed tile range (CollisionCell*) overlaps
;   any hot-only rect, set Temp bit 7 (HotBump), called from PlayerHitsMap
;   HIT while CollisionCell* still describe the rejected position.
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; LoseLife — the single life-loss path (enemy hit, timer expiry, bomb blast,
; hot rock, band). Returns C=1: lives exhausted, ReloadLevel already done
; (LoadLevel re-places the player — callers skip their stay action).
; C=0: still alive — physics zeroed here; caller does its per-site stay
; action (bar reload, RoomY shift). Tail-callable (`jmp LoseLife`).
; ------------------------------------------------------------------------------
LoseLife:
    dec PlayerLives
    bpl .LLStay
    lda #3
    sta PlayerLives
    lda #$00
    sta EnemyDeadMask
    jsr ReloadLevel
    sec
    rts
.LLStay:
    jmp DropArm                 ; same drop-in code: X/Y stay, fall from top
                                ; (DropArm zeroes physics + laser, C=0 out)

; IsRoomDark / SetRoomDark + BitMaskTable moved to bank1 (leaf_move_plan B).

; ------------------------------------------------------------------------------
; CheckBandTouch — overscan: if band on and sprite touches the water strip →
; life. Strip = bottom ~12 lines of the cave (bottom_band_plan rule 2);
; sprite origin RoomY >= 125 enters it (125 + PLAYER_SPRITE_H - 1 = 136).
; Same path as hot/enemy: lose life, then respawn 12 scanlines up (min 0).
; Band color = VBLANK-staged RoomBandColor ($D2, PF1Buf[3] dead-row alias;
; staged by the VBLANK fold from LevelEnemy+RoomNo*4+3 — a kernel-time fold
; overruns the .WaterRow line). Read inlined here and in .WaterRow (0 = off).
; ------------------------------------------------------------------------------
CheckBandTouch:
    lda RoomBandColor
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
    jsr LoseLife
    bcs .LLBdone               ; exhausted: ReloadLevel placed the player
    lda DropTarget             ; armed death Y (DropArm already zeroed RoomY)
    sec
    sbc #12                     ; clear the strip (spec: -= 12, not whole band)
    bcs .LLBstore
    lda #0
.LLBstore:
    sta RoomY
    jmp DropArm                 ; same code, destiny Y = one tile above water
.LLBdone:
    rts

; ------------------------------------------------------------------------------
; DropArm / DropStep — the ONE spawn drop-in (user rule: same code for every
; restart, only the destiny X/Y changes — X is already in RoomX, placed by the
; caller; Y is animated from the screen top down to it).
; Triggers: stage start / game over / level advance (LoadLevel tail),
; enemy/blast/timer/hot death (.LLStay, same position), water (LoseLifeBand,
; Y-12). All tail-call it -> zero added stack depth (sim_bomb_fuse guard).
;
; DropArm (A implied = current RoomY, C=0 out): freezes RoomY as DropTarget,
; starts the sprite at the top (RoomY=0), zeroes physics + laser state so
; descent is clean (LaserInput is skipped by the gate; beam gate forced 0).
;
; DropStep (runs instead of input/physics/collision while DropTarget != 0):
; 8.8 accumulator PlayerYSub += DropSpeedTable[DropTarget>>4]; carry ->
; inc RoomY; arrival (RoomY >= DropTarget) -> DropTarget = 0, normal control
; resumes next frame. Speed table = Y*256/(60+Y/2) sampled per 16px tier ->
; fall lasts ~60+Y/2 frames = 1.0-2.2 s (shallow start = quicker arrival).
; Tail-jumps to OverscanAudio: bomb/laser/input/physics/horizontal/hot/band/
; miner/enemy-hit/BombTick are all bypassed (enemies + bombs frozen 1-2 s,
; timer keeps running; bank1 UpdateJetSound hears DropTarget as throttle).
; ------------------------------------------------------------------------------
DropArm:
    lda DropTarget
    cmp #$FF
    beq .DATitle               ; title ($FF sentinel): static pose at start
    lda RoomY
    sta DropTarget
    lda #4                      ; 1..7 = jet "burning": VBL flutter runs
    sta JetPower                ;   (JP/8=0 keeps bank1 pitch at idle base)
    lda #0
    sta RoomY
    sta PlayerYSub
    sta vyLo
    sta vyHi
    lda LaserState
    and #LASER_DARK             ; reset laser, keep rooms 4-7 dark (parity:
    sta LaserState              ; EnemyRamD bits survive DropArm too)
    lda #0                      ; A out = 0 (DropArm contract, was sta LaserState)
    sta LaserBeamOn
    clc
    rts
.DATitle:
    ; Title: player already placed at level start by LoadLevel. Hide all
    ; GRP1 objects (EnemyCount=0 → SelectActiveObject .SONothing blanks
    ; ObjBase/ObjTop) and drop the miner slot so SELECT/RESET reloads
    ; refresh them via EnterRoom. HUD score = level+1 ("000001" = level 0).
    lda #0
    sta EnemyCount
    lda #$FF
    sta LevelMinerRoom          ; ROOM_NONE: no miner slot, no pickup
    lda Level
    clc
    adc #1
    sta ScoreTe                 ; ones digit (LEVEL_COUNT ≤ 9 — ≥10 needs
    lda #0                      ;  a packed-BCD tens digit here)
    sta ScoreTh
    sta ScoreHu
    clc
    rts

DropStep:
    lda DropTarget
    beq .DSdone                 ; idle (target 0 = nothing to fall)
    cmp #$FF
    beq TitleWork               ; title sentinel: select/reset, no fall
    lsr
    lsr
    lsr
    lsr
    tay
    lda DropSpeedTable,y
    clc
    adc PlayerYSub
    sta PlayerYSub
    bcc .DSdone                 ; subpixel: no whole pixel yet this frame
    inc RoomY
    lda RoomY
    cmp DropTarget
    bcc .DSdone
    lda #0
    sta DropTarget              ; arrived — input/physics resume next frame
    sta JetPower                ; clean resume (no phantom thrust hop)
.DSdone:
    jmp OverscanAudio           ; rejoin past physics/collision (no rts)

DropSpeedTable:                 ; 8.8 px/frame per Y>>4 tier (Y = tier*16+8)
    .byte 32,85,128,163,192,216,238,255,255

; ------------------------------------------------------------------------------
; TitleWork — level-select screen (DropTarget = $FF sentinel, dispatched from
; DropStep every frame). Player stands at the level start: no gravity, no
; enemies (count/miner cleared by DropArm .DATitle), no sound, timer frozen
; (tail skips the TickCounter/BarLevel block). HUD score = level+1.
;   SELECT (SWCHB b1, active-low EDGE) → level+1, wrap → 000001, reload room 0
;   RESET  (SWCHB b0, active-low EDGE) → score 000000, LoadLevel tail arms
;          the real drop-in → gameplay starts
; StepsLeft = previous SWCHB sample (physics is skipped on title, so it is
; title-owned; the first play frame rewrites it as the step budget).
; Console switches are read again after any jsr (LoadLevel clobbers X/Y/A).
; ------------------------------------------------------------------------------
TitleWork:
    ; --- SELECT edge: prev released (1) & now pressed (0) ---
    lda StepsLeft
    and #%00000010
    beq .TWselDone             ; held from last frame -> no repeat
    lda SWCHB
    and #%00000010
    bne .TWselDone             ; released now -> no press
    inc Level
    lda Level
    cmp #LEVEL_COUNT
    bne .TWselGo
    lda #0
    sta Level                  ; wrap: no level above → back to 000001
.TWselGo:
    jsr LoadLevel              ; title arm re-runs → score/objects refreshed
.TWselDone:
    ; --- RESET edge ---
    lda StepsLeft
    and #%00000001
    beq .TWrstDone
    lda SWCHB
    and #%00000001
    bne .TWrstDone
    lda #0
    sta DropTarget             ; leave title → LoadLevel tail arms real fall
    sta ScoreTh                ; gameplay score starts at 000000
    sta ScoreHu
    sta ScoreTe
    jsr LoadLevel
.TWrstDone:
    lda SWCHB
    sta StepsLeft              ; remember sample for next frame's edges
    ; --- Frame audio: ch0 silenced by UpdateBombSound (BombSnd=0); jet
    ;     channel force-muted here — UpdateJetSound is skipped because
    ;     $FF would read as "falling" and buzz; laser skipped (LaserState
    ;     = 0, AUDV0 covered above). ---
    jsr BombTick
    jsr CallPad_UpdateBombSound
    lda #0
    sta AUDV1
.TWwait:
    lda INTIM
    bne .TWwait
    jmp StartFrame

; ------------------------------------------------------------------------------
; RefreshEnemyY — write live Y → EnemyRamY (every slot, live or dead).
; Runs at overscan entry: inside the safe window (after the HUD score-ptr
; stomp of $E2-$E4, before LaserInput / CheckEnemyHit / moth / next frame's
; SelectActiveObject read it) — see the EnemyRamY contract at the ZP map.
; E1: moving types (bat) get ROM spawn + TickCounter-derived offset via
; DeriveEnemyY — no persistent movement state exists in RAM.
; Clobbers A/X/Y. Moved post-pad 2026-10-02 (SELECT → title needs this
; block after the pads; pre-pad headroom is 1B).
; ------------------------------------------------------------------------------
RefreshEnemyY:
    inc EnemyRamP                ; free-running frame clock (wraps 0-255).
                                 ; TickCounter is the 60-frame GAME timer
                                 ; (decrements 60->1, reloads) — gates derived
                                 ; from it wrapped every second (spider
                                 ; "teleported": (TC>>3)&63 only ever saw
                                 ; 0..7 and counted DOWN 0->7 = jump).
    ldx EnemyCount              ; countdown loop (-2 B vs forward; derive
    beq .REYDone                ; order n-1..0 — derivations independent,
.REYLoop:                       ; every reader runs after refresh completes)
    dex
    jsr DeriveEnemyY            ; A = live Y (ROM copy, or derived for bat)
    sta EnemyRamY,X
    txa                         ; N/Z must come from X: flags after jsr are
    bne .REYLoop                ; the sign of the DERIVED Y byte (bpl ran
.REYDone:                       ; away at X=$FF, writing $1C2/$1C1/... =
                                ; mirrored EnemyRamP/EnemyRamD/TIA = blink,
                                ; black rooms, broken PF, invisible sprites)
    ; --- SELECT held → back to the title / level-select screen ---
    lda DropTarget
    cmp #$FF
    beq .REYRts                 ; already title (TitleWork owns SELECT)
    lda SWCHB
    sta StepsLeft               ; latch so TitleWork sees "held" (no re-fire)
    and #%00000010
    bne .REYRts                 ; SELECT released
    lda #$FF
    sta DropTarget              ; title sentinel
    jsr LoadLevel               ; tail → DropArm .DATitle (score/objects)
    pla                         ; drop OUR return address (LoadLevel already
    pla                         ; popped its own) — tail into TitleWork
    jmp TitleWork
.REYRts:
    rts

; ------------------------------------------------------------------------------
; BuildColupF — 12-byte final COLUPF image at ColupfBuf ($E7-$F2).
;   Stripe: rows 0,2 = LevelWallColor; row 1 = LevelWallColor2.
;   Hot rows overwrite with TickCounter-bit4 pulse (COLOR_HOT_Y/R).
;   $F0-$F2 (bombs) NO LONGER overlap-saved: body writes rows 0-2 only,
;   save/restore round trip deleted (S3.0b — window audit: zero writers).
;   Bank1 clobbers $E0-$EF during HUD; VBLANK rebuilds every frame.
; ------------------------------------------------------------------------------
; ------------------------------------------------------------------------------
; BuildColupF — MOVED to bank2 (S5.1) — CallPad_BuildColupF.
;   Hot-rect data (RoomRects) lives in bank2, so the body reads it with
;   direct (FetchPtr),Y — the shared $FEF6 fold block's sta $1FF6 always
;   returns to bank0, so a fold inside a bank1 body could not work.
;   The dark check is inlined there too: CallPad_IsRoomDark cannot nest
;   from a pad body (ReturnPad switches to bank0 mid-call).
;   Body: bank2.asm, pinned at $FC4F. Entry save block ($F0-$F2 → collision
;   temps) was dead (rows 0-2 only) — deleted with the .AfterRows restore
;   in S3.0b.
; ------------------------------------------------------------------------------

; UpdateBombSound moved to bank1 (leaf_move_plan batch A) — CallPad_UpdateBombSound.

; ------------------------------------------------------------------------------
; ColOff/ColMask — cell-walk lookup tables (cell_collision_plan).
;   Indexed by LEFT-HALF source col 0-19 (PHM prologue mirrors right-half
;   ranges before the walk; bank2 display-space walkers mirror first too).
;   ColOff: byte offset from PF0Buf+row ($C3+row) to the register holding
;   that col (0/3/6 = PF0/PF1/PF2 row byte). ColMask: the col's bit in that
;   byte — PF0 bit4+col (cols 0-3), PF1 MSB-first (4-11), PF2 LSB-first
;   (12-19); matches convert_room.pf_values (plan 0.2 spec, proven by
;   tools/test_cell_map.py).
;   (The standalone CellSolid leaf that lived here moved INTO
;   PlayerHitsMap's walk as inline code — a jsr in the walk cost 2B of
;   stack depth and would break sim_bomb_fuse's gameplay min-SP >= $F8
;   guard; the post-pad slot keeps these tables abs,X-reachable.)
; ------------------------------------------------------------------------------
ColOff:     .byte 0,0,0,0, 3,3,3,3,3,3,3,3, 6,6,6,6,6,6,6,6
ColMask:    .byte $10,$20,$40,$80,$80,$40,$20,$10,$08,$04,$02,$01
            .byte $01,$02,$04,$08,$10,$20,$40,$80

    .ds $FE10 - *, 0            ; keep ObjSprites in $FE page (lda ObjSprites,X
                                 ; must not cross a page — 5c vs 4c kernel budget)

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
; E4 moth entry tramp ($FEF0-$FEF5) — byte-identical with bank2's copy
; (guard: verify_build check_moth_tramp). bank0 executes `sta $1FF8`; the next
; fetch ($FEF3) comes from bank2 = `jmp MothRoutine`. Neither bank runs its
; other half: bank0 is switched away at $FEF2, bank2 is never entered here.
; The 6-byte pad is the only free hole before FoldIndirect's pinned $FEF6.
; ------------------------------------------------------------------------------
    .ds $FE80 - *, 0            ; S5.3 HOF entry tramp (byte-identical w/ bank2,
                                ; guard: check_moth_tramp — pad window full)
HotOverlapFlag:
    sta $1FF8                   ; select bank2
    jmp $FCF0                   ; bank2 HotOverlapBody (dead in bank0; guard
                                ;   pins bank0/bank2 operands == bank2 label)
    .ds $FE86 - *, 0            ; S5.4 LHT entry tramp (byte-identical w/ bank2,
                                ; guard: check_moth_tramp — same pattern)
LaserHitTest:
    sta $1FF8                   ; select bank2
    jmp $FF00                   ; bank2 LaserHitTestBody (dead in bank0; guard
                                ;   pins operands == bank2.lst label)
    .ds $FEF0 - *, 0            ; fill tramp..moth gap (drift-proof)
UE_MothTramp:
    sta $1FF8                   ; select bank2
    jmp $F100                   ; bank2 MothRoutine (dead in bank0; guard pins
                                ;   bank0/bank2 operands == bank2.lst label)
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
; S6 (docs/laser_s6_log.md): stages the sweep-path column bounds
; (CollisionEndX..CollisionCellX) and reloads CollisionX after
; LaserHitTest — bank2's LaserWallClamp pulls it back to the first wall
; ON the path so the drawn M0 and the kill window share ONE value.
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
    ldx LaserState             ; X = old state (b7 held, b6 prev, b1-0 phase,
                               ;     b5-2 dark rooms 4-7)
    txa
    and #LASER_DARK            ; keep dark bits (else this store wipes them)
    sta LaserState
    txa
    and #LASER_HELD
    lsr                         ; old held (b7) -> new prev (b6)
    ora LaserState              ; stage prev (phase/held written back below)
    sta LaserState
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
    ; --- S6b: sweep-path column bounds for LaserWallClamp (runs first thing
    ; inside the LHT body). PIXEL MODEL (calibrated: PHM lit-left = arg-7,
    ; PlayerSpriteA art cols0-6): SetObjectXPos arg A -> drawn M0 = [A-7, A];
    ; nose (art face col4/col3) = RoomX-3 / RoomX-4. Path anchors the SPRITE
    ; nose, not the raw tip, so a bar that teleported past the wall (max
    ; approach: eye col > wall col) still finds it. cols = px>>2:
    ;   right: [nose_R, A]   left: [A-7, nose_L]
    ; LWC pulls CollisionX so the drawn tip/start lands 2px INSIDE the first
    ; wall; kill test uses the SAME [A-7, A] (S6 lock; NO NUSIZ/width change:
    ; that rewrite is the e24d9de rollback).
    lda PlayerDir
    beq .LWpR
    lda CollisionX              ; left: c0 = drawn-left = A-7
    sec
    sbc #7
    bcs .LWpLz
    lda #0                      ; A < 7: floor at screen left
.LWpLz:
    lsr
    lsr
    sta CollisionEndX
    lda RoomX                   ; left: c1 = nose_L = RoomX-4
    sec
    sbc #4
    jmp .LWpC
.LWpR:
    lda RoomX                   ; right: c0 = nose_R = RoomX-3
    sec
    sbc #3
    lsr
    lsr
    sta CollisionEndX
    lda CollisionX              ; right: c1 = drawn tip = A (raw, A <= 159)
.LWpC:
    lsr
    lsr
    sta CollisionCellX          ; path last col
    ; S5.4: body moved to bank2 (pads cannot nest from a pad body — the
    ; kill/lamp ACTIONS return here: A=0 miss / $50 kill / 1 lamp).
    jsr LaserHitTest            ; S4: swept kill — result in A (+Z via ReturnPad)
    pha                         ; S6: save result across positioning
    lda CollisionX              ; S6: CLAMPED by LaserWallClamp (mid-wall tip)
    ldx #2                      ; selector 2: RESP0+2=RESM0, HMP0+2=HMM0
    jsr SetObjectXPos           ; drawn M0 = [CollisionX-7, CollisionX] (S6b)
    pla                         ; restore result (PLA sets Z from the value)
    beq .LaserNoHit
    cmp #$50
    beq .LaserKill
    jsr CallPad_SetRoomDark     ; lamp crash = player-body touch (no kill, no score)
    rts
.LaserKill:
    jsr CallPad_AddScore        ; A = $50 BCD (dead bit already set in body)
.LaserNoHit:
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
; LaserHitTest — MOVED to bank2 (S5.4, entry tramp $FE86 -> `jmp $FF00`).
;   Fold-free: enemy records are level data in bank2 (direct (FetchPtr),Y),
;   and the kill/lamp ACTIONS cannot run from a bank2 body (CallPads are
;   bank0->bank1 only — pads cannot nest from a pad body). Body returns a
;   RESULT CODE in A (+Z preserved through ReturnPad's sta/rts): 0 = miss,
;   #$50 = kill (dead bit already set), 1 = lamp. LaserInput's tail does
;   `beq / cmp #$50 / jsr CallPad_SetRoomDark | jsr CallPad_AddScore`.
;   One less push level too (no fold / no pad call inside the body).
;   Full behavior docs moved with the body.
; ------------------------------------------------------------------------------

; ==============================================================================
; Interrupt vectors ($FFF2-$FFF9 = fill — NEVER put code here: $FFF6-$FFF9
; decode as F6 hotspot mirrors on peek (see MothExitPad comment at $FC49))
; ==============================================================================
; ==============================================================================
    .ds $FFFA - *, 0               ; pad to vectors at $FFFA

    .word GameStart                 ; NMI vector
    .word GameStart                 ; RESET vector
    .word GameStart                 ; IRQ vector
