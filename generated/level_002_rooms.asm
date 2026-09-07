; Generated from New Level (level 2). Do not edit by hand.
LEVEL2_START_ROOM = 0
LEVEL2_WALL_COLOR = $22
LEVEL2_START_X = 28
LEVEL2_START_Y = 24
LEVEL2_MINER_ROOM = 1
LEVEL2_MINER_X = 104
LEVEL2_MINER_Y = 120

; Room data: one (L2R<n>TilePF0, ...RoomRowLo) word pair per room, indexed by RoomNo.
LEVEL2_RoomDataTable:
  .word L2R1TilePF0, L2R1RoomRowLo ; room 0
  .word L2R2TilePF0, L2R2RoomRowLo ; room 1

; Room connections: up/down/left/right target room index per room ($ff = none).
LEVEL2_RoomConnections:
  .byte ROOM_NONE, $01, ROOM_NONE, ROOM_NONE ; room 0
  .byte $00, ROOM_NONE, ROOM_NONE, ROOM_NONE ; room 1
