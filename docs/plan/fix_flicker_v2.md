# Fix Kernel Flicker — Practical Approach

## Problem
Kernel `.Line` worst-case = 80 cycles (4 over 76 limit). Flicker on scanlines where player + enemy + laser overlap.

## Root Cause
Three conditional sections in the inner loop:
- GRP1 range check: 22c worst (object visible) / 18c best (no object)
- GRP0 range check: 24c worst (player visible) / 18c best (no player)
- ENAM0 check: 17c worst (laser active) / 14c best (no laser)
- Loop control: 16c fixed

## Achievable Optimization: GRP1 Bitfield

Replace the per-scanline GRP1 range check (ObjTop ≤ Scanline < ObjBot) with a pre-computed bitfield.

### How It Works
1. **VBLANK:** For the active object, set bits in a 24-byte ZP buffer (192 bits = 192 scanlines)
2. **Kernel:** Load bitfield byte for current scanline, shift out bit, branch on result

### Cycle Savings
Current GRP1 (worst): 22c (two CMP + branches + BIT skip)
New GRP1: ~16c (LDA + LSR + BCC) — saves **6c per scanline**

### New Worst-Case Total
6 + 24 + 17 + 16 = **63c** (was 80c, saved 17c) ✓

### Implementation
1. Add `Grp1Bitfield` = 24 bytes at $D0-$E7 in ZP
   - Wait, ColupfBuf is at $D4-$DF. Can't overlap.
   - Move to $E8-$FF — but PlayerGrp0 is at $F8.
   - Available: $F3-$F7 (5 bytes). Not enough for 24 bytes.
   - **Use end of ZP:** $E0-$F7 = 24 bytes. But $E0-$E6 = ScoreTh..On + gap, $E7-$F2 = ColupfBuf.
   - **Option:** Put bitfield at $0200+ (stack page). WAIT — stack page mirrors ZP! Can't use.
   - **Option:** Put in ROM and read via `LDA table,Y`. Uses 24 bytes of ROM.
   - **Option:** Use 3 bytes of ZP as a "cache" and shift through them.

Actually, let me reconsider. The bitfield needs to be READ during the kernel, indexed by scanline. Options:

**A) ZP bitfield (24 bytes):** Not enough free ZP.
**B) ROM bitfield (24 bytes):** Pre-computed per frame, but ROM is read-only — can't write per-frame.
**C) ZP bitfield with banked layout:** Reuse PF buffer area... but PF buffers are needed during kernel.
**D) Reduce to fewer bytes:** Use a compressed format.

**E) Simplest approach: use the existing ZP variable `Grp1Prep` as a boolean.**

If `ActiveObjectOn=1`, the object IS in this room. The kernel still needs the range check to know WHICH scanlines. But what if we pre-compute JUST the range check result for the current scanline?

Wait — that IS what the current code does. The range check IS the per-scanline computation.

**F) Pre-compute GRP1 value ($f0 or $0) per scanline into a 192-byte buffer.**

192 bytes won't fit in ZP (13 free) or stack page (mirrors ZP). Could use $0200-$02BF but that's outside ZP and stack — wait, on the 2600, $0200-$02FF mirrors $80-$FF (ZP). There's NO separate memory.

**G) Use ROM tables + indirect indexed addressing:**

Store a 192-byte ROM table where byte N = $f0 if object is visible on scanline N, else $0. But the object's position changes per frame — ROM can't change.

**H) Pre-compute into a temporary buffer during VBLANK using unused TIA/RIOT space?**

No — there's no writable memory beyond ZP ($80-$FF) and stack ($0100-$01FF = same as ZP).

### ACTUAL SOLUTION: Reduce GRP0 section

The GRP0 section is 24c worst. The biggest cost is the `jmp .Put` (3c). Restructure to eliminate it:

