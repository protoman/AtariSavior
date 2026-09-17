processor 6502
    include "vcs.h"
    include "macro.h"
    SEG.U VARS
    ORG $80

; ==========================================
; Zero Page Variables - Font Manager
; ==========================================

; Text buffers - double buffered for flicker / 30 fps
; Buffer A (active this frame)
TextBufA    ds 32   ; 32 chars max per line, stored sequentially
TextBufB    ds 32   ; 32 chars max per line, stored sequentially

; Current active buffer selector (0=BufA, 1=BufB)
ActiveBuf   ds 1

; Text line positions and counters
LineCount   ds 1    ; number of characters in current line (0-31)
CharPos     ds 1    ; horizontal position (0-159)
LineY       ds 1    ; vertical position (scanline 0-191)

; Font table pointer - points to font data in ROM
FontTableLo ds 1    ; low byte of font table address
FontTableHi ds 1    ; high byte of font table address

; Rendering temporaries
TempRow     ds 1    ; temporary row index (0-4 for 5-row chars)

; ==========================================
; Font Data Format
; ==========================================
; Each character = 5 bytes, one byte per scanline row (5 rows tall)
; Bit pattern: set bits = sprite color pixels (GRP0/GRP1), clear bits = transparent
; 8 pixels wide per character (1 byte = 8 horizontal color clocks)
; Font table starts at FontTableLo/FontTableHi
;
; Example character 'A' (5 bytes, 8 pixels wide):
;   %00100000  ; row 0: pixel 2 on
;   %01010000  ; row 1: pixels 1,3 on
;   %01110000  ; row 2: pixels 1,2,3 on
;   %01010000  ; row 3: pixels 1,3 on
;   %01010000  ; row 4: pixels 1,3 on
;
; Compact: 5 bytes/char × 256 chars max = 1.28K for full font
; Shared across banks via identical font ROM data

org $A0
FontData:
; -----------------------------------------
; Character code 0x41 = 'A' (baseline)
; -----------------------------------------
_AChar:
    .byte %00100000  ; row 0: pixel 2 on
    .byte %01010000  ; row 1: pixels 1,3 on
    .byte %01110000  ; row 2: pixels 1,2,3 on
    .byte %01010000  ; row 3: pixels 1,3 on
    .byte %01010000  ; row 4: pixels 1,3 on

; -----------------------------------------
; Character code 0x42 = 'B'
; -----------------------------------------
_BChar:
    .byte %01100000  ; row 0: pixels 0-2 on
    .byte %01010000  ; row 1: pixels 1,3 on
    .byte %01100000  ; row 2: pixels 0-2 on
    .byte %01010000  ; row 3: pixels 1,3 on
    .byte %01100000  ; row 4: pixels 0-2 on

; -----------------------------------------
; Character code 0x20 = space (5 blank rows)
; -----------------------------------------
_Space:
    .byte %00000000  ; row 0
    .byte %00000000  ; row 1
    .byte %00000000  ; row 2
    .byte %00000000  ; row 3
    .byte %00000000  ; row 4

; -----------------------------------------
; Character code 0x2E = period
; -----------------------------------------
_Period:
    .byte %00000000  ; row 0
    .byte %00000000  ; row 1
    .byte %00000000  ; row 2
    .byte %00000000  ; row 3
    .byte %00000010  ; row 4: pixel 1 on

; -----------------------------------------
; Character code 0x3F = question mark
; -----------------------------------------
_Question:
    .byte %00000110  ; row 0
    .byte %00000001  ; row 1
    .byte %00000010  ; row 2
    .byte %00000000  ; row 3
    .byte %00000010  ; row 4

; -----------------------------------------
; Character code 0x21 = exclamation point
; -----------------------------------------
_Excl:
    .byte %00000010  ; row 0: pixel 1 on
    .byte %00000010  ; row 1: pixel 1 on
    .byte %00000010  ; row 2: pixel 1 on
    .byte %00000000  ; row 3
    .byte %00000010  ; row 4: pixel 1 on

