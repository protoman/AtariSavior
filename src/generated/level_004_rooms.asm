; Generated from New Level (level 4). Do not edit by hand.
LEVEL4_START_ROOM = 0
LEVEL4_WALL_COLOR = $52
LEVEL4_WALL_COLOR2 = $56
LEVEL4_MINER_ROOM = 5
LEVEL4_MINER_X = 147
LEVEL4_MINER_Y = 84

; Room data: ONE word per room (the block's RoomRects label), indexed by RoomNo. TilePF0 is derived at room load as
; rects + 2 + 2*nrect (C3 2026-10-20: it always sits 2 bytes past the rect list in the same block, so the second word was redundant).
LEVEL4_RoomDataTable:
  .word L1R1RoomRects ; room 0 (async) [shared with L1R1]
  .word L4R2RoomRects ; room 1 (async)
  .word M5RoomRects ; room 2 (model 5)
  .word M8RoomRects ; room 3 (model 8)
  .word L4R5RoomRects ; room 4 (async)
  .word L4R6RoomRects ; room 5 (async)

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL4_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $02, $ff ; room 1
  .byte $13, $ff ; room 2
  .byte $2f, $45 ; room 3
  .byte $ff, $f3 ; room 4
  .byte $ff, $3f ; room 5

; Per-room enemy records: ONE byte (count<<6 | first record index<<1 | bottom-band flag). The band COLOR is the global BAND_COLOR (one water
; color per game — the converter rejects a second one).
LEVEL4_RoomEnemies:
  .byte $00 ; room 0: 0 record(s) from 0
  .byte $00 ; room 1: 0 record(s) from 0
  .byte $00 ; room 2: 0 record(s) from 0
  .byte $00 ; room 3: 0 record(s) from 0
  .byte $00 ; room 4: 0 record(s) from 0
  .byte $00 ; room 5: 0 record(s) from 0

; Enemy data: 0 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL4_EnemyDataTable:
