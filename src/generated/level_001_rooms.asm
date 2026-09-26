; Generated from Level 1 (level 1). Do not edit by hand.
LEVEL1_START_ROOM = 0
LEVEL1_WALL_COLOR = $20
LEVEL1_WALL_COLOR2 = $22
LEVEL1_START_X = 32
LEVEL1_START_Y = 24
LEVEL1_MINER_ROOM = 129
LEVEL1_MINER_X = 27
LEVEL1_MINER_Y = 84

; Room data: one (L1R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo. Rooms pointing at a model share that model's
; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).
LEVEL1_RoomDataTable:
  .word M0TilePF0, M0RoomRects ; room 0 (model 0)
  .word M1TilePF0, M1RoomRects ; room 1 (model 1)

; Room connections: up/down/left/right target room index per room ($ff = none).
LEVEL1_RoomConnections:
  .byte ROOM_NONE, $01, ROOM_NONE, ROOM_NONE ; room 0
  .byte $00, ROOM_NONE, ROOM_NONE, ROOM_NONE ; room 1

; Enemy data: 3 enemy records across 2 rooms, 6 bytes each (type,x,y,range_min,range_max,dir).
LEVEL1_EnemyDataTable:
  .byte 4, 147, 60, 128, 152, -1
  .byte 0, 127, 60, 108, 132, -1
  .byte 5, 79, 30, 0, 0, 1

; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.
LEVEL1_RoomEnemies:
  .byte <(LEVEL1_EnemyDataTable+0), >(LEVEL1_EnemyDataTable+0), 1, $00 ; room 0
  .byte <(LEVEL1_EnemyDataTable+6), >(LEVEL1_EnemyDataTable+6), 2, $00 ; room 1
