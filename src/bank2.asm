    processor 6502
; ==============================================================================
; Bank2 stub — selects bank0, jumps to GameStart
; ==============================================================================
    seg code
    org $F000

FetchPtr = $E5                   ; must match kernel.asm (operand baked in;
                                 ; moved S3.2 from $E0 — frees $E0 for
                                 ; rect4.h in the uniform rect cache)
WSYNC   = $02                 ; TIA — values must match kernel.asm (equ-sync)
NUSIZ0  = $04
NUSIZ1  = $05
COLUP0  = $06
COLUP1  = $07
COLUBK  = $09                ; kernel line 41
REFP0   = $0B                ; kernel line 43
COLOR_PLAYER = $48               ; must match kernel.asm
RESP0   = $10
RESP1   = $11
HMP0    = $20                   ; TIA — for the SetObjectXPos_t2 title copy
HMP1    = $21
RESM0   = $12
RESM1   = $13
GRP0    = $1B
GRP1    = $1C
ENAM0   = $1D
ENAM1   = $1E
ENABL   = $1F
CTRLPF  = $0A
VDELP0  = $25
VDELP1  = $26
Temp = $88
RoomX = $80                      ; PHMOverlay visible_left math (Phase 4)
PlayerDir = $82
LineCount = $84                  ; OverlayTramp gate — packed byte copied
                                 ; from $8F at bank1 HUD entry each frame
RoomPF0Lo = $99                 ; TilePF0 pointer INSIDE EnterRoomB2 only.
RoomPF0Hi = $9A                 ; After the 9-byte PF copy + meta read, entry
                                 ; OVERWRITES both with the room's MetaA/MetaB:
                                 ; no other code needs the pointer (all meta
                                 ; readers use the staged pair below), so the
                                 ; bytes carry the meta for the whole visit.
RoomMetaA = $99                 ; staged MetaA (band mask/m1 col/side/door-L)
RoomMetaB = $9A                 ; staged MetaB (ball col/hot/door-R+shutter b7)
LevelPFDataLo = $9F             ; level block base = RoomShapes column (kernel
LevelPFDataHi = $A0             ;   decl; C2: shape idx | band | extras)
LevelRoomN = $A1                ; rooms in the level (kernel decl, C4 2026-10-20)
LevelConnSpare = $A2            ; C1 2026-10-20: exit-scan target byte (the
                                ;   byte was freed when LevelConnHi died;
                                ;   exit handlers are cold path, single frame).
                                ;   C2 2026-10-20: also the first-record sum
                                ;   in EnterRoomB2 (scan already returned).
RoomBandColor = $BC             ; band-color cache (kernel EQU, S3.1)
BandTab = $ED                   ; Phase 3 band gate bytes — staged here,
                                 ; read by kernel .Row in bank0
CollisionX = $8B
CollisionCellX = $8C             ; max text column
CollisionCellY = $8D             ; top tile row
CollisionEndX = $8E              ; min text column
CollisionEndY = $8F              ; bottom tile row
RectCount = $92
EnemyDataLo = $B1                ; record base — restaged before every exit
EnemyDataHi = $B2
BombPacked = $B5                 ; b3-6 WallMask (destroyed rect skip)
BombX = $F6                      ; hand-copy kernel EQU — title: 68 = no bomb,
                                 ;   140 = armed (TitleKernel P1 SOXP reads it)
BombTimer = $F7                  ; hand-copy kernel EQU — title fuse/explode
EnemyIndex = $B9                 ; slot save around the col swap + rect walk
                                 ; (LevelStartRoom hand-copy retired 2026-10-20:
                                 ;   its readers OvM1Block/OvShutBand moved to
                                 ;   bank0, which reads the byte natively)
EnemyDeadMask = $BA              ; b0-2 enemy kills; b3 = ball strip
                                 ; destroyed (bank1 StripBlastCheck); b4 = M1
                                 ; strip destroyed (M1StripBlast) — check_equ_sync
                                 ; pairs this with kernel's decl)
RcBase = $89                    ; count — outside bank1's $E0-$EF stomp zone
RcW1 = $CC                       ; walk base — uniform stride incl. rect4 (S3.2)
EnemyRamX = $BD
LaserState = $C0                  ; b5-2 = RoomDarkMask rooms 4-7 (BCFDarkRun)
EnemyRamD = $C1                  ; dir bits: 1 = right, 0 = left
EnemyRamP = $C2                  ; free-running frame clock
EnemyRamY = $E2                  ; live Y (refreshed this overscan — after
                                 ; the bank1 HUD score-ptr stomp; S3.4)
TILE_COLUMNS = 20
RoomY = $81                    ; player Y — LaserHitTest vertical window
PF0Buf = $C3                   ; PF render buffers rows 0-2 ($C3-$CF) —
                                ; cell map read here; must match kernel.asm
PlayerDir = $82                ; must match kernel.asm — S6 LWC tip direction
EnemyCount = $B3               ; LaserHitTest loop bound
EnemyDeadMask = $BA            ; LaserHitTest dead bits (written on kill)
; Grp0Ptr/Grp0PtrHi/SWCHA/PlayerSprite*/PlayerWalk* EQUs retired 2026-10-20:
; their only reader (PickPlayerFrame) moved to bank0 and uses the real labels.
LAMP = 5                       ; enemy type: editor lamp — kernel LAMP must match
RAFT = 7                       ; enemy type: moving raft — kernel ENEMY_RAFT
SNAKE = 2                      ; enemy type: kernel ENEMY_SNAKE (load-dir invert)
; --- BuildColupF (S5.1, moved from bank0) — addresses must match kernel.asm ---
TILE_ROWS = 3                     ; playable color bands (rows 0-2 of ColupfBuf)
RoomRectsLo = $90                 ; hot/solid rect stream — read directly here
RoomRectsHi = $91
RoomNo      = $98
LevelWallColor = $AA              ; stripe rows 0+2
LevelWallColor2 = $AB              ; stripe row 1
TickCounter = $AD                 ; 60-frame game timer — hot-pulse phase bit 4
ColupfBuf   = $E7                 ; 12-byte COLUPF image (rows 0-2 used)
COLOR_BOMBS = $46                ; kernel COLOR_BOMBS — fuse bomb color
COLOR_CAVE_BG = $00
COLOR_DARK_PF = $04             ; dark-room fuse walls
COLOR_HOT_Y = $1C               ; kernel COLOR_BLINK_Y
COLOR_HOT_R = $44               ; kernel COLOR_BLINK_R
; --- TallyEntry (level-bonus tally) — hand-copies, check_equ_sync guarded ---
TallyTicks = $F2                ; countdown, 50-pt units (kernel EQU)
DropTarget = $8A                ; $FE = tally sentinel (hand-copy kernel byte)
BarLevel = $AE                  ; time bonus input (120 = full)
PlayerBombs = $F0               ; 50 pts each unspent
PlayerLives = $AC               ; 100 pts each remaining
JetPower = $96                  ; cleared at arm (no thrust flutter)
LaserX = $83                  ; travelling beam X (kernel decl; arm resets to 0)
BombSnd = $F1                   ; coin hold — bank1 UpdateBombSound decs it
AUDC0 = $15                     ; TIA — coin tone regs (any bank may write)
AUDF0 = $17
AUDV0 = $19
; --- LoadLevelB2 / bank2 map labels — hand-copies, check_equ_sync guarded ---
; (The SelectActiveObject hand-copies left with the body, A1 2026-10-20.)
LevelMinerRoom = $A4             ; room index; b7 = miner faces right
MinerX = $A5
MinerY = $A6
LevelStartRoom = $A7             ; b7 = KeyHeld (loaded with the level entry)
; --- LoadLevelB2 (MOVED here, C2 2026-10-20) — hand-copies, check_equ_sync ---
Level = $A3                      ; current level index (kernel decl $A3)
LevelStartX = $A8                ; level start x (kernel constant 32)
LevelStartY = $A9                ; level start y (kernel constant 24)
Hover = $9C                      ; respawn hover flag — cleared on stage entry
LevelShowTimer = $F2             ; LV001 banner countdown (kernel $F2)
BOMBS_MAX = 5                    ; kernel constant
LV_SHOW_FRAMES = 120             ; kernel constant (banner frames)
; --- room-exit handlers (MOVED here, C3 2026-10-20) — hand-copies, equ-sync --
PLAYER_MIN_X = 4                 ; kernel EQU (sprite flush with the left edge)
PLAYER_MAX_X = 159               ; kernel EQU (horizontal logical clamp)
PLAYER_MIN_Y = 0
PLAYER_MAX_Y = 132               ; kernel EQU (CAVE_LINES - PLAYER_SPRITE_H)

; C2 (2026-10-20): the level-data block labels (M<id>*, L<n>R<r>*) live in
; THIS bank now ($F307 slot include below), so the room tables resolve them
; natively — the generated/bank3_labels.asm EQU export is retired.
    include "generated/levels_equ.asm"   ; BAND_COLOR (0 bytes of ROM)

    ; --- 5-byte stub ---
    lda #0
    sta $1FF6                       ; select bank0
    jmp $F005                       ; GameStart in bank0

    ; --- #22 EnterRoomB2 ($F010) -----------------------------------------------
    ; Body of bank0's EnterRoom (tramp at $FBD0: sta $1FF8 / jmp $F010).
    ; Reached with A = room index; returns via jmp ReturnPad (X = EnemyCount).
    ; Level data lives in THIS bank → direct (FetchPtr),Y reads, NO folds
    ; (same transcription as MothRoutine below). Saves ~1660c per room change.
    ; Must end before MothRoutine ($F110 since the meta staging) — overflow
    ; = Origin Reverse.
    .ds $F010 - *, 0
EnterRoomB2:
    sta RoomNo
    tay                             ; Y = room (C2: every column is 1 B/room)
    lda LevelPFDataLo
    sta FetchPtr
    lda LevelPFDataHi
    sta FetchPtr+1
    lda (FetchPtr),Y                ; RoomShapes: idx b5-0 | band b6 | b7 extras
    sta Temp
    and #$3F                        ; shape index (C2 2026-10-20)
    asl                             ; *2: LEVEL_ShapeTable is a word table
    tax
    lda LEVEL_ShapeTable,X          ; block address = the table entry
    sta RoomRectsLo
    lda LEVEL_ShapeTable+1,X
    sta RoomRectsHi
    ; band flag b6 → RoomBandColor (staged BEFORE the block reader — the
    ; reader never writes it, and this is the only writer in the game).
    lda Temp
    and #$40
    beq .EBnoBand
    lda #BAND_COLOR
.EBnoBand:
    sta RoomBandColor
    ; TilePF0 is no longer stored per room: bank3's block reader derives it
    ; as rects + 2 + 2*nrect from the rect list it already copies (C3).

    ; --- A3 (2026-10-19): the rect stream, the PF block and the room meta
    ;     live in BANK3 (the level-data bank). One tail-jump into the block
    ;     reader; it returns to ERBlocksDone with the ptrs still in ZP.
    ;     0 pushes (the room-load chain sits at the measured SP floor).
    jmp ERBlocksPad
