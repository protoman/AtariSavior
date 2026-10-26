#!/usr/bin/env python3
"""Builds the S.A.V.I.O.R. instruction manual (PDF), in the spirit of the
classic Atari 2600 cartridge booklets.

Sprites are read straight from kernel.asm (ObjSprites / ObjColorTab /
PlayerSpriteA / PlayerColTable), so the pictures follow the art in the ROM.

Run:  python3 docs/manual/build_manual.py     ->  docs/manual/savior_manual.pdf
"""
import re
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib.colors import Color, HexColor, white, black
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

SRC = Path(__file__).resolve().parents[2]
OUT = SRC / "docs" / "manual" / "savior_manual.pdf"
KERNEL = (SRC / "kernel.asm").read_text()
SHOT_HUD = SRC / "screenshots" / "releases" / "0.8" / "002.png"
SHOT_TITLE = SRC / "screenshots" / "releases" / "0.8" / "001.png"

PAGE = (5.5 * inch, 8.5 * inch)          # half-letter booklet
MARGIN = 0.5 * inch

NAVY = HexColor("#101a33")
ORANGE = HexColor("#e8742a")
GOLD = HexColor("#f2b632")
CREAM = HexColor("#fbf4e2")
INK = HexColor("#1d1d24")
GREY = HexColor("#6c6c78")

# ---------------------------------------------------------------- palette ---
HUES = {0: (130, 130, 130), 1: (200, 180, 40), 2: (210, 130, 40),
        3: (220, 100, 60), 4: (210, 70, 80), 5: (190, 70, 150),
        6: (140, 70, 190), 7: (100, 80, 200), 8: (70, 100, 210),
        9: (60, 150, 220), 10: (60, 180, 200), 11: (60, 190, 150),
        12: (70, 190, 90), 13: (130, 190, 70), 14: (180, 180, 60),
        15: (200, 140, 80)}


def tia(b):
    """TIA colour byte (hue<<4 | luma<<1) -> reportlab colour."""
    hue, lum = (b >> 4) & 15, (b & 15) / 14.0
    if hue == 0:
        v = int(30 + 225 * lum)
        return Color(v / 255, v / 255, v / 255)
    r, g, bl = HUES[hue]
    f = 0.35 + 0.8 * lum
    return Color(min(1, r * f / 255), min(1, g * f / 255), min(1, bl * f / 255))


# ------------------------------------------------------------ ROM art data ---
def bytes_of(line):
    out = []
    for tok in re.split(r"[,\s]+", line.split(";")[0].replace(".byte", "")):
        tok = tok.strip()
        if tok.startswith("$"):
            out.append(int(tok[1:], 16))
        elif tok.startswith("%"):
            out.append(int(tok[1:], 2))
    return out


def block(start_label, stop_label):
    lines = KERNEL.split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith(start_label))
    data = []
    for l in lines[i + 1:]:
        if l.startswith(stop_label) or (l and not l[0].isspace() and ":" in l
                                        and not l.startswith(";")):
            break
        if ".byte" in l:
            data += bytes_of(l)
    return data


OBJ_GFX = block("ObjSprites:", "; Enemy type")
OBJ_COL = block("ObjColorTab:", "; ----")
_ls = KERNEL.split("\n")
_i = next(k for k, l in enumerate(_ls) if l.startswith("PlayerSpriteA:"))
PLAYER_GFX = [v for l in _ls[_i + 1:_i + 23] for v in bytes_of(l)]
PLAYER_COL = block("PlayerColTable:", "; UEPrologue")


def part(offset, rows):
    return OBJ_GFX[offset:offset + rows], OBJ_COL[offset:offset + rows]


ART = {
    "key": part(0, 12), "cell": part(12, 4), "moth": part(16, 14),
    "spider": part(30, 15), "lamp": part(45, 10), "tentacle": part(55, 14),
    "bat": part(69, 10), "snake": part(79, 6), "miner": part(85, 9),
    "bomb": part(101, 8), "raft": part(109, 2),
}


