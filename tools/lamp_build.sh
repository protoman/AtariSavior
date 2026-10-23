#!/bin/bash
# Wall-lamp demo build: a throwaway ROM with a LAMP in one room, so the art and
# the wall-side mirror can be checked in game without touching the stage.
#
# Run: bash tools/lamp_build.sh [out.bin] [col] [y] [wall_cell] [level] [room]
#   col  lamp display column 0..39 (the art is left-aligned in the cell that
#        contains it). Empty ("") = the room's first enemy x.
#   y    lamp row 0..11 (12 px each; band = y // 4). Empty = same spot.
#   cells  OPTIONAL: comma list of edits in the lamp's band, each "cell" (make
#          SOLID) or "cell=0" (make AIR), e.g. "7=0,9=1". Used to give the lamp
#          a wall on its RIGHT so the converter derives TYPE 13 (the mirror).
#   level/room are 1-BASED, default 3/2. The build prints the derived TYPE:
#              5 = drawn art (bracket left), 13 = the horizontal mirror.
#
# The models come from the STAGE FILE (stage.json carries them; the legacy
# models/models.json has only a dozen and is NOT what the build reads).
#
# SAFE BY CONSTRUCTION: it never writes src/rooms. build.sh takes the stage from
# STAGE_FILE, so the demo builds from a TEMP COPY and the user's tree keeps
# being edited by the editor in the meantime. The live ROM is rebuilt at the end
# because the conversion writes src/generated.
set -e
DIR="$(cd "$(dirname "$0")/../src" && pwd)"
TOOLS="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-python3}"
OUT="${1:-/tmp/opencode/savior_lamp.bin}"
COL="${2:-}"
ROW="${3:-}"
CELLS="${4:-}"
LEVEL="${5:-3}"
ROOM="${6:-2}"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
trap 'exit 130' INT TERM

mkdir -p "$TMP/rooms"
cp -a "$DIR/rooms/stage.json" "$TMP/rooms/"

echo "lamp_build: staged a COPY of the stage in $TMP (src/rooms is never written)"
"$PY" - "$TOOLS" "$TMP/rooms" "$COL" "$ROW" "$CELLS" "$LEVEL" "$ROOM" <<'PY'
import json
import sys
from pathlib import Path

tools, rooms = Path(sys.argv[1]), Path(sys.argv[2])
col_arg, row_arg = sys.argv[3], sys.argv[4]
edits = []
for spec in (sys.argv[5] or "").split(","):
    spec = spec.strip()
    if spec:
        cell, _, val = spec.partition("=")
        edits.append((int(cell), int(val) if val else 1))
want_level, want_room = int(sys.argv[6]), int(sys.argv[7])

sys.path.insert(0, str(tools))
import convert_level as CV

stage_path = rooms / "stage.json"
d = json.load(open(stage_path))
stage = d["stage"]
models = {m["id"]: m for m in stage.get("models", [])}
print(f"  stage models: {len(models)}")

room = None
for level in stage["levels"]:
    if int(level.get("level_id", 0)) != want_level:
        continue
    for r in level["rooms"]:
        if int(r.get("room_id", -1)) == want_room - 1:
            room = r
assert room is not None, f"level {want_level} room {want_room} not found"

enemy = (room.get("enemies") or [None])[0]
col = float(col_arg) if col_arg else float((enemy or {}).get("x", 16))
row = float(row_arg) if row_arg else float((enemy or {}).get("y", 4))
band = max(0, min(int(row) // 4, 2))

# A lamp goes in `lamps` (verify_build rejects type 5 in `enemies`); the room's
# enemies are cleared so the demo shows the lamp alone (a lamp sharing a band
# with another object rotates, and the miner would fight it for REFP1).
room["enemies"] = []
room["lamps"] = [{"x": col, "y": row}]

model = models.get(room.get("model_id"))
if model:
    width = int(model.get("width", 10))
    print("  model %s band %d: %s" % (room.get("model_id"), band,
          "".join("#" if c else "." for c in model["tiles"][band * width:(band + 1) * width])))
if edits:
    assert model, f"room model {room.get('model_id')} not in the stage models"
    width = int(model.get("width", 10))
    for cell, val in edits:
        model["tiles"][band * width + cell] = val
    print(f"  model {room.get('model_id')}: band {band} edits {edits}")

json.dump(d, open(stage_path, "w"), indent=1)
lamp_type = CV._lamp_type(room, col, row, models)
x = CV.lamp_x_px(col)
print(f"  lamp in level {want_level} room {want_room}: col {col:g} row {row:g} "
      f"-> TYPE {lamp_type} ({'mirrored' if lamp_type == 13 else 'drawn art'}), "
      f"X={x} (left edge px {x - (4 if x < 15 else 7)})")
PY

echo "lamp_build: building the demo ROM (sims skipped — they probe live content) ..."
( cd "$DIR" && STAGE_FILE="$TMP/rooms/stage.json" SIM_PY=/bin/false \
    ./build.sh "$OUT" )

echo "lamp_build: rebuilding the live ROM + generated data ..."
( cd "$DIR" && ./build.sh >/dev/null )
echo "lamp_build: done -> $OUT"
echo "lamp_build: in game, go to level $LEVEL room $ROOM"
