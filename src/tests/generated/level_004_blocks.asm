; Generated from New Level (level 4) — per-room PF/meta blocks. Do not edit by hand.

; Generated from room 0 (model 0). Do not edit by hand.
; L4R1 block SHARED with L1R1 (byte-identical dedupe)
; L4R2 block SHARED with L3R2 (byte-identical dedupe)
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
  .byte $0a                  ; (ball_col+1)
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
