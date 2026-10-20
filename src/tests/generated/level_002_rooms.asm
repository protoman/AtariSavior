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

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL2_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $0f, $ff ; room 1

; Per-room enemy records: ONE byte (count<<6 | first record index<<1 | bottom-band flag). The band COLOR is the global BAND_COLOR (one water
; color per game — the converter rejects a second one).
LEVEL2_RoomEnemies:
  .byte $00 ; room 0: 0 record(s) from 0
  .byte $41 ; room 1: 1 record(s) from 0, bottom band

; Enemy data: 1 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL2_EnemyDataTable:
  .byte 3, 71, 132, 1
