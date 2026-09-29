# Level Data Bank Relocation — Implementation Plan

**Status: PLAN (not started). Companion to `level_bank_investigation.md` (§3
HERO rule, §10 layout decision).**
Date: 2026-09-27

**Goal:** ALL generated level data (models + rooms + level tables) lives only
in bank2 (and bank3 later). bank0 keeps game code only. Mechanism = HERO fold
(HERO's rule: reader travels to the data, whole-game code never copied).

**How to resume:** this file is the checklist. Tick `[x]` as steps complete.
Each step lists: change → static check → build check → (gate) Stella check.
Nothing moves on until the previous step's checks are green.

---

## 0. Frozen contracts (read before touching anything)

1. **Fold block — exact bytes (P3.1 revision — deviation note after the block):**

```
; Caller contract: bank select is ABSOLUTE `sta $1FF8` (bank2) — X and Y are
;                  both preserved, A = junk in / data out.
; Address FOLD_ADDR = $FEF6, region = 9 code bytes + 1B zero margin
; (realized: both banks assemble the SAME source — byte-identical region,
;  simpler than the original split-filler sketch; execution is identical
;  because the inactive bank's bytes are never fetched).
;
; region bytes ($FEF6-$FEFF):
;   +0..2: sta $1FF8     (3B)   ← fetched/executed in bank0
;   +3..4: lda (FetchPtr),Y (2B) ← fetched after switch → runs in DATA bank
;   +5..7: sta $1FF6     (3B)   ← runs in DATA bank; switches back, A kept
;   +8:    rts           (1B)   ← fetched back in bank0
;   +9:    zero margin   (1B)   ← guard asserts 0 (growth detector)
;
; Flow: bank0 jsr FOLD_ADDR → sta $1FF8 switches bank at instruction end →
; PC+3 fetched from DATA bank: lda (FetchPtr),Y (read ROM there) →
; sta $1FF6 writes result byte to hotspot → switches back to bank0, A is
; preserved by sta → PC+8 fetched from bank0 = rts → caller.
```
   - Write-triggered switch (F6 hotspots respond to writes — BIT/read style
     is F8-only; we use `sta`).
   - `sta $1FF6` both switches AND keeps A → no temp cell for the result.
   - **Never reorder/insert anything in the 9-byte region in bank0 without
     doing the same in bank2/bank3.** `verify_build.py` guard enforces this
     (byte-identity + opcode bytes + label address + zero margin).
   - **P3.1 deviation (2026-09-27):** bank select changed from
     `sta $1FF8,X` (X=0/1 → bank2/bank3) to absolute `sta $1FF8`.
     Reason: every enemy loop keeps the **slot in X**, and the X
     save/restore dance has no free temp (DEY/snake hold `Temp` live across
     the read). All level data is bank2 — X-selection was dead weight.
     bank3 data (P4) must get a **second entry point** (`sta $1FF9`, another
     9B pad) — do NOT reuse this block. Updated in lockstep: both source
     copies, `verify_build FOLD_BYTES` (`8d f8 1f ...`),
     `test_level_bank BLOCK`, §0.3 below.

2. **`FetchPtr` = ZP pair `$E0/$E1`** (alias over `PF2Buf[5]/[6]`, same
   family as the documented `$F0-$F2` bomb-save alias). Contract to preserve:
   - Writers: (a) VBLANK `LoadPFBuffer` (rows built from ROM — `$E0/$E1` are
     destinations inside the PF2 phase), (b) overscan/VBLANK routines staging
     a pointer immediately before a fold batch.
   - Readers: fold body (data bank), during overscan/VBLANK only.
   - Kernel/HUD never depend on `$E0/$E1` *as FetchPtr* (HUD rebuilds
     scorePtr1/2 itself — **must be verified in P1.3**).
   - Rule (E0 lesson): set FetchPtr **immediately before** the fold batch,
     never rely on it surviving across a `jsr` that writes `$E0/$E1`.

3. **Bank-select addresses:** bank2 = `$1FF8` (FoldIndirect, absolute
   select); bank3 = `$1FF9` (unused until P4 — needs its own fold entry).
   bank3 also holds the power-up reset stub (`$F000`) + vectors
   (`$FFFA`) — data `org`s around them; these 14 bytes never move.

4. **Addresses that guards already protect (never break):**
   `ToMenuStub=$FC68`, `ToGameStub=$FC70` (fold jmp target must equal
   Overscan), `fineAdjustTable` page-aligned `$FF00`, `SetObjectXPos` in
   `$FF10-$FF1F` with `.Div15Loop` same-page, `ObjSprites+71` same-page as
   `ObjSprites`, kernel `.Line` `lda ObjSprites,X` page contract.
   New size changes in pre-pad **will** move labels — that is expected in
   P2; the guards re-derive, but read every warning/error after each build.

5. **Frame sections are TIM64T-paced** (VBLANK 37 lines `kernel.asm:388`,
   overscan 30 lines `:689`). Work that overruns the timer = roll (documented
   262/274 lesson). Every phase that adds per-frame work MUST run the
   timing measurement step (§T).

6. **bank1 sync:** if Overscan moves, `bank1.asm` `jmp $F178`-style fixups are
   caught by the fold guard (`fold jmp target == real Overscan`) — fix by
   editing bank1, never by weakening the guard.

---

## P0 — Bootstrap: a 9-byte hole in bank0 (block is 9B + 1B margin)

**Why:** the fold block callers live in bank0; bank0's only genuine free
regions are `$FEF7-$FEFF` (9B, `.ds $FF00-*` pad before fineAdjust) and
`$FFF4-$FFF9` (6B, pre-vector pad). Need 9 contiguous bytes (10 incl. margin).

- [x] **P0.1 — inventory guards before touching code**
  - Read `tools/verify_build.py` fully; list every assert/warn.
  - Record current: `Overscan` addr (from bank0.lst, currently ~`$F178`),
    main end (`$FC64`), ObjSprites addr, PlayerColTable addr, kernel `.Line`
    page-sensitive loads (`lda ObjSprites,X`, `lda PlayerColTable,Y`,
    `lda (Grp0Ptr),Y`, `bcs .Div15Loop`).
  - Check: `rtk grep -n "ObjSprites\|PlayerColTable" src/bank0.lst | head`.
  - Save baseline: `cp src/bank0.lst /tmp/bank0_p0_baseline.lst`.
  - **Result:** baseline recorded — Overscan `$F178`, main end `$FC64`,
    ObjSprites `$FEAF`, PlayerColTable `$F9CD`, SetObjectXPos `$FF10`.
    verify_build guard families: fold pads + ToMenu/ToGameStub + Overscan
    target, headroom warn, Div15Loop page+range, ObjSprites+71 page,
    .Line branch pages, BeamMask $FFxx, level checks, E0 alias ordering.

- [x] **P0.2 — find ≥1B to shave (need pad ≥ 10B incl. margin)**
  - **Done:** `kernel.asm` `.BCFdarkFill` shape — `bne/.BCFdarkBlack +
    jmp .BCFdarkFill` (9B) → `beq .BCFFuseGrey + beq .BCFdarkFill` (8B,
    −1B). Safe: `COLOR_CAVE_BG = $00` guarantees the second `beq` taken;
    `COLOR_DARK_PF = $04`. Semantics unchanged (fuse→grey, else black).
  - Check: `./build.sh` green; **zero new warnings** — OK (headroom warn
    unchanged, pre-existing). lst diff = shifts only after shave point
    `$FE93` (kernel `.Line` at `$F100` untouched); ObjSprites `$FEAF→$FEAE`
    (same page ✓).
  - **Page contract re-check:** verify_build green (ObjSprites+71, Div15,
    .Line branches all re-derived from new lst).

- [x] **P0.3 — confirm pad ≥ 10B**
  - **Result:** pad = **10B at `$FEF6-$FEFF`** (block later occupies
    `$FEF6-$FEFE`, margin byte `$FEFF` = 0).
  - Gate: none (pure space). Not committed (user rule).

---

## P1 — Fold block in bank0 + bank2 + guards (no behavior change)

- [x] **P1.1 — place the block**
  - **Done:** `kernel.asm` pad site → `FoldIndirect` (9B: `9d f8 1f b1 e0
    8d f6 1f 60`) + `.ds $FF00-*, 0` (1B margin at `$FEFF`). Lands
    `$FEF6-$FEFF`. `FetchPtr = $E0` EQU added by `ColupfBuf` with full
    alias contract comment.
  - Check: build green; `FoldIndirect` label at `$FEF6` in `bank0.lst`,
    `org $FF00` still next origin (no Origin errors).

- [x] **P1.2 — bank2 gets the data-bank copy**
  - **Done:** `bank2.asm` — same 4-instruction source after
    `.ds $FEF6 - *, 0` pin, `FetchPtr = $E0` EQU (must-match comment),
    stub + vectors unchanged. `build.sh`: `-lbank2.lst` added.
  - Check: build green; `src/bank2.lst` exists; region bytes
    `9df81fb1e08df61f6000` **identical in bank0/bank2**.

- [x] **P1.3 — verify bank1 rebuilds scorePtr1/2 every frame (FetchPtr
  safety)**
  - **Result:** `scorePtr1=$E0` (lo/hi `$E0/$E1`) rewritten inside
    `MenuMain` every HUD frame (`lda #>DigitGfx / sta scorePtr1+1..`,
    `sta scorePtr1..`). HUD runs after kernel+overscan windows; bank0 stages
    FetchPtr before each batch → no foreign writer in stage→use window.
    kernel.asm has **no** raw `sta $E0` (test asserts this).

- [x] **P1.4 — `verify_build.py` guards (extend, never weaken)**
  - **Done:** `check_fold_block` — region bytes == `FOLD_BYTES`
    (`9d f8 1f b1 e0 8d f6 1f 60`), bank0 == bank2 (10B incl. margin),
    margin byte `$FEFF` == 0, `FoldIndirect` == `$FEF6` in **both** lsts.
    Doc header updated.
  - Check: green; deliberate byte-flip in bank2.bin → **guard FAILED
    (exit 1)** → restored → OK.

- [x] **P1.5 — static test file**
  - **Done:** `tools/test_level_bank.py` — block shape in kernel+bank2
    (exact 4 mnemonics), `FetchPtr=$E0` in both, `.ds $FF00` margin after
    block, `.ds $FEF6` pin before block, bank1 scorePtr rebuild strings,
    no raw `sta $E0` in kernel.
  - Check: green alongside `test_enemy_movement.py`, `test_laser_s4.py`.

- [ ] **P1.6 — runtime gate (no call sites yet — must be behavior-neutral)**
  - Stella: game boots, plays, HUD, bombs, laser — **identical to baseline**.
    Also eyeball bomb-fuse / dark-room wall colors (P0.2 restructured that
    branch — same semantics by reasoning, verify visually).
  - Build size sanity: `bank0.bin`/`bank2.bin` = 4096 each. ✓ (already green)

---

## P2 — Move generated data to bank2 + route cold reads

**Layout rule:** generated data keeps **today's exact addresses** (`$F9xx-
$FBAx`-ish range — exact start = address of the `include` at
`kernel.asm:2277` in the P0 baseline lst). Pointers (`RoomPF0Lo`,
`RoomRectsLo`, `LevelPFDataLo`, `LevelConnLo`, `LevelEnemyLo`, enemy record
pointers) therefore keep their **values unchanged** — only the bank behind
them changes. If data wouldn't fit the original addresses in bank2 (stub
`$F000-$F007` is far below; vectors far above — it fits), stop and rethink.

- [x] **P2.1 — measure the data block** *(done — recorded in S2 log)*
  - From P0 baseline lst: record start/end of the two include regions
    (`levels_data.asm` include at `kernel.asm:2277` covers models + rooms +
    levels; `levels.asm` include at `:2289`). Write both addr ranges here
    during implementation: `DATA_RANGE = $F9D9-$FB1E` (326B; verified —
    `bank2.lst` shows both includes spanning exactly this range).
  - Check: `python3` script sums byte lengths of
    `generated/*.asm` payloads == `B-A+1`.

- [x] **P2.2 — build.sh: generate data for bank2, not bank0** *(done — S2:
  `convert_level.py` outputs byte-identical; only WHERE the includes live
  changed; `-lbank2.lst` added to build.sh in P1.2)*
  - Keep `convert_level.py` outputs byte-identical (payload change only in
    WHERE included). Add nothing to JSON flow.
  - Edit `build.sh`: bank2 dasm line unchanged; the generated includes move
    textualy (next step) — no script logic change needed **except**:
    confirm `verify_build.py` "generated level asm identical to committed"
    still runs.

- [x] **P2.3 — bank2 emits data at the frozen addresses** *(done — S2:
  `bank2.lst` shows `M0TilePF0` etc. at the frozen `$F9D9-$FB1E` addresses;
  pointer values unchanged, only the bank behind them differs)*
  - `bank2.asm`:
    ```
    org $F000
    <stub + vectors as today>          ; stays first
    org <DATA_START>                   ; e.g. $F9E0-ish
    include "generated/levels_data.asm"
    include "generated/levels.asm"     ; exact order as kernel.asm:2277/2289
    .ds <next org> - *, 0
    ... fold block already at FOLD_ADDR (P1.2 — include order must keep it)
    ```
  - Watch: fold block addr (`$FEF6-ish`) is **between** data start and
    vectors — pad around it: data include must end **before** FOLD_ADDR or
    start **after**… data range `$F9xx-$FBAx` < `$FEF6` ✓ no collision.
  - Check: `bank2.lst` shows `M0TilePF0` etc. at EXACTLY the baseline
    addresses (`rtk grep M0TilePF0 src/bank2.lst` vs baseline).

- [x] **P2.4 — bank0 stops including data**
  - `kernel.asm`: delete lines 2277 & 2289 includes (and any comment
    dependency). Data space becomes bank0 code space (compaction: code after
    the old data moves DOWN by `B-A` bytes; labels auto-adjust).
  - Check (ALL must pass):
    1. `./build.sh` — zero errors; list every warning; fold/Overscan guard
       may demand `bank1.asm` jmp fixup → fix bank1, rebuild.
    2. `rtk python3 ../tools/verify_build.py` — page guards pass
       (`ObjSprites` same-page, `SetObjectXPos` block untouched (org-fixed),
       `.Div15Loop` page).
    3. `rtk python3 ../tools/test_enemy_movement.py` + `test_laser_s4.py` +
       new `test_level_bank.py` green.
    4. `bank0.lst` must NOT contain `M0TilePF0`/`LevelDataTable` labels
       (add this assert to `test_level_bank.py` in this step).

- [x] **P2.5 — band-color cache byte (DEVIATION: VBLANK-staged, not
  EnterRoom-time)** — audit found **no** byte that survives an EnterRoom
  write through bank1 HUD + next-frame VBLANK rebuild (all candidate ranges
  VBLANK-rebuilt or bank1-written). Solution: write the cache **every frame
  in VBLANK after `LoadPFBuffer`/`BuildColupF`** via fold (RoomNo\*4+3 from
  LevelEnemy record), so ordering is structurally guaranteed each frame.
  - Chosen: `RoomBandColor = $D1` (alias `PF1Buf[2]` — kernel reads PF1Buf
    row 2 only during group-0 render, before the water strip).
  - Writers/reader table recorded in `docs/zp_layout_skill.md` + decl comment
    in `kernel.asm`.
  - `.WaterRow` lost its Y save/restore (new body = A-only); VBLANK stage
    added after `jsr BuildColupF` (timer-paced region, fits).
  - Check: build green.

- [x] **P2.6 — route cold reads through fold (EnterRoom first)**
  - `EnterRoom`: 7 reads → two fold batches, each with its own
    stage (`LevelPFData` then `LevelEnemy`) + `ldx #0` per batch.
  - `LoadRoomBottomColor` body → `lda RoomBandColor / rts` (name kept).
  - Check: build green; asserts added (no `lda (Level*)`, ≥14 fold sites,
    cache contract).

- [x] **P2.7 — route `LoadLevel` + `ExitRoom*` reads**
  - `LoadLevel` 14 reads → single stage (`LEVEL_DATA_ADDR`) + 14 folds
    (done early as part of P2.4/P2.5 batch — first runtime fold site).
  - `GetConnIdx` now stages `LevelConn` + `ldx #0`; all 4 `ExitRoom*` reads
    → `jsr FoldIndirect` (Y set by handlers' iny path, unchanged).
  - Check: build green + static asserts (`no lda (LevelConnLo)` — covered by
    the generic `lda (Level*)` assert).

- [ ] **P2.8 — runtime gate P2 (THE room/level gate)** — **ORDER FIX:
  blocked on P3.3.** Walls (`LoadPFBuffer`) + enemy records + rect walks
  still read raw bank0-stale pointers → runtime is broken until P3.1/P3.3.
  Merged order: **P3.0 §T baseline → P3.1 → P3.3 → this gate.**
  - Stella full pass:
    - Level 1: room transitions all 4 directions, PF walls correct
      (**data-address freeze proof**), water band color on/off per room,
      kill+score, bombs+thin walls, reload on death.
    - Level 2: same + tentacle/bat/spider/snake positions (enemy records
      moved!), dark room (lamp), hot rock walls.
    - Level advance / `ReloadLevel` (miner spawn reads).
    - No roll/flicker (frame length: Stella `scanline` at kernel entry ==
      baseline value from P0.1).

---

## P3 — Per-frame reads through fold (timing-measured)

> Read §0.1 timing contract first. Run §T before and after.

- [ ] **P3.0 — §T timing baseline** *(revised at P3.1: a pre-P3.1 baseline
  is INVALID — enemy type reads returned bank0 garbage, so dispatch
  branches ran different paths than correct-data timing will. First clean
  baseline = post-P3.1 build; P3.0 and P3.2 merge into one measurement.)*
  - Measure at **post-P3.1 build**: (a) TIM64T at VBLANK end (breakLabel
    `.WaitVBLANK` = `$F0CB`, read INTIM on first entry); (b) TIM64T
    remaining at overscan end (breakLabel `.WaitOverscan`, read INTIM);
    (c) frame lines (Scn diff between two `Overscan` hits = `$F18A`,
    must be 262).
  - Record numbers in this file: `VBLANK_LEFT=__c OVERSCAN_LEFT=__c LINES=__`.

- [x] **P3.1 — enemy record reads (overscan, 15 sites)** *(done 2026-09-27)*
  - **Contract change (§0.1 deviation):** fold bank select is absolute
    (`sta $1FF8`) — X preserved, so slot-in-X loops fold directly; the
    plan's original "`ldx #0` once" scheme was impossible (no free temp).
  - Stage sites (6): `LoadEnemyRam` top, `UpdateEnemies/UE_Start`,
    `DeriveEnemyY` entry (per call — caller's slot X survives),
    `SelectActiveObject` (before `jsr IsRoomDark`), `CEH_HasEnemies`,
    `LaserHitTest` entry. Closure-checked: no callee between stage and
    fold writes `FetchPtr`/`$E0`/`EnemyDataLo`.
  - Reads folded: LER 3, UE 5, DEY 3, SO 2, CEH 1, Laser 1 = **15**
    (41 `jsr FoldIndirect` total = 26 P2 + 15).
  - Follow-up fixes hit: `UE_Loop` exit → `bcc UE_Alive / jmp UE_Exit`
    (stage+reads pushed `bcs UE_Exit` 131B > range); `EnemyOffTable` +
    `BitMaskTable` moved from `$FF20` tail to end of main (laser stage
    +9B overflowed `$FFFA`; main now ends `$FB9F`, ~105B free).
  - Guards updated: `test_level_bank` (+`EnemyDataLo`, ≥41 folds, ≥22
    stage lines, BLOCK `sta $1FF8`), `test_enemy_movement` DEY fold
    expectation, stale "X = bank2" comments rewritten.
  - Checks: build green, verify_build 0 warnings, all 3 suites green.

- [ ] **P3.2 — timing re-measure §T (overscan half)** *(merged with revised
  P3.0 — one post-P3.1 measurement covers both)*
  - Overscan budget: TIM64T=35 ≈2240c; P3.1 added 15 folds × ≈26c +
    6 stages × ≈14c ≈ +474c worst case. Pass criterion: overscan-end
    TIM64T remaining > 0 with margin, **and** frame lines = 262.
  - FAIL path: reduce (fold only active-slot reads; hoist duplicate folds of
    the same Y offset; consider M3 leaf-copy upgrade for the worst routine —
    re-enter plan design, do not hack cycles).

- [ ] **P3.3 — `LoadPFBuffer` per-read fold (VBLANK)** *(code done 2026-09-28;
  checkbox waits on user wall validation)*
  - Implemented as 3 register phases, **3 bytes each** (not 12): kernel `.Row`
    reads X=0..2 and `ClearPFColumn` walks rows 0..2 — buffer bytes 3-11 are
    fill-only dead weight (all generated models have 00 there; bank1 score
    uses its own `$B3`/`$C6` buffers). Stage FetchPtr once per phase; the
    original plan's per-row PF2 re-stage (dest `$E0` at row5+) is moot at
    rows 0-2. Runtime cost ≈ 9 folds + 3 stages ≈ 300c (plan estimated 36
    folds ≈ 1120c — the fill-12 structure it assumed was itself dead weight).
  - **Phase_1 dump verdict (step4/step5):** PF0/PF1[0..1]/PF2 rows all match
    `models_data` exactly → fold data path correct. Two alias bytes explained:
    `$E0/$E1` = staged pointer (PF2Buf rows 5-6, never read → harmless),
    `$D1` = RoomBandColor clobbering PF1Buf[2] → **real bug** (bottom-band PF1
    wall rendered as band color: room 0 band=$00 vs model=$ff → mid-wall gap
    + cell-map collision mismatch = user's "collision incorrect"/"gaps").
  - **Fix 2026-09-28: `RoomBandColor` `$D1` → `$D2`** (PF1Buf[3], dead row;
    bank1 has no `$D2` EQU). Guards: `test_level_bank.py` asserts `$D2` and
    rejects `$D1`; `zp_layout_skill.md` updated. Fill trimmed to 3 in the
    same edit (stops the fill clobbering `$D2`).
  - Check: build green; PF buffers visually identical in Stella (walls
    correct = data path proof) **+ bottom-band wall now complete (the $D2
    fix's visual signature: row 2 PF1 = $ff).**

- [ ] **P3.4 — timing re-measure §T (VBLANK half) + frame gate**
  - Expect ≈ +750-900c vs post-P2 baseline. Pass: VBLANK-end TIM64T still
    > 0 with margin ≥ ~100c and frame lines unchanged.
  - FAIL path (documented decision point): fall back to
    **Pattern A impossible in bank0** (needs body-sized hole ≈45B — we do
    not have it; per investigation §6). Options then: (1) reduce per-frame
    PF reload (stop bank1 HUD corrupting buffers → VBLANK-only-on-room-change
    load — HUD workspace relocation study), (2) split LoadPFBuffer staging
    tighter, (3) revisit. **Stop and ask user on FAIL.**

- [ ] **P3.5 — runtime gate P3 (full regression = E5-style)**
  - Stella: all 4 movers + snake + laser sweep + bombs + walls destruction +
    room transitions + score + lamp dark + water kill + HUD intact +
    no flicker/roll/flicker objects. Frame `scanline` == baseline.

---

## P4 — Enable bank3 (second data bank)

> Only start when bank2 data region approaches full (or to prove the leg
> early with one level — default: PROVE EARLY with level_002).

- [ ] **P4.1 — bank3 layout**
  - `bank3.asm`: keep power-up stub `lda #0/sta $1FF6/jmp $F005` at `$F000`
    + vectors; add fold data-bank region (bytes = same shape as bank2) at
    FOLD_ADDR; move **level_002's** generated block to a `org` range in
    bank3 (data addresses = new — this time pointer VALUES change!).
  - Because level_002 addresses change: `convert_level.py` already emits
    addresses? — **verify**: generated `.word` pointer entries are absolute
    → generator must emit level_002 block **base-relative to bank3 org**.
    If generator hardcodes offsets from include position (labels, not
    numbers — likely `.word M3TilePF0` labels) then **labels resolve at
    assemble time in bank3.asm automatically** ✓ — check first; only if
    absolute numbers are emitted does the generator need a `--base` flag.
  - Check: `bank3.lst` — level_002 labels inside bank3, `bank2.lst` no
    longer has them.

- [ ] **P4.2 — guard for bank3 fold region** (mirror of P1.4 assert 4).

- [ ] **P4.3 — DataBankSel plumbing**
  - `EnterRoom`/`LoadLevel`/enemy staging: X must now be **level-dependent**
    (level_002 → X=1). Add `DataBankSel` concept: simplest = 1 ZP byte? —
    **no free ZP** → derive from `Level` flag bit: `lda Level / lsr?` —
    rule: `Level & 1 == 0 → bank2, ==1 → bank3` (level index parity) —
    document mapping in convert_level.py (it must EMIT level_002 into
    bank3 = odd). Stage helper:
    ```
    ; FoldSel: sets X from Level parity (2 instr + rts helper)
    ```
    per call site cost: ~5c. Alternatively dedicate X at staging time.
  - Check: build; static test: `test_level_bank.py` asserts level_002
    records in bank3.lst, level_001 in bank2.lst.

- [ ] **P4.4 — runtime gate P4**: full P2.8 gate **for both levels** +
    level advance/return path (level→level switch changes bank select).

---

## P5 — Cleanup & bookkeeping

- [ ] **P5.1** — update `docs/zp_layout_skill.md` (FetchPtr alias + cache
  byte), `AGENTS.md` memory-map bank table (bank2/3 content + fold rule
  "HERO rule: reader lives with data; whole-game never copied"), and
  `level_bank_investigation.md` status → COMPLETE (link this plan).
- [ ] **P5.2** — `docs/level_bank_plan.md` P0-P4 all `[x]`; plan doc's E4
  blocker updated: bank0 headroom figure (measure: main end addr after data
  removal — expect ~`$F9xx` headroom ≈ 400B+).
- [ ] **P5.3** — final full test run:
  `./build.sh && verify_build.py && test_level_bank.py &&
  test_enemy_movement.py && test_laser_s4.py` all green; bank sizes exact.
- [ ] **P5.4** — user final Stella gate; **commit only if user asks**
  (include `TODO.txt`, exclude editor-generated JSON churn unless user wants).

---

## §T — Timing measurement procedure (Stella)

1. `stella -debug savior.bin` → `clearbreaks` → `breakLabel <VBLANK_end_label>`
   (cave kernel entry) → `run` → read TIM64T (`t 0296` or watch window) +
   `scanline`.
2. `clearbreaks` → `breakLabel Overscan` → `run` → TIM64T remaining at
   overscan-end label (or measure via `scanline` deltas).
3. Compare to recorded baseline; frame total must stay 262.

## Risks (keep visible)

| Risk | Where | Mitigation |
|------|-------|------------|
| VBLANK overrun → roll | P3.3/P3.4 | §T before/after; fail path P3.4 |
| Overscan overrun → roll | P3.2 | §T; fold only needed sites |
| Fold bytes drift between banks | any | P1.4 guard (build fails) |
| Data address drift | P2.3 | label-address assert in test_level_bank |
| FetchPtr alias clobber (E0 lesson family) | P1.3/P2.6 | staging-immediately-before rule + writer table in zp doc |
| bank1 jmp Overscan drift | P2.4/P3 | existing fold guard; fix bank1 |
| Page contracts (ObjSprites/Div15) | P2.4 | existing guards; read every warning |
| X clobbered between stage and fold | P3.1 | **obsolete** — fold is X-agnostic (`sta $1FF8` absolute); X and Y preserved |
| Generator emits absolute ptrs | P4.1 | check labels-vs-numbers before moving level_002 |

## Session log (append while implementing)

- **S1 (2026-09-27):** P0.1–P0.3 + P1.1–P1.5 done; P1.6 awaits user Stella.
  - Shave: `.BCFdarkFill` restructure in `kernel.asm` (−1B; `COLOR_CAVE_BG=$00`
    makes 2nd `beq` safe) → pad 10B at `$FEF6`.
  - Fold block = **9B** (not 10 as first sketched) + 1B zero margin; both
    banks emit identical source; region `9df81fb1e08df61f60` + `00`.
    §0 contract block corrected to match.
  - `FetchPtr = $E0` EQU in kernel.asm + bank2.asm (dup operand, guarded).
  - `build.sh`: `-lbank2.lst` added. `check_fold_block` in verify_build
    (byte-identity/opcode/margin/label, deliberate-fail verified).
    `tools/test_level_bank.py` created, green. All suites green.
  - **Test/level conflict resolved (user choice):** user's editor edit put
    moth (type 4) in level_001 room0 (bat gone from level) — test
    `test_enemy_movement.py` level assert changed from "type==1 bat" to
    generic "room0 spawns ≥1 enemy". Moth renders (EnemyColorTable[4]+OBJ_MOTH
    exist) but motion no-ops until E4.
  - Uncommitted: level_001.json + generated (user's), kernel.asm, bank2.asm,
    build.sh, verify_build.py, test_level_bank.py, test_enemy_movement.py,
    plan/investigation docs. **No commit (user rule).**

- **S2 (2026-09-27):** P2.1–P2.7 done; runtime broken by design until P3.
  - Data block pinned `bank2 $F9D9-$FB1E` (326B); kernel kept hand copies
    `LEVEL_COUNT`/`LEVEL_DATA_ADDR`. LoadLevel's 14 reads = first fold site
    (stage `LEVEL_DATA_ADDR`, `ldx #0`).
  - **P2.5 deviation:** no ZP byte survives EnterRoom-write → next kernel
    read (VBLANK rebuilds buffers, bank1 HUD owns `$E0-$EF`). Fixed by
    **VBLANK-staged cache**: `RoomBandColor = $D1` (PF1Buf[2] alias), written
    after `BuildColupF` every frame via fold; `LoadRoomBottomColor` = cache
    read (A-only → `.WaterRow` Y save removed, line got cheaper).
  - P2.6: EnterRoom 2 batches (stage per batch). P2.7: GetConnIdx stages
    LevelConn, 4 ExitRoom reads fold. GetConnIdx comment updated.
  - Follow-ups hit: bank1 `jmp $F178` → `$F18A` (Overscan moved +18c code);
    FoldIndirect addr drifted to `$FEEE` when LoadRoomBottomColor shrank —
    pinned with `.ds $FEF6 - *, 0` in kernel.asm too; verify_build
    format-string bug (`'$04X'`) fixed.
  - `test_level_bank.py`: +P2 asserts (no `lda (Level*)`, ≥14 folds, cache
    contract, LEVEL_COUNT sync, LevelDataTable addr vs lst).
  - Gate order corrected (P2.8 needs P3.1/P3.3 first — walls/enemy/rect
    readers still raw). All suites green, verify_build 0 warnings.
  - Next: P3.0 §T baseline → P3.1 → P3.3 → P2.8+P3.5 gate.

- **S3 (2026-09-27):** P3.1 done — fold contract revised (absolute select).
  - **§0 contract change:** `sta $1FF8,X` → `sta $1FF8` (absolute). The
    plan's X=0 scheme collided with enemy loops holding the **slot in X**;
    no free temp for X save/restore (DEY/snake keep `Temp` live across the
    read). Lockstep: kernel.asm + bank2.asm copies, `verify_build FOLD_BYTES`
    (0x9D→0x8D), `test_level_bank BLOCK`, §0 doc.
  - 6 stage sites + 15 reads folded (41 total); stage windows
    closure-verified (no callee writes FetchPtr/$E0/EnemyDataLo).
  - Two size failures fixed: `bcs UE_Exit` 131B out of range →
    `bcc UE_Alive / jmp UE_Exit`; `$FF20` tail overflowed `$FFFA` by 3B →
    `EnemyOffTable`+`BitMaskTable` relocated to end of main (`$FB9F`).
  - P3.0 revised: pre-P3.1 baseline invalid (garbage types changed branch
    paths) — P3.0+P3.2 = one post-P3.1 Stella measurement
    (`.WaitVBLANK $F0CB`, `.WaitOverscan`, `Overscan $F18A` ×2 = 262 lines).
  - Build green, verify_build 0 warnings, all 3 suites green.
    Uncommitted (user rule). Next: user §T measurement → P3.3.
