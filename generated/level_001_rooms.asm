; Generated from Level 1 (level 1). Do not edit by hand.
LEVEL1_START_ROOM = 0
LEVEL1_WALL_COLOR = $b0
LEVEL1_START_X = 64
LEVEL1_START_Y = 24
LEVEL1_MINER_ROOM = 2
LEVEL1_MINER_X = 12
LEVEL1_MINER_Y = 108

; Room data: one (L1R<n>TilePF0, ...RoomRowLo) word pair per room, indexed by RoomNo.
LEVEL1_RoomDataTable:
  .word L1R1TilePF0, L1R1RoomRowLo ; room 0
  .word L1R2TilePF0, L1R2RoomRowLo ; room 1
  .word L1R3TilePF0, L1R3RoomRowLo ; room 2

; Room connections: up/down/left/right target room index per room ($ff = none).
LEVEL1_RoomConnections:
  .byte ROOM_NONE, $01, ROOM_NONE, ROOM_NONE ; room 0
  .byte $00, $02, ROOM_NONE, ROOM_NONE ; room 1
  .byte $01, ROOM_NONE, ROOM_NONE, ROOM_NONE ; room 2

; Enemy data: 4 enemy records across 3 rooms, 6 bytes each (type,x,y,range_min,range_max,dir).
LEVEL1_EnemyDataTable:
  .byte 0, 123, 96, 104, 128, 1
  .byte 1, 131, 120, 112, 136, 1
  .byte 2, 19, 48, 0, 24, 1
  .byte 2, 83, 36, 64, 88, 1

; Per-room enemy records: ptr_lo, ptr_hi, count, pad.
LEVEL1_RoomEnemies:
  .byte <(LEVEL1_EnemyDataTable+0), >(LEVEL1_EnemyDataTable+0), 1, 0 ; room 0
  .byte <(LEVEL1_EnemyDataTable+6), >(LEVEL1_EnemyDataTable+6), 2, 0 ; room 1
  .byte <(LEVEL1_EnemyDataTable+18), >(LEVEL1_EnemyDataTable+18), 1, 0 ; room 2
