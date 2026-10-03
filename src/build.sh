#!/bin/bash
# Build the savior kernel ROM (F6 bankswitch, 16K)
# Usage: ./build.sh [filename]
# Output: savior.bin (16K, 4 × 4K banks)

set -e

OUTPUT="${1:-savior.bin}"
DIR="$(dirname "$0")"
ROOT="$(cd "$DIR/.." && pwd)"

echo "Building F6 ROM (4 banks)..."

# Generate level data from JSON (every rooms/level_XXX.json — no hardcode)
echo "  Generating level data..."
LEVELS=("$DIR"/rooms/level_[0-9][0-9][0-9].json)
for J in "${LEVELS[@]}"; do
    python3 "$ROOT/tools/convert_level.py" "$J" "$DIR/generated/$(basename "$J" .json)" "$DIR/rooms"
done

# Generate levels index (LevelDataTable with all levels)
python3 "$ROOT/tools/convert_level.py" --levels "$DIR/generated/levels.asm" \
    "${LEVELS[@]}"

# Assemble each bank (from src/ so include paths resolve)
# bank2 FIRST: its LevelDataTable address is synced into kernel.asm
# (frozen-literal self-heal) before bank0 bakes it into an immediate.
cd "$DIR"
dasm bank2.asm -f3 -obank2.bin -lbank2.lst
echo "  bank2: OK"
python3 "$ROOT/tools/verify_build.py" --sync "$DIR"
dasm kernel.asm -f3 -obank0.bin -lbank0.lst
echo "  bank0: OK"
dasm bank1.asm -f3 -obank1.bin -lbank1.lst
echo "  bank1: OK"
dasm bank3.asm -f3 -obank3.bin
echo "  bank3: OK"

# Pad each bank to exactly 4K (DASM doesn't emit trailing zeros)
for i in 0 1 2 3; do
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
cat bank0.bin bank1.bin bank2.bin bank3.bin > "$OUTPUT"

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
echo "Done: $OUTPUT ($SIZE bytes, F6 bankswitch)"
