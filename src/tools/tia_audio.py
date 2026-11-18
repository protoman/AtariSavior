#!/usr/bin/env python3
"""TIA audio model: per-frame AUDC/AUDF/AUDV -> 16-bit mono PCM.

Each channel divides the 31.4 kHz audio clock by AUDF+1 and steps a waveform pattern (pure
divider, 4/5/9-bit polynomial counter), scaled by AUDV. The registers are sampled once per
frame (the game's sound engine writes them once a frame). The polynomial taps are the
usual ones; pitches are exact, noise timbre is close rather than bit-identical.
"""
import struct
import wave

import numpy as np

AUDIO_CLOCK = 3579545 / 114          # NTSC
RATE = 48000


def lfsr(bits, tap):
    """Maximal-length LFSR (x^bits + x^tap + 1): one full period of output bits."""
    s, out = 1, []
    for _ in range((1 << bits) - 1):
        out.append(s & 1)
        fb = (s ^ (s >> tap)) & 1
        s = (s >> 1) | (fb << (bits - 1))
    return np.array(out, dtype=np.uint8)


P4, P5, P9 = lfsr(4, 1), lfsr(5, 2), lfsr(9, 4)
for _p, _n in ((P4, 15), (P5, 31), (P9, 511)):
    assert len(_p) == _n and 0 < _p.sum() < _n

D31 = np.array([0] * 13 + [1] * 18, dtype=np.uint8)
D2 = np.array([0, 1], dtype=np.uint8)
D6 = np.array([0, 0, 0, 1, 1, 1], dtype=np.uint8)
ONE = np.array([1], dtype=np.uint8)
# AUDC -> (pattern, extra clock divider)
WAVES = {0: (ONE, 1), 1: (P4, 1), 2: (P4, 15), 3: (P5, 1), 4: (D2, 1), 5: (D2, 1),
         6: (D31, 1), 7: (P5, 1), 8: (P9, 1), 9: (P5, 1), 10: (D31, 1), 11: (ONE, 1),
         12: (D2, 3), 13: (D2, 3), 14: (D31, 3), 15: (P5, 3)}


class Channel:
    def __init__(self):
        self.div = 0
        self.idx = 0
        self.sub = 0

    def ticks(self, c, f, v, n):
        pat, mul = WAVES[c & 15]
        top = (f & 31) + 1
        out = np.empty(n, dtype=np.float32)
        d, i, s = self.div, self.idx, self.sub
        amp = (v & 15) / 15.0
        lp = len(pat)
        i %= lp                              # the waveform may have changed
        for k in range(n):
            d += 1
            if d >= top:
                d = 0
                s += 1
                if s >= mul:
                    s = 0
                    i += 1
                    if i >= lp:
                        i = 0
            out[k] = pat[i]
        self.div, self.idx, self.sub = d, i, s
        return out * amp


class Synth:
    def __init__(self, fps=60):
        self.ch = (Channel(), Channel())
        self.spf = RATE // fps
        self.tpf = AUDIO_CLOCK / fps
        self.t = 0.0
        self.chunks = []

    def frame(self, regs):
        """regs = (AUDC0, AUDF0, AUDV0, AUDC1, AUDF1, AUDV1) or None for silence."""
        if regs is None or (regs[2] == 0 and regs[5] == 0):
            self.chunks.append(np.zeros(self.spf, dtype=np.float32))
            return
        n = int(self.t + self.tpf) - int(self.t)
        self.t += self.tpf
        a = self.ch[0].ticks(regs[0], regs[1], regs[2], n)
        b = self.ch[1].ticks(regs[3], regs[4], regs[5], n)
        mix = (a + b) * 0.25
        idx = (np.arange(self.spf) * n // self.spf).astype(int)
        self.chunks.append(mix[idx])

    def write(self, path):
        x = np.concatenate(self.chunks)
        # TIA output is unipolar: take the DC out with a one-pole high-pass
        y = np.empty_like(x)
        prev_x = prev_y = 0.0
        for k, s in enumerate(x):
            prev_y = s - prev_x + 0.995 * prev_y
            prev_x = s
            y[k] = prev_y
        pcm = np.clip(y * 32767, -32767, 32767).astype("<i2")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
