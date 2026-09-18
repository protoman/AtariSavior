	PROCESSOR 6502
	include "vcs.h"
	include "macro.h"
	
ARENA_HEIGHT = 117

	SEG.U VARS
	ORG $80
	
ImageHeight:	ds 1	
Level:			 ds 1	
Rand:			 ds 1
Rand16:          ds 1  
OverscanValue:   ds 1
;DigitLivesTens: 	 ds 2
DigitLivesOnes:	ds 2
DigitOnes:       ds 2    
DigitTens:       ds 2   
DigitHundreds:   ds 2    
DigitThousands:  ds 2 
ScoreCounter:    ds 1
ScoreColor: 	 ds 1
Score:			 ds 2
Frame:			 ds 1
PlayerX:	  	 ds 5
PlayerY:		 ds 5
Player0Ptr:         ds 2    ; used for drawing player0
Player1Ptr:         ds 2    ; used for drawing player1
Color0Ptr:			ds 2
Color1Ptr:			ds 2
Missile1Ptr:         ds 2    ; used for drawing player0
Player0Draw:        ds 1    ; used for drawing player0
Player1Draw:        ds 1    ; used for drawing player1
Temp: ds 1
SavedX: ds 1
SavedY: ds 1
ShootingStatus: ds 2
MissileX: ds 2
MissileY: ds 2
SFXTimer: ds 1
SFX2Timer: ds 1
GameStatus: ds 1
Lives: ds 1
ScoreorLivesDisplay: ds 1
Temp2: ds 1

; burger - player0
; French fry - missile1
; onion ring - player1

	SEG CODE
	ORG $F000

 ; get a random number, return in rand.
Random:
        lda Rand
        lsr
 ifconst Rand16
        rol Rand16
 endif
        bcc noeor
        eor #$B4 
noeor 
        sta Rand
 ifconst Rand16
        eor Rand16
 endif
        rts 	
        
Reset:
		CLEAN_START

		lda #11
		sta Rand
		sta Rand16
		
		lda #22
		sta ScoreColor
	
Reset2:
		lda #10
		sta OverscanValue	

		lda #$A2
		sta Lives

		lda #1
		sta Level

		lda #0
		sta AUDV0
		sta AUDV1
		sta GameStatus	
		sta ShootingStatus
		sta PlayerY
		sta PlayerY+1
		sta ScoreorLivesDisplay

		lda #10
		sta OverscanValue
		
		jmp Main3

WaitForGameStarting:
		lda GameStatus
		cmp #2
		beq WaitforDePressFire

		lda INPT4           ; read the player's fire button value	
		bmi Main 

		lda #2
		sta GameStatus
		
		jmp Main
		
WaitforDePressFire:		
		lda INPT4           ; read the player's fire button value	
		bpl Main

Start_the_game:
		lda #10
		sta OverscanValue

		jsr PrepScoreForDisplay
		jsr VerticalSync
		jsr VerticalBlank
		jsr Overscan		

		lda #0
		sta Score
		sta Score+1
		
		lda #1
		sta GameStatus

		lda #1
		sta ScoreorLivesDisplay

Main:
		lda ScoreorLivesDisplay
		cmp #1
		beq SetUpSprites

		jmp Main2

SetUpSprites
		lda Lives
		cmp #$9F
		beq GameOver

		lda #77
		sta PlayerX
		sta PlayerY
		
		lda #9
		sta OverscanValue
		
		jsr PrepScoreForDisplay
		jsr VerticalSync
		jsr VerticalBlank
		jsr Overscan
		
		jsr GetPlayer1Y
		sty PlayerX+1   ; save X	
		
		lda #0
		sta ScoreorLivesDisplay

		jmp Main
		
Main2:
		lda SWCHB                        ; read the console switches
		lsr                              ; shift game reset to carry
		bcs .skipReset                   ; skip game reset	
	
		lda #10
		sta OverscanValue

Main3:
	jsr PrepScoreForDisplay
	jsr VerticalSync
	jsr VerticalBlank
	jsr Overscan	
	
F262
		lda SWCHB                        ; read the console switches
		lsr                              ; shift game reset to carry
		bcc Reset2___                  ; skip game reset	
	
		jmp Main
	
