# Leaf-set relocation: bank0 → bank1 (2026-09-30)

Derived from `space_optimization.md` Q4. Goal: free ≈213 B in bank0
before further feature work. bank3 stays reserved for levels.

## Status

- [x] Stage 0 — baseline green (4×4096, verify_build OK/1 warn, sim OK, both tests pass)
- [x] Stage 1 — audit (results below)
- [x] Stage 2 — pad layout finalized (results below)
- [x] Stage 3 — batch A move (sounds): GREEN — build 4×4096, verify_build,
      sim_bomb_fuse, test_enemy_movement, test_level_bank all pass;
      pads $FBF8-$FC48 byte-identical bank0/bank1 (81 B);
      targets UBS=$F9C0 UJS=$F9CF BSD=$FA00 BSE=$FA13;
      measured: main end $FBDC (28 B slack to pad block), free gap
      $FEB3-$FEEF = 61 B, E4 gap $FC4F-$FC67 intact (FF fill).
- [x] Stage 4 — batch B move (dark/score/column/conn): GREEN — build 4×4096,
      verify_build OK (1 warn), sim OK, both tests pass.
      Targets: GC=$FA26 CPC=$FA38 AS=$FA7F IRD=$FAA7 SRD=$FABE;
      14 sites rewritten (4/1/4/3/2); pads $FBF8-$FC48 = 81 B identical.
      bank1 ZP mirrors added ($98/$A1/$A2/$E0/$C1/$C3/$CF/$DB/$8B/$8C +
      `Temp088 = $88` — bank0's Temp, NOT bank1's $AD scratch).
      Two catches fixed: (1) ObjSprites landed $FDEF (start+71 crossed a
      page → guard error) — `.ds $FE10 - *, 0` pinned it back to the FE
      page; (2) test_enemy_movement sliced DeriveEnemyY with
      `split("GetConnIdx:")` — marker gone after the move, retargeted to
      `ExitRoomDown:` (same physical spot, rts==2 semantics intact).
- [x] Stage 5 — verify_build `check_callpads()`: pad byte-identity
      $FBF8-$FC49 bank0/bank1 + ReturnPad==$FBF8 both banks + every
      CallPad jmp literal == bank1.lst label. Negative test: flipped byte
      at $FC00 in bank1.bin → guard fires. All gates green.
- [x] Stage 6 — measured: main content end **$FBB0** (72 B slack to pad
      block), free gap **$FE58-$FEEF = 152 B**, E4 gap 25 B → bank0 total
      free **249 B** (vs ~0 at Stage 0). bank1 free after moves: 286 B
      (tail) + 236 B ($FF0F region) + ~25 B E4-side = **~547 B**.
      NOTE: the pre-move "bank1 2819 B free" estimate never matched the
      binary — measured pre-move free was ~916 B; actual remaining after
      the 359 B of bodies+pads = ~547 B. Budget HUD growth against 547 B.
- [ ] User Stella smoke test: sounds (laser/blip/explosion), dark-room
      band + enemy lighting, bomb wall-punch, room transitions N/S/E/W,
      score award (+50/+75), lamp kill (SetRoomDark path).

## Stage 1 audit results (2026-09-30)

**Final list: 9 routines + 2 tables. EXCLUDED: `LoadRoomBottomColor`** —
body = `lda RoomBandColor / rts` (4 B); moving costs an 8 B CallPad > it
frees. Its 2 call sites keep direct `jsr`.

| routine | addr | B | sites (kernel.asm src lines) | flags after call |
|---|---|---|---|---|
| AddScore | $FCDE | ~44 | 2100, 2212, 2367, 3545 | none |
| UpdateJetSound | $FCB1 | 45 | 985 | none (2× rts) |
| UpdateBombSound | $FE98 | 13 | 982 | none |
| BombSndDrop | $F986 | 17 | 810 | none |
| BombSndExplode | $F997 | ~20 | 2166 | none |
| IsRoomDark | $FDA6 | 19 | 496, 1961, 3242 | **beq on Z** |
| SetRoomDark | $FDB9 | 18 | 2117, 3548 | none (2× rts) |
| ClearPFColumn | $FC80 | 49 | 2413 | none |
| GetConnIdx | ≈$F620 | 23 | 1648, 1660, 1671, 1684 | none (returns Y, X=0) |
| + BitMaskTable | $FBE4 | 8 | readers = IsRoomDark+SetRoomDark only | move along |
| + BombClearMask | $FA79 | 8 | reader = ClearPFColumn only | move along |

Audit proofs:
- **Flags**: `IsRoomDark` ends `and EnemyRamD / rts` (Z=dark) or
  `lda #0 / rts` (Z=1 lit). ReturnPad `pla` re-sets N,Z **from restored
  A** → `beq` behaves identically. Carry survives pha/lda/sta/pla.
  No caller branches on any other flag.
