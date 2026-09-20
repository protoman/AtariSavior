# Collision System Copy Plan — from comparison/lo-a-rad-dragon/bank0.asm

## Goal
Copy the ENTIRE collision and movement system from the comparison code verbatim,
adding stubs for room exits and future features.

## What Changes

### 1. Add missing ZP variables and constants
- Add `PlayerDir` byte at $88 (after Temp)
- Add `FACING_RIGHT = 0`, `FACING_LEFT = 1`
- Change `PLAYER_MAX_Y` from 135 to 136 (match comparison code)

### 2. Replace overscan movement code
Remove current inline movement code. Replace with labeled routines copied from
comparison code:
- `CheckP0Left:` — horizontal left with collision + room exit stub
- `CheckP0Right:` — horizontal right with collision + room exit stub
- `CheckP0Up:` — vertical up with collision (simplified from StepUp, joystick-based)
- `CheckP0Down:` — vertical down with collision (simplified from StepDown, joystick-based)

### 3. Add room exit stubs
- `ExitRoomLeft:` — stub: reposition player to RoomX=100, RoomY=64
- `ExitRoomRight:` — stub: reposition player to RoomX=100, RoomY=64
- `ExitRoomUp:` — stub: reposition player to RoomX=100, RoomY=64
- `ExitRoomDown:` — stub: reposition player to RoomX=100, RoomY=64

### 4. No changes to PlayerHitsMap or YToCellRow
Already identical to comparison code.

## Verification
- Build succeeds, 4096 bytes
- `jmp $F0AC` in fold pad unchanged
- Player stops flush against all walls (left, right, top, bottom)
- Player can move freely in open space
- Player can move right then left without getting stuck
