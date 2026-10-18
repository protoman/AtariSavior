; Generated from New Level (level 4). Do not edit by hand.
LEVEL4_START_ROOM = 0
LEVEL4_WALL_COLOR = $52
LEVEL4_WALL_COLOR2 = $56
LEVEL4_START_X = 32
LEVEL4_START_Y = 24
LEVEL4_MINER_ROOM = 5
LEVEL4_MINER_X = 147
LEVEL4_MINER_Y = 84

; Room data: one (L4R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo. Rooms pointing at a model share that model's
; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).
LEVEL4_RoomDataTable:
  .word L4R1TilePF0, L4R1RoomRects ; room 0 (async)
  .word M4TilePF0, M4RoomRects ; room 1 (model 4)
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

; Generated from room 0 (model 0). Do not edit by hand.
L4R1RoomRects:
  .byte 3                  ; number of rectangles
  .byte $00, $11  ; packed (x<<2|y, w<<2|h)
  .byte $01, $09  ; packed (x<<2|y, w<<2|h)
  .byte $02, $49  ; packed (x<<2|y, w<<2|h)
  .byte 0              ; number of hot rectangles
L4R1TilePF0:
  .byte $f0, $30, $f0
L4R1TilePF1:
  .byte $00, $00, $ff
L4R1TilePF2:
  .byte $00, $00, $3f
L4R1MetaA:
  .byte $90                  ; (m1_col+1)<<4 | band mask
L4R1MetaB:
  .byte $00                  ; (ball_col+1), 0 = no ball

; Generated from room 4 (model 11). Do not edit by hand.
L4R5RoomRects:
  .byte 2                  ; number of rectangles
  .byte $00, $51  ; packed (x<<2|y, w<<2|h)
  .byte $02, $51  ; packed (x<<2|y, w<<2|h)
  .byte 0              ; number of hot rectangles
L4R5TilePF0:
  .byte $f0, $00, $f0
L4R5TilePF1:
  .byte $ff, $00, $ff
L4R5TilePF2:
  .byte $ff, $00, $ff
L4R5MetaA:
  .byte $10                  ; (m1_col+1)<<4 | band mask
L4R5MetaB:
  .byte $00                  ; (ball_col+1), 0 = no ball

; Generated from room 5 (model 10). Do not edit by hand.
L4R6RoomRects:
  .byte 2                  ; number of rectangles
  .byte $00, $51  ; packed (x<<2|y, w<<2|h)
  .byte $02, $51  ; packed (x<<2|y, w<<2|h)
  .byte 0              ; number of hot rectangles
L4R6TilePF0:
  .byte $f0, $00, $f0
L4R6TilePF1:
  .byte $ff, $00, $ff
L4R6TilePF2:
  .byte $ff, $00, $ff
L4R6MetaA:
  .byte $02                  ; (m1_col+1)<<4 | band mask
L4R6MetaB:
  .byte $0a                  ; (ball_col+1), 0 = no ball
L4R6RightPF0:
  .byte $f0, $30, $f0
L4R6RightPF1:
  .byte $ff, $00, $ff
L4R6RightPF2:
  .byte $ff, $00, $ff
L4R6RightRects:
  .byte 3                  ; number of rectangles
  .byte 0, 0, 20, 1  ; x(right_col*2), y, w, h
  .byte 18, 1, 2, 1  ; x(right_col*2), y, w, h
  .byte 0, 2, 20, 1  ; x(right_col*2), y, w, h
  .byte 0              ; number of hot rectangles
