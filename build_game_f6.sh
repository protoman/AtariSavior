#!/bin/sh
set -eu

mkdir -p generated
python3 tools/convert_level.py rooms/level_001.json generated/level_001 rooms
python3 tools/convert_level.py rooms/level_002.json generated/level_002 rooms
python3 tools/convert_level.py --levels generated/levels.asm rooms/level_001.json rooms/level_002.json
python3 tools/port_13plus2.py generated/menu_13plus2.asm
python3 tools/font.py hud "levelscorbmti 0123456789." "level" generated/hud_font.asm

dasm comparison/lo-a-rad-dragon/bank0.asm -f3 -ocomparison/lo-a-rad-dragon/bank0.bin
dasm src/bank1.asm -f3 -osrc/bank1.bin
dasm src/bank2.asm -f3 -osrc/bank2.bin
dasm src/bank3.asm -f3 -osrc/bank3.bin
cat comparison/lo-a-rad-dragon/bank0.bin src/bank1.bin \
    src/bank2.bin src/bank3.bin \
    > savior.bin
