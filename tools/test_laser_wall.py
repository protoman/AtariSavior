#!/usr/bin/env python3
"""Laser travel-budget end-to-end probe (py65, assert-based) — redesign.

Boots savior.bin headless, waits until the player lands, kills all enemies
(no interference), then for BOTH facings sweeps the player across X (fire
held; RoomY pinned + vy zeroed each frame so inputs are deterministic) and
checks every frame against an independent travel state machine
(contact-missile redesign 2026-10-08):

  model (held fire): cand = LaserX +/- 4 (facing); cand >= 160 (left
    underflow wrap) or cand past the old-sweep cap (right > RoomX+20,
    left < max(RoomX-20,0)) -> restart at the eye; else cand.
    eye = right min(RoomX+4,159) / left RoomX-4.
    rearm (LaserState b0, 2026-10-10): a contact consume sets b0 — the
    NEXT held frame re-tests the eye instead of stepping (flush hold:
    eye mid-tile, +4 would jump out of the 8px wall with no candidate
    ever inside it). b0 is captured at LaserInput's rts (inc runs at
    .LaserContact, before the rts): rearm frame want = eye(RoomX)
    (.LaserInit recomputes the eye from the live RoomX) and LaserX ==
    eye on every rearm frame.
  capture at LaserInput's rts:
    CollisionX ($8B) must EQUAL the model's next travel value — it is
      staged from the post-travel LaserX before the hit test and contact
      never moves it (the old mid-wall clamp retired with the sweep);
    LaserX ($83) must be in {model_next, eye} — the eye = the body
      legitimately consumed the missile this frame (wall cell, ball
      strip, kill/lamp) and reset it. Anything else = travel escaped the
      budget (the user regression: beam "moved way beyond the limit").
  the model re-syncs to the captured LaserX every frame (contacts are not
    modeled — they collapse to "actual = eye").

Model 0's M1/ball-band meta and the hot-rect count are zeroed in THIS
run's ROM image so strip/hot resets never masquerade as travel; plain
wall/cell contact stays and is covered by the eye allowance. Enemies are
frozen dead (DeadMask=$FF) = no kill/lamp resets either.

Run: /home/iuri/python3/bin/python3 tools/test_laser_wall.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FROZEN = SRC / "tests" / "frozen"   # test-owned banks+labels
BANKS = [bytearray(open(FROZEN / f"bank{i}.bin", "rb").read()) for i in range(4)]

# Phase 4: model 0 is the asymmetric test room — force its meta symmetric
# in THIS run's ROM image so no strip contact fires (MetaA nibble 0 skips
# the LWC M1 tip test; MetaB 0 keeps the ball strip out of the marker path).
# C5 (2026-10-20): model 0's MetaA/MetaB live in the level's async-extras
# record (ordinal 1 -> +1/+2) — zero them so no strip contact fires. The hot
# count is the block's FIRST byte now (C4).
_EX = None
_M0RR = None
for _l in (FROZEN / "bank2.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+(LEVEL1_AsyncExtras|"
                  r"M0RoomRects)\s*$", _l)
    if _m:
        if _m.group(2) == "LEVEL1_AsyncExtras":
            _EX = int(_m.group(1), 16)
        else:
            _M0RR = int(_m.group(1), 16)
assert _EX is not None and _M0RR is not None, "bank2 level labels missing"
BANKS[2][_EX + 1 - 0xF000] = 0
BANKS[2][_EX + 2 - 0xF000] = 0
BANKS[2][_M0RR - 0xF000] = 0                  # hot count = 0

# labels from bank0.lst (addresses move every commit)
LABELS = {}
for _l in (FROZEN / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", _l)
    if _m:
        LABELS[_m.group(2)] = int(_m.group(1), 16)
PC_STARTFRAME = LABELS["StartFrame"]

# ZP indices (addr & 0x7F)
I_ROOMX, I_ROOMY, I_DIR, I_LASERX = 0x00, 0x01, 0x02, 0x03  # $83 = LaserX
I_BOMBP, I_DEADMASK = 0x35, 0x3A
I_VYLO, I_VYHI = 0x13, 0x14
I_COLLX = 0x0B                  # $8B
I_LSTATE = 0x40                 # $C0 LaserState — b0 rearm captured at rts

# LaserInput's own rts sites: capture CollisionX/LaserX there (between
# LHT and those rts only SetObjectXPos / AddScore run — neither writes
# $83/$8B; enemies are all dead in the probe = miss path).
RANGE_LO = LABELS["LaserInput"]
# end marker: TallyTramp ($FFE6+) — BeamMask no longer works (it moved to
# the $FExx hole, BELOW LaserInput, when the aligned color table landed)
RANGE_HI = LABELS.get("TallyTramp", 0xFFF0)
rts_pcs = set()
for _l in (FROZEN / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+(?:[0-9a-f]{2}[ \t]+)+rts\b", _l)
    if _m:
        a = int(_m.group(1), 16)
        if RANGE_LO <= a < RANGE_HI:
            rts_pcs.add(a)
assert rts_pcs, "no LaserInput rts found in bank0.lst"


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x00          # fire HELD from boot (probe wants the beam)

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return BANKS[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            return 0
        if a == 0x000C:
            return self.inpt4
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF6 <= a <= 0x1FF9:
            self.bank = a - 0x1FF6
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]


mem = Mem()
from py65.devices.mpu6502 import MPU  # noqa: E402
mpu = MPU(memory=mem)


def step():
    mpu.step()


def eye_of(roomx, facing):
    """Reset/press-edge anchor: right min(RoomX+4,159) / left RoomX-4."""
    if facing == 0:
        return min(roomx + 4, 159)
    return roomx - 4


def travel_next(lx, roomx, facing):
    """One held frame of bank0 LaserInput travel (no contact)."""
    if facing == 0:
        nt = lx + 4
        cap = roomx + 20                 # old sweep extent: RoomX+4+16
    else:
        nt = (lx - 4) & 0xFF
        cap = max(roomx - 20, 0)
    if nt >= 160:                        # right edge / left underflow
        return eye_of(roomx, facing)
    if facing == 0 and nt > cap:
        return eye_of(roomx, facing)
    if facing == 1 and nt < cap:
        return eye_of(roomx, facing)
    return nt


def main() -> None:
    # ---- boot to the main frame loop ----
    guard = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        guard += 1
        if guard > 400000:
            sys.exit(f"never reached StartFrame (pc=${mpu.pc:04X})")

    frame = 0
    landed = None
    # ---- wait for landing, then freeze enemies ----
    while frame < 400:
        step()
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            frame += 1
            # console RESET pulses (intro 2026-10-06): f2 edge leaves the
            # $FD intro, f5 edge hits TitleWork RESET -> game start
            mem.swchb = 0xFE if frame in (2, 5) else 0xFF
            if mem.ram[I_BOMBP] & 0x80:
                landed = frame
                break
    if landed is None:
        sys.exit("player never landed (BombPacked OnGround)")
    mem.ram[I_DEADMASK] = 0xFF                 # kill all enemies (no interference)

    y0 = mem.ram[I_ROOMY]
    print(f"landed f{landed}: RoomY={y0}")

    # ---- deterministic sweep: pin RoomX/Y, dir, vy; fire held ----
    mismatches = []
    checked = 0
    contacts = 0
    model = None                              # re-synced every frame
    rearm = False                             # b0 from the previous rts
    for facing in (0, 1):
        for x in range(4, 156):
            for _ in range(4):                # 4 frames = cap-loop steps
                mem.ram[I_ROOMX] = x
                mem.ram[I_ROOMY] = y0
                mem.ram[I_DIR] = facing
                mem.ram[I_VYLO] = 0
                mem.ram[I_VYHI] = 0
                cap = None
                # run to next frame boundary; capture at LaserInput's rts
                while True:
                    step()
                    if mpu.pc in rts_pcs:
                        cap = (mem.ram[I_COLLX], mem.ram[I_LASERX],
                               mem.ram[I_LSTATE] & 0x01)
                    if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
                        break
                checked += 1
                if cap is None:
                    mismatches.append(f"X={x} dir={facing}: no LaserInput rts")
                    continue
                cx, lx, b0 = cap
                eye = eye_of(x, facing)
                if model is None:             # first captured frame: seed
                    model = lx
                    rearm = bool(b0)
                    continue
                if rearm:
                    want = eye                # rearm: .LaserInit -> eye(RoomX)
                else:
                    want = travel_next(model, x, facing)
                if cx != want:
                    mismatches.append(
                        f"X={x} dir={facing}: CollisionX=${cx:02X} "
                        f"!= travel model ${want:02X} (model prev=${model:02X})")
                if lx not in (want, eye):
                    mismatches.append(
                        f"X={x} dir={facing}: LaserX=${lx:02X} escaped "
                        f"budget (want ${want:02X} or eye ${eye:02X})")
                if lx == eye and want != eye:
                    contacts += 1             # body consumed the missile
                model = lx                    # re-sync (contact collapses)
                rearm = bool(b0)              # this frame's inc -> next want
    if mismatches:
        print(f"FAIL: {len(mismatches)} mismatched frames "
              f"(contact-missile travel budget):")
        for m in mismatches[:15]:
            print("  " + m)
        if len(mismatches) > 15:
            print(f"  ... and {len(mismatches) - 15} more")
        sys.exit(1)
    print(f"test_laser_wall: OK ({checked} frames, {contacts} contact "
          f"resets to the eye, travel inside the old sweep extent)")


if __name__ == "__main__":
    main()
