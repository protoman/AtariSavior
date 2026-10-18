# Stella debugging + screenshot recipe (what works, what does not)

Written 2026-10-18 after fumbling this twice in one night. Read this BEFORE
touching Stella; do not rely on memory. Legend: **[V]** = verified/used
successfully in this project, **[D]** = documented from a past session (not
re-verified recently), **[F]** = FAILED when tried on 2026-10-18 (see §5).

---

## 0. What Stella is FOR here (and what to use instead)

| need | tool |
|---|---|
| semantics: collision, state machines, carry physics, frame budgets | **py65 harness** — `./build.sh` sims, `tools/qa_sweep.py`, `tools/test_*.py`. These are deterministic and I can run them any time **[V]** |
| TIA-level visuals: sprite/ball/missile stripes, exact scanline positions, flicker, the real COLUPF/COLUP1 mix | **Stella only** **[D]** |
| an in-game room picture without gameplay input | Stella + RAM pokes (§4) **[F this time]**, or the py65 renderer (`tools/qa_shots.py`, `tools/render_shutter_frames.py`) **[V]** |

Rule of thumb: never burn Stella effort on something the py65 harness can
answer. Reach for Stella when the question is "what does the TIA actually
draw".

## 1. Launch (do not launch bare)

```bash
cd src/ && setsid nohup env DISPLAY=:0 stella -video software savior.bin \
  >/dev/null 2>&1 < /dev/null &
sleep 5
```
- System is **Wayland**; Stella runs under XWayland. `-video software` avoids
  GL trouble. Use an ABSOLUTE ROM path if you are not in `src/`.
- **Never run bare `stella`** (no ROM) — it opens the launcher/GUI window
  (the user saw a stray "loading file" window once) **[V]**.
- Cleanup: `pkill -f "stella.*savior"` — Stella never exits by itself **[V]**.

## 2. Screenshot the live window (spectacle — the reliable path) **[D]**

X11 grab tools (`xwd`, `import -window`) FAIL with `BadWindow` on the XWayland
window **[D]**. Use spectacle against the ACTIVE window:

```bash
spectacle -b -a -n -e -d 1200 -o /abs/path/src/screenshots/shot.png
```
- `-b` background (required with `-o`), `-a` active window, `-e` no decoration,
  `-n` no notify, `-d <ms>` delay so the frame is stable.
- **The active window must be the Stella window** (it has focus right after
  launch). If focus was stolen, the capture is of something else.
- Verify the file exists and Read it as an image.
- `xwininfo -root -tree | grep '"Stella'` works for inspection
  (geometry 640x456) but `xwd -id` still fails **[D]**.
- Limit: this photographs whatever is on screen — the **intro/title** unless a
  human pressed RESET (see §3/§4). Stella has **no CLI screenshot flag** **[D]**.

## 3. Scripted, deterministic frames (`autoexec.script`) **[D], failed [F]**

The intent: fixed `frame N`, no focus/portal dependency, plus RAM pokes so you
can reach a room without input.

```bash
mkdir -p /tmp/opencode/stella_base /tmp/opencode/stella_shots
cat > /tmp/opencode/stella_base/autoexec.script <<'EOF'
frame 5
ram $98 $01
frame 40
saveSnap
EOF
cd src/ && setsid nohup env DISPLAY=:0 stella \
  -basedir /tmp/opencode/stella_base -debug \
  -snapsavedir /tmp/opencode/stella_shots savior.bin >/dev/null 2>&1 &
sleep 20
pkill -f "stella.*savior"
ls -la /tmp/opencode/stella_shots/*.png      # expect the snapshot here
```

Script commands that work **[D]**: `frame #N` (advance N frames), `saveSnap`
(PNG of the current picture), `ram $addr $val` (poke console RAM 0x80-0xFF).

Traps, all of them learned the hard way:
- `ram` needs the **`$` prefix**; bare hex `a` parses as the A register **[D]**.
- `-debug` is required: the script is run **when the debugger prompt first
  shows**, not at power-on **[D]**.
- **The boot code CLEARS all RAM** (`LDX #0 / STA VSYNC,X`). Poke only AFTER
  the boot: `frame 5` first, then `ram`, never the other way round **[V, my bug]**.
- No read-back: you cannot dump RAM/scanlines from a script; real debugging is
  the py65 harness **[D]**.
- Joystick-style script commands (`joy0Right` …) do **not** drive the game, and
  console switches (RESET/SELECT) cannot be toggled from a script — the intro
  waits for a REAL RESET edge, so scripted **input** cannot reach gameplay
  **[D]**. (RAM pokes are the workaround; see §4.)
- `-basedir <tmp>` also keeps the session away from the real settings DB
  (`~/.config/stella/stella.sqlite3`) **[D]**.

## 4. Teleport into a room without input (RAM pokes)

Since you cannot press buttons from a script, poke the render/state bytes
instead. Addresses are **ZP ($80-$FF)**, i.e. the `ram` command's domain.
Generate the poke list from the built labels rather than by hand:

```python
# tools/… (session one-liner): ZP addresses from bank0.lst, PF bytes from bank2.bin
pf  = L2["L1R2TilePF0"]        # the room's PF block (any room: use its label)
ram $c3..$cb  <- the 9 PF bytes at pf   (PF0Buf/PF1Buf/PF2Buf rows 0-2)
ram $99/$9a   <- RoomPF0Lo/Hi = pf      (so StageBandTab reads the room meta)
ram $90/$91   <- RoomRectsLo/Hi = the room's rects label
ram $92       <- RectCount (0 = no rect walk)
ram $98       <- RoomNo
ram $80/$81   <- RoomX / RoomY (a standing position)
ram $13/$14   <- vyLo/vyHi = 0
ram $8a       <- DropTarget = 0  (leaves the intro/title path -> live play)
ram $35       <- BombPacked = $80 (OnGround)
ram $9c       <- Hover = 0
```
Status: **worked in py65 (identical pokes) [V]; the Stella path never produced
a file tonight [F]**, so treat the Stella half as unconfirmed until §5 is
resolved. The py65 equivalent is `tools/qa_sweep.py`'s `load_room`-style
harness and always works.

