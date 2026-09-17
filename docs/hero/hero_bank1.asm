; Disassembly of /tmp/hero_bank1.bin
; Disassembled Fri Sep 11 18:09:56 2026
; Using DiStella v3.02-SNAPSHOT
;
; Command Line: ./distella -pafs /tmp/hero_bank1.bin 
;

      processor 6502
VSYNC   =  $00
NUSIZ1  =  $05
COLUP1  =  $07
CTRLPF  =  $0A
REFP0   =  $0B
SWCHA   =  $0280

       ORG $F000

START:
       SEI            ;2
       STA    LFFF9   ;4
       CLD            ;2
       LDX    #$00    ;2
LF007: LDA    #$00    ;2
LF009: STA    VSYNC,X ;4
       TXS            ;2
       INX            ;2
       BNE    LF009   ;2
       LDA    $B6     ;3
       BNE    LF01A   ;2
       LDA    $80     ;3
       AND    #$7F    ;2
       STA    $80     ;3
       TAX            ;2
LF01A: LDA    LFF6D,X ;4
       STA    $F5     ;3
       LDX    #$18    ;2
LF021: LDA    LFF72,X ;4
       STA    $9B,X   ;4
       DEX            ;2
       BPL    LF021   ;2
       LDA    $F5     ;3
       AND    #$03    ;2
       TAX            ;2
       LDA    LFF6A,X ;4
       STA    $A4     ;3
       LDX    $82     ;3
       BEQ    LF03A   ;2
       JMP    LF0BA   ;3
LF03A: INX            ;2
       STX    $82     ;3
       DEC    $BA     ;5
       JMP    LF093   ;3
LF042: LDY    SWCHA   ;4
       LDA    $81     ;3
       AND    #$07    ;2
       BNE    LF063   ;2
       LDA    $B6     ;3
       BEQ    LF063   ;2
       LDY    #$FF    ;2
       DEC    $B6     ;5
       BNE    LF063   ;2
       DEC    $B6     ;5
       LDA    $B5     ;3
       BMI    LF063   ;2
       ORA    #$80    ;2
       STA    $B5     ;3
       LDX    #$BA    ;2
       BNE    LF07B   ;2
LF063: TYA            ;2
       AND    #$F0    ;2
       STA    $84     ;3
       INY            ;2
       BEQ    LF06F   ;2
       LDA    #$00    ;2
       STA    $B4     ;3
LF06F: LDA    $FB     ;3
       NOP            ;2
       LSR            ;2
       BCS    LF07E   ;2
       LDA    #$00    ;2
       STA    $BA     ;3
       LDX    #$B4    ;2
LF07B: JMP    LF007   ;3
LF07E: LDY    #$00    ;2
       LSR            ;2
       BCS    LF0B8   ;2
       LDA    #$FF    ;2
       STA    $BA     ;3
       STA    $AD     ;3
       LDA    $83     ;3
       BEQ    LF091   ;2
       DEC    $83     ;5
       BPL    LF0BA   ;2
LF091: INC    $80     ;5
LF093: LDA    $80     ;3
       AND    #$7F    ;2
       CMP    #$05    ;2
       BCC    LF0A2   ;2
       LDA    #$80    ;2
       AND    $80     ;3
       STA    $80     ;3
       ASL            ;2
LF0A2: STA    $B4     ;3
       STA    $B5     ;3
       ORA    #$A0    ;2
       TAY            ;2
       INY            ;2
       STY    $B9     ;3
       LDA    #$AA    ;2
       STA    $B7     ;3
       STA    $B8     ;3
       LDA    #$1F    ;2
       STA    $B6     ;3
       LDY    #$1E    ;2
LF0B8: STY    $83     ;3
LF0BA: LDA    $AD     ;3
       ORA    $F2     ;3
       ORA    $F7     ;3
       ORA    $F8     ;3
       BNE    LF0C6   ;2
       INC    $F6     ;5
LF0C6: LDA    $82     ;3
       ASL            ;2
       ASL            ;2
       ASL            ;2
       EOR    $82     ;3
       ASL            ;2
       ROL    $82     ;5
       LDA    $B6     ;3
       BEQ    LF106   ;2
       BIT    $B4     ;3
       BPL    LF0DB   ;2
       JMP    LF282   ;3
LF0DB: JSR    LF630   ;6
       LDX    LFF42,Y ;4
       LDA    $AC     ;3
       BEQ    LF104   ;2
       LDA    $DF     ;3
       BEQ    LF0F3   ;2
       CMP    #$2C    ;2
       BCC    LF104   ;2
       LDX    LFF56,Y ;4
       JMP    LF104   ;3
LF0F3: LDA    $A0     ;3
       SEC            ;2
       SBC    #$0F    ;2
       CMP    $9B     ;3
       BCS    LF104   ;2
       ADC    #$17    ;2
       CMP    $9B     ;3
       BCC    LF104   ;2
       LDX    #$D0    ;2
LF104: STX    $84     ;3
LF106: LDA    #$00    ;2
       STA    $BD     ;3
       LDA    $D8     ;3
       CMP    #$97    ;2
       BNE    LF14B   ;2
       LDA    $AD     ;3
       BNE    LF14B   ;2
       LDA    $9C     ;3
       CMP    #$0B    ;2
       BCC    LF14B   ;2
       BIT    COLUP1  ;3
       BPL    LF14B   ;2
       LDA    $EC     ;3
       AND    #$7F    ;2
       CLC            ;2
       ADC    #$18    ;2
       STA    $BB     ;3
       LDA    $9B     ;3
       SEC            ;2
       SBC    $BB     ;3
       CMP    #$09    ;2
       BCS    LF14B   ;2
       LDA    #$40    ;2
       STA    $E6     ;3
       STA    $AC     ;3
       LDA    #$08    ;2
       BIT    $EC     ;3
       BPL    LF13E   ;2
       LDA    #$00    ;2
LF13E: STA    $B0     ;3
       LDA    #$FF    ;2
       STA    $BD     ;3
       LDA    $BB     ;3
       CLC            ;2
       ADC    #$04    ;2
       STA    $9B     ;3
LF14B: LDA    $D8     ;3
       CMP    #$97    ;2
       BEQ    LF177   ;2
       CMP    #$99    ;2
       BEQ    LF177   ;2
       BIT    $D1     ;3
       BMI    LF177   ;2
       LDA    $AD     ;3
       BNE    LF177   ;2
       BIT    COLUP1  ;3
       BPL    LF177   ;2
       LDA    $9C     ;3
       CMP    #$0B    ;2
       BCC    LF177   ;2
       LDX    #$F0    ;2
       LDA    $9B     ;3
       CMP    $A8     ;3
       BEQ    LF175   ;2
       LDX    #$70    ;2
       BCC    LF175   ;2
       LDX    #$B0    ;2
