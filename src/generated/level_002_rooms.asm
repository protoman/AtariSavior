; Generated from New Level (level 2). Do not edit by hand.
LEVEL2_START_ROOM = 0
LEVEL2_WALL_COLOR = $d2
LEVEL2_WALL_COLOR2 = $c4
LEVEL2_START_X = 32
LEVEL2_START_Y = 24
LEVEL2_MINER_ROOM = 129
LEVEL2_MINER_X = 19
LEVEL2_MINER_Y = 84

; Room data: one (L2R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo. Rooms pointing at a model share that model's
; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).
LEVEL2_RoomDataTable:
  .word M2TilePF0, M2RoomRects ; room 0 (model 2)
  .word M3TilePF0, M3RoomRects ; room 1 (model 3)

; Room connections: up/down/left/right target room index per room ($ff = none).
LEVEL2_RoomConnections:
  .byte ROOM_NONE, $01, ROOM_NONE, ROOM_NONE ; room 0
  .byte $00, ROOM_NONE, ROOM_NONE, ROOM_NONE ; room 1

; Enemy data: 1 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL2_EnemyDataTable:
  .byte 3, 71, 132, 1

; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.
LEVEL2_RoomEnemies:
  .byte <(LEVEL2_EnemyDataTable), >(LEVEL2_EnemyDataTable), 0, $00 ; room 0
  .byte <(LEVEL2_EnemyDataTable+0), >(LEVEL2_EnemyDataTable+0), 1, $80 ; room 1
