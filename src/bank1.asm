    processor 6502
; ==============================================================================
; bank1 — HUD rendering + 6-digit score (F6 bankswitch, $F000-$FFFF)
; ==============================================================================
; Follows HERO/comparison pattern exactly:
; - GRP0/GRP1 for indicator sprites (lives, bombs)
; - 48-pixel sprite technique for score (NUSIZ copies + VDELP cross-buffer)
; - SetObjectXPos for precise positioning
; - Returns via fold-pad at $FC70

VBLANK  = $01
WSYNC   = $02
NUSIZ0  = $04
NUSIZ1  = $05
COLUP0  = $06
COLUP1  = $07
COLUPF  = $08
COLUBK  = $09
PlayerLives = $AC
PlayerBombs = $F0
BarLevel = $AE
BAR_MAX = 120            ; full bar (60 frames/step × 120 = 120s)
COLUPF  = $08
COLUBK  = $09
PF0     = $0D
PF1     = $0E
PF2     = $0F
RESP0   = $10
RESP1   = $11
GRP0    = $1B
GRP1    = $1C
ENAM0   = $1D
ENAM1   = $1E
ENABL   = $1F
HMP0    = $20
HMP1    = $21
HMOVE   = $2A
REFP0   = $0B
REFP1   = $0C
CTRLPF  = $0A
VDELP0  = $25
VDELP1  = $26

    org $F000

    ; Bank0 power-up stub: lda #0 / sta $1FF6 → lands here, jumps to GameStart
    jmp $F008

    ; --- ABW rect tables + BombMaskBit (relocated 2026-10-10) ---
    ; The BMW span-overlap fix grew the walk ~9B and overflowed the
    ; pre-$FBF8 content end ($FBF5, only 2B slack → Origin
    ; Reverse-indexed). Tables are abs-indexed from BombMarkWalls only,
    ; so they park in the $F003 fill gap (kept clear of the stub's
    ; $F008 landing zone). Recheck this gap if the power-up stub grows.
    .ds $F010 - *, 0
ABWXTab: .byte RcW1, RcW1+4, RcW1+8, RcW1+12, RcW1+16 ; rect.x (EQU-derived S3.1)
ABWWTab: .byte RcW1+2, RcW1+6, RcW1+10, RcW1+14, RcW1+18 ; rect.w
ABWYTab: .byte RcW1+1, RcW1+5, RcW1+9, RcW1+13, RcW1+17 ; rect.y (plan 5.1 punch)
ABWHTab: .byte RcW1+3, RcW1+7, RcW1+11, RcW1+15, RcW1+19 ; rect.h
BombMaskBit:
    .byte $08, $10, $20, $40, $00  ; WallMask bit per rect index; idx4 =
                                   ;  $00 (rect4 never in WallMask — zp doc
                                   ;  S3.2) — PairGone guards its double-score
                                   ;  (kernel copy died with ApplyBombWalls)

    org $F540
MenuMain:
    ; ========================================================================
    ; HUD entry point — called from bank0 via fold-pad at $FC68
    ; Follows comparison/lo-a-rad-dragon/bank2.asm pattern exactly
    ; ========================================================================

    ; --- Setup (same as comparison bank2) ---
    lda #0
    sta PF0
    sta PF1
    sta PF2
    lda #$06            ; grey background
    sta COLUBK
    lda #$0e            ; white sprites
    sta COLUP0
    sta COLUP1
    lda #0
    sta NUSIZ0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1
    sta REFP0
    sta REFP1

; ZP variables for score rendering (48-pixel sprite technique)
scorePtr1   = $E0       ; pointer to digit 1 font data (hundred-thousands)
scorePtr2   = $E2       ; pointer to digit 2 font data (ten-thousands)
scorePtr3   = $E4       ; pointer to digit 3 font data (thousands)
scorePtr4   = $E6       ; pointer to digit 4 font data (hundreds)
scorePtr5   = $E8       ; pointer to digit 5 font data (tens)
scorePtr6   = $EA       ; pointer to digit 6 font data (ones)
scbrdCnt    = $EC       ; score render loop counter (7..0)
scbrdTmp    = $ED       ; mid-scanline temp cache
DelayCnt    = $EE       ; bar delay A preloaded once per frame (bank1; ColupfBuf+7)
FineCnt     = $EF       ; bar fine delay cycles 0/2/3/4 (H3; bank1 only)
Temp        = $AD       ; scratch variable
; Score digits live at $F3-$F6 — MUST match bank0 Score* EQUs.
; Old home $BF-$C2 collided with EnemyRamX[2]/[3]/D/P during game HUD.
ScoreTh     = $F3       ; score thousands digit (must match bank0)
ScoreHu     = $F4       ; score hundreds digit
ScoreTe     = $F5       ; score tens+ones packed BCD
Level       = $A3       ; #18 current level, 0-based (must match kernel)
LevelShowTimer = $F2    ; #18 LV001 banner frames left (kernel sets, bank1 decs;
                         ;  ALIAS of TallyTicks — banner = gameplay entry only,
                         ;  tally = level-exit bonus; LoadLevel gates on $FD)
; $F6 is NOT ScoreOn — bank0 uses it as BombX. Do not write $F6 here.

; --- TIA/RIOT + ZP mirrors for relocated leaf routines (leaf_move_plan) ---
;     MUST match kernel.asm decls (hardware-fixed or frozen ZP addresses).
AUDC0       = $15
AUDC1       = $16
AUDF0       = $17
AUDF1       = $18
AUDV0       = $19
AUDV1       = $1A
SWCHA       = $0280
BombSnd     = $F1
JetPower    = $96
TickCounter = $AD               ; kernel's 60-frame timer ($AC = PlayerLives!).
                                ; Was $AC (stale) — jet wobble at `lda
                                ; TickCounter` read PlayerLives. Guard:
                                ; verify_build check_equ_sync (S3.0).
LaserState  = $C0       ; b7 fire held this frame, b5-2 = RoomDarkMask rooms
                        ; 4-7 (kernel.asm LaserState; laser b7/b6/b1-0 must
                        ; preserve b5-2 — see LaserInput/DropArm)
EnemyRamP   = $C2       ; free-running frame clock (bank0 RefreshEnemyY incs)
RoomNo      = $98
LevelConnLo = $A1
LevelConnHi = $A2
FetchPtr    = $E5                ; moved S3.2 (was $E0) — must match kernel
EnemyRamD   = $C1
PF0Buf      = $C3
PF1Buf      = $C6                ; packed rows 0-2 (S3.1; was $CF)
PF2Buf      = $C9                ; packed rows 0-2 (S3.1; was $DB)
CollisionX  = $8B
CollisionCellX = $8C
CollisionCellY = $8D            ; plan 5.1 punch: rect idx save across ClearPFColumn
CollisionEndY = $8F             ; plan 5.1 punch: last row (ClearPFColumn contract)
; bank0's LineCount — do NOT confuse with bank1's Temp ($AD) HUD scratch above.
; ClearPFColumn's first-row arg — passed by BombMarkWalls (plan 5.1 punch),
; NOT Temp: EnterRoom no longer runs ClearPFColumn (restore deleted, D1-B)
; and the old mid-input constraint is gone. Dead in overscan otherwise —
; kernel .Row re-inits it every tile row.
LineCount   = $84

