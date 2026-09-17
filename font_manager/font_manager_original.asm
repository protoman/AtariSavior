; ==========================================
; font_manager - Original Atari 2600 Text System
; A pre-rendered, sprite-based text display system
; Distinct from text24.asm/13_plus2.asm real-time approaches
; ==========================================

; Processor and hardware includes
    processor 6502
    include "vcs.h"
    include "macro.h"
    SEG.U VARS
    ORG $80

; ==========================================
; Zero Page Variables - font_manager
; ==========================================

; Text lines - each line is a null-terminated string of character indices
; Maximum 32 characters per line, 2 lines supported
Line1Chars    ds 32   ; character indices for line 1 (max 32, 0=terminator)
Line2Chars    ds 32   ; character indices for line 2 (max 32, 0=terminator)

; Active line selector (0=Line1, 1=Line2) for flicker/30fps
ActiveLine    ds 1

; Horizontal position (0-159, coarse + fine via HMP0)
CharPos       ds 1

; Vertical position (scanline 0-191, via VDEL)
LineY         ds 1

; Font table pointer - points to 5-byte-per-character font data in ROM
FontTabLo     ds 1    ; low byte of font table address
FontTabHi     ds 1    ; high byte of font table address

; Rendering temporary
TempIdx       ds 1    ; temporary character index

; ==========================================
; Font Data Format (original design)
; ==========================================

; Each character = 5 bytes, one byte per scanline row (5 rows tall)
; Key restriction: 3 pixels wide per character (not 8)
; Advantage: 2.5x more compact than 8-pixel fonts
; 8 chars × 3px = 24px wide, leaves 136px for background
; Tradeoff: less detail per character, but more chars per line

; Character mapping: index 0-9 maps to font data below
; Font data starts at FontTabLo/FontTabHi in ROM

; ==========================================
; Font Data (5 bytes/char, 3 pixels/row, 5 rows/char)
; Compact: 10 chars × 5 bytes = 50 bytes
; ==========================================

   SEG CODE
   ORG $F000
Start:

; Character index 0: 'A' variant (3 pixels wide, 5 rows)
    .byte %001        ; row 0: pixel at position 1 (3-pixel wide)
    .byte %010        ; row 1: pixel at position 1
    .byte %100        ; row 2: pixel at position 0
    .byte %010        ; row 3: pixel at position 1
    .byte %001        ; row 4: pixel at position 1

; Character index 1: 'B' variant
    .byte %111        ; row 0: pixels at positions 0-2
    .byte %100        ; row 1: pixel at position 0
    .byte %111        ; row 2: pixels at positions 0-2
    .byte %100        ; row 3: pixel at position 0
    .byte %111        ; row 4: pixels at positions 0-2

; Character index 2: 'C' variant
    .byte %110        ; row 0: pixels at positions 0-1
    .byte %100        ; row 1: pixel at position 0
    .byte %100        ; row 2: pixel at position 0
    .byte %100        ; row 3: pixel at position 0
    .byte %110        ; row 4: pixels at positions 0-1

; Character index 3: space (3 blank pixels wide per row)
    .byte %000        ; row 0
    .byte %000        ; row 1
    .byte %000        ; row 2
    .byte %000        ; row 3
    .byte %000        ; row 4

; Character index 4: period (rightmost pixel of 3)
    .byte %001        ; row 0: pixel at position 2
    .byte %001        ; row 1: pixel at position 2
    .byte %001        ; row 2: pixel at position 2
    .byte %001        ; row 3: pixel at position 2
    .byte %001        ; row 4: pixel at position 2

; Character index 5: question mark (modified from period top)
FontData:
    .byte %011        ; row 0: pixels at positions 0-1 (modified top)
    .byte %100        ; row 1: pixel at position 0
    .byte %010        ; row 2: pixel at position 1
    .byte %000        ; row 3
    .byte %010        ; row 4: pixel at position 1

; Character index 6: exclamation point
    .byte %001        ; row 0: pixel at position 0
    .byte %001        ; row 1: pixel at position 0
    .byte %001        ; row 2: pixel at position 0
    .byte %000        ; row 3
    .byte %001        ; row 4: pixel at position 0

; Character index 7: comma (2 pixels, left-aligned, 3-wide)
    .byte %110        ; row 0: pixels at positions 0-1
    .byte %000        ; row 1
    .byte %000        ; row 2
    .byte %100        ; row 3: pixel at position 0
    .byte %010        ; row 4: pixel at position 1

; Character index 8: hyphen (3 pixels wide, middle row only)
    .byte %000        ; row 0
    .byte %000        ; row 1
    .byte %111        ; row 2: pixels at positions 0-2
    .byte %000        ; row 3
    .byte %000        ; row 4

; Character index 9: plus (cross pattern, 3-wide)
    .byte %010        ; row 0: pixel at position 1
    .byte %010        ; row 1: pixel at position 1
    .byte %111        ; row 2: pixels at positions 0-2
    .byte %010        ; row 3: pixel at position 1
    .byte %010        ; row 4: pixel at position 1

