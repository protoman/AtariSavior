  processor 6502

; The game must be assembled from the REPO ROOT: DASM resolves all includes
; against the current working directory, so both the support headers below and
; the generated/ room data further down are given paths relative to the root.
    include "comparison/lo-a-rad-dragon/vcs.h"
    include "comparison/lo-a-rad-dragon/macro.h"

; ==============================================================================
; SAVIOR 2600 - bank0 (F6 16K cartridge, physical offset $0000)
; ==============================================================================
; Bank0 carries ALL game code and ROM data (kernel, room tables, sprite/color
; tables). Bank1 is the start screen (a self-contained F6 menu ROM, see
; bank1.asm); banks 2-3 are placeholders whose startup stubs just switch to
; this bank (see AGENTS.md "Bankswitching - F6").
;
; Frame timeline (262 scanlines, locked by the overscan TIM64T, OVSCAN_TIME):
;   VSYNC        3 lines
;   Positioning  3 lines   SetObjectXPos for GRP0 (player) + GRP1 object, HMOVE
;   VBLANK      35 lines   blanked wait
;   Kernel      192 lines  12 playable tile rows x 12 scanlines + 4-row HUD band
;   Overscan     29 lines  input, movement, room exits, miner pickup, enemy hits
;
; Rendering model (identical to HERO / Adventure):
;   - REFLECTED playfield (CTRLPF D0=1) + playfield priority (D2=1). The kernel
;     writes ONE PF0/PF1/PF2 triple per 12-scanline tile row; the TIA mirrors
;     the 20-bit half into a full-screen 40-cell cave, and the player sprite is
;     hidden behind solid walls by playfield priority (like HERO).
;   - Rooms are 20 columns x 12 rows; each tile is one playfield bit (4 color
;     clocks = one screen cell) wide and 12 scanlines tall.
;   - GRP0 = player (a plain square), GRP1 = the shared per-frame object slot
;     (the miner or one enemy) rotated by SelectActiveObject at 60/N fps.
;
; Data flow (build-time, run by build_game_f6.sh):
;   rooms/level_XXX.json -> tools/convert_level.py -> generated/*.asm
;   Per-level tables + LevelDataTable are included at data start ($f600) and
;   indexed at runtime through LoadLevel / EnterRoom.
;
; Zero-page is organized in three groups (see the block below):
;   - current room render/collision scratch
;   - the active level's table pointers and wall colors
;   - the GRP1/flicker object bookkeeping
;
; Full architecture and hardware references: AGENTS.md
; ==============================================================================

; ------------------------------------------------------------------------------
; Setup variables
; ------------------------------------------------------------------------------

  seg.u Variables
    org $80

RoomX           byte
RoomY           byte
PlayerDir       byte            ; sprite eye facing: FACING_RIGHT (0) or FACING_LEFT
vyLo            byte            ; Y velocity low byte (subpixel; signed 16-bit, + = down)
vyHi            byte            ; Y velocity high byte (whole pixels per frame, signed)
PlayerYSub      byte            ; subpixel accumulator for Y velocity integration
JetPower        byte            ; jet thrust 0..JET_MAX; ramps +1/frame while Up is held
StepsLeft       byte            ; per-frame Y pixel steps remaining (vertical physics loop)
Scanline        byte
LineCount       byte
MapPtrLo        byte
MapPtrHi        byte
CollisionX      byte
CollisionCellX  byte
CollisionCellY  byte
CollisionEndX   byte
CollisionEndY   byte
RoomPFDataLo    byte            ; current room's TilePF0 table address
RoomPFDataHi    byte
RoomRowMapLo    byte            ; current room's RoomRowLo table address
RoomRowMapHi    byte
RoomNo          byte            ; current room index into RoomDataTable
Level           byte            ; current level index (0 = first level)
LevelDataLo     byte            ; pointer into LevelDataTable (LevelDataHi+LevelDataLo)
LevelDataHi     byte
LevelPFDataLo   byte            ; active level's RoomDataTable base address
LevelPFDataHi   byte
LevelConnLo     byte            ; active level's RoomConnections base address
LevelConnHi     byte
LevelWallColor  byte            ; COLUPF byte for the active level's walls (rows 0-3, 8-11)
LevelWallColor2 byte            ; second COLUPF byte (rows 4-7)
LevelMinerRoom  byte            ; room index holding the miner for the active level
MinerX          byte            ; miner spawn (logical room pixel coords)
MinerY          byte
LevelEnemyLo    byte            ; active level's RoomEnemies table base (per-room ptr/count)
LevelEnemyHi    byte
EnemyDataLo     byte            ; current room's enemy data base address (first enemy record)
EnemyDataHi     byte
EnemyCount      byte            ; number of enemies in the current room (0..MAX_ENEMIES)
FlickerFrame    byte            ; GRP1 slot index for this frame (0..ObjectCount-1)
ObjectCount     byte            ; Enemies + (1 if this is the miner's room)
ActiveObjectOn  byte            ; 1 when the current room owns the GRP1 object this frame
ActiveObjectX   byte            ; GRP1 object X (room pixel 0..159): miner or selected enemy
ActiveObjectY   byte            ; GRP1 object Y (scanline 0..191)
EnemyIndex      byte            ; selected enemy's index within the room's enemy data
Temp            byte            ; general scratch (level*stride in LoadLevel)
LevelStartRoom  byte            ; active level's origin room (spawn + enemy-hit teleport)
LevelStartX     byte            ; active level's origin X
LevelStartY     byte            ; active level's origin Y
EnemyLoopCount  byte            ; CheckEnemyHit loop counter
GameMode        byte            ; 0 = start screen (bank1), nonzero = game (bank0)

; ------------------------------------------------------------------------------
; Setup consts
; ------------------------------------------------------------------------------
PLAYER_HEIGHT = 8
PLAYER_WIDTH = 4
; The visible sprite is drawn OFF SET LEFT of logical RoomX by the TIA
; fine/coarse positioning (SetObjectXPos). That offset is NOT a constant:
; verified empirically at the wall stops (mini-map pixel reads + RoomX):
;   X=8  (thin  left)  visible-left 4  -> offset 4
;   X=16 (thick left)  visible-left 9  -> offset 7
;   X=147(thick right) visible-left 140 -> offset 7
; This matches the coarse/fine model: for the FIRST coarse bin (RoomX < 15)
; RESP0 lands at pixel 3 (not 0), giving offset 4; for RoomX >= 15 RESP0 lands
; on the n*15 grid, giving a constant offset 7. So collision must subtract 4
; below X=15 and 7 at X>=15. See visible-left computation in PlayerHitsMap.
TILE_COLUMNS = 20
TILE_ROWS = 12              ; playable tile rows (the cave)
HUD_ROWS = 4                ; grey HUD band below the cave: 4 tile rows x 12 lines
LINES_PER_TILE = 12
HUD_COLOR = $06             ; emulator-aware grey (kPalette hue 0 luma 3)
; Boundary clamps let the player reach all four screen extremes (rooms will
; connect on every side). Walls still stop the player via collision; these only
; permit a fully-visible sprite flush with each edge:
; - LEFT:   offset 4 when RoomX<15, 7 when >=15; visible left = 0 at RoomX=4
; - RIGHT:  offset 7 at RoomX>=15 -> visible right = RoomX - 7 + 3 = 159 -> RoomX <= 163
;          (160 is the runtime stop; clamp is a wider safety net)
; - TOP:    visible top   = PlayerY = 0                -> PlayerY >= 0
; - BOTTOM: the cave is 12 tile rows (144 lines); the HUD is below it, so the
;          visible bottom must stay inside the cave: PlayerY + 7 <= 143 -> 136
PLAYER_MIN_X = 4
PLAYER_MAX_X = 163
PLAYER_MIN_Y = 0
PLAYER_MAX_Y = 136
; Facing direction of the player sprite's eye (0 = right, nonzero = left). The
; kernel picks the matching sprite table and the input handler updates it on
; every left/right press, so the eye always points where movement is attempted.
FACING_RIGHT = 0
FACING_LEFT = 1

; Vertical physics (HERO-style jet, for the re-added gravity + jetpack):
;   vy is a signed 16-bit velocity, += down, in pixels/frame (high byte) +
;   subpixel (low byte). Each frame gravity adds GRAVITY; while Up is held the
;   jet subtracts JetPower (thrust ramps +1/frame -> initial inertia, cap
;   JET_MAX); the fall speed clamps at MAX_FALL. GRAVITY was halved (was
;   $0010) so the player accelerates in free-fall more slowly and can brake
;   the fall with the jet, closer to HERO's feel. An upward clamp (magnitude
;   MAX_RISE, not in the original reference) keeps the jet from accelerating
;   without limit through open rooms and bounds the per-frame step count so
;   the overscan can never overrun its TIM64T window.
GRAVITY = $0008
JET_MAX = $20
MAX_FALL = $0200

; Jet sound (audio channel 0, written each frame in overscan while JetPower>0):
; AUDC0 = JET_AUDC (a low noise "engine" tone), AUDF0 sweeps
; JET_AUDF_BASE - JetPower/4 so the engine spools up and down with the throttle.
JET_AUDC = $06
JET_AUDF_BASE = $18
JET_AUDV = $07

; Room connection directions: index into each room's RoomConnections entry.
ROOM_UP = 0
ROOM_DOWN = 1
ROOM_LEFT = 2
ROOM_RIGHT = 3
ROOM_NONE = $ff

; Enemy records in LEVEL{n}_EnemyDataTable (emitted by convert_level.py):
; type, x, y, range_min, range_max, dir.
ENEMY_DATA_STRIDE = 6

; Overscan TIM64T value: locks every frame to exactly 262 scanlines.
; Fixed lines = 3 (vsync) + 3 (positioning) + 35 (vblank) + 192 (kernel) = 233,
; so the overscan gap must be 29 lines = 2204 cycles. The gap is
; 24 + 64*T + eps (24 = timer set + jmp + StartFrame's LDA/STA + WSYNC write);
; T=33 gives 2136..2142, whose next 76-cycle boundary is always 2204 -> 262.
OVSCAN_TIME = 33

PlayerX = RoomX
PlayerY = RoomY


; ------------------------------------------------------------------------------
; Setup rom
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; F6 landing pad (bank0, window $F000 / physical offset $0000)
; ------------------------------------------------------------------------------
; Every bankswitch bank (bank1/bank2/bank3) begins with a 5-byte stub:
;     lda #0
;     sta $1FF6       ; select bank0
; The 6502's fetch AFTER that store comes from bank0 at window $F005 (the
; selected bank changes immediately), so bank0 keeps an identical-size landing
; pad and a `jmp Main` at $F005-$F007. Whatever bank an emulator/console powers
; up in, execution always continues at bank0's Main.
; ------------------------------------------------------------------------------
    seg code
    org $f000       ; bank0 origin (window $F000 = F6 physical offset $0000)

    ds.b 5          ; $F000-$F004: pad matching the startup stub length (unused)
    jmp Main        ; $F005-$F007: execution lands here after any bank powers up

Main:
  CLEAN_START

; ------------------------------------------------------------------------------
; Init Variables
; ------------------------------------------------------------------------------
  lda #0
  sta GameMode            ; boot into the start screen (bank1), not the cave
  jsr LoadLevel           ; start at level 0's origin (start room/x/y from the level data)

; ------------------------------------------------------------------------------
; Render
; ------------------------------------------------------------------------------
StartFrame:

; ------------------------------------------------------------------------------
; Init VSYNC and VBLANK
; ------------------------------------------------------------------------------

  lda #2
  sta VBLANK
  sta VSYNC

  repeat 3
    sta WSYNC
  repend

  lda #0
  sta VSYNC                 ; turn off VSYNC

; Show the start screen (bank1) until the fire button starts the game.
; The menu is a self-contained frame loop in bank1 (owns its own vsync/vblank/
; kernel/overscan), so this frame simply hands off; it never comes back here
; while GameMode stays 0.
  lda GameMode
  bne .GameFrame
  jmp ToMenuStub            ; F6 fold pad -> bank1 MenuMain

.GameFrame:
; ------------------------------------------------------------------------------
; Horizontal positioning (2-3 scanlines)
; ------------------------------------------------------------------------------
  lda RoomX
  ldx #0
  jsr SetObjectXPos         ; position player0 (GRP0)
; Pick the single GRP1 object for this frame (miner or one enemy) and position
; it. See SelectActiveObject below.
  jsr SelectActiveObject
  sta WSYNC
  sta HMOVE                 ; apply the horizontal offsets we just set

; ------------------------------------------------------------------------------
; Remaining VBLANK (35 scanlines)
; ------------------------------------------------------------------------------
  ldx #35
LoopVBlank:
  sta WSYNC
  dex
  bne LoopVBlank

  lda #0
  sta VBLANK                ; turn off VBLANK

; ------------------------------------------------------------------------------
; Kernel (192 visible scanlines)
; ------------------------------------------------------------------------------
; HERO/Adventure-style REFLECTED playfield. CTRLPF D0=1 mirrors the 20-bit
; playfield, so ONE PF0/PF1/PF2 write per band defines the whole symmetric
; cave; the hardware draws the right half as the mirror of the left. Rooms
; must therefore be left-right symmetric (the room files are). CTRLPF D2=1
; (playfield priority) hides the player sprite behind walls and shows it in
; the openings, exactly like HERO.
;
; Layout: 12 playable tile rows x 20 columns (144 cave scanlines). Each tile
; is one playfield bit (4 color clocks = one screen cell) wide and 12 scanlines
; tall, followed by a 4-tile grey HUD band.
; For each tile row the kernel writes the playfield once (TIA registers
; persist), then paints 12 WSYNC-stabilised scanlines. The player sprite is
; drawn whenever Scanline - PlayerY is in 0..PLAYER_HEIGHT-1. WSYNC absorbs
; per-scanline jitter, so the only constraint is that the GRP0/PF writes land
; during HBLANK (color clocks 0-68); the writes at the top of each iteration
; inevitably do.
; ------------------------------------------------------------------------------
  lda #$00                  ; black cave interior
  sta COLUBK
  lda LevelWallColor        ; wall color (TIA byte, from the active level's data)
  sta COLUPF
  lda #$1c                  ; player color
  sta COLUP0
  lda #$05                  ; D0=1 reflect, D2=1 playfield priority
  sta CTRLPF
  lda #$00                  ; one copy, not flipped, no missiles/ball
  sta NUSIZ0
  sta NUSIZ1
  sta REFP0
  sta REFP1
  sta GRP0
  sta GRP1
  sta ENAM0
  sta ENAM1
  sta Scanline

  lda RoomPFDataLo
  sta MapPtrLo
  lda RoomPFDataHi
  sta MapPtrHi
  ldx #0                    ; tile row counter (row 0 at top of screen)
.Row:
; The current room's TilePF0/TilePF1/TilePF2 tables are contiguous 16-byte
; tables, so one base pointer covers all three registers.
  txa
  tay
  lda (MapPtrLo),Y          ; PF0 = row table + 0
  sta PF0                   ; defines the whole line via reflection
  tya
  clc
  adc #16
  tay
  lda (MapPtrLo),Y          ; PF1 = row table + 16
  sta PF1
  tya
  clc
  adc #16
  tay
  lda (MapPtrLo),Y          ; PF2 = row table + 32
  sta PF2
  lda #LINES_PER_TILE
  sta LineCount
; Stripe the cave: rows 0-3 are wall color 1, rows 4-7 wall color 2, and
; rows 8-11 wall color 1 again. COLUPF was already set once for row 0 at
; frame start, so only the row-4 and row-8 band boundaries need a rewrite.
  cpx #4
  beq .BandColor2
  cpx #8
  bne .ColorStripeDone
  lda LevelWallColor
  bne .ColorStripeApply
.BandColor2:
  lda LevelWallColor2
.ColorStripeApply:
  sta COLUPF
.ColorStripeDone:

.Line:
  lda Scanline
  sec
  sbc PlayerY               ; A = scanline - PlayerY
  cmp #PLAYER_HEIGHT
  bcs .NoSprite
  tay
; The player sprite has a 2-pixel black "eye" notch (3rd row) that sits on the
; side the player faces. Select the table by PlayerDir inside HBLANK.
  lda PlayerDir
  beq .FaceRight
  lda PlayerSpriteLeft,Y
  jmp .Put
.FaceRight:
  lda PlayerSpriteRight,Y
  jmp .Put
.NoSprite:
  lda #0
.Put:
  sta GRP0
; Draw the single GRP1 object chosen this frame (the miner or one enemy) as a
; square the same size as the player, only while this scanline is inside its
; 8-row footprint. Playfield priority (CTRLPF D2=1) hides it behind walls
; just like the player.
  lda ActiveObjectOn
  beq .NoObject
  lda Scanline
  sec
  sbc ActiveObjectY
  cmp #PLAYER_HEIGHT
  bcs .NoObject
  lda #%11110000
  jmp .ObjectPut
.NoObject:
  lda #0
.ObjectPut:
  sta GRP1
  inc Scanline
  sta WSYNC                 ; end this scanline
  dec LineCount
  bne .Line
  inx
  cpx #TILE_ROWS
  bne .Row

; ------------------------------------------------------------------------------
; HUD band: 4 grey rows (48 scanlines) below the cave.
; Clear the playfield, switch the background to HUD_COLOR and just blank the
; sprites for the band. The player and every GRP1 object are capped inside the
; 12 playable rows (PlayerY <= 136, deadly duds), so nothing is ever drawn here.
; One WSYNC per scanline keeps the frame at exactly 262 lines, unchanged.
; ------------------------------------------------------------------------------
  lda #HUD_COLOR
  sta COLUBK
  lda #0
  sta PF0
  sta PF1
  sta PF2
  lda #HUD_ROWS * LINES_PER_TILE
  sta LineCount
.HUDLine:
  lda Scanline
  sec
  sbc PlayerY
  cmp #PLAYER_HEIGHT
  bcs .HUDNoSprite
  tay
  lda PlayerDir
  beq .HUDFaceRight
  lda PlayerSpriteLeft,Y
  jmp .HUDPut
.HUDFaceRight:
  lda PlayerSpriteRight,Y
  jmp .HUDPut
.HUDNoSprite:
  lda #0
.HUDPut:
  sta GRP0
  lda #0
  sta GRP1
  inc Scanline
  sta WSYNC
  dec LineCount
  bne .HUDLine

; ------------------------------------------------------------------------------
; Overscan
; ------------------------------------------------------------------------------
; Game logic (input, movement, exits, miner pickup) runs INSIDE this TIM64T
; window. The spin below then waits for INTIM==0, so the overscan gap is
; exactly 2204 cycles (29 lines) no matter how long the logic took: the timer
; always expires at a fixed cycle after the kernel and the first WSYNC of the
; next StartFrame aligns to the same boundary every frame. VBLANK stays on
; during the whole overscan so the logic's TIA writes are blanked.
  lda #2
  sta VBLANK

  lda #OVSCAN_TIME
  sta TIM64T

; ------------------------------------------------------------------------------
; Input handler
; ------------------------------------------------------------------------------
; Horizontal movement stays positional (1 px/frame + map collision, below).
; Vertical movement is physical: gravity pulls the player down when no floor
; is underneath, and holding Up fires the jetpack (JetPower ramps with an
; initial inertia) to push him up. The frame's velocity is integrated through
; PlayerYSub and walked one pixel at a time via StepDown/StepUp so the room
; tile map stops the sprite flush at walls and doorway edges, using the same
; collision model as before.
UpdateP0Vertical:
; --- Jet thrust accumulator: +1/frame while Up is held (cap JET_MAX),
;     -1/frame otherwise. The ramp gives the jet its initial inertia. ---
  lda #%00010000
  bit SWCHA
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

; --- Clamp fall speed: down at MAX_FALL, up at -$0100 (see constants). ---
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

; --- Signed whole-pixel displacement this frame = carry + vyHi, where the
;     subpixel accumulator already consumed vyLo. ---
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

CheckP0Left:
  lda #%01000000
  bit SWCHA
  bne CheckP0Right
  lda #FACING_LEFT
  sta PlayerDir             ; turn the eye left, even if the move is blocked
  lda PlayerX
  cmp #PLAYER_MIN_X
  beq .ExitLeft             ; at the left edge -> try the room's left exit
  dec PlayerX
  jsr PlayerHitsMap
  bcc .LeftDone
  inc PlayerX
.LeftDone:
  jmp CheckP0Right
.ExitLeft:
  jsr ExitRoomLeft
  jmp CheckP0Right

CheckP0Right:
  lda #%10000000
  bit SWCHA
  bne EndInputCheck
  lda #FACING_RIGHT
  sta PlayerDir             ; turn the eye right, even if the move is blocked
  lda PlayerX
  cmp #PLAYER_MAX_X
  beq .ExitRight            ; at the right edge -> try the room's right exit
  inc PlayerX
  jsr PlayerHitsMap
  bcc .RightDone
  dec PlayerX
.RightDone:
  jmp EndInputCheck
.ExitRight:
  jsr ExitRoomRight
  jmp EndInputCheck

; ------------------------------------------------------------------------------
; StepDown: try one pixel of downward movement (called once per pixel of vy).
; A pixel is rejected when the footprint enters a solid tile (the player lands
; on the floor and vy is zeroed). At PLAYER_MAX_Y the sprite stands entirely
; inside an open passage - only reachable through a clear footprint - so the
; room's down connection is followed (ExitRoomDown leaves the player in place
; if there is no such connection).
; ------------------------------------------------------------------------------
StepDown subroutine
  lda PlayerY
  cmp #PLAYER_MAX_Y
  bcs .SDBottom
  inc PlayerY
  jsr PlayerHitsMap
  bcc .SDDone
  dec PlayerY
  lda #0
  sta vyLo
  sta vyHi
.SDDone:
  rts
.SDBottom:
  jsr ExitRoomDown
  rts

; ------------------------------------------------------------------------------
; StepUp: one pixel of upward movement. Symmetric to StepDown: a solid tile
; above stops the sprite and zeroes vy (ceiling); at the top edge the room's
; up connection is followed (ExitRoomUp leaves the player in place if none).
; ------------------------------------------------------------------------------
StepUp subroutine
  lda PlayerY
  beq .SUTop
  dec PlayerY
  jsr PlayerHitsMap
  bcc .SUDone
  inc PlayerY
  lda #0
  sta vyLo
  sta vyHi
.SUDone:
  rts
.SUTop:
  jsr ExitRoomUp
  rts

EndInputCheck:
; ------------------------------------------------------------------------------
; Miner pickup
; ------------------------------------------------------------------------------
; If the player overlaps the miner (same room, footprint within one sprite),
; advance to the next level (wrapping past the last) and spawn at its origin.
; ------------------------------------------------------------------------------
CheckMinerPickup:
  lda LevelMinerRoom
  cmp RoomNo
  bne .NoPickup
  lda PlayerX
  sec
  sbc MinerX
  bpl .XPos
  eor #$ff
  clc
  adc #1
.XPos:
  cmp #PLAYER_WIDTH
  bcs .NoPickup
  lda PlayerY
  sec
  sbc MinerY
  bpl .YPos
  eor #$ff
  clc
  adc #1
.YPos:
  cmp #PLAYER_HEIGHT
  bcs .NoPickup
  inc Level
  lda Level
  cmp #LEVEL_COUNT
  bcc .LoadIt
  lda #0                    ; wrapped past the last level -> back to the first
.LoadIt:
  jsr LoadLevel
.NoPickup:
  jsr CheckEnemyHit

; ------------------------------------------------------------------------------
; Jet sound: a low noise "engine" on audio channel 0 while the jet burns
; (JetPower > 0). The pitch follows the throttle (AUDF0 drops as JetPower
; ramps up, so the engine spools up/down), which also gives a short wind-down
; tail when Up is released. AUDV0 = 0 silences the channel the rest of the
; time. Written once per frame in overscan (TIA audio is latched per frame).
; ------------------------------------------------------------------------------
UpdateJetSound:
  lda JetPower
  beq .JetSilent
  lda #JET_AUDV
  sta AUDV0
  lda #JET_AUDC
  sta AUDC0
  lda JetPower
  lsr
  lsr                      ; JetPower/4 -> 0..$08 (full thrust)
  sta Temp
  lda #JET_AUDF_BASE
  sec
  sbc Temp
  sta AUDF0                ; AUDF0 = base - thrust: pitches down as it spools up
  jmp WaitOverscan
.JetSilent:
  sta AUDV0                ; A = 0: kill channel 0
WaitOverscan:
  lda INTIM
  bne WaitOverscan
  jmp StartFrame

; ------------------------------------------------------------------------------
; CheckEnemyHit: if the player's footprint overlaps ANY enemy in the current
; room, teleport to the level's start room and start point.
; Each enemy record (LEVEL{n}_EnemyDataTable) is: type, x, y, range_min,
; range_max, dir. The overlap test uses LOGICAL coordinates for both, exactly
; like CheckMinerPickup (the TIA left-edge offsets cancel for player and enemy).
; Timing absorbs into the overscan TIM64T window, so the frame stays 262 lines.
; Clobbers: A, X, Y, MapPtrLo/Hi, EnemyLoopCount.
; ------------------------------------------------------------------------------
CheckEnemyHit subroutine
  lda EnemyCount
  beq .HitDone
  sta EnemyLoopCount
  lda EnemyDataLo
  sta MapPtrLo
  lda EnemyDataHi
  sta MapPtrHi
.ENext:
  ldy #1
  lda (MapPtrLo),Y          ; enemy x
  sec
  sbc RoomX
  bcs .EXge                 ; enemy x >= player x
  eor #$ff
  clc
  adc #1
.EXge:
  cmp #PLAYER_WIDTH
  bcs .ENextEnemy
  ldy #2
  lda (MapPtrLo),Y          ; enemy y
  sec
  sbc RoomY
  bcs .EYge
  eor #$ff
  clc
  adc #1
.EYge:
  cmp #PLAYER_HEIGHT
  bcs .ENextEnemy
  lda LevelStartRoom        ; HIT: respawn at the level origin
  jsr EnterRoom
  lda LevelStartX
  sta RoomX
  lda LevelStartY
  sta RoomY
  lda #0                    ; respawn with no velocity or thrust
  sta vyLo
  sta vyHi
  sta PlayerYSub
  sta JetPower
  rts
.ENextEnemy:
  lda MapPtrLo
  clc
  adc #ENEMY_DATA_STRIDE
  sta MapPtrLo
  bcc .EAdvance
  inc MapPtrHi
.EAdvance:
  dec EnemyLoopCount
  bne .ENext
.HitDone:
  rts

; ------------------------------------------------------------------------------
; Check collisions
; ------------------------------------------------------------------------------
; Tests the proposed 8x8 player footprint against the room tile map.
; The 20-column room is drawn by a REFLECTED playfield, so on screen it is a
; mirrored 40-block cave: playfield block q (q = RoomX>>2, 4 px per block)
; shows text column q in the left half (q 0..19) and text column 39-q in the
; right half (q 20..39). Collision therefore maps each covered block back to
; its text column before reading the map.
; Vertical:   screen scanline -> tile row via YToCellRow (/12).
; Returns C=0 if clear, C=1 if blocked.
PlayerHitsMap:
  lda RoomX
  cmp #15
  bcs .VisibleOffset7
  sec
  sbc #4                    ; RoomX < 15: RESP lands at px 3 -> visible left = X-4
  jmp .HaveVisibleLeft
.VisibleOffset7:
  sec
  sbc #7                    ; RoomX >= 15: constant offset 7
.HaveVisibleLeft:
  sta CollisionX            ; = visible sprite left edge
  lsr
  lsr
  sta CollisionCellX        ; first playfield block under the sprite
  clc
  lda CollisionX
  adc #PLAYER_WIDTH - 1
  lsr
  lsr
  sta CollisionEndX         ; last playfield block under the sprite

  lda PlayerY
  jsr YToCellRow
  stx CollisionCellY         ; top tile row
  clc
  lda PlayerY
  adc #PLAYER_HEIGHT - 1
  jsr YToCellRow
  stx CollisionEndY          ; bottom tile row

.CheckRow:
; Resolve the room row base for tile row CollisionCellY. The current room's
; RoomRowLo and RoomRowHi tables are contiguous 16-byte tables, so a single
; RoomRowMap pointer plus a +16 offset reaches both.
  ldy CollisionCellY        ; tile row index (0..15)
  lda RoomRowMapLo
  sta MapPtrLo
  lda RoomRowMapHi
  sta MapPtrHi
  lda (MapPtrLo),Y          ; room row base lo byte
  sta CollisionX            ; stash in scratch (rebuilt by .CheckCell if used)
  lda RoomRowMapLo
  clc
  adc #16                   ; RoomRowHi table = RoomRowLo table + 16
  sta MapPtrLo
  lda RoomRowMapHi
  adc #0
  sta MapPtrHi
  lda (MapPtrLo),Y          ; room row base hi byte
  sta MapPtrHi
  lda CollisionX
  sta MapPtrLo              ; MapPtr = room row base address
  ldy CollisionCellX         ; Y = playfield block (0..39)
.CheckCell:
  cpy #TILE_COLUMNS
  bcc .LeftBlock             ; q < 20 -> text column = q
  lda #39
  sec
  sty CollisionX
  sbc CollisionX             ; q >= 20 -> text column = 39 - q (mirror)
  tay
  lda (MapPtrLo),Y
  bne .MapHit
  ldy CollisionX
  jmp .NextCell
.LeftBlock:
  lda (MapPtrLo),Y
  bne .MapHit
.NextCell:
  iny
  cpy CollisionEndX
  bcc .CheckCell
  beq .CheckCell
  inc CollisionCellY
  lda CollisionCellY
  cmp CollisionEndY
  bcc .CheckRow
  beq .CheckRow
  clc
  rts

.MapHit:
  sec
  rts

; ------------------------------------------------------------------------------
; Subroutines
; ------------------------------------------------------------------------------
; Convert a screen scanline (0..191) into a tile row index (0..15).
; A = scanline in, X = tile row out.
; ------------------------------------------------------------------------------
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

; ------------------------------------------------------------------------------
; EnterRoom: point the kernel and collision data at room A (0-based room index).
; Sets RoomNo and reloads the PF data and row-map pointers from the active
; level's RoomDataTable (LevelPFData). RoomX/RoomY are left to the caller so
; each exit can pick the entry edge.
; ------------------------------------------------------------------------------
EnterRoom subroutine
  sta RoomNo
  asl
  asl                       ; room * 4 (two .word entries per room)
  tay
  lda (LevelPFDataLo),Y
  sta RoomPFDataLo
  iny
  lda (LevelPFDataLo),Y
  sta RoomPFDataHi
  iny
  lda (LevelPFDataLo),Y
  sta RoomRowMapLo
  iny
  lda (LevelPFDataLo),Y
  sta RoomRowMapHi
; Load the current room's enemy data pointer + count from the level's
; per-room record (ptr_lo, ptr_hi, count, pad).
  lda RoomNo
  asl
  asl
  tay
  lda (LevelEnemyLo),Y
  sta EnemyDataLo
  iny
  lda (LevelEnemyLo),Y
  sta EnemyDataHi
  iny
  lda (LevelEnemyLo),Y
  sta EnemyCount
  rts

; ------------------------------------------------------------------------------
; LoadLevel: load the game state for level index A (0-based).
; Reads the LEVEL_DATA_STRIDE entry for A from LevelDataTable, points the room
; data / connections / wall color at the level's tables, spawns the player at
; the level's origin and enters its start room.
; ------------------------------------------------------------------------------
LoadLevel subroutine
  sta Level
  lda #0                    ; fresh spawn: no falling/jetting momentum
  sta vyLo
  sta vyHi
  sta PlayerYSub
  sta JetPower
  tax
  txa
  asl
  asl                       ; A = level * 4
  sta Temp
  txa
  asl
  asl
  asl                       ; A = level * 8
  clc
  adc Temp                  ; A = level * LEVEL_DATA_STRIDE
  clc
  adc #<LevelDataTable
  sta LevelDataLo
  lda #>LevelDataTable
  adc #0
  sta LevelDataHi
  ldy #0
  lda (LevelDataLo),Y       ; start room
  sta Temp
  sta LevelStartRoom
  iny
  lda (LevelDataLo),Y       ; start x
  sta RoomX
  sta LevelStartX
  iny
  lda (LevelDataLo),Y       ; start y
  sta RoomY
  sta LevelStartY
  iny
  lda (LevelDataLo),Y       ; miner room
  sta LevelMinerRoom
  iny
  lda (LevelDataLo),Y       ; miner x
  sta MinerX
  iny
  lda (LevelDataLo),Y       ; miner y
  sta MinerY
  iny
  lda (LevelDataLo),Y       ; wall color
  sta LevelWallColor
  iny
  lda (LevelDataLo),Y       ; second wall color
  sta LevelWallColor2
  iny
  lda (LevelDataLo),Y       ; RoomDataTable base lo
  sta LevelPFDataLo
  iny
  lda (LevelDataLo),Y       ; RoomDataTable base hi
  sta LevelPFDataHi
  iny
  lda (LevelDataLo),Y       ; RoomConnections base lo
  sta LevelConnLo
  iny
  lda (LevelDataLo),Y       ; RoomConnections base hi
  sta LevelConnHi
  lda Level
  asl
  tay
  lda LevelEnemyTable,Y     ; active level's RoomEnemies base
  sta LevelEnemyLo
  iny
  lda LevelEnemyTable,Y
  sta LevelEnemyHi
  lda Temp
  jmp EnterRoom

; ------------------------------------------------------------------------------
; ExitRoomUp / ExitRoomDown: follow the current room's up/down connection. If a
; target room exists, enter it at the opposite edge; otherwise stay put. Vertical
; exits preserve RoomX so the player stays in the shared passage.
; ------------------------------------------------------------------------------
ExitRoomUp subroutine
  lda RoomNo
  asl
  asl
  tay
  lda (LevelConnLo),Y         ; +ROOM_UP = 0
  cmp #ROOM_NONE
  beq .NoExit
  jsr EnterRoom
  lda #PLAYER_MAX_Y
  sta PlayerY               ; enter at the bottom edge
.NoExit:
  rts

ExitRoomDown subroutine
  lda RoomNo
  asl
  asl
  tay
  iny
  lda (LevelConnLo),Y         ; +ROOM_DOWN = 1
  cmp #ROOM_NONE
  beq .NoExit
  jsr EnterRoom
  lda #PLAYER_MIN_Y
  sta PlayerY               ; enter at the top edge
.NoExit:
  rts

; ------------------------------------------------------------------------------
; ExitRoomLeft / ExitRoomRight: follow the current room's left/right connection.
; Horizontal exits preserve RoomY so the player stays in the passage that is
; vertically aligned between connected rooms.
; ------------------------------------------------------------------------------
ExitRoomLeft subroutine
  lda RoomNo
  asl
  asl
  tay
  iny
  iny
  lda (LevelConnLo),Y         ; +ROOM_LEFT = 2
  cmp #ROOM_NONE
  beq .NoExit
  jsr EnterRoom
  lda #PLAYER_MAX_X
  sta PlayerX               ; enter at the right edge
.NoExit:
  rts

ExitRoomRight subroutine
  lda RoomNo
  asl
  asl
  tay
  iny
  iny
  iny
  lda (LevelConnLo),Y         ; +ROOM_RIGHT = 3
  cmp #ROOM_NONE
  beq .NoExit
  jsr EnterRoom
  lda #PLAYER_MIN_X
  sta PlayerX               ; enter at the left edge
.NoExit:
  rts

; ------------------------------------------------------------------------------
; SelectActiveObject: choose the single GRP1 object to draw this frame.
; The TIA has one GRP1 sprite, so the object list is the miner (when this is
; its room) followed by the room's enemies (from EnemyCount/EnemyDataLo/Hi).
; Each frame the slot pointer advances: with N slots every object flickers at
; 60/N fps. Rooms with no objects leave ActiveObjectOn = 0 so GRP1 stays off.
; Sets COLUP1, then positions GRP1 when an object is present.
; Clobbers: A, X, Y, MapPtrLo/MapPtrHi, EnemyIndex.
; ------------------------------------------------------------------------------
SelectActiveObject subroutine
  lda EnemyCount
  sta ObjectCount
  lda LevelMinerRoom
  cmp RoomNo
  bne .SelectGotCount
  inc ObjectCount           ; miner owns slot 0 when this is its room
.SelectGotCount:
  lda ObjectCount
  bne .SelectRotate
  lda #0
  sta ActiveObjectOn
  jmp .SelectDone
.SelectRotate:
  inc FlickerFrame
  lda FlickerFrame
  cmp ObjectCount
  bcc .SelectPicked
  lda #0
  sta FlickerFrame
.SelectPicked:
  lda #1
  sta ActiveObjectOn
  ldy FlickerFrame
  lda LevelMinerRoom
  cmp RoomNo
  bne .SelectEnemy          ; no miner here: Y is already an enemy index
  cpy #0
  beq .SelectMiner
  dey                       ; miner room, Y>=1: enemy index = Y-1
.SelectEnemy:
  sty EnemyIndex
  ldy #0                    ; byte offset = EnemyIndex * ENEMY_DATA_STRIDE
  ldx #0                    ; counter: 0..EnemyIndex
.SelectEnemyOffset:
  cpx EnemyIndex
  beq .SelectEnemyHave
  inx
  tya
  clc
  adc #ENEMY_DATA_STRIDE
  tay
  jmp .SelectEnemyOffset
.SelectEnemyHave:
  tya
  clc
  adc EnemyDataLo           ; MapPtr = EnemyData base + index * stride
  sta MapPtrLo
  lda #0
  adc EnemyDataHi
  sta MapPtrHi
  ldy #0
  lda (MapPtrLo),Y          ; type -> color
  tay
  lda EnemyColorTable,Y
  sta COLUP1
  ldy #1
  lda (MapPtrLo),Y          ; x (room pixel 0..159)
  sta ActiveObjectX
  ldy #2
  lda (MapPtrLo),Y          ; y (scanline 0..191)
  sta ActiveObjectY
  jmp .SelectDone
.SelectMiner:
  ldx MinerX
  stx ActiveObjectX
  ldx MinerY
  stx ActiveObjectY
  lda #$66                  ; miner purple (kPalette hue 6 luma 3)
  sta COLUP1
.SelectDone:
  lda ActiveObjectX
  ldx #1
  jsr SetObjectXPos         ; position the GRP1 object (player1), ALWAYS: even
                            ; with no object it keeps the frame at 262 lines
                            ; (the sprite is blanked by ActiveObjectOn=0).
  rts

; ------------------------------------------------------------------------------
; Horizontal positioning conversion
; A is the desired room-space X coordinate. TIA conversion happens here.
; X is the object type (0 = player0, 1 = player1, ...).
; Andrew Davie session-24 routine: rolls the divide-by-15 and the delay loop
; into one unit, and the page-aligned fineAdjustTable guarantees every RESP0
; write lands on the same clock grid, so the sprite's LEFT edge maps 1:1 to
; the requested pixel (0..159). Must be followed by HMOVE during HBLANK.
; ------------------------------------------------------------------------------
SetObjectXPos subroutine
  sta WSYNC                 ; sync to start of scanline
  sec                       ; ensure carry flag
.Div15Loop
  sbc #15                   ; subtract 15: coarse delay + remainder combined
  bcs .Div15Loop            ; loop until carry is clear
  tay                       ; Y = remainder in -15..-1
  lda fineAdjustTable,Y     ; 5 cycles (page-cross guaranteed) -> fine offset
  sta HMP0,X                ; store the fine offset
  sta RESP0,X               ; store the coarse offset
  rts

; ------------------------------------------------------------------------------
; GameStart: entry point used by the bank1 start screen (bank1's ToGameStub
; jumps here after selecting bank0). Restarts gameplay at level 0 with clean
; movement state. The address is FIXED at $f500 via the org below so bank1's
; fold stub (`jmp GameStart`, GameStart = $f500) assembles to identical bytes.
; ------------------------------------------------------------------------------
    org $f500
GameStart:
    lda #0
    sta vyLo
    sta vyHi
    sta JetPower
    sta PlayerYSub
    sta PlayerDir
    sta StepsLeft
    jsr LoadLevel           ; A is still 0 -> level 0
    jmp StartFrame

; ------------------------------------------------------------------------------
; ROM Data
; ------------------------------------------------------------------------------
; Bitmaps and colors
; ------------------------------------------------------------------------------
; Room/level data is placed after all out-of-line code. The HUD band pushed
; the code past $f400, so data starts at $f600 (~1630 bytes, ending near $fc60)
; and stays well before the page-aligned fine-adjust table at $ff00.
    org $f600
    include "generated/levels_data.asm"

; Player sprites, one per facing. 8 rows x 4 pixels (PLAYER_HEIGHT x
; PLAYER_WIDTH); X is a painted pixel, . a black pixel.
;   .X..  <- the 3rd row (row 2) is the "eye": a 2-pixel black notch on the
;   XXXX      side the player faces, made by clearing the paint there
;   XXXX
; .X..          facing RIGHT: notch on the right half
;   XXXX
;   XXXX
;   XXXX
;   XXXX
PlayerSpriteRight:
  .byte #%11110000
  .byte #%11110000
  .byte #%11000000           ; eye on the right
  .byte #%11110000
  .byte #%11110000
  .byte #%11110000
  .byte #%11110000
  .byte #%11110000
; Same sprite mirrored horizontally: the eye notch sits on the LEFT half. The
; kernel indexes either table with the row offset (scanline - PlayerY).
PlayerSpriteLeft:
  .byte #%11110000
  .byte #%11110000
  .byte #%00110000           ; eye on the left
  .byte #%11110000
  .byte #%11110000
  .byte #%11110000
  .byte #%11110000
  .byte #%11110000

; Enemy rectangle colors indexed by enemy type (editor EnemyType enum).
; All bytes are emulator-aware (hue << 4) | (luma << 1), taken from the
; shared kPalette hue-major table (hue 0 = greys, 1 = gold, 2 = orange,
; C = green, F = brown):
;   type 0 spider     dark yellow   hue 1 luma 2 -> $14
;   type 1 bat        brown         hue F luma 1 -> $F2
;   type 2 snake      green         hue C luma 2 -> $C4
;   type 3 tentacle   white         hue 0 luma 7 -> $0E
;   type 4 giant moth dark orange   hue 2 luma 1 -> $22
EnemyColorTable:
  .byte $14
  .byte $F2
  .byte $C4
  .byte $0E
  .byte $22

; Level data (per-level tables + LevelDataTable + LEVEL_COUNT) is generated by
; tools/convert_level.py --levels from the editor's JSON level files.
    include "generated/levels.asm"

; ------------------------------------------------------------------------------
; F6 cross-bank fold pads - MUST match bank1's copies at these addresses.
; The 6502 fetches the next instruction AFTER `sta $1FFx` from the newly
; selected bank, so both banks replicate these stubs byte-for-byte: the CPU
; starts them in one bank and continues the same instruction stream in the
; other. The `jmp` operands are fixed window addresses (MenuMain = $f540 in
; bank1, GameStart = $f500 here), so both assemblies emit identical bytes.
;     $fd00 ToMenuStub  lda #1 / sta $1FF7 / jmp MenuMain   (game -> start screen)
;     $fe00 ToGameStub  lda #0 / sta $1FF6 / jmp GameStart  (menu -> game)
; ------------------------------------------------------------------------------
MenuMain = $f540           ; bank1's menu entry (not present as code in bank0)
    org $fd00
ToMenuStub:
    lda #1
    sta $1FF7               ; select bank1 (start screen)
    jmp MenuMain            ; next fetch at $fd05 comes from bank1: jmp $f540
    org $fe00
ToGameStub:
    lda #0
    sta $1FF6               ; select bank0 (game code)
    jmp GameStart           ; next fetch at $fe05 comes from bank0: jmp $f500

; ------------------------------------------------------------------------------
; Fine-adjust table for SetObjectXPos. MUST be page-aligned ($xx00): the
; indexed load then always crosses a page boundary, provides the 5-cycle
; timing the routine depends on for a pixel-accurate RESP0 strobe. Placed at
; $ff00 (top of the last page) so the room data area at $f300 has the whole
; middle of the ROM to grow as rooms are added in the editor.
; ------------------------------------------------------------------------------
    org $ff00
fineAdjustBegin:
  .byte %01110000           ; left 7
  .byte %01100000           ; left 6
  .byte %01010000           ; left 5
  .byte %01000000           ; left 4
  .byte %00110000           ; left 3
  .byte %00100000           ; left 2
  .byte %00010000           ; left 1
  .byte %00000000           ; no movement
  .byte %11110000           ; right 1
  .byte %11100000           ; right 2
  .byte %11010000           ; right 3
  .byte %11000000           ; right 4
  .byte %10110000           ; right 5
  .byte %10100000           ; right 6
  .byte %10010000           ; right 7
fineAdjustTable EQU fineAdjustBegin - %11110001   ; %11110001 = -241 (start basis)

; ------------------------------------------------------------------------------
; Fill ROM to exactly 4kb
; ------------------------------------------------------------------------------

    org $fffc
  .word Main      ; tell atari where to start when we reset (bank0's own entry)
  .word Main      ; interupt at $fffe - unused by vcs but makes 4kb