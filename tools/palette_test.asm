; palette_test.asm - empirical byte -> displayed-color probe for the local Stella.
; Full-screen solid COLUPF; each fire press advances COLUPF through TestBytes (0..7, wraps).
; The visible color tells us Stella's actual byte->RGB mapping (tv.filter=0 path).
; Build: dasm tools/palette_test.asm -f3 -opalette_test.bin
; Run:   stella palette_test.bin   (press space = left joystick fire)

    processor 6502

VSYNC   equ $00
VBLANK  equ $01
WSYNC   equ $02
COLUPF  equ $08
COLUBK  equ $09
CTRLPF  equ $0a
PF0     equ $0d
PF1     equ $0e
PF2     equ $0f
INPT4   equ $0c

ColorIdx   equ $80
PrevFire   equ $81

    org $f000
Start:
    sei
    cld
    ldx #$ff
    txs
    lda #$00
    sta COLUBK
    lda #$01
    sta CTRLPF
    lda #$f0
    sta PF0
    lda #$ff
    sta PF1
    sta PF2
    lda #$00
    sta ColorIdx
    sta PrevFire
    lda TestBytes
    sta COLUPF

MainLoop:
    lda #$02
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #$00
    sta VSYNC

    jsr ReadFire

    ldx #35
.VBlank:
    sta WSYNC
    dex
    bne .VBlank

    ldx #30
.Overscan:
    sta WSYNC
    dex
    bne .Overscan

    jmp MainLoop

ReadFire:
    lda INPT4
    bmi .Released
    lda PrevFire
    bne .Held
    inc ColorIdx
    lda ColorIdx
    and #$07
    sta ColorIdx
.Held:
    lda #$01
    sta PrevFire
    jmp .Apply
.Released:
    lda #$00
    sta PrevFire
.Apply:
    ldx ColorIdx
    lda TestBytes,x
    sta COLUPF
    rts

TestBytes:
    .byte $0e, $12, $16, $28, $2a, $64, $84, $a4

    org $fffc
    .word Start
    .word Start