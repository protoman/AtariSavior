    processor 6502
    seg code
    include "colors.inc"            ; TV_CAVE_LINES (the transition frame length, trans.inc)
    include "banks.inc"             ; BK_* bank selectors by role (docs/agents/banks.md)
    org $F000
; The power-up pad every bank carries: `lda #0 / sta $1FF4` selects bank0, whose
; $F005 is `jmp GameStart`. The restart ops (game over, last stage cleared) jump
; here: the run restarts at the title and never returns to the caller.
Restart:
    lda #0
    sta BK_GENERAL
; ==============================================================================
; Bank4 — SaveKey service (docs/savekey_design.md, user 2026-10-28).
; ==============================================================================
; A 24LC256 I2C EEPROM on the RIGHT controller port: pin 3 = SDA = SWCHA bit 2,
; pin 4 = SCL = SWCHA bit 3 (Stella SaveKey.cxx). Open drain by hand: the SWCHA
; latch bits stay 0 and a line is driven LOW by setting its SWACNT bit (output)
; or RELEASED by clearing it (input, pulled up in the key). Nothing is ever
; driven high. Bit-banged without delays: every SWACNT store is >= 4 cycles
; (3.4 us), far above the chip's 400 kHz timing.
;
; ONE 12-byte record at SK_ADDR (16-byte aligned: it never straddles a 64-byte
; page), staged in SkBuf for the whole call:
;   0-1 magic $53,$01 (the 2nd byte is the format version)   2 state (1 = save)
;   3 level (0-based)   4 lives   5-7 score (packed BCD Th,Hu,Te)
;   8-10 HIGH score (packed BCD)  11 checksum = $A5 eor bytes 0-10
; A bad magic/checksum is "no data": the game starts fresh and the next write
; repairs it. No key (NACK on the control byte) aborts every op at once.
;
; SkService (A = op), C=0 when it did something, C=1 when there was nothing to do
;   0 BOOT        title power-on: Level := the saved stage; the high score goes
;                 to SkHi (vyLo/vyHi/PlayerYSub) for the title to show
;   1 RESUME      RESET on the saved stage: lives + score := the saved ones
;   2 CHECKPOINT  stage advance (the caller already did `inc Level`): save {Level,
;                 lives, score}; high = max(high,score). Level >= LEVEL_COUNT =
;                 the last stage was cleared: same as GAMEOVER
;   3 GAMEOVER    erase the save; high = max(high, score); then RESTART at the
;                 title (never returns; with no key it just restarts)
; Clobbers A/X/Y, SkB/SkN/SkT/SkL and SkBuf. Leaves SWACNT = 0 (bus released).
; Hotspot for this bank: $1FF8 (F4: bank = addr - $1FF4).
; ==============================================================================
SWCHA       = $0280
SWACNT      = $0281
SK_SDA      = $04               ; SWCHA/SWACNT bit of pin 3
SK_SCL      = $08               ; SWCHA/SWACNT bit of pin 4
SK_BOTH     = SK_SDA|SK_SCL
SK_ADDR_H   = $7F               ; record block $7FE0 (open question: AtariVox list)
SK_ADDR_L   = $E0
SK_CTRL_W   = $A0               ; 1010 000 R/W
SK_CTRL_R   = $A1
SK_REC_LEN  = 12
R_STATE     = 2
R_LEVEL     = 3
R_LIVES     = 4
R_SCORE     = 5
R_HIGH      = 8
R_CHK       = 11
LIVES_MAX   = 8
LEVEL_COUNT = 32                ; hand copy of the kernel's LEVEL_COUNT

; Game variables (hand copies of kernel.asm; check_equ_sync pairs the names)
Level       = $A3
PlayerLives = $AC
EnemyRamP   = $C2               ; free-running frame clock (bank0 RefreshEnemyY)
ScoreTh     = $F3
ScoreHu     = $F4
ScoreTe     = $F5

; Scratch: dead at every call site (title / level load) - see the design doc.
SkB         = $88               ; byte being shifted (kernel Temp)
SkN         = $89               ; op flag (kernel ZPSpare89, free)
SkT         = $8B               ; (kernel CollisionX)
SkL         = $8E               ; loop counter (kernel CollisionEndX)
SkHi        = $93               ; high score handed to the title: vyLo, vyHi, PlayerYSub
                                ;   (dead on the title; bank0 TitleScore reads them)
