; Generated from New Level (level 4).
; Do not edit by hand. C7 (2026-10-20): bank3 async EXTRAS stream —
; one record per owns-extras room, in room order (the counts byte's
; b5-0 is the 1-based ORDINAL). Record layout:
;   +0 flags: n_patches b1-0 | n_features b5-2
;   +1 MetaA  +2 MetaB  (the retired TilePF0+9/+10 pair — the
;      loader stages it into $99/$9A)
;   +3.. 1 B/patch: row b7-6 | side b4 | col b3-0 (tile = wall)
;   ..   1 B/feature: kind b7-6 (1 = phase, 2 = hcrunch
;        prefix end) | col b3-0
;   ..   [n_features > 0] 1 B count + 5 B/FEATURE record — the
;        live feature geometry ($80 phase cell / $82 hcrunch
;        prefix). Static hot + the M1 block cell are derived by
;        the loader (PF row 1 + the patch list) — C11.
LEVEL4_AsyncExtras:
  .byte $02, $90, $00, $18, $58  ; room 1: 2 patch(es), 0 feature(s), MetaA $90 MetaB $00
  .byte $04, $00, $00, $89, $01, $82, $00, $01, $20, $01  ; room 2: 0 patch(es), 1 feature(s), MetaA $00 MetaB $00
  .byte $01, $10, $00, $50  ; room 5: 1 patch(es), 0 feature(s), MetaA $10 MetaB $00
  .byte $01, $02, $0a, $49  ; room 6: 1 patch(es), 0 feature(s), MetaA $02 MetaB $0a