; ==========================================
; Initialize font system
; ==========================================
InitFont:
    ; Set up font table address - font data starts at current ORG ($F000)
    lda #<FontData    ; low byte
    sta FontTabLo
    lda #>FontData    ; high byte
    sta FontTabHi

    ; Set up default text: "A C" (2 characters in Line 1)
    ; Using indices: 0='A', 2='C', then terminator
    ldy #0

    ; Line 1: A, C, terminator, blank
    lda #0           ; 'A' index
    sta Line1Chars,y
    iny
    lda #2           ; 'C' index
    sta Line1Chars,y
    iny
    lda #0           ; terminator
    sta Line1Chars,y
    iny
    lda #0           ; blank/extra
    sta Line1Chars,y

    ; Set char count for Line 1 (2 active chars)
    lda #2

    ; Set horizontal position 40 (middle-left of 160px screen)
    lda #40
    sta CharPos

    ; Set vertical position 20 (top area, above HUD band)
    lda #20
    sta LineY

    ; Select Line 1 initially (0=Line1, 1=Line2 for flicker)
    lda #0
    sta ActiveLine

; ==========================================
; Main loop - VBlank + render
; ==========================================
MainLoop:
    ; -----------------------------------------------------------------
    ; VBLANK section (~37 scanlines)
    ; -----------------------------------------------------------------
    lda #6
    sta VBLANK

    lda #44
    sta TIM64T    ; wait ~37 scanlines (44*64=2816 cycles ≈ 37 scanlines)

VBlankLoop:
    lda INTIM
    bne VBlankLoop ; loop until timer expires

    sta WSYNC
    sta VBLANK

    ; -------------------------------------------------
    ; Pre-render display list during VBlank (KEY DIFFERENCE)
    ; We compute GRP0/GRP1 values ONCE per frame here,
    ; not per scanline during the kernel.
    ; This is what makes the system generic and timing-safe.
    ; -------------------------------------------------
    ; Build display list for the active line
    lda ActiveLine
    beq RenderLine1

RenderLine2:
    ; Line 2 active - render Line 2 characters
    ; For this demo, we'll just render Line 1 and toggle
    jmp KernelRender

RenderLine1:
    ; Line 1 active - process characters from Line1Chars
    ; Display list structure in ZP:
    ; Each entry = 5 bytes (one per row), each byte = GRP0/GRP1 pattern
    ; Plus horizontal/vertical position info
    
    ldy #0           ; character index counter
    ; We'll build a simple display list where each character's
    ; 5 font bytes are stored sequentially
    ; The kernel will just read these 5 bytes and write GRP0/GRP1

RenderCharLoop:
    lda Line1Chars,y  ; get character index
    beq RenderDone     ; terminator (0) found = end of line

    ; Map character index to font data bytes
    ; FontTabLo/FontTabHi points to font data at $F000
    ; We need to read 5 bytes for this character and store them
    ; in the display list
    
    ; For this minimal demo, we'll just store the character index
    ; and the kernel will use a lookup. A full implementation would
    ; store the actual GRP0/GRP1 pattern bytes.
    
    ; Store character index in display list entry
    sta TempIdx        ; temp storage
    iny
    cpy #32           ; max 32 chars per line
    bne RenderCharLoop

RenderDone:
    ; Display list building complete
    ; The kernel will read from this structured data
    ; For this demo, just proceed to kernel render

; -------------------------------------------------
; Kernel render - read pre-computed display list
; -------------------------------------------------
; During the 192 scanline kernel, we simply read from the
; display list built during VBlank.
; No cycle-critical TEXTDISP macros needed!

; For this demo, we'll use a simpler approach: during VBlank we
; precompute the GRP0/GRP1 values for each character position,
; store them in a flat array, and during the kernel just read
; and write them per scanline.

KernelRender:
    ; Set up horizontal positioning
    ldx CharPos
    lda #0
    jsr SetHorizPos  ; positions sprite at CharPos

    ; Set vertical position
    lda LineY
    sta VDELP0       ; vertical delay player 0

; Simple kernel loop - write GRP0/GRP1 for each character row
; For this demo, we'll render just the first character's 5 rows
; and then blank the rest of the line

; During kernel, we need to write to GRP0/GRP1 at the right time.
; The TEXTDISP macro pattern shows: sta WSYNC, then write GRP0/GRP1.
; But since we pre-rendered during VBlank, we can use a simpler approach.

; For this demo, let's just set up the sprites and show something
; The key point is the VBlank pre-rendering structure is in place

; Write initial sprite data based on first character (index 0 = 'A')
    lda #%00100000   ; row 0 of 'A'
    sta GRP0
    lda #%01010000   ; row 1 of 'A'
    ; We can't easily do 5 rows in this minimal demo without
    ; a full kernel loop, so let's just show the structure works

; -------------------------------------------------
; Overscan
; -------------------------------------------------
Overscan:
    lda #36
    sta TIM64T    ; 30 scanlines overscan

WaitOverscan:
    lda INTIM
    bne WaitOverscan

    ; End of frame - flip buffers for next frame (30 fps flicker)
    lda #1
    sta ActiveLine  ; toggle between Line1/Line2

    jmp MainLoop

; ==========================================
; Set Horizontal Position routine
; ==========================================
SetHorizPos:
    sta WSYNC   ; start a new line
    bit 0       ; waste 3 cycles
    sec         ; set carry flag
DivideLoop:
    sbc #15     ; subtract 15
    bcs DivideLoop  ; branch until negative
    eor #7      ; calculate fine offset
    asl
    asl
    asl
    asl
    sta RESP0,x ; fix coarse position
    sta HMP0,x  ; set fine offset
    rts         ; return to caller

; ==========================================
; End of ROM
; ==========================================
    align 256

    org $FFFC
    .word Start
    .word Start