"""Bank selector roles (banks.inc) <-> hotspot addresses, for tools and tests that read the ASM source.

The sources write `sta BK_ROOMS`; the old layout puts that role in bank2, hotspot $1FF6. A tool that
greps the source for `sta $1FF6` must expand the role names first: `expand(text)`.
The mapping is read from banks.inc, so a changed layout is followed automatically.
"""
import re
from pathlib import Path

_INC = Path(__file__).resolve().parents[1] / "banks.inc"


def role_hotspots() -> dict[str, int]:
    """{'BK_ROOMS': 0x1FF6, ...} from banks.inc (BKI_x = physical bank, BK_x = $1FF4 + BKI_x)."""
    idx = {}
    for m in re.finditer(r"^BKI_(\w+)\s*=\s*(\d+)", _INC.read_text(), re.M):
        idx[m.group(1)] = int(m.group(2))
    return {f"BK_{k}": 0x1FF4 + v for k, v in idx.items()}


def expand(text: str) -> str:
    """Replace every BK_<ROLE> by its $1FFx hotspot (code and comments alike)."""
    hs = role_hotspots()
    return re.sub(r"\bBK_[A-Z]+\b", lambda m: f"${hs[m.group(0)]:04X}" if m.group(0) in hs else m.group(0), text)


def read_asm(path) -> str:
    """The source of `path` with the role selectors expanded to hotspot addresses."""
    return expand(Path(path).read_text(errors="replace"))


def bank_index(role: str) -> int:
    """Physical bank (0-7) of a role, e.g. bank_index("MODELS") -> 4 (banks.inc BKI_MODELS)."""
    for m in re.finditer(r"^BKI_(\w+)\s*=\s*(\d+)", _INC.read_text(), re.M):
        if m.group(1) == role:
            return int(m.group(2))
    raise KeyError(role)
