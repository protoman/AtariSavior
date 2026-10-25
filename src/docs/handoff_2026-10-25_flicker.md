# Handoff — 2026-10-25 — cave flicker in two-object rooms

**Read this first, then `bugs.md` #16** (it carries the full measurement log).
Everything below was measured, not inferred; the dead ends are listed so the
next session does not re-walk them.

## Objective

Kill the visible flicker the user reports in level 5 rooms **2, 3 and 4**
(1-based). Room 1 of that level has no objects and is rock-stable, which is the
clue that the flicker belongs to rooms that stage a **second cave object**.

## State: green, nothing half-applied

* `./build.sh` → `verify_build: OK`, all 8 banks exact, both sims pass.
* Battery: **62 passed / 2 failed**; the 2 reds are pre-existing
  (`tools/test_slot1_midband.py`, `src/tools/test_title_demo.py`).
* Runner: `bash /tmp/opencode/run_battery.sh > /tmp/opencode/batteryN.log 2>&1`
  (background; read the tail).
* Live stage (`src/rooms/`, `models.json`, `src/generated/`) is the user's —
  regenerate only through the editor's `--generate-stage`.

## Delivered this session (all committed)

| commit | what |
|---|---|
| `7b8f0f2` | kernel: `Slot1Hook` bottom-band scanline count — killed a real **+10-line** band stretch (the 283-line frames) |
| `c05ced6`, `9acf9e3`, `31af4e1`, `87ad423`, `bb7f3ae` | generator: two objects may never share a band or a display column; build gates; `tools/test_object_bands.py` |
| `db9871a` | hot-band pulse: dim amber `$28` partner + one step per second (`TickCounter` bit 5) |
| `b12049b`, `0e2c9c3` | `bugs.md` #16: measurements, dead ends |
| — | **new tool `tools/probe_kernel.py`** (see below) |

## The remaining defect, measured

`tools/probe_kernel.py 4 1 20 21` (level 5, room 2):

```
f21 lines 271.00 bodies {0:36, 1:36, 2:36, 3:22, 4:13}
    hook [('0xf7a8', 197), ('0xf7b7', 103)]
```

* hook segment (previous WSYNC → positioning WSYNC): **197c**
* positioning/div15 line: **103c**
* the plain band setup in the same slot: **117c**
* hook WSYNC count is **identical (4661) in rooms that measure 270 and 271**,
  and the per-pc gap sums over 25 frames differ only by scattered ±20-600c
  (`$F0A9`, `$F0CE`, `$F104`, `$FF0F`) — **no 76c site**.

So: the hook deterministically costs one line more than the 2 the code
subtracts (`LINES_PER_TILE - 2`, `CollisionX - 2`) → +1 line per hook frame.
A room measures 270 or 271 depending on where the *rest* of the frame's phase
lands, which is why `-3` fixes room 2 and breaks room 3 (269).

## Dead ends (do not repeat)

1. **`-3` count constant** — fixes hot rooms (270), breaks plain rooms (269).
   `-2` is the opposite. Reverted.
2. **`sta WSYNC` anchor at hook entry** — 273/274, worse. Reverted.
3. **ZP-staged `Slot1Band`** — the arithmetic does not close: even with the
   band test reduced to 9c and the Y save removed (absolute `HMP1`/`RESP1`),
   the hook's own work is ≈47c → segment ≈164c, still over the **152c**
   two-line slot. A zero-page byte buys determinism, not a fit. Not started.
4. **Generator band gap ≥ 2** (to stop the pair's bands from merging under
   vertical drift) — hot rooms then have no legal pair (band 0 = arrival band,
   band 1 = hot hazard wall) and the second enemy is **dropped**; the user
   already noticed a missing NPC once. Allowing band 0 off-aperture does not
   help (in the usual `########..` row 0 the air cells *are* the aperture).
   Reverted.

## Next step (the actual task)

Find the missing line in a room that measures **270** while staging a hook
(level 5 room 3, `probe_kernel.py 4 2 ...`), then choose between:

**(A) make the frame constant at the hook's real cost** — subtract 3 only on
the path that truly costs 3, after the r3 deficit is understood. Needs a
line-granular ledger, not per-pc sums:

```bash
/home/iuri/python3/bin/python3 -u tools/probe_kernel.py 4 1 24 24   # 271
/home/iuri/python3/bin/python3 -u tools/probe_kernel.py 4 2 24 24   # 270
```
then diff the per-pc gap lists for **one** frame (the tool logs every WSYNC;
extend it to dump `pc gap` for a single frame and diff the two rooms:
`sum(gaps)` must differ by exactly 76 for the frame that flips).

**(B) cut the hook to fit 2 lines** — needs ~45c out of: staging 24c +
clears/blank 14c + (`Slot1Band` test 9c after the VBL staging) + the band
transition overhead. Removing the Y save (write `HMP1`/`RESP1` absolutely,
index the fine table with `tax`) frees 11c; the rest has to come from the
staging itself. If (B) lands, `-2` becomes correct everywhere and no ZP byte
is needed.

**(C) fallback with a design cost** — keep the pair only in rooms where the two
bands are ≥2 apart *and* a legal cell exists; otherwise leave the room with a
single object **and say so in the generator log**, so it is a decision, not a
silent drop. Only if (A)/(B) both fail.

## Tooling

`tools/probe_kernel.py LEVEL ROOM [FROM] [TO]` — 0-based level/room, prints
per frame: frame length, body lines per band, every WSYNC inside `Slot1Hook`
with its cycle gap. Traps it already handles (learned the hard way):

* the ROM boots to the **title**; pulse console RESET (SWCHB b0) on frames
  1 and 8 — holding it restarts the game every frame and gameplay is never
  reached (DropTarget stays `$FF`);
* clear the `wsync_seen` flag after each stall or the wall clock inflates;
* print **once per frame boundary** (the guard must compare against the last
  printed frame) or the log is cleared per instruction and every report is
  empty;
* identify WSYNC sites by **label-derived ranges** (`CaveLine`, `Slot1Hook`),
  never hardcoded addresses — bank0 moves with every edit and a stale `$F138`
  silently reports "no bodies".

Reference commands:

```bash
cd src && ./build.sh                                   # gates + both sims
SIM_LEVEL=4 SIM_ROOM=1 python3 sim_frame_budget.py     # the room gate (271 today)
/home/iuri/python3/bin/python3 tools/test_object_bands.py
bash /tmp/opencode/run_battery.sh                      # expect 62 / 2
```

Level numbers in user speech are **1-based**; `SIM_LEVEL`/probe LEVEL are
0-based (level 5 = 4, room 2 = 1).

## Known-good behaviour to preserve

* hot pulse: amber `$28` ↔ red `$44`, one step per 60-frame second (user rule
  2026-10-25: keep the pulse, no strobing);
* two objects are always ≥ 2 bands? **No** — that rule was rejected; the
  shipped gate is *different band* + *≥3 display columns*, enforced as a build
  error on the shipped stage (`SAVIOR_OBJECT_BANDS=warn` for frozen fixtures);
* `Slot1Hook` count block must stay **before** the inlined positioning
  (`ldx #1` clobbers X) — `verify_build` fails the build otherwise.
