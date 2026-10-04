#!/usr/bin/env python3
"""Phase 2 CHECK 2 probe (py65): cave-frame invariants + symmetric
bit-identity against the Phase 1 baseline ROM.

Assertions (gameplay frames >= 2 where the cave kernel runs):
  * last CTRLPF ($0A) write before cave entry (.Row) == $35 on the new
    ROM, == $05 on the baseline ROM, constant across frames;
  * last ENABL ($1F) write at .Row == 0; no bank0 ENABL write != 0
    anywhere (bank1 HUD bar writes are excluded via the log's bank tag);
  * zero bank0 RESBL ($14) / HMBL ($24) writes — symmetric models must
    never position the ball (bank1 HUD bar ball writes are expected and
    excluded);
  * bit-identical: the new ROM's TIA write sequence (frame >= 2) equals
    the baseline ROM's with CTRLPF ($0A), ENABL ($1F), COLUBK ($09),
    RESBL ($14), HMBL ($24), HMOVE ($2A) and WSYNC ($02) writes dropped.
    Intended
    deltas: CTRLPF $35 (Phase 2), Phase 3's per-band ENABL gate (writes
    0 in sym runs) + COLUBK moved from per-band .Row stores to one VBL
    .BgStore store, and the removed HUD boundary-ball (RESBL/HMBL/HMOVE;
    its 2 lines folded into TopGap so the WSYNC sequence stays aligned).

Baseline: P2_BASELINE env var, default /tmp/opencode/savior_phase1.bin
(phase1-code build). The bit-identical leg compares PF writes too, so the
baseline MUST embed the SAME room/model content as the working tree — any
content edit in src/rooms/ invalidates it. Regenerate:
  git worktree add /tmp/opencode/p1base a8fb32e
  cp -r src/rooms/. /tmp/opencode/p1base/src/rooms/
  (cd /tmp/opencode/p1base/src && ./build.sh)
  cp /tmp/opencode/p1base/src/savior.bin /tmp/opencode/savior_phase1.bin
  git worktree remove --force /tmp/opencode/p1base
If missing, the bit-identical leg is skipped (invariants still run).

Run: /home/iuri/python3/bin/python3 tools/test_phase2_ball.py
"""
import os
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

LABELS = {}
for _l in (SRC / "bank0.lst").read_text(errors="replace").splitlines():
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$", _l)
    if _m:
        LABELS.setdefault(_m.group(2), int(_m.group(1), 16))
for _need in ("StartFrame", ".Row", "Overscan"):
    if _need not in LABELS:
        sys.exit(f"label {_need} not found in bank0.lst")
PC_START = LABELS["StartFrame"]
PC_ROW = LABELS[".Row"]
PC_OVER = LABELS["Overscan"]

FRAMES = 60
CTRLPF, ENABL, RESBL, HMBL = 0x0A, 0x1F, 0x14, 0x24
HMOVE = 0x2A                     # project equate (kernel.asm:62)