LF175: STX    $84     ;3
LF177: LDA    $E1     ;3
       ORA    $BA     ;3
       ORA    $F2     ;3
       ORA    $AD     ;3
       BEQ    LF184   ;2
       JMP    LF282   ;3
LF184: LDA    #$10    ;2
       AND    $84     ;3
       BNE    LF190   ;2
       INC    $E9     ;5
       BIT    $E9     ;3
       BVC    LF196   ;2
LF190: DEC    $E9     ;5
       BPL    LF196   ;2
       INC    $E9     ;5
LF196: LDX    $F5     ;3
       LDA    LFF00,X ;4
       CLC            ;2
       ADC    $9C     ;3
       TAX            ;2
       LDA    $E9     ;3
       LSR            ;2
       LSR            ;2
       LSR            ;2
       TAY            ;2
       LDA    $9C     ;3
       STA    $BB     ;3
       CMP    #$0B    ;2
       BCC    LF1B2   ;2
       CPY    #$00    ;2
       BNE    LF1B2   ;2
       INY            ;2
LF1B2: LDA    $9F     ;3
       CPY    #$04    ;2
       BCC    LF1D8   ;2
       BIT    $E6     ;3
       BMI    LF20E   ;2
       CLC            ;2
       ADC    LFFB0,Y ;4
       CMP    #$8A    ;2
       BCC    LF20C   ;2
       LDA    #$04    ;2
       STA    $9F     ;3
       DEC    $9C     ;5
       BPL    LF1D2   ;2
       INC    $9C     ;5
       LDA    #$8A    ;2
       BNE    LF20C   ;2
LF1D2: JSR    LF63A   ;6
       JMP    LF20E   ;3
LF1D8: BIT    $E6     ;3
       BVS    LF20E   ;2
       SEC            ;2
       SBC    LFFB0,Y ;4
       CMP    #$16    ;2
       BCS    LF1F4   ;2
       LDX    $9C     ;3
       CPX    #$0A    ;2
       BCC    LF1F4   ;2
       LDX    #$00    ;2
       STX    $AE     ;3
       LDA    #$FF    ;2
       STA    $AD     ;3
       LDA    #$15    ;2
LF1F4: CMP    #$FE    ;2
       BCC    LF20C   ;2
       LDA    #$89    ;2
       STA    $9F     ;3
       LDA    $9E     ;3
       CMP    $9C     ;3
       BNE    LF204   ;2
       INC    $9E     ;5
LF204: INC    $9C     ;5
       JSR    LF63A   ;6
       JMP    LF20E   ;3
LF20C: STA    $9F     ;3
LF20E: BIT    $BD     ;3
       BMI    LF282   ;2
       LDA    $AD     ;3
       BNE    LF282   ;2
       LDA    $9B     ;3
       AND    #$03    ;2
       BNE    LF236   ;2
       BIT    $84     ;3
       BPL    LF224   ;2
       BVS    LF282   ;2
       LDA    #$08    ;2
LF224: CMP    $B0     ;3
       BEQ    LF234   ;2
       LDX    #$FD    ;2
       STX    $F3     ;3
       LDX    $AC     ;3
       BNE    LF234   ;2
       LDX    #$03    ;2
       STX    $FC     ;3
LF234: STA    $B0     ;3
LF236: LDA    $9C     ;3
       STA    $BB     ;3
       DEC    $FC     ;5
       BPL    LF282   ;2
       INC    $FC     ;5
       LDA    $9B     ;3
       LDX    $B0     ;3
       BEQ    LF253   ;2
       SEC            ;2
       SBC    #$01    ;2
       STA    $9B     ;3
       CMP    #$0C    ;2
       BCS    LF282   ;2
       LDX    #$00    ;2
       BEQ    LF25E   ;2
LF253: CLC            ;2
       ADC    #$01    ;2
       STA    $9B     ;3
       CMP    #$93    ;2
       BCC    LF282   ;2
       LDX    #$01    ;2
LF25E: JSR    LF630   ;6
       LDA    LF900,Y ;4
       AND    #$01    ;2
       CMP    LFFAA,X ;4
       BEQ    LF278   ;2
       LDA    $9E     ;3
       CMP    $9C     ;3
       BNE    LF273   ;2
       INC    $9E     ;5
LF273: INC    $9C     ;5
       JMP    LF27A   ;3
LF278: DEC    $9C     ;5
LF27A: LDA    LFFAC,X ;4
       STA    $9B     ;3
       JSR    LF63A   ;6
LF282: LDX    #$02    ;2
LF284: LDA    $A4     ;3
       LSR            ;2
       BCC    LF293   ;2
       LDA    $E0     ;3
       ORA    $DF     ;3
       BEQ    LF298   ;2
       LDA    #$02    ;2
       BNE    LF298   ;2
LF293: LDA    LFFAE,X ;4
       ORA    $A4     ;3
LF298: STA    $C5,X   ;4
       DEX            ;2
       BPL    LF284   ;2
       JSR    LF630   ;6
       LDA    LF700,Y ;4
       CMP    #$93    ;2
       BEQ    LF2A9   ;2
       AND    #$FC    ;2
LF2A9: STA    $A5     ;3
       LDA    LF800,Y ;4
       CMP    #$93    ;2
       BEQ    LF2B4   ;2
       AND    #$FC    ;2
LF2B4: STA    $A6     ;3
       LDA    LF900,Y ;4
       AND    #$FC    ;2
       ORA    #$01    ;2
       CMP    #$91    ;2
       BNE    LF2C3   ;2
       LDA    #$93    ;2
LF2C3: STA    $A7     ;3
       LDA    #$C0    ;2
       LDX    $9C     ;3
       BEQ    LF2D4   ;2
       LDA    #$FF    ;2
       CPX    #$0B    ;2
       BCS    LF2D4   ;2
       LDA    LFAFF,Y ;4
LF2D4: STA    $C1     ;3
       LDA    LFA00,Y ;4
       STA    $C0     ;3
       LDA    LFB00,Y ;4
       STA    $BF     ;3
       LDA    #$00    ;2
       LDX    $9C     ;3
       BEQ    LF2EF   ;2
       LDA    #$FF    ;2
       CPX    #$0B    ;2
       BCS    LF2EF   ;2
       LDA    LFCFF,Y ;4
