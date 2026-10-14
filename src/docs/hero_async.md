# HERO Async-Block Investigation (2026-10-05)

**Q: HERO ships the same "async painted block" feature we do (M1/whole-cave
strip) WITHOUT our bug — the enemy's color never sticks to the block. HOW?**

Rule for this file: **only HERO ROM + disassembly count.** Every claim must
carry a ROM address or an instruction sequence quoted from the dump. No
recycled assumptions from earlier sessions — re-verify everything.

---

## 0. Source

- ROM: `src/hero/hero.bin` (8192 bytes, verified this session).
- Layout (verified from the image itself): flat 8K, no bankswitch observed.
  - `rom[0:4096]` = code at `$D000-$DFFF` ("kernel half", bank A)
  - `rom[4096:8192]` = code at `$F000-$FFFF` ("logic half", bank B)
  - tail bytes `... 00 f0 00 f0` → **RESET vector ($FFFC) = $F000**
- Linear disassembly done with py65's `Disassembler` over `rom[0:4096]`
  starting at `$D100` (reproduce: MPU over slice A, `instruction_at` loop).

## 1. TIA write scan (raw opcodes, this session)

Pattern `85 nn` = `STA zp`, `8d nn nn` = `STA abs`. Scanned both halves:

### Bank A ($D000 slice)

| Write | Addresses |
|---|---|
| `STA $07` (COLUP1) | `$D172 $D19A $D1C5 $D211 $D248 $D278 $D29A $D2C8 $D39C $D470 $D479 $DC10` |
| `STA $0007` (COLUP1, abs) | `$D1ED` |
| `STA $08` (COLUPF) | `$D137 $D35C $D4B6 $D4DF $D4F9` |
| `STA $1C` (GRP1) | `$D17A $D1AA $D1D7 $D21A $D251 $D25D $D283 $D28C $D2A8 $D2D6 $D3E2 $D4E4 $D4F1 $D4F5 $D512 $DC08 $DE41 $DE4D $DE66` |
| `STA $001C` (GRP1, abs) | `$D16D $D1FE $D25A` |
| `STA $1E` (ENAM1) | `$D1CB $D1D1 $D1F2 $D1F8 $D213 $D24F $D256 $D281 $D288 $D29C $D2A2 $D2CA $D2D0` |
| `STA $05` (NUSIZ1) | `$D42B $D4C6 $DE24` |
| `STA $1B` (GRP0) | `$D23C $D2E7 $D2FA $D3DD $D3EB $D4DA $D4E9 $D510 $D514 $DC06 $DC0A $DE3D $DE47 $DE64 $DE68` |
| `STA $0D` (CTRLPF) | `$D13C $D360 $D3F4 $DC1A` |

### Bank B ($F000 slice)

- Only `STA $05` (NUSIZ1) at `$F306`.
- **Zero COLUP1 / COLUPF / GRP1 / ENAM1 writes in bank B.** All color and
  object drawing happens in bank A.

### First-order observations (before deeper reading)

1. **COLUP1 is written 13 times in bank A**, clustered around the same
   region as the GRP1/ENAM1 writes (`$D16D-$D2D0`) — i.e. inside the
   per-line drawing code, NOT once per band. Our kernel writes COLUP1 once
   per band (.Row) + once per object line — HERO appears to write it
   repeatedly inside the line code.
2. ENAM1 has 13 write sites, all in `$D1CB-$D2D0` — the same line region —
   **conditional writes, not a single VBL latch** (see disasm below). Our
   kernel comment "ENAM1 latched #$02 for the whole cave (hero-style)" is
   therefore SUSPECT — verify, do not trust.
3. `$DC10` COLUP1 + `$DC08` GRP1 + `$DC06/$DC0A` GRP0 + `$DC1A` CTRLPF =
   a second cluster at `$DC00-$DC1A` — matches a `JSR $DC00`-style HUD
   renderer entry (per-line HUD writes).

## 2. Disassembly `$D100-$D1F0` (kernel entry → line code), quoted

