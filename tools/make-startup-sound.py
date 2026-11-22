#!/usr/bin/env python3
"""Generates the SparkOS startup sound: a hammer ringing on an anvil.

Every sample is synthesised here from sine waves and seeded noise, so the sound is
original work with no recording in it. Re-running this script gives the identical file.

    python3 tools/make-startup-sound.py [out.wav] [--variant arc|zap|cave|bright|heavy|forge]   (default: arc)

A real anvil "TING" is high and bright: a sharp metallic attack, then a long ring made of
several partials that are not in a musical ratio. The forge rhythm comes from the hammer
bouncing: a hard blow, then a lighter tap as it rebounds. Needs numpy; writes 48 kHz 16-bit
stereo WAV.
"""
import sys
import wave

import numpy as np

RATE = 48_000
SEED = 2026

args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = args[0] if args else "files/system/usr/share/sounds/sparkos/startup.wav"
VARIANT = "arc"  # the approved startup sound (2026-11-20): electric zaps only
if "--variant" in sys.argv:
    VARIANT = sys.argv[sys.argv.index("--variant") + 1]

rng = np.random.default_rng(SEED)

# Partials of a steel anvil face, relative to its lowest strong mode. Not harmonic, which is
# what makes it sound like struck steel rather than a note. (amplitude, decay seconds)
ANVIL = [
    (1.000, 1.00, 2.2),
    (1.594, 0.75, 1.8),
    (2.136, 0.60, 1.5),
    (2.296, 0.50, 1.4),
    (2.653, 0.42, 1.1),
    (3.360, 0.30, 0.8),
    (4.120, 0.22, 0.6),
    (5.270, 0.14, 0.4),
]

VARIANTS = {
    # base Hz: pitch of the ring; bounce: level of the rebound tap; room: echo level;
    # blows: (time s, force, with bounce)
    "bright": dict(base=1480.0, bounce=0.42, room=0.16, rt60=1.1, length=4.2,
                   blows=[(0.00, 0.80, True), (0.52, 0.72, True), (1.04, 0.85, True), (1.72, 1.00, False)]),
    "heavy":  dict(base=1120.0, bounce=0.35, room=0.22, rt60=1.5, length=4.6,
                   blows=[(0.00, 0.85, True), (0.62, 0.80, True), (1.30, 1.00, False)]),
    "forge":  dict(base=1660.0, bounce=0.50, room=0.12, rt60=0.9, length=3.8,
                   blows=[(0.00, 0.75, True), (0.40, 0.70, True), (0.80, 0.78, True), (1.20, 0.72, True), (1.75, 1.00, False)]),
    # Slow and deliberate, in a big rocky space: about a second between blows, and each
    # ting comes back off the walls as distinct echoes (echo: list of (delay s, level))
    "cave":   dict(base=1420.0, bounce=0.38, room=0.30, rt60=2.6, length=6.4,
                   echo=[(0.26, 0.34), (0.52, 0.17), (0.78, 0.08)],
                   blows=[(0.00, 0.80, True), (1.15, 0.76, True), (2.30, 0.84, True), (3.60, 1.00, False)]),
}
# The same cave forge, with electric "bzzzt"s: every blow throws sparks that crackle, and the
# final blow lets out a long, sizzling arc. zaps: (time s, length s, level).
VARIANTS["zap"] = dict(VARIANTS["cave"], length=6.8,
                       zaps=[(0.03, 0.30, 0.55), (1.18, 0.32, 0.55), (2.33, 0.34, 0.6), (3.63, 1.30, 0.95)])
# Electric arcs only, on the same beat: no anvil.
VARIANTS["arc"] = dict(VARIANTS["zap"], blows=[], room=0.22)
V = VARIANTS[VARIANT]


def one_pole_highpass(x, cutoff_hz):
    a = np.exp(-2 * np.pi * cutoff_hz / RATE)
    y = np.empty_like(x)
    prev_x = prev_y = 0.0
    for i, v in enumerate(x):
        prev_y = a * (prev_y + v - prev_x)
        prev_x = v
        y[i] = prev_y
    return y


