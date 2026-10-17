#!/bin/bash
# Freeze the test-owned bank images + label lists used by the ROM-byte tests
# (test_cell_map / test_fixtures / test_hcrunch / test_laser_wall ...).
#
# User rule (2026-10-17, AGENTS.md): tests must NEVER read live src/*.bin,
# src/*.lst or src/generated/**. A ROM-byte test reads its bank image AND its
# label set from src/tests/frozen/ — built from the TEST-OWNED data in
# src/tests/rooms (+ src/tests/generated), never from the live game data.
#
# This script: stages src/tests/rooms over rooms/, builds the banks, captures
# bank{0..3}.{bin,lst} into src/tests/frozen/, then restores the live data and
# rebuilds savior.bin (the --sync steps rewrite source literals for whichever
# data is staged, so the live rebuild at the end is mandatory).
set -e
DIR="$(cd "$(dirname "$0")/../src" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "freeze: staging test-owned data from src/tests/rooms ..."
cp -a "$DIR/rooms" "$TMP/rooms"
cp -a "$DIR/generated" "$TMP/generated"
rm -rf "$DIR/rooms" "$DIR/generated"
cp -a "$DIR/tests/rooms" "$DIR/rooms"
cp -a "$DIR/tests/generated" "$DIR/generated"

echo "freeze: converting test rooms + assembling banks ..."
LEVELS=("$DIR"/rooms/level_[0-9][0-9][0-9].json)
for J in "${LEVELS[@]}"; do
    python3 "$ROOT/tools/convert_level.py" "$J" "$DIR/generated/$(basename "$J" .json)" "$DIR/rooms"
done
python3 "$ROOT/tools/convert_level.py" --levels "$DIR/generated/levels.asm" "${LEVELS[@]}"
python3 "$ROOT/tools/verify_build.py" --precheck "$DIR"
cd "$DIR"
dasm bank2.asm -f3 -obank2.bin -lbank2.lst
python3 "$ROOT/tools/verify_build.py" --sync "$DIR"
dasm kernel.asm -f3 -obank0.bin -lbank0.lst -s/tmp/opencode/frozen_symbols.asm
python3 "$ROOT/tools/verify_build.py" --sync-overscan "$DIR"
dasm bank1.asm -f3 -obank1.bin -lbank1.lst
python3 "$ROOT/tools/verify_build.py" --sync-phrec "$DIR"
dasm bank3.asm -f3 -obank3.bin -lbank3.lst
for i in 0 1 2 3; do
    SIZE=$(wc -c < "bank${i}.bin")
    [ "$SIZE" -lt 4096 ] && printf '\0%.0s' $(seq 1 $((4096 - SIZE))) >> "bank${i}.bin"
done
python3 "$ROOT/tools/verify_build.py" "$DIR"

echo "freeze: capturing bank images + labels into src/tests/frozen/ ..."
mkdir -p "$DIR/tests/frozen"
cp bank0.bin bank1.bin bank2.bin bank3.bin "$DIR/tests/frozen/"
cp bank0.lst bank1.lst bank2.lst bank3.lst "$DIR/tests/frozen/"

echo "freeze: restoring live data + rebuilding the live ROM ..."
rm -rf "$DIR/rooms" "$DIR/generated"
cp -a "$TMP/rooms" "$DIR/rooms"
cp -a "$TMP/generated" "$DIR/generated"
cd "$DIR" && ./build.sh >/dev/null
echo "freeze: done (src/tests/frozen/ updated; live build restored)."
