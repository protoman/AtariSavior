#!/usr/bin/env python3
"""Cut a release: build, run every gate, stamp the artifacts.

  tools/release.py [--skip-playbot] [--tag] [--out DIR]

The version comes from src/VERSION (X.Y.Z or X.Y.Z-rcN / -betaN) and is the single
source of truth: build.sh writes it into bank5 ("S.A.V.I.O.R. <version>" at $F000
of the fifth 4K bank), the manual cover prints it, and the artifacts are named
from it. Steps, each of which must pass:

  1. the git tree has no uncommitted tracked changes (TODO.txt / credits.txt / the
     user-owned tools/make_video.py aside) and CHANGELOG.md has a "## <version>" section
  2. ./build.sh   (conversion + verify_build + the two headless sims)
  3. the whole battery: every tools/test_*.py
  3b. FLICKER: tools/test_frame_stability.py --all (the 40 heaviest real rooms: VBL window
     and frame length) and sim_frame_budget in the 8 heaviest rooms (fire held + thrust +
     bomb). The every-room sweep is tools/sweep_frame_budget.sh, run by hand after changes
     that touch frame timing.
  4. tools/stage_reach.py on the live stage
  5. tools/playbot.py: every level of the live stage must finish on the real ROM (~10 min)
  6. the ROM is 32 KiB and carries this version
  7. the manual PDF is rebuilt
  8. the PAL60 and PAL ROMs are built (tools/build_variant.sh: full build.sh + both
     sims in a scratch tree), carry "S.A.V.I.O.R. <version> PAL60|PAL" in bank5 and,
     unless --skip-playbot, the playbot finishes every level on each

Artifacts go to OUT (default src/releases/, git-ignored): savior-<version>.bin (NTSC),
savior-<version>-pal60.bin, savior-<version>-pal.bin, their .sha256, the manual and
RELEASE.txt (commit, date, results).
--tag also creates the annotated git tag v<version> (local; never pushed here).
"""
import argparse
import datetime
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-(rc|beta)\d+)?$")
BANK5 = 4 * 4096 + 0xC70   # the version header (bank4 since 2026-11-14, trans.inc; RomVersion label)


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kw)


def step(msg):
    print(f"[release] {msg}", flush=True)


def fail(msg):
    print(f"[release] FAIL: {msg}")
    sys.exit(1)


def sim_python():
    """The interpreter that has py65 (build.sh uses the same SIM_PY)."""
    py = os.environ.get("SIM_PY", "/home/iuri/python3/bin/python3")
    if run([py, "-c", "import py65"]).returncode != 0:
        fail(f"{py} cannot import py65 (set SIM_PY)")
    return py


def python_with(module):
    """First interpreter that can import `module` (the sims and the manual live in
    different Python installs on the dev machine)."""
    for py in (sys.executable, "python3", os.environ.get("SIM_PY", "")):
        if py and run([py, "-c", f"import {module}"]).returncode == 0:
            return py
    fail(f"no Python with {module} found")


