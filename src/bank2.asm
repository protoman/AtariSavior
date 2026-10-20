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
LevelPFDataLo = $9F             ; RoomDataTable pointer low (kernel decl)
LevelPFDataHi = $A0             ; RoomDataTable pointer high (kernel decl)
LevelEnemyLo = $AF              ; RoomEnemies pointer low (kernel decl)
LevelEnemyHi = $B0              ; RoomEnemies pointer high (kernel decl)
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
LevelStartRoom = $A7             ; hand-copy kernel EQU — b7 = KeyHeld
                                 ;   (Phase 5); EnterRoom re-opens doors
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

; A3: level-data block labels (M<id>*, L<n>R<r>*) live in bank3 now — the
; room tables below need their absolute values as plain EQUs.
    include "generated/bank3_labels.asm"

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
    asl
    asl
    tay                             ; Y = room * 4
    lda LevelPFDataLo
    sta FetchPtr
    lda LevelPFDataHi
    sta FetchPtr+1
    lda (FetchPtr),Y                ; RoomDataTable: PF0 ptr lo
    sta RoomPF0Lo
    iny
    lda (FetchPtr),Y                ; PF0 ptr hi
    sta RoomPF0Hi
    iny
    lda (FetchPtr),Y                ; rects ptr lo
    sta RoomRectsLo
    iny
    lda (FetchPtr),Y                ; rects ptr hi
    sta RoomRectsHi

    ; --- A3 (2026-10-19): the rect stream, the PF block and the room meta
    ;     live in BANK3 (the level-data bank). One tail-jump into the block
    ;     reader; it returns to ERBlocksDone with the ptrs still in ZP.
    ;     0 pushes (the room-load chain sits at the measured SP floor).
    jmp ERBlocksPad
ERBlocksDone:

    ; --- enemy record for this room (4 bytes: ptr_lo, ptr_hi, count, band) ---
    lda RoomNo
    asl
    asl
    tay
    lda LevelEnemyLo
    sta FetchPtr
    lda LevelEnemyHi
    sta FetchPtr+1
    lda (FetchPtr),Y
    ldx #0                          ; EnemyDataLo/Hi/Count are contiguous
.EBrec:
    sta EnemyDataLo,X               ; $B1/$B2/$B3 (record bytes 0-2)
    iny
    inx
    lda (FetchPtr),Y
    cpx #3
    bne .EBrec
    sta RoomBandColor               ; SOURCE room's band on the transition frame
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
; TallyEntry — level-bonus tally body (user spec 2026-10-02). Entered from
; bank0's TallyTramp ($FFE6) via jsr; tail-jmps ReturnPad ($FBF8) so A (and
; Z) survive back to the bank0 caller.
;   DropTarget == 0 (pickup frame) -> ARM: snapshot the bonus into TallyTicks
;     in 50-pt units — 20 = miner (1000), (BarLevel+3)/6 = remaining time
;     (50% -> 10 ticks -> 500), 1/bomb, 2/life — then arm the 4-frame pace
;     divider (TickCounter), clear jet/beam, set DropTarget = $FE.
;   DropTarget == $FE (every frame) -> STEP: dec TickCounter; on 0 reload 4,
;     dec TallyTicks. Event A: b0 = add 50, b1 = coin tone written here
;     (AUDC/F/V + BombSnd=8; bank0 TallyWork's UpdateBombSound holds it,
;     coin = every 4 ticks = 200 pts), b2 = done (last tick consumed).
; Pinned $F313 (org $F9D9 below: level data pins the overflow = build fails).
; Was $F310 → $F313 (Phase 4 walk-head; kernel TallyEntry EQU moves with
; it — both jmp operands are symbolic). The LWC M1 tip test (2026-10-08)
; funds itself by moving ColOff/ColMask past this pin (see their comment).
; ------------------------------------------------------------------------------
    .ds $F313 - *, 0
