; Generated from Level 1 (level 1). Do not edit by hand.
LEVEL1_START_ROOM = 0
LEVEL1_WALL_COLOR = $20
LEVEL1_WALL_COLOR2 = $22
LEVEL1_START_X = 32
LEVEL1_START_Y = 24
LEVEL1_MINER_ROOM = 128
LEVEL1_MINER_X = 143
LEVEL1_MINER_Y = 84

; Room data: one (L1R<n>TilePF0, ...RoomRects) word pair per room, indexed by RoomNo. Rooms pointing at a model share that model's
; M<id>TilePF0 / M<id>RoomRects (emitted once in models_data.asm).
LEVEL1_RoomDataTable:
  .word L1R1TilePF0, L1R1RoomRects ; room 0 (async)
  .word L1R2TilePF0, L1R2RoomRects ; room 1 (async)

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL1_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $0f, $ff ; room 1

; Enemy data: 0 enemy records across 2 rooms, 4 bytes each (type,x,y,dir).
LEVEL1_EnemyDataTable:

; Per-room enemy records: ptr_lo, ptr_hi, count, bottom_color.
LEVEL1_RoomEnemies:
  .byte <(LEVEL1_EnemyDataTable), >(LEVEL1_EnemyDataTable), 0, $00 ; room 0
  .byte <(LEVEL1_EnemyDataTable), >(LEVEL1_EnemyDataTable), 0, $00 ; room 1

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

; Generated from room 1 (model 1). Do not edit by hand.
L1R2RoomRects:
  .byte 3                  ; number of rectangles
  .byte $00, $49  ; packed (x<<2|y, w<<2|h)
  .byte $01, $09  ; packed (x<<2|y, w<<2|h)
  .byte $02, $51  ; packed (x<<2|y, w<<2|h)
  .byte 0              ; number of hot rectangles
L1R2TilePF0:
  .byte $f0, $30, $f0
L1R2TilePF1:
  .byte $ff, $00, $ff
L1R2TilePF2:
  .byte $3f, $00, $ff
L1R2MetaA:
  .byte $29                  ; (m1_col+1)<<4 | band mask | $08 door | $01 right half
L1R2MetaB:
  .byte $00                  ; (ball_col+1), 0 = no ball