```
$D100: STA $02          ; WSYNC
$D102: STA $2a          ; HMOVE
$D104: BIT $b4 / BPL $d10a / LDA #$02
$D10A: STA $01          ; VBLANK reg write
$D10C: LDX #$02 / STX $e6      ; $e6 = 2 (band/row countdown?)
$D110: DEX                    ; X=1
$D111: LDA $9b / STA $2b      ; HMP1 <- $9B (P1/M1 fine motion)
$D115: JSR $d00c              ; position routine, selector X=1 -> RESP1/HMM1
$D118: LDX #$04 / LDA $a0 / JSR $d00c   ; selector 4 -> RESPBL (ball), X=$A0 value
$D11F: STA $02 / STA $2a       ; WSYNC + single HMOVE (both objects)
$D123: LDA $e1 / STA $09       ; COLUBK = $E1
$D127: LDA #$ff / STA $bd
$D12B: DEX                     ; X=3
$D12C: LDA $dd09,X / ORA $a4 / STA $2b   ; HMP1 per row
$D133: STA $02 / STA $2a        ; WSYNC + HMOVE
$D137: STA $08                  ; COLUPF <- A  (A = $DD09,X | $a4 — CHECK)
$D139: LDA $dc66,X / STA $0d    ; PF1  <- table[row]
$D13E: LDA $dc61,X / AND $c1 / STA $0e   ; PF0  <- same source, mask $C1
$D145: LDA $dc61,X / AND $c4 / STA $0f   ; PF2  <- same source, mask $C4
$D14C: DEX / BPL $d12c          ; row loop: X = 3,2,1,0 → 4 iterations
$D14F: STX $1f / INX / STX $04  ; $04 = 1 (X wrapped -1 → 0 → 1)
$D154: LDA #$61 / STA $25       ; $25 = $61
$D158: LDA $b0 / STA $0c        ; $0C <- $B0
$D15C: LDY #$74 / LDA ($95),Y   ; indirect fetch (Y=$74)
$D160: LDX $c7 / NOP / STA $2c / NOP / STX $08 / STA $2a
$D16A: JMP $d172                ; into the line code
$D16D: STA $001C                ; GRP1 (abs)   [branch target]
$D170: BEQ $d1ac
$D172: STA $07                  ; COLUP1 <- A  (!!! color write inside line code)
$D174: AND #$01 / BEQ $d0f8     ; bit0 of the SAME A branches backward to $D0F8
$D176: LDA ($91),Y / STA $1c    ; GRP1 fetch+draw (Y = sprite row index)
$D17C: LDX $e6 / LDA $a1,X / STA $bc
$D182: LDA $05 / ORA $f4 / STA $f4   ; NUSIZ1-read? ($05 read = CXM1P!) accumulate into $F4
$D188: LDA $ce,X / STA $97
$D18C: LDA $cb,X / STA $93
$D190: DEY
$D191: LDA $bf,X / TAX
$D194: LDA ($95),Y / STX $0e / LDX $bd
$D19A: STA $07                  ; COLUP1 (2nd write)
$D19C: STA $2a                  ; HMOVE
$D19E: STX $0d                  ; PF1 <- X ($bd value)
$D1A0: LDX $03 / STX $2c
$D1A4: AND #$01 / BEQ $d16d     ; bit0 → backward branch $D16D (GRP1 abs!)
$D1A8: LDA ($91),Y / STA $1c    ; GRP1 draw
$D1AC: STX $bb / LDX $e6
$D1B0: LDA $c2,X / STA $0f      ; PF2
$D1B4: LDA $c8,X / STA $0a      ; COLUP0 ← table[e6]!!
$D1B8: LDA $bb / STA $e3,X
$D1BC: DEY / LDA $c5,X / TAX
$D1C0: LDA ($95),Y ×2 / NOP
$D1C5: STA $07                  ; COLUP1 (3rd)
$D1C7: STA $2a                  ; HMOVE
$D1C9: STX $08                  ; COLUPF ← X (!!)
$D1CB: STA $1e                  ; ENAM1 ← A
$D1CD: AND #$01 / BNE $d1d5 / STA $1e / BEQ $d1d7
$D1D5: LDA ($91),Y / STA $1c    ; GRP1 draw
$D1D9: DEY / LDX $e6 / LDA $d1,X / STA $bb
$D1E0: AND #$0f / TAX
$D1E3: LDA ($95),Y / JSR $d029 / JSR $d029
$D1EB: DEC $e6                  ; band countdown!
$D1ED: STA $0007                ; COLUP1 (abs) ← A
$D1F0: STA $2a
```

### Observations from the dump (working, re-check as needed)

- **`$e6` counts bands**: init 2 (`LDX #$02 / STX $e6`), `DEC $e6` at
  `$D1EB` → the code runs a 3-band pass (0,1,2). "4 row iterations" in the
  PF loop at `$D12C` (X=3..0) is a SEPARATE loop (4 PF rows? check: X
  enters 3 after DEX from 4 — but the $D12C loop feeds PF0/1/2 + COLUPF =
  PF row setup; 4 iterations vs 3 color bands — investigate).
- **Two positional handoffs per frame** in bank A at $D115/$D11C:
  selector X=1 (RESP1/HMM1 = P1/M1) with `$9B`, selector X=4 (RESPBL =
  ball) with `$A0`. Same structure as our `PositionBallM1`.
- The line code contains **multiple `STA $07` interleaved with
  `STA $1C` (GRP1) and `STA $1E` (ENAM1)** — i.e. HERO re-writes COLUP1
  *inside* the line code right before/after sprite draws. Each write's A is
  also tested (`AND #$01` → backward branches `$D0F8`/`$D16D`) — the color
  byte doubles as a flag/selector.
- `STA COLUPF` inside the line code too (`$D1C9: STX $08` — with X, not A!)
  — mid-line PF changes in the line code (consistent with HERO's known
  double-PF-write-per-scanline trick — but VERIFY that separately; do not
  assume).
- COLUP1 at `$D1ED` (abs) right after `DEC $e6` = likely the per-band latch
  at band end. The value source = A from `LDA ($95),Y` chain — indirect
  table reads, not a RAM color buffer.

## 2b. Subroutines + line-code structure (session, second pass)

### `$D00C` = positional divider (the Davie RESP routine)
```
$D00C: CMP #$00 / BNE $d012 / LDA #$01   ; X==0 → X=1 (guard)
$D012: SEC / STA $02 (WSYNC)
$D017: SBC #$0f / BCS $d1017 / EOR #$0f
$D01D: ASL A ×4 / ADC #$80 / STA $10,X    ; RESP0+X ($10,X: X=0..4 → RESP0..RESPBL)
$D025: STA $02 (WSYNC) / STA $20,X        ; HMP0+X
```
Frame positioning (once, before the row loop):
- `$D115: JSR $d00c` with **X=1 → RESP1/HMM1** (P1/M1 fine position, motion byte from `$9B`)
- `$D11C: JSR $d00c` with **X=4 → RESPBL** (ball, position = `$A0`)
- single HMOVE after both: `$D11F: STA $02 / STA $2a`
Same "one VBL call, both objects" shape as our `PositionBallM1`.

### `$D029` = RTS
The `JSR $d029 / JSR $d029` pair at `$D1E5/$D1E8` is pure **delay** before
the `$D1ED` `STA $0007` (COLUP1) band-end write — cycle-count padding.

### Line code `$D16D-$D29E` (one scanline iteration, branches skip stages)

