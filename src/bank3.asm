    processor 6502
; ==============================================================================
; Bank3 — power-up stub + Phase-4 crunch bodies (vcrunch/hcrunch)
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
;   bank2 tramp @ T:  sta $1FF9          ; switch to bank3
;                     jmp $Fxxx          ; operand FETCHED bank3-side
;   bank3 @ T+3:      jmp Body           ; byte-identical image required
;   body tail:        sta $1FF8          ; switch back
;                     jmp $Fxxx          ; operand FETCHED bank2-side
;   bank2 @ tail+3:   jmp <label>        ; byte-identical image required
;
; Tramp/tail addresses (sync with bank2.asm after ANY PhaseBlink/HOV move):
;   LIVE bank-switch twins (bank2 sta $1FF9 slot -> operand fetch here):
;     $FC1B  jmp $FA40  (HOVFeatPre -> HOVFeatEntry)
;     $FC34  jmp $F880  (PhHcrPre  -> PhHcrEntry)
;     $FE57  jmp $FD80  (OvShutScan -> VCS3)
;   LEGACY twins kept as fill (their bank2 slots tail-jmp internally now —
;   PhVcrPre is `jmp VcrShutter` at $FE45, so PhVcrEntry is retired):
;     $FB57  jmp $F800 / $FB61 jmp $F880 / $FD7B jmp $FA40
;   Return tails (bank3 sta $1FF8 executed here, jmp fetched bank2-side):
;     $FCC1  tail → <bank2 .PhRec>      (vcrunch staging return)
;     $FCC7  tail → <bank2 .PhRec>      (hcrunch staging return)
;     $FCCD  tail → $FD6B HOVnext       (crunch kill miss)
;     $FCD3  tail → $FD60 HOVlegHit     (crunch kill HIT)
;     $FCD9  tail → $FD1C HOVafterGate  (phase armed → overlap tests)
;   .PhRec literal is auto-synced by build.sh (sync_phrec_literal) — the
;   PRE-READ twins above are NOT; a byte change in HOVFeatPre/PhHcrPre
;   silently moves bank2's jmp and breaks the frame (2026-10-16).
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
RoomY = $81                    ; player Y — VCS3 kill endpoints
CollisionX = $8B
CollisionCellX = $8C             ; max text column (player box)
CollisionEndX = $8E              ; min text column (player box)
CollisionCellY = $8D             ; top tile row (player box) — NOT scratch
                                 ; here (bank2 stages the door color in it)
CollisionEndY = $8F              ; bottom tile row (player box) / mask scratch
RectCount = $92                  ; PHMOverlay scratch: BallX (VCS3
                                 ; containment gate reads it — still live
                                 ; at OvShutScan entry)
EnemyDeadMask = $BA              ; b5 phase armed, b6 phase removed,
                                 ; b7 crunch-kill latch (EnterRoom zeroes)
EnemyRamP = $C2                  ; free-running frame clock
PF0Buf = $C3                     ; PF buffers rows 0-2 (9B: +0/3/6 per reg)
RoomX = $80                      ; player X (0-159) — HcrPush clamp target
RoomPF0Lo = $99                  ; TilePF0 pointer (MetaB at (ptr),10)
RoomMetaA = $99                  ; staged MetaA/MetaB (floor + ptr pair reuse)
RoomMetaB = $9A
BandTab = $ED                    ; band gate bytes (B3StageBand writes)
CTRLPF = $0A                     ; TIA (ball width $35 during staging)
NUSIZ1 = $05                     ; TIA (P1 single, M1 8 clk)

; ==============================================================================
; HcrPush — cold growth push (user 2026-10-16): while the hcrunch prefix
; ADVANCES it shoves the player toward center, so a cold shutter cannot
; trap them inside (hot = kill semantics, unchanged). Called from
; PhHcrEntry on the 16f grow-step edge (EnemyRamP & $0F == 0) with the
; spent (b7) latch filtered; this body re-checks the phase (s4-12).
; In:  CollisionX = 8n (prefix width px), CollisionCellX = band (0-2),
;      Y = hot (full MetaB byte, bank2-staged; masked here). Out: RoomX
;      clamped out of the left prefix [0,8n) / the TIA mirror [160-8n,160);
;      A/X/Y + CollisionX clobbered.
; ==============================================================================
    org $F010