class Sprite(Flowable):
    """An Atari player drawn pixel by pixel (8 columns wide)."""

    def __init__(self, gfx, col, px=4.0, wide=1.0):
        super().__init__()
        self.gfx, self.col, self.px, self.wide = gfx, col, px, wide
        self.width = 8 * px * wide
        self.height = len(gfx) * px

    def draw(self):
        c, rows = self.canv, len(self.gfx)
        for r, (g, cb) in enumerate(zip(self.gfx, self.col)):
            c.setFillColor(tia(cb))
            for bit in range(8):
                if g & (0x80 >> bit):
                    c.rect(bit * self.px * self.wide,
                           (rows - 1 - r) * self.px,
                           self.px * self.wide + 0.2, self.px + 0.2,
                           stroke=0, fill=1)


def sprite(name, px=4.0):
    return Sprite(*ART[name], px=px)


def player(px=3.0):
    return Sprite(PLAYER_GFX, PLAYER_COL, px=px)


# ------------------------------------------------------------------ styles ---
def style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.2, leading=12.6,
                textColor=INK, spaceAfter=5)
    base.update(kw)
    return ParagraphStyle(name, **base)


BODY = style("body")
SMALL = style("small", fontSize=8, leading=10.5, textColor=GREY)
H1 = style("h1", fontName="Helvetica-Bold", fontSize=19, leading=22,
           textColor=NAVY, spaceAfter=3, spaceBefore=0)
H2 = style("h2", fontName="Helvetica-Bold", fontSize=11, leading=14,
           textColor=ORANGE, spaceBefore=8, spaceAfter=3)
CAP = style("cap", fontName="Helvetica-Bold", fontSize=8.4, leading=10.5,
            textColor=NAVY, spaceAfter=1)
CELLT = style("cell", fontSize=8.6, leading=11.2, spaceAfter=0)
BUL = style("bul", leftIndent=12, bulletIndent=2, spaceAfter=3)
CENTER = style("center", alignment=1)


class Rule(Flowable):
    def __init__(self, w, color=ORANGE, t=2.4):
        super().__init__()
        self.w, self.color, self.t = w, color, t
        self.width, self.height = w, t + 4

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 2, self.w, self.t, stroke=0, fill=1)


def head(title, kicker):
    return [Paragraph(kicker.upper(), style(
        "k", fontName="Helvetica-Bold", fontSize=7.6, textColor=GREY,
        spaceAfter=1, leading=9)),
        Paragraph(title, H1), Rule(PAGE[0] - 2 * MARGIN), Spacer(1, 5)]


def bullets(items):
    return [Paragraph(t, BUL, bulletText="•") for t in items]


def entry(art, title, text, w=PAGE[0] - 2 * MARGIN, art_w=0.62 * inch):
    """A picture on the left, a title and a paragraph on the right."""
    t = Table([[art, [Paragraph(title, CAP), Paragraph(text, CELLT)]]],
              colWidths=[art_w, w - art_w])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor("#d8cfb8"))]))
    return t


class Swatch(Flowable):
    """Small drawn picture of a piece of cave."""

    def __init__(self, kind, w=0.5 * inch, h=0.46 * inch):
        super().__init__()
        self.kind, self.width, self.height = kind, w, h

    def draw(self):
        c, w, h, k = self.canv, self.width, self.height, self.kind
        wall, wall2 = HexColor("#b0750f"), HexColor("#8c5a0a")
        c.setStrokeColor(black)
        c.setLineWidth(0.4)
        if k == "wall":
            c.setFillColor(wall)
            c.rect(0, 0, w, h, fill=1)
            c.setFillColor(wall2)
            c.rect(0, 0, w, h * 0.45, stroke=0, fill=1)
        elif k == "hot":
            c.setFillColor(HexColor("#d63a28"))
            c.rect(0, 0, w, h, fill=1)
            c.setFillColor(HexColor("#f08c28"))
            for i in range(4):
                c.rect(i * w / 4 + 2, 3 + (i % 2) * 5, w / 8, h / 3, stroke=0, fill=1)
        elif k == "door":
            c.setFillColor(wall)
            c.rect(0, 0, w, h, fill=1)
            c.setFillColor(HexColor("#e8c430"))
            c.rect(w * 0.4, 0, w * 0.2, h, stroke=0, fill=1)
        elif k == "phase":
            c.setFillColor(wall)
            c.rect(w * 0.3, 0, w * 0.4, h, fill=1)
            c.setDash(2, 2)
            c.setFillColor(white)
            c.rect(w * 0.3, 0, w * 0.4, h, fill=0)
            c.setDash()
        elif k == "crunch":
            c.setFillColor(HexColor("#101010"))
            c.rect(0, 0, w, h, fill=1)
            c.setFillColor(wall)
            c.rect(0, 0, w * 0.45, h, stroke=0, fill=1)
            c.setStrokeColor(white)
            c.line(w * 0.5, h / 2, w * 0.85, h / 2)
            c.line(w * 0.78, h / 2 + 4, w * 0.85, h / 2)
            c.line(w * 0.78, h / 2 - 4, w * 0.85, h / 2)
        elif k == "water":
            c.setFillColor(HexColor("#101010"))
            c.rect(0, 0, w, h, fill=1)
            c.setFillColor(HexColor("#1c48b0"))
            c.rect(0, 0, w, h * 0.45, stroke=0, fill=1)
        elif k == "thin":
            c.setFillColor(HexColor("#101010"))
            c.rect(0, 0, w, h, fill=1)
            c.setFillColor(wall)
            c.rect(w * 0.42, 0, w * 0.16, h, stroke=0, fill=1)
        elif k == "dark":
            c.setFillColor(HexColor("#080808"))
            c.rect(0, 0, w, h, fill=1)
            c.setFillColor(HexColor("#606060"))
            c.rect(w * 0.35, h * 0.2, w * 0.3, h * 0.6, stroke=0, fill=1)
        elif k == "raft":
            c.setFillColor(HexColor("#101010"))
            c.rect(0, 0, w, h, fill=1)
            c.setFillColor(HexColor("#1c48b0"))
            c.rect(0, 0, w, h * 0.35, stroke=0, fill=1)
            c.setFillColor(tia(0xC4))
            c.rect(w * 0.2, h * 0.35, w * 0.6, h * 0.2, stroke=0, fill=1)


