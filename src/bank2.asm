    processor 6502
; ==============================================================================
; Bank2 stub — selects bank0, jumps to GameStart
; ==============================================================================
    seg code
    org $F000

FetchPtr = $E0                   ; must match kernel.asm (operand baked in)

    ; --- 5-byte stub ---
    lda #0
    sta $1FF6                       ; select bank0
    jmp $F005                       ; GameStart in bank0

    ; --- E4 moth body (bank2 free space $F008-$F9D8) -------------------------
    ; Entered from bank0 via the $FEF0 entry tramp (sta $1FF8 lands on the
    ; jmp below at $FEF3). Exits via `jmp MothExitPad` ($FC49): bank2 runs
    ; sta $1FF6, bank0 serves jmp UE_Next. Rules:
    ;   - NEVER jsr FoldIndirect or any bank0 routine (a fold from inside
    ;     bank2 would switch away mid-routine = frozen player).
    ;   - Enemy records ARE here (org $F9D9) — read directly, no fold needed.
    ;   - Keep the whole routine inline (no jsr): tramps are tail jmps so
    ;     the stack depth equals the UE body (+0 vs the $F8 guard).
    ;   - ZP (rect cache, EnemyRam*, EnemyDataLo/Hi) is RAM: bank-independent.
    org $F100
MothRoutine:
    jmp MothExitPad                 ; Step-1 stub: exit immediately (no motion)

    ; --- Level data (frozen addresses — pointer values must match bank0's
    ;     original layout, level_bank_plan P2.1: $F9D9-$FB1E = 326B) ---
    org $F9D9
    include "generated/levels_data.asm"
    include "generated/levels.asm"

; ------------------------------------------------------------------------------
; E4 moth exit tramp ($FC49-$FC4B) — byte-identical slice with kernel.asm's
; MothExitPad (guard: verify_build check_moth_tramp). bank2 executes
; `sta $1FF6`; the fetch at $FC4C comes from bank0 = `jmp UE_Next`
; (bank0's own label). This file's bytes from $FC4C never run.
; Pinned at $FC49 (NOT $FFF2): $FFF6-$FFF9 are F6 hotspot mirrors — a peek
; of those addresses calls checkSwitchBank in Stella and flips banks
; mid-instruction (see kernel.asm MothExitPad comment).
; ------------------------------------------------------------------------------
    .ds $FC49 - *, 0
MothExitPad:
    sta $1FF6

; ------------------------------------------------------------------------------
; FoldIndirect — byte-identical copy of kernel.asm's block (same $FEF6
; address). bank0 executes bytes 1-3 (`sta $1FF8`, absolute — P3.1 deviation,
; see kernel.asm) then fetches bytes 4-9
; here (data bank active); `sta $1FF6` switches back, rts fetched from bank0.
; Guard: verify_build compares bank0/bank2 regions byte-for-byte.
; ------------------------------------------------------------------------------
; ------------------------------------------------------------------------------
; E4 moth entry tramp — byte-identical with kernel.asm's $FEF0 copy
; (guard: verify_build check_moth_tramp). bank2's `sta $1FF8` half never
; runs (entry always arrives from bank0); the `jmp MothRoutine` half at
; $FEF3 runs after bank0's switch. Assembles to the same 6 bytes as
; kernel's `sta $1FF8 / jmp $F100` — operand drift fails the guard.
; ------------------------------------------------------------------------------
    .ds $FEF0 - *, 0
UE_MothTramp:
    sta $1FF8
    jmp MothRoutine
    .ds $FEF6 - *, 0
FoldIndirect:
    sta $1FF8
    lda (FetchPtr),Y
    sta $1FF6
    rts

    ; Pad to vectors at $FFFA ($FFF2-$FFF9 = fill — never code: $FFF6-$FFF9
    ; are F6 hotspot mirrors on peek, see MothExitPad at $FC49)
    .ds $FFFA - *, 0

    ; Interrupt vectors
    .word $F000                     ; NMI vector
    .word $F000                     ; RESET vector
    .word $F000                     ; IRQ vector
