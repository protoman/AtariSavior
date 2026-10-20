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
BarIdx   = $9B           ; (BarLevel+7)>>3, synced by kernel overscan (D2)
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

    ; --- power-up stub: the F6 latch powers up in an UNDEFINED bank on real
    ; hardware (Stella only randomises it with developer settings), so every
    ; bank must be able to start. This is 5 bytes on purpose: `sta $1FF6`
    ; switches to bank0, and the next fetch ($F005) then comes from BANK0,
    ; where a `jmp $F008` (GameStart) sits — the same 5-byte prefix bank2 and
    ; bank3 carry. Never shorten it to a bare `jmp`: that is what this bank had
    ; (a bank-select-less `jmp $F008` = BRK loop into zero fill).
    ; Guard: verify_build.check_boot_banks + tools/test_boot_banks.py.
    lda #0
    sta $1FF6                       ; select bank0 (hotspot: the DATA is ignored)

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

; MothYDerive — moved from bank0 (leaf_move_plan Step 0, 2026-10-16). In
; Y = record+0, X = slot (preserved). Out A = live Y delta; the bank0
; caller then jmp DEYDelta (adds the ROM spawn y). Same math as old copy.
MothYDerive:
    lda EnemyRamP
    lsr
    lsr
    and #15
    cmp #8
    bcc .mUpB1
    eor #15
.mUpB1:
    cmp #7
    bcc .mOkB1
    lda #6
.mOkB1:
    asl
    adc #$FA
    jmp ReturnPad

; TitleSelect — moved from bank0 (refactor_v4_plan Phase 3.1 canary, 2026-10-16).
; Pure leaf (no calls); returns C=1 edge (caller runs LoadLevel) / C=0 no-edge.
; Entered via CallPad_TitleSelect ($FC4F); tail-exits through ReturnPad
; (sta $1FF6/rts), which returns to the bank0 caller with C intact.
SWCHB       = $0282
StepsLeft   = $97               ; bank0 per-frame step latch (ZP byte block)
LEVEL_COUNT = 4                 ; hand copy of kernel LEVEL_COUNT
TitleSelect:
    lda StepsLeft
    and #%00000010
    beq .TSnoB1
    lda SWCHB
    and #%00000010
    bne .TSnoB1
    inc Level
    lda Level
    cmp #LEVEL_COUNT
    bne .TSokB1
    lda #0
    sta Level
.TSokB1:
    sec
    jmp ReturnPad
.TSnoB1:
    clc
    jmp ReturnPad

; ==============================================================================
; Merged title screen (2026-10-19): banner shown over the CAVE kernel? No —
; TitleKernel is the title frame itself: stage PF (rows 0-2) + player + logo
; + credit footer + the HUD band (jmp MenuMain). bank0 enters via
; CallPad_TitleKernel ($FC55) and the frame ends in the HUD → Overscan.
; ==============================================================================
RoomX        = $80
RoomY        = $81
PlayerDir    = $82
Grp0Ptr      = $86
Grp0PtrHi    = $87
BombTimer    = $F7
TallyTicks   = $F2
COLOR_CAVE_BG = $00
COLOR_HOT_Y  = $1C
COLOR_HOT_R  = $44
COLOR_BOMBS  = $46
COLOR_TITLE  = $6A
FooterPtr1   = $E0
FooterPtr2   = $E2
FooterPtr3   = $E4
FooterPtr4   = $E6
FooterPtr5   = $E8
FooterPtr6   = $EA
TPtr1        = $E0               ; logo slot pointers (= FooterPtr1-6 slots)
TPtr2        = $E2
TPtr3        = $E4
TPtr4        = $E6
TPtr5        = $E8
TPtr6        = $EA

    .ds $F080 - *, 0            ; TitleBand pin (CallPad_TitleBand literal)
; ==============================================================================
; TitleBand — merged title, bands 1-2 (2026-10-19 refactor).
; Band 0 is drawn by the CAVE kernel (stage PF + COLUPF from the room buffers,
; player via PlayerColTable/Grp0Ptr), so the title reuses the real kernel
; instead of duplicating its band rendering. The bank0 row-advance tail
; diverts here when DropTarget=$FF, exactly where band 1 would start.
; This routine: band 1 stage row + the 48px S.A.V.I.O.R. logo + the credit
; footer, then band 2's stage row + 48 lines, then the HUD band (score =
; level+1, lives/bombs/bar via MenuMain). No object is drawn on the title:
; DropArm .DATitle clears EnemyCount/LevelMinerRoom and the laser on every
; title LoadLevel, so SelectActiveObject parks GRP1.
; Entered via CallPad_TitleBand ($FC55). ZP: LineCount ($84) + Temp ($88) as
; loop counter/tmp — idle on title frames (cave overscan bypassed).
; ==============================================================================
TitleBand:
    ; ==================================================================
    ; Band 1 (48 lines): stage middle row + logo + credit footer.
    ; Same store order as the cave .Row (PF0, PF1, COLUPF, ENABL, PF2 last)
    ; so the band-transition line keeps the left half on band 0.
    ; ==================================================================
    ; Cave band 0 leaves the missiles latched (the .AfterRows clear is
    ; skipped on the title). The 48px footer sets NUSIZ=3, so a live M0/M1
    ; would draw 1-clock vertical lines through bands 1/2 — clear both here.
    lda #0
    sta ENAM0
    sta ENAM1
    lda PF0Buf+1
    sta PF0
    lda PF1Buf+1
    sta PF1
    lda ColupfBuf+1
    sta COLUPF
    lda BandTab+1
    sta ENABL
    lda PF2Buf+1
    sta PF2
    lda #6                       ; 3 copies, 32px pitch (48px logo)
    sta NUSIZ0
    sta NUSIZ1
    lda #1                       ; VDEL cross-buffer
    sta VDELP0
    sta VDELP1
    lda #0                       ; logo slots are not mirrored
    sta REFP0
    sta REFP1
    ldx #0
    lda #41
    jsr SetObjectXPos_b1
    ldx #1
    lda #57
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    lda #>TitleFont
    sta TPtr1+1
    sta TPtr2+1
    sta TPtr3+1
    sta TPtr4+1
    sta TPtr5+1
    sta TPtr6+1
    lda #<TitleFont
    sta TPtr1
    lda #<(TitleFont+8)
    sta TPtr2
    lda #<(TitleFont+16)
    sta TPtr3
    lda #<(TitleFont+24)
    sta TPtr4
    lda #<(TitleFont+32)
    sta TPtr5
    lda #<(TitleFont+40)
    sta TPtr6
    lda #COLOR_TITLE
    sta COLUP0
    sta COLUP1
    ldx #7
    stx LineCount                ; rows left (7..1 — byte0 blank)