TallyEntry:
    lda DropTarget
    beq .TEArm
    dec TickCounter             ; pace: 1 tick per 4 frames
    bne .TEIdle
    lda #4
    sta TickCounter
    dec TallyTicks
    beq .TEFinal                ; last unit: event = tick+coin+done
    lda TallyTicks
    and #3
    bne .TEOne                  ; tick only
    lda #8                      ; --- coin blip (200 pts = every 4th tick)
    sta BombSnd
    lda #4
    sta AUDC0                   ; square
    lda #24
    sta AUDF0                   ; high pitch — distinct from bomb drop ($0A)
    lda #8
    sta AUDV0
    lda #3                      ; tick + coin
    jmp ReturnPad
.TEOne:
    lda #1                      ; tick only
    jmp ReturnPad
.TEFinal:
    lda #7                      ; tick + coin + done
    jmp ReturnPad
.TEIdle:
    lda #0                      ; no event (Z set for bank0 beq)
    jmp ReturnPad
.TEArm:
    lda BarLevel
    clc
    adc #3                      ; round-to-nearest: (BarLevel+3)/6
    ldx #0
.TEDiv:
    cmp #6
    bcc .TEDivSum
    sec
    sbc #6
    inx                         ; X = time ticks (0..20; BarLevel <= 120)
    bne .TEDiv
.TEDivSum:
    jsr TallySum                ; TallyTicks = ticks + 20 + bombs + 2*lives
                                ; (masking the raft's ramp bits out of
                                ; PlayerBombs needs room this region lacks)
    lda #4
    sta TickCounter             ; fresh pace divider
    lda #0
    sta JetPower                ; frozen frame: no thrust flutter
    sta LaserX                  ; drop any live beam (travel restarts on press)
    lda #$FE
    sta DropTarget
    lda #0
    jmp ReturnPad

; ------------------------------------------------------------------------------
; BCFDarkRun / BuildColupF / PhaseBlink / HotOverlapBody moved to
; bank3 (A3 2026-10-19 — they walk the level-data record stream, which now
; lives there).
; ------------------------------------------------------------------------------
M1OffTab:                       ; MetaA b0 -> M1 x-offset. PHMOverlay's own
    .byte $ff, $4f              ;   copy (2 B); B3StageBand has the twin.

; --- Level data (frozen addresses — pointer values must match bank0's
;     original layout, level_bank_plan P2.1: $F9D9-$FB1E = 326B) ---
    .ds $F3C4 - *, 0            ; (was PickPlayerFrame's body entry pin — body
                                ;   moved to bank0 2026-10-20, repack chunk 1)
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
    .ds $F450 - *, 0            ; EnterRoomB2 block-reader pad (A3)
ERBlocksPad:
    sta $1FF9                   ; select bank3 (level-data bank)
    jmp $F3B0                   ; B3RoomBlocks — operand FETCHED bank3-side
    .ds $F458 - *, 0
    sta $1FF8                   ; bank3 half of the return tail (never fetched
                                ;   bank2-side — B3RoomBlocks ends here)
    jmp ERBlocksDone            ; fetched bank2-side at $F45B after the switch
    .ds $F4C4 - *, 0            ; pinned: bank0/bank2 TitleSequenceFold jmp
                                 ; operand ($F4C4 since P2b StageBandTab grew;
                                 ; verify_build asserts the operand is a
                                 ; TitleSequence lst row start)
    .ds $F5CF - *, 0            ; TitleSequence retired — merged title
                                 ;   screen (2026-10-19)

ColOff:
    .byte 0,0,0,0, 3,3,3,3,3,3,3,3, 6,6,6,6,6,6,6,6
ColMask:
    .byte $10,$20,$40,$80, $80,$40,$20,$10,$08,$04,$02,$01
    .byte $01,$02,$04,$08, $10,$20,$40,$80

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