LF2EF: STA    $C4     ;3
       LDA    LFC00,Y ;4
       STA    $C3     ;3
       LDA    LFD00,Y ;4
       STA    $C2     ;3
       LDA    $B1     ;3
       ROL            ;2
       ROL            ;2
       ROL            ;2
       AND    #$03    ;2
       TAX            ;2
       LDA    LFF3E,X ;4
       STA    NUSIZ1  ;3
       STA    $BB     ;3
       ORA    #$05    ;2
       STA    CTRLPF  ;3
       STA    $C8     ;3
       STA    $CA     ;3
       LDA    LFE00,Y ;4
       LSR            ;2
       LDA    #$05    ;2
       BCC    LF31C   ;2
       LDA    #$04    ;2
LF31C: ORA    $BB     ;3
       STA    $C9     ;3
       LDA    LFE00,Y ;4
       LSR            ;2
       LSR            ;2
       BCC    LF334   ;2
       LDA    $81     ;3
       LSR            ;2
       LSR            ;2
       LSR            ;2
       AND    #$01    ;2
       TAX            ;2
       LDA    LFF3C,X ;4
       STA    $C6     ;3
LF334: LDA    #$FF    ;2
       STA    $BE     ;3
       LDA    $9C     ;3
       CMP    #$0A    ;2
       BCS    LF351   ;2
       LDX    $F5     ;3
       LDA    LFF28,X ;4
       CMP    $9C     ;3
       BEQ    LF355   ;2
       LDA    $A0     ;3
       CMP    #$09    ;2
       BEQ    LF351   ;2
       CMP    #$99    ;2
       BNE    LF355   ;2
LF351: LDA    #$00    ;2
       STA    $BE     ;3
LF355: LDA    $C3     ;3
       CMP    #$7F    ;2
       BNE    LF374   ;2
       LDA    $C0     ;3
       CMP    #$FF    ;2
       BNE    LF374   ;2
       LDA    $F5     ;3
       CMP    #$0D    ;2
       BCC    LF374   ;2
       LDA    $FD     ;3
       LSR            ;2
       LSR            ;2
       LSR            ;2
       AND    #$07    ;2
       TAX            ;2
       LDA    LFFB8,X ;4
       STA    $C3     ;3
LF374: LDA    $F6     ;3
       LSR            ;2
       LSR            ;2
       AND    #$03    ;2
       TAX            ;2
       LSR            ;2
       TAY            ;2
       LDA    LFF8B,Y ;4
       STA    $85     ;3
       LDA    LFF8D,Y ;4
       STA    $86     ;3
       LDA    LFF8F,X ;4
       STA    $87     ;3
       LDA    LFF9B,Y ;4
       STA    $88     ;3
       LDA    #$4D    ;2
       STA    $89     ;3
       LDA    #$5A    ;2
       STA    $8A     ;3
       LDA    #$33    ;2
       STA    $8B     ;3
       LDA    #$17    ;2
       STA    $8C     ;3
       LDA    $EA     ;3
       AND    #$7F    ;2
       STA    $BB     ;3
       LDA    $EB     ;3
       AND    #$7F    ;2
       STA    $BC     ;3
       LDX    #$02    ;2
LF3AF: CPX    #$02    ;2
       BEQ    LF400   ;2
       JSR    LF630   ;6
       LDA    LF700,Y ;4
       AND    #$03    ;2
       CPX    #$00    ;2
       BEQ    LF3C4   ;2
       LDA    LF800,Y ;4
       AND    #$03    ;2
LF3C4: TAY            ;2
       LDA    $A1,X   ;4
       CMP    #$32    ;2
       BEQ    LF3F3   ;2
       CPY    #$03    ;2
       BNE    LF3E1   ;2
       LDA    $F7,X   ;4
       BEQ    LF3D7   ;2
       LDA    #$09    ;2
       BNE    LF3D9   ;2
LF3D7: LDA    $BB     ;3
LF3D9: CLC            ;2
       ADC    $A5,X   ;4
       STA    $A5,X   ;4
       JMP    LF3F3   ;3
LF3E1: TYA            ;2
       BEQ    LF3F3   ;2
       LDA    $BB     ;3
       STA    $A1,X   ;4
       CPY    #$02    ;2
       BNE    LF3F3   ;2
       LDA    $BC     ;3
       CLC            ;2
       ADC    $A5,X   ;4
       STA    $A5,X   ;4
LF3F3: LDA.wy $0085,Y ;4
       STA    $CB,X   ;4
       LDA.wy $0089,Y ;4
       STA    $CE,X   ;4
       JMP    LF408   ;3
LF400: LDA    #$8E    ;2
       STA    $D0     ;3
       LDA    #$64    ;2
       STA    $CD     ;3
LF408: LDA    $F7,X   ;4
       BEQ    LF41F   ;2
       SEC            ;2
       SBC    #$01    ;2
       STA    $F7,X   ;4
       BNE    LF417   ;2
       LDA    #$32    ;2
       STA    $A1,X   ;4
LF417: LDA    #$76    ;2
       STA    $CB,X   ;4
       LDA    #$40    ;2
       STA    $CE,X   ;4
LF41F: LDA    $A5,X   ;4
       CMP    #$93    ;2
       BCC    LF429   ;2
       LDA    #$8A    ;2
       STA    $CB,X   ;4
LF429: DEX            ;2
       BMI    LF42F   ;2
       JMP    LF3AF   ;3
LF42F: LDA    $A4     ;3
       LSR            ;2
       BCC    LF447   ;2
       LDX    #$02    ;2
LF436: LDA    $DE,X   ;4
       BNE    LF447   ;2
       LDA    $CB,X   ;4
       CMP    #$76    ;2
       BEQ    LF444   ;2
       LDA    #$9B    ;2
       STA    $CE,X   ;4
LF444: DEX            ;2
       BPL    LF436   ;2
LF447: LDX    #$02    ;2
LF449: LDY    $E7     ;3
       LDA    LFF93,Y ;4
       STA    $D8,X   ;4
       LDA    #$68    ;2
       STA    $DB,X   ;4
       LDA    $DE,X   ;4
       BEQ    LF48C   ;2
       DEC    $DE,X   ;6
       LDA    $DE,X   ;4
       BNE    LF466   ;2
       STA    $FA     ;3
       LDA    #$93    ;2
       STA    $A8,X   ;4
       BNE    LF48C   ;2