.TkLoop:
    ldy LineCount
    lda (TPtr6),Y                ; slot 6 = "R." — font byte7 = TOP row
    tax
    sta WSYNC
    lda (TPtr1),Y                ; slot 1 = "S."
    sta.w GRP0
    lda (TPtr2),Y                ; slot 2 = "A."
    sta GRP1
    lda (TPtr3),Y                ; slot 3 = "V."
    sta GRP0
    lda (TPtr4),Y                ; slot 4 = "I."
    sta Temp
    lda (TPtr5),Y                ; slot 5 = "O."
    ldy Temp
    sty GRP1
    sta GRP0
    stx GRP1
    stx GRP0
    dec LineCount
    bne .TkLoop
    sta WSYNC
    lda #0
    sta GRP0
    sta GRP1
    sta GRP0
    sta GRP1
    ; --- credit footer: 3 copies on both players at 60/68 ---
    lda #3
    sta NUSIZ0
    sta NUSIZ1
    ldx #0
    lda #60
    jsr SetObjectXPos_b1
    ldx #1
    lda #68
    jsr SetObjectXPos_b1
    sta WSYNC
    sta HMOVE
    lda #$0E
    sta COLUP0
    sta COLUP1
    jsr FooterBand
    ldx #19                      ; band-1 tail: logo 11 + footer 18 = 29
.TkB1Bl:
    sta WSYNC
    dex
    bne .TkB1Bl

    ; ==================================================================
    ; Band 2 (48 lines): stage bottom row.
    ; ==================================================================
    lda PF0Buf+2
    sta PF0
    lda PF1Buf+2
    sta PF1
    lda ColupfBuf+2
    sta COLUPF
    lda BandTab+2
    sta ENABL
    lda PF2Buf+2
    sta PF2
    ldx #48
.TkB2Bl:
    sta WSYNC
    dex
    bne .TkB2Bl

    ; --- HUD band: score shows level+1 (DropArm .DATitle), lives/bombs/bar ---
    lda #0
    sta ENABL
    sta ENAM1
    jmp MenuMain

TitleFont:
    ; slot 1 "S."
    .byte %00000000
    .byte %01110001
    .byte %00001001
    .byte %00001001
    .byte %01110000
    .byte %10000000
    .byte %10000000
    .byte %01110000
    ; slot 2 "A."
    .byte %00000000
    .byte %10001001
    .byte %10001001
    .byte %10001001
    .byte %11111000
    .byte %10001000
    .byte %10001000
    .byte %01110000
    ; slot 3 "V."
    .byte %00000000
    .byte %00100001
    .byte %01010001
    .byte %10001001
    .byte %10001000
    .byte %10001000
    .byte %10001000
    .byte %10001000
    ; slot 4 "I."
    .byte %00000000
    .byte %11111001
    .byte %00100001
    .byte %00100001
    .byte %00100000
    .byte %00100000
    .byte %00100000
    .byte %11111000
    ; slot 5 "O."
    .byte %00000000
    .byte %01110001
    .byte %10001001
    .byte %10001001
    .byte %10001000
    .byte %10001000
    .byte %10001000
    .byte %01110000
    ; slot 6 "R."
    .byte %00000000
    .byte %10001001
    .byte %10010001
    .byte %10100001
    .byte %11110000
    .byte %10001000
    .byte %10001000
    .byte %11110000

; ------------------------------------------------------------------------------
; TitleSelect — MOVED to bank1 (refactor_v4_plan Phase 3.1 canary, 2026-10-16).
; Entered via CallPad_TitleSelect ($FC4F); returns C=1 edge / C=0 no-edge.


; ------------------------------------------------------------------------------
; TitleIntro — intro-screen ($FD) edge check. Entered by JMP from DropStep
; (no pending return; tail-jumps out — never rts, or it would pop a stale
; frame return). Any SELECT/RESET press (level-triggered, prev-released via
; StepsLeft): DropTarget=$FF (old title) + jsr DropArm (.DATitle pose/score
; — the room is ALREADY loaded from boot LoadLevel, no deep LoadLevel:
; stack depth DropStep→TitleIntro→DropArm keeps sim_bomb_fuse min-SP).
; Always re-samples StepsLeft (title-owned on intro/title frames;
; RefreshEnemyY's idle-only guard never touches it during gameplay... its
; gameplay latch writes StepsLeft only when DropTarget==0 — intro frames
; have DropTarget=$FD so ownership stays clean).
; Clobbers A/X/Temp. Ends at TitleTailAudio (silence + overscan wait).
; ------------------------------------------------------------------------------

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
    lda #<(FooterFont+14)
    sta FooterPtr2
    lda #<(FooterFont+28)
    sta FooterPtr3
    lda #<(FooterFont+42)
    sta FooterPtr4
    lda #<(FooterFont+56)
    sta FooterPtr5
    lda #<(FooterFont+70)
    sta FooterPtr6
    ldx #13
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
    rts

