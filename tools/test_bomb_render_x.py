#!/usr/bin/env python3
"""Bomb render X regression (user report 2026-10-16):

The bomb is a GRP1 object drawn 1-of-4 frames (shared with enemies/miner).
Commit ac4c3ee moved the bomb's SetObjectXPos out of the VBL into the drop
only, so on the frames the bomb was drawn SelectActiveObject set
ActiveObjectX = BombX but never repositioned P1 — the enemy/miner frame had
already moved P1, so the bomb rendered at the last object's X (looked
pinned near the room's other object). Collision always used BombX, so only
the SPRITE was wrong.

Contract: on a bomb-draw frame, SetObjectXPos is called with (A=BombX, X=1)
(the .SODone tail positions P1 from ActiveObjectX for every object path).

Boots to the gameplay room (has an enemy so non-bomb frames move P1), then
forces a bomb-draw frame (BombPacked state=1, BombTimer&3==0) for two BombX
values and records every SetObjectXPos call. Run:
  /home/iuri/python3/bin/python3 tools/test_bomb_render_x.py
"""
import sys

import test_laser_walk_wall as W

SOXP = 0xFF0F                       # SetObjectXPos (jsr target, pinned)


def boot_to_landed():
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


def bomb_frame_calls(bombx):
    """One bomb-draw frame -> [(A, X), ...] of every SetObjectXPos call."""
    r = W.mem.ram
    r[0x76] = bombx                    # BombX ($F6)
    r[0x35] = (r[0x35] & 0xFC) | 0x01  # BombPacked state = 1
    r[0x77] = 0x00                     # BombTimer = 0 -> (BombTimer&3)==0 drawn
    r[0x01] = 68                       # RoomY
    r[0x00] = 70                       # RoomX
    calls = []
    while True:
        W.mpu.step()
        if W.mem.bank == 0 and W.mpu.pc == SOXP:
            calls.append((W.mpu.a, W.mpu.x))
        if W.mem.bank == 0 and W.mpu.pc == W.PC_STARTFRAME:
            break
    return calls


def main() -> None:
    boot_to_landed()                   # room 1 has an enemy (moves P1 off-band)
    fails = []
    for bombx in (40, 100):
        calls = bomb_frame_calls(bombx)
        if (bombx, 1) not in calls:
            fails.append(f"BombX={bombx}: P1 not positioned at BombX "
                         f"(SetObjectXPos calls={calls}) — bomb draws at a "
                         f"stale object X")
        else:
            print(f"  BombX={bombx}: P1 positioned at BombX (calls={calls})")
    if fails:
        print(f"\nFAIL: {len(fails)}")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("test_bomb_render_x: OK (bomb sprite follows BombX on draw frames)")


if __name__ == "__main__":
    main()
