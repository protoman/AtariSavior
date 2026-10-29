#!/usr/bin/env python3
"""Gameplay video of the real ROM: the playbot flies levels, tools/tia_render.py draws
every frame, ffmpeg encodes an H.264 mp4 (silent: there is no audio model).

  make_video.py [LEVEL ...] [--out FILE] [--fps 60] [--rom-dir DIR]     (default levels 2 6 12 18)

Each level gets a 3 s title card, then plays at 60 frames a second until the rescue
tally has counted. Lives are shown as 3 (the bot's cheat top-up is 8; deaths are real
but free).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402
import tia_render as T  # noqa: E402

W, H = 960, 600
SCALE = (6, 3)
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
BLURB = {2: "Reach the miner", 6: "Bats, hot rock and phase walls",
         12: "A flooded room: ride the raft", 18: "Crushers, rafts and three miners"}


def font(size):
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


class Sink:
    """Pipes RGB frames to ffmpeg."""

    def __init__(self, out, fps):
        self.p = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264",
             "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
        self.n = 0

    def image(self, img, repeat=1):
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        canvas.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
        data = canvas.tobytes()
        for _ in range(repeat):
            self.p.stdin.write(data)
        self.n += repeat

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def card(lines, sizes):
    img = Image.new("RGB", (W, H), (8, 8, 16))
    d = ImageDraw.Draw(img)
    total = sum(sizes) + 14 * (len(lines) - 1)
    y = (H - total) // 2
    for text, size, col in lines:
        f = font(size)
        w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill=col)
        y += size + 14
    return img


class VideoMixin:
    """Every ROM frame the pilot asks for is rendered and written."""
    sink = None

    def frame(self, swcha=P.NONE, fire=False):
        rows = self.render(self.tia_frame(swcha, fire))
        if self.sink is not None and rows:
            self.sink.image(T.rows_to_image(rows, SCALE))


def play_level(n, stage, sink, rom_dir):
    con = P.Console(rom_dir)
    con.boot(n)
    cls = type("VideoConsole", (VideoMixin, T.TiaConsole, type(con)), {})
    con.__class__ = cls
    con.tia_init()
    for _ in range(3):                       # warm the beam state up (not recorded)
        con.tia_frame()
    con.sink = sink
    lv = P.Level(stage, n)

    class Pilot(P.Pilot):
        def step(self, sw=P.NONE):
            super().step(sw)
            self.c.w("PlayerLives", 3)

    pilot = Pilot(con, lv, False, False)
    pilot.start_frames = con.frames
    pilot.budget = 9000
    pilot.hover = False
    try:
        pilot.play(9000)
    except P.Done:
        pass
    for _ in range(330):                     # the rescue bonus counts up
        con.frame(P.NONE, False)
    return con.frames


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int, default=[2, 6, 12, 18])
    ap.add_argument("--out", default=str(ROOT / "releases" / "savior-1.0.0-gameplay.mp4"))
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--rom-dir")
    a = ap.parse_args()
    stage = json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]
    sink = Sink(a.out, a.fps)
    gold, cream = (220, 180, 60), (235, 235, 235)
    sink.image(card([("S.A.V.I.O.R.", 96, (180, 140, 240)),
                     ("Atari 2600  -  version 1.0.0", 36, cream),
                     ("Gameplay: the joystick-only test bot flying the real ROM", 24, gold)],
                    [96, 36, 24]), a.fps * 4)
    for n in a.levels:
        sink.image(card([(f"LEVEL {n}", 84, gold), (BLURB.get(n, ""), 34, cream)], [84, 34]),
                   a.fps * 3)
        frames = play_level(n, stage, sink, a.rom_dir)
        print(f"level {n}: {frames} frames", flush=True)
    sink.image(card([("S.A.V.I.O.R. 1.0.0", 72, (180, 140, 240)),
                     ("NTSC  -  PAL60  -  PAL", 36, cream),
                     ("by Iuri Fiedoruk", 30, gold)], [72, 36, 30]), a.fps * 4)
    sink.close()
    print(f"-> {a.out}  ({sink.n} frames, {sink.n / a.fps:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
