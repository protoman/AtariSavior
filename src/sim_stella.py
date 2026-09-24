# Let's inspect what Stella's actual TIA emulator does on each cycle/clock!
# In Stella / TIA:
# Does HMOVE immediately after WSYNC cause extra clocks?
# In Atari 2600 TIA hardware:
# When HMOVE is strobed immediately after WSYNC:
# HMOVE generates the 15-clock HMOVE latch which slows down the internal counters,
# and outputs the "HMOVE ripple blank" on the left 8 pixels of the screen (or 4 pixels in Stella if not suppressed).
# But wait! If HMOVE is strobed:
# STA WSYNC (cycle 0 of new scanline)
# STA HMOVE (cycles 0..2 of that scanline)
# Does HMOVE need to be strobed IMMEDIATELY after WSYNC? YES, within cycle 0..3!
# In kernel.asm:
#   sta WSYNC
#   sta HMOVE
# This takes 3 cycles, so HMOVE is strobed on cycle 3. That is right in HBLANK.
