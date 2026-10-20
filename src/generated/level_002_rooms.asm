; Generated from New Level (level 2). Do not edit by hand.
LEVEL2_START_ROOM = 0
LEVEL2_WALL_COLOR = $d2
LEVEL2_WALL_COLOR2 = $c4
LEVEL2_MINER_ROOM = 129
LEVEL2_MINER_X = 19
LEVEL2_MINER_Y = 84

; Room shape index (C2 2026-10-20): ONE byte per room =
;   b5-0 SHAPE INDEX into LEVEL_ShapeTable (levels_index.asm)
;   b6   bottom-band flag
;   b7   owns-extras (reserved 0: the async stream is C5)
; The block address is the table entry, so the old 2-byte RoomRects
; word is gone. TilePF0 is still derived as rects + 2 + 2*nrect.
LEVEL2_RoomShapes:
  .byte SHAPE_M2 ; room 0 (model 2)
  .byte SHAPE_M3 | $40 ; room 1 (model 3)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL2_RoomPositions:
  .byte $00 ; room 0 (0, 0)
  .byte $01 ; room 1 (0, 1)

; Per-room enemy count (C2 2026-10-20): ONE byte = count<<6 |
; extras index (0 = none; the record index is derived at room load).
LEVEL2_RoomCounts:
  .byte $00 ; room 0: 0 record(s)
  .byte $40 ; room 1: 1 record(s)

; Enemy data: 1 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL2_EnemyDataTable:
  .byte 7, 119, 96, -1