SkBuf       = $C3               ; 12 bytes = PF0Buf..PF2Buf (rebuilt by the room load)

; ------------------------------------------------------------------------------
; I2C primitives. Between bits SCL is low; STOP/START leave the bus released/low.
; ------------------------------------------------------------------------------
SkStart:                        ; bus released -> START, SCL low
    lda #SK_SDA
    sta SWACNT                  ; SDA falls while SCL is high
    lda #SK_BOTH
    sta SWACNT
    rts

SkStop:                         ; any state -> STOP, bus released
    lda #SK_BOTH
    sta SWACNT                  ; SDA low, SCL low
    lda #SK_SDA
    sta SWACNT                  ; SCL high
    lda #0
    sta SWACNT                  ; SDA rises while SCL is high
    rts

SkRestart:                      ; SCL low -> repeated START, SCL low
    lda #SK_SCL
    sta SWACNT                  ; release SDA
    lda #0
    sta SWACNT                  ; release SCL
    jmp SkStart

; Send A, MSB first; returns C=0 when the chip ACKed. SCL low, SDA low on exit.
SkSend:
    sta SkB
    ldx #8
.SkBit:
    asl SkB
    ldy #SK_BOTH                ; bit 0: SDA low
    bcc .SkOut
    ldy #SK_SCL                 ; bit 1: SDA released
.SkOut:
    sty SWACNT                  ; data valid, SCL low
    tya
    and #SK_SDA
    sta SWACNT                  ; SCL high
    sty SWACNT                  ; SCL low
    dex
    bne .SkBit
    lda #SK_SCL
    sta SWACNT                  ; release SDA for the ACK
    lda #0
    sta SWACNT                  ; SCL high: the chip holds SDA low for an ACK
    lda SWCHA
    and #SK_SDA
    sta SkT
    lda #SK_SCL
    sta SWACNT                  ; SCL low
    lda #SK_BOTH
    sta SWACNT                  ; SDA low again
    lda SkT
    cmp #1                      ; C = 1 when SDA stayed high (NACK)
    rts

; Receive a byte into A. C=1 on entry -> NACK it (the last byte), C=0 -> ACK.
SkRecv:
    lda #0
    rol                         ; A = the ACK bit to send (1 = NACK)
    sta SkT
    lda #SK_SCL
    sta SWACNT                  ; SDA released, SCL low
    ldx #8
.SkRb:
    lda #0
    sta SWACNT                  ; SCL high
    lda SWCHA
    and #SK_SDA
    cmp #1                      ; C = the data bit
    rol SkB
    lda #SK_SCL
    sta SWACNT                  ; SCL low
    dex
    bne .SkRb
    ldy #SK_BOTH                ; ACK: SDA low
    lda SkT
    beq .SkAck
    ldy #SK_SCL                 ; NACK: SDA released
.SkAck:
    sty SWACNT
    tya
    and #SK_SDA
    sta SWACNT                  ; SCL high
    sty SWACNT                  ; SCL low
    lda #SK_SCL
    sta SWACNT                  ; release SDA
    lda SkB
    rts

; ------------------------------------------------------------------------------
; Record transactions
; ------------------------------------------------------------------------------
SkSum:                          ; A = $A5 eor SkBuf[0..10]
    lda #$A5
    ldy #R_CHK-1
.SkS1:
    eor SkBuf,y
    dey
    bpl .SkS1
    rts

; SkLoad: read the record into SkBuf.
; C=0 valid. C=1 with A=0: no key (nothing else is worth trying); A=1: bad data.
SkLoad:
    lda #0
    sta SWCHA                   ; latch low for pins 3/4 (never drive high)
    sta SWACNT
    jsr SkStart
    lda #SK_CTRL_W
    jsr SkSend
    bcs .SkAbsent
    lda #SK_ADDR_H
    jsr SkSend
    lda #SK_ADDR_L
    jsr SkSend
    jsr SkRestart
    lda #SK_CTRL_R
    jsr SkSend
    ldy #0
.SkRd:
    sty SkL
    cpy #SK_REC_LEN-1           ; C=1 for the last byte: NACK it
    jsr SkRecv
    ldy SkL
    sta SkBuf,y
    iny
    cpy #SK_REC_LEN
    bne .SkRd
    jsr SkStop
    lda SkBuf
    cmp #$53
    bne .SkBad
    lda SkBuf+1
    cmp #$01
    bne .SkBad
    jsr SkSum
    cmp SkBuf+R_CHK
    bne .SkBad
    clc
    rts
