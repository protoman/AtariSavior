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
RoomPF0Lo = $99                 ; TilePF0 pointer (EnterRoom stages; models
                                 ; data lives in THIS bank — bank0 cannot
                                 ; read it, see StageBandTab)
RoomPF0Hi = $9A                 ; #22 EnterRoomB2 — kernel sequential-block pair
LevelPFDataLo = $9F             ; RoomDataTable pointer low (kernel decl)
LevelPFDataHi = $A0             ; RoomDataTable pointer high (kernel decl)
LevelEnemyLo = $AF              ; RoomEnemies pointer low (kernel decl)
LevelEnemyHi = $B0              ; RoomEnemies pointer high (kernel decl)
RoomBandColor = $BC             ; band-color cache (kernel EQU, S3.1)
BandTab = $ED                   ; Phase 3 band gate bytes — staged here,
                                 ; read by kernel .Row in bank0
; Vcrunch shutter slice staging — same bytes as kernel.asm's decls
; (PhaseBlink prologue restages every VBL; VcrShutter arm overwrites).
; $EA also = FooterPtr6 below (title/footer-only role, frame-disjoint).
VcrState = $EA                   ; slice state (b0-4 = slices 0-4 closed)
VcrNext = $EB                    ; next slice index (1..5; 0 = idle)
VcrBand = $EC                    ; shutter tile band (1, middle) or $FF idle
; (No Slice0Cnt: .Row derives the shutter-band length from VcrBand/VcrNext — a
;  staged length byte read stale title-HUD $EE garbage on the
;  title->game frames: 255-line rows, 681-line boot frames, 2026-10-14.)
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
Grp0Ptr = $86                  ; must match kernel.asm (PickPlayerFrame body)
Grp0PtrHi = $87                ; must match kernel.asm
SWCHA = $0280                  ; RIOT joystick (same in every bank)
PlayerSpriteA = $f8dd           ; hand copies (bank0 symbols unreadable here);
PlayerSpriteB = $f8e9           ; tools/test_miner_colors.py asserts vs bank0.lst
PlayerWalkA = $fde7
PlayerWalkB = $fdf3
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

    ; --- 5-byte stub ---
    lda #0
    sta $1FF6                       ; select bank0
    jmp $F005                       ; GameStart in bank0

    ; --- #22 EnterRoomB2 ($F010) -----------------------------------------------
    ; Body of bank0's EnterRoom (tramp at $FBD0: sta $1FF8 / jmp $F010).
    ; Reached with A = room index; returns via jmp ReturnPad (X = EnemyCount).
    ; Level data lives in THIS bank → direct (FetchPtr),Y reads, NO folds
    ; (same transcription as MothRoutine below). Saves ~1660c per room change.
    ; Must end before org $F100 (MothRoutine) — overflow = Origin Reverse.
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

    ; --- copy solid rect list → ZP cache: ROM is packed 2B/rect
    ;     [x<<2|y, w<<2|h], cache keeps the uniform 4B walk form.
    ;     Copies 5 slots unconditionally (count = RcBase gates walkers).
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    lda (FetchPtr),Y                ; count
    cmp #6
    bcc .EBrcCntOk
    lda #5                          ; rect5+ not cached (ZP ends $DF) — clamp
.EBrcCntOk:                         ; so walkers can trust RcBase <= 5
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
    sta EnemyDataLo
    iny
    lda (FetchPtr),Y
    sta EnemyDataHi
    iny
    lda (FetchPtr),Y
    sta EnemyCount
    iny                             ; +3 = bottom-band color — must restage
    lda (FetchPtr),Y                ; HERE or CheckBandTouch kills with the
    sta RoomBandColor               ; SOURCE room's band on the transition frame
    lda #$00
    sta EnemyDeadMask               ; no dead enemies in new room

    ; --- bomb reset: clear state/timer/sound (wall bits b3-6 die with it) ---
    lda #0
    sta BombPacked
    sta BombTimer
    sta BombSnd
    sta AUDV0

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
    iny                             ; +1 = x
    lda (FetchPtr),Y
    sta EnemyRamX,X
    iny                             ; +2 = y
    lda (FetchPtr),Y
    sta EnemyRamY,X
    iny                             ; +3 = dir ($FF = left)
    lda (FetchPtr),Y
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

; 48-line band row lookup — copy of kernel's YToRowTable (bank2 cannot read
; bank0 ROM). Index = line >> 2, value = floor(line/48) = band row 0-3.
; Max in-cave index = (143+8) >> 2 = 37 — fits.
MothRowTable:
    .byte 0,0,0,0,0,0,0,0,0,0,0,0
    .byte 1,1,1,1,1,1,1,1,1,1,1,1
    .byte 2,2,2,2,2,2,2,2,2,2,2,2
    .byte 3,3,3,3,3,3,3,3,3,3,3,3

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
    tay
    lda MothRowTable,Y
    sta CollisionCellY          ; top band row
    lda RoomY
    clc
    adc #3
    lsr
    lsr
    tay
    lda MothRowTable,Y
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
    ldy #9
    lda (RoomPF0Lo),Y           ; MetaA
    lsr
    lsr
    lsr
    lsr                         ; m1_col+1 (0 = no M1 patch)
    beq .LWm1Skip
    lda EnemyDeadMask
    and #$10                    ; b4 = M1 strip destroyed -> transparent
    bne .LWm1Skip
    ldy #9
    lda (RoomPF0Lo),Y           ; reload MetaA (dead test clobbered A)
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
    txa
    clc
    adc #20                     ; miner reach = 1000 pts
    adc PlayerBombs             ; + 50 per unspent bomb (chain carry ok)
    sta TallyTicks
    lda PlayerLives
    asl                         ; + 100 per life = 2 ticks
    clc
    adc TallyTicks
    sta TallyTicks
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
; BCFDarkRun — BuildColupF's dark-room override (moved here from BCF's tail:
; the $FCF0 pin left <8 B there when the mask grew to rooms 4-7). Same pad
; rules as the inline it replaces: no folds/pads (ReturnPad switches to
; bank0), tail ends at ReturnPad. 8-bit RoomDarkMask mirrors bank1
; IsRoomDark: rooms 0-3 = EnemyRamD b4-7, rooms 4-7 = LaserState b2-5,
; rooms 8+ = lit.
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
    jmp StageBandTab            ; Phase 3: stage ball meta, then ReturnPad
                                ; (was `jmp $FBF8`; same 3 B, no pad growth)
