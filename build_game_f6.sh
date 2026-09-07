#!/bin/sh
set -eu

mkdir -p generated
python3 tools/convert_level.py rooms/level_001.json generated/level_001 rooms
python3 tools/convert_level.py rooms/level_002.json generated/level_002 rooms
python3 tools/convert_level.py --levels generated/levels.asm rooms/level_001.json rooms/level_002.json

dasm comparison/lo-a-rad-dragon/bank0.asm -f3 -ocomparison/lo-a-rad-dragon/bank0.bin
dasm comparison/lo-a-rad-dragon/bank1.asm -f3 -ocomparison/lo-a-rad-dragon/bank1.bin
dasm comparison/lo-a-rad-dragon/bank2.asm -f3 -ocomparison/lo-a-rad-dragon/bank2.bin
dasm comparison/lo-a-rad-dragon/bank3.asm -f3 -ocomparison/lo-a-rad-dragon/bank3.bin
cat comparison/lo-a-rad-dragon/bank0.bin comparison/lo-a-rad-dragon/bank1.bin \
    comparison/lo-a-rad-dragon/bank2.bin comparison/lo-a-rad-dragon/bank3.bin \
    > savior.bin