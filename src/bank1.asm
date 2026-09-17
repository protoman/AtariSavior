    processor 6502
; ==============================================================================
; bank1 — 13+2 HUD rendering (F6 bankswitch, physical offset $1000)
; ==============================================================================
; Bank1 is called from bank0 during the HUD band via fold-pad trampoline.
; On power-up, bank3's stub selects bank0, so bank1 never runs at boot.
;
; Entry point: MenuMain at $F540 (must match bank0's ToMenuStub jmp target)
; ==============================================================================

; --- TIA write addresses ---
VSYNC   = $00
VBLANK  = $01
WSYNC   = $02
NUSIZ0  = $04
NUSIZ1  = $05
COLUP0  = $06
COLUP1  = $07
COLUPF  = $08
COLUBK  = $09
CTRLPF  = $0A
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
VDELP0  = $25
VDELP1  = $26
HMOVE   = $2A
HMCLR   = $2C

; --- RIOT addresses ---
TIM64T  = $0296
INTIM   = $0284

; --- HUD entry point (called from bank0 fold-pad) ---
; Bank0's trampoline does: lda #1 / sta $1FF7 / jmp MenuMain
; MenuMain must be at $F540 so the jmp target matches.
    org $F540
MenuMain:
    ; --- Save bank0 state (TODO: implement HUD rendering here) ---
    ; For now, just return to bank0
    lda #0
    sta $1FF6                   ; select bank0
    rts

; --- Pad to vectors at $FFFA ---
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                 ; NMI → bank0 stub
    .word $F000                 ; RESET → bank0 stub
    .word $F000                 ; IRQ → bank0 stub
