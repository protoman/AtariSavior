CAVE_P0CHI   = $FC
CAVE_NDESIGN = 12
CaveDesignOff:  .byte 0,12,16,30,45,55,69,79,85,101,109,111
CaveDesignGHi:  .byte $F8,$F8,$F8,$F8,$F9,$F9,$F9,$F9,$FA,$FA,$FA,$FA
CaveDesignCHi:  .byte $FB,$FB,$FB,$FB,$FD,$FD,$FD,$FD,$FE,$FE,$FE,$FE
CaveDesignKb:   .byte 53,107,161,215,53,107,161,215,53,107,161,215
CaveFrameGHi:   .byte $FF,$FF,$FF,$FC
CaveFrameKb:    .byte 59,119,179,171
CaveFineTab:    .byte $70,$60,$50,$40,$30,$20,$10,$00,$F0,$E0,$D0,$C0,$B0,$A0,$90
CAVE_IDXLEN = 56
CaveDesignIdx:
    .byte 0,0,0,0,0,0,1,0,2,0,0,0,0,0,0,3
    .byte 0,0,0,0,0,0,4,0,0,0,0,5,0,0,0,0
    .byte 0,0,6,0,0,0,0,7,0,0,8,0,0,0,0,0
    .byte 0,0,9,0,0,0,10,11
