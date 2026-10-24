; Generated from Level 2 (level 2). Do not edit by hand.
LEVEL2_START_ROOM = 0
LEVEL2_WALL_COLOR = $a4
LEVEL2_WALL_COLOR2 = $a8
LEVEL2_MINER_ROOM = 129
LEVEL2_MINER_X = 39
LEVEL2_MINER_Y = 96

; Room shape index (C2 2026-10-20): ONE byte per room =
;   b5-0 SHAPE INDEX into LEVEL_ShapeTable (levels_index.asm)
;   b6   bottom-band flag
;   b7   owns-extras (C5): the room has a record in the level's
;        AsyncExtras stream (selected by the counts byte's b5-0)
; C5 (2026-10-20): an async room points at its SHARED MODEL shape;
; the patches/features/meta come from the extras record, so there are
; no per-room blocks any more. A room without a model is rejected
; (the shape must be shared). C11 (2026-10-21): block = 3 row-pool
; indices — the hot count/stream is gone (hot derives from PF row 1).
LEVEL2_RoomShapes:
  .byte SHAPE_M3 ; room 0 (model 3)
  .byte SHAPE_M0 ; room 1 (model 0)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL2_RoomPositions:
  .byte $00 ; room 0 (0, 0)
  .byte $01 ; room 1 (0, 1)

; Per-room enemy count (C2 2026-10-20): ONE byte = count<<6 |
; extras ordinal (C5: 1-based index into LEVELn_AsyncExtras, 0 =
; none; the enemy record index is derived at room load).
LEVEL2_RoomCounts:
  .byte $00 ; room 0: 0 record(s)
  .byte $40 ; room 1: 1 record(s)

; Enemy data: 1 enemy records across 2 rooms, 3 bytes each (type|dir, x, y).
LEVEL2_EnemyDataTable:
  .byte $01, 71, 60
