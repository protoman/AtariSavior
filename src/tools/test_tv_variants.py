#!/usr/bin/env python3
"""NTSC / PAL60 / PAL: the colour and timing plumbing (tools/gen_colors.py).

  * NTSC colors.inc is the identity and keeps the NTSC timing;
  * PAL / PAL60 only replace the HUE nibble (the kernel reads luma bits: ENAM0 off
    PlayerColTable bit 1, the power bar's luma steps), keep the greys grey, and map
    the fixed colours the game draws side by side to distinct PAL colours;
  * PAL60 keeps the NTSC frame, PAL has the 312-line frame and the 50-frame second;
  * NO colour byte is a raw literal in the sources any more: every `lda/ldy #$xx`
    that feeds COLUP0/COLUP1/COLUPF/COLUBK, every COLOR_* constant and the colour
    tables (ObjColorTab, EnemyColorTable, PlayerColTable) are written NC_xx, so a new
    colour cannot silently stay NTSC-only in a PAL ROM.

Run: python3 tools/test_tv_variants.py
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import gen_colors as G  # noqa: E402


def gen(tv):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "colors.inc"
        subprocess.run([sys.executable, str(ROOT / "tools" / "gen_colors.py"), tv, str(out)],
                       check=True)
        txt = out.read_text()
    consts = {k: int(v) for k, v in re.findall(r"^(TV_\w+|VBL_UNITS|OVER_UNITS|TICKS_PER_SEC) = (\d+)", txt, re.M)}
    nc = {int(k, 16): int(v, 16) for k, v in re.findall(r"^NC_([0-9A-F]{2}) = \$([0-9A-F]{2})", txt, re.M)}
    return consts, nc


def main() -> int:
    c, nc = gen("ntsc")
    assert nc == {i: i for i in range(256)}, "NTSC colors must be the identity"
    assert (c["TV_PAL"], c["TV_50HZ"], c["VBL_UNITS"], c["OVER_UNITS"], c["TICKS_PER_SEC"],
            c["TV_CAVE_LINES"]) == (0, 0, 31, 44, 60, 272), c
    for tv in ("pal60", "pal"):
        c, nc = gen(tv)
        assert len(nc) == 256 and all((nc[i] & 0x0F) == (i & 0x0F) for i in nc), (
            f"{tv}: the luma nibble must be kept")
        assert all(nc[i] >> 4 == 0 for i in range(16)), f"{tv}: greys stay grey"
        fixed = {0: "grey", 1: "gold", 2: "orange", 4: "red", 5: "magenta", 6: "purple",
                 8: "blue", 9: "cyan", 12: "green"}
        pal_hues = {h: nc[h << 4] >> 4 for h in fixed}
        assert len(set(pal_hues.values())) == len(fixed), (
            f"{tv}: fixed colours collide: {pal_hues}")
        assert all(pal_hues[h] not in (1, 14, 15) or h == 0 for h in fixed), (
            f"{tv}: a chromatic NTSC hue was mapped onto a PAL grey: {pal_hues}")
        assert c["TV_PAL"] == 1
    c60, _ = gen("pal60")
    assert (c60["TV_50HZ"], c60["VBL_UNITS"], c60["OVER_UNITS"], c60["TICKS_PER_SEC"],
            c60["TV_CAVE_LINES"]) == (0, 31, 44, 60, 272), "PAL60 keeps the NTSC frame"
    c50, _ = gen("pal")
    assert (c50["TV_50HZ"], c50["TICKS_PER_SEC"], c50["TV_CAVE_LINES"]) == (1, 50, 312)
    assert c50["VBL_UNITS"] > 31 and c50["OVER_UNITS"] > 44

    # no raw colour literals
    store = re.compile(r"^\s*(sta|sty|stx)\s+(COLUP0|COLUP1|COLUPF|COLUBK)\b")
    bad = []
    for name in ("kernel.asm", "bank1.asm", "bank2.asm", "bank3.asm"):
        lines = (ROOT / name).read_text().split("\n")
        code = [l.split(";", 1)[0] for l in lines]
        for i, l in enumerate(code):
            if re.match(r"^\s*COLOR_[A-Z0-9_]+\s*=\s*\$", l):
                bad.append(f"{name}:{i + 1}: raw colour constant {l.strip()}")
            m = store.match(l)
            if not m:
                continue
            reg = {"sta": "a", "sty": "y", "stx": "x"}[m.group(1)]
            for j in range(i - 1, max(-1, i - 7), -1):
                if re.match(rf"^\s*ld{reg}\b", code[j]):       # the load that feeds the store
                    if re.match(rf"^\s*ld{reg}\s+#\$[0-9A-Fa-f]{{2}}\b", code[j]):
                        bad.append(f"{name}:{j + 1}: raw colour literal {code[j].strip()}")
                    break
                if re.match(r"^\s*(jmp|jsr|rts|b[a-z]{2})\b", code[j]) or re.match(r"^\s*\.?\w+:", code[j]):
                    break
        for lab in ("ObjColorTab", "EnemyColorTable", "PlayerColTable"):
            for i, l in enumerate(lines):
                if re.match(rf"^{lab}:", l):
                    k = i + 1
                    while k < len(lines) and (code[k].strip().startswith(".byte") or not code[k].strip()):
                        if re.search(r"\$[0-9A-Fa-f]{2}\b", code[k]):
                            bad.append(f"{name}:{k + 1}: raw colour byte in {lab}: {code[k].strip()[:50]}")
                        k += 1
    assert not bad, "colour bytes must be NC_xx:\n  " + "\n  ".join(bad)

    print("test_tv_variants: OK (NTSC identity; PAL/PAL60 keep luma and greys, fixed hues stay "
          "distinct; PAL = 312 lines + 50-frame second; no raw colour bytes in the sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