# ------------------------------------------------------------- HUD diagram ---
class HudShot(Flowable):
    """The real screenshot with numbered call-outs."""

    MARKS = [  # (number, x, y) in screenshot pixels
        (1, 320, 323), (2, 70, 337), (3, 604, 337),
        (4, 110, 357), (5, 604, 357), (6, 305, 385)]

    def __init__(self, width):
        super().__init__()
        self.sw = width
        self.scale = width / 640.0
        self.width, self.height = width, 394 * self.scale

    def draw(self):
        c = self.canv
        c.drawImage(str(SHOT_HUD), 0, 0, self.width, self.height)
        for n, x, y in self.MARKS:
            cx, cy = x * self.scale, self.height - y * self.scale
            c.setFillColor(GOLD)
            c.setStrokeColor(black)
            c.circle(cx, cy, 6.2, fill=1)
            c.setFillColor(black)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(cx, cy - 2.8, str(n))
        # call-out for the player
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.2)
        c.rect(213 * self.scale, self.height - 124 * self.scale,
               36 * self.scale, 50 * self.scale)


class Joystick(Flowable):
    def __init__(self, w=3.9 * inch, h=2.35 * inch):
        super().__init__()
        self.width, self.height = w, h

    def draw(self):
        c = self.canv
        cx, cy = 1.0 * inch, self.height / 2 + 2
        c.setFillColor(HexColor("#2b2b33"))
        c.roundRect(cx - 0.62 * inch, cy - 0.62 * inch, 1.24 * inch,
                    1.24 * inch, 10, fill=1, stroke=0)
        c.setFillColor(black)
        c.circle(cx, cy, 0.26 * inch, fill=1, stroke=0)
        c.setStrokeColor(HexColor("#c0c0c8"))
        c.setLineWidth(3)
        c.line(cx, cy, cx, cy + 0.42 * inch)
        c.setFillColor(HexColor("#d63a28"))
        c.circle(cx, cy + 0.46 * inch, 0.1 * inch, fill=1, stroke=0)
        c.setFillColor(HexColor("#d63a28"))
        c.roundRect(cx + 0.3 * inch, cy - 0.57 * inch, 0.24 * inch, 0.12 * inch,
                    3, fill=1, stroke=0)
        arrows = [("UP", cx, cy + 0.92 * inch, "Jet pack: rise"),
                  ("DOWN", cx, cy - 0.86 * inch, "Drop a bomb"),
                  ("LEFT", cx - 0.97 * inch, cy, "Fly left"),
                  ("RIGHT", cx + 0.97 * inch, cy, "Fly right")]
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(NAVY)
        for lbl, x, y, _ in arrows:
            c.drawCentredString(x, y, lbl)
        # legend column
        x0 = 2.35 * inch
        y = self.height - 0.15 * inch
        rows = [("Stick UP", "Fire the jet pack. Hold it to climb; let go and you float, then fall."),
                ("Stick LEFT / RIGHT", "Fly sideways. The way you face is the way the laser fires."),
                ("Stick DOWN", "Drop a bomb (only while you stand on the ground)."),
                ("Red button", "Fire the helmet laser, straight ahead.")]
        for t, d in rows:
            c.setFont("Helvetica-Bold", 8)
            c.setFillColor(ORANGE)
            c.drawString(x0, y, t)
            y -= 10.5
            p = Paragraph(d, style("j", fontSize=8, leading=10, spaceAfter=0))
            w_, h_ = p.wrap(1.5 * inch, 100)
            p.drawOn(c, x0, y - h_ + 8)
            y -= h_ + 6


