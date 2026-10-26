#!/bin/bash
# Phase-6 QA build: build a throwaway ROM whose level 1 is the feature sweep
# (one room per feature: key, door, phase, vcrunch, hcrunch, goal).
#
# Stages src/tests/qa/rooms over src/rooms/, builds, copies the ROM + its
# models_data.asm to $OUT (/tmp/opencode/savior_qa.bin + .models.asm), then
# ALWAYS restores the live stage and rebuilds the live ROM (real sims). The
# live stage is never left modified — the trap restores on any exit.
#
# The QA build skips build.sh's py65 sims (SIM_PY=/bin/false): they probe
# LIVE stage content (tentacle room, 2-object room) that the sweep level does
# not have. They still run on the final live rebuild below. Verified: bank0 +
# bank1 are byte-identical to the live ROM; bank2 differs only in the level/
# model data (plus the $FFEF HotOverlapBody literal that tracks it) and bank3
# is the 11-byte boot stub either way — no instruction changes, so the
# CI-level guarantees are unaffected.
#
# Run: bash tools/qa_build.sh [out.bin]
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/opencode/savior_qa.bin}"
QA="$DIR/tests/qa/rooms"
TMP="$(mktemp -d)"
DONE=0

restore() {
    if [ "$DONE" = 0 ] && [ -d "$TMP/rooms" ]; then
        rm -rf "$DIR/rooms" "$DIR/generated"
        cp -a "$TMP/rooms" "$DIR/rooms"
        cp -a "$TMP/generated" "$DIR/generated"
        DONE=1
    fi
    rm -rf "$TMP"
}
trap restore EXIT

[ -d "$QA" ] || { echo "qa_build: $QA missing (run tools/gen_qa_stage.py?)"; exit 2; }
cp -a "$DIR/rooms" "$TMP/rooms"
cp -a "$DIR/generated" "$TMP/generated"
rm -rf "$DIR/rooms" "$DIR/generated"
mkdir -p "$DIR/generated"
cp -a "$QA" "$DIR/rooms"

echo "qa_build: building the QA stage (sims skipped — they probe live content) ..."
( cd "$DIR" && SIM_PY=/bin/false ./build.sh "$OUT" )
cp "$DIR/generated/models_data.asm" "${OUT%.bin}.models.asm"
cp "$DIR/bank0.lst" "${OUT%.bin}.bank0.lst"
cp "$DIR/bank2.lst" "${OUT%.bin}.bank2.lst"

restore
echo "qa_build: rebuilding the live ROM ..."
( cd "$DIR" && ./build.sh >/dev/null )
echo "qa_build: done -> $OUT"
