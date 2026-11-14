    processor 6502
    seg code
; ==============================================================================
; NEW ROM bank 3 - GAMEPLAY CODE (docs/agents/banks.md, Layout v3).
; From the old ROM: the raft, the strip blasts, ClearPFColumn, BombMarkWalls (old bank1) and the cave
; kernel's VBL PROLOGUE (old bank7). (Stage band + colour build stay with the extras walkers in bank 5:
; B3StageBand `jsr`s PhaseBlink, and a subroutine call cannot cross banks.)
; ==============================================================================
    include "colors.inc"
    include "banks.inc"
    include "generated/bank6_equs.inc"
    include "generated/cave_zp.inc"
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
LevelStartRoom = $A7     ; b7 = KeyHeld (bank0 owns it; read-only here)
BarLevel = $AE
BarIdx   = $9B           ; (BarLevel+7)>>3, synced by kernel overscan (D2)
BAR_MAX = 120            ; full bar (60 frames/step × 120 = 120s)
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
SWCHB       = $0282
StepsLeft   = $97               ; bank0 per-frame step latch (ZP byte block)
BombY       = $85               ; bank0 bomb Y; on the title it is the key-grace counter (TitleSelect)
LEVEL_COUNT = 32                 ; hand copy of kernel LEVEL_COUNT
RoomX        = $80
RoomY        = $81
PlayerDir    = $82
Grp0Ptr      = $86
Grp0PtrHi    = $87
BombTimer    = $F7
TallyTicks   = $F2
COLOR_CAVE_BG = NC_00
COLOR_HOT_Y  = NC_1C
COLOR_HOT_R  = NC_44
COLOR_BOMBS  = NC_46
COLOR_TITLE  = NC_6A
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
MelPtr   = $F6                  ; = kernel BombX   (dead on the title)
MelTimer = $F7                  ; = kernel BombTimer (dead on the title)
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
DropTarget  = $8A       ; hand-copy of kernel ZP byte (spawn drop-in / title /
Hover       = $9C       ; respawn hover (kernel ZP): $FF = armed/waiting for
HOVER_FRAMES = 90       ; 1.5 s at 60 Hz: the jet reaches lift in 1.0 s.
ScoreTh     = $F3       ; score 100k|10k digits, packed BCD (must match bank0)
ScoreHu     = $F4       ; score 1k|100 digits, packed BCD
ScoreTe     = $F5       ; score tens|ones, packed BCD
MAX_LIVES   = 8         ; extra life every 50,000 points, never above this
Level       = $A3       ; #18 current level, 0-based (must match kernel)
LevelShowTimer = $F2    ; #18 LV001 banner frames left (kernel sets, bank1 decs;
AUDC0       = $15
AUDC1       = $16
AUDF0       = $17
AUDF1       = $18
AUDV0       = $19
AUDV1       = $1A
SWCHA       = $0280
BombSnd     = $F1
HudPatB     = $E0                ; bombs-row scratch (HUD owns $E0-$EF; the score
HudEnam     = $E1                ;   pointers are written AFTER these rows)
HudPatM     = $E2
HudNus      = $E3                ; (RefreshEnemyY rewrites $E2-$E4 every overscan)
JetPower    = $96
TickCounter = $AD               ; kernel's 60-frame timer ($AC = PlayerLives!).
LaserState  = $C0       ; b7 fire held this frame, b5-2 = RoomDarkMask rooms
EnemyRamP   = $C2       ; free-running frame clock (bank0 RefreshEnemyY incs)
EnemyClk    = $D7       ; enemy clock (speed multiplier, kernel.asm)
RoomExits   = $DB       ; b1 = NO room to the west, b0 = NO room to the east (bank2
RoomNo      = $98
LevelPFDataLo = $9F              ; level block base = RoomShapes column (C2:
LevelPFDataHi = $A0              ;   pos/count/records are +n/+2n/+3n)
LevelRoomN  = $A1                ; rooms in the level (C4 2026-10-20)
LEVEL_FORMAT = $08               ; 2026-10-24: 7-bit shape index + band flag b7 (hand copy;
FetchPtr    = $E5                ; moved S3.2 (was $E0) — must match kernel
EnemyRamD   = $C1
EnemyRamX   = $BD           ; 3 bytes live enemy X (slots 0-2) — raft body
EnemyRamY   = $E2           ; 3 bytes live enemy Y (private since S3.4)
vyLo        = $93           ; Y velocity lo (signed 16) — raft riding pins it
vyHi        = $94           ; Y velocity hi
PF0Buf      = $C3
PF1Buf      = $C7                ; N=4 stride 4 (rows 0-3)
PF2Buf      = $CB                ; N=4 stride 4 (rows 0-3)
ColupfBuf   = $D3                ; BuildColupF image (N=4, 4 bytes)
BandTab     = $CF                ; per-band ENABL gate (N=4, 4 bytes)
EnemyRamP   = $C2                ; free-running frame clock (player walk)
CollisionX  = $8B
CollisionCellX = $8C
CollisionCellY = $8D            ; plan 5.1 punch: rect idx save across ClearPFColumn
CollisionEndY = $8F             ; plan 5.1 punch: last row (ClearPFColumn contract)
LineCount   = $84
BombX      = $F6                ; read-only here (see $F6 note above)
BMWScratch = $88                ; kernel Temp — NOT bank1's Temp ($AD)
CPCScratch = $89                ; ClearPFColumn AND-mask (plan 5.1b: was
RectCount  = $92                ; walk temp — BMW stashes the original screen
BombPacked = $B5                ; state+DownPrev+WallMask (b3-6)
RoomMetaA = $99                 ; staged MetaA (hand-copy of bank2's EQU —
RoomMetaB = $9A                 ;   M1StripBlast reads the door/m1 nibbles)
LaserX     = $83                 ; hand-copy: TallyEntry drops a live beam
EnemyDeadMask = $BA             ; b0-2 enemy kills (hand-copy of kernel's
CollisionEndX = $8E             ; blast lo
TILE_COLUMNS = 20
INPT4       = $0C       ; fire button (active low, bit 7)
JET_AUD_BASE = $0F           ; mirrors kernel.asm EQU (value guarded by tests)
JET_AUD_VOL  = $08
LASER_AUD_C  = 2             ; mirrors kernel.asm EQU: div-15 tone = low pitch
LASER_AUD_V  = 9
RAFT_MIN_X    = 8               ; the raft's logical X is its lit span's right
RAFT_MAX_X    = 148             ; end, exactly like the player's [x-7,x]; these
RAFTER_BASE   = 131             ; raft top when the tide is at 0: the 2-row
RAFTER_XOFF   = 6               ; PLAYER_WIDTH-1: spawn x of the body span
RAFTER_XSPAN  = 14              ; PLAYER_WIDTH+ENEMY_WIDTH-1: no-overlap gate
RAFTER_YSPAN  = 28              ; PLAYER_SPRITE_H+6: riding when the feet are
RAFTER_PINFIT = 22              ; PLAYER_SPRITE_H: pin = raft top - this
    org $F000
; power-up stub (mandatory in EVERY bank)
    lda #0
    sta BK_GENERAL

; ---- the cave kernel's PROLOGUE (from the old bank7) ----------------------------------------------
    include "generated/cave_luts.inc"
CaveFrameLo:    .byte <PlayerSpriteA,<PlayerSpriteB,<PlayerWalkA,<PlayerWalkB

; ---- the cave kernel's PROLOGUE (bank6 has no room for it) ------------------------------
; Entered from bank6: `sta $1FFB` at Kernel6Entry, then the byte at +3 is the jmp below.
; Leaves with `sta $1FFA` at Kernel6Entry+6 (bank6 continues at +9, `Kernel6Back`).
Kernel6Entry = Kernel6Pad + 3
    org Kernel6Entry + 3
    jmp Prologue7
    org Kernel6Entry + 6
    sta BK_CAVE
    org $F100
Prologue7:
    include "bank6_prologue.inc"
    jmp Kernel6Entry + 6

; ---- ColOff/ColMask copies for BMWCellSolid (bank0 has the authoritative pair) -----------------
    org $F2C0
ColOff:     .byte 0,0,0,0, 4,4,4,4,4,4,4,4, 8,8,8,8,8,8,8,8
ColMask:    .byte $10,$20,$40,$80,$80,$40,$20,$10,$08,$04,$02,$01
            .byte $01,$02,$04,$08,$10,$20,$40,$80

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

; ==============================================================================
; Raft (enemy type 7) — the moving, rideable platform. plans/raft_moving_plan.md
; ==============================================================================
; Entrance: bank0 UEDispatch -> CallPad_RaftBody (sta $1FF5 / jmp $F822) -> here;
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
;             water does. The rider's pin (top-22 = 103+off, worst case 106)
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
;   cols 0-3   -> PF0 row 3 ($C6), bit 4+col (PF0 bit 4 = leftmost pixel)
;   cols 4-11  -> PF1 row 3 ($CA), bit 7-(col-4)
;   cols 12-19 -> PF2 row 3 ($CE), bit col-12
; (row 3 = the bottom/water band of a 4-band room. These read $C5/$C8/$CB, the
; rows of the old 3-band stride-3 layout, until 2026-10-28: the raft then turned
; at ceiling/ledge cells that were not on its water row.)
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
    and $C6                     ; PF0Buf+3: the water row (4 bands; was +2 = band 3)
    rts
.RCPF1:
    cpy #12
    bcs .RCPF2
    and $CA                     ; PF1Buf+3 (stride 4; $C8 was row 1)
    rts
.RCPF2:
    and $CE                     ; PF2Buf+3 (stride 4; $CB was row 0)
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
; verify_build.check_raft_tramp). bank0 executes `sta $1FF5` at $F8C0-$F8C2 and
; the fetch at $F8C3 comes from THIS bank: `jmp $FDE3` = RaftBody below. Neither
; bank runs the other's half — bank0's operand bytes are never fetched, bank1's
; `sta $1FF5` is never executed (it is only the swapped-out image's prefix).
; In bank1's $F822-$F8C6 fill; StripBlastCheck follows it directly ($F937 pin
; deleted 2026-10-20 — the body floats and the $F9AC pin bounds the leaves).
; ------------------------------------------------------------------------------
    .ds $F8C0 - *, 0
    sta BK_HUD                  ; sta $1FF5 in the old layout (twin)
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
    lda RectCount
    bne .SBlOk                  ; an interior strip is a designed block: bombable
    lda RoomExits               ; the EDGE strip (dcol 0) is the dead-side plug
    and #2
    bne .SBright                ;   (no room to the WEST): unbreakable
.SBlOk:
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
    lda BMWScratch
    cmp #38
    bne .SBrOk                  ; an interior strip is a designed block: bombable
    lda RoomExits               ; the EDGE strip (pL 38 = right_col 9) is the plug
    and #1
    bne .SBdone                 ;   (no room to the EAST): unbreakable
.SBrOk:
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

; ClearPFColumn — A = left-half col 0..19; LineCount ($84) = first row;
;   CollisionEndY = last row (inclusive). AND-clear that col's
;   PF bit in those rows only. Clobbers A/X/Y + CPCScratch ($89) — NO
;   CollisionX (plan 5.1: BombMarkWalls keeps its broken-wall count there
;   across the call). Same-bank rts tail: BombMarkWalls jsrs this directly;
;   the old CallPad_ClearPFColumn path died with ApplyBombWalls (dead pad
;   kept).
;   Scratched retargeted Temp ($AD = bank0 TickCounter!) → $89 (plan 5.1b,
;   2026-10-20): every punch used to write the 60-frame game timer, and the
;   cell punch calls this up to 24×/blast instead of 2×, so the aliasing had
;   to go. $89 was RcBase; the rect cache has no reader since 5.1b.
ClearPFColumn:
    tay                         ; Y = col
    lda BombClearMask,Y
    sta CPCScratch              ; AND mask (clear bit; NOT CollisionX)
    ldx LineCount               ; first row
.CPCLoop:
    tya                         ; col
    cmp #4
    bcc .CPC0
    cmp #12
    bcc .CPC1
    lda PF2Buf,X
    and CPCScratch
    sta PF2Buf,X
    jmp .CPCNext
.CPC0:
    lda PF0Buf,X
    and CPCScratch
    sta PF0Buf,X
    jmp .CPCNext
.CPC1:
    lda PF1Buf,X
    and CPCScratch
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

; ========================================================================
; BombMarkWalls (S5.2, moved from bank0) — pinned at $FB10.
;   On the bomb 1->2 edge: punch the THIN walls in the blast window and
;   report how many were newly broken (A, caller scores +75 each).
;   Bomb left-half col +-2, clamped 0..19. Score is NOT done here — pads
;   cannot nest (ReturnPad switches to bank0), so the bank0 caller adds
;   +75 per wall.
;   Plan 5.1b (2026-10-20): the punch is CELL-based — no rect cache. The
;   PF buffers ARE the map (export: convert_room.pf_values; holes included),
;   so a bombable wall is found the same way find_rectangles finds a w==2
;   rect: a thin wall is ONE D7 logical cell = 2 display cols = a solid
;   PF bit-PAIR whose left and right neighbouring cells are empty. The
;   emitted cells are pair-aligned (both bits of a cell are always written
;   together: pf_values, ClearPFColumn, PhMaskTab), so ONE solidity read
;   per cell covers both cols, and vertical extent needs no data: each row
;   is tested on its own (the old rect h is exactly the run of thin rows —
;   find_rectangles stops a w==1 rect at a row that joins a wider run, and
;   so does the neighbour test). Col 0 (screen border, and its mirror col
;   39) is never destroyable — the old `rect.x == 0` skip.
;   Double-score guard = the buffer: the punched pair is empty, so a second
;   blast in the same room finds no cell (the old WallMask bits and PairGone
;   are gone; walls return on re-entry, D1-B). WallMask (BombPacked b3-6) is
;   retired: HotOverlapBody now tests its parent hot cell's PF bit.
;   Cost: ≤4 cells × 3 rows × ~3 cell probes; blast edge only.

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
    ; --- cell scan (plan 5.1b): cells floor(lo/2)..floor(hi/2), rows 0..2 --
    ; Cell k = display cols 2k, 2k+1. k=0 is the border cell (never broken,
    ; and its mirror = col 39). Each row is tested on its own: the thin
    ; rect's h is exactly the run of thin rows (find_rectangles stops a w==1
    ; rect at a row that joins a wider run, and the neighbour test does too).
    lda CollisionEndX
    lsr
    bne .BMWkOk
    lda #1
.BMWkOk:
    sta CollisionCellY          ; cell index k
.BMWkLoop:
    lda #0
    sta CollisionEndY           ; row 0 for this cell
.BMWrowLoop:
    ; solid(cell k)?  one read covers both cols (pairs are always aligned)
    lda CollisionCellY
    asl                         ; 2k = display col
    tax
    lda CollisionEndY
    jsr BMWCellSolid
    beq .BMWrNext               ; empty cell
    ; left neighbour cell (2k-2) must be empty; k=1 → col 0 is a real cell
    txa
    sec
    sbc #2
    tax
    lda CollisionEndY
    jsr BMWCellSolid
    bne .BMWrNext               ; joins a wider run on the left
    ; right neighbour (2k+2); k=9 is the seam cell (cols 18/19) → open edge
    lda CollisionCellY
    cmp #9
    beq .BMWPunch
    asl
    clc
    adc #2
    tax
    lda CollisionEndY
    jsr BMWCellSolid
    bne .BMWrNext               ; joins a wider run on the right
.BMWPunch:
    lda CollisionCellY
    cmp #1
    bne .BMWgo                  ; only the cell next to the screen border (k = 1)
    lda RoomExits               ; the wall in front of the edge column: the PF is
    and #3                      ;   MIRRORED, so breaking it opens BOTH sides - it
    bne .BMWrNext               ;   needs a room on each (user 2026-10-26: no
                                ;   opening where nothing is connected)
.BMWgo:
    lda CollisionEndY
    sta LineCount               ; ClearPFColumn first row = last row = r
    lda CollisionCellY
    asl
    jsr ClearPFColumn           ; col 2k
    lda CollisionCellY
    asl
    clc
    adc #1
    jsr ClearPFColumn           ; col 2k+1 (second half of the D7 cell)
    inc CollisionX               ; +1 wall broken (caller scores +75 each)
.BMWrNext:
    inc CollisionEndY
    lda CollisionEndY
    cmp #3
    bne .BMWrowLoop
    ; next cell; stop after floor(blast_hi/2) — CollisionCellX must survive
    ; (StripBlastCheck reads the blast window), so re-derive the bound.
    inc CollisionCellY
    lda CollisionCellX
    lsr
    cmp CollisionCellY
    bcs .BMWkLoop
.BMWDone:
    jmp M1StripBlast            ; same bank (repack chunk 2, 2026-10-20):
                                 ; M1StripBlast stages the left-strip dcol and
                                 ; sets b4, then tail-jmps StripBlastCheck.
                                 ; Still 0 push — SP guard unchanged; the
                                 ; check ends in ReturnPad with A = count.

; BMWCellSolid — plan 5.1b cell read. In: X = display col 0..19 (left half),
; A = band row 0..2. Out: Z=1 if the PF cell is EMPTY, Z=0 if SOLID (A = the
; masked byte). Clobbers A/Y, preserves X. Same-bank jsr (no pad nesting);
; caller keeps its loop vars in ZP, so X/Y loss is invisible.
BMWCellSolid:
    clc
    adc ColOff,X
    tay
    lda PF0Buf,Y
    and ColMask,X
    rts

; ---- ReturnPad: every bank's body tails `jmp $FBF8` (bank0 serves the rts at $FBFB) ----
    .ds $FBF8 - *, 0
ReturnPad:
    sta BK_GENERAL

; ---- entry pad half: bank0's CallPad_BombMarkWalls `sta` is at $FC1A, this `jmp` is fetched at $FC1D ----
    .ds $FC1D - *, 0
    jmp BombMarkWalls

    .ds $FDE3 - *, 0
RAFT_MIN_X    = 8               ; the raft's logical X is its lit span's right
RAFT_MAX_X    = 148             ; end, exactly like the player's [x-7,x]; these
                                ; rails keep it inside the room
RAFTER_BASE   = 131             ; raft top when the tide is at 0: the 2-row
                                ; surface (line 132) - 7, so its BOTTOM row
                                ; sits exactly ON the surface. The live value is
                                ; plank's BOTTOM row (top+1) lands on the water
                                ; surface (132+off) — see the tide block below;
                                ; never hard-code the Y: the surface MOVES.
RAFTER_XOFF   = 6               ; PLAYER_WIDTH-1: spawn x of the body span
RAFTER_XSPAN  = 14              ; PLAYER_WIDTH+ENEMY_WIDTH-1: no-overlap gate
RAFTER_YSPAN  = 28              ; PLAYER_SPRITE_H+6: riding when the feet are
                                ; from 22 px above the raft's top to 5 px into it
RAFTER_PINFIT = 22              ; PLAYER_SPRITE_H: pin = raft top - this

RaftBody:
    ; --- float ON the water surface, riding the TIDE ------------------------
    ; The water band's surface drifts 0-3 lines (the tide): the VBL stages
    ; 36+off into CollisionX and the kernel draws the strip as the band's last
    ; (12-off) lines, so the surface line is 132+off. The raft's bottom row
    ; (top+1, a 2-row plank) must land ON that line -> top = 131+off.
    ; This mirrors the VBL's
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
    adc #RAFTER_BASE            ; + 131 -> the surface line (132+off) minus 1
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
    ; --- pin FIRST: the rider stays on the raft even on a TURN frame --------
    ; A raft boxed in by solid row-2 cells (or parked against a rail) turns
    ; every frame and never moves; the turn path returns before the carry, so
    ; pinning here is what keeps a rider standing on it. Without it he fell
    ; through a stuck raft into the water kill line and respawned forever
    ; (user report 2026-10-22: "player position keeps changing, zig-zags").
    ; The vyHi < 0 escape is the gate's `.RaftNoRide` (rising is not a ride).
    lda EnemyRamY,X
    sec
    sbc #RAFTER_PINFIT
    sta RoomY                   ; feet on the raft's top
    lda #0
    sta vyLo
    sta vyHi                    ; landing kills the accumulated fall speed
    ; --- take-off ramp (inertia): heaviest right after boarding -------------
    ; State = PlayerBombs' ($F0) spare HIGH bits: b7 = "ridden last frame",
    ; b6-b3 = the ramp level (0-15); b2-0 stay the bomb count. Adding $10 never
    ; carries into b2-0, and the drop's `dec` is guarded by a non-zero count so
    ; it cannot borrow upward either (see the kernel EQU for the contract).
    ; Riding advances the level every 2nd frame: the raft leaves at 0.5 px/frame
    ; and reaches the full 0.75 px/frame after ~30 frames (~0.5 s), the
    ; heavy take-off. Empty (b7 clear) or level 15: full speed straight away.
    lda $F0
    bpl .RaftAtSpeed            ; b7 clear = nobody aboard -> no ramp
    cmp #%11111000              ; flag + all four level bits = spun up
    beq .RaftAtSpeed
    lda EnemyRamP
    and #1                      ; still ramping: 1 px on odd frames = 0.5 px/frame
    jmp .RaftHaveStep
.RaftAtSpeed:
    lda EnemyRamP
    and #3
    cmp #1                      ; C = (P&3) != 0
    lda #0
    adc #0                      ; 1 px on 3 of 4 frames = 0.75 px/frame (user 2026-11-10:
                                ; the raft was too quick to leave: HALF of 1.5)
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
    ; (the Y pin ran at .RaftGo — it must not depend on the raft moving)
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

    .ds $FFFA - *, 0
    .word $F000
    .word $F000
    .word $F000
