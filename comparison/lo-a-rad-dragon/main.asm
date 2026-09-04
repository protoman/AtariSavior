  processor 6502

  include "vcs.h"
  include "macro.h"

; ------------------------------------------------------------------------------
; Setup variables
; ------------------------------------------------------------------------------

  seg.u Variables
  org $80

PlayerX         byte
PlayerY         byte
OldX            byte
OldY            byte
Random          byte

; ------------------------------------------------------------------------------
; Setup consts
; ------------------------------------------------------------------------------
PLAYER_HEIGHT = 8


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
  sta PlayerX
  sta PlayerY

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
  lda PlayerX
  ldy #0
  jsr SetObjectXPos         ; set player0 x position

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
  lda #$01                  ; reflected playfield
  sta CTRLPF

  ldx #96                   ; scanline counter
.EachLine:
.DrawRoom:
  txa
  cmp #93                   ; top border
  bcs .SolidBorder
  cmp #5                    ; bottom border
  bcc .SolidBorder
  cmp #47                   ; left/right doorway
  bcc .SideBorder
  cmp #52
  bcc .Doorway

.SideBorder:
  lda #$f0                  ; side walls only
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
  lda PlayerColors,Y
  sta COLUP0
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
  inc PlayerY

CheckP0Down:
  lda #%00100000
  bit SWCHA
  bne CheckP0Left
  dec PlayerY

CheckP0Left:
  lda #%01000000
  bit SWCHA
  bne CheckP0Right
  dec PlayerX

CheckP0Right:
  lda #%10000000
  bit SWCHA
  bne EndInputCheck
  inc PlayerX

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
; Horizontal Positioning
; A is the desired x coordinate
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
