# Architecture plan v3 — prepare for future features (2026-10-16)

> **SUPERSEDED 2026-10-16 by `docs/refactor_v4_plan.md`.** v3 assumed bank0 was
> full and that freeing space needs a 4-bank pin shift; that is false — bank0
> has a verified 225B free run at `$F7FC`, and there is ~3400B free overall.
> Read `docs/refactor_v4_plan.md` first.

Supersedes v2's scope (v2 = the mechanism; this = the whole prep pass). Goal:
land the five planned features (better physics, raft, game-over screen,
difficulty settings, intro music) **without another architecture pass**.
Built from verified F6 mechanics (see `bank0_space_plan_v2.md` for the gate).

## The four real walls (not just bank0)

| wall | today | what it blocks |
|---|---|---|
| **bank0 code** | 100% full, byte-identity-frozen | any new gameplay/display code |
| **ZP** | 128B, ~0 free | physics state, raft state, new config |
| **display-kernel coupling** | title kernel `bank0↔bank2` twin-coupled | new screens (game-over, intro-music) want bank0 |
| **data home** | bank2 fragmented; bank3 data-first | music note data, more levels |

Plus **ROM size** = 16K (F6). Free now: bank1 ~1.3K, bank3 ~2.2K, bank2 ≤41B,
bank0 ~0.

## Phase 1 — cross-bank call gate (mechanism)  [path 2]
As in v2: a bank1→bank0 trampoline (push a bank0 shim; `sta $1FF6` + `rts`-as-
jump; shim `sta $1FF7`+`rts`). ~5B of bank0+bank1 twins, carved from the bank0
**tail**. Unlocks moving coupled bank0 routines to bank1. **Validate with one
tiny move (`MothYDerive`, 25B, frees bank0 end → also unblocks Phase 8).**

## Phase 2 — free bank0  [path 3 + moves]
- Move the ~330B of post-pad **event** routines → bank1 (via the gate).
- **One** pin shift of `$FB00…$FC49` down by the total removed.
- Optional (path 3): bank2 level data + `EnterRoomB2` → bank3 (bank3 is the
  data bank) → opens a bank2 run → the **title kernel** → bank2 (its only
  valid non-bank0 home).
- Net target: **~300–600B** bank0 headroom.

## Phase 3 — ZP reclamation (concrete, VERIFIED)

The ZP is densely packed. Verified-reclaimable:

1. **Derive `RoomPF1*/RoomPF2*` from `RoomPF0*`** — VERIFIED: `M4TilePF0/1/2`
   are emitted contiguously (3 rows each), so `RoomPF1 = RoomPF0+3`,
   `RoomPF2 = RoomPF0+6`. **Save 4B** (`$9B/$9C`, `$9D/$9E`). Cost:
   `lda RoomPF0Lo / clc / adc #3` at the (few) PF1/PF2 staging reads.
2. **NOT viable (checked, do not plan):** deriving `LevelConn*/LevelEnemy*`
   from `LevelPFData*` — the per-level `RoomDataTable`/`RoomConnections`/
   `RoomEnemies` blocks are **variable size** (independent labels in
   `generated/*_rooms.asm`), so there is no fixed +N offset. Would need a
   data-format change (fixed-size level entries) — out of scope.
3. **Bracket scratch lifetimes** in `$E0-$EF` — `$E0/$E1` are documented spare
   (stomp-zone); a *staged-only* bank0 byte may live there (same rule as
   `FetchPtr`). Up to 2B for phase-local state (not persistent).
4. **Free `$F6/$F7` if desired** — the deep call path bottoms at SP `$F6`
   (frame→StepDown→PHM→rect-walk→FoldIndirect = 5 jsr levels). Removing one
   level (inline a leaf) moves the stack line down 2B → `$F6/$F7` become safe
   persistent bytes. Costs a small inline.

Result: **~4B guaranteed** (item 1) + up to ~4B (items 3/4) — enough for
`vxLo/vxHi` (physics inertia) or raft X/Y. Bigger ZP wins need either the
fixed-size-level-data format change (item 2) or relocating a persistent field to
a per-bank scratch slot with a documented time-partition (harder; audit first).

## Phase 4 — display kernels (stop the coupling)

Today the title kernel (bank0) + its fold bodies/twins (bank2) are inseparable.
To let **new screens** (game-over, intro-music) live in **bank1**:
- Give the display code its **own sprite/color data at bank1-local labels**
  instead of reading bank0's addresses through bank2 twins (the twins exist only
  because `TitleBandPrep` sets `Grp0Ptr` to a bank0 label). A bank1 screen that
  uses bank1-local art needs **no twins** → it can live in bank1.
- The **game-over screen** is the ideal first decoupled screen (simple text/
  graphics, no shared gameplay sprites). Build it in bank1 from day one.
- Intro **music** can run on the *existing* title screen (bank0/bank2) if the
  engine is small; if we also want a music/settings screen, build it in bank1
  under the same decoupling rule.

## Phase 5 — data strategy (music, levels)

Rule (already true, make it explicit + give helpers):
- **Big read-only tables live in bank3** (data-first, ~2.2K free).
- They are read via the **fold** (`FoldIndirect $FEF6`, byte-identical
  bank0/bank2/bank3) or by a bank3-side consumer.
- **Music**: note/instrument tables in bank3; the engine in bank1/bank2 reads
  them via a fold (cost is fine for a title-screen tick). Engine code ≤ a few
  hundred B (bank1).
- **More levels**: `convert_level` already emits per-level spill slices into
  bank2/bank3 — extend the split policy (`LEVEL_COUNT` guard) — no new wall.

## Phase 6 — ROM headroom (know the trigger)

16K (F6) = 4×4K. Post-Phases-1-2 there is ~3.5K free (bank1+bank3). The five
features ≈ 1–2K code + ~1–2K music data → **fits at 16K**. Trigger for an F4
(32K) move: when bank3 data (levels+music) exceeds ~3K or a 5th bank is needed.
That is a **separate, large** refactor (every twin address changes) — flag it,
don't start it.

## Execution order (each step: build + relevant battery + Stella)

1. **Gate + `MothYDerive` move** → validate the gate, free bank0's tail
   (25B → Phase 8 unblocks).
2. **Batch event routines → bank1** + **one pin shift**.
3. **ZP derivation** (items 1+2) — independent, low risk.
4. **Game-over screen** (decoupled, bank1) — proves the no-twin screen pattern.
5. **Path 3** (level data → bank3; title kernel → bank2) — only if bank0 still
   needs the room.
6. **Music** (bank3 data + bank1 engine).

## Honest risks

- The gate is new machinery — Step 1 must prove it in isolation before any batch.
- The pin shift is a coordinated 4-bank edit; `ReturnPad` already tracks its
  label (R slice 1), the rest are `.byte` twins.
- ZP derivation touches hot kernel/staging reads — keep the added cycles inside
  the per-scanline/VBL budgets (`sim_frame_budget`, `sim_bomb_fuse`).
