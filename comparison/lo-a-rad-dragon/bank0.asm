  processor 6502

    include "vcs.h"
    include "macro.h"

; ------------------------------------------------------------------------------
; Setup variables
; ------------------------------------------------------------------------------

  seg.u Variables
    org $80

RoomX           byte
RoomY           byte
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
LevelWallColor  byte            ; COLUPF byte for the active level's walls
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
; Layout: 16 tile rows x 20 columns, each tile 8 color-clocks wide and 12
; scanlines tall, so the entire 192-line screen IS the cave (no menu region).
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

.Line:
  lda Scanline
  sec
  sbc PlayerY               ; A = scanline - PlayerY
  cmp #PLAYER_HEIGHT
  bcs .NoSprite
  tay
  lda PlayerSprite,Y
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
  lda PlayerSprite,Y
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
; Movement is 1 unit per frame. Walls come from the shared room tile map
; (PlayerHitsMap). The boundary clamps below are only a safety net; the
; map collision rejects any step into solid tiles.
CheckP0Up:
  lda #%00010000
  bit SWCHA                 ; compare to joy
  bne CheckP0Down
  lda PlayerY
  cmp #PLAYER_MIN_Y         ; up = smaller scanline
  beq .ExitTop              ; at the top edge -> try the room's up exit
  dec PlayerY
  jsr PlayerHitsMap
  bcc .UpDone
  inc PlayerY
.UpDone:
  jmp CheckP0Down
.ExitTop:
  jsr ExitRoomUp
  jmp CheckP0Down

CheckP0Down:
  lda #%00100000
  bit SWCHA
  bne CheckP0Left
  lda PlayerY
  cmp #PLAYER_MAX_Y         ; down = larger scanline
  bcs .ExitBottom
  inc PlayerY
  jsr PlayerHitsMap
  bcc .DownDone
  dec PlayerY
.DownDone:
  jmp CheckP0Left
.ExitBottom:
; Player reached the bottom edge inside an open passage (collision keeps them
; there, since reaching the edge requires a clear footprint). Follow the room's
; down connection; RoomX is preserved to stay aligned with the passage.
  jsr ExitRoomDown
  jmp CheckP0Left

CheckP0Left:
  lda #%01000000
  bit SWCHA
  bne CheckP0Right
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
; ROM Data
; ------------------------------------------------------------------------------
; Bitmaps and colors
; ------------------------------------------------------------------------------
; Room/level data is placed after all out-of-line code. The HUD band pushed
; the code past $f400, so data starts at $f600 (~1630 bytes, ending near $fc60)
; and stays well before the page-aligned fine-adjust table at $ff00.
    org $f600
    include "generated/levels_data.asm"

PlayerSprite:
  .byte #%11110000
  .byte #%11110000
  .byte #%11110000
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