Reset2___ 
		jmp Reset2

GameOver
		lda #10
		sta OverscanValue	

		lda #$A2
		sta Lives

		jsr PrepScoreForDisplay
		jsr VerticalSync
		jsr VerticalBlank
		jsr Overscan

		jmp Reset2
	
WaitForGameStarting____
		jmp WaitForGameStarting
	
.skipReset	
		lda #10
		sta OverscanValue	
		
	jsr PrepScoreForDisplay
	jsr VerticalSync
	jsr VerticalBlank
	jsr Overscan			
		
	lda GameStatus
	cmp #1
	bne WaitForGameStarting____
	
	jmp Main
	
Fraem_equals_0:
		lda #0
		sta Frame
		jmp Main

VerticalSync:
        lda #66
        ldx #47         ; LoaD X with 48
        sta WSYNC       ; Wait for SYNC (halts CPU until end of scanline)
        sta VSYNC       ; Accumulator D1=1, turns on Vertical Sync signal
        sta VBLANK      ; DGS - turn off video, dump paddles to ground
        stx TIM64T      ; set timer to go off in 41 scanlines (49 * 64) / 76
        sta CTRLPF      ; D1=1, playfield now in SCORE mode
        lda Frame
        and #$3f
        bne VSskip
VSskip: inc Frame       ; increment Frame count

        sta WSYNC   ; Wait for Sync - halts CPU until end of 1st scanline of VSYNC

        sta WSYNC   ; wait until end of 2nd scanline of VSYNC
        lda #0      ; LoaD Accumulator with 0 so D1=0
        sta PF0     ; blank the playfield
        sta PF1     ; blank the playfield
        sta PF2     ; blank the playfield
        sta GRP0    ; blanks player0 if VDELP0 was off
        sta GRP1    ; blanks player0 if VDELP0 was on, player1 if VDELP1 was off 
        sta GRP0    ; blanks                           player1 if VDELP1 was on		
        sta VDELP0  ; turn off Vertical Delay
        sta VDELP1  ; turn off Vertical Delay
       ; sta CXCLR   ; clear collision detection latches
        sta WSYNC   ; wait until end of 3rd scanline of VSYNC
        sta VSYNC   ; Accumulator D1=0, turns off Vertical Sync signal
Sleep12:            ;       jsr here to sleep for 12 cycles        
        rts         ; ReTurn from Subroutine
		
VerticalBlank
		lda GameStatus
		cmp #1
		bne EndVerticalBlank

		jsr Joystick

EndVerticalBlank:
		jsr PositionPlayers	
		jsr In_game_draw
		jsr Random			
		rts
	
In_game_draw:
		sta WSYNC       ; Wait for SYNC (halts CPU until end of scanline)
;---------------------------------------                
        lda INTIM       ; 4  4 - check the timer
        bne In_game_draw     ; 2  6 - (3 7) Branch if its Not Equal to 0
    ; turn on the display
        sta VBLANK      ; 3  9 - Accumulator D1=0, turns off Vertical Blank signal (image output on)        
		lda #$11          ; 2 11
		sta CTRLPF      ; 3 14 - turn on playfield mirroring
		
		lda #$76
		sta COLUPF
		
		lda #$2A
		sta COLUP1		

		ldx #0

		ldy #ARENA_HEIGHT
		sta WSYNC   

			lda #$0E
			sta COLUPF
			lda #$9a
			sta COLUBK
			;sta WSYNC
			
			lda #0
			sta PF0
			sta PF1
			sta PF2			
			
Level_1_:			
			jsr draw_sprites	

			inx		
            cpx #5
            bne Level_1_	
	
			;sta WSYNC  

				;sta WSYNC
				lda #%11100000
				sta PF2
				
				lda #0	
				sta PF1
				
Level_1_a:
				jsr draw_sprites
				inx		
                cpx #10
                bne Level_1_a
				
				;sta WSYNC
				;sta WSYNC
				lda #%11111111
				sta PF0
				lda #%11110000
				sta PF2
				
Level_1_b:				
				jsr draw_sprites
				inx		
                cpx #16
                bne Level_1_b	

				;sta WSYNC
				lda #%10000000
				sta PF1
				lda #%11111000
				sta PF2
				
