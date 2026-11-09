    processor 6502
    seg code
    org $F000
; ==============================================================================
; Bank6 - the GAMEPLAY CAVE KERNEL (HERO-style; plans/hero_style_kernel_plan.md)
; ------------------------------------------------------------------------------
; Entered from bank0's VBL tail (`sta $1FFA` at GoKernel6; the byte after it is
; `jmp Kernel6Entry` here). Runs the whole 144-line cave, then hands over to the
; bank1 HUD through the fold pad at $FC68 (its bytes live in table page $FC).
;
; The kernel lines, sprite tables and LUTs are GENERATED (tools/cave_kernel_gen.py;
; every scanline is a cycle-exact timeline asserted at generation time, the tables
; come from the art in kernel.asm). The prologue is bank6_prologue.inc, shared with the
; standalone test ROM in tools/proto.
;
; Zero page: the kernel-local state lives in bytes that are free while the cave runs
; (bank1-only HUD bytes, VBL/overscan scratch, and the stack bytes $F8-$FF: bank6 never
; calls). The map is tools/cave_kernel_gen.py KERNEL_ZP (generated/cave_zp.inc).
; ==============================================================================

; power-up stub (mandatory in EVERY bank: F4 powers up in an undefined bank)
    lda #0
    sta $1FF4                       ; select bank0 - the fetch at $F005 is its jmp GameStart

    include "colors.inc"
    include "generated/bank6_equs.inc"
    include "generated/cave_zp.inc"
    include "generated/cave_luts.inc"
CaveFrameLo:    .byte <PlayerSpriteA,<PlayerSpriteB,<PlayerWalkA,<PlayerWalkB

; ---------------------------------------------------------------- entry from bank0
    org Kernel6Pad
    jmp Kernel6Entry

Kernel6Entry:
    include "bank6_prologue.inc"

    ; ---- wait for the VBL timer, then start the kernel (one blank line first) ----
.wait:
    lda INTIM
    bne .wait
    ; The old kernel spent 8 more scanlines on the cave (two dead setup lines per band change);
    ; the frame keeps its 272 lines (every gate and TV timing assumes it) by waiting here,
    ; with VBLANK still on, so the picture ends where it always did.
    ldx #CAVE_DEAD_LINES
.pad:
    sta WSYNC
    dex
    bne .pad
    sta WSYNC
    lda #0
    sta VBLANK
    sta WSYNC
    jmp BandPad

    include "generated/cave_kernel.inc"

; ---------------------------------------------------- hand-off to the bank1 HUD
; The kernel's last line falls through here at cycle 0 of the first HUD line. The old kernel
; reached the HUD pad at cycle 33; MenuMain's first PF store must keep landing at cycle 47,
; so the nops make up the difference.
KernelExit:
    lda #0
    sta ENABL
    sta ENAM1                       ; end the whole-cave M1 latch
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    jmp $FC68                       ; fold pad (in table page $FC): lda #1 / sta $1FF5 / jmp $F540

    include "generated/cave_slot1.inc"   ; the second object's positioning lines (entered by jmp)

    include "generated/cave_tables.inc"

    org $FFFA
    .word $F000
    .word $F000
    .word $F000
