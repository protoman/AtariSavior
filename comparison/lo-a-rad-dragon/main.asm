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
OldX            byte
OldY            byte
Random          byte

; ------------------------------------------------------------------------------
; Setup consts
; ------------------------------------------------------------------------------
PLAYER_HEIGHT = 8
PLAYER_WIDTH = 8
ROOM_X_MIN = 0
ROOM_X_MAX = 140
ROOM_Y_MIN = 5
ROOM_Y_MAX = 84
ROOM_TOP_BORDER_END = 5
ROOM_BOTTOM_BORDER_START = 93
TOP_EXIT_X_MIN = 56
TOP_EXIT_X_MAX = 80
SIDE_EXIT_Y_MIN = 39
SIDE_EXIT_Y_MAX = 60
SIDE_EXIT_ORIGIN_MIN = SIDE_EXIT_Y_MIN
SIDE_EXIT_ORIGIN_MAX = SIDE_EXIT_Y_MAX - PLAYER_HEIGHT + 1
BAR_X = 28
BAR_Y = 30
BAR_HEIGHT = 32

PlayerX = RoomX
PlayerY = RoomY
PLAYER_MIN_X = ROOM_X_MIN
PLAYER_MAX_X = ROOM_X_MAX
PLAYER_MIN_Y = ROOM_Y_MIN
PLAYER_MAX_Y = ROOM_Y_MAX
DOOR_MIN_X = TOP_EXIT_X_MIN
DOOR_MAX_X = TOP_EXIT_X_MAX
DOOR_MIN_Y = SIDE_EXIT_ORIGIN_MIN
DOOR_MAX_Y = SIDE_EXIT_ORIGIN_MAX
EXIT_TOP_Y = ROOM_Y_MAX - PLAYER_HEIGHT


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
  lda #50
  sta RoomX
  sta RoomY

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
; Calculations run before VBLANK
; ------------------------------------------------------------------------------
  lda RoomX
  ldy #0
  jsr SetObjectXPos         ; set player0 x position
  lda #BAR_X
  ldy #1
  jsr SetObjectXPos         ; reserve player1 position for the bar

  sta WSYNC
  sta HMOVE                 ; apply the horizontal offets we just set

; ------------------------------------------------------------------------------
; 37 lines of VBLANK minus 2 used above
; ------------------------------------------------------------------------------

  ldx #35
LoopVBlank:
  sta WSYNC
  dex
  bne LoopVBlank

  lda #0
  sta VBLANK                ; turn off VBLANK

; ------------------------------------------------------------------------------
; 192 visible scanlines
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; 2-line kernel
; ------------------------------------------------------------------------------
  lda #$00                  ; black room interior
  sta COLUBK
  lda #$2a                  ; orange room border
  sta COLUPF
  sta COLUP1
  lda #$1c
  sta COLUP0
  lda #$01                  ; reflected playfield
  sta CTRLPF

  ldx #96                   ; scanline counter
.EachLine:
.DrawRoom:
  txa
  cmp #ROOM_BOTTOM_BORDER_START ; top border
  bcs .SolidBorder
  cmp #ROOM_TOP_BORDER_END     ; bottom border
  bcc .SolidBorder
  cmp #SIDE_EXIT_Y_MIN      ; left/right doorway
  bcc .SideBorder
  cmp #SIDE_EXIT_Y_MAX + 1
  bcc .Doorway

.SideBorder:
  lda #$10                  ; narrow side walls only
  sta PF0
  lda #$00
  sta PF1
  sta PF2
  jmp .IsPlayer

.Doorway:
  lda #$00                  ; opening through both side walls
  sta PF0
  sta PF1
  sta PF2
  jmp .IsPlayer

.SolidBorder:
  lda #$f0
  sta PF0
  lda #$ff
  sta PF1
  lda #$0f                  ; leave a central opening in top/bottom walls
  sta PF2

.IsPlayer:
  txa
  sec                       ; always set carry before sub
  sbc PlayerY
  cmp PLAYER_HEIGHT
  bcc .DrawPlayer
  lda #0                    ; if not draw empty row from sprite

.DrawPlayer:
  tay
  lda PlayerSprite,Y
  sta GRP0
  lda BarMask,X
  sta GRP1
  sta WSYNC

  sta WSYNC
  dex
  bne .EachLine

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
CheckP0Up:
  lda #%00010000
  bit SWCHA                 ; compare to joy
  bne CheckP0Down
  lda PlayerY
  cmp #PLAYER_MAX_Y
  bcc .MoveUp
  lda PlayerX
  cmp #DOOR_MIN_X
  bcc .StopUp
  cmp #DOOR_MAX_X
  bcs .StopUp
