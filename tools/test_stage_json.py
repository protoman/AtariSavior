#!/usr/bin/env python3
"""Unified stage file (E1 2026-10-20) — converter byte-identity test.

A stage file is ONE json with `models` + every level:
    {"stage": {"models": [...], "levels": [<legacy level payload>, ...]}}

This test proves the new `--stage` mode emits EXACTLY what the legacy
per-level invocation + `--levels` emit for the same content:

  * every generated .asm byte-compares equal (and the room .txt mirrors too),
  * the canonical `{"stage": ...}` form and the bare `{"models","levels"}`
    form produce the same output,
  * the output still matches the FROZEN generated/ baseline in src/tests/generated
    (the editor round-trip test covers the legacy path; this covers stage mode).

Frozen test data only (src/tests/rooms) — no live rooms/models/ are read.

Run: /home/iuri/python3/bin/python3 tools/test_stage_json.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "src" / "tests"
ROOMS = TESTS / "rooms"
FROZEN_GEN = TESTS / "generated"
CONVERT = ROOT / "tools" / "convert_level.py"
PY = "/home/iuri/python3/bin/python3"

# Non-convert snapshots (copyright font + assembler symbols).
NON_CONVERT = {"copyright_font.asm", "symbols.asm"}


def read_level(path: Path) -> dict:
    data = json.loads(path.read_text())
    return data.get("level", data)


def run(args: list[str]) -> None:
    # The synthetic stage built here keeps two objects in one band on purpose
    # (frozen collision fixtures), so the shipped-stage object-separation gate
    # is relaxed to its warning form for this test only.
    env = dict(os.environ, SAVIOR_OBJECT_BANDS="warn")
    r = subprocess.run([PY, str(CONVERT)] + args,
                       env=env, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        sys.exit(f"FAIL: convert {' '.join(args)}\n{r.stderr}")


def legacy_output(tmp: Path, levels: list[Path]) -> tuple[Path, Path]:
    gen = tmp / "generated"
    rooms = tmp / "rooms"
    gen.parent.mkdir(parents=True)
    gen.mkdir()
    rooms.mkdir()
    for j in levels:
        run([str(j), str(gen / j.stem), str(rooms)])
    run(["--levels", str(gen / "levels.asm")] + [str(j) for j in levels])
    return gen, rooms


def stage_output(tmp: Path, stage: Path) -> tuple[Path, Path]:
    gen = tmp / "generated"   # the dir NAME is baked into the include lines
    rooms = tmp / "rooms"
    gen.parent.mkdir(parents=True)
    gen.mkdir()
    rooms.mkdir()
    run(["--stage", str(stage), str(gen), str(rooms)])
    return gen, rooms


def compare(gen_a: Path, gen_b: Path, label: str) -> None:
    a = {p.name: p for p in gen_a.glob("*.asm")}
    b = {p.name: p for p in gen_b.glob("*.asm")}
    if set(a) != set(b):
        sys.exit(f"FAIL ({label}): file sets differ — "
                 f"only-legacy={sorted(set(a) - set(b))} "
                 f"only-stage={sorted(set(b) - set(a))}")
    for name in sorted(a):
        ba, bb = a[name].read_bytes(), b[name].read_bytes()
        if ba != bb:
            off = next(i for i in range(max(len(ba), len(bb)))
                       if i >= len(ba) or i >= len(bb) or ba[i] != bb[i])
            sys.exit(f"FAIL ({label}): {name} differs at byte {off} "
                     f"({ba[off:off+16]!r} != {bb[off:off+16]!r})")


def compare_dirs(a: Path, b: Path, label: str) -> None:
    fa = sorted(p.name for p in a.glob("*"))
    fb = sorted(p.name for p in b.glob("*"))
    if fa != fb:
        sys.exit(f"FAIL ({label}): {a.name} vs {b.name} file sets differ — "
                 f"{sorted(set(fa) - set(fb))} / {sorted(set(fb) - set(fa))}")
    for name in fa:
        if (a / name).read_bytes() != (b / name).read_bytes():
            sys.exit(f"FAIL ({label}): {name} differs")


def main() -> int:
    levels = sorted(ROOMS.glob("level_[0-9][0-9][0-9].json"))
    assert levels, "no frozen level_*.json in src/tests/rooms"
    models = json.loads((ROOMS / "models" / "models.json").read_text())
    models = models.get("models_file", models)["models"]
    payloads = [read_level(p) for p in levels]
    canonical = {"stage": {"models": models, "levels": payloads}}
    bare = {"models": models, "levels": payloads}

    with tempfile.TemporaryDirectory(prefix="savior_stage_") as td:
        td = Path(td)
        stage = td / "stage.json"
        stage.write_text(json.dumps(canonical, indent=2))
        bare_stage = td / "bare.json"
        bare_stage.write_text(json.dumps(bare, indent=2))

        legacy_gen, legacy_rooms = legacy_output(td / "legacy", levels)
        stage_gen, stage_rooms = stage_output(td / "canonical", stage)
        bare_gen, bare_rooms = stage_output(td / "bare", bare_stage)

        compare(legacy_gen, stage_gen, "canonical vs legacy")
        compare(legacy_gen, bare_gen, "bare vs legacy")
        compare_dirs(legacy_rooms, stage_rooms, "room txt canonical")
        compare_dirs(legacy_rooms, bare_rooms, "room txt bare")

        # The frozen generated/ baseline is the committed legacy output.
        want = {p.name: p for p in FROZEN_GEN.glob("*.asm")
                if p.name not in NON_CONVERT}
        assert want, "no frozen generated/ copies in src/tests/generated"
        got = {p.name: p for p in stage_gen.glob("*.asm")}
        missing = sorted(set(want) - set(got))
        extra = sorted(set(got) - set(want))
        if missing or extra:
            sys.exit(f"FAIL: stage output set differs from frozen — "
                     f"missing={missing} extra={extra}")
        for name in sorted(want):
            if want[name].read_bytes() != got[name].read_bytes():
                sys.exit(f"FAIL: stage {name} differs from the frozen baseline")

    print(f"test_stage_json: OK ({len(levels)} levels — stage mode emits "
          "bytes identical to legacy + frozen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
