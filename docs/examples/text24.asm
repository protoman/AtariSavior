    processor 6502
    include "vcs.h"
    include "macro.h"
    SEG.U VARS
    ORG $80

bit0 =              %00000001
bit1 =              %00000010
bit2 =              %00000100
bit3 =              %00001000
bit4 =              %00010000
bit5 =              %00100000
bit6 =              %01000000
bit7 =              %10000000
bit0mask =          %11111110
bit1mask =          %11111101
bit2mask =          %11111011
bit3mask =          %11110111
bit4mask =          %11101111
bit5mask =          %11011111
bit6mask =          %10111111
bit7mask =          %01111111

; $80
Temp            ds 1
Clock           ds 1
Text0           ds 1
Text1           ds 1
Text2           ds 1
Text3           ds 1
Text4           ds 1
Text5           ds 1
Text6           ds 1
Text7           ds 1
Text8           ds 1
Text9           ds 1
Text10          ds 1
Text11          ds 1
Text12          ds 1
Text13          ds 1
Text14          ds 1
Text15          ds 1
Text16          ds 1
Text17          ds 1
Text18          ds 1
Text19          ds 1
Text20          ds 1
Text21          ds 1
Text22          ds 1
Text23          ds 1

   SEG CODE
   ORG $F800
Start:
   CLEAN_START
    lda #6
    sta NUSIZ0
    sta NUSIZ1
    lda #$0F
    sta COLUP0
    sta COLUP1
    lda #1
    sta VDELP0
    sta VDELP1
    ldx #23
LoadTextLoop
    lda text__example1,x
    sta Text0,x
    dex
    bpl LoadTextLoop
   
NextFrame
	VERTICAL_SYNC
    lda #44
    sta TIM64T

; My VBLANK code

    inc Clock

    lda Clock
    and #bit0
    beq ____position_frame_1
        lda #32
        ldx #0
        jsr SetHorizPos
        lda #48
        ldx #1
        jsr SetHorizPos
        jmp ____end_position
    
____position_frame_1    
        lda #40
        ldx #0
        jsr SetHorizPos
        lda #56
        ldx #1
        jsr SetHorizPos
____end_position

    sta WSYNC
    sta HMOVE




WaitVBlank
    lda INTIM
    bne WaitVBlank ; loop until timer expires
    sta WSYNC
    sta VBLANK

    lda Clock
    and #bit0
    bne ____frame0_text
    jmp ____skip_text_0
____frame0_text
    ldx Text0
    lda left_text,x
    ldx Text1
    ora right_text,x
    ldy #0