- **ZP/TIA only**: all "ROM reads" from round 1 resolved to ZP decls
  (`byte` block lines 97-134: Temp, RoomNo, LevelConnLo/Hi, Score*,
  JetPower, Collision*) or hardware (AUD*, SWCHA). `FetchPtr` staging in
  GetConnIdx = pure ZP; the actual bank2 read happens in the CALLER's
  `jsr FoldIndirect` (bank0, after return) — no fold inside any moved
  body.
- **No in-set calls**: SetRoomDark→LoadRoomBottomColor was a parser
  artifact; raw body has no jsr. Every moved body is a true leaf.
- **Phases**: VBL = IsRoomDark×3 (StartFrame 496, SelectActiveObject
  1961, BuildColupF 3242) + LoadRoomBottomColor (unmoved). Pad overhead
  +28 c/call → VBL worst +84 c (1235→1319 vs TIM64T window 1472 ✓).
  All other sites = overscan. **Zero kernel `.Line` callers.**
- **Table isolation**: BitMaskTable/BombClearMask have no readers outside
  the moved set.

## Stage 2 pad layout (final)

**Contracts (untouchable, all guard-checked by verify_build):**
`org $FC68/$FC70` fold pads (byte-identical, `jmp $F183` = Overscan
$F183 — no candidate sits before it, so it cannot move), `.ds $FC49`
pin (main + bank2), `.ds $FEF0` moth tramp + `.ds $FEF6` FoldIndirect
(byte-identical bank0/bank2), `org $FF00` fineAdjust, `org $FF20` laser,
`$FFF6-$FFF9` mirror. **Because `$FEF0`/`$FEF6`/`$FC49` are `.ds`
pins, upstream deletions automatically open headroom — no address
surgery anywhere.**

