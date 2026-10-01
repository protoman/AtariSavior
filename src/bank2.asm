    processor 6502
; ==============================================================================
; Bank2 stub — selects bank0, jumps to GameStart
; ==============================================================================
    seg code
    org $F000

FetchPtr = $E5                   ; must match kernel.asm (operand baked in;
                                 ; moved S3.2 from $E0 — frees $E0 for
                                 ; rect4.h in the uniform rect cache)
Temp = $88
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
RcBase = $89                    ; count — outside bank1's $E0-$EF stomp zone
RcW1 = $CC                       ; walk base — uniform stride incl. rect4 (S3.2)
EnemyRamX = $BD
EnemyRamD = $C1                  ; dir bits: 1 = right, 0 = left
EnemyRamP = $C2                  ; free-running frame clock
EnemyRamY = $E2                  ; live Y (refreshed this overscan — after
                                 ; the bank1 HUD score-ptr stomp; S3.4)
TILE_COLUMNS = 20
RoomY = $81                    ; player Y — LaserHitTest vertical window
EnemyCount = $B3               ; LaserHitTest loop bound
EnemyDeadMask = $BA            ; LaserHitTest dead bits (written on kill)
LAMP = 5                       ; enemy type: editor lamp — kernel LAMP must match
; --- BuildColupF (S5.1, moved from bank0) — addresses must match kernel.asm ---
TILE_ROWS = 3                     ; playable color bands (rows 0-2 of ColupfBuf)
RoomRectsLo = $90                 ; hot/solid rect stream — read directly here
RoomRectsHi = $91
RoomNo      = $98
LevelWallColor = $AA              ; stripe rows 0+2
LevelWallColor2 = $AB              ; stripe row 1
TickCounter = $AD                 ; 60-frame game timer — hot-pulse phase bit 4
ColupfBuf   = $E7                 ; 12-byte COLUPF image (rows 0-2 used)
COLOR_CAVE_BG = $00
COLOR_DARK_PF = $04               ; dark-room fuse walls
COLOR_HOT_Y = $1C                 ; kernel COLOR_BLINK_Y
COLOR_HOT_R = $44                 ; kernel COLOR_BLINK_R

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
    tay                         ; S3.2: uniform stride through rect4 —
    jmp .MwLoop                 ; no window jump, no .MwStage3
.MwNrmRow:
    dey
    bpl .MwNext               ; Y <= 19 -> N clear, always taken
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
; kernel.asm's BombMaskBit; index 4 = $00 — rect4 never masked, S3.2)
MothMaskBit:
    .byte $08, $10, $20, $40, $00

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
; ReturnPad ($FBF8) — byte-identical to kernel.asm's copy (sta $1FF6 / rts).
; S5.1 pad bodies (BuildColupF) tail-jmp here: sta switches this bank to
; bank0, the rts is then fetched from bank0's identical copy, and the stack
; still holds the bank0 jsr CallPad_* return address.
; ------------------------------------------------------------------------------
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF6
    rts

; ------------------------------------------------------------------------------
; CallPad_BuildColupF — byte-identical stub. Execution starts in bank0; after
; `sta $1FF8` the pad's `jmp $FC4F` is FETCHED FROM THIS BANK (the switch
; happens mid-pad, same reason bank1 mirrors the whole pad block).
; ------------------------------------------------------------------------------
    .ds $FC38 - *, 0