FooterFont:
    ; generated by tools/footer_font.py — DO NOT EDIT
    ; "2026 Iuri / Fiedoruk" (two lines, 3x5 glyphs) packed into
    ; the 48px x 13-row footer canvas (6 x 14-byte sprites,
    ; FooterBand .FooterLoop: Y=13..1).
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $EE, $8A, $EA, $2A, $EE    ; sprite 0 (x 0-7)
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00, $EE, $8A, $EE, $28, $EE    ; sprite 1 (x 8-15)
    .byte $00, $22, $22, $32, $20, $3A, $00, $00, $00, $3B, $12, $12, $12, $3A    ; sprite 2 (x 16-23)
    .byte $00, $EE, $8A, $EE, $A2, $E2, $00, $00, $00, $A2, $A2, $A2, $A8, $B2    ; sprite 3 (x 24-31)
    .byte $00, $E8, $A8, $A8, $AA, $EC, $00, $00, $00, $00, $00, $00, $00, $00    ; sprite 4 (x 32-39)
    .byte $00, $EA, $AC, $AC, $AC, $AA, $00, $00, $00, $00, $00, $00, $00, $00    ; sprite 5 (x 40-47)

    .ds $F35A - *, 0            ; title movie art/bands retired
                                 ;   (merged title screen, 2026-10-19)

; ==============================================================================
; Title music player (2026-10-16; merged title screen 2026-10-19). Ticked once
; per title frame from TitleTailAudio via CallPad_MusicTick (bank0<->bank1
; @ $FC61). Plays the original theme "Hollow Earth".
; Packed one byte per step (2026-10-20, was 102 B of (duration,note) pairs):
;   byte = note_code*4 + duration_code
;   note_code = AUDF, $3E = rest, $3F = loop; duration_code indexes MelDur.
; Data is GENERATED by tools/gen_intro_theme.py from the readable pairs.
; AUD0 = Lead ($0C), volume 7, single voice.
; ==============================================================================
MelPtr   = $9D
MelTimer = $9E

MusicTick:
    lda #0
    sta AUDV1                   ; bass voice off (melody only)
    ldx MelPtr
    lda MelTimer
    beq .MelLoad
    dec MelTimer
    lda MusicMel,X              ; re-assert the current note (survives SFX);
                                ;   MelPtr already points at the NEXT step, so
                                ;   this mirrors the pre-pack (duration,note)
                                ;   player's MusicMel+1,X read, keeps the same
                                ;   audible melody
    lsr
    lsr                         ; note code = AUDF / $3E rest / $3F loop
    jsr MelApply
    jmp ReturnPad
.MelLoad:
    lda MusicMel,X
    and #3
    tay
    lda MelDur,Y                ; duration code -> frames
    sta MelTimer
    lda MusicMel,X
    lsr
    lsr
    cmp #$3F                    ; loop step (duration 0, so never re-asserted)
    beq .MelLoop
    jsr MelApply
    txa
    clc
    adc #1
    sta MelPtr
    jmp ReturnPad
.MelLoop:
    lda #0
    sta MelPtr
    jmp ReturnPad

; MelApply: A = note code. Starts the Lead at that pitch, or silences AUD0 on
; a rest ($3E). $3F (loop) HOLDS the tone the load frame started - the old
; paired player's `cmp #$FF / beq .MelDone` arm, kept for an identical melody.
MelApply:
    cmp #$3F
    beq .MAHold
    cmp #$3E
    beq .MAOff
    sta AUDF0
    lda #$0C                    ; Lead
    sta AUDC0
    lda #7
    sta AUDV0
    rts
.MAOff:
    lda #0
    sta AUDV0
.MAHold:
    rts

    include "art/intro_theme.asm"

; $F3E3-$F41E is free (the packed theme reclaimed 2026-10-20). M1StripBlast
; stays pinned at $F41F because bank1's TallyEntry address is hand-copied into
; kernel.asm's TallyTramp EQU and tools/test_bomb_strip.py pins this label;
; new bank1 leaves can go in this hole.
    .ds $F41F - *, 0

; ------------------------------------------------------------------------------
; M1StripBlast — Phase 4 M1 strip blast (moved from bank2 2026-10-20, repack
; chunk 2). Reads ZP ONLY (RectCount / RoomMetaA-B / EnemyDeadMask /
; BMWScratch), so it runs here and the old two-hop pad chain
; (.BMWDone -> pad $F9AC -> bank2 -> pad $F9B2) collapses to a same-bank
; jal: BombMarkWalls .BMWDone -> M1StripBlast -> StripBlastCheck, 0 switches.
; Staging contract (both scratch bytes free in this flow):
;   RectCount := 2ℓ left-strip dcol, or $FF = none/door/right-bomb;
;   BMWScratch ($88 = kernel Temp, NOT bank1's Temp $AD) := $FF when MetaB
;   b7 (right door) so the ball-strip take can never fire. Key pickup (P5)
;   sets b3/b4 for doors instead (comment hook at the takes).
; ------------------------------------------------------------------------------
M1StripBlast:
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
                                ;   high end — StripBlastCheck rejects)
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
    sty BMWScratch              ; $88 = StripBlastCheck's "no strip"
.M1SBout:
    jmp StripBlastCheck         ; same bank now (was the $F9B2 pad)