ERBlocksDone:

    ; --- enemies (C2 2026-10-20): count column = base + 2n, records = base
    ; + 3n (n = LevelRoomN). The count byte is count<<6 | extras index; the
    ; FIRST RECORD INDEX is DERIVED by summing the counts of rooms 0..room-1
    ; (records stay contiguous in room order), so the old packed index byte
    ; and its 31-record/level cap are gone. The band COLOR is the global
    ; BAND_COLOR (one water color per game).
    ; LevelConnSpare is free here: it only carries the exit-scan target, and
    ; that scan has already returned when EnterRoomB2 is entered.
    lda RoomNo
    tay                             ; Y = room (one byte per record)
    lda LevelPFDataLo
    clc
    adc LevelRoomN
    adc LevelRoomN                  ; base + 2n = RoomCounts
    sta FetchPtr
    lda LevelPFDataHi
    adc #0
    sta FetchPtr+1
    lda (FetchPtr),Y
    lsr
    lsr
    lsr
    lsr
    lsr
    lsr                             ; count = b7-6
    sta EnemyCount
    sty Temp                        ; room index (Temp free until EBLER)
    ldy #0
    lda #0
    sta LevelConnSpare              ; running first-record index
.EBSumLoop:
    cpy Temp
    beq .EBSumDone
    lda (FetchPtr),Y
    lsr
    lsr
    lsr
    lsr
    lsr
    lsr                             ; each earlier room's count (0..3)
    clc
    adc LevelConnSpare
    sta LevelConnSpare
    iny
    jmp .EBSumLoop
.EBSumDone:
    lda FetchPtr
    clc
    adc LevelRoomN                  ; base + 3n = enemy records (1 B/room)
    sta EnemyDataLo
    lda FetchPtr+1
    adc #0
    sta EnemyDataHi
    lda LevelConnSpare
    asl
    asl                             ; *4 (records are 4 B; index <= 63)
    clc
    adc EnemyDataLo
    sta EnemyDataLo
    lda EnemyDataHi
    adc #0
    sta EnemyDataHi
    lda #0                          ; (also the bomb reset seed below)
    sta EnemyDeadMask               ; no dead enemies in new room

    ; --- bomb reset: clear state/timer/sound (wall bits b3-6 die with it) ---
    sta BombPacked
    sta BombTimer
    sta BombSnd
    sta AUDV0

    ; (PF rebuild + room-meta staging moved to bank3 B3RoomBlocks — A3.)

    ; --- LoadEnemyRam: copy each ROM enemy's x,y,dir into the RAM shadow ---
    lda EnemyRamD
    and #$F0                        ; preserve RoomDarkMask bits 4-7
    sta EnemyRamD
    lda #$F0                        ; EnemyRamP clock seed (arbitrary phase)
    sta EnemyRamP
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    ldx #0
EBLER_Loop:
    cpx EnemyCount
    bcs EBLER_Done
    ldy EnemyOffTable,X             ; Y = X*4 type offset
    lda (FetchPtr),Y                ; +0 = type (kept for the snake invert)
    sta Temp                        ; Temp = record type (EnterRoom: free)
    iny                             ; +1 = x
    lda (FetchPtr),Y
    sta EnemyRamX,X
    iny                             ; +2 = y
    lda (FetchPtr),Y
    sta EnemyRamY,X
    iny                             ; +3 = dir ($FF = left)
    lda (FetchPtr),Y
    ldy Temp                        ; record type
    cpy #SNAKE
    bne EBLER_Dir
    eor #$FF                        ; SNAKE: the authored dir = where it will
                                    ; come OUT, so invert the live bit — the
                                    ; first move must be the retreat into its
                                    ; wall (user 2026-10-19). Nothing else
                                    ; reads the ROM dir: the patrol bounds are
                                    ; spawn ± SNAKE_PATROL.
EBLER_Dir:
    tay                             ; Y = dir, re-setting N from A (the cpy
                                    ; above clobbered the flags `bmi` needs;
                                    ; Y is reloaded at the loop top)
    bmi EBLER_Left
    lda EnemyBitTable,X             ; face right → set bit
    ora EnemyRamD
    sta EnemyRamD
    jmp EBLER_Next
EBLER_Left:
    lda EnemyBitTable,X             ; face left → clear bit
    eor #$FF
    and EnemyRamD
    sta EnemyRamD
EBLER_Next:
    inx
    jmp EBLER_Loop
EBLER_Done:
    jmp ReturnPad                   ; sta $1FF6 / rts — back to bank0 caller

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
    .ds $F110 - *, 0
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
    jmp MothExit             ; ÷2 gate: 1 px / 2 frames
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
    jmp MothGate               ; S6.5 col-change gate (body lives pre-$F9D9:
                               ; this region is pinned at $F25A)
MothDoWalk:
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
    lsr                        ; A = line >> 2
    jsr BandRowFromLine
    sta CollisionCellY         ; top band row = floor((Y+1)/48)
    lda EnemyRamY,X
    clc
    adc #8                     ; bottom line = Y+8
    lsr
    lsr
    jsr BandRowFromLine
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
    sta FetchPtr              ; Phase 4: raw vl px (overlay reuses it; walk
                              ; never touches FetchPtr, MothExit restages)
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

; --- Phase 4: patch-strip block (mirror-free, BEFORE the mirrored walk) ---
; The walk sees the strip as air (PF = mirror), so the candidate's RAW box
; (vl stashed in FetchPtr by the prologue) is tested against the strip px
; [BallX-7, BallX] (BallX = 87+8*rc, PHMOverlay envelope) x band mask on
; the moth's rows (OvHead/OvTail). Overlap -> turn; else mirrored walk runs
; unchanged (left-half walls still block). LineCount=0 → mask&bits=0 → skip.
    ldx CollisionCellY
    lda OvHead,X
    ldx CollisionEndY
    and OvTail,X
    and LineCount
    beq .MwSym                ; strip not painted in the moth's band rows
    lda LineCount
    lsr
    lsr
    lsr
    lsr                       ; n = right_col+1
    asl
    asl
    asl                       ; 8n
    clc
    adc #79                   ; BallX = 79+8n = 87+8*rc
    sta CollisionX            ; walk re-inits CollisionX at .MwRow — free
    lda FetchPtr              ; raw vl (prologue stash)
    cmp CollisionX            ; vl vs BallX
    beq .MovT2
    bcc .MovT2
    bcs .MwSym                ; vl > BallX → box fully right of strip
.MovT2:
    lda CollisionX
    sec
    sbc #14                   ; BallX-14
    cmp FetchPtr              ; vs vl
    bcc .MothTurn             ; (BallX-14) < vl → overlap
    beq .MothTurn
.MwSym:
; --- Cell walk (cell_collision_plan 4.1): test the PF buffers directly ---
; Same walk as PlayerHitsMap 2.1: the prologue already mirrors cols to
; the left half (and swaps min/max after mirror), so no in-loop mirror.
; The rect cache is gone from THIS walker — bomb holes read as air for
; free. RectCount = running row, CollisionX = running col (walk temps
; before — same ZP, no new allocation). HIT -> jmp .MothTurn (flip dir,
; hold position); miss falls into .MothNoHit (commit candidate). No jsr
; (bank2 moth never jsrs; stack depth = old walk exactly).
    lda CollisionCellY
    sta RectCount
.MwRow:
    lda CollisionEndX
    sta CollisionX
.MwCol:
    lda CollisionX
    tax
    ldy RectCount
    tya
    clc
    adc ColOff,X            ; PF0/PF1/PF2 group offset (0/3/6)
    tay
    lda PF0Buf,Y            ; $C3+row+off — the byte the kernel renders
    and ColMask,X           ; bit for this source col
    bne .MwHit              ; solid (Z=0)
    lda CollisionX
    cmp CollisionCellX      ; col == max?
    beq .MwRowDone
    inc CollisionX
    bne .MwCol              ; always (col never wraps to 0)
.MwRowDone:
    lda RectCount
    cmp CollisionEndY       ; row == bottom?
    beq .MothNoHit
    inc RectCount
    bne .MwRow              ; always (row never wraps to 0)
.MwHit:
    jmp .MothTurn           ; wall: flip dir, hold position (no commit)
.MothNoHit:
    ldx EnemyIndex            ; slot back (walk used X for the mask index)
    lda Temp
    sta EnemyRamX,X           ; clear -> commit candidate step
    jmp MothExit
.MothTurn:
    ldx EnemyIndex
    lda MothBitTable,X        ; flip dir bit, hold X (no commit)
    eor EnemyRamD
    sta EnemyRamD
MothExit:
    lda EnemyDataLo           ; restage record base (walk overwrote FetchPtr)
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    jmp MothExitPad

; Slot-indexed dir bits (bank2-local copy — bank0's EnemyBitTable reads as
; level-data bytes at these addresses in this bank)
MothBitTable:
    .byte $01, $02, $04

; MothMaskBit deleted (cell_collision_plan 3.1): its only reader was
; LWC's destroyed-rect scan, retired with the cell walk. The moth walk is
; cell-based now (plan 4.1); rect.w b7 + kernel BombMaskBit died with
; ApplyBombWalls (plan 5.2) — bank1 BombMaskBit stays for the bomb walk
; + hot parent-mask AND.

; Band row from a scanline — replaces the old 48-byte MothRowTable copy
; (index = line>>2, value = floor(line/48)). Same result, 24 B instead of
; 48 B, and four call sites share it instead of carrying the table.
; IN: A = scanline >> 2 (0..37; callers do the two lsr)  OUT: A = band row
BandRowFromLine:
    cmp #36
    bcs .BR3                ; 144..151 (also clamps >151)
    cmp #24
    bcs .BR2                ; 96..143
    cmp #12
    bcs .BR1                ; 48..95
    lda #0                  ; 0..47
    rts
.BR1:
    lda #1
    rts
.BR2:
    lda #2
    rts
.BR3:
    lda #3
    rts

; ------------------------------------------------------------------------------
; LaserWallClamp $F25A (name+pin kept — sim_frame_budget beam_cols keys on
; the entry; redesign 2026-10-08): CONTACT wall test — tests ONLY the
; missile TIP cell (one display col x band rows RoomY+2..3) instead of
; walking the whole swept path. The sweep/phase machine is gone: bank0
; LaserInput now travels LaserX +/-4px/frame from the eye, capped at the
; old sweep extent (RoomX+20 / max(RoomX-20,0)) and resets on contact, so
; there is no path to clamp and CollisionX is never modified (old S6
; mid-wall tip clamp retired with the sweep).
; In (bank0 LaserInput .LaserGo): CollisionX = LaserX, drawn M0 = [A-7,A],
; PlayerDir live, RoomY live, PF0Buf = the render map (bomb holes = air),
; patch-strip marker = LineCount x OvHead/OvTail (LWpSetup, $F600).
; M1 patch strip: tip px in [M1X-7, M1X] (M1X = (RoomPF0Lo)+14) = solid
; A=2 — the mirror walk alone passes the cell (patch = open, envelope) and
; the beam used to sail through the async block; kill-aware (b4 skip).
;   right: tip px = A        left: tip px = A-7 (A < 7 -> off-screen ->
;     clear -> enemy loop, no wall)
; Results: solid -> A=2 wall contact via ReturnPad (caller resets the beam
; to the eye); clear -> jmp LaserClampDone = enemy loop (0/$50/1).
; Entered/exited via jmp from/to LaserHitTestBody — stack depth unchanged
; (SP guard: gameplay >= $F8; laser chain = 2 jsr from overscan = $FB).
; Clobbers A/X/Y/RectCount/FetchPtr + CollisionEndX (marker scratch only).
; ------------------------------------------------------------------------------
    .ds $F25A - *, 0            ; pin LWC entry (sim_frame_budget beam_cols
                                 ; gate + session ledgers key on $F25A)
LaserWallClamp:
    lda RoomY                   ; beam rows RoomY+2..3 -> band rows
    clc
    adc #2
    lsr
    lsr
    jsr BandRowFromLine
    sta CollisionCellY          ; top band row
    lda RoomY
    clc
    adc #3
    lsr
    lsr
    jsr BandRowFromLine
    sta CollisionEndY           ; bottom band row
    ; --- tip col (display space): the ONLY cell the contact tests ---
    lda PlayerDir
    bne .LWtipL
    lda CollisionX              ; right: tip = A (caller keeps A <= 159)
    jmp .LWtipC
