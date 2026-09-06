#!/bin/sh
set -eu

mkdir -p generated
python3 tools/convert_level.py \
  rooms/level_001.json \
  generated/level_001 \
  rooms
dasm game_4k.asm -f3 -osavior.bin