; Generated from Level 1. Do not edit by hand.
LEVEL_START_ROOM = 0
LEVEL_WALL_COLOR = $2a

; Room data: one (TilePF0, RoomRowLo) word pair per room, indexed by RoomNo.
RoomDataTable:
  .word Room1TilePF0, Room1RoomRowLo ; room 0
  .word Room2TilePF0, Room2RoomRowLo ; room 1
  .word Room3TilePF0, Room3RoomRowLo ; room 2

; Room connections: up/down/left/right target room index per room ($ff = none).
RoomConnections:
  .byte ROOM_NONE, $01, ROOM_NONE, ROOM_NONE ; room 0
  .byte $00, $02, ROOM_NONE, ROOM_NONE ; room 1
  .byte $01, ROOM_NONE, ROOM_NONE, ROOM_NONE ; room 2
