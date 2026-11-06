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
DropTarget  = $8A
StepsLeft   = $97
PlayerLives = $AC
TickCounter = $AD
BarLevel    = $AE
ScoreTh     = $F3
ScoreHu     = $F4
ScoreTe     = $F5
BombX       = $F6
BombTimer   = $F7
StickA      = $DC
DemoOn      = $DD                    ; b7 = virtual FIRE, b6 = demo playing, b5-0 = the title's Level
Level       = $A3
DemoPos     = $DE
DemoDur     = $DF
AUDV0       = $19
AUDV1       = $1A
SWCHA       = $0280
SWCHB       = $0282
INPT4       = $0C
IDLE_FRAMES = 150                    ; x2 passes = 300 frames = 5 s of an untouched title
    .ds $F100 - *, 0
TransBody:
    lda LevelConnSpare
    bmi TBgo
    jmp DemoHook                ; the title or the demo (a plain frame never gets here:
                                ;   bank0's TailHook sends only pending/demo frames)
TBgo:
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
    lda LevelConnSpare
    cmp #$A0
    beq .TBreload               ; attract mode: reload the stage (see DemoHook)
    asl                         ; N = b6: new stage (TallyWork), else a room exit
    bmi .TBlevel
    lda #$FC
    pha
    lda #$5D
    pha                         ; EnterRoom's rts -> $FC5E (bank0 pad 2)
    lda LevelConnSpare
    and #$7F                    ; A = target room
    jmp $FBD0                   ; EnterRoom tramp twin: sta $1FF6, bank2 jmp $F010
.TBlevel:
    lda DemoOn
    beq .TBlevelOk
    jmp DHabort                 ; the demo must never advance/save the stage
.TBlevelOk:
    lda #0
    sta LevelConnSpare          ; consumed (LoadLevel's chain would zero it too)
    lda #$FC
    pha
    lda #$60
    pha                         ; SaveKey's rts -> $FC61 (bank0 pad 3)
    lda #2                      ; SaveKey op 2 = CHECKPOINT (may RESTART the game)
    jmp $FC08                   ; twin of bank0's CallPad_SaveKey: sta $1FF8, bank4 jmp
.TBreload:
    lda #0
    sta LevelConnSpare
    sta AUDV0                   ; the title theme (or the demo's last sound) stops
    sta AUDV1
    beq TransAfterSave          ; A = 0: always taken
TransAfterSave:
    lda #$FC
    pha
    lda #$5D
    pha                         ; LoadLevel's final rts (DropArm) -> $FC5E
    jmp $FC20                   ; twin of bank0's LoadLevel: sta $1FF6, bank2 jmp LoadLevelB2
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


; ==============================================================================
; DemoHook (attract mode, 2026-11) — runs at the END of every non-plain frame
; (title, drop-in, tally, demo), from TransBody. Entered with A != 0.
;   title idle  : 300 frames (5 s) with every title input released -> start the demo
;   demo        : play DemoScript through StickA/DemoOn (EOR-ed onto the real
;                 SWCHA/INPT4 reads), any real input -> back to the title
;   reload      : LevelConnSpare = $A0 makes TransBody run LoadLevel in a blank
;                 frame (like a room change); DropTarget decides the result:
;                 0 = the real drop-in (demo), $FF = the title preview.
; The demo is the REAL game on the selected stage (so the logo/credits band hook
; of the title is off by design); lives are topped up every frame, nothing saves.
; ==============================================================================
    .ds $F200 - *, 0
DemoHook:
    lda DemoOn
    bne .DHdemo
    lda DropTarget
    cmp #$FF
    bne .DHout                  ; drop-in fall / tally sentinel: not ours
    lda StepsLeft               ; title's last input sample (1 = released)
    and #$17
    cmp #$17
    bne .DHidleReset
    inc DemoDur
    lda DemoDur
    cmp #IDLE_FRAMES
    bcc .DHwait
    lda #0
    sta DemoDur
    inc DemoPos
    lda DemoPos
    cmp #2
    bcc .DHwait
    lda Level
    ora #$40
    sta DemoOn                  ; 5 s of nothing: play (remembering the title's stage)
    lda #0
    sta Level                   ; the demo is scripted on stage 1 whatever is selected
    beq DHreload                ; always taken
.DHidleReset:
    lda #0
    sta DemoDur
    sta DemoPos
.DHwait:                        ; a title frame ends with its overscan timer
    lda INTIM
    bne .DHwait
.DHout:
    jmp $FC58
.DHdemo:
    lda DropTarget
    cmp #$FF
    beq DHabort                 ; a console switch (REY) already sent us to the title:
                                ;   only the stage number and the preview are left to fix
    lda SWCHA
    and #$F0
    cmp #$F0
    bne DHabort                 ; stick moved
    lda INPT4
    bpl DHabort                 ; fire
    lda SWCHB
    and #3
    cmp #3
    bne DHabort                 ; SELECT / RESET
    lda #3
    sta PlayerLives             ; the demo never loses
    dec DemoDur
    bne .DHout                  ; mid-step: the virtual presses stay
    ldy DemoPos
    lda DemoScript,y            ; step = duration, presses (D7-D4 = R L D U, D0 = fire)
    beq DHloop                  ; 0 = end of script: restart it
    sta DemoDur
    lda DemoScript+1,y
    tax
    and #$F0
    sta StickA
    lda DemoOn
    and #$7F
    sta DemoOn
    txa
    lsr                         ; C = fire
    bcc .DHnoFire
    lda DemoOn
    ora #$80                    ; EOR-ed onto INPT4 D7: pressed
    sta DemoOn
.DHnoFire:
    iny
    iny
    sty DemoPos
    bne .DHout                  ; always taken (script < 256 B)
DHloop:
DHreload:
    lda DemoOn
    and #$7F
    sta DemoOn                  ; fire released
    lda #0
    sta StickA
    sta DemoPos
    sta DropTarget              ; 0 -> LoadLevel arms the real drop-in
    sta ScoreTh
    sta ScoreHu
    sta ScoreTe
    sta BombX                   ; the title melody's state byte
    lda #1
    sta DemoDur                 ; next frame fetches step 0
    lda #3
    sta PlayerLives
    lda #TICKS_PER_SEC
    sta TickCounter
    lda #120
    sta BarLevel
    bne DHpend
DHabort:                        ; back to the title (the REY exit's state)
    lda DemoOn
    and #$3F
    sta Level                   ; the stage the player had selected
    lda #0
    sta DemoOn
    sta StickA
    sta DemoPos
    sta DemoDur
    sta BombX
    sta BombTimer
    sta ScoreTh
    sta ScoreHu
    sta ScoreTe
    lda #%11101000              ; SELECT/RESET/UP/DOWN/FIRE count as held: no instant start
    sta StepsLeft
    lda #$FF
    sta DropTarget
DHpend:
    lda #$A0
    sta LevelConnSpare
    jmp TBgo

; The script: duration (frames), presses. Presses: $80 right, $40 left, $20 down
; (drops the bomb on its press edge, standing only), $10 up (jet), $01 fire (laser).
; Stage 1 (the pocket under the start): fall in, walk to both walls, drop a bomb,
; fly out over it (the laser fires while flying), hover until it has gone off,
; then glide back to the drop-in spot (X=39, Y=0, facing right) for a seamless loop. The first step covers the drop-in (~72 frames) and the free fall.
DemoScript:
    .byte 140, $00             ; drop-in + fall to the floor
    .byte  12, $80             ; walk right to the wall
    .byte  14, $40             ; walk left (faces left)
    .byte   3, $20             ; DOWN: bomb
    .byte   2, $00
    .byte  14, $80             ; walk right, away from it
    .byte  40, $10             ; jet up out of the pocket
    .byte  30, $90             ; up + right
    .byte  40, $11             ; up + FIRE: laser
    .byte  35, $50             ; up + left
    .byte  35, $90             ; up + right
    .byte  40, $11             ; up + FIRE
    .byte  30, $10
    .byte  39, $50             ; up + left along the ceiling ...
    .byte   6, $90             ; ... and back right: ends at X=39, facing right, Y=0 --
    .byte  10, $10             ;   exactly where the next drop-in starts (a seamless loop)
    .byte   0                  ; end: restart the demo

    .ds $FBD0 - *, 0
    sta $1FF6                   ; twin of bank0's EnterRoom tramp (bank2 has the jmp)
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF4                   ; the every-bank ReturnPad contract (bank0 rts at $FBFB)
    .ds $FC08 - *, 0
    sta $1FF8                   ; twin of CallPad_SaveKey (bank4 serves the jmp at $FC0B)
    .ds $FC20 - *, 0
    sta $1FF6                   ; twin of LoadLevel (bank2 serves the jmp at $FC23)
    .ds $FC58 - *, 0
    sta $1FF4                   ; bank0 $FC5B = jmp StartFrame
    jmp TransBody               ; $FC5B: fetched after bank0's `sta $1FF9` at $FC58
    .ds $FC61 - *, 0
    jmp TransFinish             ; $FC61: after bank0's second pad at $FC5E
    .ds $FC64 - *, 0
    jmp TransAfterSave          ; $FC64: after bank0's third pad at $FC61

    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
