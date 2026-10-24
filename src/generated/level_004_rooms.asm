; Generated from Level 4 (level 4). Do not edit by hand.
LEVEL4_START_ROOM = 0
LEVEL4_WALL_COLOR = $16
LEVEL4_WALL_COLOR2 = $18
LEVEL4_MINER_ROOM = 131
LEVEL4_MINER_X = 39
LEVEL4_MINER_Y = 96

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
LEVEL4_RoomShapes:
  .byte SHAPE_M3 ; room 0 (model 3)
  .byte SHAPE_M21 ; room 1 (model 21)
  .byte SHAPE_M17 ; room 2 (model 17)
  .byte SHAPE_M5 | $40 ; room 3 (model 5)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL4_RoomPositions:
  .byte $00 ; room 0 (0, 0)
  .byte $01 ; room 1 (0, 1)
  .byte $02 ; room 2 (0, 2)
  .byte $03 ; room 3 (0, 3)

; Per-room enemy count (C2 2026-10-20): ONE byte = count<<6 |
; extras ordinal (C5: 1-based index into LEVELn_AsyncExtras, 0 =
; none; the enemy record index is derived at room load).
LEVEL4_RoomCounts:
  .byte $00 ; room 0: 0 record(s)
  .byte $40 ; room 1: 1 record(s)
  .byte $40 ; room 2: 1 record(s)
  .byte $40 ; room 3: 1 record(s)

; Enemy data: 3 enemy records across 4 rooms, 3 bytes each (type|dir, x, y).
LEVEL4_EnemyDataTable:
  .byte $01, 71, 12
  .byte $05, 15, 48
  .byte $07, 55, 120
