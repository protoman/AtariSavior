# Lessons Learned — 2026-10-10: the `$FD6B` tramp escape

Bug #10 root cause: `BombEnemyBlast` cross-bank trampoline jumped to
`$FD6B`, but `BombEnemyBlastBody` lives at `$FD6A` — a 1-byte stale
operand. Execution entered mid-instruction (`lda EnemyCount` = `a5 b3`,
entered at `b3`) and ran garbage: `LAX ($F0),Y` / `ALR ($A5),Y` /
**`inc $4A,X`** — with the sim/user state producing `X=$80`, the `inc`
landed on `$CA` (wall PF2 band1) and physically set wall bits
(`$03→$04→$05…`). Both tramp copies (kernel.asm + bank2.asm twin bytes
at `$FDD8`) had the wrong operand; both comments documented it as
correct.

## 1. Why the simulations escaped it

1. **Tests assert outputs, not entry points.** Every green test checked
   *wall state, score, frame lines, SP depth* — nothing ever asserted
   *the tramp `jmp` operand equals the destination label address*. The
   one behavior test that ran the blast (`test_bomb_user_sequence`)
   watched writes into `$C3-$CB`, but the `inc` only hits a buffer when
   the garbage `LAX ($F0),Y` happens to load `X=$80` (or `$79`/`$43`…).
   In my sim runs that register state never occurred → 0 buffer writes →
   green. **The bug is state-dependent; output assertions sample one
   state.** An entry-point assertion is state-independent.
2. **The garbage stream reconverges.** Misaligned execution re-syncs
   with real code at `$FD72` (one `lsr` consumed the difference), so the
   body mostly "works": enemy-kill sometimes fails, `CollisionCellX`
   gets garbage — but tests either don't require a kill there or got a
   kill by accident. Near-correct aggregate behavior defeats
   outcome-based tests.
3. **The byte-identity guards covered the wrong pairs.** Guards exist
   for PickPlayerFrame (`check_frame_tramp`: bytes + operand == label)
   and the moth tramp fill (`check_moth_tramp`) — but BombEnemyBlast's
   twin was only "byte-identical with kernel.asm" (comment-only, both
   copies equally wrong) and its operand was hand-synced prose
   ("operand in kernel.asm"). **Byte-identity between two copies proves
   nothing when both share the same wrong literal; only
   operand == label is a real check.**
4. **Hard-coded addresses are a known-lossy pattern.** This is the same
   family as the historical `$F182→$F176→$F173` Overscan sync and the
   FFF2-FFFF9 hotspot lessons: literals written by hand, comments
   updated to match the wrong value, and the code "documented" as
   correct — documentation then *suppresses* suspicion.
5. **My static scans (this session) had two systematic holes** until I
   fixed them against the trace:
   - *operand-keyed*: looked for RMW/store operands ∈ `$C3-$CB` — missed
     `inc $4A,X` (base `$4A` + index `$80` aliases `$CA`);
   - *store-only*: first pass ignored RMW (`inc/dec/asl/ror…`) entirely.
   Static scans must resolve addressing modes (base+index, abs mirrors
   `$01C3/$04C3/…` = same physical RAM) or they prove a subset of the
   truth.
6. **Trace columns lie.** Stella's bytes/disasm columns come from the
   stale `savior.lst` (showed `00 brk` for everything). Trust only
   frame/bank/pc/regs; decode instructions from the built `.bin`. I also
   saw the junk tell — undocumented opcodes `b3`/`43` executing at odd
   pcs — and under-weighted it. **Any executed pc that is not an
   instruction start in `bankN.lst`, and any undocumented opcode, is
   junk execution until proven otherwise.**

## 2. Prevention (automation that kills this class)

