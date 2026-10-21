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
SWCHA   = $0280                 ; joystick port (room-entry input refresh)
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
    sta RoomPF0Lo                   ; C7: staged for bank3's B3RoomBlocks (the
                                    ;   SHAPE ADDRESS TABLE lives in that bank,
                                    ;   so bank2 needs no bank3 label). Loader
                                    ;   scratch: overwritten with MetaA later.
    sta Temp
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
    ; base + 2n = RoomCounts. 2n is computed FIRST: adding n twice to the
    ; low byte loses the first carry (the second `adc n` consumes it) and the
    ; high byte then misses that carry — level 14 of a 20-level stage read its
    ; counts from base+2n-0x100 and saw EnemyCount=0 (2026-10-20).
    lda LevelRoomN
    asl                             ; 2n (n <= 20 rooms -> <= 40, fits a byte)
    clc
    adc LevelPFDataLo
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
    asl                             ; 2*first (records are 3 B, 2026-10-21)
    clc
    adc LevelConnSpare              ; 3*first; C = carry out (not dropped)
    adc EnemyDataLo                 ; + record base (C saved for the high byte)
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
    ldy EnemyOffTable,X             ; Y = X*3 record offset
    lda (FetchPtr),Y                ; +0 = type (b3-0) | dir (b7: 1 = left)
    sta Temp                        ; Temp = raw record byte (free: EnterRoom)
    iny                             ; +1 = x
    lda (FetchPtr),Y
    sta EnemyRamX,X
    iny                             ; +2 = y
    lda (FetchPtr),Y
    sta EnemyRamY,X
    lda Temp
    and #$0F                        ; record type
    cmp #SNAKE
    bne EBLER_Dir
    lda Temp
    eor #$80                        ; SNAKE: the authored dir = where it will
                                    ; come OUT, so invert the live bit — the
                                    ; first move must be the retreat into its
                                    ; wall (user 2026-10-19). Nothing else
                                    ; reads the ROM dir: the patrol bounds are
                                    ; spawn ± SNAKE_PATROL.
    sta Temp
EBLER_Dir:
    lda Temp                        ; b7 = 1 -> left (sets N)
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
    ; --- C7 (2026-10-20): the joystick-shadow refresh (Temp = SWCHA>>4)
    ;     moved to bank3's ERLoadDone: the shape/PF/meta walkers that run
    ;     AFTER this point use Temp as scratch, and Temp is the byte bank0's
    ;     input block keeps reading for the rest of the frame.
    ; --- C7 (2026-10-20): the PF / meta / extras half runs in BANK3 (the
    ;     shape blocks, the row pool and the async extras streams live
    ;     there). It is LAST on purpose: bank3's chain ends in its own
    ;     ReturnPad, so there is no cross-bank return pad and no extra push.
    ;     The counts column is bank2 data — stage the owns-extras room's
    ;     1-based ordinal here, before the switch.
    lda RoomPF0Lo
    bpl .EBnoExtras                 ; b7 clear = symmetric room, no record
    ; base + 2n = RoomCounts. 2n is computed FIRST: adding n twice to the
    ; low byte loses the first carry (the second `adc n` consumes it) and the
    ; high byte then misses that carry — level 14 of a 20-level stage read its
    ; counts from base+2n-0x100 and saw EnemyCount=0 (2026-10-20).
    lda LevelRoomN
    asl                             ; 2n (n <= 20 rooms -> <= 40, fits a byte)
    clc
    adc LevelPFDataLo
    sta FetchPtr
    lda LevelPFDataHi
    adc #0
    sta FetchPtr+1
    ldy RoomNo
    lda (FetchPtr),Y
    and #$3F                        ; extras ordinal (0 = none)
    sta LevelConnSpare              ; bank3 ExtrasLoad reads this