.SkAbsent:
    jsr SkStop
    lda #0
    sec
    rts
.SkBad:
    lda #1
    sec
    rts

; SkStore: complete the record (magic + checksum) and write it, then ACK-poll the
; chip's write cycle (<= 5 ms). C=0 written, C=1 the chip never answered.
SkStore:
    lda #$53
    sta SkBuf
    lda #$01
    sta SkBuf+1
    jsr SkSum
    sta SkBuf+R_CHK
    jsr SkStart
    lda #SK_CTRL_W
    jsr SkSend
    bcs .SkWfail
    lda #SK_ADDR_H
    jsr SkSend
    lda #SK_ADDR_L
    jsr SkSend
    ldy #0
.SkWr:
    sty SkL
    lda SkBuf,y
    jsr SkSend
    ldy SkL
    iny
    cpy #SK_REC_LEN
    bne .SkWr
    jsr SkStop
    lda #200
    sta SkL                     ; poll up to 200 times
.SkPoll:
    jsr SkStart
    lda #SK_CTRL_W
    jsr SkSend
    jsr SkStop                  ; (keeps C)
    bcc .SkWdone                ; ACK: the write cycle is over
    dec SkL
    bne .SkPoll
    sec
    jmp SkRelease
.SkWfail:
    jsr SkStop
    sec
    jmp SkRelease
.SkWdone:
    clc
SkRelease:                      ; leave the bus released (C kept)
    lda #0
    sta SWACNT
    ldx SkN
    dex
    dex
    dex                         ; (dex keeps C) SkN = 3: game over / run won
    bne .SkBack
    lda Level                   ; game over / run won: the title comes back on the level
    cmp #LEVEL_COUNT            ;   just played (no SaveKey needed): GameStart keeps
    bcc .SkKeep                 ;   Level when these two bytes hold the magic
    lda #0
    sta Level
.SkKeep:
    lda #$5A
    sta SkT
    lda #$A5
    sta SkL
    jmp Restart
.SkBack:
    jmp ReturnPad               ; back to the bank0 caller (the C flag survives)

; ------------------------------------------------------------------------------
; Ops
; ------------------------------------------------------------------------------
SkService:
    sta SkN                     ; the op: SkRelease restarts the run when it is 3
    tax
    beq SkBoot
    dex
    beq SkResume
    dex
    beq SkCheckpoint
    dex
    beq .SkGO
    jmp SkTitle                 ; 4 = the title's score window
.SkGO:
    jmp SkWriter                ; 3 = game over


SkBoot:
    jsr SkLoad
    bcs SkNothing
    ldy #2
