;------------------------------------------------------
;--- Standard 48px display kernel for Score display
;
; Centered: X = 56..104


SCORE_DIGIT_COLOR = $0E     ;-- white


;----- Variables needed by the score drawing loop

scorePtr1   = $E0   ;-- hundred thousands
scorePtr2   = $E2   ;-- ten thousands
scorePtr3   = $E4   ;-- thousands
scorePtr4   = $E6   ;-- hundreds
scorePtr5   = $E8   ;-- tens
scorePtr6   = $EA   ;-- ones

scbrdCnt    = $EC
scbrdTmp    = $ED



    ;--- Prepare for score display, 
    ;--    by set sprite positioning to center the display
    ;--
    ;--- NOTE:  This routine changes REFPx, NUSIZx, VDELPx.
    ;--         Also, GRPx will need to be cleared.

    LDA     #0
    STA     WSYNC
    STA     REFP0               ;3  [3]     -clear player reflection
    STA     REFP1               ;3  [6]
    LDA     #$01                ;2  [8]
    STA     CTRLPF              ;3  [11]
    LDA     #SCORE_DIGIT_COLOR  ;2  [13]    -- color of digits
    STA     COLUP0              ;3  [16]
    STA     COLUP1              ;3  [19]

    ; -- center the 48px kernel
    LDA     #$10                ;2  [21]
    STA     HMP0                ;3  [24]    -- -1 to P0
    LDA     #$20                ;2  [26]
    STA     HMP1                ;3  [29]    -- -2 to P1
    LDA     #$03                ;2  [31]
    STA     NUSIZ0              ;3  [34]
    STA     NUSIZ1              ;3  [37]
    STA     RESP0               ;3  *40* -- rough align numbers (120 - 68 = 52 - 1 + 5 ==> PIX: 56)
    STA     RESP1               ;3  *43*
    STA     VDELP0              ;3  [46] -- TURN on Vertical Delay for both players to activate graphics buffers
    STA     VDELP1              ;3  [49]    which helps with timing issues when loading graphics data
    
    STA     WSYNC
    STA     HMOVE
    
    ;----- Score Display loop

    LDY     #7
    STY     scbrdCnt
scoreBoardLoop48:
    LDY     <scbrdCnt           ;3 [64]
    LDA    (scorePtr6),Y        ;5 [69] -- scoreboard drawing loop
    TAX                         ;2 [71]
    STA    WSYNC                ;3 [0]
    LDA    (scorePtr1),Y        ;5 [5]
    STA.w  GRP0                 ;4 [9]  -- store digit 0
    LDA    (scorePtr2),Y        ;5 [14]
    STA    GRP1                 ;3 [17] -- ready to draw digit 0,  store digit 1
    LDA    (scorePtr3),Y        ;5 [22]
    STA    GRP0                 ;3 [25]  -- ready to draw digit 1,  store digit 2
    LDA    (scorePtr4),Y        ;5 [30]
    STA    <scbrdTmp            ;3 [33]
    LDA    (scorePtr5),Y        ;5 [38]
    LDY    <scbrdTmp            ;3 [41] - PIXEL: 55 --- 41 * 3 =-> 123 - 68 = 55 
    STY    GRP1                 ;3 *44*  -- draw digit 2, store digit 3
    STA    GRP0                 ;3 *47*  -- draw digit 3, store digit 4
    STX    GRP1                 ;3 *50* -- draw digit 4, store digit 5
    STX    GRP0                 ;3 [53] - draw digit 5, store junk
                                ;-- cycle 53 --- 53 * 3 =-> 159 - 68 = 91 pixel pos

    DEC     <scbrdCnt           ;5 [58]

    BNE     scoreBoardLoop48    ;3  [61]
    JMP     cleanupScoreBoard   ;3  [64]