.LWtipL:
    lda CollisionX
    sec
    sbc #7                      ; left: tip = A-7
    bcs .LWtipC
    jmp LaserClampDone          ; tip off screen left -> clear (enemy loop)
.LWtipC:
    sta RectCount               ; tip px scratch (mirror walk re-inits it)
    lda RoomMetaA               ; MetaA
    lsr
    lsr
    lsr
    lsr                         ; m1_col+1 (0 = no M1 patch)
    beq .LWm1Skip
    lda EnemyDeadMask
    and #$10                    ; b4 = M1 strip destroyed -> transparent
    bne .LWm1Skip
    lda RoomMetaA               ; reload MetaA (dead test clobbered A)
    lsr
    lsr
    lsr
    lsr
    asl
    asl
    asl
    sec
    sbc #1                      ; M1X
    sec
    sbc RectCount                ; M1X - tip
    bcc .LWm1Skip               ; tip > M1X: past the strip's right edge
    cmp #8
    bcc .LWm1Solid               ; tip in [M1X-7, M1X] = drawn strip px
.LWm1Skip:
    lda RectCount
    lsr
    lsr                         ; px -> col
    sta FetchPtr                ; display col (strip test + mirror walk)
    jmp LWpSetup                ; patch-strip first (out-of-line $F600):
                                ; tails to LWpSolid / LWpNotPatch
.LWm1Solid:
    lda #2                      ; M1 patch strip solid at the tip (A=2)
    jmp ReturnPad                   ; ReturnPad -> bank0 (contact resets eye)
LWpNotPatch:                    ; strip miss: mirror-test the ONE tip col
    lda FetchPtr
    cmp #20
    bcc .LWsrc                  ; left-half display col = source col
    lda #39
    sec
    sbc FetchPtr                ; right-half: mirrored source col 39-d
.LWsrc:
    tax                        ; X = source col 0-19
    lda CollisionCellY
    sta RectCount
.LWrow:
    lda RectCount
    clc
    adc ColOff,X
    tay
    lda PF0Buf,Y
    and ColMask,X
    bne LWpSolid                ; solid -> wall contact (A=2)
    lda RectCount
    cmp CollisionEndY
    beq .LWclear                ; bottom row tested -> tip col is clear
    inc RectCount
    bne .LWrow                  ; always (RectCount <= 2, never wraps to 0)
.LWclear:
    jmp LaserClampDone          ; back to the body (stack depth unchanged)
LWpSolid:                       ; global: strip/row walk solid -> CONTACT
    lda #2                      ; result: wall tip — caller resets to eye
    jmp ReturnPad                   ; ReturnPad -> bank0 LaserInput (A/Z kept)

; S6.5 col-change gate for MothRoutine (see entry at .MothRangeOk): walk
; result depends only on the (col,row) box. Moth rows are band-constant
; (Y sine +-6 inside spawn band, MothYDerive) and RAW candidate-col ==
; committed-col implies equal vl-cols (vl = f(Temp) deterministic; a raw
; mismatch at coarse edges only OVER-walks, never under-walks). Same-col
; candidate = the side the moth already arrived from = clear -> commit.
; Saves the prologue (~140c) + 5-rect loop (~340c) on every moth-run frame
; that stays in its column: measured +478c spikes inside UpdateEnemies.
MothGate:
    lda EnemyRamX,X
    lsr
    lsr                     ; committed raw col
    sta CollisionX           ; scratch (range anchor already consumed)
    lda Temp
    lsr
    lsr                     ; candidate raw col
    cmp CollisionX
    bne .MothGateWalk       ; new column -> must probe
    lda Temp
    sta EnemyRamX,X          ; same box -> arrival state was clear -> commit
    jmp MothExit
.MothGateWalk:
    jmp MothDoWalk

; ------------------------------------------------------------------------------
; TallyEntry MOVED to bank1 (repack chunk 3, 2026-10-20): ZP/TIA only,
; and the tally frame is the bank1 HUD frame anyway. The hard `org $F313`
; pin died with it; the region is fill.
; ------------------------------------------------------------------------------
; ------------------------------------------------------------------------------
; BCFDarkRun / BuildColupF / PhaseBlink / HotOverlapBody moved to
; bank3 (A3 2026-10-19 — they walk the level-data record stream, which now
; lives there).
; ------------------------------------------------------------------------------
; M1OffTab MOVED to bank0 with PHMOverlay (repack chunk 4); bank3 keeps its
; own twin for B3StageBand.
; OvHead/OvTail STAY here: the overlay cluster moved to bank0 (which has its
; own copy), but bank2's MothDoWalk patch test and LWC's .LWpSetup still read
; these band-edge masks in-bank (cross-bank reads are impossible, so the 6 B
; genuinely duplicate).
OvHead:
    .byte 7,6,4                 ; rows 0..2 → mask bits >= row
OvTail:
    .byte 1,3,7                 ; rows 0..2 → mask bits <= row

; --- Level data (frozen addresses — pointer values must match bank0's
;     original layout, level_bank_plan P2.1: $F9D9-$FB1E = 326B) ---
; ($F3C4 pin DELETED 2026-10-20, audit round 2: it was PickPlayerFrame's body
;  entry pin, retired with the repack chunk-1 move. Nothing ever sat between
;  it and the $F450 ERBlocks pad, so the gap is plain fill.)
; ------------------------------------------------------------------------------
; PickPlayerFrame MOVED to bank0 ($F9F5 region, repack chunk 1 2026-10-20).
; With it went the $FDE1 tramp mirror and the $F8DD/$FDE7 art twins: the body
; now reads bank0's PlayerSpriteA/B and PlayerWalkA/B while bank0 is active,
; so bank2 needs neither the duplicate art nor the hand-copied EQUs.
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; StageBandTab MOVED to bank3 (chunk A2, 2026-10-19): B3StageBand at $F0A3.
; It reads only the room-entry staged meta (RoomMetaA/B), so it needs no
; bank2 read; bank2's cost is the 6-byte tail tramp in BCFDarkRun below.
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; TitleSequence — RETIRED 2026-10-19 (merged title screen). The space is
; fill; the old cross-bank entry was bank0 TitleSequenceFold (jsr → $F4C4,

; the jmp bytes are mirrored in this bank); tail exits jmp $FBF8 (ReturnPad)
; so the bank0 jsr returns. Runs once per frame from TitleIntro. No jsr
; inside (fold depth must not nest). Guard: DropTarget == $FD.
;   0 fly right→140  1 drop→48  2 face left  3 arm bomb (fuse 180)
;   4 walk→76 (screen center)  5 wait explosion  6 walk→20 (home)
;   7 pause 240 → reset to 0 (loop)
; Fuse/explosion countdown is OWNED here — TitleTailAudio skips BombTick on
; titles, so no walls/score/lives side effects can leak into title state.
; BombY is never set: the band bottom-aligns the bomb to RoomY==48's sprite
; window (armed only while grounded), so there is no reader for it.
; ------------------------------------------------------------------------------
; --- C1 (2026-10-20): bank3-evacuation slot map -----------------------------
; Windows reserved by the .ds pads below (measured empty at HEAD 36d3d06):
;   $F307-$F44F  329 B  level-data blocks (models_data + per-room blocks)
;   $F8B7-$F9D8  290 B  B3RoomBlocks + the HotOverlapBody cluster
;   $F9D9-$FBCF  503 B  PhaseBlink/BuildColupF/BCFDarkRun + hcrunch tables
;   $FCB8-$FD86  207 B  B3StageBand (+ M1OffTab)
;   $FF59-$FFE5  141 B  HOVFeatEntry
; Reserving them turns an overflow into a named pad instead of a ROM error.
; ------------------------------------------------------------------------------
    .ds $F307 - *, 0
    ; C2 (2026-10-20): the level-data blocks moved HERE from bank3
    ; (models_data + every per-room block; labels used by the room
    ; tables below and walked by B3RoomBlocks).
    include "generated/spill_bank3.asm"
    .ds $F450 - *, 0            ; EnterRoomB2 block-reader pad (A3)
ERBlocksPad:
    jmp B3RoomBlocks            ; C2: same bank now (was `sta $1FF9` + jmp
                                ;   $F3B0 with a bank3 tail at $F458). The
                                ;   body returns `jmp ERBlocksDone` itself, so
                                ;   the pad is one tail-jump and 0 pushes.
; ($F4C4 / $F5CF pins DELETED 2026-10-20, audit round 2: TitleSequence was
;  retired with the merged title, so there is no jmp operand and no lst row to
;  match. ColOff is read as `lda ColOff,X`, so the table floats: it now starts
;  right after the ERBlocks return tail, and the $F600 pin still holds
;  LWpSetup / LWpSolid / LWpNotPatch.)

ColOff:
    .byte 0,0,0,0, 3,3,3,3,3,3,3,3, 6,6,6,6,6,6,6,6
ColMask:
    .byte $10,$20,$40,$80, $80,$40,$20,$10,$08,$04,$02,$01
    .byte $01,$02,$04,$08, $10,$20,$40,$80

; (A1 2026-10-20: SelectActiveObject moved BACK to bank0 — the body, its
; SetObjectXPos/SetObjReflection copies and the type tables left this bank.
; This window is free again for the bank3 evacuation. The enemy records this
; bank still owns are read only by EnterRoomB2 / MothRoutine / LWC / LHT.)

    .ds $F600 - *, 0            ; Phase 4 LWC patch-strip setup+test (out-of-
                                 ; line: the pre-TallyEntry fill is ~0B)
LWpSetup:
    ; Marker = pL = 18+2*right_col (patch strip LEFT display col) when the
    ; strip is solid for SOME tested band row, else $FC (d-$FC >= 4 for all
    ; display cols — never matches the {0,1} strip test).
    ; Band-active = LineCount mask x OvHead[top] & OvTail[bottom] (same
    ; tables as PHMOverlay): an inactive band keeps the strip transparent.
    lda LineCount
    beq .LWpNone
    ldx CollisionCellY
    lda OvHead,X
    ldx CollisionEndY
    and OvTail,X
    and LineCount
    beq .LWpNone
    lda LineCount
    lsr
    lsr
    lsr
    lsr                         ; n = right_col+1
    asl                         ; 2n
    clc
    adc #18                     ; 18+2n = 20+2*(n-1) = pL
    jmp .LWpSet
.LWpNone:
    lda #$FC
.LWpSet:
    sta CollisionEndX           ; marker (c0 already consumed by LWC entry)
LWpTest:
    ; d - marker in {0,1} = display col pL or pL+1 → solid (the strip
    ; behaves like a real 2-col wall); borrow/none land >=2.
    lda FetchPtr
    sec
    sbc CollisionEndX
    cmp #2
    bcc .LWhit
    jmp LWpNotPatch             ; miss → mirror/row walk (LWC, same bank)
.LWhit:
    jmp LWpSolid                ; strip col → wall contact A=2 (LWC, same bank)

; OvM1Block MOVED to bank0 (repack chunk 4, 2026-10-20) with PHMOverlay
; and OvShutBand — it reads ZP + PF0Buf and bank0's ColOff/ColMask.

FooterPtr1 = $E0                 ; title-only pointer block; overwritten by HUD
FooterPtr2 = $E2
FooterPtr3 = $E4
FooterPtr4 = $E6
FooterPtr5 = $E8
FooterPtr6 = $EA

