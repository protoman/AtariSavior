# Savior Kernel — Architecture

## Key Principle: Always Follow HERO First

**The Activision developers who created HERO are smarter than both of us combined. When in doubt, do NOT come up with "better" ideas. Just follow their path.** Look at what they did, understand why, and replicate it. Every time we tried to invent our own approach (inline bank-switching, NUSIZ copies for HUD elements, custom positioning), it failed or produced poor results. Every time we followed HERO's patterns (fold-pad bank switching, PF-based HUD rendering, SetObjectXPos), it worked.

**When implementing any feature, ALWAYS look at how HERO does it first and follow that approach.** HERO is the reference architecture. If there are multiple ways to implement something, HERO's way is the default choice. Only deviate from HERO's approach if there is a clear technical reason documented in this file. This applies to: rendering, HUD elements, sprite techniques, positioning, collision, sound, and every other aspect of the game.

**When something works in HERO, do NOT tell the user that following that idea will not work.** If HERO uses a technique for a specific feature (e.g., 3 lives, 5 bombs), and it works, then implement it the same way. Do not suggest alternatives or claim the approach has limitations. The fact that HERO does it proves it works.

**Before claiming how HERO implements something, ALWAYS look at the actual code first.** Do not suppose or assume based on partial understanding. Check hero_bank1.asm, the comparison code, and data tables (especially lookup tables like LFF3E for NUSIZ values, LFF6D for positioning, LFF96 for sprite data). If the code contradicts your assumption, the code wins — update your understanding and tell the user what you found, not what you thought.

**Why this rule exists:** In this session, the agent was told HERO uses NUSIZ copies for lives/bombs but kept insisting it was wrong and suggested 13+2 instead. Later found LFF3E=$30,$30,$20,$20 proving HERO uses NUSIZ. The agent was also told HERO uses PF for score but kept suggesting sprites. The pattern: the agent reads a PART of the code, forms an assumption, then defends it instead of reading more. The fix: read the FULL relevant section, trace the data flow, and verify against the actual disassembly before responding.

**What we already use from HERO (keep these, do NOT replace):**
- Reflected playfield (CTRLPF D0=1) — symmetric cave design
- PF registers written ONCE per tile row (TIA persists across scanlines)
- Fixed-time kernel with unconditional inner loop (no per-scanline branches)
- Andrew Davie's session-24 horizontal positioning (SetObjectXPos with div15 loop + page-aligned fineAdjustTable)
- HMOVE applied during HBLANK after RESP0/HMP0 are set
- Joystick read from SWCHA with 4× LSR to shift bits to D0-D3
- Frame timing: 3 VSYNC + 37 VBLANK + 192 kernel + 30 overscan = 262 scanlines
- F4 bankswitching (32K, 8 banks × 4K)


## Where things live (read the file for the task at hand)

| Topic | File |
|---|---|
| Non-ROM user rules (count from 1, generator is the product, real-data repro, TODO/credits) | `docs/working_agreements.md` |
| Reproduce first, red test first, timebox, session budget | `docs/agents/workflow.md` |
| Level data format, async walls, bank2/bank3 split, generator rules (phase, hcrunch) | `docs/agents/level_data_and_generator.md` |
| ROM layout, F4 banks, frame timing, zero-page, cave kernel, cycle budget | `docs/agents/kernel_and_rom.md` |
| Raft entity, laser missile invariants | `docs/agents/game_features.md` |
| Build, DASM gotchas, frozen test data, re-freeze | `docs/agents/testing_and_build.md` |
| Stella, screenshots, timing measurement | `docs/agents/debugging.md` |
| Bug post-mortems (stack/ZP, hotspot zone, positioning, WSYNC) | `docs/agents/lessons_learned.md` |
| Flicker budget, title kernel, VDEL stripe | `docs/agents/kernel_timing_rules.md` |
| php/pla, Origin Reverse-indexed, score rewards, open items | `docs/agents/coding_gotchas.md` |
| HERO patterns, differences, power bar | `docs/agents/hero_reference.md` |
| Phases 1-10 checklist | `docs/agents/development_plan.md` |

Section names inside the moved text that say "above", "below" or "Lessons
Learned" refer to the old single file: search `docs/agents/` for the title.


### Critical Rule: the LIVE Stage Is the User's — Never Edit It

