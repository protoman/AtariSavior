#!/usr/bin/env python3
"""Visual eyeball strip for the hcrunch retune (plan step D).

Stella scripts cannot drive console-switch edges (no SWCHB setter, no
read-back), so the shutter's motion is rendered from the SAME py65
harness path test_hcrunch uses: boot -> load_room(4) -> one pinned frame
per bucket s=0..15 (clock = s*16+8) -> PF buffers at the HUD fold ->
PNG grid.

A correct strip shows (grow-to-center retune, user 2026-10-16):
  tiles s0..s3  : dwell at home — stub prefix (n=1, col0+mirror col39)
  tiles s4..s12 : grow by one 8px cell per 16f step toward the CENTER
                  (n = 1+min(s-3, full-1); s12 = full = 10 cells = the
                  left half up to the screen seam)
  tiles s13..s15: fast retract (eff 3*(15-s) = 6,3,0) back to the stub
  => n = [1,1,1,1,2,3,4,5,6,7,8,9,10,7,4,1] (HcrClock; mirrors
  test_hcrunch.covered).

Run: /home/iuri/python3/bin/python3 tools/render_shutter_frames.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import test_hcrunch as T
import test_laser_walk_wall as W

OUT = W.SRC / "screenshots" / "hcrunch" / "retune_curve.png"

BG = (10, 10, 16)
WALL = (70, 200, 90)
PLAYER = (240, 240, 240)
LABEL = (210, 210, 210)

# PF cell model (same masks as W.cell_solid — reflected playfield)
PF_ADDRS = (0xC3, 0xC6, 0xC9)          # PF0/1/2 band0 base; band1 = +1
BAND_H = 48
TILE_W, TILE_H = 160, 144              # cave only (3 bands x 48)


def cell_lit(pf0, pf1, pf2, d):
    """left-half cell d (0..19) lit for display col computed via mirror."""
    src = d if d < 20 else 39 - d
    if src < 4:
        return bool(pf0 & (0x10 << src))
    if src < 12:
        return bool(pf1 & (0x80 >> (src - 4)))
    return bool(pf2 & (0x01 << (src - 12)))


def draw_tile(img, x0, y0, pf, px, py):
    """pf = 9 bytes (PF0/1/2 x band0/1/2), px/py = player top-left."""
    dr = ImageDraw.Draw(img)
    for band in range(3):
        pf0, pf1, pf2 = pf[3 * band], pf[3 * band + 1], pf[3 * band + 2]
        for d in range(40):
            if not cell_lit(pf0, pf1, pf2, d):
                continue
            dr.rectangle(
                (x0 + d * 4, y0 + band * BAND_H,
                 x0 + d * 4 + 3, y0 + (band + 1) * BAND_H - 1),
                fill=WALL)
    if 0 <= py < TILE_H:
        dr.rectangle((x0 + px, y0 + py,
                      x0 + px + 7, y0 + min(py + 11, TILE_H - 1)),
                     fill=PLAYER)


def main() -> None:
    T.boot()
    W.load_room(4)

    pins = {"x": 70, "y": 20, "clock": 8}

    def poke():
        r = W.mem.ram
        W.mem.swcha = 0xFF                # no input: player pinned, no walk
        r[T.I_ROOMX] = pins["x"]
        r[T.I_ROOMY] = pins["y"]
        r[T.I_VYLO] = 0
        r[T.I_VYHI] = 0
        r[W.I_ENCOUNT] = 0
        r[T.I_RAMP] = pins["clock"]

    # settle: 2 frames so VBL StageBandTab rebuilds from M4 MetaA
    samples = []
    T.run_frames(2, poke, samples)

    frames = []
    for s in range(16):
        pins["clock"] = s * 16 + 8
        samples = []
        T.run_frames(1, poke, samples)
        r = W.mem.ram
        pf = [r[(a + band) & 0x7F]
              for band in range(3) for a in PF_ADDRS]   # band-major 9B
        frames.append((s, pf, pins["clock"]))

    lab, pad = 16, 4
    tile_h = TILE_H + lab
    img = Image.new("RGB", (4 * (TILE_W + pad), 4 * (tile_h + pad)), BG)
    for i, (s, pf, clock) in enumerate(frames):
        col, row = i % 4, i // 4
        x0 = col * (TILE_W + pad)
        y0 = row * (tile_h + pad)
        draw_tile(img, x0, y0, pf, pins["x"], pins["y"])
        n = T.covered(clock)
        ImageDraw.Draw(img).text(
            (x0 + 4, y0 + TILE_H + 2),
            f"s={s:2d} clock={clock:3d} n={n}", fill=LABEL)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
