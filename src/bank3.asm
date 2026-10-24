    processor 6502
    seg code
    org $F000
; ==============================================================================
; Bank3 — level-data SHAPES + the walkers that read them (C7 2026-10-20)
; ==============================================================================
; The level-data subsystem is SPLIT (docs/level_format_plan_2026-10-20.md §7):
;
;   bank2  level entries (LevelDataTable) + room tables (shapes/positions/
;          counts) + enemy records + the EXTRAS ORDINAL — and every walker
;          that reads THOSE (EnterRoomB2, exits, LoadLevelB2, moth, LWC/LHT,
;          bomb blast). Their data is only ever read in-bank.
;   bank3  shape blocks + row pool + LEVEL_ShapeTable + the async EXTRAS
;          streams + this file's walkers (B3RoomBlocks/ExtrasLoad,
;          PhaseBlink/PhRec/BuildColupF/BCFDarkRun, HotOverlapBody,
;          B3StageBand, PhHcrEntry/CrPfx/HcrClock, HOVFeatEntry).
;
; Why the extras move too: a feature room's hot stream lives INSIDE its
; extras record and is walked every VBL by PhaseBlink/BuildColupF/
; HotOverlapBody — a direct `lda (FetchPtr),Y` in the caller's bank (a fold
; would cost 25c on the VBL path). Record walkers and record data must share
; a bank, so the extras stream belongs with the shapes.
;
; Cross-bank contract (the ONLY one this file has):
;   bank2 EnterRoomB2 stages the ROM shapes byte in RoomPF0Lo ($99, loader
;   scratch) and, for an owns-extras room, the 1-based ordinal in
;   LevelConnSpare ($A2), then executes `sta $1FF7` at $F450. The opcode
;   fetch at $F453 already comes from THIS bank, so B3RoomBlocks MUST start
;   at $F453 (`check_bank3_entry` pins it). Every exit is `jmp ReturnPad`
;   ($FBF8 in this bank: `sta $1FF4`, rts fetched from bank0) — no return
;   pad, no twin, 0 extra stack pushes.
;
; `Level` ($A3) indexes this bank's per-level extras base table
; (LevExtrasLo/Hi, generated), so no counts-column arithmetic happens here.
; ==============================================================================

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
BandTab = $CF                   ; N=4 band gate bytes ($CF-$D2) — staged here,
                                 ; read by kernel .Row in bank0
PF1Buf = $C7                    ; N=4 stride-4 PF row buffers (kernel twins)
PF2Buf = $CB
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
TILE_ROWS = 4                     ; playable color bands (rows 0-3 of ColupfBuf)
RoomRectsLo = $90                 ; FEATURE-record stream ptr (C11): the room's
                                  ;   extras record stream, or RoomNoStream
                                  ;   ($00 count) when it has none
RoomRectsHi = $91
RoomM1Hot   = $AF                 ; C11: hot-band M1 block cell = col+1
                                  ;   (0 = none), staged by ExtrasLoad from the
                                  ;   patch list — kernel decl LevelEnemySpare
RoomNo      = $98
LevelWallColor = $AA              ; stripe rows 0+2
LevelWallColor2 = $AB              ; stripe row 1
TickCounter = $AD                 ; 60-frame game timer — hot-pulse phase bit 4
ColupfBuf   = $D3                 ; 4-byte COLUPF image (N=4, rows 0-3)
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

    ; --- 5-byte stub: select bank0, then the fetch at $F005 is bank0's ---
    lda #0
    sta $1FF4                       ; select bank0

; ------------------------------------------------------------------------------
; DATA WINDOW 1 — $F010-$F44F (1 088 B): the per-level async EXTRAS streams +
; their base table (levels_extras.asm), emitted by tools/convert_level.py and
; listed in generated/spill_bank3.asm; capacity-checked there
; (`_BANK3_EXTRAS_SLOT`). Nothing else may live here.
; ------------------------------------------------------------------------------
    .ds $F010 - *, 0
    include "generated/spill_bank3.asm"
    .ds $F453 - *, 0                ; bank2's $F450 `sta $1FF7` fetch target
