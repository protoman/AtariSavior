    processor 6502
; ==============================================================================
; Bank2 stub — selects bank0, jumps to GameStart
; ==============================================================================
    seg code
    org $F000

FetchPtr = $E0                   ; must match kernel.asm (operand baked in)
Temp = $88
MapPtrLo = $89                   ; rect4.x cache (P3.4)
MapPtrHi = $8A                   ; rect4.y cache
CollisionX = $8B
CollisionCellX = $8C             ; max text column
CollisionCellY = $8D             ; top tile row
CollisionEndX = $8E              ; min text column
CollisionEndY = $8F              ; bottom tile row
RectCount = $92
EnemyDataLo = $B1                ; record base — restaged before every exit
EnemyDataHi = $B2
BombPacked = $B5                 ; b3-6 WallMask (destroyed rect skip)
EnemyIndex = $B9                 ; slot save around the col swap + rect walk
RcBase = $C6
RcW1 = $C7
RcW2 = $CB
EnemyRamX = $BD
EnemyRamD = $C1                  ; dir bits: 1 = right, 0 = left
EnemyRamP = $C2                  ; free-running frame clock
EnemyRamY = $C3                  ; live Y (refreshed this overscan)
Rc4W = $DE
Rc4H = $DF
TILE_COLUMNS = 20

    ; --- 5-byte stub ---
    lda #0
    sta $1FF6                       ; select bank0
    jmp $F005                       ; GameStart in bank0

    ; --- E4 moth body (bank2 free space $F008-$F9D8) -------------------------
    ; Entered from bank0 via the $FEF0 entry tramp (sta $1FF8 lands on the
    ; jmp below at $FEF3). Exits via `jmp MothExitPad` ($FC49): bank2 runs
    ; sta $1FF6, bank0 serves jmp UE_Next. Rules:
    ;   - NEVER jsr FoldIndirect or any bank0 routine (a fold from inside
    ;     bank2 would switch away mid-routine = frozen player).
    ;   - Enemy records ARE here (org $F9D9) — read directly, no fold needed.
    ;   - Keep the whole routine inline (no jsr): tramps are tail jmps so
    ;     the stack depth equals the UE body (+0 vs the $F8 guard).
    ;   - ZP (rect cache, EnemyRam*, EnemyDataLo/Hi) is RAM: bank-independent.
    org $F100
MothRoutine:
    ; E4 Stage C: horizontal patrol (docs/e4_moth_plan.md). 1 px / 2 frames
    ; (EnemyRamP & 1), range = spawn ± 8 tiles (32 px), wall/range/wrap =
    ; flip dir + hold, clear = commit candidate. Row/col inputs feed a
    ; verbatim copy of PlayerHitsMap's P3.4 rect walk; HIT turns instead of
    ; returning C=1.
    ; In: X = slot, Y = record base, FetchPtr = record base (records are in
    ; THIS bank — direct (FetchPtr),Y reads, NO fold). NEVER jsr bank0
    ; (mid-bank2 fold = frozen player). Slot is saved to EnemyIndex because
    ; the col swap and walk both use X (E3 lesson). Every exit re-stages
    ; FetchPtr (the walk overwrites it with window bytes) then
    ; jmp MothExitPad (sta $1FF6 / jmp UE_Next in bank0).
    lda EnemyRamP
    and #1
    beq .MothRun              ; branch-over-jmp (tail labels exceed ±127)
    jmp .MothExit             ; ÷2 gate: 1 px / 2 frames
.MothRun:
    stx EnemyIndex             ; slot — turn/commit paths restore it
    lda EnemyRamD              ; live dir bit
    and MothBitTable,X
    bne .MothR
    lda EnemyRamX,X
    sec
    sbc #1
    jmp .MothChk
.MothR:
    lda EnemyRamX,X
    clc
    adc #1
.MothChk:
    cmp #160
    bcc .MothChk2             ; branch-over-jmp (tail labels exceed ±127)
    jmp .MothTurn             ; wrap (left edge) or off right edge -> turn.
.MothChk2:                    ; plan's mod-256 range test reads rel 208..255
                              ; as "in range" when spawn < 48 (tentacle family)
    sta Temp                   ; Temp = candidate X (free in overscan)
    iny                        ; Y = record+1 = ROM spawn X (bank2 local)
    lda (FetchPtr),Y
    sta CollisionX             ; range anchor (walk reuses CollisionX later)
    lda Temp
    sec
    sbc CollisionX             ; candidate - spawn (mod 256)
    cmp #33
    bcc .MothRangeOk           ; 0..32 = right half (8 tiles)
    cmp #224
    bcs .MothRangeOk           ; 224..255 = -32..-1 = left half -> in range
    jmp .MothTurn              ; 33..223 = out of spawn ± 8 tiles -> turn
