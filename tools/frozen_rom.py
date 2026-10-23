"""Frozen 16K ROM image built from src/tests/frozen/bank{0..3}.bin.

ROM-behaviour tests (TIA trace probes) must not depend on the LIVE stage: the
project's stage is the user's content and the editor can regenerate it at any
time. These tests only care about the CODE, so they boot a ROM assembled from
the frozen test-owned banks (C7/E-era rule) and read the matching frozen
labels. The four 4K banks are concatenated in F6 order (bank0..bank3).
"""
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "src" / "tests" / "frozen"
_cache: Path | None = None


def path() -> Path:
    """Cached temp file with the frozen 32K (F4, 8 banks) image."""
    global _cache
    if _cache is not None and _cache.exists():
        return _cache
    fd, name = tempfile.mkstemp(prefix="savior_frozen_", suffix=".bin")
    with open(fd, "wb") as out:
        for i in range(8):
            out.write((FROZEN / f"bank{i}.bin").read_bytes())
    _cache = Path(name)
    return _cache
