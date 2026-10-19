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
  .word L1R1TilePF0, L1R1RoomRects ; room 0 (async)
  .word M1TilePF0, M1RoomRects ; room 1 (model 1)

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL1_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $0f, $ff ; room 1

; Enemy data: 2 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL1_EnemyDataTable:
  .byte 2, 8, 60, 1
  .byte 0, 127, 60, -1

; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.
LEVEL1_RoomEnemies:
  .byte <(LEVEL1_EnemyDataTable+0), >(LEVEL1_EnemyDataTable+0), 1, $00 ; room 0
  .byte <(LEVEL1_EnemyDataTable+4), >(LEVEL1_EnemyDataTable+4), 1, $00 ; room 1

; Generated from room 0 (model 0). Do not edit by hand.
L1R1RoomRects:
  .byte 3                  ; number of rectangles
  .byte $00, $11  ; packed (x<<2|y, w<<2|h)
  .byte $01, $09  ; packed (x<<2|y, w<<2|h)
  .byte $02, $49  ; packed (x<<2|y, w<<2|h)
  .byte 0              ; number of hot rectangles
L1R1TilePF0:
  .byte $f0, $30, $f0
L1R1TilePF1:
  .byte $00, $00, $ff
L1R1TilePF2:
  .byte $00, $00, $3f
L1R1MetaA:
  .byte $90                  ; (m1_col+1)<<4 | band mask
L1R1MetaB:
  .byte $00                  ; (ball_col+1), 0 = no ball