```asm
; CURRENT (24c worst, 18c best):
  lda Scanline              ; 3
  sec                       ; 2
  sbc PlayerY               ; 3
  cmp #PLAYER_HEIGHT        ; 2
  bcs .NoSprite             ; 2³
  tay                       ; 2
  lda PlayerGrp0,Y          ; 4
  jmp .Put                  ; 3
.NoSprite:
  lda #0                    ; 2
.Put:
  sta GRP0                  ; 3

; OPTIMIZED (21c worst, 18c best):
  lda Scanline              ; 3
  sec                       ; 2
  sbc PlayerY               ; 3
  cmp #PLAYER_HEIGHT        ; 2
  bcs .NoSprite             ; 2³
  tay                       ; 2
  lda PlayerGrp0,Y          ; 4
  sta GRP0                  ; 3
  bne .SkipZero             ; 3   ← bit test: GRP0 data is never $00 for visible rows
.NoSprite:
  lda #0                    ; 2
  sta GRP0                  ; 3
.SkipZero:
```

Wait — the `bne` tests N flag from `lda PlayerGrp0,Y`. If sprite row is $00 (all black), bne is NOT taken and we fall through to `.NoSprite` which stores $0 again. Harmless but wastes3c.

If sprite row is NON-zero (common — player is yellow), bne IS taken and we skip .NoSprite. Saves3c on the jmp.

But `.NoSprite` path: `bcs` taken (3c) → `lda #0`(2) → `sta GRP0`(3) → falls through to `.SkipZero` which is after `.NoSprite`. We need `.SkipZero` AFTER the `.NoSprite` block.

Actually the structure is wrong. Let me restructure:

```asm
  lda Scanline              ; 3
  sec                       ; 2
  sbc PlayerY               ; 3
  cmp #PLAYER_HEIGHT        ; 2
  bcs .NoSprite             ; 2³ (taken = no sprite)
  tay                       ; 2
  lda PlayerGrp0,Y          ; 4
  sta GRP0                  ; 3
  jmp .AfterGRP0            ; 3  ← still needs jmp
.NoSprite:
  lda #0                    ; 2
  sta GRP0                  ; 3
.AfterGRP0:
```

This is the same as current. The jmp is unavoidable when the sprite IS visible because we must skip the `lda #0 / sta GRP0`.

**What if we reverse the logic — check "is scanline BELOW sprite" first:**

```asm
  lda Scanline              ; 3
  sec                       ; 2
  sbc PlayerY               ; 3
  cmp #PLAYER_HEIGHT        ; 2
  bcc .SpriteVisible        ; 2³  (taken when visible)
  ; Not visible — common path, no jmp needed
  lda #0                    ; 2
  sta GRP0                  ; 3
  jmp .AfterGRP0            ; 3
.SpriteVisible:
  tay                       ; 2
  lda PlayerGrp0,Y          ; 4
  sta GRP0                  ; 3
.AfterGRP0:
```

Best (not visible): 3+2+3+2+3+2+3+3 = 21c (was18c, WORSE by 3c)
Worst (visible): 3+2+3+2+2+2+4+3 = 21c (was24c, BETTER by 3c)

The common case gets 3c MORE expensive. Bad trade (184 scanlines × 3c = 552c extra per frame).

### ACTUAL ACTUAL SOLUTION: Accept GRP0 as-is, optimize GRP1 with bitfield using ROM

Use 24 bytes of ROM (in the data area) to store a pre-built bitfield for each possible object position. But the object position changes per frame, so this doesn't work with ROM.

### THE ONLY REAL FIX: Full kernel redesign using indirect indexed reading

Read GRP0 data from ROM via `(zp),Y` during the kernel. Pre-load font/object pointers into ZP during VBLANK.

**For GRP1:** The object data is already in ROM at a known address. In VBLANK, set a ZP pointer to the object's sprite data. In the kernel, read via `(Grp1Ptr),Y` where Y = scanline - ObjTop.

This saves the range check! Instead of checking if scanline is in range, we just read from the pointer. If the offset is out of range (Y > 7), we get garbage — but we still need the range check.

**The fundamental problem:** you ALWAYS need to check if the scanline is within the sprite's range. There's no way around it on the 6502 without pre-computing ALL 192 values.

### REVISED PLAN: Pre-compute GRP0 into stack during VBLANK

