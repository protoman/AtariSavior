    processor 6502
; ==============================================================================
; Bank3 — power-up stub + Phase-4 crunch body (hcrunch)
; ==============================================================================
; Power-up bank (F6: selected at reset). The 5-byte stub switches to bank0
; and the rest of the 4K was free until Phase 4 (2026-10-13) — bank0 has 1B
; of pre-pad headroom and bank2's gaps are ~130B max, so the crunch PF
; staging + kill bodies (~500B) live HERE, reached by sta $1FF9 tramp pads
; and returned from via sta $1FF8 tails at the $FCC1 pad slots (bank2
; mirrors the jmp images — F6 pad rule; see bank2.asm "Phase 4 bank3
; return pads").
;
; Cross-bank contract (M1ToBank* pattern, 0 pushes — pads never nest):
;   caller tramp @ T: sta $1FF9          ; switch to bank3
;                     jmp $Fxxx          ; operand FETCHED bank3-side
;   bank3 @ T+3:      jmp Body           ; byte-identical image required
;   body tail:        sta $1FF6/$1FF8    ; switch back (ReturnPad or pad)
;
; LIVE entry images (the `jmp` fetched after the caller's `sta $1FF9`):
;   $F453  B3RoomBlocks      (bank2 ERBlocksPad, EnterRoom's data half)
;   $FC3B  BuildColupF       (kernel/bank1 CallPad_BuildColupF)
;   $FFEF  HotOverlapBody    (kernel AND bank2 `HotOverlapFlag` at $FFEC)
; Live return tails: B3RoomBlocks `sta $1FF8` at $F458 -> bank2 $F45B;
; everything else exits via bank3 ReturnPad ($FBF8 -> `sta $1FF6` + bank0 rts).
;
; A3/C2 retired the pre-read twins and the $FCC1-$FCD9 return pads: PhaseBlink,
; BuildColupF, HotOverlapBody and the $82 dispatcher all live HERE now, so
; those paths are local jmps (no pad, no switch, no stack shuttle).
;
; ZP EQUs hand-copied from kernel.asm/bank2.asm (check_equ_sync does not
; scan bank3 — keep these correct by hand).
; ==============================================================================
    seg code
    org $F000

    ; --- 5-byte stub (unchanged) ---
    lda #0
    sta $1FF6                       ; select bank0
    jmp $F005                       ; GameStart in bank0 (bank0-side fetch)

; --- hand-copy EQUs (must match kernel.asm / bank2.asm) ---
FetchPtr = $E5
LineCount = $84
Temp = $88
RoomY = $81                    ; player Y — hcrunch kill endpoints
CollisionX = $8B
CollisionCellX = $8C             ; max text column (player box)
CollisionEndX = $8E              ; min text column (player box)
CollisionCellY = $8D             ; top tile row (player box) — NOT scratch
                                 ; here (bank2 stages the door color in it)
CollisionEndY = $8F              ; bottom tile row (player box) / mask scratch
RectCount = $92                  ; PHMOverlay scratch: BallX (right strip)
EnemyDeadMask = $BA              ; b5 phase armed, b6 phase removed,
                                 ; b7 crunch-kill latch (EnterRoom zeroes)
EnemyRamP = $C2                  ; free-running frame clock
PF0Buf = $C3                     ; PF buffers rows 0-2 (9B: +0/3/6 per reg)
RoomPF0Lo = $99                  ; TilePF0 pointer (MetaB at (ptr),10)
RoomPF0Hi = $9A
RoomMetaA = $99                  ; staged MetaA/MetaB (floor + ptr pair reuse)
RoomMetaB = $9A
RoomRectsLo = $90                ; rect stream ptr (bank2 EnterRoomB2 stages)
RoomRectsHi = $91
RcBase = $89                     ; rect count for the ZP walk cache
RcW1 = $CC                       ; uniform 4B rect cache
RoomNo = $98
LevelWallColor = $AA             ; BuildColupF stripe rows 0+2
LevelWallColor2 = $AB            ; stripe row 1
TickCounter = $AD                ; hot-pulse phase bit 4
ColupfBuf = $E7
COLOR_CAVE_BG = $00
COLOR_DARK_PF = $04
COLOR_HOT_Y = $1C
COLOR_HOT_R = $44
TILE_ROWS = 3
BombPacked = $B5
LaserState = $C0
EnemyRamD = $C1
BandTab = $ED                    ; band gate bytes (B3StageBand writes)
CTRLPF = $0A                     ; TIA (ball width $35 during staging)
NUSIZ1 = $05                     ; TIA (P1 single, M1 8 clk)

; ==============================================================================
; B3StageBand — StageBandTab, MOVED from bank2 (chunk A2, 2026-10-19).
;
; Entered by LOCAL `jmp B3StageBand` from .BCFdarkDone (BCFDarkRun/PhaseBlink
; all live in THIS bank since A3), so no entry image or pin is needed any
; more: the old `.byte $4C,<B3StageBand` image at $F3AC was dead and got
; deleted with this relocation (repack chunk 5, 2026-10-20). The body moved
; from $F0A3 to $FC38 so the level-data window could start at $F0A3 (+189 B
; of headroom for generated blocks).
; Zero pushes end to end: this body ends `jmp $FBF8` (ReturnPad), whose
; `sta $1FF6 / rts` pops the ORIGINAL bank0 VBL jsr — the chain never nests.
;
; Reads ZP ONLY: RoomMetaA/B are staged at room entry (bank2 EnterRoomB2),
; so no level-data access and therefore no bank2 read tramp is needed.
;
; Packed meta (bugs.md 28 point 1): MetaA = (m1_col+1)<<4 | band_mask
; (b0-2 = band0/1/2 gates); MetaB = ball_col+1 (0 = feature absent).
; Expanded every VBL to:
;   BandTab ($ED-$EF) <- $ff/$00 per-band ENABL gates
;   Temp    ($88)     <- BallX = 87+8*ball_col (0 = symmetric -> skip)
;   CollisionEndX ($8E) <- M1X = 7+8*m1_col (0 = no M1; kill-gated below)
; Window: this VBL write -> cave read -> bank1 HUD stomps $ED-$EF after the
; cave read -> overscan rewrites $88 (joystick) after the ball read.
; ==============================================================================
    ; --- A3 level data (2026-10-19): shared model blocks + every per-room
    ;     PF/meta block. Emitted by convert_level --levels into
    ;     generated/spill_bank3.asm; bank2 keeps only the room TABLES (they
    ;     resolve these labels through generated/bank3_labels.asm).
    ;     Window moved from $F160 to $F0A3 (repack chunk 5, 2026-10-20) after
    ;     B3StageBand left for $FC38: 777 B of window, ~304 B used.
    org $F0A3
    include "generated/spill_bank3.asm"

; ==============================================================================
; A3 (2026-10-19): level-data walkers moved from bank2 — the record stream
; (rects/meta) lives in THIS bank now, so these read it directly.
; ==============================================================================
    org $F3B0

; ==============================================================================
; B3RoomBlocks — EnterRoomB2's level-data half (A3 2026-10-19).
; Reached by a tail-jump from bank2 ERBlocksPad (`sta $1FF9 / jmp $F3B0`),
; returns with `sta $1FF8 / jmp $F45B` (bank2's ERBlocksDone).
; Reads the room block from THIS bank: rect stream → ZP cache, 9-byte PF
; rebuild, then MetaA/MetaB into the dead pointer pair ($99/$9A).
; 0 pushes; clobbers A/X/Y/FetchPtr (bank2 restages every one of them).
; ==============================================================================
B3RoomBlocks:
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
    jmp $F458                       ; return tail (pinned after the image)




; --- fixed entry image: bank2 ERBlocksPad's `jmp` operand is fetched HERE ---
    .ds $F453 - *, 0
    .byte $4C, <B3RoomBlocks, >B3RoomBlocks   ; jmp B3RoomBlocks
; --- return tail PINNED at $F458: bank2's $F45B is a row start ---
    .ds $F458 - *, 0
    sta $1FF8                       ; back to bank2
    jmp $F45B                       ; ERBlocksDone (operand fetched bank2-side)


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


; A3b (2026-10-19): HOVFeatPre / PhHcrPre DELETED. Both bodies are in
; this bank now, so the feature dispatchers read the record fields
; straight from FetchPtr with Y = record base — no 4-field stack
; shuttle (the stack floor improves by ~7 bytes on both paths).

; ==============================================================================
; PhHcrEntry — PhaseBlink $82 (hcrunch) tramp target.
; Contract (user decision 2026-10-19): the crunch band is ALWAYS band 1,
; ALWAYS hot, ALWAYS the same geometry — a fixed 10-cell prefix (half the
; playfield width). The record fields x/band/w/h are IGNORED; the $82
; class byte and the 5-byte stride stay only so the walker is untouched.
; PF band1 = P(n), n = HcrClock(10): the prefix rows are entirely covered
; by the crunch, so the prefix mask is the whole row (no AND pass).
; IN: Y = record base, FetchPtr unused. OUT: Y = base+4 (.PhRec contract).
; Clobbers A/X/Y + CollisionX (HcrClock scratch); no stack use.
; ==============================================================================
    org $F880
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
    org $F980
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

; ==============================================================================
; HOVFeatEntry — .HOVfeature tramp target ($FD7B → here). Feature-record
; dispatch for HotOverlapBody. Stack: pushed record-base Y (.HOVloop
; invariant); A = record class. Every exit tail-jmps back through a
; $FCCx pad (the pushed Y survives — HOVnext/HOVlegHit pop it).
;   $80 phase:  armed (b5) && !removed (b6) → .HOVafterGate overlap
;               tests → shared Hot hit (bank2 latches b6, Temp b7)
;   $82 hcrunch: ANY overlap with the fixed band-1 / 10-cell prefix →
;               HOVlegHit (Temp b7 → LoseLife). No latch (2026-10-19).
; ==============================================================================
    org $FA40
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

; ==============================================================================
; A3 (2026-10-19): the pre-read/return tramp images are gone — PhaseBlink,
; HotOverlapBody and the HOV feature dispatcher all live in bank3 now, so
; those paths are plain local jmps. What remains here is the entry image
; fetched after a bank0/bank1 `sta $1FF9`.
; ==============================================================================
    .ds $FBF8 - *, 0            ; B3StageBand/BuildColupF exit: jmp ReturnPad.
ReturnPad:                      ;   The `sta $1FF6` runs HERE, the `rts` opcode
    sta $1FF6                   ;   is fetched from bank0 at $FBF9 -> pops the
    rts                         ;   bank0 VBL/jsr caller.
    .ds $FC35 - *, 0            ; CallPad_BuildColupF entry image: bank0/bank1
    jmp BuildColupF             ;   execute `sta $1FF9`, this fetch is bank3-side

    org $FC38
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

    .ds $FFEF - *, 0            ; fill between B3StageBand ($FC38, body above)
                                ;   and the HotOverlapFlag entry image below.
                                ;   Emitted HERE (forward from the body's end)
                                ;   because a later .ds would overwrite the
                                ;   body: DASM .ds writes to its org.


    org $FFEF                   ; HotOverlapFlag entry image: bank0 executes
                                ;   `sta $1FF9` at $FFEC, the jmp at +3 is
                                ;   fetched HERE. `org`, not `.ds`: the range
                                ;   below is B3StageBand's ($FC38 fill was
                                ;   emitted with the body) — a .ds here would
                                ;   overwrite it.
    jmp HotOverlapBody

    .ds $FFFA - *, 0
    .word $F000                 ; NMI vector
    .word $F000                 ; RESET vector ← power-up entry
    .word $F000                 ; IRQ vector
