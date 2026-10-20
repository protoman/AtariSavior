; Generated from New Level (level 3). Do not edit by hand.
LEVEL3_START_ROOM = 0
LEVEL3_WALL_COLOR = $92
LEVEL3_WALL_COLOR2 = $96
LEVEL3_MINER_ROOM = 133
LEVEL3_MINER_X = 23
LEVEL3_MINER_Y = 84

; Room shape index (C2 2026-10-20): ONE byte per room =
;   b5-0 SHAPE INDEX into LEVEL_ShapeTable (levels_index.asm)
;   b6   bottom-band flag
;   b7   owns-extras (C5): the room has a record in the level's
;        AsyncExtras stream (selected by the counts byte's b5-0)
; C5 (2026-10-20): an async room points at its SHARED MODEL shape;
; the patches/features/meta come from the extras record, so there are
; no per-room blocks any more. A room without a model is rejected
; (the shape must be shared). C4: block = hot stream | PF triple —
; TilePF0 = block + 1 + 5*hot_count.
LEVEL3_RoomShapes:
  .byte SHAPE_M0 | $80 ; room 0 (async extras)
  .byte SHAPE_M4 | $80 ; room 1 (async extras)
  .byte SHAPE_M5 ; room 2 (model 5)
  .byte SHAPE_M6 ; room 3 (model 6)
  .byte SHAPE_M7 ; room 4 (model 7)
  .byte SHAPE_M1 ; room 5 (model 1)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL3_RoomPositions:
  .byte $00 ; room 0 (0, 0)
  .byte $01 ; room 1 (0, 1)
  .byte $02 ; room 2 (0, 2)
  .byte $03 ; room 3 (0, 3)
  .byte $04 ; room 4 (0, 4)
  .byte $05 ; room 5 (0, 5)

; Per-room enemy count (C2 2026-10-20): ONE byte = count<<6 |
; extras ordinal (C5: 1-based index into LEVELn_AsyncExtras, 0 =
; none; the enemy record index is derived at room load).
LEVEL3_RoomCounts:
  .byte $01 ; room 0: 0 record(s), extras 1
  .byte $02 ; room 1: 0 record(s), extras 2
  .byte $80 ; room 2: 2 record(s)
  .byte $80 ; room 3: 2 record(s)
  .byte $80 ; room 4: 2 record(s)
  .byte $00 ; room 5: 0 record(s)

; Enemy data: 6 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL3_EnemyDataTable:
  .byte 1, 127, 60, 1
  .byte 5, 27, 18, 1
  .byte 0, 23, 108, 1
  .byte 2, 103, 60, 1
  .byte 4, 39, 60, 1
  .byte 5, 27, 18, 1
