  processor 6502

    include "comparison/lo-a-rad-dragon/vcs.h"
    include "comparison/lo-a-rad-dragon/macro.h"

; F6 bank1 start screen. The generated body is a relocated, byte-faithful port
; of docs/tutorial/13_plus2.asm. It keeps the demo's timing, font, orange PF
; mask/borders, centered text, and 13_plus2 TEXTDISP sequence.
GameMode = $b2
GameStart = $f550

    seg code
    org $f000
Reset:
    lda #0
    sta $1FF6

    include "generated/menu_13plus2.asm"
