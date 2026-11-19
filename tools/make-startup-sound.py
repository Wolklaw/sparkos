#!/usr/bin/env python3
"""Generates the SparkOS startup sound: a hammer on steel in a cave.

Every sample is synthesised here from sine waves and seeded noise, so the sound is
original work with no recording in it. Re-running this script gives the identical file.

    python3 tools/make-startup-sound.py [out.wav]

Needs numpy. Writes 48 kHz 16-bit stereo WAV.
"""
import sys
import wave

import numpy as np

RATE = 48_000
LENGTH = 5.2  # seconds, including the cave tail
SEED = 2026
OUT = sys.argv[1] if len(sys.argv) > 1 else "files/system/usr/share/sounds/sparkos/startup.wav"

rng = np.random.default_rng(SEED)
n_total = int(LENGTH * RATE)
t_all = np.arange(n_total) / RATE

# Partial ratios of a free steel bar (the classic anvil and bar modes), plus the
# amplitude and how fast each partial dies away (higher modes ring shorter).
BAR_RATIOS = np.array([1.0, 2.756, 5.404, 8.933, 13.344, 18.64])
BAR_AMPS = np.array([1.0, 0.62, 0.40, 0.24, 0.14, 0.08])
BAR_DECAY = np.array([0.95, 0.72, 0.52, 0.36, 0.26, 0.18])  # seconds to fall by 1/e


def one_pole_lowpass(x, cutoff_hz):
    a = np.exp(-2 * np.pi * cutoff_hz / RATE)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # short signals only, fine in pure numpy loops
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def strike(base_hz, force):
    """One hammer blow: a short click, a dull thump, and the ringing steel."""
    dur = 4.5  # long enough for the ring to die out on its own (no cut-off click)
    n = int(dur * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)

    # Ringing steel, slightly detuned per blow so repeated strikes don't sound pasted
    for ratio, amp, decay in zip(BAR_RATIOS, BAR_AMPS, BAR_DECAY):
        f = base_hz * ratio * (1 + rng.normal(0, 0.002))
        if f > RATE / 2.2:
            continue
        phase = rng.uniform(0, 2 * np.pi)
        # harder blows excite the high modes more
        a = amp * (force ** (0.6 + 0.25 * ratio / BAR_RATIOS[-1]))
        out += a * np.exp(-t / (decay * (0.8 + 0.2 * force))) * np.sin(2 * np.pi * f * t + phase)

    # The anvil body: a lower, softer ring under the bar
    body_f = base_hz * 0.47
    out += 0.35 * force * np.exp(-t / 0.6) * np.sin(2 * np.pi * body_f * t)

    # Impact click: a few milliseconds of bright noise
    click_n = int(0.006 * RATE)
    click = rng.normal(0, 1, click_n) * np.exp(-np.arange(click_n) / (0.0012 * RATE))
    out[:click_n] += 0.9 * force * click

    # Hammer thump: a low knock that is over in a tenth of a second
    out += 0.55 * force * np.exp(-t / 0.035) * np.sin(2 * np.pi * 95 * t)

    # Soft attack over 0.4 ms to avoid a digital tick, and a gentle fade at the very end
    ramp = int(0.0004 * RATE)
    out[:ramp] *= np.linspace(0, 1, ramp)
    tail = int(0.5 * RATE)
    out[-tail:] *= np.cos(np.linspace(0, np.pi / 2, tail)) ** 2
    return out


def cave_impulse(rt60=2.6):
    """A dark, rocky room: a few early echoes off near walls, then a long dim tail."""
    n = int(rt60 * 1.2 * RATE)
    t = np.arange(n) / RATE
    tail = rng.normal(0, 1, n) * np.exp(-6.91 * t / rt60)  # -60 dB at rt60
    tail = one_pole_lowpass(tail, 2200)  # stone soaks up the highs
    ir = np.zeros(n)
    # Early echoes off uneven rock: irregular delays, each smeared over a couple of
    # milliseconds so they don't flutter
    for delay_ms, gain in [(23, 0.30), (37, 0.22), (58, 0.17), (89, 0.12), (131, 0.08)]:
        i = int(delay_ms * RATE / 1000)
        smear = int(0.0025 * RATE)
        ir[i:i + smear] += gain * rng.normal(0, 1, smear) * np.exp(-np.arange(smear) / (0.0008 * RATE))
    onset = int(0.015 * RATE)
    ir[onset:] += 0.05 * tail[: n - onset]
    return ir


def convolve(a, b):
    size = 1 << int(np.ceil(np.log2(len(a) + len(b) - 1)))
    return np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)[: len(a) + len(b) - 1]


# The rhythm: three working blows, a short breath, then the heavy final one.
BLOWS = [  # (time s, base Hz, force)
    (0.00, 612.0, 0.50),
    (0.46, 618.0, 0.44),
    (0.92, 609.0, 0.54),
    (1.62, 596.0, 1.00),
]

dry = np.zeros(n_total)
for at, hz, force in BLOWS:
    s = strike(hz, force)
    i = int(at * RATE)
    end = min(n_total, i + len(s))
    dry[i:end] += s[: end - i]

# Stereo: the same cave heard from two slightly different spots. The echo sits under the
# blows (about a third of their energy) so each strike stays distinct.
def rms(v):
    return float(np.sqrt(np.mean(v ** 2))) + 1e-12

mix = []
for _ in range(2):
    wet = convolve(dry, cave_impulse())[:n_total]
    wet *= 0.36 * rms(dry) / rms(wet)
    mix.append(dry + wet)
stereo = np.stack(mix, axis=1)

# Fade the tail out, then normalise to -3 dBFS
fade = int(0.9 * RATE)
stereo[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
stereo *= 10 ** (-3 / 20) / np.max(np.abs(stereo))

pcm = (stereo * 32767).astype("<i2")
with wave.open(OUT, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(pcm.tobytes())

print(f"wrote {OUT}: {LENGTH:.1f} s, {RATE} Hz stereo, peak -3 dBFS, seed {SEED}")