BCFDarkMask:
    .byte $10, $20, $40, $80    ; rooms 0-3 → EnemyRamD bits 4-7
    .byte $10, $20, $40, $80    ; rooms 4-7 → lsr×2 = LaserState bits 2-5

; --- Level data (frozen addresses — pointer values must match bank0's
;     original layout, level_bank_plan P2.1: $F9D9-$FB1E = 326B) ---
    .ds $F3C4 - *, 0            ; pin body entry = bank0 tramp's jmp operand
; ------------------------------------------------------------------------------
; PickPlayerFrame body — entered from bank0's VBL via the $FDE1 tramp (the
; jmp operand is fetched from THIS bank). GRP0 frame pick: jet flutter
; (PlayerSpriteA/B) > ground walk (PlayerWalkA/B, phase EnemyRamP&$08) >
; static A. Clobbers A/Y; sets Grp0Ptr/Grp0PtrHi; tail-jmps ReturnPad so the
; VBL jsr returns in bank0 (pads must not nest — no rts here).
; ------------------------------------------------------------------------------
PickPlayerFrame:
    lda JetPower
    bne .Jet                   ; jet burning -> A/B flutter (existing)
    lda BombPacked
    bpl .FrameA                ; b7 OnGround clear (airborne) -> static
    lda SWCHA
    and #%11000000             ; D7 right / D6 left, active LOW
    cmp #%11000000
    beq .FrameA                ; neither held -> standing
    lda EnemyRamP              ; free-running clock: bit3 = 8-frame
    and #%00001000             ; half-cycle -> 16-frame full walk cycle
    beq .WalkA                 ; (double speed of the 32-frame bit4 version)
    lda #<PlayerWalkB
    ldy #>PlayerWalkB
    jmp .SetGrpPtr
.WalkA:
    lda #<PlayerWalkA
    ldy #>PlayerWalkA
    jmp .SetGrpPtr
.Jet:
    lda TickCounter
    and #%00000100
    beq .FrameA
    lda #<PlayerSpriteB
    ldy #>PlayerSpriteB
    jmp .SetGrpPtr
.FrameA:
    lda #<PlayerSpriteA
    ldy #>PlayerSpriteA
.SetGrpPtr:
    sta Grp0Ptr
    sty Grp0PtrHi
    jmp ReturnPad              ; sta $1FF6 (via ReturnPad) + rts -> VBL

