#!/bin/bash
# Wall-lamp demo build: a throwaway ROM with a LAMP in one room, so the new art
# and the wall-side mirror can be checked in game without touching the stage.
#
# Run: bash tools/lamp_build.sh [out.bin] [col] [y] [wall_cell] [level] [room]
#   col  lamp display column 0..39 (editor units, the lamp is centred). Empty
#        ("") = keep the room's first enemy x, i.e. put the lamp where that
#        enemy stood.
#   y    lamp row 0..11 (12 px each; band = y // 4). Empty = same spot.
#   wall_cell  OPTIONAL: make this cell of the lamp's band SOLID in the room's
#              model, so the lamp has a wall on its RIGHT and the converter
#              derives TYPE 13 (the mirrored design).
#   level/room are 1-BASED, default 2/2. The build prints the derived TYPE:
#              5 = drawn art (bracket left), 13 = the horizontal mirror.
#
# SAFE BY CONSTRUCTION (2026-10-22): it never writes src/rooms. build.sh takes
# the stage from STAGE_FILE, so the demo builds from a TEMP COPY of the stage
# and the user's tree keeps being edited by the editor in the meantime. The
# live ROM is rebuilt at the end because the conversion writes src/generated.
set -e
DIR="$(cd "$(dirname "$0")/../src" && pwd)"
TOOLS="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-python3}"
OUT="${1:-/tmp/opencode/savior_lamp.bin}"
COL="${2:-}"
ROW="${3:-}"
WALL_CELL="${4:-}"
LEVEL="${5:-3}"
ROOM="${6:-2}"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
trap 'exit 130' INT TERM

mkdir -p "$TMP/rooms"
cp -a "$DIR/rooms/stage.json" "$TMP/rooms/"
cp -a "$DIR/rooms/models" "$TMP/rooms/"

echo "lamp_build: staged a COPY of the stage in $TMP (src/rooms is never written)"
"$PY" - "$TOOLS" "$TMP/rooms" "$COL" "$ROW" "$WALL_CELL" "$LEVEL" "$ROOM" <<'PY'
import json
import sys
from pathlib import Path

tools, rooms = Path(sys.argv[1]), Path(sys.argv[2])
col_arg, row_arg = sys.argv[3], sys.argv[4]
wall_cell = int(sys.argv[5]) if sys.argv[5] else None
want_level, want_room = int(sys.argv[6]), int(sys.argv[7])

sys.path.insert(0, str(tools))
import convert_level as CV

stage_path = rooms / "stage.json"
d = json.load(open(stage_path))
room = None
for level in d["stage"]["levels"]:
    if int(level.get("level_id", 0)) != want_level:
        continue
    for r in level["rooms"]:
        if int(r.get("room_id", -1)) == want_room - 1:
            room = r
assert room is not None, f"level {want_level} room {want_room} not found"

# Position: explicit, else the spot of the room's first enemy (so the lamp
# replaces that object instead of landing in a wall).
enemy = (room.get("enemies") or [None])[0]
col = float(col_arg) if col_arg else float((enemy or {}).get("x", 16))
row = float(row_arg) if row_arg else float((enemy or {}).get("y", 4))

# A lamp goes in `lamps` (verify_build rejects type 5 in `enemies`); the room's
# enemies are cleared so the demo shows the lamp alone (a lamp + another object
# in one band still rotates, and the miner would share the REFP1 write).
room["enemies"] = []
room["lamps"] = [{"x": col, "y": row}]

models_path = rooms / "models" / "models.json"
models = CV.load_models(models_path)
if wall_cell is not None:
    raw = json.load(open(models_path))
    entries = raw.get("models_file", raw).get("models", [])
    entry = next(e for e in entries if e.get("id") == room.get("model_id"))
    width = int(entry.get("width", 10))
    band = max(0, min(int(row) // 4, 2))
    entry["tiles"][band * width + wall_cell] = 1
    json.dump(raw, open(models_path, "w"), indent=1)
    models = CV.load_models(models_path)
    print(f"  model {room.get('model_id')}: band {band} cell {wall_cell} made solid")

json.dump(d, open(stage_path, "w"), indent=1)
lamp_type = CV._lamp_type(room, col, row, models)
print(f"  lamp in level {want_level} room {want_room} at col {col:g} row {row:g} "
      f"-> TYPE {lamp_type} "
      f"({'mirrored design' if lamp_type == 13 else 'drawn art'})")
PY

echo "lamp_build: building the demo ROM (sims skipped — they probe live content) ..."
( cd "$DIR" && STAGE_FILE="$TMP/rooms/stage.json" SIM_PY=/bin/false \
    ./build.sh "$OUT" )

echo "lamp_build: rebuilding the live ROM + generated data ..."
( cd "$DIR" && ./build.sh >/dev/null )
echo "lamp_build: done -> $OUT"
echo "lamp_build: in game, go to level $LEVEL room $ROOM"
