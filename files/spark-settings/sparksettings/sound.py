"""Sound through wpctl (PipeWire): devices by name, volume, the default, per-app volume."""

import glob
import math
import os
import re
import struct
import tempfile
import wave
from typing import Dict, List, Optional

from .core import out, run, spawn, have, xdg_config_home

TREE = "│├└─ \t"
_NODE = re.compile(r'^(\*)?\s*(\d+)\.\s+(.*?)\s*(?:\[vol:\s*([\d.]+)(\s+MUTED)?\])?\s*$')


class Node:
    def __init__(self, id_: int, name: str, volume: Optional[float], muted: bool, default: bool):
        self.id, self.name, self.volume, self.muted, self.default = id_, name, volume, muted, default


class Status:
    def __init__(self):
        self.sinks: List[Node] = []
        self.sources: List[Node] = []
        self.streams: List[Node] = []


def parse_status(text: str) -> Status:
    st = Status()
    section = None
    in_audio = False
    for raw in text.splitlines():
        line = raw.rstrip()
        bare = line.strip(TREE).strip()
        if not bare:
            continue
        if not line.startswith((' ', '│', '├', '└')):
            in_audio = bare == 'Audio'
            section = None
            continue
        if not in_audio:
            continue
        head = re.match(r'^[\s│]*[├└]─\s+(.*?):\s*$', line)
        if head:
            section = head.group(1).lower()
            continue
        if section not in ('sinks', 'sources', 'streams'):
            continue
        m = _NODE.match(line.lstrip(TREE))
        if not m:
            continue
        name = m.group(3)
        if section == 'streams':
            if re.search(r'\s[<>]\s|\[(active|paused|idle)\]', name) or '\t' in name:
                continue
            st.streams.append(Node(int(m.group(2)), name, None, False, False))
            continue
        vol = float(m.group(4)) if m.group(4) else None
        node = Node(int(m.group(2)), name, vol, bool(m.group(5)), bool(m.group(1)))
        (st.sinks if section == 'sinks' else st.sources).append(node)
    return st


def status() -> Status:
    st = parse_status(out(['wpctl', 'status']))
    for s in st.streams:
        s.volume, s.muted = get_volume(s.id)
    return st


def get_volume(id_: int):
    text = out(['wpctl', 'get-volume', str(id_)])
    m = re.search(r'Volume:\s*([\d.]+)', text)
    return (float(m.group(1)) if m else None), 'MUTED' in text


def set_default(id_: int) -> bool:
    return run(['wpctl', 'set-default', str(id_)])[0] == 0


def set_volume(id_: int, fraction: float) -> bool:
    fraction = max(0.0, min(1.5, fraction))
    return run(['wpctl', 'set-volume', str(id_), f"{fraction:.2f}"])[0] == 0


def set_mute(id_: int, muted: bool) -> bool:
    return run(['wpctl', 'set-mute', str(id_), '1' if muted else '0'])[0] == 0


def tone_file() -> str:
    """A 1 second 440 Hz tone, written once to the temporary folder."""
    path = os.path.join(tempfile.gettempdir(), 'spark-settings-tone.wav')
    if not os.path.exists(path):
        with wave.open(path, 'wb') as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(44100)
            frames = bytearray()
            for i in range(44100):
                fade = min(1.0, i / 2000, (44100 - i) / 2000)
                v = int(9000 * fade * math.sin(2 * math.pi * 440 * i / 44100))
                frames += struct.pack('<hh', v, v)
            w.writeframes(bytes(frames))
    return path


def play_tone(sink_id: Optional[int] = None) -> bool:
    if have('pw-play'):
        cmd = ['pw-play']
        if sink_id is not None:
            cmd += ['--target', str(sink_id)]
        return spawn(cmd + [tone_file()])
    if have('paplay'):
        return spawn(['paplay', tone_file()])
    return False


# ──────────────────────── Output sample rate ────────────────────────
# "Follow the track" leaves PipeWire to the system list in
# /usr/share/pipewire/pipewire.conf.d/10-sparkos-sample-rates.conf (44100 to 192000). A fixed
# rate is one drop-in of the user's own, read after that file, that pins the device to it.
FALLBACK_RATES = [44100, 48000, 96000, 192000]
KNOWN_RATES = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 88200, 96000, 176400, 192000,
               352800, 384000]
