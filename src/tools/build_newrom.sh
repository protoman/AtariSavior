#!/bin/bash
# Build the NEW (empty, being filled) ROM layout of docs/agents/banks.md from src/newrom/.
# The old ROM (build.sh) is untouched. Output: newrom/savior_new.bin (32K) + the boot-bank check.
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SRC/newrom"
# bank0 first: its symbols feed the cave bank's equates (newrom/generated is the new ROM's own output dir)
mkdir -p generated
dasm bank0.asm -f3 -I. -I.. -I../generated -obank0.bin -lbank0.lst -sgenerated/symbols.asm > /dev/null
python3 "$SRC/tools/gen_bank6_equs.py" "$SRC/newrom"
python3 "$SRC/tools/cave_kernel_gen.py" --real "$SRC/newrom/generated" "$SRC/kernel.asm" > /dev/null
for b in 0 1 2 3 4 5 6 7; do
    dasm "bank$b.asm" -f3 -I. -Igenerated -I.. -I../generated -o"bank$b.bin" -l"bank$b.lst" > /dev/null
    SIZE=$(wc -c < "bank$b.bin")
    if [ "$SIZE" -gt 4096 ]; then echo "ERROR: newrom bank$b is $SIZE bytes (exceeds 4K)"; exit 1; fi
    if [ "$SIZE" -lt 4096 ]; then printf '\0%.0s' $(seq 1 $((4096 - SIZE))) >> "bank$b.bin"; fi
done
cat bank0.bin bank1.bin bank2.bin bank3.bin bank4.bin bank5.bin bank6.bin bank7.bin > savior_new.bin
python3 "$SRC/tools/check_newrom.py" "$SRC/newrom"
echo "newrom: savior_new.bin ($(wc -c < savior_new.bin) bytes)"
