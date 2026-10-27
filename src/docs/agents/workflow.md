# Workflow rules — reproduce, red test, estimate, session budget

_How to work on a bug or a task: reproduce first, red test first, timebox, budget the session._  
_Split out of `AGENTS.md` (2026-10-27); text unchanged. Index: `AGENTS.md`._

### Critical Rule: Reproduce the User's Report Through THEIR Entry Point

**When the user says a tool/feature "does not work", reproduce it with the exact
tool, tab and entry point they use — never a nearby internal function.** On
2026-10-18 the user reported that Delete did nothing on a hcrunch row (they said
it three times, and even warned "assume your tests might fail"). The agent's
regression case called `MapCanvas::ApplyBrushAt` directly with `BrushTool::
ERASE_AIR` (the empty brush) and passed — while the user was clicking
`BrushTool::DELETE_ENTITY`, a different tool handled by a different branch that
only erased entities. The test was green, the user's click was a literal no-op,
and the agent spent a session doubting a correct report.

Rules:
- **A green test that does not use the user's path proves nothing about their
  path.** Name the tool/tab/entry point in the test (here: `DELETE_ENTITY`, the
  Level tab) and drive it the way the UI does.
- **The user's observation outranks your model of the code.** If they say it
  fails and your reading says it cannot, your reading is incomplete — find the
  other branch. "I checked and it should work" is not an answer.
- Do not ask them to re-verify something they already verified; reproduce it.

### Critical Rule: Red Test First — Reproduce, Then Fix

**Before fixing a bug, write a test that FAILS because of that bug, run it and
see it red, and only then touch the code. The fixed code must turn that same
test green.** (User rule 2026-10-23.) A fix without a red test is a guess: it
cannot show the bug was real, and nothing stops it from silently regressing.

- **Prove the test is red on the unmodified build** — run it, read the failing
  assertion, and keep that message naming the actual symptom (e.g. "right-side
  locked door did NOT block"). A test that passes before the fix is testing
  something else.
- **Drive the real routine** (`tools/test_m1_door.py` calls the frozen
  `OvM1Block` with a staged room; `test_jet_clamp.py` calls the real
  `UpdateP0Vertical`) — not a re-implementation of the algorithm, or the test
  can only ever agree with itself.
- **Order that works with the frozen banks:** re-freeze FIRST
  (`tools/freeze_test_banks.sh`) so the frozen image carries the buggy code,
  watch the test go red, then fix, rebuild, re-freeze, watch it go green. A
  stale frozen image makes the red step meaningless.
- Keep the test afterwards as the regression guard, and keep the bug's date,
  symptom and root cause in its docstring (see `test_m1_door.py`,
  `test_jet_clamp.py`, `test_laser_clamp.py`).


## Rule: Estimate First — 20% Timebox on "Can You Do X?" Questions

When the user asks "can you do X in T minutes?", the answer must come from
a **fast mental estimate**, not from investigation. If deciding takes more
than ~20% of T (e.g. >2 min for a 10-min task), the answer is already **NO**
— say NO immediately. Spending the budget on wondering whether you can is
itself the failure.

**Why this rule exists:** 2026-10-06 — user asked "fix frame regression in
10 minutes max?"; the agent started investigating instead of answering, and
had to be told three times to stop.

## Rule: Session Budget Discipline

The model context window is fixed and the ENTIRE conversation (system prompt +
`AGENTS.md` + every tool output) is re-sent each turn. Long sessions do not
"get shorter" — the remaining working budget shrinks with every full-file read,
listing dump and rebuild log. Treat context like the ROM budget: spend it
deliberately.

- **One chunk per session.** Start by reading the current plan/handoff
  (`docs/*_plan.md`, `docs/handoff_*.md`) and a 5-line state note — never
  re-derive what is written down.
- **Read by index, not by file.** `codegraph_explore` first; `grep` with tight
  patterns for a specific symbol; `sed -n 'a,bp'` for a slice. Full-file reads
  of `kernel.asm`/`bank2.asm` (1000+ lines) are a last resort.
- **Filter every command's output**: `./build.sh 2>&1 | grep -E
  "error|Done|sim_|verify_build"`, `tail -5` on sims, `grep -c` for counts.
  Never paste a full `.lst` or a full battery log.
- **Commit after each chunk** (build + both sims + battery green), with the
  chunk name in the message, so a cut-off session always leaves a green tree.
- **Update the size ledger in the same commit**: run
  `tools/rom_size_report.py --md` and paste the table into the active plan
  (per-bank code/data/used/free + level-data total). The ledger is the tripwire
  if a later chunk misbehaves.
- **Re-freeze the test banks** (`tools/freeze_test_banks.sh`) before trusting a
  battery run after ANY bank code change — the frozen images otherwise keep
  executing the previous build and a green battery proves nothing.
- **Budget floor:** when roughly a fifth of the session is left, stop starting
  new edits. Finish/verify the current one, commit, and write the exact next
  step (design, addresses, blocker, files) into the plan/handoff.
- **Never leave the tree broken**: a reverted attempt + a documented design is
  worth more than a half-applied refactor. Record what was learned (the failing
  sim output, the exact stack/address symptom) in the plan.

**Why this rule exists:** 2026-10-19 — a long session (crunch unification +
bank3 level-data move) repeatedly ran out of budget mid-refactor; the bank3
move had to be attempted twice and reverted twice, and the handoff had to carry
the design that the session could no longer execute.
