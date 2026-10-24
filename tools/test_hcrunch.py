#!/usr/bin/env python3
"""hcrunch tests — simplified contract (user decision 2026-10-19, py65).

Contract:
  * the crunch band is ALWAYS band 1 (middle) — record y/band ignored;
  * ALWAYS hot: any overlap of the player box with the covered prefix kills,
    at any clock phase and any extent (no cold "closing only" rule);
  * ALWAYS the same geometry: fixed 10-cell prefix (half playfield width) —
    record x/w/h ignored, the 5-byte record stride stays for the walker;
  * NO growth push (HcrPush removed) and NO one-kill-per-visit latch
    (EnemyDeadMask b7 is never written by the crunch path);
  * the clock animation stays: n = HcrClock(10) (1..10 cells, 16f/step,
    dwell -> grow to center -> fast retract), PF band1 = P(n).

Model4 (frozen fixture) still carries the $82 record + C cells, so the
staging path is exercised for real. The test patches the record's y/w bytes
to prove they are ignored.

Cases:
   1. arm     — clock 8 (dwell) -> PF band1 = P(1); record y patched to 2
                 must NOT move the staging to band2;
   2. curve   — 16 buckets: PF band1 == P(covered(clock));
   3. stable  — covered may change only on 16f boundaries;
   4. dwell   — n==1 run >= 3 buckets at cycle start;
   5. kill    — x0 y68 band1, clock 8 (n=1): lives 3 -> 2, b7 NOT latched;
   6. rekill  — same pins again: kills again (no latch);
   7. open    — clock 240 (retract half): still kills (always hot);
   8. sealed  — clock 192 (n=10, prefix reaches center): x38 kills;
   9. band0   — y20: band gate rejects, no kill;
  10. band2   — y116: band gate rejects, no kill;
  11. nohit   — x70 y68 (n=1 prefix covers cols 0-1): no kill;
  12. nopush  — grow edge clock 0x80: RoomX untouched (left and right);
  13. static  — no record reads in PhHcrEntry / the $82 HOV handler; no
                 HcrPush symbol; the fixture record is still 5 bytes.

Run: /home/iuri/python3/bin/python3 tools/test_hcrunch.py
"""
import re
import sys
from pathlib import Path

import test_laser_walk_wall as W

SRC = W.SRC
FROZEN = W.SRC / "tests" / "frozen"   # test-owned banks+labels

import test_fixtures as FX          # noqa: E402

# C11 (2026-10-21): a shape block carries no record stream — the $82 hcrunch
# record is staged as synthetic RAM data and RoomRects points at it.
STREAM_ADDR = 0xA0
I_RRLO, I_RRHI = 0x10, 0x11             # $90/$91 RoomRects ptr
I_M1HOT = 0x2F                          # $AF RoomM1Hot

I_ROOMX, I_ROOMY = W.I_ROOMX, W.I_ROOMY
I_VYLO, I_VYHI = W.I_VYLO, W.I_VYHI
I_DEAD = W.I_DEAD
I_RAMP = 0x42                           # $C2 EnemyRamP frame clock
I_LIVES = 0x2C                          # $AC PlayerLives

HUD_JMP = None
for _l in (FROZEN / "bank0.lst").read_text(errors="replace").splitlines():
    _code = _l.split(";")[0]
    if "jmp" in _code and "$FC68" in _code:
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})", _l)
        if _m:
            HUD_JMP = int(_m.group(1), 16)
            break
if HUD_JMP is None:
    sys.exit("bank0.lst: `jmp $FC68` not found")

# N=4 stride 4: band-1 rows are PF0 $C4, PF1 $C8, PF2 $CC
PF0_B1, PF1_B1, PF2_B1 = 0xC4 & 0x7F, 0xC8 & 0x7F, 0xCC & 0x7F
PF0_B2 = 0xC5 & 0x7F
FULL = 10

# P(n) prefix masks (mirror of bank2 CrPfx0/1/2 — change both together).
P_TRIPLE = {
    # Coverage starts at pair 1: pair 0 (the side openings) stays open.
    1: (0xC0, 0x00, 0x00), 2: (0xC0, 0xC0, 0x00), 3: (0xC0, 0xF0, 0x00),
    4: (0xC0, 0xFC, 0x00), 5: (0xC0, 0xFF, 0x00), 6: (0xC0, 0xFF, 0x03),
    7: (0xC0, 0xFF, 0x0F), 8: (0xC0, 0xFF, 0x3F), 9: (0xC0, 0xFF, 0xFF),
    10: (0xC0, 0xFF, 0xFF),
}
N_OF = {tuple(v): k for k, v in P_TRIPLE.items()}