Level_1_c:				
				jsr draw_sprites
				inx		
                cpx #26
                bne Level_1_c				
	
				;sta WSYNC			
				;sta WSYNC
				;sleep 9
				;jsr Sleep12
				
				lda #$78
				sta COLUPF				

				;sta WSYNC
				lda #255
				sta PF0	
				lda #%11000000
				sta PF1
				
Level_1_d:
				lda #%11111100
				sta PF2
				jsr draw_sprites
				inx		
                cpx #36
                bne Level_1_d		

				;sta WSYNC
				lda #255
				sta PF0				
				lda #%11100000
				sta PF1
				lda #%11111110
				sta PF2
				
Level_1_e:				
				jsr draw_sprites
				inx		
                cpx #46
                bne Level_1_e	

				lda #255
				sta PF0	

			;	sta WSYNC
			
				lda #%11110000
				sta PF1
				lda #%11111111
				sta PF2
			
Level_1_f:
				jsr draw_sprites
				
				inx		
                cpx #56
                bne Level_1_f	

			;	sta WSYNC	
	
				lda #$B8
				sta COLUBK	
				
				sta WSYNC
				lda #0
				sta PF0
				sta PF1
Level_1_g:		
				jsr draw_sprites
				inx		
                cpx #70
                bne Level_1_g

			;	sta WSYNC			
				lda #%00000001
				sta PF1
Level_1_h:				
				jsr draw_sprites
				inx		
                cpx #82
                bne Level_1_h
		
				;sta WSYNC
	
				lda #0
				sta PF2
				sta PF1	
				
Level_1_i:				
				jsr draw_sprites
				inx		
                cpx #97
                bne Level_1_i	
			
				jmp Score_Code
			
Score_Code:		
				sta WSYNC
				lda #0
				sta COLUBK
				inx		
                cpx #100
                bne Score_Code

        sta WSYNC
        ldx #1              ; 2  2
        stx VDELP0          ; 3  5  turn on vertical delay
        stx VDELP1          ; 3  8  turn on vertical delay
		
		ldx #0              ; 2 10
        stx GRP0            ; 3 13  make sure player0 is off
        stx GRP1            ; 3 16  make sure player1 is off
        stx ENABL           ; 3 19  make sure ball is off
        stx ENAM0           ; 3 22  make sure Missile1 is off
        stx ENAM1           ; 3 25  make sure Missile0 is off     
        stx REFP0           ; 3 28  make sure reflect is off
        stx REFP1           ; 3 31  make sure reflect is off

        ldx #3              ; 2 33  3 copies close
        stx NUSIZ0          ; 3 36 		
        stx RESP0           ; 3 39  player0 at X=54
        ldx #1              ; 2 41  2 copies close
        stx NUSIZ1          ; 3 44  player1 - 2 copies, close
        stx RESP1           ; 3 47  player1 at X=78
        ldx #$E0            ; 2 49  +2 for fine positioning
        stx HMP0            ; 3 52  fine positioning for player0, X = 56
        stx HMP1            ; 3 55  fine positioning for player1, X = 80
        lda ScoreColor      ; 3 58
        sta COLUP0          ; 3 61
        sta COLUP1          ; 3 64		
        sta WSYNC
        sta HMOVE           ; sets player0 X=56, player1 X=80

        ldy #7
        sty ImageHeight
		
ScoreLoop       
        sta WSYNC
                                    ; NOTE GRP0d and GRP1d  = value in delay
                                    ;      GRP0 and GRP1    = value to show
        lda (DigitLivesOnes),y      ; 5
        sta GRP0                    ; 3  8  lives in GRP0d
        sta GRP1                    ; 3 11  lives in GRP1d, lives in GRP0.        
        lda (DigitThousands),y      ; 5 16  
        sta GRP0                    ; 3 19  D___ in GRP0d, lives in GRP1 (not shown)
        lda (DigitHundreds),y       ; 5 24
        tax                         ; 2 26  _D__ in X 
        lda (DigitTens),y           ; 5 31
        sta Temp2                   ; 3 34
        lda (DigitOnes),y           ; 5 39  ___D in A
        ldy Temp2                   ; 3 42  __D_ in Y
        stx GRP1                    ; 3 47 _D__ in GRP1d, D___ in GRP0
        sty GRP0                    ; 3 50 __D_ in GRP0d, _D__ in GRP1
        sta GRP1                    ; 3 53 ___D in GRP1d, __D_ in GRP0
        sta GRP0                    ; 3 56 ___D in GRP1, GRP0d not used
        dec ImageHeight             ; 5 61
        ldy ImageHeight             ; 3 64
        bpl ScoreLoop               ; 2/3 66/67
        
        sta WSYNC           ; extra blank line to keep it 262 scanlines
        lda #0
		sta NUSIZ0
		sta NUSIZ1
		sta COLUBK
		
        rts