.MoveUp:
  inc PlayerY
  jmp CheckP0Down
.StopUp:
  lda #PLAYER_MAX_Y
  sta PlayerY

CheckP0Down:
  lda #%00100000
  bit SWCHA
  bne CheckP0Left
  lda PlayerY
  cmp #PLAYER_MIN_Y
  bcs .MoveDown
  lda PlayerX
  cmp #DOOR_MIN_X
  bcc .StopDown
  cmp #DOOR_MAX_X
  bcs .StopDown
.MoveDown:
  dec PlayerY
  jmp CheckP0Left
.StopDown:
  lda #PLAYER_MIN_Y
  sta PlayerY

CheckP0Left:
  lda #%01000000
  bit SWCHA
  bne CheckP0Right
  lda PlayerY
  cmp #PLAYER_MIN_Y
  bcc .TopBottomLeft
  cmp #EXIT_TOP_Y
  bcs .TopBottomLeft
  bne .SideLeft
.TopBottomLeft:
  lda PlayerX
  cmp #DOOR_MIN_X
  beq .StopTopBottomLeft
  bcc .StopTopBottomLeft
.SideLeft:
  lda PlayerX
  cmp #PLAYER_MIN_X
  bne .MoveLeft
  lda PlayerY
  cmp #DOOR_MIN_Y
  bcc .StopLeft
  cmp #DOOR_MAX_Y
  bcs .StopLeft
  lda #PLAYER_MAX_X
  sta PlayerX
  jmp CheckP0Right
  ; The side opening currently wraps to the opposite edge until room
  ; transitions are implemented.
.MoveLeft:
  dec PlayerX
  jmp CheckP0Right
.StopTopBottomLeft:
  lda #DOOR_MIN_X
  sta PlayerX
  jmp CheckP0Right
.StopLeft:
  lda #PLAYER_MIN_X
  sta PlayerX

CheckP0Right:
  lda #%10000000
  bit SWCHA
  bne EndInputCheck
  lda PlayerY
  cmp #PLAYER_MIN_Y
  bcc .TopBottomRight
  cmp #EXIT_TOP_Y
  bcs .TopBottomRight
  bne .SideRight
.TopBottomRight:
  lda PlayerX
  cmp #DOOR_MAX_X
  beq .StopTopBottomRight
  bcs .StopTopBottomRight
.SideRight:
  lda PlayerX
  cmp #PLAYER_MAX_X
  bne .MoveRight
  lda PlayerY
  cmp #DOOR_MIN_Y
  bcc .StopRight
  cmp #DOOR_MAX_Y
  bcs .StopRight
  lda #PLAYER_MIN_X
  sta PlayerX
  jmp EndInputCheck
.MoveRight:
  inc PlayerX
  jmp EndInputCheck
.StopTopBottomRight:
  lda #DOOR_MAX_X
  sta PlayerX
  jmp EndInputCheck
.StopRight:
  lda #PLAYER_MAX_X
  sta PlayerX

EndInputCheck:

; ------------------------------------------------------------------------------
; Check collisions
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; Next frame
; ------------------------------------------------------------------------------
  jmp StartFrame

; ------------------------------------------------------------------------------
; Subroutines
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
; Random using Linear-Feedback Shift Register
; - Generate random number using LFSR
; ------------------------------------------------------------------------------
SetRandom subroutine
  lda Random
  asl
  eor Random
  asl
  eor Random
  asl
  asl
  eor Random
  asl
  rol Random                ; ok we have LFSR random

  rts

; ------------------------------------------------------------------------------
; ROM Data
; ------------------------------------------------------------------------------
; Bitmaps and colors
; ------------------------------------------------------------------------------
  org $f300
BarMask:
  REPEAT BAR_Y
    .byte $00
  REPEND
  REPEAT BAR_HEIGHT
    .byte $ff
  REPEND
  REPEAT 96 - BAR_Y - BAR_HEIGHT + 1
    .byte $00
  REPEND

PlayerSprite:
  .byte #%00000000
  .byte #%01001000
  .byte #%11111100
  .byte #%01111000
  .byte #%10000000
  .byte #%10101000
  .byte #%10000000
  .byte #%01111000

PlayerColors:
  .byte $00
  .byte $96
  .byte $96
  .byte $1c
  .byte $1c
  .byte $1c
  .byte $1c
  .byte $1c

; ------------------------------------------------------------------------------
; Fill ROM to exactly 4kb
; ------------------------------------------------------------------------------

  org $fffc
  .word Start     ; tell atari where to start when we reset
  .word Start     ; interupt at $fffe - unused by vcs but makes 4kb
