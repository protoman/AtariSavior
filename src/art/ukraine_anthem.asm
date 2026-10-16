; one pass = bars 0-24, 8th=13 frames, AUDC=$0C
; melody +0 semitones, bass +12 semitones

MusicMel:  ; 50 entries
    .byte $FF,$FE, $1F,$FE, $82,$0A, $1A,$0B, $1A,$0A, $1A,$09, $34,$08, $1A,$FE
    .byte $1A,$09, $34,$0A, $34,$0B, $34,$FE, $34,$0A, $34,$FE, $34,$0A, $4E,$0F
    .byte $1A,$0D, $34,$0C, $1A,$03, $1A,$0B, $41,$0A, $0D,$FE, $34,$0A, $1A,$0B
    .byte $1A,$0A, $1A,$09, $41,$08, $0D,$FE, $1A,$09, $34,$0A, $27,$0B, $0D,$FE
    .byte $34,$0C, $34,$0A, $34,$FE, $34,$0A, $9C,$0F, $34,$FE, $68,$0D, $1A,$0A
    .byte $1A,$0B, $1A,$0C, $1A,$0D, $1A,$0F, $1A,$0D, $27,$0C, $0D,$0F, $68,$0D
    .byte $68,$0C, $1A,$0B
    .byte $00,$FF   ; end

MusicBas:  ; 36 entries
    .byte $68,$FE, $0D,$1B, $A9,$FE, $68,$0C, $68,$11, $68,$0C, $34,$11, $34,$10
    .byte $68,$0F, $68,$FE, $5B,$0F, $0D,$FE, $34,$0F, $34,$11, $5B,$0C, $0D,$FE
    .byte $5B,$11, $0D,$FE, $4E,$0C, $1A,$FE, $34,$0C, $34,$0B, $41,$0A, $27,$FE
    .byte $34,$0A, $34,$FE, $D0,$0F, $4E,$0A, $1A,$FE, $41,$0A, $27,$FE, $68,$0C
    .byte $41,$0A, $27,$FE, $68,$0F, $1A,$11
    .byte $00,$FF   ; end

; sizes: mel 102B  bas 74B  total 176B

; sum mel=2496 frames, sum bas=2496 frames  (target 2496)
