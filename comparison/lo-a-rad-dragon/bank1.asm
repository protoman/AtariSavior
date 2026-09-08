  processor 6502

; The game must be assembled from the REPO ROOT (same rule as bank0.asm): the
; includes and the generated/ start screen data use root-relative paths.
    include "comparison/lo-a-rad-dragon/vcs.h"
    include "comparison/lo-a-rad-dragon/macro.h"

; ==============================================================================
; SAVIOR 2600 - bank1 (F6 16K cartridge, physical offset $1000)
; ==============================================================================
; Bank1 holds the START SCREEN (bank0 is full of game code/data). The menu is
; self-contained: it owns its own vsync/vblank/kernel/overscan and loops on
; itself until the fire button starts the game.
;
; Bank handoff (the F6 fold trick):
;   The 6502 fetches the NEXT instruction byte AFTER `sta $1FFx` from the newly
;   selected bank. Two 8-byte stubs are therefore replicated byte-for-byte at
;   the SAME window addresses in BOTH banks (see bank0.asm "F6 cross-bank fold
;   pads"), so a bank-switching CPU keeps executing the same instruction stream:
;
;     $fd00 ToMenuStub  lda #0 / sta $1FF7 / jmp MenuMain   (bank0 -> menu)
;     $fe00 ToGameStub  lda #0 / sta $1FF6 / jmp GameStart  (bank1 -> game)
;
;   bank0's StartFrame hits ToMenuStub when GameMode==0; the menu hits
;   ToGameStub when fire is pressed (GameMode is set to 1 first).
;
; The menu kernel renders the 40x192 start screen as an ASYMMETRIC playfield:
; CTRLPF=0 (no reflection), the LEFT half's PF bytes are written during HBLANK
; and the RIGHT half's are re-written mid-line (after the left risers have
; been drawn, before the right half starts). Tables come from
; generated/start_screen.asm (tools/start_screen.py), one 192-byte block per
; register/half, each page-aligned so the kernel's indexed loads never cross a
; page (stable timing).
;
;
; Frame timeline (262 scanlines, same lock as the game):
;   VSYNC        3 lines
;   VBLANK      38 lines   (the 3-line bank0 prefix already ran before MenuMain)
;   Kernel      192 lines  asymmetric playfield
;   Overscan     29 lines  fire-button check, waits the TIM64T window
;
; Fire button = INPT4 (joystick 0), active low.

; Fixed window addresses shared with bank0 (bank0.asm places its GameStart code
; at $f500 and EQUates MenuMain to $f540). Both banks' fold stubs reference
; these constants so the `jmp` operands assemble to identical bytes.
GameStart = $f500
MenuMain  = $f540
; ZP flag shared with bank0: GameMode lives at $B2 (see bank0.asm "seg.u
; Variables" - it is the 51st byte, so $80+51 = $B2). It must be a fixed
; address here because the menu and the game read/write it cross-bank.
GameMode  = $b2
OVSCAN_TIME = 33        ; same TIM64T lock value as bank0's overscan


    seg code
    org $f000

Reset:
    lda #0
    sta $1FF6           ; F6 boot stub (parity with the other banks): if bank1
                        ; is ever powered up, the fetch after this store lands
                        ; on bank0's landing pad ($F005: jmp Main).
    org $f540
MenuMain:
; --- VSYNC + VBLANK: the menu owns its own frame loop, so it re-issues the
;     vsync (the bank0 frame that handed off here already ran its 3 vsync
;     lines, but starting clean keeps every menu frame at 262 lines). ---
    lda #2
    sta VBLANK
    sta VSYNC
    repeat 3
      sta WSYNC
    repend
    lda #0
    sta VSYNC           ; turn off VSYNC

; Remaining VBLANK (38 lines total, matching the game's pre-kernel budget).
; Lines: ~30 pause loop + ~5 text-window copy + ~2 sprite positions + 1 HMOVE.
    ldx #30
.MVBlank:
    sta WSYNC
    dex
    bne .MVBlank

; --- no text24 setup needed ---

    lda #0
    sta VBLANK          ; turn off VBLANK

; --- Menu static setup (latched once per frame) ---
    sta COLUBK          ; black background (A = 0)
    lda #$0E            ; emulator-aware white (kPalette hue 0 luma 7)
    sta COLUPF
    sta COLUP0
    sta COLUP1
    lda #0
    sta CTRLPF          ; D0=0: no reflection - the mid-line PF rewrites win
    lda #0
    sta NUSIZ0
    sta NUSIZ1
    lda #0
    sta VDELP0
    sta VDELP1
    lda #0
    sta REFP0
    sta REFP1
    sta GRP0
    sta GRP1
    sta ENAM0
    sta ENAM1
    sta ENABL
    sta AUDV0           ; silence audio channel 0 (jet engine lives in bank0)
    sta AUDV1

; --- Kernel: asymmetric playfield rows 0..191.
    ldx #0
.MenuLine:
    sta WSYNC
    lda StartScreenColors,x
    sta COLUPF                    ; COLUPF lands during HBLANK
    lda StartScreenPF0L,x
    sta PF0
    lda StartScreenPF1L,x
    sta PF1
    lda StartScreenPF2L,x
    sta PF2                      ; left half done (~cycle 28)
    lda StartScreenPF0R,x
    sta PF0                      ; right PF0 lands ~cyc 37 (window 28..49)
    nop
    lda StartScreenPF1R,x
    sta PF1                      ; right PF1 lands ~cyc 46 (window 38..54)
    nop
    lda StartScreenPF2R,x
    sta PF2                      ; right PF2 lands ~cyc 57 (window 49..65)
    inx
    cpx #START_SCREEN_ROWS       ; 192 rows
    bne .MenuLine

.KernelTail:

    lda #2
    sta VBLANK
    lda #OVSCAN_TIME            ; same TIM64T lock value as the game frame
    sta TIM64T

; Fire button (INPT4 bit 7, active low) starts the game.
    lda INPT4
    bmi .NoFire
    lda #1
    sta GameMode
    jmp ToGameStub              ; bank1 -> bank0, lands in GameStart (level 0)

.NoFire:
    lda INTIM
    bne .NoFire
    jmp MenuMain                ; next menu frame (menu owns its own vsync)

; ------------------------------------------------------------------------------
; ------------------------------------------------------------------------------

; ------------------------------------------------------------------------------
; Start screen bitmaps (192 bytes per table, page-aligned; generated).
; ------------------------------------------------------------------------------
    include "generated/start_screen.asm"

; ------------------------------------------------------------------------------
; F6 cross-bank fold pads - MUST match bank0's copies at these addresses
; (identical bytes, see the header comment). The menu enters via ToGameStub's
; `sta $1FF6`; after the write the fetch at $fe05 comes from bank0 (== bank0's
; ToGameStub `jmp GameStart`).
; ------------------------------------------------------------------------------
    org $fd00
ToMenuStub:
    lda #1
    sta $1FF7           ; select bank1 (this screen)
    jmp MenuMain        ; MenuMain = $f540
    org $fe00
ToGameStub:
    lda #0
    sta $1FF6           ; select bank0 (game code)
    jmp GameStart       ; GameStart = $f500

    org $fffc
    .word Reset      ; unused by F6 (bank3 owns the boot vector) but fills 4K
    .word Reset