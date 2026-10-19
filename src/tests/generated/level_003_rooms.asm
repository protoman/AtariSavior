; Generated from New Level (level 3). Do not edit by hand.
LEVEL3_START_ROOM = 0
LEVEL3_WALL_COLOR = $92
LEVEL3_WALL_COLOR2 = $96
LEVEL3_MINER_ROOM = 133
LEVEL3_MINER_X = 23
LEVEL3_MINER_Y = 84

; Room data: one (L3R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo. Rooms pointing at a model share that model's
; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).
LEVEL3_RoomDataTable:
  .word L3R1TilePF0, L3R1RoomRects ; room 0 (async)
  .word L3R2TilePF0, L3R2RoomRects ; room 1 (async)
  .word M5TilePF0, M5RoomRects ; room 2 (model 5)
  .word M6TilePF0, M6RoomRects ; room 3 (model 6)
  .word M7TilePF0, M7RoomRects ; room 4 (model 7)
  .word M1TilePF0, M1RoomRects ; room 5 (model 1)

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL3_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $02, $ff ; room 1
  .byte $13, $ff ; room 2
  .byte $24, $ff ; room 3
  .byte $35, $ff ; room 4
  .byte $4f, $ff ; room 5

; Enemy data: 6 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL3_EnemyDataTable:
  .byte 1, 127, 60, 1
  .byte 5, 27, 18, 1
  .byte 0, 23, 108, 1
  .byte 2, 103, 60, 1
  .byte 4, 39, 60, 1
  .byte 5, 27, 18, 1

; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.
LEVEL3_RoomEnemies:
  .byte <(LEVEL3_EnemyDataTable), >(LEVEL3_EnemyDataTable), 0, $00 ; room 0
  .byte <(LEVEL3_EnemyDataTable), >(LEVEL3_EnemyDataTable), 0, $00 ; room 1
  .byte <(LEVEL3_EnemyDataTable+0), >(LEVEL3_EnemyDataTable+0), 2, $00 ; room 2
  .byte <(LEVEL3_EnemyDataTable+8), >(LEVEL3_EnemyDataTable+8), 2, $00 ; room 3
  .byte <(LEVEL3_EnemyDataTable+16), >(LEVEL3_EnemyDataTable+16), 2, $00 ; room 4
  .byte <(LEVEL3_EnemyDataTable), >(LEVEL3_EnemyDataTable), 0, $00 ; room 5
