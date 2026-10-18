#!/usr/bin/env python3
"""Render a QA room to PNG from the live simulation state (no Stella).

Used by tools/qa_sweep.py when QA_SHOTS=1 is set in the environment: the sweep
drives the real ROM with the joystick, and after each room's assertions this
module draws what the cave currently looks like — playfield cells straight from
the PF buffers, the player box, the bottom-band water colour, plus a caption
line with the state the buffers cannot show (door M1 x, shutter BallX).

Why: the Phase-6 sweep needs a picture set, but Stella cannot reach gameplay
from a script (the intro waits for a real RESET edge), so the sim state IS the
camera. Sprite-based hazards (M1 door stripe, vcrunch shutter) are annotated in
the caption instead of drawn — they are not in the playfield buffers.

Run (from the repo root, after bash tools/qa_build.sh):
  QA_SHOTS=1 /home/iuri/python3/bin/python3 tools/qa_sweep.py
"""
from pathlib import Path

from PIL import Image, ImageDraw  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src"
OUT = SRC / "screenshots" / "qa"

BAND_H = 48
TILE_W, TILE_H = 160, 144          # the 3-band cave only
BG = (10, 10, 16)
WALL = (113, 35, 0)                # the live level-1 brown
WALL2 = (134, 61, 11)
PLAYER = (240, 240, 240)
DOOR = (230, 230, 62)              # COLUP1 yellow stripe
WATER = (30, 90, 200)
CAPTION = (210, 210, 210)
PF_ADDRS = (0xC3, 0xC6, 0xC9)      # PF0/1/2 band0 base; band row = +row
I_ROOMY, I_ROOMNO = 0x01, 0x18


def cell_lit(pf0: int, pf1: int, pf2: int, d: int) -> bool:
    """Display column d (0..39) lit? Reflected playfield: mirror the right."""
    src = d if d < 20 else 39 - d
    if src < 4:
        return bool(pf0 & (0x10 << src))
    if src < 12:
        return bool(pf1 & (0x80 >> (src - 4)))
    return bool(pf2 & (0x01 << (src - 12)))


def save(path: Path, mem, note: str = "", water: bool = False) -> Path:
    """PNG of the current cave state (PF buffers + player box) + caption."""
    r = mem.ram
    pf = [[r[(a + band) & 0x7F] for a in PF_ADDRS] for band in range(3)]
    room_y = r[I_ROOMY]
    band_row = min(room_y // BAND_H, 2)
    room_x = r[0x00]

    lab, pad = 14, 4
    width = max(250, TILE_W + 2 * pad)
    img = Image.new("RGB", (width, TILE_H + lab + 2 * pad), BG)
    dr = ImageDraw.Draw(img)
    # bottom_band (water): the last 12 scanlines of band 2, open cells only —
    # exactly what COLUBK does in the room (bottom_band_plan rule 2/3).
    band_color = water                        # bottom_band from the CALLER: RoomBandColor
                                              # ($D2) aliases PF1Buf[3] (a dead row the
                                              # loader also writes), so a RAM peek lies
    for band in range(3):
        pf0, pf1, pf2 = pf[band]
        for d in range(40):
            lit = cell_lit(pf0, pf1, pf2, d)
            if not lit and band == 2 and band_color:
                # open cell inside the water strip (scanlines 132-143)
                dr.rectangle((pad + d * 4, pad + 132,
                              pad + d * 4 + 3, pad + 143), fill=WATER)
                continue
            if not lit:
                continue
            shade = WALL if band != 1 else WALL2
            dr.rectangle((pad + d * 4, pad + band * BAND_H,
                          pad + d * 4 + 3, pad + (band + 1) * BAND_H - 1),
                         fill=shade)
    # player box [RoomX-7, RoomX] x [RoomY, RoomY+11] (the collision contract)
    px = pad + max(0, room_x - 7)
    py = pad + room_y
    dr.rectangle((px, py, min(px + 7, pad + TILE_W - 1),
                  min(py + 11, pad + TILE_H - 1)), fill=PLAYER)
    dr.text((pad, pad + TILE_H + 2),
            f"room {r[I_ROOMNO]} x={room_x} y={room_y} band={band_row} "
            f"water={'on' if band_color else 'off'} "
            f"{note}".strip()[:44], fill=CAPTION)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path
