"""Make Spark Clock's five alarm sounds. Every sound is generated here from sine waves, noise and
simple envelopes: nothing is sampled or taken from anyone, so they are the project's own and
carry no outside licence. The random noise uses a fixed seed, so the files come out the same
every time.

Writes sounds/<name>.wav: mono, 16-bit, 16 kHz, each about two to three seconds, made to be
played again and again with a short gap.

Run:  python files/spark-clock/make_sounds.py
"""

import math
import os
import random
import struct
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'sounds')
RATE = 16000
PEAK = 0.8


def silence(seconds: float):
    return [0.0] * int(RATE * seconds)


def env(n: int, attack: float = 0.005, release: float = 0.03):
    """A gate: short fade in and out so nothing clicks."""
    a, r = max(1, int(RATE * attack)), max(1, int(RATE * release))
    return [min(1.0, i / a, (n - i) / r) for i in range(n)]


def tone(freq: float, seconds: float, harmonics=((1, 1.0),), release: float = 0.03):
    n = int(RATE * seconds)
    gate = env(n, release=release)
    out = []
    for i in range(n):
        phase = 2 * math.pi * freq * i / RATE
        out.append(gate[i] * sum(amp * math.sin(phase * mult) for mult, amp in harmonics))
    norm = sum(amp for _m, amp in harmonics)
    return [x / norm for x in out]


def bell(freq: float, seconds: float, decay: float = 3.5):
    """A struck bell: inharmonic partials, each dying away on its own."""
    partials = ((1.0, 1.0, 1.0), (2.76, 0.5, 1.6), (5.4, 0.25, 2.4), (8.93, 0.12, 3.2))
    n = int(RATE * seconds)
    out = []
    for i in range(n):
        t = i / RATE
        value = sum(a * math.sin(2 * math.pi * freq * m * t) * math.exp(-decay * d * t)
                    for m, a, d in partials)
        out.append(value * min(1.0, i / (RATE * 0.002)))
    return out


def mix_into(base, extra, at: float):
    start = int(RATE * at)
    if start + len(extra) > len(base):
        base.extend([0.0] * (start + len(extra) - len(base)))
    for i, x in enumerate(extra):
        base[start + i] += x
    return base


def beacon():
    """Three short digital beeps, then a pause: plain and hard to sleep through."""
    out = []
    for _ in range(3):
        out += tone(988, 0.12, ((1, 1.0), (3, 0.25), (5, 0.1)), release=0.01)
        out += silence(0.1)
    for _ in range(3):
        out += tone(1319, 0.12, ((1, 1.0), (3, 0.25), (5, 0.1)), release=0.01)
        out += silence(0.1)
    return out + silence(0.7)


def pulse():
    """Two alternating tones, a siren with soft edges."""
    out = []
    for _ in range(3):
        out += tone(523, 0.22, ((1, 1.0), (2, 0.3)), release=0.06)
        out += tone(784, 0.22, ((1, 1.0), (2, 0.3)), release=0.06)
    return out + silence(0.8)


def chime():
    """A bell arpeggio, softer than the others."""
    out = silence(0.0)
    for k, freq in enumerate((523.25, 659.25, 783.99, 1046.5)):
        mix_into(out, bell(freq, 1.6), 0.35 * k)
    return out + silence(0.6)


def drift():
    """Three slow swells, rising: for waking up gently."""
    out = []
    for freq in (261.63, 329.63, 392.0):
        n = int(RATE * 1.2)
        swell = []
        for i in range(n):
            x = i / n
            shape = math.sin(math.pi * x) ** 2
            phase = 2 * math.pi * freq * i / RATE
            swell.append(shape * (math.sin(phase) + 0.4 * math.sin(2 * phase + 0.3)
                                  + 0.2 * math.sin(3 * phase)) / 1.6)
        out += swell
    return out + silence(0.5)


def static():
    """The house fault as a sound: a tone that tears into bursts of noise and slips between two
    pitches a little apart, like the magenta and cyan channels."""
    rng = random.Random(2026)
    out = []
    for burst in range(6):
        n = int(RATE * 0.16)
        gate = env(n, attack=0.002, release=0.01)
        a, b = 880.0, 880.0 * 1.0595          # one semitone apart
        for i in range(n):
            noise = rng.uniform(-1, 1) * (0.7 if burst % 2 else 0.25)
            phase_a = 2 * math.pi * a * i / RATE
            phase_b = 2 * math.pi * b * i / RATE
            tone_mix = 0.5 * (math.sin(phase_a) + (1 if math.sin(phase_b) > 0 else -1) * 0.5)
            sample = gate[i] * (tone_mix * (1 - 0.5 * (burst % 2)) + noise * 0.6)
            out.append(round(sample * 6) / 6)  # coarse steps: a bit-crushed edge
        out += silence(0.05 if burst % 2 else 0.12)
    return out + silence(0.8)


SOUNDS = {'beacon': beacon, 'pulse': pulse, 'chime': chime, 'drift': drift, 'static': static}


def write(name: str, samples) -> str:
    peak = max(1e-9, max(abs(x) for x in samples))
    scale = PEAK / peak
    path = os.path.join(OUT, name + '.wav')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, x * scale)) * 32767))
                               for x in samples))
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, make in SOUNDS.items():
        samples = make()
        path = write(name, samples)
        print(f"{name}: {len(samples) / RATE:.1f} s, {os.path.getsize(path) // 1024} KB")


if __name__ == '__main__':
    main()