Frame0Text
    ; Text line 1 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text4            ; 4     (13)
    lda left_text,x         ; 4     (17)
    ldx Text5            ; 4     (21)
    ora right_text,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text8            ; 4     (32)
    lda left_text,x         ; 4     (36)
    ldx Text9            ; 4     (40)
    ora right_text,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text12           ; 4     (51)
    lda left_text,x         ; 4     (55)
    ldx Text13           ; 4     (59)
    ora right_text,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text16           ; 4     (4)
    lda left_text,x         ; 4     (8)
    ldx Text17           ; 4     (12)
    ora right_text,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text20           ; 4     (23*)
    lda left_text,x         ; 4     (27)
    ldx Text21           ; 4     (31)
    ora right_text,x        ; 4     (35)
    
    ldx Temp                ; 3     (38)
    sleep 4
    sty GRP1                ; 3     (41)
    stx GRP0                ; 3     (44)
    sta GRP1                ; 3     (47)
    sleep 3                 ; 3     (50)
    sta GRP0                ; 3     (53)

    ldy #0                  ; 2     (55)
    ldx Text0            ; 3     (58)
    lda left_text+1,x       ; 4     (62)
    ldx Text1            ; 3     (65)
    ora right_text+1,x      ; 4     (69)

    ; Text line 2 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text4            ; 4     (13)
    lda left_text+1,x         ; 4     (17)
    ldx Text5            ; 4     (21)
    ora right_text+1,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text8            ; 4     (32)
    lda left_text+1,x         ; 4     (36)
    ldx Text9            ; 4     (40)
    ora right_text+1,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text12           ; 4     (51)
    lda left_text+1,x         ; 4     (55)
    ldx Text13           ; 4     (59)
    ora right_text+1,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text16           ; 4     (4)
    lda left_text+1,x         ; 4     (8)
    ldx Text17           ; 4     (12)
    ora right_text+1,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text20           ; 4     (23*)
    lda left_text+1,x         ; 4     (27)
    ldx Text21           ; 4     (31)
    ora right_text+1,x        ; 4     (35)
    
    ldx Temp                ; 3     (38)
    sleep 4
    sty GRP1                ; 3     (41)
    stx GRP0                ; 3     (44)
    sta GRP1                ; 3     (47)
    sleep 3                 ; 3     (50)
    sta GRP0                ; 3     (53)

    ldy #0                  ; 2     (55)
    ldx Text0            ; 3     (58)
    lda left_text+2,x       ; 4     (62)
    ldx Text1            ; 3     (65)
    ora right_text+2,x      ; 4     (69)

    ; Text line 3 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text4            ; 4     (13)
    lda left_text+2,x         ; 4     (17)
    ldx Text5            ; 4     (21)
    ora right_text+2,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text8            ; 4     (32)
    lda left_text+2,x         ; 4     (36)
    ldx Text9            ; 4     (40)
    ora right_text+2,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text12           ; 4     (51)
    lda left_text+2,x         ; 4     (55)
    ldx Text13           ; 4     (59)
    ora right_text+2,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text16           ; 4     (4)
    lda left_text+2,x         ; 4     (8)
    ldx Text17           ; 4     (12)
    ora right_text+2,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text20           ; 4     (23*)
    lda left_text+2,x         ; 4     (27)
    ldx Text21           ; 4     (31)
    ora right_text+2,x        ; 4     (35)
    
    ldx Temp                ; 3     (38)
    sleep 4
    sty GRP1                ; 3     (41)
    stx GRP0                ; 3     (44)
    sta GRP1                ; 3     (47)
    sleep 3                 ; 3     (50)
    sta GRP0                ; 3     (53)

    ldy #0                  ; 2     (55)
    ldx Text0            ; 3     (58)
    lda left_text+3,x       ; 4     (62)
    ldx Text1            ; 3     (65)
    ora right_text+3,x      ; 4     (69)

    ; Text line 4 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text4            ; 4     (13)
    lda left_text+3,x         ; 4     (17)
    ldx Text5            ; 4     (21)
    ora right_text+3,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text8            ; 4     (32)
    lda left_text+3,x         ; 4     (36)
    ldx Text9            ; 4     (40)
    ora right_text+3,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text12           ; 4     (51)
    lda left_text+3,x         ; 4     (55)
    ldx Text13           ; 4     (59)
    ora right_text+3,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text16           ; 4     (4)
    lda left_text+3,x         ; 4     (8)
    ldx Text17           ; 4     (12)
    ora right_text+3,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text20           ; 4     (23*)
    lda left_text+3,x         ; 4     (27)
    ldx Text21           ; 4     (31)
    ora right_text+3,x        ; 4     (35)
    
    ldx Temp                ; 3     (38)
    sleep 4
    sty GRP1                ; 3     (41)
    stx GRP0                ; 3     (44)
    sta GRP1                ; 3     (47)
    sleep 3                 ; 3     (50)
    sta GRP0                ; 3     (53)

    ldy #0                  ; 2     (55)
    ldx Text0            ; 3     (58)
    lda left_text+4,x       ; 4     (62)
    ldx Text1            ; 3     (65)
    ora right_text+4,x      ; 4     (69)

    ; Text line 5 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text4            ; 4     (13)
    lda left_text+4,x         ; 4     (17)
    ldx Text5            ; 4     (21)
    ora right_text+4,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text8            ; 4     (32)
    lda left_text+4,x         ; 4     (36)
    ldx Text9            ; 4     (40)
    ora right_text+4,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text12           ; 4     (51)
    lda left_text+4,x         ; 4     (55)
    ldx Text13           ; 4     (59)
    ora right_text+4,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text16           ; 4     (4)
    lda left_text+4,x         ; 4     (8)
    ldx Text17           ; 4     (12)
    ora right_text+4,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text20           ; 4     (23*)
    lda left_text+4,x         ; 4     (27)
    ldx Text21           ; 4     (31)
    ora right_text+4,x        ; 4     (35)
    
    ldx Temp                ; 3     (38)
    sleep 4
    sty GRP1                ; 3     (41)
    stx GRP0                ; 3     (44)
    sta GRP1                ; 3     (47)
    sleep 3                 ; 3     (50)
    sta GRP0                ; 3     (53)

    sta WSYNC
    lda #0
    sta GRP0
    sta GRP1
    sta GRP0
    jmp ____end_text


