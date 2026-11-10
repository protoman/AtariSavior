#!/bin/bash
# The playbot flies the LIVE stage (rooms/stage.json - the data you see in the editor;
# user 2026-11-10: the bot must always use existing level data), built in a scratch
# copy of src/ (rooms/ and generated/ are never touched). FRESH=1 generates a new stage
# in the scratch copy instead.
#   tools/stage_check.sh [playbot args, e.g. 2 3 --safe]     (default: every level, --safe)
# Builds the ROM from that stage (sims skipped: they
# probe the live stage) and flies it. "FORCED" lines = edges where NO waiting time or
# hover height got the bot through alive: the level takes the life, not the bot.
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-/home/iuri/python3/bin/python3}"
EDITOR="${EDITOR_BIN:-$SRC/tools/editor/cmake-build-debug/savior_editor}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/savior_check.XXXXXX")"
[ -n "$KEEP" ] || trap 'rm -rf "$WORK"' EXIT
rsync -a --exclude releases --exclude screenshots --exclude .git \
      --exclude 'tools/editor/cmake-build-debug' --exclude __pycache__ "$SRC/" "$WORK/"
if [ -n "$FRESH" ]; then
    rm -rf "$WORK/rooms"/level_* "$WORK/rooms/stage.json"
    "$EDITOR" --generate-stage "$WORK/rooms/stage.json" >/dev/null
fi
( cd "$WORK" && SIM_PY=/bin/false ./build.sh >/dev/null )
cd "$WORK"
if [ $# -eq 0 ]; then set -- --safe; fi
"$PY" -u tools/playbot.py "$@"