- **[DONE 2026-10-10] `verify_build.check_tramp_targets`** — static,
  runs every build: scan sources for `sta $1FF6..$1FF9` + following
  `jmp $Fxxx`; assert the target is an instruction start in the
  destination bank's listing; assert kernel.asm tramp bytes == bank2
  twin bytes (`.byte $8D,$F8,$1F / $4C,$6A,$FD`) and that the operand
  resolves to `BombEnemyBlastBody`. Hand-synced literals are now
  machine-checked; the class dies here, not in a screenshot.
- **Instruction-start whitelist in sim watchers** — any py65 run that
  exercises bank switches should assert tramp-entry: after a write to
  `$1FF6-$1FF9`, the next fetched pc must be in the destination bank's
  instruction-start set. Cheap (set lookup at 4 addresses), catches the
  whole tramp family at runtime, independent of register state.
- **Buffer-write watcher = resolved address + RMW + mirrors + allowlist**
  — watchers must watch *physical* buffer addresses (zp/abs/indexed
  resolved per instruction, plus `$01xx/$04xx` RAM mirrors, plus RMW),
  and flag any writer outside the allowlist (`ClearPFColumn`, `EnterRoom`
  copy, boot `.ClearZP`) or violating the subset law. My trace parser
  now does exactly this; it found `inc $4A,X` after store-scans failed.
- **Undocumented-opcode census** — one line in the trace parser; nonzero
  output = red flag.

## 3. Reproducing WITHOUT user help (autonomous pipeline)

1. **py65 = primary repro vehicle** (`tools/test_bomb_user_sequence.py`
   pattern): full input pins (SWCHA/INPT4), real `sta $1FF8` hotspot
   switching (Mem.write already models F6), boot → drop-in → walk →
   drop → explode. Extend it with: (a) tramp-entry pc assertion,
   (b) physical-RAM write watcher + subset-law/allowlist, (c) sweep of
   register states at tramp entry (poke X across `$00-$FF` around the
   blast) so the state-dependent alias surfaces. Red/green with zero
   interaction.
2. **Stella trace session = second line when py65 and hardware disagree
   (this session's exact recipe, now reusable):**
   - `mv src/savior.script.tracebak src/savior.script` + same for
     `~/.config/stella/autoexec.script` (content: `logTrace`/`run`;
     keep `*.tracebak` by default — they crawl the game),
   - `timeout --signal=KILL 300 stella -debug -loglevel 2
     -logtoconsole 1 savior.bin > bomb_trace.log 2>&1`,
   - parse with the store/RMW/mirror + instruction-start + landmark
     scanner (this session's script; raw bytes stay in the sandbox),
   - rename scripts back, reset `stella.sqlite3` (`dbg.logtrace`,
     `logtoconsole`, `loglevel` = 0 — schema is `setting/value`, not
     `key/value`).
3. **Stella scripted snapshots need no joystick** — autoexec.script can
   arm a bomb entirely with RAM pokes (`ram $f6 $63 / ram $f7 $03 /
   ram $b5 $01`, always `$`-prefix) + `frame N` + `saveSnap` →
   deterministic blast screenshots. Limit: no joystick emulation and no
   RAM read-back, so *assertions* stay in py65; Stella provides the
   picture.
4. **What still needs the user**: live feel (flicker, input latency) and
   judging whether a visual is "wrong". Everything else — repro, capture,
   decode, verdict — is scripted above.

## 4. Recognition checklist (next time a "wall changed by itself")

1. `grep` tramps: `sta $1FFx` followed by `jmp $Fxxx` → target must be
   an instruction start (this exact bug took 30 seconds to find once the
   trace said "wrote bit-set but no store exists").
2. Any trace pc between two `bankN.lst` instruction starts = junk
   execution; dump ±1 bytes around it and decode from `savior.bin`.
3. Undocumented opcodes in trace = junk flow.
4. "No store can explain RAM" → think RMW, indexed base outside the
   target range, `$01xx/$04xx` mirrors, and stack pushes (`SP` low
   enough to alias) — in that order; my min-SP check (`$F9`) ruled the
   last one out.