; -----------------------------------------
; Character code 0x2C = comma
; -----------------------------------------
_Comma:
    .byte %00000000  ; row 0
    .byte %00000000  ; row 1
    .byte %00000000  ; row 2
    .byte %00000010  ; row 3: pixel 1 on
    .byte %00000100  ; row 4: pixel 2 on

; -----------------------------------------
; Character code 0x2D = hyphen
; -----------------------------------------
_Hyphen:
    .byte %00000000  ; row 0
    .byte %00000000  ; row 1
    .byte %00000111  ; row 2: pixels 0-2 on
    .byte %00000000  ; row 3
    .byte %00000000  ; row 4

; -----------------------------------------
; Character code 0x2B = plus
; -----------------------------------------
_Plus:
    .byte %00000010  ; row 0: pixel 1 on
    .byte %00000010  ; row 1: pixel 1 on
    .byte %00000111  ; row 2: pixels 0-2 on
    .byte %00000010  ; row 3: pixel 1 on
    .byte %00000010  ; row 4: pixel 1 on

; End of font data marker
FontDataEnd:

; Font offset table - indexed by character code minus 'A'
; Each entry is the address of that character's 5-byte font data
; Index 0 = 'A' (0x41), Index 1 = 'B' (0x42), etc.
; We have definitions for A, B, space, period, question, exclamation, comma, hyphen, plus
; That's indices 0-8 (9 characters)
FontOffsets:
    .word _AChar   ; index 0 = 'A'
    .word _BChar   ; index 1 = 'B'
    .word _Space   ; index 2 = ' ' (space)
    .word _Period  ; index 3 = '.'
    .word _Question ; index 4 = '?'
    .word _Excl    ; index 5 = '!'
    .word _Comma   ; index 6 = ','
    .word _Hyphen  ; index 7 = '-'
    .word _Plus    ; index 8 = '+'

; ==========================================
; Code Segment
; ==========================================
SEG CODE
ORG $F000

Start:
    CLEAN_START

; ==========================================
; Initialize Font System
; ==========================================
InitFont:
    ; Set up font table address
    lda #<FontData    ; low byte
    sta FontTableLo
    lda #>FontData    ; high byte
    sta FontTableHi

    ; Set up default text: "A ! A !" = 8 characters
    ; Using font offset table indices:
    ; Index 0 = 'A', Index 5 = '!', Index 2 = space
    ; Pattern: A, space, !, A, space, !, A, space
    ldy #0
LoadDefaultText:
    lda IndexChars,y
    sta TextBufA,y
    iny
    cpy #8
    bne LoadDefaultText
    lda #8
    sta LineCount
    lda #40       ; horizontal position 40 (middle of 160px screen)
    sta CharPos
    lda #20       ; vertical position 20 (top of playfield)
    sta LineY

    lda #0        ; select buffer A for this frame
    sta ActiveBuf

; Character indices: 0=A, 1=unused, 2=space, 3=unused, 4=unused, 5=!, 6=unused, 7=unused
IndexChars:
    .byte 0, 0, 2, 0, 0, 5, 0, 0

; ==========================================
; Main Loop
; ==========================================
MainLoop:
    ; -----------------------------------------------------------------
    ; VBLANK section (~37 scanlines)
    ; -----------------------------------------------------------------
    ; Vertical sync
    lda #6
    sta VBLANK

    lda #44
    sta TIM64T    ; wait ~37 scanlines (44*64 cycles = 2816 ≈ 37 scanlines at 60Hz)

VBlankLoop:
    lda INTIM
    bne VBlankLoop ; loop until timer expires

    sta WSYNC
    sta VBLANK

    ; -------------------------------------------------
    ; Update text buffer (double buffer for flicker / 30 fps)
    ; -------------------------------------------------
    lda ActiveBuf
    beq UseBufferA
UseBufferB:
    ; Use buffer B this frame - clear it
    ldy #0
    ldx #8
ClearBufB:
    sta TextBufB,y  ; store 0 (null char)
    iny
    dex
    bne ClearBufB
    lda #1        ; select buffer B
    sta ActiveBuf
    jmp PreRenderStart

