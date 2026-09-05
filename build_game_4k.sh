#!/bin/sh
set -eu

mkdir -p generated
python3 tools/convert_room.py \
  rooms/level_001_room_001.txt \
  generated/level_001_room_001.asm
dasm game_4k.asm -f3 -osavior.bin
