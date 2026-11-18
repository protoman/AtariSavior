#!/usr/bin/env python3
"""Survey (banks plan gate 2): how many ROM-data reads does each steady frame make from banks 2/3?
Counts per frame, in every room: `lda (FetchPtr),Y` / `lda (EnemyDataLo),Y` executed in bank2 or bank3 (the
reads that would become folds if that code moved away from the level data) and FoldIndirect calls from bank0.
Fire held and released. Prints the worst rooms. Run: python3 tools/measure_level_reads.py [--jobs N] [LEVEL ...]
"""
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import playbot as P  # noqa: E402
import test_frame_stability as F  # noqa: E402

FETCH = 0xE5
ENEMY = 0xB1          # EnemyDataLo
FOLD = 0xFEF6


def run_frame(con, fire):
    con.swcha = P.NONE
    con.inpt4 = 0x00 if fire else 0x80
    m = con.mpu
    c = {"b2": 0, "b3": 0, "fold": 0, "steps": 0}
    while True:
        pc = m.pc
        b = con.bank
        op = con[pc]
        if op == 0xB1:
            zp = con[pc + 1]
            if zp in (FETCH, ENEMY):
                if b == 2:
                    c["b2"] += 1
                elif b == 3:
                    c["b3"] += 1
        if b == 0 and pc == FOLD:
            c["fold"] += 1
        m.step()
        c["steps"] += 1
        if con.bank == 0 and m.pc == con.pc_frame:
            break
        if c["steps"] > 400000:
            break
    con.frames += 1
    return c


def one_level(level):
    con0 = P.Console()
    con0.boot(level)
    base = con0.save()
    rows = []
    for ri, room in enumerate(F.STAGE["levels"][level - 1]["rooms"]):
        for fire in (False, True):
            con = P.Console()
            con.restore(base)
            if ri:
                con.w("LevelConnSpare", ri | 0x80)
                for _ in range(4):
                    con.frame(P.NONE)
                if con.r("RoomNo") != ri:
                    continue
            con.w("PlayerLives", 8)
            if ri == F.STAGE["levels"][level - 1]["miner_room"]:
                con.w("RoomX", 140 if con.r("MinerX") < 80 else 10)
            for _ in range(6):
                con.frame(P.NONE)
            worst = {"b2": 0, "b3": 0, "fold": 0}
            for _ in range(60):
                c = run_frame(con, fire)
                for k in worst:
                    worst[k] = max(worst[k], c[k])
            rows.append((level, ri + 1, fire, worst))
    return rows


def main():
    jobs = 3
    a = sys.argv[1:]
    if "--jobs" in a:
        i = a.index("--jobs")
        jobs = int(a[i + 1])
        del a[i:i + 2]
    levels = [int(x) for x in a] or list(range(1, len(F.STAGE['levels']) + 1))
    allrows = []
    with Pool(jobs) as pool:
        for r in pool.imap_unordered(one_level, levels):
            allrows += r
    for key in ("b3", "b2", "fold"):
        allrows.sort(key=lambda r: -r[3][key])
        print(f"worst per-frame {key}:", [(r[0], r[1], r[2], r[3][key]) for r in allrows[:6]])
    tot = max((r[3]["b2"] + r[3]["b3"] + r[3]["fold"], r) for r in allrows)
    print("worst combined reads/frame:", tot[0], "in L%d room %d fire=%s" % (tot[1][0], tot[1][1], tot[1][2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
