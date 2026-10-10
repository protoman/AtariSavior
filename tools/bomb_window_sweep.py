#!/usr/bin/env python3
"""BombX window sweep — diagnostic, NOT in the battery (no test_ prefix).

Maps which bomb x positions actually punch the model1 thin wall (rect
span [12,13]) — past vs after the 2026-10-10 BMW span-overlap fix:

  punch range = fold 10..15 (span overlap within the +-2 window);
  fold >= 16 = bomb 3+ cols from the wall = correct miss.

Run: /home/iuri/python3/bin/python3 tools/bomb_window_sweep.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import test_bomb_half_wall as T  # noqa: E402

mem, mpu = T.mem, T.mpu
PC_STARTFRAME = T.PC_STARTFRAME


def boot():
    guard = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        T.step()
        guard += 1
        if guard > 400000:
            sys.exit("never reached StartFrame")
    landed = None
    while T.frame < 400:
        T.step()
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            mem.swchb = 0xFE if T.frame in (2, 5) else 0xFF
            if mem.ram[T.I_BOMBP] & 0x80:
                landed = T.frame
                break
    if landed is None:
        sys.exit("player never landed")
    mem.ram[T.I_DEAD] = 0xFF
    print(f"landed f{landed}")


def punches(bombx: int) -> bool:
    """One blast at bombx. True iff PF2 row1 ($CA) bits0-1 cleared."""
    roomx = 0 if bombx >= 60 else 140
    T.load_room(1)
    before = mem.ram[0x4A]
    mem.ram[T.I_BOMBX] = bombx
    mem.ram[T.I_ROOMX] = roomx
    mem.ram[T.I_ROOMY] = 70
    mem.ram[T.I_BOMBSND] = 0
    mem.ram[T.I_BOMBP] = 0x01
    mem.ram[T.I_BOMBT] = 2
    T.watch = True
    T.snap = [mem.ram[a] for a in T.PF_IDX]
    start = len(T.writes)
    T.start_frame = T.frame
    bmw = None
    limit = T.start_frame + 8
    while bmw is None and T.frame < limit:
        T.pin(70)
        T.step()
        if mem.bank == 1 and mpu.pc == T.PC_BMW:
            bmw = T.frame
    if bmw is None:
        T.watch = False
        return False, before, mem.ram[0x4A], 0
    end = bmw + 3
    while T.frame < end:
        T.pin(70)
        T.step()
    T.watch = False
    n = len(T.writes) - start
    return (mem.ram[0x4A] & 0x03) == 0, before, mem.ram[0x4A], n


def main():
    boot()
    print("bombx col fold hit?  CA before->after  pf_writes")
    for bombx in range(36, 136, 4):
        hit, b, a, n = punches(bombx)
        col = (bombx - 7) >> 2
        fold = col if col < 20 else 39 - col
        print(f"  {bombx:3d}  c{col:02d} f{fold:02d}  "
              f"{'PUNCH' if hit else 'MISS '}  "
              f"${b:02X}->${a:02X}  {n}")

    # focused cases
    print("\nstand-on-wall cases:")
    for bombx in (48, 52, 56, 104, 108, 111, 115):
        hit, b, a, n = punches(bombx)
        col = (bombx - 7) >> 2
        fold = col if col < 20 else 39 - col
        print(f"  bombx={bombx:3d} col={col:02d} fold={fold:02d} "
              f"{'PUNCH' if hit else 'MISS'} CA ${b:02X}->${a:02X}")


if __name__ == "__main__":
    main()