UseBufferA:
    ; Use buffer A this frame - clear it
    ldy #0
    ldx #8
ClearBufA:
    sta TextBufA,y  ; store 0 (null char)
    iny
    dex
    bne ClearBufA
    lda #0        ; select buffer A
    sta ActiveBuf

; -------------------------------------------------
; Pre-render display list during VBlank
; -------------------------------------------------
PreRenderStart:
    ; Set up horizontal positioning for first character
    ldx #0          ; character index counter
    lda CharPos
    jsr SetHorizPos   ; positions sprite at CharPos (uses WSYNC internally)

    ; Set up vertical position (VDEL)
    lda LineY
    sta VDELP0       ; vertical delay player 0 (1-7 scanlines)

    ; -----------------------------------------------------------------
    ; Render each character from the text buffer
    ; -----------------------------------------------------------------
    ldx #0           ; character index counter
    ldy LineCount    ; number of characters
    cpy #0
    beq RenderBlank  ; if no characters, just blank

RenderCharsLoop:
    ; ---------------------------------
    ; Get character index from active buffer
    ; ---------------------------------
    lda ActiveBuf
    beq _GetFromA
    ; Buffer B - index into TextBufB
    ldy TextBufB,x  ; read character index from buffer B
    bne _ContinueFontLookup

_GetFromA:
    ; Buffer A - index into TextBufA
    ldy TextBufA,x  ; read character index from buffer A

_ContinueFontLookup:
    ; Map character index to font table offset
    ; Character indices: 0='A', 1=undefined...2=space, 5=!
    ; Our FontOffsets has 9 entries (indices 0-8)
    ; We need to validate the index is in range 0-8
    ; For this simple example, assume valid indices

    tax              ; X = character index (0-8)
    ldy FontOffsets,x ; get low byte of font offset
    lda FontTableHi  ; get high byte of font table
    ; Now (Y+FontTableHi) points to the 5-byte font data for this char

    ; ---------------------------------
    ; Render 5 rows of the character
    ; ---------------------------------
    ldy #0           ; row counter (0-4)
RenderRows:
    ; Get font byte for this row
    ; (FontTableLo),Y indirect indexed read
    lda (FontTableLo),y  ; read byte from font table

    ; Advance to next row
    iny
    cpy #5           ; have we done 5 rows?
    bne RenderRows

    ; Advance to next character
    inx
    cpx LineCount    ; compare with total count
    bne RenderCharsLoop

RenderBlank:
    ; If LineCount < 8, blank remaining character positions
    ; (In a full implementation, we'd write blank GRP0/GRP1)
    ; For now, just ensure we don't read past our data

; ==========================================
; Set Horizontal Position routine
; ==========================================
; Sets RESP0,x and HMP0,x to position sprite at given X position (0-159)
; Uses the standard Atari 2600 coarse/fine division algorithm
SetHorizPos:
    sta WSYNC   ; start a new line (absorbs jitter)
    bit 0       ; waste 3 cycles
    sec         ; set carry flag
DivideLoop:
    sbc #15     ; subtract 15
    bcs DivideLoop  ; branch until negative (X = floor(X/15))
    eor #7      ; calculate fine offset complement
    asl         ; multiply by 2 (for HMP nibble * 2)
    asl         ; 
    asl         ; 
    asl         ; HMP0,x = fine offset (0-15, but we use complement)
    sta RESP0,x ; fix coarse position (writes RESP0 to reset sprite counter)
    sta HMP0,x  ; set fine offset
    rts         ; return to caller

; ==========================================
; Text data - character indices
; ==========================================
; These indices map to FontOffsets table entries
; Index 0 = 'A' (0x41), Index 2 = space, Index 5 = '!'
TextData:
    ; "A ! A !" pattern for 8 chars:
    ; A, space, !, A, space, !, A, space
    .byte 0, 0, 2, 0, 0, 5, 0, 0

; ==========================================
; End of ROM
; ==========================================
    align 256

    org $FFFC
    .word Start
    .word Start