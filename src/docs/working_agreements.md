# Working agreements (user rules that are not about the ROM)

Short, durable rules about HOW to work with the user. `AGENTS.md` links here;
the ROM/kernel invariants stay in `AGENTS.md`. Each rule says why it exists.

## 1. Count from 1 when talking to the user (user 2026-10-27)

Levels, rooms and models are counted from 1, exactly as the editor shows them.
The editor's model labels are 1-based too: "Model 32" on screen is data `id`
31. Bands may be counted from 0, but say which, and prefer 1-based ("band 2
(index 1)" if it could be ambiguous).

- **Why:** the user said "Model 32" and the agent looked up data `id` 32, a
  different shape. It cost several turns until a screenshot showed the editor
  label was `id` + 1.
- **How to apply:** subtract 1 at the boundary before looking anything up,
  add 1 when replying. With a screenshot, trust the editor label over the data
  index.

## 2. The saved stage is disposable; the generator is the product (user 2026-10-27)

"The current level data is irrelevant, that is why we are working on a
generator. We can erase all current levels at will and regen it."

- **Why:** once the generator is calibrated (several iterations), new games on
  the same engine come from regenerating the levels. So every design rule
  belongs in the generator (`Build20LevelStage`, `tools/editor/src/
  DataSerializer.cpp`) plus a test that pins it (`tools/test_generator.py`),
  never in hand-edited rooms.
- **How to apply:** when a rule changes, change the generator and its test.
  Do not worry about migrating existing rooms or shared shapes; report
  violations in the saved stage only as evidence the rule was missing. Still
  never hand-edit `rooms/` or `generated/` (the user regenerates), and keep the
  frozen test copies under `tests/` as they are.
- **Gotcha:** `test_generator.py` does not rebuild the editor. Run
  `cmake --build tools/editor/cmake-build-debug` after a generator change.
- **Rules already pinned this way:** phase walls are horizontal obstacles only;
  the hcrunch gap is checked on band 3 (see `AGENTS.md`, "Generator Hazard
  Placement").

## 3. Reproduce with real data, through the real entry path (user 2026-10-25)

"Try to use real data in the simulator when possible."

- **Why:** two "not reproduced" reports (level 8 room 3) rested on synthetic or
  poked setups, and the user had a screenshot proving otherwise.
- **How to apply:** for a repro probe, read the live stage (read-only) and enter
  rooms through the real exits or start, not by poking RoomX/RoomY. Tests in the
  repo still use frozen copies under `tests/`.
- Related: `AGENTS.md`, "Reproduce the User's Report Through THEIR Entry Point".

## 4. TODO.txt and credits.txt may be committed (user 2026-10-27)

"You can commit those files. Just do not edit or read TODO as if it was a
guide."

- **How to apply:** include them in a commit when asked to commit; stage blindly
  with `git add TODO.txt credits.txt`. Never open, grep, edit or quote
  `TODO.txt`, and never take values or plans from it (see the `AGENTS.md` rule
  "NEVER Read or Write TODO.txt", which still holds).