____skip_text_0
StartFrame1Text
    ldx Text2
    lda left_text,x
    ldx Text3
    ora right_text,x
    ldy #0
Frame1Text
    ; Text line 1 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text6            ; 4     (13)
    lda left_text,x         ; 4     (17)
    ldx Text7            ; 4     (21)
    ora right_text,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text10           ; 4     (32)
    lda left_text,x         ; 4     (36)
    ldx Text11           ; 4     (40)
    ora right_text,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text14           ; 4     (51)
    lda left_text,x         ; 4     (55)
    ldx Text15           ; 4     (59)
    ora right_text,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text18           ; 4     (4)
    lda left_text,x         ; 4     (8)
    ldx Text19           ; 4     (12)
    ora right_text,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text22           ; 3     (22)
    lda left_text,x         ; 4     (26*)
    ldx Text23           ; 3     (29)
    ora right_text,x        ; 4     (33)
    
    ldx Temp                ; 3     (36)
    sleep 6                 ; 4     (40)
    sty GRP1                ; 3     (43)
    stx GRP0                ; 3     (46)
    sta GRP1                ; 3     (49)
    sleep 3                 ; 3     (52)
    sta GRP0                ; 3     (55)

    ldy #0                  ; 2     (57)
    ldx Text2            ; 4     (61)
    lda left_text+1,x       ; 4     (65)
    ldx Text3            ; 4     (69)
    ora right_text+1,x      ; 4     (73)

    ; Text line 2 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text6            ; 4     (13)
    lda left_text+1,x         ; 4     (17)
    ldx Text7            ; 4     (21)
    ora right_text+1,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text10           ; 4     (32)
    lda left_text+1,x         ; 4     (36)
    ldx Text11           ; 4     (40)
    ora right_text+1,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text14           ; 4     (51)
    lda left_text+1,x         ; 4     (55)
    ldx Text15           ; 4     (59)
    ora right_text+1,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text18           ; 4     (4)
    lda left_text+1,x         ; 4     (8)
    ldx Text19           ; 4     (12)
    ora right_text+1,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text22           ; 3     (22)
    lda left_text+1,x         ; 4     (26*)
    ldx Text23           ; 3     (29)
    ora right_text+1,x        ; 4     (33)
    
    ldx Temp                ; 3     (36)
    sleep 6                 ; 4     (40)
    sty GRP1                ; 3     (43)
    stx GRP0                ; 3     (46)
    sta GRP1                ; 3     (49)
    sleep 3                 ; 3     (52)
    sta GRP0                ; 3     (55)

    ldy #0                  ; 2     (57)
    ldx Text2            ; 4     (61)
    lda left_text+2,x       ; 4     (65)
    ldx Text3            ; 4     (69)
    ora right_text+2,x      ; 4     (73)

    ; Text line 3 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text6            ; 4     (13)
    lda left_text+2,x         ; 4     (17)
    ldx Text7            ; 4     (21)
    ora right_text+2,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text10           ; 4     (32)
    lda left_text+2,x         ; 4     (36)
    ldx Text11           ; 4     (40)
    ora right_text+2,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text14           ; 4     (51)
    lda left_text+2,x         ; 4     (55)
    ldx Text15           ; 4     (59)
    ora right_text+2,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text18           ; 4     (4)
    lda left_text+2,x         ; 4     (8)
    ldx Text19           ; 4     (12)
    ora right_text+2,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text22           ; 3     (22)
    lda left_text+2,x         ; 4     (26*)
    ldx Text23           ; 3     (29)
    ora right_text+2,x        ; 4     (33)
    
    ldx Temp                ; 3     (36)
    sleep 6                 ; 4     (40)
    sty GRP1                ; 3     (43)
    stx GRP0                ; 3     (46)
    sta GRP1                ; 3     (49)
    sleep 3                 ; 3     (52)
    sta GRP0                ; 3     (55)

    ldy #0                  ; 2     (57)
    ldx Text2            ; 4     (61)
    lda left_text+3,x       ; 4     (65)
    ldx Text3            ; 4     (69)
    ora right_text+3,x      ; 4     (73)

    ; Text line 4 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text6            ; 4     (13)
    lda left_text+3,x         ; 4     (17)
    ldx Text7            ; 4     (21)
    ora right_text+3,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text10           ; 4     (32)
    lda left_text+3,x         ; 4     (36)
    ldx Text11           ; 4     (40)
    ora right_text+3,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text14           ; 4     (51)
    lda left_text+3,x         ; 4     (55)
    ldx Text15           ; 4     (59)
    ora right_text+3,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text18           ; 4     (4)
    lda left_text+3,x         ; 4     (8)
    ldx Text19           ; 4     (12)
    ora right_text+3,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text22           ; 3     (22)
    lda left_text+3,x         ; 4     (26*)
    ldx Text23           ; 3     (29)
    ora right_text+3,x        ; 4     (33)
    
    ldx Temp                ; 3     (36)
    sleep 6                 ; 4     (40)
    sty GRP1                ; 3     (43)
    stx GRP0                ; 3     (46)
    sta GRP1                ; 3     (49)
    sleep 3                 ; 3     (52)
    sta GRP0                ; 3     (55)

    ldy #0                  ; 2     (57)
    ldx Text2            ; 4     (61)
    lda left_text+4,x       ; 4     (65)
    ldx Text3            ; 4     (69)
    ora right_text+4,x      ; 4     (73)

    ; Text line 5 / 5
 
    ;line 1
    sta WSYNC               ; 3     (0)
    sty COLUP0              ; 3     (3)
    sty COLUP1              ; 3     (6)
    sta GRP0                ; 3     (9)

    ldx Text6            ; 4     (13)
    lda left_text+4,x         ; 4     (17)
    ldx Text7            ; 4     (21)
    ora right_text+4,x        ; 4     (25*)
    sleep 2
    sta GRP1                ; 3     (28)
    
    ldx Text10           ; 4     (32)
    lda left_text+4,x         ; 4     (36)
    ldx Text11           ; 4     (40)
    ora right_text+4,x        ; 4     (44)
    sleep 2
    sta GRP0                ; 3     (47)
    
    ldx Text14           ; 4     (51)
    lda left_text+4,x         ; 4     (55)
    ldx Text15           ; 4     (59)
    ora right_text+4,x        ; 4     (63)
    
    ldy #$0F          ; 2     (65)
    sty COLUP0              ; 3     (68)
    sty COLUP1              ; 3     (71)
    tay                     ; 2     (73)
    
    ;line 2
    sta WSYNC               ; 3     (0)

    ldx Text18           ; 4     (4)
    lda left_text+4,x         ; 4     (8)
    ldx Text19           ; 4     (12)
    ora right_text+4,x        ; 4     (16)
    sta Temp                ; 3     (19)

    ldx Text22           ; 3     (22)
    lda left_text+4,x         ; 4     (26*)
    ldx Text23           ; 3     (29)
    ora right_text+4,x        ; 4     (33)
    
    ldx Temp                ; 3     (36)
    sleep 6                 ; 4     (40)
    sty GRP1                ; 3     (43)
    stx GRP0                ; 3     (46)
    sta GRP1                ; 3     (49)
    sleep 3                 ; 3     (52)
    sta GRP0                ; 3     (55)