LF466: CMP    #$20    ;2
       BCS    LF48C   ;2
       CMP    #$13    ;2
       BCS    LF476   ;2
       LDY    $FA     ;3
       BEQ    LF476   ;2
       LDY    #$04    ;2
       BNE    LF47A   ;2
LF476: LSR            ;2
       AND    #$03    ;2
       TAY            ;2
LF47A: LDA    LFF96,Y ;4
       STA    $D8,X   ;4
       LDA    #$40    ;2
       STA    $DB,X   ;4
       LDA    $F2     ;3
       BNE    LF48C   ;2
       LDA    LFFA5,Y ;4
       STA    $E1     ;3
LF48C: LDA    $A8,X   ;4
       CMP    #$93    ;2
       BNE    LF496   ;2
       LDA    #$99    ;2
       STA    $D8,X   ;4
LF496: DEX            ;2
       BPL    LF449   ;2
       LDA    $9C     ;3
       CMP    #$0B    ;2
       BCC    LF4C0   ;2
       LDA    $F5     ;3
       CMP    #$09    ;2
       BCC    LF4C0   ;2
       LDA    $C2     ;3
       BNE    LF4C0   ;2
       LDA    $BF     ;3
       CMP    #$C0    ;2
       BNE    LF4C0   ;2
       LDA    #$97    ;2
       STA    $D8     ;3
       LDA    #$05    ;2
       STA    $DB     ;3
       LDA    $EC     ;3
       AND    #$7F    ;2
       CLC            ;2
       ADC    #$1C    ;2
       STA    $A8     ;3
LF4C0: LDA    $F5     ;3
       CMP    #$10    ;2
       BCC    LF502   ;2
       LDA    $9C     ;3
       CMP    #$0B    ;2
       BCC    LF54A   ;2
       LDA    $C2     ;3
       BNE    LF54A   ;2
       LDA    $BF     ;3
       CMP    #$E0    ;2
       BNE    LF54A   ;2
       LDA    $D8     ;3
       CMP    #$97    ;2
       BEQ    LF54A   ;2
       LDA    $A8     ;3
       CMP    #$93    ;2
       BNE    LF4F0   ;2
       LDX    #$78    ;2
       LDA    #$08    ;2
       AND    $B0     ;3
       BNE    LF4EC   ;2
LF4EA: LDX    #$1C    ;2
LF4EC: STX    $A8     ;3
       BNE    LF52B   ;2
LF4F0: CMP    #$92    ;2
       BEQ    LF54A   ;2
       LDA    $AD     ;3
       CMP    #$95    ;2
       BNE    LF505   ;2
       LDA    $AE     ;3
       BNE    LF505   ;2
       LDA    #$92    ;2
       STA    $A8     ;3
LF502: JMP    LF54A   ;3
LF505: LDA    #$03    ;2
       LDX    $F5     ;3
       CPX    #$12    ;2
       BCC    LF50F   ;2
       LDA    #$01    ;2
LF50F: AND    $81     ;3
       BNE    LF52B   ;2
       LDY    $A8     ;3
       CPY    $9B     ;3
       BEQ    LF52B   ;2
       BCS    LF524   ;2
       INY            ;2
       LDX    #$78    ;2
       CPY    #$78    ;2
       BCS    LF4EC   ;2
       BCC    LF529   ;2
LF524: DEY            ;2
       CPY    #$1C    ;2
       BCC    LF4EA   ;2
LF529: STY    $A8     ;3
LF52B: LDA    $F6     ;3
       LSR            ;2
       LSR            ;2
       LSR            ;2
       AND    #$07    ;2
       LDX    $AD     ;3
       BEQ    LF540   ;2
       TXA            ;2
       LSR            ;2
       LSR            ;2
       LSR            ;2
       LSR            ;2
       LSR            ;2
       TAX            ;2
       LDA    LFFC0,X ;4
LF540: TAX            ;2
       LDA    LF6D2,X ;4
       STA    $D8     ;3
       LDA    #$C4    ;2
       STA    $DB     ;3
LF54A: LDA    #$DD    ;2
       STA    $98     ;3
       LDA    #$DB    ;2
       STA    $94     ;3
       LDA    #$DA    ;2
       STA    $9A     ;3
       LDA    $9F     ;3
       SEC            ;2
       SBC    #$17    ;2
       STA    $BB     ;3
       LDA    #$DA    ;2
       STA    $92     ;3
       LDX    #$E2    ;2
       LDA    $AD     ;3
       CMP    #$96    ;2
       BCS    LF58A   ;2
       LDA    #$DE    ;2
       STA    $92     ;3
       LDX    #$E6    ;2
       LDA    $E1     ;3
       BNE    LF58A   ;2
       LDY    $E7     ;3
       LDX    LFFA2,Y ;4
       LDA    $AC     ;3
       BEQ    LF58A   ;2
       LDX    #$CC    ;2
       ASL            ;2
       BCC    LF58A   ;2
       LDA    #$DC    ;2
       STA    $92     ;3
       LDY    $E8     ;3
       LDX    LFF9D,Y ;4
LF58A: TXA            ;2
       SEC            ;2
       SBC    $BB     ;3
       STA    $91     ;3
       LDA    #$74    ;2
       SEC            ;2
       SBC    $BB     ;3
       STA    $95     ;3
       LDA    #$DD    ;2
       STA    $96     ;3
       LDY    $F5     ;3
       LDA    LFF28,Y ;4
       CMP    $9C     ;3
       BNE    LF5DC   ;2
       LDA    #$71    ;2
       STA    $D9     ;3
       LDA    #$26    ;2
       STA    $DC     ;3
       LDA    #$80    ;2
       STA    $A9     ;3
       LDA    LFF14,Y ;4
       TAY            ;2
       LDA    LFE00,Y ;4
       AND    #$FC    ;2
       CMP    #$08    ;2
       BNE    LF5D4   ;2
       LDX    #$01    ;2
LF5BF: LDA    $CB,X   ;4
       CMP    #$76    ;2
       BNE    LF5C9   ;2
       LDA    #$6D    ;2
       STA    $CB,X   ;4
LF5C9: DEX            ;2
       BPL    LF5BF   ;2
       LDA    #$08    ;2
       STA    REFP0   ;3
       LDA    #$18    ;2
       STA    $A9     ;3
LF5D4: LDA    $F2     ;3
       BEQ    LF5DC   ;2
       LDA    #$7E    ;2
       STA    $D9     ;3