.EBnoExtras:
    jmp ERBlocksPad                 ; $F450 `sta $1FF9` → bank3 $F453

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
; --- C7 (2026-10-20): bank2 data slots (the shape half left for bank3) -----
; Every window below is an include-block terminated by its `.ds` pad, so a
; level-data overflow fails at a NAMED slot instead of DASM's cryptic
; `Origin Reverse-indexed`, and tools/verify_build.py --precheck prints the
; placement map before bank2 is even assembled.
;   $F307-$F44F  329 B   (was the shape-block slot — the shapes moved to bank3)
;   $F453-$F5FF  429 B   (was B3RoomBlocks/ExtrasLoad — moved to bank3 $F453)
;   $F700-$F853  340 B   (levels_index + room tables; the historical slot)
;   $F8B7-$F9D8  290 B   (was the HotOverlapBody cluster — moved to bank3)
;   $F9D9-$FBCF  503 B   (was PhaseBlink/BuildColupF/BCFDarkRun — bank3)
;   $FCB8-$FD86  207 B   (was B3StageBand — bank3)
;   $FF59-$FFE5  141 B   (was HOVFeatEntry — bank3)
; Only the level TABLES (room shape/position/count columns + the flat enemy
; records) live here; their walkers are EnterRoomB2 / the exits / LoadLevelB2 /
; moth / LWC / LHT / the bomb blast, all of which read them in-bank.
; ------------------------------------------------------------------------------
    .ds $F307 - *, 0
    include "generated/spill_F307.asm"
    .ds $F450 - *, 0            ; C7: the only cross-bank call in the room load
ERBlocksPad:
    sta $1FF9                   ; bank3 B3RoomBlocks MUST start at $F453 (the
                                ;   fetch at +3 comes from bank3) — guard:
                                ;   verify_build.check_bank3_entry
    .ds $F453 - *, 0            ; data slot START (never fetched in bank2)
    include "generated/spill_F453.asm"
    .ds $F600 - *, 0            ; Phase 4 LWC patch-strip setup+test (out-of-
                                ; line: the pre-TallyEntry fill is ~0B)
; ColOff/ColMask stay HERE (LWC .LWpSetup and the moth patrol read them; a
; cross-bank read is impossible) — 40 B in the $F854 fill.

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
; C5 (2026-10-20): ColOff/ColMask moved here from the $F453 loader window
; (which needed the 40 B for B3RoomBlocks + ExtrasLoad). Both are read as
; `lda/and Table,X` (absolute,X) so their address is free.
; ------------------------------------------------------------------------------
ColOff:
    .byte 0,0,0,0, 3,3,3,3,3,3,3,3, 6,6,6,6,6,6,6,6
ColMask:
    .byte $10,$20,$40,$80, $80,$40,$20,$10,$08,$04,$02,$01
    .byte $01,$02,$04,$08, $10,$20,$40,$80

; ------------------------------------------------------------------------------
; C7 (2026-10-20): the $F8B7 window — HotOverlapBody moved to bank3 (it walks
; the shape/extras stream, which lives there). Slot only.
; ------------------------------------------------------------------------------
    .ds $F8B7 - *, 0
    include "generated/spill_F8B7.asm"

; ------------------------------------------------------------------------------
; C7 (2026-10-20): the $F9D9 window — PhaseBlink/PhRec/BuildColupF/BCFDarkRun
; (with BCFDarkMask/PhMaskTab) and the hcrunch prefix clock moved to bank3:
; they walk the shape/extras stream. Slot only.
; ------------------------------------------------------------------------------
    .ds $F9D9 - *, 0
    include "generated/spill_F9D9.asm"

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
    .ds $FC1A - *, 0            ; C7: CallPad_BuildColupF's +3 image is BANK3's
                                ;   now (bank0 runs `sta $1FF9` at $FC17); the
                                ;   3 bytes here stay fill.
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
    ; C7 (2026-10-20): B3StageBand + M1OffTab moved to bank3 (it jsrs
    ; PhaseBlink). Slot only; BombEnemyBlastBody stays PINNED at $FD87.
    ; ------------------------------------------------------------------
    .ds $FCB8 - *, 0
    include "generated/spill_FCB8.asm"

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
    ldy EnemyOffTable,X         ; Y = X*3 = type offset (record: type|dir,x,y)
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
; LaserTipEnemy (2026-10-20) — enemy covering the beam's TIP PIXEL, tested
; BEFORE the wall clamp. The clamp only looks at the tip CELL, so an enemy
; drawn over a solid cell (the snake's whole design: it retreats into its
; wall) lost to the wall and a visible hit did nothing (user report). A
; sprite overlaps the tip pixel iff eX-7 <= tip <= eX, i.e. eX in
; [tip, tip+7] — an enemy BEHIND the wall cannot match, because the tip px
; sits inside the solid cell and the next sprite starts past it. Also covers
; the air-tip case harmlessly (same kill the body loop would award).
; IN: CollisionX = tip arg (LaserX, unchanged), PlayerDir = facing.
; OUT: A=0 no tip enemy -> LaserWallClamp (normal wall/enemy order);
;      A=$50 kill / A=1 lamp -> ReturnPad (caller resets the beam).
; Clobbers A/X/Y/FetchPtr + RectCount (the wall clamp re-inits it anyway);
; Temp is NOT touched (the joystick shadow stays live for the caller).
LaserTipEnemy:
    lda CollisionX
    ldx PlayerDir
    beq .LTEtip
    sec
    sbc #7                      ; left-facing tip = A-7 (drawn [A-7, A])
    bcc .LTEnone                ; tip off screen left: no enemy