OvM1Block:
    ; Phase 4 M1 (left strip) collision overlay. Entered by JMP from
    ; PHMOverlay's .OvClear (right-strip miss) — 0 pushes; both exits
    ; ReturnPad ($FBF8). In: CollisionX = vl, CollisionCellY/EndY =
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
    lda RoomMetaA               ; MetaA
    and #$01                    ; Phase 5: b0 = M1 strip on the RIGHT half
    tax                         ;   (door band mask is $02 → b0 free)
    lda RoomMetaA               ; reload MetaA
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
                                ;   match the bank2 StageBandTab staging.
    sta RectCount               ; scratch M1X (EndX = prologue min col is
                                ; CollisionEndX — kept intact for HotOverlapFlag)
    lda CollisionX              ; vl
    cmp RectCount                ; vl vs M1X (same shape as the ball test)
    bcc .OvM1T2
    beq .OvM1T2
    bcs .OvM1no                 ; vl > M1X → player fully left of strip
.OvM1T2:
    lda RectCount
    cmp #13
    bcc .OvM1Band               ; M1X < 13 (ℓ = 0): M1X-13 wraps — skip
    sec                         ; the second test (test 1 already implies
    sbc #13                     ; overlap for every valid vl)
    cmp CollisionX
    bcc .OvM1Band
    beq .OvM1Band
    bcs .OvM1no                 ; M1X-13 > vl → player fully right
.OvM1Band:
    lda RectCount
    sec
    sbc #7
    lsr
    lsr
    lsr                         ; ℓ = (M1X-7)/8
    tax                         ; X = ℓ (PHM callers preserve X themselves)
    lda CollisionCellY
    sta RectCount               ; $92 walk temp — free after the cell walk
                                ; (RowIdx re-inits at kernel entry)
.OvM1Row:
    lda RectCount
    tay
    tya
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
    jmp HotOverlapFlag          ; C=1 contract; body sets Temp b7 on hot hit
.OvM1unlock:
    lda EnemyDeadMask
    ora #$10                    ; b4 = M1 strip (left door) destroyed
    sta EnemyDeadMask
    clc
    jmp ReturnPad               ; passable
.OvM1no:
    clc
    jmp ReturnPad

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
    .ds $F700 - *, 0
; --- Level-data spill 1 (bugs.md 27): fill gap $F767..$F800 (153B).
    ; levels_index first — it defines ROOM_NONE for the table includes.
    include "generated/spill_F767.asm"           ; #27b: index + level files, placed by convert_level
    .ds $F800 - *, 0

; ------------------------------------------------------------------------------
; StageBandTab ping-pong (chunk A2, 2026-10-19). bank3 B3StageBand stages the
; band/ball state, then `jmp $F800` (its `sta $1FF8` runs there); the fetch at
; $F803 is THIS bank's `jmp PhBlinkTail`. PhaseBlink stays here (it walks the
; rect stream), then the tail switches back so bank3 can run the overlay pack.
; Zero pushes both ways — the bank0 VBL jsr frame is never touched.
; ------------------------------------------------------------------------------
    .ds $F854 - *, 0            ; FooterFont ends $F854 (13-row) — sprite/color data
    .ds $F864 - *, 0            ; #27b level spill slot ($F864, 28B; empty until
    include "generated/spill_F840.asm" ;  convert_level places a level here)
    .ds $F880 - *, 0