## 4b. 2026-10-18 measurements (verified in this environment)

**[V] The scripted snapshot WORKS in this exact form:**

```bash
rm -rf /tmp/opencode/sb /tmp/opencode/ss && mkdir -p /tmp/opencode/sb /tmp/opencode/ss
printf 'frame 60\nsaveSnap\n' > /tmp/opencode/sb/autoexec.script
cd src/ && timeout 20 stella -video software -basedir /tmp/opencode/sb -debug \
  -snapsavedir /tmp/opencode/ss savior.bin >/dev/null 2>&1
pkill -f "stella.*savior"
# -> /tmp/opencode/ss/savior_dbg_<hash>.png   (320x228 RGB, the real frame)
```
Points that mattered: a **fresh** basedir (`rm -rf` first — Stella creates
`state/ nvram/ stella.sqlite3` inside it), `-debug` present, `saveSnap` (not
`snap`), `frame N` before it.

**[F] ANY memory-write line kills the script in this build (Stella 7.0 build
8005):** with one poke added (`ram $80 $28` / `ram $0080 $28` /
`write $80 $28`) the run produced **no PNG at all** — the script stops at the
first unknown/unsupported command, so everything after it (including
`saveSnap`) never runs. `ram` is an **interactive** debugger command: the only
standalone command literals in `/usr/bin/stella` are `print saveSnap snap
write`, and `ram` is absent, while `write` exists but did not take my argument
forms. **Conclusion: poke RAM INTERACTIVELY at the debugger prompt** (a human),
or use the py65 renderer — do not put memory writes in `autoexec.script` until
a working scripted form is found.

**A comment line is fine** (`; ...` did not break the working script) — the
earlier suspicion that comments broke it was wrong; the pokes did.

## 5. Debugging the scripted path when no PNG appears (2026-10-18 failure)

Symptom: launch + `-debug` + basedir script → **no PNG anywhere, empty log**,
window presumably running (a plain `timeout 5 stella … savior.bin` blocks =
it is emulating) **[F]**. Do these in order:

1. Search for the snapshot OUTSIDE `-snapsavedir` — Stella also writes to the
   CWD and/or the basedir's own snapshot folder:
   `find ~ /tmp /home/iuri/Desenvolvimento/atari_2600/ai_savior -name '*.png' -newermt '-20 minutes'`
   (2026-10-18 this found only unrelated files under `/tmp/opencode/md-emu/`.)
2. Run with logging and grep for the script:
   `timeout 12 stella -loglevel 2 -logtoconsole 1 -video software -basedir <tmp> -debug -snapsavedir <tmp> savior.bin 2>&1 | grep -iE "script|snap|error"`
   (2026-10-18: no matching lines at all.)
3. Try BOTH script locations — Stella looks for the ROM-dir script
   (`savior.script`, next to the ROM / CWD) and the basedir `autoexec.script`:
   `cp /tmp/opencode/stella_shots/autoexec.script src/savior.script`
   **and remove it afterwards** (a stray `savior.script` runs on every launch;
   `src/savior.script.tracebak` exists for the tracing recipe and must stay a
   `.tracebak`).
4. Confirm the debugger actually entered (the prompt/log shows it) — if the
   window never reaches the prompt, neither script runs.
5. Check the settings DB is not polluted by an old trace session:
   `python3 -c "import sqlite3;c=sqlite3.connect('/home/iuri/.config/stella/stella.sqlite3');c.execute('update settings set value=0 where key in (\"dbg.logtrace\",\"logtoconsole\")');c.commit()"`
   (a dirty DB prints a `trace` line per instruction and the game crawls) **[D]**.
6. Fall back: §2 (spectacle) for a picture of whatever is on screen, or the
   py65 renderer for a specific room.

## 6. Interactive debugger (when a human is driving)

- `stella -debug savior.bin`; backtick toggles the debugger.
- `breakLabel <addr>` sets a bankswitch-safe breakpoint (uses the list file).
  **NEVER `break <addr>`** — it fires at the physical address in ALL F6 banks
  **[V]**.
- `Scn Ln` field = two boxes: LEFT = current scanline, RIGHT = LAST completed
  frame's total lines (only the RIGHT one is a frame total) **[V]**.
- `_scan` does not work; `breakif {_scan == N}` is unreliable **[V]**.
- `print *$XX` **dereferences** (`*` is the pointer operator) — it shows the
  cell AT `[$XX]`. To read a ZP variable raw use `watch $XX`, or `ram` (full ZP
  dump), or click the `00xx` RIOT grid **[V]**.
- Tracing: the two trace scripts live renamed as `*.tracebak`
  (`src/savior.script.tracebak`, `~/.config/stella/autoexec.script.tracebak`).
  Rename both back to run a trace with
  `timeout --signal=KILL 10 stella -debug -loglevel 2 -logtoconsole 1 savior.bin`,
  then rename them to `.tracebak` again and reset the DB (§5.5) **[D]**.

## 7. Rule for next time

If a Stella attempt fails twice, STOP and write the failure mode into this file
(§5) instead of retrying variants — that is exactly how this file came to
exist, and the py65 harness can answer most questions in the meantime.
