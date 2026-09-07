#!/bin/sh
set -eu

mkdir -p generated
python3 tools/convert_level.py rooms/level_001.json generated/level_001 rooms
python3 tools/convert_level.py rooms/level_002.json generated/level_002 rooms
python3 tools/convert_level.py --levels generated/levels.asm rooms/level_001.json rooms/level_002.json
dasm game_4k.asm -f3 -osavior.bin