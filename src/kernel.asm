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
LaserX          byte            ; travelling beam X, M0 arg 0-159 (contact
                                ; missile: +4px/frame from the eye toward
                                ; facing; resets on contact/offscreen/release;
                                ; was LaserBeamOn $02 gate — gate moved to
                                ; LaserState b1 so this byte could hold state)
LineCount       byte            ; scanlines remaining in current tile row
BombY           byte            ; bomb drop Y (was dead TileRow; scanline snapshot)
Grp0Ptr         byte            ; pointer to player sprite data (lo)
Grp0PtrHi       byte            ; pointer to player sprite data (hi)
Temp            byte            ; general scratch

; Collision ZP variables (from comparison/lo-a-rad-dragon/bank0.asm)
ZPSpare89       byte            ; $89 FREE (was RcBase, the rect-cache count,
                                ; retired by plan C4 2026-10-20: every walker
                                ; is cell-based). Kept allocated so the
                                ; sequential block does not shift.
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
; RoomPF1/RoomPF2 pointers were DEAD (2026-10-16, D1.1): every reader
; indexes (RoomPF0Lo),Y across the 3 contiguous PF rows (TilePF0/1/2 are
; emitted 3 rows apart), so no separate PF1/PF2 pointer is ever used.
; Reclaimed as a free ZP pool for new features (addresses stay stable so
; bank1/bank2 hand-copies do not shift).
BarIdx          byte            ; ($9B) bar table idx (BarLevel+7)>>3 (D2 sync)
Hover           byte            ; ($9C) respawn hover flag (bugs.md #1): 1 while
                                ;       gravity is suppressed after a respawn
MelPtr          byte            ; ($9D) intro music: melody stream index (bank1)
MelTimer        byte            ; ($9E) intro music: melody frames left
LevelPFDataLo   byte            ; pointer to the level's RoomShapes column (low)
LevelPFDataHi   byte            ; pointer to the level's RoomShapes column (high)
LevelRoomN      byte            ; rooms in this level (C4 2026-10-20, C2 3 B
                                ;   record): the RoomPositions / RoomCounts /
                                ;   enemy-record bases are its +n / +2n / +3n
LevelConnSpare  byte            ; C1 2026-10-20: exit-scan target byte in
                                ;   bank2 (was LevelConnHi — its pointer is
                                ;   derived; the byte stays allocated so the
                                ;   hand-copied ZP blocks do not shift)

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
RoomM1Hot       byte            ; C11 2026-10-21: hot-band M1 block cell =
                                ;   col+1 (0 = none), staged by bank3's
                                ;   ExtrasLoad from the room's patch list (was
                                ;   LevelEnemyLo; the RoomCounts base is
                                ;   now base+2n, derived in EnterRoomB2 — the
                                ;   byte stays allocated so ZP does not shift)
LevelEnemySpare2 byte           ; free (was LevelEnemyHi)
EnemyDataLo     byte            ; pointer to current room enemy data (low)
EnemyDataHi     byte            ; pointer to current room enemy data (high)
EnemyCount      byte            ; number of enemies in current room
FlickerFrame    byte            ; GRP1 slot index for flicker
BombPacked      byte            ; bomb state at $B5 (was ephemeral ObjectCount):
                                ;   b0-1 state 0=none,1=fuse,2=explode
                                ;   b2 DownPrev edge, b3-6 WallMask, b7 OnGround
ObjBase1        = $EA               ; Phase 5 slot-1 staging: sprite base
ObjTop1         = $EB               ;   ($FF = none), ObjTop (RoomY-relative)
ObjX1           = $EC               ;   and object X. Bank1's HUD owns these
                                ;   three bytes ($EA/$EB = scorePtr6, $EC =
                                ;   scbrdCnt) but rebuilds them AFTER the cave
                                ;   read, so the VBL write -> cave read window
                                ;   is safe (ZP doc rule 6). Staged every VBL by
                                ;   StageSlot1, consumed by Slot1Hook.
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
PlayerBombs     = $F0           ; bombs left in b2-0 (0..5; readers mask, see
                                ; below). b7 = bank1 RaftBody's "ridden last
                                ; frame" flag, b6-b3 = its take-off ramp level
                                ; (0-15) — the raft's inertia state lives here
                                ; because the ZP map has no free byte (AGENTS).
                                ; Contract: only the raft writes b7-3; the bomb
                                ; code touches b2-0 (its `dec` is guarded by a
                                ; nonzero count, so it cannot borrow upward);
                                ; LoadLevel/ReloadLevel write the whole byte,
                                ; which merely resets the ramp. Every reader of
                                ; the COUNT masks with #%00000111.
BOMBS_MAX       = 5             ; starting / reload bomb count
BombSnd         = $F1           ; frames of bomb audio left (0=silent; bank1 must not write)
LevelShowTimer  = $F2           ; #18 frames left of the LV001 HUD banner (bank1 decs;
                                 ;  ALIAS of TallyTicks — lifetimes are disjoint: banner
                                 ;  = gameplay entry (LoadLevel, DropTarget != $FD),
                                 ;  tally = level-exit bonus, intro phase = boot only)
LV_SHOW_FRAMES  = 120           ; banner duration (2s at 60Hz)
TallyTicks = $F2               ; level-bonus countdown, 50-pt units (tally)
; (was RoomWallMask $F2 — D1-B, plan 5.2: no cross-room hole state)

; Score ZP variables (shared with bank1 HUD — addresses MUST match bank1)
; $F3-$F5 live score only — $F6 is BombX (bank1 ScoreOn is unused).
ScoreTh         = $F3           ; score thousands digit (0-9)
ScoreHu         = $F4           ; score hundreds digit (0-9)
ScoreTe         = $F5           ; score tens digit (0-9)
; PF0ScoreBuf/PF1ScoreBuf removed (S3.0): dead legacy EQUs — the 48px
; sprite score never used PF score buffers (decl-only, zero references).

; Rect cache RETIRED (plan C4 / cell_collision_plan 7.1, 2026-10-20).
; The solid rect list is no longer emitted and no walker reads a cache:
; PlayerHitsMap, LaserWallClamp, the moth walk and BombMarkWalls all test
; PF cells. $CC-$DF are FREE (20 B, the "option A" ZP reclaim); $89 stays
; allocated as ZPSpare89 so the sequential block above does not shift.
; History worth keeping: the cache lived at $CC-$DF because bank1's HUD
; writes $E0-$EF every frame — rect4.h on $E0 was zeroed by scorePtr1 and
; probes walked through rect4 walls (the $E0 stomp-zone rule still applies
; to every persistent byte).
; Buffers packed: PF0 $C3-$C5, PF1 $C6-$C8, PF2 $C9-$CB (rows 0-2 only).
; ($E0/$E1 are spare/stomp-zone — never persistent bank0 state.)

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
BandTab         = $ED           ; Phase 3 asym ball: staged Band0/1/2
                                ; ($ff = ball band, $00 = mirror). Written
                                ; by bank2 StageBandTab (BuildColupF tail,
                                ; every VBL) BEFORE this frame's cave; read
                                ; by .Row's ENABL gate; bank1 HUD stomps
                                ; $ED-$EF (scbrdTmp etc.) only AFTER the
                                ; cave read — staged-only window, like
                                ; FetchPtr. Next VBL restages.
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
LaserState      = $C0           ; laser: b7 fire held this frame,
                                ;   b6 fire held last frame (press-edge),
                                ;   b5-2 RoomDarkMask rooms 4-7,
                                ;   b1 beam gate for the kernel .Line
                                ;     (PlayerColTable bit1 on the beam row shares b1; mirror of b7)
EnemyRamD       = $C1           ; dir bits 0-3 = enemy 0-3 (1=right, 0=left)
EnemyRamP       = $C2           ; bits0-3 moth phase (shared/sync); bits4-7
                                ;   vdir for spider/bat/tentacle (1=down)
EnemyRamY       = $E2           ; 3 bytes: live Y per enemy ($E2-$E4) —
                                ;   private since S3.4; see contract above

; ==============================================================================
; Constants
; ==============================================================================
PLAYER_HEIGHT   = 12            ; GRP1 object (enemy/miner) height AND hit box
                                ;   (Phase 6 tall art 2026-10-22); player uses
                                ;   PLAYER_SPRITE_H
PLAYER_SPRITE_H = 12            ; player sprite height in scanlines (8x12)
PLAYER_WIDTH    = 7             ; lit player sprite spans 7 pixels; REFP0 shift handled
ENEMY_WIDTH     = 8             ; snake GRP1 width ($ff = 8 px) — flush-out span
LAMP_WIDTH      = 4             ; OBJ_LAMP uses GRP1's leftmost 4 lit pixels
MINER_WIDTH     = 4             ; OBJ_MINER spans 4 lit GRP1 pixels
SNAKE_PATROL    = 4             ; ONE TILE each side of the spawn (user
                                ; 2026-10-19): the patrol is SYMMETRIC about the
                                ; placed X, so the snake retreats a tile behind
                                ; its placement and then comes out a tile — 2
                                ; tiles of travel total. The editor cannot ask
                                ; the user to place it 2 tiles from the border.
TILE_COLUMNS    = 20            ; columns per half (reflected playfield)
TILE_ROWS       = 3             ; number of playable color bands
LINES_PER_TILE  = 48            ; scanlines per tile row
HUD_ROWS        = 1             ; HUD band (48 scanlines)
CAVE_LINES      = 144           ; TILE_ROWS × LINES_PER_TILE
VISIBLE_LINES   = 192           ; CAVE_LINES + (HUD_ROWS × LINES_PER_TILE)

; GRP1 sprite design offsets into ObjSprites (12 bytes each; 0 = blank/off)
OBJ_NONE        = 0
OBJ_KEY         = 0     ; type-6 KEY design = the offset-0 slot
OBJ_MOTH        = 12
OBJ_SPIDER      = 24
OBJ_LAMP        = 36
OBJ_TENTACLE    = 48
OBJ_BAT         = 60
OBJ_SNAKE       = 72
OBJ_MINER       = 84
OBJ_BOMB        = 96

; Player bounds (must stay inside cave walls)
PLAYER_MIN_X    = 4             ; sprite flush with left edge (HERO)
PLAYER_MAX_X    = 159           ; horizontal logical-position clamp
PLAYER_MIN_Y    = 0
PLAYER_MAX_Y    = 132           ; CAVE_LINES - PLAYER_SPRITE_H

; Jetpack physics constants (HERO-style)
GRAVITY         = $0008         ; gravity per frame (signed 16-bit, + = down)
JET_MAX         = $14           ; max jet thrust accumulator = 20. With the
                                ; ÷4 ramp gate below: full thrust at 80f,
                                ; net lift (vy=0) at exactly 60f = 1.0s
                                ; spin-up (bugs.md #31); was $20 (÷1 ramp:
                                ; lift after 0.25s — too snappy).
MAX_FALL        = $0180         ; max fall speed (positive = down). Was $0200
                                ; (2.0 px/frame) — the terminal fall felt too
                                ; fast (user report 2026-10-21): 1.5 px/frame.

JET_AUD_BASE    = $0F           ; engine AUDF base: freq = base - JetPower/8 - sputter
JET_AUD_VOL     = $08           ; engine volume while Up is held
LASER_AUD_C     = 2             ; laser ch0 control: div-15 tone = low pitch
LASER_AUD_V     = 9             ; laser ch0 volume while fire held



; Facing direction of the player sprite's eye
FACING_RIGHT    = 0
FACING_LEFT     = 1

; LaserState bits
LASER_HELD      = %10000000     ; b7: fire held this frame (INPT4 D7=0)
LASER_ARMED     = %00000010     ; b1: kernel .Line beam gate — ENAM0 =
                                ;   (PlayerColTable bit1) & b1, so the beam
                                ;   row is the table's bit1 row (index 2)
LASER_ON        = %10000010     ; b7+b1 in one ora (held AND armed)
LASER_DARK      = %00111100     ; b5-2: RoomDarkMask rooms 4-7 (IsRoomDark/SetRoomDark)
LASER_REARM     = %00000001     ; b0: contact consumed last frame — next held
                                ;   frame re-tests the eye instead of stepping
                                ;   (flush hold: eye mid-tile, +4 would jump
                                ;   out with no candidate ever inside the wall)
LASER_KEEP      = %00111101     ; dark|rearm: prologue store preserving b0

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
COLOR_TITLE     = $6A           ; hue 6 luma 5 = purple (title text)

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
                                    ;  $F190 Overscan (bank1 stub literal tracks it —
                                    ;  fold-pad byte guard fires when it moves)
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
    ; --- Merged title: DropTarget=$FF (2026-10-19). The CAVE kernel renders
    ;     the stage (room 0 + player + HUD whose score shows level+1); a band
    ;     hook overlays the SAVIOR logo and the credits, and the theme plays.
    ;     SELECT cycles the level, RESET starts the game. Valid fall targets
    ;     are Y ≤ 191; sentinels $FF/$FE are "not a fall". ---
    lda #$FF
    sta DropTarget

    ; --- Load first level (the title previews it on the live stage:
    ;     LoadLevel leaves the player at the level start, no flight) ---
    jsr LoadLevel

    ; --- Set player color ---
    lda #COLOR_PLAYER
    sta COLUP0

    ; --- Set playfield to reflected mode + priority ---
    ; D0=1 = reflect (left half mirrors to right)
    ; D2=1 = playfield priority (player drawn BEHIND walls, like HERO)
    ; D5-D4=%11 = 8-clock ball (D6 overlay mask; Phase 2 — ball stays
    ; disabled at kernel entry, size only matters once Phase 3 enables it)
    lda #$35                      ; CTRLPF: reflect + priority + ball 8 clk
    sta CTRLPF

; ==============================================================================
; Frame loop
; ==============================================================================
StartFrame:

; ------------------------------------------------------------------------------
; VSYNC (3 scanlines)
; ------------------------------------------------------------------------------
; FIX (bugs.md #29 Class C): the OLD block started with `sta VSYNC` immediately
; at frame entry, so the CPU was still inside the 76-cycle HBLANK when it
; wrote VSYNC=$02 and the first `sta WSYNC`. A WSYNC that lands inside HBLANK
; does not advance the wall clock to the next scanline boundary (it is already
; there), so the VSYNC pulse was 2 lines instead of 3 on ~30% of frames (the
; fraction depends on where the previous frame's overscan happened to end) —
; the whole screen shifted up 1 scanline on those frames = the jitter.
;
; FIX: re-anchor first with an unconditional `sta WSYNC`. This always stalls to
; the next scanline boundary (even if we were already at it — the store is 3c
; past the HBLANK start so it always advances). THEN the 3 WSYNCs are a clean,
; deterministic 3-scanline VSYNC pulse. Costs 1 scanline/frame (262 -> 263);
; the sim wall-model target is updated to match.
    sta WSYNC                   ; re-anchor to scanline boundary (always stalls)
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
    ; A1 2026-10-20: SelectActiveObject is back in bank0 (C1 reverted), so the
    ; per-object FoldIndirect + CallPad_IsRoomDark cost is back: +46c on EVERY
    ; measured worst frame (sim_frame_budget: default 1013->1059c, FLY=Y
    ; 1078->1124c, FLY=X 1052->1098c, FLY=M 1051->1097c; wall model unchanged).
    ; Worst 1059c of the 1472c window = 413c margin.
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

    ; --- D6/D7 ball staging MOVED after .BgStore (Phase 3): the meta block
    ; lives in bank2's models_data — a bank0 (RoomPF0Lo) read fetched bank0's
    ; $F9xx zero pad (flag always 0). bank2 StageBandTab (BuildColupF tail)
    ; now stages BallX into Temp; this block reads the staged copy. ---

    ; --- No sprite copy needed — kernel reads directly from ROM ---
    ; Do NOT HMOVE here: wait until P1 is positioned too. An early HMOVE
    ; applied stale bank1 HMP1 (score), and a second HMOVE after SelectActiveObject
    ; applied HMP0 twice → player fine-adjust doubled (visual teleport/jitter).

    ; --- Select which object GRP1 draws this frame (miner or enemy) ---
    ; Reads EnemyRamY ($E2) — no VBL writer of $E2 exists (Y writers are
    ; overscan-only, score ptrs are HUD-only), so no ordering constraint.
    ; A1 2026-10-20: body back in bank0 (was C1's bank2 copy) — the enemy
    ; records are level data in bank2/bank3, so the type byte is fetched
    ; through FoldIndirect again (~46c/frame more than the bank2 copy).
    jsr SelectActiveObject

    ; --- PF0: NO per-frame refresh since S3.4 — EnemyRamY moved to $E2-$E4,
    ; so $C3-$C5 keep the EnterRoom pattern forever (the old LoadPF0Only
    ; repair = 3 folds ≈ 130c/frame is deleted). PF1/PF2 rows 0-2 likewise
    ; have no per-frame writer; full 9-fold rebuild only on EnterRoom.
    ; Plan 5.1: the S6.1 every-frame ApplyBombWalls re-apply is GONE —
    ; BombMarkWalls punches holes once at the fuse 1->2 edge.
    jsr CallPad_BuildColupF    ; stripe+hot COLUPF bytes into ColupfBuf ($E7-$F2)

    ; --- Band color: RoomBandColor ($BC) is staged ONCE per room by
    ; EnterRoomB2 (C2 2026-10-20: b6 of the room's RoomShapes byte; the
    ; 2026-10-04 up-exit fix). The
    ; old per-frame VBL fold that re-read the same ROM byte is
    ; REDUNDANT since then and is deleted (2026-10-19): it saved nothing the
    ; kernel needs, cost ~30c of VBL time, and it was a level-data read in
    ; the VBL path (the read that made a bank3 data move need another
    ; reader). test_band_restage covers the contract.

    ; --- Cave COLUBK for this frame → written DIRECTLY (Phase 3) ---
    ; state=2: blink (60-BombTimer)&3 → black/yellow/red/yellow; else COLOR_CAVE_BG
    ; Dark room: black except the existing explosion blink (state=2).
    ; Phase 3: .Row no longer re-stores Temp→COLUBK per band (the slot now
    ; holds the BandTab ENABL gate), so this store IS the cave's COLUBK.
    ; Temp is free here onward for the staged BallX (bank2 StageBandTab) —
    ; no reader between this point and overscan's own `sta Temp` (joystick).
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
    sta COLUBK

    ; --- D6 objects (asym ball + M1): ONE VBL call (pre-pad = 1B headroom) ---
    ; PositionBallM1 (fill hole at $F9C4, bank0-only) reads Temp (staged
    ; BallX; 0 ⇔ symmetric → no RESPBL/HMBL, sym frames bit-identical) and
    ; CollisionEndX (staged M1X; 0 → no M1) — ball selector 4, M1 selector 3,
    ; ENAM1 latched on when M1X≠0. Runs before the single HMOVE below
    ; (HMP0+X shadow registers accumulate). Per-band ENABL comes from BandTab
    ; at each .Row setup line; .AfterRows clears ENABL+ENAM1 before the HUD.
    jsr PositionBallM1

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

    ; --- Sprite frame: jet flutter / ground walk cycle (leaf at $FDFx pad) ---
    jsr PickPlayerFrame

    ; --- Cave TIA restores inside the VBL window (moved 2026-10-06) ---
    ; Was inline between VBL-tail and .Row: making it a jsr'd KernelInit
    ; added ~19c + an entry WSYNC to the cycle-precise VBL-tail→.Row span
    ; → wall 263→264 every frame. Inits live HERE (window headroom
    ; 1472-1076 ≈ 396c, cost ~25c) so the entry span SHRINKS vs inline.
    ; HUD cannot clobber these: HUD runs AFTER the kernel each frame.
    lda #$30                      ; NUSIZ0 = single copy P0 + M0 width 8
    sta NUSIZ0
    ; NUSIZ1 + CTRLPF restores DELETED (P2b): bank2 StageBandTab owns both
    ; every VBL (door drives M1 4clk / ball 4clk). TitleKernel re-establishes
    ; its own NUSIZ1 (:2595/:2683/:2695) per frame.
    lda #COLOR_PLAYER             ; restore player color (HUD had it green)
    sta COLUP0
    lda #0                        ; clear VDELP0/VDELP1 (HUD sets them to 1)
    sta VDELP0
    sta VDELP1
    sta ENABL                     ; HUD-bar leftover off before first visible
                                  ;   line (.Row row0 BandTab rewrites next)

    ; --- Wait for VBLANK timer ---
.WaitVBLANK:
    lda INTIM
    bne .WaitVBLANK

    ; --- Kernel-entry re-anchor (bugs.md #29 Class C, 2026-10-11) ---
    ; TIM64T expires on a 64-cycle tick, the poll exits up to 63c late, and
    ; the band-0 .Row setup WSYNC gap is ~75c — so the kernel start line
    ; oscillated ±1 with the tick phase (measured: first .Line WSYNC at scn
    ; 20 on 100 frames, scn 21 on 51 frames under bomb/thrust input = the
    ; whole-screen jitter, HUD seam flipping rows 144/194). The re-anchor
    ; below (VBLANK still on = blank line) absorbs the quantization: the
    ; kernel + HUD are now WSYNC-line-locked every frame. +1 line/frame
    ; (blank, invisible); wall-model target moves 264 -> 265.
    sta WSYNC

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

    ; --- Kernel entry: title/cave dispatch (TIA inits live in VBL tail) ---
    jsr KernelInit

CaveKernelRow:
.Row:
    ; --- Set PF registers for this tile row (TIA persists) ---
    ; Store ORDER is cycle-critical (thin-yellow-line fix, 2026-10-01): the
    ; stores land mid-visible (advance block then these pairs), so on the
    ; row1→row2 band-transition line the left half must keep the OLD band's
    ; PF+color while the right half may show the NEW band. Write cycles
    ; (cN = CPU cycles on the setup line, x = pixel at 4x, HBLANK ends c22.7):
    ;   PF0 w c34 x136 | PF1 w c41 x222 | COLUPF w c48 x296 |
    ;   COLUP1 w c51 x332 (D6 M1 band color — AFTER the left half, so the
    ;     transition line keeps the OLD band's M1/P1 color on the left, same
    ;     rule as COLUPF) |
    ;   ENABL w c58 (BandTab gate, +1c vs the old COLUBK pair) |
    ;   PF2 w c65 x500 (moved +3c — still past right-half PF2 pixels x449)
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
    sta Temp                      ; A1 (line-budget plan): stage band color
                                  ; for .ObjZero's A==8 restore (moved up —
                                  ; same A; Temp has no other kernel reader)
    lda CollisionCellY            ; P2b door color staged by bank2 VBL:
                                  ; $80 = no door / $1C = yellow stripe
    bmi .M1band
    sta COLUP1                    ; door: yellow (only visible on the door's
                                  ;   open bands — wall PF hides it elsewhere)
    sta Temp                      ; bugs.md #15: also stage the door color into
                                  ;   Temp, so .ObjZero's plain restore keeps
                                  ;   the stripe yellow (0 extra cycles on the
                                  ;   object line; +3c here on the setup line)
    bpl .M1done                   ; $1C b7=0 → always
.M1band:
    lda ColupfBuf,X
    sta COLUP1                    ; D6: M1 band color (left-col block) — P1
                                  ; inherits it until .Line's object path
.M1done:

    ; --- Per-band ball gate (Phase 3): BandTab[row] $ff/$00 → ENABL ---
    ; Takes the slot of the per-band `lda Temp / sta COLUBK` (VBL writes
    ; COLUBK once now) — same position, +1c (7c gate vs 6c pair), PF2 shifts
    ; c61→c62 (later = right half keeps OLD band even longer, thin-yellow fix
    ; intact). TIA latches ENABL per line: set on this setup line → ball on
    ; from the band's first body line; water + HUD inherit row2's value
    ; (.AfterRows clears ENABL before the HUD band; the HUD bar enables
    ; its own ball).
    lda BandTab,X
    sta ENABL
    lda PF2Buf,X
    sta PF2
    ; --- Phase 5: is the second GRP1 object in THIS band? ---------------
    ; Sits in the setup window's free tail (~59c after PF2, before the WSYNC
    ; that ends the pass, so the phased stores above never move). The early
    ; out costs 5c; Slot1Hook pays 2 extra lines ONLY on the band that hosts
    ; slot 1 (SetObjectXPos WSYNC line + the HMOVE line).
    lda ObjBase1
    bmi .RowNoSlot1
    jsr Slot1Hook
.RowNoSlot1:
    ; (2026-10-15) GRP0 blank REMOVED: +5c pushed the rows0/1 setup
    ; segment to 75c armed (>=74 = write lands next line = +1 stall line
    ; = whole-screen shift). The blank only traded a stale-byte duplicate
    ; for a blank line at band boundaries — shipped pre-99b8e86 without
    ; either; case15 filters zero writes so the Y-align guard is unaffected.
    ; --- Scanlines this pass: rows 0/1 = 48; row 2 = 36+off (tide, CollisionX).
    ; The bottom water strip (last 12-off lines, bottom_band_plan rule 2)
    ; renders in .WaterRow after this pass — its own setup line + (11-off)
    ; bodies keeps the row-2 total at 49 lines (setup+48) exactly.
    ; Split tail (2026-10-05, row1 setup gap 77->74): row1 gate used to pay
    ; `bne` 3c to skip the tide load AND share the WSYNC — gap was 77 (stall,
    ; +1 line/frame). Rows 0/1 now store+WSYNC before the tide block, then
    ; jmp over it (+3c charged to the FIRST body line = 66max+3jmp+3WSYNC
    ; = 72 <=76). Row2 path byte-identical in cost (cpx/beqT/lda/sta/WSYNC
    ; = 11+3 = 76, zero margin — the `beq` target is 9 bytes ahead, same
    ; page, T=3c; do not let this block grow toward a page edge).
    ; A1 gap fix (2026-10-05): `sta Temp` (+3c in .Row) pushed gaps to
    ; 77/79 = stall EVERY frame (265-line frames). `sta LineCount` moved
    ; AFTER `sta WSYNC` — same bytes, -3c from the gap window, +3c to the
    ; first body line (66max+3LC[+3jmp]+3WSYNC = 75 rows0/1, 72 row2).
    ; LineCount is not read until the line's `dec` tail — the early store
    ; was never required; keep the store strictly between WSYNC and .Line.
    cpx #TILE_ROWS-1
    beq .RowLinesTide        ; row 2: tide count (36+off) from CollisionX
    ; rows 0/1: fixed 48 lines (the vcrunch shutter slice derive is gone).
    lda #48
    ; --- Sync to next scanline (rows 0/1) ---
    sta WSYNC
    sta LineCount
    jmp .Line
.RowLinesTide:
    lda CollisionX           ; 36..39 — VBL tide calc (see VBL comment)
    ; --- Sync to next scanline (row 2; falls straight into .Line) ---
    sta WSYNC
    sta LineCount

.Line:
    ; --- Player sprite: color for THIS line, graphics byte for NEXT line ---
    ; GRP0 written on line S displays on line S+1 (latched at the sprite's
    ; window start after the write) — index graphics with A0+1 ($ff wraps
    ; to 0 = row0 on the line before the sprite).
    ; Running-Y: Y = A0 = Scanline - RoomY is computed ONCE at kernel entry
    ; (sec/sbc RoomY/tay); .Line's iny advances it (Y = A0+1 after the
    ; graphics write = A0 of the next line). Nothing between rows may touch
    ; Y — the water-strip band-color read is an inlined `lda` (Y untouched).
    ; Cycle budget — MEASURED (sim_frame_budget, bugs.md #29 Class A):
    ; the old worst path (in-window color/beam/GRP0 + object in-range) was
    ; 78c: WSYNC write landed 2c into the next line -> full-line stall ->
    ; +1 scanline on every frame whose object window overlapped the A0=11
    ; line (24 stalls in the SIM_LEVEL=2 window, always even frames —
    ; SelectActiveObject parity rotation). Root fix: the color/beam gate
    ; below stops at A0=10; row 11 inherits row 10's COLUP0/ENAM0 writes
    ; (PlayerColTable [10]==[11], verify_build asserts) because
    ; GRP0 row11 is fetched on line A0=10 already ("row11 shows via
    ; line10"). Worst path measured 2026-10-15 (vcrunch jitter hunt):
    ; in-window color/beam/GRP0 + object in-range = 69c between WSs,
    ; start-to-start d=72 — was 73/76 (= stall zone 74-76, whole-screen
    ; +1-line jitter) until the dead `cpy #12 / bcs .GrpZero` (4c, never
    ; taken on the A0<=10 color path) moved to .GrpSkip. Budget: work
    ; <= 70c / d <= 73 — a 74-76 segment stalls a full scanline.
    ; ObjSprites+107 must stay in ONE page (else lda ObjSprites,X
    ; page-crosses, +1c on the GRP1 fetch) — verify_build enforces this.
    ; Branch targets all same-page (3c taken) and PlayerColTable in $F8xx
    ; (verify_build guards the A0=10 page-cross budget).
    ; GRP1 object section clobbers X (ObjSprites index) — row counter lives in
    ; RowIdx and X is reloaded after bne. Row-advance +6c on the .Row setup
    ; scanline (segment 63c -> 69c <= 76c): frame length unchanged.
    ; The old Scanline/sec/sbc/tay prefix cost 10c more (body 66c -> WSYNC
    ; write on cycle 76 = one cycle late): WSYNC stalled a full line per
    ; overlapping scanline — stretched cave row, HUD pushed down, and with
    ; GRP1 flicker rotation the frame length alternated (one-tile oscillation).
    ; Keep the hot path at <= 70c work: an overrun duplicates the scanline.
    cpy #PLAYER_SPRITE_H - 1
    bcs .GrpSkip                ; A0 >= 11 (incl $ff): no color/beam this line.
                                ; A0=11 skips too (Class-A stall line): rows
                                ; 10/11 share color+beam bytes, so row 10's
                                ; writes are still in effect here.
    ; --- Laser S2.2: ENAM0 = PlayerColTable bit1 & LaserState.b1 ----------
    ; Phase 0 (2026-10-21): the retired BeamMask table duplicated bit 1 of
    ; PlayerColTable for a separate 4c fetch. One yellow strip on RoomY+2
    ; only (user directive 2026-10-08: the red row-3 strip is gone; the kill
    ; window in LaserHitTestBody keeps rows RoomY+2..3 = superset of the
    ; draw). In-window path only (Y<=11), so outside the window ENAM0 keeps
    ; its last write ($00 at A0=10) — no HUD artifact. verify_build asserts
    ; bit1 is set at index 2 and nowhere else, and that rows 10/11 stay equal
    ; (the A0=11 gate skip inherits row 10's writes).
    lda PlayerColTable,Y        ; 4c — per-row color; bit 1 = ENAM0 enable
    sta COLUP0                  ; applies to this line (colour bit0 = don't-care)
    and LaserState              ; 3c — beam gate: b1 armed only while fire held
    sta ENAM0                   ; 3c (bar showed without fire before this)
    iny                         ; Y = A0+1 ($ff wraps to 0 = sprite row 0).
                                ;   Color/beam gate entered only with A0<=10
                                ;   -> after iny Y<=11: always fetchable, so
                                ;   the old `cpy #PLAYER_SPRITE_H / bcs
                                ;   .GrpZero` here was DEAD 4c on the worst
                                ;   path (2+2, never taken — A0=11+ never
                                ;   reaches it, it goes to bcs .GrpSkip).
    lda (Grp0Ptr),Y             ; 5c — byte for the NEXT scanline
    sta GRP0
.Grp1:

    ; --- GRP1 SECOND (object/enemy sprite): one design row per scanline ---
    ; ObjTop..ObjTop+11 window → row byte from ObjSprites[ObjBase + offset].
    ; Object off: ObjBase=$FF sentinel (ObjTop parked 144). S2.2: ObjTop is RoomY-relative;
    ; Y here = A0+1 = next line's A0, so `Y - ObjTopRel` = Scanline - ObjTop
    ; (mod 256, exact). In-object iff result 0..11 → `cmp #12/bcs` (C=0 in
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
    lda ObjColorTab,X      ; per-row object color (+5c cross — the cycle sum
                           ; equals the probe's proven pass: 5c beam + 4c
                           ; color after phase 0's beam fold)
    sta COLUP1
.AfterObj:

    ; --- Loop control ---
    sta WSYNC                   ; wait for end of this scanline
    dec LineCount               ; decrement scanlines remaining in row
    bne .Line                   ; loop if more scanlines in this row

    ; --- Advance to next tile row (X clobbered by object section: reload) ---
    ldx RowIdx
    inx
    stx RowIdx
    ; Phase 3: single cpx + bcs replaces `cpx #TILE_ROWS / cpx #TILE_ROWS+1`
    ; (−2B, −2c on rows 1/2 setup lines; X=3 already branched, X=4 → C=1).
    cpx #TILE_ROWS
    beq .WaterRow                ; row 2 done -> water strip pass
    bcs .AfterRows               ; X=4 (C=1,Z=0): water pass done
    ; Title ($FF): band 0 was the real cave stage; bands 1-2 (logo/footer +
    ; bottom row) are bank1's TitleBand. Gameplay falls through to .Row,
    ; +5c on this setup line only (measured: wall model unchanged).
    lda DropTarget
    cmp #$FF
    bne .Row
    jmp CallPad_TitleBand
.GrpSkip:                       ; A0 >= 11 (incl $ff): no color/beam/fetch on
    iny                         ;   this line — advance running Y, then blank
    jmp .GrpZero                ;   GRP0 for the next line. Relocated here
                                ;   (was inline after sta ENAM0) so the color
                                ;   path drops its dead cpy/bcs (4c — worst
                                ;   path 73c work/76 start-to-start = stall
                                ;   zone -> 69c/72, single line). bcs .GrpSkip
                                ;   stays same-page 3c (F136 -> F1xx, rel8
                                ;   fits; verify_build branch guard).
.WaterRow:
    ; PF0/1/2 + COLUPF persist from row 2's setup; COLUBK = the VBL .BgStore
    ; value (Phase 3: .Row no longer re-stores it per band) — the strip
    ; overlays the same cells, so only the band color + 11 lines are needed.
    ; Band color: blink (BombPacked state=2) keeps COLUBK; 0 = band off.
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
.GrpZero:                       ; dead space: entered only from .GrpSkip
                                ;   (bcs A0>=11 -> iny -> jmp here)
    lda #0                      ; (nothing falls through `jmp .Row`)
    sta GRP0
    jmp .Grp1
.ObjZero:
    bne .ObjNoRes           ; flags live from `cmp #PLAYER_HEIGHT` upstream:
                            ; A==8 ONLY = first line below the window — the
                            ; only line where COLUP1 still holds the object
                            ; color (all other obj-out lines: band color from
                            ; .Row is intact, or this line already restored).
                            ; A!=8 (above window / below first line): skip the
                            ; restore — this was the A0=11 worst line
                            ; (color+beam+GrpZero+restore = 77c > 76 → WSYNC
                            ; late → +1 line/frame, sim 264). #6 attempt to
                            ; restore EVERY line measured 271-line frames —
                            ; keep the A==8-only restore.
    lda Temp                    ; bugs.md #15: door bands stage $1C here at
                                ;   .Row, others the band colour ColupfBuf,X
    sta COLUP1                 ; restore-then-blank: A==8 blanks GRP1 10c later
                               ; than before (one line, ~15px of row7 dup) —
                               ; accepted to fit +1B headroom.
.ObjNoRes:
    lda #0
    sta GRP1
    beq .AfterObj              ; Z=1 from lda #0 — always taken (3c = jmp,
                               ; saves 1B vs jmp: net +1B total = $FC67 fit)
.AfterRows:
    ; Phase 3: cave may leave the ball on (band2 BandTab=$ff) — clear ENABL
    ; at the very start of the HUD line, before bank1's first WSYNC and
    ; before the ball's x pixel on this line (bank1 has no pre-pin room for
    ; the clear: +2B tripped .ds $F9C0).
    lda #0
    sta ENABL
    sta ENAM1                    ; D6: end M1 whole-cave latch (HERO writes
                                 ; the ball latch twice per frame — same
                                 ; discipline; bank1 HUD has no room for it)
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
    and #%00000111              ; b2-0 = bombs; b7-3 are the raft's ramp state
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
    lda BombX                    ; position P1 ONCE here (overscan, timer-gated);
    ldx #1                       ;   bomb X is constant during the straight fall,
    jsr SetObjectXPos            ;   so VBL bomb path skips SOXP (its WSYNC shifted
                                 ;   the re-anchor phase = +1-line pump on bt0)
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

; --- Jet thrust accumulator: +1 every 4th frame while Up is held
;     (cap JET_MAX). BUGS #31 (2026-10-11, clarified spec):
;       * spin-up: ÷4 ramp gate (EnemyRamP & 3) — net lift at exactly
;         60f = 1.0s of held-Up (user-confirmed "perfect").
;       * release -> FLOAT: JetPower takes b7 as the float flag and the
;         low 7 bits as a 54-frame countdown ($80|54 = $B6). Phase A:
;         gravity-only decel stops the climb in ~0.3s; then Y is pinned
;         (vy re-zeroed every frame) for ~0.5s (user retest: the first
;         1.0s hover was too long — halved); then the flag clears and
;         normal gravity resumes (fall ~0.85s after release). State
;         lives in JetPower, NOT
;         StepsLeft: StepsLeft is the RefreshEnemyY SWCHB latch's byte
;         (title edge-detect contract) and .UpSteps rewrites it every
;         rising frame — both clobbered a StepsLeft-based float.
;       * Sound is press-gated (SWCHA D4) — buzz starts on the press.
;       * +~50B here: absorbed by the pre-pad $F8DD pad slack
;         (headroom stays $FC67).
; ------------------------------------------------------------------------------
    lda #%00000001              ; test D0 (up, after 4x LSR)
    bit Temp
    bne .JetDecay
    lda JetPower                ; Up held: cancel an active float first
    bpl .RampStart              ;   (b7 flag) — WITHOUT this guard the
    lda #0                      ;   clear would wipe JetPower every held
    sta JetPower                ;   frame and the ramp could never build
.RampStart:
    lda EnemyRamP               ; ramp gate: +1 only on the free-running
    and #3                      ;   clock's phase 0 (every 4th frame)
    bne .Gravity
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
.JetDecay:                      ; Up NOT held this frame
    lda JetPower
    beq .Gravity                ; 0: idle / normal fall
    bmi .FloatRun               ; b7 set: float already active -> step it
    lda vyHi                    ; RELEASE EDGE (thrust 1..127, b7 clear):
    ora vyLo
    beq .Gravity                ;   vy == 0 (DropArm JP=4 residue) — no
                                ;   climb to stop, do NOT float
    lda #$80+54                 ;   $B6 = float flag | 54-frame countdown:
    sta JetPower                ;   ~26f climb-decel + ~28f pinned-Y
    jmp .Gravity                ;   (user: 1s hover too long ->
.FloatRun:
    dec JetPower                ;   halved to ~0.5s); fall ~0.85s
    lda JetPower                ;   after release. tick: $B6..$81
    and #$7F
    bne .FRActive
    sta JetPower                ; A = 0: countdown done -> flag cleared,
    beq .Gravity                ;   normal gravity fall from here
.FRActive:
    lda vyHi
    bmi .Gravity                ; still climbing: gravity-only decel
    lda #0                      ; rise stopped: pin Y for the rest of
    sta vyLo                    ;   the countdown (~1.0s hover)
    sta vyHi
    jmp .Integrate

; --- Physics: vy += GRAVITY (gravity), vy -= JetPower (jet thrust). ---
;     JetPower b7 = float flag (bugs #31): float frames add gravity
;     only — subtracting $80+ would blast the player upward.
.Gravity:
    clc
    lda vyLo
    adc #<GRAVITY
    sta vyLo
    lda vyHi
    adc #>GRAVITY
    sta vyHi
    lda JetPower
    bmi .ThrustSkip              ; float: no thrust subtraction
    sec
    lda vyLo
    sbc JetPower
    sta vyLo
    lda vyHi
    sbc #0
    sta vyHi
.ThrustSkip:

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
;     Respawn hover (bugs.md #1) runs HERE so every velocity path reaches it
;     (the clamp above `jmp .Integrate`s past anything placed earlier). While
;     Hover is set, pin Y (vy=0, no fall) but let the jet ramp run; once thrust
;     can beat gravity (JetPower >= GRAVITY+1) clear it and normal physics
;     resumes (he lifts off). No Up -> hovers in place.
.Integrate:
    lda Hover
    beq .DoInt
    lda JetPower
    cmp #GRAVITY + 1
    bcs .HoverEnd
    lda #0
    sta vyLo
    sta vyHi
    jmp .DoInt
.HoverEnd:
    lda #0
    sta Hover
.DoInt:
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

    ; --- Game timer (60 frames/step × 120 = 120s) ---------------------------
    dec TickCounter
    bne .TimerDone              ; not 1s yet
    lda #60
    sta TickCounter
    ; Forced fall (DropTarget != 0): swallow ONLY the bar step (bugs.md #30).
    ; TickCounter keeps running (jet-flutter clock + second phase stay
    ; frame-exact), so the bar pauses while the player cannot act — no more
    ; red-at-start from the game-start drop-in — without shifting the
    ; PickPlayerFrame animation phase the bit-identity probe asserts.
    lda DropTarget
    bne .TimerDone
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
    ; D2: sync the compressed bar-table index here (BarLevel only changes in
    ; this block / at full-reset sites). (B+7)>>3 → 0..15; HUD reader pays 0c.
    lda BarLevel
    clc
    adc #7
    lsr
    lsr
    lsr
    sta BarIdx

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
; EnterRoom tramp lives at $FBD0 (shared fill region — bank2 mirrors the
; 6 bytes there; see TitleTailAudio below). Body = EnterRoomB2 in bank2.

EnemyBitTable:
    .byte $01, $02, $04, $08

; ------------------------------------------------------------------------------
; UpdateEnemies — per-type live motion from RAM shadow (overscan).
; E0: loop runs EVERY frame; each type carries its own speed gate (snake
; ÷4 here; bat ungated, spider ÷8, tentacle ÷2/÷8, moth ÷2 in E1-E4).
; Snake patrol: bounds are SYMMETRIC about the ROM spawn X (± SNAKE_PATROL =
; one tile, user 2026-10-19 — see the constant): retreat a tile behind the
; placement, come out a tile, repeat. The ROM dir names the side it comes OUT
; on: the loader inverts a snake's live dir at room load (bank2 EnterRoomB2),
; so the first move is the retreat into its wall. Ignores editor range_* per
; user 2026-09-23. No wall collision.
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
    ldy EnemyOffTable,X          ; Y = X*3 = type offset
    jsr FoldIndirect             ; type
    jmp UEDispatch               ; UEDispatch ($F82C pin gap) replaces the old
                                 ; 18 B per-type compare chain with one 3 B jmp:
                                 ; frees 15 B of pre-pad headroom and gives the
                                 ; type tables room for the raft byte.
UE_SnakeBody:
    lda TickCounter              ; snake: 1 px / 8 frames (user 2026-10-19:
    and #7                      ;   halved from /4 — it read as too fast)
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
    sec
    sbc #SNAKE_PATROL            ; rmin = spawn - SNAKE_PATROL: SYMMETRIC patrol
                                 ; (user 2026-10-19) — no dir read needed, the
                                 ; range is the placement ± one tile either way
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
    clc
    adc #SNAKE_PATROL            ; rmax = spawn + SNAKE_PATROL (symmetric)
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
    and #1                       ; ÷2 gate: 1 px / 2 frames = 0.5 px/frame
                                 ; = half the player's 1 px/frame (user
                                 ; 2026-10-10: &3 read as chunky/slow)
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
    cmp #5
    bcc .TentProbeX              ; cand<=4: offset would push RoomX to <=3 —
                                 ; PHM's negative visible-left wraps to 255
                                 ; (col garbage / ColOff OOB walk). cand<=4
                                 ; ink pokes off-screen anyway; RoomX=cand
                                 ; already covers cell0.
    sec
    sbc #1                       ; #4: per-enemy origin offset — tentacle ink
                                 ; sits 5/7 px left of A (moth .Mvl convention,
                                 ; bank2), but PHM's PLAYER prologue derives
                                 ; lit-left = arg-4/arg-7 with the bin on
                                 ; RoomX-PlayerDir → box missed the cell left
                                 ; of the ink at cand 8/12 (sprite drew 1 px
                                 ; into the wall — bugs.md #4). cand-1 shifts
                                 ; the tested box 1 px left: cell-exact or 1 px
                                 ; conservative for every cand/facing pair
                                 ; (tools/test_cell_map.py tentacle section).
.TentProbeX:
    sta RoomX                    ; probe as the tentacle (candidate x [-1])
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
    cmp #ENEMY_MOTH             ; E4: Y arm — CallPad to bank1 (leaf_move_plan)
    bne .DEYStatic
    jsr CallPad_MothYDerive
    jmp DEYDelta
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
; ------------------------------------------------------------------------------
; C3 (2026-10-20): the four handlers MOVED to bank2 ($FC4F cluster) — the
; connection table is level data in bank2, so each handler now reads its own
; 2-byte conn record directly (bank1 GetConnIdx + FoldIndirect hops gone).
; bank0 keeps only the entry pads at $FBD9-$FBE4 (3 B each, `sta $1FF8`;
; bank2 serves the `jmp` at A+3). The OPPOSITE-EDGE placement is written
; BEFORE `jmp EnterRoomB2`, because EnterRoom never touches RoomX/RoomY
; (checked: EnterRoomB2 + B3RoomBlocks read neither) — that keeps the whole
; tail in bank2 with 0 pushes: EnterRoomB2's `jmp ReturnPad` pops the
; ORIGINAL `jsr ExitRoomXxx` frame, exactly like the old in-bank return.
; Guard: verify_build.CORRIDOR_PADS (4 pads) + check_exit_handlers (edge
; placement precedes the EnterRoomB2 tail; no-exit path ends in ReturnPad).
; ------------------------------------------------------------------------------

; ==============================================================================
; Level management
; ==============================================================================
; LoadLevel MOVED to bank2 (C2, 2026-10-20) — body = LoadLevelB2 ($F640).
; The level index/table lives in bank2 (level data), so the old body paid 7
; `jsr FoldIndirect` (7 x 25c + 14 bank switches) to read a 7-byte entry that
; an in-bank (FetchPtr),Y read now fetches directly. Both halves are split
; pads (same discipline as CallPad_SelectObject):
;   A=$FC20  CallPad_LoadLevel / LoadLevel: `sta $1FF8`   (bank0 runs this)
;   A+3=$FC23  bank2 `jmp LoadLevelB2`                    (fetched after it)
;   body tail `jmp $FC26` -> bank2 `sta $1FF6` at $FC26 -> the fetch at $FC29
;   comes from HERE: `jmp LF_B0Tail`, i.e. the drop-in tail (EnterRoom call,
;   level-start placement, `jmp DropArm`) stays in bank0 so the call chain and
;   the measured stack depth are UNCHANGED (0 extra jsr levels, 0 pushes).
; Entry layout: stride 7 = miner_room (b7 = faces right), miner_x, wall color,
; wall color 2, block base word (RoomShapes), room count n (the RoomPositions
; /RoomCounts/enemy-record bases are that block's +n/+2n/+3n offsets, C2).
; Guards: verify_build.check_callpads pins the entry pad bytes + operand,
; check_loadlevel_tramp pins the return half; tools/test_respawn_hover.py,
; test_room_dark.py and test_level_bank.py read the bank2 body.

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
    ; Y overlap: player [RoomY, +11] vs miner [MinerY, +11]
    ; accept iff RoomY - MinerY in [-11, +11]  (add 11, compare 23)
    lda RoomY
    sec
    sbc MinerY
    clc
    adc #PLAYER_SPRITE_H - 1
    cmp #PLAYER_SPRITE_H + PLAYER_HEIGHT - 1
    bcs .CMPDone                ; no Y overlap
    ; Pickup! Arm the level-bonus tally (frozen count-up, then advance).
    ; TallyArm (bank2, via TallyTramp) snapshots time/bombs/lives into
    ; TallyTicks and sets DropTarget=$FE; each frame's dispatch then runs
    ; TallyWork, whose done path does the old tail (level++/LoadLevel/bar).
    jsr TallyTramp
.CMPDone:
    rts

; ==============================================================================
; SelectActiveObject restored to bank0 (A1, 2026-10-20 — reverts C1). The
; body + the two type tables sit in the $F615 fill (before CallPad_RaftBody's
; $F8C0 pin) so nothing ahead of them moves address: bank0's flow tail is not
; binding any more (680 B of org-able fill), and the move frees ~360 B in
; bank2 for the bank3 evacuation. Entry is a plain in-bank `jsr` from the VBL;
; the type byte comes through FoldIndirect and the dark test through
; CallPad_IsRoomDark again (they are bank2/bank1 boundaries, not re-implemented
; here). Guards: verify_build pins the bank0 SetObjectXPos page contract;
; tools/test_room_dark.py, test_bomb_render_x.py, test_key_pickup.py,
; test_enemy_movement.py and test_raft.py (tally gate) watch THIS body.
; ==============================================================================

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
    ; Y overlap: player [RoomY, +11] vs enemy [ActiveObjectY, +11] — exact
    lda RoomY
    sec
    sbc ActiveObjectY
    clc
    adc #PLAYER_SPRITE_H - 1
    cmp #PLAYER_SPRITE_H + PLAYER_HEIGHT - 1
    bcs CEHNext                ; no Y overlap
        ; Lamp (type 5): crash → RoomDarkMask; lamp stays in rotation (grey), no life
    ldx EnemyIndex
    ldy EnemyOffTable,X         ; Y = EnemyIndex * 3
    jsr FoldIndirect            ; type
    cmp #LAMP
    beq CEH_Lamp
    cmp #KEY                    ; type 6 = key: collect, no life loss
    bcc .CEHkill                ; 0-4 (LAMP handled above) = enemy: lose life
    bne CEHNext                 ; 7 = RAFT: a platform is walked on, not hit
    jmp CEH_Key                 ; 6 = key
.CEHkill:
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
    jsr BombEnemyBlast          ; S9: A = 1 kill (bank2, lamp-safe), 0 none
    beq .BTNoKill
    lda #$50                    ; +50 per kill — moved out of the pad body
    jsr CallPad_AddScore        ;   (pads cannot nest; same shape as BMW above)
.BTNoKill:
    jsr BombPlayerBlast         ; S5: player ±1 col any Y → life (may ReloadLevel → clears masks)
    jsr CallPad_BombSndExplode          ; S10: noise burst
.BTDone:
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
;   (pads cannot nest: ReturnPad switches to bank0 mid-call). bank1 owns the
;   ABW tables + BombMaskBit now (plan 5.2 deleted the kernel copies along
;   with ApplyBombWalls).
; ------------------------------------------------------------------------------


; ==============================================================================
; Data tables
; ==============================================================================

; --- Explosion blink COLUBK: index = (60-BombTimer) % 3 ---
BombBlinkColors:
    .byte COLOR_CAVE_BG         ; 0 black
    .byte COLOR_BLINK_Y         ; 1 yellow
    .byte COLOR_BLINK_R         ; 2 red
    .byte COLOR_BLINK_Y         ; 3 yellow (4-phase blink: b/y/r/y)

; BombMaskBit: bank1-only now (plan 5.2 — kernel copy died with ApplyBombWalls).

; BombClearMask moved to bank1 with ClearPFColumn (leaf_move_plan batch B).

; --- Player sprites: 8x12, all 8 pixels wide (bit7 = leftmost pixel) ---
; Frame A = normal, frame B = jet legs (rows 7-8 differ; 3 pixels changed).
; Per-row colors in PlayerColTable (RED/RED/YELLOW/RED/GRAY/RED/.../BLACK/BLACK).
; ------------------------------------------------------------------------------
; CEH_Key — type-6 key pickup (docs/feature_tiles_plan.md Phase 5): latch
; KeyHeld ($A7 b7) and mark the key slot dead so it vanishes, with NO life
; loss. X = EnemyIndex (set by CheckEnemyHit's hit path); reached via
; `jmp CEH_Key` from that dispatch. Lives in the $F82C pre-pad pin gap
; (177B slack before the $F8DD sprite pin); pre-pad END headroom is 1B but
; this region is upstream of the pin, so it costs nothing at $FC67.
; KEY is one per level, so KeyHeld is a single bit (no per-key storage).
; LevelStartRoom b7 resets when LoadLevel rewrites $A7 (:1875) before its own
; read at :1922, so no reader mask is needed; KeyHeld survives room changes
; and normal deaths, resets on game-over reload.
; ------------------------------------------------------------------------------
CEH_Key:
    lda EnemyDeadMask
    ora EnemyBitTable,X
    sta EnemyDeadMask
    lda LevelStartRoom
    ora #$80                    ; KeyHeld = b7
    sta LevelStartRoom
    rts

; ------------------------------------------------------------------------------
; UEDispatch — the enemy-type dispatch tail, moved out of UpdateEnemies into the
; $F82C pin gap (upstream of the $F8DD sprite pin, so the pre-pad END is
; unaffected and the 15 B the folded chain frees stays free). Every non-raft arm
; tail-jumps, exactly like the old inline chain, so the stack depth is unchanged.
; ------------------------------------------------------------------------------
UEDispatch:
    cmp #ENEMY_RAFT
    bne .UEDNotRaft
    jsr CallPad_RaftBody         ; bank1 body; returns past this jmp (ReturnPad)
    jmp UE_Next
.UEDNotRaft:
    cmp #ENEMY_TENTACLE
    bne .UEDNotTent
    jmp UE_Tentacle              ; tail jmp: saves 2 push bytes (stack guard)
.UEDNotTent:
    cmp #ENEMY_MOTH              ; E4: moth body runs in bank2 (code fold)
    bne .UEDNotMoth
    jmp UE_MothTramp             ; tail jmp: 0 push (stack guard, like tentacle)
.UEDNotMoth:
    cmp #ENEMY_SNAKE
    bne .UEDNotSnake
    jmp UE_SnakeBody
.UEDNotSnake:
    jmp UE_Next                  ; other types: no X motion (Y is derived)
                                 ; (absolute jmps: this block is far from the
                                 ;  bodies — relative branches do not reach)

; ==============================================================================
; SelectActiveObject — choose the single GRP1 object to draw this frame (A1
; revert: back in bank0; C1's bank2 copy is gone). TIA has one GRP1 sprite, so
; objects flicker by rotating slots. Sets ObjBase, ActiveObjectX,
; ActiveObjectY, ObjTop, COLUP1 and P1's hardware X (SetObjectXPos).
; Slot count (enemies + miner?) lives in Temp for this VBLANK only.
; The enemy TYPE byte is level data in bank2/bank3 → FoldIndirect; the
; room-dark test is bank1's IsRoomDark → CallPad_IsRoomDark.
; ==============================================================================
SelectActiveObject:
    ; Tally / frozen scene (DropTarget = $FE): show the PLAYER and the MINER
    ; only — no enemies, no raft, no bomb. That frame bypasses the overscan, so
    ; RefreshEnemyY never runs while bank1's HUD writes $E0-$EF: EnemyRamY
    ; ($E2-$E4) is left holding score-pointer bytes, and any enemy drawn then
    ; jumps to a garbage Y (user report 2026-10-18: the raft "moved up to the
    ; middle of the screen" the moment the points counting started).
    lda DropTarget
    cmp #$FE
    bne .SOFull
    lda #0
    sta FlickerFrame            ; keep the modulo counter bounded (2026-10-16)
    sta ObjBase                 ; 0 = no object
    lda LevelMinerRoom
    and #$7f
    cmp RoomNo
    beq .SOTallyMiner
    jmp .SODone                 ; miner not here -> nothing drawn
.SOTallyMiner:
    lda #OBJ_MINER
    sta ObjBase
    lda MinerX
    sta ActiveObjectX
    lda MinerY
    clc
    adc #3                      ; same 3px offset as the normal miner path
    sta ActiveObjectY
    lda #$66                    ; purple (hue 6, luma 3)
    sta COLUP1
    jmp .SODone
.SOFull:
    inc FlickerFrame            ; advance every frame (bomb + enemy paths)
    ; --- Bomb fuse (state=1): 1 of 4 frames = bomb (enemies keep priority) ---
    lda BombPacked
    and #%00000011
    cmp #1
    bne .SOCount
    lda BombTimer
    and #3
    bne .SOCount                ; 3 of 4 -> miner/enemy
    lda #OBJ_BOMB               ; bomb design offset into ObjSprites
    sta ObjBase
    lda BombX
    sta ActiveObjectX
    lda BombY
    sta ActiveObjectY
    lda #COLOR_BOMBS             ; $46 red (P1 X set by the .SODone tail)
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
    ; No objects this frame: A = Temp = 0. Blank the sprite AND reset the
    ; flicker counter — with no objects the modulo below never runs, so
    ; FlickerFrame would grow unbounded and .SOModLoop (a subtract loop)
    ; would run O(FlickerFrame) iterations in the VBL on the next room with
    ; objects (measured +533c / +7 lines room-crossing spike, 2026-10-16).
    sta FlickerFrame
    lda #$FF
    sta ObjBase
    jmp .SODone
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
    clc
    adc #3                      ; draw 3px below data Y (miner_position.png —
                                ; sprite floated above the floor line; tuning
                                ; constant — pickup box still uses MinerY)
    sta ActiveObjectY
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
    lda #$FF
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
    ldy EnemyOffTable,X         ; Y = EnemyIndex * 3 = type offset
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
    cpx #KEY
    bne .SOPNorm
    lda LevelStartRoom          ; Phase 5: KeyHeld ($A7 b7) → key already
    bmi .SOEnemySkip            ;   taken → skip render (never reappears)
.SOPNorm:
    lda ObjSpriteOffTable,X     ; type → ObjSprites design offset
    sta ObjBase
.SOEnemyColorDone:
    ldx EnemyIndex
    lda EnemyRamY,X             ; live Y from $E2 (private since S3.4)
    sta ActiveObjectY
    jmp .SODone

.SOEnemySkip:
    lda #$FF
    sta ObjBase

.SODone:
    ; Position GRP1 from ActiveObjectX — ONE shared call for every object
    ; path (bomb/miner/enemy). ac4c3ee moved the bomb's SOXP to the drop and
    ; the bomb path skipped it, so the bomb rendered at the last enemy/miner
    ; X (looked fixed). ObjBase==0 (no object / dead-enemy slot) skips it.
    lda ObjBase
    bmi .SODoneNoPos
    lda ActiveObjectX
    ldx #1
    jsr SetObjectXPos
.SODoneNoPos:
    jsr SetObjReflection
    ; Set ObjTop for kernel GRP1 visibility check.
    ; S2.2: ObjTop stored RoomY-relative (ObjTopRel = ActiveObjectY-RoomY+1) so
    ; the kernel compares against running-Y (`tya`) instead of `lda Scanline`
    ; — frees 9c/line (lda Scanline + inc Scanline) for the laser beam write.
    ; Kernel .Grp1 does: tya / sec / sbc ObjTop / cmp #8 / bcs .ObjZero.
    ; ObjBot (write-only, no readers): stores removed S1.5, decl removed
    ; S3.0b (was last sequential decl — no address shift).
    lda ObjBase
    bmi .SONoObj
    lda ActiveObjectY
    sec
    sbc RoomY
    clc
    adc #1                      ; A = ActiveObjectY - RoomY + 1 (mod 256)
    sta ObjTop
    jsr StageSlot1              ; Phase 5: pair a second object in a higher band
    rts
.SONoObj:
    lda #144                    ; Park the GRP1 window off-cave for EVERY
    sec                         ; RoomY. The kernel draws when running-Y
    sbc RoomY                   ; (Scanline-RoomY) - ObjTopRel ∈ [0,7] =
    sta ObjTop                  ; Scanline-(RoomY+ObjTopRel); parking ObjTopRel
    jsr StageSlot1              ; clears slot 1 too (no slot 0 to pair with)
    rts                         ; = 144-RoomY → Scanline-144 ∈ [112,255] →
                                ; never <8 → never drawn. A CONSTANT 144
                                ; wrapped for RoomY ≥ 112 (Scanline-(144+RY)
                                ; mod 256 ∈ [0,7]) and drew ObjSprites[row+
                                ; ObjBase]; with the key art now at slot 0
                                ; (ObjBase=$FF → row 1..7 = index 0..6) that
                                ; leaked the key onto the player's rows
                                ; (user 2026-10-17). The old blank slot 0 had
                                ; hidden this latent bug.

; ==============================================================================
; Enemy color table (emulator-aware: hue<<4 | luma<<1)
EnemyColorTable:
    .byte $14                   ; spider — hue 1 luma 2 = dark yellow
    .byte $f2                   ; bat — hue 15 luma 7 = brown
    .byte $c4                   ; snake — hue 12 luma 2 = green
    .byte $0e                   ; tentacle — hue 0 luma 7 = white
    .byte $22                   ; moth — hue 2 luma 1 = dark orange
    .byte $0e                   ; lamp (type 5) — white; dark rooms override to grey
    .byte $1C                   ; key (type 6) — yellow
    .byte $c4                   ; raft (type 7) — green, matching the SNAKE art
                                ; slot it borrows ($c4 = ObjColorTab slot 6). User
                                ; 2026-10-18: keep the SOLID block and read it as
                                ; a trunk/log — the solid art also looks bigger
                                ; than the notched LAMP one, so the player lands
                                ; on it more confidently.

; Enemy type → ObjSprites design offset (index = ENEMY_* type)
ObjSpriteOffTable:
    .byte OBJ_SPIDER            ; 0
    .byte OBJ_BAT               ; 1
    .byte OBJ_SNAKE             ; 2
    .byte OBJ_TENTACLE          ; 3
    .byte OBJ_MOTH              ; 4
    .byte OBJ_LAMP              ; 5 (LAMP)
    .byte OBJ_KEY               ; 6 (KEY — offset-0 slot)
    .byte OBJ_SNAKE             ; 7 (RAFT — the solid 8x8 block: a log/trunk over
                                ; the water, and the most "landable" shape in the
                                ; table. ObjSprites is exactly 72 B and ends at
                                ; $FF00, so a dedicated design needs 8 art bytes
                                ; freed; every entry is 8x8, so nothing is
                                ; "larger" — solid just reads bigger than notched.)

; ==============================================================================
; Phase 5 — second GRP1 object (no flicker). TIA has one GRP1 sprite, so two
; objects in a room used to alternate frames (30 Hz flicker each). When they
; live in DIFFERENT cave bands each can be drawn on ALL of its scanlines: the
; band's setup swaps the live trio (ObjBase/ObjTop/ActiveObjectX) for slot 1
; and repositions P1 there. The per-line object path is untouched — it already
; draws from the live trio and takes COLUP1 from ObjColorTab[ObjBase+row].
;
; Invariant (do not relax): slot 1's band is STRICTLY HIGHER than slot 0's.
; Bands are set up 0->1->2, so no later band has to restore slot 0's trio.
; Rooms whose two objects share a band keep the old behaviour (slot 0 only,
; rotation in SelectActiveObject unchanged).
; Cost: the band-compare early-out sits in the setup line's free tail (0
; lines); a band that DOES host slot 1 pays 2 lines (SetObjectXPos must start
; on a line boundary and the HMOVE needs the next line's HBLANK).
;
; StageSlot1 (VBLANK, after SelectActiveObject): stages ObjBase1/ObjTop1/ObjX1,
; $FF = none. Slot 1 = the miner or the first live enemy whose Y is in a band
; above slot 0's. The KEY skip mirrors the slot-0 path (KeyHeld = LevelStartRoom
; b7). Tally frames ($FE) are gated out: EnemyRamY holds score-pointer bytes
; then (AGENTS: tally frame draws the MINER only).
; ==============================================================================
StageSlot1:
    lda #$FF
    sta ObjBase1                ; default: no second object
    lda DropTarget
    cmp #$FE
    bne .S1go
    rts                         ; tally frame: miner only (stale EnemyRamY)
.S1go:
    ; --- scan the room's LIVE candidates (enemies + miner): min Y, max Y ---
    ; Slot 1 must NOT depend on SelectActiveObject's rotation: with the bomb
    ; taking 1 of 4 frames the frame length would alternate 267/269 (sim
    ; caught it, 2026-10-21). It depends only on the room's geometry.
    lda #$FF
    sta Temp                    ; min Y ($FF = no candidates)
    lda #0
    sta FetchPtr                ; max Y
    sta FetchPtr+1              ; max candidate index ($FF = the miner)
    ldx #0
.S1scan:
    cpx EnemyCount
    bcs .S1cand
    lda EnemyDeadMask
    and EnemyBitTable,X
    bne .S1snext
    lda EnemyRamY,X
    cmp Temp
    bcs .S1notMin
    sta Temp
.S1notMin:
    cmp FetchPtr
    bcc .S1snext
    sta FetchPtr
    stx FetchPtr+1
.S1snext:
    inx
    jmp .S1scan
.S1cand:
    lda LevelMinerRoom
    and #$7f
    cmp RoomNo
    bne .S1span
    lda MinerY
    clc
    adc #3                      ; same +3 draw offset as the slot-0 miner path
    cmp Temp
    bcs .S1minOk
    sta Temp
.S1minOk:
    cmp FetchPtr
    bcc .S1span
    sta FetchPtr
    lda #$FF
    sta FetchPtr+1              ; the miner owns the top slot
.S1span:
    lda Temp
    cmp #$FF
    beq .S1ret                  ; no candidates at all
    ; slot 1 exists only when the candidates span TWO bands: one per band is
    ; what removes the flicker. Same-band rooms keep the old rotation (a swap
    ; there would hide the other object forever).
    jsr .S1band
    sta EnemyIndex              ; band(min)
    lda FetchPtr
    jsr .S1band
    cmp EnemyIndex
    beq .S1ret                  ; all candidates in one band
    ; --- stage the highest-band candidate as slot 1 ---
    ldx FetchPtr+1
    cpx #$FF
    beq .S1stageMiner
    ldy EnemyOffTable,X         ; Y = record offset (FoldIndirect preserves Y)
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    txa
    pha                         ; keep the candidate index across the type read
    jsr FoldIndirect            ; A = type (bank2 record through the twin)
    tax
    cpx #KEY
    bne .S1stageEnemy
    lda LevelStartRoom          ; b7 = key already taken -> never reappears
    bmi .S1retPop
.S1stageEnemy:
    lda ObjSpriteOffTable,X
    sta ObjBase1
    pla                         ; X = candidate index
    tax
    lda EnemyRamX,X
    sta ObjX1
    lda EnemyRamY,X
    sec
    sbc RoomY
    clc
    adc #1
    sta ObjTop1
    rts
.S1stageMiner:
    lda #OBJ_MINER
    sta ObjBase1
    lda MinerX
    sta ObjX1
    lda MinerY
    clc
    adc #3
    sec
    sbc RoomY
    clc
    adc #1
    sta ObjTop1
    rts
.S1band:
    ldy #0
    cmp #48
    bcc .S1bRet
    iny
    cmp #96
    bcc .S1bRet
    iny
.S1bRet:
    tya
    rts
.S1retPop:
    pla
.S1ret:
    rts

; Slot1Hook — called from the .Row setup (X = RowIdx = band). Swaps the live
; trio when slot 1 lives in this band, then repositions P1 and strobes HMOVE
; on the following line's HBLANK. Preserves X (RowIdx) and Y (running-Y: the
; .Line loop relies on it being untouched between rows).
Slot1Hook:
    tya
    pha                         ; save running-Y (SetObjectXPos does `tay`)
    lda ObjTop1
    clc
    adc RoomY
    sec
    sbc #1                      ; A = slot 1's absolute room Y
    cmp BandStart,X
    bcc .SHout                  ; above this band
    cmp BandStart+1,X
    bcs .SHout                  ; in a later band
    lda ObjBase1
    sta ObjBase
    lda ObjTop1
    sta ObjTop
    lda ObjX1
    sta ActiveObjectX
    ldx #1
    jsr SetObjectXPos           ; its own WSYNC starts the positioning line
    ldx RowIdx
    sta WSYNC                   ; end of the positioning line
    sta HMOVE                   ; cycle 0 of the next line = HBLANK
.SHout:
    pla
    tay
    rts

BandStart:
    .byte 0,48,96,144           ; first scanline of bands 0..3

; CallPad_RaftBody — bank1 RaftBody entry. Pinned at $F8C0 with a
; BYTE-IDENTICAL twin in bank1 (bank1.asm, same address): the `sta $1FF7`
; switches banks, so the `jmp` opcode AND its operand are fetched from bank1,
; not from here. That is the same FoldIndirect discipline every other tramp
; uses — the twin cannot be skipped or shortened.
; Guard: verify_build.check_raft_tramp (identity + operand == bank1 RaftBody).
    .ds $F850 - *, 0            ; ObjSprites: 12 rows/type = 108 B.
                                 ; Base low byte $50 + max index 107 =
                                 ; 187 -> `lda ObjSprites,X` stays in one
                                 ; page (verify_build guard).
; 12 rows per type, bits 7-4 (col0 = bit7). Offsets come from the OBJ_*
; EQUs via ObjSpriteOffTable (stride 12).
ObjSprites:
    ; KEY (offset 0): bow, shaft, stepped teeth
    .byte $3C,$42,$5A,$42,$3C,$18,$18,$18,$18,$1C,$18,$10
    ; MOTH (12): antennae, upper wing pair, body, lower wing pair, taper
    .byte $90,$60,$F0,$F0,$60,$90,$F0,$F0,$60,$90,$60,$30
    ; SPIDER (24): round body, then four leg rows spreading down
    .byte $60,$F0,$F0,$60,$90,$60,$90,$90,$48,$24,$12,$06
    ; LAMP (36): shade, neck, bowl, post, wide base
    .byte $F0,$F0,$60,$60,$F0,$F0,$F0,$60,$60,$60,$3C,$3C
    ; TENTACLE (48): bulky shoulder tapering to a tip
    .byte $60,$90,$80,$60,$30,$30,$30,$18,$18,$0C,$0C,$04
    ; BAT (60): wing pair, body, hanging tail
    .byte $90,$60,$F0,$60,$60,$90,$90,$60,$30,$18,$0C,$00
    ; SNAKE (72): solid block (it lives inside its wall cell; the raft rides it)
    .byte $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF
    ; MINER (84): helmet, pink face, body, tool, hips, legs
    .byte $0C,$1C,$4C,$36,$0F,$07,$3F,$6E,$3C,$3C,$18,$18
    ; BOMB (96): fuse, round body, tapered nose
    .byte $10,$20,$20,$60,$F0,$F0,$F0,$60,$30,$18,$18,$0C

    .ds $F8C0 - *, 0
CallPad_RaftBody:
    sta $1FF7                    ; select bank1 (last byte fetched from bank0)
    jmp $FDE3                    ; bank1 RaftBody — returns via bank1's ReturnPad

    .ds $F8DD - *, 0            ; PIN $F8DD: bank2 EQUs PlayerSpriteA/PlayerSpriteB/
                                 ;   PlayerWalkA/B are address-frozen there; bank2
                                 ;   holds art byte-twins at the SAME address
                                 ;   (PickPlayerFrame reads its own EQUs while
                                 ;   bank2 active — test_miner_colors asserts
                                 ;   EQU == bank0 label AND byte identity). The
                                 ;   S9 bomb-lamp stub deletion upstream must
                                 ;   never shift these again.
PlayerSpriteA:
    .byte %00111100             ; row 0 (sprites.png 2026-10-03)
    .byte %01111110             ; row 1
    .byte %01111100             ; row 2 — yellow face
    .byte %01111110             ; row 3
    .byte %01111100             ; row 4 — grey pack
    .byte %11111110             ; row 5
    .byte %11111110             ; row 6
    .byte %00111110             ; row 7 — jet frame A
    .byte %00111110             ; row 8
    .byte %00010100             ; row 9
    .byte %00010100             ; row 10 — grey boots
    .byte %00010100             ; row 11

PlayerSpriteB:
    .byte %00111100             ; row 0
    .byte %01111110             ; row 1
    .byte %01111100             ; row 2 — yellow face
    .byte %01111110             ; row 3
    .byte %01111100             ; row 4 — grey pack
    .byte %11111110             ; row 5
    .byte %11111110             ; row 6
    .byte %01111110             ; row 7 — jet frame B (+1 px vs A)
    .byte %10111110             ; row 8
    .byte %00010100             ; row 9
    .byte %00010100             ; row 10
    .byte %00010100             ; row 11

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
KEY            = 6             ; type-6 enemy record = editor key (Phase 5 pickup)
ENEMY_RAFT     = 7             ; type-7 enemy record = the moving, rideable raft
                               ; (plans/raft_moving_plan.md): floats on the open
                               ; water of model row 2, carries the player and
                               ; returns; body lives in bank1 (RaftBody)
ENEMY_DATA_STRIDE = 6
LEVEL_COUNT    = 4              ; hand copy of generated LEVEL_COUNT (cmp in
                                ; LoadLevel advance guard — test asserts sync).
                                ; 2026-10-21: live stage cut 20 -> 4 levels to
                                ; fund the HERO kernel plan (bank0 eviction);
                                ; the 20-level stage is kept at
                                ; src/tests/stages/stage_20_levels.json
LEVEL_DATA_ADDR = $F307        ; frozen address of bank2's LevelDataTable
                                ; (S4.1 −$FAFA, S4.2 −$FA8E, 2026-10-02
                                ;  −$FA86 as the ≤2-object room migration
                                ;  shrank the tables; check_frozen_addrs
                                ;  enforces)
                                ; (test asserts bank2.lst label == this)
LEVEL_FORMAT   = $06           ; C11 2026-10-21: room-record + shape format. 6 =
                                ; 4 (shape index b5-0 | band b6 | owns-extras
                                ; b7, position byte, enemy count <<6 | extras
                                ; ordinal, then the level's AsyncExtras stream)
                                ; + shape blocks store 3 row-pool indices
                                ; instead of 9 raw PF bytes (C3 row dictionary).
                                ; Hand copy of the generated EQU (bank1 carries
                                ; the twin — check_equ_sync; verify_build
                                ; compares both to generated/levels_index.asm)
; ==============================================================================
; YToRowTable — convert scanline to 48-line band row (0-2), idx A>>2
; ==============================================================================
; The jsr wrapper that used to live here was dead (PlayerHitsMap inlines the
; lsr/lsr/tay/lda lookup — saves 2 JSR stack push levels to keep SP >= $F8)
; and was removed in S1.6. Table rationale: the old subtract loop grew
; linearly with RoomY and made 3× PlayerHitsMap (fall 2 + L/R 1) exceed
; overscan TIM64T=35 (~2240c) in 4-rect rooms → frame >262 lines → vertical
; roll when strafing while falling.
; Indexed by A>>2: 37 entries (idx 0-35 = A 0-143 = the player envelope
; "Max A = PLAYER_MAX_Y+11 = 143", + idx36 = the tentacle-bob clamp, below).
; Costs +4c/call vs the 192-entry table, saves 144 ROM bytes.
; Row = idx/12 = scanline/48 (3 cave bands of 48 lines = rows 0-2).
;
; 36 entries: 12 each of 0,1,2 (value = index/12 = scanline/48) +
; idx36 = 2: tentacle RoomY 133/134 (bob on spawn y=132) → A=(Y+11)>>2 =
; 36 — WITHOUT this byte the lookup reads the OOB opcode ($A5 = `lda
; RoomY`) → CollisionEndY garbage → cell walk false-hits ~24/32 bob
; frames → measured 0.125 px/f vs the &1 gate's 0.5 (bugs.md #13).
; Clamped value 2 = last cave row: box bottom (line 144-145) past the
; cave (0-143) walks row 2 = floor wall, never PF0Buf+3 (row 3 = $C6,
; not a buffer byte). Player never reaches idx36 (PLAYER_MAX_Y=132).
YToRowTable:
    .byte 0,0,0,0,0,0,0,0,0,0,0,0
    .byte 1,1,1,1,1,1,1,1,1,1,1,1
    .byte 2,2,2,2,2,2,2,2,2,2,2,2
    .byte 2                         ; idx36 — tentacle bob clamp (see above)

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
; render buffers PF0/1/2Buf ARE the map (BombMarkWalls punches bomb holes
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
    tax                            ; X = col, seeded ONCE per row (bugs.md #31:
                                   ;   was re-loaded every cell — −8c/cell walk
                                   ;   trim for the falling+probe heavy frame)
.CWCol:
    ldy RectCount
    tya
    clc
    adc ColOff,X            ; PF0/PF1/PF2 group offset (0/3/6)
    tay
    lda PF0Buf,Y            ; $C3+row+off — the byte the kernel renders
    and ColMask,X           ; bit for this source col
    bne .CWHit              ; solid (Z=0)
    cpx CollisionCellX      ; col == max? (X == CollisionX, stx below keeps
    beq .CWRowDone          ;   the memory walk-temp fresh for HotOverlapFlag)
    inx
    stx CollisionX
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
    ; Phase 4: miss → asym-patch overlay (push-neutral tramp, moth pattern).
    ; OverlayTramp gates on LineCount ($84 = packed byte, VBL/$8F staged):
    ; symmetric rooms pay +8c and return here-shaped clc/rts; asym rooms
    ; cross to bank2 PHMOverlay (patch column + band mask), exit via
    ; ReturnPad $FBF8 — rts pops THIS call's return (0 pushes total, SP
    ; guard unchanged). Overlay sets C itself (plain sec — patch cells are
    ; envelope-guaranteed non-hot, so HotOverlapFlag must not run).
    jmp OverlayTramp

EnemyOffTable:
    .byte 0,3,6                 ; enemy index * 3 (2026-10-21: 3 B record —
                                ; type b3-0|dir b7, x, y)

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
    .ds $F9B8 - *, 0            ; Phase 4 overlay tramp — shared address with
                                 ; bank2's twin image (40B bank2 hole before
                                 ; org $F9D9); F6-safe ($F9B1 & $1FFF ∉ hotspots)
OverlayTramp:
    lda LineCount                ; packed asym byte (0 = symmetric)
    beq .OTsym                   ; sym: clc/rts, never enters the cluster
    jmp PHMOverlay               ; bank0 cluster ($FA30; repack chunk 4)
.OTsym:
    clc
    rts

; ------------------------------------------------------------------------------
; PositionBallM1 — D6 asymmetric objects, BOTH positioned in one VBL call.
; WHY here: pre-pad headroom is 1B — inline ball+m1 (22B) cannot live in the
; VBL block, so the ball block became this jsr and the body sits in the
; $F9C4..$FBF7 fill (ReturnPad pin at $FBF8 unaffected; F6-safe:
; $F9C4 & $1FFF = $19C4 ∉ $1FF6-$1FF9; bank0-only, not a fold twin).
;   Temp          = staged BallX (bank2 StageBandTab): 0 = symmetric → skip.
;                   selector 4 = HMBL/RESPBL, ball x drawn clocks [A-7,A].
;   CollisionEndX = staged M1X (MetaA nibble, bank2 StageBandTab):
;                   0 = no M1 patch → skip.
;                   selector 3 = HMM1/RESM1, left-col block x = 7+8*col
;                   (passed to SetObjectXPos as M1X+1 — Stella draws 8-wide
;                   M1 one clock left of the [A-7,A] player contract).
;                   ENAM1 latched #$02 for the whole cave (hero-style: 2
;                   ENAM writes/frame — enable here, clear in .AfterRows);
;                   walls hide the parked M1 in unpatched bands (PF > M1 in
;                   the priority chain — convert enforces the solid cell).
; Runs before the single HMOVE (HMP0+X shadow registers accumulate).
; Sym path cost: jsr+rts overhead only — no RESP/HMP write, frames stay
; bit-identical to the pre-D6 build.
; ------------------------------------------------------------------------------
PositionBallM1:
    lda Temp
    beq .M1
    clc
    adc #1                      ; #9: Stella draws ball/missile 1 clock left of
                                ;   the player contract — Ball.hxx/Missile.hxx
                                ;   renderCounterOffset=-4 vs Player.hxx=-5
                                ;   (same class as the M1 +1 below)
    ldx #4                      ; selector 4: HMP0+4=HMBL, RESP0+4=RESPBL
    jsr SetObjectXPos
.M1:
    lda CollisionEndX
    beq .Done
    clc
    adc #1                      ; Stella renders 8-wide M1 one clock left of
                                ;   the [A-7,A] contract (pixel-measured 2026-10-06,
                                ;   screenshots/assymetric/bug_adjust_collision.png:
                                ;   staged 71 -> drawn [63,70], needs [64,71])
    ldx #3                      ; selector 3: HMP0+3=HMM1, RESP0+3=RESM1
    jsr SetObjectXPos
    lda #$02                    ; missile enable D1 (same encoding the laser
    sta ENAM1                   ;   beam uses for ENAM0)
.Done:
    rts

; ------------------------------------------------------------------------------
; KernelInit — cave running-Y (fill: pre-pad headroom 1B).
; TIA inits moved to the VBL tail 2026-10-06 (entry-span budget — see there).
; The title ($FF sentinel) runs THIS kernel too: band 0 is the real stage,
; then the row-advance tail diverts to bank1's TitleBand (logo/footer/band 2).
; Effects: RowIdx=0, Y=-RoomY, X=0, A=0. ENAM0/ENAM1 NOT touched.
; ------------------------------------------------------------------------------
KernelInit:
    lda #0
    sta RowIdx                    ; tile-row counter (0-2)
    sec
    sbc RoomY                     ; A = -RoomY = A0 at scanline 0
    tay                           ; running-Y for cave .Line
    ldx #0
    rts                           ; → CaveKernelRow (.Row follows the jsr)

; DropSpeedTable — drop-in 8.8 px/frame per Y>>4 tier (Y = tier*16+8), read
; abs,Y by DropStep (post-pad) — moved here to free post-pad room (bugs.md #1).
DropSpeedTable:
    .byte 32,85,128,163,192,216,238,255,255

; ------------------------------------------------------------------------------
; PickPlayerFrame — sprite frame pick (moved from bank2 2026-10-20, repack
; chunk 1). The bank2 copy plus its two art twins ($F8DD/$FDE7) and the $FDE1
; tramp are gone: the body now reads bank0's own PlayerSpriteA/B and
; PlayerWalkA/B, so both the art duplicate and the per-frame bank switch
; (jsr tramp + ReturnPad) disappear. Tail is `rts` (was `jmp ReturnPad`,
; -2 B) because the caller is the bank0 VBL jsr — no switch to return from.
; GRP0 frame pick: jet flutter (PlayerSpriteA/B) > ground walk
; (PlayerWalkA/B, phase EnemyRamP&$08) > static A. Clobbers A/Y; sets
; Grp0Ptr/Grp0PtrHi.
; ------------------------------------------------------------------------------
PickPlayerFrame:
    lda JetPower
    bne .Jet                   ; jet burning -> A/B flutter (existing)
    lda BombPacked
    bpl .FrameA                ; b7 OnGround clear (airborne) -> static
    lda SWCHA
    and #%11000000             ; D7 right / D6 left, active LOW
    cmp #%11000000
    beq .FrameA                ; neither held -> standing
    lda EnemyRamP              ; free-running clock: bit3 = 8-frame
    and #%00001000             ; half-cycle -> 16-frame full walk cycle
    beq .WalkA                 ; (double speed of the 32-frame bit4 version)
    lda #<PlayerWalkB
    ldy #>PlayerWalkB
    jmp .SetGrpPtr
.WalkA:
    lda #<PlayerWalkA
    ldy #>PlayerWalkA
    jmp .SetGrpPtr
.Jet:
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
    rts                        ; back to the VBL jsr (same bank, no switch)

; ==============================================================================
; Phase 4 asym-patch collision overlay cluster — MOVED from bank2 to bank0
; (repack chunk 4, 2026-10-20). One entry (OverlayTramp at $F9B8, inline
; `jmp PHMOverlay` instead of a bank switch), three bodies, two tables:
;   PHMOverlay / OvM1Block / OvShutBand   (ball strip → M1 strip → shutter)
;   OvHead/OvTail (band edges), M1OffTab (MetaA b0 → side offset)
; bank0 already owns ColOff/ColMask (kernel PHM walk) and the $FFEC
; HotOverlapFlag pad, so nothing is duplicated: bank2 loses the bodies, the
; $F9B8 twin, the 2 B M1OffTab and the whole switch (2 fewer per miss path).
; ZP names folded to kernel's: RoomMetaA/B ARE CheckP0Left-walk leftovers
; $99/$9A = RoomPF0Lo/Hi (bank3 stages MetaA/B over the dead pointer pair).
; Exits are plain rts: the PHM caller is bank0, so no ReturnPad round trip.
; ==============================================================================
PHMOverlay:
    ; LineCount packed: b4-b7 = right_col+1, b0-2 = bands with the painted
    ; ball-strip ($ff BandTab entries). D6 envelope: ONE right column
    ; [BallX-7, BallX] px, BallX = 87+8*rc — overlay is additive (cells
    ; painted only where the mirrored cell is open, never hot).
    ; Exact visible_left (same math as PHM's prologue), then px overlap of
    ; [vl, vl+6] (PLAYER_WIDTH=7 lit) with the patch column, then band x rows.
    sec
    lda RoomX
    sbc PlayerDir
    cmp #15
    bcs .Ov7
    sec
    sbc #4
    jmp .OvVL
.Ov7:
    sbc #7
.OvVL:
    clc
    adc PlayerDir               ; A = visible_left px
    sta CollisionX              ; walk temps are free on the miss path
    lda LineCount
    lsr
    lsr
    lsr
    lsr                         ; n = right_col+1 (1..10)
    asl
    asl
    asl                         ; 8n
    clc
    adc #79                     ; BallX = 79+8n = 87+8*rc (patch right edge)
    sta RectCount               ; scratch (NOT CollisionCellX): the prologue
                                ; box must survive for HotOverlapFlag — OvM1Block
                                ; funnels block hits there for hot-death. Scratch
                                ; = RectCount ($92): free after the cell walk,
                                ; RowIdx re-inits at kernel entry. NEVER Temp —
                                ; CheckP0Left/Right read the joystick in Temp
                                ; AFTER this physics call (Temp scratch here
                                ; left D3=0 = phantom right-press = drift bug).
    lda CollisionX
    cmp RectCount               ; vl vs BallX
    bcc .OvT2
    beq .OvT2
    bcs .OvClear                ; vl > BallX → player fully right of patch
.OvT2:
    lda RectCount
    sec
    sbc #13                     ; BallX-13 (lit span is 7px, not 8: [vl,vl+6])
    cmp CollisionX              ; vs vl: overlap iff BallX-13 <= vl
    bcc .OvBand
    beq .OvBand
.OvClear:
    jmp OvM1Block               ; right-strip miss → M1 (left) strip test;
                                ; IT returns with C set/clear.
                                ; Shutter rooms: miss here = player left of
                                ; the VISIBLE right-half block → passable
                                ; (kill follows the drawn block only, async
                                ; ruling 2026-10-14 — no left mirror)
.OvBand:
    jmp OvShutBand              ; band overlap → shutter kill / strip solid

OvM1Block:
    ; Phase 4 M1 (left strip) collision overlay. Entered by JMP from
    ; PHMOverlay's .OvClear — 0 pushes; both exits rts to the PHM caller.
    ; In: CollisionX = vl, CollisionCellY/EndY =
    ; player row range (survive the right tests — do NOT clobber the
    ; prologue box: CellX/EndX/CellY/EndY must stay intact, the block
    ; path hands them to HotOverlapFlag). Scratch = RectCount ($92; M1X,
    ; then ℓ math — see PHMOverlay note). Kill-aware
    ; (EnemyDeadMask b4); a row blocks iff its PF cell at col ℓ is open —
    ; the wall-hide envelope guarantees open ⟺ patched (every band at ℓ
    ; is wall or M1-patched, never plain-open).
    lda EnemyDeadMask
    and #$10                    ; b4 = M1 strip destroyed → transparent
    bne .OvM1no
    lda RoomPF0Lo               ; staged MetaA ($99)
    and #$01                    ; Phase 5: b0 = M1 strip on the RIGHT half
    tax                         ;   (door band mask is $02 → b0 free)
    lda RoomPF0Lo               ; reload MetaA
    lsr
    lsr
    lsr
    lsr                         ; m1_col+1 (0 = no M1 patch)
    beq .OvM1no
    asl
    asl
    asl                         ; 8*(m1_col+1)
    clc
    adc M1OffTab,X              ; -1 (left, $FF) / +79 (right, $4f) → the
                                ;   side's M1X (7+8*col / 87+8*col) — MUST
                                ;   match B3StageBand's staging (its own twin)
    sta RectCount               ; scratch M1X (EndX = prologue min col is
                                ; CollisionEndX — kept intact for HotOverlapFlag)
    lda CollisionX              ; vl
    cmp RectCount                ; vl vs M1X (same shape as the ball test)
    bcc .OvM1T2
    beq .OvM1T2
    bcs .OvM1no                 ; vl > M1X → player fully left of strip
.OvM1T2:
    lda RectCount
    cmp #13
    bcc .OvM1Band               ; M1X < 13 (ℓ = 0): M1X-13 wraps — skip
    sec                         ; the second test (test 1 already implies
    sbc #13                     ; overlap for every valid vl)
    cmp CollisionX
    bcc .OvM1Band
    beq .OvM1Band
    bcs .OvM1no                 ; M1X-13 > vl → player fully right
.OvM1Band:
    lda RectCount
    sec
    sbc #7
    lsr
    lsr
    lsr                         ; ℓ = (M1X-7)/8
    tax                         ; X = ℓ (PHM callers preserve X themselves)
    lda CollisionCellY
    sta RectCount               ; $92 walk temp — free after the cell walk
                                ; (RowIdx re-inits at kernel entry)
.OvM1Row:
    lda RectCount
    tay
    tya
    clc
    adc ColOff,X                ; PF0/PF1/PF2 group offset (0/3/6)
    tay
    lda PF0Buf,Y                ; same cell read as PlayerHitsMap
    and ColMask,X
    beq .OvM1block              ; open → patch cell active in this row
    lda RectCount
    cmp CollisionEndY
    beq .OvM1no
    inc RectCount
    bne .OvM1Row                ; row never wraps to 0
.OvM1block:
    ; Blocked by the M1 cell: run the hot check too — convert emits the
    ; M1 patch cell as a hot rect on the hot band (mask $00, never dies
    ; with a wall), so touching the block on a hot band = death, exactly
    ; like a hot PF wall. Off-band / non-hot: body finds no rect → sec,
    ; still blocked. b4 (strip destroyed) never reaches here (.OvM1no).
    ; Phase 5 key: touching the M1 strip (left door) while KeyHeld removes
    ; it (b4) — touch, not mere possession.
    lda LevelStartRoom
    bmi .OvM1unlock
    jmp HotOverlapFlag          ; C=1 contract; body sets Temp b7 on hot hit
.OvM1unlock:
    lda EnemyDeadMask
    ora #$10                    ; b4 = M1 strip (left door) destroyed
    sta EnemyDeadMask
    clc
    rts                         ; passable (bank0 caller)
.OvM1no:
    clc
    rts

; ------------------------------------------------------------------------------
; OvShutBand — right-column strip on the PHMOverlay miss path. Entered from
; PHMOverlay .OvBand (right-column + player-band overlap). MetaB b7 marks a
; LOCKED_DOOR right strip; b7 clear is a plain D6 strip. A plain strip is
; solid. A door strip is solid until the key is held, then the touch
; destroys it (EnemyDeadMask b3) and the walk passes (Phase 5).
; Kill follows the VISIBLE right-half block only (async ruling 2026-10-14 —
; no left mirror). The retired vcrunch kill test is gone.
; ------------------------------------------------------------------------------
OvShutBand:
    ldx CollisionCellY
    lda OvHead,X                ; bits >= row
    ldx CollisionEndY
    and OvTail,X                ; bits <= row
    and LineCount               ; active-band mask (b0-2)
    beq .OSBm1                  ; not in a painted band → M1 strip test
    lda RoomPF0Hi               ; staged MetaB ($9A)
    bpl .OSBsolid               ; b7=0: plain D6 strip → solid
    lda LevelStartRoom          ; KeyHeld?
    bpl .OSBsolid               ; no key → locked (solid)
    lda EnemyDeadMask           ; key held: the touch destroys the strip
    ora #$08                    ; b3 = ball strip (right door) destroyed
    sta EnemyDeadMask
    jmp .OSBm1                  ; passable (strip blanked next B3StageBand)
.OSBsolid:
    sec
    rts
.OSBm1:
    jmp OvM1Block

OvHead:
    .byte 7,6,4                 ; rows 0..2 → mask bits >= row
OvTail:
    .byte 1,3,7                 ; rows 0..2 → mask bits <= row
M1OffTab:                       ; MetaA b0 -> M1 x-offset.
    .byte $ff, $4f              ; B3StageBand has the twin.

; ------------------------------------------------------------------------------
; TitleBcd (2026-10-20) — A = 1-based level number → packed BCD in ScoreTe.
; The title's level display IS the HUD score field, read as packed BCD
; (tens = ScoreTe>>4, ones = ScoreTe&$F); writing raw binary broke the number
; at level 10 (10 → blank glyph). Cold path (title entry / SELECT only).
; Lives in the retired $FB00/$FB37 fill so the pre-pad END stays $FC58.
; Clobbers A/X only; ScoreTh/Hu are zeroed by the caller.
; ------------------------------------------------------------------------------
; $FB00/$FB37 pins RETIRED (repack chunk 4, 2026-10-20): TitleFont lives in
; bank1 and TitleIntro died with the merged title, so both .ds boundaries
; were dead — the overlay cluster now runs straight through them into the
; $FBD0 pin below (EnterRoom tramp twin, still live).
; ------------------------------------------------------------------------------
TitleBcd:
    ldx #0
.TLBcd:                         ; A = level number → X = tens, A = ones
    cmp #10
    bcc .TLBcdDone
    sbc #10
    inx
    bne .TLBcd
.TLBcdDone:
    sta ScoreTe                 ; ones (high nibble 0)
    txa
    asl
    asl
    asl
    asl                         ; tens << 4
    ora ScoreTe
    sta ScoreTe
    rts

; 12 rows per type (Phase 6 tall art). Color rows 8-11 = the type's own
; color (they tint the M1 block on those lines when a room has an M1 patch).
ObjColorTab:
    .byte $1c,$1c,$1c,$1c,$1c,$1c,$1c,$1c,$1c,$1c,$1c,$1c   ; 0 KEY   ($1c yellow)
    .byte $22,$22,$22,$22,$22,$22,$22,$22,$22,$22,$22,$22   ; 1 MOTH  ($22 dark orange)
    .byte $14,$14,$14,$14,$14,$14,$14,$14,$14,$14,$14,$14   ; 2 SPIDER
    .byte $0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e   ; 3 LAMP  ($0e white)
    .byte $0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e,$0e   ; 4 TENTACLE
    .byte $f2,$f2,$f2,$f2,$f2,$f2,$f2,$f2,$f2,$f2,$f2,$f2   ; 5 BAT   ($f2 brown)
    .byte $c4,$c4,$c4,$c4,$c4,$c4,$c4,$c4,$c4,$c4,$c4,$c4   ; 6 SNAKE ($c4 green)
    .byte $54,$54,$4a,$54,$54,$08,$54,$54,$54,$54,$08,$08   ; 7 MINER (hips purple, legs grey)
    .byte $46,$46,$46,$46,$46,$46,$46,$46,$46,$46,$46,$46   ; 8 BOMB  ($46 red)

; ------------------------------------------------------------------------------
; ObjSprites — 4×8 designs, left-aligned bits 7-4 (col0=bit7), 8 rows each.
; Row r displays on scanline RoomY+ObjTop-1+r (ObjTop is RoomY-relative since
; S2.2; .Grp1 checks r = Y-ObjTop where Y = running A0+1). GRP1 write
; latching, same as before.
; Offset = OBJ_* constant; index 0 = blank (object off).
; ------------------------------------------------------------------------------

    .ds $FBD0 - *, 0            ; #22: pin tramp at $FBD0 — bank2's twin
                                 ;   sits at the same address (pin moved from
                                 ;   $FB84 2026-10-13 for PhaseBlink staging,
                                 ;   then $FBC0 → $FBD0 2026-10-14: model2
                                 ;   asym data +49B pushed the bank2 window)
; EnterRoom tramp — body lives in bank2 ($F010, EnterRoomB2).
; bank0 runs `sta $1FF8`; the fetch at $FBD3 comes from bank2's identical
; twin → `jmp $F010` executes in bank2. Body tail = jmp ReturnPad ($FBF8)
; → sta $1FF6 / rts. Saves ~1660c per room change (folds → direct reads).
; A preserved through sta $1FF8; body returns X = EnemyCount.
EnterRoom:
    sta $1FF8
    jmp $F010                    ; EnterRoomB2 — fetched from bank2 twin

; ------------------------------------------------------------------------------
; C3 (2026-10-20): room-exit entry pads. Four `sta $1FF8` halves packed 3 B
; apart (the corridor rule): a bank0 caller `jsr ExitRoomXxx` lands here, and
; the fetch at A+3 comes from BANK2, which holds the matching `jmp ExitXxxB2`
; ($FBDC/$FBDF/$FBE2/$FBE5). The bodies live at bank2's $FC4F cluster; their
; no-exit and post-EnterRoom paths tail-jmp ReturnPad, so the caller's jsr
; frame is popped exactly once. Guards: verify_build.CORRIDOR_PADS +
; check_exit_handlers.
; ------------------------------------------------------------------------------
    .ds $FBD9 - *, 0
CallPad_ExitDown:
ExitRoomDown:
    sta $1FF8                   ; C3: body = bank2 $FC4F cluster
CallPad_ExitUp:
ExitRoomUp:
    sta $1FF8
CallPad_ExitLeft:
ExitRoomLeft:
    sta $1FF8
CallPad_ExitRight:
ExitRoomRight:
    sta $1FF8

    .ds $FBF8 - *, 0            ; TitleSequenceFold / FooterFold /
                                 ;   TitlePlayerFold retired with the intro
                                 ;   movie (merged title, 2026-10-19)
ReturnPad:
    sta $1FF6
    rts

; 2026-10-20 (chunk 4): the corridor pads are SPLIT across the banks, exactly
; like the tail pads below. A bank0 caller runs `sta $1FFx` AT A; the next
; opcode fetch (A+3) already comes from the TARGET bank, which keeps only the
; `jmp` half. Nothing in bank1/bank2/bank3 calls a CallPad (only `jmp
; ReturnPad`), so bank0's `jmp` halves and the target banks' `sta` halves were
; dead bytes — packing the live halves reclaimed 70 B of code (bank0 −33,
; bank1 −37). The whole block is still 0 push / 0 cycles: `sta` changes no
; register, no flag, no stack byte.
;   A=$FBFC sta $1FF7   A+3=$FBFF -> bank1 jmp UpdateBombSound
;   A=$FBFF sta $1FF7   A+3=$FC02 -> bank1 jmp UpdateJetSound
;   A=$FC02 sta $1FF7   A+3=$FC05 -> bank1 jmp BombSndDrop
;   A=$FC05 sta $1FF7   A+3=$FC08 -> bank1 jmp BombSndExplode
;   A=$FC08 RETIRED by C3 (the exit handlers read the conn table in bank2)
;   A=$FC0B sta $1FF7   A+3=$FC0E -> bank1 jmp AddScore
;   A=$FC0E sta $1FF7   A+3=$FC11 -> bank1 jmp IsRoomDark
;   A=$FC11 sta $1FF7   A+3=$FC14 -> bank1 jmp SetRoomDark
;   A=$FC14 sta $1FF7   A+3=$FC17 -> bank1 jmp UpdateLaserSound
;   A=$FC17 sta $1FF9   A+3=$FC1A -> bank3 jmp BuildColupF (record stream)
;   A=$FC1A sta $1FF7   A+3=$FC1D -> bank1 jmp BombMarkWalls ($FB10)
;   ($FC1D CallPad_SelectObject RETIRED by A1 2026-10-20: SelectActiveObject
;    is back in bank0, so the VBL calls it directly.)
; Guard: verify_build.check_callpads pins each A and asserts the ROM bytes of
; BOTH halves (bank0 sta / target-bank jmp operand == its .lst label).
CallPad_UpdateBombSound:
    sta $1FF7
CallPad_UpdateJetSound:
    sta $1FF7
CallPad_BombSndDrop:
    sta $1FF7
CallPad_BombSndExplode:
    sta $1FF7
    .byte 0,0,0                 ; $FC08: CallPad_GetConnIdx retired by C3
CallPad_AddScore:
    sta $1FF7
CallPad_IsRoomDark:
    sta $1FF7
CallPad_SetRoomDark:
    sta $1FF7
CallPad_UpdateLaserSound:
    sta $1FF7
CallPad_BuildColupF:
    sta $1FF9                   ; C7: body lives in bank3 now ($F9D9 cluster —
                                ;   it walks the shape/extras stream there)
CallPad_BombMarkWalls:
    sta $1FF7                   ; S5.2: body lives in bank1 ($FB10)
    .byte 0,0,0                 ; $FC1D-$FC1F: CallPad_SelectObject retired by
                                ;   A1 (SelectActiveObject is back in bank0, so
                                ;   the VBL jsrs it directly). The 3 dead bytes
                                ;   stay: CallPad_LoadLevel MUST remain at
                                ;   $FC20, because bank2's $FC23/$FC26 halves
                                ;   are pinned to that address.

; ------------------------------------------------------------------------------
; C2 (2026-10-20): LoadLevel moved to bank2 ($F640). Entry pad + return half.
; ENTRY: a bank0 caller `jsr LoadLevel` lands on `sta $1FF8` here; the opcode
; fetch at $FC23 then comes from bank2 = `jmp LoadLevelB2` (split-pad rule).
; The three bank0 bytes at $FC23-$FC25 are NEVER fetched (bank2's jmp lives
; there) — zero-filled so nothing can branch into them by accident.
; RETURN: the body's tail is `jmp $FC26`; bank2's $FC26 holds `sta $1FF6`, so
; the fetch at $FC29 lands on the `jmp LF_B0Tail` below (live bank0 half).
; Guard: verify_build.check_callpads (entry pad) + check_loadlevel_tramp
; (return half + this stub's shape).
; ------------------------------------------------------------------------------
CallPad_LoadLevel:
LoadLevel:
    sta $1FF8                   ; C2: body = bank2 $F640 LoadLevelB2
    .byte 0,0,0                 ; $FC23-$FC25 — bank2's `jmp LoadLevelB2`

    .byte 0,0,0                 ; $FC26-$FC28 — bank2 runs `sta $1FF6` there
    jmp LF_B0Tail               ; $FC29 — fetched bank0-side after the swap
; Drop-in tail, kept in bank0 (0 extra jsr levels, 0 pushes): EnterRoom is the
; normal bank0 tramp, and DropArm's rts still pops the original caller frame.
LF_B0Tail:
    lda LevelStartRoom
    jsr EnterRoom
    lda LevelStartX
    sta RoomX
    lda LevelStartY
    sta RoomY
    jmp DropArm

    .ds $FC49 - *, 0             ; pin (main growth past $FC49 = build error)
MothExitPad:
    sta $1FF6                   ; select bank0 (executed from bank2's copy)
    jmp UE_Next                 ; resume dispatch loop (bank0 half)

    .ds $FC4F - *, 0            ; bank0↔bank1 CallPad slot (refactor_v4)
; 2026-10-20: the three tail pads are SPLIT across the banks, not twinned.
; A bank0 caller runs the `sta $1FF7` AT A; the next opcode fetch (A+3) comes
; from bank1, which keeps ONLY the `jmp`. Bank0's `jmp` half and bank1's `sta`
; half were dead bytes (nothing calls a tail pad from bank1). Packing the live
; halves + deleting the caller-less CallPad_Overscan reclaimed 15 B here:
;   A=$FC4F sta $1FF7   A+3=$FC52 -> bank1 jmp TitleSelect
;   A=$FC52 sta $1FF7   A+3=$FC55 -> bank1 jmp TitleBand
;   A=$FC55 sta $1FF7   A+3=$FC58 -> bank1 jmp MusicTick
; Guard: verify_build.check_callpads runs this A / A+3 contract byte-for-byte
; (the $FBF8-$FC48 corridor above stays fully byte-identical).
CallPad_TitleSelect:
    sta $1FF7
CallPad_TitleBand:
    sta $1FF7
CallPad_MusicTick:
    sta $1FF7

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
    ; TAIL-jmp LoadLevel (bugs.md #29 Class B, 2026-10-11). The old
    ; `jsr LoadLevel / zeros / rts` left FOUR jsr slots live when LoadLevel
    ; reached `jsr EnterRoom`: CheckEnemyHit/timer death paths ran
    ; main->jsr CEH->jmp LoseLife->jsr ReloadLevel->jsr LoadLevel->
    ; jsr EnterRoom at SP=$F7, so the return address sat on $F6/$F7
    ; (BombX/BombTimer), EnterRoomB2's `sta BombTimer` zeroed the pushed
    ; PCH, and ReturnPad's rts popped ($00<<8|BombX)+1 = $009A -> ZP
    ; executed as code -> $F008 pad -> GameStart REBOOT to title (the
    ; SIM_EXIT=down f265 296-line crash frame + the title-264 family).
    ; With the tail-jmp the slot count drops by one: EnterRoom's return
    ; lands on $F8/$F9 (stack-only cells) on every death path.
    ; The old post-code (vy/JetPower zeros + rts) was unreachable; DELETED
    ; 2026-10-16 (intro music) — the $FDD8 blast-tramp pin below absorbs the
    ; shift, so the twins stay put. DropArm zeroes vyLo/vyHi/PlayerYSub itself
    ; (JetPower=4 stays through the drop-in flutter — identical to the .LLStay
    ; path). LoseLife's `sec` still runs (DropArm's rts pops the jsr ReloadLevel
    ; slot back into LoseLife).
    jmp LoadLevel

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
    lda #$FF
    sta Hover                   ; bugs.md #1 + user rule 2026-10-21: WAIT for
                                ; the player's first input ($FF = armed, grace
                                ; not started); the 1.5 s grace starts on the
                                ; first direction/attack press.
                                ;   (LoadLevel clears it on a stage-entry reset)
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

; ------------------------------------------------------------------------------
; CEH_Key — type-6 key pickup (docs/feature_tiles_plan.md Phase 5): latch
; KeyHeld ($A7 b7) and mark the key slot dead so it vanishes, with NO life
; loss. X = EnemyIndex (set by CheckEnemyHit). Post-pad leaf (bank0 pre-pad
; is at its 1B limit); reached from CheckEnemyHit's type-6 dispatch by jmp
; (out of `beq` range). KEY is one per level, so KeyHeld is a single bit.
; LevelStartRoom b7 resets when LoadLevel rewrites $A7 (:1875) before its own
; read at :1922, so no reader mask is needed; KeyHeld survives room changes
; and normal deaths, resets on game-over reload.
; ------------------------------------------------------------------------------
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
; LoseLifeBand — life path + respawn just above the water strip.
; The shift MUST happen BEFORE LoseLife: its stay path tail-jumps DropArm,
; which freezes RoomY as the drop destiny. Shifting after the call was dead
; code — a water death respawned at the death Y (inside the strip, >= 125) and
; the player died again on landing, unable to fly out (user report 2026-10-21).
; The shift is one tile (spec: -= 12, not the whole band): the band check
; tests the sprite ORIGIN (RoomY >= 125), so 125 -> 113 clears the strip.
; Tail-jmps LoseLife (never returns here): its exhausted path rts straight to
; CheckBandTouch.
; ------------------------------------------------------------------------------
LoseLifeBand:
    lda RoomY
    sec
    sbc #12                     ; one tile up
    bcs .LLBstore
    lda #0                      ; near the top: clamp at 0
.LLBstore:
    sta RoomY
    jmp LoseLife                ; freezes this Y as DropTarget and drops in


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
    cmp #$FD
    bcs .DATitle              ; sentinels $FF title / $FE tally → static
                              ;   pose (real fall Y ≤ $BF → C=0 below; $FE
                              ;   tally cleared to 0 by TallyWork before its
                              ;   LoadLevel — same-size swap 2026-10-06)
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
    sta LaserX
    clc
    rts
.DATitle:
    ; Title: player already placed at level start by LoadLevel. Hide all
    ; GRP1 objects (EnemyCount=0 → SelectActiveObject's no-object path
    ; blanks ObjBase/ObjTop) and drop the miner slot so SELECT/RESET reloads
    ; refresh them via EnterRoom. HUD score = level+1 ("000001" = level 0).
    lda #0
    sta EnemyCount
    lda #$FF
    sta LevelMinerRoom          ; ROOM_NONE: no miner slot, no pickup
    ; No beam on the title: band 0 is the CAVE .Line now, which re-enables
    ; ENAM0 from PlayerColTable bit1 & LaserState. Clear held+gate (b7/b1) only —
    ; LASER_KEEP keeps b0 and the rooms 4-7 dark mask, so a dark-room
    ; preview still renders dark.
    lda LaserState
    and #LASER_KEEP
    sta LaserState
    lda Level
    clc
    adc #1                      ; 1-based level number (the title SELECT)
    jsr TitleBcd                ; A → packed BCD in ScoreTe (bank0 fill)
    lda #0
    sta ScoreTh
    sta ScoreHu
    clc
    rts

DropStep:
    lda DropTarget
    beq .DSdone                 ; idle (target 0 = nothing to fall)
    cmp #$FF
    beq TitleWork               ; merged title = stage preview + level select
    cmp #$FE
    bne .DSfall
    jmp TallyWork               ; level-bonus tally sentinel (bank2 step)
.DSfall:
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

; DropSpeedTable moved to the pre-pad free region ($F9FB) — post-pad before
; the $FDE1 pin was full (bugs.md #1 Hover needs the room). Read is abs,Y, so
; its address is irrelevant to DropStep.

; ------------------------------------------------------------------------------
; TitleWork — merged title/level-select screen (DropTarget = $FD sentinel,
; dispatched from DropStep every frame). The TitleKernel shows the logo, the
; selected level number (digits band) and the credits; the theme plays here.
; No gravity/enemies/sound beyond the music (frame is title-owned; timer
; frozen). SELECT cycles Level, RESET starts the game at the selected level.
;   SELECT (SWCHB b1, active-low EDGE) → jsr TitleSelect (fill): level+1,
;          wrap → 000001, reload room 0 (swallow removed 2026-10-07, 8b —
;          the intro exit ate the first press and made #2 read as dead)
;   RESET  (SWCHB b0, active-low EDGE) → score 000000, LoadLevel tail arms
;          the real drop-in → gameplay starts
; ($FD reaches here directly — merged title, 2026-10-19.)
; StepsLeft = previous SWCHB sample (physics is skipped on title, so it is
; title-owned; the first play frame rewrites it as the step budget).
; Console switches are read again after any jsr (LoadLevel clobbers X/Y/A).
; ------------------------------------------------------------------------------
TitleWork:
    ; --- SELECT edge (TitleSelect, fill region) ---
    jsr CallPad_TitleSelect
    bcc .TWselDone             ; C=0: no edge
    jsr LoadLevel              ; preview + HUD score follow the selected level
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
TitleTailAudio:                 ; tail: TitleWork falls in (no rts)
    lda DropTarget              ; merged title ($FF): music owns AUD0/AUD1,
    cmp #$FF                    ;   no bomb fuse/tick on title frames
    beq .TWmusic
    bne .TWnoTick               ;   BombTick's blast side effects on titles
    jsr BombTick
.TWnoTick:
    jsr CallPad_UpdateBombSound
    lda #0
    sta AUDV1
    beq .TWwait                 ; A=0 -> always taken
.TWmusic:                       ; title: music wins the audio regs
    jsr CallPad_MusicTick       ;   wins the audio registers every frame
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
    ; --- SELECT or RESET held → back to the old title / level-select screen
    ;     ($FF = first room + HUD count). Gate: DropTarget == 0 EXACTLY
    ;     (idle/landed). Sentinels ($FD/$FF/$FE) skip via ≠0; a DROP-IN
    ;     fall (Y≠0) also skips — so the press that STARTED the game (held
    ;     through TitleWork RESET, level-triggered here) cannot bounce back
    ;     to the title while falling (bounce-fixed 2026-10-06). Residual:
    ;     RESET held past LANDING still re-fires — press must be released
    ;     before the drop-in finishes. ---
    lda DropTarget
    bne .REYRts                 ; not idle: not ours
    lda SWCHB
    sta StepsLeft               ; latch so TitleWork sees "held" (no re-fire)
    and #%00000011              ; SELECT b1 + RESET b0 (level-triggered,
    cmp #%00000011              ;   same style as the old SELECT-only check)
    beq .REYRts                 ; neither pressed
    lda #$FF
    sta DropTarget              ; merged title sentinel ($FF, 2026-10-19)
    jsr LoadLevel               ; reload the level-start room for the preview
    pla                         ; drop OUR return address (LoadLevel already
    pla                         ;   popped its own) — tail into TitleWork
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

; ------------------------------------------------------------------------------
; BombEnemyBlast — bank2 entry tramp ($FDD8, lamp-safe S9 2026-10-07): the
; BombTick `jsr` lands here (bank0), `sta $1FF8` switches to bank2, the `jmp`
; is fetched from bank2's byte-identical mirror at this same address and
; lands on the body at $FD87 (the lamp type-check reads enemy records that
; live in bank2). Body tail-jmps ReturnPad ($FBF8); A = 1 kill (BombTick
; awards +50 — pads cannot nest), 0 none. Old inline body ($F87F, 66B)
; deleted: the region re-packs into the gap before the $FBD6 fold pin
; (pre-pad headroom stays 1B — pins absorb upstream shrink, not the org).
; TWIN: bank2.asm mirrors these exact 6 bytes at $FDD8 (the pad after
; .HOVdone). The PickPlayerFrame pin that used to absorb the size is gone
; (retired 2026-10-20); the $FC49 / $FBF8 pins bound this block today.
; ------------------------------------------------------------------------------
    .ds $FDD8 - *, 0            ; pin: bank2's blast-tramp mirror is at $FDD8
BombEnemyBlast:
    sta $1FF8
    jmp $FD87                   ; BombEnemyBlastBody (bank2.lst — after
                                ;   .HOVfeature; NOT in the TitleJetColors
                                ;   span)
                                ;   (2026-10-13: was $FD79 — crush-kill b6
                                ;   latch + feature gate pushed +14; same day
                                ;   was $FD6C — .HOVfeature pushed +13; 2026-
                                ;   10-10: was $FD6B — 1-byte stale operand =
                                ;   entry mid-instruction at `lda EnemyCount+1`;
                                ;   garbage path's `inc $4A,X` set wall bits
                                ;   via $CA)

; ------------------------------------------------------------------------------
; PickPlayerFrame tramp RETIRED (2026-10-20, repack chunk 1): the body now
; lives in bank0 ($F9F5 region), so the VBL `jsr PickPlayerFrame` resolves
; in-bank and the 6-byte `sta $1FF8 / jmp $F3C4` pad plus its bank2 mirror
; are gone. PlayerWalkA/B flow up to $FDDE (nothing pins them any more).
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; PlayerWalkA/B — dedicated ground-walk frames (sprites.png 2026-10-03,
; extracted pixel-exact; torso rows 0-6 identical to the jet pair).
;   A = boots apart (stride, rows 10-11 spread to cols 2+6 / 1+6)
;   B = boots together (passing pose, rows 10-11 = cols 3+4)
; Legs rows 7-9 identical in both — only the boots move. Standing forces
; PlayerSpriteA; walk cycle alternates A<->B every 8 frames (EnemyRamP&$08,
; 16-frame full cycle) while grounded + L/R held.
; ------------------------------------------------------------------------------
PlayerWalkA:
    .byte %00111100             ; row 0 torso (sprites.png 2026-10-03)
    .byte %01111110             ; row 1
    .byte %01111100             ; row 2 — yellow face
    .byte %01111110             ; row 3
    .byte %01111100             ; row 4 — grey pack
    .byte %11111110             ; row 5
    .byte %11111110             ; row 6
    .byte %00111110             ; row 7  legs
    .byte %00111110             ; row 8
    .byte %00010100             ; row 9
    .byte %00100010             ; row 10 boots apart (spread)
    .byte %01000010             ; row 11 boots apart

PlayerWalkB:
    .byte %00111100             ; row 0 torso (sprites.png 2026-10-03)
    .byte %01111110             ; row 1
    .byte %01111100             ; row 2 — yellow face
    .byte %01111110             ; row 3
    .byte %01111100             ; row 4 — grey pack
    .byte %11111110             ; row 5
    .byte %11111110             ; row 6
    .byte %00111110             ; row 7  legs
    .byte %00111110             ; row 8
    .byte %00010100             ; row 9
    .byte %00011000             ; row 10 boots together (passing)
    .byte %00011000             ; row 11 boots together




    .ds $FE00 - *, 0            ; ObjColorTab $FE00-$FE47, ObjSprites $FE48-$FE8F:
    .ds $FE90 - *, 0            ; ObjColorTab/ObjSprites moved to the
                                 ; $F744 fill (Phase 6: tall art). The $FE8F
                                 ; end is kept so FoldIndirect stays at $FE90.
                                 ; BOTH same-page 4c fetches (verify guards);
                                 ; end $FE8F -> HOF tramp $FE90 (shifted +$10,
                                 ; mirrors+HOF_ENTRY/LHT_ENTRY synced)
; ------------------------------------------------------------------------------
; ObjColorTab — per-scanline GRP1 object colors, stride 8 = ObjSprites
; stride; indexed by the same X = ObjBase + r in .Grp1 at $FE00 (4c, same
; page for all 72 B — the passing +7 probe's exact cycle sum). Row colors
; per OBJ_* slot: type color x8 (matches EnemyColorTable /
; SelectActiveObject frame colors — no visual change for enemies/lamp/bomb);
; MINER slot = miner.png purple/pink/grey -> nearest NTSC $54/$4A/$08.
; NOTE: dark rooms no longer force grey objects — the frame-level $0A write
; is overridden per row (no budget for a dark skip flag; see .Line probe).
; ------------------------------------------------------------------------------

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
    .ds $FE96 - *, 0            ; S5.4 LHT entry tramp (byte-identical w/ bank2,
                                ; guard: check_moth_tramp — shifted +$10)
LaserHitTest:
    sta $1FF8                   ; select bank2
    jmp $FF00                   ; bank2 LaserHitTestBody (dead in bank0; guard
                                ;   pins operands == bank2.lst label)

; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; TallyWork — level-bonus count-up (user spec 2026-10-02): reaching the miner
; freezes the frame (dispatch bypasses input/physics/enemies via DropTarget
; $FE), bank2 TallyEntry adds +50 every 4 frames and writes the coin tone
; (every 200 pts); when TallyTicks hits 0 the done path advances the level
; exactly like the old CheckMinerPickup tail, then rejoins OverscanAudio.
;   Event bits in A (through ReturnPad sta/rts): b0 = add 50, b2 = done.
;   Tail mirrors TitleWork: UpdateBombSound holds the coin (BombSnd>0), jet
;   muted, own INTIM wait -> StartFrame: timer block skipped = frozen scene.
; Lives in the $FE8C LHT..moth fill (bank0 has no pre-pad headroom).
; ------------------------------------------------------------------------------
TallyWork:
    jsr TallyTramp              ; A = event (bank2 TallyEntry step)
    tay
    and #1
    beq .TNoScore
    lda #$50                    ; BCD +50 per tick (pack is $50 exactly)
    jsr CallPad_AddScore
.TNoScore:
    tya
    and #4
    beq .TLive
    inc Level                   ; --- done: advance (old CheckMinerPickup tail)
    lda Level
    cmp #LEVEL_COUNT
    bne .TNotWrap
    lda #0                      ; wrap past last level
    sta Level
.TNotWrap:
    lda #0
    sta DropTarget           ; clear $FE BEFORE LoadLevel — DropArm's new
                             ;   `cmp #$FD / bcs` treats ≥$FD as sentinel
                             ;   pose ($FE must take the real-fall path)
    jsr LoadLevel
    lda #120                    ; reset timer for new level
    sta BarLevel
    lda #60
    sta TickCounter
    jmp OverscanAudio           ; normal sounds + timer resume
.TLive:
    jsr CallPad_UpdateBombSound ; hold/silence ch0 for the coin blip
    lda #0
    sta AUDV1                   ; jet muted (UpdateJetSound skipped)
.TWait:
    lda INTIM
    bne .TWait
    jmp StartFrame



    .ds $FEE7 - *, 0            ; bank0↔bank1 CallPad (leaf_move_plan Step 0)
CallPad_MothYDerive:
    sta $1FF7
    jmp $F038

    .ds $FEF0 - *, 0            ; fill tramp..moth gap (drift-proof)
UE_MothTramp:
    sta $1FF8                   ; select bank2
    jmp $F110                   ; bank2 MothRoutine (dead in bank0; guard pins
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
; Input: A = horizontal position (0-159 color clocks); drawn = [A-7, A]
;        X = object selector (0 = HMP0/RESP0 player, 1 = HMP1/RESP1 object,
;            2 = HMM0/RESM0 laser, 4 = HMBL/RESPBL ball — bank1 bar already
;            uses 4; HMP0+4=$24=HMBL, RESP0+4=$14=RESPBL)
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
; LaserInput — contact missile (redesign 2026-10-08, replaces the S3 sweep):
; the beam is ONE 8px bar that LEAVES the EYE and travels +/-4px/frame toward
; the facing until contact, then resets to the eye (single missile, KISS —
; user spec: no piercing, no HERO comparison needed).
;   press edge (b7 held, b6 prev): LaserX = eye  (right RoomX-1 = nose,
;                                                left  RoomX-4)
;   held frame: LaserX +/-4; LaserX >= 160 (right edge OR left underflow
;     wrap) -> reset to eye (unsigned check catches both)
;   contact (bank2 LaserHitTestBody): A = 0 continue / $50 kill (+score,
;     dead bit set in body) / 1 lamp (SetRoomDark) / 2 wall tip -> all three
;     contact kinds reset LaserX = eye BEFORE positioning (missile consumed;
;     tip-in-wall never draws: contact frame restarts at the eye; PF has
;     priority over M0 anyway).
;   release: b7/b1 cleared in the prologue, HMM0 = 0; LaserX kept (next
;     press edge re-anchors).
; PIXEL MODEL (unchanged): SetObjectXPos arg A -> drawn M0 = [A-7, A].
; LaserState: b7 held, b6 prev (press edge), b5-2 dark, b1 = .Line gate,
; b0 = rearm (contact consumed last frame — re-test the eye next frame)
; (PlayerColTable bit1 shares b1 — ENAM0 = bit1 & LaserState; the old
; LaserBeamOn $02 byte now holds LaserX, there was no free ZP byte).
; S5.4: kill/lamp/wall ACTIONS run here (pad body returns only A).
; Overscan: VBLANK on, end waits on TIM64T — SetObjectXPos's WSYNC costs 1
; of 30 lines. Temp (joystick) intact. Lives after $FF20 (pre-$FF00 full).
; ------------------------------------------------------------------------------
LaserInput:
    ldx LaserState             ; X = old state (b7 held, b6 prev, b5-2 dark)
    txa
    and #LASER_KEEP            ; keep dark bits + b0 rearm (else this store
    sta LaserState             ; wipes them — inc at contact must survive)
    txa
    and #LASER_HELD
    lsr                         ; old held (b7) -> new prev (b6)
    ora LaserState              ; prev in b6; b7/b1 cleared for this frame
    sta LaserState
    lda INPT4                   ; active-low fire button, D7: 0 = pressed
    bpl .LaserFire              ; pressed: arm + travel (released sits right
                                ; below — moved here so the cap code could
                                ; not push .LaserReleased past bmi's ±127)
.LaserReleased:
    lda #0
    sta HMM0                    ; HMOVE re-applied stale fine offset
                                ; otherwise -> bars slid across screen
    rts                         ; LaserX kept; next press edge re-anchors
.LaserFire:
    lda LaserState
    ora #LASER_ON               ; b7 held + b1 armed (kernel .Line gate)
    sta LaserState
    txa
    and #LASER_HELD
    beq .LaserInit              ; press edge: (re)start at the eye
    ; --- rearm (b0): last frame a contact consumed the missile — re-test
    ; the EYE instead of stepping. Flush hold: eye sits mid-tile and the +4
    ; step would jump out of the 8px wall with no candidate ever inside it
    ; (pass-through, 2026-10-10). dec clears b0; bne .LaserInit: state ≠ 0
    ; here (b7 held from the ora above). Open-hold cadence alternates
    ; travel-consume / eye-retest = 1 LWC per frame, same as before.
    lda LaserState
    and #LASER_REARM
    beq .LAdvStep
    dec LaserState
    bne .LaserInit
    ; --- travel: +/-4 px toward the facing (PlayerDir live), capped at the
    ; old S3 sweep extent (SweepOff max 16: right tip <= RoomX+20, left
    ; floor max(RoomX-20,0)) — past the cap restarts at the eye, the
    ; triangle-loop feel of the sweep (user: beam "moved way beyond the
    ; limit"). RectCount = free scratch (LWC re-owns it for its row walk).
.LAdvStep:
    ldy PlayerDir
    lda LaserX
    clc
    adc StepDelta,y             ; dir 0 = +4, dir 1 = -4 (table after eye)
.LAdvS:
    sta RectCount               ; candidate (not committed yet)
    cmp #160                    ; right edge >=160 OR left underflow wrap
    bcc .LAdvCap
    jmp .LaserInit
.LAdvCap:
    lda PlayerDir
    bne .LAdvCapL
    lda RoomX
    clc
    adc #20                     ; old max tip = RoomX + 4 + SweepOff(16)
    cmp RectCount
    bcs .LAdvKeep               ; cap >= cand -> within old laser extent
    jmp .LaserInit
.LAdvCapL:
    lda RoomX
    sec
    sbc #20
    bcs .LAdvCapLs
    lda #0                      ; old left clamp floor (extent >= 0)
.LAdvCapLs:
    cmp RectCount               ; cap vs cand
    beq .LAdvKeep
    bcc .LAdvKeep               ; cap < cand -> cand still above floor
    jmp .LaserInit
.LAdvKeep:
    lda RectCount
    sta LaserX
    jmp .LaserGo                ; committed: skip the eye restart
.LaserInit:
    jsr .LaserEye               ; edge/offscreen: restart at the eye
.LaserGo:
    lda LaserX
    sta CollisionX              ; cur arg for LaserHitTest (drawn [A-7,A])
    jsr LaserHitTest            ; A = 0 / $50 kill / 1 lamp / 2 wall
    beq .LaserPos               ; no contact: keep travelling
    cmp #$50
    beq .LaserKill
    cmp #2
    beq .LaserContact           ; wall CONSUMES the missile (user 2026-10-10):
                                ;   same as kill minus score — restart at
                                ;   the eye THIS frame, buzz keeps (b7).
                                ;   #9's blank + the wall-center hold clamp
                                ;   both superseded: a contact missile is
                                ;   consumed by walls. No hold state, no
                                ;   cap reorder, no pass-through possible.
    jsr CallPad_SetRoomDark     ; lamp crash = player-body touch (no kill)
    jmp .LaserContact
.LaserKill:
    jsr CallPad_AddScore        ; A = $50 BCD (dead bit already set in body)
.LaserContact:
    jsr .LaserEye               ; consumed -> restart at the eye THIS frame
    inc LaserState              ; b0 rearm: next held frame re-tests the eye
                                ; (b0 was 0: travel only runs with b0 clear,
                                ; rearm dec'd it before this init) — flush
                                ; hold otherwise steps +4 out of the tile
.LaserPos:
    lda LaserX
    ldx #2                      ; selector 2: RESP0+2=RESM0, HMP0+2=HMM0
    jsr SetObjectXPos           ; drawn M0 = [LaserX-7, LaserX]
    rts

; Eye spawn point. Right clamped to 159 (TIA position past 159 is
; unverified for SetObjectXPos); left >= 0 because RoomX >= PLAYER_MIN_X=4.
.LaserEye:
    lda PlayerDir
    bne .LEyeL
    lda RoomX
    clc
    adc #4
    cmp #160
    bcc .LEyeS
    lda #159
.LEyeS:
    sta LaserX
    rts
.LEyeL:
    lda RoomX
    sec
    sbc #4
    sta LaserX
    rts

StepDelta:                      ; travel step per PlayerDir (0=right, 1=left)
    .byte 4, 252

    .ds $FFE6 - *, 0            ; pin TallyTramp (was the BeamMask slot)
                                 ; freed 12B here — drift must not move it)
; ------------------------------------------------------------------------------
; TallyTramp ($FFE6, byte-identical with BANK1 now — the body moved there in
; repack chunk 3, 2026-10-20; guard: verify_build). bank0 jsr's here
; (CheckMinerPickup arm / TallyWork step): `sta $1FF7` selects bank1, then the
; jmp operand is fetched from bank1's image at the same PC (FoldIndirect
; discipline). The bank1 body tail-jmps ReturnPad ($FBF8) -> rts back to the
; bank0 jsr. Ends $FFEB — $FFF2-$FFF9 stay fill (F6 hotspot mirrors).
; ------------------------------------------------------------------------------
TallyEntry = $F44F              ; bank1 TallyEntry — operand must match label
TallyTramp:
    sta $1FF7
    jmp TallyEntry

; ------------------------------------------------------------------------------
; HotOverlapFlag — bank3 entry tramp (C7 2026-10-20: the hot walk went back
; to bank3 with the shape/extras stream it reads). Moved off $FE90 into the
; 6-byte gap after TallyTramp. bank0 executes `sta $1FF9`; the `jmp` at +3 is
; fetched from bank3's image at $FFEF (guard: check_moth_tramp).
; ------------------------------------------------------------------------------
    .ds $FFEC - *, 0
HotOverlapFlag:
    sta $1FF9                   ; select bank3 (record stream lives there)
    jmp $F8F8                   ; bank3 HotOverlapBody (synced by verify_build)
    .ds $FFF2 - *, 0            ; $FFF2-$FFF9 stay fill (F6 hotspot mirrors)

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
