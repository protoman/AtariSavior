proc 6502
include vcs.h
include macro.h
SEG.U VARS
ORG 0
Temp ds 1
SEG CODE
ORG 
Start:
  rts
org 
  .word Start
  .word Start
