"""Sound through wpctl (PipeWire): devices by name, volume, the default, per-app volume."""

import math
import os
import re
import struct
import tempfile
import wave
from typing import Dict, List, Optional

from .core import out, run, spawn, have

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
