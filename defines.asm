VSYNC   = $00
VBLANK  = $01
WSYNC   = $02
RSYNC   = $03
NUSIZ0  = $04
NUSIZ1  = $05
COLUP0  = $06
COLUP1  = $07
COLUPF  = $08
COLUBK  = $09
CTRLPF  = $0A
REFP0   = $0B
REFP1   = $0C
PF0     = $0D
PF1     = $0E
PF2     = $0F
RESP0   = $10
RESP1   = $11
RESM0   = $12
RESM1   = $13
RESBL   = $14
AUDC0   = $15
AUDC1   = $16
AUDF0   = $17
AUDF1   = $18
AUDV0   = $19
AUDV1   = $1A
GRP0    = $1B
GRP1    = $1C
ENAM0   = $1D
ENAM1   = $1E
ENABL   = $1F
HMP0    = $20
HMP1    = $21
HMM0    = $22
HMM1    = $23
HMBL    = $24
VDELP0  = $25
VDELP1  = $26
VDELM0  = $27
VDELM1  = $28
RESMP0  = $29
RESMP1  = $2A
HMOVE   = $2B
HMCLR   = $2C
CXCLR   = $2D

; Read registers
CXM0P   = $00
CXM1P   = $01
CXP0FB  = $02
CXP1FB  = $03
CXM0FB  = $04
CXM1FB  = $05
CXBLPF  = $06
CXPPMM  = $07
INPT0   = $08
INPT1   = $09
INPT2   = $0A
INPT3   = $0B
INPT4   = $0C
INPT5   = $0D

; RIOT registers
SWCHA   = $280
SWACNT  = $281
SWCHB   = $282
SWBCNT  = $283
INTIM   = $284
TIMINT  = $285

; RIOT timer
TIM1T   = $294
TIM8T   = $295
TIM64T  = $296
T1024T  = $297

; Bankswitch addresses for F6 (16K)
BANK0   = $1FF6
BANK1   = $1FF7
BANK2   = $1FF8
BANK3   = $1FF9

; Useful constants
BLACK   = $00
WHITE   = $0E
BROWN   = $32
ORANGE  = $5A
RED     = $46
BLUE    = $82
GREEN   = $C2
YELLOW  = $1C
CYAN    = $8A
MAGENTA = $64
GREY    = $0A

PF_SOLID   = $FF
PF_SIDE    = $F0
PF_EMPTY   = $00

; Player sprite dimensions
PLAYER_HEIGHT = 8
PLAYER_WIDTH  = 8

; Screen dimensions
SCREEN_WIDTH  = 160
SCREEN_HEIGHT = 192

; Border dimensions
TOP_BORDER    = 8
BOTTOM_BORDER = 8
SIDE_BORDER   = 4

; Physics constants
GRAVITY_LO = $10
GRAVITY_HI = $00

JET_ACCEL    = $01
JET_MAX      = $20
JET_DECEL    = $01
JET_THRUST   = $04

; Player bounds (inside the playfield border)
PLAYER_MIN_X = 4
PLAYER_MAX_X = 152
PLAYER_MIN_Y = 8
PLAYER_MAX_Y = 184 - PLAYER_HEIGHT
