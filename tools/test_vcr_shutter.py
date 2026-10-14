#!/usr/bin/env python3
"""Sprite-shutter kill tests (vcrunch_shutter_plan Phase C, py65).

Model2 (level 2 room 1) carries the V cell at row1 col8 — the middle-band
Phase C arm (specials rule 2026-10-14: V sits on row 1). The kill/overlay
path is PHMOverlay's miss path (punched
cell): the player sits in the right-half ball window, the cell walk
misses (punched/air), and OvShutBand runs OvShutScan — endpoints RoomY
(head) + RoomY+11 (feet) vs the slice state of clock-1 (kill parity).

Cases:
  1. arm      — after load: VcrBand=1, VcrNext=1, VcrState staged
                ($1F for pinned clock 100), bbox punched in PF1 band1,
                ColupfBuf[1]=$44 (Phase D hazard recolor);
  2. open     — clock 64 -> state $1B (center slice open), sprite fully
                inside slice2 (lines 66-78) -> aperture passable, no latch;
  3. corridor — clock 100 ($1F fully closed) but player at y116 (band2):
                band gate (OvHead/OvTail vs painted BandTab) rejects ->
                no kill (band1-only shutter: vertical position decides);
  4. bomb     — joystick Down edge drops a bomb (state=1, fuse ticking)
                WHILE the shutter pipeline keeps cycling (VcrNext consumed
                to 5, state matched, hazard color kept) — plan Phase D:
                bomb lives on GRP1, shutter owns the ball, no contention;
  5. kill     — clock 100 ($1F), player in band1 ball window ->
                 EnemyDeadMask b7 latches (crunch kill, cold containment
                 trivially true for the fully closed state);
  6. crunch  — clock 64 ($1B), y48: sprite 48..59 both endpoints CLOSED
                 below the [66,79) aperture -> cold containment KILLS
                 (crunched under the lower slab) — user spec 2026-10-14;
  7. crunch2 — same, y80: sprite 80..91 both closed above gapHi -> kill;
  8. coldtap — clock 64 ($1B), y57: head 57 CLOSED, feet 68 OPEN ->
                  cold: NO kill (touch from the open side is not a
                  crunched kill);
  9. hottap  — same geometry, MetaB b6 set (hot band): TOUCH -> kill.

The kill cases run LAST-ish (a latch leads to LoseLife; EnterRoom zeroes
the latch on respawn and the per-frame pins re-stage the room). Staging
samples are taken at the `jmp $FC68` HUD fold — after VBL staging,
before bank1's $EA-$EF stomp.

Run: /home/iuri/python3/bin/python3 tools/test_vcr_shutter.py
"""
import re
import sys
from pathlib import Path

import test_laser_walk_wall as W

SRC = W.SRC

import test_fixtures as FX          # noqa: E402
FX.freeze_m2(W.BANKS, W.L2)         # frozen model2 (user rule 2026-10-14)

# ZP indices (addr & 0x7F)
I_ROOMX, I_ROOMY = W.I_ROOMX, W.I_ROOMY
I_VYLO, I_VYHI = W.I_VYLO, W.I_VYHI
I_DEAD = W.I_DEAD                       # $BA EnemyDeadMask (b7 = crunch latch)
I_RAMP = 0x42                           # $C2 EnemyRamP frame clock
I_VSTATE, I_VNEXT, I_VBAND = 0x6A, 0x6B, 0x6C   # $EA/$EB/$EC
I_TEMP = 0x08                           # $88 Temp (b7 -> kernel hot-bump)
I_COLUPF1 = 0x68                        # $E8 ColupfBuf[1] (band1 color)
I_BOMBP = W.I_BOMBP                     # $B5 BombPacked (b7 OnGround, b1-0 state)
I_BOMBT = 0x77                          # $F7 BombTimer fuse countdown

# HUD fold: first bank0->bank1 fold after the cave kernel — staging is
# still the VBL's (bank1 stomps $E0-$EF only after entering the HUD).
HUD_JMP = None
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _code = _l.split(";")[0]           # drop lst comment (no jmp/$FC68 mix)
    if "jmp" in _code and "$FC68" in _code:
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})", _l)
        if _m:
            HUD_JMP = int(_m.group(1), 16)
            break