def stage_levels():
    """Number of levels of the live stage (the playbot must finish every one)."""
    import json
    return len(json.loads((ROOT / "rooms" / "stage.json").read_text())["stage"]["levels"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-playbot", action="store_true")
    ap.add_argument("--tag", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "releases"))
    a = ap.parse_args()

    version = (ROOT / "VERSION").read_text().strip()
    if not SEMVER.match(version):
        fail(f"VERSION {version!r} is not X.Y.Z[-rcN|-betaN]")
    step(f"version {version}")

    dirty = [l for l in run(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.splitlines()
             if Path(l[3:]).name not in ("TODO.txt", "credits.txt", "make_video.py")]
    if dirty:
        fail("uncommitted tracked changes:\n  " + "\n  ".join(dirty))
    if not re.search(rf"^## {re.escape(version)}\b", (ROOT / "CHANGELOG.md").read_text(), re.M):
        fail(f'CHANGELOG.md has no "## {version}" section')
    commit = run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()

    py = sim_python()
    step("build.sh")
    r = run(["env", "FULL_SIMS=1", "./build.sh"])
    if r.returncode:
        fail("build.sh failed:\n" + r.stdout[-1500:] + r.stderr[-500:])

    step("battery (tools/test_*.py)")
    tests = sorted((ROOT / "tools").glob("test_*.py"))
    bad = []
    for t in tests:
        if run([py, str(t)]).returncode:
            bad.append(t.name)
    if bad:
        fail(f"{len(bad)} failing test(s): {', '.join(bad)}")

    step("flicker: test_frame_stability --all (40 heaviest rooms)")
    r = run([py, "tools/test_frame_stability.py", "--all"])
    if r.returncode:
        fail("test_frame_stability --all:\n" + r.stdout[-2500:])
    step("flicker: sim_frame_budget in the 8 heaviest rooms (parallel, ~40 min)")
    heavy = subprocess.run(
        [py, "-c", "import sys; sys.path.insert(0, 'tools'); import test_frame_stability as F; "
                   "print(' '.join(f'{l - 1},{r}' for l, r, n in F.heavy_rooms(8)))"],
        cwd=ROOT, text=True, capture_output=True).stdout.split()
    procs = []
    for lr in heavy:
        lv, rm = lr.split(",")
        procs.append((lr, subprocess.Popen(
            [py, "sim_frame_budget.py"], cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=dict(os.environ, SIM_LEVEL=lv, SIM_ROOM=rm))))
    bad_sim = []
    for lr, pr in procs:
        out_ = pr.communicate()[0]
        if pr.returncode or "SIM OK" not in out_:
            bad_sim.append(f"L{int(lr.split(',')[0]) + 1} room {int(lr.split(',')[1]) + 1}: "
                           + out_[-300:].replace("\n", " | "))
    if bad_sim or not heavy:
        fail("frame-budget sim failed in:\n  " + "\n  ".join(bad_sim or ["no heavy rooms found"]))
    sweep_rooms = len(heavy)

    step("stage_reach")
    r = run([sys.executable, "tools/stage_reach.py", "rooms/stage.json"])
    if r.returncode or "FAIL" in r.stdout:
        fail("stage_reach:\n" + r.stdout)

    nlev = stage_levels()
    play = "skipped (--skip-playbot)"
    if not a.skip_playbot:
        step(f"playbot (all {nlev} levels, ~10 min)")
        r = run([py, "tools/playbot.py"])
        done = r.stdout.count(": DONE")
        if r.returncode or done != nlev:
            fail(f"playbot finished {done} of {nlev} levels:\n" + r.stdout[-2000:])
        play = f"{nlev} of {nlev} levels finish"

    rom = (ROOT / "savior.bin").read_bytes()
    if len(rom) != 32768:
        fail(f"savior.bin is {len(rom)} bytes, not 32768")
    stamp = f"S.A.V.I.O.R. {version}".encode() + b"\0"
    if rom[BANK5:BANK5 + len(stamp)] != stamp:
        fail("the ROM does not carry this version in bank5")

    step("manual")
    r = run([python_with("reportlab"), "docs/manual/build_manual.py"])
    if r.returncode:
        fail("build_manual.py failed:\n" + r.stderr[-800:])

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    variants = []
    for tv, label in (("pal60", "PAL60"), ("pal", "PAL")):
        step(f"{label} build (full build.sh + both sims, scratch tree)")
        env = dict(os.environ, KEEP="1")
        r = subprocess.run(["tools/build_variant.sh", tv, str(out)], cwd=ROOT, text=True,
                           capture_output=True, env=env)
        if r.returncode:
            fail(f"{label} build failed:\n" + r.stdout[-1500:] + r.stderr[-500:])
        scratch = re.search(r"scratch tree: (\S+)", r.stdout).group(1)
        try:
            vrom = (out / f"savior-{version}-{tv}.bin").read_bytes()
            vstamp = f"S.A.V.I.O.R. {version} {label}".encode() + b"\0"
            if len(vrom) != 32768 or vrom[BANK5:BANK5 + len(vstamp)] != vstamp:
                fail(f"{label} ROM is not 32768 bytes with the {label} version stamp")
            if not a.skip_playbot:
                step(f"{label} playbot (all {nlev} levels, ~10 min)")
                r = run([py, "tools/playbot.py", "--rom-dir", scratch])
                done = r.stdout.count(": DONE")
                if r.returncode or done != nlev:
                    fail(f"{label} playbot finished {done} of {nlev} levels:\n" + r.stdout[-2000:])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        variants.append((label, f"savior-{version}-{tv}.bin",
                         hashlib.sha256(vrom).hexdigest()))
    rom_out = out / f"savior-{version}.bin"
    rom_out.write_bytes(rom)
    sha = hashlib.sha256(rom).hexdigest()
    (out / f"savior-{version}.bin.sha256").write_text(f"{sha}  {rom_out.name}\n")
    shutil.copy(ROOT / "docs" / "manual" / "savior_manual.pdf",
                out / f"savior-{version}-manual.pdf")
    (out / "RELEASE.txt").write_text(
        f"S.A.V.I.O.R. {version}\n"
        f"commit   {commit}\n"
        f"built    {datetime.datetime.now().isoformat(timespec='seconds')}\n"
        f"rom      {rom_out.name}  32768 bytes  sha256 {sha}\n"
        + "".join(f"rom      {n}  32768 bytes  sha256 {h}  ({lab})\n" for lab, n, h in variants)
        + f"battery  {len(tests)} tests, 0 failures\n"
        f"flicker  test_frame_stability --all OK (40 heaviest rooms); sim_frame_budget OK in the {sweep_rooms} heaviest rooms\n"
        f"playbot  {play}\n")
    if a.tag:
        r = run(["git", "tag", "-a", f"v{version}", "-m", f"S.A.V.I.O.R. {version}"])
        if r.returncode:
            fail("git tag failed: " + r.stderr)
        step(f"tagged v{version} (not pushed)")
    step(f"OK -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
