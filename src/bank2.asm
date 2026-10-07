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
COLOR_PLAYER = $48               ; must match kernel.asm
RESP0   = $10
RESP1   = $11
RESM0   = $12
RESM1   = $13
GRP0    = $1B
GRP1    = $1C
ENAM0   = $1D
ENAM1   = $1E
ENABL   = $1F
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
EnemyIndex = $B9                 ; slot save around the col swap + rect walk
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
PlayerSpriteA = $f8d5           ; hand copies (bank0 symbols unreadable here);
PlayerSpriteB = $f8e1           ; tools/test_miner_colors.py asserts vs bank0.lst
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
LaserBeamOn = $83               ; cleared at arm (no stale beam)
BombSnd = $F1                   ; coin hold — bank1 UpdateBombSound decs it
AUDC0 = $15                     ; TIA — coin tone regs (any bank may write)
AUDF0 = $17
AUDV0 = $19

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
; S6 LaserWallClamp (docs/laser_s6_log.md — baby step 1) — sweep-path clamp.
; The held laser's kill window must never reach past the FIRST wall on the
; path the swept beam occupies this frame (sweep = 8 px/phase + 8 px missile;
; without the clamp a phase jump puts the whole beam beyond the wall and it
; kills enemies straight through it).
; In (staged by bank0 LaserInput .LaserPos, S6b):
;   CollisionEndX (c0), CollisionCellX (c1) = path cols px>>2
;     right (PlayerDir=0): path px = [nose_R=RoomX-3, A]      (A = raw arg)
;     left  (1):           path px = [A-7, nose_L=RoomX-4]
;   CollisionX = A (unclamped), RoomY live, PF0/1/2Buf live (the map —
;   BombMarkWalls-punched holes read as air for free).
;   PIXEL MODEL: drawn M0 = [A-7, A] (SetObjectXPos arg -> box-left arg-7;
;   PlayerSpriteA lit cols0-6, PHM lit-left = arg-7). Kill test = same
;   [A-7, A] (adc #14 in the body). The raw tip/eye anchoring of S6a missed
;   the wall at max approach (nose col >= wall col) and left a 1-3px visible
;   gap + behind-player stub — all three Stella symptoms (2026-10-01).
; Walks the cell map ONCE (cell_collision_plan 3.1) — rows =
; band(RoomY+2)..band(RoomY+3) (exact LHT kill window), every DISPLAY col
; in [c0..c1] (right-half cols mirror 39-d into the buffers). First solid
; col on the travel direction:
;   right: col -> tip A   <= col*4+2  -> pull DOWN (min)
;   left:  col -> start A >= col*4+9  -> pull UP   (max)
; (col*4 = wall face px; drawn [A-7, A]: right tip lands 2px INSIDE the
; wall's left half, left start lands 2px inside its right half — visible
; tip flush at the face (PF has priority over M0, CTRLPF=$05), never past
; face+3/far side: enemies beyond survive; in/near-wall enemies die.)
; NO NUSIZ/width/BeamMask change (the e24d9de rollback): beam stays 8 px;
; only CollisionX moves. Out: CollisionX clamped (never lengthened past the
; invariant). Clobbers A/X/Y/FetchPtr/RectCount + CollisionCell*/End*.
; Entered/exited via jmp from/to LaserHitTestBody — stack depth unchanged
; (SP guard: gameplay >= $F8; laser chain = 2 jsr from overscan = $FB).
; Lives here (bank2 $F260+): bank0 has 1B pre-pad headroom; org $F9D9 below
; pins level data (Origin Reverse-indexed if this overflows = build fails).
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
    ; --- cell walk (cell_collision_plan 3.1): scan every display col on
    ; the path against the PF render buffers (bomb holes = air for free;
    ; the rect cache + destroyed-mask scan are gone from THIS walker). Candidates are DISPLAY px (kill window is display space);
    ; only the buffer lookup mirrors right-half cols (source = 39-d).
    ; FetchPtr = running display col (no indirect reads here — the LHT
    ; body restages FetchPtr after LaserClampDone), RectCount = running
    ; band row (overscan-only alias of RowIdx, kernel idle).
    lda CollisionEndX          ; c0 (display space, staged by LaserInput)
    sta FetchPtr
    ; --- Phase 4: patch-strip setup+test (out-of-line @ $F600 — the
    ; pre-TallyEntry fill is ~0B; 12B inline overflowed the $F310 pin).
    jmp LWpSetup               ; gap: decode + strip test, tails to the
                               ; globals LWpSolid / LWpNotPatch below
LWpNotPatch:                   ; global: gap test's miss target
    lda FetchPtr
    cmp #20
    bcc .LWsrc                 ; left-half display col = source col
    lda #39
    sec
    sbc FetchPtr               ; right-half: mirrored source col 39-d
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
    bne LWpSolid
    lda RectCount
    cmp CollisionEndY
    beq LWpNext                ; bottom row tested -> col is clear
    inc RectCount
    bne .LWrow                 ; always (RectCount <= 2, never wraps to 0)
LWpSolid:                      ; global: gap test's strip target
    ; first solid display col on the travel path folds into CollisionX:
    ;   right: cand = col*4+2, min-apply (tip lands 2px inside the wall)
    ;   left:  cand = col*4+9, max-apply (start lands 2px inside)
    ; max/min fold = order independent, ascending scan is fine.
    lda PlayerDir
    beq .LWsR
    lda FetchPtr               ; left
    asl
    asl
    clc
    adc #9                     ; cand = face+9 (start A >= face+9, S6b)
    cmp CollisionX
    bcc LWpNext                ; cand < A -> keep (max-apply)
    sta CollisionX
    jmp LWpNext
.LWsR:
    lda FetchPtr               ; right
    asl
    asl
    clc
    adc #2                     ; cand = face+2 (tip A <= face+2, S6b)
    cmp CollisionX
    bcs LWpNext                ; cand >= A -> no pull (min-apply)
    sta CollisionX
LWpNext:                       ; global: loop end (row-loop + clamp targets)
    lda FetchPtr
    cmp CollisionCellX         ; just processed c1?
    beq .LWdone
    inc FetchPtr
    jmp LWpTest
.LWdone:
    jmp LaserClampDone          ; back to the body (stack depth unchanged)

; Cell-map lookup copies (bank2 cannot read bank0 ROM) — cell_collision_plan
; 0.2 bit spec, byte-identical to kernel.asm's ColOff/ColMask: group offset
; 0/3/6 + per-col bit (PF0 LSB-first nibble, PF1 MSB-first, PF2 LSB-first).
ColOff:
    .byte 0,0,0,0, 3,3,3,3,3,3,3,3, 6,6,6,6,6,6,6,6
ColMask:
    .byte $10,$20,$40,$80, $80,$40,$20,$10,$08,$04,$02,$01
    .byte $01,$02,$04,$08, $10,$20,$40,$80

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
; Was $F310 — +3 for the Phase 4 LWC patch-strip walk-head (kernel
; TallyEntry EQU moves with it; both jmp operands are symbolic).
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
    jmp $FBF8
.TEOne:
    lda #1                      ; tick only
    jmp $FBF8
.TEFinal:
    lda #7                      ; tick + coin + done
    jmp $FBF8
.TEIdle:
    lda #0                      ; no event (Z set for bank0 beq)
    jmp $FBF8
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
    sta LaserBeamOn             ; drop any live beam
    lda #$FE
    sta DropTarget
    lda #0
    jmp $FBF8

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
; StageBandTab — Phase 3 asym ball: copy model meta into bank0 ZP for the cave.
; Reached from BuildColupF's tail (BCFDarkRun jmp here); ends at ReturnPad so
; the VBL jsr returns to bank0 (pads must not nest — no rts here).
; WHY here: models_data lives in THIS bank — a bank0 (RoomPF0Lo),Y read
; fetches bank0's $F9xx zero pad (the Phase 2 ball block silently read zeros).
;   BandTab ($ED-$EF) <- TilePF0+11..13 — .Row's per-band ENABL gate.
;   Temp    ($88)     <- TilePF0+10 (BallX) — VBL ball block after .BgStore
;                        (0 ⇔ symmetric → skip; verify_build enforces).
; Window: staged every VBL → read by cave → bank1 HUD stomps $ED-$EF after
; the cave read → overscan rewrites $88 (joystick) after the ball read.
; ------------------------------------------------------------------------------
StageBandTab:
    ldy #10
    lda (RoomPF0Lo),Y
    sta Temp                    ; BallX (doubles as the asym flag)
    ldy #11
    lda (RoomPF0Lo),Y
    sta BandTab
    iny
    lda (RoomPF0Lo),Y
    sta BandTab+1
    iny
    lda (RoomPF0Lo),Y
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
    ; --- D6 M1 (left-col block): TilePF0+14 = M1X -> CollisionEndX ($8E) ---
    ; 0 = no M1 patch. Window: this VBL write -> PositionBallM1 reads it
    ; later the same VBL (staged-file pattern like Temp/BallX). Overscan
    ; routines (PHM/LWC/blast/laser) restage their own CollisionEndX values
    ; AFTER the cave read, so the alias never crosses a frame boundary.
    ; NOT zeroed with BandTab on strip kill — M1 is a whole-cave latch and
    ; convert guarantees its cell is solid/unpatched (wall) where it must hide.
    ; M1 strip DESTROYED (EnemyDeadMask b4, StripBlastCheck's M1 twin) →
    ; stage 0: PositionBallM1 skips ENAM1, the pack's b3 flag clears, and
    ; both overlay paths (PHM/blast) treat the strip as gone next frame.
    ldy #14
    lda (RoomPF0Lo),Y
    sta CollisionEndX
    lda EnemyDeadMask
    and #$10                    ; b4 = M1 strip destroyed (room-scoped)
    beq .M1stage
    lda #0
    sta CollisionEndX
.M1stage:
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
    jmp $FBF8                   ; ReturnPad → bank0 VBLANK caller

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
    ; d - marker in {0,1} = display col pL or pL+1 → solid (clamp folds
    ; exactly like a real 2-col wall); borrow/none land >=2.
    lda FetchPtr
    sec
    sbc CollisionEndX
    cmp #2
    bcc .LWhit
    jmp LWpNotPatch             ; miss → mirror/row walk (LWC, same bank)
.LWhit:
    jmp LWpSolid                ; strip col → clamp fold (LWC, same bank)

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
    ldy #14
    lda (RoomPF0Lo),Y           ; M1X = 7+8ℓ (0 = no M1 patch)
    beq .OvM1no
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
    jmp HotOverlapFlag          ; C=1 contract; body sets Temp b7 on hot hit
.OvM1no:
    clc
    jmp $FBF8

FooterPtr1 = $E0                 ; title-only pointer block; overwritten by HUD
FooterPtr2 = $E2
FooterPtr3 = $E4
FooterPtr4 = $E6
FooterPtr5 = $E8
FooterPtr6 = $EA

    .ds $F700 - *, 0
FooterBand:
    sta WSYNC
    lda #>FooterFont
    sta FooterPtr1+1
    sta FooterPtr2+1
    sta FooterPtr3+1
    sta FooterPtr4+1
    sta FooterPtr5+1
    sta FooterPtr6+1
    lda #<FooterFont
    sta FooterPtr1
    lda #<FooterFont+8
    sta FooterPtr2
    lda #<FooterFont+16
    sta FooterPtr3
    lda #<FooterFont+24
    sta FooterPtr4
    lda #<FooterFont+32
    sta FooterPtr5
    lda #<FooterFont+40
    sta FooterPtr6
    ldx #7
    stx LineCount
.FooterLoop:
    ldy LineCount
    lda (FooterPtr6),Y
    tax
    sta WSYNC
    lda (FooterPtr1),Y
    sta.w GRP0
    lda (FooterPtr2),Y
    sta GRP1
    lda (FooterPtr3),Y
    sta GRP0
    lda (FooterPtr4),Y
    sta Temp
    lda (FooterPtr5),Y
    ldy Temp
    sty GRP1
    sta GRP0
    stx GRP1
    stx GRP0
    dec LineCount
    bne .FooterLoop
    sta WSYNC
    lda #0
    sta VDELP0
    sta VDELP1
    sta GRP0
    sta GRP1
    sta GRP0
    sta GRP1
    jmp $FBF8

    .ds $F800 - *, 0
FooterFont:
    ; Six 8-pixel slices, top-to-bottom rows are bytes 6..2.
    ; The 4x5 glyphs spell "2026 Iuri".
    .byte $00, $00, $3C, $11, $09, $05, $38, $00
    .byte $00, $00, $CF, $24, $22, $21, $CE, $00
    .byte $00, $00, $30, $48, $70, $40, $30, $00
    .byte $00, $00, $1E, $0C, $0C, $0C, $1E, $00
    .byte $00, $00, $54, $B4, $94, $96, $95, $00
    .byte $00, $00, $38, $10, $30, $00, $10, $00

    .ds $F880 - *, 0
    .ds $F970 - *, 0

    .ds $F970 - *, 0            ; pinned: bank1 .BMWDone jmp operand ($F970)
M1StripBlast:
    ; Phase 4 M1 strip blast — entered from bank1 BombMarkWalls .BMWDone
    ; via the $F9AC shared pad (`sta $1FF8 / jmp $F970`; 0 pushes). Bank2-
    ; only: the M1X meta (TilePF0+14) lives in THIS bank's ROM. Window in:
    ; CollisionEndX/CellX = blast lo/hi in LEFT-half display cols (0..19) —
    ; the strip's dcols [2ℓ, 2ℓ+1] are in the same frame, no mirror.
    ; RectCount = ORIGINAL screen col from the BMW prologue: >=20 = right-
    ; side bomb, whose real blast is entirely in the right half (the window
    ; is its mirror image) — a left-frame overlap test would false-hit, so
    ; skip. Window is READ-ONLY (StripBlastCheck still needs it for the
    ; right strip). Out: crosses back via the $F9B2 pad half.
    lda RectCount               ; original screen col (BMW prologue stash)
    cmp #20
    bcs .M1SBout                ; right-side bomb → never touches the left
    lda EnemyDeadMask
    and #$10                    ; b4 already set → no double score
    bne .M1SBout
    ldy #14
    lda (RoomPF0Lo),Y           ; M1X (0 = no M1 patch)
    beq .M1SBout
    sec
    sbc #7
    lsr
    lsr                         ; (M1X-7)/4 = 2ℓ = strip left dcol
    sta CollisionCellY          ; $8D free during BombMarkWalls
    lda CollisionCellX          ; blast hi
    cmp CollisionCellY
    bcc .M1SBout                ; hi < 2ℓ → strip right of the blast
    lda CollisionEndX           ; blast lo
    cmp CollisionCellY
    bcc .M1SBtake               ; lo < 2ℓ (and hi >= 2ℓ) → overlap
    sec
    sbc CollisionCellY
    cmp #2
    bcs .M1SBout                ; lo >= 2ℓ+2 → blast ends left of strip
.M1SBtake:
    lda EnemyDeadMask
    ora #$10
    sta EnemyDeadMask           ; b4 = M1 strip destroyed (room-scoped)
    inc CollisionX              ; +1 wall for the caller's score loop
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

    org $F9D9
    include "generated/levels_data.asm"
    include "generated/levels.asm"

; ------------------------------------------------------------------------------
; ReturnPad ($FBF8) — byte-identical to kernel.asm's copy (sta $1FF6 / rts).
; S5.1 pad bodies (BuildColupF) tail-jmp here: sta switches this bank to
; bank0, the rts is then fetched from bank0's identical copy, and the stack
; still holds the bank0 jsr CallPad_* return address.
; ------------------------------------------------------------------------------
    .ds $FBE0 - *, 0
    sta $1FF8
    jmp FooterBand
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
    ; Moved to BCFDarkRun (pre-level-data gap): the $FCF0 pin left <8 B
    ; here once the dark mask grew to rooms 4-7. Still inlined in THIS
    ; bank — pads cannot nest (ReturnPad switches to bank0).
    jmp BCFDarkRun

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
    ; Parent gate: mask $00 = M1 block rect → dies with the STRIP
    ; (EnemyDeadMask b4), never with a wall (walk hits the floor cell
    ; under the block reach this body even after the strip is gone).
    ; Any other mask = wall piece → dies when that piece is blasted.
    lda (FetchPtr),Y            ; hot parent mask
    bne .HOVwallGate
    lda EnemyDeadMask
    and #$10                    ; b4: strip destroyed → M1 rect dead
    bne .HOVnext                ; (.HOVnext pops the loop's pushed Y)
    beq .HOVafterGate           ; strip alive → continue (result was 0)
.HOVwallGate:
    and BombPacked
    bne .HOVnext
.HOVafterGate:
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
    .ds $FDE1 - *, 0            ; PickPlayerFrame tramp mirror (byte-identical
                                 ; with kernel.asm's copy — verify_frame_tramp)
PickPlayerFrameTramp:
    sta $1FF8                   ; executed only as the post-switch fetch image
    jmp $F3C4                   ; bank2 PickPlayerFrame body (this bank)

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
                                 ; IT returns via ReturnPad (C set/clear)
.OvBand:
    ldx CollisionCellY
    lda OvHead,X                ; bits >= row
    ldx CollisionEndY
    and OvTail,X                ; bits <= row
    and LineCount               ; active-band mask (b0-2)
    beq .OvClear                ; patch not painted in any player row
    sec
    jmp $FBF8
OvHead:
    .byte 7,6,4                 ; rows 0..2 → mask bits >= row
OvTail:
    .byte 1,3,7                 ; rows 0..2 → mask bits <= row

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
; (held path only). Interval = [cur, cur+7] (8 px missile); sweep steps are
; 8 px = missile width, so consecutive frames tile gap-free — no prev-frame
; storage needed. Vertical: beam rows [RoomY+2, RoomY+3] vs enemy [Y,+7] ->
; (RoomY-Y)+3 in [0..8]. Horizontal (same convention as CheckEnemyHit):
; |eLo-lo| <= 7 via (d+7) in [0..14]; arg clamped [0,159] = screen-edge clip.
; Fold-free: enemy records are level data in THIS bank — stage once, direct
; `lda (FetchPtr),Y` for the type (was `jsr FoldIndirect`).
; RESULT PROTOCOL (pads cannot nest from a pad body — the kill/lamp actions
; stay in bank0's LaserInput): every exit returns A + Z through ReturnPad
; (sta/rts preserve both): A=0 miss / #$50 kill (dead bit set here, caller
; scores) / A=1 lamp (caller does CallPad_SetRoomDark — same as player-body
; touch; no kill, no score). First live enemy in span only (next frame the
; dead mask skips it — no resurrection, no double score).
; Does NOT touch Temp (joystick still live at the call site).
; S6 (docs/laser_s6_log.md): the body first tail-jmps to LaserWallClamp,
; which walks the rect cache against the path cols LaserInput staged
; (CollisionEndX..CollisionCellX) and pulls CollisionX back to the first
; wall on the travel path — so this kill window can never reach the far
; side of that wall. LWC ends `jmp LaserClampDone` (back here): stack
; depth unchanged. Clobbers A/X/Y/FetchPtr + CollisionCellX/Y,
; CollisionEndX/Y, RectCount; MODIFIES CollisionX (the clamp).
; ------------------------------------------------------------------------------
    .ds $FF00 - *, 0            ; pinned: bank0 tramp operand is literal $FF00
LaserHitTestBody:
    jmp LaserWallClamp          ; S6: clamp CollisionX at the first wall on
                                ; the swept path BEFORE any kill test
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