.MothRangeOk:
    ; rows: cell space = 48-line BANDS (LINES_PER_TILE=48, TILE_ROWS=3 — the
    ; kernel .Row runs x3 and PHM's YToRowTable = floor(line/48), rects rows
    ; 0-2). The old >>4 (= /16) gave rows 3-4 at the moth's Y 54-82 = BELOW
    ; every rect -> the walk never hit -> sprite committed into the visible
    ; right wall (rendered band 1 cols 38-39 = rect row 1 mirror). Convert
    ; with the same lsr/lsr/tay + /48 table idiom as PHM.
    ; GRP1 window = scanlines Y+1..Y+8 (ObjTop = Y+1 formula).
    lda EnemyRamY,X
    clc
    adc #1                     ; top line = Y+1
    lsr
    lsr                        ; A = line >> 2 (48-entry table index)
    tay
    lda MothRowTable,Y
    sta CollisionCellY         ; top band row = floor((Y+1)/48)
    lda EnemyRamY,X
    clc
    adc #8                     ; bottom line = Y+8
    lsr
    lsr
    tay
    lda MothRowTable,Y
    sta CollisionEndY          ; bottom band row = floor((Y+8)/48)
    ; cols from VISIBLE left, not Temp: SetObjectXPos draws the sprite
    ; ~5/7 px LEFT of A (BombMarkWalls/PHM convention) — probing Temp let
    ; the moth sit ~7 px inside a wall before the probe saw it.
    sec
    lda Temp
    cmp #15
    bcs .Mvl7a
    sbc #4                     ; C=0 from cmp -> visible = Temp - 5
    jmp .MvlA
.Mvl7a:
    sbc #7                     ; C=1 -> Temp - 7
.MvlA:
    lsr
    lsr                        ; first block = vl >> 2
    cmp #TILE_COLUMNS
    bcc .MothC1
    sta CollisionX
    lda #39
    sec
    sbc CollisionX
.MothC1:
    sta CollisionEndX          ; min text column
    sec
    lda Temp
    cmp #15
    bcs .Mvl7b
    sbc #4
    jmp .MvlB
.Mvl7b:
    sbc #7
.MvlB:
    clc
    adc #7                     ; last block = (visible_left + 7) >> 2
    lsr
    lsr
    cmp #TILE_COLUMNS
    bcc .MothC2
    sta CollisionX
    lda #39
    sec
    sbc CollisionX
.MothC2:
    sta CollisionCellX         ; max text column
    lda CollisionEndX          ; mirror reverses order -> ensure min <= max
    cmp CollisionCellX
    bcc .MothColsOk
    ldx CollisionCellX
    stx CollisionEndX
    sta CollisionCellX
.MothColsOk:

