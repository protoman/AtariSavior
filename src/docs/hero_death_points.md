# HERO Enemy Death Points / Particles — Investigation (2026-09-30)

**Q: How does HERO show points/particles at the position where an enemy died?**

**A: No floating "+N" popup sprite exists.** Points go to the HUD score only.
At the death position, HERO animates **the dying enemy in its own sprite
slot**: a per-slot countdown timer swaps the sprite pointer through a
4-phase animation and flashes the color, then the slot is removed and the
enemy count drops. Because the effect reuses the dead enemy's own hardware
slot, it cannot flicker and costs no extra object.

## Death timer machinery (verified — bank B `$F447–$F497`)

Per frame, loop `X = 2..0` over enemy slots:

```
F447 LDX #$02
F449 LDY $e7                     ; anim clock
F44B LDA $ff93,Y                 ; base sprite ptr-hi table
F44E STA $d8,X
F450 LDA #$68 / STA $db,X        ; aux value normal = $68
F454 LDA $de,X / BEQ $f48c       ; timer==0 → skip
F458 DEC $de,X                   ; <-- THE decrement (py65 write-PC ground truth)
F45A LDA $de,X / BNE $f466
F45E STA $fa                     ; timer→0: $FA = 0
F460 LDA #$93 / STA $a8,X        ; dead marker $A8,X = $93
F464 BNE $f48c
F466 CMP #$20 / BCS $f48c        ; timer >= 32: base frame
F46A CMP #$13 / BCS $f476        ; 19..31 → phase anim
F46E LDY $fa / BEQ $f476         ; $FA==0 → phase anim
F472 LDY #$04 / BNE $f47a        ; else force Y=4
F476 LSR A / AND #$03 / TAY      ; phase = (timer >> 1) & 3
F47A LDA $ff96,Y / STA $d8,X     ; SWAP sprite ptr-hi = animation frame
F47F LDA #$40 / STA $db,X        ; aux during anim = $40
F483 LDA $f2 / BNE $f48c         ; sound gate
F487 LDA $ffa5,Y / STA $e1       ; sound effect (Y-indexed)
F48C LDA $a8,X / CMP #$93 / BNE $f496
F492 LDA #$99 / STA $d8,X        ; final frame ptr-hi = $99
F496 DEX / BPL $f449
```

Table bytes (flat ROM, `$FFxx → ROM[0x1000 + $0xxx]`):

- `$FF93` base ptr-hi: `26 33 40 4d 58 65 8a 8b 7f 92 e5 cc b3 9a 81 81 9a b3 …`
- `$FF96` anim ptr-hi (Y=0..3): `4d 58 65 8a` (Y=4 → `8b`)
- `$FFA5` sound bytes (Y=0..): `00 00 00 0a 00 00 01`

Empirical render effect while timer ≠ 0 (slot 0 poked): **COLUP0 → `$30`**
on scanlines 157–164 (the poked slot's band) vs `$01`/`$1C` normally —
color flash in place, GRP shape unchanged in the sampled writes. Timer value
observed decrementing exactly 1/frame (write PC `$F458` every frame).

## Timer arming (bank A `$D8DF–$D910`)

`LDA #$40 / STA $de,X` (64-frame anim) fires only when ALL hold:

- `$AC ≠ 0` (state/laser flag), `$B2 ≠ 0` (enemies alive)
- `$A8,X == $93` (slot marked dead), `$DE,X == 0` (no timer running)
- `$84 == $D0`, `$9B & 3 == 0`, `$9B ≥ $0D`
- then stores `$9B` into `$A8,X` (marker replaced by position-ish value)

## Kill finalization + score (bank A `$D949–$D998`)

Runs every frame once gameplay is active:

- `LDA $de,X / CMP #$1F / BEQ $D956` — catches the timer passing `$1F` →
  `DEC $b2` (enemy count), then score windows:
  - slot X window vs `$A5,X` (±`$13`/`+ $23`) and `$F7,X==0`, slot≠2 →
    `LDA #$13 STA $f7,X` (hit lockout) + **`LDA #$50 / JSR $DBBA` (+50)**
  - hero-Y window vs `$A0` → `LDA #$00 STA $A0 / LDA #$75 STA $FA /
    JSR $DBBA` (**+75**, also stores `$FA=$75`)
  - hero/enemy box too close → nudge `$9B`, `JSR $DE6B` = hero death
    (`STX $AE / LDA #$FF / STA $AD`)
- other score sites: `$D89F` +50 (hit), `$D76B` +50 (enemies cleared),
  `$D752` +table (indexed `$F5`), `$D92B` +$10 pickup (`DEC $f2`)
- `$DBBA` = BCD score add; score displayed only as HUD digits

`$FA` writers: `$D996` (`$75` at kill), `$F45E` (0 at timer end), `$F64F`
(unknown context). Only read found: `$F46E` (anim phase gate) — **no
display path, so `$FA` is not a popup value.**

## State gating (required to reproduce anything)

- Frame 0: `$BA = $FF`; frame 5 (after reset press): `$AD = $FF`.
- `$BA ≠ 0` → `D72A → D774 → D9DF`: skips **all** gameplay logic
  (death path, enemy update, hit loop, kill block) every frame. py65 watch:
  `D949` executes 0 times in frames 0–60 while gated.
- Clearing `ram[$BA]=0, ram[$AD]=0` at frame 30: `D817`/`D889`/`D949` run
  every frame from then on. `$AD` counts down 1/frame (`D7FE`) from `$FF`.
- Hero then gets instantly re-killed (`$AD→FF` at f33 via `$DE6B` — enemy
  touch) unless armed: `ram[$F7..$F9] = $13` blocks the `$DE6B` call
  (`D8AA LDA $f7,X / BNE skip`). `$F8/$F9` are stack-page mirrors — probe
  only, do not copy.
- `$DE,X` poke test: value decays 1/frame; the `CMP #$1F` kill catch was NOT
  reproduced (arming gate `$AC ≠ 0` never satisfied — `INPT4` held 45 frames
  did not set `$AC`). Labeled open.

## Recipe for our game

1. On kill: keep the enemy in its OWN slot; start `Timer = 40` on it.
2. Each frame: `Timer--`; while `Timer ≥ 32` base frame; `19–31` phase =
   `(Timer>>1) & 3` → swap sprite pointer (4 small "spark" frames); flash
   color (observed `$30`); aux `$DB = $40` instead of `$68`.
3. At 0: final frame ptr, then remove slot (`enemy count--`), add BCD score
   (HUD only).
4. No popup object, no per-frame rotation — the dying enemy itself is the
   "points" visual. Fits the flicker rules in `hero_flicker.md`.

## References

- Disassembly: `/tmp/opencode/hero_bankA_flow.asm` (bank A), py65
  `Disassembler` sweeps over `hero.bin` (flat 8K, `$D000=ROM[0:4096]`,
  `$F000=ROM[4096:8192]`).
- Scripts: `/tmp/opencode/death_poke.py` (render diff), `kill_watch.py`
  (PC/branch watch), `gate_probe.py` (state gating), `live_check.py`
  (gate-cleared gameplay run).
- Screenshot: `screenshots/HERO.png`.
