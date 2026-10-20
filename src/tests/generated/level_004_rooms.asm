; Generated from New Level (level 4). Do not edit by hand.
LEVEL4_START_ROOM = 0
LEVEL4_WALL_COLOR = $52
LEVEL4_WALL_COLOR2 = $56
LEVEL4_MINER_ROOM = 5
LEVEL4_MINER_X = 147
LEVEL4_MINER_Y = 84

; Room shape index (C2 2026-10-20): ONE byte per room =
;   b5-0 SHAPE INDEX into LEVEL_ShapeTable (levels_index.asm)
;   b6   bottom-band flag
;   b7   owns-extras (reserved 0: the async stream is C5)
; The block address is the table entry, so the old 2-byte RoomRects
; word is gone. C4 (2026-10-20): the block is hot stream | PF | meta
; (no solid rect list) — TilePF0 = block + 1 + 5*hot_count.
LEVEL4_RoomShapes:
  .byte SHAPE_L4R1 ; room 0 (async)
  .byte SHAPE_L4R2 ; room 1 (async)
  .byte SHAPE_M5 ; room 2 (model 5)
  .byte SHAPE_M8 ; room 3 (model 8)
  .byte SHAPE_L4R5 ; room 4 (async)
  .byte SHAPE_L4R6 ; room 5 (async)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL4_RoomPositions:
  .byte $10 ; room 0 (1, 0)
  .byte $11 ; room 1 (1, 1)
  .byte $12 ; room 2 (1, 2)
  .byte $13 ; room 3 (1, 3)
  .byte $03 ; room 4 (0, 3)
  .byte $23 ; room 5 (2, 3)

; Per-room enemy count (C2 2026-10-20): ONE byte = count<<6 |
; extras index (0 = none; the record index is derived at room load).
LEVEL4_RoomCounts:
  .byte $00 ; room 0: 0 record(s)
  .byte $00 ; room 1: 0 record(s)
  .byte $00 ; room 2: 0 record(s)
  .byte $00 ; room 3: 0 record(s)
  .byte $00 ; room 4: 0 record(s)
  .byte $00 ; room 5: 0 record(s)

; Enemy data: 0 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL4_EnemyDataTable:
