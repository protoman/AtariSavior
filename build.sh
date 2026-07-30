#!/bin/bash
set -e

echo "Assembling bank0..."
dasm bank0.asm -f3 -obank0.bin

echo "Assembling bank1..."
dasm bank1.asm -f3 -obank1.bin

echo "Assembling bank2..."
dasm bank2.asm -f3 -obank2.bin

echo "Assembling bank3..."
dasm bank3.asm -f3 -obank3.bin

echo "Concatenating banks..."
cat bank0.bin bank1.bin bank2.bin bank3.bin > rom.bin

echo "Done. rom.bin is $(wc -c < rom.bin) bytes."

for f in bank*.bin; do
    echo "  $f: $(wc -c < $f) bytes"
done
