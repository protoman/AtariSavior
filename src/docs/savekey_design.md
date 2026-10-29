# SaveKey design (draft, 2026-10-28)

Goal (user): keep the **high score**, and the **stage / points / lives at the start
of each stage**; erase the save (not the high score) on a game over; on the next
power-on the title comes up with that stage selected and RESET resumes with the
saved points and lives. No SaveKey plugged in = the game behaves exactly as it does
today.

## 1. Hardware facts

- SaveKey / AtariVox = a 24LC256-class I2C EEPROM (32 KB, 64-byte pages) on the
  **right** controller port. It uses joystick-port **pins 3 and 4** as SDA/SCL
  (pin 3 = SDA = SWCHA bit 2, pin 4 = SCL = SWCHA bit 3; confirmed in Stella's
  `SaveKey.cxx`). The game only reads
  the LEFT stick, so the port is free.
- Open-drain by hand: the bus has pull-ups in the key, so a line is driven LOW by
  making the pin an output (SWACNT bit = 1, SWCHA bit = 0) and RELEASED by making
  it an input (SWACNT bit = 0). Never drive it high.
- Bit-banged at roughly 45 cycles per bit (~26 kbit/s, far below the chip's limit):
  a 12-byte read is ~5 ms, a 12-byte page write ~5 ms plus the chip's write cycle
  (<= 5 ms, ACK-polled). **A whole save fits in one frame (16.7 ms).**
- No chip answering the device address (NACK) = no key: every routine returns
  "absent" at once and the game carries on.
- Wear: one write per stage change (+ game over). 1M cycles per cell: irrelevant.

## 2. What is stored (one record, 12 bytes, 16-byte aligned so it never straddles
a 64-byte page)

| off | size | meaning |
|---|---|---|
| 0 | 2 | magic `$53 $01` (the second byte is the format version) |
| 2 | 1 | state: 0 = no save, 1 = save present |
| 3 | 1 | level (0-based) at the start of the saved stage |
| 4 | 1 | lives at the start of that stage |
| 5 | 3 | score at the start of that stage (packed BCD, ScoreTh/Hu/Te) |
| 8 | 3 | HIGH SCORE (packed BCD) |
| 11 | 1 | checksum = `$A5` eor bytes 0-10 |

A bad magic/checksum = "no key data": the game starts fresh and the first write
overwrites it. A block shared with another program is never trusted without the
magic. **Block address:** the chip is shared with other games; pick one 16-byte
block high in the chip (proposal `$7FE0`) and check it against the AtariVox
memory list before release (open question 4).

## 3. When we read and write

| event | action |
|---|---|
| power-on / RESET to the title | READ. Valid record with a save: `Level` = saved level (the title shows it as it already does), "resume" is armed by `Level == saved level`. |
| title: SELECT changes the stage | different from the saved level, so the next RESET is a fresh run (0 points, 3 lives). The save stays in the chip until the next stage change overwrites it. |
| RESET (start) with the saved stage | after `LoadLevel`: lives and score := saved values (second small READ, so no RAM is held while on the title). |
| stage advance (miner rescued, bonus tally done, `Level` incremented) | WRITE {level, lives, score, high = max(high, score)}. Only on a real advance, not on a death reload. |
| game over | WRITE {state 0, high = max(high, score)}, then the game over behaviour of question 1. |
| last stage cleared | WRITE {state 0, high = max(high, score)}. |

The high score is refreshed at every stage-start write for free (the record is
rewritten anyway), so a power-off mid-run still keeps the best score reached.

## 4. Game over (needs a ruling, question 1)

Today `LoseLife` with no lives left REFILLS to 3 lives and reloads the same level
with the score KEPT: there is no game over at all, so a "high score" could only
ever grow. Erasing the save at that point would also be undone at the next stage
start. Proposal: a real game over = commit the high score, erase the save, reset
the run (score 0, 3 lives) and go back to the title.

## 5. Architecture and budgets

- **Code lives in an empty bank (4-7; they are stubs today), as leaf routines**
  entered through twin pads like `RaftBody`. Estimated 350-450 bytes: I2C
  start/stop/send/receive/ack, `SkRead`, `SkWrite`, record pack/verify. Bank0 is
  byte-frozen, so its only growth is the hook call sites; those go in bank2's
  `LoadLevelB2` path / bank1's title code where there is slack, not in bank0
  (hook placement to be verified when implementing).
- **Zero page:** no free byte exists. The routines use only scratch that is dead
  at the call: the title (all gameplay ZP idle) and `LoadLevel` (before the room
  state is built). The 12-byte record is staged in that dead scratch
  (`Collision*`, `FetchPtr`, enemy shadows), picked and checked against
  `docs/zp_layout_skill.md` when implementing. No permanent RAM is added.
