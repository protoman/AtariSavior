def sim_eor7(x):
    # sta WSYNC (cycle 0)
    # sec (2)
    cyc = 2
    val = x
    while True:
        cyc += 2 # sbc #15
        val -= 15
        if val >= 0:
            cyc += 3 # bcs taken
        else:
            cyc += 2 # bcs fall through
            break
    # val is in -15..-1
    # eor #7:
    rem = val & 0xff
    eor_val = rem ^ 7
    # asl * 4
    hmp_raw = (eor_val << 4) & 0xff
    # sta HMP0,Y (5 cycles for abs,Y)
    cyc += 2 + 8 + 5
    # sta RESP0,Y (5 cycles)
    cyc += 5
    strobe = cyc * 3
    nibble = hmp_raw >> 4
    if nibble >= 8:
        shift = nibble - 16
    else:
        shift = nibble
    return strobe, shift, strobe - shift, hmp_raw

for x in range(30, 46):
    s, h, net, raw = sim_eor7(x)
    print(f"X={x:2d}: strobe={s:3d} hmp={h:+2d} (raw=0x{raw:02x}) net={net:3d} diff={net-x}")
