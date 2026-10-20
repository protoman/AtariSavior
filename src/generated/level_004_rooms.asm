; Generated from New Level (level 4). Do not edit by hand.
LEVEL4_START_ROOM = 0
LEVEL4_WALL_COLOR = $52
LEVEL4_WALL_COLOR2 = $56
LEVEL4_MINER_ROOM = 5
LEVEL4_MINER_X = 147
LEVEL4_MINER_Y = 84

; Room data: one (L4R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo. Rooms pointing at a model share that model's
; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).
LEVEL4_RoomDataTable:
  .word L1R1TilePF0, L1R1RoomRects ; room 0 (async) [shared with L1R1]
  .word L4R2TilePF0, L4R2RoomRects ; room 1 (async)
  .word M5TilePF0, M5RoomRects ; room 2 (model 5)
  .word M8TilePF0, M8RoomRects ; room 3 (model 8)
  .word L4R5TilePF0, L4R5RoomRects ; room 4 (async)
  .word L4R6TilePF0, L4R6RoomRects ; room 5 (async)

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL4_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $02, $ff ; room 1
  .byte $13, $ff ; room 2
  .byte $2f, $45 ; room 3
  .byte $ff, $f3 ; room 4
  .byte $ff, $3f ; room 5

; Enemy data: 0 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL4_EnemyDataTable:

; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.
LEVEL4_RoomEnemies:
  .byte <(LEVEL4_EnemyDataTable), >(LEVEL4_EnemyDataTable), 0, $00 ; room 0
  .byte <(LEVEL4_EnemyDataTable), >(LEVEL4_EnemyDataTable), 0, $00 ; room 1
  .byte <(LEVEL4_EnemyDataTable), >(LEVEL4_EnemyDataTable), 0, $00 ; room 2
  .byte <(LEVEL4_EnemyDataTable), >(LEVEL4_EnemyDataTable), 0, $00 ; room 3
  .byte <(LEVEL4_EnemyDataTable), >(LEVEL4_EnemyDataTable), 0, $00 ; room 4
  .byte <(LEVEL4_EnemyDataTable), >(LEVEL4_EnemyDataTable), 0, $00 ; room 5
