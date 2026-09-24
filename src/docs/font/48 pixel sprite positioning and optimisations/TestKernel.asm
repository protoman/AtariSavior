;============================================================================== 
	processor 6502
	include "src\vcs.h"	
	
;============================================================================== 
;								V A I R A B L E S
;============================================================================== 


	MAC DIVIDE_BY_15
	sec
.divideby15
	sbc #15 
	bcs .divideby15
	tay
	lda fineAdjustTable,y 
	ENDM
	
	SEG.U VAIRABLES_BEGIN
	ORG $80

tempY					ds 1
temp2					ds 1
temp3					ds 1

	SEG VAIRABLES_END

	SEG
	ORG $F000
	
fineAdjustBegin

	.byte %01110000 ; Left 7             
	.byte %01100000 ; Left 6            
	.byte %01010000 ; Left 5            
	.byte %01000000 ; Left 4            
	.byte %00110000 ; Left 3            
	.byte %00100000 ; Left 2            
	.byte %00010000 ; Left 1            
	.byte %00000000 ; No movement.            
	.byte %11110000 ; Right 1            
	.byte %11100000 ; Right 2            
	.byte %11010000 ; Right 3            
	.byte %11000000 ; Right 4            
	.byte %10110000 ; Right 5            
	.byte %10100000 ; Right 6            
	.byte %10010000 ; Right 7
	
fineAdjustTable EQU fineAdjustBegin - %11110001 ; NOTE: %11110001 = -15

;============================================================================== 
;							S Y S T E M - C L E A R
;============================================================================== 

Reset
    ldx #0
    lda #0 
.Clear  
	sta 0,x 
    inx 
    bne .Clear
	
;==============================================================================
;									M A I N
;==============================================================================

	lda #1
	sta CTRLPF ; reflection

;===========================
Main

VerticalSync               
    lda #0
    sta VBLANK
    lda #2
    sta VSYNC
    sta WSYNC
    sta WSYNC
    sta WSYNC
    lda #0
    sta VSYNC  
 
VerticalBlank
	ldx #48
.verticalBlank  
	sta WSYNC
    dex
    bne .verticalBlank	
;===========================
	jmp DrawFrame	
;===========================
Overscan
	lda #42
	sta TIM64T	
	
.TimerLoop
	lda INTIM
	cmp #0
	bne .TimerLoop
	
	jmp Main
;===========================	

;==============================================================================
;					B A C K G R O U N D - D R A W I N G - K E R N E L
;==============================================================================

DrawFrame
	ldx #227

.frame
	stx COLUBK
	sta WSYNC
	dex 
	cpx #100
	beq SpriteCode
	
	cpx #0
	bne .frame
	jmp Overscan
	
	
;==============================================================================
;					S P R I T E - D R A W I N G - K E R N E L
;==============================================================================

SpriteCode

	lda #0
	sta COLUBK 
	
;=================================	sprite positioning 

	lda #28
	sta WSYNC	
	
	DIVIDE_BY_15
	sta HMP0
	sta RESP0 
	
	lda #36
	sta WSYNC
	
	DIVIDE_BY_15
	sta HMP1
	sta RESP1 
	sta WSYNC	
	sta HMOVE

;=================================

; player colour
	lda #$0F
	sta COLUP0
	lda #$0F;60
	sta COLUP1
	
; playfield graphics and colour	
	lda #77
	sta COLUPF
	lda #%00010000
	sta PF0

; setup initial table index value
;	ldy #0
	ldy #8
	sty tempY
	
	; setup vertical delay and player copy settings
	lda #1
	sta VDELP0
	sta VDELP1
	
	lda #%00000011 ; 3 copies 1 clock width close
	sta NUSIZ0
	sta NUSIZ1
	sta NUSIZ1 ; cycle timing
	nop
	;nop
	;nop
	;nop
	
;=================================
.spriteLoop				; 49
   ldy tempY       		; 3   ; 52
   lda Color,y   		; 4+  ; 56
   sta COLUP0     		; 3   ; 59
   sta COLUP1     		; 3   ; 62
   lda Graphics1,y 		; 4+  ; 66
   sta GRP0             ; 3   ; 69
   lda Graphics2,y 		; 4+  ; 73
   sta GRP1             ; 3   ; 00
   lda Graphics3,y 		; 4+  ; 04
   sta GRP0             ; 3   ; 07
   lda Graphics4,y 		; 4+  ; 11
   sta temp2       		; 3   ; 14
   lda Graphics5,y 		; 4+  ; 18
   tax                  ; 2   ; 20
   lda Graphics6,y 		; 4+  ; 24
   tay                  ; 2   ; 26
   lda temp2       		; 3   ; 29
   sta GRP1             ; 3   ; 32
   stx GRP0             ; 3   ; 35
   sty GRP1             ; 3   ; 38
   sty GRP0             ; 3   ; 41
   dec tempY       		; 5   ; 46
   bne .spriteLoop 		; 2++ ; 48++
;=================================	
	ldx #0
	stx VDELP0
	stx VDELP1
	stx GRP0
	stx GRP1
	stx GRP0
	stx GRP1
;=================================

; padding
	ldx #4
.padLoop2
	sta WSYNC
	dex 
	bne .padLoop2
	
	stx COLUPF
	
	ldx #84
	jmp .frame

;============================================================================== 

	.byte #%00000000 ; padding needed to get the timing right when in the sprite loop
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000
	.byte #%00000000

;============================================================================== 
Color
	.byte #%00000000
	.byte #45 
	.byte #35 
	.byte #40 
	.byte #45 
	.byte #35  
	.byte #40 
	.byte #45
Graphics1
	.byte #%00000000
	.byte #%00110000 
	.byte #%00000000 
	.byte #%11111100
	.byte #%00000000
	.byte #%11111100 
	.byte #%00000000
	.byte #%00110000	
Graphics2
	.byte #%00000000
	.byte #%10001011
	.byte #%10001001
	.byte #%10001001
	.byte #%10101001
	.byte #%10101001
	.byte #%11011001
	.byte #%01010011	
Graphics3
	.byte #%00000000
	.byte #%10101011
	.byte #%00101010
	.byte #%00110010
	.byte #%00101011
	.byte #%00101010
	.byte #%00101010
	.byte #%10100011
Graphics4
	.byte #%00000000
	.byte #%01100110
	.byte #%00010001
	.byte #%00010001
	.byte #%00100110
	.byte #%01000001
	.byte #%01000001
	.byte #%00110110	
Graphics5
	.byte #%00000000
	.byte #%00100010
	.byte #%01010101
	.byte #%01010101
	.byte #%01110101
	.byte #%01000101
	.byte #%01000101
	.byte #%00110010
Graphics6
	.byte #%00000000
	.byte #%00001100
	.byte #%00000000
	.byte #%00111111
	.byte #%00000000
	.byte #%00111111
	.byte #%00000000
	.byte #%00001100


	ORG $FFFA
	
InterruptVectors
	.word Reset          ; NMI
	.word Reset          ; RESET
	.word Reset          ; IRQ 
 
	END
	
;============================================================================== 
;								E N D  O F  F I L E
;==============================================================================


 