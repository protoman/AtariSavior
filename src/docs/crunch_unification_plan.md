# Crunch unification — plan + size ledger

Status: **in progress** (started 2026-10-19). Goal: shrink the vcrunch/hcrunch
subsystem (~1.5 KB between bank3 bodies and bank2 staging) without changing what
the player sees. Every chunk lands as its own commit, build + both sims + full
battery green, and the ledger below is updated in the same commit — that is the
tripwire if a later chunk misbehaves: diff the ledger, find the chunk.

## Behaviour that must NOT change (user rulings)

- vcrunch: sprite-slice shutter over the middle band; cold kill only while
  closing and only when the player is fully inside closed slices; hot band kills
  on touch; a closed shutter is a SOLID block (no walking through); one kill per
  room visit (b7 latch); side brushes never kill.
- hcrunch: prefix band from col 0; cold kill while closing (sc < 52) at any
  extent; hot exempt; grow-to-center push (HcrPush) keeps a cold shutter from
  sealing the player inside; kill latch once per visit.
- Both: kill test runs on the same clock the kernel rendered (EnemyRamP-1), and
  the record walk stays in PhaseBlink.

## Chunk list

| chunk | content | expected |
|---|---|---|
| C1 | merge `HOVFeatEntry` + `HOVvcrunch` + `HOVhcrunch` into one dispatcher (shared field drain + latch) | ~ -100 B |
| C2 | share the PF staging between `VcrShutter` (bank2) and `PhHcrEntry` (bank3) — needs both in one bank | ~ -80..150 B |
| C3 | fold `HcrPush`/`HcrClock` into the staging path, drop the bank3 tramp + pads | ~ -40 B |
| C4 | drop the retired legacy twin images (`jmp $F800`/`jmp $F880` fill) and re-pin the pads | ~ -6 B |

C2 is the structural one; it may require the level-data move to bank3 first
(bank2 needs the room).

## Size ledger

Measured with `tools/rom_size_report.py --md` (DASM listing-based; code vs data
vs fill, plus generated level-data bytes).

### Baseline (start of crunch work, commit `61fcd15`)

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3180 | 360 | 554 | 3540 | 556 |
| bank1 | 2628 | 554 | 552 | 3182 | 914 |
| bank2 | 2705 | 748 | 617 | 3453 | 643 |
| bank3 | 834 | 69 | 942 | 903 | 3193 |
| **total** | **9347** | **1731** | **2665** | **11078** | **5306** |

level data: index 56 + level tables 334 + models 166 = **556 B**

### C1 — single HOV dispatcher (`HOVFeatEntry` + `HOVvcrunch` + `HOVhcrunch` merged)

| bank | code | data | fill | used | free |
|---|---|---|---|---|---|
| bank0 | 3180 | 360 | 554 | 3540 | 556 |
| bank1 | 2628 | 554 | 552 | 3182 | 914 |
| bank2 | 2705 | 748 | 617 | 3453 | 643 |
| bank3 | 824 | 69 | 952 | 893 | 3203 |
| **total** | **9337** | **1731** | **2675** | **11068** | **5316** |

delta vs baseline: code **-10 B** (bank3), used -10 B. Level data unchanged
556 B. (The merge removed the jsr/rts pair + one drain, but the two arms'
bounds checks and the near-trampolines cost most of it back — C2/C3 carry the
real weight.)
