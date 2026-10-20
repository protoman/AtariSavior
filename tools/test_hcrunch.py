#!/usr/bin/env python3
"""hcrunch shutter tests ($82 prefix shutter — contract-first, py65).

Model4 (level 3 room 2, frozen fixture) carries the $82 record at band1
sweep cols 0-19 (x=0, y=1, w=20, h=1, full = w>>1 = 10 cells = the whole
left half up to the screen center). PhaseBlink stages the covered prefix
into PF band1 every VBL (PhHcrEntry: row & ~P(full) | P(n), n = clock
covered cells); the kill path is the record walk (HotOverlapBody
.HOVfeature -> HOVFeatPre -> bank3 HOVhcrunch).

Motion contract (user ruling 2026-10-16, grow-to-center):
  s = EnemyRamP>>4  -> 16f/step, 256f cycle;
  dwell s 0-3 (64f at home) ; eff = s-3 (grow 1..9, s 4..12 = to center) ;
  eff = 3*(15-s) (fast retract s 13..15 = 6,3,0 — wipe home);
  covered = 1 + min(eff, full-1)  -> stub >= 1 ALWAYS.
The test's `covered()` mirror IS this contract.

Cold growth push (user 2026-10-16): while the prefix ADVANCES (s4-12,
cold, player box overlapping the band) PhHcrEntry -> HcrPush clamps
RoomX out of the covered px ([RoomX-7,RoomX] vs [0,8n)+mirror
[160-8n,160)) so a cold shutter cannot trap. Sealed (n>=10, no
aperture) skips the push. Hot (MetaB b6) never pushes.

Kill rule (user 2026-10-16): cold kill while CLOSING (sc<52 == s<13 =
dwell+grow) at ANY extent — the old totally-closed exemption is gone
(it froze a cornered player at the seal; push prevents the approach,
the seal-moment catch is the crunch). Hot exempts — any phase/extent
kills. Opening (sc>=52) never kills. Frozen M4 MetaB = $00 (cold only).

Cases:
   1. arm     — after load: PhaseBlink ran, PF band1 staged $30 at clock 8
                 (dwell n=1 — also proves staging is live: the raw fixture
                 row is $F0);
   2. curve   — pinned clock s*16+8 for s 0..15: PF0/1/2 band1 must
                 equal P(covered()) (full triples, $30 stub .. $F0/FF/FF
                 center);
   3. stable  — n(s*16+8) == n(s*16+15): covered may change ONLY on 16f
                 boundaries;
   4. dwell   — the n==1 run straddling cycle start >= 3 buckets = 48f
                 contiguous at home (new curve gives 5 = 80f);
   5. kill    — clock 8 (dwell, n=1 < full, push inactive), x=0 y=68
                 band1: PHM HIT -> $82 -> b7 latch + LoseLife;
   6. rearm   — latch blocks re-kill (lives stay 2), EnterRoom-style
                 clear re-arms (latch fires again);
   7. sealed  — clock 192 (s12, n=10 == full): catch at the seal KILLS
                 (cold+closing+caught at any extent);
   8. opening — clock 240 (s15, sc>=52): no kill (retract half);
   9. band0   — y=20: dispatch runs, band gate rejects -> no latch;
  10. nohit   — x=70 y=68: nothing solid under the box -> no latch;
  11. pushL   — clock 80 (s5 n=3), x=5 y=68 no input: RoomX clamped to
                 8n+7 = 31 (out of the left prefix);
  12. pushR   — clock 80, x=150: mirror prefix [136,159) -> RoomX = 135;
   13. noPush  — dwell (clock 8) / retract (clock 224) / band0 (y=20):
                 RoomX untouched;
   14. spent   — b7 crunch-kill latch set: PF band1 frozen at the home
                 stub P(1) at any clock (no more animation after a kill);
   15. hot-nopush — MetaB b6 (hot) suppresses HcrPush (RoomX untouched);
   16. hot-kill   — MetaB b6 (hot) kills at the OPENING phase too (cold
                 case 8 = no kill), i.e. any extent.

Staging samples are taken at the `jmp $FC68` HUD fold (VBL staging
done, bank1's $EA-$EF stomp not yet run — PF buffers $C3-$CB are
outside the stomp zone anyway).

Run: /home/iuri/python3/bin/python3 tools/test_hcrunch.py
"""
import re
import sys
from pathlib import Path