def one_pole_lowpass(x, cutoff_hz):
    a = np.exp(-2 * np.pi * cutoff_hz / RATE)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def ting(base_hz, force, dur=3.4):
    """One hammer blow on the anvil face: a hard, bright click and the steel ringing."""
    n = int(dur * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for ratio, amp, decay in ANVIL:
        f = base_hz * ratio * (1 + rng.normal(0, 0.0015))
        if f > RATE / 2.3:
            continue
        # a harder blow lights up the upper partials more, and a pair of very close
        # frequencies per partial gives real steel's slow shimmer (beating)
        a = amp * force ** (0.7 + 0.15 * ratio)
        for detune, share in ((0.0, 0.7), (rng.uniform(1.5, 4.0), 0.3)):
            phase = rng.uniform(0, 2 * np.pi)
            out += share * a * np.exp(-t / decay) * np.sin(2 * np.pi * (f + detune) * t + phase)

    # The strike: 3 ms of hard, bright noise (steel on steel), no low thump
    k = int(0.003 * RATE)
    click = one_pole_highpass(rng.normal(0, 1, k), 2500) * np.exp(-np.arange(k) / (0.0006 * RATE))
    out[:k] += 1.6 * force * click

    ramp = int(0.0002 * RATE)
    out[:ramp] *= np.linspace(0, 1, ramp)
    fade = int(0.4 * RATE)
    out[-fade:] *= np.cos(np.linspace(0, np.pi / 2, fade)) ** 2
    return out


def bzzt(length, level):
    """An electric arc: a harsh buzz that wobbles in pitch, chopped into crackles, with
    pops of static on top. Bright and loud at first, sizzling away at the end."""
    n = int(length * RATE)
    t = np.arange(n) / RATE
    # buzz: a square-ish wave around 110-140 Hz whose pitch wanders, plus its 3rd harmonic
    f = 118 + 14 * np.sin(2 * np.pi * 7.5 * t) + 6 * rng.normal(0, 1, n).cumsum() / np.sqrt(np.arange(1, n + 1))
    phase = 2 * np.pi * np.cumsum(f) / RATE
    buzz = np.tanh(4 * np.sin(phase)) + 0.35 * np.tanh(3 * np.sin(3.01 * phase))
    # chop it on and off at random, 25-60 times a second: that's what makes it crackle
    gate = np.zeros(n)
    i = 0
    while i < n:
        on = int(rng.uniform(0.006, 0.030) * RATE)
        off = int(rng.uniform(0.002, 0.012) * RATE)
        gate[i:i + on] = rng.uniform(0.55, 1.0)
        i += on + off
    gate = one_pole_lowpass(gate, 900)
    # static pops: sparse, very bright clicks, thickest at the start
    pops = np.zeros(n)
    count = int(140 * length)
    where = (rng.power(0.6, count) * n).astype(int)  # bunched towards the start
    pops[np.clip(where, 0, n - 1)] = rng.uniform(-1, 1, count)
    pops = one_pole_highpass(pops, 3000)
    hiss = one_pole_highpass(rng.normal(0, 1, n), 4500)
    env = np.exp(-t / (0.35 * length)) * np.minimum(1, t / 0.004)
    sig = (0.55 * buzz * gate + 2.2 * pops + 0.12 * hiss * gate) * env
    fade = int(min(0.15, length / 3) * RATE)
    sig[-fade:] *= np.linspace(1, 0, fade) ** 2
    return level * sig / (np.max(np.abs(sig)) + 1e-9)


def room(rt60):
    """A small stone room: a couple of quick reflections and a short, slightly dark tail."""
    n = int(rt60 * 1.1 * RATE)
    t = np.arange(n) / RATE
    ir = np.zeros(n)
    for ms, g in ((11, 0.35), (23, 0.22), (37, 0.15)):
        i = int(ms * RATE / 1000)
        s = int(0.0015 * RATE)
        ir[i:i + s] += g * rng.normal(0, 1, s) * np.exp(-np.arange(s) / (0.0005 * RATE))
    tail = one_pole_lowpass(rng.normal(0, 1, n) * np.exp(-6.91 * t / rt60), 6000)
    ir += 0.04 * tail
    # distinct echoes off far walls, each a little duller than the last
    for delay, level in V.get("echo", []):
        i = int(delay * RATE)
        if i < n:
            s = int(0.004 * RATE)
            ir[i:i + s] += level * 8 * one_pole_lowpass(rng.normal(0, 1, s), 3500) * np.exp(-np.arange(s) / (0.001 * RATE))
    return ir


def convolve(a, b):
    size = 1 << int(np.ceil(np.log2(len(a) + len(b) - 1)))
    return np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)[: len(a) + len(b) - 1]


n_total = int(V["length"] * RATE)
dry = np.zeros(n_total)


def place(sig, at):
    i = int(at * RATE)
    end = min(n_total, i + len(sig))
    if i < n_total:
        dry[i:end] += sig[: end - i]


for at, force, bounce in V["blows"]:
    hz = V["base"] * (1 + rng.normal(0, 0.004))
    place(ting(hz, force), at)
    if bounce:
        # the hammer rebounds and taps the face again, lighter and a touch higher
        place(ting(hz * 1.01, force * V["bounce"]), at + rng.uniform(0.085, 0.11))

for at, length, level in V.get("zaps", []):
    place(bzzt(length, level), at)


def rms(v):
    return float(np.sqrt(np.mean(v ** 2))) + 1e-12


mix = []
for _ in range(2):
    wet = convolve(dry, room(V["rt60"]))[:n_total]
    wet *= V["room"] * rms(dry) / rms(wet)
    mix.append(dry + wet)
stereo = np.stack(mix, axis=1)

fade = int(0.6 * RATE)
stereo[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
stereo *= 10 ** (-3 / 20) / np.max(np.abs(stereo))

pcm = (stereo * 32767).astype("<i2")
with wave.open(OUT, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(pcm.tobytes())

print(f"wrote {OUT}: variant {VARIANT}, {V['length']:.1f} s, {RATE} Hz stereo, peak -3 dBFS, seed {SEED}")
