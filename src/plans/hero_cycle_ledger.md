# HERO Kernel Plan — Phase 0 Cycle Ledger (2026-10-21)

Measured, not estimated: `tools/cycle_ledger.py` parses `src/bank0.lst` and walks
the real assembled instruction stream (branch taken/not-taken and page-cross
costs come from the emitted bytes). Run it any time:

```
/home/iuri/python3/bin/python3 tools/cycle_ledger.py
```

Conventions: 76 cycles per scanline. `.Line` entry sits **8 cycles into a
scanline** (the previous line's `dec LineCount / bne .Line` runs right after its
WSYNC halt). A WSYNC store whose write lands at cycle C halts the CPU at C and
resumes at the next line start.

---

## 1. `.Line` paths (all six, from `.Line` entry)

| path | cycles | WSYNC store at line cycle |
|---|---|---|
| P1 player-in, object-in **← worst** | 64 | **72** |
| P2 player-in, object-out | 57 | 65 |
| P3 player-in, object first-out (A==8) | 62 | 70 |
| P4 player-out, object-in | 51 | 59 |
| P5 player-out, object-out | 44 | 52 |
| P6 player-out, object first-out (A==8) | 49 | 57 |

Store phases on the worst path (line-relative = next line's pixels):

| store | cycle | effect |
|---|---|---|
| `COLUP0` | c19 | this line (TIA applies immediately, pixels start c22.7) |
| `ENAM0` | c29 | this line (beam) |
| `GRP0` | c39 | next line (sprite byte written one line ahead) |
| `GRP1` | c62 | next line |
| `COLUP1` | c69 | next line |
| `WSYNC` | c72 | halts, resumes at next line |

### The real headroom is 1 cycle, not 4

`PlayerColTable` is placed at **$F8F5-$F900** — it straddles the `$F8`/`$F9`
page. The colour path runs only for `A0 <= 10`, i.e. `Y <= 11`, and **Y=11 is
the crossing row** (`abs,Y` read = 5c instead of 4c). So on the `A0=10` line:

- P1 = **73** (the project's stall contract is `<= 73`),
- P3 = **71**.

Absolute limit is the 76-cycle line, so there are 3 cycles of hard margin and
**0 cycles against the contract**. Any `.Line` addition must be paid for first.

---

## 2. Candidate verdicts (from `docs/hero_async.md` §4)

### ✅ 1. Laser beam fold — CONFIRMED, **−4 cycles**

`PlayerColTable` already carries the ENAM0 enable bit:

| row | value | bit 1 |
|---|---|---|
| 2 (beam row, `BeamMask[2]=2`) | `COLOR_P_YELLOW = $1E` | **1** |
| all others | `COLOR_P_RED = $48`, `COLOR_P_GRAY = $08` | 0 |

`LaserState` b1 = `LASER_ARMED = %00000010`, and `BeamMask` is
`0,0,2,0,0,…`, so `PlayerColTable,Y & LaserState` **is** `BeamMask & LaserState`
today. The fold:

```
lda PlayerColTable,Y     4c      lda PlayerColTable,Y     4c
sta COLUP0               3c      sta COLUP0               3c
lda BeamMask,Y           4c  ->  and LaserState           3c
and LaserState           3c      sta ENAM0                3c
sta ENAM0                3c      13c  (−4c, −12B table)
                     17c
```

Valid because TIA colour bit 0 is don't-care and bit 1 of every non-beam row is
already 0. `BeamMask` (12 B) and its page guard are deleted; a `verify_build`
assertion replaces them ("bit 1 set only at index 2 of PlayerColTable").

### ❌ 2. Object window — REFUTED

Computing the object row is already minimal: `tya` (2) + `sec` (2) +
`sbc ObjTop` (3) = 7 c, plus `cmp`/`bcs` (4). A VBL-staged row start cannot
remove the subtraction (the art index *is* `row`), and a ZP counter costs the
same to advance. No 4 c here.

### ❌ 3. Loop control — REFUTED

HERO pays `DEY/BMI` (4 c) because **Y is its loop counter**. In our loop Y is
the running sprite row (`A0+1`), so the counter must live in ZP:
`dec LineCount` (5) + `bne` (3) = 8 c. Freeing Y would cost more elsewhere.

---

### Post-fold measurement (Phase 2 landed, commit follows)

| path | before | after beam fold |
|---|---|---|
| P1 player-in + object-in | 72 | **68** |
| P2 player-in, object-out | 65 | **61** |
| P3 player-in, A==8 | 70 | **66** |

The `A0=10` page-cross line is now 69 — **4 c inside the 73 c contract and 7 c
inside the absolute line**. That 4 c is the whole budget for later `.Line`
work. `BeamMask` (12 B) is gone; `verify_build` now pins "bit 1 set only at
index 2 of PlayerColTable" instead of the old fetch/page guard.

---

## 3. `.Row` setup line — it is a **2-scanline window with ~60 free cycles**

Store phases (gameplay, no door; the door path lands COLUP1 at c64 instead):

| store | cycle |
|---|---|
| `PF0` | 37 |
| `PF1` | 44 |
| `COLUPF` | 51 |
| `COLUP1` | 67 |
| `ENABL` | 74 |
| `PF2` | 81 |
| `WSYNC` | 90 (rows 0/1) / 93 (row 2 tide) |

The WSYNC store lands 14-17 cycles into the **second** line, so the CPU halts to
the end of that line: the setup pass costs 2 scanlines. Accounting for the
frame: 3 bands × 1 extra line = +3, plus the 2 re-anchor lines = **262 + 5 =
267** — which is exactly `sim_frame_budget`'s cave target.

**Consequence:** everything after `sta PF2` (c81) up to the setup WSYNC has
**~59-62 free cycles** — adding work there does not shift any timing-critical
store and does not add a line (as long as the store stays ≤ 152).

**Stale comment found:** the header says `COLUP1 w c51`; that predates the
door/M1 branch. On the no-door gameplay path it lands at c64 (store ends c67).
Harmless (still after the left half), but the comment must be corrected.

---

## 4. Correction to the plan: the tint is NOT a persistence bug

Phase 3 of `hero_kernel_plan.md` assumed the `.ObjZero` A==8 colour restore was
still missing. **It is already in the kernel** (`$f176-$f17a`,
`lda Temp / sta COLUP1`, +6 c, and those 6 c are already inside P3's 70 c).
The sticky colour is therefore fixed; what remains is the **8-line overlap**
where the object's rows and the block are both drawn with `COLUP1`. One colour
register per scanline — no per-line table can separate them, in HERO or here
(HERO separates by channel: moving objects on `COLUP0` = P0, painted/static
elements on `COLUP1` = P1/M1).

So the tint fix is a **carrier** decision (async block on the ball = `COLUPF`,
i.e. option 2a), not kernel work: the generator side flip for cold rooms + the
hot-room staging in bank3. It is independent of Phases 4-6.

---

## 5. What this does to the plan's estimates

| phase | before (plan) | measured |
|---|---|---|
| 2 cycles | −8 c from 3 candidates | **−4 c** (beam fold only); object window and loop control closed; +4 c ROM freed |
| 3 tint | +10 c kernel restore | **not kernel work** — the restore exists; fix = ball carrier (bank3 + generator) |
| 5 flicker | +1-2 lines, needs Phase 2 funding | **0 extra lines**: per-band `RESP1`+`HMP1` fit the setup line's ~60 free cycles; `HMOVE` goes between the setup's `sta LineCount` and the band's first body line (CPU already resumes at that line's cycle 0-3 = HBLANK) |
| 6 tall sprites | kernel rewrite of the object path | **~+1 c** (`cmp ObjHeight` in ZP replaces `cmp #8`) + ROM art per type (~2 B per extra row: 1 art + 1 colour). One type per commit, ~36 B for an 18-row extension |

Wall-model target stays **267** through Phases 2-6 unless Phase 5's RESP proves
otherwise; the sim decides.

---

## 6. Open items for later phases

- `PlayerColTable` crossing `$F8/$F9` costs 1 c on the `A0=10` line. Either
  accept (contract is met) or reorder the $F8DD cluster so the crossing table is
  a sprite instead of the colour table — no win either way unless Phase 2 needs
  the cycle; note it, do not "fix" it blindly (the cluster is twin-pinned).
- `ObjColorTab` ($FE00-$FE47) and `ObjSprites` ($FE48-$FE8F) are in-page ✓ no
  cross penalty; `PlayerWalkA/B` ($FDDE-$FDF5) in-page ✓.
- The `.Row` door path (c64 COLUP1) is dead in the live stage (0 doors) but the
  phase must be re-checked if doors ever come back.
