; ==============================================================================
; NEW ROM bank selectors by ROLE (docs/agents/banks.md, Layout v3). BKI_x = the physical bank of role x.
; The new ROM is built from newrom/ (tools/build_newrom.sh); this file shadows src/banks.inc there.
; ==============================================================================
BKI_GENERAL   = 0       ; main loop, input, physics, collision, sound, the fold pads
BKI_CAVE      = 1       ; the generated gameplay cave kernel (+ its prologue)
BKI_HUD       = 2       ; HUD, title, level select
BKI_GAMEPLAY  = 3       ; raft, bomb wall marks, strip blast, stage band, colour build
BKI_SAVE      = 4       ; save-to-cartridge (I2C)
BKI_TRANS     = 4       ; version header, blank transition frame, attract script
BKI_MODELS    = 4       ; room models: shape step + shape blocks / row pool
BKI_OVERLAY   = 4       ; asym-patch collision overlay cluster (placed when bank 4 is filled)
BKI_EXTRAS    = 5       ; extras walkers + extras data of all 32 levels
BKI_ROOMS     = 6       ; room bank A: room code + room data
BKI_ROOMS_B   = 7       ; room bank B: same code, the levels past LEVEL_SPLIT
BKI_PROLOGUE  = 1       ; cave kernel start-up code (same bank as the cave once bank 1 is filled)

BK_GENERAL    = $1FF4 + BKI_GENERAL
BK_CAVE       = $1FF4 + BKI_CAVE
BK_HUD        = $1FF4 + BKI_HUD
BK_GAMEPLAY   = $1FF4 + BKI_GAMEPLAY
BK_SAVE       = $1FF4 + BKI_SAVE
BK_TRANS      = $1FF4 + BKI_TRANS
BK_MODELS     = $1FF4 + BKI_MODELS
BK_OVERLAY    = $1FF4 + BKI_OVERLAY
BK_EXTRAS     = $1FF4 + BKI_EXTRAS
BK_ROOMS      = $1FF4 + BKI_ROOMS
BK_ROOMS_B    = $1FF4 + BKI_ROOMS_B
BK_PROLOGUE   = $1FF4 + BKI_PROLOGUE