import test_laser_walk_wall as W

SRC = W.SRC
FROZEN = W.SRC / "tests" / "frozen"   # test-owned banks+labels

import test_fixtures as FX          # noqa: E402
FX.freeze_m4(W.BANKS, W.L3)         # frozen model4 (user rule 2026-10-14)

# ZP indices (addr & 0x7F)
I_ROOMX, I_ROOMY = W.I_ROOMX, W.I_ROOMY
I_VYLO, I_VYHI = W.I_VYLO, W.I_VYHI
I_DEAD = W.I_DEAD                       # $BA EnemyDeadMask (b7 = kill latch)
I_RAMP = 0x42                           # $C2 EnemyRamP frame clock
I_LIVES = 0x2C                          # $AC PlayerLives

# HUD fold: first bank0->bank1 fold after the cave kernel — VBL staging
# is still the frame's (bank1 stomps $EA-$EF only after entering HUD).
HUD_JMP = None
for _l in (FROZEN / "bank0.lst").read_text(errors="replace").splitlines():
    _code = _l.split(";")[0]           # drop lst comment (no jmp/$FC68 mix)
    if "jmp" in _code and "$FC68" in _code:
        _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})", _l)
        if _m:
            HUD_JMP = int(_m.group(1), 16)
            break
if HUD_JMP is None:
    sys.exit("bank0.lst: `jmp $FC68` not found")

# PF buffer band1 rows (PF0Buf $C3, +3 PF1, +6 PF2 — ZP index = addr & 0x7F)
PF0_B1, PF1_B1, PF2_B1 = 0xC4 & 0x7F, 0xC7 & 0x7F, 0xCA & 0x7F
FULL = 10                               # fixture record w=20 -> full cells

# P(n) = (PF0,PF1,PF2) prefix masks for n covered cells (mirror of
# bank3 CrPfx0/1/2 — change both together).
P_TRIPLE = {
    1: (0x30, 0x00, 0x00), 2: (0xF0, 0x00, 0x00), 3: (0xF0, 0xC0, 0x00),
    4: (0xF0, 0xF0, 0x00), 5: (0xF0, 0xFC, 0x00), 6: (0xF0, 0xFF, 0x00),
    7: (0xF0, 0xFF, 0x03), 8: (0xF0, 0xFF, 0x0F), 9: (0xF0, 0xFF, 0x3F),
    10: (0xF0, 0xFF, 0xFF),
}
N_OF = {v: k for k, v in P_TRIPLE.items()}


def covered(clock: int) -> int:
    """Python mirror of the RETUNED contract (HcrClock, grow-to-center).
    Change bank3 and this together — the curve case fails when they
    disagree."""
    s = (clock >> 4) & 15
    if s < 4:
        eff = 0                         # home dwell, s 0-3
    elif s < 13:
        eff = s - 3                     # grow 1..9 (to center)
    else:
        eff = 3 * (15 - s)              # fast retract 6,3,0
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


def run_frames(n, pins, samples):
    """n frames with pins poked at each StartFrame; append
    (PF0b1, PF1b1, PF2b1, DeadMask, Lives) at every HUD fold."""
    for _ in range(n):
        pins()
        while True:
            W.mpu.step()
            if W.mem.bank == 0 and W.mpu.pc == HUD_JMP:
                r = W.mem.ram
                samples.append((r[PF0_B1], r[PF1_B1], r[PF2_B1],
                                r[I_DEAD], r[I_LIVES]))
            if W.mem.bank == 0 and W.mpu.pc == W.PC_STARTFRAME:
                break