Quoted skeleton (bytes verified via linear disasm):
```
$D16D: STA $001C            ; GRP1 abs
$D170: BEQ $d1ac
$D172: STA $07              ; COLUP1 ← A          [color write #1]
$D174: AND #$01 / BEQ $d0f8 ; bit0 of A = flag → $D0F8: JMP $D17A (blank path)
$D178: LDA ($91),Y / STA $1c ; GRP1 draw (graphics byte)
$D17C: LDX $e6 / LDA $a1,X / STA $bc
$D182: LDA $05 / ORA $f4 / STA $f4    ; $05 read = CXM1P collision accumulate
$D188/$D18C: LDA $ce,X→$97 / LDA $cb,X→$93   ; per-band pointer swaps
$D190: DEY                  ; Y-- (scanline counter, see below)
$D194: LDA ($95),Y / STX $0e / LDX $bd
$D19A: STA $07              ; COLUP1  [write #2]   + $19C STA $2a (HMOVE)
$D19E: STX $0d              ; PF1 ← X (mid-line PF write)
$D1A4: AND #$01 / BEQ $d16d ; flag → GRP1-abs path
$D1A8: LDA ($91),Y / STA $1c ; GRP1 draw
$D1B0: LDA $c2,X / STA $0f   ; PF2  ← table[e6]
$D1B4: LDA $c8,X / STA $0a   ; COLUP0 ← table[$e6]   (band color for P0!)
$D1BC: DEY / LDA $c5,X / TAX
$D1C5: STA $07              ; COLUP1  [write #3]  + $1C7 HMOVE + $C9 COLUPF←X
$D1CB: STA $1e              ; ENAM1 ← A
$D1CD: AND #$01 / BNE / STA $1e / BEQ ; ENAM1 gate dance
$D1D5: LDA ($91),Y / STA $1c ; GRP1 draw
$D1E0: AND #$0f / TAX
$D1E3: LDA ($95),Y / JSR $d029 ×2 (delay)
$D1EB: DEC $e6              ; band countdown ($e6: 2→…)
$D1ED: STA $0007            ; COLUP1  [write #4, abs] + $D1F0 HMOVE
$D1F2: STA $1e              ; ENAM1
$D1F4: AND #$01 / BNE …     ; flag gate → $D1FC draw / $D1FE blank
$D20B: STA $02              ; WSYNC  ← scanline boundary #1
$D20D: STA $2a              ; HMOVE
$D20F: LDA ($95),Y / $D211 STA $07 [write #5] / $D213 STA $1e
$D215: LSR A / BCC $d234    ; flag in carry
$D218: LDA ($91),Y / STA $1c ; GRP1 draw
$D21D: LDX #$12 / STA $2b    ; HMP1 ← $12
$D221: DEY / STY $bb / TXA / SEC / SBC $bc / TAY / CMP #$0d / BCC $d23a
$D234: STX $1e / STX $1c     ; blank ENAM1+GRP1 (X=0)
$D23A: LDA ($93),Y / STA $1b ; GRP0 draw (player!)
$D23E: LDA ($97),Y / LDY $bb / STA $06 ; COLUP0 ← per-scanline table ($97)
$D244: LDA ($95),Y / STA $2a / STA $07 [write #6]
$D24A: LSR A / BCS $d255 / (blank ENAM1+GRP1) / $D255: ASL A / STA $1e
$D258: LDA ($91),Y / STA $001c / STA $1c ; GRP1 draw
$D25F: DEX / BPL $d221      ; INNER LOOP (DEX) → back to $d221!
$D262: DEY
$D263: LDA $07 / LDX $e6 / STA $d2,X   ; ← saves current COLUP1 into $D2+band (RAM!)
$D269: LDA $d9,X / STA $99 ; LDA $dc,X / STA $97 ; LDA $d5,X / AND #$0f / TAX
$D276: LDA ($95),Y / STA $07 [write #7] / LSR / STA $2a / BCS → ENAM1 via ASL
$D28C: STA $1c ; DEY / DEX / BNE $d28f   ; second INNER LOOP
$D292: STA $10               ; RESP0 mid-frame! (X=0 path)
$D294: LDA ($95),Y
$D296: STA $02               ; WSYNC  ← scanline boundary #2
$D298: STA $2a / STA $07 [write #8] / STA $1e / AND #$01 …
```

### Working conclusions (VERIFY as marked)

- **Y = per-scanline countdown**, initialized `$D15C: LDY #$74` (116),
  decremented by `DEY` through the chain — NOT a sprite-row index.
  **CONFIRMED (2026-10-05, §5b):** per-group Y-at-close = 70,5B,49,34,
  22,0D; the Y drop EQUALS each WSYNC segment's scanline span (21,18,
  21,18,21) → Y decrements once per scanline inside a segment, WSYNC
  only at segment ends. The earlier "only ~18-21 cave WSYNCs/frame"
  caution counted SEGMENTS, not scanlines — retract REFUTED-PENDING.
  So `($95),Y` = **a per-scanline control table**:
  one byte per scanline driving COLUP1 + HMOVE + ENAM1 + GRP1 gate (bit0),
  `($91),Y` = per-scanline GRP1 graphics, `($93),Y` = GRP0 (player),
  `($97),Y` = COLUP0 (player color), all indexed by the same scanline Y.
- **COLUP1 is rewritten inside every scanline iteration** (writes #1..#8
  are branch-skipped stages — each executed path passes ≥1 `STA $07`
  before WSYNC). A color from scanline N cannot stick to N+1: the next
  line rewrites it from `($95),Y`. ⇒ *this is the candidate answer to
  "HOW HERO avoids the sticky bug"* — **confirmed by trace (§5: 528/528
  groups; §5b: 1:1 one write per scanline inside every segment)**.