LF5DC: LDX    #$06    ;2
       LDA    $A5,X   ;4
       CLC            ;2
       ADC    #$30    ;2
       BNE    LF5EF   ;2
LF5E5: LDA    $A5,X   ;4
       CMP    #$93    ;2
       BCC    LF5EF   ;2
       LDA    #$A9    ;2
       BNE    LF606   ;2
LF5EF: LDY    #$FF    ;2
       SEC            ;2
LF5F2: INY            ;2
       SBC    #$0F    ;2
       BCS    LF5F2   ;2
       EOR    #$0F    ;2
       ASL            ;2
       ASL            ;2
       ASL            ;2
       ASL            ;2
       ADC    #$80    ;2
       AND    #$F0    ;2
       STA    $D1,X   ;4
       TYA            ;2
       ORA    $D1,X   ;4
LF606: STA    $D1,X   ;4
       DEX            ;2
       BPL    LF5E5   ;2
       INX            ;2
       LDA    $9C     ;3
       CMP    #$0A    ;2
       BCS    LF61B   ;2
       LDY    $F5     ;3
       LDA    LFF28,Y ;4
       CMP    $9C     ;3
       BNE    LF622   ;2
LF61B: LDA    $81     ;3
       LSR            ;2
       LSR            ;2
       AND    #$07    ;2
       TAX            ;2
LF622: STX    $FB     ;3
       LDX    #$02    ;2
LF626: LDA    $B7,X   ;4
       STA    $BB,X   ;4
       DEX            ;2
       BPL    LF626   ;2
       JMP    LFFEC   ;3
LF630: LDY    $F5     ;3
       LDA    LFF00,Y ;4
       CLC            ;2
       ADC    $9C     ;3
       TAY            ;2
       RTS            ;6

LF63A: LDX    #$02    ;2
LF63C: LDA    $F7,X   ;4
       BEQ    LF648   ;2
       LDA    #$32    ;2
       STA    $A1,X   ;4
       LDA    #$00    ;2
       STA    $F7,X   ;4
LF648: DEX            ;2
       BPL    LF63C   ;2
       LDA    #$00    ;2
       STA    $B1     ;3
       STA    $FA     ;3
       STA    $EA     ;3
       STA    $EB     ;3
       STA    $F6     ;3
       LDA    #$50    ;2
       STA    $FD     ;3
       LDA    #$93    ;2
       STA    $A8     ;3
       STA    $A9     ;3
       STA    $AA     ;3
       LDA    $B0     ;3
       CMP    #$08    ;2
       LDA    #$80    ;2
       BCC    LF66D   ;2
       LDA    #$60    ;2
LF66D: STA    $EC     ;3
       LDA    $BB     ;3
       LDX    $9C     ;3
       CPX    $9D     ;3
       STA    $9D     ;3
       BNE    LF68B   ;2
       LDX    #$04    ;2
LF67B: LDA    $A0,X   ;4
       STA    $BB     ;3
       LDA    $ED,X   ;4
       STA    $A0,X   ;4
       LDA    $BB     ;3
       STA    $ED,X   ;4
       DEX            ;2
       BPL    LF67B   ;2
       RTS            ;6

LF68B: LDX    #$04    ;2
LF68D: LDA    $A0,X   ;4
       STA    $ED,X   ;4
       DEX            ;2
       BPL    LF68D   ;2
       LDA    $F5     ;3
       AND    #$03    ;2
       TAX            ;2
       LDA    LFF6A,X ;4
       STA    $A4     ;3
       LDX    $F5     ;3
       LDA    LFF00,X ;4
       CLC            ;2
       ADC    $9C     ;3
       TAX            ;2
       LDA    LFE00,X ;4
       AND    #$FC    ;2
       BEQ    LF6B0   ;2
       ORA    #$01    ;2
LF6B0: STA    $A0     ;3
       TAX            ;2
       CPX    #$09    ;2
       BEQ    LF6BD   ;2
       CPX    #$99    ;2
       BEQ    LF6BD   ;2
       LDX    #$00    ;2
LF6BD: LDA    $9E     ;3
       CMP    $9C     ;3
       BNE    LF6C7   ;2
       LDA    #$00    ;2
       BEQ    LF6CB   ;2
LF6C7: STX    $A0     ;3
       LDA    #$32    ;2
LF6CB: STA    $A1     ;3
       STA    $A2     ;3
       STA    $A3     ;3
       RTS            ;6

LF6D2: .byte $A6,$B2,$BE,$CA,$D6,$CA,$BE,$B2,$00,$00,$00,$00,$00,$00,$00,$00
       .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
       .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
LF700: .byte $93,$93,$93,$93,$50,$93,$93,$46,$93,$28,$93,$93,$93,$93,$4C,$18
       .byte $40,$4C,$51,$93,$93,$93,$5E,$93,$7B,$93,$71,$93,$93,$1A,$50,$60
       .byte $93,$3C,$18,$68,$93,$93,$93,$44,$93,$93,$13,$72,$19,$50,$68,$78
       .byte $48,$93,$93,$50,$50,$68,$1B,$93,$93,$93,$63,$93,$93,$36,$53,$93
       .byte $93,$7C,$38,$3D,$93,$3A,$93,$18,$93,$2A,$4E,$3E,$53,$52,$93,$93
       .byte $93,$19,$93,$1D,$93,$28,$81,$2E,$2E,$2E,$26,$3E,$53,$93,$2A,$93
       .byte $93,$38,$85,$50,$14,$15,$36,$41,$4D,$65,$93,$6D,$3C,$64,$20,$93
       .byte $93,$7D,$93,$29,$43,$28,$5A,$93,$36,$52,$5D,$57,$93,$64,$3C,$32
       .byte $93,$6C,$93,$93,$93,$88,$93,$51,$6D,$93,$3D,$62,$4C,$5E,$65,$3E
       .byte $93,$93,$43,$93,$43,$32,$93,$93,$25,$93,$16,$5E,$44,$53,$42,$5C
       .byte $93,$93,$40,$93,$42,$93,$6B,$93,$93,$93,$2A,$53,$5B,$3C,$93,$31
       .byte $93,$93,$32,$4C,$7F,$36,$42,$60,$61,$61,$4D,$5C,$1E,$4C,$5E,$93
       .byte $93,$81,$21,$52,$4A,$93,$19,$93,$5E,$40,$13,$2E,$65,$53,$2C,$70
       .byte $93,$19,$6B,$51,$13,$93,$26,$93,$93,$31,$93,$5E,$4C,$35,$46,$93
       .byte $93,$93,$3E,$76,$89,$93,$40,$31,$2E,$35,$74,$2E,$4C,$64,$93,$69
       .byte $93,$80,$62,$28,$3A,$2E,$70,$6A,$62,$70,$4E,$4C,$70,$66,$6A,$93