; ------------------------------------------------------------------------------
; TitleBandPrep — called by TitlePlayerBand at band entry (same-bank jsr).
; Sets Grp0Ptr frame (walk phases 4/6 alternate PlayerWalkA/B on EnemyRamP
; bit3, phases 2/3/5/7 static A, phases 0/1/8 jet flutter), REFP0 =
; PlayerDir<<3 (bit3 = mirror, kernel.asm:602), FooterPtr1 = bomb state (draw rows), COLUP1 = fuse color or
; COLUBK = explosion blink color (same (60-BombTimer)&3 table as the game's
; BombBlinkColors). Band tail restores COLUBK/REFP0 before the footer.
; Clobbers A/X/Y; rts (same-bank — NOT a fold; stack +2 during the call).
; ------------------------------------------------------------------------------
; ==============================================================================
; LoadLevelB2 — MOVED from bank0 (C2, 2026-10-20; was $F535-$F5B1 = 124 B).
; Entry: bank0 `jsr LoadLevel` ($FC20 `sta $1FF8`) -> the fetch at $FC23 is
; THIS bank's `jmp LoadLevelB2`. Tail: `jmp LF_TailSwap` ($FC26 = `sta $1FF6`
; here) -> bank0's `jmp LF_B0Tail`, which runs EnterRoom + the level-start
; placement + `jmp DropArm` in bank0. 0 extra jsr levels, 0 pushes: the stack
; depth of boot/RESET/title/tally (sim_bomb_fuse, test_tally) is unchanged.
; Why: the level index + tables ARE bank2 level data, so the 7 FoldIndirect
; reads (7 x 25c, 14 switches) are direct (FetchPtr),Y reads here.
; Entry layout (7 B stride): miner_room (b7 = faces right), miner_x, wall
; color, wall color 2, block base word (RoomShapes), room count n. The
; start room / start x / start y / miner y are kernel constants (0/32/24/84).
; ==============================================================================
    .ds $F640 - *, 0
LoadLevelB2:
    ; Stage leave/reload/advance: walls return + bombs refill to 5
    lda #0
    sta BombPacked              ; state + WallMask bits (D1-B: no $F2 mirror)
    sta BombTimer
    sta EnemyRamD               ; clear dir + RoomDarkMask (bits 4-7) — stay
    sta PlayerDir               ; face right on every stage entry (new stage,
                                ;  game-over restart = LoseLife->ReloadLevel->
                                ;  here; same-stage respawn keeps facing)
    sta Hover                   ; bugs.md #1: stage entry lands normally; the
                                ;   respawn hover is armed only by LoseLife
    lda LaserState
    and #%11000111              ; clear RoomDarkMask rooms 4-7 (LaserState b5-2)
    sta LaserState
    lda #BOMBS_MAX
    sta PlayerBombs
    lda DropTarget              ; #18: arm the LV001 banner unless this is the
    cmp #$FF                    ; title preview (HUD score shows level+1)
    beq .LLNoBanner
    lda #(LV_SHOW_FRAMES|$80)   ; bit7 = banner flag: decs down to $80; any
    sta LevelShowTimer          ; tally ARM (<=127) kills it instantly
.LLNoBanner:
    ; LevelDataTable is level data in THIS bank: pointer = LevelDataTable +
    ; Level*7 (no FetchPtr staging through a fold any more).
    lda Level
    asl                         ; *2
    asl                         ; *4
    asl                         ; *8
    sec
    sbc Level                   ; *7
    tay                         ; Y = Level * 7
    lda #<LevelDataTable
    sta FetchPtr
    lda #>LevelDataTable
    sta FetchPtr+1
    ldx #0                      ; callers' X contract (kept from the bank0 body)
    ; start room / start x/y are kernel constants now (0 / 32 / 24 px)
    lda #0
    sta LevelStartRoom
    lda #32
    sta LevelStartX
    lda #24
    sta LevelStartY
    ; +0: miner room (b7 = faces right)
    lda (FetchPtr),Y
    sta LevelMinerRoom
    iny
    ; +1: miner x (miner y is the constant 84 px = 7 rows)
    lda (FetchPtr),Y
    sta MinerX
    lda #84
    sta MinerY
    iny
    ; +2..+3: wall colors
    lda (FetchPtr),Y
    sta LevelWallColor
    iny
    lda (FetchPtr),Y
    sta LevelWallColor2
    iny
    ; +4..+5: block base (RoomShapes; RoomPositions / RoomCounts / enemy
    ; records are its +n/+2n/+3n offsets, see EnterRoomB2 + the exit
    ; handlers below — C2 2026-10-20: 3 B/room, no block word)
    lda (FetchPtr),Y
    sta LevelPFDataLo
    iny
    lda (FetchPtr),Y
    sta LevelPFDataHi
    iny
    ; +6: room count n → EnterRoomB2 / ExitScanB2 (both in this bank) derive
    ; the RoomPositions / RoomCounts / enemy-record bases from it
    lda (FetchPtr),Y
    sta LevelRoomN
    jmp LF_TailSwap             ; bank0: EnterRoom + placement + jmp DropArm

    .ds $F700 - *, 0
; --- Level-data spill 1 (bugs.md 27): fill gap $F767..$F800 (153B).
    ; levels_index first — it defines ROOM_NONE for the table includes.
    include "generated/spill_F767.asm"           ; #27b: index + level files, placed by convert_level