HcrPush:
    tya                 ; hot (MetaB b6, $40/0 — bank2-side, passed in Y)
    and #$40
    bne .Hpd            ; hot: kill semantics own it — no push
    lda EnemyRamP
    lsr
    lsr
    lsr
    lsr                 ; s = P>>4
    cmp #4
    bcc .Hpd            ; s0-3 dwell: stub static, no push
    cmp #13
    bcs .Hpd            ; s13-15 retract: opening, no push
    ldx CollisionCellX
    clc
    lda RoomY
    adc #11             ; PLAYER_SPRITE_H-1
    sec
    sbc HcrBandLo,X     ; bottom - band_lo (0/48/96)
    bcc .Hpd            ; entirely above the band
    cmp #59             ; 48+11: bottom-band_lo >= 59 → entirely below
    bcs .Hpd
    lda CollisionX      ; 8n
    cmp #80
    bcs .Hpd            ; sealed (n>=10): no aperture — HOVhcrunch kills
    clc
    adc #7              ; aperture_lo = 8n+7
    cmp RoomX
    bcc .Hrr            ; clear of the left prefix
    beq .Hrr            ; flush = clear
    sta RoomX           ; left overlap: clamp right
.Hrr:
    lda CollisionX      ; 8n
    clc
    adc RoomX
    cmp #160
    bcc .Hpd            ; clear of the mirror prefix
    lda #159
    sec
    sbc CollisionX      ; 159-8n
    sta RoomX           ; right overlap: clamp left
.Hpd:
    rts
    org $F0A0
HcrBandLo:
    .byte 0, 48, 96                ; band → band_lo

; ==============================================================================
; B3StageBand — StageBandTab, MOVED from bank2 (chunk A2, 2026-10-19).
;
; Tail-entered from bank2 BCFDarkRun at $F3A9:
;   jsr PhaseBlink   (stays bank2 — it walks the rect stream)
;   sta $1FF9
;   jmp $F0A3        <- OPCODE fetched from THIS bank at $F3AF
; so bank3 MUST hold `jmp $F0A3` at $F3AF (pinned at the end of this block).
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
    org $F0A3
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
                            ; (vcrunch) AND b6 (hot) — b6 used to survive
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
    ; staging above and before the pack below (VcrShutter overwrites
    ; Temp/BandTab for the shutter cell — running it earlier let SBT's own
    ; staging erase the shutter, and every crunch kill stopped latching).
    ; Leg 1: this `sta` runs here, the fetch at $F803 is bank2's
    ; `jmp PhBlinkTail` (byte-image pinned in bank2.asm).
    jmp $F800
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

    .ds $F3AC - *, 0            ; PIN: bank2 BCFDarkRun's `sta $1FF9` ends
                                ;   here (sta +3) — this image is what runs.
    .byte $4C, <B3StageBand, >B3StageBand   ; jmp B3StageBand

    .ds $F800 - *, 0            ; ping-pong leg 1 (see the jmp above)
    sta $1FF8                   ;   bank2 continues at $F803
    .ds $F80C - *, 0
    jmp SBT_B                   ; ping-pong leg 2 twin: bank2's PhBlinkTail
                                ;   does `sta $1FF9` and fetches THIS jmp

