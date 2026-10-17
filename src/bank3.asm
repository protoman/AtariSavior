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
; PhVcrEntry — PhaseBlink $81 (vcrunch) tramp target.
; Record: $81, x (4px col), y (row), w (4px), h (rows). The covered TOP
; rows of the bbox keep/set their pair bits (shutter closed), the open
; rows clear them (shutter retracted). covered_h = CrunchClock(h) —
; ping-pong with a dwell at the home stub (always ≥1 row: never gone,
; user ruling 2026-10-13). Y = record class on entry; tail leaves
; Y = base+2 for PhNext. Clobbers A/X/Y + LineCount/CCX/CEY.
; ==============================================================================
    org $F800
PhVcrEntry:
    ; Entered from bank2 PhVcrPre: stack (top→) = h, w, y, x, <caller>.
    ; bank2 pushed the fields — bank3 MUST NOT read (FetchPtr) (cross-bank
    ; ROM = garbage). Y = base+4 on entry; saved for the .PhRec return.
    tya
    pha                     ; [base+4]
    tsx
    lda $0105,X             ; x
    sta LineCount
    lda $0104,X             ; w
    sta CollisionCellX
    lda $0102,X             ; h
    tax
    jsr CrunchClock         ; A = covered_h (1..h)
    pha                     ; [base+4, ch]
    ; bbox width masks: pairs (x>>1)..((x+w-1)>>1) via CrunchMasks
    lda LineCount
    lsr
    tay                     ; p0
    lda CollisionCellX
    sec
    sbc #1
    clc
    adc LineCount           ; x+w-1
    lsr
    tax                     ; p1
    jsr CrunchMasks         ; LineCount/CCX/CEY = pair-range masks
    ; OR covered rows: start y, count ch
    ; stack: ch, base+4, h, w, y, x
    tsx
    lda $0105,X             ; y
    ldy $0101,X             ; ch
    jsr PhVcApplyOR
    ; AND open rows: start y+ch, count h-ch (0 → done)
    tsx
    lda $0103,X             ; h
    sec
    sbc $0101,X             ; h-ch
    beq .PVfin
    tay
    tsx
    lda $0105,X             ; y
    clc
    adc $0101,X             ; y+ch
    jsr PhVcApplyAND
.PVfin:
    pla
    pla                     ; ch, base+4 → A = base+4
    tay                     ; Y = base+4 (record end → .PhRec iny → next class)
    pla
    pla
    pla
    pla                     ; drain h, w, y, x
    jmp $FCC1               ; pad: sta $1FF8 / jmp .PhRec (bank2 image)

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
; CrunchClock — ping-pong shutter clock (VCR mirrors + retired
; PhVcrEntry; the two hcrunch call sites moved to HcrClock 2026-10-16).
;   In:  X = full extent (cells, ≥1)
;   Out: A = covered (1..full) — never 0 (always-solid stub)
;   Clobbers A/X/Y (callers save what they need)
; sc = EnemyRamP>>2 (0..63); triangle tri = sc<32 ? sc : 63-sc (0..31..0);
; dwell: effective = max(0, tri-4) — a ~16f flat bottom at home (both
; ends of the sc wrap land in the dwell zone). covered = 1+min(eff,
; full-1). Sweep: eff climbs 0..27 over tri 4..31 = 28 sc steps × 4f ≈
; 112f out + 112f back + dwell — tunable via the #4/#32 constants
; (user CHECK: eyeball speed, 2026-10-13).
; ==============================================================================
    org $F900
CrunchClock:
    cpx #1
    bne .ccNorm
    lda #1                  ; full==1: covered is always 1 — skip the clock
    rts
.ccNorm:
    lda EnemyRamP
    lsr
    lsr                     ; sc 0..63
    cmp #32
    bcc .ccF
    eor #$3F                ; sc>=32: 63-sc (sc^63 — high bits don't overlap)
.ccF:
    cmp #4
    bcc .ccZ                ; dwell: tri<4 → 0
    sbc #4                  ; C=1 from cmp
.ccZ:
    tay                     ; Y = eff
    txa
    sec
    sbc #1                  ; A = full-1
    pha                     ; (stack as the min() temp — no ZP free)
    tsx
    tya
    cmp $0101,X             ; eff vs full-1
    bcc .ccA                ; eff smaller → keep A=eff
    lda $0101,X             ; else full-1
.ccA:
    pla
    clc
    adc #1
    rts

