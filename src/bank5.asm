; ==============================================================================
; Bank 5 - ROOM BANK B (docs/agents/banks.md layout v3). The room-bank code of bank2, assembled again with
; ROOMS_B = 1: byte-identical code at the same addresses, the data windows hold the levels past LEVEL_SPLIT
; (generated/spill_B_*.asm), and the router stub zones hold `jmp body` where A's stubs `sta BK_ROOMS_B`.
; (Until 2026-11-14 the transition frame lived here; it moved to bank4, trans.inc.)
; ==============================================================================
ROOMS_B = 1
    include "bank2.asm"
