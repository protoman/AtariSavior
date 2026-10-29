#!/bin/bash
# Build the PAL or PAL60 ROM in a scratch copy of src/ (the live tree and its generated/
# data stay NTSC). Usage: tools/build_variant.sh pal|pal60 [OUT_DIR]
#   pal60 = the NTSC 262/272-line frame at 60 Hz with PAL colours
#   pal   = 312 lines at 50 Hz, PAL colours, a 50-frame power-bar second
# The scratch build runs the full build.sh (verify_build + both sims, which read the
# variant's colors.inc), then the ROM is copied to OUT_DIR/savior-<version>-<tv>.bin.
set -e
TV="$1"
case "$TV" in pal|pal60) ;; *) echo "usage: $0 pal|pal60 [OUT_DIR]"; exit 2 ;; esac
SRC="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${2:-$SRC/releases}"
VERSION="$(tr -d '[:space:]' < "$SRC/VERSION")"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/savior_$TV.XXXXXX")"
[ -n "$KEEP" ] || trap 'rm -rf "$WORK"' EXIT      # KEEP=1: keep the scratch tree (banks, listings)
rsync -a --exclude releases --exclude screenshots --exclude .git \
      --exclude 'tools/editor/cmake-build-debug' --exclude __pycache__ "$SRC/" "$WORK/"
( cd "$WORK" && TV="$TV" ./build.sh )
mkdir -p "$OUT"
cp "$WORK/savior.bin" "$OUT/savior-$VERSION-$TV.bin"
( cd "$OUT" && sha256sum "savior-$VERSION-$TV.bin" > "savior-$VERSION-$TV.bin.sha256" )
echo "built $OUT/savior-$VERSION-$TV.bin"
[ -z "$KEEP" ] || echo "scratch tree: $WORK"
