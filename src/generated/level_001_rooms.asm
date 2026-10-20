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

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL1_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $0f, $ff ; room 1

; Per-room enemy records: (count<<5 | first record index), bottom_color.
LEVEL1_RoomEnemies:
  .byte $20, $00 ; room 0: 1 record(s) from 0
  .byte $21, $00 ; room 1: 1 record(s) from 1

; Enemy data: 2 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL1_EnemyDataTable:
  .byte 2, 8, 60, 1
  .byte 0, 127, 60, -1
