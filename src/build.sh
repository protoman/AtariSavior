#!/bin/bash
# Build the savior kernel ROM (F4 bankswitch, 32K)
# Usage: ./build.sh [filename]
# Output: savior.bin (32K, 8 x 4K banks)

set -e

OUTPUT="${1:-savior.bin}"
DIR="$(dirname "$0")"
ROOT="$(cd "$DIR/.." && pwd)"

echo "Building F4 ROM (8 banks)..."

# Generate level data. A stage file holds models + every level:
#   rooms/stage.json exists -> it IS the project (the editor's single file)
#   STAGE_FILE=...          -> build any other stage without touching rooms/
#   otherwise               -> legacy per-level level_NNN.json files
# ROM-behaviour tests boot the FROZEN banks, so the live stage can be the
# generated one (2026-10-20).
STAGE_FILE="${STAGE_FILE:-}"
if [ -z "$STAGE_FILE" ] && [ -f "$DIR/rooms/stage.json" ]; then
    STAGE_FILE="$DIR/rooms/stage.json"
fi
if [ -n "$STAGE_FILE" ]; then
    echo "  Level source: unified stage file $STAGE_FILE"
    # No level files here: the stage IS the source, and the .txt mirrors are
    # build scratch. They go to a temp dir (never the user's rooms/ tree) and
    # the same dir is handed to verify_build via the environment (2026-10-20:
    # writing them into rooms/ polluted the live stage, and an unexported
    # STAGE_FILE made verify compare the ROM against the LEGACY models.json).
    STAGE_ROOMS="$(mktemp -d "${TMPDIR:-/tmp}/savior_stage_rooms.XXXXXX")"
    trap 'rm -rf "$STAGE_ROOMS"' EXIT
    python3 "$ROOT/tools/convert_level.py" --stage "$STAGE_FILE" \
        "$DIR/generated" "$STAGE_ROOMS"
    export STAGE_FILE STAGE_ROOMS
else
    echo "  Level source: legacy per-level JSON ($DIR/rooms/level_NNN.json)"
    # Generate level data from JSON (every rooms/level_XXX.json — no hardcode)
    echo "  Generating level data..."
    LEVELS=("$DIR"/rooms/level_[0-9][0-9][0-9].json)
    for J in "${LEVELS[@]}"; do
        python3 "$ROOT/tools/convert_level.py" "$J" "$DIR/generated/$(basename "$J" .json)" "$DIR/rooms"
    done

    # Generate levels index (LevelDataTable with all levels)
    python3 "$ROOT/tools/convert_level.py" --levels "$DIR/generated/levels.asm" \
        "${LEVELS[@]}"
fi

# level-data window pre-check (bugs.md 27): fail early with the placement
# map instead of DASM's cryptic `Origin Reverse-indexed` at the pad line
python3 "$ROOT/tools/verify_build.py" --precheck "$DIR"

# Assemble each bank (from src/ so include paths resolve)
# C7 (2026-10-20): the level-data subsystem is SPLIT — bank3 owns the shape
# blocks + extras streams and every walker that reads them, bank2 owns the
# level/room/enemy tables and theirs. bank3 assembles FIRST (the HOF pad
# literal is patched from its listing), then bank2, then the bank0 literals.
cd "$DIR"
dasm bank3.asm -f3 -obank3.bin -lbank3.lst
echo "  bank3: OK"
dasm bank2.asm -f3 -obank2.bin -lbank2.lst
echo "  bank2: OK"
# kernel's HotOverlapFlag pad ends `jmp $xxxx` -> bank3 HotOverlapBody
python3 "$ROOT/tools/verify_build.py" --sync-hof "$DIR"
python3 "$ROOT/tools/verify_build.py" --sync "$DIR"
dasm kernel.asm -f3 -obank0.bin -lbank0.lst -sgenerated/symbols.asm
echo "  bank0: OK"
# bank1's fold pad jmp literal tracks Overscan (moves with pre-pad code) —
# self-heal from bank0.lst instead of the hand-sync that bit us 3+ times.
python3 "$ROOT/tools/verify_build.py" --sync-overscan "$DIR"
dasm bank1.asm -f3 -obank1.bin -lbank1.lst
echo "  bank1: OK"
# F4 (32K): banks 4-6 are free windows, bank7 is the power-up bank (F4 reads
# its reset vector from the LAST bank). No cross-bank literals in them yet.
for b in 4 5 6 7; do
    dasm "bank$b.asm" -f3 -o"bank$b.bin" -l"bank$b.lst"
    echo "  bank$b: OK"
done

# Pad each bank to exactly 4K (DASM doesn't emit trailing zeros)
for i in 0 1 2 3 4 5 6 7; do
    SIZE=$(wc -c < "bank${i}.bin")
    if [ "$SIZE" -lt 4096 ]; then
        PAD=$((4096 - SIZE))
        printf '\0%.0s' $(seq 1 $PAD) >> "bank${i}.bin"
        echo "  bank${i}: padded $SIZE → 4096"
    elif [ "$SIZE" -eq 4096 ]; then
        echo "  bank${i}: $SIZE bytes (exact)"
    else
        echo "ERROR: bank${i}.bin is $SIZE bytes (exceeds 4K)"
        exit 1
    fi
done

# Verify banks + level data BEFORE shipping (errors abort via set -e)
python3 "$ROOT/tools/verify_build.py" "$DIR"

# Headless py65 sim: bomb lifecycle + stack-depth guard (AGENTS.md stack rule).
# Hard-fails the build on regression; skips with a warning only if py65 is absent.
SIM_PY="${SIM_PY:-/home/iuri/python3/bin/python3}"
if "$SIM_PY" -c "import py65" 2>/dev/null; then
    echo "  sim_bomb_fuse: running..."
    "$SIM_PY" "$DIR/sim_bomb_fuse.py" > /tmp/sim_bomb_fuse.out 2>&1 || {
        echo "SIM FAILED — last lines:"
        tail -20 /tmp/sim_bomb_fuse.out
        exit 1
    }
    echo "  sim_bomb_fuse: OK"
else
    echo "  WARNING: py65 not importable via $SIM_PY — sim_bomb_fuse SKIPPED"
    echo "           (enable: $SIM_PY -m pip install py65)"
fi

# Concatenate into 16K ROM
cat bank0.bin bank1.bin bank2.bin bank3.bin \
    bank4.bin bank5.bin bank6.bin bank7.bin > "$OUTPUT"

# Headless frame-budget sim: worst-case frame (fly + laser held + bomb +
# 2 objects) must hold 263 lines/frame — hard-fails on flicker regressions.
if "$SIM_PY" -c "import py65" 2>/dev/null; then
    echo "  sim_frame_budget: running..."
    "$SIM_PY" "$DIR/sim_frame_budget.py" > /tmp/sim_frame_budget.out 2>&1 || {
        echo "SIM FAILED — last lines:"
        tail -25 /tmp/sim_frame_budget.out
        exit 1
    }
    echo "  sim_frame_budget: OK"
else
    echo "  WARNING: py65 not importable via $SIM_PY — sim_frame_budget SKIPPED"
fi

SIZE=$(wc -c < "$OUTPUT")
echo "Done: $OUTPUT ($SIZE bytes, F4 bankswitch)"
