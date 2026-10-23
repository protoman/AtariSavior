#!/bin/bash
# Wall-lamp demo build: a throwaway ROM with a LAMP in level 2 room 2 (the live
# stage has no lamps yet), so the new art and the wall-side mirror can be
# checked in game. The live stage and its ROM are never modified.
#
# Run: bash tools/lamp_build.sh [out.bin] [col] [y] [wall_cell] [level] [room]
#   col  lamp display column 0..39 (editor units, the lamp is centred)
#   y    lamp row 0..11 (12 px each; band = y // 4)
#   wall_cell  OPTIONAL: make this cell of the lamp's band SOLID in the room's
#              model. The lamp then has a wall on its RIGHT and the converter
#              derives TYPE 13 (the mirrored design). Without it the model is
#              untouched.
#   level/room are 1-BASED, default 2/2 (level 2 -> descend from the start).
#
# The build prints the lamp TYPE the converter derived (5 = drawn art, 13 =
# the horizontal mirror), so a demo build also checks the derivation.
#
# Same discipline as raft_build.sh / spider_build.sh: copy src/rooms +
# src/generated, edit the COPY, build with the sims skipped (they probe live
# content), then restore and rebuild the live ROM.
set -e
DIR="$(cd "$(dirname "$0")/../src" && pwd)"
TOOLS="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-python3}"
OUT="${1:-/tmp/opencode/savior_lamp.bin}"
COL="${2:-4}"
ROW="${3:-2}"
WALL_CELL="${4:-}"
LEVEL="${5:-2}"
ROOM="${6:-2}"
TMP="$(mktemp -d)"
DONE=0

restore() {
    rc=$?
    if [ "$DONE" = 0 ] && [ -d "$TMP/rooms" ]; then
        rm -rf "$DIR/rooms" "$DIR/generated"
        cp -a "$TMP/rooms" "$DIR/rooms"
        cp -a "$TMP/generated" "$DIR/generated"
        DONE=1
        now="$(cd "$DIR" && find rooms -type f -print0 | sort -z | \
               xargs -0 sha256sum | sha256sum)"
        if [ -n "$LIVE_SHA" ] && [ "$now" != "$LIVE_SHA" ]; then
            echo "lamp_build: *** LIVE STAGE MISMATCH AFTER RESTORE ***" >&2
            echo "lamp_build: src/rooms != pre-build snapshot — DO NOT COMMIT." >&2
            rc=1
        fi
    fi
    rm -rf "$TMP"
    exit $rc
}
trap restore EXIT
trap 'exit 130' INT TERM
export FREEZE_STAGED=1

cp -a "$DIR/rooms" "$TMP/rooms"
cp -a "$DIR/generated" "$TMP/generated"
LIVE_SHA="$(cd "$DIR" && find rooms -type f -print0 | sort -z | \
            xargs -0 sha256sum | sha256sum)"

echo "lamp_build: staging a stage copy with a LAMP at col $COL row $ROW in level $LEVEL room $ROOM ..."
"$PY" - "$TOOLS" "$DIR/rooms" "$COL" "$ROW" "$WALL_CELL" "$LEVEL" "$ROOM" <<'PY'
import json
import sys
from pathlib import Path

tools, rooms = Path(sys.argv[1]), Path(sys.argv[2])
col, row = float(sys.argv[3]), float(sys.argv[4])
wall_cell = int(sys.argv[5]) if sys.argv[5] else None
want_level, want_room = int(sys.argv[6]), int(sys.argv[7])

sys.path.insert(0, str(tools))
import convert_level as CV

stage_path = rooms / "stage.json"
assert stage_path.exists(), "no stage.json in the staged copy"
d = json.load(open(stage_path))
room = model = None
for level in d["stage"]["levels"]:
    if int(level.get("level_id", 0)) != want_level:
        continue
    for r in level["rooms"]:
        if int(r.get("room_id", -1)) == want_room - 1:
            room = r
assert room is not None, f"level {want_level} room {want_room} not found"

# The lamp goes in `lamps` (verify_build rejects type 5 in `enemies`), and the
# room's enemies are cleared so the demo shows the lamp alone.
room["enemies"] = []
room["lamps"] = [{"x": col, "y": row}]

models_path = rooms / "models" / "models.json"
models = CV.load_models(models_path)
model = models.get(room.get("model_id"))
if wall_cell is not None:
    raw = json.load(open(models_path))
    entries = raw.get("models_file", raw).get("models", [])
    entry = next(e for e in entries if e.get("id") == room["model_id"])
    width = int(entry.get("width", 10))
    band = max(0, min(int(row) // 4, 2))
    entry["tiles"][band * width + wall_cell] = 1
    json.dump(raw, open(models_path, "w"), indent=1)
    models = CV.load_models(models_path)
    print(f"  model {room['model_id']}: band {band} cell {wall_cell} made solid")

json.dump(d, open(stage_path, "w"), indent=1)
lamp_type = CV._lamp_type(room, col, row, models)
print(f"  lamp at col {col} row {row} -> converter picked TYPE {lamp_type} "
      f"({'mirrored design' if lamp_type == 13 else 'drawn art'})")
PY

echo "lamp_build: building the demo ROM (sims skipped — they probe live content) ..."
( cd "$DIR" && SIM_PY=/bin/false ./build.sh "$OUT" )

restore
echo "lamp_build: rebuilding the live ROM ..."
( cd "$DIR" && ./build.sh >/dev/null )
echo "lamp_build: done -> $OUT"
echo "lamp_build: play level 2, descend from the start room; the lamp is in room 2"