; ==============================================================================
; PhVcrEntry — PhaseBlink $81 (vcrunch) tramp target.
; Record: $81, x (4px col), y (row), w (4px), h (rows). The covered TOP
; rows of the bbox keep/set their pair bits (shutter closed), the open
; rows clear them (shutter retracted). covered_h = CrunchClock(h) —
; ping-pong with a dwell at the home stub (always ≥1 row: never gone,
; user ruling 2026-10-13). Y = record class on entry; tail leaves
; Y = base+2 for PhNext. Clobbers A/X/Y + LineCount/CCX/CEY.
; ==============================================================================
; ==============================================================================
; PhVcrEntry RETIRED (2026-10-19) — bank2's PhVcrPre tail-jmps VcrShutter
; (bank2) since the Phase-B rework; no tramp targets $F800 anymore (the
; $FB57/$FE67 images are legacy fill). The whole $F800-$F87F block is free
; for data. Vcrunch's live path = bank2 VcrShutter (PF punch + Temp/BandTab)
; + bank3 VCS3 (kill); CrunchClock/CrunchMasks/PhVcApply* remain for it.
; ==============================================================================
; ==============================================================================
; PhHcrEntry — PhaseBlink $82 (hcrunch) tramp target.
; Record: $82, 0, band (row), w (4px = 2*cells), 1. Single-row band
; prefix from col 0: cells 0..n-1 covered (n = HcrClock(full)), the
; rest of the full bbox cleared. PF = (row & ~P(full)) | P(n) — fused in
; ONE pass (P(n) ⊆ P(full), so AND-then-OR collapses; one pass halves the
; buffer reads). Y = class on entry; tail leaves Y = base+2. Clobbers
; A/X/Y + LineCount/CCX/CEY.
; ==============================================================================
    org $F880
PhHcrEntry:
    ; Entered from bank2 PhHcrPre: stack (top→) = h, w, y(band), x, <caller>.
    ; Hot (MetaB b6) is staged bank2-side in LineCount ($84) and read HERE,
    ; right after HcrClock, BEFORE the mask staging reuses LineCount. The
    ; push is deliberately the FIRST thing after n: it only needs n + band +
    ; hot, and reordering keeps the 4-field stack contract (no 5th push) so
    ; bank2's tramp stays aligned with this bank's twin.
    ; Y = base+4 on entry; saved for the .PhRec return.
    tya
    pha                     ; [base+4]
    tsx
    lda $0104,X             ; y = band
    pha                     ; [base+4, band]
    tsx
    lda $0104,X             ; w
    lsr                     ; full cells (w is even, 2*cells)
    pha                     ; [base+4, band, full]
    tax                     ; X = full
    jsr HcrClock            ; A = n covered cells (1..full); b7 → 1 (spent)
    pha                     ; [base+4, band, full, n]
    ; cold growth push (user 2026-10-16). Split from the staging (option A):
    ; on the 16f grow-step edge (EnemyRamP & $0F == 0) we PUSH and SKIP the
    ; staging; every other frame we STAGE and never push. The PF buffer then
    ; shows last frame's prefix for the one step frame (the shutter renders
    ; one frame late on a step — invisible at 16f/step), but the ~90c staging
    ; and the ~65c push never share a frame, so the worst VBL is base +
    ; max(staging, push) instead of the sum (the flicker fix). Spent (b7)
    ; always stages (freeze at stub) and never pushes.
    lda EnemyRamP
    and #$0F
    bne .HcStage            ; not the step edge → stage the shutter
    lda EnemyDeadMask
    and #$80
    bne .HcStage            ; spent: stage the stub, never push
    tsx
    lda $0103,X             ; band
    sta CollisionCellX
    lda $0101,X             ; n
    asl
    asl
    asl                     ; 8n (prefix width px) — HcrPush's only ext input
    sta CollisionX
    lda LineCount           ; hot (MetaB b6, $40/0) — bank2 staged it
    tay                     ; Y = hot
    jsr HcrPush
    jmp .HcDrain            ; push frame: skip the staging (see above)
.HcStage:
    ; Fused bbox-open + prefix-close, ONE band row (h is always 1 for $82):
    ;   PF[row] = (PF[row] & ~P(full)) | P(n)
    ; ~P(full) staged in LineCount/CCX/CEY; P(n) read from CrPfx*,Y inline.
    ; One pass replaces ApplyAND-then-ApplyOR (same result — P(n) ⊆ P(full)
    ; — but half the buffer reads); frees ~50c of the hcrunch VBL.
    tsx
    ldy $0102,X             ; full
    lda CrPfx0,Y
    eor #$FF
    sta LineCount
    lda CrPfx1,Y
    eor #$FF
    sta CollisionCellX
    lda CrPfx2,Y
    eor #$FF
    sta CollisionEndY
    tsx
    ldy $0101,X             ; n → CrPfx index
    lda $0103,X             ; band
    tax                     ; X = PF buffer row index
    lda PF0Buf,X
    and LineCount
    ora CrPfx0,Y
    sta PF0Buf,X
    lda PF0Buf+3,X
    and CollisionCellX
    ora CrPfx1,Y
    sta PF0Buf+3,X
    lda PF0Buf+6,X
    and CollisionEndY
    ora CrPfx2,Y
    sta PF0Buf+6,X