____end_text
    
FinishVS
    sleep 10
    lda #0
    sta GRP1
    sta GRP0
    sta GRP1


    ldx #(181)
VSLoop
    sta WSYNC
    dex
    bne VSLoop

    
SetupOS
    lda #36
    sta TIM64T

; My Overscan code
            
WaitOverscan
    lda INTIM
    bne WaitOverscan
    
    jmp NextFrame



SetHorizPos
    sta WSYNC   ; start a new line
    bit 0       ; waste 3 cycles
    sec     ; set carry flag
DivideLoop
    sbc #15     ; subtract 15
    bcs DivideLoop  ; branch until negative
    eor #7      ; calculate fine offset
    asl
    asl
    asl
    asl
    sta RESP0,x ; fix coarse position
    sta HMP0,x  ; set fine offset
    rts     ; return to caller

text__example1

 .byte __T, __H, __I, __S, _sp, __I, __S, _sp, __S, __O, __M, __E, _sp, __S, __A, __M, __P, __L, __E, _sp, __T, __E, __X, __T

    align 256

text_data

left_text

__A = * - text_data ; baseline (0)
    .byte %00100000 
    .byte %01010000
    .byte %01110000
    .byte %01010000
    .byte %01010000
    
__B = * - text_data
    .byte %01100000
    .byte %01010000
    .byte %01100000
    .byte %01010000
    .byte %01100000    
    
