#!/usr/bin/env python3
"""Editor round-trip (CHECK5, plan Phase 5):

1. Field preservation: `savior_editor --selftest` loads the FROZEN test
   copy of models.json (src/tests/rooms/models/models.json — AGENTS
   test-data rule: tests never read live rooms/models), saves to a temp
   file, reloads, and byte-compares every model incl. asym_patches —
   catches both the load-side and save-side drops the user hit when the
   editor stripped the field on save (2026-10-04).
2. Source->generated consistency (D7/Phase 5 item 2): regenerate every
   FROZEN level json with the same convert commands build.sh uses, into
   a TEMP directory (never the repo), then byte-compare every emitted
   .asm against the frozen generated/ copies in src/tests/generated/.

Builds the editor first if the binary is missing (cmake cache is reused).

Re-freeze (only when stage content deliberately changes): run ./build.sh
first so generated/ matches the edited data, then copy the edited
rooms/level_*.json + rooms/models/models.json and the convert outputs
listed in src/tests/generated/ into src/tests/ (same relative tree).

Run: /home/iuri/python3/bin/python3 tools/test_editor_roundtrip.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT
TESTS = SRC / "tests"
EDITOR_DIR = ROOT / "tools" / "editor"
BUILD_DIR = EDITOR_DIR / "cmake-build-debug"
BINARY = BUILD_DIR / "savior_editor"
MODELS = TESTS / "rooms" / "models" / "models.json"
FROZEN_GEN = TESTS / "generated"
# Frozen src/tests/generated/ files that the convert commands this test
# re-runs (build.sh uses convert_level.py only) do NOT emit: the editor's
# copyright micro-font (src/tools/copyright_font.py) and the assembler
# symbol dump. They are snapshotted for other purposes — exclude them from
# the "regenerated set" comparison so they are not reported as missing.
NON_CONVERT = {"copyright_font.asm", "symbols.asm"}
# (2026-10-20) The retired bank2 data-slot snapshots spill_F840/F901/window
# were deleted with user approval; generated/bank3_labels.asm went too (the
# level-data label export is assembled in bank2 now). convert_level emits
# only spill_F767 + spill_bank3.
PY = "/home/iuri/python3/bin/python3"


def ensure_editor() -> Path:
    if BINARY.exists():
        return BINARY
    print("editor binary missing — building (cmake)...")
    r = subprocess.run(["cmake", "--build", str(BUILD_DIR)],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not BINARY.exists():
        sys.exit(f"editor build failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return BINARY


def main() -> int:
    binary = ensure_editor()

    # --- 1. field round-trip on the frozen models.json ---------------------
    # 0. headless BRUSH test: the async brushes must write the ROOM's async
    #    layer, never the retired model fields (2026-10-18 relocation). Runs
    #    offscreen: a brush that pops a modal warning would hang here, which is
    #    itself a failure signal (valid targets only).
    import os as _os
    env = dict(_os.environ, QT_QPA_PLATFORM="offscreen")
    rb = subprocess.run([str(binary), "--brushtest"], capture_output=True,
                        text=True, timeout=120, env=env)
    if rb.returncode != 0 or "brushtest: OK" not in rb.stdout:
        print(f"FAIL: editor --brushtest rc={rb.returncode}\n"
              f"{rb.stdout[-600:]}{rb.stderr[-600:]}")
        return 1
    r = subprocess.run([str(binary), "--selftest", str(MODELS)],
                       capture_output=True, text=True, timeout=120)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        print(f"FAIL: editor selftest rc={r.returncode}\n{out}")
        return 1
    if "selftest OK" not in out:
        print(f"FAIL: unexpected selftest output:\n{out}")
        return 1
    print(out.strip())

    # --- 2. regenerate frozen sources into temp, compare frozen outputs ----
    levels = sorted((TESTS / "rooms").glob("level_[0-9][0-9][0-9].json"))
    assert levels, "no frozen level_XXX.json in src/tests/rooms"
    with tempfile.TemporaryDirectory(prefix="savior_roundtrip_") as td:
        tmp = Path(td)
        # dir NAME must stay "generated": convert_level bakes
        # `include "<dirname>/..."` into levels_data/levels.asm output.
        tmp_gen = tmp / "generated"
        tmp_rooms = tmp / "rooms"
        tmp_gen.mkdir()
        tmp_rooms.mkdir()
        for j in levels:
            r = subprocess.run(
                [PY, str(ROOT / "tools" / "convert_level.py"), str(j),
                 str(tmp_gen / j.stem), str(tmp_rooms)],
                capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                print(f"FAIL: convert {j.name}:\n{r.stderr}")
                return 1
        r = subprocess.run(
            [PY, str(ROOT / "tools" / "convert_level.py"), "--levels",
             str(tmp_gen / "levels.asm")] + [str(j) for j in levels],
            capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(f"FAIL: convert --levels:\n{r.stderr}")
            return 1

        want = {p.name: p for p in FROZEN_GEN.glob("*.asm")
                if p.name not in NON_CONVERT}
        got = {p.name: p for p in tmp_gen.glob("*.asm")}
        assert want, "no frozen generated/ copies in src/tests/generated"
        missing = sorted(set(want) - set(got))
        extra = sorted(set(got) - set(want))
        if missing or extra:
            print(f"FAIL: regenerated file set differs — "
                  f"missing={missing} extra={extra}")
            return 1
        for name in sorted(want):
            a = want[name].read_bytes()
            b = got[name].read_bytes()
            if a != b:
                off = next(i for i in range(max(len(a), len(b)))
                           if i >= len(a) or i >= len(b) or a[i] != b[i])
                print(f"FAIL: {name} differs at byte {off} "
                      f"(frozen {a[off:off+16]!r} != "
                      f"regen {b[off:off+16]!r})")
                return 1

    print("test_editor_roundtrip: OK (selftest + frozen regen byte-equal)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
