    processor 6502
    seg code
    include "colors.inc"            ; TV_CAVE_LINES (frame length of this TV standard)
    org $F000
; Power-up stub (every bank has it: F4 powers up in an undefined bank): `lda #0 /
; sta $1FF4` selects bank0, whose $F005 is `jmp GameStart`. Guard: verify_build
; check_boot_banks (all 8 banks).
    lda #0
    sta $1FF4
; ==============================================================================
; Bank5 — free 4K window in the F4 (32K, 8 banks) layout.
; ==============================================================================
; Besides the stub, only the version header lives here ($F005: "S.A.V.I.O.R. <VERSION>", 0 - build.sh
; writes version.asm from the VERSION file). The file still assembles to a full 4K
; image: the tail is filled to the vector area, and the vectors are emitted (unused,
; but every bank image must be 4096 B and DASM only writes what is emitted).
; Hotspot for this bank: $1FF9 (F4: bank = addr - $1FF4).
; ==============================================================================
RomVersion:
    include "version.asm"

; ==============================================================================
; TransBody — the blank ROOM-TRANSITION frame (2026-11). An exit sets
; LevelConnSpare = room | $80 (bank2 ExitDirB2); EnterRoom's 1000-2000c would
; overrun the overscan, so every gameplay frame ends in bank0's Transition pad
; ($FC58: `sta $1FF9`, then this bank's `jmp TransBody` at $FC5B):
;   not pending -> `jmp $FC58` = our `sta $1FF4` there; bank0 $FC5B runs
;                  `jmp StartFrame` (cost: ~22c per frame).
;   pending     -> emit one blank frame: VSYNC, VBLANK stays on, EnterRoom
;                  (it ends in ReturnPad, whose rts lands on bank0's second pad
;                  $FC5E because we push $FC5D), then TransFinish pads the
;                  frame to 272 lines and leaves through $FC58 the same way.
; EnterRoom's chain zeroes LevelConnSpare (bank3 ERLoadDone): flag consumed.
; ==============================================================================
VSYNC       = $00
TIM64T      = $0296
INTIM       = $0284
WSYNC       = $02
TF_LINES    = 54 + TV_CAVE_LINES - 272   ; scanlines after the 255-unit timer (tuned: 272 total on NTSC)
LevelConnSpare = $A2
    .ds $F100 - *, 0
TransBody:
    lda LevelConnSpare
    bmi .TBgo
    jmp $FC58                   ; not pending: back to bank0 -> jmp StartFrame
.TBgo:
    sta WSYNC
    lda #2
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #0
    sta VSYNC
    lda #255
    sta TIM64T                  ; 255 * 64c = 214 lines, EnterRoom runs inside
    lda #$FC
    pha
    lda #$5D
    pha                         ; EnterRoom's rts -> $FC5E (bank0 pad 2)
    lda LevelConnSpare
    and #$7F                    ; A = target room
    jmp $FBD0                   ; EnterRoom tramp twin: sta $1FF6, bank2 jmp $F010
TransFinish:
.TBwait:
    lda INTIM
    bne .TBwait
    ldx #TF_LINES
.TBline:
    sta WSYNC
    dex
    bne .TBline
    jmp $FC58

    .ds $FBD0 - *, 0
    sta $1FF6                   ; twin of bank0's EnterRoom tramp (bank2 has the jmp)
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF4                   ; the every-bank ReturnPad contract (bank0 rts at $FBFB)
    .ds $FC58 - *, 0
    sta $1FF4                   ; bank0 $FC5B = jmp StartFrame
    jmp TransBody               ; $FC5B: fetched after bank0's `sta $1FF9` at $FC58
    .ds $FC61 - *, 0
    jmp TransFinish             ; $FC61: after bank0's second pad at $FC5E

    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
