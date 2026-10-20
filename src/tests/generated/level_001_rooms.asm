; Generated from Level 1 (level 1). Do not edit by hand.
LEVEL1_START_ROOM = 0
LEVEL1_WALL_COLOR = $20
LEVEL1_WALL_COLOR2 = $22
LEVEL1_MINER_ROOM = 129
LEVEL1_MINER_X = 27
LEVEL1_MINER_Y = 84

; Room shape index (C2 2026-10-20): ONE byte per room =
;   b5-0 SHAPE INDEX into LEVEL_ShapeTable (levels_index.asm)
;   b6   bottom-band flag
;   b7   owns-extras (reserved 0: the async stream is C5)
; The block address is the table entry, so the old 2-byte RoomRects
; word is gone. C4 (2026-10-20): the block is hot stream | PF | meta
; (no solid rect list) — TilePF0 = block + 1 + 5*hot_count.
LEVEL1_RoomShapes:
  .byte SHAPE_L1R1 ; room 0 (async)
  .byte SHAPE_M1 ; room 1 (model 1)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL1_RoomPositions:
  .byte $00 ; room 0 (0, 0)
  .byte $01 ; room 1 (0, 1)

; Per-room enemy count (C2 2026-10-20): ONE byte = count<<6 |
; extras index (0 = none; the record index is derived at room load).
LEVEL1_RoomCounts:
  .byte $40 ; room 0: 1 record(s)
  .byte $40 ; room 1: 1 record(s)

; Enemy data: 2 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL1_EnemyDataTable:
  .byte 6, 155, 84, -1
  .byte 0, 127, 60, -1