; TallySum — the level-bonus total for TallyEntry (frozen-scene frame).
; Split OUT of the inline TallyEntry region (it ends at a hard org) into bank2's
; free slack before the $F970 pin. IN: X = time ticks (0..20). OUT: TallyTicks
; set; A clobbered, X/Y kept. The bomb count MUST be masked: PlayerBombs' high
; bits carry the raft's take-off ramp state (b7 flag, b6-3 level — see the
; kernel EQU contract), and a stale ride would otherwise inflate the bonus.
; Temp ($88) is free here: the tally frame bypasses the input (its joystick
; store) and the next VBL restages Temp anyway.
TallySum:
    lda PlayerBombs
    and #%00000111              ; bombs only, never the ramp bits
    sta Temp
    txa
    clc
    adc #20                     ; miner reach = 1000 pts
    adc Temp                    ; + 50 per unspent bomb (chain carry ok)
    sta TallyTicks
    lda PlayerLives
    asl                         ; + 100 per life = 2 ticks
    clc
    adc TallyTicks
    sta TallyTicks
    rts

    .ds $F8B7 - *, 0            ; spill-pool gap
                                ; (was the $F8DD jet-art twin pin — deleted
                                ;   2026-10-20 with the PickPlayerFrame move;
                                ;   the spill include's own .ds absorbs the gap)
; --- Level-data spill 2 (bugs.md 27/27b): fill gap $F901..$F970 (111B) ---
    include "generated/spill_F901.asm"        ; #27b: placed by convert_level
    ; Phase 3 blink masks — pair index (2c>>1) → the two adjacent PF bits
    ; for that left-half cell (PF0: bits4-7 left-to-right; PF1: bits7-0;
    ; PF2: bits0-7 reversed). Pairs never straddle a register (even 2c).
    .ds $F970 - *, 0            ; pinned: bank1 .BMWDone jmp operand ($F970)
M1StripBlast:
    ; Phase 4 M1 strip blast — entered from bank1 BombMarkWalls .BMWDone
    ; via the $F9AC shared pad (`sta $1FF8 / jmp $F970`; 0 pushes). Bank2-
    ; only job (P2b stager): the packed meta (TilePF0+9/+10) lives in THIS
    ; bank's ROM — read the door flags + left-strip dcol, stage them, let
    ; bank1 StripBlastCheck run BOTH overlap takes (the blast window is
    ; left-half cols 0..19 and stays READ-ONLY here).
    ; Staging contract (both scratch bytes free in this flow):
    ;   RectCount := 2ℓ left-strip dcol, or $FF = none/door/right-bomb;
    ;   Temp ($88 = bank1 BMWScratch) := $FF when MetaB b7 (right door)
    ;   so the ball-strip take can never fire. Key pickup (P5) sets b3/b4
    ;   for doors instead (comment hook at the takes).
    lda RectCount               ; original screen col (BMW prologue stash)
    cmp #20
    bcs .M1SBnone               ; right bomb → left strip unreachable
    lda EnemyDeadMask
    and #$10                    ; b4 already set → nothing to stage
    bne .M1SBnone
    lda RoomMetaA               ; MetaA
    and #$08                    ; b3 = left door (key-only, bomb-immune)
    bne .M1SBnone               ; stays $FF: bank1 takes no left strip
    lda RoomMetaA               ; reload (and clobbered A)
    lsr
    lsr
    lsr
    lsr                         ; m1_col+1 (0 = no M1 → 2ℓ = $FE, off the
                                ;   high end — bank1's hi test rejects)
    sec
    sbc #1                      ; ℓ = left_col
    asl                         ; 2ℓ = strip left dcol
    sta RectCount               ; staged (nothing after this reads the col)
    jmp .M1SBdoorR
.M1SBnone:
    lda #$FF
    sta RectCount               ; no left strip this frame
.M1SBdoorR:
    lda RoomMetaB               ; MetaB, b7 = right door
    bpl .M1SBout
    ldy #$FF
    sty Temp                    ; = bank1's BMWScratch ($88) — "no strip"
.M1SBout:
    jmp M1ToBank1               ; shared pad $F9B2 (sta $1FF7 / jmp $F937,
                                 ; byte-identical in bank1) → StripBlastCheck

    .ds $F9AC - *, 0            ; shared cross-bank pad — byte-IDENTICAL twin
                                 ; of bank1's $F9A4 block (identity asserted
                                 ; in test_bomb_strip). After either `sta $1FFx`
                                 ; the next opcode fetch comes from the newly
                                 ; selected bank at pc+3, so the `jmp` bytes
                                 ; must match in both banks (F6 pad rule).
M1ToBank2:                      ; reached bank1-side after `sta $1FF8`
    sta $1FF8                   ; switch bank1 → bank2
    jmp $F970                   ; M1StripBlast
M1ToBank1:                      ; = $F9B2 — M1StripBlast jmps here bank2-side
    sta $1FF7                   ; switch bank2 → bank1
    jmp $F937                   ; StripBlastCheck

    .ds $F9B8 - *, 0            ; Phase 4 overlay tramp twin (kernel.asm's
                                 ; copy sits at the same address — bank0
                                 ; executes +0..+6, the bank2 fetch starts
                                 ; at the jmp; the clc/rts tail is bank0-only)
OverlayTramp:
    lda LineCount                ; dead in bank2 (entry arrives at +7)
    beq .OTsym
    sta $1FF8
    jmp PHMOverlay
.OTsym:
    clc
    rts

    ; --- Level data, main window $F9D9..$FBD6 (509B; pads pin the end).
    ; A3 (2026-10-19): models_data + per-room blocks moved to bank3; only the
    ; per-room TABLES stay here (RoomDataTable/connections/enemy tables) —
    ; their M<id>/L<n>R<r> word pairs resolve through generated/bank3_labels.asm.
    org $F9D9
    include "generated/spill_window.asm"       ; #27b: level tables, placed by convert_level

; ReturnPad ($FBF8) — byte-identical to kernel.asm's copy (sta $1FF6 / rts).
; S5.1 pad bodies (BuildColupF) tail-jmp here: sta switches this bank to
; bank0, the rts is then fetched from bank0's identical copy, and the stack
; still holds the bank0 jsr CallPad_* return address.
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
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF6
    rts

; ------------------------------------------------------------------------------
; CallPad_BuildColupF twin — bank3 body now (A3). bank0/bank1 execute
; `sta $1FF9`; the `jmp` at +3 is fetched from BANK3 (its $FC3B image).
; ------------------------------------------------------------------------------
    .ds $FC32 - *, 0
CallPad_BuildColupF:
    sta $1FF9                   ; bank3 (level-data walker)
    jmp $F507                   ; BuildColupF (bank3; synced by verify_build)

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
; BuildColupF + HotOverlapBody moved to bank3 (A3 2026-10-19 — they walk the
; level-data record stream, which now lives there). The space below is fill;
; BombEnemyBlastBody stays PINNED at its original address so the bank0/bank2
; blast-tramp literals ($FDD8 twins) need no resync.
; ------------------------------------------------------------------------------
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
; before this pad). Pinned $FDE1 below = PickPlayerFrame tramp.
; ------------------------------------------------------------------------------
    .ds $FDD8 - *, 0
    .byte $8D, $F8, $1F         ; sta $1FF8 (twin)
    .byte $4C, $87, $FD         ; jmp $FD87 (twin — fetched post-switch)
    .ds $FDE1 - *, 0            ; (was the PickPlayerFrame tramp mirror + the
                                 ;   PlayerWalkA/B art twin: both deleted
                                 ;   2026-10-20 — body moved to bank0)

    .ds $FE00 - *, 0            ; PHMOverlay pinned: bank0's dead jmp operand
                                 ; is the literal $FE00 (moth-style dead bytes;
                                 ; body only ever runs bank2-side)
PHMOverlay:
    ; Phase 4 asym-patch collision (entered via OverlayTramp, 0 pushes).
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
    cmp RectCount                ; vl vs BallX
    bcc .OvT2
    beq .OvT2
    bcs .OvClear                ; vl > BallX → player fully right of patch
.OvT2:
    lda RectCount
    sec
    sbc #13                     ; BallX-13 (lit span is 7px, not 8: [vl,vl+6])
    cmp CollisionX              ; vs vl: overlap iff BallX-13 <= vl
    bcc .OvBand
    beq .OvBand
.OvClear:
    jmp OvM1Block               ; right-strip miss → M1 (left) strip test;
                                 ; IT returns via ReturnPad (C set/clear).
                                 ; Shutter rooms: miss here = player left of
                                 ; the VISIBLE right-half block → passable
                                 ; (kill follows the drawn block only, async
                                 ; ruling 2026-10-14 — no left mirror)
.OvBand:
    jmp OvShutBand              ; band overlap → shutter kill / strip solid
                                 ; (body in the $FE9C hole; band test lives
                                 ; there so the $FE00-$FE90 window stays fit)
OvHead:
    .byte 7,6,4                 ; rows 0..2 → mask bits >= row
OvTail:
    .byte 1,3,7                 ; rows 0..2 → mask bits <= row

    .ds $FE96 - *, 0            ; S5.4 LHT tramp — byte-identical w/ kernel.asm
                                ; (shifted +$10 with kernel's tables)
LaserHitTest:
    sta $1FF8                   ; dead in bank2 (entry arrives at $FE89)
    jmp LaserHitTestBody        ; == $FF00 — operand guard vs bank0 literal

; ------------------------------------------------------------------------------
; OvShutBand — right-column strip on the PHMOverlay miss path. Entered from
; PHMOverlay .OvBand (right-column + player-band overlap). MetaB b7 marks a
; LOCKED_DOOR right strip; b7 clear is a plain D6 strip. A plain strip is
; solid. A door strip is solid until the key is held, then the touch
; destroys it (EnemyDeadMask b3) and the walk passes (Phase 5).
; Kill follows the VISIBLE right-half block only (async ruling 2026-10-14 —
; no left mirror). The retired vcrunch kill test is gone.
; ------------------------------------------------------------------------------
    .ds $FE9C - *, 0            ; free hole before the moth tramp ($FEF0)
OvShutBand:
    ldx CollisionCellY
    lda OvHead,X                ; bits >= row
    ldx CollisionEndY
    and OvTail,X                ; bits <= row
    and LineCount               ; active-band mask (b0-2)
    beq .OSBm1                  ; not in a painted band → M1 strip test
    lda RoomMetaB               ; MetaB
    bpl .OSBsolid               ; b7=0: plain D6 strip → solid
    lda LevelStartRoom          ; KeyHeld?
    bpl .OSBsolid               ; no key → locked (solid)
    lda EnemyDeadMask           ; key held: the touch destroys the strip
    ora #$08                    ; b3 = ball strip (right door) destroyed
    sta EnemyDeadMask
    jmp .OSBm1                  ; passable (strip blanked next StageBandTab)
.OSBsolid:
    sec
    jmp ReturnPad
.OSBm1:
    jmp OvM1Block

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

    ; Tally entry tramp slice ($FFE6-$FFEB, byte-identical with kernel.asm —
; guard: check_moth_tramp). bank0 executes `sta $1FF8`; the fetch at $FFE9
; comes from THIS bank = `jmp TallyEntry`. Neither bank runs its other half.
    .ds $FFE6 - *, 0
TallyTramp:
    sta $1FF8
    jmp TallyEntry

; ------------------------------------------------------------------------------
; HotOverlapFlag (bank2-side, A3): OvM1Block/OvShutBand reach it with `jmp`
; while bank2 is selected, so THIS copy is the live one. Bank3 has no room
; at $FE93 (OvShutBand .OSline), so the pad sits at $FFEC like bank0's;
; the `jmp` at +3 is fetched from bank3's $FFEF image.
; ------------------------------------------------------------------------------
    .ds $FFEC - *, 0
HotOverlapFlag:
    sta $1FF9                   ; select bank3
    jmp $F5C3                   ; bank3 HotOverlapBody (synced by verify_build)
    .ds $FFF2 - *, 0            ; $FFF2-$FFF9 stay fill (F6 hotspot mirrors)

    ; Pad to vectors at $FFFA ($FFF2-$FFF9 = fill — never code: $FFF6-$FFF9
    ; are F6 hotspot mirrors on peek, see MothExitPad at $FC49)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