PositionPlayers:
        ldx #1              ; position players 0 and 1
POloop:
        lda PlayerX,x       ; get the Player's X position
        jsr PosPlayer       ; set coarse X position and fine-tune amount 
        dex                 ; DEcrement X
        bpl POloop          ; Branch PLus so we position all Players
        sta WSYNC           ; wait for end of scanline
        sta HMOVE           ; Tell TIA to use fine-tune values to set final X positions
		
        lda PlayerY       ;
        clc
        sta Temp            ; save for position calculations		
		
    ; Player0Draw = ARENA_HEIGHT + Burger_HEIGHT - Y_position
        lda #(ARENA_HEIGHT + Burger_HEIGHT)
        sec
        sbc PlayerY
        sta Player0Draw
        
    ; Player0Ptr = BurgerGfx + Burger_HEIGHT - 1 - Y position
        lda #<(BurgerGfx + Burger_HEIGHT - 1)
        sec
        sbc Temp
        sta Player0Ptr
        lda #>(BurgerGfx + Burger_HEIGHT - 1)
        sbc #0
        sta Player0Ptr+1	
		sta Color0Ptr+1                     ; DGS33
		
        lda #<(BurgerColors + Burger_HEIGHT - 1)   ; DGS33
        sec                                 ; DGS33
        sbc PlayerY                         ; DGS33
        sta Color0Ptr                       ; DGS33
		
    ; Player1Draw = ARENA_HEIGHT + BOX_HEIGHT - Y_position
        lda #(ARENA_HEIGHT + Onionring_HEIGHT)
        sec
        sbc PlayerY+1
        sta Player1Draw     		
		
        lda PlayerY+1      ;
        clc
        sta Temp            ; save for position calculations		
		
    ; Player0Ptr = BurgerGfx + Burger_HEIGHT - 1 - Y position
        lda #<(OnionringGfx + Onionring_HEIGHT - 1)
        sec
        sbc Temp
        sta Player1Ptr
        lda #>(OnionringGfx + Onionring_HEIGHT - 1)
        sbc #0
        sta Player1Ptr+1			
	
		rts

draw_sprites
		;sta WSYNC
        lda #Burger_HEIGHT-1 ; 2 13 - height of the Burger graphics, 
        dcp Player0Draw     ; 5 18 - Decrement Player0Draw and compare with height
        bcs DoDrawGrp0      ; 2 20 - (3 21) if Carry is Set then player0 is on current scanline
        lda #0              ; 2 22 - otherwise use 0 to turn off player0
        .byte $2C           ; 4 26 - $2C = BIT with absolute addressing, trick that
                            ;        causes the lda (Player0Ptr),y to be skipped
DoDrawGrp0:                 ;   21 - from bcs DoDrawGRP0
		lda (Player0Ptr),y  ; 5 26 - load the shape for player0
		sta WSYNC	
		sta GRP0
	
        lda (Color0Ptr),y     
        sta COLUP0  	

		cpy MissileY+1
        bne DontDrawMissile1

		lda ShootingStatus
	    cmp #1
        bne DontDrawMissile1
	
		lda #2
		sta ENAM1

		jmp DoneShootM1
		
DontDrawMissile1
		lda #0
		sta ENAM1
		
DoneShootM1:
        lda #Onionring_HEIGHT-1 ; 2 44 - height of the Burgeroid graphics, subtract 1 due to starting with 0
        dcp Player1Draw     ; 5 49 - Decrement Player1Draw and compare with height
        bcs DoDrawGrp1      ; 2 51 - (3 52) if Carry is Set, then player1 is on current scanline
        lda #0              ; 2 53 - otherwise use 0 to turn off player1
        .byte $2C           ; 4 57 - $2C = BIT with absolute addressing, trick that
                            ;        causes the lda (Player1Ptr),y to be skipped