; --- Walk rectangle list (verbatim copy of PlayerHitsMap's P3.4 walk;
;     HIT jumps to .MothTurn instead of bank0's HotOverlapFlag) ---
    lda RcBase
    bne .MwGo
    jmp .MothNoHit
.MwGo:
    sta RectCount
    lda #RcW1
    sta FetchPtr
    lda #$00
    sta FetchPtr+1
    ldy #0
.MwLoop:
    tya
    lsr
    lsr
    tax
    lda MothMaskBit,X
    and BombPacked
    bne .MwNext               ; destroyed rect -> not solid
    lda (FetchPtr),Y          ; rect.x
    cmp CollisionCellX
    beq .MwColOk
    bcs .MwNext
.MwColOk:
    sta CollisionX
    iny
    iny                       ; rect.w
    clc
    lda (FetchPtr),Y
    adc CollisionX
    cmp CollisionEndX
    beq .MwNrmCol
    bcc .MwNrmCol
    dey                       ; rect.y
    lda (FetchPtr),Y
    cmp CollisionEndY
    beq .MwRowOk
    bcs .MwNrmRow
.MwRowOk:
    iny
    iny                       ; rect.h
    clc
    lda (FetchPtr),Y
    sta CollisionX
    dey
    dey
    lda (FetchPtr),Y
    adc CollisionX
    cmp CollisionCellY
    beq .MwNrmRow
    bcc .MwNrmRow
    jmp .MothTurn             ; HIT — wall: flip dir, hold position
.MwNrmCol:
    dey
    dey
.MwNext:
    dec RectCount
    beq .MothNoHit
    tya
    clc
    adc #4
    tay
    cpy #16
    beq .MwStage3
    cpy #8
    bcc .MwLoop
    lda #RcW2
    sta FetchPtr
    jmp .MwLoop
.MwNrmRow:
    dey
    bpl .MwNext               ; Y <= 16 -> N clear, always taken
.MwStage3:
    lda MapPtrLo              ; rect4.x
    cmp CollisionCellX
    beq .MwS3c
    bcs .MothNoHit
.MwS3c:
    sta CollisionX
    clc
    lda Rc4W
    adc CollisionX
    cmp CollisionEndX
    beq .MothNoHit
    bcc .MothNoHit
    lda MapPtrHi              ; rect4.y
    cmp CollisionEndY
    beq .MwS3r
    bcs .MothNoHit
.MwS3r:
    clc
    lda Rc4H
    adc MapPtrHi
    cmp CollisionCellY
    beq .MothNoHit
    bcc .MothNoHit
    jmp .MothTurn             ; rect4 hit — flip dir, hold
.MothNoHit:
    ldx EnemyIndex            ; slot back (walk used X for the mask index)
    lda Temp
    sta EnemyRamX,X           ; clear -> commit candidate step
    jmp .MothExit
.MothTurn:
    ldx EnemyIndex
    lda MothBitTable,X        ; flip dir bit, hold X (no commit)
    eor EnemyRamD
    sta EnemyRamD
.MothExit:
    lda EnemyDataLo           ; restage record base (walk overwrote FetchPtr)
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    jmp MothExitPad

; Slot-indexed dir bits (bank2-local copy — bank0's EnemyBitTable reads as
; level-data bytes at these addresses in this bank)
MothBitTable:
    .byte $01, $02, $04

; Destroyed-rect mask bits, index = global rect offset >> 2 (copy of
; kernel.asm's BombMaskBit)
MothMaskBit:
    .byte $08, $10, $20, $40

; 48-line band row lookup — copy of kernel's YToRowTable (bank2 cannot read
; bank0 ROM). Index = line >> 2, value = floor(line/48) = band row 0-3.
; Max in-cave index = (143+8) >> 2 = 37 — fits.
MothRowTable:
    .byte 0,0,0,0,0,0,0,0,0,0,0,0
    .byte 1,1,1,1,1,1,1,1,1,1,1,1
    .byte 2,2,2,2,2,2,2,2,2,2,2,2
    .byte 3,3,3,3,3,3,3,3,3,3,3,3

    ; --- Level data (frozen addresses — pointer values must match bank0's
    ;     original layout, level_bank_plan P2.1: $F9D9-$FB1E = 326B) ---
    org $F9D9
    include "generated/levels_data.asm"
    include "generated/levels.asm"

; ------------------------------------------------------------------------------
; E4 moth exit tramp ($FC49-$FC4B) — byte-identical slice with kernel.asm's
; MothExitPad (guard: verify_build check_moth_tramp). bank2 executes
; `sta $1FF6`; the fetch at $FC4C comes from bank0 = `jmp UE_Next`
; (bank0's own label). This file's bytes from $FC4C never run.
; Pinned at $FC49 (NOT $FFF2): $FFF6-$FFF9 are F6 hotspot mirrors — a peek
; of those addresses calls checkSwitchBank in Stella and flips banks
; mid-instruction (see kernel.asm MothExitPad comment).
; ------------------------------------------------------------------------------
    .ds $FC49 - *, 0
MothExitPad:
    sta $1FF6

; ------------------------------------------------------------------------------
; FoldIndirect — byte-identical copy of kernel.asm's block (same $FEF6
; address). bank0 executes bytes 1-3 (`sta $1FF8`, absolute — P3.1 deviation,
; see kernel.asm) then fetches bytes 4-9
; here (data bank active); `sta $1FF6` switches back, rts fetched from bank0.
; Guard: verify_build compares bank0/bank2 regions byte-for-byte.
; ------------------------------------------------------------------------------
; ------------------------------------------------------------------------------
; E4 moth entry tramp — byte-identical with kernel.asm's $FEF0 copy
; (guard: verify_build check_moth_tramp). bank2's `sta $1FF8` half never
; runs (entry always arrives from bank0); the `jmp MothRoutine` half at
; $FEF3 runs after bank0's switch. Assembles to the same 6 bytes as
; kernel's `sta $1FF8 / jmp $F100` — operand drift fails the guard.
; ------------------------------------------------------------------------------
    .ds $FEF0 - *, 0
UE_MothTramp:
    sta $1FF8
    jmp MothRoutine
    .ds $FEF6 - *, 0
FoldIndirect:
    sta $1FF8
    lda (FetchPtr),Y
    sta $1FF6
    rts

    ; Pad to vectors at $FFFA ($FFF2-$FFF9 = fill — never code: $FFF6-$FFF9
    ; are F6 hotspot mirrors on peek, see MothExitPad at $FC49)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
