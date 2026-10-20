; Generated from New Level (level 4). Do not edit by hand.
LEVEL4_START_ROOM = 0
LEVEL4_WALL_COLOR = $52
LEVEL4_WALL_COLOR2 = $56
LEVEL4_MINER_ROOM = 5
LEVEL4_MINER_X = 147
LEVEL4_MINER_Y = 84

; Room shape index (C2 2026-10-20): ONE byte per room =
;   b5-0 SHAPE INDEX into LEVEL_ShapeTable (levels_index.asm)
;   b6   bottom-band flag
;   b7   owns-extras (C5): the room has a record in the level's
;        AsyncExtras stream (selected by the counts byte's b5-0)
; C5 (2026-10-20): an async room points at its SHARED MODEL shape;
; the patches/features/meta come from the extras record, so there are
; no per-room blocks any more. A room without a model is rejected
; (the shape must be shared). C4: block = hot stream | PF triple —
; TilePF0 = block + 1 + 5*hot_count.
LEVEL4_RoomShapes:
  .byte SHAPE_M0 | $80 ; room 0 (async extras)
  .byte SHAPE_M4 | $80 ; room 1 (async extras)
  .byte SHAPE_M5 ; room 2 (model 5)
  .byte SHAPE_M8 ; room 3 (model 8)
  .byte SHAPE_M11 | $80 ; room 4 (async extras)
  .byte SHAPE_M10 | $80 ; room 5 (async extras)

; Room grid positions (LEVEL_FORMAT 2, C1 2026-10-20): ONE byte/room,
; (x<<4 | y) normalised to the level origin. Exits are DERIVED at
; room load by scanning this column (bank2 ExitScanB2), so no
; connection bytes are stored: a nibble of 15 never occurs and marks
; a neighbour outside the grid.
LEVEL4_RoomPositions:
  .byte $10 ; room 0 (1, 0)
  .byte $11 ; room 1 (1, 1)
  .byte $12 ; room 2 (1, 2)
  .byte $13 ; room 3 (1, 3)
  .byte $03 ; room 4 (0, 3)
  .byte $23 ; room 5 (2, 3)

; Per-room enemy count (C2 2026-10-20): ONE byte = count<<6 |
; extras ordinal (C5: 1-based index into LEVELn_AsyncExtras, 0 =
; none; the enemy record index is derived at room load).
LEVEL4_RoomCounts:
  .byte $01 ; room 0: 0 record(s), extras 1
  .byte $02 ; room 1: 0 record(s), extras 2
  .byte $00 ; room 2: 0 record(s)
  .byte $00 ; room 3: 0 record(s)
  .byte $03 ; room 4: 0 record(s), extras 3
  .byte $04 ; room 5: 0 record(s), extras 4

; Enemy data: 0 enemy records across 6 rooms, 4 bytes each (type,x,y,dir).
LEVEL4_EnemyDataTable:

; C5 (2026-10-20) async EXTRAS stream — one record per
; owns-extras room, in room order (the counts byte b5-0 is the
; 1-based ORDINAL). Record layout (hex per line below):
;   +0 flags: n_patches b1-0 | n_features b5-2
;   +1 MetaA  +2 MetaB  (the pair that used to sit at
;      TilePF0+9/+10 — the loader stages it into $99/$9A)
;   +3.. 1 B/patch: row b7-6 | side b4 | col b3-0 (tile = wall)
;   ..   1 B/feature: kind b7-6 (1 = phase, 2 = hcrunch
;        prefix end) | col b3-0
;   ..   [n_features > 0] 1 B hot count + 5 B/hot record — the
;        ROOM's hot stream (feature cells split the shape's own
;        hot rects, so the walkers read this copy instead).
LEVEL4_AsyncExtras:
  .byte $02, $90, $00, $18, $58  ; room 0: 2 patch(es), 0 feature(s), MetaA $90 MetaB $00
  .byte $04, $00, $00, $89, $01, $82, $00, $01, $20, $01  ; room 1: 0 patch(es), 1 feature(s), MetaA $00 MetaB $00
  .byte $01, $10, $00, $50  ; room 4: 1 patch(es), 0 feature(s), MetaA $10 MetaB $00
  .byte $01, $02, $0a, $49  ; room 5: 1 patch(es), 0 feature(s), MetaA $02 MetaB $0a