; ==============================================================================
; CrunchMasks — PF pair-range masks via the prefix tables.
;   In:  Y = first pair (0-9), X = last pair (0-9, ≥ Y)
;   Out: LineCount = PF0 mask, CollisionCellX = PF1 mask,
;        CollisionEndY = PF2 mask
;   Clobbers A/X/Y
; mask(p0..p1) = P(p1+1) & ~P(p0) — P(n) = OR of pairs 0..n-1 per
; register (CrPfx0/1/2, n = 0..10). Prefix-from-0 callers (hcrunch)
; skip this and load CrPfx* directly.
; ==============================================================================
    org $F940
CrunchMasks:
    ; Prefix masks are cumulative-disjoint, so P(p1+1) ^ P(p0) ==
    ; P(p1+1) & ~P(p0) — the XOR form drops 2 insns/register (-21c).
    lda CrPfx0+1,X
    eor CrPfx0,Y
    sta LineCount
    lda CrPfx1+1,X
    eor CrPfx1,Y
    sta CollisionCellX
    lda CrPfx2+1,X
    eor CrPfx2,Y
    sta CollisionEndY
    rts

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
; PhVcApplyOR / PhVcApplyAND — write one PF buffer row trio.
;   In:  A = row (0-2), Y = row count (≥1); masks in LineCount/CCX/CEY
;   PF0Buf[row], +3 (PF1), +6 (PF2) — the 9-byte buffer layout the
;   phase-cell path already uses (offset 0/3/6 + row).
;   Clobbers A/X/Y.
; ==============================================================================
    org $F9B0
PhVcApplyOR:
    tax
.PVo:
    lda PF0Buf,X
    ora LineCount
    sta PF0Buf,X
    lda PF0Buf+3,X
    ora CollisionCellX
    sta PF0Buf+3,X
    lda PF0Buf+6,X
    ora CollisionEndY
    sta PF0Buf+6,X
    inx
    dey
    bne .PVo
    rts

    org $F9E0
PhVcApplyAND:
    tax
.PVa:
    lda LineCount
    eor #$FF
    and PF0Buf,X
    sta PF0Buf,X
    lda CollisionCellX
    eor #$FF
    and PF0Buf+3,X
    sta PF0Buf+3,X
    lda CollisionEndY
    eor #$FF
    and PF0Buf+6,X
    sta PF0Buf+6,X
    inx
    dey
    bne .PVa
    rts

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
    cmp #$80
    beq .HFphase
    pha                         ; save class (b7 check clobbers A)
    lda EnemyDeadMask
    and #$80                    ; b7: crunch kill already happened?
    bne .HFmissP                ; yes → pass (wall stays, no re-kill)
    pla
    cmp #$81
    bne .HF82
    jsr HOVvcrunch
    beq .HFm81                  ; miss → drain + HOVnext
    pla
    pla
    pla
    pla                         ; kill → drain h,w,y,x (base on top for HOVlegHit)
    jmp $FCD3                   ; pad: sta $1FF8 / jmp HOVlegHit (bank2 image)
.HF82:
    cmp #$82
    bne .HFm81                  ; unknown b7 class → same drain path
    jsr HOVhcrunch
    beq .HFm81
    pla
    pla
    pla
    pla
    jmp $FCD3                   ; pad: sta $1FF8 / jmp HOVlegHit (bank2 image)
.HFmissP:
    pla                         ; drop saved class
.HFm81:
    pla
    pla
    pla
    pla                         ; drain h,w,y,x (base on top for HOVnext)
    jmp $FCCD                   ; pad: sta $1FF8 / jmp HOVnext (bank2 image)
.HFphase:
    lda EnemyDeadMask
    and #$60                    ; b5 armed | b6 phase dead
    cmp #$20                    ; armed AND not yet removed?
    bne .HFmiss
    jmp $FCD9                   ; pad: sta $1FF8 / jmp HOVafterGate (bank2 image)
.HFmiss:
    jmp $FCCD                   ; $80 miss: no field drain (none pushed)

; ==============================================================================
; HOVvcrunch — $81 kill test. Covered rect = [x, y, w, covered_h] (top
; rows of the bbox — same extent PhaseBlink stages this frame).
; Overlap: x ≤ max && x+w > min && y ≤ bottom && y+covered_h > top.
; Out: A = 1 kill (b7 latched) / 0 miss. Y clobbered (base on stack
; survives). CollisionX ($88 = Temp) scratch — HOV already owns it.
; ==============================================================================
HOVvcrunch:
    ; Entered via jsr from HOVFeatEntry: stack (top→) = ret(2), h, w, y, x,
    ; <base>. Fields from bank2 PreFields — no (FetchPtr) reads.
    tsx
    lda $0106,X                 ; x
    cmp CollisionCellX          ; x vs max col
    beq .HVx
    bcc .HVx
    lda #0
    rts
.HVx:
    sta LineCount               ; save x
    tsx
    lda $0105,X                 ; y
    cmp CollisionEndY           ; y vs bottom row
    beq .HVy
    bcc .HVy
    lda #0
    rts
.HVy:
    sta CollisionX              ; save y
    tsx
    clc
    lda $0106,X                 ; x
    adc $0104,X                 ; + w
    cmp CollisionEndX           ; x+w vs min col (strict >)
    beq .HVno
    bcc .HVno
    tsx
    lda $0103,X                 ; h
    sta LineCount               ; Phase B sprite shutter: covered = h (static
                                ;   full — same extent the ball renders; the
                                ;   per-frame CrunchClock sweep returns in
                                ;   Phase C with the sub-band window)
    lda CollisionX              ; y
    clc
    adc LineCount               ; y + covered_h
    cmp CollisionCellY          ; vs top row (strict >)
    beq .HVno2
    bcc .HVno2
    lda EnemyDeadMask
    ora #$80                    ; b7: crunch kill latch
    sta EnemyDeadMask
    lda #1
    rts
.HVno:
.HVno2:
    lda #0
    rts

; ==============================================================================
; HOVhcrunch — $82 kill test. Covered rect = [0, band, 2*covered_cells, 1]
; (prefix from col 0 — same extent PhaseBlink stages this frame).
; Overlap: band ∈ [top, bottom] && covered_w > min col.
; Rule 1 (user 2026-10-14): cold kill only while CLOSING (sc<32) and not
; totally closed (covered==full); hot (LineCount = MetaB b6, staged
; bank2-side by HOVFeatPre) exempts both gates.
; Out: A = 1 kill (b7 latched) / 0 miss.
; ==============================================================================
HOVhcrunch:
    ; Entered via jsr from HOVFeatEntry: stack (top→) = ret(2), h, w, y(band),
    ; x, <base>. Fields from bank2 PreFields — no (FetchPtr) reads.
    tsx
    lda $0105,X                 ; y = band
    cmp CollisionCellY          ; band < top?
    bcc .HHno
    cmp CollisionEndY           ; band vs bottom
    beq .HHw
    bcc .HHw
    bne .HHno
.HHw:
    tsx
    lda $0104,X                 ; w
    lsr                         ; full cells
    tax
    ; Rule (user 2026-10-16): cold kill while CLOSING (sc<52 = s<13 =
    ; dwell+grow under HcrClock — the grow half IS the closing sweep);
    ; hot (LineCount = MetaB, staged bank2-side by HOVFeatPre; asl×2
    ; brings b6 to C) exempts — any phase/extent kills. The old
    ; totally-closed exemption is GONE: a catch at the seal froze the
    ; player inside the wall (push prevents the approach; the seal-
    ; moment catch is the crunch). Opening (sc>=52) never kills.
    lda LineCount
    asl
    asl                     ; b7 out, b6 -> C
    bcs .HHcc               ; hot -> any phase/extent kills
    lda EnemyRamP
    lsr
    lsr                         ; sc
    cmp #52
    bcs .HHno                   ; opening half -> no kill
.HHcc:
    txa
    pha                     ; full — wall check stays callee-independent
    jsr HcrClock                ; n covered cells (X = full preserved)
    sta CollisionX              ; save covered (free temp here)
    lda LineCount
    asl
    asl                         ; b7 out, b6 -> C
    pla                         ; full (PLA preserves C)
    bcs .HHovl                  ; hot -> any extent kills
    ; cold + closing + caught kills at ANY extent (fall through)
.HHovl:
    lda CollisionX
    asl                         ; covered_w in 4px cols
    cmp CollisionEndX           ; covered_w vs min col (strict >)
    beq .HHno
    bcc .HHno
    lda EnemyDeadMask
    ora #$80
    sta EnemyDeadMask
    lda #1
    rts
.HHno:
    lda #0
    rts

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
    jmp $FB1A                   ; .PhRec (vcrunch; Y=base+4, iny→next class)
    .ds $FCC7 - *, 0
    sta $1FF8
    jmp $FB1A                   ; .PhRec (hcrunch; Y=base+4, iny→next class)
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
