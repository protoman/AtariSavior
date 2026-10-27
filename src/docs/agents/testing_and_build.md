# Build and testing

_build.sh, DASM gotchas, frozen test data rules, re-freeze procedure._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

## Build

```bash
./build.sh          # builds savior.bin (32K, F4)
```

Requires: `dasm` (6502 cross-assembler)

### DASM Assembly Gotchas

- **`=` definitions MUST start at column 1** — DASM treats indented `=` as
  unknown mnemonics and silently fails. Example: `    Temp = $AD` fails but
  `Temp = $AD` works. This caused bank1 to silently use stale .bin files.
- **ALWAYS verify bank1.bin is actually rebuilt** — if DASM fails but the
  build script catches the error (via `|| echo`), the old .bin is reused.
  Check file timestamps after building.

## Testing

### Test stage data — frozen test-owned copies only (user rule 2026-10-14)

**Tests must never read live `src/rooms/`, `models.json`, or `generated/`**
(models, level jsons, generated slices) and must NOT gate on
ROM↔fixture equality — the user keeps editing stages, so live-coupled
tests break on every edit. **Frozen test copies live in `src/tests/`.**
Test scripts stay where they are (`tools/test_*.py`,
`src/tools/test_title_demo.py`) and read only from `src/tests/`.
**No editor change to rooms/models may break any test or build.**

**RE-ASSERTED 2026-10-17 (user, emphatic): "When creating tests, create the
rooms, and put them in tests folder. Do not use live-data for tests."**
This means, concretely, that a test **authors its own rooms/models** and
keeps them under `src/tests/` — it does **not** read `src/*.bin`,
`src/*.lst`, or `src/generated/**` (the live build). The earlier
"ROM byte staging" (`test_fixtures.py` injecting into the live
`src/bank2.bin` at live `bank2.lst` label addresses) **VIOLATED this rule**:
because the label addresses come from `bank2.lst`, those tests were coupled
to whatever the editor last wrote into `models_data.asm`, so a model edit
(e.g. model 4 losing its hot rect → a 13B→10B rect slot) broke
`test_fixtures` + `test_hcrunch` + `test_laser_wall`. That mechanism is
**NOT** sanctioned any more — it must be replaced by frozen copies.
**Whenever a ROM-byte fixture is needed: copy the bank image AND the label
set into `src/tests/` and read those, never the live build.**

Two staging mechanisms (both fully test-owned):
- **File copies** (models.json, level jsons, generated slices):
  frozen files under `src/tests/`.
- **Frozen ROM image + labels**: a test-owned `src/tests/bank*.bin` (and a
  frozen label set) — never `src/bank*.bin` / `src/*.lst`. Fixture bytes change only by deliberately
  re-freezing in that module.

Sanctioned exceptions — their job IS to track live data (run them after
`./build.sh`, since they compare live sources against the built ROM):
- converter-validation tests (`test_features_data`, `test_asym_data`)
- `test_band_restage` (live level jsons ↔ built ROM EnterRoom behavior)
- `test_level_bank` (kernel `LEVEL_COUNT` hand-copy ↔ live
  `generated/levels.asm` count — freezing it would break on level add)

**Re-freeze procedure** (only when stage content deliberately changes):
run `./build.sh` first (so `generated/` matches the edited data), then
copy the edited `rooms/level_*.json`, `rooms/models/models.json`, and the
convert outputs under `src/tests/generated/` into `src/tests/` keeping
the same relative tree. `test_editor_roundtrip` regenerates from the
frozen copies into a TEMP dir — it must never write the repo.

Run in Stella:
```bash
stella savior.bin        # normal emulation
stella -debug savior.bin # debugger
```