if HUD_JMP is None:
    sys.exit("bank0.lst: `jmp $FC68` not found")

PHMASK4 = W.BANKS[2][W.L2["PhMaskTab"] + 4 - 0xF000]   # pair mask (cols 8-9)
PF1_BAND1 = 0xC7 & 0x7F                # PF0Buf + offset3 + band1 (ZP index)


def covered(clock: int) -> int:
    """Python mirror of VcrCoveredState (bank2) — same constants as
    bank3 CrunchClock (verify_build check_crunch_clock guards the pair)."""
    sc = clock >> 2
    if sc >= 32:
        sc ^= 0x3F                    # eor #$3F fold (32..63 -> 31..0)
    if sc >= 4:
        sc -= 4                       # sbc #4 head (C from cmp #4)
    return 0x11 if sc < 9 else (0x1B if sc < 18 else 0x1F)


def boot():
    guard = 0
    while not (W.mem.bank == 0 and W.mpu.pc == W.PC_STARTFRAME):
        W.step()
        guard += 1
        if guard > 400000:
            sys.exit("never reached StartFrame")
    frame = 0
    while frame < 400:
        W.step()
        if W.mem.bank == 0 and W.mpu.pc == W.PC_STARTFRAME:
            frame += 1
            W.mem.swchb = 0xFE if frame in (2, 5) else 0xFF
            if W.mem.ram[W.I_BOMBP] & 0x80:
                return
    sys.exit("player never landed")


def run_frames(n, pins, samples):
    """n frames with pins poked at each StartFrame; append
    (VcrState, VcrNext, VcrBand, DeadMask, Temp, ColupfBuf[1]) at every
    HUD fold — ColupfBuf must be sampled HERE (at StartFrame bank1's
    scorePtr stomp already put $FD over $E8)."""
    for _ in range(n):
        pins()
        while True:
            W.mpu.step()
            if W.mem.bank == 0 and W.mpu.pc == HUD_JMP:
                r = W.mem.ram
                samples.append((r[I_VSTATE], r[I_VNEXT], r[I_VBAND],
                                r[I_DEAD], r[I_TEMP], r[I_COLUPF1]))
            if W.mem.bank == 0 and W.mpu.pc == W.PC_STARTFRAME:
                break


