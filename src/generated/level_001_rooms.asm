; Generated from Level 1 (level 1). Do not edit by hand.
LEVEL1_START_ROOM = 0
LEVEL1_WALL_COLOR = $20
LEVEL1_WALL_COLOR2 = $22
LEVEL1_START_X = 32
LEVEL1_START_Y = 24
LEVEL1_MINER_ROOM = 1
LEVEL1_MINER_X = 44
LEVEL1_MINER_Y = 72

; Room data: one (L1R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo.
LEVEL1_RoomDataTable:
  .word L1R1TilePF0, L1R1RoomRects ; room 0
  .word L1R2TilePF0, L1R2RoomRects ; room 1

; Room connections: up/down/left/right target room index per room ($ff = none).
LEVEL1_RoomConnections:
  .byte ROOM_NONE, $01, ROOM_NONE, ROOM_NONE ; room 0
  .byte $00, ROOM_NONE, ROOM_NONE, ROOM_NONE ; room 1

; Enemy data: 2 enemy records across 2 rooms, 6 bytes each (type,x,y,range_min,range_max,dir).
LEVEL1_EnemyDataTable:
  .byte 2, 8, 60, 0, 16, 1
  .byte 0, 127, 60, 108, 132, -1

; Per-room enemy records: ptr_lo, ptr_hi, count, pad.
LEVEL1_RoomEnemies:
  .byte <(LEVEL1_EnemyDataTable+0), >(LEVEL1_EnemyDataTable+0), 1, 0 ; room 0
  .byte <(LEVEL1_EnemyDataTable+6), >(LEVEL1_EnemyDataTable+6), 1, 0 ; room 1
