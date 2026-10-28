    processor 6502
    seg code
    org $F000
; The power-up pad every bank carries: `lda #0 / sta $1FF4` selects bank0, whose
; $F005 is `jmp GameStart`. The restart ops (game over, last stage cleared) jump
; here: the run restarts at the title and never returns to the caller.
Restart:
    lda #0
    sta $1FF4
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
;   0 BOOT        title power-on: Level := the saved stage
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
LEVEL_COUNT = 20                ; hand copy of the kernel's LEVEL_COUNT

; Game variables (hand copies of kernel.asm; check_equ_sync pairs the names)
Level       = $A3
PlayerLives = $AC
ScoreTh     = $F3
ScoreHu     = $F4
ScoreTe     = $F5

; Scratch: dead at every call site (title / level load) - see the design doc.
SkB         = $88               ; byte being shifted (kernel Temp)
SkN         = $89               ; op flag (kernel ZPSpare89, free)
SkT         = $8B               ; (kernel CollisionX)
SkL         = $8E               ; loop counter (kernel CollisionEndX)
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
    jmp SkWriter                ; 3 = game over

SkBoot:
    jsr SkLoad
    bcs SkNothing
    lda SkBuf+R_STATE
    beq SkNothing              ; state 0: no save
    lda SkBuf+R_LEVEL
    cmp #LEVEL_COUNT
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
    lda #0
    sta SkBuf+R_STATE
    sta SkBuf+R_LEVEL
    sta SkBuf+R_SCORE
    sta SkBuf+R_SCORE+1
    sta SkBuf+R_SCORE+2
    lda #3
    sta SkBuf+R_LIVES
    jmp SkStore

; ------------------------------------------------------------------------------
; Cross-bank twins (bank0 is the caller; every pad is split across the banks):
;   entry  A=$FC08: bank0 runs `sta $1FF8`; the fetch at $FC0B comes from HERE
;          = `jmp SkService` (bank0's own bytes at $FC0B are never fetched)
;   return $FBF8: this `sta $1FF4` selects bank0, whose `rts` at $FBFB returns
;          to the caller (bank0's ReturnPad is the same two instructions)
; ------------------------------------------------------------------------------
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF4
    .ds $FC0B - *, 0
    jmp SkService

    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
