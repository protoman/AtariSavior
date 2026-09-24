; Generated from level_001.json. Do not edit by hand.
L1_START_ROOM = 0
L1_START_X = 32
L1_START_Y = 24
L1_MINER_ROOM = 1
L1_MINER_X = 18
L1_MINER_Y = 84
L1_NUM_MODELS = 4
L1_NUM_ROOMS = 2

L1_M1RoomRects:
  .byte 3                  ; number of rectangles
  .byte 0, 0, 5, 4  ; x, y, width, height
  .byte 0, 4, 2, 8  ; x, y, width, height
  .byte 2, 8, 16, 4  ; x, y, width, height
L1_M1TilePF0:
  .byte $f0, $f0, $f0, $f0, $30, $30, $30, $30, $f0, $f0, $f0, $f0
L1_M1TilePF1:
  .byte $80, $80, $80, $80, $00, $00, $00, $00, $ff, $ff, $ff, $ff
L1_M1TilePF2:
  .byte $00, $00, $00, $00, $00, $00, $00, $00, $3f, $3f, $3f, $3f

L1_M2RoomRects:
  .byte 3                  ; number of rectangles
  .byte 0, 0, 18, 4  ; x, y, width, height
  .byte 0, 4, 3, 8  ; x, y, width, height
  .byte 3, 8, 17, 4  ; x, y, width, height
L1_M2TilePF0:
  .byte $f0, $f0, $f0, $f0, $70, $70, $70, $70, $f0, $f0, $f0, $f0
L1_M2TilePF1:
  .byte $ff, $ff, $ff, $ff, $00, $00, $00, $00, $ff, $ff, $ff, $ff
L1_M2TilePF2:
  .byte $3f, $3f, $3f, $3f, $00, $00, $00, $00, $ff, $ff, $ff, $ff

L1_M3RoomRects:
  .byte 4                  ; number of rectangles
  .byte 0, 0, 20, 1  ; x, y, width, height
  .byte 0, 1, 5, 3  ; x, y, width, height
  .byte 0, 4, 2, 8  ; x, y, width, height
  .byte 2, 8, 16, 4  ; x, y, width, height
L1_M3TilePF0:
  .byte $f0, $f0, $f0, $f0, $30, $30, $30, $30, $f0, $f0, $f0, $f0
L1_M3TilePF1:
  .byte $ff, $80, $80, $80, $00, $00, $00, $00, $ff, $ff, $ff, $ff
L1_M3TilePF2:
  .byte $ff, $00, $00, $00, $00, $00, $00, $00, $3f, $3f, $3f, $3f

L1_M4RoomRects:
  .byte 4                  ; number of rectangles
  .byte 0, 0, 18, 4  ; x, y, width, height
  .byte 0, 4, 1, 8  ; x, y, width, height
  .byte 1, 8, 7, 4  ; x, y, width, height
  .byte 9, 8, 11, 4  ; x, y, width, height
L1_M4TilePF0:
  .byte $f0, $f0, $f0, $f0, $10, $10, $10, $10, $f0, $f0, $f0, $f0
L1_M4TilePF1:
  .byte $ff, $ff, $ff, $ff, $00, $00, $00, $00, $f7, $f7, $f7, $f7
L1_M4TilePF2:
  .byte $3f, $3f, $3f, $3f, $00, $00, $00, $00, $ff, $ff, $ff, $ff

; Room data table: (PF0_ptr, Rects_ptr) per room, indexed by RoomNo.
L1_RoomDataTable:
  .word L1_M1TilePF0, L1_M1RoomRects ; room 0
  .word L1_M2TilePF0, L1_M2RoomRects ; room 1

L1_RoomConnections:
  .byte ROOM_NONE, $01, ROOM_NONE, ROOM_NONE ; room 0 (up, down, left, right)
  .byte $00, ROOM_NONE, ROOM_NONE, ROOM_NONE ; room 1 (up, down, left, right)

ROOM_NONE = $ff