- **Pad block**: pre-pin slack, anchored `.ds $FBF8 - *, 0`
  (reachable after batch A's pre-pin deletions grow slack 76→~113 B).
  ReturnPad @ $FBF8 (8 B), CallPads after: batch A 4 → $FBF8-$FC1F;
  batch B +5 → $FC20-$FC47; `.ds $FC49` pin keeps filling to FC48 ✓.
  E4's gap $FC4F-$FC67 untouched ✓.
- **bank1**: `.ds $F9C0 - *, 0` + moved bodies (targets for CallPads),
  then `.ds $FBF8 - *, 0` + byte-identical pad copies, falling into the
  existing `.ds $FC68 - *, 0` stub block (bank1 F9C0-FC67 = 00-fill today).
- **Pad bytes** (identical both banks):
  `ReturnPad: pha / lda #0 / sta $1FF6 / pla / rts` (8 B);
  `CallPad_T: lda #1 / sta $1FF7 / jmp <literal bank1 addr>` (8 B).
  jmp targets = literals (byte-identity forbids per-bank symbols) —
  Stage 5 guard parses bank1.lst label addrs vs pad operands.
- **bank0 gain**: pre-pin deletions ≈76 B (bigger slack before FC49,
  feeds E4 too) + post-pad deletions 188 − 80 pads ≈ 108 B free gap
  before the FEF0 pin ⇒ **≈184 B net**.

## Cross-bank call mechanism

```
bank0 caller:  jsr CallPad_T          ; 3 B = same as direct jsr (net 0)
CallPad_T:     lda #1                 ; \
               sta $1FF7              ;  | 8 B, byte-identical BOTH banks,
               jmp T_bank1            ; /  at one fixed address pair
T (bank1):     ...body...
               jmp ReturnPad
ReturnPad:     pha                    ; save A (return value)
               lda #0                 ; \
               sta $1FF6              ;  | switch back to bank0
               pla                    ; / restore A — PLA sets N,Z from A
               rts                    ; popped return addr = bank0 caller ✓
```

- First 5 bytes of CallPad_T fetched from **bank0** (switch happens on
  `sta $1FF7`); `jmp` operand fetched from bank1. ReturnPad prefix runs
  in bank1, `pla/rts` fetched from bank0 → both pads must exist
  byte-identical at the same address in BOTH banks.
- Flags contract: carry survives pha/lda/sta/pla; N/Z after `pla`
  reflect returned A. Stage 1 must confirm no caller branches on flags
  independent of the returned A (if one does → upgrade ReturnPad with
  php/plp, +3 B).
- Stack: +1 transient byte (pha). `sim_bomb_fuse` guards (gameplay SP
  ≥ $F8, run ≥ $F7) must stay green.
- F6 hazard: pads at $FCxx — far from $FFF6-$FFF9 mirror ✓.
- ZP: moved bodies keep their original ZP addresses (RAM shared) — no
  new aliases introduced.

## Pad placement (finalized in Stage 1)

- bank0 home: the 75 B slack in front of the MothExitPad pin
  (`.ds $FC49 - *, 0` region, ≈$FC00-$FC48 after the score-fossil
  deletion). Anchor pads with `.ds PadStart - *, 0`.
- bank1 home: SAME addresses — inside bank1's free $F9C0-$FC67 zone.
- Budget: ReturnPad 8 + N × CallPad 8 ≤ 75 → **N ≤ 8 full pads**.
  Fallback if N > 8: (a) drop candidates Stage 1 finds dead, (b) slim
  CallPads in bank0 (only 5 bytes are fetched before the switch —
  documented fallback, weakens the byte-identity guard), (c) surface
  the shortfall to the user before choosing.
- Downstream address stability: deletions in the main region shift code
  toward the $FC49 pin (absorbed by the .ds anchor). Deletion of
  AddScore lives in the post-pad region (FC78+, added 2026-09-23 after
  `Origin Reverse-indexed`) — must insert a compensating `.ds` so
  ObjSprites / laser / fineAdjust / SetObjectXPos page contracts
  (verify_build guards) stay byte-stable. Stage 1 records exact
  addresses to decide.
- Never touch: ToMenuStub $FC68, ToGameStub $FC70, MothExitPad
  $FC49-$FC4E, $FFF6-$FFF9, org $FF00 / $FF10 / $FF20 regions.

## Move mechanics per batch

1. Cut routine bodies + any tables Stage 1 lists as ROM deps from
   `kernel.asm`; paste into `bank1.asm` at the chosen org (after HUD
   content, before pad addresses).
2. Every `rts` in a moved body → `jmp ReturnPad` (audit counts them).
3. bank0: insert pads, rewrite call sites `jsr T` → `jsr CallPad_T`
   (exact-symbol sed; Stage 1 lists every site).
4. Build: 4×4096 + verify_build + sim_bomb_fuse + movement/level tests.
5. Grep: no leftover `jsr T` in bank0; no orphaned tables.

## Guards (Stage 5)

- verify_build: pad bytes identical bank0.bin vs bank1.bin at the pad
  offsets (byte compare at `addr - $F000`).
- verify_build: `jsr CallPad_*` present / no raw `jsr T` of moved
  routines anywhere in bank0.
- Existing guards untouched: ObjSprites+71 page, Div15Loop $FF12-$FF1B,
  check_moth_tramp.

## Post-move bugfix (2026-09-30): pads clobbered the A argument

**Symptom (screenshots/bomb_bug.png):** bomb near the center thin wall
punched a hole visually at the SECOND tile from the left edge AND its
mirror (second from right) — center hole absent — while wall collision
behaved correctly.

**Root cause:** CallPads began `lda #1 / sta $1FF7` to trigger the F6
hotspot. The `lda #1` destroyed the argument passed in A. So
`ClearPFColumn` (A = col) received `A=1` → punched col 1 (+ mirror col
18) instead of the bomb's col. Collision stayed right because
`BombMarkWalls`/`WallMask` is a separate path. Same class hit
`AddScore` (A = BCD amount) → +1 instead of +50/+75.

**Fix:** F6 hotspots switch on ANY write — the value is ignored (proven
in-game by `FoldIndirect`'s `sta $1FF6` carrying data bytes) — so pads
now pass A through untouched: CallPad = `sta $1FF7 / jmp`,
ReturnPad = `sta $1FF6 / rts`. Pads no longer touch stack either (the
old `pha/lda #0/sta/pla` dance was only there to restore the A that
`lda #0` destroyed). Pad blocks shrank 20 B in both banks; byte
identity and jmp literals unchanged; addresses after the block are
pinned by `.ds $FC49` so nothing else moved.

**Guards added to `check_callpads`:** ReturnPad must be exactly
`8D F6 1F 60`; no `lda/tax/tay/txa/tya/pha/pla` allowed in any pad
body. Both negative-tested (insert `lda #1` → fires; corrupt ReturnPad
byte → fires).

**Gates after fix:** build 4×4096, verify OK (1 warn), sim OK, both
tests pass; Stella headless 691 frames × exactly 262, min SP $F9.

## Rules

- One batch per build; nothing proceeds on a red build (AGENTS
  build-test-build).
- No kernel `.Line` / VBL timing budget changes — pads live only on
  overscan/VBL call paths (Stage 1 flags any caller in a timed region;
  VBL window currently +237 c margin ≈ 12 c pad overhead is fine).
- No file deletions; only routine-body relocation inside existing files.