.HcDrain:
    pla                     ; n
    pla                     ; full
    pla                     ; band
    pla                     ; base+4 → A = base+4
    tay                     ; Y = base+4 (record end → .PhRec iny → next class)
    pla
    pla
    pla
    pla                     ; drain h, w, y, x
    jmp $FCC7               ; pad: sta $1FF8 / jmp .PhRec (bank2 image)

; ==============================================================================
; CrunchClock / CrunchMasks DELETED (2026-10-19): their only caller was
; PhVcrEntry, which bank2 stopped tramping to in the Phase-B rework (vcrunch
; now stages its PF punch in bank2 VcrShutter and kills through VCS3). The
; live ping-pong formula is VcrStateTab (VBL) + VCS3 (kill) — both guarded.
; ==============================================================================
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
; tramp path; hcrunch fuses its AND+OR pass inside PhHcrEntry.
; ==============================================================================
; ==============================================================================
; HcrClock — retuned shutter clock (hcrunch-only; 2026-10-16 retune).
;   In:  X = full extent (cells, ≥1); reads EnemyRamP (StartFrame-pinned)
;   Out: A = covered (1..full) — never 0 (always-solid stub)
;   Clobbers A (X/Y preserved — unlike CrunchClock)
; s = EnemyRamP>>4 (0..15, one 256f period = 16 buckets of 16f):
;   s 0-3   dwell at home  (eff 0)       -> n=1, 64f stub
;   s 4-12  grow to center  (eff s-3)    -> n 2..full (1..9 cells of
;          8px — full=w>>1; w=20 record = center of the screen)
;   s 13-15 fast retract    (eff 3*(15-s) = 6,3,0) — wipe home in 3
;          steps (the old instant far-end turn, stretched to center)
; covered = 1 + min(eff, full-1). CrunchClock (sc>>2 triangle, ~4f/step)
; stays for its VCR mirrors + verify_build token gate — only the two
; hcrunch call sites moved here (16f/step, grow-to-center ruling
; 2026-10-16).
; ==============================================================================
HcrClock:
    lda EnemyDeadMask
    and #$80            ; b7: crunch kill latched this visit?
    beq .hcLive
    lda #1              ; spent — freeze the shutter at the home stub
    rts                 ;   (min width) for the rest of the visit
.hcLive:
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
;   $81 vcrunch / $82 hcrunch: covered extent vs player box →
;               HOVcKill (latch b7) → HOVlegHit (Temp b7 → LoseLife).
;               b7 latch = kill ONCE per room visit (DropArm respawns at
;               the death spot; the shutter is always-solid so a re-kill
;               loop would be instant death). EnterRoom zeroes b7.
; ==============================================================================
    org $FA40
HOVFeatEntry:
    ; $81/$82 entered from bank2 HOVFeatPre: stack (top→) = h, w, y, x,
    ; <base from .HOVloop>. Fields MUST be drained before HOVnext/HOVlegHit
    ; (they pop the .HOVloop base). $80 has no fields (HOVafterGate = bank2).
    ; C1 (2026-10-19): ONE dispatcher for both crunch classes — the old
    ; HOVvcrunch/HOVhcrunch jsr+rts pair and their duplicated drains are gone.
    ; Conditional misses branch to the nearby .HFmissJ trampoline (a direct
    ; bcc to .HFmissD is >127 B away in both arms).
    cmp #$80
    bne .HFnotPhase
    jmp .HFphase                ; (far: trampoline form for every branch here)
.HFnotPhase:
    pha                         ; save class (b7 check clobbers A)
    lda EnemyDeadMask
    and #$80                    ; b7: crunch kill already happened?
    beq .HFnotLatched
    jmp .HFmissP                ; yes → pass (wall stays, no re-kill)
.HFnotLatched:
    pla
    cmp #$81
    bne .HFnotV
    jmp .HFv
.HFnotV:
    cmp #$82
    beq .HFh_begin
    jmp .HFmissP                ; unknown b7 class → same drain path