- **Frame time:** a save is <= ~10 ms. It runs inside the existing level-change
  frame (`LoadLevel` already hiccups there), so at worst one rolled frame at a
  stage change. Measured with `sim_frame_budget` once built.
- **Failure handling:** NACK on the control byte = absent (abort); write ACK-poll
  has a timeout; a failed write is ignored (the game never waits on the key).

## 6. Tests

- `tools/eeprom24lc256.py`: a py65 I2C slave model (start/stop, device address,
  16-bit address, page write with wrap, ACK polling, write-cycle busy), driven by
  the SWCHA/SWACNT writes the ROM makes.
- `tools/test_savekey.py`: round trip; no key (all NACK) = game unchanged;
  corrupt/foreign data ignored; stage advance writes the right record; game over
  clears the save and keeps the high score; title preselect and resume; cost per
  operation in cycles stays under the frame budget.
- Manual: Stella can emulate a SaveKey on the right port (Settings > Emulation);
  the steps go in this doc once built.

## 7. Decisions (user 2026-10-28)

1. **Game over is real**: commit the high score, erase the save, score 0 / 3
   lives, back to the title.
2. **SELECT**: the saved stage resumes with its points and lives; any other
   stage starts fresh.
3. **High score visible**: the title's score window alternates between the stage
   number and the high score (the high score shows for 1 s out of every 4.3 s).
4. **Still open, not blocking**: the EEPROM block address (`$7FE0` proposed; check
   the AtariVox memory list before release). Pins 3/4 = SDA/SCL is confirmed.

## 8. Status

- **Step 1 DONE** (2026-10-28): `bank4.asm` `SkService` (ops 0-3), the chip model
  `tools/eeprom24lc256.py`, `tools/test_savekey.py`. Slowest op = checkpoint,
  16.6k cycles = 83% of a frame, ~6k of it the chip's 5 ms write cycle.
- **Step 2 DONE** (2026-10-28): wired into bank0 through `CallPad_SaveKey` ($FC08,
  a retired pad slot: 0 extra bytes; bank4 serves `jmp SkService` at $FC0B and a
  `ReturnPad` twin at $FBF8; the pad is in `verify_build` CORRIDOR_PADS).
  Hooks: BOOT after the init, RESUME at the title RESET edge (before `LoadLevel`),
  CHECKPOINT in the tally done path (before `LoadLevel`; `Level == LEVEL_COUNT`
  = run won), GAMEOVER in `LoseLife` (SP reset first). The restart is done by
  bank4 itself (`Restart` = the power-up pad twin at $F000, bank0 `jmp GameStart`
  at $F005), so bank0 only gained the call sites; `ReloadLevel` is gone (no
  caller left), and the redundant `lda #0 / sta Level` after ClearZP too.
  Stack: bank4 nests 4 bytes under the pad (measured min SP $F9 in the game).
  `tools/test_savekey_game.py` drives the whole flow on the frozen ROM.
- **Behaviour change:** running out of lives is now a REAL game over (back to the
  title, 0 points, 3 lives); clearing the last stage ends the run the same way
  (it used to wrap to stage 1 keeping the score).
- **Step 3 DONE** (2026-10-28): op 4 TITLE (no I2C) runs every title frame from
  `TitleWork`: the HUD score window shows the stage number and, for 64 of every
  256 frames (EnemyRamP $80-$BF; the clock restarts at $F0 on each LoadLevel, so
  SELECT always shows the stage first), the high score BOOT left in
  vyLo/vyHi/PlayerYSub (dead on the title). No high score = stage number only.

## 9. Implementation order

1. (done) chip model, tests, I2C leaf in bank4.
2. (done) boot / resume / checkpoint / game over / last stage wired.
3. (done) title alternates the stage number and the high score.
4. Budget check in the real game (`sim_frame_budget` with a key), Stella checklist.

## 10. Stella checklist (manual; not yet run)

Stella: Options > Emulation > Controllers (or the game properties), RIGHT port =
SaveKey (it keeps its EEPROM in a `.sv` file). Then:
1. First boot (blank key): the title shows stage 1; no high score is shown.
2. RESET, play, rescue the miner: the next stage starts (a short hiccup is
   expected while the key is written, ~1 frame).
3. Close Stella, reopen with the same key: the title comes up on that stage, and
   for ~1 s every ~4 s the score window shows the high score instead of the stage
   number. RESET resumes with the saved lives and points.
4. SELECT to another stage and RESET: lives 3, points 0.
5. Lose all lives: back to the title (stage 1, 3 lives, 0 points); the high score
   is kept; reopening Stella shows stage 1 (the save was erased).
6. Right port = "Joystick" (no key): everything plays as before, no writes.
7. If a step fails, `tools/eeprom24lc256.py` is the model of what the ROM expects;
   compare Stella's `SaveKey`/`MT24LC256` behaviour (control byte `$A0/$A1`,
   16-bit address, 64-byte pages, ACK polling during the write cycle).
