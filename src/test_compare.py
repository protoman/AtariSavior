# Let's test why Andrew Davie vs eor #7 differ
def sim_davie(x):
    # WSYNC
    # sec (2)
    cyc = 2
    rem = x
    while True:
        cyc += 2
        rem -= 15
        if rem >= 0:
            cyc += 3
        else:
            cyc += 2
            break
    # tay (2)
    # lda fineAdjustTable,y (5)
    # sta HMP0,x (4)
    # sta RESP0,x (4)
    cyc += 2 + 5 + 4 + 4
    strobe = cyc * 3
    # rem is in -15..-1 ($F1..$FF)
    # idx = (rem & 0xff) - 241
    # fineAdjustBegin:
    table = [7, 6, 5, 4, 3, 2, 1, 0, -1, -2, -3, -4, -5, -6, -7]
    idx = (rem & 0xff) - 241
    hmp = table[idx]
    # In TIA:
    # When RESPx is strobed at cycle C (clock 3*C), the object's counter is reset.
    # But wait! At which color clock does the object start rendering relative to RESP strobe?
    # In TIA hardware:
    # A write to RESP0 resets player 0.
    # Player 0 starts 4 color clocks (or 5) after the strobe.
    # Then HMOVE moves it:
    # An HMOVE pulse injects additional clocks during the first 15 clocks of HBLANK (clocks 0..14).
    # Specifically, a motion value of:
    # 0 = 0 shift
    # +1 to +7 (bits 7-4 = $10..$70) = moves 1 to 7 pixels to the LEFT
    # -1 to -8 (bits 7-4 = $F0..$80) = moves 1 to 8 pixels to the RIGHT
    # So pos = strobe - hmp (if hmp is +moves left, -moves right)
    return strobe, hmp, strobe - hmp

print("Testing Davie for x in range 30..46:")
for x in range(30, 46):
    s, h, net = sim_davie(x)
    print(f"X={x:2d}: rem={x%15-15:3d}, strobe={s:3d}, hmp={h:+2d}, net={net:3d}")