RATE_FILE = '50-sample-rates.conf'
RATE_HEADER = """\
# Written by Spark Settings (Sound, Output sample rate). Delete this file, or choose "Follow
# the track" there, to go back to the system's list of rates.
#
# This pins the sound output to one rate. Windows apps run by Spark Run (Amazon Music Ultra HD,
# for example) only offer hi-res when the device already runs at that rate. Everything else
# is resampled to it.
"""


def rate_file() -> str:
    return os.path.join(xdg_config_home(), 'pipewire', 'pipewire.conf.d', RATE_FILE)


def rate_label(rate: int) -> str:
    """44100 -> '44.1 kHz', 96000 -> '96 kHz'."""
    khz = f"{rate / 1000:.3f}".rstrip('0').rstrip('.')
    return f"{khz} kHz"


def parse_stream(text: str):
    """One /proc/asound/cardN/stream0: (the device's name line, its playback rates, sorted).
    Capture rates are left out. A range such as '44100 - 192000 (continuous)' gives the usual
    rates inside it."""
    lines = text.splitlines()
    name = lines[0].strip() if lines else ''
    rates = set()
    in_playback = False
    for raw in lines[1:]:
        line = raw.strip()
        if line.startswith('Playback:'):
            in_playback = True
        elif line.startswith('Capture:'):
            in_playback = False
        elif in_playback and line.startswith('Rates:'):
            body = line[len('Rates:'):]
            span = re.search(r'(\d+)\s*-\s*(\d+)', body)
            if span:
                low, high = int(span.group(1)), int(span.group(2))
                rates.update(r for r in KNOWN_RATES if low <= r <= high)
            else:
                rates.update(int(n) for n in re.findall(r'\d+', body))
    return name, sorted(r for r in rates if 8000 <= r <= 768000)


_GENERIC = {'usb', 'audio', 'analog', 'stereo', 'digital', 'output', 'speakers', 'headphones',
            'surround', 'pro', 'duplex', 'full', 'speed', 'high', 'low', 'the', 'and'}


def _words(text: str):
    return {w for w in re.findall(r'[a-z0-9]+', text.lower()) if len(w) >= 3 and w not in _GENERIC}


def device_rates(device_name: str = '', root: str = '/proc/asound') -> List[int]:
    """The playback rates the output device supports. The device is matched to its card by the
    words they share (wpctl's name for it and the card's name line); with no match, or nothing
    readable, the usual four."""
    best, best_score = [], 0
    for path in sorted(glob.glob(os.path.join(root, 'card*', 'stream0'))):
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                name, rates = parse_stream(f.read())
        except OSError:
            continue
        score = len(_words(name) & _words(device_name))
        if rates and score > best_score:
            best, best_score = rates, score
    return best or list(FALLBACK_RATES)


def read_rate(path: Optional[str] = None) -> int:
    """The fixed rate in the user's file, 0 when there is none (follow the track)."""
    try:
        with open(path or rate_file(), encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return 0
    m = re.search(r'^\s*default\.clock\.rate\s*=\s*(\d+)', text, re.M)
    return int(m.group(1)) if m else 0


def write_rate(rate: int, path: Optional[str] = None) -> bool:
    """Pin the output to `rate`, or with 0 remove the file so PipeWire follows the track."""
    path = path or rate_file()
    try:
        if rate <= 0:
            if os.path.exists(path):
                os.remove(path)
            return True
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            f.write(f"{RATE_HEADER}context.properties = {{\n"
                    f"    default.clock.rate = {rate}\n"
                    f"    default.clock.allowed-rates = [ {rate} ]\n}}\n")
        os.replace(path + '.tmp', path)
        return True
    except OSError:
        return False


def apply_rate(rate: int) -> bool:
    """Make the running PipeWire use it now (0 gives the choice back to PipeWire)."""
    return run(['pw-metadata', '-n', 'settings', '0', 'clock.force-rate', str(max(0, rate))])[0] == 0