.HFh_begin:

    ; ---------------- $82 hcrunch: band ∈ [top,bottom] ----------------
    tsx
    lda $0103,X                 ; y = band
    cmp CollisionCellY
    bcs .HFh_lo
    jmp .HFmissD                ; band < top
.HFh_lo:
    cmp CollisionEndY
    beq .HFh2
    bcc .HFh2                   ; band <= bottom
    jmp .HFmissD                ; band > bottom
.HFh2:
    tsx
    lda $0102,X                 ; w
    lsr                         ; full cells
    tax
    ; Rule (user 2026-10-16): cold kill while CLOSING (sc<52 = dwell+grow);
    ; hot (LineCount = MetaB, staged bank2-side; asl×2 brings b6 to C)
    ; exempts — any phase/extent kills. Opening never kills.
    lda LineCount
    asl
    asl                         ; b7 out, b6 -> C
    bcs .HFh3                   ; hot → any phase/extent kills
    lda EnemyRamP
    lsr
    lsr                         ; sc
    cmp #52
    bcc .HFh3                   ; closing half
    jmp .HFmissJ                ; opening half → no kill
.HFh3:
    txa
    pha                         ; full — stays callee-independent
    jsr HcrClock                ; n covered cells (X = full preserved)
    sta CollisionX              ; save covered
    lda LineCount
    asl
    asl                         ; b7 out, b6 -> C
    pla                         ; full (PLA preserves C)
    bcs .HFh4                   ; hot → any extent kills
.HFh4:
    lda CollisionX
    asl                         ; covered_w in 4px cols
    cmp CollisionEndX           ; covered_w vs min col (strict >)
    bcc .HFmissJ
    beq .HFmissJ
    jmp .HFkill

.HFmissJ:
    jmp .HFmissD

    ; ---------------- $81 vcrunch: covered rect [x, y, w, h] -------------
.HFv:
    tsx
    lda $0104,X                 ; x
    cmp CollisionCellX          ; x vs max col
    beq .HFv2
    bcc .HFv2
    jmp .HFmissD
.HFv2:
    sta LineCount               ; save x
    tsx
    lda $0103,X                 ; y
    cmp CollisionEndY           ; y vs bottom row
    beq .HFv3
    bcc .HFv3
    jmp .HFmissD
.HFv3:
    sta CollisionX              ; save y
    tsx
    clc
    lda $0104,X                 ; x
    adc $0102,X                 ; + w
    cmp CollisionEndX           ; x+w vs min col (strict >)
    bcc .HFmissJ
    beq .HFmissJ
    tsx
    lda $0101,X                 ; h
    sta LineCount               ; Phase B sprite shutter: covered = h
    lda CollisionX              ; y
    clc
    adc LineCount               ; y + covered_h
    cmp CollisionCellY          ; vs top row (strict >)
    bcc .HFmissJ
    beq .HFmissJ

.HFkill:
    lda EnemyDeadMask
    ora #$80                    ; b7: crunch kill latch
    sta EnemyDeadMask
    pla
    pla
    pla
    pla                         ; drain h,w,y,x (base on top for HOVlegHit)
    jmp $FCD3                   ; pad: sta $1FF8 / jmp HOVlegHit (bank2 image)
.HFmissD:
    pla
    pla
    pla
    pla                         ; drain h,w,y,x (base on top for HOVnext)
.HFmiss:
    jmp $FCCD                   ; pad: sta $1FF8 / jmp HOVnext (bank2 image)
.HFmissP:
    pla                         ; drop saved class
    jmp .HFmissD
.HFphase:
    lda EnemyDeadMask
    and #$60                    ; b5 armed | b6 phase dead
    cmp #$20                    ; armed AND not yet removed?
    bne .HFmiss
    jmp $FCD9                   ; pad: sta $1FF8 / jmp HOVafterGate (bank2 image)