; ------------------------------------------------------------------------------
; TallyEntry — level-bonus tally body (moved from bank2 2026-10-20, repack
; chunk 3: it touches ZP/TIA only, and the tally frame runs the bank1 HUD
; anyway). Entered from bank0's TallyTramp ($FFE6) via jsr; tail-jmps
; ReturnPad ($FBF8, bank1 copy) so A (and Z) survive back to the bank0 caller.
;   DropTarget == 0 (pickup frame) -> ARM: snapshot the bonus into TallyTicks
;     in 50-pt units — 20 = miner (1000), (BarLevel+3)/6 = remaining time
;     (50% -> 10 ticks -> 500), 1/bomb, 2/life — then arm the 4-frame pace
;     divider (TickCounter), clear jet/beam, set DropTarget = $FE.
;   DropTarget == $FE (every frame) -> STEP: dec TickCounter; on 0 reload 4,
;     dec TallyTicks. Event A: b0 = add 50, b1 = coin tone written here
;     (AUDC/F/V + BombSnd=8; bank0 TallyWork's UpdateBombSound holds it,
;     coin = every 4 ticks = 200 pts), b2 = done (last tick consumed).
; The old hard `org $F313` pin and bank2's `org $F880` TallySum slot are gone
; with the move; both bodies now flow in bank1's $F41F-$F53F fill.
; ------------------------------------------------------------------------------
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
                                ; PlayerBombs needs the split helper below)
    lda #4
    sta TickCounter             ; fresh pace divider
    lda #0
    sta JetPower                ; frozen frame: no thrust flutter
    sta LaserX                  ; drop any live beam (travel restarts on press)
    lda #$FE
    sta DropTarget
    lda #0
    jmp ReturnPad

; TallySum — the level-bonus total for TallyEntry (frozen-scene frame).
; Split out of the inline region in bank2 (which ended at a hard org); now a
; same-bank jsr in the same fill.
TallySum:
    lda PlayerBombs
    and #%00000111              ; bombs only, never the raft ramp bits
    sta BMWScratch              ; $88 = kernel Temp — NOT bank1's Temp ($AD =
                                ; TickCounter: writing it stalls the game timer)
    txa
    clc
    adc #20                     ; miner reach = 1000 pts
    adc BMWScratch              ; + 50 per unspent bomb (chain carry ok)
    sta TallyTicks
    lda PlayerLives
    asl                         ; + 100 per life = 2 ticks
    clc
    adc TallyTicks
    sta TallyTicks
    rts

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
LevelPFDataLo = $9F              ; level block base (C4: conn/enemy ptrs are
LevelPFDataHi = $A0              ;   block offsets +2n/+4n/+5n now)
LevelRoomN  = $A1                ; rooms in the level (C4 2026-10-20)
FetchPtr    = $E5                ; moved S3.2 (was $E0) — must match kernel
EnemyRamD   = $C1
EnemyRamX   = $BD           ; 3 bytes live enemy X (slots 0-2) — raft body
EnemyRamY   = $E2           ; 3 bytes live enemy Y (private since S3.4)
vyLo        = $93           ; Y velocity lo (signed 16) — raft riding pins it
vyHi        = $94           ; Y velocity hi
PF0Buf      = $C3
PF1Buf      = $C6                ; packed rows 0-2 (S3.1; was $CF)
PF2Buf      = $C9                ; packed rows 0-2 (S3.1; was $DB)
ColupfBuf   = $E7                ; BuildColupF image (VBL, 12 bytes)
BandTab     = $ED                ; per-band ENABL gate (VBL StageBandTab)
EnemyRamP   = $C2                ; free-running frame clock (player walk)
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
                                 ; check_equ_sync pair); M1StripBlast restages
                                 ; it as the left-strip dcol (2ℓ / $FF) that
                                 ; StripBlastCheck's left take reads
