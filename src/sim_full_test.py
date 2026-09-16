# Let's inspect:
# In Andrew Davie's session 24:
# fineAdjustBegin:
# %01110000 ; left 7  (idx 0)
# %01100000 ; left 6  (idx 1)
# %01010000 ; left 5  (idx 2)
# %01000000 ; left 4  (idx 3)
# %00110000 ; left 3  (idx 4)
# %00100000 ; left 2  (idx 5)
# %00010000 ; left 1  (idx 6)
# %00000000 ; 0       (idx 7)
# %11110000 ; right 1 (idx 8)
# %11100000 ; right 2 (idx 9)
# %11010000 ; right 3 (idx 10)
# %11000000 ; right 4 (idx 11)
# %10110000 ; right 5 (idx 12)
# %10100000 ; right 6 (idx 13)
# %10010000 ; right 7 (idx 14)

# Wait! What does "right 1" mean in HMP?
# In 2600 TIA specification:
# HMP bits 4-7:
# 0111 = +7 (moves 7 color clocks to the LEFT)
# ...
# 0001 = +1 (moves 1 color clock to the LEFT)
# 0000 = 0 (no motion)
# 1111 = -1 (moves 1 color clock to the RIGHT)
# ...
# 1001 = -7 (moves 7 color clocks to the RIGHT)
# 1000 = -8 (moves 8 color clocks to the RIGHT)

# Wait! Does HMOVE move the sprite by HMP clocks EVERY scanline if HMOVE is called every scanline?
# In kernel.asm, HMOVE is called ONCE per frame, in VBLANK:
# sta WSYNC
# sta HMOVE
# Wait! Does HMOVE need HMCLR?
# In TIA: Once HMP0 is written, its value remains in HMP0 until overwritten or cleared by HMCLR.
# If HMOVE is only strobed ONCE per frame, HMP0 adjusts it ONCE per frame!
# BUT what if HMP0 still holds a value from frame to frame?
# In each frame:
# JSR SetObjectXPos writes a NEW value to HMP0!
# Then sta WSYNC; sta HMOVE applies it!
# Wait! What about HMCLR? Does HERO call HMCLR or anything?