__C = * - text_data
    .byte %00110000
    .byte %01000000
    .byte %01000000
    .byte %01000000
    .byte %00110000    
    
__D = * - text_data
    .byte %01100000
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %01100000
    
__E = * - text_data
    .byte %01110000
    .byte %01000000
    .byte %01100000
    .byte %01000000
    .byte %01110000
    
__F = * - text_data
    .byte %01110000
    .byte %01000000
    .byte %01100000
    .byte %01000000
    .byte %01000000

__G = * - text_data
    .byte %00110000
    .byte %01000000
    .byte %01010000
    .byte %01010000
    .byte %00100000

__H = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %01110000
    .byte %01010000
    .byte %01010000
    
__I = * - text_data
    .byte %01110000
    .byte %00100000
    .byte %00100000
    .byte %00100000
    .byte %01110000
    
__J = * - text_data
    .byte %00010000
    .byte %00010000
    .byte %00010000
    .byte %01010000
    .byte %00100000

__K = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %01100000
    .byte %01010000
    .byte %01010000

__L = * - text_data
    .byte %01000000
    .byte %01000000
    .byte %01000000
    .byte %01000000
    .byte %01110000
    
__M = * - text_data
    .byte %01010000
    .byte %01110000
    .byte %01110000
    .byte %01010000
    .byte %01010000
    
__N = * - text_data
    .byte %01100000
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %01010000

__O = * - text_data
    .byte %01110000
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %01110000

__P = * - text_data
    .byte %01100000
    .byte %01010000
    .byte %01100000
    .byte %01000000
    .byte %01000000
    
__Q = * - text_data
    .byte %00100000
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %00110000
    
__R = * - text_data
    .byte %01100000
    .byte %01010000
    .byte %01100000
    .byte %01010000
    .byte %01010000
    
__S = * - text_data
    .byte %00110000
    .byte %01000000
    .byte %00100000
    .byte %00010000
    .byte %01100000
    
__T = * - text_data
    .byte %01110000
    .byte %00100000
    .byte %00100000
    .byte %00100000
    .byte %00100000
    
__U = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %01110000
    
__V = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %00100000

__W = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %01110000
    .byte %01110000
    .byte %01010000

__X = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %00100000
    .byte %01010000
    .byte %01010000
    
__Y = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %00100000
    .byte %00100000
    .byte %00100000
    
__Z = * - text_data
    .byte %01110000
    .byte %00010000
    .byte %00100000
    .byte %01000000
    .byte %01110000

_sp = * - text_data
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00000000

_pd = * - text_data
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00100000

_qu = * - text_data
    .byte %01100000
    .byte %00010000
    .byte %00100000
    .byte %00000000
    .byte %00100000
 
_ex = * - text_data
    .byte %00100000
    .byte %00100000
    .byte %00100000
    .byte %00000000
    .byte %00100000

_cm = * - text_data
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00100000
    .byte %01000000

_hy = * - text_data
    .byte %00000000
    .byte %00000000
    .byte %01110000
    .byte %00000000
    .byte %00000000

_pl = * - text_data
    .byte %00100000
    .byte %00100000
    .byte %01110000
    .byte %00100000
    .byte %00100000

_ap = * - text_data
    .byte %00100000
    .byte %01000000
    .byte %00000000
    .byte %00000000
    .byte %00000000

_lp = * - text_data
    .byte %00100000
    .byte %01000000
    .byte %01000000
    .byte %01000000
    .byte %00100000

_rp = * - text_data
    .byte %01000000
    .byte %00100000
    .byte %00100000
    .byte %00100000
    .byte %01000000