CallPad_BuildColupF:
    sta $1FF8
    jmp $FC4F

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
; BuildColupF — MOVED from bank0 (S5.1, CallPad_BuildColupF -> jmp $FC4F).
; Body as it was in kernel.asm, with S5.1 adaptations:
;   - jsr FoldIndirect x4 -> lda (FetchPtr),Y: the rect stream lives in
;     THIS bank (direct read, same pattern as the moth records).
;     (The shared $FEF6 fold's sta $1FF6 always returns to bank0, so a
;     fold inside ANY other bank's body cannot work.)
;   - jsr CallPad_IsRoomDark -> inlined below: pads cannot nest (ReturnPad
;     switches to bank0; rts would resume at this address in bank0).
;   - rts -> jmp $FBF8 (ReturnPad) for the bank0 VBLANK caller.
; ------------------------------------------------------------------------------
    .ds $FC4F - *, 0
BuildColupF:
    ; Bomb save ($F0-$F2 → collision temps) deleted S3.0b: this body writes
    ; ColupfBuf rows 0-2 only — it never reached $F0-$F2 (vestigial from
    ; the 12-row era; kernel .AfterRows restore deleted in the same commit).
    ; --- stripe fill ---
    ldx #0
.BCFstripe:
    cpx #1
    bne .BCFc1
    lda LevelWallColor2
    jmp .BCFstore
.BCFc1:
    lda LevelWallColor
.BCFstore:
    sta ColupfBuf,X
    inx
    cpx #TILE_ROWS
    bne .BCFstripe
    ; --- pulse color → Temp (free until .BgStore) ---
    lda TickCounter
    and #$10
    beq .BCFpulseY
    lda #COLOR_HOT_R
    jmp .BCFpulse
.BCFpulseY:
    lda #COLOR_HOT_Y
.BCFpulse:
    sta Temp
    ; --- walk hot rects, overwrite those rows ---
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    lda (FetchPtr),Y            ; solid count (direct read — data in bank2)
    asl
    asl
    clc
    adc #1
    tay                         ; Y → hot count
    lda (FetchPtr),Y
    beq .BCFdone
    sta RectCount
    iny
.BCFrect:
    tya
    pha
    iny
    iny                         ; Y = base+2 (y; record = mask, x, y, w, h)
    lda (FetchPtr),Y
    sta CollisionCellX          ; first row
    iny
    iny                         ; Y = base+4 (h)
    clc
    lda (FetchPtr),Y
    adc CollisionCellX
    sta CollisionX              ; one-past last row
    ldx CollisionCellX
.BCFrow:
    cpx #TILE_ROWS
    bcs .BCFrectDone
    cpx #12
    bcs .BCFrectDone
    lda Temp
    sta ColupfBuf,X
    inx
    cpx CollisionX
    bne .BCFrow
.BCFrectDone:
    pla
    clc
    adc #5
    tay
    dec RectCount
    bne .BCFrect
.BCFdone:
    ; --- Dark room: walls black; fuse (state=1) walls dark grey ---
    ; Inlined bank1 IsRoomDark: rooms 4+ never dark; EnemyRamD bits 4-7 =
    ; dark flag for rooms 0-3 (bit set = dark).
    lda RoomNo
    cmp #4
    bcs .BCFdarkDone            ; rooms 4+ never dark (mask covers 0-3)
    tax
    lda BCFDarkMask,X           ; $10/$20/$40/$80 = BitMaskTable[4+RoomNo]
    and EnemyRamD
    beq .BCFdarkDone            ; lit → keep stripe/hot colors
    lda BombPacked
    and #%00000011
    cmp #1
    beq .BCFFuseGrey            ; bomb fuse active → dark grey walls
    lda #COLOR_CAVE_BG          ; black walls (matches black background)
    beq .BCFdarkFill            ; A=$00 (COLOR_CAVE_BG) → always taken
.BCFFuseGrey:
    lda #COLOR_DARK_PF          ; hue 0 luma 2 = very dark grey walls
.BCFdarkFill:
    ldx #0
.BCFdarkLoop:
    sta ColupfBuf,X
    inx
    cpx #TILE_ROWS
    bne .BCFdarkLoop
.BCFdarkDone:
    jmp $FBF8                   ; ReturnPad → bank0 VBLANK caller
BCFDarkMask:
    .byte $10, $20, $40, $80    ; IsRoomDark bits for RoomNo 0-3

; ------------------------------------------------------------------------------
; HotOverlapBody — MOVED from bank0 (S5.3, kernel `jmp HotOverlapFlag` at
; $FE80 tramp -> `jmp $FCF0` here). Fold-free: the hot-rect stream (RoomRects)
; is level data in THIS bank, so the 7 `jsr FoldIndirect` become direct
; `lda (FetchPtr),Y` (one less push level on the hot path too).
; Behavior (full docs moved with the body): if the player's proposed tile
; range (CollisionCell*) overlaps any hot-only rect, set Temp bit 7 (HotBump).
; Called from PlayerHitsMap HIT while CollisionCell* still describe the
; rejected position. Hot record = parent mask, x, y, w, h (5 B); parent mask
; & BombPacked != 0 = that wall was blasted -> hot piece dead.
; Contract: TAIL-CALLED from bank0 (`jmp`, 0 push) — every exit must return
; C=1 to the ORIGINAL PlayerHitsMap caller. Exits therefore end
; `sec / jmp $FBF8` (ReturnPad: sta $1FF6 switches to bank0, rts pops the
; pre-tramp return address; sta touches neither A nor flags -> C survives).
; Clobbers A/X/Y/FetchPtr/RectCount (caller returns immediately after).
; ------------------------------------------------------------------------------
    .ds $FCF0 - *, 0            ; pinned: bank0 tramp operand is literal $FCF0
HotOverlapBody:
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    lda (FetchPtr),Y            ; solid count (direct read — data in this bank)
    asl
    asl                         ; *4
    clc
    adc #1                      ; +1 count byte → hot count offset
    tay
    lda (FetchPtr),Y            ; hot count
    beq .HOVdone                ; no hot rects
    sta RectCount
    iny                         ; first hot rect base
.HOVloop:
    tya
    pha
    ; Parent gate — skip if the containing wall piece was already blasted.
    lda (FetchPtr),Y            ; hot parent mask ($00 = never dies)
    and BombPacked
    bne .HOVnext
    iny                         ; Y = base+1 (x)
    ; Column overlap (same tests as PlayerHitsMap)
    lda (FetchPtr),Y            ; rect.x
    cmp CollisionCellX
    beq .HOVcolOk
    bcc .HOVcolOk
    bne .HOVnext                ; A > cellX → Z=0 (was jmp, -1B)
.HOVcolOk:
    sta CollisionX
    iny
    iny                         ; Y = base+3 (w)
    clc
    lda (FetchPtr),Y            ; rect.w
    adc CollisionX
    cmp CollisionEndX
    beq .HOVnext
    bcc .HOVnext
    ; Row overlap (base+3 → base+2 = y, same as PlayerHitsMap dey).
    dey                         ; Y = base+2 (y)
    lda (FetchPtr),Y            ; rect.y
    cmp CollisionEndY
    beq .HOVrowOk
    bcc .HOVrowOk
    bne .HOVnext                ; A > endY → Z=0 (was jmp, -1B)
.HOVrowOk:
    iny
    iny                         ; Y = base+4 (h)
    clc
    lda (FetchPtr),Y            ; rect.h
    sta CollisionX
    dey
    dey                         ; Y = base+2 (y)
    lda (FetchPtr),Y            ; rect.y (re-read for y+h)
    adc CollisionX              ; y+h
    cmp CollisionCellY
    beq .HOVnext
    bcc .HOVnext
    ; Hot hit
    pla
    lda Temp
    ora #%10000000
    sta Temp
    sec                         ; tail-call contract: return C=1
    jmp $FBF8                   ; ReturnPad → original caller (C survives)
.HOVnext:
    pla
    clc
    adc #5
    tay
    dec RectCount
    bne .HOVloop
.HOVdone:
    sec                         ; tail-call contract: return C=1
    jmp $FBF8                   ; ReturnPad → original caller (C survives)

; ------------------------------------------------------------------------------
; HOF entry tramp ($FE80-$FE85) — byte-identical with kernel.asm's copy
; (guard: verify_build check_moth_tramp). bank0 executes `sta $1FF8` at
; $FE80-$FE82; the fetch at $FE83 comes from THIS bank = `jmp $FCF0`. Neither
; bank runs its other half: bank0 is switched away at $FE82, bank2 never
; enters at $FE80. Pinned $FE80: the $FBF8-$FC48 pad window is full (5 B
; left, a stub needs 6 B) and $FE86-$FEEF is the only free hole before the
; moth tramp's $FEF0.
; ------------------------------------------------------------------------------
    .ds $FE80 - *, 0
HotOverlapFlag:
    sta $1FF8                   ; dead in bank2 (entry arrives at $FE83)
    jmp HotOverlapBody          ; == $FCF0 — operand guard vs bank0 literal
    .ds $FE86 - *, 0            ; S5.4 LHT tramp — byte-identical w/ kernel.asm
LaserHitTest:
    sta $1FF8                   ; dead in bank2 (entry arrives at $FE89)
    jmp LaserHitTestBody        ; == $FF00 — operand guard vs bank0 literal

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

; ------------------------------------------------------------------------------
; LaserHitTestBody — MOVED from bank0 (S5.4, entry tramp $FE86 -> `jmp $FF00`).
; Swept laser kill. CollisionX = cur M0 arg, stored by LaserInput .LaserPos
; (held path only). Interval = [cur, cur+W-1] where W = wall-clamped beam
; width (S6): the kernel stages bound = W+7 in RectCount before this call
; (was hardcoded 7/15 for the fixed 8px missile); sweep steps are 8 px so
; consecutive frames tile gap-free — no prev-frame storage needed.
; Vertical: beam rows [RoomY+2, RoomY+3] vs enemy [Y,+7] ->
; (RoomY-Y)+3 in [0..8]. Horizontal: |eLo-lo| <= W-1 via (d+7) < bound;
; arg clamped [0,159] = screen-edge clip.
; Fold-free: enemy records are level data in THIS bank — stage once, direct
; `lda (FetchPtr),Y` for the type (was `jsr FoldIndirect`).
; RESULT PROTOCOL (pads cannot nest from a pad body — the kill/lamp actions
; stay in bank0's LaserInput): every exit returns A + Z through ReturnPad
; (sta/rts preserve both): A=0 miss / #$50 kill (dead bit set here, caller
; scores) / A=1 lamp (caller does CallPad_SetRoomDark — same as player-body
; touch; no kill, no score). First live enemy in span only (next frame the
; dead mask skips it — no resurrection, no double score).
; Does NOT touch Temp (joystick still live at the call site).
; Clobbers A/X/Y/FetchPtr (caller re-inits X before SetObjectXPos next
; frame; LaserInput dispatches on A right after the return).
; ------------------------------------------------------------------------------
    .ds $FF00 - *, 0            ; pinned: bank0 tramp operand is literal $FF00
LaserHitTestBody:
    ; --- Stage (P3.1): enemy record pointer — loop writes no FetchPtr ---
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    ldx #0
.LHLoop:
    cpx EnemyCount
    bcs .LHTOut
    lda EnemyDeadMask
    and EnemyBitTable,X
    bne .LHNext
    lda RoomY
    sec
    sbc EnemyRamY,X
    clc
    adc #3                      ; (RoomY-eY)+3 in [0..8] = eY in [RoomY-5, RoomY+3]
    cmp #9                      ; out of beam rows RoomY+2..3
    bcs .LHNext
    lda EnemyRamX,X
    sec
    sbc CollisionX
    clc
    adc #7
    cmp RectCount               ; (eLo-lo)+7 vs bound=W+7 → hit iff d <= W-1
                                ; (S6: RectCount staged by kernel LaserInput)
    bcs .LHNext
.LHHit:
    ldy EnemyOffTable,X         ; type offset into staged record
    lda (FetchPtr),Y            ; direct — level data in this bank (was fold)
    cmp #LAMP
    beq .LHLamp
    lda EnemyDeadMask
    ora EnemyBitTable,X
    sta EnemyDeadMask
    lda #$50                    ; result: kill — caller adds #$50 score
    jmp $FBF8                   ; ReturnPad → bank0 caller (A/Z/C preserved)
.LHLamp:
    lda #1                      ; result: lamp — caller crashes the lamp
    jmp $FBF8
.LHNext:
    inx
    bne .LHLoop
.LHTOut:
    lda #0                      ; result: miss (Z set for caller's beq)
    jmp $FBF8

; Type-offset table (copy of kernel EnemyOffTable: enemy index * 4; S4.1) and
; dead-bit table (copy of kernel EnemyBitTable) — bank0 ROM is not visible
; from here; labels keep the kernel-side test anchors working.
EnemyOffTable:
    .byte 0,4,8

EnemyBitTable:
    .byte $01, $02, $04, $08

    ; Pad to vectors at $FFFA ($FFF2-$FFF9 = fill — never code: $FFF6-$FFF9
    ; are F6 hotspot mirrors on peek, see MothExitPad at $FC49)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