DoDrawGrp1:                 ;   52 - from bcs DoDrawGrp1
        lda (Player1Ptr),y  ; 5 57 - load the shape for player1
		sta WSYNC	
        sta GRP1            ; 3  3 - @0-22, update player1 graphics
		
EndThsi	
        dey                

		rts	

PrepScoreForDisplay:
        lda #>DigitGfx
;		sta DigitLivesTens+1		
		sta DigitLivesOnes+1
        sta DigitThousands+1
        sta DigitHundreds+1
        sta DigitTens+1
        sta DigitOnes+1
        
        ; lda Lives
        ; and #$F0
        ; lsr
        ; clc
        ; adc #<DigitGfx
        ; sta DigitLivesTens
        
        lda Lives
        and #$0F
        asl
        asl
        asl
        clc
        adc #<DigitGfx
        sta DigitLivesOnes		
		
        lda Score
        and #$F0
        lsr
        clc
        adc #<DigitGfx
        sta DigitThousands
        
        lda Score
        and #$0F
        asl
        asl
        asl
        clc
        adc #<DigitGfx
        sta DigitHundreds
        
        lda Score+1
        and #$F0
        lsr
        clc
        adc #<DigitGfx
        sta DigitTens
        
        lda Score+1
        and #$0F
        asl
        asl
        asl
        clc
        adc #<DigitGfx
        sta DigitOnes
        rts
	
GetPlayer1Y:
		jsr Random
		lsr
		sta PlayerY+1
		
		lda PlayerY+1
		cmp #111
		bcs FFFF			
		
		cmp #35
		bcs EndGetPlayer1Y
		
		lda PlayerY+1
		adc #35
		sta PlayerY+1

EndGetPlayer1Y
		ldy #150
		sty PlayerX+1
		
		rts
	
FFFF
		lda PlayerY+1
		adc #220
		sta PlayerY+1	

		jmp EndGetPlayer1Y
	
LoseaLife:
		sta CXCLR

		lda SFX2Timer
		cmp #31
		beq ActuallyLoseaLife
		
		lda #200
		sta PlayerY
		sta PlayerY+1

		inc SFX2Timer
		
		lda #14
		sta AUDC0
		lda #4
		sta AUDV0
		lda SFX2Timer
		sta AUDF0
			
		rts
				
ActuallyLoseaLife:
		lda #0
		sta AUDV0
		sta SFX2Timer

		lda #1
		sta ScoreorLivesDisplay		
		
		dec Lives
	
		rts

Joystick:
		lda SFX2Timer
		bne LoseaLife

		lda CXPPMM                 ; 3       
		and #%10000000             ; 2        
        bne LoseaLife
		
Move_OnionRing
		lda Frame
		and #3
		beq SlowItDown2

		lda #0
		sta HMP1

		jmp NNNNNNJoystick
	
SlowItDown2
		lda #%00010000
		sta HMP1

        ldy PlayerX+1  ; get the Player's X position
        dey             ; and move it left
        cpy #3       ; test for edge of screen
        bcs SaveX12      ; save X if we're not at the edge
		
		jsr GetPlayer1Y

SaveX12: sty PlayerX+1   ; save X

NNNNNNJoystick
        lda SWCHA       ; reads joystick positions
  
PJloop:    
        asl             ; shift A bits left, R is now in the carry bit
        bcs CheckLeft   ; branch if joystick is not held right
        ldy PlayerX  
        iny             ; and move it right
        cpy #139       ; test for edge of screen
        bcc SaveX       ; save Y if we're not at the edge
        ldy #139          ; else wrap to left edge
SaveX:  sty PlayerX   ; saveX
     ;   ldy #0          ; turn off reflect of player, which
      ;  sty REFP0     ; makes Burgeroid image face right

CheckLeft:
        asl             ; shift A bits left, L is now in the carry bit
        bcs CheckDown   ; branch if joystick not held left
        ldy PlayerX   ; get the Player's X position
        dey             ; and move it left
        cpy #20       ; test for edge of screen
        bcs SaveX2      ; save X if we're not at the edge
        ldy #20        ; else wrap to right edge