def covered(clock: int) -> int:
    """HcrClock mirror: s=P>>4; dwell 0-3, grow s-3 (4-12), retract 3*(15-s)."""
    s = (clock >> 4) & 15
    if s < 4:
        eff = 0
    elif s < 13:
        eff = s - 3
    else:
        eff = 3 * (15 - s)
    return 1 + min(eff, FULL - 1)


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


pins = {"x": 70, "y": 20, "clock": 8}
samples = []


def poke():
    r = W.mem.ram
    W.mem.swcha = 0x7F                # P0 right: the walk runs every frame
    r[I_ROOMX] = pins["x"]
    r[I_ROOMY] = pins["y"]
    r[I_VYLO] = 0
    r[I_VYHI] = 0
    r[W.I_ENCOUNT] = 0
    r[I_RAMP] = pins["clock"]


def run_frames(n):
    samples.clear()
    for _ in range(n):
        poke()
        while True:
            W.step()
            if W.mem.bank == 0 and W.mpu.pc == HUD_JMP:
                r = W.mem.ram
                samples.append((r[PF0_B1], r[PF1_B1], r[PF2_B1],
                                r[I_DEAD], r[I_LIVES]))
            if W.mem.bank == 0 and W.mpu.pc == W.PC_STARTFRAME:
                break


def probe(clock, x=None, y=None):
    pins.update(clock=clock)
    if x is not None:
        pins["x"] = x
    if y is not None:
        pins["y"] = y
    run_frames(1)
    return samples[-1]


def main() -> None:
    fails = []
    boot()
    W.load_room(4)
    # C11 (2026-10-21): stage the frozen $82 record as synthetic RAM data and
    # point RoomRects at it (a shape block carries no record stream any more).
    for _i, _b in enumerate(FX.M4_STREAM):
        W.mem.ram[STREAM_ADDR + _i - 0x80] = _b
    W.mem.ram[I_RRLO] = STREAM_ADDR & 0xFF
    W.mem.ram[I_RRHI] = STREAM_ADDR >> 8
    W.mem.ram[I_M1HOT] = 0                # no hot-band M1 block cell
    W.mem.ram[0x1A] = 0                   # $9A RoomMetaB: cold (no hot sweep)

    # Patch the record's y and w in the PRIVATE bank copy: fields must be
    # ignored (band stays 1, prefix stays 10).
    off = STREAM_ADDR
    count = W.mem.ram[off - 0x80]          # record count (C11: features only)
    rec = off + 1                          # first record's class byte
    assert count and W.mem.ram[rec - 0x80] == 0x82, (
        f"fixture class {W.mem.ram[rec - 0x80]:02X}")
    W.mem.ram[rec + 2 - 0x80] = 2          # y(band) -> 2 (ignored)
    W.mem.ram[rec + 3 - 0x80] = 4          # w -> 4 cells (ignored)
    assert rec + 4 <= off + 1 + 5, "record stride changed"

    # --- 1. arm + ignored record fields ---------------------------------
    pf0, pf1, pf2, dead, _lv = probe(clock=8)
    if (pf0, pf1, pf2) != P_TRIPLE[1]:
        fails.append(f"arm: PF band1=${pf0:02X}/${pf1:02X}/${pf2:02X}, want "
                     f"$30/00/00 (dwell P(1), fixed band1)")
    if W.mem.ram[PF0_B2] != 0xF0:
        fails.append(f"arm: band2 PF0=${W.mem.ram[PF0_B2]:02X}, want $F0 "
                     f"(record y=2 must be ignored)")
    if dead & 0x80:
        fails.append("arm: EnemyDeadMask b7 set (removed latch)")
    print(f"  arm: PF0b1=${pf0:02X} (P(1)); record y/w ignored; b7 clear")

    # --- 2/3/4. curve + bucket stability + dwell ------------------------
    got = []
    for s in range(16):
        base = s * 16
        m = probe(base + 8)
        l = probe(base + 15)
        n = covered(base + 8)
        want = P_TRIPLE[n]
        got.append(N_OF.get(tuple(m[:3]), 0))
        if (m[0], m[1], m[2]) != want:
            fails.append(f"curve s={s:2d}: PF=${m[0]:02X}/${m[1]:02X}/"
                         f"${m[2]:02X}, want "
                         f"${want[0]:02X}/${want[1]:02X}/${want[2]:02X} "
                         f"(n={n}) — HcrClock drift")
        if l[:3] != m[:3]:
            fails.append(f"stable s={s:2d}: PF changed inside a 16f bucket")
    print(f"  curve: n[s0..15]={got}")
    run = 0
    i = 0
    while i < 16 and got[i] == 1:
        run += 1
        i += 1
    if run < 3:
        fails.append(f"dwell: contiguous n==1 run = {run} buckets < 3")
    # --- 5/6. kill + re-kill (no latch) ---------------------------------
    def expect_kill(tag, clock, x, y, frames=6):
        pins.update(clock=clock, x=x, y=y)
        W.mem.ram[I_DEAD] = 0
        W.mem.ram[I_LIVES] = 3
        run_frames(frames)
        took = W.mem.ram[I_LIVES] < 3      # no latch: may fire repeatedly
        dead = W.mem.ram[I_DEAD]
        if not took:
            fails.append(f"{tag}: no life lost (clock={clock} x={x} y={y})")
        if dead & 0x80:
            fails.append(f"{tag}: b7 latch written (must be removed)")
        if took and not (dead & 0x80):
            print(f"  {tag}: kill, b7 clear (clock={clock} x={x} y={y})")
        return took

    expect_kill("kill  ", clock=8, x=8, y=68)
    expect_kill("rekill", clock=8, x=8, y=68)     # no latch -> kills again
    expect_kill("open  ", clock=240, x=8, y=68)   # retract half: still hot
    expect_kill("sealed", clock=192, x=38, y=68)  # n=10 reaches center

    # --- 9/10/11. gates -------------------------------------------------
    def expect_clear(tag, clock, x, y, frames=6):
        pins.update(clock=clock, x=x, y=y)
        W.mem.ram[I_DEAD] = 0
        W.mem.ram[I_LIVES] = 3
        run_frames(frames)
        if W.mem.ram[I_LIVES] != 3:
            fails.append(f"{tag}: killed (clock={clock} x={x} y={y}) — "
                         f"gate failed")
        else:
            print(f"  {tag}: no kill (clock={clock} x={x} y={y})")

    # N=4: a 36-line band is shorter than the 22 px player box + gap, so
    # y must keep the whole box inside band 0 (rows 5..10 = idx < 9).
    expect_clear("band0", clock=8, x=0, y=12)
    expect_clear("band2", clock=192, x=0, y=116)
    expect_clear("nohit", clock=8, x=70, y=68)

    # --- 12. no growth push ---------------------------------------------
    def probe_push(clock, x, y):
        pins.update(clock=clock, x=x, y=y)

        def poke_ni():
            r = W.mem.ram
            W.mem.swcha = 0xFF
            r[I_ROOMX] = pins["x"]
            r[I_ROOMY] = pins["y"]
            r[I_VYLO] = 0
            r[I_VYHI] = 0
            r[W.I_ENCOUNT] = 0
            r[I_RAMP] = pins["clock"]
        for _ in range(2):
            poke_ni()
            while True:
                W.step()
                if W.mem.bank == 0 and W.mpu.pc == W.PC_STARTFRAME:
                    break
        return W.mem.ram[I_ROOMX]

    for tag, px in (("left", 5), ("right", 150)):
        got_x = probe_push(0x80, px, 68)
        if got_x != px:
            fails.append(f"nopush/{tag}: RoomX={got_x}, want {px} (HcrPush "
                         f"removed)")
    print("  nopush: grow edge leaves RoomX untouched (left + right)")

    # --- 13. static: no record reads, no push, stride kept --------------
    b3 = (SRC / "bank3.asm").read_text()  # C7: the crunch walkers are bank3
    ph = b3[b3.index("PhHcrEntry:"):]
    ph = ph[:ph.index("; Prefix tables")]
    if "(FetchPtr),Y" in ph:
        fails.append("PhHcrEntry still reads record fields")
    hov = b3[b3.index(".HFh_begin:"):]
    hov = hov[:hov.index(".HFkill:")]
    if "(FetchPtr),Y" in hov or "LineCount" in hov:
        fails.append("the $82 HOV handler still reads record fields")
    if "HcrPush:" in b3:
        fails.append("HcrPush still present")
    stream = FX.M4_STREAM
    # C4: hot count at +0, first record class at +1 (5 B records).
    if len(stream) < 6 or stream[0] != 1 or stream[1] != 0x82:
        fails.append("fixture record stride/class changed")

    if fails:
        print(f"\nFAIL: {len(fails)}")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("test_hcrunch: OK (fixed band1/10 prefix, always hot, no push, "
          "no latch)")


if __name__ == "__main__":
    main()
