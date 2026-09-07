; Generated from Level 1 (level 1). Do not edit by hand.
LEVEL1_START_ROOM = 0
LEVEL1_WALL_COLOR = $b0
LEVEL1_START_X = 64
LEVEL1_START_Y = 24
LEVEL1_MINER_ROOM = 2
LEVEL1_MINER_X = 20
LEVEL1_MINER_Y = 156

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