class Mem:
    def __init__(self, banks):
        self.banks = banks
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 3
        self.swcha = 0xFF              # neutral stick
        self.swchb = 0xFF
        self.inpt4 = 0xFF              # fire released
        self.wsync_seen = False
        self.wall = 0
        self.deadline = {}
        self.log = []                  # (frame, bank, addr, val)
        self.frame = -1
        self.last = {}                 # addr -> last written value

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.banks[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            dl = self.deadline.get(0x296, 0)
            if self.wall >= dl:
                return 0
            return min(0xFF, max(1, (dl - self.wall + 63) // 64))
        if a == 0x000C:
            return self.inpt4
        if 0x1FF6 <= a <= 0x1FF9:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF6 <= a <= 0x1FF9:
            self.bank = a - 0x1FF6
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a in (0x0294, 0x0296, 0x0297):
            mult = {0x294: 1024, 0x296: 64, 0x297: 8}[a]
            self.deadline[a] = self.wall + v * mult
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            if (a & 0x3F) == 2:
                self.wsync_seen = True
            self.tia[a & 0x3F] = v
            self.log.append((self.frame, self.bank, a & 0x3F, v))
            self.last[a & 0x3F] = v


def run(rom: Path) -> dict:
    import py65.devices.mpu6502 as m
    blob = rom.read_bytes()
    assert len(blob) == 16384, f"{rom} is {len(blob)} bytes, want 16K"
    banks = [blob[4096 * i:4096 * (i + 1)] for i in range(4)]
    mem = Mem(banks)
    mpu = m.MPU(memory=mem)
    prev = 0

    def step():
        nonlocal prev
        mpu.step()
        c = mpu.processorCycles - prev
        prev = mpu.processorCycles
        mem.wall += c
        if mem.wsync_seen:
            w = mem.wall
            mem.wall = (w // 76 + 1) * 76 if w % 76 else w
            mem.wsync_seen = False

    frame = -1
    ctrlpf_at_row = []
    enabl_at_row = []
    cave_rows = 0
    steps = 0
    while frame < FRAMES:
        step()
        steps += 1
        if steps > 6_000_000:
            sys.exit(f"{rom.name}: runaway (frame {frame})")
        pc, bk = mpu.pc, mem.bank
        if bk == 0 and pc == PC_START:
            frame += 1
            mem.frame = frame
            # console RESET pulse: title -> game start (same as sim)
            mem.swchb = 0xFE if frame in (1, 2) else 0xFF
        if bk == 0 and pc == PC_ROW and frame >= 0:
            cave_rows += 1
            ctrlpf_at_row.append((frame, mem.last.get(CTRLPF)))
            enabl_at_row.append((frame, mem.last.get(ENABL)))
    return dict(
        ctrlpf=[v for f, v in ctrlpf_at_row if f >= 2],
        enabl_at_row=[v for f, v in enabl_at_row if f >= 2],
        cave_rows=cave_rows,
        log=mem.log,
    )


def check(r: dict, want_ctrlpf: int, log_fallback: bool = False) -> list[str]:
    """log_fallback: for the baseline ROM — its .Row address differs from
    the current bank0.lst parse (pre-pad code shifted), so the breakpoint
    never fires there; validate via any-bank CTRLPF writes in the log
    (phase1 baseline: bank1 HUD is the only writer, all $05)."""
    fails = []
    rows = r["ctrlpf"]
    if rows:
        bad = sorted({v for v in rows if v != want_ctrlpf})
        if bad:
            fails.append(f"CTRLPF at cave entry = "
                         + ", ".join(f"${v:02X}" for v in bad)
                         + f", want ${want_ctrlpf:02X}")
        if len(set(rows)) != 1:
            fails.append(f"CTRLPF not constant: {sorted(set(rows))}")
    elif log_fallback:
        # baseline phase1: CTRLPF was written by bank1 HUD only (no bank0
        # VBL site yet) — any-bank writes, all must equal want.
        vals = [v for f, b, a, v in r["log"] if f >= 2 and a == CTRLPF]
        if not vals:
            fails.append("baseline: no CTRLPF writes in log")
        elif set(vals) != {want_ctrlpf}:
            fails.append("baseline CTRLPF writes = "
                         + ", ".join(f"${v:02X}" for v in sorted(set(vals)))
                         + f", want ${want_ctrlpf:02X}")
    else:
        fails.append("cave kernel (.Row) never reached")
    ea = [v for v in r["enabl_at_row"] if v != 0]
    if ea:
        fails.append(f"ENABL at cave entry != 0: {sorted(set(ea))}")
    bank0 = [(f, a, v) for f, b, a, v in r["log"] if f >= 2 and b == 0]
    for f, a, v in bank0:
        if a == ENABL and v != 0:
            fails.append(f"bank0 ENABL write ${v:02X} at frame {f} (want only 0)")
            break
    ball = [(f, a, v) for f, a, v in bank0 if a in (RESBL, HMBL)]
    if ball:
        fails.append(f"bank0 ball-reg writes in symmetric run: {ball[:6]} "
                     f"(count {len(ball)})")
    return fails


def main() -> int:
    new = SRC / "savior.bin"
    r = run(new)
    fails = check(r, 0x35)

    base_path = Path(os.environ.get(
        "P2_BASELINE", "/tmp/opencode/savior_phase1.bin"))
    trace = [(a, v) for f, b, a, v in r["log"] if f >= 2]
    # Intended deltas (all stripped): CTRLPF $35 (Phase 2); Phase 3's
    # per-band ENABL gate + COLUBK moved to one VBL store; the removed
    # HUD boundary-ball (its RESBL/HMBL/HMOVE writes + the 2 lines folded
    # into TopGap). WSYNC ($02) is stripped too: its write VALUE is just
    # the leftover A (hardware-ignored) and the ball block carried
    # BallXTable/fine-adjust junk in A — line COUNT stays asserted by the
    # wall-model sim, not here.
    _strip = (CTRLPF, ENABL, 0x09, RESBL, HMBL, HMOVE, 0x02)
    stripped = [(a, v) for a, v in trace if a not in _strip]
    if base_path.exists():
        b = run(base_path)
        fails += check(b, 0x05, log_fallback=True)
        b_stripped = [(a, v) for f, bb, a, v in b["log"]
                      if f >= 2 and a not in _strip]
        if stripped != b_stripped:
            n = min(len(stripped), len(b_stripped))
            i = next((k for k in range(n) if stripped[k] != b_stripped[k]), n)
            fails.append(
                f"TIA write trace differs from baseline at index {i} "
                f"(new {stripped[i] if i < len(stripped) else '-'} vs base "
                f"{b_stripped[i] if i < len(b_stripped) else '-'}; "
                f"len {len(stripped)} vs {len(b_stripped)})")
        else:
            print(f"bit-identical vs baseline: {len(stripped)} TIA writes "
                  f"(CTRLPF/ENABL/COLUBK dropped) match over {FRAMES} frames")
    else:
        print(f"NOTE: baseline {base_path} missing — bit-identical leg skipped")

    if fails:
        for f in fails:
            print(f"FAIL: {f}")
        return 1
    print(f"test_phase2_ball: OK (CTRLPF $35 x{len(r['ctrlpf'])} cave "
          f"entries, ENABL 0, no bank0 ball writes, {FRAMES} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
