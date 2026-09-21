#!/bin/bash
# Build the savior kernel ROM (F6 bankswitch, 16K)
# Usage: ./build.sh [filename]
# Output: savior.bin (16K, 4 × 4K banks)

set -e

OUTPUT="${1:-savior.bin}"
DIR="$(dirname "$0")"
ROOT="$(cd "$DIR/.." && pwd)"

echo "Building F6 ROM (4 banks)..."

# Generate room data from text files
echo "  Generating room data..."
python3 "$ROOT/tools/convert_room.py" "$DIR/rooms/level_001_room_001.txt" "$DIR/generated/level_001_room_001.asm"

# Assemble each bank (from src/ so include paths resolve)
cd "$DIR"
dasm kernel.asm -f3 -obank0.bin -lbank0.lst && echo "  bank0: OK" || echo "  bank0: FAILED"
dasm bank1.asm -f3 -obank1.bin && echo "  bank1: OK" || echo "  bank1: FAILED"
dasm bank2.asm -f3 -obank2.bin && echo "  bank2: OK" || echo "  bank2: FAILED"
dasm bank3.asm -f3 -obank3.bin && echo "  bank3: OK" || echo "  bank3: FAILED"

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

# Concatenate into 16K ROM
cat bank0.bin bank1.bin bank2.bin bank3.bin > "$OUTPUT"

SIZE=$(wc -c < "$OUTPUT")
echo "Done: $OUTPUT ($SIZE bytes, F6 bankswitch)"