;_lt = * - text_data
;    .byte %00010000
;    .byte %00100000
;    .byte %01000000
;    .byte %00100000
;    .byte %00010000

;_gt = * - text_data
;    .byte %01000000
;    .byte %00100000
;    .byte %00010000
;    .byte %00100000
;    .byte %01000000

_co = * - text_data
    .byte %00000000
    .byte %01000000
    .byte %00000000
    .byte %01000000
    .byte %00000000

_sl = * - text_data
    .byte %00010000
    .byte %00010000
    .byte %00100000
    .byte %01000000
    .byte %01000000

_eq = * - text_data
    .byte %00000000
    .byte %01110000
    .byte %00000000
    .byte %01110000
    .byte %00000000

_qt = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %00000000
    .byte %00000000
    .byte %00000000

_tr = * - text_data
    .byte %00000000
    .byte %00100000
    .byte %00110000
    .byte %00100000
    .byte %00000000

__0 = * - text_data
    .byte %00100000
    .byte %01010000
    .byte %01010000
    .byte %01010000
    .byte %00100000
    
__1 = * - text_data
    .byte %00100000
    .byte %01100000
    .byte %00100000
    .byte %00100000
    .byte %01110000
    
__2 = * - text_data
    .byte %01100000
    .byte %00010000
    .byte %00100000
    .byte %01000000
    .byte %01110000
    
__3 = * - text_data
    .byte %01100000
    .byte %00010000
    .byte %00100000
    .byte %00010000
    .byte %01100000
    
__4 = * - text_data
    .byte %01010000
    .byte %01010000
    .byte %01110000
    .byte %00010000
    .byte %00010000
    
__5 = * - text_data
    .byte %01110000
    .byte %01000000
    .byte %01100000
    .byte %00010000
    .byte %01100000
    
__6 = * - text_data
    .byte %00110000
    .byte %01000000
    .byte %01100000
    .byte %01010000
    .byte %00100000

__7 = * - text_data
    .byte %01110000
    .byte %00010000
    .byte %00100000
    .byte %01000000
    .byte %01000000

__8 = * - text_data
    .byte %00100000
    .byte %01010000
    .byte %00100000
    .byte %01010000
    .byte %00100000
    
__9 = * - text_data
    .byte %00100000
    .byte %01010000
    .byte %00110000
    .byte %00010000
    .byte %01100000
    


text_data_height = * - text_data

    align 256

right_text

; A
    .byte %00000010 
    .byte %00000101
    .byte %00000111
    .byte %00000101
    .byte %00000101

    
; B
    .byte %00000110
    .byte %00000101
    .byte %00000110
    .byte %00000101
    .byte %00000110    
    
; C
    .byte %00000011
    .byte %00000100
    .byte %00000100
    .byte %00000100
    .byte %00000011    
    
; D
    .byte %00000110
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000110
    
; E
    .byte %00000111
    .byte %00000100
    .byte %00000110
    .byte %00000100
    .byte %00000111
    
; F
    .byte %00000111
    .byte %00000100
    .byte %00000110
    .byte %00000100
    .byte %00000100

; G
    .byte %00000011
    .byte %00000100
    .byte %00000101
    .byte %00000101
    .byte %00000010

; H
    .byte %00000101
    .byte %00000101
    .byte %00000111
    .byte %00000101
    .byte %00000101
    
; I
    .byte %00000111
    .byte %00000010
    .byte %00000010
    .byte %00000010
    .byte %00000111
    
; J
    .byte %00000001
    .byte %00000001
    .byte %00000001
    .byte %00000101
    .byte %00000010

; K
    .byte %00000101
    .byte %00000101
    .byte %00000110
    .byte %00000101
    .byte %00000101

; L
    .byte %00000100
    .byte %00000100
    .byte %00000100
    .byte %00000100
    .byte %00000111
    
; M
    .byte %00000101
    .byte %00000111
    .byte %00000111
    .byte %00000101
    .byte %00000101
    
; N
    .byte %00000110
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000101

; O
    .byte %00000111
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000111

; P
    .byte %00000110
    .byte %00000101
    .byte %00000110
    .byte %00000100
    .byte %00000100
    
; Q
    .byte %00000010
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000011
    
