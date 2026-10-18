#!/bin/bash
# Raft demo build: a throwaway ROM whose level-2 water room carries the MOVING
# raft instead of its tentacle, so the feature can be played end to end.
#
# Run: bash tools/raft_build.sh [out.bin]   (default /tmp/opencode/savior_raft.bin)
# In game: level 2 -> descend from the start room into the water room. The raft
# patrols the channel between the ledges; stand on a ledge, let it come under
# you and step off to drop onto it. It carries you across and comes back.
#
# Why a staged COPY of the live stage:
#   * level 2 room 1 is the only live water room and it sits at the 2-object cap
#     (tentacle + the level's miner). A raft needs a slot.
#   * swapping the tentacle out IN PLACE breaks sim_bomb_fuse: it forces Level 2
#     and fabricates that room's enemies for the bomb-hole check (/tmp/sim_bomb_fuse.out).
#   * every other level-2 position is unreachable: models 2 and 3 are solid at
#     display cols 0-1 / 38-39 in all three bands, so the start room has no
#     left/right exit to hang a new room off.
# So: copy rooms/ + generated/, edit the COPY, build the demo, restore, rebuild
# the live ROM. The live stage, its ROM and both sims are never modified.
set -e
DIR="$(cd "$(dirname "$0")/../src" && pwd)"
PY="${PY:-python3}"
OUT="${1:-/tmp/opencode/savior_raft.bin}"
TMP="$(mktemp -d)"
DONE=0

restore() {
    if [ "$DONE" = 0 ] && [ -d "$TMP/rooms" ]; then
        rm -rf "$DIR/rooms" "$DIR/generated"
        cp -a "$TMP/rooms" "$DIR/rooms"
        cp -a "$TMP/generated" "$DIR/generated"
        DONE=1
    fi
    rm -rf "$TMP"
}
trap restore EXIT

cp -a "$DIR/rooms" "$TMP/rooms"
cp -a "$DIR/generated" "$TMP/generated"

echo "raft_build: staging a stage copy with the raft in the level-2 water room ..."
"$PY" - "$DIR/rooms/level_002.json" <<'PY'
import json
import sys

path = sys.argv[1]
d = json.load(open(path))
for r in d["level"]["rooms"]:
    if not r.get("bottom_band"):
        continue
    out = []
    for e in r.get("enemies") or []:
        if int(e.get("type", 0)) == 3:          # the tentacle -> the moving raft
            e = dict(e, type=7, x=20.0, y=11.0, range_min=20.0, range_max=20.0)
        out.append(e)
    r["enemies"] = out
    print(f"  water room {r['room_id']}: enemies -> "
          f"{[(e['type'], e['x'], e['y']) for e in out]}")
json.dump(d, open(path, "w"), indent=1)
PY

echo "raft_build: building the demo ROM (sims skipped — they probe live content) ..."
( cd "$DIR" && SIM_PY=/bin/false ./build.sh "$OUT" )
cp "$DIR/bank0.lst" "${OUT%.bin}.bank0.lst"
cp "$DIR/bank1.lst" "${OUT%.bin}.bank1.lst"

restore
echo "raft_build: rebuilding the live ROM ..."
( cd "$DIR" && ./build.sh >/dev/null )
echo "raft_build: done -> $OUT"
echo "raft_build: play level 2 and drop into the water room (raft patrols the channel)"
