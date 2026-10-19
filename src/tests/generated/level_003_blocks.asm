; Generated from New Level (level 3) — per-room PF/meta blocks. Do not edit by hand.

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

; Generated from room 1 (model 4). Do not edit by hand.
L3R2RoomRects:
  .byte 3                  ; number of rectangles
  .byte $00, $49  ; packed (x<<2|y, w<<2|h)
  .byte $02, $11  ; packed (x<<2|y, w<<2|h)
  .byte $1a, $39  ; packed (x<<2|y, w<<2|h)
  .byte 1              ; number of hot rectangles
  .byte $82, 0, 1, 20, 1  ; hcrunch band prefix
L3R2TilePF0:
  .byte $f0, $f0, $f0
L3R2TilePF1:
  .byte $ff, $ff, $3f
L3R2TilePF2:
  .byte $3f, $ff, $ff
L3R2MetaA:
  .byte $00                  ; (m1_col+1)<<4 | band mask
L3R2MetaB:
  .byte $00                  ; (ball_col+1), 0 = no ball