; R
    .byte %00000110
    .byte %00000101
    .byte %00000110
    .byte %00000101
    .byte %00000101
    
; S
    .byte %00000011
    .byte %00000100
    .byte %00000010
    .byte %00000001
    .byte %00000110
    
; T
    .byte %00000111
    .byte %00000010
    .byte %00000010
    .byte %00000010
    .byte %00000010
    
; U
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000111
    
; V
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000010

; W
    .byte %00000101
    .byte %00000101
    .byte %00000111
    .byte %00000111
    .byte %00000101

; X
    .byte %00000101
    .byte %00000101
    .byte %00000010
    .byte %00000101
    .byte %00000101
    
; Y
    .byte %00000101
    .byte %00000101
    .byte %00000010
    .byte %00000010
    .byte %00000010
    
; Z
    .byte %00000111
    .byte %00000001
    .byte %00000010
    .byte %00000100
    .byte %00000111

; space
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00000000

; period
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00000010

; question mark
    .byte %00000110
    .byte %00000001
    .byte %00000010
    .byte %00000000
    .byte %00000010

; exclamation point
    .byte %00000010
    .byte %00000010
    .byte %00000010
    .byte %00000000
    .byte %00000010

; comma
    .byte %00000000
    .byte %00000000
    .byte %00000000
    .byte %00000010
    .byte %00000100

; hyphen
    .byte %00000000
    .byte %00000000
    .byte %00000111
    .byte %00000000
    .byte %00000000

; plus
    .byte %00000010
    .byte %00000010
    .byte %00000111
    .byte %00000010
    .byte %00000010

; apostrophe
    .byte %00000010
    .byte %00000100
    .byte %00000000
    .byte %00000000
    .byte %00000000

; left parenthesis 
    .byte %00000010
    .byte %00000100
    .byte %00000100
    .byte %00000100
    .byte %00000010

; right parenthesis 
    .byte %00000100
    .byte %00000010
    .byte %00000010
    .byte %00000010
    .byte %00000100

; less than
;    .byte %00000001
;    .byte %00000010
;    .byte %00000100
;    .byte %00000010
;    .byte %00000001

; greater than
;    .byte %00000100
;    .byte %00000010
;    .byte %00000001
;    .byte %00000010
;    .byte %00000100

; colon
    .byte %00000000
    .byte %00000100
    .byte %00000000
    .byte %00000100
    .byte %00000000

; slash
    .byte %00000001
    .byte %00000001
    .byte %00000010
    .byte %00000100
    .byte %00000100

; equal
    .byte %00000000
    .byte %00000111
    .byte %00000000
    .byte %00000111
    .byte %00000000

; quote
    .byte %00000101
    .byte %00000101
    .byte %00000000
    .byte %00000000
    .byte %00000000

; triangle
    .byte %00000000
    .byte %00000010
    .byte %00000011
    .byte %00000010
    .byte %00000000

; 0
    .byte %00000010
    .byte %00000101
    .byte %00000101
    .byte %00000101
    .byte %00000010
    
; 1
    .byte %00000010
    .byte %00000110
    .byte %00000010
    .byte %00000010
    .byte %00000111
    
; 2
    .byte %00000110
    .byte %00000001
    .byte %00000010
    .byte %00000100
    .byte %00000111
    
; 3
    .byte %00000110
    .byte %00000001
    .byte %00000010
    .byte %00000001
    .byte %00000110
    
; 4
    .byte %00000101
    .byte %00000101
    .byte %00000111
    .byte %00000001
    .byte %00000001
    
; 5
    .byte %00000111
    .byte %00000100
    .byte %00000110
    .byte %00000001
    .byte %00000110
    
; 6
    .byte %00000011
    .byte %00000100
    .byte %00000110
    .byte %00000101
    .byte %00000010

; 7
    .byte %00000111
    .byte %00000001
    .byte %00000010
    .byte %00000100
    .byte %00000100

; 8
    .byte %00000010
    .byte %00000101
    .byte %00000010
    .byte %00000101
    .byte %00000010
    
; 9
    .byte %00000010
    .byte %00000101
    .byte %00000011
    .byte %00000001
    .byte %00000110



   ECHO ([$FFFC-.]d), "bytes free"

    org $fffc
    .word Start
    .word Start

