  processor 6502
  include "comparison/lo-a-rad-dragon/vcs.h"

; ------------------------------------------------------------------------------
; Bank 2 (F6, window $F000 / physical offset $2000)
; Houses overflow game logic (laser fire check + collision) called from bank0
; via fold-pad trampoline at $FF10.
; ZP and TIA registers are shared across all banks.
; ------------------------------------------------------------------------------

; ZP variables shared with bank0 (must match bank0's layout exactly)
LaserActive      = $d0
LaserY           = $d1
LaserEnemyLo     = $d2
LaserEnemyHi     = $d3
PlayerY          = $81
ScoreHu          = $c3

    seg code
    org $f000

Reset:
    lda #0
    sta $1FF6           ; F6: select bank0

; LaserCollision: called from bank0's LaserTrampoline ($FC58).
; Handles both fire button check AND collision detection.
; On entry: bank2 selected.
; On exit:  RTS returns to bank0 via fold pad.
LaserCollision:
; --- Fire button check ---
  lda LaserActive
  beq .TryFire
  dec LaserActive
  jmp .CheckHit           ; laser active — skip fire, go check collision
.TryFire:
  bit INPT4               ; N=1 when button NOT pressed
  bmi .CheckHit           ; not pressed — go check collision anyway
  lda #10
  sta LaserActive
  lda PlayerY
  clc
  adc #2                  ; eye is at row 2
  sta LaserY

; --- Collision check ---
.CheckHit:
  lda LaserActive
  beq .NoHit
  lda CXM0P
  and #$80                ; bit 7 = missile0-player1
  beq .NoHit
  ldy #2
  lda #255
  sta (LaserEnemyLo),Y    ; mark enemy dead
  sed
  clc
  lda ScoreHu
  adc #5                  ; +50 points (BCD)
  sta ScoreHu
  cld
.NoHit:
  lda #0
  sta CXCLR               ; clear collision latches
  rts

; Fold pad at $FF10: byte-identical to bank0's LaserTrampoline.
    org $ff10
    sta $1FF8
    jsr LaserCollision
    sta $1FF6
    rts

    org $fffc
    .word Reset
    .word Reset