`src/rooms/`, `src/rooms/models/models.json` and `src/generated/` are the user's
stage. **Do not edit them** (user rule 2026-10-18: "when needed I'll edit the
rooms myself, you should not worry or depend on it"). They change under the
agent's feet, and several gates deliberately pin live content:

- `sim_bomb_fuse` FORCES Level 2 and fabricates that room's enemies (it needs
  room 1's wall rects for the bomb-hole check) — any edit to that room breaks it.
- `sim_frame_budget` / `qa_*` probe live rooms for their scenarios.
- The frozen test banks are built from `src/tests/rooms`, not from the live stage.

So when a feature needs stage data (a room, a spawn, a demo):
1. **frozen/test-owned copies** in `src/tests/` for tests (`tools/freeze_test_banks.sh`
   rebuilds the frozen banks from `src/tests/rooms`), and
2. **a staged demo build** for anything playable — copy the stage, edit the COPY,
   build, restore (`tools/raft_build.sh` is the model: `SIM_PY=/bin/false ./build.sh`
   + a `trap restore EXIT` that rebuilds the live ROM).
If a feature truly needs live stage content, ask the user — do not add it
unasked (the raft's demo ROM exists for exactly this reason).

**Never `git add -A src`.** On 2026-10-18 a blind `git add -A src tools` committed
a REVERTED `src/rooms/level_002.json` — the user had replaced that room's tentacle
with the raft, and the staging scripts (`freeze_test_banks.sh`, `raft_build.sh`
both copy rooms/ to a temp dir, replace it, then restore) left the tree at an
older state that got swept in. The user's edit had to be rebuilt by hand.
Rules: stage `src/rooms` and `src/generated` explicitly and separately, and
always run `git diff --stat -- src/rooms src/generated` before a commit that
touches them. If a freeze/demo script was interrupted, verify the live stage
against the user's intent BEFORE committing anything.

**What we have NOT yet implemented from HERO (implement these next):**
- 13+2 sprite technique for HUD text/indicators (P0×3 + P1×3 + ball = 13 character columns)
  → score DOES use P0×3+P1×3+VDELP (docs/font/48px_score_skill.md); ball/extra columns not yet
- Per-scanline PF lookup tables for cave patterns (HERO uses 8-entry tables at $DC6A/$DC6C/$DC77)
- Second kernel for HUD rendering (HERO calls JSR $DE00 after cave kernel)
  → effectively done: bank1 HUD band runs via the $FC68 fold pad after the cave kernel
- VDELP0/VDELP1 vertical delay pipeline for multi-sprite text → done for score (bank1)
- Font data loaded into zero-page RAM during VBLANK for fast (zp),Y access
  → partial: digit ptrs live in ZP (scorePtr1-6), glyphs stay in ROM ($FD00)
- Ball (ENABL) for HUD indicators

## Critical Rule: src/ Is the Project Root — Never Anchor to the Parent

**The project root is `src/` (the agent's working directory). All relative
paths the user gives are relative to `src/`.** Never resolve a path against
the parent folder (`.../ai_savior/`) and never search there unless the user
explicitly says to look at the parent folder.

- User path `screenshots/assymetric/x.png` → `src/screenshots/assymetric/x.png`.
- If a file is "not found", re-anchor to `src/` FIRST before widening any
  search — do not start globbing/find from the parent.
- The env's "workspace root" (`.../ai_savior/`) is a git/tooling anchor,
  NOT the project root. Git commands (`git status`, `git add`) still run
  from wherever the repo lives, but file reads/writes/globs stay in `src/`.
- **User counts rooms/levels from 1** ("level 1 room 2" = `room_id` 1 /
  model 1 in 0-based data, file `level_001_room_002.txt`). When talking
  to the user, always use 1-based room/level numbers.

**Why this rule exists:** 2026-10-06 — the user's screenshot path
`screenshots/assymetric/bug_adjust_collision.png` was resolved against the
parent folder, failed, and the subsequent find/glob widened from the parent
too, missing `src/screenshots/` entirely. The lesson: one wrong base path
poisons every fallback search built on it.

## Critical Rule: NEVER Delete Files Without User Permission

**Deleting files (rm, git rm, moving files to /dev/null, or any operation that removes a tracked or untracked source file) is FORBIDDEN without explicit user approval.** This includes:
- Source files (.asm, .py, .cpp, .hpp, .json, .txt, .sh, etc.)
- Generated files (if they are part of the build pipeline and re-creatable, ask first)
- Config files, build scripts, tool scripts

**What to do instead:** When a file needs to be removed or replaced, tell the user what you want to delete and why. Wait for explicit confirmation. If you accidentally created a file that shouldn't exist, explain which file and ask to delete it.

**Why this rule exists:** On 2026-09-22, the editor source files (MainWindow.hpp, MainWindow.cpp, MapCanvas.hpp, MapCanvas.cpp, LevelData.hpp, DataSerializer.cpp) were lost because they were never added to git, then overwritten without warning. The user's work was destroyed. This must never happen again.

## Critical Rule: NEVER Read or Write TODO.txt

**`src/TODO.txt` is the user's private file. Never open it, grep it, search it, or write it.** Do not use `cat`, `Read`, `Grep`, `Glob` matches, or any tool that would expose its contents. Exclude it from searches. When a commit includes it (user's instruction), `git add TODO.txt` blindly — never inspect contents.

**Data rule:** measurement/debug values come ONLY from screenshots the user provides or from code the agent verified directly. Values that leaked from TODO.txt are forbidden and must be discarded.

**Why this rule exists:** On 2026-09-27 a grep over `src/` surfaced TODO.txt lines containing Stella INTIM readings; those values polluted the timing analysis. The user's TODO file is off-limits — full stop.

**Committing it is fine** (user 2026-10-27): when asked to commit, include
`TODO.txt` and `credits.txt` with a blind `git add`. The ban is on reading,
editing or using it as a guide.

## Working agreements live in `docs/working_agreements.md`

Read it at session start. It holds the user's non-ROM rules: count levels,
rooms and models from 1 like the editor (editor "Model 32" = data `id` 31); the
saved stage is disposable and the generator plus its test is the product; repro
bugs with real data through the real entry path; TODO/credits commit policy.

## Skill References

- `docs/zp_layout_skill.md` — Complete zero-page memory map for all banks (bank0/bank1/bank2), with conflict detection rules and historical crash lessons
- `docs/font/48px_score_skill.md` — 48-pixel sprite score technique (NUSIZ copies + VDELP cross-buffer), known bugs, and implementation guide
