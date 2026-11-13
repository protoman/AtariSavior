; ==============================================================================
; Bank selectors by ROLE (docs/agents/banks.md). Code never writes a literal $1FF4-$1FFB: it writes
; the selector of the bank that holds the ROLE it wants (`sta BK_ROOMS`), so the physical bank
; number of every role is decided HERE and nowhere else. The F4 hotspot of physical bank n is $1FF4+n.
;
; BKI_x = the physical bank (0-7) that holds role x. OLD layout (what build.sh assembles today):
; ==============================================================================
BKI_GENERAL   = 0       ; main loop, input, physics, collision, sound, the fold pads
BKI_HUD       = 1       ; HUD, title and level select, raft, bomb wall marks, strip blast
BKI_ROOMS     = 2       ; level room half: room readers, exits, laser, moth, blast + the room tables
BKI_EXTRAS    = 3       ; level extras half: phase/hcrunch/hot/dark walkers + the extras data
BKI_SAVE      = 4       ; save-to-cartridge (I2C)
BKI_TRANS     = 5       ; version header, blank transition frame, attract script
BKI_CAVE      = 6       ; the generated gameplay cave kernel
BKI_PROLOGUE  = 7       ; cave kernel start-up code + the room-model (shape) window

BK_GENERAL    = $1FF4 + BKI_GENERAL
BK_HUD        = $1FF4 + BKI_HUD
BK_ROOMS      = $1FF4 + BKI_ROOMS
BK_EXTRAS     = $1FF4 + BKI_EXTRAS
BK_SAVE       = $1FF4 + BKI_SAVE
BK_TRANS      = $1FF4 + BKI_TRANS
BK_CAVE       = $1FF4 + BKI_CAVE
BK_PROLOGUE   = $1FF4 + BKI_PROLOGUE
