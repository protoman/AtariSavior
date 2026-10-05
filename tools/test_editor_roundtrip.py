#!/usr/bin/env python3
"""Editor round-trip (CHECK5, plan Phase 5):

1. Field preservation: `savior_editor --selftest models.json` loads the
   real file (must NOT drop asym_patches), saves to a temp file, reloads,
   and byte-compares every model incl. asym_patches — catches both the
   load-side and save-side drops the user hit when the editor stripped
   the field on save (2026-10-04).
2. Source->generated consistency (D7/Phase 5 item 2): regenerate every
   level with the same convert commands build.sh uses, then
   `git diff --exit-code src/generated` must be clean — editor-saved
   content must convert to exactly the committed bytes.

Builds the editor first if the binary is missing (cmake cache is reused).

Run: /home/iuri/python3/bin/python3 tools/test_editor_roundtrip.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
EDITOR_DIR = ROOT / "src" / "tools" / "editor"
BUILD_DIR = EDITOR_DIR / "cmake-build-debug"
BINARY = BUILD_DIR / "savior_editor"
MODELS = SRC / "rooms" / "models" / "models.json"
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

    # --- 1. field round-trip on the REAL models.json ---------------------
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

    # --- 2. regenerate generated/ and require a clean diff ---------------
    levels = sorted((SRC / "rooms").glob("level_[0-9][0-9][0-9].json"))
    assert levels, "no level_XXX.json found"
    for j in levels:
        out_prefix = SRC / "generated" / j.stem
        r = subprocess.run(
            [PY, str(ROOT / "tools" / "convert_level.py"), str(j),
             str(out_prefix), str(SRC / "rooms")],
            capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(f"FAIL: convert {j.name}:\n{r.stderr}")
            return 1
    r = subprocess.run(
        [PY, str(ROOT / "tools" / "convert_level.py"), "--levels",
         str(SRC / "generated" / "levels.asm")] + [str(j) for j in levels],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"FAIL: convert --levels:\n{r.stderr}")
        return 1
    r = subprocess.run(["git", "-C", str(ROOT), "diff", "--exit-code", "--",
                        "src/generated"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("FAIL: generated/ differs from committed bytes after "
              "regeneration (editor-saved content must convert clean):\n"
              + r.stdout[-2000:])
        return 1

    print("test_editor_roundtrip: OK (selftest + generated diff clean)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