- `$D263: LDA $07 / STA $d2,X` = save current COLUP1 to a band-indexed
  RAM slot ($D2+band) — purpose unknown (restore? HUD? collision?).
- `$D1ED` band-end `STA $0007` after two `JSR $d029`(=RTS delay) — A = last
  `($95),Y` byte. Purpose unknown.
- ENAM1 = `STA $1e` with values derived from the SAME table byte (raw at
  `$D213`; `ASL A`-cleared-bit0 at `$D255/$D287`; plus the `$D1CD` dance) —
  **not a one-shot VBL latch** ⇒ our kernel comment "ENAM1 latched for the
  whole cave (hero-style)" is NOT what this code does. Flag for correction
  in our kernel comments later (do not edit yet).
- `STA $91/$95/$96/$92` all in `$D43D-$D458` (VBL/level setup region) —
  next: disassemble to get the table base addresses and verify entries.

## 2c. Tables + loop topology (session, third pass) — MAJOR

### Pointer setup (from `$D430` disasm; $D430 first byte misaligned — dump
started mid-instruction, rest verified)

```
$D433: LDA #$34 / STA $0a        ; CTRLPF = $34 (HUD mode: reflect OFF)
$D43B: LDA #$dd / STA $92 / STA $96   ; hi bytes: BOTH pointers in $DDxx/$Dxxx
$D441: LDA #$a9 / STA $91             ; ptr A = $91/$92 = $DDA9
$D445: LDA #$b7 / STA $95             ; ptr B = $95/$96 = $DDB7
$D449: STA $2b / JSR $dc00            ; call HUD renderer with ptr A/B as args
$D44E: LDA #$34 / STA $91             ; after HUD: ptr A := $DA34
$D452: LDA #$69 / STA $95             ; ptr B := $DD69
$D456: LDA #$da / STA $92             ; (hi of A = $DA; hi of B still $DD)
```
⇒ **cave-time pointers: `($91) = $DA34`, `($95) = $DD69`.** Both tables
are 117 bytes (Y counts `$74`=116 → 0) and END CLEAR OF CODE:
`$DA34+117 = $DAAB`, `$DD69+117 = $DDDD` (code `$DC00+`) ✓.

### CTL table `$DD69` (= `($95)` → COLUP1 + HMOVE + ENAM1 + GRP1 gate)

Dumped 117 bytes (this session, `rom[0xD69:0xD69+0x75]`):

- Values are NTSC colors: `$44 $1C $0D $99 $45 $47 $1D $1E $1C $AA $34 $0C …`
  (distinct set recorded in-session: 0x0,0x1,0x4,0x6,0x8,0xc,0xd,0x10,0x14,
  0x18,0x1c,0x1d,0x1e,0x20,0x28,0x2c,0x34,0x44,0x45,0x46,0x47,0x70,0x94,
  0x99,0xaa).
- **bit0 = object-draw flag** (per disasm `AND #$01 / BEQ/BNE`): set on
  exactly 26 entries forming ONE contiguous Y-run **Y=105..79** (the
  object window / painted-block region at the cave top). Odd colors there
  ($45,$47,$01) = flag baked INTO the color byte.
- The other lines carry even colors only → flag clear (no draw, and the
  ENAM1 `ASL` path derives enable from the same odd/even bit).

### GFX table `$DA34` (= `($91)` → GRP1 graphics byte per scanline)

Dumped: `$1c $1c … $08 $08 $0c $18 $08 $00 …` — sprite bitmaps (00=blank),
per-scanline indexed by the same Y — GRP1 is REWRITTEN every scanline to
build an object taller than 8 pixels.

### Loop topology (line code)

```
$D15C: LDY #$74               ; Y = 116 = per-SCANLINE countdown
 entry $D172 (also from back-edge $D309: JMP $d172)
$D172: STA $07                ; ★ COLUP1 ← A  (A = ($95),Y color byte)
$D174: AND #$01 / BEQ $d0f8   ; flag dispatch ($D0F8: JMP $d17a)
 …stages (see §2b): more STA $07 ($D19A/$D1C5/$D211/$D248/$D278/$D2C8),
    STA $1e/ENAM1, STA $1c/GRP1 draws, PF stores ($19E STX $0d etc),
    COLUP0 ← ($97),Y ($D23E), HMOVE from the same byte ($D246/$D2C6…)
$D2D9: DEY / BMI $d30c        ; Y-- ; Y<0 → EXIT to band/room tail
 …reload block: $D2FC LDY $bb / LDX $a4 / LDA ($95),Y
$D302: STX $1e / STX $0008    ; ENAM1 + COLUPF ← X  (verify: X=$a4 value)
$D307: STA $2a                ; HMOVE ← color byte
$D309: JMP $d172              ; ★ LOOP BACK — re-enters AT the COLUP1 write
WSYNC sites inside the loop: $D20B, $D296 (path-dependent)
$D30C: (Y<0 exit) band/room tail: $D351 LDA $dd0a,Y / ORA $a4 /
       STX $1b / $D358 WSYNC / $D35C STA $08 (COLUPF) …
```

### ★ Structural answer to the main question (verified from bytes)

**Every scanline iteration re-enters at `$D172 STA $07` — an UNCONDITIONAL
COLUP1 write from the per-scanline table byte — before any flag branch.**
Consequences:

1. A color written on scanline N (e.g. enemy color) can never be visible
   on scanline N+1: the very first instruction of the next iteration
   overwrites COLUP1 with that line's table value, landing in HBLANK/early
   line (before the strip's pixels).
2. There is no "sticky enemy color below the window" state at all — the
   per-scanline table precomputes, for EVERY line, what the color must be
   (strip/band color on non-object lines, object color on the object's
   Y=105..79 lines).
3. ENAM1 enable = derived per line from the same byte (odd→`ASL`→bit1) —
   NOT a whole-cave latch. Our kernel comment `ENAM1 latched #$02 for the
   whole cave (hero-style…)` misdescribes this code (flag for our comment
   fix later).
4. GRP1 tall-object trick = per-scanline rewrite from `$DA34` table
   (same Y) — GRP1 also never relies on persistence.

### Other STA sites accounted for

- `$D39C STA $07` — level-load region (preceded by `AND $86 / ORA $86`,
  `$D3A4 LDA $ab / LSR×3 / TAX / LDA $dc6b,X` = per-level table index) —
  NOT the line loop. (First bytes of the $D390 dump were mid-instruction.)
- `$D470/$D479 STA $07` — title/blink: `LDA $85 / CPX #$60 … LDA #$1c /
  STA $07 / STA $06 / JSR $de00 / LDA #$0c / STA $07` — counter-gated
  $1C↔$0C color for HUD/title text (COLUP0+COLUP1 same value).
- `$DC10` — inside the `JSR $DC00` HUD renderer (writes $91/$95 ptrs
  before the call ⇒ HUD text uses ptr A=$DDA9/$DDB7).
- Bank B: no color writes at all.
- `STA $9B` (M1/P1 fine-motion source): **ZERO hits in bank A** ⇒ written
  from bank B (the $F000 logic half) — pending verify (next pass).

## 2d. `$9B` = a horizontal PATROL (bank B, this session)

`$9B` is never written in bank A. Bank B disasm:

```
$F144: LDA $bb / CLC / ADC #$04 / STA $9b   ; pos = $bb + 4
$F240: LDA $9b / LDX $b0 / BEQ $f253
$F246: SEC / SBC #$01 / STA $9b            ; step LEFT
$F24B: CMP #$0c / BCS $f282                ; clamp floor $0C
$F253: CLC / ADC #$01 / STA $9b            ; step RIGHT
$F258: CMP #$93 / BCC $f282                ; clamp ceiling $93
$F25C: LDX #$01 / … edge handling: JSR $f630 / LDA $f900,Y / AND #$01 /
      CMP $ffaa,X … INC/DEC $9c / LDA $ffac,X / STA $9b (reset pos)
$F15D: BIT $07 / BPL …  ($07 READ = CXPPMM collision feedback)
```
⇒ `$9B` = **bouncing horizontal position between `$0C` and `$93`**
(direction byte `$b0`, divider `$fc`), i.e. HERO's object MOVES left/right
every frame — a patrol. The cave-side consumer: `$D111 LDA $9b / STA $2b`
(HMP1 fine motion) + `$D115 JSR $d00c` with A=$9B (RESP1 coarse) — P1/M1
positioned from `$9B` ONCE per frame, same as our PositionBallM1's single
VBL call.

So the cave object = **moving (X-bouncing) tall GRP1 sprite + (possibly)
M1 at the same X**, fixed Y window, STATIC per-line colors/graphics from
tables. No dynamic per-frame color computation exists in the line loop.

Supporting tables/subs decoded (bank B, this session):

- `$FFAA = 00 01` — edge-compare values for `CMP $ffaa,X` (X=0/1 dir).
- `$FFAC = 93 0f` — patrol reset positions: dir0 → `$93` (right edge),
  dir1 → `$0F` (near left floor `$0C`).
- `$F630`: `LDY $f5 / LDA $ff00,Y / CLC / ADC $9c / TAY / RTS` — Y =
  `$FF00[$F5] + $9C` (state+counter → table index). Caller `$F261` then
  does `LDA $f900,Y / AND #$01 / CMP $ffaa,X` = per-state flag vs edge.
- `$F900` (32B): state bytes (`90 90 … 50 68 14 24 18 51 91 80 4c …`) —
  motion/flag data, bit0 varies (`$51/$91` odd).
- `$F63A`: `LDX #$02 … LDA $f7,X / BEQ / LDA #$32 / STA $a1,X / LDA #$00 /
  STA $f7,X` … `STA $b1 / STA $fa` = clears 3 slot states + `$B1/$FA`
  (reset/death cleanup).
- Object identity still OPEN: tall sprite bitmap (`$DA34` window bytes
  `00 00 1c×6 08 08 0c 04 10 00 … 18 3c 3c 18 3c 3c 18 00 …` = rung-like
  pattern) + horizontal patrol — name it only after a runtime trace or
  further cross-refs (do NOT guess).
- **Runtime census note (2026-10-05, §5b):** in 119 observed frames
  `$9B` is written ONLY at boot/level-load — `LF021: LDX #$18 / LDA
  LFF72,X / STA $9B,X / DEX / BPL` fills a 25-byte RAM table `$9B-$B3`
  from ROM `$FF72` (init, not patrol). The patrol code above exists but
  never runs in the traced state (zero steady-frame `$9B` writes) —
  patrol activation is tied to the OPEN gameplay-start question.

## 3. Open questions → resolved / open

- [x] **Where does the strip/band COLUP1 color come from?** The
      per-scanline CTL table `$DD69` (loaded into `$95/$96` at cave setup
      `$D454`), byte per scanline, re-written at loop entry `$D172`.
      Plus band-end write `$D1ED` (after 2× `JSR $d029` = RTS delays) and
      level-load writes `$D39C`. NOT a RAM color buffer — hero has no
      ColupfBuf equivalent; the table IS the precomputed state.
- [x] **Does GRP1 draw in the cave?** YES — tall object built by
      per-scanline GRP1 rewrites from table `$DA34`, window Y=105..79
      (26 lines), driven by flag bit0 of the CTL byte. What the object
      *is* (identity) still open — see below ($9B patrol).
- [x] **ENAM1 cadence**: NOT a whole-cave latch. ENAM1 written per line
      inside the loop (`$D1CB/$D213/$D2CA/$D2F2…`), value derived from the
      same CTL byte (flag lines: `ASL A` → odd→even sets enable bit;
      blank paths force 0). Our kernel comment "hero-style whole-cave
      latch" is WRONG about hero — flagged for later correction.
- [x] **`$D0F8`/`$D16D` branches**: bit0 flag dispatch — `$D0F8: JMP
      $D17A` (blank GRP1 path), `$D16D` = GRP1-abs blank+skip entry. Part
      of the unrolled stage machine; all spot-checked paths still hit a
      `STA $07` before their WSYNC.
- [x] **Line-loop backbone**: entry `$D172`, back-edge `$D309 JMP $d172`
      (re-enters AT the COLUP1 write), Y countdown `$D2D9 DEY / BMI
      $d30c` exit, WSYNC sites `$D20B` + `$D296` (path-dependent).
- [x] **Clock-phase of COLUP1 writes** — measured (§5/§5b): first write
      at wall%76 = c3 (440×) or c6 (88×) = HBLANK, exactly one per
      scanline inside every segment; late companion writes at c70-c73
      observed (double-write asym). Enough data even if we never adopt
      a mid-line strategy.
- [ ] **`$9B` object identity**: code side decoded — bank B patrol
      (`$F144/$F240/$F249/$F256/$F27D`, clamps `$0C..$93`) + boot fill
      `LF021` (25-byte table `$9B-$B3` from `$FF72`); RUNTIME side open:
      patrol never executes in traced frames (§5b) — needs a state where
      gameplay runs, same blocker as gameplay-start.
- [ ] **Gameplay-start**: input path runs every frame (`LF042 LDY
      SWCHA`, `$84=$70` stored on held-right, verified 37 frames) but
      RESP0/HMP0 write offsets never change across 49 frames despite
      fire pulse + held right → movement gated by an unreached state.
      Candidates: attract/title flow needing a different start sequence,
      or a harness fidelity gap (read-hotspot bank switching not
      modeled, §5b). §5's COLUP1 conclusion is NOT affected (the cave
      kernel renders identically in any state).
  **PARKED (2026-10-05, user agreement):** gameplay-start, `$9B`
  runtime patrol, and `$AD` semantics are OUT OF SCOPE for the async-PF
  work — player movement / enemy position never touch the color path
  (colors come from the static table, bit0 flag). Recorded here for
  completeness; do not resume unless async-PF work needs them.
