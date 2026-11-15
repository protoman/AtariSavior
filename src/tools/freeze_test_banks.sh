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
DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
# The live stage is REPLACED by src/tests/rooms while this runs, so the restore
# must be trapped, never inline-only: on 2026-10-18 an early exit left the test
# stage in src/rooms (whose level_002 still had the tentacle), the backup was
# deleted, and the next blind `git add -A src` committed the revert over the
# user's own room edit. The trap restores + verifies the hash of src/rooms
# against the pre-freeze snapshot and fails loudly if they differ.
LIVE_SHA=""
restore() {
    rc=$?
    if [ -d "$TMP/rooms" ]; then
        rm -rf "$DIR/rooms" "$DIR/generated"
        cp -a "$TMP/rooms" "$DIR/rooms"
        cp -a "$TMP/generated" "$DIR/generated"
        now="$(cd "$DIR" && find rooms -type f -print0 | sort -z | \
               xargs -0 sha256sum | sha256sum)"
        if [ -n "$LIVE_SHA" ] && [ "$now" != "$LIVE_SHA" ]; then
            echo "freeze: *** LIVE STAGE MISMATCH AFTER RESTORE ***" >&2
            echo "freeze: src/rooms does not match the pre-freeze snapshot." >&2
            echo "freeze: DO NOT COMMIT — restore the user's stage first." >&2
            rc=1
        fi
    fi
    rm -rf "$TMP"
    exit $rc
}
trap restore EXIT
trap 'exit 130' INT TERM
# the staged test stage IS src/tests/rooms, so the live-vs-test check in
# verify_build must stand down while this script runs
export FREEZE_STAGED=1

echo "freeze: staging test-owned data from src/tests/rooms ..."
cp -a "$DIR/rooms" "$TMP/rooms"
cp -a "$DIR/generated" "$TMP/generated"
LIVE_SHA="$(cd "$DIR" && find rooms -type f -print0 | sort -z | \
            xargs -0 sha256sum | sha256sum)"
rm -rf "$DIR/rooms" "$DIR/generated"
cp -a "$DIR/tests/rooms" "$DIR/rooms"
cp -a "$DIR/tests/generated" "$DIR/generated"

echo "freeze: converting test rooms + assembling banks ..."
LEVELS=("$DIR"/rooms/level_[0-9][0-9][0-9].json)
for J in "${LEVELS[@]}"; do
    python3 "$DIR/tools/convert_level.py" "$J" "$DIR/generated/$(basename "$J" .json)" "$DIR/rooms"
done
python3 "$DIR/tools/convert_level.py" --levels "$DIR/generated/levels.asm" "${LEVELS[@]}"
python3 "$DIR/tools/verify_build.py" --precheck "$DIR"
cd "$DIR"
# Layout v3 (docs/agents/banks.md): same order as build.sh; the file number is the physical bank.
INC="-I. -Igenerated"
dasm bank5.asm -f3 $INC -obank5.bin -lbank5.lst
dasm bank6.asm -f3 $INC -obank6.bin -lbank6.lst
python3 "$DIR/tools/verify_build.py" --sync-hof "$DIR"
python3 "$DIR/tools/verify_build.py" --sync "$DIR"
dasm bank0.asm -f3 $INC -obank0.bin -lbank0.lst -sgenerated/symbols.asm
python3 "$DIR/tools/verify_build.py" --sync-overscan "$DIR"
python3 "$DIR/tools/gen_bank6_equs.py" "$DIR"
python3 "$DIR/tools/cave_kernel_gen.py" --real "$DIR/generated" "$DIR/bank0.asm" > /dev/null
for b in 1 2 3 4 7; do
    dasm "bank$b.asm" -f3 $INC -o"bank$b.bin" -l"bank$b.lst" > /dev/null
done
for i in 0 1 2 3 4 5 6 7; do
    SIZE=$(wc -c < "bank${i}.bin")
    [ "$SIZE" -lt 4096 ] && printf '\0%.0s' $(seq 1 $((4096 - SIZE))) >> "bank${i}.bin"
done
python3 "$DIR/tools/verify_build.py" "$DIR"

echo "freeze: capturing bank images + labels into src/tests/frozen/ ..."
mkdir -p "$DIR/tests/frozen"
cp bank[0-7].bin "$DIR/tests/frozen/"
cp bank[0-7].lst "$DIR/tests/frozen/"

# The test-owned convert outputs must match the test-owned rooms, or
# test_editor_roundtrip compares fresh conversions against a stale snapshot
# (2026-10-20: a converter format change left tests/generated on the old
# level-table layout). Copy only what convert_level.py emits — symbols.asm
# (dasm dump) and copyright_font.asm (editor tool) are separate snapshots.
echo "freeze: refreshing src/tests/generated/ from the staged conversion ..."
for f in "$DIR"/generated/level_[0-9][0-9][0-9]_*.asm \
         "$DIR"/generated/levels.asm "$DIR"/generated/levels_data.asm \
         "$DIR"/generated/levels_index.asm "$DIR"/generated/levels_index_B.asm "$DIR"/generated/levels_equ.asm \
         "$DIR"/generated/models_data.asm "$DIR"/generated/levels_extras.asm \
         "$DIR"/generated/spill_*.asm; do
    [ -f "$f" ] && cp "$f" "$DIR/tests/generated/$(basename "$f")"
done

echo "freeze: restoring live data + rebuilding the live ROM ..."
rm -rf "$DIR/rooms" "$DIR/generated"
cp -a "$TMP/rooms" "$DIR/rooms"
cp -a "$TMP/generated" "$DIR/generated"
cd "$DIR" && ./build.sh >/dev/null
echo "freeze: done (src/tests/frozen/ updated; live build restored)."
