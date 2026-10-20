; Generated from New Level (level 2). Do not edit by hand.
LEVEL2_START_ROOM = 0
LEVEL2_WALL_COLOR = $d2
LEVEL2_WALL_COLOR2 = $c4
LEVEL2_MINER_ROOM = 129
LEVEL2_MINER_X = 19
LEVEL2_MINER_Y = 84

; Room data: ONE word per room (the block's RoomRects label), indexed by RoomNo. TilePF0 is derived at room load as
; rects + 2 + 2*nrect (C3 2026-10-20: it always sits 2 bytes past the rect list in the same block, so the second word was redundant).
LEVEL2_RoomDataTable:
  .word M2RoomRects ; room 0 (model 2)
  .word M3RoomRects ; room 1 (model 3)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL2_RoomPositions:
  .byte $00 ; room 0 (0, 0)
  .byte $01 ; room 1 (0, 1)

; Per-room enemy records: ONE byte (count<<6 | first record index<<1 | bottom-band flag). The band COLOR is the global BAND_COLOR (one water
; color per game — the converter rejects a second one).
LEVEL2_RoomEnemies:
  .byte $00 ; room 0: 0 record(s) from 0
  .byte $41 ; room 1: 1 record(s) from 0, bottom band

; Enemy data: 1 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL2_EnemyDataTable:
  .byte 3, 71, 132, 1