def main() -> None:
    fails = []
    boot()
    W.load_room(2)                     # model2 (V at row1 col4)

    # settle/arm position = corridor y20 (band0): the band gate rejects
    # non-shutter bands, so the kill latch never fires during staging
    # checks (a latch would disarm VcrShutter for the rest of the room
    # visit — bmi .VSnoArm).
    pins = {"x": 125, "y": 20, "clock": 100, "dead": 0x00}

    def poke():
        # NOTE: I_DEAD is NOT poked per frame — the kill latch is set at
        # overscan and would be wiped before the next HUD-fold sample.
        # Right press drives PlayerHitsMap every frame (walk -> miss ->
        # OverlayTramp -> PHMOverlay); with vy pinned and no input the
        # player never moves and the miss path never runs.
        r = W.mem.ram
        W.mem.swcha = 0x7F                # P0 right (active low D7)
        r[I_ROOMX] = pins["x"]
        r[I_ROOMY] = pins["y"]
        r[I_VYLO] = 0
        r[I_VYHI] = 0
        r[W.I_ENCOUNT] = 0
        r[I_RAMP] = pins["clock"]

    def set_dead(v):
        W.mem.ram[I_DEAD] = pins["dead"] = v

    # --- settle: 2 frames so VBL StageBandTab rebuilds the overlay pack
    set_dead(0x00)
    samples = []
    run_frames(2, poke, samples)

    # --- case 1: arm + punch ------------------------------------------------
    want = covered(pins["clock"])
    st, nxt, band, dead, _t, cf1 = samples[-1]
    if band != 1:
        fails.append(f"arm: VcrBand=${band:02X}, want $01 (armed band1)")
    if nxt != 5:
        # kernel consumes VcrNext 1->5 across the shutter band's RowSlice
        # calls; the HUD-fold sample sees the post-run value (5 = every
        # slice ran).
        fails.append(f"arm: VcrNext=${nxt:02X}, want $05 (slice run consumed)")
    if st != want:
        fails.append(f"arm: VcrState=${st:02X}, want ${want:02X} "
                     f"(clock {pins['clock']})")
    if W.mem.ram[PF1_BAND1] & PHMASK4:
        fails.append(f"arm: PF1 band1 pair4 not punched "
                     f"(=${W.mem.ram[PF1_BAND1]:02X} mask=${PHMASK4:02X})")
    if cf1 != 0x44:
        fails.append(f"arm: ColupfBuf[1]=${cf1:02X}, want $44 "
                     f"(Phase D hazard recolor)")
    print(f"  arm: state=${st:02X} next=${nxt:02X} band=${band:02X} "
          f"punch mask=${PHMASK4:02X} col1=${cf1:02X}")

    def expect_clear(tag, clock, y, frames=6):
        pins.update(clock=clock, y=y)
        set_dead(0x00)
        samples.clear()
        run_frames(frames, poke, samples)
        if any(s[3] & 0x80 for s in samples):
            fails.append(f"{tag}: crunch latch set (state=${covered(clock):02X}, "
                         f"y={y}) — aperture/band gate failed")
            return False
        st = samples[-1][0]
        if st != covered(clock):
            fails.append(f"{tag}: VcrState=${st:02X}, want "
                         f"${covered(clock):02X} (clock {clock})")
        print(f"  {tag}: no kill, state=${st:02X} "
              f"({'center open' if covered(clock) == 0x1B else 'closed'})")
        return True

    # --- case 2: open aperture over the player -----------------------------
    # clock 64 -> $1B (slice2 = lines 66-78 open); sprite y66..77 fully
    # inside slice2 -> both endpoints open -> passable.
    expect_clear("open ", clock=64, y=66)

    # --- case 3: fully closed but band2 (corridor) -------------------------
    # band gate (OvHead/OvTail vs painted BandTab) rejects before the scan:
    # band1-only shutter — vertical position decides.
    expect_clear("band2", clock=100, y=116)

    # --- case 4: bomb live while the shutter keeps sweeping ---------------
    # Joystick Down edge (SWCHA D5=0 -> Temp b1 after 4x LSR) drops a bomb
    # when OnGround+bombs+state0; b7 is forced per-frame because RoomY is
    # pinned (physics may not re-confirm the floor). Goal: bomb state
    # machine ticking CONCURRENT with a cycling shutter — plan Phase D
    # (bomb borrows GRP1, shutter owns the ball, color/pipeline intact).
    pins.update(clock=100, y=20, x=125)
    set_dead(0x00)

    def poke_bomb():
        poke()
        W.mem.swcha = 0x5F                # right + down (active low)
        W.mem.ram[I_BOMBP] |= 0x80        # OnGround forced (pinned RoomY)

    samples.clear()
    run_frames(2, poke_bomb, samples)     # frame1: drop edge, Timer=180
    run_frames(4, poke_bomb, samples)
    st = samples[-1][0]
    state2 = W.mem.ram[I_BOMBP] & 0x03
    bomb_fails = []
    if state2 != 1:
        bomb_fails.append(f"bomb: BombPacked state={state2}, want 1 (dropped)")
    t = W.mem.ram[I_BOMBT]
    if not (0 < t < 180):
        bomb_fails.append(f"bomb: BombTimer={t}, want <180 (fuse ticking)")
    cf1 = samples[-1][5]                 # fold sample (see run_frames)
    if cf1 != 0x44:
        bomb_fails.append(f"bomb: ColupfBuf[1]=${cf1:02X}, want $44 (kept)")
    bad = [s for s in samples
           if s[1] != 5 or s[0] != covered(pins["clock"]) or s[3] & 0x80]
    if bad:
        s0 = bad[0]
        bomb_fails.append(f"bomb: shutter pipeline disturbed at HUD fold: "
                          f"state=${s0[0]:02X} next=${s0[1]:02X} "
                          f"dead=${s0[3]:02X} (want state=${covered(100):02X} "
                          f"next=$05, no latch)")
    fails.extend(bomb_fails)
    if not bomb_fails:
        print(f"  bomb: state={state2} fuse={t} shutter=alive "
              f"(state=${st:02X} next=$05) col1=${cf1:02X}")
    # release the bomb input for the kill case (bomb keeps burning — the
    # kill path is overlay/PHM, independent of GRP1)
    W.mem.swcha = 0x7F

    # --- case 5: kill ($1F — both semantics agree) -------------------------
    pins.update(clock=100, y=68, x=125)
    set_dead(0x00)
    samples.clear()
    run_frames(6, poke, samples)
    if not any(s[3] & 0x80 for s in samples):
        fails.append("kill: no crunch latch with $1F state, sprite in band1 "
                     "ball window (x=125 y=68 clock=100) — kill path dead")
    else:
        s = next(s for s in samples if s[3] & 0x80)
        print(f"  kill: latch set (state=${covered(100):02X}, "
              f"Temp=${s[4]:02X} at sample)")

    # --- cases 6-9: hot/cold kill semantics (user spec 2026-10-14) --------
    # MetaB = (RoomPF0Lo)+10; b6 = mid_band_type hot. Poke the test's own
    # bank2 copy (synthetic staging — not live game data).
    metap = W.mem.ram[0x99 & 0x7F] | (W.mem.ram[0x9A & 0x7F] << 8)  # RoomPF0Lo
    meta_off = metap + 10 - 0xF000
    meta_orig = W.BANKS[2][meta_off]

    def set_hot(on: bool):
        W.BANKS[2][meta_off] = (meta_orig | 0x40) if on else (meta_orig & ~0x40)

    def expect_kill(tag, clock, y, frames=6):
        pins.update(clock=clock, y=y)
        set_dead(0x00)
        W.mem.ram[0x2C & 0x7F] = 3      # PlayerLives — each kill costs one;
                                        #   exhausted lives = game over and
                                        #   the overlay stops running
        samples.clear()
        run_frames(frames, poke, samples)
        if not any(s[3] & 0x80 for s in samples):
            fails.append(f"{tag}: no latch (state=${covered(clock):02X}, "
                         f"y={y}) — expected kill")
            return
        # removal (user spec 2026-10-14): post-latch VcrShutter punches-only —
        # BandTab unarmed (no ball block), VcrBand/VcrNext idle, red restored
        set_dead(0x80)                  # keep the latch across these frames
        samples.clear()
        run_frames(3, poke, samples)
        st, nxt, band, dead, _t, cf1 = samples[-1]
        if band != 0xFF or nxt != 0:
            fails.append(f"{tag}: post-kill arm alive (VcrBand=${band:02X} "
                         f"VcrNext=${nxt:02X}) — wall not removed "
                         f"(want idle $FF/0)")
        if W.mem.ram[0x6E & 0x7F] == 0xFF:          # BandTab[1] ($EE)
            fails.append(f"{tag}: post-kill BandTab[1]=$FF — ball block "
                         f"still armed")
        if cf1 == 0x44:
            fails.append(f"{tag}: post-kill ColupfBuf[1]=$44 — hazard "
                         f"recolor kept on a removed wall")
        print(f"  {tag}: latch set (state=${covered(clock):02X}, y={y}, "
              f"removed: band=${band:02X} col1=${cf1:02X})")

    set_hot(False)
    # case 6: cold, $1B, both endpoints closed below the aperture (F=59<66)
    expect_kill("crunch", clock=64, y=48)
    # case 7: cold, $1B, both closed above gapHi (H=80>=79, F=91) — y80
    # keeps 3px drift margin inside [79,88)/[88,97) (y85 sat 1px from
    # the 97 bound; one gravity step opened the feet)
    expect_kill("crunch2", clock=64, y=80)
    # case 8: cold, head closed (b1) feet open (b2) — touch is NOT a
    # cold kill (sprite not crunched; aperture open over the feet)
    set_hot(False)
    expect_clear("coldtap", clock=64, y=57)
    # case 9: hot, same geometry — touch kills
    set_hot(True)
    expect_kill("hottap", clock=64, y=57)
    set_hot(False)                     # restore fixture semantics

    if fails:
        print(f"\nFAIL: {len(fails)}")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("test_vcr_shutter: OK (9 cases)")


if __name__ == "__main__":
    main()