BombPacked = $B5                ; state+DownPrev+WallMask (b3-6)
RoomMetaA = $99                 ; staged MetaA (hand-copy of bank2's EQU —
RoomMetaB = $9A                 ;   M1StripBlast reads the door/m1 nibbles)
LaserX     = $83                 ; hand-copy: TallyEntry drops a live beam
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
    ; Full (BarLevel >= BAR_MAX-7 = 113..120): pure yellow, no red write.
    ; The 8-dec hold (bugs.md #30, 2026-10-11) delays the FIRST red until
    ; t=8s = exactly one chunk period (K=8), so the first red appears on
    ; the same cadence as every later chunk. Chunks are 3-4c (9-12px) so
    ; the bite (14px incl. the F4 top-block render offset) is ~1.2x a
    ; chunk instead of the reported 5-6x.
    ; H3c dual path: F=0 slim / F=1 slim+nop / F=2,3,4 full dispatch.
    ; dispatch ≤73c from the TopGap WSYNC to the first bar WSYNC.
    ; ====================================================================
    lda BarLevel
    cmp #(BAR_MAX-7)
    bcc .BarRedSetup    ; B < 117 → red path (short fwd branch)
    ldx #3
.YLoop:
    sta WSYNC
    lda #$1C            ; yellow (hue 1, luma 6)
    sta COLUPF
    dex
    bne .YLoop
    jmp .BarGap

.BarRedSetup:
    ldy BarIdx          ; precomputed (BarLevel+7)>>3, synced in kernel overscan
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
    and #%00000111      ; b7-3 = the raft's ramp state, not bombs (see kernel)
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
    and #%00000111      ; mask the raft's ramp bits out of the count
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
    ; at $FD.. — bank1's pre-pad region is tight, nothing fits).
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
; D2 (2026-10-16): both tables were EXACTLY period-8 ([1-8],[9-16],…) so
; they shrank 121→15 entries, indexed (B+7)>>3 (see the reader). Entry 0 =
; B=0; entry g≥1 = B in [8(g-1)+1, 8g]. Verified against the old 121B blobs.
BarDelayTable:          ; (B+7)>>3, 15 entries
    .byte 0, 2,3,2,4,5,2,5,7,8,5,8,10,11,8
BarFineTable:           ; (B+7)>>3, 15 entries; ∈{0,1,2,3,4}
    .byte 2, 1,0,2,1,0,4,2,1,0,4,2,1,0,4

; ------------------------------------------------------------------------------

; ==============================================================================
; Raft (enemy type 7) — the moving, rideable platform. plans/raft_moving_plan.md
; ==============================================================================
; Entrance: bank0 UEDispatch -> CallPad_RaftBody (sta $1FF7 / jmp $F822) -> here;
; exit: jmp ReturnPad ($FBF8, bank1's twin) -> bank0's jmp UE_Next.
; CallPad rules honoured: no nested CallPad, no bank0 jsr, ZP is shared RAM.
; ZP ALIAS WARNING: this code uses bank0's Temp at $88 (free here — every other
; overscan Temp consumer, the joystick read and the hot-bump flag, ran before
; UpdateEnemies). It must NEVER touch bank1's Temp symbol ($AD = bank0's
; TickCounter — writing that would stall the game timer).
;
; User spec 2026-10-18: floats only on water; carries the player across and
; returns; ~1.5x the player's 1 px/frame; inertia when it starts.
;   Y       = the water surface, NOT the authored y and NOT a constant: the
;             surface line drifts 0-3 lines with the TIDE (VBL stages 36+off
;             into CollisionX, kernel draws the strip as the band's last
;             (12-off) lines), so the raft is placed at 125+off and its bottom
;             row sits exactly on the moving surface — it rides the wave the
;             water does. The rider's pin (top-12 = 113+off, worst case 116)
;             stays clear of the 125 water-kill line at every tide phase.
;             This write lands after RefreshEnemyY, so the VBL draws it.
;   Speed   = 1 px on even frames, 2 px on odd (EnemyRamP parity) = 1.5 px/frame.
;   Inertia = a real spin-up ramp: 1 px/frame for ~30 frames (~0.5 s) then the
;             full 1/2 parity (1.5 avg), so the take-off is heavy. The state
;             lives in PlayerBombs' ($F0) spare high bits (b7 = ridden flag,
;             b6-b3 = level) — the ZP map has no free byte and the bomb count
;             keeps b2-0 (see the kernel EQU contract). Stepping off clears the
;             flag+level, so the empty raft runs at full speed and the next
;             take-off ramps again. It also holds the frame it turns around on.
;   Range   = derived from the playfield, no data and no ZP: the model row-2
;             cell just beyond the raft's leading edge is read from the PF row-2
;             buffers and a SOLID cell turns it around, so the raft patrols
;             exactly the open water span of the room.
;   Ride    = the raft is a FERRY: it moves ONLY while the player's box overlaps
;             its upper rows; step off and it parks immediately (the ramp state
;             is cleared too, so the next take-off ramps again). While over it a
;             non-rising player (vyHi >= 0) is pinned to the raft's top with vy
;             zeroed (gravity must never accumulate into the water) and carried
;             by the raft's step; thrust up skips the pin but keeps the carry, so
;             flying off is always possible. Leaving and re-entering the ROOM
;             resets the raft to its authored spawn x (LoadEnemyRam re-copies
;             it), which is the "reset" the user asked for.
; In: X = enemy slot. Clobbers A/Y and bank0 Temp ($88).
; ==============================================================================
; RaftCellSolid — is the model row-2 (water row) playfield cell in display
; column A solid? Reflect mapping: CTRLPF $35 (reflect) is the cave default and
; a raft room has no door/bar band to switch it off. IN: A = display col 0..39.
; OUT: Z=1 open (water) / Z=0 solid. Clobbers A/Y.
;   cols 0-3   -> PF0 row 2 ($C5), bit 4+col (PF0 bit 4 = leftmost pixel)
;   cols 4-11  -> PF1 row 2 ($C8), bit 7-(col-4)
;   cols 12-19 -> PF2 row 2 ($CB), bit col-12
;   cols 20-39 -> the mirrored half: source = 39-col
RaftCellSolid:
    cmp #20
    bcc .RCSrc
    eor #$ff
    clc
    adc #40
.RCSrc:
    tay
    lda RaftCellMasks,Y
    cpy #4
    bcs .RCPF1
    and $C5
    rts
.RCPF1:
    cpy #12
    bcs .RCPF2
    and $C8
    rts
.RCPF2:
    and $CB
    rts

RaftBitTab:                     ; 1 << slot (EnemyBitTable is bank0's ROM, so a
    .byte $01, $02, $04, $08    ; 4-byte copy keeps this body bank-local)

RaftCellMasks:                  ; mask for source column 0..19: PF0 cols 0-3 —
    .byte $10, $20, $40, $80    ; PF0 cols 0-3 (bit 4 = leftmost), then
    .byte $80, $40, $20, $10    ; PF1 cols 4-11 (bit 7 = leftmost)
    .byte $08, $04, $02, $01    ; PF2 cols 12-19 (bit 0 = leftmost)
    .byte $01, $02, $04, $08
    .byte $10, $20, $40, $80
; ------------------------------------------------------------------------------
; CallPad_RaftBody twin — BYTE-IDENTICAL with kernel.asm's copy at $F8C0 (guard:
; verify_build.check_raft_tramp). bank0 executes `sta $1FF7` at $F8C0-$F8C2 and
; the fetch at $F8C3 comes from THIS bank: `jmp $FDE3` = RaftBody below. Neither
; bank runs the other's half — bank0's operand bytes are never fetched, bank1's
; `sta $1FF7` is never executed (it is only the swapped-out image's prefix).
; In bank1's $F822-$F8C6 fill; StripBlastCheck follows it directly ($F937 pin
; deleted 2026-10-20 — the body floats and the $F9AC pin bounds the leaves).
; ------------------------------------------------------------------------------
    .ds $F8C0 - *, 0
    .byte $8D, $F7, $1F         ; sta $1FF7 (twin)
    .byte $4C, $E3, $FD         ; jmp $FDE3 (twin — fetched post-switch)

