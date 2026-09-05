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

; ------------------------------------------------------------------------------
; Setup consts
; ------------------------------------------------------------------------------
PLAYER_HEIGHT = 8
PLAYER_WIDTH = 8
TILE_COLUMNS = 20
TILE_ROWS = 16
LINES_PER_TILE = 12
PLAYER_MIN_X = 8
PLAYER_MAX_X = 151
PLAYER_MIN_Y = 12
PLAYER_MAX_Y = 172

PlayerX = RoomX
PlayerY = RoomY


; ------------------------------------------------------------------------------
; Setup rom
; ------------------------------------------------------------------------------

    seg code
    org $f000       ; define the code origin at $f000 - start of the ROM

Start:
  CLEAN_START

; ------------------------------------------------------------------------------
; Init Variables
; ------------------------------------------------------------------------------
  lda #132
  sta RoomX               ; spawn centered in the open lane (cols 16-18)
  lda #96
  sta RoomY               ; spawn in tile row 8 (open lane)

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
; Horizontal positioning (2 scanlines)
; ------------------------------------------------------------------------------
  lda RoomX
  ldy #0
  jsr SetObjectXPos         ; set player0 x position
  sta WSYNC
  sta HMOVE                 ; apply the horizontal offset we just set

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
  lda #$2a                  ; orange walls
  sta COLUPF
  lda #$1c                  ; player color
  sta COLUP0
  lda #$05                  ; D0=1 reflect, D2=1 playfield priority
  sta CTRLPF
  lda #$00                  ; one copy, not flipped, no missiles/ball
  sta NUSIZ0
  sta REFP0
  sta GRP1
  sta ENAM0
  sta ENAM1
  sta Scanline

  ldx #0                    ; tile row counter (row 0 at top of screen)
.Row:
  lda TilePF0,X
  sta PF0                   ; defines the whole line via reflection
  lda TilePF1,X
  sta PF1
  lda TilePF2,X
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
  bcc .StopUp
  dec PlayerY
  jsr PlayerHitsMap
  bcc .UpDone
  inc PlayerY
.UpDone:
  jmp CheckP0Down
.StopUp:
  lda #PLAYER_MIN_Y
  sta PlayerY

CheckP0Down:
  lda #%00100000
  bit SWCHA
  bne CheckP0Left
  lda PlayerY
  cmp #PLAYER_MAX_Y         ; down = larger scanline
  bcs .StopDown
  inc PlayerY
  jsr PlayerHitsMap
  bcc .DownDone
  dec PlayerY
.DownDone:
  jmp CheckP0Left
.StopDown:
  lda #PLAYER_MAX_Y
  sta PlayerY

CheckP0Left:
  lda #%01000000
  bit SWCHA
  bne CheckP0Right
  lda PlayerX
  cmp #PLAYER_MIN_X
  bcc .StopLeft
  dec PlayerX
  jsr PlayerHitsMap
  bcc .LeftDone
  inc PlayerX
.LeftDone:
  jmp CheckP0Right
.StopLeft:
  lda #PLAYER_MIN_X
  sta PlayerX

CheckP0Right:
  lda #%10000000
  bit SWCHA
  bne EndInputCheck
  lda PlayerX
  cmp #PLAYER_MAX_X
  bcs .StopRight
  inc PlayerX
  jsr PlayerHitsMap
  bcc .RightDone
  dec PlayerX
.RightDone:
  jmp EndInputCheck
.StopRight:
  lda #PLAYER_MAX_X
  sta PlayerX

EndInputCheck:
  jmp StartFrame

; ------------------------------------------------------------------------------
; Check collisions
; ------------------------------------------------------------------------------
; Tests the proposed 8x8 player footprint against the room tile map.
; Horizontal: room pixel -> tile column via >>3 (8 pixel columns).
; Vertical:   screen scanline -> tile row via YToCellRow (/12).
; Returns C=0 if clear, C=1 if blocked.
PlayerHitsMap:
  lda RoomX
  sta CollisionX
  clc
  adc #PLAYER_WIDTH - 1
  lsr
  lsr
  lsr
  sta CollisionEndX          ; right tile column
  lda CollisionX
  lsr
  lsr
  lsr
  sta CollisionCellX         ; left tile column

  lda PlayerY
  jsr YToCellRow
  stx CollisionCellY         ; top tile row
  clc
  lda PlayerY
  adc #PLAYER_HEIGHT - 1
  jsr YToCellRow
  stx CollisionEndY          ; bottom tile row

.CheckRow:
  ldx CollisionCellY
  lda RoomRowLo,X
  sta MapPtrLo
  lda RoomRowHi,X
  sta MapPtrHi
  ldy CollisionCellX
.CheckCell:
  lda (MapPtrLo),Y
  bne .MapHit
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
; Horizontal positioning conversion
; A is the desired room-space X coordinate. TIA conversion happens here.
; Y is the object type
;   0 = player0, 1 = player1, 2 = missile0, 3 = missile1, 4 = ball
; ------------------------------------------------------------------------------
SetObjectXPos subroutine
  sta WSYNC                 ; start new scanline
  sec                       ; ensure carry flag
.Div15Loop
  sbc #15                   ; sub 15 from desired X to get coarse location
  bcs .Div15Loop            ; loop until carry is clear
  eor #7                    ; put in range -8 to 7
  repeat 4                  ; shift left 4 times, only want top 4 bits
    asl
  repend
  sta HMP0,Y                ; store the fine offset
  sta RESP0,Y               ; store the coarse offset
  rts

; ------------------------------------------------------------------------------
; ROM Data
; ------------------------------------------------------------------------------
; Bitmaps and colors
; ------------------------------------------------------------------------------
    org $f300
    include "generated/level_001_room_001.asm"

PlayerSprite:
  .byte #%11111111
  .byte #%11111111
  .byte #%11111111
  .byte #%11111111
  .byte #%11111111
  .byte #%11111111
  .byte #%11111111
  .byte #%11111111

; ------------------------------------------------------------------------------
; Fill ROM to exactly 4kb
; ------------------------------------------------------------------------------

    org $fffc
  .word Start     ; tell atari where to start when we reset
  .word Start     ; interupt at $fffe - unused by vcs but makes 4kb