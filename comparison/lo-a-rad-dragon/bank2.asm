  processor 6502
  include "comparison/lo-a-rad-dragon/vcs.h"

; ZP variables shared with bank0
LaserActive      = $d0
LaserY           = $d1
PlayerY          = $81
ScoreHu          = $c3
EnemyCount       = $a6
EnemyDataLo      = $a4
EnemyDataHi      = $a5
ActiveObjectY    = $ab
MapPtrLo         = $8a
MapPtrHi         = $8b
Temp             = $ad
ENEMY_DATA_STRIDE = 6

; ------------------------------------------------------------------------------
; Bank 2 (F6, window $F000 / physical offset $2000)
; Houses laser fire check + collision detection.
; ------------------------------------------------------------------------------

    include "comparison/lo-a-rad-dragon/vcs.h"
    include "comparison/lo-a-rad-dragon/macro.h"

HUD_COLOR = $06

; ZP variable addresses (must match bank0's declarations exactly)
Level           = $96
FontP0          = $b3
FontP1          = $b8
PF0ScoreBuf     = $b3          ; reused from FontP0 after level rendering
PF1ScoreBuf     = $b8          ; reused from FontP1 after level rendering
PF2ScoreBuf     = $c6          ; reused from ScoreDigit2 (no longer needed)
Temp            = $ad
ScoreTh         = $c2
ScoreHu         = $c3
ScoreTe         = $c4
ScoreOn         = $c5

    seg code
    org $f000

Reset:
    lda #0
    sta $1FF6           ; F6: select bank0

; LaserCheck: called from bank0's LaserTrampoline ($FF10).
; Handles both fire button check AND collision detection.
LaserCheck:
; --- Fire button check ---
  lda LaserActive
  beq .TryFire
  dec LaserActive
  jmp .CheckHit
.TryFire:
  bit INPT4                  ; N=1 when button NOT pressed
  bmi .CheckHit
  lda #10
  sta LaserActive
  lda PlayerY
  clc
  adc #2                     ; eye is at row 2
  sta LaserY

; --- Collision check: walk enemy table to find the one matching ActiveObjectY ---
.CheckHit:
  lda LaserActive
  beq .NoHit
  lda EnemyCount
  beq .NoHit
  sta Temp                    ; loop counter
  lda EnemyDataLo
  sta MapPtrLo
  lda EnemyDataHi
  sta MapPtrHi
.Loop:
  ldy #2
  lda (MapPtrLo),Y
  cmp ActiveObjectY
  beq .Hit
  lda MapPtrLo
  clc
  adc #ENEMY_DATA_STRIDE
  sta MapPtrLo
  bcc .Next
  inc MapPtrHi
.Next:
  dec Temp
  bne .Loop
  jmp .NoHit
.Hit:
  ldy #2
  lda #255
  sta (MapPtrLo),Y           ; mark enemy dead
  sed
  clc
  lda ScoreHu
  adc #5                     ; +50 points (BCD)
  sta ScoreHu
  cld
.NoHit:
  lda #0
  sta CXCLR
  rts

; Fold pad at $FF10: byte-identical to bank0's LaserTrampoline.
    org $ff10
    sta $1FF8
    jsr LaserCheck
    sta $1FF6
    rts

    org $fffc
    .word Reset
    .word Reset