SaveX2: sty PlayerX   ; save X
    ;    ldy #8          ; turn on reflect of player, which
     ;   sty REFP0     ; makes Burgeroid image face left 

CheckDown:
        asl                     ; shift A bits left, D is now in the carry bit
        bcs CheckUp             ; branch if joystick not held down
        ldy PlayerY          ; get the Player's Y position
        dey                     ; move it down
        cpy #31            ; test for bottom of screen
        bcs SaveY               ; save Y if we're not at the bottom
		ldy #31					; else wrap to top
SaveY:  sty PlayerY          ; save Y

CheckUp:
        asl                     ; shift A bits left, U is now in the carry bit
        bcs FireButton       ; branch if joystick not held up
        ldy PlayerY           ; get the Player's Y position
        iny                     ; move it up
        cpy #116	    			; test for top of screen
        bcc SaveY2              ; save Y if we're not at the top
        ldy #116                 ; else wrap to bottom
SaveY2: sty PlayerY           ; save Y
        
FireButton:
 		lda SFXTimer
		beq FireButton2
		
		jsr Fry_ring_crash_sfx

FireButton2
		lda #$30		
		sta NUSIZ1
		sta NUSIZ0

 		lda ShootingStatus
		cmp #1
		beq Missile1Moving
		
		cmp #2
		beq EndMissile1Movement_______
		
		lda INPT4           ; read the player's fire button value	
		bpl FirePressed
	
		rts

EndMissile1Movement_______
	jmp EndMissile1Movement

FirePressed:
		lda #4
		sta AUDV0
		
		lda #1
        sta ShootingStatus
		sta AUDC0
	
		lda PlayerY
		adc #251
		sta MissileY+1

		lda PlayerX
		adc #7
		sta MissileX+1
		
		ldx #3
		jsr PosPlayer	
		
		;rts
	
Missile1Moving
		lda MissileX+1
		cmp #150
		bcs EndMissile1Movement	
		
		lda Frame
		and #3
		beq SlowItDown1

		lda CXM1P                 ; 3       
		and #%01000000             ; 2        
        bne Collision_fry
		
		lda #0
		sta HMM1
		sta HMP0

		jsr EffectiveShot
		
		rts

Fry_ring_crash_sfx:
		lda SFXTimer
		cmp #10
		beq quit_sfx
		
		inc SFXTimer
		
		lda #8
		sta AUDC1
		
		lda SFXTimer
		sta AUDF1
		
		lda #4
		sta AUDV1
		
		rts

quit_sfx:
		lda #0
		sta AUDV1
		sta SFXTimer
		
		jsr GetPlayer1Y
		
		sta CXCLR	
		
		rts

Collision_fry:
		jsr EndMissile1Movement
		
        sed             ; turn on decimal mode
        clc
        lda Score+1     ; Score+1 holds the Tens and Ones digits
        adc #1          ; add 1 to score
        sta Score+1
        lda Score       ; Score holds the Thousands and Hundreds digits
        adc #0          ; add 0 to this digit, carry will inc by 1 if needed
        sta Score       ;
        cld             ; turn off decimal mode

		lda #255
		sta PlayerX+1
		sta PlayerY+1
		
		lda #1
		sta SFXTimer
		
		jmp Fry_ring_crash_sfx
		
SlowItDown1
		lda MissileX+1
		lsr
		lsr
		lsr
		sta AUDF0
	
		lda #%11100000
		sta HMM1
	
		lda MissileX+1
		adc #6
		sta MissileX+1	
	
		lda #0
		sta HMP0

		jsr EffectiveShot
		
		rts
	
EffectiveShot:		
		sta WSYNC
		sta HMOVE
		
		rts
		
EndMissile1Movement:
		lda #0
		sta AUDV0
		sta MissileX+1
		sta ENAM1		

		lda INPT4           ; read the player's fire button value	
		bpl FirePressed2

        lda #0
        sta ShootingStatus	
		sta HMM1
		sta HMP0		

		jsr EffectiveShot		

		lda #0
		sta ENAM1
		
		rts
	
