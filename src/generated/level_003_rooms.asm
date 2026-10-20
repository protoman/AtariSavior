; Generated from New Level (level 3). Do not edit by hand.
LEVEL3_START_ROOM = 0
LEVEL3_WALL_COLOR = $92
LEVEL3_WALL_COLOR2 = $96
LEVEL3_MINER_ROOM = 133
LEVEL3_MINER_X = 23
LEVEL3_MINER_Y = 84

; Room data: ONE word per room (the block's RoomRects label), indexed by RoomNo. TilePF0 is derived at room load as
; rects + 2 + 2*nrect (C3 2026-10-20: it always sits 2 bytes past the rect list in the same block, so the second word was redundant).
LEVEL3_RoomDataTable:
  .word L1R1RoomRects ; room 0 (async) [shared with L1R1]
  .word M4RoomRects ; room 1 (model 4)
  .word M5RoomRects ; room 2 (model 5)
  .word M6RoomRects ; room 3 (model 6)
  .word M7RoomRects ; room 4 (model 7)
  .word M1RoomRects ; room 5 (model 1)

; Room connections: 2 bytes/room, nibble-packed (up<<4|down, left<<4|right); $F = none.
LEVEL3_RoomConnections:
  .byte $f1, $ff ; room 0
  .byte $02, $ff ; room 1
  .byte $13, $ff ; room 2
  .byte $24, $ff ; room 3
  .byte $35, $ff ; room 4
  .byte $4f, $ff ; room 5

; Per-room enemy records: ONE byte (count<<6 | first record index<<1 | bottom-band flag). The band COLOR is the global BAND_COLOR (one water
; color per game — the converter rejects a second one).
LEVEL3_RoomEnemies:
  .byte $00 ; room 0: 0 record(s) from 0
  .byte $00 ; room 1: 0 record(s) from 0
  .byte $80 ; room 2: 2 record(s) from 0
  .byte $84 ; room 3: 2 record(s) from 2
  .byte $88 ; room 4: 2 record(s) from 4
  .byte $0c ; room 5: 0 record(s) from 6

; Enemy data: 6 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL3_EnemyDataTable:
  .byte 1, 127, 60, 1
  .byte 5, 27, 18, 1
  .byte 0, 23, 108, 1
  .byte 2, 103, 60, 1
  .byte 4, 39, 60, 1
  .byte 5, 27, 18, 1