def main() -> None:
    fails = []
    boot()
    W.load_room(4)                     # model4 ($82 band1 shutter)

    pins = {"x": 70, "y": 20, "clock": 8}

    def poke():
        # I_DEAD is NOT poked per frame — the kill latch is set at
        # overscan and would be wiped before the next HUD-fold sample.
        # Right press drives PlayerHitsMap every frame (walk -> HIT ->
        # HotOverlapBody); with vy pinned and no input the player never
        # moves and the walk never runs.
        r = W.mem.ram
        W.mem.swcha = 0x7F                # P0 right (active low D7)
        r[I_ROOMX] = pins["x"]
        r[I_ROOMY] = pins["y"]
        r[I_VYLO] = 0
        r[I_VYHI] = 0
        r[W.I_ENCOUNT] = 0
        r[I_RAMP] = pins["clock"]

    def set_dead(v):
        W.mem.ram[I_DEAD] = v

    def probe(clock, x=None, y=None):
        """1 pinned frame -> (pf0b1, pf1b1, pf2b1, dead, lives)."""
        pins.update(clock=clock)
        if x is not None:
            pins["x"] = x
        if y is not None:
            pins["y"] = y
        samples = []
        run_frames(1, poke, samples)
        return samples[-1]

    # --- settle: 2 frames so VBL StageBandTab rebuilds from M4 MetaA ----
    samples = []
    run_frames(2, poke, samples)

    # --- case 1: arm/staging --------------------------------------------
    # y20/band0 x70 keeps the walk off the kill path during staging
    # checks (a latch would block re-kill for the rest of the visit).
    pf0, pf1, pf2, dead, _lv = probe(clock=8)
    if pf0 != 0x30:
        fails.append(f"arm: PF0 band1=${pf0:02X}, want $30 (dwell n=1 "
                     f"staged; $F0 = raw fixture row, PhHcrEntry never ran)")
    if pf1 != 0x00 or pf2 != 0x00:
        fails.append(f"arm: PF1/2 band1=${pf1:02X}/${pf2:02X}, want $00/$00")
    if dead & 0x80:
        fails.append("arm: kill latch set at settle (y20 band0 must not kill)")
    print(f"  arm: PF0b1=${pf0:02X} (staged dwell n=1)")

    # --- case 2: curve (grow-to-center contract) ------------------------
    mid_n, late_n = [], []
    for s in range(16):
        base = s * 16
        m = probe(base + 8)
        l = probe(base + 15)
        n = covered(base + 8)
        want = P_TRIPLE[n]
        mid_n.append((m[0], m[1], m[2]))
        late_n.append((l[0], l[1], l[2]))
        if (m[0], m[1], m[2]) != want:
            fails.append(f"curve s={s:2d} (clock {base+8:3d}): PF band1="
                         f"${m[0]:02X}/${m[1]:02X}/${m[2]:02X}, want "
                         f"${want[0]:02X}/${want[1]:02X}/${want[2]:02X} "
                         f"(n={n}) — clock formula drift")
        # case 3 (stability): same bucket must not change covered
        if l[:3] != m[:3]:
            fails.append(f"stable s={s:2d}: PF ${m[0]:02X}/${m[1]:02X}/"
                         f"${m[2]:02X} @clock{base+8} -> ${l[0]:02X}/"
                         f"${l[1]:02X}/${l[2]:02X} @clock{base+15} — covered "
                         f"changed inside a 16f bucket")
    got = [N_OF.get(p, 0) for p in mid_n]
    print(f"  curve: n[s0..15]={got}")

    # --- case 4: home dwell >= 48f (3 buckets) straddling cycle start ---
    run = 0
    i = 15                              # walk backward from s0 (cyclic)
    while got[i % 16] == 1 and run < 16:
        run += 1
        i -= 1
    i = 0                               # forward from s0
    while i < 16 and got[i] == 1:
        run += 1
        i += 1
    if run < 3:
        fails.append(f"dwell: contiguous n==1 run = {run} buckets = "
                     f"{run*16}f at cycle start, want >=3 buckets = 48f")
    else:
        print(f"  dwell: n==1 run = {run} buckets = {run*16}f >= 48f")
    if 0 in got:
        fails.append(f"dwell: unrecognized PF0 in curve samples "
                     f"{got} (n_of=0 — staging wrote neither $30 nor $F0)")

    # --- case 5: dwell kill (x0 y68 band1, n=1 < full) ------------------
    pins.update(x=0, y=68, clock=8)
    set_dead(0x00)
    W.mem.ram[I_LIVES] = 3
    samples = []
    run_frames(6, poke, samples)
    if not any(s[3] & 0x80 for s in samples):
        fails.append("kill: no latch (clock 8 dwell, x0 y68) — record walk "
                     "or HOVhcrunch gates failed")
    else:
        lv = W.mem.ram[I_LIVES]
        if lv != 2:
            fails.append(f"kill: PlayerLives={lv}, want 2 (LoseLife ran — "
                         f"Temp b7 end-to-end)")
        else:
            print("  kill: latch set + lives 3->2 (clock 8, x0 y68)")

    # --- case 6: latch blocks re-kill; clear re-arms --------------------
    samples = []
    run_frames(4, poke, samples)         # latch still set (NOT poked)
    if W.mem.ram[I_LIVES] != 2:
        fails.append(f"rearm: lives={W.mem.ram[I_LIVES]} after 4 latched "
                     f"frames, want 2 (b7 must block a second kill)")
    set_dead(0x00)                       # EnterRoom-style clear
    W.mem.ram[I_LIVES] = 3
    samples = []
    run_frames(6, poke, samples)
    if not any(s[3] & 0x80 for s in samples):
        fails.append("rearm: no latch after EnemyDeadMask clear — b7 "
                     "one-kill-per-room contract broken")
    elif W.mem.ram[I_LIVES] != 2:
        fails.append(f"rearm: lives={W.mem.ram[I_LIVES]}, want 2")
    else:
        print("  rearm: b7 blocks re-kill; clear re-arms (second kill ok)")

    # --- cases 7-13: kill-at-seal / no-kill guards / growth push --------
    def expect_clear(tag, clock, x, y, frames=6):
        pins.update(clock=clock, x=x, y=y)
        set_dead(0x00)
        samples = []
        run_frames(frames, poke, samples)
        if any(s[3] & 0x80 for s in samples):
            fails.append(f"{tag}: latch set (clock={clock} x={x} y={y}) — "
                         f"gate failed")
        else:
            print(f"  {tag}: no kill (clock={clock} x={x} y={y})")

    # --- case 7: sealed catch kills (s12, n=10 == full, push sealed) ----
    # (the old "totally closed = wall" no-kill is gone — it froze a
    # cornered player inside the seal; user 2026-10-16)
    pins.update(x=0, y=68, clock=192)
    set_dead(0x00)
    W.mem.ram[I_LIVES] = 3
    samples = []
    run_frames(6, poke, samples)
    if not any(s[3] & 0x80 for s in samples):
        fails.append("sealed: no latch (clock 192, n=full, x0 y68) — "
                     "cold+closing+caught must kill at the seal")
    elif W.mem.ram[I_LIVES] != 2:
        fails.append(f"sealed: PlayerLives={W.mem.ram[I_LIVES]}, want 2")
    else:
        print("  sealed: catch at the seal kills (clock 192, n=10)")

    expect_clear("opening", clock=240, x=0, y=68)   # s15 sc>=52 (retract)
    expect_clear("band0  ", clock=8, x=0, y=20)     # dispatch + band gate
    expect_clear("nohit  ", clock=8, x=70, y=68)    # no PHM HIT -> no walk

    # --- cases 11-13: cold growth push ----------------------------------
    def probe_push(clock, x, y, frames=2):
        """No-input frames (walk idle) — push is VBL-side. Returns RoomX."""
        pins.update(clock=clock, x=x, y=y)

        def poke_ni():
            r = W.mem.ram
            W.mem.swcha = 0xFF            # no direction: walk never runs
            r[I_ROOMX] = pins["x"]
            r[I_ROOMY] = pins["y"]
            r[I_VYLO] = 0
            r[I_VYHI] = 0
            r[W.I_ENCOUNT] = 0
            r[I_RAMP] = pins["clock"]
        run_frames(frames, poke_ni, [])
        return W.mem.ram[I_ROOMX]

    got_x = probe_push(clock=0x80, x=5, y=68)       # s8, n=6: prefix [0,47)
    if got_x != 55:
        fails.append(f"pushL: RoomX={got_x}, want 55 (8n+7, n=6)")
    else:
        print("  pushL: RoomX 5 -> 55 (grow n=6, left prefix)")
    got_x = probe_push(clock=0x80, x=150, y=68)
    if got_x != 111:
        fails.append(f"pushR: RoomX={got_x}, want 111 (159-8n, n=6)")
    else:
        print("  pushR: RoomX 150 -> 111 (mirror prefix [113,159))")
    ok_nopush = True
    for tag, clk, px, py in (("dwell", 8, 5, 68), ("retract", 224, 5, 68),
                             ("band0", 0x80, 5, 20)):
        got_x = probe_push(clock=clk, x=px, y=py)
        if got_x != px:
            fails.append(f"noPush/{tag}: RoomX={got_x}, want {px} "
                         f"(clock={clk} y={py} must not push)")
            ok_nopush = False
    if ok_nopush:
        print("  noPush: dwell/retract/band0 leave RoomX untouched")

    # --- case 14: spent latch freezes the shutter at the stub -----------
    # After the crunch kills (EnemyDeadMask b7 latched), the prefix must
    # STOP at n=1 (min width) for the rest of the room visit instead of
    # continuing to animate (user 2026-10-16). clock=0x80 (s8) would be
    # n=6 if live; b7 must force the stub.
    pins.update(x=70, y=20, clock=0x80)      # band0: keep the walk off
    set_dead(0x80)
    m = probe(clock=0x80)
    set_dead(0x00)
    if (m[0], m[1], m[2]) != P_TRIPLE[1]:
        fails.append(f"spent: PF band1=${m[0]:02X}/${m[1]:02X}/${m[2]:02X}, "
                     f"want ${P_TRIPLE[1][0]:02X}/00/00 — b7 latch must freeze "
                     f"the shutter at the home stub (min width)")
    else:
        print("  spent: b7 latch freezes the shutter at the stub (min width)")

    # --- cases 15-16: hot (MetaB b6) semantics --------------------------
    # Hot hcrunch: the shutter kills at ANY extent and NEVER pushes. Both
    # M4 hcrunch rooms are cold, so this path is untested live — inject b6
    # into the frozen fixture's MetaB byte (TilePF0+10) and probe.
    # MetaB is STAGED in ZP at room entry ($9A) — patch the staged byte,
    # not the ROM copy (the ROM is not re-read after entry).
    W.mem.ram[0x9A & 0x7F] = 0x40         # MetaB b6 = hot
    # 15: hot never pushes (cold pushL at clock 0x80 -> 55)
    set_dead(0x00)
    got_x = probe_push(clock=0x80, x=5, y=68)
    if got_x != 5:
        fails.append(f"hot-nopush: RoomX={got_x}, want 5 (MetaB b6 hot "
                     f"must suppress HcrPush)")
    else:
        print("  hot-nopush: b6 hot suppresses HcrPush (no clamp)")
    # 16: hot kills at the OPENING phase too (cold case 8 = no kill)
    pins.update(x=0, y=68, clock=240)
    set_dead(0x00)
    W.mem.ram[I_LIVES] = 3
    samples = []
    run_frames(6, poke, samples)
    if not any(s[3] & 0x80 for s in samples):
        fails.append("hot: no latch (clock 240 opening) — hot must kill at "
                     "ANY extent (b6 exemption)")
    elif W.mem.ram[I_LIVES] != 2:
        fails.append(f"hot: PlayerLives={W.mem.ram[I_LIVES]}, want 2")
    else:
        print("  hot-kill: opening-phase catch kills when hot (b6)")
    W.mem.ram[0x9A & 0x7F] = 0x00         # restore cold

    if fails:
        print(f"\nFAIL: {len(fails)}")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("test_hcrunch: OK (16 cases)")


if __name__ == "__main__":
    main()
