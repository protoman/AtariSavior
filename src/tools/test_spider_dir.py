#!/usr/bin/env python3
"""Spider direction (user 2026-10-28): the record's dir is the FIRST sweep.

dir right = down first (the kernel's native spawn..spawn+24), dir left = up
first (the converter anchors the record 24 px higher: sweep y-24..y). Near the
cave top/bottom the direction is forced inward so the 15-row sprite never
leaves the 144 px cave, whatever the data says.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_level as cl  # noqa: E402


def record_y_dir(y_rows, d):
    room = {"room_id": 0, "model_id": 0,
            "enemies": [{"type": 0, "x": 6, "y": y_rows, "dir": d}]}
    lines = cl._enemy_tables("T", [room], {}, {})
    # ".byte $type,$x,$y" - pull the first record's three bytes
    for ln in lines:
        m = re.search(r"\.byte\s+\$([0-9a-f]{2}),\s*(\d+),\s*(\d+)",
                      ln, re.I)
        if m and "RoomCounts" not in ln:
            t, x, y = int(m.group(1), 16), int(m.group(2)), int(m.group(3))
            return t, y
    raise AssertionError("no enemy record emitted:\n" + "\n".join(lines))


def main() -> int:
    f = cl.spider_forced_dir
    assert f(0.0) == 1 and f(1.5) == 1, "top of the cave must force DOWN"
    assert f(10.0) == -1 and f(9.0) == -1, "bottom must force UP (y+24+15 > 144)"
    assert f(6.0) == 0 and f(4.0) == 0, "mid cave is the author's choice"
    # data says up at the top / down at the bottom: forced inward anyway
    t, y = record_y_dir(1.0, -1)
    assert t & 0x80 == 0 and y == 12, f"top spider kept dir left (t={t:#x} y={y})"
    t, y = record_y_dir(10.0, 1)
    assert t & 0x80 and y == 120 - 24, f"bottom spider not up-first ({t:#x},{y})"
    # free: right = native, left = anchored 24 px higher
    t, y = record_y_dir(6.0, 1)
    assert t & 0x80 == 0 and y == 72, (t, y)
    t, y = record_y_dir(6.0, -1)
    assert t & 0x80 and y == 72 - 24, (t, y)
    # walls: a solid band right above forces DOWN, right below forces UP
    solid = "#" * 10
    air = "." * 10
    rows = [solid, air, air, air]          # wall in band 0 (px 0-35)
    assert f(3.0, rows, 8) == 1, "wall above (band 0): must sweep down"
    rows = [air, air, air, solid]          # floor band 3 (px 108-143)
    assert f(6.0, rows, 8) == -1, "wall below: must sweep up"
    assert f(3.0, rows, 8) == 0, "walls out of reach: free"
    rows = [air, air, air, solid]
    rows[3] = "#" * 4 + "." * 6            # wall only under cols 0..7
    assert f(6.0, rows, 12) == 0, "the wall is not in the spider's cell"
    assert f(6.0, rows, 2) == -1
    # moth: first leg away from a wall / the screen edge within 8 columns
    m = cl.moth_forced_dir
    air = "." * 10
    rows = [air, air, air, air]
    assert m(5.0, rows, 20) == 0, "open room: free"
    assert m(5.0, rows, 2) == 1, "left screen edge within 8 columns: go right"
    assert m(5.0, rows, 36) == -1, "right screen edge: go left"
    wall = "." * 7 + "###"                # cells 7-9: columns 14-19 and mirror
    rows = [air, wall, air, air]
    print("test_spider_dir: OK (forced inward near the edges, up-first anchors "
          "the record 24 px higher)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