# ---------------------------------------------------------- page templates ---
def cover(c, doc):
    w, h = PAGE
    c.setFillColor(NAVY)
    c.rect(0, 0, w, h, stroke=0, fill=1)
    # cave silhouette
    c.setFillColor(HexColor("#7a3a10"))
    c.rect(0, h - 1.5 * inch, 1.4 * inch, 1.5 * inch, stroke=0, fill=1)
    c.rect(w - 1.1 * inch, h - 1.2 * inch, 1.1 * inch, 1.2 * inch, stroke=0, fill=1)
    c.rect(2.1 * inch, h - 0.9 * inch, 0.9 * inch, 0.9 * inch, stroke=0, fill=1)
    c.setFillColor(HexColor("#c9692a"))
    c.rect(0, 0, 2.2 * inch, 1.35 * inch, stroke=0, fill=1)
    c.rect(w - 2.2 * inch, 0, 2.2 * inch, 1.35 * inch, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(0, 1.35 * inch, w, 0.08 * inch, stroke=0, fill=1)

    c.setFillColor(HexColor("#b48cf0"))
    c.setFont("Helvetica-Bold", 31)
    c.drawCentredString(w / 2, h - 3.0 * inch, "S.A.V.I.O.R.")
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(w / 2, h - 3.35 * inch, "I N S T R U C T I O N   M A N U A L")
    c.setFillColor(CREAM)
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, h - 3.7 * inch,
                        "Dive into the caves. Bring every miner home.")
    c.setFont("Helvetica-Oblique", 8.4)
    c.drawCentredString(w / 2, 0.75 * inch,
                        "A game cartridge for the Atari 2600™ Video Computer System™")
    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, 0.55 * inch, "© 2026 Iuri Fiedoruk")
    # the hero flying, and a miner waiting
    for sp, x, y in ((player(5.2), w / 2 - 20, h - 2.05 * inch),
                     (sprite("miner", 5.2), w - 1.85 * inch, 1.55 * inch)):
        sp.canv = c
        c.saveState()
        c.translate(x, y)
        sp.draw()
        c.restoreState()