Wait — we established the stack page mirrors ZP. But what about using the ACTUAL stack ($0100-$01FF) during VBLANK only?

During VBLANK, before any JSR calls, the stack is at $FF (after CLEAN_START). We could push 192 bytes... but that would move SP from $FF to $FF-192 = $39. Then any JSR would push to $38, $37... which mirrors to ZP $38, $37 etc. Those ARE used by our variables! ($80-$FF is ZP, $38 is below $80... actually $38 is NOT in our ZP range $80-$FF).

Wait — on the 2600, the stack is at $0100-$01FF. This mirrors $00-$FF (the ENTIRE zero page + TIA + RIOT). So $0138 mirrors to $38 which is... NOT in our variable range ($80-$FF). But it IS in the TIA range ($00-$3F). Writing to $38 would write to TIA register $38 (which is an unused/undefined address).

Hmm, $38 = bit 3 set = mirrors to $18 (RESBL) or... actually the mirroring on 2600 is:
- $00-$3F: TIA (write) / $00-$0D: TIA (read)
- $80-$FF: RAM

Stack $0100-$01FF mirrors $00-$FF:
- $0100-$013F mirrors TIA ($00-$3F)
- $0180-$01FF mirrors RAM ($80-$FF)

So pushing to stack when SP=$39 would write to $0139 which mirrors to $39 — which is in the TIA range. Writing random bytes to TIA could cause visual glitches.

But we only need the stack during VBLANK (before kernel). During VBLANK, TIA writes are blanked (VBLANK=2). So writing to TIA addresses during VBLANK is harmless!

**THIS COULD WORK!**

1. During VBLANK, BEFORE any JSR calls, push 192 bytes of pre-computed GRP0 data onto the stack
2. SP moves from $FF to $FF-192 = $39
3. During kernel, pop bytes from stack to get pre-computed GRP0 values

But wait — the kernel runs AFTER VBLANK. During VBLANK, we do JSR calls (HudCopy in bank2 via trampoline). These push return addresses onto the stack, consuming the pre-computed data!

**Unless we do the push AFTER all VBLANK JSR calls.** The VBLANK flow:
1. Positioning (SetObjectXPos, SelectActiveObject) — uses JSR
2. VBLANK on
3. Pre-computation (PF buffers, sprite copy) — no JSR
4. JSR ToBank2 (HUD) — pushes return address
5. WSYNC waits
6. Kernel

If we push the 192 bytes AFTER step4 (after ToBank2 returns), the stack is clean. But then we need ~192 cycles to push, which takes ~2.5 scanlines. VBLANK has 37 scanlines total, minus 3 for VSYNC = 34. After positioning (~3), pre-comp (~8), ToBank2 (~58 scanlines??)...

Wait — ToBank2 is called AFTER the kernel, not during VBLANK. Let me re-check the code flow.

Looking at the code: `jsr ToBank2` is at line 542, AFTER the kernel loop. So during VBLANK, there are NO JSR calls to bank2. The JSR calls during VBLANK are only SetObjectXPos and SelectActiveObject (lines 279, 282). After those return, SP is back to $FF.

So the VBLANK pre-computation (lines 302-409) runs with SP=$FF. We could push 192 bytes AFTER the pre-computation and BEFORE the kernel. SP would go from $FF to $39.

But during the kernel, we need to READ from the stack. The kernel doesn't use JSR/RTS (it's a tight loop). So SP stays at $39 throughout the kernel. We can `pla` to read the pre-computed data.

Wait — `pla` reads from $0100+SP and decrements SP. If we push 192 bytes (SP goes $FF→$39), then `pla` reads from $0139 (first push was at $01FF, last at $0139). The stack is LIFO, so the first `pla` returns the LAST pushed byte.

We need to push in REVERSE ORDER (last scanline first) so that `pla` returns scanline0 first.

But there's a problem: during the kernel's `.Row` loop, X is the tile row counter. We need another register for the scanline. We could use Y for the scanline and `pla` for the GRP0 value.