- [ ] **Bank B pointer re-set** at `$F58E/$F595` (STA $91/$95) — second
      home of the table pointers (title/level state?).

## 4. Why HERO doesn't hit OUR sticky-color bug + fix candidates

Our bug (measured): `.Row` writes COLUP1 = band color once per band; the
object path (`lda ObjColorTab,X / sta COLUP1`, DYNAMIC enemy color) then
overwrites it; nothing restores → M1 bar keeps the enemy color from the
object window to the band end. Restoring in `.ObjZero` costs +10c and
pushes the fixed-time `.Line` over the scanline budget (`sim_frame_budget`
wall-model 264 vs 263 — the +1 line is isolated to that line, measured).

HERO comparison (all verified above):

| | HERO | our kernel |
|---|---|---|
| color source | static per-scanline table `$DD69` (load-time) | `ColupfBuf` RAM + DYNAMIC `ObjColorTab,X` at runtime |
| COLUP1 write cadence | **every scanline**, loop entry `$D172` (unconditional; back-edge `$D309`) | per band (.Row) + per object line (object path) |
| dynamic color | none — colors pre-baked per line, flag in bit0 | enemy color computed live → can poison the register |
| persistence relied on | never — next line always rewrites | yes (band writes only at setup) |
| GRP1 tall object | per-scanline rewrite, fixed Y window | 8-line window, dynamic colors |
| ENAM1 | per-line value from same table byte (flag-derived) | VBL latch + per-band gates (our comment wrongly says "hero-style latch") |
| per-line cost of color writes | ~8c (`LDA ($95),Y` 5c + `STA $07` 3c) PLUS `($97),Y`→COLUP0 — budgeted into their unrolled loop | we cannot afford +7c at loop entry (measured) |

Root difference: **HERO precomputes; we compute at runtime.** HERO also
has no laser BeamMask gate (+8c/line in our budget), no ColupfBuf RAM
indirections — their per-line bill fits, ours is at the edge.

### Fix candidates for OUR kernel (ranked)

1. **Free cycles in `.Line` to afford the restore** — candidates: the
   laser BeamMask block (`lda BeamMask,Y` 5c cross + `and` + `sta` = 11c)
   is OUR addition hero lacks: pre-mask when `LaserBeamOn` is off (VBL
   table flip?) or gate per-frame → potential −4..−8c → fund `.ObjZero`
   restore (+10) or a loop-entry restore (+7). Needs measurement; sim is
   the gate.
2. **Drop the dynamic enemy color write** (hero-style static tables) —
   precompute object color per line → no runtime `sta COLUP1` on the
   object path at all; but then .Row's band write = only writer ✓ bug
   disappears structurally. Cost: precomputed color tables per enemy
   type × lines (ROM + VBL staging) — a bigger refactor.
3. **Restore only after the window** (flag detect A==8 first-out): +4c on
   plain obj-out lines, +15 once per window end — measured earlier as
   risky (plain lines already near limit).
4. **Ship bug 1 (hot death) alone**, park bug 2 (color) — restore is the
   only failing piece for the sim gate.

## 5. Empirical verification — py65 line trace (2026-10-05, FINAL)