; --- BombMarkWalls (S5.2, moved from bank0) — must match kernel.asm ---
BombX      = $F6                ; read-only here (see $F6 note above)
BMWScratch = $88                ; kernel Temp — NOT bank1's Temp ($AD)
RcBase     = $89                ; rect cache count (S3.2-fix: count sits on
                                 ; the $89 pad so rects fit $CC-$DF — clear
                                 ; of bank1's $E0 stomp that ate rect4.h)
RcW1       = $CC                ; rect0.x — cache base for ABW tables
RectCount  = $92                ; walk temp — BMW stashes the original screen
                                 ; col here (hand-copy of kernel's decl —
                                 ; check_equ_sync pair); M1StripBlast reads it
BombPacked = $B5                ; state+DownPrev+WallMask (b3-6)
EnemyDeadMask = $BA             ; b0-2 enemy kills (hand-copy of kernel's
                                 ; decl — check_equ_sync pair); b3 = D6 ball
                                 ; strip destroyed (StripBlastCheck); b4 = M1
                                 ; strip destroyed (M1StripBlast) — both die
                                 ; with the room via EnterRoom's zero
CollisionEndX = $8E             ; blast lo
TILE_COLUMNS = 20

INPT4       = $0C       ; fire button (active low, bit 7)

    ; --- Bar PF setup before TopGap (grey-on-grey: invisible) ---
    ; Yellow COLUPF only on the 3 bar lines; HMOVE line stays short.
    lda #$E0            ; margins (bit 4 = leftmost 4 clocks OFF)
    sta PF0
    lda #$FF
    sta PF1
    sta PF2
    lda #$06            ; grey (same as COLUBK)
    sta COLUPF
    lda #0
    sta GRP0            ; clear cave player sprite
    sta NUSIZ0
    lda #$05            ; CTRLPF: reflect + priority + 1-clock ball.
    sta CTRLPF
    ; --- Phase 4: copy the VBL-packed asym byte ($8F) → LineCount ($84) ---
    ; Cave .Row clobbered $84; this runs after the cave and before the
    ; score-ptr stomp window; overscan PHM reads $84 (OverlayTramp gate).
    lda CollisionEndY
    sta LineCount

    ; --- Top gap: 6 scanlines (lower HUD elements) ---
    ; 4 + the 2 lines the removed ball-at-boundary block used to occupy:
    ; bar/lives/bombs/score keep their exact scanlines (HudPad stays 9).
    ldx #6
.TopGap:
    sta WSYNC
    dex
    bne .TopGap

    ; ====================================================================
    ; Line 1: Timer bar — PF body, mid-scanline COLUPF yellow→red
    ; Full (BarLevel >= BAR_MAX-3 = 117..120): pure yellow, no red write.
    ; The 4-dec hold (bugs.md #30, 2026-10-11) delays the FIRST red until
    ; t=4s = exactly one chunk period, so the first red appears on the
    ; same cadence as every later chunk (report: "already red at start;
    ; first one should take the same time each chunk needs").
    ; H3c dual path: F=0 slim / F=1 slim+nop / F=2,3,4 full dispatch.
    ; dispatch ≤73c from the TopGap WSYNC to the first bar WSYNC.
    ; ====================================================================
    ldy BarLevel
    cpy #(BAR_MAX-3)
    bcc .BarRedSetup    ; B < 117 → red path (short fwd branch)
    ; Full bar: pure yellow, 3 lines only (no red write).
    ldx #3
.YLoop:
    sta WSYNC
    lda #$1C            ; yellow (hue 1, luma 6)
    sta COLUPF
    dex
    bne .YLoop
    jmp .BarGap

.BarRedSetup:
    lda BarDelayTable,Y
    sta DelayCnt
    lda BarFineTable,Y
    sta FineCnt
    ldy #$44            ; red (hue 4, luma 2) for sty COLUPF
    lda FineCnt
    bne .NotF0          ; F≠0 → check F=1
    ; --- Fine=0: slim, no pad (≤67c @A=11) ---
.BarRedF0:
    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF1
.BF1:
    dex
    bne .BF1
.RF1:
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF2
.BF2:
    dex
    bne .BF2
.RF2:
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF3
.BF3:
    dex
    bne .BF3
.RF3:
    sty COLUPF
    jmp .BarGap

.NotF0:
    cmp #1
    beq .BarRedF1       ; F=1 → slim+nop (avoids page-cross on bne .BarRedFull)
    jmp .BarRedFull     ; F=2,3,4 → dispatch
    ; --- Fine=1: slim + 2c nop/line (fills 3px gaps) ---
.BarRedF1:
    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF1n
.BF1n:
    dex
    bne .BF1n
.RF1n:
    nop                 ; +2c → +6 clocks vs F=0
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF2n
.BF2n:
    dex
    bne .BF2n
.RF2n:
    nop
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .RF3n
.BF3n:
    dex
    bne .BF3n
.RF3n:
    nop
    sty COLUPF
    jmp .BarGap

    ; --- Fine ∈ {2,3,4}: full dispatch, content ≤71c ---
.BarRedFull:
    sta WSYNC
    lda #$1C            ; yellow (hue 1, luma 6)
    sta COLUPF
    ldx DelayCnt        ; 3c, Z if A=0
    beq .Fine1          ; A=0 → fine only
.BD1:
    dex                 ; 2c
    bne .BD1            ; 3c taken / 2c last → 5A-1
.Fine1:
    ldx FineCnt         ; 3c (≠0 here)
    cpx #2              ; 2c
    beq .R1             ; Fine=2
    cpx #3              ; 2c
    beq .F31            ; Fine=3
    nop                 ; Fine=4
    nop
    jmp .R1
.F31:
    bit DelayCnt        ; 3c zp
    jmp .R1
.R1:
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .Fine2
.BD2:
    dex
    bne .BD2
.Fine2:
    ldx FineCnt
    cpx #2
    beq .R2
    cpx #3
    beq .F32
    nop
    nop
    jmp .R2
.F32:
    bit DelayCnt
    jmp .R2
.R2:
    sty COLUPF

    sta WSYNC
    lda #$1C
    sta COLUPF
    ldx DelayCnt
    beq .Fine3
.BD3:
    dex
    bne .BD3
.Fine3:
    ldx FineCnt
    cpx #2
    beq .R3
    cpx #3
    beq .F33
    nop
    nop
    jmp .R3
.F33:
    bit DelayCnt
    jmp .R3
.R3:
    sty COLUPF
    ; no jmp here: .BarGap is the next instruction — the old `jmp .BarGap`
    ; cost 3c AFTER the red boundary write and pushed line-3 content to 76c
    ; (BarGap WSYNC started at c76 → full-line stall → HUD band 51→52 lines
    ; → frame 263 on Fine2/3/4 frames). Lines 1/2 enter their WSYNC at c73.
.BarGap:

    ; --- gap: end bar line 3, clear PF during gap HBLANK ---
    ; (no ENABL write: the boundary-ball was removed — nothing in the HUD
    ; enables the ball anymore; .AfterRows already cleared it for the cave
    ; gate's benefit.)
    sta WSYNC
    lda #0
    sta PF0
    sta PF1
    sta PF2

    ; ====================================================================
    ; Line 2: Lives — green squares, count based on PlayerLives
    ; P0 with NUSIZ based on lives: $03=3 copies, $01=2, $00=1
    ; ====================================================================
    lda PlayerLives
    beq .NoLives                ; 0 lives = skip
    cmp #3
    bne .LivesNot3
    lda #$03                    ; 3 copies close
    jmp .LivesSetNusiz
.LivesNot3:
    cmp #2
    bne .LivesNot2
    lda #$01                    ; 2 copies close
    jmp .LivesSetNusiz
.LivesNot2:
    lda #$00                    ; 1 copy
.LivesSetNusiz:
    sta NUSIZ0
    lda #$C6                    ; green
    sta COLUP0
    lda #12                     ; base X
    ldx #0
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    lda #$E0                    ; 3-color-clock-wide square pattern
    sta GRP0
    ldy #5                      ; 5 scanlines tall
.LivesLoop:
    sta WSYNC
    dey
    bne .LivesLoop
    lda #0
    sta GRP0
    sta NUSIZ0
    jmp .LivesDone
.NoLives:
    lda #0
    sta GRP0
    sta NUSIZ0
    ldy #5
.LivesBlankLoop:
    sta WSYNC
    dey
    bne .LivesBlankLoop
    sta WSYNC            ; match lives path: SetObjectXPos + HMOVE
    sta WSYNC
.LivesDone:

    ; --- 1 scanline gap ---
    sta WSYNC

    ; ====================================================================
    ; Line 3: Bombs — red squares, count = PlayerBombs (0..5)
    ; P0 at 12: NUSIZ0 $00/$01/$03 → 1/2/3 copies
    ; P1 at 60: NUSIZ1 $00/$01 → 1/2 copies (only if count >= 4)
    ; Always same WSYNC structure (2×pos + HMOVE + 5 + 3 gap = 11)
    ; ====================================================================
    lda #$46            ; red
    sta COLUP0
    sta COLUP1
    lda PlayerBombs
    cmp #5
    bne .BmNot5
    lda #$03
    sta NUSIZ0
    lda #$01
    sta NUSIZ1
    jmp .BmNusizDone
.BmNot5:
    cmp #4
    bne .BmNot4
    lda #$03
    sta NUSIZ0
    lda #$00
    sta NUSIZ1
    jmp .BmNusizDone
.BmNot4:
    cmp #3
    bne .BmNot3
    lda #$03
    sta NUSIZ0
    jmp .BmP1off
.BmNot3:
    cmp #2
    bne .BmNot2
    lda #$01
    sta NUSIZ0
    jmp .BmP1off
.BmNot2:
    lda #$00            ; 0 or 1 bomb
    sta NUSIZ0
.BmP1off:
    lda #$00
    sta NUSIZ1
.BmNusizDone:
    lda #12             ; P0 base
    ldx #0
    jsr SetObjectXPos_b1
    lda #60             ; P1 base
    ldx #1
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    lda PlayerBombs
    beq .BmBlank
    cmp #4
    bcs .BmBoth
    lda #$E0
    sta GRP0
    lda #0
    sta GRP1
    jmp .BmDraw
.BmBoth:
    lda #$E0
    sta GRP0
    sta GRP1
    jmp .BmDraw
.BmBlank:
    lda #0
    sta GRP0
    sta GRP1
.BmDraw:
    ldy #5
.BombsLoop:
    sta WSYNC
    dey
    bne .BombsLoop
    lda #0
    sta GRP0
    sta GRP1
    sta NUSIZ0
    sta NUSIZ1

    ; --- 3 scanline gap (moved score down to avoid bomb collision) ---
    sta WSYNC
    sta WSYNC
    sta WSYNC

    ; ====================================================================
    ; Line 4: Score — 6-digit test ("012389") — 48-pixel sprite technique
    ; NUSIZ0=3 (3 copies close) + NUSIZ1=3 (3 copies close)
    ; Interleaved: P0c1 P1c1 P0c2 P1c2 P0c3 P1c3 = 6 digit slots
    ; VDELP0=1, VDELP1=1 for cross-buffer pipeline
    ; ====================================================================

    ; --- Setup sprites ---
    lda #$0E             ; white
    sta COLUP0
    sta COLUP1
    lda #3               ; NUSIZ = 3 copies close
    sta NUSIZ0
    sta NUSIZ1
    lda #1               ; VDELP = ON (cross-buffer active)
    sta VDELP0
    sta VDELP1
    ; Flush both VDELP buffers + live registers to 0.
    ; Without this, stale buffer data from previous frame shows as
    ; white ghost copies during the positioning scanlines.
    lda #0
    sta GRP0             ; GRP0A (buffer) = 0
    sta GRP1             ; GRP1A (buffer) = 0, GRP0 live = GRP0A = 0
    sta GRP0             ; GRP1 live = GRP1A = 0
    sta REFP0
    sta REFP1

    ; --- Position P0 and P1 for interleaved 6-digit layout ---
    ; P0 at pixel 60, P1 at pixel 68 (shifted 4px right to fix pipeline timing)
    lda #60
    ldx #0
    jsr SetObjectXPos_b1
    lda #68
    ldx #1
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE

    ; --- Score digits + #18 LV001 banner pointers (sub with the glyphs
    ; at $FD.. — bank1 pre-pad $F937 pin has ~1B slack, nothing fits).
    jsr SetupScorePointers

    ; --- Clear sprites before loop (3-write pattern for VDELP) ---
    lda #0
    sta GRP0
    sta GRP1
    sta GRP0

    ; ====================================================================
    ; 8-scanline render loop (exactly 71 cycles + WSYNC = 74 per line)
    ; Proven kernel from score48pix.asm
    ; ====================================================================
    ldy #7
    sty scbrdCnt
.ScoreLoop:
    ldy <scbrdCnt          ; 3c
    lda (scorePtr6),Y      ; 5c — pre-load LAST digit (digit 6)
    tax                    ; 2c — cache in X
    sta WSYNC              ; 3c
    lda (scorePtr1),Y      ; 5c — load digit 1
    sta.w GRP0             ; 4c — digit 1 -> GRP0A buffer
    lda (scorePtr2),Y      ; 5c — load digit 2
    sta GRP1               ; 3c — digit 2 -> GRP1A, digit 1 live on P0c1
    lda (scorePtr3),Y      ; 5c — load digit 3
    sta GRP0               ; 3c — digit 3 -> GRP0A, digit 2 live on P1c1
    lda (scorePtr4),Y      ; 5c — load digit 4
    sta <scbrdTmp          ; 3c — cache digit 4
    lda (scorePtr5),Y      ; 5c — load digit 5
    ldy <scbrdTmp          ; 3c — Y = digit 4
    sty GRP1               ; 3c — digit 4 -> GRP1A, digit 3 live on P0c2
    sta GRP0               ; 3c — digit 5 -> GRP0A, digit 4 live on P1c2
    stx GRP1               ; 3c — digit 6 -> GRP1A, digit 5 live on P0c3
    stx GRP0               ; 3c — digit 6 -> GRP0A, digit 6 live on P1c3
    dec <scbrdCnt          ; 5c
    bne .ScoreLoop         ; 3c

    ; --- Cleanup ---
    lda #0
    sta GRP0
    sta GRP1
    sta NUSIZ0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1

    ; --- Restore cave kernel settings ---
    lda #$35            ; CTRLPF: reflect + priority + 8-clk ball (cave mode
                        ; since D6 — bank1 bar overwrote $05 during its band)
    sta CTRLPF
    lda #0
    sta NUSIZ0
    lda #0
    sta NUSIZ1
    sta VDELP0
    sta VDELP1

    ; ====================================================================
    ; Pad remaining scanlines to reach exactly 48 total
    ; Path A (PlayerLives > 0) — execution count:
    ;   Top gap:  6 (4 + 2 former ball-pos lines — elements keep lines)
    ;   Timer:    3 loop + 1 gap = 4
    ;   Lives:    1 SetObjectXPos + 1 HMOVE + 5 render + 1 gap = 8
    ;   Bombs:    2 SetObjectXPos + 1 HMOVE + 5 render + 3 gap = 11
    ;   Score:    2 SetObjectXPos + 1 HMOVE + 7 ScoreLoop = 10
    ;   Subtotal: 6+4+8+11+10 = 39
    ;   Pad:      48 - 39 = 9
    ; .NoLives blank path pads +2 WSYNC so both paths total 48.
    ; ====================================================================
    ldx #9
.HudPad:
    sta WSYNC
    dex
    bne .HudPad

    ; --- Return to bank0 via fold-pad ---
    jmp $FC70

; ========================================================================
; SetObjectXPos — Andrew Davie algorithm (page-aligned table)
; X=0 positions P0, X=1 positions P1
; A = pixel position (0-159)
; ========================================================================
SetObjectXPos_b1:
    sta WSYNC
    sec
.Div15Loop:
    sbc #15
    bcs .Div15Loop
    tay
    lda fineAdjustTable_b1,Y
    sta HMP0,X
    sta RESP0,X
    rts

; Bar H3c tables (B=0..120): content ≤71c (WSYNC 3c fits in 76).
; Paths (cycles after WSYNC → sty red): F=0 slim 12+5A; F=1 slim+nop 14+5A;
; F=2 full 20+5A; F=3 full 30+5A; F=4 full 31+5A (A=0 special-cased).
BarDelayTable:          ; B=0..120
    .byte 2,2,2,2,2,1,1,1,1,3,3,3,3,3,3,3
    .byte 3,2,2,2,2,4,4,4,4,4,4,4,4,3,3,3
    .byte 3,5,5,5,5,5,5,5,5,4,4,4,4,6,6,6
    .byte 6,6,6,6,6,5,5,5,5,7,7,7,7,7,7,7
    .byte 7,6,6,6,6,8,8,8,8,8,8,8,8,7,7,7
    .byte 7,9,9,9,9,9,9,9,9,8,8,8,8,10,10,10
    .byte 10,10,10,10,10,9,9,9,9,11,11,11,11,11,11,11
    .byte 11,8,8,8,8,8,8,8,8

BarFineTable:           ; B=0..120; ∈{0,1,2,3,4}; path = f(F)
    .byte 0,1,1,1,1,2,2,2,2,0,0,0,0,1,1,1
    .byte 1,2,2,2,2,0,0,0,0,1,1,1,1,2,2,2
    .byte 2,0,0,0,0,1,1,1,1,2,2,2,2,0,0,0
    .byte 0,1,1,1,1,2,2,2,2,0,0,0,0,1,1,1
    .byte 1,2,2,2,2,0,0,0,0,1,1,1,1,2,2,2
    .byte 2,0,0,0,0,1,1,1,1,2,2,2,2,0,0,0
    .byte 0,1,1,1,1,2,2,2,2,0,0,0,0,1,1,1
    .byte 1,4,4,4,4,4,4,4,4

; ------------------------------------------------------------------------------
    .ds $F937 - *, 0            ; pinned: bank2 M1StripBlast back-jmp operand
                                 ; ($F937) — test_bomb_strip asserts both literals
; StripBlastCheck — Phase 4: bomb blast vs the D6 patch strips. Tail-jumped
; from BombMarkWalls .BMWDone, which now crosses to bank2 FIRST (M1 twin,
; `sta $1FF8 / jmp $F970` — the meta lives in bank2's ROM) and comes back
; here (`sta $1FF7 / jmp $F937`). Still 0 pushes (the jsr+pha version
; measured SP $F7 < the $F8 gameplay guard, and the pha leaked on the
; early-exit path -> runaway work -> 309-line frames in Stella 2026-10-04).
; Every exit ends in ReturnPad with A = count.
; In: BMWScratch = strip left col pL in RIGHT-half space ($FF = none/sym,
; captured before the punch loop), CollisionEndX/CellX = blast window in
; LEFT-half space (bomb col mirrored at BMW entry), CollisionX = count.
; Overlap after mirroring (39-x) with the strip not yet dead → set
; EnemyDeadMask b3 (ball strip; b4 = M1 strip, set by M1StripBlast) and
; inc the count (caller's +75 loop scores it). The
; kill bits die with the room (EnterRoom zeroes EnemyDeadMask) — same
; lifecycle as WallMask holes (D1-B).
; ------------------------------------------------------------------------------
StripBlastCheck:
    ; BMW blast cols are LEFT-frame; strip pL is RIGHT-frame → mirror the
    ; window here (space is free in this gap): lo_r = 39-hi_l,
    ; hi_r = 39-lo_l. Y holds hi_r (no stack push).
    clc
    lda CollisionEndX           ; lo_l
    eor #$FF
    adc #40                     ; hi_r = 39-lo_l
    tay
    clc
    lda CollisionCellX          ; hi_l
    eor #$FF
    adc #40                     ; lo_r = 39-hi_l
    sta CollisionEndX           ; EndX := lo_r
    sty CollisionCellX          ; CellX := hi_r
    lda CollisionCellX          ; hi
    sec
    sbc BMWScratch              ; hi - pL
    bcc .SBdone                 ; hi < pL → strip right of the blast
    lda CollisionEndX           ; lo
    cmp BMWScratch
    bcc .SBtake                 ; lo < pL (blast reaches right, hi >= pL)
    beq .SBtake                 ; lo == pL
    sec
    sbc #1
    cmp BMWScratch
    bne .SBdone                 ; lo >= pL+2 → blast ends left of the strip
.SBtake:
    lda EnemyDeadMask
    and #$08
    bne .SBdone                 ; already destroyed → no double score
    lda #$08
    ora EnemyDeadMask
    sta EnemyDeadMask           ; b3 = strip destroyed (in-room persistent)
    inc CollisionX              ; +1 wall for the caller's score loop
.SBdone:
    lda CollisionX              ; A = walls newly broken (caller contract)
    jmp $FBF8                   ; ReturnPad → bank0 caller (0 push)

    .ds $F9AC - *, 0            ; shared cross-bank pad — bank2 carries the
                                 ; SAME 12 bytes at $F9AC (identity asserted
                                 ; in test_bomb_strip): after `sta $1FF8` the
                                 ; NEXT opcode fetch is from the NEW bank at
                                 ; pc+3, so both banks must hold the identical
                                 ; `jmp` (F6 pad rule — ReturnPad/OverlayTramp
                                 ; do the same).
M1ToBank2:                      ; reached bank1-side: .BMWDone jmps here
    sta $1FF8                   ; switch bank1 → bank2
    jmp $F970                   ; M1StripBlast
M1ToBank1:                      ; = $F9B2 (M1StripBlast jmps here bank2-side;
    sta $1FF7                   ; after that switch bank1 executes this copy)
    jmp $F937                   ; StripBlastCheck

; ========================================================================
; Leaf routines relocated from bank0 — batch A, sounds (leaf_move_plan)
; Entry targets for bank0 CallPads; every tail jmps ReturnPad at $FBF8
; (byte-identical pad in both banks — pha/lda/sta/pla/rts).
; ========================================================================
    .ds $F9C0 - *, 0

JET_AUD_BASE = $0F           ; mirrors kernel.asm EQU (value guarded by tests)
JET_AUD_VOL  = $08
LASER_AUD_C  = 2             ; mirrors kernel.asm EQU: div-15 tone = low pitch
LASER_AUD_V  = 9
DropTarget = $8A             ; hand-copy of kernel ZP byte (spawn drop-in)

UpdateBombSound:
    lda BombSnd
    beq .UBSSilence
    dec BombSnd
    bne .UBSDone
.UBSSilence:
    lda #0
    sta AUDV0
.UBSDone:
    jmp $FBF8

UpdateJetSound:
    lda DropTarget              ; spawn drop-in: engine buzz while falling
    bne .JetOn                  ;   (no Up held — DropArm zeroes JetPower)
    lda SWCHA
    and #%00010000              ; D4 = up (0 = pressed)
    beq .JetOn
    lda #0                      ; throttle off -> mute engine
    beq .JetStore               ; A=0 -> Z set, always taken (byte-neutral)
.JetOn:
    lda #1                      ; 4-bit poly = raspy engine buzz
    sta AUDC1
    lda JetPower
    lsr
    lsr
    lsr                         ; JetPower/8 = 0..4 (revs with thrust)
    eor #$ff
    clc
    adc #1                      ; A = -(JetPower/8)
    clc
    adc #JET_AUD_BASE           ; A = base - JetPower/8
    tax
    lda TickCounter
    lsr                         ; C = TickCounter bit0 (was and #1)
    bcc .JetWob                 ;   parity wobble -1 every other frame (30 Hz)
    dex                         ; (bcc = old beq; dex when bit0 set)
.JetWob:
    txa
    sta AUDF1
    lda #JET_AUD_VOL
.JetStore:
    sta AUDV1
    jmp $FBF8

BombSndDrop:
    lda #6
    sta BombSnd
    lda #4                      ; square
    sta AUDC0
    lda #10
    sta AUDF0
    lda #8
    sta AUDV0
    jmp $FBF8

BombSndExplode:
    lda #30
    sta BombSnd
    lda #8                      ; noise
    sta AUDC0
    lda #0
    sta AUDF0
    lda #10
    sta AUDV0
    jmp $FBF8

; ========================================================================
; Leaf routines relocated from bank0 — batch B (leaf_move_plan)
; ========================================================================

; GetConnIdx — stage FetchPtr for the four exit handlers' folds.
; Conn table lives in bank2; the fold read happens in the bank0 CALLER's
; jsr FoldIndirect after return. Returns Y = RoomNo*2 (2 packed bytes per
; room: up/down, left/right), X = 0.
GetConnIdx:
    lda RoomNo
    asl
    tay
    lda LevelConnLo
    sta FetchPtr
    lda LevelConnHi
    sta FetchPtr+1
    ldx #0
    jmp $FBF8

; ClearPFColumn — A = left-half col 0..19; LineCount ($84) = first row;
;   CollisionEndY = last row (inclusive). AND-clear that col's
;   PF bit in those rows only. Clobbers A/X/Y/Temp ($AD) — NO CollisionX
;   (plan 5.1: BombMarkWalls keeps its broken-wall count there across the
;   call). Same-bank rts tail: BombMarkWalls jsrs this directly; the old
;   CallPad_ClearPFColumn path died with ApplyBombWalls (dead pad kept).
ClearPFColumn:
    tay                         ; Y = col
    lda BombClearMask,Y
    sta Temp                    ; AND mask (clear bit; NOT CollisionX)
    ldx LineCount               ; first row
.CPCLoop:
    tya                         ; col
    cmp #4
    bcc .CPC0
    cmp #12
    bcc .CPC1
    lda PF2Buf,X
    and Temp
    sta PF2Buf,X
    jmp .CPCNext
.CPC0:
    lda PF0Buf,X
    and Temp
    sta PF0Buf,X
    jmp .CPCNext
.CPC1:
    lda PF1Buf,X
    and Temp
    sta PF1Buf,X
.CPCNext:
    cpx CollisionEndY
    beq .CPCDone
    inx
    bne .CPCLoop               ; rows 0..2; X never wraps here
.CPCDone:
    rts                        ; plan 5.1: same-bank subroutine (was pad tail)

; AND-mask to clear col 0-19's PF bit (inverse of convert_room.pf_values)
BombClearMask:
    .byte $EF, $DF, $BF, $7F                    ; col 0-3  (PF0)
    .byte $7F, $BF, $DF, $EF, $F7, $FB, $FD, $FE ; col 4-11 (PF1)
    .byte $FE, $FD, $FB, $F7, $EF, $DF, $BF, $7F ; col 12-19 (PF2)

; AddScore — add BCD amount in A (e.g. #$50, #$75) to HUD score.
; ScoreTh/ScoreHu = binary 0-9; ScoreTe = packed BCD. Clobbers A.
; Real 6502 BCD add — SED/ADC/CLD straight-line: D is cleared before any
; jsr, the 2600 has no interrupts, and nothing here restores D via plp
; (the 2026-09-23 decimal-mode rule). The old BINARY `cmp #$A0 / sbc #$A0`
; fix-up missed nibble-level overflow: $25+$75 = $9A stored raw -> ones
; digit A -> glyph index 10 -> DigitGfx+80 (past the 10-glyph font) =
; the solid-block score digit (screenshots/score_issue_002.png).
; C=1 = BCD carry (sum >= 100) -> ScoreHu path.
; SIZE PIN: routine runs $FA7D..$FAA4 exactly (UpdateLaserSound's pad
; target is $FAA5). Old head = clc/adc/cmp/bcc/sbc = 9 bytes, new head =
; sed/clc/adc/cld/bcc = 7, so the two nops restore the exact length —
; without them every pad below shifts silently.
AddScore:
    sed
    clc
    adc ScoreTe
    cld
    bcc .ASstoreTe
    nop                         ; byte-pin (see SIZE PIN above)
    nop                         ; byte-pin
    pha                         ; save wrapped ScoreTe
    inc ScoreHu
    lda ScoreHu
    cmp #10
    bcc .AShuOk
    lda #0
    sta ScoreHu
    inc ScoreTh
    lda ScoreTh
    cmp #10
    bcc .ASthOk
    lda #9
    sta ScoreTh
.ASthOk:
.AShuOk:
    pla
.ASstoreTe:
    sta ScoreTe
    jmp $FBF8

; UpdateLaserSound — low "zoom" tone on channel 0 while fire is held.
; Call order in bank0 overscan: UpdateBombSound, UpdateJetSound, this — so
; AUDV0 is already forced to 0 by UpdateBombSound when BombSnd = 0, which is
; exactly what silence-on-release needs (this routine then does nothing).
; Bomb events own ch0 (BombSnd > 0 -> skip) so blip/explosion stay audible.
; Pitch sweeps AUDF 4..14 on the free-running frame clock: AUDC=2 divides by
; 15, so f = 31400/((AUDF+1)*15) = 419..140 Hz (low). Triangle, 8 steps x
; 8 frames = 1.07 s per cycle, no audible wrap jump.
; Clobbers A/X; Y preserved. No ZP writes.
UpdateLaserSound:
    lda BombSnd
    bne .ULSOut                 ; bomb event owns channel 0
    lda LaserState
    bpl .ULSOut                 ; fire released -> ch0 stays silent
    lda EnemyRamP
    lsr
    lsr
    lsr                         ; /8 frames per sweep step
    and #7
    tax
    lda LaserFreqTable,X
    sta AUDF0
    lda #LASER_AUD_C
    sta AUDC0
    lda #LASER_AUD_V
    sta AUDV0
.ULSOut:
    jmp $FBF8

LaserFreqTable:
    .byte 4,7,10,12,14,12,10,7

; PairGone — leaf in the pre-BMW free zone ($FACC..$FB0F). Called ONLY for
;   rect idx4 (the sole maskless slot), so rect4.x is deref'd here directly
;   (RcW1+16 = rect4.x — EQU-derived, not a magic number). Returns Z=1 iff
;   cols (rect4.x, rect4.x+1) are BOTH clear in row LineCount (pair present
;   anywhere in the span ⇒ Z=0). Rect idx4 has no WallMask bit (BombMaskBit
;   is 4-wide, b3-6), so this single-row buffer read replaces the mask
;   double-score guard for that slot only — first blast sees the pair
;   solid, any re-blast sees it clear and skips (parity: idx0-3 keep the
;   mask path untouched). Pair x is even (cell-aligned) and ≠0 (caller
;   gates), so x and x+1 always share one PF buffer. Clobbers A,X,Y,Temp.
;   Same-bank jsr legal (no pad nesting).
PairGone:
    lda RcW1+16                 ; rect4.x (ABWXTab,X with X=4)
    tax
    lda BombClearMask,X
    eor #$FF
    tay                         ; Y = bit for col x
    inx
    lda BombClearMask,X
    eor #$FF
    sta Temp                    ; bit for col x+1
    tya
    ora Temp
    sta Temp                    ; both pair bits
    ; X = x+1 here — buffer dispatch still selects correctly (pair x is
    ; even: PF0 iff x<4 ⟺ X<4; PF1 4..10 ⟺ X 5..11; PF2 x≥12 ⟺ X≥13).
    ldy LineCount
    cpx #4
    bcc .pg0
    cpx #12
    bcc .pg1
    lda PF2Buf,Y
    and Temp
    rts
.pg0:
    lda PF0Buf,Y
    and Temp
    rts
.pg1:
    lda PF1Buf,Y
    and Temp
    rts

; ========================================================================
; BombMarkWalls (S5.2, moved from bank0) — pinned at $FB10.
;   On the bomb 1->2 edge: walk the rect cache, set WallMask bit (BombPacked
;   b3-6) for each w==2 rect whose x is in blast cols (bomb left-half col
;   +-2, clamped 0..19). w==2 = one D7 logical cell (rect x/w are emitted
;   in 4px display cols; a thin wall is exactly one cell = 2 cols). Skip x==0 (screen border). Score is NOT done here —
;   pads cannot nest (ReturnPad switches to bank0), so this returns
;   A = #walls newly broken and the bank0 caller adds +75 per wall.
;   Plan 5.1: each newly broken rect is punched here immediately —
;   ClearPFColumn on col x AND col x+1 (D7 thin wall w = 2 display cols;
;   the single-col punch left half the wall standing behind a set mask bit)
;   — the old VBL ApplyBombWalls re-apply + EnterRoom
;   restore are deleted (D1-B). WallMask b3-6 survives only in-room: the
;   hot parent-mask AND (HotOverlapBody) still reads it until phase 6.
;   ABW tables + BombMaskBit are bank1-only now (kernel copies died with
;   ApplyBombWalls).
;   #7(i): walk now covers rects 0-4 (cache slot rect4 at $DC-$DF was
;   loaded but never walked — a thin wall there was unbreakable). Rect5
;   is not cached (ZP ends $DF) and stays unwalkable — shipped models
;   have no thin rect at idx5. Rect idx4 has no WallMask bit: PairGone's
;   buffer read replaces the mask as its double-score guard. A full
;   buffer cell-sweep was evaluated and REJECTED: find_rectangles merges
;   maximal runs, so every shipped thin wall has a solid neighbor slab
;   (checked all 8 models) — buffer adjacency cannot distinguish thin
;   stubs from thick walls without breaking gameplay parity.
;   Also fixed: the col x+1 punch passed the ABW table VALUE (the rect's
;   ZP address) as the ClearPFColumn col instead of deref'ing rect.x —
;   the second half of every thin wall was punched at a garbage col
;   (caught by the new test_bomb_strip rect-walk case; pre-existing
;   since plan 5.1). RcBase is now clamped ≤5 at the bank2 cache load —
;   BMW trusts it (no local clamp).
; ========================================================================
    .ds $FB10 - *, 0
BombMarkWalls:
    ; visible-left mapping identical to PlayerHitsMap: the bomb is drawn from
    ; BombX via SetObjectXPos, so its left edge is BombX-5 / BombX-7, not BombX.
    sec
    lda BombX
    cmp #15
    bcc .BMWoff7
    sbc #7                      ; visible left = BombX - 7
    bcs .BMWVL                  ; C set (X>=15) — skip the -5 path
.BMWoff7:
    sbc #4                      ; visible left = BombX - 5 (CMP clears carry)
.BMWVL:
    lsr
    lsr                         ; screen col = visible_left/4 (0..39)
    sta RectCount               ; ORIGINAL screen col (0..39): >=20 = right
                                ; bomb → real blast lives in the right half,
                                ; so M1StripBlast must skip its left overlap
                                ; test (the window below is mirror-space for
                                ; right bombs). RectCount free pre-loop.
    cmp #TILE_COLUMNS
    bcc .BMWCol
    sta BMWScratch
    lda #39
    sec
    sbc BMWScratch               ; mirror right-half → left-half col
.BMWCol:
    sta BMWScratch               ; bomb left-half col
    ; blast lo = max(col-2, 0)   (±2: player is 8px wide, so a bomb dropped
    ; blast hi = min(col+2, 19)    flush-left sits 2 cols from the wall)
    lda BMWScratch
    cmp #2
    bcc .BMWLo0
    sec
    sbc #2
    bcs .BMWStoreLo
.BMWLo0:
    lda #0
.BMWStoreLo:
    sta CollisionEndX           ; blast_lo (free: overscan, after movement)
    lda BMWScratch
    cmp #18
    bcs .BMWHi19
    clc
    adc #2
    bcc .BMWStoreHi
.BMWHi19:
    lda #19
.BMWStoreHi:
    sta CollisionCellX          ; blast_hi (loop compares rect.x against it)
    ; --- Phase 4: capture the strip's left col BEFORE the punch loop
    ; (ClearPFColumn overwrites LineCount with rect rows). pL = 18+2n,
    ; n = packed nibble (right_col+1); $FF = symmetric/none. BMWScratch is
    ; free here (bomb col already folded into blast lo/hi).
    lda LineCount
    beq .SBnocap
    lsr
    lsr
    lsr
    lsr                         ; n = right_col+1
    asl
    clc
    adc #18                     ; pL = 20+2*right_col
    jmp .SBst
.SBnocap:
    lda #$FF
.SBst:
    sta BMWScratch
    lda #0
    sta CollisionX              ; walls-broken count (returned in A)
    lda RcBase                  ; cached rect count (clamped ≤5 at load)
    beq .BMWDone
    tax                         ; X = rect count (1..5)
    dex                         ; X = 4..0
.BMWLoop:
    lda ABWXTab,X
    tay
    lda 0,Y                     ; rect.x
    beq .BMWNext                ; x==0 = screen L/R border — never destroy
    sta CollisionEndY           ; hold x for the span test below; punch path
                                ;   rewrites CollisionEndY (last row) before
                                ;   ClearPFColumn reads it — no conflict
    lda ABWWTab,X
    tay
    lda 0,Y
    cmp #2                      ; thin wall = 1 D7 cell = 2 display cols
    bne .BMWNext
    ; --- SPAN overlap (2026-10-10): blast hits the wall if ANY col of
    ; [x, x+w-1] lies in [blast_lo, blast_hi]. The old rect.x-only test
    ; missed bombs sitting one col right of rect.x: fold 15 → window
    ; [13,17] vs rect span [12,13] → 0 PF writes ("right wall: nothing
    ; happens"; sweep bombx 104-107 = natural flush drop beside the
    ; mirrored instance cols 26-27). w is already known == 2 here, so
    ; far = x+1.
    lda CollisionEndY           ; x
    cmp CollisionCellX          ; x vs hi
    beq .BMWIn                  ; x == hi → right col in blast
    bcs .BMWNext                ; x > hi → span entirely right of blast
    clc
    adc #1                      ; far = x + w - 1
    cmp CollisionEndX           ; far vs lo
    bcc .BMWNext                ; far < lo → span entirely left of blast
.BMWIn:
    stx CollisionCellY          ; save rect idx (ClearPFColumn clobbers X)
    ; --- plan 5.1: punch rows y..y+h-1 (D7 thin wall w = 2 display cols;
    ;   cols x AND x+1. Single-col punch was a D7 regression: it cleared
    ;   only col x, and the just-set mask bit then blocked any re-blast
    ;   of the surviving col x+1 (user test 2026-10-04 — "removes only
    ;   half, remaining wall can't be blasted at all"). ClearPFColumn is
    ;   same-bank rts — jsr legal (no pad nesting), SP -2 for ~40c each.
    lda ABWYTab,X
    tay
    lda 0,Y
    sta LineCount               ; first row
    lda ABWHTab,X
    tay
    lda 0,Y
    clc
    adc LineCount
    sec
    sbc #1
    sta CollisionEndY           ; last row (inclusive)
    lda BombMaskBit,X
    and BombPacked              ; already broken?
    bne .BMWNext                ; yes → no double score
    cpx #4
    bne .BMWSet
    jsr PairGone                ; idx4: no WallMask bit — buffer guard instead
    ldx CollisionCellY          ; PairGone clobbered X (x+1) — restore idx
    cmp #0                      ; re-derive Z from A (ldx set Z from idx)
    beq .BMWNext                ; pair already clear → prior blast (no score)
.BMWSet:
    lda BombMaskBit,X
    ora BombPacked
    sta BombPacked               ; set WallMask bit (keeps state+DownPrev)
.BMWPunch:
    inc CollisionX               ; +1 wall broken (caller scores +75 each)
    ; X = rect idx on entry (mask path never clobbers it; the idx4 guard
    ; block restored it after PairGone) — first punch may use X directly.
    lda ABWXTab,X
    tay
    lda 0,Y                     ; A = col (ClearPFColumn arg)
    jsr ClearPFColumn
    ldx CollisionCellY          ; restore rect idx (ClearPFColumn clobbers X)
    lda ABWXTab,X
    tay
    lda 0,Y
    clc
    adc #1                      ; col x+1 — second half of the D7 thin wall
    jsr ClearPFColumn
    ldx CollisionCellY          ; restore rect idx for .BMWNext's dex
.BMWNext:
    dex
    bpl .BMWLoop
.BMWDone:
    jmp M1ToBank2               ; shared pad $F9AC (sta $1FF8 / jmp $F970,
                                 ; byte-identical in bank2) → M1StripBlast
                                 ; sets b4 if the blast covers the left strip,
                                 ; then the pad's back-half crosses to
                                 ; StripBlastCheck. Still 0 push — SP guard
                                 ; unchanged; the check ends in ReturnPad with
                                 ; A = count.

; ABWXTab/ABWWTab/ABWYTab/ABWHTab/BombMaskBit live at $F010 (top-of-bank
; fill gap) — relocated 2026-10-10 when the BMW span fix overflowed the
; $FBF8 pin. Only BombMarkWalls indexes them (abs,X/Y), no cross-bank
; operand points at them.

; ========================================================================
; Cross-bank call pads — byte-identical to bank0 at these addresses
; (docs/leaf_move_plan.md). F6 hotspot ignores the written value, so pads
; pass A/X/Y/flags through untouched (`sta` does not affect flags).
; ========================================================================
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF6
    rts
CallPad_UpdateBombSound:
    sta $1FF7
    jmp $F9C0
CallPad_UpdateJetSound:
    sta $1FF7
    jmp $F9CF
CallPad_BombSndDrop:
    sta $1FF7
    jmp $FA00
CallPad_BombSndExplode:
    sta $1FF7
    jmp $FA13
CallPad_GetConnIdx:
    sta $1FF7
    jmp $FA26
CallPad_ClearPFColumn:
    sta $1FF7
    jmp $FA37
CallPad_AddScore:
    sta $1FF7
    jmp $FA7C
CallPad_IsRoomDark:
    sta $1FF7
    jmp $FC78
CallPad_SetRoomDark:
    sta $1FF7
    jmp $FC9E
CallPad_UpdateLaserSound:
    sta $1FF7
    jmp $FAA4
CallPad_BuildColupF:
    sta $1FF8                   ; S5.1: body lives in bank2 (direct rect reads)
    jmp $FC4F
CallPad_BombMarkWalls:
    sta $1FF7                   ; S5.2: body lives in bank1 ($FB10)
    jmp $FB10

; ========================================================================
; Fold-pad stubs (byte-identical to bank0)
; ========================================================================
    .ds $FC68 - *, 0
    lda #1
    sta $1FF7
    jmp $F540

    .ds $FC70 - *, 0
    lda #0
    sta $1FF6
    jmp $F19E           ; Overscan in bank0 (must match bank0 ToGameStub;
                        ; verify_build --sync-overscan patches this from
                        ; bank0.lst after every bank0 build)

; ========================================================================
; IsRoomDark/SetRoomDark — moved here (post-ToGameStub free space) when the
; mask grew to 8 bits: the $F9C0-$FB10 body span had only ~19 B headroom.
; CallPad jmp literals live in BOTH kernel.asm and bank1.asm — verify_build
; check_callpads asserts they equal these labels.
; ------------------------------------------------------------------------
; IsRoomDark — Z=1 if lit, Z=0 if dark (RoomDarkMask = 8-bit split:
; rooms 0-3 = EnemyRamD bits 4-7, rooms 4-7 = LaserState bits 2-5.
; Rooms 8+ have no bit → always lit, never crash.)
; Clobbers A/X; Y preserved. PLA in ReturnPad re-sets Z from A — contract
; survives the cross-bank return.
IsRoomDark:
    lda RoomNo
    cmp #4
    bcs .IRDhi
    clc
    adc #4                      ; bit index = 4 + RoomNo
    tax
    lda BitMaskTable,X
    and EnemyRamD               ; Z=1 → lit (bit clear), Z=0 → dark
    jmp $FBF8
.IRDhi:
    cmp #8
    bcs .IRDlit                 ; rooms 8+ never dark (no mask bit)
    tax
    lda BitMaskTable,X          ; $10/$20/$40/$80
    lsr
    lsr                         ; → $04/$08/$10/$20 = LaserState b2-5
    and LaserState
    jmp $FBF8
.IRDlit:
    lda #0                      ; Z=1 → lit
    jmp $FBF8

; SetRoomDark — set dark flag for current RoomNo (rooms 0-3 → EnemyRamD
; bits 4-7, rooms 4-7 → LaserState bits 2-5; rooms 8+ = no-op, room
; simply stays lit). Cleared only by LoadLevel.
SetRoomDark:
    lda RoomNo
    cmp #4
    bcs .SRDhi
    clc
    adc #4
    tax
    lda BitMaskTable,X
    ora EnemyRamD
    sta EnemyRamD
    jmp $FBF8
.SRDhi:
    cmp #8
    bcs .SRDdone                ; rooms 8+: no bit to set (no crash)
    tax
    lda BitMaskTable,X
    lsr
    lsr
    ora LaserState
    sta LaserState
.SRDdone:
    jmp $FBF8

; Bit masks for IsRoomDark/SetRoomDark. Index 4+room for EnemyRamD
; (rooms 0-3 → bits 4-7); index = room for LaserState (rooms 4-7 →
; bits 4-7 of the table, lsr×2 down to bits 2-5 = LaserState spare).
BitMaskTable:
    .byte $01, $02, $04, $08, $10, $20, $40, $80

; ========================================================================
; Score digit font — 8x8 pixels, page-aligned for fast (zp),Y addressing
; 10 digits (0-9), 8 bytes each = 80 bytes
; MSB-first: bit7 = leftmost pixel
; ========================================================================
    org $FD00
DigitGfx:
    ; Digit 0
    .byte %0
    .byte %01111100
    .byte %11000110
    .byte %11000110
    .byte %11000110
    .byte %11000110
    .byte %11000110
    .byte %01111100

    ; Digit 1
    .byte %0
    .byte %00011000
    .byte %00011000
    .byte %00011000
    .byte %00011000
    .byte %01011000
    .byte %00111000
    .byte %00011000

    ; Digit 2
    .byte %0
    .byte %11111110
    .byte %11000000
    .byte %01100000
    .byte %00011000
    .byte %00000110
    .byte %11000110
    .byte %01111100

    ; Digit 3
    .byte %0
    .byte %11111100
    .byte %00000110
    .byte %00000110
    .byte %00111100
    .byte %00000110
    .byte %00000110
    .byte %11111100

    ; Digit 4
    .byte %0
    .byte %00001100
    .byte %00001100
    .byte %11111110
    .byte %11001100
    .byte %11001100
    .byte %11001100
    .byte %11000000

    ; Digit 5
    .byte %0
    .byte %11111100
    .byte %00000110
    .byte %00000110
    .byte %11111100
    .byte %11000000
    .byte %11000000
    .byte %11111110

    ; Digit 6
    .byte %0
    .byte %01111100
    .byte %11000110
    .byte %11000110
    .byte %11111100
    .byte %11000000
    .byte %11000010
    .byte %01111100

    ; Digit 7
    .byte %0
    .byte %01100000
    .byte %00110000
    .byte %00011000
    .byte %00001100
    .byte %00000110
    .byte %00000110
    .byte %11111110

    ; Digit 8
    .byte %0
    .byte %01111100
    .byte %11000110
    .byte %11000110
    .byte %01111100
    .byte %11000110
    .byte %11000110
    .byte %01111100

    ; Digit 9
    .byte %0
    .byte %01111100
    .byte %10000110
    .byte %00000110
    .byte %01111110
    .byte %11000110
    .byte %11000110
    .byte %01111100

    ; Glyph 10 = blank (#18 LV banner trailing slot; byte7=top, byte1=bottom)
    .byte %0
    .byte %0
    .byte %0
    .byte %0
    .byte %0
    .byte %0
    .byte %0
    .byte %0

    ; Glyph 11 = L (#18)
    .byte %0
    .byte %01111110
    .byte %01100000
    .byte %01100000
    .byte %01100000
    .byte %01100000
    .byte %01100000
    .byte %01100000

    ; Glyph 12 = V (#18)
    .byte %0
    .byte %00011000
    .byte %00011000
    .byte %00111100
    .byte %00111100
    .byte %01100110
    .byte %01100110
    .byte %01100110

; SetupScorePointers — score digit ptrs + #18 LV001 banner (#18):
; first frame zeroes ScoreTh/Hu/Te (Temp = $AD first-frame flag); every
; frame points scorePtr1-6 at DigitGfx+digit*8 (right-aligned "00ThHu.."),
; or — while LevelShowTimer > 0 — at "L V 0 tens ones _" for Level+1
; (hundreds stays '0'; LEVEL_COUNT <= 99). Decrements LevelShowTimer
; once per banner frame. Lives with the glyphs: bank1 pre-pad $F937 pin
; has ~1B slack (score section is a jsr here from MenuMain).
SetupScorePointers:
    ; --- Initialize score to 0 on first frame ---
    lda Temp
    bne .scoreInitDone
    inc Temp
    lda #0
    sta ScoreTh
    sta ScoreHu
    lda #$00
    sta ScoreTe
.scoreInitDone:

    ; --- Set up 6 digit pointers ---
    ; High bytes first (all $FD)
    lda #>DigitGfx
    sta scorePtr1+1
    sta scorePtr2+1
    sta scorePtr3+1
    sta scorePtr4+1
    sta scorePtr5+1
    sta scorePtr6+1

    lda LevelShowTimer
    and #$80                   ; bit7 = banner flag (#18; tally ARM clears it)
    beq .scoreLows
    dec LevelShowTimer
    lda #<DigitGfx+88          ; glyph 11 = L
    sta scorePtr1
    lda #<DigitGfx+96          ; glyph 12 = V
    sta scorePtr2
    lda #0                     ; hundreds '0'
    sta scorePtr3
    lda Level
    clc
    adc #1                     ; 1-based level number
    ldx #0
.LVTens:
    cmp #10
    bcc .LVTensDone
    sbc #10
    inx
    bne .LVTens
.LVTensDone:
    asl
    asl
    asl                        ; ones * 8
    sta scorePtr5
    txa
    asl
    asl
    asl                        ; tens * 8
    sta scorePtr4
    lda #<DigitGfx+80          ; glyph 10 = blank (trailing slot)
    sta scorePtr6
    rts

    ; scorePtr1..2 = leading zeros
.scoreLows:
    lda #0
    sta scorePtr1
    sta scorePtr2

    ; scorePtr3 = ScoreTh * 8
    lda ScoreTh
    asl
    asl
    asl
    sta scorePtr3

    ; scorePtr4 = ScoreHu * 8
    lda ScoreHu
    asl
    asl
    asl
    sta scorePtr4

    ; scorePtr5 = (ScoreTe >> 4) * 8  (tens digit)
    lda ScoreTe
    lsr
    lsr
    lsr
    lsr                   ; tens digit in low nibble
    asl
    asl
    asl
    sta scorePtr5

    ; scorePtr6 = (ScoreTe & $0F) * 8  (ones digit)
    lda ScoreTe
    and #$0F
    asl
    asl
    asl
    sta scorePtr6
    rts

; ========================================================================
; Fine-adjust table (page-aligned at $FF00)
; ========================================================================
    org $FF00
fineAdjustBegin_b1:
  .byte %01110000
  .byte %01100000
  .byte %01010000
  .byte %01000000
  .byte %00110000
  .byte %00100000
  .byte %00010000
  .byte %00000000
  .byte %11110000
  .byte %11100000
  .byte %11010000
  .byte %11000000
  .byte %10110000
  .byte %10100000
  .byte %10010000
fineAdjustTable_b1 EQU fineAdjustBegin_b1 - %11110001

; ========================================================================
; Interrupt vectors
; ========================================================================
    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
