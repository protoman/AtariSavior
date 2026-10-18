; Generated from New Level (level 3). Do not edit by hand.
LEVEL3_START_ROOM = 0
LEVEL3_WALL_COLOR = $92
LEVEL3_WALL_COLOR2 = $96
LEVEL3_START_X = 32
LEVEL3_START_Y = 24
LEVEL3_MINER_ROOM = 132
LEVEL3_MINER_X = 27
LEVEL3_MINER_Y = 84

; Room data: one (L3R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo. Rooms pointing at a model share that model's
; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).
LEVEL3_RoomDataTable:
  .word L3R1TilePF0, L3R1RoomRects ; room 0 (async)
  .word M4TilePF0, M4RoomRects ; room 1 (model 4)
  .word M5TilePF0, M5RoomRects ; room 2 (model 5)
  .word M6TilePF0, M6RoomRects ; room 3 (model 6)
  .word M7TilePF0, M7RoomRects ; room 4 (model 7)
  .word L3R6TilePF0, L3R6RoomRects ; room 5 (async)

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL3_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $02, $ff ; room 1
  .byte $13, $ff ; room 2
  .byte $24, $ff ; room 3
  .byte $35, $ff ; room 4
  .byte $4f, $ff ; room 5

; Enemy data: 5 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL3_EnemyDataTable:
  .byte 1, 127, 60, 1
  .byte 5, 27, 18, 1
  .byte 2, 103, 60, 1
  .byte 6, 135, 84, 1
  .byte 5, 27, 18, 1

; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.
LEVEL3_RoomEnemies:
  .byte <(LEVEL3_EnemyDataTable), >(LEVEL3_EnemyDataTable), 0, $00 ; room 0
  .byte <(LEVEL3_EnemyDataTable), >(LEVEL3_EnemyDataTable), 0, $00 ; room 1
  .byte <(LEVEL3_EnemyDataTable+0), >(LEVEL3_EnemyDataTable+0), 2, $00 ; room 2
  .byte <(LEVEL3_EnemyDataTable+8), >(LEVEL3_EnemyDataTable+8), 2, $00 ; room 3
  .byte <(LEVEL3_EnemyDataTable+16), >(LEVEL3_EnemyDataTable+16), 1, $00 ; room 4
  .byte <(LEVEL3_EnemyDataTable), >(LEVEL3_EnemyDataTable), 0, $00 ; room 5

; Generated from room 0 (model 0). Do not edit by hand.
L3R1RoomRects:
  .byte 3                  ; number of rectangles
  .byte $00, $11  ; packed (x<<2|y, w<<2|h)
  .byte $01, $09  ; packed (x<<2|y, w<<2|h)
  .byte $02, $49  ; packed (x<<2|y, w<<2|h)
  .byte 0              ; number of hot rectangles
L3R1TilePF0:
  .byte $f0, $30, $f0
L3R1TilePF1:
  .byte $00, $00, $ff
L3R1TilePF2:
  .byte $00, $00, $3f
L3R1MetaA:
  .byte $90                  ; (m1_col+1)<<4 | band mask
L3R1MetaB:
  .byte $00                  ; (ball_col+1), 0 = no ball

; Generated from room 5 (model 1). Do not edit by hand.
L3R6RoomRects:
  .byte 3                  ; number of rectangles
  .byte $00, $49  ; packed (x<<2|y, w<<2|h)
  .byte $01, $09  ; packed (x<<2|y, w<<2|h)
  .byte $02, $51  ; packed (x<<2|y, w<<2|h)
  .byte 0              ; number of hot rectangles
L3R6TilePF0:
  .byte $f0, $30, $f0
L3R6TilePF1:
  .byte $ff, $00, $ff
L3R6TilePF2:
  .byte $3f, $00, $ff
L3R6MetaA:
  .byte $29                  ; (m1_col+1)<<4 | band mask | $08 door | $01 right half
L3R6MetaB:
  .byte $00                  ; (ball_col+1), 0 = no ball