Harness `/tmp/opencode/hero_line_trace.py`: flat-8K py65 model, WSYNC
aligns virtual clock to 76, TIM64T/INTIM emulated, SWCHB neutral (RESET
pulsed $F7 on the first read — WRONG BIT, see the §5b correction: RESET
= D0, pressed value $FE; $F7 was harmless because power-up boot runs
the full init anyway). Cave line = WSYNC-to-WSYNC group at the
line-loop sync pcs `$D20B`/`$D296` (valid: cave display lines are
WSYNC-delimited; the un-WSYNCed INTIM spins live only in VBL/timer code
and were excluded). NOTE: one harness "group" = one hero SEGMENT of
18-21 scanlines, not one scanline (§5b); the per-scanline claim was
re-measured 1:1 there.

**Result over a full run (8000 lines ≈ 88 frames):**

| Check | Result |
|---|---|
| cave line-loop groups traced | **528** |
| groups WITHOUT a COLUP1 write | **0 / 528** ✓ |
| first COLUP1 write phase | **c3 (440×) or c6 (88×)** = HBLANK → applies from pixel 0 ✓ |
| sample ordered writes on one line | `[(c6,$01), (c70,$1C), (c71,$1C), (c73,$1C)]` — early whole-line write + late writes (late phases land past the right-half split = HERO's double-write-per-scanline asym, now observed directly) |
| non-cave lines without COLUP1 (11 pcs) | classified below — none are cave-band scanlines |

Non-cave no-write line classification (disasm this session):

| pc | content | region |
|---|---|---|
| `$D100` | `STA $02 / BIT $b4 … STA $01` | VBL/VBLANK |
| `$D11F` | `STA $02 / LDA $e1 / STA $09` (COLUBK) | pre-cave setup |
| `$D133` | `STA $08` (COLUPF) + `$DC66/$DC61` PF tables | PF row setup (per design: COLUP1 not written here; transition line keeps OLD band color) |
| `$D358` | `STA $08` + `($bb),Y` PF fetch | band/room tail |
| `$D373` | `STY $08 / LDY #$ff / STY $0d,$0e` | PF blanking/sync line |
| `$D3BB` | `$d7` mask logic | level state |
| `$D3D4` | `STA $1b` (GRP0 from `$de72,X`) | player-draw transition |
| `$D437` | `LDA #$dd / STA $92,$96` | pointer setup |
| `$D4AE` | `STA $09,$08 / LDA #$30` | blank + CTRLPF=$30 (HUD handoff) |
| `$D4D0` | `LDA $df80,Y / STA $1b` | GRP0 tables (HUD/text) |
| `$D503` | `STA $0296` (TIM64T) + `STX $01` | frame timer arm |

**Verdict: the structural claim (§2c ★) is now empirically proven:**
every cave scanline rewrites COLUP1 from the per-line table in HBLANK,
before any pixel — a previous line's value can never be visible on the
next line → HERO cannot have our sticky-color bug. Our bug exists because
our kernel writes COLUP1 only per band + on the dynamic object path.

**Harness caveats recorded (do not re-derive):**
- frame wall-time = 19988c ≈ 263 lines ✓ (measured from SWCHB read
  spacing, once/frame at `$D71E`) — earlier "87-line frames" scare was an
  anchor artifact: un-WSYNCed INTIM spins (`$D0FB`) inflate wall-time
  between WSYNC groups, so WSYNC-count ≠ time outside the cave.
- identical histograms across sampled frames = py65 determinism (same
  phase each run), not proof of a static screen.
- RESET pulse delivered (first SWCHB read = $F7 at wall 21588 — wrong
  bit, superseded by the $FE pulse in §5b; game runs the full init from
  power-up regardless); whether gameplay started is OPEN (see §3).

## 5b. Post-verification pass — hero_dey.py (2026-10-05, cont.)

Harness `/tmp/opencode/hero_dey.py`: per-WSYNC-group (pc, Y-at-close,
wall, events) + full RAM write log + SWCHB anchor + joystick/fire
injection. Runs: 19 / 24 / 49 / 119 frames (walls 400k-2.4M).

### Frame / reset / input facts

- RESET decode at `$D71E: LDA $0282 / STA $fb / LSR A / BCC $d774` —
  LSR shifts D0 → RESET = **bit0**, pressed value **$FE**. §5's $F7
  pulse was bit3 (wrong) but harmless: power-up boot runs full init.
  Harness now pulses $FE (wall < 45000).
- SWCHB read = exactly 1 per frame (49 reads / 49 frames) → frame
  anchor valid.
- INPT4 = `$0C` active-low D7. Harness returned 0 for unhandled I/O =
  fire "held" from boot → fixed: $80 released, $00 pulse wall
  70000-90000. (Caution: read_io still returns 0 for any other
  unhandled read.)

### WSYNC group = SEGMENT (precision upgrade to §5)

- 6 WSYNC groups/frame (`$D20B`×3 + `$D296`×3); each spans **18-21
  scanlines** (1368-1596c) with NO internal WSYNC — fixed-time inner
  loop, WSYNC only at segment ends. §5's "cave line" was the harness
  extraction unit = one segment, not one scanline.
- Inside a group: **exactly one COLUP1 write per scanline** (measured
  21/21, 18/18, 21/21, 18/18, 21/21), first write in HBLANK (c3/c6) →
  the per-scanline rewrite claim now holds at 1:1 scanline precision.
- Y-at-close per group: 70, 5B, 49, 34, 22, 0D; Y drop = segment span
  exactly (21,18,21,18,21) → **Y = per-scanline countdown CONFIRMED**
  (§2b REFUTED-PENDING retracted; earlier "18-21 WSYNCs/frame" counted
  segments).
- Frame = 19988c ≈ 263 scanlines (reconfirmed over all runs).

### Banking caveat (record, do not re-derive)

- Only cross-bank control transfers in the whole disasm: bank0 START
  `BIT $FFF9 / JSR $F000` (→ bank1 START), bank1 `LFFEC: BIT LFFF8 /
  JSR $DFEC / LDX #$FF / TXS / JMP LF042` (→ bank0 `$DFEC`, then into
  bank1 input `$F042`). bank1 START holds the only hotspot WRITE
  (`STA LFFF9`); bank0 has zero hotspot writes; the `BIT $FFF8/$FFF9`
  are READS (real F8: read = no-op; Stella CartridgeEnhanced: read
  hotspot switches — AGENTS rule).
- Harness = flat label-split (A[$Dxxx] / B[$Fxxx], ROM-range writes
  dropped) and executes both halves: **15861/171502 instructions
  (9.2%) in $Fxxx**. Traces coherent over 49 frames → self-consistent
  so far, but read-hotspot switching is NOT modeled.
- Sampling rule: a WSYNC-close-pc histogram showed ZERO $Fxxx pcs and
  was WRONG (bank1 runs WSYNC-less). Prove bank presence by executed-
  pc counts, never by close-pc histograms.

### Input path (gameplay-start attempt — still OPEN)

- `LF042: LDY SWCHA` executes every frame (49/49). Held-right ($7F)
  stored as `$84 = $70` (`LF063: TYA / AND #$F0 / STA $84`) — verified
  live for 37 consecutive frames (wall 150000-900000 after fire pulse).
- Bank0 consumer (raw bytes): `LDA $84 / CMP #$F0 / BEQ ... / JMP
  $D949` (dpad not neutral → state handler).
- **No positional response**: RESP0/HMP0 write offsets byte-identical
  in EVERY frame (10 RESP0/frame at offsets 4317,5913,7281,8877,
  10245,11841,13322,13937,16066,16978) despite fire pulse + 37 frames
  held right → movement gated by an unreached state (§3 gameplay-start).

### RAM state decoded (119-frame + 49-frame census)

- `$81` = frame counter, +1/frame (value 2 at f0; `$70` at f110 in the
  119-frame run).
- `$AD`: bank1 sets `$FF` on its SELECT path (`LF087: LDA #$FF / STA
  $BA / STA $AD`); bank0 decrements 1/frame via raw bytes `C6 9F C6
  AD` (DEC $9F / DEC $AD) from `$95`; threshold `LDA $AD / CMP #$77 /
  BCS / INC $AB`; gate `LF290: LDA $AD / BNE $LF282`. Observed: writes
  STOP ~f60-70 (state-dependent). Exact meaning OPEN.
- `$9B`: only boot/level-load writes (25-byte table fill `LF021`);
  patrol code never executes in traced frames (§2d note).
- GRP0: 3528 writes / 49 frames, values animate (player + HUD columns).
- Static in observed state: RESP1 (39 writes total, pcs `$D6F6/$D6FE`,
  vals `$00/$82`); player coarse/fine position writes constant.

### Object writers (identity support)

- Cave GRP1: pcs `$D251/$D25A/$D25D` (per-scanline inside segments) =
  raw bytes `LDA ($91),Y / STA $1C` = the tall table sprite.
- HUD GRP1: pcs `$DE41/$DE4D/$DE51` + `$DC08` = digit columns
  `LDA $DE77,X / STA $1C` paired with GRP0 `LDA $DE72,X / STA $1B`
  (HUD renderer `JSR $DC00`).
- All measured COLUP1 write pcs match §2b's labeled `STA $07` loop
  sites (`$D172/$D19A/$D1C5/$D1ED/$D211/$D248/$D278/$D29A/$D2C8`) +
  HUD `$DC10` — no unexplained writer remains.

## 6. Session log

- 2026-10-05: file created; ROM layout + TIA write scan + `$D100-$D1F0`
  disasm recorded. Second pass: `$D00C` (position), `$D029` (RTS/delay),
  `$D230-$D29E` line-code structure + per-scanline-table hypothesis.
- 2026-10-05 (cont.): tables identified ($DA34 gfx / $DD69 ctl, 117B,
  Y=$74 countdown), CTL dump + bit0 window Y=105..79 recorded, loop
  topology ($D172 entry / $D309 back-edge), `$D00C` position routine,
  `$D029`=RTS delay, bank B `$9B` patrol decode, remaining COLUP1 sites
  classified ($D39C level-load, $D470/$D479 title blink, $DC10 HUD),
  section 4 (answer + fix candidates) written.
  (cont.): identified `$FFAA/$FFAC/$F900/$F630/$F63A` (§2d).
- 2026-10-05 (cont.): py65 line-trace harness built; core claim verified
  528/528 (§6); 11 non-cave no-write pcs classified; frame = 19988c
  confirmed; Y-countdown claim corrected to "pending DEY-count".
  **BREAK POINT** — user doing a model change; open items: §3 object
  identity + gameplay-start check, DEY-count pass, §4 candidates await
  user's fix decision.
- 2026-10-05 (cont. 2, after resume): hero_dey.py harness (per-group
  Y+events, RAM census, joystick/fire injection). Findings written to
  §5b: RESET = bit0/$FE ($F7 correction), segments = 18-21 scanlines
  with 1:1 per-scanline COLUP1, Y-drop = segment span (DEY-count
  CONFIRMED, §2b retracted), banking trampolines + 9.2% bank-B exec +
  close-pc-histogram trap, input path verified live ($84=$70) but zero
  positional response over 49 frames, $81/$AD/$9B/GRP0 census, object
  writer pcs. §3: clock-phase checked, gameplay-start + $9B runtime
  added as open. **BREAK POINT** — report to user; remaining: gameplay-
  start root cause (state gate vs harness fidelity), §4 fix candidates
  await user decision.
