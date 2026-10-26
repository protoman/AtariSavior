"""ZP lifetime audit: map every `sta <NAME>` to its enclosing global label."""
import re
from pathlib import Path

SRC = Path("/home/iuri/Desenvolvimento/atari_2600/ai_savior/src")

# names the ZP doc marks as room-scoped / level-scoped / phase-scoped
ROOM = ["EnemyDataLo", "EnemyDataHi", "EnemyCount", "EnemyRamX", "EnemyRamY",
        "EnemyRamD", "EnemyRamP", "RoomRectsLo", "RoomRectsHi", "RoomMetaA",
        "RoomMetaB", "RoomNo", "LevelConnSpare", "MinerX", "MinerY",
        "LevelMinerRoom", "RoomBandColor", "EnemyDeadMask", "EnemyIndex"]
LEVEL = ["Level", "LevelRoomN", "LevelPFDataLo", "LevelPFDataHi",
         "LevelStartRoom", "LevelStartX", "LevelStartY", "LevelWallColor",
         "LevelWallColor2", "PlayerLives", "PlayerBombs", "BarLevel",
         "LaserState", "Hover", "DropTarget"]


def writers(name):
    out = []
    for f in ("kernel.asm", "bank1.asm", "bank2.asm", "bank3.asm"):
        label = "?"
        for i, ln in enumerate((SRC / f).read_text(errors="replace").splitlines(), 1):
            code = ln.split(";")[0]
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", code)
            if m:
                label = m.group(1)
            if re.search(rf"\b(sta|stx|sty)\s+{name}\b", code):
                out.append(f"{f}:{label}")
    return sorted(set(out))


print("=== ROOM-scoped (must be staged by EnterRoomB2 / LoadEnemyRam / ExtrasLoad)")
for n in ROOM:
    w = writers(n)
    print(f"{n:14s} {', '.join(w) if w else '(no store!)'}")

print("\n=== LEVEL-scoped (LoadLevel / LoadLevelB2)")
for n in LEVEL:
    w = writers(n)
    print(f"{n:14s} {', '.join(w) if w else '(no store!)'}")