def inside(c, doc):
    w, h = PAGE
    c.setFillColor(CREAM)
    c.rect(0, 0, w, h, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.rect(0, 0, w, 0.36 * inch, stroke=0, fill=1)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(MARGIN, 0.14 * inch, "S.A.V.I.O.R.")
    c.setFillColor(CREAM)
    c.drawRightString(w - MARGIN, 0.14 * inch, str(doc.page))


# ----------------------------------------------------------------- content ---
def story():
    W = PAGE[0] - 2 * MARGIN
    s = []

    # ---- contents / getting started
    s += head("Getting started", "Before you fly")
    s += [Paragraph(
        "Plug the cartridge into your console <b>with the power switched off</b>, "
        "plug a joystick controller into the <b>left controller jack</b>, then "
        "switch the console on. The title screen appears with the letters "
        "<b>S.A.V.I.O.R.</b> and your pilot hanging in the cave above them.", BODY)]
    s += [Table([[Paragraph("<b>SELECT</b>", CELLT),
                  Paragraph("On the title screen, each press picks the next level. "
                            "The level number is shown in the score window.", CELLT)],
                 [Paragraph("<b>RESET</b>", CELLT),
                  Paragraph("Starts the game with a score of 000000, three lives "
                            "and five bombs.", CELLT)]],
                colWidths=[0.9 * inch, W - 0.9 * inch],
                style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("BACKGROUND", (0, 0), (0, -1), HexColor("#efe2bd")),
                                  ("BOX", (0, 0), (-1, -1), 0.5, GREY),
                                  ("INNERGRID", (0, 0), (-1, -1), 0.4, HexColor("#d8cfb8")),
                                  ("TOPPADDING", (0, 0), (-1, -1), 4),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])),
          Spacer(1, 8)]
    s += [Paragraph("Contents", H2)]
    toc = [("Your mission", 3), ("The controls", 4), ("Reading the screen", 5),
           ("Your equipment", 6), ("The cave", 7), ("Creatures", 8),
           ("Objects", 9), ("Scoring and levels", 10), ("Hints from the pros", 11),
           ("Credits", 12)]
    for t, p in toc:
        s.append(Paragraph(f"{t} <font color='#6c6c78'>{'.' * (44 - len(t))}</font> {p}",
                           style("toc", fontSize=9.2, leading=13, spaceAfter=0)))
    s.append(PageBreak())

    # ---- mission
    s += head("Your mission", "The object of the game")
    s += [Paragraph(
        "Miners are trapped deep in a maze of caves, and the clock is running. "
        "You are the <b>S.A.V.I.O.R.</b> pilot: a rescuer with a rocket-powered "
        "jet pack, a laser built into your helmet and a bag of bombs.", BODY),
        Paragraph(
        "Fly from room to room, find the trapped miner and <b>touch</b> "
        "him. Deeper levels hide up to <b>three miners</b>, and the level is "
        "finished only when <b>every miner has been rescued</b>. Then the rescue "
        "bonus is counted and the next, more dangerous, cave opens.", BODY)]
    s += [Table([[player(4.4), sprite("miner", 4.4),
                  Paragraph("Reach the miner before the power bar runs dry, "
                            "without running into anything that bites, burns, "
                            "crushes or drowns you.", CELLT)]],
                colWidths=[0.55 * inch, 0.55 * inch, W - 1.1 * inch],
                style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("BOX", (0, 0), (-1, -1), 0.6, ORANGE),
                                  ("BACKGROUND", (0, 0), (-1, -1), HexColor("#fff9e8")),
                                  ("TOPPADDING", (0, 0), (-1, -1), 8),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])),
          Spacer(1, 6)]
    s += [Paragraph("How you lose a life", H2)] + bullets([
        "You touch a <b>creature</b>.",
        "You touch a <b>hot rock</b> wall, or get <b>crushed</b> by a moving wall.",
        "You fall into the <b>water</b> at the bottom of a flooded room.",
        "You are standing in the blast of your own <b>bomb</b>.",
        "The <b>power bar</b> runs out."])
    s += [Paragraph(
        "You begin with <b>three lives</b>. Lose them all and the level starts "
        "again with three fresh lives, five bombs and the creatures back in "
        "place. <b>Your score is kept.</b>", BODY)]
    s.append(PageBreak())

    # ---- controls
    s += head("The controls", "Joystick and console")
    s += [Joystick(), Spacer(1, 4)]
    s += [Paragraph("Console switches", H2)]
    sw = [("SELECT", "On the title screen, each press moves to the next level "
                     "(the number shows in the score window); after the last "
                     "level it wraps back to 1. <b>During a game</b>, pressing "
                     "it takes you back to the title screen."),
          ("RESET", "On the title screen, starts the game at the level shown: "
                    "score 000000, three lives, five bombs. <b>During a game</b>, "
                    "pressing it also returns to the title screen, where you "
                    "can pick a level with SELECT and press RESET again.")]
    t = Table([[Paragraph(f"<b>{a_}</b>", CELLT), Paragraph(b_, CELLT)] for a_, b_ in sw],
              colWidths=[0.8 * inch, W - 0.8 * inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), HexColor("#efe2bd")),
                           ("BOX", (0, 0), (-1, -1), 0.5, GREY),
                           ("INNERGRID", (0, 0), (-1, -1), 0.4, HexColor("#d8cfb8")),
                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    s += [t, Spacer(1, 4)]
    s += [Paragraph("Flying tips", H2)] + bullets([
        "Gravity always pulls you down. <b>Hold UP</b> to burn the jet: it builds "
        "power gradually, so take-off is gentle, but once you are falling a held "
        "jet catches you quickly.",
        "Release UP to float for a moment, then drop. Short taps give fine control "
        "in narrow shafts.",
        "Move the stick <b>while</b> thrusting to slip through gaps. Walls stop you "
        "flush; they never hurt, only hot rock does.",
        "You can <b>stand</b> on any floor. Bombs are dropped from the ground, so "
        "land first."])
    s.append(PageBreak())

    # ---- screen
    s += head("Reading the screen", "The HUD")
    s += [HudShot(W), Spacer(1, 6)]
    rows = [
        ("1", "Power bar",
         "Your time. It starts full and yellow; the red part grows from the right "
         "as the seconds pass. When it is all red, you lose a life. A power cell "
         "refills it."),
        ("2", "Lives",
         "One green square per life remaining. When the last one goes, the "
         "level starts again."),
        ("3", "Key",
         "A yellow square at the right of the lives row. It lights up while you "
         "carry a key (not shown in this picture)."),
        ("4", "Bombs",
         "One red square per bomb in your bag (you start with five). Drop one "
         "and a square goes out."),
        ("5", "Miners",
         "Purple squares: how many miners are still waiting to be rescued."),
        ("6", "Score",
         "Six digits. It is not reset when you lose your last life."),
    ]
    t = Table([[Paragraph(f"<b>{n}</b>", style("n", alignment=1, fontSize=9, textColor=NAVY)),
                Paragraph(f"<b>{h}.</b> {d}", CELLT)] for n, h, d in rows],
              colWidths=[0.28 * inch, W - 0.28 * inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), GOLD),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor("#d8cfb8")),
                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    s += [t]
    s.append(PageBreak())

    # ---- equipment
    s += head("Your equipment", "Jet pack, laser and bombs")
    s += [entry(player(2.6), "The jet pack",
                "Powered by the stick: <b>UP</b>. Its thrust grows the longer you "
                "hold it and fades gently when you let go. It makes noise, so "
                "listen: a steady buzz means you are climbing.", art_w=0.7 * inch)]
    laser = Table([[""]], colWidths=[0.6 * inch], rowHeights=[0.1 * inch])
    laser.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), tia(0x1E))]))
    s += [entry(laser, "The helmet laser",
                "Hold the <b>red button</b> to send a short beam the way you "
                "face. It destroys creatures (<b>+50</b>) and switches off a lamp. "
                "It is stopped by any wall, and it cannot hurt miners, keys or "
                "power cells. Keep the button down to fire again and again.")]
    s += [entry(sprite("bomb", 4.0), "Bombs",
                "Press <b>DOWN</b> while standing on the floor to plant a bomb "
                "(one at a time). After about <b>three seconds</b> it explodes and "
                "the screen flashes for a second. The blast reaches a little to "
                "each side of the bomb, any height.")]
    s += bullets([
        "A bomb <b>opens thin, one-cell-wide walls</b> (<b>+75</b>) and destroys "
        "creatures in its path (<b>+50</b>).",
        "It also hurts <b>you</b>. Step away from the bomb before it goes off.",
        "A wall that borders no other room cannot be blasted open: there is "
        "nothing on the other side.",
        "You carry <b>five bombs</b>. A new life does not give more, so save "
        "them for the walls that matter."])
    s.append(PageBreak())

    # ---- cave
    s += head("The cave", "Walls, doors and traps")
    s += [Paragraph(
        "Every room is a mirror: what is on the left half is on the right. The "
        "colour of the walls changes with each level.", BODY)]
    s += [entry(Swatch("wall"), "Solid rock",
                "Safe to touch; it just stops you. You can stand on it.")]
    s += [entry(Swatch("thin"), "Thin walls",
                "A wall one cell wide. Blast it with a bomb to open the way. "
                "Stand clear.")]
    s += [entry(Swatch("hot"), "Hot rock",
                "Glowing red rock. <b>Touching it costs a life.</b> Keep a safe "
                "distance when you fly along it.")]
    s += [entry(Swatch("door"), "Locked door",
                "A gold stripe that blocks the way. Pick up the <b>key</b> "
                "first; touching the door with the key opens it.")]
    s += [entry(Swatch("phase"), "Phase wall",
                "A wall that blinks on and off. It is solid when it shows and "
                "<b>crushes you</b> if it comes back while you are inside. "
                "A phase wall you have crushed through stays open for the rest "
                "of the visit.")]
    s += [entry(Swatch("crunch"), "Crusher",
                "A wall that sweeps in from the side across a whole band every "
                "few seconds. Always leave the band through the gap <b>above or "
                "below</b> the entrance before it closes.")]
    s += [entry(Swatch("water"), "Flooded room",
                "The surface rises and falls a little. <b>Touching the water "
                "costs a life.</b> Cross on a raft or stay above it.")]
    s.append(PageBreak())

    # ---- creatures
    s += head("Creatures", "Everything that bites")
    s += [Paragraph(
        "Touching any creature costs a life. Shoot them with the laser or catch "
        "them in a bomb blast: each one is worth <b>50 points</b>. A room holds "
        "at most two of them.", BODY)]
    s += [entry(sprite("spider", 3.0), "Spider",
                "Hangs at a fixed spot and bobs up and down along its thread. "
                "Time your pass for when it is at the top.")]
    s += [entry(sprite("bat", 3.6), "Bat",
                "Flaps up and down on its column and never rests.")]
    s += [entry(sprite("snake", 4.6), "Snake",
                "Lives inside the walls and slithers out and back along a short "
                "patrol. The laser reaches it where its head shows.")]
    s += [entry(sprite("tentacle", 3.0), "Tentacle",
                "A water monster that bobs in a flooded room and reaches for "
                "you.")]
    s += [entry(sprite("moth", 3.0), "Giant moth",
                "Patrols a room, flapping slowly but surely.")]
    s += [Paragraph(
        "<b>Faster and faster.</b> Every five levels the creatures speed up: "
        "<b>x1.5</b> from level 6, <b>x2</b> from level 11, <b>x2.5</b> from "
        "level 16.", BODY)]
    s.append(PageBreak())

    # ---- objects
    s += head("Objects", "Things worth finding")
    s += [entry(sprite("miner", 4.0), "The miner",
                "Touch him to rescue him. If other miners remain you hear a short "
                "blip and score <b>500</b>; after the last one the level ends "
                "with the rescue bonus. Check the purple squares on screen to "
                "see how many are left. Miners never move.")]
    s += [entry(sprite("key", 3.0), "Key",
                "Touch it to pick it up: a yellow square appears at the right of "
                "the lives row. It opens a locked door and stays with you when "
                "you leave the room, and when you lose a life.")]
    s += [entry(sprite("cell", 5.0), "Power cell",
                "A glowing cyan cell. Touch it to <b>refill the power bar</b> "
                "completely. Each cell can be used once per level. Long levels "
                "hide a few of them.")]
    s += [entry(sprite("lamp", 3.4), "Lamp",
                "Touch it or shoot it and the whole room goes <b>dark</b>: only "
                "the lamp and the creatures remain visible as grey shapes. It "
                "does not cost a life, and the room stays dark until the level "
                "ends.")]
    s += [entry(sprite("raft", 4.0), "Raft",
                "A log floating on the water. Land on it and it carries you "
                "across to the other side, speeding up as you ride. It moves "
                "<b>only while you are on it</b>. Step off and it waits for you.")]
    s.append(PageBreak())

    # ---- scoring
    s += head("Scoring and levels", "Points and progress")
    pts = [("Destroy a creature (laser or bomb)", "50"),
           ("Blow open a thin wall", "75"),
           ("Rescue a miner (when others remain)", "500"),
           ("Rescue the last miner", "Rescue bonus")]
    t = Table([[Paragraph(a, CELLT), Paragraph(f"<b>{b}</b>", CELLT)] for a, b in pts],
              colWidths=[W - 1.05 * inch, 1.05 * inch])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, GREY),
                           ("INNERGRID", (0, 0), (-1, -1), 0.4, HexColor("#d8cfb8")),
                           ("BACKGROUND", (0, 0), (-1, -1), HexColor("#fff9e8")),
                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    s += [t, Spacer(1, 6)]
    s += [Paragraph("The rescue bonus", H2),
          Paragraph(
              "When the last miner is safe, the game freezes on the rescue and "
              "counts a bonus: points for the <b>time left on the power bar</b>, "
              "a flat reward for the level, <b>every unused bomb</b> and "
              "<b>double points for every life</b> you still have. Fly quickly, "
              "save your bombs and stay alive.", BODY),
          Paragraph("Levels", H2),
          Paragraph(
              "There are twenty levels. Each is a network of connected rooms: "
              "leave a room through an opening on any side and you arrive in the "
              "neighbouring room. A level may have one, two or three miners "
              "(one up to level 6, two from level 7, three from level 14), "
              "doors with keys, flooded rooms, crushers and phase walls. The "
              "deeper you go, the more of these you will meet at once.", BODY),
          Paragraph("When the game ends", H2),
          Paragraph(
              "Lose your last life and the current level restarts. Press "
              "<b>SELECT</b> and <b>RESET</b> on the title screen to choose a "
              "level and start over.", BODY)]
    s.append(PageBreak())

    # ---- hints
    s += head("Hints from the pros", "Fly like a veteran")
    s += bullets([
        "<b>Look before you leap.</b> Creatures follow fixed patterns; "
        "watch one full cycle before you pass.",
        "<b>Land to drop a bomb.</b> Bombs only come out on the ground, and "
        "you need a second or two to get clear. Plan your retreat first.",
        "<b>Use the laser, not the bombs, on creatures.</b> Bombs open walls; "
        "the laser costs nothing.",
        "<b>Watch the power bar.</b> If it is more than half red, head for a "
        "power cell or the miner. Do not explore.",
        "<b>The mirror tells you the cave.</b> If you can see one half of a room, "
        "you know the other half.",
        "<b>Crushers and phase walls cost a life only if you stay in.</b> "
        "Always leave a band by its gap, never wait inside.",
        "<b>Leave the lamp alone</b> unless you must: a dark room is hard "
        "to read. But remember that it stays dark.",
        "<b>A key is yours until the level ends.</b> Take your time to find the "
        "door; carrying it costs nothing.",
        "<b>Every miner counts.</b> If the purple squares are not gone, the "
        "level is not over, even when the first miner is already safe.",
    ])
    s.append(PageBreak())

    # ---- credits
    s += head("Credits", "Thank you")
    credits = (SRC / "credits.txt").read_text().split("\n")
    s += [Paragraph(
        "<b>S.A.V.I.O.R.</b> is an Atari 2600 game written from scratch by "
        "Iuri Fiedoruk. It would not exist without the people and the work "
        "below.", BODY)]
    s += [Paragraph("The game that inspired it", H2),
          Paragraph("<b>H.E.R.O.</b> (Activision, 1984, designed by John Van "
                    "Ryzin) is the reference for the whole kernel: the mirrored "
                    "playfield, the fixed-time scanline loop, the HUD band and "
                    "the way the cartridge switches banks.", BODY),
          Paragraph("Techniques we learned from", H2),
          Paragraph("<b>Andrew Davie</b> for the horizontal positioning "
                    "routines. The <i>lo-a-rad-dragon</i> reference project "
                    "from Rick Parrish's LORD2 repository for the fixed-point "
                    "physics model. The Atari 2600 community for the "
                    "48-pixel sprite text and the player-copy tricks.", BODY),
          Paragraph("Ideas and inspiration", H2),
          Paragraph("<b>Felipe Zacani</b>: the idea of multiple miners, doors "
                    "and keys, and his game <i>Spelunk Man</i>.", BODY),
          Paragraph("Tools", H2),
          Paragraph("Stella (emulator and debugger), DASM (the 6502 "
                    "cross-assembler), py65 (the 6502 simulator used by the "
                    "tests) and Qt (the level and model editor).", BODY),
          Spacer(1, 8),
          Paragraph("Special thanks", H2),
          Paragraph("To my lovely wife Arismeire and daughter Katya Valeria.",
                    BODY),
          Spacer(1, 14),
          Paragraph("<i>Atari 2600 and Video Computer System are trademarks "
                    "of their respective owners. This manual is an independent "
                    "document for a fan-made cartridge.</i>", SMALL)]
    return s


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=PAGE, leftMargin=MARGIN,
                          rightMargin=MARGIN, topMargin=0.5 * inch,
                          bottomMargin=0.6 * inch,
                          title="S.A.V.I.O.R. Instruction Manual",
                          author="Iuri Fiedoruk")
    frame = Frame(MARGIN, 0.6 * inch, PAGE[0] - 2 * MARGIN,
                  PAGE[1] - 1.1 * inch, id="f", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=cover),
        PageTemplate(id="inside", frames=[frame], onPage=inside)])
    flow = [NextPageTemplate("inside"), PageBreak()] + story()
    doc.build(flow)
    print("manual ->", OUT)


if __name__ == "__main__":
    build()