LF800: .byte $93,$30,$93,$3C,$39,$6D,$93,$2C,$30,$69,$42,$2A,$93,$7C,$79,$6B
       .byte $42,$6C,$84,$53,$93,$16,$4C,$4C,$16,$4C,$28,$4E,$93,$61,$49,$22
       .byte $56,$71,$81,$41,$1E,$34,$93,$34,$59,$2B,$22,$3C,$80,$17,$68,$4C
       .byte $81,$4D,$93,$3C,$93,$1A,$93,$4C,$70,$5B,$1D,$93,$4C,$63,$28,$4C
       .byte $93,$1D,$93,$93,$93,$93,$5C,$93,$41,$54,$80,$93,$70,$70,$84,$4C
       .byte $93,$2E,$6A,$2E,$73,$6F,$42,$18,$93,$59,$11,$2E,$3D,$93,$2E,$3E
       .byte $93,$93,$2A,$16,$72,$32,$4C,$93,$5C,$93,$3C,$5E,$7C,$5E,$79,$2E
       .byte $93,$24,$4C,$70,$46,$59,$93,$76,$28,$12,$10,$12,$53,$22,$2E,$42
       .byte $93,$14,$32,$22,$56,$81,$89,$2A,$38,$12,$62,$3C,$12,$2E,$42,$3E
       .byte $93,$32,$5E,$49,$6D,$93,$78,$89,$32,$2C,$45,$2E,$35,$24,$6C,$59
       .byte $93,$32,$39,$3A,$21,$4D,$18,$19,$18,$93,$59,$22,$33,$6B,$3E,$4C
       .byte $93,$89,$26,$54,$2D,$39,$70,$31,$93,$93,$6E,$20,$6E,$21,$2E,$38
       .byte $93,$2E,$80,$52,$4A,$4D,$32,$66,$78,$93,$32,$78,$1E,$39,$18,$2E
       .byte $93,$32,$88,$2E,$2E,$6A,$26,$4D,$93,$72,$56,$24,$20,$60,$88,$2A
       .byte $93,$36,$6E,$21,$80,$4C,$93,$2E,$43,$58,$3F,$75,$15,$22,$28,$62
       .byte $93,$36,$21,$73,$3A,$93,$12,$31,$31,$93,$88,$21,$1E,$25,$2E,$1A
LF900: .byte $90,$90,$90,$90,$90,$90,$90,$50,$90,$68,$90,$90,$90,$50,$14,$24
       .byte $18,$50,$84,$90,$90,$51,$91,$80,$4C,$80,$50,$90,$90,$50,$84,$50
       .byte $60,$34,$70,$18,$68,$90,$90,$50,$18,$4C,$64,$80,$28,$1C,$50,$78
       .byte $40,$90,$90,$50,$68,$50,$68,$78,$50,$18,$68,$30,$39,$91,$91,$91
       .byte $90,$50,$80,$80,$80,$80,$80,$40,$18,$50,$80,$90,$90,$90,$90,$90
       .byte $90,$50,$80,$4C,$4C,$1C,$28,$84,$88,$88,$81,$91,$91,$91,$91,$91
       .byte $90,$50,$68,$84,$50,$2C,$84,$68,$88,$88,$68,$90,$90,$90,$90,$90
       .byte $93,$50,$1C,$90,$70,$50,$88,$80,$90,$68,$69,$91,$91,$91,$91,$91
       .byte $91,$50,$2C,$18,$28,$88,$88,$90,$50,$2D,$91,$91,$91,$91,$91,$91
       .byte $90,$51,$91,$50,$90,$50,$68,$84,$90,$88,$4C,$90,$90,$90,$90,$90
       .byte $90,$50,$68,$60,$20,$58,$80,$80,$80,$80,$51,$91,$91,$91,$91,$91
       .byte $90,$18,$90,$78,$68,$14,$64,$88,$88,$88,$78,$90,$90,$90,$90,$90
       .byte $90,$50,$28,$78,$88,$68,$4C,$81,$91,$80,$65,$91,$91,$91,$91,$91
       .byte $90,$50,$80,$7C,$50,$80,$90,$3C,$4C,$4C,$4C,$90,$90,$90,$90,$90
       .byte $90,$4C,$70,$5C,$24,$88,$4C,$68,$6C,$88,$79,$91,$91,$91,$91,$91
       .byte $90,$4C,$80,$88,$88,$88,$80,$70,$80,$80,$84,$90,$90,$90,$90,$90
LFA00: .byte $00,$C0,$00,$00,$E0,$C0,$00,$00,$00,$00,$00,$C0,$80,$00,$03,$80
       .byte $80,$00,$00,$C0,$00,$00,$00,$FF,$00,$00,$00,$00,$00,$00,$00,$C0
       .byte $FF,$00,$00,$00,$C0,$C0,$80,$80,$00,$FF,$F0,$F0,$FC,$E0,$E0,$C0
       .byte $00,$00,$80,$00,$FF,$00,$F8,$F8,$00,$00,$E0,$F0,$00,$00,$00,$00
       .byte $00,$00,$81,$F1,$FE,$FF,$FF,$00,$00,$FF,$00,$00,$00,$00,$00,$00
       .byte $00,$00,$00,$00,$FC,$01,$00,$CF,$FF,$FF,$00,$00,$00,$00,$00,$00
       .byte $80,$FF,$00,$00,$00,$9C,$00,$FF,$FF,$FF,$03,$00,$00,$00,$00,$00
       .byte $E0,$C0,$00,$00,$00,$FC,$F3,$00,$00,$00,$00,$00,$00,$00,$00,$00
       .byte $00,$00,$9C,$80,$F0,$C3,$03,$00,$00,$00,$00,$00,$00,$00,$00,$00
       .byte $00,$00,$00,$00,$00,$FF,$00,$00,$00,$FC,$03,$00,$00,$00,$00,$00
       .byte $00,$F8,$FC,$00,$00,$00,$00,$00,$00,$FF,$00,$00,$03,$00,$00,$00
       .byte $00,$00,$00,$FF,$00,$00,$FF,$FF,$FF,$FF,$00,$00,$00,$03,$00,$00
       .byte $00,$F0,$C3,$FF,$FF,$FF,$00,$00,$F0,$FF,$00,$00,$00,$00,$00,$00
       .byte $00,$00,$07,$00,$00,$00,$00,$FF,$FF,$00,$0E,$00,$00,$00,$00,$00
       .byte $00,$00,$E0,$F0,$FC,$C0,$FF,$FC,$FF,$FF,$1F,$00,$00,$00,$00,$00
       .byte $00,$00,$F3,$F3,$FF,$FF,$00,$FF,$00,$FF,$0F,$03,$00,$00,$00
