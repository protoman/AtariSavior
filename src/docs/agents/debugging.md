# Debugging — Stella, screenshots, timing measurement

_Stella debugger, Wayland screenshots, scripted snapshots, timing, Scn Ln fields, pseudo-registers._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

## Debugging

### Stella Debugger

- `stella -debug savior.bin` — launch with debugger
- Backtick (`) — enter debugger from emulation
- `run` — resume execution
- `breakLabel <addr>` — set bankswitch-safe breakpoint
- `clearbreaks` — clear all breakpoints
- `scanline` — show current scanline

### Screenshots (Wayland) — agent captures Stella itself

System is **Wayland**; X11 grab tools (`xwd`, `import -window`) fail with
`BadWindow` on the XWayland window — do not use them. Working recipe
(verified 2026-10-06, first title-screen capture):

```bash
# 1. Launch (XWayland display + software video; detached so it survives)
cd src/ && setsid nohup env DISPLAY=:0 stella -video software savior.bin \
  >/dev/null 2>&1 < /dev/null &
sleep 5   # boot + title frames

# 2. Capture the ACTIVE window (Stella has focus after launch).
#    -b = background (required for -o/-d), -a = active window,
#    -e = no decoration, -n = no notify, -d = delay ms
spectacle -b -a -n -e -d 1200 -o /abs/path/src/screenshots/shot.png

# 3. Verify the file exists, Read it as image, then:
pkill -f "stella.*savior"
```

- Never launch bare `stella` or `stella -help` — no ROM arg opens the
  launcher/GUI (user saw a "loading file" window).
- `xwininfo -root -tree | grep '"Stella'` works for window inspection
  (geometry 640x456) but `xwd -id` still fails — spectacle only.
- Stella has NO CLI screenshot flag (checked `-help`).

### Scripted snapshots — deterministic frame captures (autoexec.script)

Source: `screenshots/debug/debug_in_stella.jpeg` (past-session method).
For exact-frame PNGs (better than spectacle for A/B timing checks —
fixed `frame N`, no focus/portal dependency):

```bash
mkdir -p /tmp/opencode/stella_base /tmp/opencode/stella_shots
cat > /tmp/opencode/stella_base/autoexec.script <<'EOF'
frame 5
saveSnap
EOF
cd src/ && setsid nohup env DISPLAY=:0 stella \
  -basedir /tmp/opencode/stella_base -debug \
  -snapsavedir /tmp/opencode/stella_shots savior.bin >/dev/null 2>&1 &
sleep 6            # Stella NEVER exits on its own — background + kill:
pkill -f "stella.*savior"
# PNGs land in /tmp/opencode/stella_shots
```

- `-basedir <tmp>` makes Stella run `autoexec.script` from that dir AND
  keeps the session away from the real Stella settings (sqlite db —
  no `logTrace` pollution from the trace-recipe rules below).
- Script commands that work: `frame #N` (advance N frames),
  `saveSnap` (PNG of current picture), `ram $addr $val` (poke RAM —
  e.g. `ram $81 $40` to set RoomY).
- Traps (measured by past session): `ram` bare hex `a` parses as the
  A register — ALWAYS `$`-prefix (`ram $0a $05`); joystick-style
  script commands (`joy0Right` etc.) do NOT affect the running game;
  no read-back (can't dump RAM/scanline counts out of a script).
- Because of those gaps, real debugging stays in the py65 sims
  (`sim_frame_budget` etc.) — Stella scripts = camera + pokes only.
  Live jitter/pacing still needs human eyes (simulator timing is only
  as good as its hardware model; Stella is the reference).

### Timing Measurement

Use `breakLabel` at two addresses, subtract Scn values:

1. `clearbreaks`
2. `breakLabel <start_addr>` → run → note Scn value
3. `clearbreaks`
4. `breakLabel <end_addr>` → run → note Scn value
5. Subtract to get duration in scanlines

**NEVER use `break`** — it fires at the physical ROM address in ALL banks
(causes cross-bank contamination with bankswitched ROMs).

**py65 PC traces MUST filter the execution bank (2026-09-29):** bank0/bank1
share the $F000-$FFFF address space — a raw PC counter sees bank1 HUD code at
the SAME address as a bank0 routine (tentacle's `beq .TentCommit` at $F5A5 =
bank1's `lda BarDelayTable,Y`), silently mixing them: counts came out ~5× too
high and the "probe path" PCs were bar-red delay instructions. Rule: pair
every `(pc, ...)` count with `mem.bank` (measure's `hpc[(pc,bank)]` does);
a lone hex PC is ambiguous.

**`print *$XX` DEREFERENCES — it is NOT a raw byte read (2026-09-28):**
`*` is Stella's pointer operator: `print *$B5` uses the byte AT `$B5` as an
address and shows THAT cell (observed: `print *$B5` → `ram_81` because
`[$B5]=$81`; `print *$F7` → `CXBLPF|$30(R)` because `[$F7]=$35` pointed at
the TIA collision register at `$35`). Reading a ZP variable raw (measured 2026-10-23, Stella 7.0):
- **`watch $XX` does NOT read memory - it evaluates the expression.** Watching
  `$80`, `$92`, `$99`, `$9A`, `$84`, `$C7` printed the constants `$80`, `$92`,
  `$99`, `$9A`, `$84`, `$C7` - every "value" equal to its own address. The
  earlier note that called it a raw byte read was WRONG; do not use it.
- **Use the hex grid** (the `00xx` table: rows = high nibble, cols = low
  nibble) or the `ram` command. That is the reliable read.
- `print *$XX` is the dereference form and is fine for a plain byte read:
  `print *$9A` shows the byte AT $9A.
Symptom of having used `*` by accident: output names a *different* address
(TIA register or `ram_XX`) than the one you typed.

### Scn Ln fields (TIA info panel) — source: Stella `TiaInfoWidget.cxx`

The row labeled `Scanline` (short form **`Scn Ln`**) holds TWO value boxes
(comment line 32: "current and the last-frame scanline counts, which share a
row"). Box order is fixed by reflow (line 199-200: `{myScanlineCount,
myScanlineCountLast}`) — **left box first, right box second:**

| Box | Widget | Source | Meaning (tooltip) |
|-----|--------|--------|-------------------|
| **LEFT** | `myScanlineCount` | `tia.scanlines()` = `myCurrentFrameTotalLines` | "Current scanline of this frame" — 0 at frame start, +1 per scanline |
| **RIGHT** | `myScanlineCountLast` | `tia.scanlinesLastFrame()` = `myCurrentFrameFinalLines` | "Number of scanlines of last frame" — frozen; updates ONLY at frame boundary |

- Frame boundary = `notifyFrameComplete()` (AbstractFrameManager.cxx:91) →
  RIGHT = totalLines at that instant, LEFT resets to 0. Fired by: VSYNC
  falling edge (≥2-line pulse), or timeout paths (`myVsyncLineCount > 50`).
- So `Scn 45|301` = line 45 of the CURRENT frame; last completed frame was
  301 lines long.
- Cross-checks: `Frame Cycles` ≈ LEFT×76 + Scn Cycle (tooltip: "CPU cycles
  executed this frame"); `Frame` = boundary counter.
- NEVER conclude "frame is N lines" from LEFT — LEFT is a position, not a
  total. Only RIGHT is a frame total, and only right after a boundary it
  actually belongs to.

### Pseudo-registers (Stella 7.0)

- `_scan` does NOT work — resolves to $00 (CXM0P)
- `breakif {_scan == N}` is UNRELIABLE
- Use `breakLabel` + Scn field instead