.SkHi:
    lda SkBuf+R_HIGH,y          ; the title shows the high score now and then
    sta SkHi,y
    dey
    bpl .SkHi
    lda SkBuf+R_LEVEL           ; (state 0 = no run to resume, but the level of the
    cmp #LEVEL_COUNT            ;   last run stays selected: user 2026-11-11)
    bcs SkNothing
    sta Level
    jmp SkOk
SkNothing:
    sec
    jmp SkRelease

SkOk:
    clc
    jmp SkRelease

SkResume:
    jsr SkLoad
    bcs SkNothing
    lda SkBuf+R_STATE
    beq SkNothing
    lda SkBuf+R_LEVEL
    cmp Level
    bne SkNothing              ; another stage was picked: fresh start
    lda SkBuf+R_LIVES
    cmp #LIVES_MAX+1
    bcs SkNothing
    sta PlayerLives
    ldy #2
.SkSc:
    lda SkBuf+R_SCORE,y
    sta ScoreTh,y
    dey
    bpl .SkSc
    jmp SkOk

; The two writers share SkPrep (entered by `jmp`, so the call chain stays at
; pad 2 + SkLoad 2 + a leaf 2 = 6 stack bytes - the stack mirror is only 8 wide).
; SkN = 2 checkpoint, 3 game over. A missing key ends the op, bad data leaves a
; zero high score. SkBuf[R_HIGH..] = max(old high, current score) on the way out.
SkCheckpoint:
    lda Level
    cmp #LEVEL_COUNT
    bcc SkWriter                ; a stage advance
    lda #3
    sta SkN                     ; the last stage was cleared: the run is over
SkWriter:
    jsr SkLoad
    bcc .SkHave
    cmp #0
    bne .SkBadData
    sec                         ; absent: do not touch anything
    jmp SkRelease
.SkBadData:
    lda #0
    sta SkBuf+R_HIGH
    sta SkBuf+R_HIGH+1
    sta SkBuf+R_HIGH+2
.SkHave:
    ldy #0
.SkCmp:
    lda ScoreTh,y
    cmp SkBuf+R_HIGH,y
    bne .SkDiff
    iny
    cpy #3
    bne .SkCmp
    beq .SkMerged               ; equal
.SkDiff:
    bcc .SkMerged               ; score < high
    ldy #2
.SkCp:
    lda ScoreTh,y
    sta SkBuf+R_HIGH,y
    dey
    bpl .SkCp
.SkMerged:
    lda SkN
    cmp #3
    beq .SkOver
    lda #1
    sta SkBuf+R_STATE
    lda Level
    sta SkBuf+R_LEVEL
    lda PlayerLives
    sta SkBuf+R_LIVES
    ldy #2
.SkSv:
    lda ScoreTh,y
    sta SkBuf+R_SCORE,y
    dey
    bpl .SkSv
    jmp SkStore
.SkOver:
    lda Level                   ; the title comes back on the level just played
    cmp #LEVEL_COUNT            ;   (a cleared last stage wraps to the first)
    bcc .SkOvLv
    lda #0
.SkOvLv:
    sta SkBuf+R_LEVEL
    lda #0
    sta SkBuf+R_STATE
    sta SkBuf+R_SCORE
    sta SkBuf+R_SCORE+1
    sta SkBuf+R_SCORE+2
    lda #3
    sta SkBuf+R_LIVES
    jmp SkStore

; Op 4 TITLE (every title frame, no I2C): the HUD score window shows the 1-based
; stage number (packed BCD, 000001 = stage 1) and, for 64 of every 256 frames
; (EnemyRamP $80-$BF; it restarts at $F0 on every LoadLevel, so SELECT always
; shows the stage first), the HIGH SCORE BOOT left in SkHi. No high score (no key,
; blank chip) = the stage number only. DropArm's title path writes the same stage
; number once per LoadLevel (SELECT); this keeps it right in between.
SkTitle:
    lda Level
    clc
    adc #1
    ldx #0
.SkTen:
    cmp #10
    bcc .SkOnes
    sbc #10
    inx
    bne .SkTen                  ; (X <= 2: always taken)
.SkOnes:
    sta SkB
    txa
    asl
    asl
    asl
    asl
    ora SkB
    sta ScoreTe                 ; packed BCD: tens, ones
    lda #0
    sta ScoreTh
    sta ScoreHu
    lda EnemyRamP
    and #$C0
    cmp #$80
    bne .SkTdone                ; only clock $80-$BF (64 of 256 frames) shows it
    lda SkHi
    ora SkHi+1
    ora SkHi+2
    beq .SkTdone                ; no high score yet
    ldx #2
.SkTHi:
    lda SkHi,x
    sta ScoreTh,x
    dex
    bpl .SkTHi
.SkTdone:
    jmp ReturnPad

; ---- the SHAPE STEP of the room load (moved from bank3 2026-11-10, from bank7 to bank4 (the models share bank4) 2026-11-14) ------------------
; bank3 B3RoomBlocks (at $F453) does `sta BK_MODELS`; the next fetch (+3) is the jmp below.
; ShapeStep7 expands the room's shape block into the PF buffers and stages the hot flag in
; RoomMetaB; `sta $1FF7` at +6 returns to bank3 (B3Meta, +9).
FetchPtr = $E5
RoomPF0Lo = $99
RoomMetaB = $9A
PF0Buf = $C3
PF1Buf = $C7
PF2Buf = $CB
TILE_ROWS = 4
    org $F453 + 3
    jmp ShapeStep7
    org $F453 + 6
    sta BK_EXTRAS
    org $F460
ShapeStep7:
    lda RoomPF0Lo
    and #$7F                        ; shape index, 7 bits (128 shapes)
    asl                             ; *2: LEVEL_ShapeTable is a word table
    tax
    lda LEVEL_ShapeTable,X          ; block address = the table entry
    sta FetchPtr
    lda LEVEL_ShapeTable+1,X
    sta FetchPtr+1
    ldy #TILE_ROWS-1
.sp:
    lda (FetchPtr),Y                ; row index for this band (b7 = band 1's hot flag)
    and #$7F
    tax
    lda RowPoolPF0,X
    sta PF0Buf,Y
    lda RowPoolPF1,X
    sta PF1Buf,Y
    lda RowPoolPF2,X
    sta PF2Buf,Y
    dey
    bpl .sp
    ldy #1
    lda (FetchPtr),Y                ; band-1 index | hot b7
    and #$80
    lsr                             ; $80 -> $40 (MetaB b6)
    sta RoomMetaB
    jmp $F453 + 6                   ; sta $1FF7 -> bank3 B3Meta

; ---- DATA WINDOW: shape blocks + row pool + shape address table ----------------------
; (models_data.asm via generated/spill_bank3_shapes.asm; convert_level.py capacity-checks
; it as _BANK3_SHAPES_SLOT = $F4C0-$FBF7, below bank4's ReturnPad.)
    .ds $F4C0 - *, 0
    include "generated/spill_bank3_shapes.asm"


; ------------------------------------------------------------------------------
; Cross-bank twins (bank0 is the caller; every pad is split across the banks):
;   entry  A=$FC08: bank0 runs `sta $1FF8`; the fetch at $FC0B comes from HERE
;          = `jmp SkService` (bank0's own bytes at $FC0B are never fetched)
;   return $FBF8: this `sta $1FF4` selects bank0, whose `rts` at $FBFB returns
;          to the caller (bank0's ReturnPad is the same two instructions)
; ------------------------------------------------------------------------------
    .ds $F9BF - *, 0
    jmp PHMOverlay                 ; OverlayTramp hop (bank0 `sta BK_OVERLAY` at $F9BC)
    .ds $FBD0 - *, 0
    sta BK_ROOMS                   ; twin of bank0's EnterRoom pad (the transition frame jumps here)
    .ds $FBF8 - *, 0
ReturnPad:
    sta BK_GENERAL
    .ds $FC08 - *, 0
    sta BK_SAVE                    ; twin of CallPad_SaveKey (the `jmp` below is fetched after it)
    .ds $FC0B - *, 0
    jmp SkService
    .ds $FC20 - *, 0
    sta BK_ROOMS                   ; twin of LoadLevel (bank2 serves the jmp at $FC23)
    .ds $FC58 - *, 0
    sta BK_GENERAL                 ; bank0 $FC5B = jmp StartFrame
    jmp TransBody                  ; $FC5B: fetched after bank0's `sta BK_TRANS` pad at $FC58
    .ds $FC61 - *, 0
    jmp TransFinish                ; $FC61: after bank0's second pad at $FC5E
    .ds $FC64 - *, 0
    jmp TransAfterSave             ; $FC64: after bank0's third pad at $FC61
    .ds $FC70 - *, 0
RomVersion:
    include "version.asm"
    include "trans.inc"

; ==============================================================================
; Phase 4 asym-patch collision overlay cluster - moved here from bank0 (the bank0 reserve of >= 200 B).
; Entered from bank0's OverlayTramp: `sta BK_OVERLAY` at $F9BC, then the `jmp PHMOverlay` fetched at $F9BF
; (below). Exits are `jmp ReturnPad` ($FBF8: sta BK_GENERAL, bank0's rts at $FBFB = the PHM caller; flags kept).
; DoorLocked is inlined (OvDoorLocked); its hot tail is the HotOverlapFlag twin pad at $FFEC
; (`sta BK_EXTRAS`, the extras bank serves `jmp HotOverlapBody` at $FFEF and ends through ReturnPad).
; ColOff/ColMask are copies (bank0 keeps the pair for the PHM walk); OvHead/OvTail/M1OffTab live only here.
; ==============================================================================
RoomX = $80
PlayerDir = $82
LineCount = $84
Temp = $88
CollisionX = $8B
CollisionCellY = $8D
CollisionEndY = $8F
RectCount = $92
RoomPF0Lo = $99
RoomPF0Hi = $9A
LevelStartRoom = $A7
EnemyDeadMask = $BA
PF0Buf = $C3
PLAYER_WIDTH = 7
PHMOverlay:
    ; LineCount packed: b4-b7 = right_col+1, b0-2 = bands with the painted
    ; ball-strip ($ff BandTab entries). D6 envelope: ONE right column
    ; [BallX-7, BallX] px, BallX = 87+8*rc — overlay is additive (cells
    ; painted only where the mirrored cell is open, never hot).
    ; Exact visible_left (same math as PHM's prologue), then px overlap of
    ; [vl, vl+6] (PLAYER_WIDTH=7 lit) with the patch column, then band x rows.
    sec
    lda RoomX
    sbc PlayerDir
    cmp #15
    bcs .Ov7
    sec
    sbc #4
    jmp .OvVL
.Ov7:
    sbc #7
.OvVL:
    clc
    adc PlayerDir               ; A = visible_left px
    sta CollisionX              ; walk temps are free on the miss path
    lda LineCount
    lsr
    lsr
    lsr
    lsr                         ; n = right_col+1 (1..10)
    beq .OvClear                ; 2026-10-23: n = 0 means this room has NO ball
                                ;   column. Without this the test invented a
                                ;   phantom ball at x79 (BallX = 79 + 8n) and a
                                ;   player standing near it was routed to the
                                ;   shutter/right-door path, so the LEFT (M1)
                                ;   door test never ran — the door never blocked.
    asl
    asl
    asl                         ; 8n
    clc
    adc #79                     ; BallX = 79+8n = 87+8*rc (patch right edge)
    sta RectCount               ; scratch (NOT CollisionCellX): the prologue
                                ; box must survive for HotOverlapFlag — OvM1Block
                                ; funnels block hits there for hot-death. Scratch
                                ; = RectCount ($92): free after the cell walk,
                                ; RowIdx re-inits at kernel entry. NEVER Temp —
                                ; CheckP0Left/Right read the joystick in Temp
                                ; AFTER this physics call (Temp scratch here
                                ; left D3=0 = phantom right-press = drift bug).
    lda CollisionX
    cmp RectCount               ; vl vs BallX
    beq .OvT2
    bcs .OvClear                ; vl > BallX → player fully right of patch
.OvT2:                          ; (vl < BallX falls through)
    lda RectCount
    sec
    sbc #13                     ; BallX-13 (lit span is 7px, not 8: [vl,vl+6])
    cmp CollisionX              ; vs vl: overlap iff BallX-13 <= vl
    beq .OvBand
    bcs .OvClear                ; BallX-13 > vl: no overlap (2026-11-14: order swapped so the miss falls
                                ;   straight into OvM1Block - the `jmp` is gone, -3 B in a full bank)
.OvBand:
    jmp OvShutBand              ; band overlap → shutter kill / strip solid
.OvClear:
                                ; right-strip miss → M1 (left) strip test (OvM1Block follows);
                                ; IT returns with C set/clear.
                                ; Shutter rooms: miss here = player left of
                                ; the VISIBLE right-half block → passable
                                ; (kill follows the drawn block only, async
                                ; ruling 2026-10-14 — no left mirror)

OvM1Block:
    ; Phase 4 M1 (left strip) collision overlay. Entered by JMP from
    ; PHMOverlay's .OvClear — 0 pushes; both exits rts to the PHM caller.
    ; In: CollisionX = vl, CollisionCellY/EndY =
    ; player row range (survive the right tests — do NOT clobber the
    ; prologue box: CellX/EndX/CellY/EndY must stay intact, the block
    ; path hands them to HotOverlapFlag). Scratch = RectCount ($92; M1X,
    ; then ℓ math — see PHMOverlay note). Kill-aware
    ; (EnemyDeadMask b4); a row blocks iff its PF cell at col ℓ is open —
    ; the wall-hide envelope guarantees open ⟺ patched (every band at ℓ
    ; is wall or M1-patched, never plain-open).
    lda EnemyDeadMask
    and #$10                    ; b4 = M1 strip destroyed → transparent
    bne .OvM1no
    lda RoomPF0Lo               ; staged MetaA ($99)
    and #$01                    ; Phase 5: b0 = M1 strip on the RIGHT half
    tax                         ;   (door band mask is $02 → b0 free)
    lda RoomPF0Lo               ; reload MetaA
    lsr
    lsr
    lsr
    lsr                         ; m1_col+1 (0 = no M1 patch)
    beq .OvM1no
    asl
    asl
    asl                         ; 8*(m1_col+1)
    clc
    adc M1OffTab,X              ; -1 (left, $FF) / +79 (right, $4f) → the
                                ;   side's M1X (7+8*col / 87+8*col) — MUST
                                ;   match B3StageBand's staging (its own twin)
    sta RectCount               ; scratch M1X (EndX = prologue min col is
                                ; CollisionEndX — kept intact for HotOverlapFlag)
    ; --- contact test: the door is a solid 8 px block [M1X-7, M1X] --------
    ; The player box is 7 lit px [vl, vl+6], so the block must fire as soon
    ; as the boxes TOUCH: vl in [M1X-13, M1X]. Both sides are right-justified
    ; (the M1 is drawn [x-7, x]), so the same window covers a left-wall door
    ; approached from its right and a right-wall one from its left.
    ; Two earlier shapes were wrong and are recorded here so they stay dead:
    ;  - one-sided [M1X-12, M1X] blocked, but the LEFT door read the wrong PF
    ;    register (the old (M1X-7)>>3 cell) and never fired;
    ;  - [M1X-6, M1X] (span the strip's last px) fired only after the player
    ;    had walked 7 px INTO the art: "I can enter inside it, but I can't
    ;    pass its right side" — the block plane sat one tile right of the
    ;    drawing (user report 2026-10-23).
    ; 2026-10-25 (user, level 7 room 1: "half the player can move inside the
    ; wall"): below argument 15 SetObjectXPos strobes RESM1 inside HBLANK, so
    ; the strip is DRAWN 3 px right of [M1X-7, M1X] - the same clamp that makes
    ; the player's visible edge RoomX-4 (not -7) under x=15. The col-0 strip
    ; (M1X 7) occupies [3,10]; test the box edge 3 px closer. vl < 3 (the
    ; player at the screen edge) borrows: that is still contact.
    lda RectCount
    cmp #14                     ; M1X >= 14 (argument >= 15): no clamp
    lda CollisionX              ; vl = the box's left edge (lda keeps C)
    bcs .OvM1Cmp
    sbc #2                      ; C clear: A - 3
    bcc .OvM1Band
.OvM1Cmp:
    cmp RectCount               ; M1X = the strip column
    beq .OvM1Band               ; the column is the box's left edge
    bcs .OvM1no                 ; vl > M1X → the strip is left of the box
    clc
    adc #PLAYER_WIDTH + 6       ; vl + 13 = box right edge + the strip's 7 px
    cmp RectCount
    bcc .OvM1no                 ; vl + 13 < M1X → no contact with [M1X-7, M1X]
.OvM1Band:
    ; 2026-10-23: ℓ is the PF CELL of the strip (ColOff/ColMask are indexed by
    ; x>>2, 20 cells = the 80 px half, mirrored) - it was (M1X-7)>>3, which
    ; pointed one register off for a left strip: a door at col 7 (x=63, cell
    ; 15, PF2 bit 3) was looked up as cell 7 (PF1 bit 4), the live $FC has that
    ; bit set, so the scan read a WALL and called the door passable.
    lda RectCount
    lsr
    lsr                         ; ℓ = M1X / 4 = the PF cell (0..19 left half)
    cmp #20                     ; the 80 px half = 20 PF cells (mirrored)
    bcc .OvM1Cell
    eor #$FF                    ; right half: A = 255 - ℓ (one's complement)
    sec
    adc #39                     ; 255 - ℓ + 40 = 295 - ℓ = 39 - ℓ (mod 256)
                                ; reflect mapping (test_cell_map.visible_range).
                                ; Was `eor #%00011111` = 31 - ℓ, off by 8 cells:
                                ; the level-4 room 3 door (M1X 103, cell 25)
                                ; read cell 6, a WALL, and returned clc — the
                                ; player walked through it (2026-10-23 trace:
                                ; 268 overlaps, all .OvM1no, X=6 at $FAA6).
.OvM1Cell:
    tax                         ; X = ℓ (PHM callers preserve X themselves)
    lda CollisionCellY
    sta RectCount               ; $92 walk temp — free after the cell walk
                                ; (RowIdx re-inits at kernel entry)
.OvM1Row:
    lda RectCount
    clc
    adc ColOff,X                ; PF0/PF1/PF2 group offset (0/3/6)
    tay
    lda PF0Buf,Y                ; same cell read as PlayerHitsMap
    and ColMask,X
    beq .OvM1block              ; open → patch cell active in this row
    lda RectCount
    cmp CollisionEndY
    beq .OvM1no
    inc RectCount
    bne .OvM1Row                ; row never wraps to 0
.OvM1block:
    ; Blocked by the M1 cell: run the hot check too — convert emits the
    ; M1 patch cell as a hot rect on the hot band (mask $00, never dies
    ; with a wall), so touching the block on a hot band = death, exactly
    ; like a hot PF wall. Off-band / non-hot: body finds no rect → sec,
    ; still blocked. b4 (strip destroyed) never reaches here (.OvM1no).
    ; Phase 5 key: touching the M1 strip (left door) while KeyHeld removes
    ; it (b4) — touch, not mere possession.
    lda LevelStartRoom
    bmi .OvM1unlock
    jmp OvDoorLocked              ; locked: blocks in a cold room too (fill)
.OvM1unlock:
    lda EnemyDeadMask
    ora #$10                    ; b4 = M1 strip (left door) destroyed
    sta EnemyDeadMask
    clc
    jmp ReturnPad                         ; passable (bank0 caller)
.OvM1no:
    clc
    jmp ReturnPad

; ------------------------------------------------------------------------------
; OvShutBand — right-column strip on the PHMOverlay miss path. Entered from
; PHMOverlay .OvBand (right-column + player-band overlap). MetaB b7 marks a
; LOCKED_DOOR right strip; b7 clear is a plain D6 strip. A plain strip is
; solid. A door strip is solid until the key is held, then the touch
; destroys it (EnemyDeadMask b3) and the walk passes (Phase 5).
; Kill follows the VISIBLE right-half block only (async ruling 2026-10-14 —
; no left mirror). The retired vcrunch kill test is gone.
; ------------------------------------------------------------------------------
OvShutBand:
    ldx CollisionCellY
    lda OvHead,X                ; bits >= row
    ldx CollisionEndY
    and OvTail,X                ; bits <= row
    and LineCount               ; active-band mask (b0-2)
    beq .OSBm1                  ; not in a painted band → M1 strip test
    and #$02                    ; b1 = the box overlaps the strip's band 2 (the hot band)
    tax                         ;   X = 2 / 0 (PHM callers preserve X themselves)
    lda RoomPF0Hi               ; staged MetaB ($9A)
    bpl .OSBsolid               ; b7=0: plain D6 strip → solid
    lda LevelStartRoom          ; KeyHeld?
    bpl .OSBsolid               ; no key → locked (solid)
    lda EnemyDeadMask           ; key held: the touch destroys the strip
    ora #$08                    ; b3 = ball strip (right door) destroyed
    sta EnemyDeadMask
    jmp .OSBm1                  ; passable (strip blanked next B3StageBand)
.OSBsolid:
    ; User 2026-11-11 (level 9 room 1): "all elements (PF or simulating PF) in a hot band
    ; should kill on touch" - the ball strip is drawn in the hot colours there, so touching
    ; it on the hot band is HotBump (Temp b7), like the M1 block and a hot PF wall.
    txa
    beq .OSBsolidRet            ; not on the hot band
    bit RoomPF0Hi               ; MetaB: V = b6 hot room
    bvc .OSBsolidRet
    asl Temp
    sec
    ror Temp                    ; Temp b7 = HotBump: UpdateP0Vertical turns it into LoseLife
.OSBsolidRet:
    sec
    jmp ReturnPad
.OSBm1:
    jmp OvM1Block

OvDoorLocked:                   ; bank0's DoorLocked, inlined
    lda RoomPF0Hi               ; staged MetaB
    and #$40                    ; b6 = hot shape
    bne .ODLhot
    sec                         ; cold room: the door is simply solid
    jmp ReturnPad
.ODLhot:
    jmp $FFEC                   ; hot band: the overlap body owns the hit (C=1)

ColOff:     .byte 0,0,0,0, 4,4,4,4,4,4,4,4, 8,8,8,8,8,8,8,8
ColMask:    .byte $10,$20,$40,$80,$80,$40,$20,$10,$08,$04,$02,$01
; OvHead/OvTail/M1OffTab moved here from the overlay cluster (2026-11-11: the ball-strip
; hot kill needed their 10 bytes; they are data, position-free, but keep OvHead/OvTail adjacent -
; test_async_band3 reads them as one 8-byte signature).
OvHead:
    .byte 15,14,12,8            ; rows 0..3 -> mask bits >= row (4 bands)
OvTail:
    .byte 1,3,7,15              ; rows 0..3 -> mask bits <= row
M1OffTab:                       ; MetaA b0 -> M1 x-offset.
    .byte $ff, $4f              ; B3StageBand has the twin.

    .ds $FFEC - *, 0
    sta BK_EXTRAS                   ; twin of bank0's HotOverlapFlag (the extras bank serves the jmp at $FFEF)

    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
