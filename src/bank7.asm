    processor 6502
    seg code
    org $F000
; ==============================================================================
; Bank7 — POWER-UP BANK for F4 (32K, 8 banks)
; ==============================================================================
; F4 reads the reset vector from the LAST bank, so the entry stub lives here:
; EXACTLY five bytes — `lda #0 / sta $1FF4` — because after that write the next
; fetch at $F005 comes from bank0, whose pad is byte-identical there
; ($F005: jmp GameStart). Anything longer would land mid-instruction in bank0.
; Guard: tools/verify_build.py check_boot_banks.
; Hotspot for this bank: $1FFB.
; ==============================================================================
    lda #0
    sta BK_GENERAL                       ; select bank0 — the fetch at $F005 is its

    include "colors.inc"
    include "banks.inc"             ; BK_* bank selectors by role (docs/agents/banks.md)
    include "generated/bank6_equs.inc"
    include "generated/cave_zp.inc"
    include "generated/cave_luts.inc"
CaveFrameLo:    .byte <PlayerSpriteA,<PlayerSpriteB,<PlayerWalkA,<PlayerWalkB

; ---- the cave kernel's PROLOGUE (bank6 has no room for it) ------------------------------
; Entered from bank6: `sta $1FFB` at Kernel6Entry, then the byte at +3 is the jmp below.
; Leaves with `sta $1FFA` at Kernel6Entry+6 (bank6 continues at +9, `Kernel6Back`).
Kernel6Entry = Kernel6Pad + 3
    org Kernel6Entry + 3
    jmp Prologue7
    org Kernel6Entry + 6
    sta BK_CAVE
    org $F100
Prologue7:
    include "bank6_prologue.inc"
    jmp Kernel6Entry + 6


; ---- the SHAPE STEP of the room load (moved from bank3, 2026-11-10) ------------------
; bank3 B3RoomBlocks (at $F453) does `sta $1FFB`; the next fetch (+3) is the jmp below.
; ShapeStep7 expands the room's shape block into the PF buffers and stages the hot flag in
; RoomMetaB; `sta $1FF7` at +6 returns to bank3 (B3Meta, +9).
FetchPtr = $E5
RoomPF0Lo = $99
RoomMetaB = $9A
PF0Buf = $C3
PF1Buf = $C7
PF2Buf = $CB
TILE_ROWS = 4
    org $F453 + 3
    jmp ShapeStep7
    org $F453 + 6
    sta BK_EXTRAS
    org $F460
ShapeStep7:
    lda RoomPF0Lo
    and #$7F                        ; shape index, 7 bits (128 shapes)
    asl                             ; *2: LEVEL_ShapeTable is a word table
    tax
    lda LEVEL_ShapeTable,X          ; block address = the table entry
    sta FetchPtr
    lda LEVEL_ShapeTable+1,X
    sta FetchPtr+1
    ldy #TILE_ROWS-1
.sp:
    lda (FetchPtr),Y                ; row index for this band (b7 = band 1's hot flag)
    and #$7F
    tax
    lda RowPoolPF0,X
    sta PF0Buf,Y
    lda RowPoolPF1,X
    sta PF1Buf,Y
    lda RowPoolPF2,X
    sta PF2Buf,Y
    dey
    bpl .sp
    ldy #1
    lda (FetchPtr),Y                ; band-1 index | hot b7
    and #$80
    lsr                             ; $80 -> $40 (MetaB b6)
    sta RoomMetaB
    jmp $F453 + 6                   ; sta $1FF7 -> bank3 B3Meta

; ---- DATA WINDOW: shape blocks + row pool + shape address table ----------------------
; (models_data.asm via generated/spill_bank3_shapes.asm; convert_level.py capacity-checks
; it as _BANK3_SHAPES_SLOT, which is now bank7's.)
    .ds $F4C0 - *, 0
    include "generated/spill_bank3_shapes.asm"

    .ds $FFFA - *, 0
    .word $F000                     ; NMI (never used: sei)
    .word $F000                     ; RESET -> this bank's stub
    .word $F000                     ; IRQ (never used)
