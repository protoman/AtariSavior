#!/bin/sh
# Frame-budget sweep: run sim_frame_budget.py (fire held, thrust, bomb) in EVERY
# room of the live stage (rooms/stage.json), 14 at a time. SIM_LEVEL/SIM_ROOM are
# 0-based data indices. Results: $OUT/L<level>R<room>.out, summary on stdout.
#   sh tools/sweep_frame_budget.sh [outdir]
# Debug knobs of the sim: SIM_SPD (force EnemySpd), SIM_WSDBG (per-frame kernel
# WSYNC count + player/laser state), SIM_WSPC (+SIM_WSPC_FROM=frame): the WSYNC
# call sites that differ between the shortest and longest kernel frame.
cd "$(dirname "$0")/.." || exit 1
OUT=${1:-/tmp/frame_sweep}
PY=${PY:-/home/iuri/python3/bin/python3}
mkdir -p "$OUT" && rm -f "$OUT"/L*.out
$PY - > "$OUT/jobs.txt" <<'PYEOF'
import json
for lv, l in enumerate(json.load(open('rooms/stage.json'))['stage']['levels']):
    for r in range(len(l['rooms'])):
        print(lv, r)
PYEOF
export OUT PY
xargs -P 14 -L 1 sh -c 'SIM_LEVEL=$0 SIM_ROOM=$1 $PY sim_frame_budget.py > $OUT/L$0R$1.out 2>&1' < "$OUT/jobs.txt"
$PY - "$OUT" <<'PYEOF'
import glob, re, sys, collections
agg = collections.defaultdict(lambda: [0, 0])
for f in glob.glob(sys.argv[1] + '/L*.out'):
    lv = int(re.search(r'L(\d+)R', f)[1]) + 1
    agg[lv][0] += 1
    agg[lv][1] += 'SIM OK' in open(f).read()
for lv in sorted(agg):
    print(f'level {lv}: {agg[lv][1]}/{agg[lv][0]} rooms inside the frame budget')
PYEOF