LFAFF: .byte $00
LFB00: .byte $FF,$FF,$FF,$FC,$FF,$FF,$FF,$C0,$FF,$FC,$FF,$FF,$FF,$9F,$F1,$0F
       .byte $FF,$9F,$FF,$FF,$FF,$FF,$C0,$FF,$CF,$FF,$FC,$FF,$FF,$80,$FF,$E7
       .byte $FF,$FC,$CF,$FF,$FF,$FF,$FF,$CF,$FF,$FF,$C3,$00,$07,$FF,$F0,$FF
       .byte $F0,$FF,$FF,$FF,$FF,$FF,$F0,$FF,$CF,$FF,$00,$C0,$FC,$FE,$F0,$FF
       .byte $FF,$C3,$C0,$C0,$C0,$C0,$FF,$CF,$FF,$C0,$FF,$F0,$80,$FF,$C0,$FF
       .byte $FF,$CF,$FF,$E7,$E7,$F8,$87,$00,$00,$C0,$F0,$E0,$C0,$C0,$FC,$FF
       .byte $FF,$FF,$9F,$FF,$9E,$9F,$FF,$00,$00,$FF,$C0,$F0,$C0,$FF,$C0,$FF
       .byte $FF,$E7,$FF,$FC,$FF,$00,$C0,$FF,$FF,$FF,$C0,$00,$FF,$00,$C0,$FF
       .byte $FF,$9E,$0F,$FC,$03,$0F,$FF,$FF,$FE,$FF,$FF,$C0,$C0,$C0,$FF,$FF
       .byte $FF,$FF,$FF,$FF,$C3,$FF,$81,$FF,$C0,$FF,$80,$C0,$C0,$C0,$C0,$FF
       .byte $FF,$FF,$FF,$F3,$FF,$CF,$C0,$CF,$CF,$FF,$FC,$00,$00,$C0,$FF,$FF
       .byte $CF,$FF,$F0,$FF,$9F,$FF,$00,$00,$00,$F0,$C0,$C0,$E0,$C0,$F0,$FF
       .byte $FF,$00,$F0,$00,$FF,$FF,$CF,$FF,$C0,$FF,$C7,$E0,$E0,$E0,$C0,$F8
       .byte $FF,$CC,$E0,$FF,$CF,$FF,$F0,$FF,$FF,$9F,$FF,$E0,$C0,$E0,$FF,$FC
       .byte $FF,$FC,$FF,$01,$07,$FF,$FF,$FE,$00,$F0,$80,$E0,$C0,$F0,$E0,$FF
       .byte $FF,$C0,$00,$00,$00,$C0,$FC,$C0,$F0,$80,$80,$C0,$E0,$F0,$E0,$FF
LFC00: .byte $00,$00,$00,$00,$F0,$00,$00,$00,$00,$00,$00,$00,$00,$00,$FF,$FF
       .byte $00,$00,$00,$C0,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
       .byte $00,$FE,$00,$00,$00,$00,$00,$00,$00,$00,$F0,$00,$FC,$00,$00,$00
       .byte $00,$00,$00,$00,$1F,$00,$F8,$00,$00,$F0,$C0,$FF,$00,$FC,$00,$00
       .byte $00,$00,$FF,$FF,$FC,$F1,$01,$00,$00,$1F,$00,$00,$00,$F0,$FF,$00
       .byte $00,$00,$00,$00,$FC,$FF,$00,$7F,$3F,$0F,$FF,$00,$00,$C0,$00,$00
       .byte $00,$3F,$C0,$00,$1C,$00,$00,$3F,$C3,$3F,$C3,$00,$C0,$00,$00,$00
       .byte $00,$00,$00,$00,$00,$00,$FF,$00,$F8,$FC,$C0,$00,$C0,$00,$C0,$00
       .byte $00,$1C,$00,$00,$00,$FF,$FF,$00,$00,$00,$00,$00,$E0,$00,$00,$00
       .byte $00,$00,$00,$00,$00,$7F,$FF,$00,$00,$00,$03,$00,$E0,$00,$00,$00
       .byte $00,$00,$F0,$00,$00,$00,$F0,$00,$00,$7F,$FF,$00,$03,$FF,$00,$00
       .byte $00,$F0,$E0,$03,$C0,$E0,$F3,$7F,$7C,$7F,$C0,$FF,$00,$FF,$00,$C0
       .byte $00,$00,$FF,$00,$03,$03,$00,$00,$00,$7F,$00,$FF,$00,$00,$FF,$00
       .byte $00,$00,$FF,$00,$00,$00,$00,$00,$7F,$1C,$00,$FF,$FF,$00,$00,$C0
       .byte $00,$00,$E0,$00,$FC,$00,$7F,$C0,$3F,$CF,$1F,$FC,$FF,$00,$C0,$C0
       .byte $00,$00,$FF,$FF,$03,$7F,$FF,$FC,$FC,$FC,$FF,$FF,$C0,$F0,$C0