; ==============================================================================
; Bank3-side tramp images (byte-identical with bank2's fetch slots) and
; return tails. The `sta $1FF8` at each tail executes bank3-side; the
; `jmp` operand bytes at +3 are fetched from bank2 post-switch — bank2's
; $FCC1 pads hold the same jmp images.
; ==============================================================================
    .ds $FB57 - *, 0
    .byte $4C, $00, $F8         ; jmp $F800 (image: bank2 $FB57, PhVcrEntry)
    .ds $FB61 - *, 0
    .byte $4C, $80, $F8         ; jmp $F880 (image: bank2 $FB61, PhHcrEntry)

    .ds $FBEE - *, 0            ; pads $FB64→$FBEE
    sta $1FF8                   ; $FBEE — twin of bank2 Bank2ReturnPad
    rts                         ; $FBF1 — fetched bank2-side post-switch
    .ds $FBF8 - *, 0            ; B3StageBand's exit: `jmp ReturnPad`. The
ReturnPad:                      ;   `sta $1FF6` runs HERE, the `rts` opcode is
    sta $1FF6                   ;   fetched from bank0's ReturnPad at $FBF9
    rts                         ;   (post-switch) -> pops the bank0 VBL jsr.
    .ds $FC1B - *, 0
    .byte $4C, $40, $FA         ; jmp $FA40 (image: bank2 $FC1B — post-switch
                                ;   fetch of HOVFeatPre's jmp; bank2's HOV
                                ;   staging dropped the pha/pla pair, moving
                                ;   the slot -2 from the old $FC1D)
    .ds $FC34 - *, 0
    .byte $4C, $80, $F8         ; jmp $F880 (image: bank2 $FC34 — post-switch
                                ;   fetch of PhHcrPre's jmp; sta $1FF9 sits at
                                ;   $FC31 after the 4-field push + MetaB read).
                                ;   Missing/misaligned twin = zeros executed
                                ;   bank3-side → $F000 pad → GameStart re-init

    .ds $FCC1 - *, 0            ; return tails (slots match bank2 pads)
    sta $1FF8
    jmp $FAFB                   ; .PhRec (vcrunch; Y=base+4, iny→next class)
    .ds $FCC7 - *, 0
    sta $1FF8
    jmp $FAFB                   ; .PhRec (hcrunch; Y=base+4, iny→next class)
    .ds $FCCD - *, 0
    sta $1FF8
    jmp $FD6B                   ; HOVnext (miss)
    .ds $FCD3 - *, 0
    sta $1FF8
    jmp $FD60                   ; HOVlegHit (kill)
    .ds $FCD9 - *, 0
    sta $1FF8
    jmp $FD1C                   ; HOVafterGate (phase armed)

    .ds $FD7B - *, 0
    .byte $4C, $40, $FA         ; jmp $FA40 (image: bank2 $FD7B, HOVFeatEntry)

; ------------------------------------------------------------------------------
; VCS3 — OvShutScan body (Phase C kill test; bank2 tramp `sta $1FF9 / jmp
; $FD80` at $FE48). IN: A = kill clock (EnemyRamP-1), Y = MetaB b6 hot bit
; ($40/0 — staged bank2-side; MetaB lives in bank2 models_data ROM, a
; (RoomPF0Lo),Y fetch here would see bank3's pad). OUT (2026-10-14b):
; C=0 passable (A ignored) / C=1 + A≠0 kill / C=1 + A=0 SOLID block —
; returned through the $FBEE pad (sta $1FF8 executed here, rts fetched
; from bank2's byte-identical copy) to OvShutBand's jsr — A and C
; survive both; X/Y clobbered (OvShutBand reloads A before the latch).
; Kill semantics (user spec 2026-10-14, superseded the 2026-10-13
; endpoint-only rule): a horizontal containment gate (after the clock
; math, before the hot/cold split) — the player's lit span must sit
; inside the column [BallX-7, BallX] or the call returns passable
; (side brush, user bug 2026-10-14: touching the closed block from the
; side is not a crunch). Then hot band (MetaB b6) = touching ANY
; closed slice kills (endpoint test ≡ any-part: the ping-pong states
; $11/$1B/$1F never have a closed middle with open ends). Cold band =
; containment only: kill iff the whole sprite sits inside CLOSED
; slices (crunched) — $1F trivially; $1B/$11 iff the box misses the
; aperture (H≥gapHi or F<gapLo). Touching an edge from the open side
; is not a cold kill — that is what the hot flag is for. Every
; NON-kill outcome (side brush, opening half, totally closed, the
; aperture at the player's Y) goes through the solidity test
; (.V3solidBody): both endpoints open → passable, else SOLID block —
; the punched cell must not be walkable through a closed shutter
; (user 2026-10-14b).
; Clock parity: RefreshEnemyY inc'd EnemyRamP at overscan entry, so
; clock-1 = the exact value the kernel rendered slices from this frame.
; Endpoints: RoomY (head) + RoomY+11 (feet = PLAYER_SPRITE_H-1) — every
; open state's gap is >=13 lines ($1B = the 13-line center slice), so
; both endpoints open ⟺ the whole sprite is clear of that state.
; Ping-pong constants (#32/#4) = bank2 VcrCoveredState + CrunchClock
; (verify_build check_crunch_clock asserts the trio).
; ------------------------------------------------------------------------------
    .ds $FD80 - *, 0
VCS3:
    lsr
    lsr                         ; clock>>2 (64-frame ping-pong period)
    cmp #32
    bcc .V3hop
    eor #$3F                    ; 32..63 -> 31..0 (fold down)
.V3hop:
    cmp #4
    bcc .VC3q
    sbc #4                      ; head offset (C set by cmp) — dwell zone
.VC3q:
    cmp #4
    bcc .V3open                 ; eff 0-3 (both dwell halves) -> fully open
                                ;   (state $00: no closed slices — passable;
                                ;   mirrors VcrCoveredState 2026-10-14c)
    cmp #9
    bcc .VC311
    cmp #18
    bcc .VC31b
    lda #$1f                    ; fully closed
    jmp .OSgo
.VC31b:
    lda #$1b                    ; center slice open
    jmp .OSgo
.V3open:
    lda #0                      ; fully open
    beq .OSgo                   ; (always — Z=1 from A=0)
.VC311:
    lda #$11                    ; only edge slices closed
.OSgo:
    tax                         ; X = slice state
    ; Horizontal containment gate (user bug 2026-10-14): the KILL only
    ; fires when the player's lit span sits INSIDE the shutter column —
    ; a side brush never kills. It is also never freely passable: every
    ; non-kill outcome routes through the solidity test (closed slices
    ; BLOCK — user 2026-10-14b: no walking through a closed shutter;
    ; the aperture at the player's Y passes). ZP inputs still live from
    ; PHMOverlay's gate: CollisionX ($8B) = vl, RectCount ($92) = BallX;
    ; block = [BallX-7, BallX], lit span = [vl, vl+6].
    lda RectCount
    sec
    sbc #7                  ; BallX-7 = block left edge
    cmp CollisionX          ; vl vs left edge
    bcc .V3in               ; starts inside
    beq .V3in               ; flush left -> inside
    jmp .V3solid            ; side-left: solid where closed
.V3in:
    lda CollisionX
    clc
    adc #6                  ; vl+6 = player right edge
    cmp RectCount           ; vs BallX
    bcc .V3hot              ; fully inside
    beq .V3hot              ; flush right -> inside
    jmp .V3solid            ; side-right: solid where closed
.V3hot:
    tya                         ; A = hot bit ($40/0) — staged bank2-side
                                ;   (MetaB lives in bank2 models_data ROM)
    beq .OScontain              ; cold: kill only when CRUNCHED (contained)
    txa                         ; hot: TOUCH — either endpoint in a closed
    tay                         ;   slice kills
    lda RoomY
    jsr .OSline
    bcs .OSkill                 ; head inside a closed slice → kill
    lda RoomY
    clc
    adc #11
    jsr .OSline
    bcs .OSkill                 ; feet inside a closed slice → kill
    jmp .OSmiss                 ; clear of every closed slice → pass
; Cold path: kill only while CLOSING and crunched (Rule 1 2026-10-14);
; every other outcome routes through the solidity test — closed slices
; block, the aperture at the player's Y passes.
.OScontain:
    lda EnemyRamP
    sec
    sbc #1                  ; kill clock
    lsr
    lsr                     ; sc = clock>>2
    cmp #32
    bcs .V3solid            ; opening half -> no kill, solidity
    cpx #$1f
    beq .V3solid            ; totally closed -> no kill, solidity
    txa
    tay                     ; Y = state (for .OSline)
    lda RoomY
    jsr .OSline
    bcc .V3solid            ; head open -> solidity (feet decides)
    lda RoomY
    clc
    adc #11
    jsr .OSline
    bcc .V3solid            ; feet open (head closed) -> solidity
    ; both endpoints closed — crunched: kill iff the box misses the
    ; state's aperture ($1B = [66,79), $11 = [57,88))
    txa
    ldy #0
    cmp #$1b
    beq .OSgap
    iny
.OSgap:
    lda RoomY
    cmp .OSgapHi,y              ; H >= gapHi → wholly above aperture → kill
    bcs .OSkill
    lda RoomY
    clc
    adc #11
    cmp .OSgapLo,y              ; F < gapLo → wholly below aperture → kill
    bcc .OSkill
    jmp .V3solid            ; (unreachable: a 12px sprite cannot span a
                            ;  >=13px aperture with both ends closed)
.OSmiss:
    clc                     ; A ignored — C=0 = passable
    jmp $FBEE
.OSkill:
    lda #1                  ; A≠0 + C=1 = kill (OvShutBand latches b7+Temp)
    sec
    jmp $FBEE
.OSsolid:
    lda #0                  ; A=0 + C=1 = solid block (walk blocked, no kill)
    sec
    jmp $FBEE
.OSgapHi:
    .byte 79, 88
.OSgapLo:
    .byte 66, 57
.V3solid:
    jmp .V3solidBody        ; shared solidity thunk (body moved out — no
                            ;   room in the $FD80..$FE57 window)

    .ds $FE57 - *, 0
    .byte $4C, $80, $FD         ; jmp $FD80 (image: bank2 $FE57, OvShutScan tramp)
    .ds $FE67 - *, 0
    .byte $4C, $00, $F8         ; jmp $F800 (image: bank2 $FE67, PhVcrPre tramp)
    .ds $FE7D - *, 0
    .byte $4C, $80, $F8         ; jmp $F880 (image: bank2 $FE7D, PhHcrPre tramp)

; A = global cave line (RoomY), Y = state → C = state bit of the owning
; slice. Ranges shifted +48 for the middle band (shutter band 1 since the
; 2026-10-14 specials rule): [57,66) [66,79) [79,88) [88,97); >=97 never
; closed (bottom band has no shutter). Moved to $FE80 (2026-10-14b) —
; the VCS3 solidity rework outgrew the $FD80..$FE57 window.
.OSline:
    cmp #57
    bcc .OSl0
    cmp #66
    bcc .OSl1
    cmp #79
    bcc .OSl2
    cmp #88
    bcc .OSl3
    cmp #97
    bcc .OSl4
    clc
    rts
.OSl0:
    tya
    lsr                         ; bit0 → C
    rts
.OSl1:
    tya
    lsr
    lsr                         ; bit1 → C
    rts
.OSl2:
    tya
    lsr
    lsr
    lsr                         ; bit2 → C
    rts
.OSl3:
    tya
    lsr
    lsr
    lsr
    lsr                         ; bit3 → C
    rts
.OSl4:
    tya
    lsr
    lsr
    lsr
    lsr
    lsr                         ; bit4 → C
    rts

; Shared solidity test (user 2026-10-14b — no walking through a closed
; shutter): IN Y = state; both endpoints open → passable (.OSmiss),
; else SOLID (.OSsolid — C=1, A=0: the walk blocks, no kill latch).
; Entered from VCS3's .V3solid thunk (side brushes + every cold
; non-kill outcome: opening half, totally closed, aperture-touch).
.V3solidBody:
    txa
    tay                         ; Y = state (X survives the callers)
    lda RoomY
    jsr .OSline
    bcc .V3sol2                 ; head open → feet decides
    jmp .OSsolid
.V3sol2:
    lda RoomY
    clc
    adc #11
    jsr .OSline
    bcs .V3solS            ; feet closed (head open) → solid
    jmp .OSmiss            ; both open → whole sprite in the aperture
.V3solS:
    jmp .OSsolid

    ; Pad to vectors at $FFFA
    .ds $FFFA - *, 0
    .word $F000                 ; NMI vector
    .word $F000                 ; RESET vector ← power-up entry
    .word $F000                 ; IRQ vector
