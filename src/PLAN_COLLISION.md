# Collision Investigation — Findings

## Root Cause (found 2026-09-21)

The collision code (PlayerHitsMap) is IDENTICAL between our kernel and the
comparison branch. The visible_left calculation (`sbc #4` / `sbc #7`) is correct.

The actual issue was TWO bad "fixes" that were applied:

1. **convert_room.py PF0 mapping** — An attempted fix to `0x80 >> col` broke
   the PF0 bit order. The original `0x10 << col` is correct because TIA PF0
   has bit 4 = leftmost pixel, not bit 7.

2. **visible_left calculation** — An attempted fix changed `sbc #4` to `adc #3`,
   computing RoomX+3 instead of RoomX-5. The original `sbc #4` (which actually
   computes X-5 due to CMP clearing carry) is correct, matching the comparison
   branch that works.

## Verified Correct Values

### Measured pixel positions (comparison branch, works correctly)
- RoomX < 15: sprite left edge ≈ RoomX - 5
- RoomX >= 15: sprite left edge ≈ RoomX - 7

### visible_left calculation
```
sec
lda RoomX
cmp #15
bcs .off7
sbc #4          ; RoomX < 15: visible_left = X - 5 (carry cleared by CMP)
jmp .gotVL
.off7:
sbc #7          ; RoomX >= 15: visible_left = X - 7 (carry set by CMP)
```

### PF0 bit order (TIA hardware)
- Bit 4 = pixel 0 (leftmost)
- Bit 5 = pixel 1
- Bit 6 = pixel 2
- Bit 7 = pixel 3 (rightmost of PF0 group)
- So `0x10 << col` maps col 0 → bit 4 → leftmost pixel ✓

## What was fixed
- CavePF0/1/2 and CaveRects now generated from `rooms/level_001_room_001.txt`
  via `tools/convert_room.py` (PF and rects always match)
- build.sh calls convert_room.py automatically before assembling
- kernel.asm includes generated data instead of hardcoded values
