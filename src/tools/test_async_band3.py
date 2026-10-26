#!/usr/bin/env python3
"""Async strips in BAND 3 (the bottom band) — data + ROM guard.

Why it exists (2026-10-24, N=4 follow-up): the async ball gate (MetaA b0-2) has
three bits for four bands, so `B3StageBand` ended its staging with a BRIDGE
(`lda BandTab+2 / sta BandTab+3`) — band 3 mirrored band 2. That was fine while
band 3 was a copy of row 2, but the current 3-row migration maps a model to
[band0, band1, AIR, band2], i.e. the authored BOTTOM row now lives in band 3
while band 2 is the inserted AIR band. A bottom-row strip therefore enabled the
ball in the empty middle band too (a strip drawn where no cell is patched) and
its own band worked only through the mirror.

Fix under test: MetaB b4 is the band-3 gate.
  - converter: the extras patch byte stores the BAND (b7-6), not the authored
    row, and a band-3 patch sets MetaB b4 instead of MetaA b2;
  - `B3StageBand`: BandTab+3 is staged from MetaB b4 (no mirror);
  - the collision pack ($8F b0-3) carries four gate bits, so a band-3 strip
    kills (`OvHead/OvTail` grew a 4th entry in bank0 and bank2).

Cases: (1) a row-2 patch emits MetaA b2 clear + MetaB b4 set + band 3 in the
patch byte; (2) the ROM stages BandTab+3 from MetaB b4 and leaves BandTab+2
dark; (3) an old-style MetaA b2 gate no longer leaks into band 3.

Frozen banks + labels (src/tests/frozen/) only — never the live build.
Run: /home/iuri/python3/bin/python3 tools/test_async_band3.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import convert_level  # noqa: E402
from test_cell_map import Mem, RTS_SENTINEL, parse_labels, BANK0, BANK3  # noqa: E402
from py65.devices.mpu6502 import MPU  # noqa: E402

FROZEN = ROOT / "tests" / "frozen"

# --- 1. converter layer ----------------------------------------------------
# Synthetic 10x3 model (same fixture family as test_asym_data): band 0 and
# band 2 open, band 1 wall cols 0-7 so the patch mirror sits on a wall.
TILES = [0] * 10 + [1] * 8 + [0, 0] + [0] * 10
MODEL = {"id": 90, "width": 10, "height": 3, "tiles": TILES}
ROOM = {"room_id": 0, "asym_patches": [[2, 0, 1]]}   # row 2 (bottom), col 0


def extras_bytes(room=ROOM):
    rows = convert_level.rows_from_json({"model_id": MODEL["id"]},
                                        {MODEL["id"]: MODEL})
    rec, _nfeat = convert_level.room_extras(room, MODEL, rows, "test")
    flags = rec[0]
    assert flags & 0x03 == 1, f"flags ${flags:02x}: want 1 patch"
    return rec[1], rec[2], rec[3]        # MetaA, MetaB, patch byte


# --- 2. ROM layer ----------------------------------------------------------
NEED3 = {"B3StageBand", "RoomMetaA", "RoomMetaB", "BandTab",
         "EnemyDeadMask", "RoomRectsLo", "RoomRectsHi"}
L3 = parse_labels(FROZEN / "bank3.lst", NEED3)
missing = NEED3 - L3.keys()
if missing:
    sys.exit(f"frozen bank3 labels missing: {sorted(missing)}")
Z = {k: v & 0x7F for k, v in L3.items() if 0x80 <= v <= 0xFF}


def stage(meta_a, meta_b):
    """Run the REAL B3StageBand once -> {0..3: BandTab byte}."""
    mem = Mem()
    r = mem.ram
    r[Z["RoomMetaA"]] = meta_a
    r[Z["RoomMetaB"]] = meta_b
    r[Z["EnemyDeadMask"]] = 0
    r[Z["RoomRectsLo"]] = 0x00          # hot record stream: count 0 -> done
    r[Z["RoomRectsHi"]] = 0x00
    mpu = MPU(memory=mem)
    mem.bank = 3
    mpu.pc = L3["B3StageBand"]
    mpu.a = mpu.x = mpu.y = 0
    mpu.sp = 0xFD
    ret = (RTS_SENTINEL - 1) & 0xFFFF      # rts adds 1
    mem[0x1FF] = ret >> 8                  # PCH sits at the higher address
    mem[0x1FE] = ret & 0xFF                # PCL (rts pulls SP+1 first)
    for _ in range(4000):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            break
    else:
        raise AssertionError("B3StageBand never returned (no rts sentinel)")
    base = Z["BandTab"]
    return {band: r[(base + band) & 0x7F] for band in range(4)}


def main() -> int:
    # --- case 1: a row-2 patch is a BAND-3 patch ------------------------
    meta_a, meta_b, patch = extras_bytes()
    assert patch >> 6 == 3, (
        f"patch byte ${patch:02x} stores band {patch >> 6}, want 3 — the "
        "extras patch field must hold the BAND (a 3-row model maps row 2 to "
        "band 3, band 2 is the inserted AIR band)")
    assert meta_a & 0x04 == 0, (
        f"MetaA ${meta_a:02x} still carries the band-2 gate for a bottom-row "
        "patch — that enables the ball in the AIR band")
    assert meta_b & 0x10, (
        f"MetaB ${meta_b:02x} has no band-3 gate (b4) for a bottom-row patch")
    print(f"  case 1 OK: MetaA ${meta_a:02x} MetaB ${meta_b:02x} "
          f"patch band {patch >> 6}")

    # --- case 2: the ROM stages band 3 from MetaB b4 --------------------
    got = stage(meta_a, meta_b)
    assert got[3] == 0xFF, (
        f"BandTab+3 = ${got[3]:02x}, want $ff — B3StageBand ignored the "
        "band-3 gate (MetaB b4)")
    assert got[2] == 0x00, (
        f"BandTab+2 = ${got[2]:02x}, want $00 — the ball is enabled in the "
        "AIR band, straight from the retired band-2 mirror")
    assert got[0] == 0x00 and got[1] == 0x00, f"BandTab 0/1 = {got}"
    print(f"  case 2 OK: bands {[hex(got[b]) for b in range(4)]}")

    # --- case 3: an old-style band-2 gate must not leak into band 3 -----
    got = stage(0x04, 0x01)               # b2 gate + a ball column
    assert got[2] == 0xFF and got[3] == 0x00, (
        f"bands {[hex(got[b]) for b in range(4)]}: a band-2 gate must stay "
        "in band 2 (the mirror is gone)")

    # --- case 4: no gate at all, no ball -> every band dark -------------
    got = stage(0x00, 0x00)
    assert set(got.values()) == {0x00}, f"bands {[hex(got[b]) for b in range(4)]}"

    # --- case 5: the collision tables carry 4 bands ---------------------
    sig = bytes([15, 14, 12, 8, 1, 3, 7, 15])     # OvHead 0-3, OvTail 0-3
    assert BANK0.find(sig) >= 0, (
        "kernel OvHead/OvTail are not the 4-band pair 15,14,12,8 / 1,3,7,15 — "
        "a 3-row table makes a band-3 strip pass-through (X=3 reads past it)")
    from test_cell_map import BANK2
    assert BANK2.find(sig) >= 0, (
        "bank2's OvHead/OvTail copy ($FFE6) is not the 4-band pair — its "
        "walkers gate band 3 on the wrong bits")
    print("  cases 3-5 OK: no mirror, 4-band gate tables in bank0/bank2")

    print("test_async_band3: OK (band-3 gate: data + ROM staging + tables)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
