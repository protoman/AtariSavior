#!/usr/bin/env python3
"""Release versioning: VERSION is the single source of truth.

  * src/VERSION is X.Y.Z or X.Y.Z-rcN / -betaN;
  * src/version.asm (written by build.sh) says the same;
  * the built ROM carries "S.A.V.I.O.R. <version>" NUL-terminated at $F005 of bank5 (after the power-up stub);
  * the manual script prints it (it reads the same file).

Run: /home/iuri/python3/bin/python3 tools/test_version.py   (after ./build.sh)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = (ROOT / "VERSION").read_text().strip()
assert re.fullmatch(r"\d+\.\d+\.\d+(-(rc|beta)\d+)?", version), f"VERSION {version!r}"

asm = (ROOT / "version.asm").read_text()
assert f'"S.A.V.I.O.R. {version}"' in asm, "version.asm is stale: run ./build.sh"

rom = (ROOT / "savior.bin").read_bytes()
stamp = f"S.A.V.I.O.R. {version}".encode() + b"\0"
assert rom[5 * 4096 + 5:5 * 4096 + 5 + len(stamp)] == stamp, (
    f"bank5 header {rom[5 * 4096 + 5:5 * 4096 + 37]!r}, want {stamp!r}: run ./build.sh")

manual = (ROOT / "docs" / "manual" / "build_manual.py").read_text()
assert 'VERSION = (SRC / "VERSION")' in manual and "Version {VERSION}" in manual, (
    "the manual cover must print src/VERSION")

print(f"test_version: OK ({version}: VERSION = version.asm = bank5 header = manual cover)")