FirePressed2:	
	    lda #2
        sta ShootingStatus

		lda #0
		sta HMM1
		sta HMP0		
		jsr EffectiveShot		

		lda #0
		sta ENAM1		
		
		rts
		
PosPlayer:
        sec
        sta WSYNC
DivideLoop
        sbc #15        ; 2  2 - each time thru this loop takes 5 cycles, which is 
        bcs DivideLoop ; 2  4 - the same amount of time it takes to draw 15 pixels
        eor #7         ; 2  6 - The EOR & ASL statements convert the remainder
        asl            ; 2  8 - of position/15 to the value needed to fine tune
        asl            ; 2 10 - the X position
        asl            ; 2 12
        asl            ; 2 14
        sta.wx HMP0,X  ; 5 19 - store fine tuning of X
        sta RESP0,X    ; 4 23 - set coarse X position of Player
        rts            ; 6 29 - ReTurn from Subroutine		
	
Overscan
        sta WSYNC   ; Wait for SYNC (start of next scanline)
        lda #2      ; LoaD Accumulator with 2
        sta VBLANK  ; STore Accumulator to VBLANK, D1=1 turns image output off
        lda OverscanValue  	; previously OverscanValue
        sta TIM64T  ; set timer for end of Overscan
OSwait:
        sta WSYNC
        bit TIMINT
        bpl OSwait  ; wait for the timer to denote end of Overscan
		rts	
	
		align 256
	
DigitGfx:
		.byte %0
        .byte %01111100
        .byte %11000110
        .byte %11000110
        .byte %11000110
        .byte %11000110
        .byte %11000110
        .byte %01111100
   	
		.byte %0	
        .byte %00011000
        .byte %00011000
        .byte %00011000
        .byte %00011000
        .byte %01011000
        .byte %00111000
        .byte %00011000

		.byte %0
        .byte %11111110
        .byte %11000000
        .byte %01100000
        .byte %00011000
        .byte %00000110
        .byte %11000110
        .byte %01111100

		.byte %0
        .byte %11111100
        .byte %00000110
        .byte %00000110
        .byte %00111100
        .byte %00000110
        .byte %00000110
        .byte %11111100

		.byte %0
        .byte %00001100
        .byte %00001100
        .byte %11111110
        .byte %11001100
        .byte %11001100
        .byte %11001100
        .byte %11000000

		.byte %0
        .byte %11111100
        .byte %00000110
        .byte %00000110
        .byte %11111100
        .byte %11000000
        .byte %11000000
        .byte %11111110

		.byte %0
        .byte %01111100
        .byte %11000110
        .byte %11000110
        .byte %11111100
        .byte %11000000
        .byte %11000010
        .byte %01111100

		.byte %0
        .byte %01100000
        .byte %00110000
        .byte %00011000
        .byte %00001100
        .byte %00000110
        .byte %00000110
        .byte %11111110

		.byte %0
        .byte %01111100
        .byte %11000110
        .byte %11000110
        .byte %01111100
        .byte %11000110
        .byte %11000110
        .byte %01111100

		.byte %0
        .byte %01111100
        .byte %10000110
        .byte %00000110
        .byte %01111110
        .byte %11000110
        .byte %11000110
        .byte %01111100
	
		align 256
	
OnionringGfx:
        .byte %01111110
        .byte %11111111
        .byte %11000111		
        .byte %11000011
        .byte %11100011
        .byte %01111110
        .byte %00111100
Onionring_HEIGHT = * - OnionringGfx  	
	
BurgerGfx:
        .byte %01111110
        .byte %11111111		
        .byte %11111111		
        .byte %11111111		
        .byte %11111111
        .byte %11111111
        .byte %11111111
        .byte %01111110
Burger_HEIGHT = * - BurgerGfx  

BurgerColors:
		.byte #$2C
		.byte #$2C
		.byte #$26
		.byte #$36			
		.byte #$C6
		.byte #$2C		
		.byte #$2C
		.byte #$2C 
		.byte #$2C		

	echo "------", [$FFFA - *]d, "bytes free before you run out of space."

            ORG $FFFA

InterruptVectors
            .word Reset          ; NMI
            .word Reset          ; RESET
            .word Reset          ; IRQ

      END	