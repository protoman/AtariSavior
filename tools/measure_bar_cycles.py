#!/usr/bin/env python3
"""Bar-section cycle measurement — find which timer-bar path overruns 76c.

The HUD band is structurally a fixed 48 WSYNC lines, so a ±1 scanline
flicker is NOT a WSYNC-count bug. It's a per-line CYCLE overrun: if a bar
line's content exceeds 76 cycles, the WSYNC write lands at c76/c77 (late),
the TIA spills that scanline, and the grey bottom edge of the band shifts
by 1 = the whole-screen jitter the user sees.

The bar section runs 5 dispatch paths off BarLevel/FineCnt/DelayCnt:
.YLoop (full), .BarRedF0, .BarRedF1, .BarRedFull(F=2,3,4). We boot to
gameplay, then for every BarLevel 0..120 measure the cycle count of each
bar line (TopGap..BarGap) and flag any line whose content (WSYNC-to-WSYNC
gap) is >= 76 cycles.

Run: /home/iuri/python3/bin/python3 tools/measure_bar_cycles.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BANKS = [open(SRC / f"bank{i}.bin", "rb").read() for i in range(8)]

BARLEVEL = 0xAE          # BarLevel ZP
PLAYERLIVES = 0xAC       # PlayerLives
PLAYERBOMBS = 0xF0       # PlayerBombs
WSYNC = 0x02


class Mem:
    def __init__(self):
        self.ram = bytearray(128)
        self.tia = bytearray(0x40)
        self.bank = 7
        self.swcha = 0xFF
        self.swchb = 0xFF
        self.inpt4 = 0x40
        self.wsync_writes = 0
        self.log_wsync = False
        self.wsync_log = []      # list of (bank, pc) at each WSYNC write
        self.mpu_pc = 0          # updated by step() before each mpu.step()
        self.wall = 0            # CPU-cycle wall clock (advance in step())

    def advance(self, c):
        """Advance the wall clock; on a WSYNC store ($02) snap to the next
        scanline boundary (76c) like hardware — same model as sim_frame_budget."""
        self.wall += c
        if c == 0:
            return
        # WSYNC halt is triggered by the STORE to $02, detected in __setitem__
        # (see below). Here we just accumulate CPU cycles.

    def __getitem__(self, a):
        a &= 0xFFFF
        if a >= 0xF000:
            return self.banks_[self.bank][a - 0xF000]
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            return self.ram[a & 0x7F]
        if a == 0x0280:
            return self.swcha
        if a == 0x0282:
            return self.swchb
        if a == 0x0284:
            return 0
        if a == 0x000C:
            return self.inpt4
        if 0x1FF4 <= a <= 0x1FFB:
            return 0
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            return self.tia[a & 0x3F]
        return 0

    def __setitem__(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if 0x1FF4 <= a <= 0x1FFB:
            self.bank = a - 0x1FF4
            return
        if a >= 0xF000:
            return
        if 0x80 <= a <= 0xFF or 0x180 <= a <= 0x1FF:
            self.ram[a & 0x7F] = v
            return
        if a == WSYNC:
            self.wsync_writes += 1
            # WSYNC halt: snap wall to next scanline boundary (76c/line)
            w = self.wall
            self.wall = (w // 76 + 1) * 76 if w % 76 else w
            # log (bank, pc) at each WSYNC so we can reconstruct the sequence
            if self.log_wsync:
                self.wsync_log.append((self.bank, self.mpu_pc))
            return
        if a in (0x0294, 0x0296, 0x0297):
            return
        if a <= 0x003F or 0x0100 <= a <= 0x017F:
            self.tia[a & 0x3F] = v


mem = Mem()
mem.banks_ = BANKS

from py65.devices.mpu6502 import MPU
mpu = MPU(memory=mem)

# bank0 StartFrame label
_LBL0 = {}
for _l in open(SRC / "bank0.lst", errors="replace"):
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$",
                  _l)
    if _m:
        _LBL0.setdefault(_m.group(2), int(_m.group(1), 16))
PC_STARTFRAME = _LBL0["StartFrame"]

# bank1 bar-region labels
_LBL1 = {}
for _l in open(SRC / "bank1.lst", errors="replace"):
    _m = re.match(r"^\s*\d+\s+([0-9a-f]{4})\s+"
                  r"([A-Za-z_.][A-Za-z0-9_.]*)(?:\s+subroutine)?\s*(?:;.*)?$",
                  _l)
    if _m:
        _LBL1.setdefault(_m.group(2), int(_m.group(1), 16))
TOPGAP = _LBL1[".TopGap"]
BARGAP = _LBL1[".BarGap"]
YLOOP = _LBL1[".YLoop"]
BARREDF0 = _LBL1[".BarRedF0"]
BARREDF1 = _LBL1[".BarRedF1"]
BARREDFULL = _LBL1[".BarRedFull"]

print(f"bar region: TopGap=${TOPGAP:04X} BarGap=${BARGAP:04X}")
print(f"paths: YLoop=${YLOOP:04X} F0=${BARREDF0:04X} "
      f"F1=${BARREDF1:04X} Full=${BARREDFULL:04X}")


def step():
    mem.mpu_pc = mpu.pc
    before = mpu.processorCycles
    mpu.step()
    c = mpu.processorCycles - before
    mem.advance(c)


def boot_to_gameplay():
    """Boot, hit title RESET edge, land in gameplay (DropTarget==0).
    Sequence matches test_menu_flow.py: f1-f2 released -> f3 single RESET
    -> 4 frames -> title $FF; then title RESET -> drop-in lands -> DROPT==0."""
    guard = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        guard += 1
        if guard > 400000:
            sys.exit("never reached StartFrame")

    def run_to_frame(sw):
        g = 0
        while True:
            step()
            g += 1
            if g > 40000:
                sys.exit("frame stalled")
            if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
                mem.swchb = sw
                return

    run_to_frame(0xFF); run_to_frame(0xFF)      # f1, f2 released
    run_to_frame(0xFE)                          # f3 single RESET pulse
    for _ in range(4):
        run_to_frame(0xFF)                      # -> old title $FF
    run_to_frame(0xFE)                          # title RESET -> start game
    run_to_frame(0xFF)
    for _ in range(400):                        # idle until drop-in lands
        run_to_frame(0xFF)
        if mem.ram[0x0A & 0x7F] == 0:           # DropTarget $8A == 0
            return True
    return False


def measure_bar(barlevel, playerlives=3, playerbombs=5):
    """Run frames until PC enters bar region; measure per-line cycles."""
    # set state (ZP indices are &0x7F into the 128-byte ram array)
    mem.ram[BARLEVEL & 0x7F] = barlevel
    mem.ram[PLAYERLIVES & 0x7F] = playerlives
    mem.ram[PLAYERBOMBS & 0x7F] = playerbombs

    # advance to next StartFrame, then step into bar region, counting cycles
    g = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        g += 1
        if g > 40000:
            return None
    # now in overscan/start of next frame; step until bank1 bar region
    in_bar = False
    line_start_cycle = None
    lines = []           # list of cycle-counts per bar line
    cyc = 0
    guard = 0
    while True:
        # count cycles: py65 doesn't expose per-step cycles directly;
        # approximate by instruction — use mpu.step and a cycle table.
        step()
        cyc += _cycles_at(mpu.pc)
        guard += 1
        if guard > 20000:
            break
        pc = mpu.pc
        if mem.bank == 1 and pc == TOPGAP:
            in_bar = True
            line_start_cycle = cyc
            lines = []
            continue
        if in_bar and mem.bank == 1 and pc == WSYNC + 0xF000:
            pass
        if in_bar and mem.bank == 1:
            # detect WSYNC write: the store to $02. Track via mem hook count.
            pass
        if in_bar and mem.bank == 1 and pc == BARGAP:
            break
    return lines


# 6502 cycle table (instruction length in cycles; branch/page-cross approx)
_CY = None


def _load_cycles():
    global _CY
    _CY = [2] * 256
    # rough static lengths (no page-cross refinement — good enough to find
    # a >76c line since delay loops dominate)
    for op, c in {
        0xA9: 2, 0xA5: 3, 0xB5: 4, 0xAD: 4, 0xBD: 4, 0xB9: 4, 0xA1: 6,
        0xB1: 5, 0x85: 3, 0x95: 4, 0x8D: 4, 0x9D: 5, 0x99: 5, 0x81: 6,
        0x91: 6, 0xAA: 2, 0xA8: 2, 0x8A: 2, 0x98: 2, 0xCA: 2, 0x88: 2,
        0xE8: 2, 0xC8: 2, 0xE6: 5, 0xC6: 5, 0xF6: 6, 0xD6: 6, 0xEE: 6,
        0xDE: 7, 0xFE: 7, 0xE0: 2, 0xC0: 2, 0x20: 6, 0x60: 6, 0x40: 6,
        0x4C: 3, 0x6C: 5, 0x10: 2, 0x30: 2, 0x50: 2, 0x70: 2, 0x90: 2,
        0xB0: 2, 0xD0: 2, 0xF0: 2, 0x90: 2, 0x0A: 2, 0x4A: 2, 0x2A: 2,
        0x6A: 2, 0x29: 2, 0x09: 2, 0x49: 2, 0x69: 2, 0xE9: 2, 0xC9: 2,
        0x24: 3, 0x2C: 4, 0x00: 7, 0xEA: 2, 0x18: 2, 0x38: 2, 0x58: 2,
        0x78: 2, 0xB8: 2, 0xD8: 2, 0xF8: 2, 0x8D: 4, 0xAD: 4,
    }.items():
        _CY[op] = c
    # branches 2/3
    for op in (0x10, 0x30, 0x50, 0x70, 0x90, 0xB0, 0xD0, 0xF0):
        _CY[op] = 2


def _cycles_at(pc):
    if _CY is None:
        _load_cycles()
    op = mem[pc]
    return _CY[op]


# --- robust approach: py65 real cycle counter at each WSYNC boundary ---
def measure_bar2(barlevel, playerlives=3, playerbombs=5):
    """Run to bar region, force BarLevel, measure per-line cycles via
    py65 processorCycles deltas between WSYNC writes."""
    g = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        g += 1
        if g > 40000:
            return None
    # step into bar region; on entering, force BarLevel to the value under
    # test (the timer may have decremented it during overscan), then measure
    # each WSYNC-to-WSYNC line's real cycle count.
    in_bar = False
    lines = []
    last_cycles = 0
    forced = False
    guard = 0
    while guard < 30000:
        pc = mpu.pc
        if mem.bank == 1 and pc == TOPGAP:
            in_bar = True
            lines = []
            mpu.processorCycles = 0
            last_cycles = 0
            forced = False
            wsync_before[0] = mem.wsync_writes  # ignore prior (kernel) WSYNCs
        if in_bar:
            if not forced:
                # force the BarLevel under test right at bar entry
                mem.ram[BARLEVEL & 0x7F] = barlevel
                mem.ram[PLAYERLIVES & 0x7F] = playerlives
                mem.ram[PLAYERBOMBS & 0x7F] = playerbombs
                forced = True
            if mem.bank == 1 and pc == BARGAP:
                # record the final line (BarGap WSYNC closes the bar block)
                lines.append(mpu.processorCycles - last_cycles)
                break
            step()
            if mem.wsync_writes != wsync_before[0]:
                lines.append(mpu.processorCycles - last_cycles)
                last_cycles = mpu.processorCycles
                wsync_before[0] = mem.wsync_writes
        else:
            step()
        guard += 1
    return lines


# track wsync writes in a mutable cell so the inner loop can compare
wsync_before = [0]

# HUD band section labels (from bank1.lst)
HUDPAD = _LBL1[".HudPad"]
TOPGAP = _LBL1[".TopGap"]
LIVESLOOP = _LBL1[".LivesLoop"]
LIVESDONE = _LBL1[".LivesDone"]
BOMBSLOOP = _LBL1[".BombsLoop"]
SCORELOOP = _LBL1[".ScoreLoop"]
print(f"HudPad=${HUDPAD:04X} LivesLoop=${LIVESLOOP:04X} BombsLoop=${BOMBSLOOP:04X}")


def run_frame_wsync():
    """Advance exactly one frame (StartFrame->StartFrame), returning the
    ordered list of (bank, pc) for every WSYNC write in that frame."""
    g = 0
    while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
        step()
        g += 1
        if g > 40000:
            return None
    # reset the wall clock + WSYNC count at frame start so we can read BOTH
    # the scanline count (wall delta / 76) and the WSYNC count for this frame.
    # Wall reset happens at StartFrame (VSYNC), so the count covers
    # VBLANK + kernel + overscan = 259 scanlines. HUD adds the 3 VSYNC
    # stall lines that the next frame's reset will attribute to it, so
    # total frame = measured_lines + 3 = 262.
    mem.wall = 0
    mem.wsync_writes = 0
    mem.wsync_log = []
    mem.log_wsync = True
    guard = 0
    while True:
        step()
        guard += 1
        if guard > 40000:
            break
        if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
            break
    mem.log_wsync = False
    lines = mem.wall / 76.0
    return mem.wsync_log, mem.wsync_writes, lines


def hud_band_wsync(log):
    """Count WSYNC writes that occur in bank1 within the HUD band region
    (pc between TOPGAP and end of HudPad loop)."""
    # HudPad loop ends at the 'rts'/'jmp' after the bne; find last bank1 WSYNC
    # in the TOPGAP..$F7ED range. We approximate band end as pc just after
    # the HudPad loop (pc in [TOPGAP, HUDPAD_END]).
    HUDPAD_END = _LBL1[".HudPad"] + 0x20  # generous; HudPad loop is small
    n = 0
    for bank, pc in log:
        if bank == 1 and TOPGAP <= pc <= HUDPAD_END:
            n += 1
    return n


if __name__ == "__main__":
    ok = boot_to_gameplay()
    print(f"booted to gameplay: {ok}")
    if not ok:
        sys.exit("could not reach gameplay")

    # --- Transition-span measurement: cave last WSYNC -> first TopGap WSYNC ---
    # .AfterRows = $F191 (bank0). The cave's last WSYNC is the one just before
    # .AfterRows. We count cycles from that WSYNC to the first bank1 TopGap WSYNC.
    AFTERROWS = _LBL0.get(".AfterRows", 0xF191)
    print(f"\n.AferRows=${AFTERROWS:04X} TopGap=${TOPGAP:04X}")

    # Advance to StartFrame, then step; detect cave WSYNC (bank0, near .AfterRows)
    # then count cycles until bank1 TopGap WSYNC.
    def measure_transition():
        g = 0
        while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
            step()
            g += 1
            if g > 40000:
                return None
        # step into the frame; find the LAST bank0 WSYNC before .AfterRows
        # (the cave kernel's final scanline), then count to bank1 TopGap.
        in_kernel = False
        last_wsync_cyc = None
        mpu.processorCycles = 0
        guard = 0
        while guard < 60000:
            pc = mpu.pc
            # detect cave kernel WSYNC: bank0, pc in .Line..AfterRows range
            if mem.bank == 0 and 0xF122 <= pc <= AFTERROWS:
                in_kernel = True
            if in_kernel and mem.bank == 1 and pc == TOPGAP:
                # reached TopGap; the span = cycles since last cave WSYNC
                return (mpu.processorCycles, last_wsync_cyc)
            step()
            # track WSYNC writes in the cave kernel
            if in_kernel and mem.bank == 0 and mem.wsync_writes != getattr(measure_transition, '_ws', [0])[0]:
                if not hasattr(measure_transition, '_ws'):
                    measure_transition._ws = [0]
                if mem.wsync_writes != measure_transition._ws[0]:
                    last_wsync_cyc = mpu.processorCycles
                    measure_transition._ws[0] = mem.wsync_writes
            guard += 1
        return None

    # --- Precise transition span: cave last WSYNC -> first TopGap WSYNC ---
    # The cave kernel's final scanline WSYNC is the last bank0 WSYNC executed
    # before PC reaches .AfterRows ($F191). Count cycles from that WSYNC to
    # the first bank1 TopGap WSYNC. This is the cycle-precise handoff span.
    AFTERROWS = _LBL0.get(".AfterRows", 0xF191)
    LINE_PC = _LBL0.get("CaveLine", 0xF122)
    spans = []
    for f in range(150):
        g = 0
        while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
            step()
            g += 1
            if g > 40000:
                break
        # step into kernel; track last bank0 WSYNC cycle, detect .AfterRows,
        # then count to bank1 TopGap WSYNC
        last_cave_wsync_cyc = None
        mpu.processorCycles = 0
        wsnap = mem.wsync_writes
        guard = 0
        reached_afterrows = False
        while guard < 30000:
            pc = mpu.pc
            if mem.bank == 0 and pc == AFTERROWS:
                reached_afterrows = True
            if mem.bank == 1 and pc == TOPGAP and last_cave_wsync_cyc is not None:
                spans.append(mpu.processorCycles - last_cave_wsync_cyc)
                break
            step()
            # track bank0 WSYNC writes in the kernel (.Line..AfterRows)
            if (mem.bank == 0 and not reached_afterrows
                    and mem.wsync_writes != wsnap
                    and LINE_PC - 0x40 <= pc <= AFTERROWS):
                last_cave_wsync_cyc = mpu.processorCycles
                wsnap = mem.wsync_writes
            guard += 1
    if spans:
        from collections import Counter
        sc = Counter(spans)
        print(f"\ncave-last-WSYNC -> TopGap-WSYNC span, {len(spans)} frames:")
        for c, n in sorted(sc.items()):
            print(f"  {c}c: {n} frames")
        print(f"  min={min(spans)} max={max(spans)} spread={max(spans)-min(spans)}")
        # A stable handoff has spread 0. Any spread >= 1 means the cave's last
        # scanline cycle count varies -> HUD band shifts by that many scanlines.
    else:
        print("\nno transition spans captured")

    # --- Overscan duration: Overscan entry -> next StartFrame ---
    # Overscan is timer-paced (TIM64T #50 = 3200c). If overscan WORK exceeds
    # 3200c the timer expires before the wait loop, overscan runs long -> frame
    # 263 -> HUD band shifts down 1 display row (row 194 -> overscan black).
    OVERSCAN = _LBL0.get("Overscan", 0xF19A)
    print(f"\nOverscan=${OVERSCAN:04X}")
    overspans = []
    for f in range(150):
        g = 0
        while not (mem.bank == 0 and mpu.pc == OVERSCAN):
            step()
            g += 1
            if g > 60000:
                break
        mpu.processorCycles = 0
        guard = 0
        while guard < 20000:
            if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
                overspans.append(mpu.processorCycles)
                break
            step()
            guard += 1
    if overspans:
        from collections import Counter
        oc = Counter(overspans)
        print(f"Overscan->StartFrame cycles, {len(overspans)} frames:")
        for c, n in sorted(oc.items()):
            tag = "  <-- OVERRUN >3200c" if c > 3200 else ""
            print(f"  {c}c: {n} frames{tag}")
        over = [c for c in overspans if c > 3200]
        print(f"  min={min(overspans)} max={max(overspans)} "
              f"over-3200={len(over)}/{len(overspans)}")

    # --- VBLANK duration: VBLTimer -> .Row (kernel entry) ---
    # VBL = timer-paced TIM64T #23 = 1472c. .WaitVBLANK polls INTIM until it
    # expires, so VBL is nominally fixed. BUT if the VBL game-logic work (from
    # VBLTimer to .WaitVBLANK) exceeds 1472c, the timer is already expired and
    # the kernel starts immediately -> VBL is longer than 1472c -> HUD shifts
    # down 1 (the seam flip). Measure VBLTimer -> .Row across frames.
    VBLTIMER = _LBL0.get("VBLTimer", None)
    ROW_PC = _LBL0.get(".Row", None)
    print(f"\nVBLTimer=${VBLTIMER:04X} .Row=${ROW_PC:04X}"
          if VBLTIMER and ROW_PC else "\nlabels missing")
    if VBLTIMER and ROW_PC:
        vblspans = []
        for f in range(150):
            g = 0
            while not (mem.bank == 0 and mpu.pc == VBLTIMER):
                step()
                g += 1
                if g > 60000:
                    break
            mpu.processorCycles = 0
            guard = 0
            while guard < 20000:
                if mem.bank == 0 and mpu.pc == ROW_PC:
                    vblspans.append(mpu.processorCycles)
                    break
                step()
                guard += 1
        if vblspans:
            from collections import Counter
            vc = Counter(vblspans)
            print(f"VBLTimer->.Row cycles, {len(vblspans)} frames:")
            for c, n in sorted(vc.items()):
                tag = "  <-- OVERRUN >1472c" if c > 1472 else ""
                print(f"  {c}c: {n} frames{tag}")
            over = [c for c in vblspans if c > 1472]
            print(f"  min={min(vblspans)} max={max(vblspans)} "
                  f"over-1472={len(over)}/{len(vblspans)}")

    # --- Cave kernel WSYNC count: .Row -> .AfterRows (bank0) ---
    # The cave should emit exactly 144 WSYNC (3 bands x 48). If it emits 145
    # on some frames, the cave/HUD seam shifts down 1 (the detector flip).
    AFTERROWS = _LBL0.get(".AfterRows", 0xF191)
    ROW_PC = _LBL0.get(".Row", None)
    print(f"\n cave WSYNC count .Row=${ROW_PC:04X} -> .AfterRows=${AFTERROWS:04X}")
    if ROW_PC:
        from collections import Counter
        cave_counts = Counter()
        for f in range(150):
            g = 0
            while not (mem.bank == 0 and mpu.pc == ROW_PC):
                step()
                g += 1
                if g > 60000:
                    break
            wsnap = mem.wsync_writes
            guard = 0
            while guard < 20000:
                if mem.bank == 0 and mpu.pc == AFTERROWS:
                    cave_counts[mem.wsync_writes - wsnap] += 1
                    break
                step()
                guard += 1
        print(f"cave kernel WSYNC count distribution, {sum(cave_counts.values())} frames:")
        for c, n in sorted(cave_counts.items()):
            tag = "  <-- NOT 147!" if c != 147 else ""
            print(f"  {c} WSYNC: {n} frames{tag}")

    # --- Seam state: dump CollisionX (tide 36-39) + BombPacked + RoomBandColor
    # at .AfterRows, to correlate with the detector's two-class seam flip.
    # CollisionX = 36+off (tide). BombPacked b0-1 = bomb state (2 = exploding,
    # skips water-strip COLUBK). RoomBandColor = water-strip band color.
    COLLX = _LBL0.get("CollisionX", 0x8B) if "CollisionX" in _LBL0 else 0x8B
    # find real ZP addresses from kernel.asm EQUs
    import re as _re
    _ks = (SRC / "kernel.asm").read_text()
    def _equ(name):
        m = _re.search(rf"^{name}\s*=\s*\$([0-9A-Fa-f]+)", _ks, _re.M)
        return int(m.group(1), 16) if m else None
    COLLX = _equ("CollisionX") or 0x8B
    BOMBP = _equ("BombPacked") or 0xB5
    BANDC = _equ("RoomBandColor") or 0xBC
    print(f"\n seam state @.AfterRows: CollisionX=${COLLX:02X} "
          f"BombPacked=${BOMBP:02X} RoomBandColor=${BANDC:02X}")
    from collections import Counter
    seam_state = Counter()
    if ROW_PC:
        for f in range(200):
            g = 0
            while not (mem.bank == 0 and mpu.pc == ROW_PC):
                step()
                g += 1
                if g > 60000:
                    break
            guard = 0
            while guard < 20000:
                if mem.bank == 0 and mpu.pc == AFTERROWS:
                    cx = mem.ram[COLLX & 0x7F]
                    bp = mem.ram[BOMBP & 0x7F]
                    bc = mem.ram[BANDC & 0x7F]
                    seam_state[(cx, bp & 3, bc)] += 1
                    break
                step()
                guard += 1
        print(f" (CollisionX, BombPacked&3, RoomBandColor) distribution, "
              f"{sum(seam_state.values())} frames:")
        for k, n in sorted(seam_state.items()):
            print(f"  CollX={k[0]} Bomb={k[1]} Band={k[2]:02X}: {n}")

    # --- Cave LAST scanline cycle budget: the .Line body just before
    # .AfterRows. If this body hits 76c (WSYNC written at c76), the next
    # scanline starts late -> seam flips. Measure the WSYNC-to-WSYNC cycle
    # gap for the cave's final .Line iteration across frames (under thrust
    # input to reproduce the detector's movement-dependent flip).
    print(f"\n cave last-scanline body cycles (thrust input):")
    # enable thrust: SWCHA bit for joystick UP is D4 (bit 4, active low=0)
    # 0xEF = D4=0 (up held). Keep fire released (INPT4 bit7=1=0x80).
    from collections import Counter
    lastline_cyc = Counter()
    if ROW_PC:
        for f in range(200):
            mem.swcha = 0xEF   # joystick UP held (thrust)
            g = 0
            while not (mem.bank == 0 and mpu.pc == ROW_PC):
                step()
                g += 1
                if g > 60000:
                    break
            # track WSYNC writes; measure the LAST cave WSYNC-to-.AfterRows gap
            wsnap = mem.wsync_writes
            last_ws_cyc = None
            mpu.processorCycles = 0
            guard = 0
            while guard < 20000:
                if mem.bank == 0 and mpu.pc == AFTERROWS:
                    if last_ws_cyc is not None:
                        lastline_cyc[mpu.processorCycles - last_ws_cyc] += 1
                    break
                step()
                if mem.wsync_writes != wsnap:
                    last_ws_cyc = mpu.processorCycles
                    wsnap = mem.wsync_writes
                guard += 1
        print(f"  last .Line WSYNC->.AfterRows cycle distribution:")
        for c, n in sorted(lastline_cyc.items()):
            tag = "  <-- LATE (>=73)" if c >= 73 else ""
            print(f"    {c}c: {n} frames{tag}")

    # --- Total WSYNC under THRUST+BOMB input (detector's gameplay) ---
    # The idle total was 203 fixed. Under movement/bomb the frame may emit 204
    # (a +1 scanline stall) on some frames = the seam flip. Measure total WSYNC
    # per frame across thrust + periodic fire (bomb) cycles.
    print(f"\n total WSYNC + frame-lines under thrust+fire input:")
    from collections import Counter
    tf_total = Counter()
    tf_lines = Counter()
    for f in range(200):
        # thrust held (SWCHA D4=0 = 0xEF); fire pressed every 8th frame
        mem.swcha = 0xEF
        mem.inpt4 = 0x00 if (f % 8 < 3) else 0x80   # fire held 3 of every 8
        res = run_frame_wsync()
        if res is None:
            continue
        log, nws, lines = res
        tf_total[nws] += 1
        tf_lines[round(lines, 2)] += 1
    print(f"  total WSYNC/frame distribution (thrust+fire):")
    for c, n in sorted(tf_total.items()):
        tag = "  <-- +1 vs idle 203!" if c != 203 else ""
        print(f"    {c} WSYNC: {n} frames{tag}")
    print(f"  frame-lines (wall/76) distribution (thrust+fire):")
    for c, n in sorted(tf_lines.items()):
        tag = "" if abs(c - 263.0) < 0.15 else "  <-- OFF 263!"
        print(f"    {c} lines: {n} frames{tag}")

    # --- Which section loses the WSYNC under fire? Split per-frame WSYNC into
    # cave (bank0 .Row..AfterRows) vs HUD (bank1 TopGap..HudPad) vs rest.
    AFTERROWS = _LBL0.get(".AfterRows", 0xF191)
    ROW_PC = _LBL0.get(".Row", None)
    print(f"\n per-section WSYNC under thrust+fire:")
    from collections import Counter
    sect = Counter()
    for f in range(200):
        mem.swcha = 0xEF
        mem.inpt4 = 0x00 if (f % 8 < 3) else 0x80
        g = 0
        while not (mem.bank == 0 and mpu.pc == PC_STARTFRAME):
            step()
            g += 1
            if g > 40000:
                break
        mem.wsync_log = []
        mem.log_wsync = True
        guard = 0
        while True:
            step()
            guard += 1
            if guard > 40000:
                break
            if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
                break
        mem.log_wsync = False
        log = mem.wsync_log
        cave = sum(1 for b, p in log if b == 0 and ROW_PC and ROW_PC <= p <= AFTERROWS)
        hud = sum(1 for b, p in log if b == 1 and TOPGAP <= p <= _LBL1[".HudPad"] + 0x20)
        total = len(log)
        sect[(cave, hud, total)] += 1
    print(f"  (cave, hud, total) distribution:")
    for k, n in sorted(sect.items()):
        print(f"    cave={k[0]} hud={k[1]} total={k[2]}: {n} frames")

    # --- Overscan DURATION under thrust+fire (the ±1 source) ---
    # Overscan is timer-paced TIM64T #50 = 3200c. If overscan WORK (incl. the
    # SetObjectXPos WSYNC stalls for bomb/laser/enemy) exceeds 3200c, the frame
    # runs long -> 263 scanlines -> next frame's seam shifts down 1. Measure
    # Overscan->StartFrame cycles under thrust+fire.
    OVERSCAN = _LBL0.get("Overscan", 0xF19A)
    print(f"\n overscan duration under thrust+fire:")
    from collections import Counter
    over_d = Counter()
    over3200 = 0
    for f in range(200):
        mem.swcha = 0xEF
        mem.inpt4 = 0x00 if (f % 8 < 3) else 0x80
        g = 0
        while not (mem.bank == 0 and mpu.pc == OVERSCAN):
            step()
            g += 1
            if g > 60000:
                break
        mpu.processorCycles = 0
        guard = 0
        while guard < 20000:
            if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
                c = mpu.processorCycles
                over_d[c] += 1
                if c > 3200:
                    over3200 += 1
                break
            step()
            guard += 1
    if over_d:
        print(f"  Overscan->StartFrame cycles, {sum(over_d.values())} frames:")
        # bucket by 64c to keep output short
        from collections import defaultdict
        bucket = defaultdict(int)
        for c, n in over_d.items():
            bucket[(c // 64) * 64] += n
        for b in sorted(bucket):
            tag = "  <-- OVERRUN >3200c" if b >= 3200 else ""
            print(f"    ~{b}c: {bucket[b]} frames{tag}")
        print(f"  min={min(over_d)} max={max(over_d)} over-3200={over3200}/{sum(over_d.values())}")

    # --- VBL duration under thrust+fire (bomb explosion may overrun) ---
    # The bomb explosion (BombPacked state 2) runs ApplyBombWalls + blink in
    # VBL. If those frames overrun TIM64T #23 (1472c), VBL is short -> the
    # kernel (and HUD seam) starts 1 scanline early -> seam shifts up. Measure
    # VBLTimer->.Row under thrust+fire.
    VBLTIMER = _LBL0.get("VBLTimer", None)
    ROW_PC = _LBL0.get(".Row", None)
    if VBLTIMER and ROW_PC:
        print(f"\n VBL duration under thrust+fire:")
        from collections import Counter
        vbl_d = Counter()
        over1472 = 0
        for f in range(200):
            mem.swcha = 0xEF
            mem.inpt4 = 0x00 if (f % 8 < 3) else 0x80
            g = 0
            while not (mem.bank == 0 and mpu.pc == VBLTIMER):
                step()
                g += 1
                if g > 60000:
                    break
            mpu.processorCycles = 0
            guard = 0
            while guard < 20000:
                if mem.bank == 0 and mpu.pc == ROW_PC:
                    c = mpu.processorCycles
                    vbl_d[c] += 1
                    if c > 1472:
                        over1472 += 1
                    break
                step()
                guard += 1
        if vbl_d:
            print(f"  VBLTimer->.Row cycles, {sum(vbl_d.values())} frames:")
            from collections import defaultdict
            bucket = defaultdict(int)
            for c, n in vbl_d.items():
                bucket[(c // 32) * 32] += n
            for b in sorted(bucket):
                tag = "  <-- OVERRUN >1472c" if b >= 1472 else ""
                print(f"    ~{b}c: {bucket[b]} frames{tag}")
            print(f"  min={min(vbl_d)} max={max(vbl_d)} over-1472={over1472}/{sum(vbl_d.values())}")

    # --- WSYNC write-cycle margin: cycle-since-last-WSYNC for every WSYNC in
    # the cave->HUD transition region, under thrust+fire. A WSYNC written at
    # cycle >=74 stalls a full line (the "one-cycle-late WSYNC" family). Measure
    # the gap for each WSYNC from the cave's last .Line through TopGap.
    AFTERROWS = _LBL0.get(".AfterRows", 0xF191)
    ROW_PC = _LBL0.get(".Row", None)
    LINE_PC = _LBL0.get("CaveLine", 0xF122)
    if ROW_PC:
        print(f"\n WSYNC write-cycle margin (thrust+fire), cave last lines -> TopGap:")
        from collections import Counter
        gap_c = Counter()
        late = 0
        total_ws = 0
        for f in range(200):
            mem.swcha = 0xEF
            mem.inpt4 = 0x00 if (f % 8 < 3) else 0x80
            g = 0
            while not (mem.bank == 0 and mpu.pc == ROW_PC):
                step()
                g += 1
                if g > 60000:
                    break
            # step through the whole frame; record cycle-since-prev-WSYNC for
            # every WSYNC in bank0 .Line..AfterRows and bank1 TopGap..HudPad
            wsnap = mem.wsync_writes
            mpu.processorCycles = 0
            last_ws = 0
            guard = 0
            while guard < 40000:
                pc = mpu.pc
                in_region = ((mem.bank == 0 and LINE_PC and LINE_PC - 0x80 <= pc <= AFTERROWS)
                             or (mem.bank == 1 and TOPGAP <= pc <= _LBL1[".HudPad"] + 0x20))
                step()
                if mem.wsync_writes != wsnap:
                    if in_region:
                        gap = mpu.processorCycles - last_ws
                        gap_c[gap] += 1
                        total_ws += 1
                        if gap >= 74:
                            late += 1
                    last_ws = mpu.processorCycles
                    wsnap = mem.wsync_writes
                if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
                    break
                guard += 1
        if gap_c:
            print(f"  WSYNC gap distribution, {total_ws} WSYNC in region:")
            for c, n in sorted(gap_c.items()):
                tag = "  <-- LATE >=74" if c >= 74 else ""
                print(f"    {c}c: {n}{tag}")
            print(f"  LATE (>=74c) WSYNC: {late}/{total_ws}")

        # --- Which PC writes the late (>=74c) WSYNC? ---
        print(f"\n late-WSYNC PC attribution (thrust+fire):")
        from collections import Counter
        late_pc = Counter()
        for f in range(100):
            mem.swcha = 0xEF
            mem.inpt4 = 0x00 if (f % 8 < 3) else 0x80
            g = 0
            while not (mem.bank == 0 and mpu.pc == ROW_PC):
                step()
                g += 1
                if g > 60000:
                    break
            wsnap = mem.wsync_writes
            mpu.processorCycles = 0
            last_ws = 0
            last_pc = None
            guard = 0
            while guard < 40000:
                pc = mpu.pc
                bank = mem.bank
                in_region = ((bank == 0 and LINE_PC and LINE_PC - 0x80 <= pc <= AFTERROWS)
                             or (bank == 1 and TOPGAP <= pc <= _LBL1[".HudPad"] + 0x20))
                step()
                if mem.wsync_writes != wsnap:
                    if in_region:
                        gap = mpu.processorCycles - last_ws
                        if gap >= 74:
                            late_pc[(bank, last_pc, gap)] += 1
                    last_ws = mpu.processorCycles
                    last_pc = pc
                    wsnap = mem.wsync_writes
                if mem.bank == 0 and mpu.pc == PC_STARTFRAME:
                    break
                guard += 1
        for (bank, pc, gap), n in sorted(late_pc.items(), key=lambda kv: -kv[1])[:15]:
            # resolve label
            lbl = ""
            for L, ad in (_LBL0 if bank == 0 else _LBL1).items():
                if ad == pc:
                    lbl = L
                    break
            print(f"  bank{bank} pc=${pc:04X} {lbl} gap={gap}c x{n}")

    # --- Original HUD-band WSYNC count (keep as sanity) ---
    from collections import Counter
    hud_counter = Counter()
    total_counter = Counter()
    NFRAMES = 100
    for f in range(NFRAMES):
        res = run_frame_wsync()
        if res is None:
            continue
        log, total, _lines = res
        hud = hud_band_wsync(log)
        hud_counter[hud] += 1
        total_counter[total] += 1
    print(f"\n=== {NFRAMES} frames ===")
    print("HUD-band WSYNC count distribution (bank1, TopGap..HudPad):")
    for cnt, n in sorted(hud_counter.items()):
        print(f"  {cnt} WSYNC: {n} frames")
    print("total-frame WSYNC count distribution:")
    for cnt, n in sorted(total_counter.items()):
        print(f"  {cnt} WSYNC: {n} frames")