; ------------------------------------------------------------------------------
; C1 (2026-10-20) evac window: $F8B7-$F9D8 (290 B) — B3RoomBlocks and the
; HotOverlapBody cluster land here next chunk. Nothing else may claim it.
; (Retired tenants of this area: FooterFont sprite/color data ends $F854; the
; two empty #27b spill slots $F864/$F901 were folded into the window above,
; and the A2 StageBandTab ping-pong died with A3's same-bank move.)
; ------------------------------------------------------------------------------
    .ds $F854 - *, 0            ; FooterFont ends $F854 (13-row) — sprite/color data

; ------------------------------------------------------------------------------
; C2 (2026-10-20): $F8B7 window — the level-data block reader and the
; HotOverlapBody walk. Both walk the block stream that now lives in THIS bank
; ($F307 slot), so `lda (FetchPtr),Y` is a plain in-bank read — no tramp, no
; switch, no fold. Entered from ERBlocksPad / bank0's HotOverlapFlag pad
; ($FFEC -> bank2 $FFEF image) and exited through ReturnPad or ERBlocksDone.
; ------------------------------------------------------------------------------
    .ds $F8B7 - *, 0

B3RoomBlocks:
    ; --- copy solid rect list → ZP cache: ROM is packed 2B/rect
    ;     [x<<2|y, w<<2|h], cache keeps the uniform 4B walk form.
    ;     Copies 5 slots unconditionally (count = RcBase gates walkers).
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    lda (FetchPtr),Y                ; count (RAW — the cache below clamps to 5)
    ; C3 2026-10-20: TilePF0 = rects + 2 + 2*nrect (count byte + the always-0
    ; hot-count byte sit between the rect list and the PF triple in the block).
    ; The per-room word pair dropped this second pointer.
    asl                             ; 2*nrect
    clc
    adc RoomRectsLo
    sta RoomPF0Lo
    lda RoomRectsHi
    adc #0
    sta RoomPF0Hi
    lda RoomPF0Lo
    clc
    adc #2
    sta RoomPF0Lo
    bcc .EBpf0Ok
    inc RoomPF0Hi
.EBpf0Ok:
    lda (FetchPtr),Y                ; count again for the cache clamp
    cmp #6
    bcc .EBrcCntOk
    lda #5                          ; rect5+ not cached (ZP ends $DF) — clamp
.EBrcCntOk:
    sta RcBase
    iny                             ; Y = first packed byte
    ldx #0                          ; dest offset in rect0..4 ($CC+)
.EBrcW:
    lda (FetchPtr),Y
    lsr
    lsr                             ; x = p0 >> 2
    sta RcW1,X
    lda (FetchPtr),Y
    and #3                          ; y = p0 & 3
    sta RcW1+1,X
    iny
    lda (FetchPtr),Y
    lsr
    lsr                             ; w = p1 >> 2
    sta RcW1+2,X
    lda (FetchPtr),Y
    and #3                          ; h = p1 & 3
    sta RcW1+3,X
    iny
    inx
    inx
    inx
    inx
    cpx #20
    bne .EBrcW

    ; --- PF rebuild: one 9-byte read (PF0+PF1+PF2 rows are contiguous in
    ;     ROM and in RAM: PF0Buf $C3 + Y covers $C3-$CB = all 9 rows) ---
    lda RoomPF0Lo
    sta FetchPtr
    lda RoomPF0Hi
    sta FetchPtr+1
    ldy #0
.EBpf:
    lda (FetchPtr),Y
    sta PF0Buf,Y
    iny
    cpy #9
    bne .EBpf

    ; --- room meta staging: MetaA/MetaB → the pointer bytes ($99/$9A) ---
    ; Y = 9 on entry from the copy loop above (so no LDY here).
    lda (FetchPtr),Y                ; MetaA (Y = 9)
    sta RoomMetaA                   ; = RoomPF0Lo — pointer lo dies here
    iny
    lda (FetchPtr),Y                ; MetaB (Y = 10)
    sta RoomMetaB                   ; = RoomPF0Hi — pointer hi dies here
    jmp ERBlocksDone                ; C2: same-bank return (bank3's $F458 tail
                                    ;   and the `sta $1FF8` are gone)

HotOverlapBody:
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    lda (FetchPtr),Y            ; solid count (direct read — data in this bank)
    asl                          ; packed 2B/rect stream
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
    ; Parent gate: mask $00 = M1 block rect → dies with the STRIP
    ; (EnemyDeadMask b4), never with a wall (walk hits the floor cell
    ; under the block reach this body even after the strip is gone).
    ; Any other mask = wall piece → dies when that piece is blasted.
    lda (FetchPtr),Y            ; hot parent mask
    bmi .HOVfeature             ; b7 set = feature record ($80 phase /
                                 ;   $82 hcrunch; $81 is inert) — NOT a
                                 ;   legacy death rect (see .HOVfeature
                                 ;   after .HOVdone).
    bne HOVafterGate           ; nonzero = wall piece → PF gate at the hit
                               ;   (plan 5.1b: no WallMask bits any more)
    lda EnemyDeadMask
    and #$10                    ; b4: strip destroyed → M1 rect dead
    bne HOVnext                ; (HOVnext pops the loop's pushed Y)
    beq HOVafterGate           ; strip alive → continue (result was 0)
HOVafterGate:
    iny                         ; Y = base+1 (x)
    ; Column overlap (same tests as PlayerHitsMap)
    lda (FetchPtr),Y            ; rect.x
    cmp CollisionCellX
    beq .HOVcolOk
    bcc .HOVcolOk
    bne HOVnext                ; A > cellX → Z=0 (was jmp, -1B)
.HOVcolOk:
    sta CollisionX
    iny
    iny                         ; Y = base+3 (w)
    clc
    lda (FetchPtr),Y            ; rect.w
    adc CollisionX
    cmp CollisionEndX
    beq HOVnext
    bcc HOVnext
    ; Row overlap (base+3 → base+2 = y, same as PlayerHitsMap dey).
    dey                         ; Y = base+2 (y)
    lda (FetchPtr),Y            ; rect.y
    cmp CollisionEndY
    beq .HOVrowOk
    bcc .HOVrowOk
    bne HOVnext                ; A > endY → Z=0 (was jmp, -1B)
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
    beq HOVnext
    bcc HOVnext
    ; Hot hit
    dey
    dey                         ; Y = base+2 → base (record class)
    lda (FetchPtr),Y
    bmi .HOVphaseLatch         ; b7 set = feature record → phase latch
    ; Legacy hot rect (plan 5.1b): its parent wall must still be SOLID in
    ; the PF buffers. A thin parent is a bombable cell, so a blast punches
    ; it and the hot piece dies with the wall (the old WallMask AND). Mask
    ; $00 (M1 block cell, PF-open by envelope) is gated above → no read.
    ; The probe lives AFTER the $F9D9 window (HOVHotPfGate) so this pinned
    ; 290 B window does not grow.
    beq HOVlegHit
    jmp HOVHotPfGate
HOVlegHit:
    pla
    lda Temp
    ora #%10000000
    sta Temp
    sec                         ; tail-call contract: return C=1
    jmp ReturnPad                   ; ReturnPad → original caller (C survives)
.HOVphaseLatch:
    lda EnemyDeadMask
    ora #$40                    ; b6: phase dead — walls removed from now on
    sta EnemyDeadMask           ;   (PhaseBlink forces punch-OFF, kill gated)
    jmp HOVlegHit
HOVnext:
    pla
    clc
    adc #5
    tay
    dec RectCount
    bne .HOVloop
.HOVdone:
    sec                         ; tail-call contract: return C=1
    jmp ReturnPad                   ; ReturnPad → original caller (C survives)

; Feature-record dispatch ($80 phase / $82 hcrunch; $81 inert):
; armed/overlap/kill tests live in bank3 (HOVFeatEntry). $80 phase: b5 armed
; (staged by PhaseBlink each VBL) + candidate-box overlap → shared Hot hit
; (Temp b7 → bank0 `jsr LoseLife`); kill gated on armed-and-not-removed
; (`and #$60 / cmp #$20`), latches b6, PhaseBlink punch forced OFF while b6
; set (walls REMOVED, same-room only — EnterRoom zeroes the mask).
; $81 (retired vcrunch, tile 11 removed 2026-10-19) stays inert: skip.
; Entered with Y = record base + pushed Y (loop invariant), A = mask.
; 15B kept: the cmp/beq/jmp + pad replace the old tramp byte-for-byte —
; the BombEnemyBlastBody $FD87 pin (kernel tramp operand) must not move.
.HOVfeature:
    cmp #$81
    beq HOVnext             ; unknown legacy class → pass (pops the loop Y)
    ; LineCount is clobbered by the kernel .Row between this VBL staging and
    ; the overscan walk, so the hot byte (MetaB b6) is re-staged HERE, at the
    ; call, exactly like the old bank2 pre-read did.
    lda RoomMetaB
    sta LineCount
    lda (FetchPtr),Y        ; restore the class (Y = record base)
    jmp HOVFeatEntry        ; A3b: same-bank, fields read from FetchPtr
    .ds 8, 0                ; pad: 2+2+3+8 = 15B = old body size

; ------------------------------------------------------------------------------
; C2 (2026-10-20): $F9D9 window — the VBL crunch/stage walkers (PhaseBlink,
; BuildColupF, BCFDarkRun) and the hcrunch prefix clock. All of it reads the
; block stream in THIS bank now. Entry: bank0's CallPad_BuildColupF
; ($FC17 -> bank2 $FC1A image) and B3StageBand's `jsr PhaseBlink`; every exit
; goes through ReturnPad. The per-room TABLES that used to sit here moved into
; the spill_F767 window ($F700-$F853).
; ------------------------------------------------------------------------------
    .ds $F9D9 - *, 0

PhaseBlink:
    ; Door stripe color → CollisionCellY ($8D): $80 = no door (the kernel
    lda #$80
    ; band-setup line keeps the band color on COLUP1); $1C = yellow
    ; (hue1 luma6 — doors + key are yellow, user ruling 2026-10-12; the
    ; +10c door branch cost +2 cave frame lines — wall-model retargeted
    ; per-kernel, bugs.md #32 closed). The overscan PHM prologue restages
    ; $8D as its own top-row temp AFTER the kernel — no lifecycle overlap.
    ; (Staged here, not in StageBandTab: that window is pin-full.)
    lda #$80
    sta CollisionCellY
    lda RoomMetaA           ; MetaA
    and #$08                ; b3 = left door
    beq .PhNoDoor
    lda #$1C                ; yellow door stripe
    sta CollisionCellY
.PhNoDoor:
    ; --- blink phase → EnemyDeadMask b5 (armed = cell solid this frame) --
    ; mod-90 clock: 45 ON / 45 OFF (+76f tail per 256 wrap) = ~+40% over the
    ; old raw bit5 32/32 blink (user, 2026-10-13). Staged here every VBL so
    ; overscan HotOverlapBody can read the SAME frame's state: EnemyRamP is
    ; incremented at overscan entry (RefreshEnemyY), so a raw-clock read in
    ; HOV would be one frame ahead of the kernel's rendered blink.
    lda EnemyRamP
    cmp #90
    bcc .Phm1
    sbc #90
.Phm1:
    cmp #90
    bcc .Phm2
    sbc #90
.Phm2:
    cmp #45                    ; C=1 ⟺ phase ≥ 45 ⟺ blink OFF
    lda EnemyDeadMask          ; (LDA preserves C)
    bcs .PhfOff
    ora #$20
    bcc .PhfSt                 ; C=0 → always taken (skips the AND)
.PhfOff:
    and #$DF
.PhfSt:
    sta EnemyDeadMask
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    lda (FetchPtr),Y        ; solid count
    asl
    clc
    adc #1
    tay                     ; Y → hot count
    lda (FetchPtr),Y
    beq .PhDone             ; no hot records at all
    sta RectCount
PhRec:
    lda RectCount
    beq .PhDone
    dec RectCount
    iny                     ; Y → record class
    lda (FetchPtr),Y
    bpl .PhSkip             ; legacy hot rect — not a blink cell
    cmp #$80
    beq .PhPhase
    cmp #$82
    bne .PhSkip             ; unknown b7 class: skip 4
    ; hcrunch: enter the body DIRECTLY — the record fields are ignored
    ; (fixed band 1 + fixed 10-cell prefix), FetchPtr is not read here.
    jmp PhHcrEntry
.PhPhase:
    iny                     ; Y → 2c (even, 0-18)
    lda (FetchPtr),Y
    lsr                     ; pair index 0-9
    tax
    lda PhMaskTab,X         ; two adjacent PF bits for the cell pair
    sta CollisionCellX      ; mask (scratch — overscan restages $8C)
    eor #$FF
    sta CollisionEndY       ; ~mask (scratch — pack rebuild overwrites)
    ; buffer offset: pair<2 → PF0 (0), <6 → PF1 (3), else PF2 (6)
    lda #0
    cpx #2
    bcc .PhOffA
    lda #3
    cpx #6
    bcc .PhOffA
    lda #6
.PhOffA:
    sta LineCount           ; offset scratch
    iny                     ; Y → row (band 0-2)
    lda (FetchPtr),Y
    clc
    adc LineCount           ; A = buffer offset + row (0-8 → $C3+A)
    tax
    lda EnemyDeadMask           ; b5 flag staged above this frame
    and #$40                    ; b6: walls removed by crush kill
    bne .PhOff                  ; force open every VBL until EnterRoom clears
    lda EnemyDeadMask           ; b5 flag staged above this frame
    and #$20                ; armed ⟺ cell solid
    beq .PhOff
    lda PF0Buf,X
    ora CollisionCellX
    sta PF0Buf,X
    jmp PhNext
.PhOff:
    lda PF0Buf,X
    and CollisionEndY
    sta PF0Buf,X
    jmp PhNext
PhNext:                     ; Y = row (base+2): skip w/h → next class.
                            ; GLOBAL: bank3 crunch bodies tail-jmp here
                            ; via the $FCC1 pads (Y left at base+2).
    iny                     ; Y → w
    iny                     ; Y → h (record last byte)
    jmp PhRec
.PhSkip:                    ; non-phase record: skip its last 4 bytes
    iny
    iny
    iny
    iny                     ; Y → h (record last byte)
    jmp PhRec
.PhDone:
    rts

; ------------------------------------------------------------------------------


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
    asl                          ; packed 2B/rect stream
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
    lda (FetchPtr),Y            ; record class/mask
    bmi .BCFrectDone            ; b7 set = feature record ($80 phase /
                                 ;   $82 hcrunch; $81 is inert) — NOT a
                                 ;   hot band; its rows keep the stripe
                                 ;   color (the phase cell's own blink
                                 ;   lives in the PF bits, not the color)
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
    ; Moved to BCFDarkRun (pre-level-data gap): the $FCF0 pin left <8 B
    ; here once the dark mask grew to rooms 4-7. Still inlined in THIS
    ; bank — pads cannot nest (ReturnPad switches to bank0).
    jmp BCFDarkRun

; ------------------------------------------------------------------------------


BCFDarkRun:
    lda RoomNo
    cmp #4
    bcs .BCFhi
    tax
    lda BCFDarkMask,X           ; rooms 0-3: $10/$20/$40/$80
    and EnemyRamD
    beq .BCFdarkDone            ; lit → keep stripe/hot colors
    bne .BCFon                  ; dark (Z clear — beq just fell through)
.BCFhi:
    cmp #8
    bcs .BCFdarkDone            ; rooms 8+ never dark (no mask bit)
    tax
    lda BCFDarkMask,X           ; rooms 4-7: $10/$20/$40/$80
    lsr
    lsr                         ; → $04/$08/$10/$20 = LaserState b2-5
    and LaserState
    beq .BCFdarkDone            ; lit → keep stripe/hot colors
.BCFon:
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
    jmp B3StageBand            ; A3: local (PhaseBlink/pack live here now)
    sta $1FF9                   ; chunk A2: StageBandTab lives in bank3
BCFDarkMask:
    .byte $10, $20, $40, $80    ; rooms 0-3 → EnemyRamD bits 4-7
    .byte $10, $20, $40, $80    ; rooms 4-7 → lsr×2 = LaserState bits 2-5


PhMaskTab:
    .byte $30, $C0                     ; PF0 pairs (0,1) (2,3)
    .byte $C0, $30, $0C, $03           ; PF1 pairs (4,5) (6,7) (8,9) (10,11)
    .byte $03, $0C, $30, $C0           ; PF2 pairs (12,13) ... (18,19)

PhHcrEntry:
    tya
    pha                     ; [base] — PhRec needs Y = base+4
    lda #10
    tax                     ; full = 10 cells
    jsr HcrClock            ; A = n covered (1..10); X/Y preserved
    tay                     ; Y = n
    lda CrPfx0,Y
    sta PF0Buf+1
    lda CrPfx1,Y
    sta PF0Buf+4            ; PF1Buf band1
    lda CrPfx2,Y
    sta PF0Buf+7            ; PF2Buf band1
    pla
    clc
    adc #4
    tay
    jmp PhRec

; Prefix tables: P(n) for n pairs from pair 0 — n = 0..10.
; Pair → register: 0-1 PF0 ($30,$C0), 2-5 PF1 ($C0,$30,$0C,$03),
; 6-9 PF2 ($03,$0C,$30,$C0). PF0 maxes at n=2, PF1 at n=6, PF2 at n=10.
CrPfx0:
    .byte $00, $30, $F0, $F0, $F0, $F0, $F0, $F0, $F0, $F0, $F0
CrPfx1:
    .byte $00, $00, $00, $C0, $F0, $FC, $FF, $FF, $FF, $FF, $FF
CrPfx2:
    .byte $00, $00, $00, $00, $00, $00, $00, $03, $0F, $3F, $FF

; ==============================================================================
; PhVcApplyOR / PhVcApplyAND DELETED (2026-10-19) — same retired vcrunch
; tramp path. PhHcrEntry now stores the prefix mask directly (fixed 10).
; ==============================================================================
; ==============================================================================
; HcrClock — hcrunch animation clock (fixed full=10 since 2026-10-19).
;   In:  X = full extent (cells, ≥1); reads EnemyRamP (StartFrame-pinned)
;   Out: A = covered (1..full) — never 0 (always-solid stub)
;   Clobbers A (X/Y preserved — unlike CrunchClock). No latch: the kill
;   repeats on contact (DropArm respawns at the room top, so no loop).
; s = EnemyRamP>>4 (0..15, one 256f period = 16 buckets of 16f):
;   s 0-3   dwell at home  (eff 0)       -> n=1, 64f stub
;   s 4-12  grow to center  (eff s-3)    -> n 2..full (1..9 cells of
;          8px — full=w>>1; w=20 record = center of the screen)
;   s 13-15 fast retract    (eff 3*(15-s) = 6,3,0) — wipe home in 3
;          steps (the old instant far-end turn, stretched to center)
; covered = 1 + min(eff, full-1). CrunchClock (sc>>2 triangle, ~4f/step)
; stays for its VCR mirrors + verify_build token gate — only the two
; hcrunch call sites moved here (16f/step, grow-to-center ruling
; 2026-10-16). Both callers pass full=10 (PhHcrEntry stages it, HOV
; tests it); the latch freeze was removed with the 2026-10-19 contract.
; ==============================================================================
HcrClock:
    cpx #1
    bne .hcN
    lda #1              ; full=1: n always 1
    rts
.hcN:
    lda EnemyRamP
    lsr
    lsr
    lsr
    lsr                 ; s = P>>4
    cmp #4
    bcs .hcNd
    lda #0              ; s0-3 dwell: eff 0
    beq .hcOut          ; (always)
.hcNd:
    cmp #13
    bcs .hcNf
    sec
    sbc #3              ; s4-12: eff = s-3 (1..9) — grow to center
    bcs .hcOut          ; (always, no borrow)
.hcNf:
    eor #$0F            ; s13-15: t = 15-s (2,1,0) — fast retract
    sta CollisionX
    asl
    clc
    adc CollisionX      ; eff = 3t (6,3,0)
.hcOut:
    clc
    adc #1              ; candidate = eff+1
    sta CollisionX      ; scratch (HOV owns Temp; VBL path owns no consumer)
    txa                 ; full
    cmp CollisionX
    bcs .hcR
    rts                 ; full < candidate -> A = full already
.hcR:
    lda CollisionX
    rts


; ReturnPad ($FBF8) — bank2's live half is the `sta $1FF6` only: every body
; here tail-jmps `$FBF8`, the sta switches to bank0, and the `rts` at $FBFB is
; fetched from bank0 (so bank0's copy must keep `sta $1FF6 / rts`).
; ------------------------------------------------------------------------------
    .ds $FBD0 - *, 0            ; #22 EnterRoom tramp twin — byte-identical
                                 ;   with kernel.asm at $FBD0 (pin moved from
                                 ;   $FB84 2026-10-13, then $FBC0 2026-10-14:
                                 ;   model2 asym data +49B pushed the window —
                                 ;   growth past this pin fails the build)
    sta $1FF8
    jmp $F010                    ; EnterRoomB2 — this half fetched after bank0's sta
    .ds $FBD6 - *, 0            ; TitleSequenceFold twin (kernel.asm same
                                 ;   address — jmp operand fetched here after
                                 ;   bank0's sta $1FF8, so bytes must match)
; ------------------------------------------------------------------------------
; C3 (2026-10-20): room-exit pad halves. bank0's four `sta $1FF8` pads sit at
; $FBD9/$FBDC/$FBDF/$FBE2, so each post-switch fetch lands HERE at A+3:
;   $FBDC -> jmp ExitDownB2   $FBDF -> jmp ExitUpB2
;   $FBE2 -> jmp ExitLeftB2   $FBE5 -> jmp ExitRightB2
; $FBD9-$FBDB are dead (bank0's Down pad byte lives there).
; Guard: verify_build.check_callpads (CORRIDOR_PADS) resolves every operand
; from THIS listing; check_exit_handlers pins the bodies.
; ------------------------------------------------------------------------------
    .ds $FBD9 - *, 0
    .byte 0,0,0                 ; $FBD9-$FBDB — bank0 `sta $1FF8` is fetched there
    jmp ExitDownB2              ; $FBDC
    jmp ExitUpB2                ; $FBDF
    jmp ExitLeftB2              ; $FBE2
    jmp ExitRightB2             ; $FBE5
; ------------------------------------------------------------------------------
; CallPad_BuildColupF's bank2 image RETIRED 2026-10-20 (chunk 4): the corridor
; pads are split now, so bank0's `sta $1FF9` at $FC17 pairs with BANK3's `jmp`
; at $FC1A. Nothing in bank2 ever called this pad (verify_build.check_callpads
; rejects `jsr/jmp CallPad_*` outside kernel.asm), and after the split the
; twin here would be a broken image (its +3 lands on fill), so it is gone
; rather than left as a trap.
; ------------------------------------------------------------------------------
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF6                   ; the `rts` at $FBFB is served by bank0
    rts                         ; (dead byte here: kept, zero cost to change)

; ------------------------------------------------------------------------------
; C2 (2026-10-20): LoadLevel return halves (see LoadLevelB2 + kernel.asm $FC20).
;   $FC23 `jmp LoadLevelB2`  — fetched bank2-side after bank0's `sta $1FF8`
;                              at $FC20 (entry; bank0's $FC23-$FC25 are dead)
;   $FC26 `sta $1FF6`        — the body tail `jmp LF_TailSwap` lands here;
;                              the fetch at $FC29 comes from bank0, whose
;                              `jmp LF_B0Tail` is the live half
; Guard: verify_build.check_loadlevel_tramp asserts all 12 bytes + operands.
; ------------------------------------------------------------------------------
    .ds $FC1A - *, 0            ; C2: CallPad_BuildColupF entry image — bank0
    jmp BuildColupF             ;   runs `sta $1FF8` at $FC17, this fetch is
                                ;   bank2-side (was bank3's $FC1A)
    .ds $FC23 - *, 0
    jmp LoadLevelB2             ; $FC23
LF_TailSwap:
    sta $1FF6                   ; $FC26 — bank0 serves the `jmp LF_B0Tail`
    .byte 0,0,0                 ; $FC29-$FC2B dead (bank0's jmp fetched there)

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

; ==============================================================================
; Room-exit handlers — MOVED from bank0 (C3, 2026-10-20; were $F4DB-$F535 = 90 B).
; C1 (2026-10-20): LEVEL_FORMAT 2 — there is NO connection table any more. Each
; room owns ONE grid-position byte (x<<4|y, normalised to the level origin) at
; level base + n (C2 2026-10-20: the 3 B record is three columns, so the
; position column still starts one block-of-n in), and an exit is resolved by
; stepping that byte by a direction delta ($FF up / $01 down / $F0 left /
; $10 right) and SCANNING the level's position column for a match (<= 20
; iterations, cold path = room load only).
;
; Why no boundary guard is needed: a nibble of 15 never occurs in a stored
; position (POSITION_SPAN = 15 in convert_level.py, nibble 15 = sentinel), and
; stepping off the grid always wraps the moved nibble to 15 — so an exit past
; the grid edge can never match a room. The old nibble-room-index pack capped a
; level at 15 rooms; this lifts it to 225 grid cells (20 rooms/level with room
; to spare) at 1 B/room instead of 2.
;
; Entry: bank0's `jsr ExitRoomXxx` pad ($FBD9-$FBE4, `sta $1FF8`) -> the `jmp`
; halves at $FBDC-$FBE5 above. Every exit path ends in a `jmp`:
;   * no exit      -> ReturnPad (bank0 `rts` pops the caller's jsr frame)
;   * room changed -> `jmp EnterRoomB2`, whose own `jmp ReturnPad` does the same
; The opposite-edge placement is written BEFORE EnterRoomB2 because EnterRoom
; never reads/writes RoomX/RoomY (verified in EnterRoomB2 + B3RoomBlocks), and
; Y is used for the constant so A keeps the ROOM INDEX EnterRoomB2 stores.
; Guard: verify_build.check_exit_handlers.
; ==============================================================================
    .ds $FC4F - *, 0
; Scan the level's position column for the target byte.
; In: A = target position, FetchPtr = level base + n. Out: A = room index,
; C = 0 found / 1 none. Clobbers A/Y only (X is the caller's direction).
ExitScanB2:
    sta LevelConnSpare
    ldy #0
.EScanLoop:
    lda (FetchPtr),Y
    cmp LevelConnSpare
    beq .EScanHit
    iny
    cpy LevelRoomN
    bne .EScanLoop
    sec                         ; ran off the end: no room at that position
    rts
.EScanHit:
    tya                         ; room index
    clc
    rts

; Shared body: X = direction (0 up, 1 down, 2 left, 3 right).
; Stages FetchPtr = level base + n (RoomPositions, C2 2026-10-20: the room
; record is 3 B spread over three columns, so the position column still starts
; one block-of-n in), reads this room's own position, steps it by the
; direction delta and scans (no jsr for the staging: one push fewer than the
; old LevelConnB2 helper).
ExitUpB2:
    ldx #0
    jmp ExitDirB2
ExitDownB2:
    ldx #1
    jmp ExitDirB2
ExitLeftB2:
    ldx #2
    jmp ExitDirB2
ExitRightB2:
    ldx #3                      ; (falls through: last stub)
ExitDirB2:
    lda LevelPFDataLo
    clc
    adc LevelRoomN
    sta FetchPtr
    lda LevelPFDataHi
    adc #0
    sta FetchPtr+1
    ldy RoomNo
    lda (FetchPtr),Y            ; own position (x<<4|y)
    clc
    adc ExitDeltaTab,X          ; neighbour position (nibble 15 = off grid)
    jsr ExitScanB2
    bcs ExitNoneB2              ; nobody there: stay here
    cpx #2
    bcc .EDvertical
    ldy ExitEdgeTab,X           ; left/right: enter at the opposite X edge
    sty RoomX
    jmp EnterRoomB2
.EDvertical:
    ldy ExitEdgeTab,X           ; up/down: enter at the opposite Y edge
    sty RoomY
    jmp EnterRoomB2

ExitDeltaTab:
    .byte $FF, $01, $F0, $10    ; up, down, left, right
ExitEdgeTab:
    .byte PLAYER_MAX_Y, PLAYER_MIN_Y, PLAYER_MAX_X, PLAYER_MIN_X

ExitNoneB2:
    jmp ReturnPad               ; no exit: stay here, back to the bank0 caller

; ------------------------------------------------------------------------------
; BuildColupF + HotOverlapBody moved to bank3 (A3 2026-10-19 — they walk the
; level-data record stream, which now lives there). The space below is fill;
; BombEnemyBlastBody stays PINNED at its original address so the bank0/bank2
; blast-tramp literals ($FDD8 twins) need no resync.
; ------------------------------------------------------------------------------
    ; ------------------------------------------------------------------
    ; C2 (2026-10-20): B3StageBand + M1OffTab (was bank3 $FC38-$FCF2).
    ; Called from BCFDarkRun (`jmp B3StageBand`) and bank1's HUD fold; ends
    ; `jmp ReturnPad`. ZP/TIA only — no level-data read.
    ; ------------------------------------------------------------------
    .ds $FCB8 - *, 0
B3StageBand:
    ; --- expand band mask -> BandTab $ff/$00 ×3 (bit0 ENABL + bit7 pack) ---
    ; --- Phase 5: stage the M1 x-offset for the door SIDE. A door has no
    ; ball (its asym rows resolve to None → band mask $00), so MetaA bit0
    ; is free: 1 = M1 strip on the RIGHT half (x = 87+8*col → offset +79),
    ; 0 = left (x = 7+8*col → offset -1). The M1 block adds it via
    ; clc/adc RectCount. MetaA bit0 is ALSO the band-0 ball gate — the
    ; no-ball path below blanks BandTab so it never enables the ball.
    ; RectCount ($92) is free in the VBL (kernel re-inits RowIdx at entry;
    ; the pack uses $8F).
    lda RoomMetaA           ; MetaA
    and #$01
    tax
    lda M1OffTab,X
    sta RectCount
    lda RoomMetaA           ; MetaA
    lsr                     ; band0 bit -> carry
    lda #0
    rol
    beq .SBTb0z
    lda #$ff
.SBTb0z:
    sta BandTab
    lda RoomMetaA
    lsr
    lsr                     ; band1 bit -> carry
    lda #0
    rol
    beq .SBTb1z
    lda #$ff
.SBTb1z:
    sta BandTab+1
    lda RoomMetaA
    lsr
    lsr
    lsr                     ; band2 bit -> carry
    lda #0
    rol
    beq .SBTb2z
    lda #$ff
.SBTb2z:
    sta BandTab+2
    ; --- strip destroyed by a bomb? (EnemyDeadMask b3 — StripBlastCheck
    ; set it this overscan) → blank all band gates so the cave renders no
    ; strip; the pack below then emits mask 0 → every overlay stays
    ; transparent too. BandTab restages from ROM next room entry. ---
    lda EnemyDeadMask
    and #$08
    beq .SBTstripAlive
    lda #0
    sta BandTab
    sta BandTab+1
    sta BandTab+2
.SBTstripAlive:
    ; --- D6 M1 (left-col block): M1X = 8*(m1_col+1)-1 -> CollisionEndX ($8E) ---
    ; 0 = no M1 patch. Window: this VBL write -> PositionBallM1 reads it
    ; later the same VBL (staged-file pattern like Temp/BallX). Overscan
    ; routines (PHM/LWC/blast/laser) restage their own CollisionEndX values
    ; AFTER the cave read, so the alias never crosses a frame boundary.
    ; NOT zeroed with BandTab on strip kill — M1 is a whole-cave latch and
    ; convert guarantees its cell is solid/unpatched (wall) where it must hide.
    ; M1 strip DESTROYED (EnemyDeadMask b4, StripBlastCheck's M1 twin) →
    ; stage 0: PositionBallM1 skips ENAM1, the pack's b3 flag clears, and
    ; both overlay paths (PHM/blast) treat the strip as gone next frame.
    lda RoomMetaA
    lsr
    lsr
    lsr
    lsr                     ; m1_col+1 (0 = no M1 patch)
    beq .M1zero
    asl
    asl
    asl                     ; *8
    clc
    adc RectCount           ; staged offset: -1 (left, $FF) / +79 (right,$4f)
    jmp .M1got
.M1zero:
    lda #0
.M1got:
    sta CollisionEndX
    lda EnemyDeadMask
    and #$10                    ; b4 = M1 strip destroyed (room-scoped)
    beq .M1stage
    lda #0
    sta CollisionEndX
.M1stage:
    ; --- BallX staging: Temp ($88) ---
    ; 0 ⇔ symmetric (kernel ball block skips; verify_build enforces).
    ; CTRLPF: constant $35 (8-clk ball) — the P2 door 4clk eor ($B5) is
    ; GONE (user 2026-10-12: door must look like the plain async strip;
    ; only the key/bomb semantics differ). One write per VBL is the
    ; cave's value (the HUD's own $05/$35 dance runs after the cave).
    lda #$35
    sta CTRLPF
    lda RoomMetaB           ; MetaB = ball_col+1 (0 = none)
    and #$0F                ; ball_col+1 is b0-b3 only (max 10); drops b7
                            ; (retired door/vcrunch flag) AND b6 (hot) — b6 used to survive
                            ; and fake a 1-cell ball at x72-79 on a
                            ; hot-without-ball model
    beq .SBTnoBall
    asl
    asl
    asl                     ; *8
    clc
    adc #79                 ; 8*(ball_col+1)+79 = 87+8*ball_col — the
                            ; calibrated SetObjectXPos arg (S6b: arg A
                            ; draws clocks [A-7, A]; right_col c occupies
                            ; [80+8c, 87+8c]). PHMOverlay recomputes this
                            ; value independently (:1992) — the two MUST
                            ; agree or the stripe draws beside its own
                            ; collision cell (was #86 = +7px ≈ one cell
                            ; right; user-spotted 2026-10-12).
    sta Temp
    jmp .SBTballDone
.SBTnoBall:
    lda #0
    sta Temp
    ; --- No ball in this room → BE the ball gate off. ---------------------
    ; BandTab is the per-band ENABL gate for the cave (.Row). MetaA bit0 is
    ; the band-0 gate AND (for a door) the "M1 strip on the RIGHT half"
    ; flag — a door has no ball, so its bit0 must NOT enable one. Before
    ; this, the door room rendered a wall-coloured (COLUPF) ball bar over
    ; the band-0 opening: ENABL on, RESPBL never strobed (Temp=0) → the
    ; ball free-ran at x72-79 (user screenshot 2026-10-17, door_right.png).
    sta BandTab
    sta BandTab+1
    sta BandTab+2
.SBTballDone:
    ; --- NUSIZ1 owned here since P2b (kernel's VBL $30 restore deleted) ---
    ; Constant $30 (P1 single, M1 8 clk): the door distinction is COLOR
    ; (yellow $1C staged below), not width — the 4clk block read as "half
    ; a tile", the 2clk thin stripe as "only one strip" (user, 2026-10-12).
    lda #$30
    sta NUSIZ1
    ; Door stripe color ($8D) is staged inside PhaseBlink (this window
    ; was full to the $F4C4 pin, retired 2026-10-20 — the 14B staging
    ; block lives with the walk where there is hole).
    ; --- Phase 3: phase-cell blink (PF buffer pokes) ----------------------
    ; Body moved after the level data (PhaseBlink, ~130B — the StageBandTab
    ; window $F3C4..$F4C4 was full; the data window has the only free
    ; hole). Contract: clobbers A/X/Y/FetchPtr/RectCount/LineCount/
    ; CollisionCellX/CollisionEndY ($8F scratch — the pack below rebuilds
    ; it). The PF buffers ARE the collision map (cell walk + laser read
    ; them) — toggling the cell's two bits THERE makes render + PHM +
    ; laser follow with zero kernel cost. 64f full cycle = EnemyRamP bit5
    ; (32 on + 32 off; clock-derived, no state bytes — locked plan).
    ; --- PhaseBlink ping-pong (chunk A2): it MUST run after the band/ball
    ; staging above and before the pack below (the crunch walk overwrites
    ; Temp/BandTab for its cell — running it earlier let SBT's own staging
    ; erase the crunch mask, and every crunch kill stopped latching).
    ; Leg 1: this `sta` runs here, the fetch at $F803 is bank2's
    ; `jmp PhBlinkTail` (byte-image pinned in bank2.asm).
    ; --- A3: PhaseBlink is LOCAL now (the record stream lives in bank3) ---
    jsr PhaseBlink
SBT_B:
    ; --- Phase 4: pack collision overlay byte → CollisionEndY ($8F) ---
    ; b4-b7 = right_col+1, b0-2 = ball band mask, b3 = M1 present
    ; (staged $8E != 0), 0 = symmetric. Cave never
    ; writes $8F; bank1 HUD entry copies it to LineCount ($84 — cave .Row
    ; clobbers it) before overscan PHM reads. BallX in Temp stays raw (the
    ; kernel's ball block reads it later this VBL).
    ; b3 seeds BEFORE the Temp=0 early-out so an M1-ONLY room still packs
    ; nonzero (kernel OverlayTramp gates on LineCount != 0 — no M1 cross
    ; otherwise).
    lda CollisionEndX           ; staged M1X (kill-gated above)
    beq .M1nof                  ; 0 = no M1 → seed 0 (A is 0)
    lda #$08                    ; b3 = M1 present
.M1nof:
    sta CollisionEndY
    lda Temp
    beq .SBTPack                ; no ball → keep b3-only (or 0) pack
    sec
    sbc #79                     ; (BallX-79)>>3 = ball_col+1 (BallX =
    lsr                         ;   87+8*ball_col) → <<4 lands it in b4-b7
    lsr                         ;   with ONE sbc (was sbc #87 + adc #$10)
    lsr
    asl
    asl
    asl
    asl
    ora CollisionEndY           ; merge with the b3 seed
    sta CollisionEndY
    ; BandTab bytes are $ff/$00 → their bit7 IS the gate.
    lda #0
    bit BandTab
    bpl .SBTp0
    ora #$01
.SBTp0:
    bit BandTab+1
    bpl .SBTp1
    ora #$02
.SBTp1:
    bit BandTab+2
    bpl .SBTp2
    ora #$04
.SBTp2:
    ora CollisionEndY
    sta CollisionEndY
.SBTPack:
    jmp ReturnPad                   ; ReturnPad → bank0 VBLANK caller
M1OffTab:                           ; Phase 5: MetaA b0 → M1 x-offset (left/right)
    .byte $ff, $4f

    .ds $FD87 - *, 0
; BombEnemyBlast body — kill first live enemy |dcol| < 2 (any Y). Type check:
; LAMP (5) is NOT killable — the old inline loop set the dead bit on lamps too
; (lost lamp, no dark-room trigger, +50 score for nothing — bugs.md 3).
; Entered from bank0 stub (sta $1FF8 / jmp <here> — operand in kernel.asm,
; twin at $FDD8 below), 0 pushes; every exit `jmp $FBF8` ReturnPad.
; Out: A = 1 kill (caller awards +50 — pads cannot nest), 0 none (Z set).
; Clobbers A/X/Y. Level enemy records live in THIS bank, so the type read
; is a direct (EnemyDataLo),Y — no fold.
; Lives here (after .HOVdone) — NOT between TitleJetColors and the $F970
; pad: test_title_demo diffs that whole source span for $xx color literals.
; ------------------------------------------------------------------------------
BombEnemyBlastBody:
    lda EnemyCount
    beq .BEBnone
    lda BombX
    lsr
    lsr
    sta CollisionCellX          ; bomb screen col
    lda #0
    sta EnemyIndex
.BEBLoop:
    ldx EnemyIndex
    cpx EnemyCount
    bcs .BEBnone
    lda EnemyDeadMask
    and EnemyBitTable,X
    bne .BEBNext                ; already dead
    ldy EnemyOffTable,X         ; Y = X*4 = type offset (record: type,x,y,dir)
    lda (EnemyDataLo),Y
    cmp #LAMP
    beq .BEBNext                ; lamp: blast passes through (item 3 fix)
    cmp #RAFT
    beq .BEBNext                ; raft: a blast cannot destroy the platform the
                                ; player is riding across the water
    lda EnemyRamX,X             ; live X from RAM
    ; |dcol| < 2 (col = px/4) — ignore Y entirely
    lsr
    lsr
    sec
    sbc CollisionCellX
    bcs .BEBAbsCol
    eor #$ff
    clc
    adc #1
.BEBAbsCol:
    cmp #2
    bcs .BEBNext
    lda EnemyDeadMask
    ora EnemyBitTable,X
    sta EnemyDeadMask           ; kill (first overlapping enemy per blast)
    lda #1                      ; killed — bank0 caller awards +50
    jmp ReturnPad                   ; ReturnPad
.BEBNext:
    inc EnemyIndex
    jmp .BEBLoop
.BEBnone:
    lda #0                      ; Z set for caller's beq
    jmp ReturnPad                   ; ReturnPad

; ------------------------------------------------------------------------------
; HOF entry tramp ($FE80-$FE85) — byte-identical with kernel.asm's copy
; (guard: verify_build check_moth_tramp). bank0 executes `sta $1FF8` at
; $FE80-$FE82; the fetch at $FE83 comes from THIS bank = `jmp $FCF0`. Neither
; bank runs its other half: bank0 is switched away at $FE82, bank2 never
; enters at $FE80. Pinned $FE80: the $FBF8-$FC48 pad window is full (5 B
; left, a stub needs 6 B) and $FE86-$FEEF is the only free hole before the
; moth tramp's $FEF0.
; ------------------------------------------------------------------------------
; ------------------------------------------------------------------------------
; BombEnemyBlast tramp mirror ($FDD8-$FDDD) — byte-identical with kernel.asm's
; copy at the same address (bomb-lamp fix 2026-10-07). bank0 executes `sta
; $1FF8` at $FDD8-$FDDA; the fetch at $FDDB comes from THIS bank = `jmp $FD87`
; (BombEnemyBlastBody). Neither bank runs its other half: bank0 is switched
; away at $FDDA, bank2 never enters at $FDD8 (the .HOVdone tail-jmps $FBF8
; before this pad). $FDE1 no longer pins anything (PickPlayerFrame's tramp
; mirror retired 2026-10-20).
; ------------------------------------------------------------------------------
    .ds $FDD8 - *, 0
    .byte $8D, $F8, $1F         ; sta $1FF8 (twin)
    .byte $4C, $87, $FD         ; jmp $FD87 (twin — fetched post-switch)
; ($FDE1 pin DELETED 2026-10-20, audit round 2: PickPlayerFrame's tramp mirror
;  and the PlayerWalkA/B art twin moved to bank0 — nothing sits at $FDE1.)

    .ds $FE00 - *, 0            ; (was PHMOverlay's pin — the overlay
                                 ;   cluster moved to bank0 2026-10-20,
                                 ;   repack chunk 4)
; ------------------------------------------------------------------------------
; PHMOverlay / OvM1Block / OvShutBand / OvHead / OvTail / M1OffTab MOVED to
; bank0 (repack chunk 4, 2026-10-20): they read ZP + PF0Buf only, and bank0
; already owns ColOff/ColMask + the $FFEC HotOverlapFlag pad, so the per-miss
; bank switch disappears and the tables stop being duplicated.
; ------------------------------------------------------------------------------
    .ds $FE96 - *, 0            ; S5.4 LHT tramp — byte-identical w/ kernel.asm
                                ; (shifted +$10 with kernel's tables)
LaserHitTest:
    sta $1FF8                   ; dead in bank2 (entry arrives at $FE89)
    jmp LaserHitTestBody        ; == $FF00 — operand guard vs bank0 literal

; ------------------------------------------------------------------------------
; OvShutBand MOVED to bank0 (repack chunk 4, 2026-10-20) with PHMOverlay and
; OvM1Block. The $FE9C hole is fill again.
; ------------------------------------------------------------------------------

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
; kernel's `sta $1FF8 / jmp $F110` — operand drift fails the guard.
; ------------------------------------------------------------------------------
; HOVHotPfGate (plan 5.1b, 2026-10-20) — legacy hot rect parent test. The
; record's own PF cell must still be solid: a thin parent wall is a bombable
; cell, so a blast punches it and the hot piece dies with the wall (this is
; the PF form of the retired WallMask AND). Entered from HotOverlapBody's hit
; path with Y = record base (mask,x,y,w,h) after the box overlap passed.
; Exits: cell solid -> HOVlegHit (kill), cell empty -> HOVnext (pass/advance).
; Placed in the $FEA6-$FEEF hole (the $F8B7 window is pin-full).
HOVHotPfGate:
    iny
    lda (FetchPtr),Y            ; x (left-half display col 0..19)
    tax
    iny
    lda (FetchPtr),Y            ; y (band row 0..2)
    clc
    adc ColOff,X
    tay
    lda PF0Buf,Y
    and ColMask,X
    beq .HOVPFskip             ; parent wall blasted (cell punched) -> pass
    jmp HOVlegHit
.HOVPFskip:
    jmp HOVnext

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
; Contact-missile kill (redesign 2026-10-08): CollisionX = LaserX (cur M0
; arg, stored by LaserInput .LaserGo), drawn M0 = [A-7, A]. The body tests
; ONE tip cell for wall first, then the missile's OWN body box against each
; live enemy — no piercing: first contact wins and the caller resets the
; beam to the eye. Vertical: beam rows [RoomY+2, RoomY+3] vs enemy [Y,+7] ->
; (RoomY-Y)+3 in [0..8]. Horizontal (same convention as CheckEnemyHit):
; |eLo-lo| <= 7 via (d+7) in [0..14]; caller keeps arg in [0,159].
; Fold-free: enemy records are level data in THIS bank — stage once, direct
; `lda (FetchPtr),Y` for the type (was `jsr FoldIndirect`).
; RESULT PROTOCOL (pads cannot nest from a pad body — the kill/lamp/wall
; ACTIONS stay in bank0's LaserInput): every exit returns A + Z through
; ReturnPad (sta/rts preserve both): A=0 no contact (keep travelling) /
; #$50 kill (dead bit set here, caller scores + resets) / A=1 lamp (caller
; does CallPad_SetRoomDark + resets) / A=2 wall tip (caller resets, no
; score). First live enemy in span only (dead mask skips it next frame —
; no resurrection, no double score).
; Does NOT touch Temp (joystick still live at the call site).
; Wall first: the body tail-jmps to LaserWallClamp ($F25A) — tip cell
; (patch-strip + mirrored PF rows) — solid returns A=2 straight through
; ReturnPad (enemies behind the wall survive); clear ends
; `jmp LaserClampDone` (back here = enemy loop): stack depth unchanged.
; Clobbers A/X/Y/FetchPtr + CollisionCellY/CollisionEndY, RectCount,
; CollisionEndX (strip marker); MODIFIES NOTHING else (no clamp any more).
; ------------------------------------------------------------------------------
    .ds $FF00 - *, 0            ; pinned: bank0 tramp operand is literal $FF00
LaserHitTestBody:
    jmp LaserWallClamp          ; contact: tip-cell wall test FIRST (A=2 or
                                ; fall into the enemy loop via LaserClampDone)
LaserClampDone:
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
    adc #7                      ; kill == drawn overlap: beam [A-7,A] x
                                ; enemy [eX-7,eX] (SAME arg-box convention
                                ; CheckEnemyHit uses for RoomX vs eX) ->
                                ; eX in [A-7, A+7] <=> (eX-A)+7 in [0..14].
                                ; S6b's adc #14 was a 7px-LEFT shift: it
                                ; killed empty space left of the beam and
                                ; missed every enemy overlapping the tip
                                ; from the right (laser_collision_tip_bug).
    cmp #15                     ; bcs -> miss
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
    jmp ReturnPad                   ; ReturnPad → bank0 caller (A/Z/C preserved)
.LHLamp:
    lda #1                      ; result: lamp — caller crashes the lamp
    jmp ReturnPad
.LHNext:
    inx
    bne .LHLoop
.LHTOut:
    lda #0                      ; result: miss (Z set for caller's beq)
    jmp ReturnPad

; Type-offset table (copy of kernel EnemyOffTable: enemy index * 4; S4.1) and
; dead-bit table (copy of kernel EnemyBitTable) — bank0 ROM is not visible
; from here; labels keep the kernel-side test anchors working.
EnemyOffTable:
    .byte 0,4,8

EnemyBitTable:
    .byte $01, $02, $04, $08

    ; Tally entry tramp slice RETIRED here (repack chunk 3, 2026-10-20): the
; body moved to bank1, so the $FFE6 twin lives in bank1 now. This bank's
; $FFE6-$FFEB bytes are fill.
    ; ------------------------------------------------------------------
    ; C2 (2026-10-20): HOVFeatEntry (was bank3 $FA40) — the $80 phase / $82
    ; hcrunch dispatch for .HOVfeature; fields read from FetchPtr in-bank.
    ; ------------------------------------------------------------------
    .ds $FF59 - *, 0
HOVFeatEntry:
    ; .HOVfeature dispatch. IN: A = record class, Y = record base,
    ; FetchPtr = record stream (all same-bank since A3). No field pre-read and
    ; no stack: fields are read at (FetchPtr),base+1..4 as needed. Returns to
    ; HOVnext / HOVlegHit (both pop the .HOVloop base) or HOVafterGate ($80,
    ; which needs Y = base — the $80 path never touches Y).
    cmp #$80
    bne .HFnotPhase
    jmp .HFphase                ; (far trampoline; Y = base preserved)
.HFnotPhase:
    lda (FetchPtr),Y            ; class byte
    cmp #$82
    beq .HFh_begin
    jmp .HFmiss                 ; $81 and unknown classes are inert
.HFh_begin:

    ; ---------------- $82 hcrunch: fixed band 1 + fixed 10-cell prefix ---
    ; Record fields ignored (user decision 2026-10-19): the band is always
    ; band 1 and the prefix is always 10 cells. ALWAYS HOT: any overlap of
    ; the player box with the covered prefix kills, at any phase/extent
    ; (the clock animation only moves the covered prefix).
    lda CollisionCellY
    cmp #2                      ; top row below band1 → miss
    bcs .HFmissD
    lda CollisionEndY
    cmp #1                      ; bottom row above band1 → miss
    bcc .HFmissD
    ldx #10
    jsr HcrClock                ; A = n covered cells; X/Y preserved
    asl                         ; 2n = covered 4px cols from col 0
    cmp CollisionEndX           ; covered_w vs min col (strict >)
    bcc .HFmissJ
    beq .HFmissJ
    jmp .HFkill

.HFmissJ:
    jmp .HFmissD

.HFkill:
    jmp HOVlegHit               ; loop Y still on the stack (popped there)
.HFmissD:
.HFmiss:
    jmp HOVnext                 ; loop Y still on the stack (popped there)
.HFphase:
    lda EnemyDeadMask
    and #$60                    ; b5 armed | b6 phase dead
    cmp #$20                    ; armed AND not yet removed?
    bne .HFmiss
    jmp HOVafterGate            ; A3: local (Y = base still live)

    .ds $FFE6 - *, 0

; ------------------------------------------------------------------------------
; HotOverlapFlag (bank2-side) RETIRED 2026-10-20 (repack chunk 4): its only
; callers (OvM1Block/OvShutBand) moved to bank0, so the live pad is bank0's
; own $FFEC copy. No bank2 code tails there any more.
; ------------------------------------------------------------------------------
    .ds $FFEF - *, 0            ; C2: HotOverlapFlag entry image — bank0 runs
    jmp HotOverlapBody          ;   `sta $1FF8` at $FFEC, the jmp at +3 is
                                ;   fetched HERE (was bank3's $FFEF)
    .ds $FFF2 - *, 0            ; $FFF2-$FFF9 stay fill (F6 hotspot mirrors)

    ; Pad to vectors at $FFFA ($FFF2-$FFF9 = fill — never code: $FFF6-$FFF9
    ; are F6 hotspot mirrors on peek, see MothExitPad at $FC49)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
