; Generated from Level 1 (level 1). Do not edit by hand.
LEVEL1_START_ROOM = 0
LEVEL1_WALL_COLOR = $20
LEVEL1_WALL_COLOR2 = $22
LEVEL1_MINER_ROOM = 129
LEVEL1_MINER_X = 27
LEVEL1_MINER_Y = 84

; Room data: ONE word per room (the block's RoomRects label), indexed by RoomNo. TilePF0 is derived at room load as
; rects + 2 + 2*nrect (C3 2026-10-20: it always sits 2 bytes past the rect list in the same block, so the second word was redundant).
LEVEL1_RoomDataTable:
  .word L1R1RoomRects ; room 0 (async)
  .word M1RoomRects ; room 1 (model 1)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL1_RoomPositions:
  .byte $00 ; room 0 (0, 0)
  .byte $01 ; room 1 (0, 1)

; Per-room enemy records: ONE byte (count<<6 | first record index<<1 | bottom-band flag). The band COLOR is the global BAND_COLOR (one water
; color per game — the converter rejects a second one).
LEVEL1_RoomEnemies:
  .byte $40 ; room 0: 1 record(s) from 0
  .byte $42 ; room 1: 1 record(s) from 1

; Enemy data: 2 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL1_EnemyDataTable:
  .byte 6, 155, 84, -1
  .byte 0, 127, 60, -1
