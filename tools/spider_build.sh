#!/bin/bash
# Enemy-art demo build: a throwaway ROM whose level-2 room 2 carries the enemy
# type you name instead of its bat, so a new sprite can be played without
# touching the user's stage.
#
# Run: bash tools/spider_build.sh [out.bin] [type] [level] [room]
#      type defaults to 0 = SPIDER (1 BAT, 2 SNAKE, 3 TENTACLE, 4 MOTH,
#      5 LAMP, 6 KEY, 7 RAFT); out defaults to /tmp/opencode/savior_demo_<type>.bin
#      (kept as savior_spider.bin for type 0). level/room are 1-BASED and
#      default to 2/2; some types need a specific room (a TENTACLE must be in
#      a water room, i.e. level 4 room 4, which carries the raft).
# In game: level 2 -> descend from the start room; room 2 has the enemy.
#
# Why a staged COPY of the live stage (same pattern as raft_build.sh):
# src/rooms/ + src/generated/ belong to the user. Copy them, edit the COPY,
# build, restore, rebuild the live ROM. The live stage and its ROM are never
# modified, and the sims are skipped because they probe live content.
set -e
DIR="$(cd "$(dirname "$0")/../src" && pwd)"
PY="${PY:-python3}"
TYPE="${2:-0}"
LEVEL="${3:-2}"
ROOM="${4:-2}"
if [ "$TYPE" = 0 ]; then
    OUT="${1:-/tmp/opencode/savior_spider.bin}"
else
    OUT="${1:-/tmp/opencode/savior_demo_${TYPE}.bin}"
fi
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
            echo "spider_build: *** LIVE STAGE MISMATCH AFTER RESTORE ***" >&2
            echo "spider_build: src/rooms != pre-build snapshot — DO NOT COMMIT." >&2
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

echo "spider_build: staging a stage copy with enemy type $TYPE in level $LEVEL room $ROOM ..."
"$PY" - "$DIR/rooms" "$TYPE" "$LEVEL" "$ROOM" <<'PY'
import json
import sys
from pathlib import Path

rooms = Path(sys.argv[1])
SPIDER = int(sys.argv[2])
WANT_LEVEL = int(sys.argv[3])
WANT_ROOM = int(sys.argv[4])
targets = [p for p in (rooms / "stage.json",
                       rooms / "level_002.json") if p.exists()]
assert targets, "no stage.json / level_002.json in the staged copy"
for path in targets:
    d = json.load(open(path))
    unified = "stage" in d
    levels = d["stage"]["levels"] if unified else [d["level"]]
    hit = 0
    for level in levels:
        # stage.json: level_id is 1-BASED (2 = the user's level 2)
        if unified and int(level.get("level_id", 0)) != WANT_LEVEL:
            continue
        for r in level["rooms"]:
            if int(r.get("room_id", -1)) != WANT_ROOM - 1:   # room_id is 0-based
                continue
            out = []
            for e in r.get("enemies") or []:
                e = dict(e, type=SPIDER)            # bat -> spider, same spot
                hit += 1
                out.append(e)
            r["enemies"] = out
    json.dump(d, open(path, "w"), indent=1)
    print(f"  {path.name}: {hit} enemy(ies) -> type {SPIDER}")
    # stage.json is what the build reads; the legacy per-level file only has
    # level 2, so a miss there is expected when another level was targeted.
    if unified:
        assert hit, (f"no enemy found in level {WANT_LEVEL} room {WANT_ROOM} of "
                     f"{path.name}")
PY

echo "spider_build: building the demo ROM (sims skipped — they probe live content) ..."
( cd "$DIR" && SIM_PY=/bin/false ./build.sh "$OUT" )
cp "$DIR/bank0.lst" "${OUT%.bin}.bank0.lst"
cp "$DIR/bank1.lst" "${OUT%.bin}.bank1.lst"

restore
echo "spider_build: rebuilding the live ROM ..."
( cd "$DIR" && ./build.sh >/dev/null )
echo "spider_build: done -> $OUT"
echo "spider_build: play level 2, room 2 (start room 1 -> descend)"
