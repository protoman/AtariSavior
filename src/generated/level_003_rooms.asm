; Generated from New Level (level 3). Do not edit by hand.
LEVEL3_START_ROOM = 0
LEVEL3_WALL_COLOR = $92
LEVEL3_WALL_COLOR2 = $96
LEVEL3_START_X = 32
LEVEL3_START_Y = 24
LEVEL3_MINER_ROOM = 133
LEVEL3_MINER_X = 23
LEVEL3_MINER_Y = 84

; Room data: one (L3R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo. Rooms pointing at a model share that model's
; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).
LEVEL3_RoomDataTable:
  .word M0TilePF0, M0RoomRects ; room 0 (model 0)
  .word M4TilePF0, M4RoomRects ; room 1 (model 4)
  .word M5TilePF0, M5RoomRects ; room 2 (model 5)
  .word M6TilePF0, M6RoomRects ; room 3 (model 6)
  .word M7TilePF0, M7RoomRects ; room 4 (model 7)
  .word M1TilePF0, M1RoomRects ; room 5 (model 1)

; Room connections: up/down/left/right target room index per room ($ff = none).
LEVEL3_RoomConnections:
  .byte ROOM_NONE, $01, ROOM_NONE, ROOM_NONE ; room 0
  .byte $00, $02, ROOM_NONE, ROOM_NONE ; room 1
  .byte $01, $03, ROOM_NONE, ROOM_NONE ; room 2
  .byte $02, $04, ROOM_NONE, ROOM_NONE ; room 3
  .byte $03, $05, ROOM_NONE, ROOM_NONE ; room 4
  .byte $04, ROOM_NONE, ROOM_NONE, ROOM_NONE ; room 5

; Enemy data: 8 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL3_EnemyDataTable:
  .byte 0, 135, 48, -1
  .byte 5, 91, 18, 1
  .byte 1, 127, 60, 1
  .byte 5, 27, 18, 1
  .byte 0, 23, 108, 1
  .byte 2, 103, 60, 1
  .byte 4, 39, 60, 1
  .byte 5, 27, 18, 1

; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.
LEVEL3_RoomEnemies:
  .byte <(LEVEL3_EnemyDataTable), >(LEVEL3_EnemyDataTable), 0, $00 ; room 0
  .byte <(LEVEL3_EnemyDataTable+0), >(LEVEL3_EnemyDataTable+0), 2, $00 ; room 1
  .byte <(LEVEL3_EnemyDataTable+8), >(LEVEL3_EnemyDataTable+8), 2, $00 ; room 2
  .byte <(LEVEL3_EnemyDataTable+16), >(LEVEL3_EnemyDataTable+16), 2, $00 ; room 3
  .byte <(LEVEL3_EnemyDataTable+24), >(LEVEL3_EnemyDataTable+24), 2, $00 ; room 4
  .byte <(LEVEL3_EnemyDataTable), >(LEVEL3_EnemyDataTable), 0, $00 ; room 5