.LTEtip:
    sta RectCount               ; tip px (wall clamp scratch; re-inited there)
    lda EnemyDataLo
    sta FetchPtr
    lda EnemyDataHi
    sta FetchPtr+1
    ldx #0
.LTEloop:
    cpx EnemyCount
    bcs .LTEnone
    lda EnemyDeadMask
    and EnemyBitTable,X
    bne .LTEnext
    lda RoomY
    sec
    sbc EnemyRamY,X
    clc
    adc #3                      ; same vertical window as the body scan
    cmp #9                      ; beam rows RoomY+2..3 vs enemy [Y, Y+7]
    bcs .LTEnext
    lda EnemyRamX,X
    sec
    sbc RectCount               ; eX - tip
    bcc .LTEnext                ; eX < tip: sprite ends left of the tip
    cmp #8                      ; eX in [tip, tip+7]: sprite covers the tip
    bcs .LTEnext
    ldy EnemyOffTable,X         ; type offset into the staged record
    lda (FetchPtr),Y            ; direct — enemy records are in THIS bank
    cmp #LAMP
    beq .LTElamp
    lda EnemyDeadMask
    ora EnemyBitTable,X
    sta EnemyDeadMask
    lda #$50                    ; kill — caller adds #$50 score
    jmp ReturnPad
.LTElamp:
    lda #1                      ; lamp — caller crashes it (dark room)
    jmp ReturnPad
.LTEnext:
    inx
    bne .LTEloop
.LTEnone:
    lda #0
    jmp LaserWallClamp

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
; C7 (2026-10-20): HOVHotPfGate moved to bank3 with the rest of the hot
; walk (it needs ColOff/ColMask and the PF buffers of that walk).
    .ds $FE9C - *, 0
    include "generated/spill_FE9C.asm"
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
; Order: LaserTipEnemy (2026-10-20) → LaserWallClamp ($F25A) → enemy loop.
; The tip-enemy pass only hits a sprite that COVERS the tip pixel (the snake
; lives inside its wall); then the wall tip cell (patch-strip + mirrored PF
; rows) — solid returns A=2 through ReturnPad (enemies behind the wall
; survive); clear ends `jmp LaserClampDone` (back here = enemy loop): stack
; depth unchanged.
; Clobbers A/X/Y/FetchPtr + CollisionCellY/CollisionEndY, RectCount,
; CollisionEndX (strip marker); MODIFIES NOTHING else (no clamp any more).
; ------------------------------------------------------------------------------
    .ds $FF00 - *, 0            ; pinned: bank0 tramp operand is literal $FF00
LaserHitTestBody:
    jmp LaserTipEnemy           ; tip-PIXEL enemy first (a sprite drawn over a
                                ; solid cell must win: snake), then the wall
                                ; clamp -> enemy loop via LaserClampDone
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

; Type-offset table (copy of kernel EnemyOffTable: enemy index * 3; 2026-10-21
; 3 B enemy records) and dead-bit table (copy of kernel EnemyBitTable) —
; bank0 ROM is not visible from here; labels keep the kernel-side anchors.
EnemyOffTable:
    .byte 0,3,6

EnemyBitTable:
    .byte $01, $02, $04, $08

    ; Tally entry tramp slice RETIRED here (repack chunk 3, 2026-10-20): the
; body moved to bank1, so the $FFE6 twin lives in bank1 now. This bank's
; $FFE6-$FFEB bytes are fill.
    ; ------------------------------------------------------------------
    ; ------------------------------------------------------------------------------
; C7 (2026-10-20): HOVFeatEntry moved to bank3 with the hot walk it serves.
; $FF59-$FFE5 is a data slot now; $FFE6-$FFF1 stay fill ($FFF6-$FFF9 are F6
; hotspot mirrors — never code, never data).
; ------------------------------------------------------------------------------
    .ds $FF59 - *, 0
    include "generated/spill_FF59.asm"
    .ds $FFE6 - *, 0

    .ds $FFF2 - *, 0            ; $FFF2-$FFF9 stay fill (F6 hotspot mirrors)

    ; Pad to vectors at $FFFA ($FFF2-$FFF9 = fill — never code: $FFF6-$FFF9
    ; are F6 hotspot mirrors on peek, see MothExitPad at $FC49)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