LFCFF: .byte $C0
LFD00: .byte $3F,$FF,$3F,$FF,$03,$FF,$3F,$00,$FC,$FF,$3F,$FF,$3F,$FF,$FF,$FF
       .byte $3F,$FF,$07,$FF,$3F,$FF,$00,$7F,$FF,$3F,$FF,$FF,$3F,$FC,$3F,$F3
       .byte $F9,$00,$FF,$FC,$3F,$FF,$3F,$FF,$7F,$F9,$FF,$FF,$FF,$3F,$FF,$CF
       .byte $00,$FF,$3F,$00,$3F,$FC,$FE,$3F,$FF,$FC,$FC,$F0,$00,$00,$C0,$FF
       .byte $3F,$FF,$00,$00,$00,$00,$C3,$FF,$3F,$00,$00,$00,$C0,$00,$00,$FF
       .byte $3F,$FF,$7F,$7F,$FF,$FF,$3F,$00,$00,$00,$00,$00,$C0,$00,$C0,$FF
       .byte $3F,$00,$FF,$3F,$7E,$FF,$00,$00,$00,$00,$E0,$C0,$00,$F0,$FF,$FF
       .byte $3F,$FF,$FF,$FF,$3F,$FF,$00,$FF,$00,$00,$E0,$E0,$00,$C0,$00,$00
       .byte $3F,$3E,$FF,$FF,$FF,$FF,$FF,$3F,$FE,$FF,$FF,$E0,$00,$C0,$F0,$00
       .byte $3F,$FF,$3F,$FF,$3F,$00,$FF,$FF,$FE,$7F,$00,$E0,$00,$C0,$0F,$C0
       .byte $3F,$FC,$03,$FF,$0F,$7F,$FF,$FF,$7F,$3F,$00,$C0,$F0,$00,$FF,$F8
       .byte $3F,$FF,$00,$00,$FF,$01,$00,$00,$00,$00,$00,$00,$C0,$00,$E0,$00
       .byte $3F,$FF,$00,$00,$00,$7F,$FF,$FF,$00,$01,$FF,$00,$C0,$C0,$00,$00
       .byte $3F,$FF,$FF,$3F,$FF,$FF,$E0,$7F,$7F,$7C,$FF,$00,$00,$C0,$00,$00
       .byte $7F,$FF,$07,$FF,$FF,$7F,$00,$00,$00,$00,$00,$00,$00,$C0,$00,$00
       .byte $7F,$FF,$00,$00,$00,$00,$00,$F0,$F0,$F0,$00,$00,$00,$00,$00,$00
LFE00: .byte $00,$08,$00,$34,$01,$98,$00,$00,$00,$4C,$5C,$08,$00,$00,$00,$00
       .byte $5C,$2C,$2C,$98,$00,$9A,$08,$02,$34,$32,$3A,$00,$02,$3C,$5E,$00
       .byte $4E,$01,$02,$4C,$3E,$08,$42,$5C,$3E,$40,$03,$64,$03,$64,$3E,$64
       .byte $0A,$98,$02,$02,$02,$3E,$02,$3E,$3E,$76,$02,$02,$9A,$10,$4C,$08
       .byte $02,$36,$02,$02,$02,$02,$02,$72,$2E,$02,$0A,$90,$4C,$90,$00,$98
       .byte $02,$6E,$3E,$6E,$03,$02,$5E,$02,$02,$02,$9A,$00,$4C,$02,$4C,$08
       .byte $02,$02,$22,$32,$02,$02,$02,$02,$02,$02,$08,$4E,$02,$4C,$4C,$98
       .byte $02,$36,$0A,$9A,$3A,$62,$02,$0A,$9A,$02,$9A,$4E,$1C,$4E,$02,$0A
       .byte $02,$22,$02,$4E,$4E,$02,$0A,$9A,$90,$9A,$4E,$4E,$02,$4E,$00,$08
       .byte $02,$9B,$0A,$0A,$9A,$02,$03,$0A,$9A,$5A,$08,$4E,$92,$4E,$36,$9A
       .byte $02,$5E,$03,$6E,$32,$2E,$02,$4E,$66,$02,$11,$4E,$45,$02,$00,$08
       .byte $02,$0A,$9A,$02,$22,$2A,$02,$02,$02,$02,$0A,$02,$4E,$8E,$4E,$9A
       .byte $02,$62,$02,$00,$02,$02,$66,$9A,$0B,$02,$9A,$10,$4E,$4C,$02,$08
       .byte $02,$62,$02,$62,$6A,$0A,$9A,$02,$02,$02,$0A,$88,$02,$4E,$02,$9A
       .byte $02,$5E,$03,$6A,$03,$5A,$02,$01,$02,$02,$98,$10,$02,$4E,$12,$0A
       .byte $02,$5E,$00,$02,$02,$02,$02,$02,$02,$02,$08,$8E,$8A,$8A,$02,$9A
LFF00: .byte $00,$02,$06,$0C,$14,$1C,$26,$32,$40,$50,$60,$70,$80,$90,$A0,$B0
       .byte $C0,$D0,$E0,$F0
LFF14: .byte $01,$05,$0B,$13,$1B,$25,$31,$3F,$4F,$5F,$6F,$7F,$8F,$9F,$AF,$BF
       .byte $CF,$DF,$EF,$FF
LFF28: .byte $01,$03,$05,$07,$07,$09,$0B,$0D,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F
       .byte $0F,$0F,$0F,$0F
LFF3C: .byte $42,$44
LFF3E: .byte $30,$30,$20,$20
LFF42: .byte $70,$B0,$70,$B0,$70,$70,$70,$B0,$70,$B0,$70,$B0,$70,$70,$B0,$70
       .byte $B0,$70,$B0,$70
LFF56: .byte $B0,$70,$B0,$70,$B0,$B0,$B0,$70,$B0,$70,$B0,$70,$B0,$B0,$70,$B0
       .byte $70,$B0,$70,$B0
LFF6A: .byte $20,$C0,$90
LFF6D: .byte $00,$04,$08,$0C,$10
LFF72: .byte $20,$00,$00,$00,$8B,$3D,$32,$32,$32,$20,$93,$93,$93,$93,$93,$93
       .byte $00,$00,$95,$01,$00,$00,$00,$06,$04
LFF8B: .byte $1A,$27
LFF8D: .byte $02,$0E
LFF8F: .byte $34,$40,$4C,$58
LFF93: .byte $26,$33,$40
LFF96: .byte $4D,$58,$65,$8A,$8B
LFF9B: .byte $7F,$92
LFF9D: .byte $E5,$CC,$B3,$9A,$81
LFFA2: .byte $81,$9A,$B3
LFFA5: .byte $00,$00,$00,$0A,$00
LFFAA: .byte $00,$01
LFFAC: .byte $93,$0F
LFFAE: .byte $06,$04
LFFB0: .byte $02,$01,$00,$00,$00,$00,$01,$02
LFFB8: .byte $0F,$1F,$3F,$7F,$FF,$7F,$3F,$1F
LFFC0: .byte $00,$00,$00,$00,$00,$01,$02,$03,$00,$00,$00,$00,$00,$00,$00,$00
       .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
       .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
LFFEC: BIT    LFFF8   ;4
       JSR    $DFEC   ;6
       LDX    #$FF    ;2
       TXS            ;2
       JMP    LF042   ;3
LFFF8: .byte $EA
LFFF9: .byte $EA,$EA,$EA,$00,$F0,$00,$F0
