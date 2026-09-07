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
Temp            byte            ; general scratch (level*stride in LoadLevel)

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
TILE_ROWS = 16
LINES_PER_TILE = 12
; Boundary clamps let the player reach all four screen extremes (rooms will
; connect on every side). Walls still stop the player via collision; these only
; permit a fully-visible sprite flush with each edge:
; - LEFT:   offset 4 when RoomX<15, 7 when >=15; visible left = 0 at RoomX=4
; - RIGHT:  offset 7 at RoomX>=15 -> visible right = RoomX - 7 + 3 = 159 -> RoomX <= 163
;          (160 is the runtime stop; clamp is a wider safety net)
; - TOP:    visible top   = PlayerY = 0                -> PlayerY >= 0
; - BOTTOM: visible bottom = PlayerY + 7 = 191        -> PlayerY <= 184
PLAYER_MIN_X = 4
PLAYER_MAX_X = 163
PLAYER_MIN_Y = 0
PLAYER_MAX_Y = 184

; Room connection directions: index into each room's RoomConnections entry.
ROOM_UP = 0
ROOM_DOWN = 1
ROOM_LEFT = 2
ROOM_RIGHT = 3
ROOM_NONE = $ff

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
  jsr SetObjectXPos         ; position player0 (miner uses object 1)
  lda RoomNo
  cmp LevelMinerRoom
  bne .Player1Done
  lda MinerX
  ldx #1
  jsr SetObjectXPos         ; position the miner sprite (player1)
.Player1Done:
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
  lda #$c6                  ; miner color (green, emulator-aware encoding)
  sta COLUP1
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
; Draw the miner (an 8x8 green square, same footprint as the player) on GRP1,
; but only inside its own room. Playfield priority (CTRLPF D2=1) hides it
; behind walls just like the player.
  lda LevelMinerRoom
  cmp RoomNo
  bne .NoMiner
  lda Scanline
  sec
  sbc MinerY
  cmp #PLAYER_HEIGHT
  bcs .NoMiner
  lda #%11110000
  jmp .MinerPut
.NoMiner:
  lda #0
.MinerPut:
  sta GRP1
  inc Scanline
  sta WSYNC                 ; end this scanline
  dec LineCount
  bne .Line
  inx
  cpx #TILE_ROWS
  bne .Row

; ------------------------------------------------------------------------------
; Overscan
; ------------------------------------------------------------------------------

  lda #2
  sta VBLANK

  ldx #30
LoopOverscan:
  sta WSYNC
  dex
  bne LoopOverscan

  lda #0
  sta VBLANK

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
  jmp StartFrame

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
  iny
  lda (LevelDataLo),Y       ; start x
  sta RoomX
  iny
  lda (LevelDataLo),Y       ; start y
  sta RoomY
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
    org $f300
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