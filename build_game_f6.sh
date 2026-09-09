#!/bin/sh
set -eu

mkdir -p generated
python3 tools/convert_level.py rooms/level_001.json generated/level_001 rooms
python3 tools/convert_level.py rooms/level_002.json generated/level_002 rooms
python3 tools/convert_level.py --levels generated/levels.asm rooms/level_001.json rooms/level_002.json
python3 tools/port_13plus2.py generated/menu_13plus2.asm
python3 tools/font.py hud "levelscorbmti 0123456789." "level;score 00.000;lives 3 bombs 4;time 200" generated/hud_font.asm
python3 tools/font.py slots HudSlots "Level:level;Score:score 00.000;Lives:lives 3 bombs 4;Time:time 200" generated/hud_slots.asm

dasm comparison/lo-a-rad-dragon/bank0.asm -f3 -ocomparison/lo-a-rad-dragon/bank0.bin
dasm comparison/lo-a-rad-dragon/bank1.asm -f3 -ocomparison/lo-a-rad-dragon/bank1.bin
dasm comparison/lo-a-rad-dragon/bank2.asm -f3 -ocomparison/lo-a-rad-dragon/bank2.bin
dasm comparison/lo-a-rad-dragon/bank3.asm -f3 -ocomparison/lo-a-rad-dragon/bank3.bin
cat comparison/lo-a-rad-dragon/bank0.bin comparison/lo-a-rad-dragon/bank1.bin \
    comparison/lo-a-rad-dragon/bank2.bin comparison/lo-a-rad-dragon/bank3.bin \
    > savior.bin
