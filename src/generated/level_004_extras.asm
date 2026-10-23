; Generated from Level 4 (level 4).
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
  .byte $01, $39, $00, $42  ; room 3: 1 patch(es), 0 feature(s), MetaA $39 MetaB $00