; ------------------------------------------------------------------------------
; StageBandTab — asym meta: decode packed model meta into bank0 ZP for the cave.
; Reached from BuildColupF's tail (BCFDarkRun jmp here); ends at ReturnPad so
; the VBL jsr returns to bank0 (pads must not nest — no rts here).
; WHY here: models_data lives in THIS bank — a bank0 (RoomPF0Lo),Y read
; fetches bank0's $F9xx zero pad (the Phase 2 ball block silently read zeros).
; Packed meta (bugs.md 28 point 1): TilePF0+9 = MetaA = (m1_col+1)<<4 |
; band_mask (b0-2 = band0/1/2 gates); TilePF0+10 = MetaB = ball_col+1
; (0 = feature absent). Expanded to the old RAM shapes:
;   BandTab ($ED-$EF) <- $ff/$00 per-band ENABL gates (.Row ENABL reads
;                        bit0; the pack's `bit`/`bpl` reads bit7)
;   Temp    ($88)     <- BallX = 87+8*ball_col (0 ⇔ symmetric → skip;
;                        verify_build enforces)
;   CollisionEndX ($8E) <- M1X = 7+8*m1_col (0 = no M1; kill-gated below)
; Window: staged every VBL → read by cave → bank1 HUD stomps $ED-$EF after
; the cave read → overscan rewrites $88 (joystick) after the ball read.
; ------------------------------------------------------------------------------
StageBandTab:
    ; --- expand band mask -> BandTab $ff/$00 ×3 (bit0 ENABL + bit7 pack) ---
    ldy #9
    ; --- Phase 5: stage the M1 x-offset for the door SIDE. A door's band
    ; mask is $02, so MetaA bit0 is free: 1 = M1 strip on the RIGHT half
    ; (x = 87+8*col → offset +79), 0 = left (x = 7+8*col → offset -1).
    ; The M1 block adds it via clc/adc RectCount. RectCount ($92) is free in
    ; the VBL (kernel re-inits RowIdx at entry; the pack uses $8F).
    lda (RoomPF0Lo),Y       ; MetaA
    and #$01
    tax
    lda M1OffTab,X
    sta RectCount
    lda (RoomPF0Lo),Y       ; MetaA
    lsr                     ; band0 bit -> carry
    lda #0
    rol
    beq .SBTb0z
    lda #$ff
.SBTb0z:
    sta BandTab
    lda (RoomPF0Lo),Y
    lsr
    lsr                     ; band1 bit -> carry
    lda #0
    rol
    beq .SBTb1z
    lda #$ff
.SBTb1z:
    sta BandTab+1
    lda (RoomPF0Lo),Y
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
    ldy #9
    lda (RoomPF0Lo),Y
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
    ldy #10
    lda (RoomPF0Lo),Y       ; MetaB = ball_col+1 (0 = none)
    and #$7F                ; defensive: b7 unused since the door eor died
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
.SBTballDone:
    ; --- NUSIZ1 owned here since P2b (kernel's VBL $30 restore deleted) ---
    ; Constant $30 (P1 single, M1 8 clk): the door distinction is COLOR
    ; (yellow $1C staged below), not width — the 4clk block read as "half
    ; a tile", the 2clk thin stripe as "only one strip" (user, 2026-10-12).
    lda #$30
    sta NUSIZ1
    ; Door stripe color ($8D) is staged inside PhaseBlink (this window
    ; is full to the $F4C4 pin — the 14B staging block lives with the
    ; walk where there is hole).
    ; --- Phase 3: phase-cell blink (PF buffer pokes) ----------------------
    ; Body moved after the level data (PhaseBlink, ~130B — the StageBandTab
    ; window $F3C4..$F4C4 was full; the data window has the only free
    ; hole). Contract: clobbers A/X/Y/FetchPtr/RectCount/LineCount/
    ; CollisionCellX/CollisionEndY ($8F scratch — the pack below rebuilds
    ; it). The PF buffers ARE the collision map (cell walk + laser read
    ; them) — toggling the cell's two bits THERE makes render + PHM +
    ; laser follow with zero kernel cost. 64f full cycle = EnemyRamP bit5
    ; (32 on + 32 off; clock-derived, no state bytes — locked plan).
    jsr PhaseBlink
    ; --- Phase 4: pack collision overlay byte → CollisionEndY ($8F) ---
    ; b4-b7 = right_col+1, b0-2 = ball band mask, b3 = M1 present
    ; (staged $8E != 0), 0 = symmetric. Cave never
    ; writes $8F; bank1 HUD entry copies it to LineCount ($84 — cave .Row
    ; clobbers it) before overscan PHM reads. BallX in Temp stays raw (the
    ; kernel's ball block reads it later this VBL).
    ; b3 seeds BEFORE the Temp=0 early-out so an M1-ONLY room still packs
    ; nonzero (kernel OverlayTramp gates on LineCount != 0 — no M1 cross
    ; otherwise).
    lda #0
    sta CollisionEndY
    lda CollisionEndX           ; staged M1X (kill-gated above)
    beq .M1nof
    lda #$08
    sta CollisionEndY           ; b3 = M1 present
.M1nof:
    lda Temp
    beq .SBTPack                ; no ball → keep b3-only (or 0) pack
    sec
    sbc #87
    lsr
    lsr
    lsr                         ; right_col 0..9
    asl
    asl
    asl
    asl
    clc
    adc #$10                    ; (right_col+1) into b4-b7
    ora CollisionEndY           ; merge with the b3 seed
    sta CollisionEndY
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

; ------------------------------------------------------------------------------
; TitleSequence — intro ($FD) phase machine (plans/title_bomb_sequence_plan).
; Cross-bank entry: bank0 TitleSequenceFold (jsr → sta $1FF8 → jmp $F4C4,
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
    .ds $F4C4 - *, 0            ; pinned: bank0/bank2 TitleSequenceFold jmp
                                 ; operand ($F4C4 since P2b StageBandTab grew;
                                 ; verify_build asserts the operand is a
                                 ; TitleSequence lst row start)
TitleSequence:
    lda DropTarget
    cmp #$FD
    beq .TSAlive
    jmp .TSdone
.TSAlive:
    ; --- own the bomb fuse (title: BombTick gated off) ---
    lda BombPacked
    and #%00000011
    beq .TSNoBomb
    cmp #1
    beq .TSFuse
    dec BombTimer               ; state 2 — explosion countdown
    bne .TSNoBomb
    lda BombPacked              ; → state 0 (mask/DownPrev kept)
    and #%11111100
    sta BombPacked
    lda #0
    sta BombTimer
    jmp .TSNoBomb
.TSFuse:
    dec BombTimer
    bne .TSNoBomb
    lda BombPacked              ; 1 → 2, explode tone (no BMW/score/blast)
    and #%11111100
    ora #%00000010
    sta BombPacked
    lda #60
    sta BombTimer
    lda #8                      ; noise — bank1 BombSndExplode's regs
    sta AUDC0
    lda #0
    sta AUDF0
    lda #10
    sta AUDV0
    lda #30
    sta BombSnd                 ; UpdateBombSound fades AUDV0 out
.TSNoBomb:
    lda BombPacked              ; no live bomb → BombX = footer/base X
    and #%00000011
    bne .TSPhase
    lda #68
    sta BombX
.TSPhase:
    ; --- dispatch ---
    lda TallyTicks
    bne .TSNotP0
    lda RoomX                   ; phase 0: fly right to 140
    cmp #140
    bcc .P0Fly
    jmp .TSAdv
.P0Fly:
    inc RoomX
    jmp .TSdone
.TSNotP0:
    cmp #1
    bne .TSNotP1
    lda RoomY                   ; phase 1: drop to 48 (ground)
    cmp #48
    bcc .P1Drop
    jmp .TSAdv
.P1Drop:
    inc RoomY
    jmp .TSdone
.TSNotP1:
    cmp #2
    bne .TSNotP2
    lda #1                      ; phase 2: face left (FACING_LEFT)
    sta PlayerDir
    jmp .TSAdv
.TSNotP2:
    cmp #3
    bne .TSNotP3
    lda BombPacked              ; phase 3: arm bomb at X=140, fuse 180
    ora #%00000001
    sta BombPacked
    lda #140
    sta BombX
    lda #180
    sta BombTimer
    lda #4                      ; square — bank1 BombSndDrop's regs
    sta AUDC0
    lda #10
    sta AUDF0
    lda #8
    sta AUDV0
    lda #6
    sta BombSnd
    jmp .TSAdv
.TSNotP3:
    cmp #4
    bne .TSNotP4
    lda RoomX                   ; phase 4: walk left to center (X=76)
    cmp #77
    bcc .P4Wait
    dec RoomX
    jmp .TSdone
.P4Wait:
    lda #0                      ; at center: wait for the blast facing right
    sta PlayerDir
    jmp .TSAdv
.TSNotP4:
    cmp #5
    bne .TSNotP5
    lda BombPacked              ; phase 5: wait out fuse + explosion
    and #%00000011
    bne .TSdone
    lda #1                      ; blast gone: walk home facing left
    sta PlayerDir
    jmp .TSAdv
.TSNotP5:
    cmp #6
    bne .TSNotP6
    lda RoomX                   ; phase 6: walk home (X=20), then pause 240
    cmp #21
    bcc .TSPause
    dec RoomX
    jmp .TSdone
.TSPause:
    lda #240
    sta BombTimer
    lda #0                      ; home: wait facing right (before the climb)
    sta PlayerDir
    jmp .TSAdv
.TSNotP6:
    cmp #7
    bne .TSNotP7
    dec BombTimer               ; phase 7: own the 240-frame pause — BombTick
    bne .TSdone                 ;   is gated off on titles, nothing else ticks
    jmp .TSAdv                  ;   (dir already 0 — set at .TSPause) -> phase 8
.TSNotP7:
    cmp #8
    bne .TSdone
    lda RoomY                   ; phase 8: fly back up to original Y=0, then
    bne .P8Climb                ;   restart the loop (no teleport)
    lda #20                     ;   X walked home already; belt + braces
    sta RoomX
    lda #0
    sta TallyTicks
    jmp .TSdone
.P8Climb:
    dec RoomY
    jmp .TSdone
.TSAdv:
    inc TallyTicks
.TSdone:
    jmp ReturnPad                   ; ReturnPad → bank0 TitleIntro (0 push)

; Cell-map lookup copies (bank2 cannot read bank0 ROM) — cell_collision_plan
; 0.2 bit spec, byte-identical to kernel.asm's ColOff/ColMask: group offset
; 0/3/6 + per-col bit (PF0 LSB-first nibble, PF1 MSB-first, PF2 LSB-first).
; Moved here 2026-10-08 (was between LWpSolid and MothGate): the TallyEntry
; $F313 pin splits bank2's pre-region and the LWC M1 tip test needed the 44B.
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
    ldy #9
    lda (RoomPF0Lo),Y           ; MetaA
    and #$01                    ; Phase 5: b0 = M1 strip on the RIGHT half
    tax                         ;   (door band mask is $02 → b0 free)
    lda (RoomPF0Lo),Y           ; reload MetaA
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
    .ds $F854 - *, 0            ; FooterFont ends $F854 (13-row) — sprite/color data
    .ds $F864 - *, 0            ; #27b level spill slot ($F864, 28B; empty until
    include "generated/spill_F840.asm" ;  convert_level places a level here)
    .ds $F880 - *, 0
    .ds $F8B7 - *, 0            ; spill-pool gap: VcrCoveredState relocated here
; ------------------------------------------------------------------------------
; VcrCoveredState — aperture clock → slice state (vcrunch_shutter_plan Phase C).
; (moved from the $FE9C hole 2026-10-17 to make room for the ball-door key
;  touch-unlock in OvShutBand; no callers since VcrStateTab took the hot path —
;  kept as the formula reference verify_build guards against CrunchClock.)
; IN: A = frame clock (EnemyRamP). OUT: A = $00/$11/$1B/$1F (slice states).
; Mirror of bank3 CrunchClock (lsr/lsr = clock>>2, cmp #32 / eor #$3F fold,
; cmp #4 / sbc #4 head offset — verify_build asserts the shared constants).
; ------------------------------------------------------------------------------
VcrCoveredState:
    lsr
    lsr                         ; clock>>2 (64-frame ping-pong period)
    cmp #32
    bcc .VChop
    eor #$3F                    ; 32..63 -> 31..0 (fold down)
.VChop:
    cmp #4
    bcc .VCq
    sbc #4                      ; head offset (C set by cmp) — dwell zone
.VCq:
    cmp #4
    bcc .VCopen                 ; eff 0-3 (both dwell halves) -> fully open
    cmp #9
    bcc .VC11
    cmp #18
    bcc .VC1b
    lda #$1f                    ; fully closed
    rts
.VC1b:
    lda #$1b                    ; center slice open
    rts
.VC11:
    lda #$11                    ; only edge slices closed
    rts
.VCopen:
    lda #0                      ; fully open
    rts
    .ds $F8DD - *, 0            ; twin: bank0 PlayerSpriteA lives here (test_miner)
TitleJetSprite:
    ; Exact A/B copies of PlayerSpriteA/B; game alternates every 4 frames.
    .byte %00111100, %01111110, %01111100, %01111110
    .byte %01111100, %11111110, %11111110, %00111110
    .byte %00111110, %00010100, %00010100, %00010100
    .byte %00111100, %01111110, %01111100, %01111110
    .byte %01111100, %11111110, %11111110, %01111110
    .byte %10111110, %00010100, %00010100, %00010100
; --- Level-data spill 2 (bugs.md 27/27b): fill gap $F901..$F970 (111B) ---
    include "generated/spill_F901.asm"        ; #27b: placed by convert_level
    ; Phase 3 blink masks — pair index (2c>>1) → the two adjacent PF bits
    ; for that left-half cell (PF0: bits4-7 left-to-right; PF1: bits7-0;
    ; PF2: bits0-7 reversed). Pairs never straddle a register (even 2c).
PhMaskTab:
    .byte $30, $C0                     ; PF0 pairs (0,1) (2,3)
    .byte $C0, $30, $0C, $03           ; PF1 pairs (4,5) (6,7) (8,9) (10,11)
    .byte $03, $0C, $30, $C0           ; PF2 pairs (12,13) ... (18,19)
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
    ldy #9
    lda (RoomPF0Lo),Y           ; MetaA
    and #$08                    ; b3 = left door (key-only, bomb-immune)
    bne .M1SBnone               ; stays $FF: bank1 takes no left strip
    lda (RoomPF0Lo),Y           ; reload (and clobbered A)
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
    ldy #10
    lda (RoomPF0Lo),Y           ; MetaB, b7 = right door
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
    ; Level 3 (~104B) spills to the $F901 gap and level 4 + levels_index
    ; (~128B) to the $F767 gap above (bugs.md 27 — re-place on growth).
    org $F9D9
    include "generated/models_data.asm"
    include "generated/level_001_rooms_data.asm"
    include "generated/level_002_rooms_data.asm"
    include "generated/level_003_rooms_data.asm"
    include "generated/level_004_rooms_data.asm"
    include "generated/spill_window.asm"       ; #27b: level rooms, placed by convert_level

    ; --- Phase 3: phase-cell blink (moved here — StageBandTab window full)
    ; Walks the hot-stream $80 records [class, 2c, row, 2, 1] and toggles
    ; the cell's two PF bits per EnemyRamP bit5 (64f cycle: 32 ON + 32
    ; OFF). The PF buffers are the collision map — render, PHM, and the
    ; laser all follow the blink for free. $81/$82 (vcrunch/hcrunch)
    ; tramp to bank3 (CrunchClock ping-pong staging — Phase 4); legacy
    ; hot rects are skipped. CollisionEndY ($8F) is
    ; scratch: the pack rebuild in StageBandTab overwrites it right
    ; after the call returns.
PhaseBlink:
    ; --- Phase C vcrunch slice staging (defaults; the walk's VcrShutter
    ; arm overwrites for shutter rooms). Runs every VBL this routine does —
    ; bank1 HUD already stomped $EA/$EB/$EC after the cave, so a full
    ; restage here is the only way the next kernel reads sane values.
    ; Idle defaults: VcrBand=$FF (tail dispatch never matches), VcrNext=0
    ; (idle marker — only 1..4 slices), VcrState=0. The band0 length needs
    ; no byte: .Row derives 8/48 from these two.
    lda #$FF
    sta VcrBand
    lda #0
    sta VcrNext
    sta VcrState
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
    ldy #9
    lda (RoomPF0Lo),Y       ; MetaA
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
.PhRec:
    lda RectCount
    beq .PhDone
    dec RectCount
    iny                     ; Y → record class
    lda (FetchPtr),Y
    bpl .PhSkip             ; legacy hot rect — not a blink cell
    cmp #$80
    beq .PhPhase
    cmp #$81
    bne .PhB82
    jmp PhVcrPre            ; Phase 4: pre-read fields (bank2 ROM), tramp bank3
.PhB82:
    cmp #$82
    bne .PhSkip             ; unknown b7 class: skip 4
    jmp PhHcrPre            ; Phase 4: pre-read fields (bank2 ROM), tramp bank3
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
    jmp .PhRec
.PhSkip:                    ; non-phase record: skip its last 4 bytes
    iny
    iny
    iny
    iny                     ; Y → h (record last byte)
    jmp .PhRec
.PhDone:
    rts

; ------------------------------------------------------------------------------
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
    sta $1FF8
    jmp $F4C4                    ; TitleSequence
    .ds $FBE0 - *, 0
    sta $1FF8
    jmp $F700
    .ds $FBE8 - *, 0
    sta $1FF8
    jmp $F880
    .ds $FBEE - *, 0
Bank2ReturnPad:                 ; bank3 VCS3 (OvShutScan body) tail target:
                                ;   sta executes bank3-side, rts fetched from
                                ;   THIS byte-identical copy (post-switch)
    sta $1FF8
    rts
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF6
    rts

; ------------------------------------------------------------------------------
; CallPad_BuildColupF — byte-identical stub. Execution starts in bank0; after
; `sta $1FF8` the pad's `jmp $FC4F` is FETCHED FROM THIS BANK (the switch
; happens mid-pad, same reason bank1 mirrors the whole pad block).
; ------------------------------------------------------------------------------
    ; ---- HOV feature pre-read ($FBFC gap; $80 skips field reads) --------
HOVFeatPre:                 ; .HOVfeature: A = class, Y = record base
        cmp #$80
        beq .HFPdirect      ; $80 phase: no fields, no staging (Y = base
                            ;   must survive — HOVafterGate reads it)
        tax                 ; X = class (survives the field pushes; the old
                            ;   Y-restore + class reload is dead — bank3
                            ;   reads fields from the stack, never Y)
        iny
        lda (FetchPtr),Y
        pha                 ; x
        iny
        lda (FetchPtr),Y
        pha                 ; y
        iny
        lda (FetchPtr),Y
        pha                 ; w
        iny
        lda (FetchPtr),Y
        pha                 ; h
        ; Rule 1 (user 2026-10-14): stage MetaB for HOVhcrunch's hot
        ; exemption. Full byte — bank3 tests b6 via asl×2 (b7 shutter
        ; flag shifts out first; hcrunch rooms keep b7 clear). LineCount
        ; is free on the HOV hit path (the overlay reader is the miss
        ; path — mutually exclusive; kernel restages per row). X still
        ; holds the class (survives the field pushes) — no pha/pla pair.
        ldy #10
        lda (RoomPF0Lo),Y   ; MetaB
        sta LineCount
        txa                 ; class (A = record class for bank3)
.HFPdirect:
        sta $1FF9
        jmp $FA40           ; HOVFeatEntry (bank3)
PhHcrPre:                   ; PhaseBlink $82: Y = record base
        ldx #4              ; field-push loop (x,y,w,h — same stack order;
.PHp                        ;   PhHcrEntry reads via tsx, A unused)
        iny
        lda (FetchPtr),Y
        pha
        dex
        bne .PHp            ; Y = base+4 (bank3's return contract)
        tya
        pha                 ; save base+4 across the MetaB read
        ldy #10
        lda (RoomPF0Lo),Y       ; MetaB (bank2 ROM image at TilePF0+10 =
                                ; $FA3C; a bank3 fetch sees pad $FF there)
        sta LineCount           ; full byte — bank3's HcrPush masks b6;
                                ; read EARLY in PhHcrEntry, before the PF
                                ; mask staging reuses LineCount.
        pla
        tay                 ; Y = base+4 (record end → .PhRec iny)
        sta $1FF9
        jmp $F880           ; PhHcrEntry (bank3)
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
;   - jsr CallPad_IsRoomDark -> BCFDarkRun (pre-level-data gap; pads cannot
;     nest: ReturnPad switches to bank0, so rts would resume in bank0).
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
                                 ;   $81 vcrunch / $82 hcrunch) — NOT a
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
; Phase 4 bank3 return pads ($FCC1-$FCDD): bank3 crunch bodies tail
; `sta $1FF8 / jmp <here>` — the sta executes bank3-side; the 3-byte jmp
; at +3 is FETCHED FROM THIS BANK post-switch (F6 pad rule), so each
; `jmp <label>` image below must stay byte-identical with bank3.asm's
; tail at the SAME address (dasm check_tramp_targets verifies the
; bank3-side jmp operand against these labels). Slots 0-2 of each pad
; are bank3-only (the sta) — never fetched bank2-side.
; ------------------------------------------------------------------------------
    .ds $FCC1 - *, 0
    .byte 0, 0, 0
    jmp PhNext               ; vcrunch PF staging return (Y = base+2)
    .byte 0, 0, 0
    jmp PhNext               ; hcrunch PF staging return (Y = base+2)
    .byte 0, 0, 0
    jmp HOVnext              ; crunch miss → record walk continues
    .byte 0, 0, 0
    jmp HOVlegHit            ; crunch kill HIT → shared Temp b7 tail
    .byte 0, 0, 0
    jmp HOVafterGate         ; phase armed → overlap tests
    .ds $FCF0 - *, 0            ; pinned: bank0 tramp operand is literal $FCF0
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
                                 ;   $81 vcrunch / $82 hcrunch) — NOT a
                                 ;   legacy death rect (see .HOVfeature
                                 ;   after .HOVdone).
    bne .HOVwallGate
    lda EnemyDeadMask
    and #$10                    ; b4: strip destroyed → M1 rect dead
    bne HOVnext                ; (HOVnext pops the loop's pushed Y)
    beq HOVafterGate           ; strip alive → continue (result was 0)
.HOVwallGate:
    and BombPacked
    bne HOVnext
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
    bpl HOVlegHit              ; legacy hot rect → no phase latch
    lda EnemyDeadMask
    ora #$40                    ; b6: phase dead — walls removed from now on
    sta EnemyDeadMask           ;   (PhaseBlink forces punch-OFF, kill gated)
HOVlegHit:
    pla
    lda Temp
    ora #%10000000
    sta Temp
    sec                         ; tail-call contract: return C=1
    jmp ReturnPad                   ; ReturnPad → original caller (C survives)
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

; Feature-record dispatch ($80 phase / $81 vcrunch / $82 hcrunch — Phase 4):
; armed/overlap/kill tests live in bank3 (HOVFeatEntry). $80 phase: b5 armed
; (staged by PhaseBlink each VBL) + candidate-box overlap → shared Hot hit
; (Temp b7 → bank0 `jsr LoseLife`); kill gated on armed-and-not-removed
; (`and #$60 / cmp #$20`), latches b6, PhaseBlink punch forced OFF while b6
; set (walls REMOVED, same-room only — EnterRoom zeroes the mask).
; $81 vcrunch: sprite shutter — the kill rides the OverlayTramp MISS path
; (OvShutTest/OvShutBand, MetaB b7 gate) because the punched cell never
; trips this walk. The record path (loop push + HOVFeatPre's 4 field pushes
; + bank3 jsr HOVvcrunch) measured SP=$F6 = real BombTimer ($F7) stomp
; (sim_bomb_fuse mirror stomp, 2026-10-13) — skip the record here.
; Entered with Y = record base + pushed Y (loop invariant), A = mask.
; 15B kept: the cmp/beq/jmp + pad replace the old tramp byte-for-byte —
; the BombEnemyBlastBody $FD87 pin (kernel tramp operand) must not move.
.HOVfeature:
    cmp #$81
    beq HOVnext             ; vcrunch skip (HOVnext pops the loop Y)
    jmp HOVFeatPre          ; → pre-read fields (bank2 ROM) → bank3 dispatch
    .ds 8, 0                ; pad: 2+2+3+8 = 15B = old body size

; ------------------------------------------------------------------------------
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
    .ds $FDE1 - *, 0            ; PickPlayerFrame tramp mirror (byte-identical
                                 ; with kernel.asm's copy — verify_frame_tramp)
PickPlayerFrameTramp:
    sta $1FF8                   ; executed only as the post-switch fetch image
    jmp $F3C4                   ; bank2 PickPlayerFrame body (this bank)
    ; Twin of bank0 PlayerWalkA/B ($FDE7, 12+12 rows): PickPlayerFrame reads
    ; the hand-copy EQUs while THIS bank is active — without these bytes the
    ; walk frames fetched zeros and the sprite vanished (title + gameplay).
    .byte %00111100, %01111110, %01111100, %01111110
    .byte %01111100, %11111110, %11111110, %00111110
    .byte %00111110, %00010100, %00100010, %01000010   ; walk A boots apart
    .byte %00111100, %01111110, %01111100, %01111110
    .byte %01111100, %11111110, %11111110, %00111110
    .byte %00111110, %00010100, %00011000, %00011000   ; walk B boots together

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

    ; ---- Phase-4 feature pre-read (bank2 ROM owns the record data) -------
    ; Sprite shutter (vcrunch_shutter_plan Phase B): VcrShutter punches the
    ; bbox open in the PF buffers every VBL (the ball block renders in an
    ; open cell — PF priority would hide it under a solid wall) and stages
    ; Temp/BandTab for the kernel ball. Collision/kill no longer ride the
    ; punched cell (the cell walk misses it): PHMOverlay's miss path
    ; (MetaB b7) runs the shutter kill instead. The old bank3 tramp
    ; (PhVcrEntry PF OR/AND staging) is retired — any h handled here.
PhVcrPre:                   ; PhaseBlink $81: Y = record base
        jmp VcrShutter       ; tail (0 pushes — the VBL chain is at the
                              ;   measured SP floor; VcrShutter ends at .PhRec)
; ------------------------------------------------------------------------------
; OvShutScan — Phase C kill test, bank3 body (VCS3 at $FD80). Tramp only:
; the MetaB hot bit (b6) is read HERE (models_data is bank2 ROM — a bank3
; (RoomPF0Lo),Y fetch would see bank3's pad at that address) and passed in
; Y; A = kill clock. sta $1FF9 + jmp — after the hotspot write the jmp
; OPCODE is fetched from bank3's image at the same address (pinned
; `.byte $4C,$80,$FD` at $FE57). Body returns C=1 kill / C=0 passable via
; the $FBEE pad (`sta $1FF8` executed bank3-side; `rts` fetched from
; bank2's byte-identical copy) back to OvShutBand's jsr — A and C
; survive both, stack depth unchanged (+2 for the jsr only). Out
; (2026-10-14b): C=0 passable / C=1 + A≠0 kill / C=1 + A=0 solid block.
; Kill semantics (user spec 2026-10-14): hot band (MetaB b6) = touching
; any closed slice kills; cold band = containment (sprite fully inside
; closed slices), closing phase only (Rule 1). Full logic: bank3 VCS3
; (header there).
; ------------------------------------------------------------------------------
OvShutScan:
    ldy #10
    lda (RoomPF0Lo),Y           ; MetaB
    and #$40                    ; A = b6 mid_band_type hot mask ($40/0)
    tay                         ; Y = hot bit — survives sta $1FF9 + jmp
    lda EnemyRamP
    sec
    sbc #1                      ; kill clock = render clock (post-inc)
    sta $1FF9                   ; bank3
    jmp $FD80                   ; VCS3 — image pinned bank3-side at $FE57
PFOffTab:
    .byte 0,0,3,3,3,3,6,6,6,6   ; pair 0-9 -> PF0/PF1/PF2 reg offset
                                 ;   (VcrShutter punch — moved out of the
                                 ;   $FF00 window to make the Step 4
                                 ;   left-mirror staging fit)
    .ds $FE64 - *, 0
VcrStateTab:                     ; 32B — sc (clock>>2, folded 32..63 -> 31..0)
                                 ;   -> $00/$11/$1B/$1F. VBL hot path uses
                                 ;   this table (2026-10-15: the jsr
                                 ;   VcrCoveredState form was 21c/frame —
                                 ;   V-room VBL sat one TIM64T tick from the
                                 ;   +1-line bucket and bomb-draw frames
                                 ;   crossed it = whole-screen jump).
                                 ;   VcrCoveredState stays as the formula
                                 ;   reference (verify_build guards this
                                 ;   table against it + bank3 CrunchClock).
    .byte $00,$00,$00,$00,$00,$00,$00,$00   ; sc 0-7   dwell (fully open)
    .byte $11,$11,$11,$11,$11               ; sc 8-12  edge slices
    .byte $1b,$1b,$1b,$1b,$1b,$1b,$1b,$1b,$1b  ; sc 13-21 center-open
    .byte $1f,$1f,$1f,$1f,$1f,$1f,$1f,$1f,$1f,$1f  ; sc 22-31 full

    .ds $FE90 - *, 0
HotOverlapFlag:
    sta $1FF8                   ; dead in bank2 (entry arrives at $FE83)
    jmp HotOverlapBody          ; == $FCF0 — operand guard vs bank0 literal
    .ds $FE96 - *, 0            ; S5.4 LHT tramp — byte-identical w/ kernel.asm
                                ; (shifted +$10 with kernel's tables)
LaserHitTest:
    sta $1FF8                   ; dead in bank2 (entry arrives at $FE89)
    jmp LaserHitTestBody        ; == $FF00 — operand guard vs bank0 literal

; ------------------------------------------------------------------------------
; OvShutBand — shutter kill on the PHMOverlay miss path (vcrunch_shutter_plan
; Phase B). Entered from PHMOverlay .OvBand (right-column + player-band
; overlap). The punched cell no longer trips the PF cell walk, so the overlay
; path IS the kill trigger: MetaB b7 (convert's shutter flag) gates it; plain
; D6 strip rooms (b7 clear) fall through to plain solid (old .OvBand
; behavior). Kill follows the VISIBLE right-half block only (async ruling
; 2026-10-14 — the left mirror was removed to fix flicker). Where the
; block is closed but the player is not crunched, VCS3 returns SOLID —
; the walk blocks (no walking through a closed shutter, user
; 2026-10-14b); only the aperture at the player's Y is passable.
; Kill = EnemyDeadMask b7 latch (once per room visit — EnterRoom zeroes) +
; Temp b7 -> kernel hot-bump -> LoseLife; latched = wall REMOVED (open
; hole — VcrShutter punches-only and disarms BandTab; no re-kill).
; ------------------------------------------------------------------------------
    .ds $FE9C - *, 0            ; free hole before the moth tramp ($FEF0)
OvShutBand:
    ldx CollisionCellY
    lda OvHead,X                ; bits >= row
    ldx CollisionEndY
    and OvTail,X                ; bits <= row
    and LineCount               ; active-band mask (b0-2)
    beq .OSBm1                  ; not in a painted band → M1 strip test
    ldy #10
    lda (RoomPF0Lo),Y           ; MetaB
    bpl .OSBsolid               ; b7=0: plain D6 strip → solid (old behavior)
    lda EnemyDeadMask
    bmi .OSBm1                  ; b7 latch: wall REMOVED (VcrShutter punch-
                                ;   only path disarms BandTab, so this arm
                                ;   is defense-in-depth) — passable, no
                                ;   re-kill (user spec 2026-10-14)
    lda LevelStartRoom          ; Phase 5 key: KeyHeld + a plain ball-strip
    bpl .OSBshut                ;   RIGHT door (VcrBand=$FF → not a vcrunch
    lda VcrBand                 ;   room) → the touch destroys it (b3) and the
    cmp #$ff                    ;   walk passes. A vcrunch room (VcrBand 0-2)
    bne .OSBshut                ;   keeps its shutter test — the key does NOT
    lda EnemyDeadMask           ;   disable the hazard.
    ora #$08                    ; b3 = ball strip (right door) destroyed
    sta EnemyDeadMask
    jmp .OSBm1                  ; passable (strip blanked next StageBandTab)
.OSBshut:
    jsr OvShutScan              ; Phase C (bank3 VCS3 via tramp), 2026-10-14b:
                                ;   C=0 passable (A ignored) / C=1 + A≠0 kill
                                ;   / C=1 + A=0 SOLID (block, no latch)
    bcc .OSBm1                  ; aperture open over the player → passable
    beq .OSBsolid               ; A=0: solid — the walk blocks, no death
    lda #$80
    sta Temp                    ; b7 -> kernel hot-bump -> LoseLife
    ora EnemyDeadMask           ; A = $80 | mask (b7 latch; other bits kept)
    sta EnemyDeadMask           ; crunch-kill latch
.OSBsolid:
    sec
    jmp ReturnPad
.OSBm1:
    jmp OvM1Block

; ------------------------------------------------------------------------------
; VcrCoveredState — MOVED to bank2's spill-pool gap ($F8B7) below (2026-10-17),
; freeing this $FE9C hole for OvShutBand's key touch-unlock branch.
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

; ------------------------------------------------------------------------------
; VcrShutter — sprite-shutter staging (vcrunch_shutter_plan Phase B).
; Tail-entered from PhVcrPre (PhaseBlink walk, 0 pushes — the VBL chain sits
; on the measured SP floor) and tail-exits at .PhRec.
;   IN:  FetchPtr = hot record stream, Y = record base (class byte)
;   OUT: Y = base+4 (.PhRec contract: its iny -> base+5 = next class)
;   Clobbers A/X/Y + LineCount/CollisionCellX/CollisionEndY/Temp (all
;   PhaseBlink scratch in this window; the pack rebuilds CollisionEndY
;   after PhaseBlink returns). NO stack use.
; - Punches the vcrunch bbox OPEN in PF0/1/2Buf (pair-range AND): the ball
;   block would hide under a solid cell (CTRLPF priority), and the render
;   and the cell walk share the buffers by design. Reflect mirrors the
;   punched left-half cell to the right half.
; - Stages Temp = mirrored BallX = 159-4x (right edge; >= 87 so the pack's
;   (Temp-87)>>3 decode stays valid) and BandTab[band..band+h-1] = $ff —
;   the D6 ball machinery then renders the block with zero kernel changes.
; ------------------------------------------------------------------------------
VcrShutter:
    tya
    sta CollisionCellX          ; stash record base (Y dies in the punch loop)
    ; --- BandTab[band] = $ff (per-band ENABL gate) ---
    iny
    iny                         ; Y = base+2 (y = start band)
    lda (FetchPtr),Y
    tax                         ; band start (flags still = band test)
    ; --- Phase C arm: middle band + alive → stage the slice run ---
    cmp #1
    bne .VSnoArm                ; band≠1: legacy off-middle bbox → static solid
    ; --- Phase C arm gate: middle band + alive → stage the slice run ---
    lda EnemyDeadMask
    bmi .VSpunch                ; b7 latch (died once): the wall is REMOVED
                                ;   this visit (user spec 2026-10-14) — jump
                                ;   past recolor/arm/BandTab into the punch
                                ;   only: the hole stays open, the ball block
                                ;   never renders, the overlay gate stays
                                ;   disarmed (no re-kill — OvShutBand also
                                ;   treats the latch as passable)
    ; --- Phase D: hazard recolor (ball shares COLUPF with the band) ---
    ; One overwrite of ColupfBuf[1]: middle-band walls + the ball block both
    ; go hazard red ($44 = the power-bar red) — reads as danger, not wall.
    ; Zero kernel cost; BuildColupF rebuilds the green every VBL, so the
    ; color auto-restores on room exit. Covers the shutter's band only
    ; (X = band; a band≠1 legacy bbox renders no ball anyway).
    lda #$44
    sta ColupfBuf,X
    lda EnemyRamP
    lsr
    lsr                         ; sc = clock>>2 (fold same as VcrCoveredState)
    cmp #32
    bcc .VSsc
    eor #$3F                    ; 32..63 -> 31..0
.VSsc:
    tay
    lda VcrStateTab,Y           ; $FE64 — 32B state table (21c vs the old
                                ;   43c jsr form; V-room VBL was one TIM64T
                                ;   tick from the +1-line bucket and
                                ;   bomb-draw frames crossed it)
    sta VcrState
    lsr                         ; C = state bit0 (slice0 closed)
    bcc .VSpunch                ; fully open (user 2026-10-14c): skip the
                                ;   arm + BandTab — prologue defaults stay
                                ;   (VcrBand=$FF, VcrNext=0) and BandTab
                                ;   keeps StageBandTab's MetaA value ($00
                                ;   in shutter rooms): slice0 off, pack
                                ;   gate off, nothing renders/passable
    lda #1
    sta VcrBand                 ; arm the kernel slice dispatch (band 1)
    sta VcrNext                 ; slice0 runs via the kernel-entry .Row (8)
.VSnoArm:
    ; h read + multi-row loop deleted with the row-0 convert rule: bbox h=1
    ; always, so a single BandTab[band] store is the whole gate (punch loop
    ; below still reads h itself).
    lda #$ff
    sta BandTab,X
.VSpunch:
    ; --- punch the bbox open: pair mask + per-band-row AND ---
    ldy CollisionCellX
    iny                         ; Y = base+1 (x, 4px col 0-18)
    lda (FetchPtr),Y
    lsr
    tax                         ; pair 0-9
    lda PhMaskTab,X
    eor #$FF
    sta LineCount               ; ~pair mask (bits to clear)
    lda PFOffTab,X              ; PF reg offset 0/3/6 (was a 7-branch
    sta CollisionEndY           ;   ladder — table in the $FE5A hole)
    ldy CollisionCellX
    iny
    iny                         ; Y = base+2 (band)
    lda (FetchPtr),Y
    sta Temp                    ; row cursor
    ldy CollisionCellX
    iny
    iny
    iny
    iny                         ; Y = base+4 (h)
    lda (FetchPtr),Y
    tax                         ; X = rows remaining (no stack: SP floor)
.VSrow:
    lda CollisionEndY
    clc
    adc Temp
    tay
    lda PF0Buf,Y
    and LineCount
    sta PF0Buf,Y
    inc Temp
    dex
    bne .VSrow
    ; --- Temp = mirrored BallX (right-half always: pack-safe) ---
    ldy CollisionCellX
    iny                         ; Y = base+1 (x)
    lda (FetchPtr),Y
    asl
    asl                         ; 4x
    sta LineCount
    lda #159
    sec
    sbc LineCount
    sta Temp
    ; --- .PhRec contract: Y = base+4 (its iny -> base+5 = next class) ---
    ldy CollisionCellX
    iny
    iny
    iny
    iny
    jmp .PhRec

    ; Tally entry tramp slice ($FFE6-$FFEB, byte-identical with kernel.asm —
; guard: check_moth_tramp). bank0 executes `sta $1FF8`; the fetch at $FFE9
; comes from THIS bank = `jmp TallyEntry`. Neither bank runs its other half.
    .ds $FFE6 - *, 0
TallyTramp:
    sta $1FF8
    jmp TallyEntry

    ; Pad to vectors at $FFFA ($FFF2-$FFF9 = fill — never code: $FFF6-$FFF9
    ; are F6 hotspot mirrors on peek, see MothExitPad at $FC49)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
