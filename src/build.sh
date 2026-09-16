#!/bin/bash
# Build the savior kernel ROM (F6 bankswitch, 16K)
# Usage: ./build.sh [filename]
# Output: savior.bin (16K, 4 × 4K banks)

set -e

OUTPUT="${1:-savior.bin}"
DIR="$(dirname "$0")"

echo "Building F6 ROM (4 banks)..."

# Assemble each bank
dasm "$DIR/kernel.asm" -f3 -o"$DIR/bank0.bin" -l"$DIR/bank0.lst" && echo "  bank0: OK" || echo "  bank0: FAILED"
dasm "$DIR/bank1.asm" -f3 -o"$DIR/bank1.bin" && echo "  bank1: OK" || echo "  bank1: FAILED"
dasm "$DIR/bank2.asm" -f3 -o"$DIR/bank2.bin" && echo "  bank2: OK" || echo "  bank2: FAILED"
dasm "$DIR/bank3.asm" -f3 -o"$DIR/bank3.bin" && echo "  bank3: OK" || echo "  bank3: FAILED"

# Pad each bank to exactly 4K (DASM doesn't emit trailing zeros)
for i in 0 1 2 3; do
    SIZE=$(wc -c < "$DIR/bank${i}.bin")
    if [ "$SIZE" -lt 4096 ]; then
        PAD=$((4096 - SIZE))
        printf '\0%.0s' $(seq 1 $PAD) >> "$DIR/bank${i}.bin"
        echo "  bank${i}: padded $SIZE → 4096"
    elif [ "$SIZE" -eq 4096 ]; then
        echo "  bank${i}: $SIZE bytes (exact)"
    else
        echo "ERROR: bank${i}.bin is $SIZE bytes (exceeds 4K)"
        exit 1
    fi
done

# Concatenate into 16K ROM
cat "$DIR/bank0.bin" "$DIR/bank1.bin" "$DIR/bank2.bin" "$DIR/bank3.bin" > "$OUTPUT"

SIZE=$(wc -c < "$OUTPUT")
echo "Done: $OUTPUT ($SIZE bytes, F6 bankswitch)"