; ($F937 pin DELETED 2026-10-20, audit round 2: it pinned bank2's
;  M1StripBlast back-jmp operand, and that body is same-bank now — the chain
;  is .BMWDone -> M1StripBlast -> StripBlastCheck inside bank1, so
;  StripBlastCheck is reached by label and floats. It now starts right after
;  the raft tramp twin; the $F9AC pin still bounds the sound-leaf block.)
; StripBlastCheck — Phase 4: bomb blast vs the D6 patch strips. Tail-jumped
; from BombMarkWalls .BMWDone through M1StripBlast (same bank, label `jmp`s
; — repack chunk 2; 0 pushes, no switch). Still 0 pushes (the jsr+pha
; version measured SP $F7 < the $F8 gameplay guard, and the pha leaked on the
; early-exit path -> runaway work -> 309-line frames in Stella 2026-10-04).
; Every exit ends in ReturnPad with A = count.
; In: BMWScratch = strip left col pL in RIGHT-half space ($FF = none/sym,
; captured before the punch loop), CollisionEndX/CellX = blast window in
; LEFT-half space (bomb col mirrored at BMW entry), CollisionX = count.
; Overlap after mirroring (39-x) with the strip not yet dead → set
; EnemyDeadMask b3 (ball strip; b4 = M1 strip, set by M1StripBlast) and
; inc the count (caller's +75 loop scores it). The
; kill bits die with the room (EnterRoom zeroes EnemyDeadMask) — same
; lifecycle as WallMask holes (D1-B). P2b door models never
; reach .SBtake: M1StripBlast (bank2, runs first) stashes BMWScratch :=
; $FF when MetaB b7 — the take's window test then falls into .SBdone.
; Key pickup (P5) sets b3/b4 for doors instead (key-only unlock).
; ------------------------------------------------------------------------------
StripBlastCheck:
    ; --- P2b left strip take (staged by bank2 M1StripBlast) --------------
    ; RectCount = 2ℓ left dcol, $FF = none / left door / right bomb.
    ; Window is still LEFT-half here (the mirror below). Door models stage
    ; $FF both ways (MetaA b3 / MetaB b7) so neither take runs — key (P5)
    ; sets b3/b4 instead.
    lda RectCount
    bmi .SBright                ; $FF → no left strip this frame
    lda CollisionCellX          ; blast hi
    cmp RectCount
    bcc .SBright                ; hi < 2ℓ → strip right of the blast
    lda CollisionEndX           ; blast lo (C=1 from the hi cmp)
    sbc RectCount               ; lo - 2ℓ (borrow ⇒ lo < 2ℓ)
    bcc .SBleftTake             ; blast starts left → overlap
    cmp #2
    bcs .SBright                ; lo >= 2ℓ+2 → blast ends left of strip
                                ;   (A=0/1 falls into take = overlap)
.SBleftTake:
    lda EnemyDeadMask
    and #$10
    bne .SBright                ; already destroyed → no double score
    lda #$10
    ora EnemyDeadMask
    sta EnemyDeadMask           ; b4 = M1 strip destroyed (room-scoped)
    inc CollisionX              ; +1 wall for the caller's score loop
.SBright:
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
    jmp ReturnPad                   ; ReturnPad → bank0 caller (0 push)

; ($F9AC pin DELETED 2026-10-20, audit round 2: the shared 12 B M1-hop pad
;  died with the M1StripBlast move — .BMWDone -> M1StripBlast ->
;  StripBlastCheck is same-bank now, so $F9AC held no byte.)

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
    jmp ReturnPad

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
    jmp ReturnPad

BombSndDrop:
    lda #6
    sta BombSnd
    lda #4                      ; square
    sta AUDC0
    lda #10
    sta AUDF0
    lda #8
    sta AUDV0
    jmp ReturnPad

BombSndExplode:
    lda #30
    sta BombSnd
    lda #8                      ; noise
    sta AUDC0
    lda #0
    sta AUDF0
    lda #10
    sta AUDV0
    jmp ReturnPad

; ========================================================================
; Leaf routines relocated from bank0 — batch B (leaf_move_plan)
; ========================================================================

; GetConnIdx RETIRED (C3, 2026-10-20): the four exit handlers moved to
; bank2 and read the connection record in-bank (LevelConnB2), so this pad's
; body had no caller. Deleting it (plus the bank0 `sta` half and this bank's
; `jmp` half) reclaimed 15 B here and removed a live-but-uncalled pad.

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
    jmp ReturnPad

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
    jmp ReturnPad

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
    jmp M1StripBlast            ; same bank (repack chunk 2, 2026-10-20):
                                 ; M1StripBlast stages the left-strip dcol and
                                 ; sets b4, then tail-jmps StripBlastCheck.
                                 ; Still 0 push — SP guard unchanged; the
                                 ; check ends in ReturnPad with A = count.

; ABWXTab/ABWWTab/ABWYTab/ABWHTab/BombMaskBit live at $F010 (top-of-bank
; fill gap) — relocated 2026-10-10 when the BMW span fix overflowed the
; $FBF8 pin. Only BombMarkWalls indexes them (abs,X/Y), no cross-bank
; operand points at them.

; ========================================================================
; Cross-bank call pads — 2026-10-20 (chunk 4): SPLIT across the banks, no
; twin. kernel.asm holds the eleven `sta $1FFx` halves compactly at
; $FBFC..$FC1C; after the switch the fetch at A+3 lands HERE, so this bank
; keeps only the `jmp` halves (at A+3, i.e. $FBFF onward). The reverse halves
; were dead bytes: no bank1/bank2/bank3 code calls a CallPad (guard:
; verify_build.check_callpads rejects any `jsr/jmp CallPad_*` outside
; kernel.asm). F6 hotspot ignores the written value, so a pad still passes
; A/X/Y/flags through untouched (`sta` affects no flag).
;   $FBFF <-$FBFC+3 UpdateBombSound      $FC0E <-$FC0B+3 AddScore
;   $FC02 <-$FBFF+3 UpdateJetSound       $FC11 <-$FC0E+3 IsRoomDark
;   $FC05 <-$FC02+3 BombSndDrop          $FC14 <-$FC11+3 SetRoomDark
;   $FC08 <-$FC05+3 BombSndExplode       $FC17 <-$FC14+3 UpdateLaserSound
;   ($FC0B retired by C3)               $FC1D <-$FC1A+3 BombMarkWalls
; $FC1A (BuildColupF's +3) belongs to BANK3 — its pad is `sta $1FF9`.
; ========================================================================
    .ds $FBF8 - *, 0
ReturnPad:
    sta $1FF6                   ; the `rts` at $FBFB is served by bank0
    .ds $FBFF - *, 0
    jmp UpdateBombSound
    jmp UpdateJetSound
    jmp BombSndDrop
    jmp BombSndExplode
    .byte 0,0,0                 ; $FC0B: GetConnIdx's half, retired by C3
    jmp AddScore                ; label, not the literal: bank1 shifts move it
    jmp IsRoomDark
    jmp SetRoomDark
    jmp UpdateLaserSound        ; label, not the literal (bank1 shifts)
    .ds $FC1D - *, 0            ; ($FC1A is bank3's BuildColupF image)
    jmp BombMarkWalls           ; S5.2: body lives in bank1 ($FB10)

; CallPad tail pads (2026-10-20: SPLIT across the banks, no twin). kernel.asm
; holds the three `sta $1FF7` at $FC4F/$FC52/$FC55; after the switch the fetch
; at A+3 lands HERE, so bank1 keeps only the `jmp` halves. Nothing calls a
; tail pad from bank1, so bank1's `sta` halves and bank0's `jmp` halves were
; dead bytes — reclaiming them gave bank0 15 B of pre-pad headroom.
;   $FC52 <-$FC4F+3 CallPad_TitleSelect
;   $FC55 <-$FC52+3 CallPad_TitleBand
;   $FC58 <-$FC55+3 CallPad_MusicTick
; Guard: verify_build.check_callpads (per-pad A / A+3 contract).
    .ds $FC52 - *, 0
    jmp TitleSelect
    .ds $FC55 - *, 0
    jmp $F080                   ; TitleBand
    .ds $FC58 - *, 0
    jmp MusicTick

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
    jmp $F18A           ; Overscan in bank0 (must match bank0 ToGameStub;
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
    jmp ReturnPad
.IRDhi:
    cmp #8
    bcs .IRDlit                 ; rooms 8+ never dark (no mask bit)
    tax
    lda BitMaskTable,X          ; $10/$20/$40/$80
    lsr
    lsr                         ; → $04/$08/$10/$20 = LaserState b2-5
    and LaserState
    jmp ReturnPad
.IRDlit:
    lda #0                      ; Z=1 → lit
    jmp ReturnPad

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
    jmp ReturnPad
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
    jmp ReturnPad

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
; once per banner frame. Lives with the glyphs (bank1's pre-pad region is
; tight; the score section is a jsr here from MenuMain).
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
; CallPad_MothYDerive twin — byte-identical with kernel.asm at $FEE7
; ========================================================================
    .ds $FDE3 - *, 0
RAFT_MIN_X    = 8               ; the raft's logical X is its lit span's right
RAFT_MAX_X    = 148             ; end, exactly like the player's [x-7,x]; these
                                ; rails keep it inside the room
RAFTER_BASE   = 125             ; raft top when the tide is at 0 = the water
                                ; surface (line 132) - 7, so its BOTTOM row
                                ; sits exactly ON the surface. The live value is
                                ; RAFTER_BASE + off (see the tide block below) —
                                ; never hard-code the Y: the surface MOVES.
RAFTER_XOFF   = 6               ; PLAYER_WIDTH-1: spawn x of the body span
RAFTER_XSPAN  = 14              ; PLAYER_WIDTH+ENEMY_WIDTH-1: no-overlap gate
RAFTER_YSPAN  = 18              ; PLAYER_SPRITE_H+6: riding when the feet are
                                ; from 12 px above the raft's top to 5 px into it
RAFTER_PINFIT = 12              ; PLAYER_SPRITE_H: pin = raft top - this

RaftBody:
    ; --- float ON the water surface, riding the TIDE ------------------------
    ; The water band's surface drifts 0-3 lines (the tide): the VBL stages
    ; 36+off into CollisionX and the kernel draws the strip as the band's last
    ; (12-off) lines, so the surface line is 132+off. The raft's bottom row
    ; (top+7) must land ON that line -> top = 125+off. This mirrors the VBL's
    ; triangle EXACTLY (p = EnemyRamP>>4: p0-3 down 0->3, p4-7 up 3->0,
    ; p8-15 rest), and this frame's EnemyRamP inc runs before UpdateEnemies,
    ; so both sides see the same p — the raft bobs with the water it floats on.
    ; CollisionX itself is unusable here: the input rect-walks clobber it
    ; before UpdateEnemies runs. Keep the two formulas in step (AGENTS).
    lda EnemyRamP
    and #$F0
    beq .RaftTide               ; p=0 -> off 0 (A already 0)
    lsr
    lsr
    lsr
    lsr                         ; A = p (1..15)
    cmp #8
    bcc .RaftTideTri
    lda #0                      ; rest phase p8-15
    beq .RaftTide               ; always
.RaftTideTri:
    cmp #4
    bcc .RaftTide               ; p1-3: off = p
    eor #$FF
    sec
    adc #7                      ; p4-7: off = 7-p
.RaftTide:
    clc
    adc #RAFTER_BASE            ; + 125 -> the surface line (132+off) minus 7
    sta EnemyRamY,X             ; the authored y is ignored on purpose: the
                                ; water line is what the raft floats on

    ; --- does the player count as "over the raft"? --------------------------
    ; The raft is a FERRY (user rule 2026-10-18): it moves ONLY while he is over
    ; it, parks the moment he steps off, and its position resets on room entry
    ; (LoadEnemyRam re-copies the record's spawn x). Gating the whole motion
    ; block here is what makes it park; the pin/carry later still applies while
    ; riding. The test runs against the CURRENT x (before the step), i.e. the
    ; raft he is actually standing on.
    lda RoomX
    sec
    sbc EnemyRamX,X
    clc
    adc #RAFTER_XOFF
    cmp #RAFTER_XSPAN
    bcs .RaftNoRide             ; no X overlap: nobody aboard
    lda RoomY
    sec
    sbc EnemyRamY,X
    clc
    adc #RAFTER_PINFIT
    cmp #RAFTER_YSPAN
    bcs .RaftNoRide             ; not in the raft's upper rows
    lda vyHi
    bmi .RaftNoRide             ; rising: let him fly away (no pin)
    jmp .RaftGo
.RaftNoRide:
    ; nobody over the raft: PARK it (no motion) and clear the ramp state so the
    ; next take-off ramps again; the bomb count in b2-0 is preserved
    lda $F0
    and #%00000111
    sta $F0
    jmp ReturnPad
.RaftGo:
    ; --- take-off ramp (inertia): heaviest right after boarding -------------
    ; State = PlayerBombs' ($F0) spare HIGH bits: b7 = "ridden last frame",
    ; b6-b3 = the ramp level (0-15); b2-0 stay the bomb count. Adding $10 never
    ; carries into b2-0, and the drop's `dec` is guarded by a non-zero count so
    ; it cannot borrow upward either (see the kernel EQU for the contract).
    ; Riding advances the level every 2nd frame: the raft leaves at 1 px/frame
    ; and reaches the full 1/2 parity (1.5 avg) after ~30 frames (~0.5 s), the
    ; heavy take-off. Empty (b7 clear) or level 15: full speed straight away.
    lda $F0
    bpl .RaftAtSpeed            ; b7 clear = nobody aboard -> no ramp
    cmp #%11111000              ; flag + all four level bits = spun up
    beq .RaftAtSpeed
    lda #1                      ; still ramping: 1 px/frame
    bne .RaftHaveStep           ; always
.RaftAtSpeed:
    lda EnemyRamP
    and #1
    clc
    adc #1                      ; 1 px even frames, 2 px odd = 1.5 px/frame
.RaftHaveStep:
    sta $88                     ; bank0 Temp = this frame's step
    lda RaftBitTab,X
    and EnemyRamD
    beq .RaftLeft
    ; ---- leading edge right: candidate = x + step ---------------------------
    lda EnemyRamX,X
    clc
    adc $88
    bcs .RaftTurn               ; wrapped past 255
    cmp #RAFT_MAX_X
    bcs .RaftTurn               ; right rail
    clc
    adc #1                      ; the cell just beyond the right edge
    lsr
    lsr
    jsr RaftCellSolid
    bne .RaftTurn               ; solid ahead (ledge / room edge) -> turn
    lda EnemyRamX,X
    clc
    adc $88
    sta EnemyRamX,X
    jmp .RaftRide
    ; ---- turn-around (kept here: both arms branch to it, and the ramp pushed
    ; ---- it past the 127-byte relative reach when it sat at the very end) ----
.RaftTurn:
    lda RaftBitTab,X
    eor EnemyRamD
    sta EnemyRamD               ; flip this slot's dir bit (the high nibble is
                                ; bank1's RoomDarkMask — must be preserved)
    jmp ReturnPad               ; and the turn costs this frame (the inertia)
    ; ---- leading edge left --------------------------------------------------
.RaftLeft:
    lda EnemyRamX,X
    sec
    sbc $88
    bcc .RaftTurn               ; wrapped below 0
    cmp #RAFT_MIN_X
    bcc .RaftTurn               ; left rail
    sec
    sbc #8                      ; the cell just beyond the left edge
    bcs .RaftLeftCol
    lda #0
.RaftLeftCol:
    lsr
    lsr
    jsr RaftCellSolid
    bne .RaftTurn
    lda EnemyRamX,X
    sec
    sbc $88
    sta EnemyRamX,X
    ; ---- carry + pin while the player is aboard -----------------------------
.RaftRide:
    lda vyHi
    bmi .RaftNoPin              ; rising: pin skipped, carry still happens
    lda EnemyRamY,X
    sec
    sbc #RAFTER_PINFIT
    sta RoomY                   ; feet on the raft's top
    lda #0
    sta vyLo
    sta vyHi                    ; landing kills the accumulated fall speed
.RaftNoPin:
    ; ramp: arm the flag, and +1 level every 2nd frame (capped at 15)
    lda $F0
    ora #%10000000
    sta $F0
    lda EnemyRamP
    lsr                         ; C = the frame-parity bit
    bcs .RaftCarry              ; odd frame: flag only this time
    lda $F0
    and #%01111000
    cmp #%01111000
    beq .RaftCarry              ; already spun up
    lda $F0
    clc
    adc #%00010000
    sta $F0
.RaftCarry:
    lda RaftBitTab,X
    and EnemyRamD
    beq .RaftCarryL
    lda RoomX
    clc
    adc $88
    sta RoomX
    jmp .RaftDone
.RaftCarryL:
    lda RoomX
    sec
    sbc $88
    sta RoomX
    jmp .RaftDone
.RaftDone:
    jmp ReturnPad

    .ds $FEE7 - *, 0
    sta $1FF7
    jmp $F029

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

; ------------------------------------------------------------------------------
; Tally entry tramp slice ($FFE6-$FFEB) — byte-identical with kernel.asm's
; copy at the same address (F6 pad rule). bank0 executes `sta $1FF7` at
; $FFE6-$FFE8; the fetch at $FFE9 comes from THIS bank = `jmp TallyEntry`
; ($F44F — moved here from bank2, repack chunk 3, 2026-10-20). Neither bank
; runs its other half. $FFF2-$FFF9 stay fill (hotspot mirrors).
; ------------------------------------------------------------------------------
    .ds $FFE6 - *, 0
TallyTramp_b1:
    sta $1FF7
    jmp TallyEntry

; ========================================================================
; Interrupt vectors
; ========================================================================
    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