; ==============================================================================
; B3RoomBlocks — shape → PF0Buf + staged meta/extras (C7: bank2 tail-jumps
; here; ends `jmp ReturnPad`).
;
; Shape block (C11 2026-10-21) = EXACTLY 3 row-pool indices (band 0/1/2).
; Band 1's index byte carries b7 = mid_band_type (hot): hot cells only ever
; exist on model row 1, so the flag rides that band and the block needs no
; flags byte. MetaA/MetaB are NOT in the block: an owns-extras room reads its
; pair (+patches+features) from the level's async extras stream; every other
; room derives MetaA = 0 and MetaB = $40 iff the shape is hot.
; ==============================================================================
B3RoomBlocks:
    ; C7: the shape ADDRESS comes from THIS bank's LEVEL_ShapeTable, so bank2
    ; needs no bank3 label and no symbol export. RoomPF0Lo = the raw shapes
    ; byte staged by EnterRoomB2 (idx b5-0 | band b6 | owns-extras b7).
    lda RoomPF0Lo
    and #$3F                        ; shape index (C2 2026-10-20)
    asl                             ; *2: LEVEL_ShapeTable is a word table
    tax
    lda LEVEL_ShapeTable,X          ; block address = the table entry
    sta FetchPtr
    lda LEVEL_ShapeTable+1,X
    sta FetchPtr+1
    ; C11: no stream by default — a room only gets one from its extras record
    ; (feature records). RoomMetaB/RoomM1Hot are staged below or by ExtrasLoad.
    ; RoomRects points at a static $00 count byte so the walkers (overscan
    ; HotOverlapBody / VBL PhaseBlink) read "empty stream", never TIA.
    lda #0
    sta RoomM1Hot
    lda #<RoomNoStream
    sta RoomRectsLo
    lda #>RoomNoStream
    sta RoomRectsHi

    ; --- C3/C13 PF rebuild: 4 row-pool indices -> PF buffers (N=4, stride 4) ---
    ;     Y = band (3..0) for BOTH the index read and the three PF stores;
    ;     X = pool row. SoA columns, so one index register serves all three.
    ;     C11: mask b7 (band 1's hot flag) before the pool lookup.
    ldy #TILE_ROWS-1
.EBpf:
    lda (FetchPtr),Y                ; row index for this band
    and #$7F
    tax
    lda RowPoolPF0,X
    sta PF0Buf,Y
    lda RowPoolPF1,X
    sta PF1Buf,Y
    lda RowPoolPF2,X
    sta PF2Buf,Y
    dey
    bpl .EBpf

    ; --- C5 meta source: owns-extras (shape byte b7) → the extras stream;
    ;     otherwise MetaA = 0 and MetaB = $40 iff the shape is hot (C11: the
    ;     flag is band 1's index b7).
    lda RoomPF0Lo
    bmi .EBextras
    lda #0
    sta RoomMetaA
    ldy #1
    lda (FetchPtr),Y                ; band-1 index | hot b7
    and #$80
    lsr                             ; $80 -> $40 (MetaB b6)
    sta RoomMetaB
    jmp ERLoadDone
.EBextras:
    jmp ExtrasLoad

; --- C5/C7: async extras loader (record layout: tools/convert_level.py) ---
; The stream lives in THIS bank, so the room's record is reached from the
; generated per-level base (LevExtrasLo/Hi) + the ordinal bank2 staged in
; LevelConnSpare. No counts-column sum here (that column is bank2 data).
ExtrasLoad:
    lda LevelConnSpare
    beq .EXLload                    ; 0 = no record (defensive)
    sec
    sbc #1
    sta Temp                        ; records still to skip
    ldx Level
    lda LevExtrasLo,X
    sta FetchPtr
    lda LevExtrasHi,X
    sta FetchPtr+1
.EXLskip:
    lda Temp
    beq .EXLload
    dec Temp
    ldy #0
    lda (FetchPtr),Y                ; flags
    and #$03
    clc
    adc #3
    sta LevelConnSpare              ; 3 + n_patches
    lda (FetchPtr),Y
    lsr
    lsr
    and #$0F                        ; n_features
    beq .EXLskipFlat
    clc
    adc LevelConnSpare
    tay                             ; Y = 3 + np + nf = hot-count offset
    lda (FetchPtr),Y                ; hot record count
    iny                             ; Y = offset past the count byte
    sta LevelConnSpare              ; H
    tya
    clc
    adc FetchPtr
    sta FetchPtr
    bcc .EXLskipHot
    inc FetchPtr+1
.EXLskipHot:
    lda LevelConnSpare
    asl
    asl
    clc
    adc LevelConnSpare              ; 5H
    clc
    adc FetchPtr
    sta FetchPtr
    bcc .EXLskip
    inc FetchPtr+1
    jmp .EXLskip
.EXLskipFlat:
    lda LevelConnSpare              ; 3 + np
    clc
    adc FetchPtr
    sta FetchPtr
    bcc .EXLskip
    inc FetchPtr+1
    jmp .EXLskip


.EXLload:
    ; FetchPtr = this room's extras record
    ldy #0
    lda (FetchPtr),Y                ; flags
    sta LevelConnSpare
    iny
    lda (FetchPtr),Y                ; MetaA
    sta RoomMetaA
    iny
    lda (FetchPtr),Y                ; MetaB
    sta RoomMetaB
    ; --- apply the patch list: MetaA b0-2 = bands with a SIDE-0 (ball)
    ;     patch. Side-1 (M1) patches paint via the strip and gate no band. ---
    lda #0
    sta Temp
    lda LevelConnSpare
    and #$03
    beq .EXLfeat
    tax                             ; n_patches
    ldy #3
.EXLpatch:
    lda (FetchPtr),Y
    and #$10                        ; side b4: nonzero = M1 side
    bne .EXLm1
    lda (FetchPtr),Y
    and #$C0                        ; row b7-6
    beq .EXLrowB0
    cmp #$40
    beq .EXLrowB1
    lda #%00000100                  ; row 2
    jmp .EXLrowOr
.EXLrowB1:
    lda #%00000010                  ; row 1
    jmp .EXLrowOr
.EXLrowB0:
    lda #%00000001                  ; row 0
.EXLrowOr:
    ora Temp
    sta Temp
    jmp .EXLpatchNext
.EXLm1:
    ; C11 (2026-10-21): an M1 patch on the HOT band is a PF-OPEN cell (the
    ; strip paints there, the wall-hide envelope keeps the cell open), so the
    ; overscan PF sweep cannot see it. Stage its cell (col+1, 0 = none) from
    ; the patch list — this replaced the extras' mask-$00 hot record. A cold
    ; room's M1 patch was never a death cell, so the b6 gate is the contract.
    lda RoomMetaB
    and #$40                        ; hot shape?
    beq .EXLpatchNext
    lda (FetchPtr),Y
    and #$C0
    cmp #$40                        ; row 1 only (the hot band)
    bne .EXLpatchNext
    lda (FetchPtr),Y
    and #$0F                        ; col b3-0 (0-9, left cell)
    clc
    adc #1                          ; store col+1 so 0 means "absent"
    sta RoomM1Hot
.EXLpatchNext:
    iny
    dex
    bne .EXLpatch
    lda RoomMetaA
    ora Temp                        ; keep the authored gates, add the
    sta RoomMetaA                   ;   side-0 patch rows (the converter
                                    ;   asserts they agree, so this is
                                    ;   idempotent for real stage data)
.EXLfeat:
    ; --- feature cells: the PF pairs the retired per-room block carried.
    ;     A hcrunch entry ($80 kind) covers cols 0..col (contiguous prefix);
    ;     a phase entry ($40 kind) is one cell. Row is always band 1. ---
    ldy #0
    lda (FetchPtr),Y
    lsr
    lsr
    and #$0F
    sta EnemyIndex                  ; features remaining (scratch: the enemy
                                    ; RECORD POINTER EnemyDataLo is live —
                                    ; C7 moved the shape step AFTER LoadEnemyRam)
    beq .EXLdone                    ; patch-only: the shape's hot stream stays
    lda (FetchPtr),Y
    and #$03
    clc
    adc #3
    tay                             ; Y = first feature byte
.EXLfeatLoop:
    lda (FetchPtr),Y
    sta LevelConnSpare              ; kind b7-6 | col b3-0
    and #$3F
    sta Temp                        ; current col
.EXLfeatCol:
    ldx Temp
    lda PhMaskTab,X                 ; PF bit pair for cell `col`
    sta RectCount                   ; mask (hot flag already consumed)
    lda #0
    cpx #2
    bcc .EXLfOff
    lda #4
    cpx #6
    bcc .EXLfOff
    lda #8
.EXLfOff:
    clc
    adc #1                          ; row 1 in the 4-row (stride-4) buffer
    tax
    lda PF0Buf,X
    ora RectCount
    sta PF0Buf,X
    lda LevelConnSpare
    bpl .EXLfNext                   ; b7 clear = phase (one cell)
    dec Temp
    bpl .EXLfeatCol                 ; hcrunch prefix 0..col
.EXLfNext:
    iny
    dec EnemyIndex
    bne .EXLfeatLoop
    ; --- hot stream = this room's copy, right after the feature bytes.
    ;     The feature loop left Y at 3 + n_patches + n_features. ---
    tya
    clc
    adc FetchPtr
    sta RoomRectsLo
    lda FetchPtr+1
    adc #0
    sta RoomRectsHi
.EXLdone:
    jmp ERLoadDone

; ------------------------------------------------------------------------------
; ERLoadDone — the room load's LAST act before returning to bank0. C7 moved
; the shape/PF/meta step to the END of EnterRoomB2, and these walkers use
; Temp as scratch — but bank0's overscan input block keeps reading the
; shifted joystick bits out of Temp for the rest of the frame. Leaving a
; scratch value there fakes a held direction on every transition (the user's
; "eye snaps right + 1 px twitch" report, 2026-10-20); SWCHA is stable inside
; a frame, so this reproduces what the input block staged.
; ------------------------------------------------------------------------------
ERLoadDone:
    lda SWCHA
    lsr
    lsr
    lsr
    lsr
    sta Temp
    jmp ReturnPad

; ------------------------------------------------------------------------------
; DATA WINDOW 2 — $F5CC-$F8B6 (747 B): the shape blocks + row pool + shape
; address table (models_data.asm), listed in generated/spill_bank3_shapes.asm.
; C12 (2026-10-21): split off the $F010 window so the shape library is not
; capped by it. B3RoomBlocks (in-bank) is the only reader, so no new tramp.
; ------------------------------------------------------------------------------
    .ds $F5CC - *, 0
    include "generated/spill_bank3_shapes.asm"


; ------------------------------------------------------------------------------
; HotOverlapBody — bank0's HotOverlapFlag pad (`sta $1FF7` at $FFEC -> the
; `jmp` image at $FFEF) enters here; it walks THIS bank's hot stream with a
; plain (FetchPtr),Y read. Exits through ReturnPad with C=1.
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; C2 (2026-10-20): $F8B7 window — the level-data block reader and the
; HotOverlapBody walk. Both read THIS bank, so `lda (FetchPtr),Y` is a plain
; in-bank read — no tramp, no switch, no fold. Entered from ERBlocksPad /
; bank0's HotOverlapFlag pad ($FFEC -> bank2 $FFEF image) and exited through
; ReturnPad.
; ------------------------------------------------------------------------------
    .ds $F8B7 - *, 0

; C11 (2026-10-21): the "no record stream" sentinel. RoomRectsLo/Hi point here
; whenever the room owns no FEATURE records (B3RoomBlocks stages it; only an
; extras record with feature cells repoints the pair), so the overscan walk
; and the VBL PhaseBlink walk read a $00 count instead of a TIA address.
RoomNoStream:
    .byte $00

; C5 (2026-10-20): B3RoomBlocks MOVED to the free $F453 window (it grew by
; the async-extras dispatch). The window start stays reserved and
; HotOverlapBody keeps its $F8F8 address, so nothing downstream shifts.
    .ds $F8F8 - *, 0

HotOverlapBody:
    ; ==========================================================================
    ; C11 (2026-10-21): HOT DEATH IS DERIVED FROM THE PF BUFFERS.
    ; convert promotes EVERY row-1 wall cell of a mid_band_type=1 model, so a
    ; hot shape's hot cells ARE its solid row-1 PF cells; the C4 bomb punch
    ; clears PF0Buf cells, so a blasted (thin) parent cell stops being hot with
    ; no record stream and no parent gate. Hot cells never exist on rows 0/2.
    ; The per-shape 5 B/record stream is gone (LEVEL_FORMAT 6); MetaB b6 —
    ; staged at room load — gates the sweep so only hot rooms pay for it.
    ; ==========================================================================
    lda RoomMetaB
    and #$40                    ; b6 = mid_band_type hot
    beq .HOVstream              ; cold room: feature records only
    ; Hot cells only live on model row 1 → the box must include it.
    lda CollisionCellY          ; top row
    cmp #2
    bcs .HOVstream              ; top row 2 → box is below the hot band
    lda CollisionEndY           ; bottom row
    beq .HOVstream              ; bottom row 0 → box is above the hot band
    ; Sweep the box's display columns over PF row 1 — the SAME cell store the
    ; player walk reads (PF0Buf + row + ColOff[X], bit ColMask[X]). Reached
    ; only from a cell-walk hit, so this is "the wall I bumped is hot".
    ldx CollisionEndX           ; min col
.HOVpfCol:
    lda ColOff,X                ; PF0/PF1/PF2 group offset (0/3/6)
    clc
    adc #1                      ; +1 = row 1 in the 3-row buffer
    tay
    lda PF0Buf,Y
    and ColMask,X               ; bit for this source col
    bne .HOVkill                ; solid row-1 cell in a hot room → death
    cpx CollisionCellX          ; col == max?
    beq .HOVm1
    inx
    bne .HOVpfCol
.HOVm1:
    ; M1 block cell on the hot band: PF-OPEN by envelope (the strip paints
    ; there), so the sweep above cannot see it. ExtrasLoad staged its cell
    ; (col+1) from the room's patch list; it dies with the STRIP (b4).
    lda RoomM1Hot
    beq .HOVstream
    lda EnemyDeadMask
    and #$10                    ; b4: strip destroyed → cell transparent
    bne .HOVstream
    lda RoomM1Hot
    asl                         ; A = 2*(col+1) = the cell's display right edge
    cmp CollisionEndX           ; right edge > box min col?
    beq .HOVstream
    bcc .HOVstream
    sec
    sbc #2                      ; A = 2*col = the cell's display left edge
    cmp CollisionCellX          ; left edge <= box max col?
    beq .HOVkill
    bcc .HOVkill
    bne .HOVstream
.HOVkill:
    lda Temp
    ora #%10000000
    sta Temp
    sec                         ; tail-call contract: return C=1
    jmp ReturnPad               ; ReturnPad → original caller (C survives)

    ; --- feature-record stream (extras, feature rooms only) -----------------
.HOVstream:
    lda RoomRectsLo
    sta FetchPtr
    lda RoomRectsHi
    sta FetchPtr+1
    ldy #0
    lda (FetchPtr),Y            ; record count (0 = no stream)
    beq .HOVdone
    sta RectCount
    iny                         ; first record base
.HOVloop:
    tya
    pha
    ; C11: only FEATURE records ($80 phase / $82 hcrunch / $81 inert) are
    ; emitted into the extras stream now — static hot and the M1 block cell are
    ; derived above. A b7-clear class is stale: skip it.
    lda (FetchPtr),Y            ; record class
    bpl HOVnext
    jmp .HOVfeature
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
    ; Hot hit — only the phase record reaches the overlap box (C11: no legacy
    ; rects), so latch the phase-removed flag and fall into the kill tail.
.HOVphaseLatch:
    lda EnemyDeadMask
    ora #$40                    ; b6: phase dead — walls removed from now on
    sta EnemyDeadMask           ;   (PhaseBlink forces punch-OFF, kill gated)
HOVlegHit:
    pla                         ; pop the loop's pushed Y
    jmp .HOVkill                ; shared kill tail (sets Temp b7, C=1)
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
    lda (FetchPtr),Y        ; hot count (C4: no solid rect list)
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
    ; buffer offset: pair<2 → PF0 (0), <6 → PF1 (4), else PF2 (8) — N=4
    ; stride 4, so PF1Buf($C7)/PF2Buf($CB) rows sit at +4/+8 from PF0Buf.
    lda #0
    cpx #2
    bcc .PhOffA
    lda #4
    cpx #6
    bcc .PhOffA
    lda #8
.PhOffA:
    sta LineCount           ; offset scratch
    iny                     ; Y → row (band 0-3)
    lda (FetchPtr),Y
    clc
    adc LineCount           ; A = buffer offset + row (0-11 → $C3+A)
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
    ; --- stripe colors (N=4 bands, written once) — alternate c1,c2,c1,c2 --
    lda LevelWallColor
    sta ColupfBuf+0
    sta ColupfBuf+2
    lda LevelWallColor2
    sta ColupfBuf+1
    sta ColupfBuf+3
    ; --- hot middle band: ONE row, ONE color ----------------------------
    ; C10 (2026-10-21): hot cells only ever exist on model row 1 (convert
    ; promotes EVERY row-1 wall to H when mid_band_type=1), so the old
    ; per-frame walk of the hot rect stream just re-derived "row 1 is hot".
    ; MetaB b6 IS that flag — reading it removes ~200c of VBL work per frame
    ; in hot rooms, which is what pushed the VBL past its line boundary and
    ; made the whole screen flicker (level 3/4 hot rooms, 268-line frames).
    lda RoomMetaB
    and #$40                    ; b6 = mid_band_type hot
    beq .BCFdone
    lda TickCounter
    and #$10
    beq .BCFpulseY
    lda #COLOR_HOT_R
    bne .BCFhotStore
.BCFpulseY:
    lda #COLOR_HOT_Y
.BCFhotStore:
    sta Temp                    ; keep the pulse-color contract
    sta ColupfBuf+1
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
    sta $1FF7                   ; chunk A2: StageBandTab lives in bank3
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
    sta PF1Buf+1            ; band 1 (hcrunch) — stride-4 label form
    lda CrPfx2,Y
    sta PF2Buf+1
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

; ------------------------------------------------------------------------------
; ReturnPad ($FBF8) — C7: bank3's copy. Every body here tail-jmps `$FBF8`;
; the `sta $1FF4` switches to bank0 and the `rts` at $FBFB is fetched from
; bank0 (bank0's copy must keep `sta $1FF4 / rts`).
; ------------------------------------------------------------------------------
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF4
    rts

; ------------------------------------------------------------------------------
; Entry images: bank0's pads switch to bank3 at the `sta`, so the fetch at +3
; runs HERE. (Same addresses as before the C2 move, so bank0's literals and
; the guard tables keep their meaning.)
; ------------------------------------------------------------------------------
    .ds $FC1A - *, 0                ; CallPad_BuildColupF's +3 ($FC17 sta $1FF7)
    jmp BuildColupF


; ------------------------------------------------------------------------------
; B3StageBand + M1OffTab — reached from BCFDarkRun (`jmp B3StageBand`); ends
; `jmp ReturnPad`. ZP/TIA only.
; ------------------------------------------------------------------------------

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
    ; --- N=4 bridge (phase 1: 3-row data) ---------------------------------
    ; The kernel draws 4 bands, B3RoomBlocks mirrors PF row 2 into row 3, so
    ; the async gate must mirror too or a bottom-band strip vanishes. Phase 2
    ; (LEVEL_FORMAT 7) gives band 3 its own MetaB bit and this goes away.
    lda BandTab+2
    sta BandTab+3
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

; ------------------------------------------------------------------------------
; ColOff/ColMask — cell-walk lookup tables (bank0 has the authoritative copy;
; this bank needs its own for the C11 hot PF sweep in HotOverlapBody).
; Same bytes as kernel.asm (guard: check_bank3_coloff).
; C11 (2026-10-21): HOVHotPfGate is GONE — hot death reads the PF cell the
; player bumped (sweep) instead of gating a per-shape wall record, so the
; $FE9C window is fill again.
; ------------------------------------------------------------------------------
    .ds $FEC0 - *, 0
ColOff:     .byte 0,0,0,0, 3,3,3,3,3,3,3,3, 6,6,6,6,6,6,6,6
ColMask:    .byte $10,$20,$40,$80,$80,$40,$20,$10,$08,$04,$02,$01
            .byte $01,$02,$04,$08,$10,$20,$40,$80


; ------------------------------------------------------------------------------
; HOVFeatEntry — the $80 phase / $82 hcrunch dispatch for .HOVfeature;
; fields read from FetchPtr in-bank. Returns to HOVnext / HOVlegHit (both pop
; the .HOVloop base) or HOVafterGate.
; ------------------------------------------------------------------------------

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

    .ds $FFEF - *, 0                ; HotOverlapFlag image — bank0 runs
    jmp HotOverlapBody              ;   `sta $1FF7` at $FFEC, the jmp at +3
                                    ;   is fetched HERE
    .ds $FFF2 - *, 0                ; $FFF2-$FFF9 stay fill (F6 hotspot mirrors)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector ← power-up entry
    .word $F000                     ; IRQ vector

