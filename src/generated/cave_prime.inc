    ldy #0
    lda G0
    beq .zero0                      ; out of range (S = 0): the prime byte is 0
    dec G0
    lda (G0),Y
    inc G0
    jmp .set0g
.zero0:
    lda #0
.set0g:
    sta GRP0
    lda G1
    beq .zero1
    dec G1
    lda (G1),Y
    inc G1
    jmp .set1g
.zero1:
    lda #0
.set1g:
    sta GRP1
    ldx #0