Wait — the kernel currently uses:
- X = tile row (0-11)
- Y = sprite row index (0-7, clobbered in GRP0 section)
- A = various

If we pre-compute GRP0 on the stack, we can `pla` to get the value directly. No range check needed! Just `pla; sta GRP0`.

**New GRP0 section:** `pla; sta GRP0` = 2c + 3c = **5c** (was 24c worst, 18c best)

That saves **19c worst case!**

New total: GRP1(22) + GRP0(5) + ENAM0(17) + Loop(16) = **60c** ✓✓✓

### BUT: The stack page mirrors ZP

The stack at $0139-$01FF mirrors $39-$FF in ZP. Writing to the stack writes to ZP addresses $39-$FF. Specifically:
- $01FF mirrors $FF (in our range — but it's the LAST ZP byte, unused)
- $01FE mirrors $FE (unused)
- ...
- $01F8 mirrors $F8 (PlayerGrp0!)
- ...
- $0180 mirrors $80 (RoomX — used!)
- $0139 mirrors $39 (TIA range — harmless during VBLANK)

**CRITICAL:** Pushing to the stack when SP is in $80-$FF range CORRUPTS our ZP variables!

When SP=$FF, push writes to $01FF which mirrors $FF (safe — unused).
When SP=$FE, push writes to $01FE which mirrors $FE (safe — unused).
...
When SP=$F8, push writes to $01F8 which mirrors $F8 (PlayerGrp0! CORRUPTION!)
...
When SP=$80, push writes to $0180 which mirrors $80 (RoomX! CORRUPTION!)

So we can only safely push 8 bytes ($FF-$F8) before hitting PlayerGrp0. After that, every push corrupts our variables.

**This approach DOES NOT WORK.** The stack page mirroring makes it impossible to use as a buffer.

### ACTUAL FINAL PLAN

After exhaustive analysis, the kernel flicker requires a fundamental architectural change. The two viable approaches:

**Approach A: Split rendering into two kernel passes**
- Pass 1: Cave + object (GRP1) — no player sprite
- Pass 2: Player sprite (GRP0) overlay — no cave
- Each pass is simpler and fits within 76c
- Problem: total scanlines double (192×2 = 384), exceeding NTSC 262 limit

**Approach B: Pre-compute GRP0 into a 192-byte buffer using a separate memory region**
- The 2600 has NO separate memory. $80-$FF is ZP/RAM, $0100-$01FF mirrors it.
- There is literally no writable memory beyond 128 bytes.
- HERO uses `(zp),Y` to read from ROM — pre-computes font pointers in ZP, reads sprite rows from ROM via indirect indexed.

**Approach C: HERO-style — read GRP0 from ROM via `(zp),Y`**
- Store player sprite pointer in ZP (2 bytes)
- Each scanline: compute row offset, read from ROM via `(Grp0Ptr),Y`
- Still needs range check, BUT the read is from ROM (5c) instead of ZP (4c) — actually 1c MORE
- No savings

**THE ACTUAL FIX: Pre-compute GRP1 as a boolean, optimize ENAM0**

The GRP1 range check can be replaced with a simple boolean check: `ActiveObjectOn` tells us if the object is in the room. If yes, we STILL need the range check for which scanlines.

BUT: we can split the check into two parts:
1. Pre-compute `Grp1Prep` in VBLANK: $f0 if object active, $0 if not
2. In kernel: skip the range check when `ActiveObjectOn=0` (already done via `beq .NoObjPrep`)
3. When active: still need the range check (22c)

Net: only saves cycles when object is NOT active. When active, same cost.

**OK I'll implement what I can:**
1. Optimize the loop control (remove `inc Scanline`, use `iny` + sync) — saves ~2c per iteration
2. Restructure GRP0 to use `bne` instead of `jmp` — saves 0-3c per visible scanline
3. Test and measure

These small optimizations might get us to 76-77c, which is borderline. The flicker would be on 0-1 scanlines instead of 4.

For a complete fix, we'd need to redesign the kernel to use a fundamentally different rendering model. That's a larger project.
